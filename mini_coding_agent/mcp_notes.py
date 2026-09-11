"""
文件作用：
把一个固定的本地 MCP 项目说明工具接入 Agent 的工具调用。

整体结构：
1）read_notes：启动只读沙箱中的服务，完成初始化、发现和调用；
2）send：收发有大小与时间限制的 stdio JSON-RPC 消息；
3）收尾：关闭 stdin 并回收服务进程。
"""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time

from .sandbox import sandbox_argv
from .workspace import Workspace


# 调用固定的 MCP 项目说明工具，并记录完整协议往返。
def read_notes(ws: Workspace, event) -> dict:
    server = Path(__file__).with_name("mcp_server.py").resolve()
    command = sandbox_argv(ws, ["python3", "-I", "/mcp_server.py"], readonly=True, server=server)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin"})
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    request_id = 0

    # 发送一条 JSON-RPC 消息，必要时限时等待对应响应。
    def send(method, params=None, notification=False):
        nonlocal request_id
        request_id += 1
        request = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            request["params"] = params
        if not notification:
            request["id"] = request_id
        event("mcp_send", message=request)
        process.stdin.write((json.dumps(request) + "\n").encode())
        process.stdin.flush()
        if notification:
            return None
        data = bytearray()
        deadline = time.monotonic() + 5
        while b"\n" not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise ValueError("MCP response timed out")
            chunk = os.read(process.stdout.fileno(), 8192)
            if not chunk:
                raise ValueError("MCP server exited before responding; check Bubblewrap availability")
            data.extend(chunk)
            if len(data) > 65536:
                raise ValueError("MCP response too large")
        response = json.loads(data)
        event("mcp_receive", message=response)
        if response.get("jsonrpc") != "2.0" or response.get("id") != request_id or "error" in response:
            raise ValueError("invalid or unsuccessful MCP response")
        return response["result"]

    try:
        info = send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "mini-coding-agent", "version": "0.1.0"}})
        if info.get("protocolVersion") != "2025-06-18" or "tools" not in info.get("capabilities", {}):
            raise ValueError("MCP version or tools capability mismatch")
        send("notifications/initialized", notification=True)
        tools = send("tools/list")["tools"]
        if len(tools) != 1 or tools[0]["name"] != "project_notes":
            raise ValueError("bundled MCP tool was not discovered")
        result = send("tools/call", {"name": tools[0]["name"], "arguments": {}})
        return {"ok": not result.get("isError", False), "transport": "stdio", **result}
    finally:
        selector.close()
        process.stdin.close()  # 关闭 stdin，以 EOF 通知 stdio 服务结束。
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()
