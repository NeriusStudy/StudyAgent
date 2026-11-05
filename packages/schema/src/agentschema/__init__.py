# ==============================================================================
# 1. 导入所需的工具包
# ==============================================================================
from datetime import datetime, timezone  # <--- 补充导入 timezone
from typing import Optional, List, Any

from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4

# 导入配置类
from .config import (
    AppConfig,
    AgentConfig,            # 新增
    StrategyType,           # 新增
    LLMConfig,
    StorageConfig,
    Settings,
    load_settings,
    save_settings,
    DEFAULT_CONFIG_PATH,
)

# 导入大模型协议接口（这需要你建一个 protocols.py 文件，下面有教）
from .protocols import LLMProvider, ToolHandler  # <--- 导入 Protocol


# 更新导出的列表，把所有对外暴露的类都放进去
__all__ = [
    # 配置相关
    "AppConfig", "AgentConfig", "StrategyType", "LLMConfig", "StorageConfig", "Settings",
    "load_settings", "save_settings", "DEFAULT_CONFIG_PATH",
    # 协议相关
    "LLMProvider",
    # 数据模型
    "Role", "Message", "SessionEvent", "RunRequest", "StreamChunk",
]


# ==============================================================================
# 2. 基础枚举：定义“角色”
# ==============================================================================
class Role(str, Enum):
    USER = "user"           # 用户输入
    ASSISTANT = "assistant" # AI（助手）回复
    SYSTEM = "system"       # 系统提示词
    TOOL = "tool"          # 新增：工具执行结果的角色

# ==============================================================================
# 工具调用相关的数据模型
# ==============================================================================
class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str          # 原始 JSON 字符串，交给 Pydantic 校验

class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict        # JSON Schema，由 Pydantic model_json_schema() 生成


# ==============================================================================
# 3. 核心原子数据：单条消息
# ==============================================================================
class Message(BaseModel):
    role: Role
    content: Optional[str] = None
    tool_calls: Optional[List["ToolCall"]] = None   # assistant 发起的工具调用
    tool_call_id: Optional[str] = None              # tool 消息对应的调用 ID


# ==============================================================================
# 4. 事件溯源基础：会话事件
# ==============================================================================
class SessionEvent(BaseModel):
    """会话事件"""
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    message: Message
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. 网络通信契约：客户端发给服务端的请求体
# ==============================================================================
class RunRequest(BaseModel):
    """客户端发来的请求"""
    session_id: str
    user_input: str
    strategy: Optional[StrategyType] = None   # 可选：请求级覆盖默认策略

# ==============================================================================
# 6. 网络通信契约：服务端流式返回的数据碎片
# ==============================================================================
class StreamChunk(BaseModel):
    """流式返回的一个片段"""
    delta: str       
    finished: bool = False