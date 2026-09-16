"""旅游知识库普通混合向量检索节点。"""

from config.milvus_config import milvus_config
from processor.query_processor.base import NodeBase
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.embedding_utils import generate_embeddings
from utils.milvus_utils import (
    build_travel_expr,
    create_hybrid_search_requests,
    get_milvus_client,
    hybrid_search,
)
from utils.task_utils import add_done_task


class NodeSearchEmbedding(NodeBase):
    """对旅游问题执行 dense+sparse 混合向量检索。"""

    name = "node_search_embedding"

    _OUTPUT_FIELDS = [
        "chunk_id", "content", "title", "parent_title", "file_title", "source_file",
        "source_path", "content_type", "city", "entity_name", "attraction_name",
        "route_name", "hotel_name", "restaurant_name", "document_name", "topic",
    ]

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = (state.get("rewritten_query") or state.get("original_query") or "").strip()
        if not query:
            return {"embedding_chunks": []}

        try:
            embeddings = generate_embeddings([query])
            reqs = create_hybrid_search_requests(
                dense_vector=embeddings["dense"][0],
                sparse_vector=embeddings["sparse"][0],
                expr=build_travel_expr(
                    cities=state.get("cities"),
                    entities=state.get("travel_entities"),
                ),
                limit=10,
            )
            result = hybrid_search(
                client=get_milvus_client(),
                collection_name=milvus_config.chunks_collection,
                reqs=reqs,
                ranker_weights=(0.8, 0.2),
                output_fields=self._OUTPUT_FIELDS,
            )
            add_done_task(state.get("session_id"), self.name, state.get("is_stream"))
            return {"embedding_chunks": result[0] if result else []}
        except Exception as exc:
            logger.exception("旅游普通检索失败: %s", exc)
            return {"embedding_chunks": []}
