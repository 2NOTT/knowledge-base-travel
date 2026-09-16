"""旅游知识库结果合并与重排序节点。"""

from typing import Any, Dict, List

from processor.query_processor.base import NodeBase
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.reranker_http_utils import rerank_documents
from utils.task_utils import add_done_task

RERANK_MAX_TOPK = 5
RERANK_MIN_TOPK = 2
RERANK_GAP_ABS = 0.3
RERANK_GAP_RATIO = 0.25


class NodeRerank(NodeBase):
    """把本地两路召回和联网结果统一后交给 Reranker。"""

    name = "node_rerank"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        merged = self._merge_sources(state)
        if not merged:
            state["reranked_docs"] = []
            add_done_task(state.get("session_id"), self.name, state.get("is_stream"))
            return state

        query = state.get("rewritten_query") or state.get("original_query") or ""
        try:
            scores = rerank_documents(query, [doc["content"] for doc in merged])
        except Exception as exc:
            logger.warning("旅游 Reranker 调用失败，保留召回顺序: %s", exc)
            scores = [0.0] * len(merged)

        ranked = sorted(
            [{**doc, "score": score} for doc, score in zip(merged, scores)],
            key=lambda doc: doc["score"],
            reverse=True,
        )
        state["reranked_docs"] = self._cliff_cutoff(ranked)
        add_done_task(state.get("session_id"), self.name, state.get("is_stream"))
        return state

    @staticmethod
    def _entity_from_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
        entity = hit.get("entity") if isinstance(hit, dict) else None
        return entity if isinstance(entity, dict) else (hit if isinstance(hit, dict) else {})

    def _merge_sources(self, state: QueryGraphState) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for hit in state.get("rrf_chunks") or []:
            entity = self._entity_from_hit(hit)
            if not entity.get("content"):
                continue
            docs.append({
                **entity,
                "source": "local",
                "title": entity.get("title") or entity.get("entity_name") or entity.get("file_title"),
                "content": entity["content"],
                "url": None,
            })

        for web_doc in state.get("web_search_docs") or []:
            content = web_doc.get("snippet") or web_doc.get("content")
            if not content:
                continue
            docs.append({
                "chunk_id": None,
                "title": web_doc.get("title"),
                "content": content,
                "url": web_doc.get("url"),
                "source": "web",
            })
        return docs

    @staticmethod
    def _cliff_cutoff(ranked_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        upper = min(RERANK_MAX_TOPK, len(ranked_docs))
        lower = min(RERANK_MIN_TOPK, upper)
        cutoff = upper
        for index in range(lower - 1, upper - 1):
            current = ranked_docs[index].get("score")
            following = ranked_docs[index + 1].get("score")
            if current is None or following is None:
                continue
            absolute_gap = current - following
            relative_gap = absolute_gap / (abs(current) + 1e-6)
            if absolute_gap >= RERANK_GAP_ABS or relative_gap >= RERANK_GAP_RATIO:
                cutoff = index + 1
                break
        return ranked_docs[:cutoff]
