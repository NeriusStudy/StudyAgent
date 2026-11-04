# ==============================================================================
# 1. 导入所需工具包
# ==============================================================================
# FastAPI：Web 框架，负责接收 HTTP 请求、路由分发、返回响应。
from fastapi import FastAPI

# EventSourceResponse：注意！它不在 fastapi 里，而在 sse-starlette 这个第三方包里。
# SSE（Server-Sent Events）是一种“服务器单向推送”的协议，非常适合大模型流式输出。
# 它做的事：把你 yield 出来的每一段内容，自动包装成 SSE 标准格式 "data: xxx\n\n"，并推给客户端。
# ⚠️ 前置条件：packages/server/pyproject.toml 的 dependencies 里必须有 "sse-starlette"。
from sse_starlette.sse import EventSourceResponse

# 从底层的 agentschema 包导入请求体结构和流式碎片结构。
# ⚠️ 包名是 agentschema（无下划线），不是 agent_schema。
from agentschema import RunRequest, StreamChunk

# 从 agentllm 包导入 Provider 实现。
# ⚠️ 包名是 agentllm（无下划线）。
from agentllm import OpenAICompatibleProvider

# 从 agentcore 包导入 AgentLoop。
# ⚠️ 包名是 agentcore（无下划线）。
from agentcore import AgentLoop


# ==============================================================================
# 2. 模块级“单例”：在应用启动时创建一次，全进程共享
# ==============================================================================
# 为什么要写在模块顶层（而不是写在 /run 函数里）？
# - Provider 内部要读环境变量、可能还要维护 HTTP 连接池，每次请求都新建会浪费资源。
# - AgentLoop 内部维护了 _sessions 字典（内存中的会话历史）。如果每次请求都新建，
#   会话历史会瞬间丢失，多轮对话就废了。必须全局唯一。
#
# ⚠️ 注意这里的“早失败”设计：
# 如果启动时没设置 LLM_BASE_URL 环境变量，OpenAICompatibleProvider() 会立刻抛 ValueError，
# 导致整个 uvicorn 服务直接起不来（这是好事，把配置错误暴露在启动阶段，
# 而不是等用户第一次发消息时才 500）。
provider = OpenAICompatibleProvider()

# 把 provider 注入给 AgentLoop（依赖注入）。
# AgentLoop 只管业务逻辑，不知道 provider 是怎么配置的。
agent_loop = AgentLoop(provider)


# ==============================================================================
# 3. 创建 FastAPI 应用实例
# ==============================================================================
# title 参数会显示在 FastAPI 自动生成的 Swagger 文档页（/docs）上，方便调试。
app = FastAPI(title="Minimal Agent Server")


# ==============================================================================
# 4. 健康检查接口
# ==============================================================================
@app.get("/health")
async def health():
    """
    健康检查端点。
    用途：Docker/K8s 探针、CI 冒烟测试、监控系统定期轮询。
    只要返回 200 且 body 是 {"status": "ok"}，就代表服务进程活着。
    注意：它不检查大模型是否可用（那会很慢），只检查 Web 进程本身。
    """
    return {"status": "ok"}


# ==============================================================================
# 5. 核心接口：/run（SSE 流式对话）
# ==============================================================================
# response_class=EventSourceResponse：
#   这个参数主要用于让 FastAPI 在 /docs 文档页里正确标注返回类型为 SSE（text/event-stream）。
#   真正生效的还是要靠下面手动 return EventSourceResponse(...)。
#   方法用 POST 而不是 GET：
#   因为要传 JSON 请求体（session_id + user_input），GET 的 URL 传参既丑又有限制。
#   代价：浏览器原生 EventSource 对象只能发 GET，所以客户端必须用 fetch 或 httpx 流式读，
#   这一点在你的 cli 里已经处理好了。
@app.post("/run", response_class=EventSourceResponse)
async def run(request: RunRequest):
    """
    SSE 流式接口。
    
    请求流程：
      1. 客户端 POST 一个 JSON（符合 RunRequest 结构）。
      2. FastAPI 自动用 Pydantic 校验，校验失败返回 422。
      3. 进入本函数，调用 agent_loop.run_stream 异步生成器。
      4. 每得到一段文字，包装成 StreamChunk，转成 JSON 字符串，yield 出去。
      5. EventSourceResponse 负责把每个 yield 的值包装成 "data: {json}\n\n" 推给客户端。
      6. 生成器耗尽时，SSE 连接自动关闭。
    
    为什么这里要再包一层 event_generator？
      因为 EventSourceResponse 需要一个“异步可迭代对象”（async generator）。
      而 agent_loop.run_stream 的产出是“裸的字符串碎片”，
      我们需要把它转换成“符合 schema 契约的 StreamChunk JSON”，
      所以用一个内层生成器做适配。
    """
    # 内层异步生成器：负责数据格式转换
    async def event_generator():
        # 从 AgentLoop 拿流式文字碎片。
        # async for 会一直循环，直到 provider 那边吐出 [DONE] 或抛出异常。
        async for delta in agent_loop.run_stream(request.session_id, request.user_input):
            # 把裸字符串封装成标准化的 StreamChunk 对象。
            # 好处：以后要往碎片里加字段（比如 token 用量、工具调用信息），
            # 只要改 StreamChunk 的定义即可，客户端解析逻辑不用乱改。
            chunk = StreamChunk(delta=delta)
            
            # model_dump_json() 是 Pydantic 提供的方法，
            # 把对象序列化成 JSON 字符串，例如：
            #   StreamChunk(delta="你", finished=False)
            #   → '{"delta":"你","finished":false}'
            # EventSourceResponse 收到这个字符串后，会自动加上 "data: " 前缀和双换行。
            # 所以客户端实际收到的是：
            #   data: {"delta":"你","finished":false}\n\n
            # 这与 cli 里 line[6:] 的解析逻辑完全对应。
            yield chunk.model_dump_json()

    # 返回 SSE 响应对象。
    # 注意：这里没有 await，因为 EventSourceResponse 是作为响应对象被 FastAPI 返回的，
    # FastAPI 会在后台自动迭代 event_generator 并推流。
    return EventSourceResponse(event_generator())