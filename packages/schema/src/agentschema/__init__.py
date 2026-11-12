# packages/schema/src/agentschema/__init__.py
from datetime import datetime, timezone
from typing import Optional, List, Any
from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4

from .config import (
    AppConfig, AgentConfig, StrategyType, LLMConfig, StorageConfig,
    ToolsConfig, LocalToolConfig, MCPServerConfig,
    Settings, load_settings, save_settings, DEFAULT_CONFIG_PATH,
)
from .protocols import LLMProvider, ToolHandler

__all__ = [
    # 配置相关
    "AppConfig", "AgentConfig", "StrategyType", "LLMConfig", "StorageConfig",
    "ToolsConfig", "LocalToolConfig", "MCPServerConfig",
    "Settings", "load_settings", "save_settings", "DEFAULT_CONFIG_PATH",
    # 协议相关
    "LLMProvider", "ToolHandler",
    # 数据模型
    "Role", "Message", "SessionEvent", "RunRequest", "StreamChunk",
    "ToolCall", "ToolResult", "ToolDefinition",
]


# ============================================================
# 基础枚举
# ============================================================
class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# ============================================================
# 工具调用数据模型
# ============================================================
class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict


# ============================================================
# 核心原子数据
# ============================================================
class Message(BaseModel):
    role: Role
    content: Optional[str] = None
    tool_calls: Optional[List["ToolCall"]] = None
    tool_call_id: Optional[str] = None


# ============================================================
# 事件溯源
# ============================================================
class SessionEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    message: Message
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# 网络通信契约
# ============================================================
class RunRequest(BaseModel):
    session_id: str
    user_input: str
    strategy: Optional[StrategyType] = None


class StreamChunk(BaseModel):
    delta: str
    finished: bool = False