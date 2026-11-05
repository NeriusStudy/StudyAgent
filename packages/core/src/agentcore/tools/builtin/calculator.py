import json
from pydantic import BaseModel, Field, ValidationError
from agentschema import ToolResult

class CalculatorArgs(BaseModel):
    expression: str = Field(
        ...,
        description="要计算的数学表达式，例如 '2 + 3 * 4'",
        min_length=1,
    )

class CalculatorTool:
    name = "calculator"
    description = "计算数学表达式，支持 + - * / 和括号"
    parameters = CalculatorArgs.model_json_schema()

    async def execute(self, arguments: str) -> ToolResult:
        try:
            args = CalculatorArgs.model_validate_json(arguments)
        except ValidationError as e:
            return ToolResult(
                tool_call_id="",          # 由执行器补全？这里需要调整
                content=f"参数校验失败: {e}",
                is_error=True,
            )
        # 安全求值：只允许基本运算，绝不使用 eval 裸跑
        allowed = set("0123456789+-*/(). ")
        if not set(args.expression).issubset(allowed):
            return ToolResult(
                tool_call_id="",
                content="表达式包含不允许的字符",
                is_error=True,
            )
        try:
            value = eval(args.expression, {"__builtins__": {}}, {})
            return ToolResult(tool_call_id="", content=str(value))
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"计算错误: {e}", is_error=True)