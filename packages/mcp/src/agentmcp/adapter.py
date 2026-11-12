# packages/mcp/src/agentmcp/adapter.py
import json
from typing import Any
from agentschema import ToolResult, ToolHandler
from mcp import ClientSession

class MCPToolAdapter:
    """
    把一个 MCP 工具包装成 ToolHandler，让 core 的 ToolRegistry 可以统一调度。
    它持有 ClientSession 的引用，调用时通过 MCP 协议转发。
    """
    def __init__(self, session: ClientSession, mcp_tool: Any):
        self._session = session
        self.name = mcp_tool.name
        self.description = mcp_tool.description or ""
        # 兼容 mcp SDK v1 (camelCase) 和 v2 (snake_case)
        self.parameters = getattr(
            mcp_tool, 
            "input_schema", 
            getattr(mcp_tool, "inputSchema", {})
        ) or {}

    async def execute(self, arguments: str) -> ToolResult:
        # 1. 解析参数
        try:
            args_dict = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError as e:
            # 修复 Bug：直接返回错误信息，不要引用未定义的变量
            return ToolResult(
                tool_call_id="", # 由 ToolExecutor 统一补全
                content=f"参数不是合法 JSON：{e}",
                is_error=True,
            )

        # 2. 调用 MCP 工具
        try:
            result = await self._session.call_tool(self.name, args_dict)
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                content=f"MCP 工具调用失败：{e}",
                is_error=True,
            )

        # 3. 解析返回结果
        text_content = ""
        for item in result.content:
            if hasattr(item, "text"):
                text_content += item.text
            else:
                text_content += str(item)

        # 兼容 mcp SDK v1 (isError) 和 v2 (is_error)
        is_error = getattr(result, "is_error", getattr(result, "isError", False))

        return ToolResult(
            tool_call_id="",
            content=text_content,
            is_error=is_error,
        )