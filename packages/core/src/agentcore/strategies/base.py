from typing import AsyncIterator, Protocol
from agentschema import Message, LLMProvider

class BaseStrategy(Protocol):
    async def run(
        self,
        messages: list[Message],
        provider: LLMProvider,
    ) -> AsyncIterator[str]:
        ...