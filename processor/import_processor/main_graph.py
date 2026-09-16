"""知识库导入工作流。"""

import logging

from langgraph.constants import END
from langgraph.graph import StateGraph

from processor.import_processor.base import setup_logging
from processor.import_processor.nodes.node_bge_embedding import NodeBGEEmbedding
from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
from processor.import_processor.nodes.node_entry import NodeEntry
from processor.import_processor.nodes.node_import_milvus import NodeImportMilvus
from processor.import_processor.nodes.node_md_img import NodeMDImg
from processor.import_processor.nodes.node_pdf_to_md import NodePDFToMD
from processor.import_processor.nodes.node_travel_metadata import NodeTravelMetadata
from processor.import_processor.state import ImportGraphState


class KBImportWorkflow:
    """构建并运行知识库导入流程。"""

    def __init__(self):
        self._compiled_graph = None

    @property
    def graph(self):
        if self._compiled_graph is None:
            self._compiled_graph = self.build_graph()
        return self._compiled_graph

    def build_graph(self):
        graph = StateGraph(ImportGraphState)

        graph.add_node("node_entry", NodeEntry())
        graph.add_node("node_pdf_to_md", NodePDFToMD())
        graph.add_node("node_md_img", NodeMDImg())
        graph.add_node("node_document_split", NodeDocumentSplit())
        graph.add_node("node_travel_metadata", NodeTravelMetadata())
        graph.add_node("node_bge_embedding", NodeBGEEmbedding())
        graph.add_node("node_import_milvus", NodeImportMilvus())

        graph.set_entry_point("node_entry")
        graph.add_conditional_edges(
            "node_entry",
            self.route_after_entry,
            {
                "node_pdf_to_md": "node_pdf_to_md",
                "node_md_img": "node_md_img",
                END: END,
            },
        )

        graph.add_edge("node_pdf_to_md", "node_md_img")
        graph.add_edge("node_md_img", "node_document_split")
        graph.add_edge("node_document_split", "node_travel_metadata")
        graph.add_edge("node_travel_metadata", "node_bge_embedding")
        graph.add_edge("node_bge_embedding", "node_import_milvus")
        graph.add_edge("node_import_milvus", END)

        return graph.compile()

    @staticmethod
    def route_after_entry(state: ImportGraphState) -> str:
        if state.get("is_pdf_read_enabled"):
            return "node_pdf_to_md"
        if state.get("is_md_read_enabled"):
            return "node_md_img"
        return END

    def run(self, state: ImportGraphState, stream: bool = False):
        if stream:
            return self.graph.stream(state)
        return self.graph.invoke(state)


if __name__ == "__main__":
    setup_logging()
    init_state = {
        "import_file_path": r"D:\doc\H3C LA2608室内无线网关 用户手册-6W100-整本手册.pdf",
        "file_dir": r"D:\output",
    }
    workflow = KBImportWorkflow()
    logging.getLogger().info(workflow.run(init_state))
