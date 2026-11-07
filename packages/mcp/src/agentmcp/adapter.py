# packages/mcp/src/agentmcp/adapter.py
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
        # v2 将 inputSchema 改名为 input_schema
        self.parameters = getattr(
            mcp_tool, 
            "input_schema", 
            getattr(mcp_tool, "inputSchema", {})
        ) or {}

    async def execute(self, arguments: str) -> ToolResult:
        # arguments 是来自模型的 JSON 字符串，MCP 的 call_tool 需要 dict
        import json
        try:
            args_dict = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError as e:
            return ToolResult(
                tool_call_id="",
                content=text_content,
                # 兼容 mcp SDK v1 (isError) 和 v2 (is_error)
                is_error=getattr(result, "is_error", getattr(result, "isError", False)),
            )

        try:
            result = await self._session.call_tool(self.name, args_dict)
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                content=text_content,
                # 兼容 mcp SDK v1 (isError) 和 v2 (is_error)
                is_error=getattr(result, "is_error", getattr(result, "isError", False)),
            )

        # MCP 返回的 content 是一个列表，通常取第一个 text 内容
        text_content = ""
        for item in result.content:
            if hasattr(item, "text"):
                text_content += item.text
            else:
                text_content += str(item)

        return ToolResult(
            tool_call_id="",
            content=text_content,
            # 兼容 mcp SDK v1 (isError) 和 v2 (is_error)
            is_error=getattr(result, "is_error", getattr(result, "isError", False)),
        )