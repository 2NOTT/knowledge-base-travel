"""旅游问答历史记录的 MongoDB 读写工具。"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

load_dotenv()


class HistoryMongoTool:
    """管理旅游问答历史集合和会话索引。"""

    def __init__(self):
        mongo_url = os.getenv("MONGO_URL", "")
        db_name = os.getenv("MONGO_DB_NAME", "kb001")
        if not mongo_url:
            raise ValueError("MONGO_URL 未配置")

        self.client = MongoClient(
            mongo_url,
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        self.db = self.client[db_name]
        self.chat_message = self.db["chat_message"]
        self.chat_message.create_index([("session_id", 1), ("ts", -1)])
        logging.info("Successfully connected to MongoDB: %s", db_name)


# 延迟连接：没有 MongoDB 时，服务仍可启动并使用本地知识库检索。
_history_mongo_tool: Optional[HistoryMongoTool] = None


def get_history_mongo_tool() -> HistoryMongoTool:
    """返回进程内复用的 MongoDB 工具实例。"""

    global _history_mongo_tool
    if _history_mongo_tool is None:
        _history_mongo_tool = HistoryMongoTool()
    return _history_mongo_tool


def clear_history(session_id: str) -> int:
    """清空指定会话的历史消息。"""

    try:
        result = get_history_mongo_tool().chat_message.delete_many({"session_id": session_id})
        return result.deleted_count
    except Exception as exc:
        logging.error("清空旅游历史失败: %s", exc)
        return 0


def save_chat_message(
    session_id: str,
    role: str,
    text: str,
    rewritten_query: str = "",
    item_names: Optional[List[str]] = None,
    image_urls: Optional[List[str]] = None,
    message_id: Optional[str] = None,
    travel_entities: Optional[List[str]] = None,
) -> str:
    """保存一条旅游问答消息；``item_names`` 仅用于兼容旧历史数据。"""

    entities = travel_entities if travel_entities is not None else item_names
    document = {
        "session_id": session_id,
        "role": role,
        "text": text,
        "rewritten_query": rewritten_query or "",
        "travel_entities": entities,
        # 保留旧字段，允许已有 Mongo 历史和旧前端继续读取。
        "item_names": entities,
        "image_urls": image_urls,
        "ts": datetime.now().timestamp(),
    }

    try:
        collection = get_history_mongo_tool().chat_message
        if message_id:
            collection.update_one({"_id": ObjectId(message_id)}, {"$set": document})
            return message_id
        result = collection.insert_one(document)
        return str(result.inserted_id)
    except Exception as exc:
        logging.error("保存旅游历史失败: %s", exc)
        return ""


def update_message_travel_entities(ids: List[str], travel_entities: List[str]) -> int:
    """批量更新历史消息的旅游实体。"""

    try:
        object_ids = [ObjectId(item) for item in ids]
        result = get_history_mongo_tool().chat_message.update_many(
            {"_id": {"$in": object_ids}},
            {"$set": {"travel_entities": travel_entities, "item_names": travel_entities}},
        )
        return result.modified_count
    except Exception as exc:
        logging.error("更新旅游实体失败: %s", exc)
        return 0


def update_message_item_names(ids: List[str], item_names: List[str]) -> int:
    """旧函数名兼容入口，内部统一更新旅游实体。"""

    return update_message_travel_entities(ids, item_names)


def get_recent_messages(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """按时间正序读取指定会话的最近消息；数据库不可用时返回空列表。"""

    try:
        cursor = (
            get_history_mongo_tool()
            .chat_message.find({"session_id": session_id})
            .sort("ts", ASCENDING)
            .limit(limit)
        )
        return list(cursor)
    except Exception as exc:
        logging.error("读取旅游历史失败: %s", exc)
        return []


if __name__ == "__main__":
    print("旅游历史记录工具已加载；请通过查询服务读写 MongoDB。")
