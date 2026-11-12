# packages/server/src/agentserver/main.py
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from agentschema import (
    load_settings, StrategyType, RunRequest, StreamChunk, ToolDefinition,
)
from agentllm import OpenAICompatibleProvider
from agentcore import (
    AgentLoop, ChatStrategy, ReactStrategy, ToolRegistry, ToolExecutor,
)
from agentmcp import MCPClientManager

# ============================================================
# 1. 配置与全局单例
# ============================================================
settings = load_settings()
provider = OpenAICompatibleProvider(settings.app.llm)

# 工具注册表与执行器（全局唯一，热重载时原地更新）
registry = ToolRegistry()
executor = ToolExecutor(registry)

# AgentLoop 只持有 provider，无状态
agent_loop = AgentLoop(provider)

# MCP 管理器列表
mcp_managers: list[MCPClientManager] = []


# ============================================================
# 2. 工具加载逻辑（供 lifespan 和热重载共用）
# ============================================================

async def load_all_tools(reload_settings: bool = False) -> None:
    """
    按当前配置加载所有工具。
    - reload_settings=True 时重新读取 config.toml
    - 先清空旧工具，再加载本地工具，再连接 MCP Server 并注册其工具
    """
    global settings, mcp_managers

    if reload_settings:
        settings = load_settings()

    # 清空旧工具
    registry.clear()

    # 关闭旧的 MCP 连接
    for manager in mcp_managers:
        try:
            await manager.close()
        except Exception:
            pass
    mcp_managers.clear()

    # ---- 加载本地工具 ----
    for local_conf in settings.app.tools.local_tools:
        if not local_conf.enabled:
            print(f"[Tools] 本地工具 {local_conf.name} 已禁用，跳过")
            continue
        try:
            registry.register_local_tool(local_conf.name)
            print(f"[Tools] 本地工具已加载：{local_conf.name}")
        except ValueError as e:
            print(f"[Tools] 本地工具加载失败：{e}")

    # ---- 加载 MCP 工具 ----
    for mcp_conf in settings.app.tools.mcp_servers:
        print(f"[MCP] 正在连接 {mcp_conf.name} ({mcp_conf.transport})...")
        manager = MCPClientManager()
        try:
            if mcp_conf.transport == "http":
                if not mcp_conf.url:
                    print(f"[MCP] 跳过 {mcp_conf.name}：未配置 url")
                    continue
                await manager.connect_streamable_http(mcp_conf.url)
            elif mcp_conf.transport == "stdio":
                if not mcp_conf.command:
                    print(f"[MCP] 跳过 {mcp_conf.name}：未配置 command")
                    continue
                await manager.connect_stdio(mcp_conf.command, mcp_conf.args)
            else:
                print(f"[MCP] 未知 transport：{mcp_conf.transport}")
                continue

            for tool in manager.tools:
                try:
                    registry.register(tool)
                except ValueError as e:
                    print(f"[MCP] 工具冲突跳过：{e}")

            mcp_managers.append(manager)
        except Exception as e:
            print(f"[MCP] 连接 {mcp_conf.name} 失败：{e}")

    print(f"[Tools] 工具注册表当前共 {len(registry)} 个工具。")


# ============================================================
# 3. FastAPI 生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await load_all_tools(reload_settings=False)
    yield
    for manager in mcp_managers:
        await manager.close()
    print("[Tools] 所有 MCP 连接已关闭。")


app = FastAPI(title="EnterpriseAgentServer", lifespan=lifespan)


# ============================================================
# 4. 策略工厂
# ============================================================

def get_tool_definitions() -> list[ToolDefinition]:
    return registry.list_definitions()


def build_strategy(strategy_type: StrategyType):
    if strategy_type == StrategyType.REACT:
        return ReactStrategy(
            executor=executor,
            tool_definitions=get_tool_definitions(),
            max_steps=settings.app.agent.max_react_steps,
        )
    return ChatStrategy()


# ============================================================
# 5. 路由
# ============================================================

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/reload-tools")
async def reload_tools():
    """
    热重载工具端点：CLI 修改 config.toml 后调用此端点，
    server 重新读取配置并加载工具，无需重启进程。
    """
    await load_all_tools(reload_settings=True)
    return {
        "status": "reloaded",
        "tools": [d.name for d in registry.list_definitions()],
        "count": len(registry),
    }


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