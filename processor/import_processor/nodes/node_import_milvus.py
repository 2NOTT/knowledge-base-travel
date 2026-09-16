"""将旅游切片和元数据写入 Milvus。"""

import logging
from typing import Any, Dict, List

from pymilvus import DataType

from config.milvus_config import milvus_config
from processor.import_processor.base import BaseNode, setup_logging
from processor.import_processor.exceptions import MilvusError, StateFieldError
from processor.import_processor.state import ImportGraphState
from utils.milvus_utils import escape_milvus_string, get_milvus_client


class NodeImportMilvus(BaseNode):
    """创建旅游知识库集合并幂等写入文档切片。"""

    name = "node_import_milvus"

    _TEXT_FIELDS = (
        "title",
        "parent_title",
        "file_title",
        "source_file",
        "source_path",
        "content_type",
        "city",
        "entity_name",
        "attraction_name",
        "route_name",
        "hotel_name",
        "restaurant_name",
        "document_name",
        "topic",
    )
    _FIELD_MAX_LENGTHS = {field: (2048 if field == "source_path" else 256) for field in _TEXT_FIELDS}
    _FIELD_MAX_LENGTHS["content"] = 65535

    def process(self, state: ImportGraphState) -> ImportGraphState:
        chunks, vector_dimension = self._validate_input(state)
        client = self._prepare_collection(vector_dimension)
        self._clear_old_file(client, chunks[0].get("file_title", ""))
        state["chunks"] = self._insert(client, chunks)
        return state

    @staticmethod
    def _validate_input(state: ImportGraphState) -> tuple[List[Dict[str, Any]], int]:
        chunks = state.get("chunks")
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(field_name="chunks", message="chunks不能为空", expected_type=list)
        first = chunks[0]
        for field in ("dense_vector", "sparse_vector"):
            if field not in first:
                raise StateFieldError(field_name="chunks", message=f"缺少{field}字段")
        return chunks, len(first["dense_vector"])

    def _prepare_collection(self, vector_dimension: int):
        client = get_milvus_client()
        if not client:
            raise MilvusError("Milvus 连接失败")
        collection_name = milvus_config.chunks_collection
        if not collection_name:
            raise MilvusError("CHUNKS_COLLECTION 未配置")
        if not client.has_collection(collection_name):
            self._create_collection(client, collection_name, vector_dimension)
        return client

    def _clear_old_file(self, client, file_title: str) -> None:
        if not file_title:
            return
        try:
            client.delete(
                collection_name=milvus_config.chunks_collection,
                filter=f"file_title == '{escape_milvus_string(file_title)}'",
            )
        except Exception as exc:
            raise MilvusError(f"清理旧旅游文档失败: {exc}") from exc

    def _insert(self, client, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        for chunk in chunks:
            row = dict(chunk)
            # chunk_id 是 Milvus auto_id 主键，不能把上一次状态中的值再次插入。
            row.pop("chunk_id", None)
            row["part"] = int(row.get("part", 0))
            text_values = {"content": str(row.get("content") or "")}
            text_values.update({field: str(row.get(field) or "") for field in self._TEXT_FIELDS})
            for field, value in text_values.items():
                max_length = self._FIELD_MAX_LENGTHS[field]
                if len(value) > max_length:
                    raise MilvusError(
                        f"旅游切片字段 {field} 超过 Milvus 限制 {max_length} 字符，"
                        "请先调整切片或元数据。"
                    )
                row[field] = value
            rows.append(row)

        result = client.insert(collection_name=milvus_config.chunks_collection, data=rows)
        ids = result.get("ids") or []
        for index, chunk in enumerate(rows):
            if index < len(ids):
                chunk["chunk_id"] = ids[index]
        return rows

    @staticmethod
    def _create_collection(client, collection_name: str, vector_dimension: int) -> None:
        schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="part", datatype=DataType.INT8)
        for field in NodeImportMilvus._TEXT_FIELDS:
            max_length = 2048 if field == "source_path" else 256
            schema.add_field(field_name=field, datatype=DataType.VARCHAR, max_length=max_length)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=vector_dimension)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_name="sparse_inverted_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            params={"inverted_index_algo": "DAAT_MAXSCORE", "normalize": True, "quantization": "none"},
        )
        client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)


if __name__ == "__main__":
    setup_logging()
    logging.getLogger().info("NodeImportMilvus 需要通过导入流程调用")
