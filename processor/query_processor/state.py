from typing import List, TypedDict


class QueryGraphState(TypedDict, total=False):
    """旅游问答图在各节点之间传递的状态。"""

    session_id: str
    message_id: str
    original_query: str
    rewritten_query: str
    history: list
    is_stream: bool

    # 旅游问题解析结果
    travel_entities: List[str]
    cities: List[str]

    # 检索和生成中间结果
    embedding_chunks: list
    hyde_embedding_chunks: list
    web_search_docs: list
    hyde_doc: str
    rrf_chunks: list
    reranked_docs: list
    prompt: str
    answer: str
