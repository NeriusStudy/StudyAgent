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
from agentschema import Message


# ==============================================================================
# 2. 定义 Provider 类
# ==============================================================================
class OpenAICompatibleProvider:
    """
    一个极简的 OpenAI 兼容 Provider（提供商）。
    什么是“OpenAI 兼容”？因为现在市面上 90% 的大模型（DeepSeek、通义千问、Kimi、本地跑的 Ollama 等）
    都模仿了 OpenAI 的 API 接口格式。只要我们的代码按 OpenAI 的格式发请求，这些模型都能通吃。
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        """
        初始化方法。
        参数带有默认值 None，代表“如果调用时不传参数，我就去环境变量里找；如果环境变量也没有，就用写死的默认值”。
        这样做的好处是：代码非常灵活，以后部署到服务器上，只要改环境变量，不用改一行代码。
        """
        # 1. 设置 API 的基础地址 (Base URL)
        # os.environ.get("LLM_BASE_URL", "")：从环境变量读取，如果没有则返回空字符串。
        # .rstrip("/")：去掉 URL 末尾多余的斜杠。比如用户填了 "https://api.deepseek.com/v1/"，自动变成 "https://api.deepseek.com/v1"，防止后面拼接路径时出现双斜杠 "//"。
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        
        # 2. 设置 API 密钥
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        
        # 3. 设置模型名称
        # 如果环境变量里没配置，默认使用 "gpt-4o-mini"（仅作为兜底）
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")

        # 4. 早失败原则 (Fail Fast)
        # 如果连地址都没有，说明配置严重错误，直接抛出异常（报错），不要等到发请求时才报错。
        if not self.base_url:
            raise ValueError("LLM_BASE_URL 未设置，请检查你的环境变量！")

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
            "model": self.model, # 告诉服务器用哪个模型
            # 列表推导式：把 Pydantic 的 Message 对象，转换为纯字典。
            # 注意 m.role.value：因为我们的 Role 是 Enum，必须取 .value 才能得到纯字符串 "user"。
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "stream": True, # 极其关键！开启流式输出（打字机效果）
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