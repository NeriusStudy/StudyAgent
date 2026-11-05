# ==============================================================================
# 1. 导入所需的工具包
# ==============================================================================
# os: Python 自带模块，用来读取操作系统的环境变量（比如你的 API 密钥，绝对不能硬编码在代码里）。
import os
# httpx: 一个现代化的、支持异步（async）的 HTTP 客户端。用它来向大模型服务器发网络请求。
import httpx
# json: 用来把大模型返回的 JSON 格式字符串，解析成 Python 的字典（dict）。
import json
# AsyncIterator: 类型提示，告诉 IDE 和开发者，下面这个函数是一个“异步生成器”。
from typing import AsyncIterator

# 从我们底层的 agentschema 包中导入 Message 类，用来接收历史对话数据。
# 从我们底层的 agentschema 包中导入 LLMConfig 类，用来读取大模型提供商的配置。
from agentschema import Message, LLMConfig, Role, ToolCall, ToolDefinition


# ==============================================================================
# 2. 定义 Provider 类
# ==============================================================================
class OpenAICompatibleProvider:
    """
    一个极简的 OpenAI 兼容 Provider（提供商）。
    什么是“OpenAI 兼容”？因为现在市面上 90% 的大模型（DeepSeek、通义千问、Kimi、本地跑的 Ollama 等）
    都模仿了 OpenAI 的 API 接口格式。只要我们的代码按 OpenAI 的格式发请求，这些模型都能通吃。
    """

    def __init__(self, config: LLMConfig):
        # 不再读环境变量，直接使用传入的配置
        self.base_url = config.base_url.rstrip("/")
        self.api_key = config.api_key
        self.model = config.model

        if not self.base_url:
            raise ValueError("LLM_BASE_URL 未设置！")
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未设置！")
    
    def _to_api_message(self, m: Message) -> dict:
        """
        把内部 Message 转成 OpenAI 兼容 API 的 message 格式。
        关键差异：
        - 普通消息：{"role": "user", "content": "..."}
        - assistant 发起工具调用：{"role": "assistant", "content": null, "tool_calls": [...]}
        - tool 回填结果：{"role": "tool", "content": "...", "tool_call_id": "..."}
        """
        msg: dict = {"role": m.role.value}

        # content 可能是 None（assistant 调工具时），只有非 None 才放进去
        if m.content is not None:
            msg["content"] = m.content

        # assistant 发起的工具调用
        if m.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in m.tool_calls
            ]

        # tool 消息必须带 tool_call_id，让模型知道这是对哪次调用的回复
        if m.tool_call_id:
            msg["tool_call_id"] = m.tool_call_id

        return msg
    
    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
    ) -> Message:
        """
        非流式调用，专门给 ReAct 循环用。
        返回带 tool_calls 的 assistant Message（如果模型没调工具，tool_calls 为 None）。

        为什么不用流式？
        - ReAct 需要先拿到完整的 tool_calls 才能决定执行哪些工具，流式解析 tool_calls 的增量 JSON 非常复杂
        - 工具调用本身不是"打字机"体验，用户不需要逐字看到"我要调计算器"
        - 只有最后的自然语言回复才需要流式（这一步由策略层在拿到结果后再次调用 stream_chat 实现）
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 把内部 ToolDefinition 转成 OpenAI 的 tools 格式
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters,
                },
            }
            for d in tools
        ]

        payload = {
            "model": self.model,
            "messages": [self._to_api_message(m) for m in messages],
            "tools": openai_tools,
            "tool_choice": "auto",
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=tc["function"]["arguments"],
            )
            for tc in choice.get("tool_calls", [])
        ]

        return Message(
            role=Role.ASSISTANT,
            content=choice.get("content"),
            tool_calls=tool_calls or None,   # 空列表转 None，符合 schema 语义
        )

    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        """
        这是一个【异步生成器】方法。
        - 接收：一个 Message 对象的列表（历史对话记录）。
        - 返回：一段一段吐出字符串（AI 的回复碎片）。
        
        为什么要用 `async for` 和 `yield`？
        因为大模型打字很慢，要等几十秒。如果是同步请求，整个程序都会卡住。
        用异步生成器，我们可以一边接收、一边处理、一边转发给前端。
        """
        # 拼接出最终的请求地址，例如：https://api.deepseek.com/v1/chat/completions
        url = f"{self.base_url}/chat/completions"
        
        # 请求头：包含鉴权信息和数据格式声明
        headers = {
            "Authorization": f"Bearer {self.api_key}", # Bearer 后面跟你的密钥，这是行业标准
            "Content-Type": "application/json",        # 告诉服务器，我们发过去的是 JSON 格式数据
        }
        
        # 请求体 (Payload)：把我们的内部数据翻译成大模型要的格式
        payload = {
            "model": self.model,
            "messages": [self._to_api_message(m) for m in messages],
            "stream": True,
        }

        # 使用 httpx 创建一个异步客户端，超时时间设置为 60 秒
        async with httpx.AsyncClient(timeout=60) as client:
            # client.stream 表示发起一个“流式”请求，而不是等所有数据都下载完才返回
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                # 检查 HTTP 状态码。如果是 4xx（如 401 没权限）或 5xx（服务器错误），这里会自动抛出异常。
                resp.raise_for_status()
                
                # 按“行”迭代读取数据。
                # 大模型流式返回的数据格式叫 SSE (Server-Sent Events)。
                # 它的长相大概是这样：
                # data: {"choices": [{"delta": {"content": "你"}}]}
                # data: {"choices": [{"delta": {"content": "好"}}]}
                # data: [DONE]
                async for line in resp.aiter_lines():
                    
                    # 1. 过滤无效行。如果不是以 "data: " 开头，直接跳过。
                    if not line.startswith("data: "):
                        continue
                    
                    # 2. 切片提取数据。把前 6 个字符（"data: "）切掉，并去掉首尾空格。
                    data = line[6:].strip()
                    
                    # 3. 判断流是否结束。收到 "[DONE]" 说明大模型说完了，跳出循环。
                    if data == "[DONE]":
                        break
                    
                    # 4. 解析 JSON 字符串为 Python 字典
                    chunk = json.loads(data)
                    
                    # 5. 提取文本碎片。
                    # 大模型返回的 JSON 结构很深，必须一层层剥开：
                    # chunk["choices"][0] 是第一个选项（通常只有一个）
                    # ["delta"] 是增量部分
                    # .get("content", "") 获取具体文字。为什么要用 .get？
                    # 因为第一个数据块可能只有角色信息（"role": "assistant"），没有 content 字段。用 .get 防止报 KeyError 错误。
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    
                    # 6. 如果提取到了实际的文字碎片，就 yield 出去。
                    # yield 是生成器的标志，它会把数据交出去给调用者（也就是 core 里的 AgentLoop），
                    # 然后暂停在这里，等下一次循环继续。
                    if delta:
                        yield delta