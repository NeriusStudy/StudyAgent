# packages/core/src/agentcore/strategies/chat_strategy.py
from typing import AsyncIterator
from agentschema import Message, LLMProvider


class ChatStrategy:
    """纯对话策略：把模型输出直接流式转发给上层。不调用任何工具。"""

    async def run(
        self,
        messages: list[Message],
        provider: LLMProvider,
    ) -> AsyncIterator[str]:
        async for delta in provider.stream_chat(messages):
            yield delta