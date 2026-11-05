# packages/core/src/agentcore/loop.py
from typing import AsyncIterator
from agentschema import Message, Role, LLMProvider
from .strategies.base import BaseStrategy


class AgentLoop:
    """
    Agent 主循环。现在它是无状态执行器：
    1. 维护每个 session 的历史消息
    2. 每次 run_stream 接收一个 strategy，委托它执行
    策略由 server 按请求决定，AgentLoop 不持有任何策略实例，天然并发安全。
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._sessions: dict[str, list[Message]] = {}

    def _get_history(self, session_id: str) -> list[Message]:
        if session_id not in self._sessions:
            self._sessions[session_id] = [
                Message(role=Role.SYSTEM, content="You are a helpful assistant.")
            ]
        return self._sessions[session_id]

    async def run_stream(
        self,
        session_id: str,
        user_input: str,
        strategy: BaseStrategy,
    ) -> AsyncIterator[str]:
        history = self._get_history(session_id)
        history.append(Message(role=Role.USER, content=user_input))

        full_reply: list[str] = []
        async for delta in strategy.run(history, self.provider):
            full_reply.append(delta)
            yield delta

        history.append(Message(role=Role.ASSISTANT, content="".join(full_reply)))