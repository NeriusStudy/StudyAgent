# packages/schema/src/agentschema/protocols.py
from typing import Protocol, AsyncIterator, TYPE_CHECKING, List, Any


# 这行代码的意思是：只有在 IDE 或做静态类型检查时，才导入 Message、ToolCall、ToolResult，运行时完全忽略这行，从而完美避开循环导入
# 运行时完全忽略这行，从而完美避开循环导入
if TYPE_CHECKING:
    from . import Message, ToolCall, ToolResult


class LLMProvider(Protocol):
    """
    定义大模型提供商的契约标准。
    core 只认这个协议，不关心具体是哪家模型。
    """
    # 注意这里用 List["Message"]，把 Message 加上引号，延迟解析
    async def stream_chat(self, messages: List["Message"]) -> AsyncIterator[str]:
        ... # 只有声明，没有实现

class ToolHandler(Protocol):
    name: str
    description: str
    parameters: dict
    async def execute(self, arguments: str) -> "ToolResult":
        ...