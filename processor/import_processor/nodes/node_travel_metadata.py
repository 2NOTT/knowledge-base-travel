"""旅游文档元数据整理节点。"""

from typing import Dict, List

from processor.import_processor.base import BaseNode
from processor.import_processor.exceptions import StateFieldError
from processor.import_processor.state import ImportGraphState


class NodeTravelMetadata(BaseNode):
    """校验并补齐旅游文档的统一元数据。"""

    name = "node_travel_metadata"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        chunks = state.get("chunks")
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(field_name="chunks", message="chunks不能为空", expected_type=list)

        metadata = dict(state.get("document_metadata") or {})
        entity_name = (
            metadata.get("entity_name")
            or metadata.get("attraction_name")
            or metadata.get("route_name")
            or metadata.get("hotel_name")
            or metadata.get("restaurant_name")
            or metadata.get("document_name")
            or state.get("file_title", "")
        )
        if not entity_name:
            raise StateFieldError(field_name="entity_name", message="旅游主体名称不能为空", expected_type=str)

        metadata.setdefault("file_title", state.get("file_title", ""))
        metadata["entity_name"] = entity_name
        for chunk in chunks:
            chunk.update(metadata)

        state["document_metadata"] = metadata
        state["entity_name"] = entity_name
        state["chunks"] = chunks
        return state
