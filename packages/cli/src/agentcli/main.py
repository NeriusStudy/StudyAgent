# ==============================================================================
# 1. 导入所需的工具包
# ==============================================================================
# asyncio: Python 标准库的异步 IO 框架。因为我们的网络请求是异步的，需要它来启动事件循环。
import asyncio

# json: 用来把服务器传回来的 JSON 字符串解析成 Python 的字典。
import json

# sys: 用来读取终端命令行传入的参数（比如你在终端敲的 "你好"）。
import sys

# httpx: 现代化的异步 HTTP 客户端，用来向服务端发起网络请求。
import httpx


# ==============================================================================
# 2. 全局配置
# ==============================================================================
# 服务端的接口地址。目前是本地启动的 FastAPI 服务。
# 以后如果部署到云服务器，只需把这里改成比如 "https://api.yourdomain.com/run" 即可。
SERVER_URL = "http://127.0.0.1:8000/run"


# ==============================================================================
# 3. 核心交互函数：发送请求并接收流式响应
# ==============================================================================
async def chat(session_id: str, user_input: str):
    """
    这是一个异步函数，负责完成一次完整的对话。
    
    参数:
    - session_id: 会话的唯一标识。服务端靠它来区分“你是谁”，从而记住你们之前的聊天记录。
    - user_input: 你这次想在终端里对 AI 说的话。
    """
    # 组装要发给服务端的 JSON 数据。
    # 注意这里的键名 "session_id" 和 "user_input" 必须与后端 agentschema 里的 RunRequest 定义完全一致。
    payload = {"session_id": session_id, "user_input": user_input}
    
    # 创建异步 HTTP 客户端。
    # timeout=None 是关键：大模型思考可能很慢，如果设置了超时（比如默认 5 秒），
    # 大模型还没想出来，客户端就主动断开连接了。这里必须设为 None（永不超时）。
    async with httpx.AsyncClient(timeout=None) as client:
        
        # client.stream 是流式请求的核心。
        # 普通的 client.post 会等服务器把所有数据都返回完才给你；
        # 而 client.stream 就像接了一根水管，服务器吐一点，我们就能立刻处理一点。
        async with client.stream("POST", SERVER_URL, json=payload) as resp:
            
            # 检查 HTTP 状态码。如果服务端报错（如 500 内部错误、422 参数校验失败），
            # 这里会立刻抛出异常，防止后续代码强行解析错误数据。
            resp.raise_for_status()
            
            # 按“行”异步迭代服务器的返回内容。
            # 服务端返回的是标准的 SSE (Server-Sent Events) 格式，长相如下：
            #   data: {"delta": "你", "finished": false}
            #   data: {"delta": "好", "finished": false}
            #   data: {"delta": "", "finished": true}
            async for line in resp.aiter_lines():
                
                # 过滤掉非数据行。SSE 协议中有时候会有空行或者 "event: xxx" 这样的控制行，我们只要 "data: " 开头的。
                if line.startswith("data: "):
                    
                    # 切片操作：把前 6 个字符（也就是 "data: "）切掉，只保留后面的 JSON 字符串。
                    # .strip() 去掉首尾多余的空格和换行符。
                    data = line[6:].strip()
                    
                    # 如果是空数据，直接跳过。
                    if not data:
                        continue
                    
                    # 把 JSON 字符串反序列化成 Python 字典。
                    # 例如：'{"delta": "你"}' -> {"delta": "你"}
                    chunk = json.loads(data)
                    
                    # 提取字典里的 "delta" 字段，也就是那一小段文字。
                    # 用 .get("delta", "") 而不是 chunk["delta"] 是为了防崩溃：
                    # 假如服务器最后发了个结束信号 {"finished": true} 没带 delta，.get 会返回空字符串，不会报错。
                    # print 的参数：
                    # end="" 意思是打印完不换行，让字连着字；
                    # flush=True 极其重要：强制刷新缓冲区。如果不加，终端可能会攒够一整行才显示，失去了“打字机”的效果。
                    print(chunk.get("delta", ""), end="", flush=True)
    
    # 整个对话结束后，打印一个换行，让终端提示符回到下一行，看着更舒服。
    print()


# ==============================================================================
# 4. 程序入口
# ==============================================================================
# 这行代码是 Python 的标准魔法：只有当这个文件被直接运行（而不是被当作模块导入）时，才会执行下面的代码。
if __name__ == "__main__":
    
    # sys.argv 包含了你在终端敲下的所有参数。
    # sys.argv[0] 是脚本名字（比如 main.py）。
    # sys.argv[1] 才是你真正输入的问题。
    # 如果你只敲了脚本名没带问题，长度就会小于 2。
    if len(sys.argv) < 2:
        # 友好提示怎么使用。⚠️注意：你这里的提示词写的是 agent_cli.main（带下划线），
        # 但你的包名叫 agentcli（没下划线），建议这里改成正确的。
        print("用法: uv run --package agentcli python -m agentcli.main \"你的问题\"")
        sys.exit(1) # 退出程序，返回错误码 1
    
    # 为本地测试指定一个固定的会话 ID。
    # 这意味着只要你这个终端不关，不管问几次，AI 都能记得你之前说的话（服务端有历史记录）。
    # 以后如果做真正的命令行工具，可以在这里使用随机生成的 UUID，实现每次启动都是全新会话。
    session_id = "local-test-session"
    
    # asyncio.run() 是启动异步程序的“点火钥匙”。
    # 它会创建一个事件循环，运行我们定义的 chat 函数，直到 chat 里的所有 await 结束。
    # 把你在终端输入的真实问题（sys.argv[1]）传进去。
    asyncio.run(chat(session_id, sys.argv[1]))