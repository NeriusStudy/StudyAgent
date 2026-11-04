# packages/cli/src/agentcli/main.py
import typer
import asyncio
import json
import httpx
import tomli_w
from pathlib import Path
from typing import Optional
from agentschema import Settings, AppConfig, load_settings

# 创建 Typer 应用实例
app = typer.Typer(help="Enterprise Agent 命令行工具", no_args_is_help=True)

# 全局配置路径（默认当前目录下的 config.toml）
CONFIG_PATH = Path("config.toml")

# =======================
# 辅助函数：加载与保存配置
# =======================
# 辅助函数：直接调用底层加载器
def get_config() -> Settings:
    return load_settings(CONFIG_PATH)

def save_config(settings: Settings):
    """将配置写入 TOML 文件"""
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(settings.app.model_dump(), f)
    typer.secho(f"✅ 配置已保存至 {CONFIG_PATH.absolute()}", fg=typer.colors.GREEN)

# =======================
# 1. 命令组：config (用于修改配置)
# =======================
config_app = typer.Typer(help="管理 Agent 配置")
app.add_typer(config_app, name="config")

@config_app.command("set")
def set_config(
    key: str = typer.Argument(..., help="配置键名，例如 llm.api_key, storage.db_url"),
    value: str = typer.Argument(..., help="配置的值")
):
    """修改配置（例如：agentcli config set llm.api_key sk-xxx）"""
    settings = get_config()
    
    # 解析嵌套键，如 llm.api_key
    parts = key.split(".")
    if len(parts) != 2:
        typer.secho("❌ 错误：配置键必须为 '分组.字段' 格式，如 'llm.api_key'", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    group, field = parts
    if not hasattr(settings.app, group):
        typer.secho(f"❌ 错误：未知的配置分组 '{group}'", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    group_obj = getattr(settings.app, group)
    if not hasattr(group_obj, field):
        typer.secho(f"❌ 错误：未知的配置字段 '{field}'", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # 修改值
    setattr(group_obj, field, value)
    save_config(settings)

@config_app.command("show")
def show_config():
    """显示当前所有配置"""
    settings = get_config()
    typer.echo(f"当前配置 ({CONFIG_PATH.absolute()}):")
    typer.echo(json.dumps(settings.app.model_dump(), indent=2, ensure_ascii=False))

# =======================
# 2. 命令：chat (用于对话)
# =======================
@app.command("chat")
def chat(
    message: str = typer.Argument(..., help="你想对 AI 说的话"),
    session: str = typer.Option("default-session", "--session", "-s", help="会话 ID"),
    url: str = typer.Option("http://127.0.0.1:8000/run", "--url", "-u", help="服务端地址")
):
    """发送消息并流式接收回复"""
    settings = get_config()
    
    # 检查是否配置了 API Key
    if not settings.app.llm.api_key:
        typer.secho("⚠️ 警告：尚未配置 API Key，请先运行 `agentcli config set llm.api_key 你的密钥`", fg=typer.colors.YELLOW)

    async def _run():
        payload = {"session_id": session, "user_input": message}
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:].strip()
                            if not data:
                                continue
                            chunk = json.loads(data)
                            typer.echo(chunk.get("delta", ""), nl=False)
                typer.echo() # 换行
            except httpx.ConnectError:
                typer.secho("❌ 无法连接到服务端，请确保 `uv run --package agentserver uvicorn agentserver.main:app --port 8000` 已经启动", fg=typer.colors.RED)

    asyncio.run(_run())

# =======================
# 程序入口
# =======================
if __name__ == "__main__":
    app()