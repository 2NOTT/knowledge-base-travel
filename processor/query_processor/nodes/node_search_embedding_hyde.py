"""旅游知识库 HyDE 混合向量检索节点。"""

from config.milvus_config import milvus_config
from processor.query_processor.base import NodeBase
from processor.query_processor.prompt.search_embedding_hyde import HYDE_PROMPT
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.embedding_utils import generate_embeddings
from utils.llm_utils import get_llm_client
from utils.milvus_utils import (
    build_travel_expr,
    create_hybrid_search_requests,
    get_milvus_client,
    hybrid_search,
)
from utils.task_utils import add_done_task


class NodeSearchEmbeddingHyde(NodeBase):
    """先生成旅游问题的假设答案，再执行第二路混合向量检索。"""

    name = "node_search_embedding_hyde"

    _OUTPUT_FIELDS = [
        "chunk_id", "content", "title", "parent_title", "file_title", "source_file",
        "source_path", "content_type", "city", "entity_name", "attraction_name",
        "route_name", "hotel_name", "restaurant_name", "document_name", "topic",
    ]

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = (state.get("rewritten_query") or state.get("original_query") or "").strip()
        try:
            hyde_doc = get_llm_client().invoke(HYDE_PROMPT.format(rewritten_query=query)).content
            combined_text = f"{query}\n{hyde_doc}"
            embeddings = generate_embeddings([combined_text])
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
            return {"hyde_embedding_chunks": result[0] if result else [], "hyde_doc": hyde_doc}
        except Exception as exc:
            logger.exception("旅游 HyDE 检索失败: %s", exc)
            return {"hyde_embedding_chunks": [], "hyde_doc": ""}
