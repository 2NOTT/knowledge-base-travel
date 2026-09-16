import asyncio
import json

from config.bailian_mcp_config import mcp_config
from processor.query_processor.base import NodeBase
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.json_format_utils import serialize_json
from utils.task_utils import add_done_task


class NodeWebSearchMcp(NodeBase):
    """
    节点功能，调用外部搜索引擎补充信息
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_web_search_mcp"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """
        节点逻辑
        :param state: 工作流状态对象
        :return: 更新后的状态对象
        """

        query = (state.get("rewritten_query") or state.get("original_query") or "").strip()
        web_docs = []
        try:
            if query:
                result = asyncio.run(self._mcp_call(query))
                web_docs = self._parse_result(result)
        except Exception as exc:
            # 联网是补充路线，网络/MCP异常不应让本地知识库问答整体失败。
            logger.warning("旅游联网检索失败，将继续使用本地结果: %s", exc)
        finally:
            add_done_task(state.get("session_id"), self.name, state.get("is_stream"))
        return {"web_search_docs": web_docs}

    @staticmethod
    def _parse_result(result) -> list[dict]:
        if not result or not getattr(result, "content", None):
            return []
        raw_text = getattr(result.content[0], "text", "")
        if not raw_text:
            return []
        payload = json.loads(raw_text) if isinstance(raw_text, str) else raw_text
        pages = payload.get("pages", []) if isinstance(payload, dict) else []
        return [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("snippet") or item.get("content"),
            }
            for item in pages
            if isinstance(item, dict) and (item.get("snippet") or item.get("content"))
        ]


    async def _mcp_call(self, query: str):

        if not query or not mcp_config.mcp_base_url or not mcp_config.api_key:
            return None

        # 延迟导入，避免没有启用联网搜索时，第三方 agents 包阻塞本地知识库启动。
        try:
            from agents.mcp import MCPServerStreamableHttp
        except Exception as exc:
            logger.warning("联网搜索依赖不可用，将跳过联网检索: %s", exc)
            return None

        # 1.创建mcp客户端对象
        mcp_client = MCPServerStreamableHttp(
            name="Streamable HTTP Python Server",
            params={
                "url": mcp_config.mcp_base_url,
                "headers": {"Authorization": f"Bearer {mcp_config.api_key}"},
                "timeout": 10,
            },
            cache_tools_list=True,
            max_retry_attempts=3,
        )

        try:
            # 2. 建立连接
            await mcp_client.connect()

            # 3. 执行查询
            result = await mcp_client.call_tool(
                tool_name="bailian_web_search",
                arguments={
                    "query": query,
                    "count": 5
                }
            )

            return result

        finally:
            # 4. 清理资源
            try:
                await mcp_client.cleanup()
            except Exception as exc:
                logger.debug("清理联网搜索连接失败: %s", exc)




if __name__ == "__main__":

    init_state = {
        "rewritten_query": "成都有哪些适合亲子游客的景点？"
    }

    # 执行节点的业务调用
    node_web_search_mcp = NodeWebSearchMcp()
    result = node_web_search_mcp(init_state)
    logger.info(serialize_json(result, indent=4))


