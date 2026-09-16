import unittest
from types import SimpleNamespace

from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
from processor.import_processor.nodes.node_travel_metadata import NodeTravelMetadata
from processor.import_processor.nodes.node_bge_embedding import NodeBGEEmbedding
from processor.import_processor.nodes.node_import_milvus import NodeImportMilvus
from processor.import_processor.exceptions import MilvusError
from processor.query_processor.main_graph import KBQueryWorkflow
from processor.query_processor.nodes.node_rrf import NodeRrf
from processor.query_processor.nodes.node_web_search_mcp import NodeWebSearchMcp
from utils.milvus_utils import build_travel_expr


class TravelAdaptationTests(unittest.TestCase):
    def test_markdown_metadata_is_attached_to_chunks(self):
        content = """# 成都景点推荐
## 元数据
- 内容类型：景点介绍
- 城市：成都
- 景点名称：成都景点推荐
- 主题：城市漫游

## 目的地概览
熊猫基地适合亲子游客。
"""
        state = {
            "file_title": "成都景点推荐",
            "md_content": content,
        }
        result = NodeDocumentSplit().process(state)
        self.assertEqual(result["document_metadata"]["city"], "成都")
        self.assertEqual(result["chunks"][0]["content_type"], "景点介绍")
        self.assertEqual(result["chunks"][0]["entity_name"], "成都景点推荐")

    def test_travel_metadata_node_sets_entity_name(self):
        state = {
            "file_title": "成都线路推荐",
            "document_metadata": {"city": "成都", "route_name": "成都三日游"},
            "chunks": [{"content": "行程内容", "title": "## 第一天"}],
        }
        result = NodeTravelMetadata().process(state)
        self.assertEqual(result["entity_name"], "成都三日游")
        self.assertEqual(result["chunks"][0]["city"], "成都")

    def test_embedding_text_contains_travel_context(self):
        text = NodeBGEEmbedding._embedding_text(
            {
                "city": "成都",
                "content_type": "景点介绍",
                "entity_name": "熊猫基地",
                "title": "## 适合人群",
                "content": "适合亲子游客。",
            }
        )
        self.assertIn("成都 景点介绍 熊猫基地", text)
        self.assertIn("适合亲子游客", text)

    def test_empty_travel_filter_means_full_collection(self):
        self.assertIsNone(build_travel_expr())
        self.assertEqual(
            build_travel_expr(cities=["成都"], entities=["熊猫基地"]),
            '(city in ["成都"]) or (entity_name in ["熊猫基地"])',
        )

    def test_rrf_ignores_invalid_hits_and_uses_milvus_id_fallback(self):
        hits = NodeRrf._normalise_hits(
            [
                None,
                {"id": 7, "entity": {"content": "成都景点"}},
                {"entity": {"chunk_id": 7, "content": "重复命中"}},
                {"entity": {"content": "缺少主键"}},
            ]
        )
        self.assertEqual([hit["chunk_id"] for hit in hits], [7, 7])
        merged = NodeRrf()._rrf_merge([(hits, 1.0)], max_results=5)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][0]["chunk_id"], 7)

    def test_web_search_parser_keeps_only_usable_pages(self):
        result = SimpleNamespace(
            content=[
                SimpleNamespace(
                    text='{"pages": [{"title": "成都文旅", "url": "https://example.com", "snippet": "熊猫基地"}, {"title": "空结果"}]}'
                )
            ]
        )
        self.assertEqual(NodeWebSearchMcp._parse_result(result)[0]["title"], "成都文旅")
        self.assertEqual(NodeWebSearchMcp._parse_result(result)[0]["snippet"], "熊猫基地")

    def test_query_graph_keeps_three_retrieval_branches(self):
        nodes = KBQueryWorkflow().compile().get_graph().nodes
        self.assertTrue(
            {
                "node_search_embedding",
                "node_search_embedding_hyde",
                "node_web_search_mcp",
                "node_rrf",
                "node_rerank",
            }.issubset(nodes)
        )

    def test_milvus_insert_rejects_oversized_travel_content(self):
        with self.assertRaises(MilvusError):
            NodeImportMilvus()._insert(
                object(),
                [{"content": "x" * 65536}],
            )

    def test_milvus_reimport_filter_scopes_same_travel_document(self):
        filter_expression = NodeImportMilvus._build_document_filter(
            {
                "file_title": "住宿推荐",
                "city": "成都",
                "entity_name": "成都住宿推荐",
            }
        )
        self.assertEqual(
            filter_expression,
            "file_title == '住宿推荐' and city == '成都' and entity_name == '成都住宿推荐'",
        )


if __name__ == "__main__":
    unittest.main()
