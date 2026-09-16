"""旅游知识库查询工作流。"""

from dotenv import load_dotenv
from langgraph.constants import END
from langgraph.graph import StateGraph

from processor.query_processor.nodes.node_answer_output import NodeAnswerOutput
from processor.query_processor.nodes.node_rerank import NodeRerank
from processor.query_processor.nodes.node_rrf import NodeRrf
from processor.query_processor.nodes.node_search_embedding import NodeSearchEmbedding
from processor.query_processor.nodes.node_search_embedding_hyde import NodeSearchEmbeddingHyde
from processor.query_processor.nodes.node_travel_query_prepare import NodeTravelQueryPrepare
from processor.query_processor.nodes.node_web_search_mcp import NodeWebSearchMcp
from processor.query_processor.state import QueryGraphState

load_dotenv()


class KBQueryWorkflow:
    """保留课程项目的三路检索、RRF、Reranker 和生成链路。"""

    def __init__(self):
        self.workflow = StateGraph(QueryGraphState)
        self.node_travel_query_prepare = NodeTravelQueryPrepare()
        self.node_search_embedding = NodeSearchEmbedding()
        self.node_search_embedding_hyde = NodeSearchEmbeddingHyde()
        self.node_web_search_mcp = NodeWebSearchMcp()
        self.node_rrf = NodeRrf()
        self.node_rerank = NodeRerank()
        self.node_answer_output = NodeAnswerOutput()
        self._register_nodes()
        self._setup_routes()
        self._compiled_app = None

    def _register_nodes(self):
        self.workflow.add_node("node_travel_query_prepare", self.node_travel_query_prepare)
        self.workflow.add_node("node_multi_search", lambda state: state)
        self.workflow.add_node("node_search_embedding", self.node_search_embedding)
        self.workflow.add_node("node_search_embedding_hyde", self.node_search_embedding_hyde)
        self.workflow.add_node("node_web_search_mcp", self.node_web_search_mcp)
        self.workflow.add_node("node_join", lambda state: state)
        self.workflow.add_node("node_rrf", self.node_rrf)
        self.workflow.add_node("node_rerank", self.node_rerank)
        self.workflow.add_node("node_answer_output", self.node_answer_output)

    def _setup_routes(self):
        self.workflow.set_entry_point("node_travel_query_prepare")
        self.workflow.add_edge("node_travel_query_prepare", "node_multi_search")

        # 三路检索：本地混合向量、HyDE 混合向量、联网搜索。
        self.workflow.add_edge("node_multi_search", "node_search_embedding")
        self.workflow.add_edge("node_multi_search", "node_search_embedding_hyde")
        self.workflow.add_edge("node_multi_search", "node_web_search_mcp")

        self.workflow.add_edge("node_search_embedding", "node_join")
        self.workflow.add_edge("node_search_embedding_hyde", "node_join")
        self.workflow.add_edge("node_web_search_mcp", "node_join")
        self.workflow.add_edge("node_join", "node_rrf")
        self.workflow.add_edge("node_rrf", "node_rerank")
        self.workflow.add_edge("node_rerank", "node_answer_output")
        self.workflow.add_edge("node_answer_output", END)

    def compile(self):
        if self._compiled_app is None:
            self._compiled_app = self.workflow.compile()
        return self._compiled_app

    def run(self, initial_state: QueryGraphState, stream: bool = False):
        app = self.compile()
        return app.stream(initial_state) if stream else app.invoke(initial_state)


if __name__ == "__main__":
    workflow = KBQueryWorkflow()
    print(workflow.compile().get_graph().draw_ascii())
