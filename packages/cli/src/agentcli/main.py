# packages/cli/src/agentcli/main.py
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer

from agentschema import (
    Settings, AppConfig, load_settings, save_settings, DEFAULT_CONFIG_PATH,
    StrategyType, LocalToolConfig, MCPServerConfig,
)

# ============================================================
# Typer 应用
# ============================================================
app = typer.Typer(help="Enterprise Agent 命令行工具", no_args_is_help=True)

# 配置路径（统一使用 agentschema 的默认路径）
CONFIG_PATH = DEFAULT_CONFIG_PATH


# ============================================================
# 辅助函数
# ============================================================

def get_config() -> Settings:
    return load_settings(CONFIG_PATH)


def save_config(settings: Settings):
    save_settings(settings, CONFIG_PATH)
    typer.secho("配置已保存", fg=typer.colors.GREEN)


# ============================================================
# 1. config 命令组（原有功能）
# ============================================================
config_app = typer.Typer(help="管理 Agent 配置")
app.add_typer(config_app, name="config")


@config_app.command("set")
def set_config(
    key: str = typer.Argument(..., help="配置键名，例如 llm.api_key"),
    value: str = typer.Argument(..., help="配置的值"),
):
    """修改配置（例如：agentcli config set llm.api_key sk-xxx）"""
    settings = get_config()
    parts = key.split(".")
    if len(parts) != 2:
        typer.secho("错误：配置键必须为 '分组.字段' 格式", fg=typer.colors.RED)
        raise typer.Exit(1)

    group, field = parts
    if not hasattr(settings.app, group):
        typer.secho(f"错误：未知的配置分组 '{group}'", fg=typer.colors.RED)
        raise typer.Exit(1)

    group_obj = getattr(settings.app, group)
    if not hasattr(group_obj, field):
        typer.secho(f"错误：未知的配置字段 '{field}'", fg=typer.colors.RED)
        raise typer.Exit(1)

    setattr(group_obj, field, value)
    save_config(settings)


@config_app.command("show")
def show_config():
    """显示当前所有配置"""
    settings = get_config()
    typer.echo(f"当前配置（{CONFIG_PATH.absolute()}）:")
    typer.echo(json.dumps(settings.app.model_dump(), indent=2, ensure_ascii=False))


# ============================================================
# 2. tool 命令组（新增：管理工具配置）
# ============================================================
tool_app = typer.Typer(help="管理 Agent 的工具配置")
app.add_typer(tool_app, name="tool")


@tool_app.command("list")
def list_tools():
    """列出当前配置中的所有工具（本地 + MCP）"""
    settings = get_config()
    tools_cfg = settings.app.tools

    typer.secho("=== 本地工具 ===", fg=typer.colors.CYAN)
    if not tools_cfg.local_tools:
        typer.echo("  （无）")
    for t in tools_cfg.local_tools:
        status = "启用" if t.enabled else "禁用"
        typer.echo(f"  - {t.name}  [{status}]")

    typer.secho("=== MCP Server ===", fg=typer.colors.CYAN)
    if not tools_cfg.mcp_servers:
        typer.echo("  （无）")
    for m in tools_cfg.mcp_servers:
        detail = m.url if m.transport == "http" else f"{m.command} {' '.join(m.args)}"
        typer.echo(f"  - {m.name}  ({m.transport})  {detail}")


@tool_app.command("add-local")
def add_local_tool(
    name: str = typer.Argument(..., help="本地工具名称，对应 agentcore/tools/builtin/ 下的模块名"),
):
    """添加一个本地工具到配置中"""
    settings = get_config()
    tools_cfg = settings.app.tools

    for t in tools_cfg.local_tools:
        if t.name == name:
            typer.secho(f"错误：本地工具 '{name}' 已存在", fg=typer.colors.RED)
            raise typer.Exit(1)

    tools_cfg.local_tools.append(LocalToolConfig(name=name, enabled=True))
    save_config(settings)
    typer.secho(f"本地工具 '{name}' 已添加", fg=typer.colors.GREEN)


@tool_app.command("remove-local")
def remove_local_tool(
    name: str = typer.Argument(..., help="要删除的本地工具名称"),
):
    """从配置中删除一个本地工具"""
    settings = get_config()
    tools_cfg = settings.app.tools

    original_len = len(tools_cfg.local_tools)
    tools_cfg.local_tools = [t for t in tools_cfg.local_tools if t.name != name]

    if len(tools_cfg.local_tools) == original_len:
        typer.secho(f"错误：本地工具 '{name}' 不存在", fg=typer.colors.RED)
        raise typer.Exit(1)

    save_config(settings)
    typer.secho(f"本地工具 '{name}' 已删除", fg=typer.colors.GREEN)


@tool_app.command("add-mcp")
def add_mcp_server(
    name: str = typer.Argument(..., help="MCP Server 的唯一名称"),
    transport: str = typer.Argument(..., help="传输方式: 'stdio' 或 'http'"),
    command: Optional[str] = typer.Option(None, "--command", "-c", help="stdio 模式的执行命令"),
    args: Optional[str] = typer.Option(None, "--args", "-a", help="stdio 模式的命令参数，空格分隔"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="http 模式的地址"),
):
    """添加一个 MCP Server 到配置中"""
    settings = get_config()
    tools_cfg = settings.app.tools

    for m in tools_cfg.mcp_servers:
        if m.name == name:
            typer.secho(f"错误：MCP Server '{name}' 已存在", fg=typer.colors.RED)
            raise typer.Exit(1)

    if transport == "stdio":
        if not command:
            typer.secho("错误：stdio 模式必须提供 --command", fg=typer.colors.RED)
            raise typer.Exit(1)
        args_list = args.split() if args else []
        mcp = MCPServerConfig(
            name=name, transport="stdio",
            command=command, args=args_list,
        )
    elif transport == "http":
        if not url:
            typer.secho("错误：http 模式必须提供 --url", fg=typer.colors.RED)
            raise typer.Exit(1)
        mcp = MCPServerConfig(name=name, transport="http", url=url)
    else:
        typer.secho(f"错误：未知 transport '{transport}'", fg=typer.colors.RED)
        raise typer.Exit(1)

    tools_cfg.mcp_servers.append(mcp)
    save_config(settings)
    typer.secho(f"MCP Server '{name}' 已添加", fg=typer.colors.GREEN)


@tool_app.command("remove-mcp")
def remove_mcp_server(
    name: str = typer.Argument(..., help="要删除的 MCP Server 名称"),
):
    """从配置中删除一个 MCP Server"""
    settings = get_config()
    tools_cfg = settings.app.tools

    original_len = len(tools_cfg.mcp_servers)
    tools_cfg.mcp_servers = [m for m in tools_cfg.mcp_servers if m.name != name]

    if len(tools_cfg.mcp_servers) == original_len:
        typer.secho(f"错误：MCP Server '{name}' 不存在", fg=typer.colors.RED)
        raise typer.Exit(1)

    save_config(settings)
    typer.secho(f"MCP Server '{name}' 已删除", fg=typer.colors.GREEN)


# ============================================================
# 3. chat 命令
# ============================================================

@app.command("chat")
def chat(
    message: str = typer.Argument(..., help="你想对 AI 说的话"),
    session: str = typer.Option("default-session", "--session", "-s", help="会话 ID"),
    url: str = typer.Option("http://127.0.0.1:8000/run", "--url", "-u", help="服务端地址"),
    strategy: Optional[StrategyType] = typer.Option(
        None, "--strategy", "-t",
        help="选择策略: chat / react（不传则用服务端配置的默认策略）",
    ),
):
    """发送消息并流式接收回复"""
    settings = get_config()
    if not settings.app.llm.api_key:
        typer.secho("警告：尚未配置 API Key，请先运行 agentcli config set llm.api_key 你的密钥",
                    fg=typer.colors.YELLOW)

    payload = {"session_id": session, "user_input": message}
    if strategy is not None:
        payload["strategy"] = strategy.value

    async def _run():
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
                    typer.echo()
            except httpx.ConnectError:
                typer.secho(
                    "无法连接到服务端，请确保 `uv run --package agentserver uvicorn agentserver.main:app --port 8000` 已经启动",
                    fg=typer.colors.RED,
                )

    asyncio.run(_run())


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    app()