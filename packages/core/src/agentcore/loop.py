# ==============================================================================
# 1. 导入所需的工具包
# ==============================================================================
# AsyncIterator: 类型提示，用于标注异步生成器函数的返回值类型。
from typing import AsyncIterator

# 从底层的 agentschema 包导入数据契约：
# - Message：单条对话消息（包含 role 和 content）
# - Role：角色枚举（USER / ASSISTANT / SYSTEM）
# 不再 import agentllm
# from agentllm import OpenAICompatibleProvider  
from agentschema import Message, Role, LLMProvider


# ==============================================================================
# 2. AgentLoop 类：整个 Agent 的“大脑”
# ==============================================================================
class AgentLoop:
    """
    最小的 Agent Loop（智能体循环）。
    
    核心职责：
    1. 维护每个会话（session）的历史对话记录。
    2. 接收用户新输入，拼接到历史记录末尾。
    3. 把完整历史交给 LLM Provider，流式获取回复。
    4. 把完整回复作为 ASSISTANT 消息追加回历史，为多轮对话做准备。
    
    设计原则：
    - 不感知 HTTP（不 import fastapi），只处理纯业务逻辑。
    - 不感知具体模型（不关心是 OpenAI 还是 DeepSeek），只依赖 Provider 接口。
    """

    def __init__(self, provider: LLMProvider): # <--- 依赖倒置！
        self.provider = provider
        self._sessions: dict[str, list[Message]] = {}
    

    def _get_history(self, session_id: str) -> list[Message]:
        """
        获取某个会话的历史消息列表。如果会话不存在，就自动初始化。
        
        返回的是列表对象的引用，而不是副本。
        这意味着调用方拿到列表后直接 append，会同步修改 _sessions 里的数据。
        这是有意为之的（懒加载 + 零拷贝），但要注意：以后多线程/多协程并发时
        需要考虑加锁，避免两个请求同时改同一个会话。
        """
        # 如果这个 session_id 还没出现过，就创建一个新的历史列表。
        if session_id not in self._sessions:
            self._sessions[session_id] = [
                # 初始化时立刻加入一条 SYSTEM 消息，这是给大模型的“人设”设定。
                # 例如：“你是一个有用的助手”。以后可以换成从配置文件读取。
                Message(role=Role.SYSTEM, content="You are a helpful assistant.")
            ]
        # 返回历史列表的引用。注意：如果 session 已存在，直接返回已存在的那个列表。
        return self._sessions[session_id]

    async def run_stream(self, session_id: str, user_input: str) -> AsyncIterator[str]:
        """
        核心方法：处理一次完整的用户输入，并流式返回 AI 的回复。
        
        为什么是 async + yield？
        - async：因为内部要 await 网络请求（provider.stream_chat）。
        - yield：因为要实现流式输出，每收到一个文字碎片就立刻交给调用方（server 层）。
        
        参数：
        - session_id：区分不同会话（一个用户可能有多个聊天窗口）。
        - user_input：用户这一轮输入的新文本。
        """
        # 1. 拿到（或初始化）当前会话的历史列表
        history = self._get_history(session_id)

        # 2. 把用户的新输入追加到历史末尾。
        # 注意：这里直接修改的是列表引用，_sessions 里的数据同步更新了。
        history.append(Message(role=Role.USER, content=user_input))

        # 3. 准备一个空列表，用来收集 AI 回复的每一个碎片。
        # 为什么需要它？因为流式返回结束后，我们需要把 AI 的完整回复写回历史。
        # 如果不收集，历史里只有用户的话，下一轮 AI 就“失忆”了。
        full_reply: list[str] = []

        # 4. 调用 Provider 的流式接口。
        # provider.stream_chat(history) 返回一个异步生成器，
        # 每次循环得到一小段文字（delta）。
        async for delta in self.provider.stream_chat(history):
            # 把碎片存起来，用于最后拼接完整回复。
            full_reply.append(delta)
            # 同时立刻把碎片 yield 出去，让 server 层可以推送给客户端。
            # 这就是“边收边发”的关键：用户不用等 AI 说完，就能看到文字一个个出现。
            yield delta

        # 5. 流式结束后，把收集到的所有碎片拼成完整字符串，追加到历史。
        # "".join(["你", "好", "！"]) 会得到 "你好！"。
        # 角色是 ASSISTANT，表示这是 AI 说的话。
        history.append(Message(role=Role.ASSISTANT, content="".join(full_reply)))