"""
文件作用：
适配 OpenAI-compatible Chat Completions，将工具调用和 usage 返回给执行循环。

整体结构：
1）load_config：读取显式配置文件和 LLM_* 环境变量；
2）estimate_tokens：保留首轮冷启动估算接口；运行时校准在 budget 模块；
3）ChatProvider.complete：发送 HTTP 请求并提取模型回复。

职责边界：
凭据只用于主进程的 HTTP 请求，不传给代码执行工具，也不保存私有推理字段。
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import urllib.error
import urllib.request


def load_config(env_file: Path | None = None) -> dict[str, str]:
    """读取简单 KEY=value 配置，再用当前 LLM_* 环境变量覆盖。"""
    config = {}
    if env_file:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                raise ValueError("env file must contain KEY=value lines")
            config[key.strip()] = value.strip().strip("\"'")
    config.update({k: v for k, v in os.environ.items() if k.startswith("LLM_")})
    return config


def estimate_tokens(value) -> int:
    """兼容首轮 bytes/3+512 估算；实际循环使用近期 usage 校准。"""
    return math.ceil(len(json.dumps(value, ensure_ascii=False).encode("utf-8")) / 3) + 512


class ChatProvider:
    """封装模型 HTTP 调用，避免凭据进入工具层。"""
    def __init__(self, config: dict[str, str], *, thinking="disabled"):
        if thinking not in {"enabled", "disabled"}:
            raise ValueError("thinking must be enabled or disabled")
        self.thinking = thinking
        self.key = config.get("LLM_API_KEY", "")
        self.model = config.get("LLM_MODEL", "")
        if not self.key or not self.model:
            raise ValueError("set LLM_API_KEY and LLM_MODEL, or supply --env-file")
        base = config.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not base.startswith("https://"):
            raise ValueError("LLM_BASE_URL must use HTTPS")
        self.url = base + "/chat/completions"
        self.extra = json.loads(config.get("LLM_EXTRA_BODY", "{}"))
        if not isinstance(self.extra, dict) or set(self.extra) - {"thinking"}:
            raise ValueError('LLM_EXTRA_BODY only supports a provider-specific "thinking" field')
        # 程序默认显式关闭思考，只有用户指定 enabled 才开启；覆盖旧配置。
        self.extra.pop("thinking", None)
        self.extra["thinking"] = {"type": thinking}

    def request_body(self, messages, tools, max_tokens):
        """统一构造请求体，供预估与实际发送复用。"""
        return {"model": self.model, "messages": messages, "tools": tools,
                "tool_choice": "auto", "max_tokens": max_tokens, **self.extra}

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int) -> dict:
        """请求一次模型回复，返回工具调用、用量和结束原因。"""
        body = self.request_body(messages, tools, max_tokens)
        request = urllib.request.Request(self.url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                         headers={"Authorization": "Bearer " + self.key,
                                                  "Content-Type": "application/json"})
        # 禁止重定向，避免将 Authorization 转发到其他主机。
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise RuntimeError("model response exceeds 2 MiB")
            data = json.loads(raw)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"model HTTP {error.code}; check model, endpoint and credentials") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError("model network/timeout error; no automatic retries") from None
        choice = data["choices"][0]
        message = choice["message"]
        # 只保留公开回复与工具调用，不记录私有推理字段。
        clean = {"role": "assistant", "content": message.get("content")}
        if message.get("tool_calls"):
            clean["tool_calls"] = message["tool_calls"]
        return {"message": clean, "usage": data.get("usage"),
                "finish_reason": choice.get("finish_reason")}
