# packages/server/src/agentserver/main.py
from fastapi import FastAPI
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


# ============================================================
# 1. 模块级单例：应用启动时创建一次，全进程共享
# ============================================================
settings = load_settings()
provider = OpenAICompatibleProvider(settings.app.llm)

# 1.1 创建注册表，注册内置工具（以后加工具只改这里）
registry = ToolRegistry()
registry.register(CalculatorTool())

# 1.2 创建执行器
executor = ToolExecutor(registry)

# 1.3 生成工具清单（启动时算一次，所有请求复用）
tool_definitions: list[ToolDefinition] = registry.list_definitions()

# 1.4 AgentLoop 只持有 provider，不再持有 strategy
agent_loop = AgentLoop(provider)


# ============================================================
# 2. 策略工厂：根据类型构建对应的策略实例
# ============================================================
def build_strategy(strategy_type: StrategyType):
    """根据策略类型构建策略实例。新增策略时只在这里加一个分支。"""
    if strategy_type == StrategyType.REACT:
        return ReactStrategy(
            executor=executor,
            tool_definitions=tool_definitions,
            max_steps=settings.app.agent.max_react_steps,
        )
    return ChatStrategy()


app = FastAPI(title="EnterpriseAgentServer")


# ============================================================
# 3. 健康检查
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================
# 4. 核心接口：/run（SSE 流式对话，支持按请求选择策略）
# ============================================================
@app.post("/run", response_class=EventSourceResponse)
async def run(request: RunRequest):
    # 请求带了 strategy 就用它，否则用配置文件里的默认策略
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