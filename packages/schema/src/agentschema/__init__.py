# ==============================================================================
# 1. 导入所需的工具包
# ==============================================================================
# datetime: 用于生成和记录时间戳（比如事件是什么时候发生的）
from datetime import datetime

# Enum: Python 标准库中的枚举类。用来定义一组有限的、固定的常量。
from enum import Enum

# BaseModel: Pydantic 的核心类。只要继承了它，你的数据就能自动被校验类型，并且能一键转为 JSON。
# Field: Pydantic 的辅助工具。用来给字段设置默认值、默认生成规则（比如自动生成 ID）。
from pydantic import BaseModel, Field

# uuid4: 生成全局唯一的随机 ID（比如类似 "550e8400-e29b-41d4-a716-446655440000" 的字符串）。
from uuid import uuid4

# AppConfig, LLMConfig, StorageConfig, Settings, load_settings: 我们自己定义的配置类，放在 agentschema/config.py 里。
from .config import AppConfig, LLMConfig, StorageConfig, Settings, load_settings

# 导出的类列表，方便其他模块直接从 agentschema 导入。
__all__ = [
    "AppConfig", "LLMConfig", "StorageConfig", "Settings", "load_settings",
]

# ==============================================================================
# 2. 基础枚举：定义“角色”
# ==============================================================================
# 为什么同时继承 str 和 Enum？
# 1. 继承 Enum 是为了在代码里限制：只能是这三个选项之一，写错（比如写 "bot"）会报错。
# 2. 继承 str 是为了在转成 JSON 发给大模型 API 时，它自动变成纯字符串 "user"，而不是带有 Enum 包装的复杂对象（OpenAI 等大模型 API 只认纯字符串）。
class Role(str, Enum):
    USER = "user"           # 用户输入
    ASSISTANT = "assistant" # AI（助手）回复
    SYSTEM = "system"       # 系统提示词（比如 "你是一个有用的助手"）


# ==============================================================================
# 3. 核心原子数据：单条消息
# ==============================================================================
class Message(BaseModel):
    """
    代表对话中的“一句话”。
    大模型（如 OpenAI/DeepSeek）接收的历史对话，本质上就是一个 Message 列表：
    [ {"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"} ]
    """
    role: Role     # 这句话是谁说的（必须是 Role 枚举里的值）
    content: str   # 这句话的具体内容（纯文本）


# ==============================================================================
# 4. 事件溯源基础：会话事件
# ==============================================================================
class SessionEvent(BaseModel):
    """会话事件，目前只放消息，以后可以加工具调用事件"""
    
    # 唯一标识这一个事件。Field(default_factory=...) 是关键：
    # 不能直接写 id: str = uuid4().hex，因为那样会在类定义时只生成一次 ID，导致所有实例用同一个 ID。
    # 使用 default_factory 传入一个匿名函数，意思是：“每次实例化这个类时，请重新调用这个函数生成一个新 ID”。
    id: str = Field(default_factory=lambda: uuid4().hex)
    
    # 这个事件属于哪一个会话？（用于区分不同用户的对话，或者同一用户的多个聊天窗口）
    session_id: str
    
    # 嵌套结构：一个事件里包含一个 Message 对象。
    # Pydantic 会自动帮你校验传入的字典结构是否符合 Message 的要求。
    message: Message
    
    # 事件发生的时间。default_factory=datetime.utcnow 会在每次创建时自动调用，获取当前 UTC 时间。
    # 注意：在最新的 Pydantic v2 中，推荐写成 default_factory=lambda: datetime.now(timezone.utc) 以免出现弃用警告。
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. 网络通信契约：客户端发给服务端的请求体
# ==============================================================================
class RunRequest(BaseModel):
    """客户端发来的请求"""
    # 客户端告诉服务端：“请在哪个会话里，处理我的这条新输入”
    session_id: str   # 会话标识符
    user_input: str   # 用户刚刚敲下的那一句话（纯文本）


# ==============================================================================
# 6. 网络通信契约：服务端流式返回的数据碎片
# ==============================================================================
class StreamChunk(BaseModel):
    """流式返回的一个片段"""
    # 大模型是像“打字机”一样一个字一个字返回的。
    # delta 代表“增量”，即这一瞬间新吐出来的那几个字。
    # 比如模型说 "你好世界"，我们可能会收到 4 个 StreamChunk，delta 分别是 "你", "好", "世", "界"。
    delta: str       
    
    # 标记流是否结束了。客户端看到这个为 True，就可以停止接收了（目前这个极简版本暂时用不到，但预留好位置，以后扩展很有用）。
    finished: bool = False