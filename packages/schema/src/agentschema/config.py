# packages/schema/src/agentschema/config.py
import shutil
import tomllib
import tomli_w
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 统一定义默认路径
DEFAULT_CONFIG_PATH = Path("config.toml")

# 1. 定义各个模块的配置子集
class LLMConfig(BaseModel):
    base_url: str = Field(default="https://api.deepseek.com/v1", description="API基础地址")
    api_key: str = Field(default="", description="API密钥")
    model: str = Field(default="deepseek-chat", description="使用的模型名称")

class StorageConfig(BaseModel):
    log_dir: str = Field(default="./logs", description="日志存储目录")
    db_url: str = Field(default="sqlite:///./agent.db", description="数据库连接地址")
    memory_path: str = Field(default="./memory", description="本地记忆存储路径")

class StrategyType(str, Enum):
    CHAT = "chat"
    REACT = "react"

class AgentConfig(BaseModel):
    strategy: StrategyType = StrategyType.CHAT
    max_react_steps: int = 10

# ================= 新增：MCP 配置 =================
class MCPServerConfig(BaseModel):
    name: str = Field(description="MCP Server 的唯一名称，用于日志和调试")
    transport: str = Field(default="stdio", description="传输方式: 'stdio' 或 'http'")
    
    # stdio 模式专用
    command: str = Field(default="", description="执行命令，如 'npx'")
    args: list[str] = Field(default_factory=list, description="命令参数列表")
    
    # http 模式专用
    url: str = Field(default="", description="HTTP MCP 的地址，如 'http://localhost:3001/mcp'")

class ToolsConfig(BaseModel):
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list, description="需要连接的 MCP 服务器列表")
# =================================================

# 2. 顶级配置类
class AppConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig) # 新增 tools 配置

# 3. 配置文件管理类
class Settings(BaseSettings):
    config_file: Path = Path("config.toml")
    app: AppConfig = Field(default_factory=AppConfig)

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_nested_delimiter="__",
        extra="ignore"
    )

def load_settings(config_path: Path = Path("config.toml")) -> Settings:
    if not config_path.exists():
        example_path = Path("config.example.toml")
        if example_path.exists():
            shutil.copy(example_path, config_path)
            print(f"提示: 未找到 {config_path}, 已自动为您生成。")
            print(f"提示: 请打开 {config_path} 文件, 填入您的真实 API Key!")
        else:
            print(f"提示: 未找到配置文件, 将使用默认配置。")

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        return Settings(app=AppConfig(**data))

    return Settings()

def save_settings(settings: Settings, config_path: Path = DEFAULT_CONFIG_PATH):
    with open(config_path, "wb") as f:
        tomli_w.dump(settings.app.model_dump(exclude_none=True), f)

__all__ = [
    "AppConfig", "LLMConfig", "StorageConfig", "AgentConfig", 
    "ToolsConfig", "MCPServerConfig", "StrategyType", 
    "Settings", "load_settings", "save_settings", "DEFAULT_CONFIG_PATH"
]