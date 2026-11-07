# packages/mcp/src/agentmcp/client.py

import asyncio
import httpx
from contextlib import AsyncExitStack
from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from .adapter import MCPToolAdapter


class MCPClientManager:
    """
    管理一个 MCP Server 连接。
    支持两种传输模式：
    - stdio（本地进程）
    - Streamable HTTP（远程服务）
    """
    def __init__(self):
        self._session: ClientSession | None = None
        self.tools: list[MCPToolAdapter] = []
        self._exit_stack = AsyncExitStack()
        
        # HTTP 模式专用
        self._transport_cm = None
        self._session_cm = None
        self._http_client: httpx.AsyncClient | None = None
        self._owner_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._ready_future: asyncio.Future | None = None
        self._closed_future: asyncio.Future | None = None

    async def connect_stdio(self, command: str, args: list[str] | None = None):
        """
        以 stdio 方式启动并连接一个 MCP Server。
        """
        server_params = StdioServerParameters(
            command=command,
            args=args or [],
        )
        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()

        result = await self._session.list_tools()
        self.tools = [MCPToolAdapter(self._session, t) for t in result.tools]
        print(f"[MCP] 已连接 stdio，发现 {len(self.tools)} 个工具：{[t.name for t in self.tools]}")

    async def connect_streamable_http(self, url: str, headers: dict | None = None):
        """
        以 Streamable HTTP 方式连接远程 MCP Server。
        整个上下文生命周期在一个专属后台 Task 中运行，避免 anyio cancel scope 跨任务错误。
        """
        self._stop_event = asyncio.Event()
        self._ready_future = asyncio.get_running_loop().create_future()
        self._closed_future = asyncio.get_running_loop().create_future()

        self._owner_task = asyncio.create_task(
            self._run_http_lifecycle(url, headers)
        )

        # 等待后台 Task 完成连接和工具发现
        await self._ready_future
        print(f"[MCP] 已连接 HTTP Server，发现 {len(self.tools)} 个工具：{[t.name for t in self.tools]}")

    async def _run_http_lifecycle(self, url: str, headers: dict | None = None):
        """专属后台 Task：拥有 streamable_http_client 和 ClientSession 的完整生命周期。"""
        self._http_client = httpx.AsyncClient(
            headers=headers or {},
            timeout=httpx.Timeout(30.0, read=300.0),
        )
        try:
            self._transport_cm = streamable_http_client(url, http_client=self._http_client)
            read_stream, write_stream = await self._transport_cm.__aenter__()

            self._session_cm = ClientSession(read_stream, write_stream)
            self._session = await self._session_cm.__aenter__()

            await self._session.initialize()
            result = await self._session.list_tools()
            self.tools = [MCPToolAdapter(self._session, t) for t in result.tools]

            # 通知调用方：连接就绪
            if not self._ready_future.done():
                self._ready_future.set_result(None)

            # 等待关闭信号
            await self._stop_event.wait()

        except Exception as e:
            # 连接失败，通知调用方并退出
            if not self._ready_future.done():
                self._ready_future.set_exception(e)
        finally:
            # 在这个 Task 内部完成所有清理，保证 anyio cancel scope 在同一 Task 中退出
            if self._session_cm is not None:
                try:
                    await self._session_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            if self._transport_cm is not None:
                try:
                    await self._transport_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            if self._http_client is not None:
                await self._http_client.aclose()

            if not self._closed_future.done():
                self._closed_future.set_result(None)

    async def close(self):
        """统一关闭逻辑：兼容 stdio 和 HTTP 两种模式"""
        if self._owner_task is not None:
            # HTTP 模式：通知后台 Task 自行关闭
            if self._stop_event is not None:
                self._stop_event.set()
            await self._owner_task
            if self._closed_future is not None:
                await self._closed_future
        else:
            # stdio 模式：直接退出 AsyncExitStack
            await self._exit_stack.aclose()
            
        print("[MCP] 连接已关闭。")