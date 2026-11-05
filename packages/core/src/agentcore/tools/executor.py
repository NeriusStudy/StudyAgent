from agentschema import ToolCall, ToolResult, ToolHandler

class ToolExecutor:
    def __init__(self, registry):
        self.registry = registry

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            tool = self.registry.get(call.name)
            # 参数校验由具体工具内部完成（见计算器示例）
            result = await tool.execute(call.arguments)
            return result
        except Exception as e:
            return ToolResult(
                tool_call_id=call.id,
                content=f"工具执行失败: {str(e)}",
                is_error=True,
            )