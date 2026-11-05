# ==============================================================================
# 1. 导入所需的工具包
# ==============================================================================
from datetime import datetime, timezone  # <--- 修改点 1：补充导入 timezone

from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4

# 导入配置类，并新增 save_settings 和 DEFAULT_CONFIG_PATH
from .config import (
    AppConfig, 
    LLMConfig, 
    StorageConfig, 
    Settings, 
    load_settings, 
    save_settings,          # <--- 修改点 2：导入保存函数
    DEFAULT_CONFIG_PATH     # <--- 导入默认路径
)

# 导入大模型协议接口（这需要你建一个 protocols.py 文件，下面有教）
from .protocols import LLMProvider  # <--- 修改点 3：导入 Protocol


# 更新导出的列表，把所有对外暴露的类都放进去
__all__ = [
    # 配置相关
    "AppConfig", "LLMConfig", "StorageConfig", "Settings", 
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


# ==============================================================================
# 3. 核心原子数据：单条消息
# ==============================================================================
class Message(BaseModel):
    """代表对话中的一句话"""
    role: Role     
    content: str   


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


# ==============================================================================
# 6. 网络通信契约：服务端流式返回的数据碎片
# ==============================================================================
class StreamChunk(BaseModel):
    """流式返回的一个片段"""
    delta: str       
    finished: bool = False