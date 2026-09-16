"""旅游知识库切片的 BGE-M3 混合向量生成节点。"""

import logging
from typing import Any, Dict, List

from processor.import_processor.base import BaseNode, setup_logging
from processor.import_processor.exceptions import StateFieldError
from processor.import_processor.state import ImportGraphState
from utils.embedding_utils import generate_embeddings


class NodeBGEEmbedding(BaseNode):
    """为旅游切片生成 dense 和 sparse 两种向量。"""

    name = "node_bge_embedding"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        chunks = state.get("chunks")
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(field_name="chunks", message="chunks不能为空", expected_type=list)

        state["chunks"] = self._generate_embeddings(chunks)
        return state

    @staticmethod
    def _embedding_text(chunk: Dict[str, Any]) -> str:
        """把城市、类型、主体和正文放在一起，避免正文脱离旅游上下文。"""

        context = " ".join(
            value
            for value in (
                chunk.get("city"),
                chunk.get("content_type"),
                chunk.get("entity_name"),
                chunk.get("title"),
            )
            if value
        )
        return f"{context}\n{chunk.get('content', '')}".strip()

    def _generate_embeddings(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        batch_size = self.config.embedding_batch_size

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = generate_embeddings([self._embedding_text(chunk) for chunk in batch])
            dense_vectors = vectors.get("dense") or []
            sparse_vectors = vectors.get("sparse") or []
            if len(dense_vectors) != len(batch) or len(sparse_vectors) != len(batch):
                raise ValueError("BGE-M3 返回的向量数量与切片数量不一致")

            for index, chunk in enumerate(batch):
                chunk["dense_vector"] = dense_vectors[index]
                chunk["sparse_vector"] = sparse_vectors[index]
                output.append(chunk)

        return output


if __name__ == "__main__":
    setup_logging()
    logging.getLogger().info("NodeBGEEmbedding 需要通过导入流程调用")
