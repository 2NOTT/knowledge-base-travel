import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langgraph.constants import END

from config.minio_config import minio_config
from processor.import_processor.exceptions import FileProcessingError, StateFieldError
from processor.import_processor.import_config import ImportConfig
from processor.import_processor.main_graph import KBImportWorkflow
from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
from processor.import_processor.nodes.node_entry import NodeEntry
from processor.import_processor.nodes.node_md_img import NodeMDImg
from processor.import_processor.nodes.node_pdf_to_md import NodePDFToMD
from utils.mongo_history_utils import get_recent_messages
from utils.task_utils import (
    add_running_task,
    clear_task,
    get_running_task_list,
    remove_running_task,
)


class ImportRegressionTests(unittest.TestCase):
    def test_import_routes_pdf_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "manual.PDF"
            md_path = Path(temp_dir) / "manual.md"
            pdf_path.touch()
            md_path.touch()

            pdf_state = NodeEntry().process({"import_file_path": str(pdf_path)})
            md_state = NodeEntry().process({"import_file_path": str(md_path)})

        self.assertTrue(pdf_state["is_pdf_read_enabled"])
        self.assertFalse(pdf_state["is_md_read_enabled"])
        self.assertEqual(KBImportWorkflow.route_after_entry(pdf_state), "node_pdf_to_md")
        self.assertFalse(md_state["is_pdf_read_enabled"])
        self.assertTrue(md_state["is_md_read_enabled"])
        self.assertEqual(KBImportWorkflow.route_after_entry(md_state), "node_md_img")
        self.assertEqual(KBImportWorkflow.route_after_entry({}), END)

    def test_import_graph_compiles_with_all_nodes(self):
        nodes = KBImportWorkflow().graph.get_graph().nodes

        self.assertTrue(
            {
                "node_entry",
                "node_pdf_to_md",
                "node_md_img",
                "node_document_split",
                "node_travel_metadata",
                "node_bge_embedding",
                "node_import_milvus",
            }.issubset(nodes)
        )

    def test_markdown_image_replacement_returns_content(self):
        content = "before\n![old](images/panel.png)\nafter"
        image_info = {"panel.png": ("控制面板", "http://minio/bucket/panel.png")}

        result = NodeMDImg()._process_md_file(content, image_info)

        self.assertEqual(result, "before\n![控制面板](http://minio/bucket/panel.png)\nafter")

    def test_markdown_without_images_reaches_document_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            md_path = Path(temp_dir) / "chengdu.md"
            md_path.write_text("# 成都景点\n\n熊猫基地适合亲子游客。", encoding="utf-8")

            state = NodeEntry().process({"import_file_path": str(md_path)})
            state = NodeMDImg().process(state)
            result = NodeDocumentSplit().process(state)

        self.assertIn("熊猫基地", result["md_content"])
        self.assertTrue(result["chunks"])

    def test_recent_messages_returns_latest_in_chronological_order(self):
        class FakeCursor:
            def __init__(self):
                self.documents = [
                    {"session_id": "s1", "ts": 1},
                    {"session_id": "s1", "ts": 2},
                    {"session_id": "s1", "ts": 3},
                ]

            def sort(self, field, direction):
                self.documents.sort(key=lambda item: item[field], reverse=direction < 0)
                return self

            def limit(self, value):
                self.documents = self.documents[:value]
                return self

            def __iter__(self):
                return iter(self.documents)

        class FakeCollection:
            def find(self, _query):
                return FakeCursor()

        fake_tool = SimpleNamespace(chat_message=FakeCollection())
        with patch(
            "utils.mongo_history_utils.get_history_mongo_tool",
            return_value=fake_tool,
        ):
            result = get_recent_messages("s1", limit=2)

        self.assertEqual([item["ts"] for item in result], [2, 3])

    def test_failed_node_is_removed_from_running_tasks(self):
        task_id = "test-failed-node-status"
        add_running_task(task_id, "node_import_milvus")
        remove_running_task(task_id, "node_import_milvus")

        self.assertEqual(get_running_task_list(task_id), [])
        clear_task(task_id)

    def test_minio_image_url_contains_path_separator(self):
        client = SimpleNamespace(fput_object=lambda **kwargs: None)
        with (
            tempfile.NamedTemporaryFile() as image_file,
            patch.object(minio_config, "endpoint", "minio:9000"),
            patch.object(minio_config, "bucket_name", "knowledge-base"),
        ):
            result = NodeMDImg()._upload_to_minio(client, image_file.name, "images/panel.png")

        self.assertEqual(result, "http://minio:9000/knowledge-base/images/panel.png")

    def test_short_sections_with_different_titles_do_not_merge(self):
        node = NodeDocumentSplit(config=ImportConfig(min_content_length=500))
        sections = [
            {"title": "# 第一章", "content": "第一章内容", "file_title": "手册"},
            {"title": "# 第二章", "content": "第二章内容", "file_title": "手册"},
        ]

        result = node._step_4_refine_chunks(sections)

        self.assertEqual(len(result), 2)
        self.assertEqual(
            [chunk["parent_title"] for chunk in result],
            ["# 第一章", "# 第二章"],
        )

    def test_document_split_reports_missing_field(self):
        with self.assertRaises(StateFieldError):
            NodeDocumentSplit()._step_1_get_inputs({"md_content": "content"})

    def test_mineru_create_request_has_timeout(self):
        config = ImportConfig(mineru_base_url="https://mineru.example", mineru_api_token="token")
        node = NodePDFToMD(config=config)
        response = SimpleNamespace(status_code=500)

        with (
            tempfile.NamedTemporaryFile(suffix=".pdf") as pdf_file,
            patch(
                "processor.import_processor.nodes.node_pdf_to_md.requests.post",
                return_value=response,
            ) as post,
            self.assertRaises(FileProcessingError),
        ):
            node._step_2_upload_and_poll(Path(pdf_file.name))

        self.assertEqual(post.call_args.kwargs["timeout"], (10, 30))


if __name__ == "__main__":
    unittest.main()
