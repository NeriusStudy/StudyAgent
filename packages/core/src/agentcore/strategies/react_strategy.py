# packages/core/src/agentcore/strategies/react_strategy.py
from typing import AsyncIterator
from agentschema import Message, Role, LLMProvider, ToolDefinition
from ..tools.executor import ToolExecutor


class ReactStrategy:
    """
    ReAct 策略：Reasoning + Acting。
    核心循环：请求模型 -> 如果模型要调工具就执行 -> 结果回填 -> 再请求模型。
    直到模型不再调用工具，或达到 max_steps 上限。
    """

    def __init__(self, executor: ToolExecutor, tool_definitions: list[ToolDefinition], max_steps: int = 10):
        self.executor = executor
        self.tool_definitions = tool_definitions
        self.max_steps = max_steps

    async def run(
        self,
        messages: list[Message],
        provider: LLMProvider,
    ) -> AsyncIterator[str]:
        for step in range(self.max_steps):
            # 1. 请求模型，拿到可能带 tool_calls 的 assistant 消息
            assistant_msg = await provider.chat_with_tools(messages, self.tool_definitions)
            messages.append(assistant_msg)

            # 2. 模型没有调用工具 -> 把 content 吐出去，结束
            if not assistant_msg.tool_calls:
                if assistant_msg.content:
                    yield assistant_msg.content
                return

            # 3. 模型调用了工具 -> 逐个执行，结果以 TOOL 消息回填
            for call in assistant_msg.tool_calls:
                # 可选：把“模型要调工具”这件事也流式通知前端，方便调试
                yield f"\n[调用工具: {call.name}]\n"

                result = await self.executor.execute(call)
                messages.append(Message(
                    role=Role.TOOL,
                    content=result.content,
                    tool_call_id=call.id,
                ))

        # 达到最大轮数，强制结束并提示
        yield "\n[已达到最大 ReAct 轮数，强制停止]"