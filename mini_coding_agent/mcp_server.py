"""
文件作用：
提供只读的 PROJECT_NOTES.md 工具，体验 MCP 独立进程通信。

整体结构：
1）VERSION / TOOL：声明固定协议版本和工具信息；
2）serve：处理初始化、工具发现与调用，将 JSON-RPC 响应写入 stdout。

职责边界：
仅实现本实验需要的 2025-06-18 stdio 协议子集，不是通用 MCP 服务框架。
"""
import json
from pathlib import Path
import sys

VERSION = "2025-06-18"
TOOL = {"name": "project_notes", "description": "Read this workspace's PROJECT_NOTES.md acceptance notes.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False}}


def serve():
    """按初始化状态处理 stdio 请求，只开放项目说明读取。"""
    initialized = ready = False
    for line in sys.stdin:
        request_id = None
        try:
            if len(line.encode()) > 65536:
                raise ValueError("message too large")
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise ValueError("expected a JSON-RPC 2.0 object")
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            if method == "notifications/initialized" and initialized:
                ready = True
                continue
            if "id" not in request:
                continue
            if method == "initialize":
                initialized = True
                result = {"protocolVersion": VERSION, "capabilities": {"tools": {}},
                          "serverInfo": {"name": "mini-project-notes", "version": "0.1.0"}}
            elif method == "ping":
                result = {}
            elif not ready:
                raise ValueError("initialize and notifications/initialized are required")
            elif method == "tools/list":
                result = {"tools": [TOOL]}
            elif method == "tools/call":
                if params.get("name") != TOOL["name"] or params.get("arguments", {}) != {}:
                    raise ValueError("only project_notes with empty arguments is supported")
                try:
                    path = Path("/workspace/PROJECT_NOTES.md")
                    if path.is_symlink() or not path.is_file() or path.stat().st_size > 12000:
                        raise ValueError("PROJECT_NOTES.md must be a regular UTF-8 file <= 12000 bytes")
                    result = {"content": [{"type": "text", "text": path.read_text(encoding="utf-8")}], "isError": False}
                except (OSError, ValueError) as error:
                    result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
            else:
                response = {"jsonrpc": "2.0", "id": request_id,
                            "error": {"code": -32601, "message": "Method not found"}}
                print(json.dumps(response), flush=True)
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (ValueError, TypeError, AttributeError) as error:
            response = {"jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32602, "message": str(error)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    serve()
