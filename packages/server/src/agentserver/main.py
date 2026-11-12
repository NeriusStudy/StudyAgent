# packages/server/src/agentserver/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from agentschema import (
    load_settings, StrategyType, RunRequest, StreamChunk, ToolDefinition,
)
from agentllm import OpenAICompatibleProvider
from agentcore import (
    AgentLoop, ChatStrategy, ReactStrategy, ToolRegistry, ToolExecutor,
)
from agentcore.tools.builtin.calculator import CalculatorTool
from agentmcp import MCPClientManager

# 1. 加载配置
settings = load_settings()
provider = OpenAICompatibleProvider(settings.app.llm)

# 2. 工具注册表：先注册本地工具
registry = ToolRegistry()
registry.register(CalculatorTool())

# 3. 执行器
executor = ToolExecutor(registry)

# 4. AgentLoop
agent_loop = AgentLoop(provider)

# 5. MCP 管理器列表（支持同时连多个 MCP Server）
mcp_managers: list[MCPClientManager] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ================= 启动时：根据配置连接所有的 MCP Server =================
    for mcp_conf in settings.app.tools.mcp_servers:
        print(f"[Server] 正在连接 MCP Server: {mcp_conf.name} ({mcp_conf.transport})...")
        manager = MCPClientManager()
        
        try:
            if mcp_conf.transport == "http":
                if not mcp_conf.url:
                    print(f"[Server] 跳过 {mcp_conf.name}：未配置 url")
                    continue
                await manager.connect_streamable_http(mcp_conf.url)
            elif mcp_conf.transport == "stdio":
                if not mcp_conf.command:
                    print(f"[Server] 跳过 {mcp_conf.name}：未配置 command")
                    continue
                await manager.connect_stdio(mcp_conf.command, mcp_conf.args)
            else:
                print(f"[Server] 未知的 transport 类型: {mcp_conf.transport}")
                continue
                
            # 将发现的工具注册进 registry
            for tool in manager.tools:
                try:
                    registry.register(tool)
                except ValueError as e:
                    print(f"[Server] 工具冲突跳过: {e}")
            
            mcp_managers.append(manager)
        except Exception as e:
            print(f"[Server] 连接 MCP Server {mcp_conf.name} 失败: {e}")

    print(f"[Server] 工具注册表现有 {len(registry)} 个工具。")
    
    yield # 应用开始处理请求
    
    # ================= 关闭时：清理所有 MCP 连接 =================
    for manager in mcp_managers:
        await manager.close()

app = FastAPI(title="EnterpriseAgentServer", lifespan=lifespan)

def get_tool_definitions() -> list[ToolDefinition]:
    """每次请求时动态生成工具清单，确保包含最新的 MCP 工具。"""
    return registry.list_definitions()

def build_strategy(strategy_type: StrategyType):
    if strategy_type == StrategyType.REACT:
        return ReactStrategy(
            executor=executor,
            tool_definitions=get_tool_definitions(),
            max_steps=settings.app.agent.max_react_steps,
        )
    return ChatStrategy()

@app.get("/health")
async def health():
    return {"status": "ok"}

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