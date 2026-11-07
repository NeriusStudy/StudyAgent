# packages/server/src/agentserver/main.py

# ==================== 新增 1：导入 asynccontextmanager ====================
from contextlib import asynccontextmanager

from fastapi import FastAPI
# 注意：你原代码里是 sse_startlette，如果这里是拼写错误，请确保改成 sse_starlette
from sse_starlette.sse import EventSourceResponse

from agentschema import (
    load_settings,
    StrategyType,
    RunRequest,
    StreamChunk,
    ToolDefinition,
)
from agentllm import OpenAICompatibleProvider
from agentcore import (
    AgentLoop,
    ChatStrategy,
    ReactStrategy,
    ToolRegistry,
    ToolExecutor,
)
from agentcore.tools.builtin.calculator import CalculatorTool

# ==================== 新增 2：导入 MCP 客户端管理器 ====================
from agentmcp import MCPClientManager

# 1. 模块级单例：应用启动时创建一次，全进程共享
settings = load_settings()
provider = OpenAICompatibleProvider(settings.app.llm)

# 1.1 创建注册表，注册内置工具
registry = ToolRegistry()
registry.register(CalculatorTool())

# 1.2 创建执行器（保持不变，它持有 registry 的引用，后续 MCP 工具注册后自动生效）
executor = ToolExecutor(registry)

# 1.4 AgentLoop 只持有 provider，不再持有 strategy
agent_loop = AgentLoop(provider)

# ==================== 修改 1：删除模块级的 tool_definitions ====================
# 原代码：tool_definitions: list[ToolDefinition] = registry.list_definitions()
# 原因：MCP 工具在 lifespan 启动时才会注册，写死在这里会漏掉 MCP 工具。

# ==================== 新增 3：MCP 管理器与生命周期管理 ====================
mcp_manager = MCPClientManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 连接到已经独立运行的 Everything Streamable HTTP Server
    await mcp_manager.connect_streamable_http("http://localhost:3001/mcp")
    # await mcp_manager.connect_stdio(
    #     command="npx",
    #     args=["-y", "@modelcontextprotocol/server-everything"],
    # )
    for tool in mcp_manager.tools:
        registry.register(tool)
    print(f"[Server] 工具注册表现有 {len(registry)} 个工具。")
    yield
    await mcp_manager.close()

# ==================== 修改 2：给 FastAPI 加上 lifespan ====================
app = FastAPI(title="EnterpriseAgentServer", lifespan=lifespan)

# ==================== 新增 4：动态获取最新工具清单 ====================
def get_tool_definitions() -> list[ToolDefinition]:
    """每次请求时动态生成工具清单，确保包含最新的 MCP 工具。"""
    return registry.list_definitions()

# 2. 策略工厂：根据类型构建对应的策略实例
def build_strategy(strategy_type: StrategyType):
    if strategy_type == StrategyType.REACT:
        return ReactStrategy(
            executor=executor,                       # 保持不变（它引用的 registry 已更新）
            tool_definitions=get_tool_definitions(), # <--- 修改：改为动态获取
            max_steps=settings.app.agent.max_react_steps,
        )
    return ChatStrategy()

# 3. 健康检查（保持不变）
@app.get("/health")
async def health():
    return {"status": "ok"}

# 4. 核心接口：/run（SSE流式对话，支持按请求选择策略）（保持不变）
@app.post("/run", response_class=EventSourceResponse)
async def run(request: RunRequest):
    strategy_type = request.strategy or settings.app.agent.strategy
    strategy = build_strategy(strategy_type)

    async def event_generator():
        async for delta in agent_loop.run_stream(
            request.session_id,
            request.user_input,
            strategy,
        ):
            yield StreamChunk(delta=delta).model_dump_json()

    return EventSourceResponse(event_generator())