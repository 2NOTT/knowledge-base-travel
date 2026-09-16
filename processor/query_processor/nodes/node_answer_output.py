"""旅游知识库答案生成节点。"""

import re
from typing import Dict, List, Tuple

from processor.query_processor.base import NodeBase
from processor.query_processor.prompt.answer_prompt import ANSWER_PROMPT
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.llm_utils import get_llm_client
from utils.mongo_history_utils import save_chat_message
from utils.sse_utils import SSEEvent, push_to_session
from utils.task_utils import add_done_task, set_task_result

MAX_CONTEXT_CHARS = 12000


class NodeAnswerOutput(NodeBase):
    """根据重排后的旅游资料生成答案，并保留 SSE/历史记录能力。"""

    name = "node_answer_output"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        answer = state.get("answer") or ""
        if not answer:
            prompt = self._build_prompt(state)
            state["prompt"] = prompt
            state["answer"] = self._generate(state, prompt)

        image_urls = self._extract_images(state.get("reranked_docs") or [])
        if state.get("answer"):
            set_task_result(state.get("session_id"), "answer", state.get("answer", ""))
            set_task_result(state.get("session_id"), "image_urls", image_urls)
            self._write_history(state, image_urls)

        session_id = state.get("session_id")
        add_done_task(session_id, self.name, state.get("is_stream"))
        if state.get("is_stream"):
            push_to_session(
                session_id,
                SSEEvent.FINAL,
                {"answer": state.get("answer", ""), "status": "completed", "image_urls": image_urls},
            )
        return state

    def _build_prompt(self, state: QueryGraphState) -> str:
        budget = MAX_CONTEXT_CHARS
        context, budget = self._format_docs(state.get("reranked_docs") or [], budget)
        history, budget = self._format_history(state.get("history") or [], budget)
        entities = ", ".join(state.get("travel_entities") or []) or "无指定实体"
        question = state.get("rewritten_query") or state.get("original_query") or ""
        return ANSWER_PROMPT.format(
            context=context or "无参考内容",
            travel_entities=entities,
            history=history or "暂无历史对话",
            question=question,
        )

    @staticmethod
    def _format_docs(docs: List[Dict], budget: int) -> Tuple[str, int]:
        entries = []
        used = 0
        fields = (
            ("source", "来源"),
            ("file_title", "文件"),
            ("title", "章节"),
            ("content_type", "类型"),
            ("city", "城市"),
            ("entity_name", "实体"),
            ("url", "链接"),
        )
        for index, doc in enumerate(docs, start=1):
            content = str(doc.get("content") or "").strip()
            if not content:
                continue
            tags = [f"[{index}]"]
            for field, label in fields:
                value = str(doc.get(field) or "").strip()
                if value:
                    tags.append(f"[{label}={value}]")
            entry = " ".join(tags) + "\n" + content
            if used + len(entry) > budget:
                break
            entries.append(entry)
            used += len(entry) + 2
        return "\n\n".join(entries), budget - used

    @staticmethod
    def _format_history(messages: List[Dict], budget: int) -> Tuple[str, int]:
        labels = {"user": "用户", "assistant": "助手"}
        lines = []
        used = 0
        for message in messages:
            role = labels.get(message.get("role"))
            text = str(message.get("text") or "").strip()
            if not role or not text:
                continue
            line = f"{role}: {text}"
            if used + len(line) > budget:
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines), budget - used

    @staticmethod
    def _generate(state: QueryGraphState, prompt: str) -> str:
        llm = get_llm_client()
        session_id = state.get("session_id")
        if state.get("is_stream"):
            parts = []
            try:
                for chunk in llm.stream(prompt):
                    delta = getattr(chunk, "content", "") or ""
                    if delta:
                        parts.append(delta)
                        push_to_session(session_id, SSEEvent.DELTA, {"delta": delta})
                return "".join(parts)
            except Exception as exc:
                logger.exception("旅游流式回答失败: %s", exc)
                push_to_session(session_id, SSEEvent.ERROR, {"error": str(exc)})
                return ""

        try:
            answer = llm.invoke(prompt).content
            set_task_result(session_id, "answer", answer)
            return answer
        except Exception as exc:
            logger.exception("旅游回答生成失败: %s", exc)
            return "抱歉，生成旅游回答时出现错误。"

    @staticmethod
    def _extract_images(docs: List[Dict]) -> List[str]:
        pattern = re.compile(r"!\[.*?\]\((.*?)\)")
        urls = []
        seen = set()
        for doc in docs:
            candidates = []
            url = str(doc.get("url") or "").strip()
            if url and url.lower().split("?", 1)[0].endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")):
                candidates.append(url)
            candidates.extend(pattern.findall(str(doc.get("content") or "")))
            for candidate in candidates:
                candidate = candidate.strip()
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    urls.append(candidate)
        return urls

    @staticmethod
    def _write_history(state: QueryGraphState, image_urls: List[str]) -> None:
        try:
            save_chat_message(
                session_id=state.get("session_id", "default"),
                role="assistant",
                text=state.get("answer", ""),
                rewritten_query=state.get("rewritten_query", ""),
                travel_entities=state.get("travel_entities") or [],
                image_urls=image_urls,
            )
        except Exception as exc:
            logger.warning("保存旅游回答历史失败: %s", exc)
