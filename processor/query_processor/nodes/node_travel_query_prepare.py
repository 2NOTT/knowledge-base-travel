"""旅游问题预处理节点。"""

import json
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.lm_config import lm_config
from processor.query_processor.base import NodeBase
from processor.query_processor.prompt.travel_query_prepare import (
    TRAVEL_QUERY_SYSTEM_PROMPT,
    TRAVEL_QUERY_TEMPLATE,
)
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.mongo_history_utils import get_recent_messages, save_chat_message
from utils.task_utils import add_done_task


class NodeTravelQueryPrepare(NodeBase):
    """改写旅游问题，但不会因为缺少实体而阻断后续检索。"""

    name = "node_travel_query_prepare"

    _CITY_HINTS = ("成都", "杭州", "三亚", "厦门", "云南", "张家界", "乌镇", "昆明", "大理", "丽江")
    _ENTITY_HINTS = (
        "熊猫基地", "春熙路", "太古里", "宽窄巷子", "人民公园", "武侯祠", "锦里",
        "西湖", "灵隐", "龙井", "鼓浪屿", "环岛路", "天涯海角", "蜈支洲岛",
        "天门山", "武陵源", "森林公园", "洱海", "玉龙雪山",
    )

    def process(self, state: QueryGraphState) -> QueryGraphState:
        session_id, original_query = self._validate(state)
        history = self._load_history(session_id)
        state["history"] = history
        state["message_id"] = self._save_user_message(session_id, original_query)

        extracted = self._extract(original_query, history)
        state["travel_entities"] = extracted["travel_entities"]
        state["cities"] = extracted["cities"]
        state["rewritten_query"] = extracted["rewritten_query"]
        state["answer"] = ""
        add_done_task(session_id, self.name, state.get("is_stream"))
        return state

    @staticmethod
    def _validate(state: QueryGraphState) -> tuple[str, str]:
        session_id = state.get("session_id")
        original_query = (state.get("original_query") or "").strip()
        if not session_id:
            raise ValueError("参数 session_id 不能为空")
        if not original_query:
            raise ValueError("参数 original_query 不能为空")
        return session_id, original_query

    @staticmethod
    def _load_history(session_id: str) -> list:
        try:
            return get_recent_messages(session_id)
        except Exception as exc:
            logger.warning("读取旅游会话历史失败，将按无历史处理: %s", exc)
            return []

    @staticmethod
    def _save_user_message(session_id: str, query: str) -> str:
        try:
            return save_chat_message(session_id, "user", query)
        except Exception as exc:
            logger.warning("保存旅游用户问题失败: %s", exc)
            return ""

    def _extract(self, query: str, history: list) -> Dict[str, Any]:
        fallback = self._fallback(query)
        try:
            history_text = "\n".join(
                f"{message.get('role', '')}: {message.get('text', '')}" for message in history
            )
            llm = ChatOpenAI(
                model=lm_config.travel_model or lm_config.llm_model,
                api_key=lm_config.api_key,
                base_url=lm_config.base_url,
                temperature=lm_config.llm_temperature,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
            response = llm.invoke(
                [
                    SystemMessage(content=TRAVEL_QUERY_SYSTEM_PROMPT),
                    HumanMessage(
                        content=TRAVEL_QUERY_TEMPLATE.format(
                            history_text=history_text or "暂无历史会话",
                            query=query,
                        )
                    ),
                ]
            )
            content = response.content if isinstance(response.content, str) else str(response.content)
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
            result = json.loads(content)
            entities = self._clean_list(result.get("travel_entities"))
            cities = self._clean_list(result.get("cities"))
            rewritten = str(result.get("rewritten_query") or query).strip()
            return {
                "travel_entities": entities or fallback["travel_entities"],
                "cities": cities or fallback["cities"],
                "rewritten_query": rewritten,
            }
        except Exception as exc:
            logger.warning("旅游问题抽取失败，使用原问题检索: %s", exc)
            return fallback

    def _fallback(self, query: str) -> Dict[str, Any]:
        cities = [city for city in self._CITY_HINTS if city in query]
        entities = cities + [entity for entity in self._ENTITY_HINTS if entity in query]
        return {
            "travel_entities": list(dict.fromkeys(entities)),
            "cities": list(dict.fromkeys(cities)),
            "rewritten_query": query,
        }

    @staticmethod
    def _clean_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
