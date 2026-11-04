# packages/schema/src/agentschema/config.py
import tomllib
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 1. 定义各个模块的配置子集
class LLMConfig(BaseModel):
    """大模型提供商配置"""
    base_url: str = Field(default="https://api.deepseek.com/v1", description="API基础地址")
    api_key: str = Field(default="", description="API密钥")
    model: str = Field(default="deepseek-chat", description="使用的模型名称")

class StorageConfig(BaseModel):
    """存储配置 (为未来的记忆、日志、数据库预留)"""
    log_dir: str = Field(default="./logs", description="日志存储目录")
    db_url: str = Field(default="sqlite:///./agent.db", description="数据库连接地址")
    memory_path: str = Field(default="./memory", description="本地记忆存储路径")

# 2. 顶级配置类，组合所有子配置
class AppConfig(BaseModel):
    """全局应用配置"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

# 3. 配置文件管理类
class Settings(BaseSettings):
    """
    继承自 BaseSettings，它会自动帮忙处理：
    1. 从环境变量读取（优先级最高）
    2. 从 .env 文件读取
    3. 提供默认值
    """
    # 指定配置文件的默认路径 (当前工作目录下的 config.toml)
    config_file: Path = Path("config.toml")
    
    # 核心配置对象
    app: AppConfig = Field(default_factory=AppConfig)

    model_config = SettingsConfigDict(
        env_prefix="AGENT_", # 以后环境变量可以写成 AGENT_APP_LLM__API_KEY
        env_nested_delimiter="__",
        extra="ignore"
    )

# 4. 新增：通用的配置加载函数
def load_settings(config_path: Path = Path("config.toml")) -> Settings:
    """
    企业级配置加载器：
    优先读取本地 config.toml，如果不存在则使用默认配置。
    以后如果要接入环境变量，也可以在这里做优先级合并。
    """
    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        # 注意：TOML 文件的最顶层就是 llm 和 storage，对应 AppConfig
        return Settings(app=AppConfig(**data))
    
    # 如果连配置文件都没有（比如刚 clone 下来），就用默认值
    return Settings()

# 导出配置类
__all__ = ["AppConfig", "LLMConfig", "StorageConfig", "Settings"]