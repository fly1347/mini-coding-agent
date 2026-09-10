"""
文件作用：
验证 HTTP 模型适配与凭据处理，不发送真实 API 请求。

整体结构：
ProviderTests 替换 HTTP 返回值，检查工具调用解析、错误消息和请求配置边界。
"""
import io
import json
import unittest
from unittest.mock import patch
import urllib.error

from mini_coding_agent.provider import ChatProvider


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = ChatProvider({"LLM_API_KEY": "test-only-secret", "LLM_MODEL": "test-model",
                                      "LLM_BASE_URL": "https://example.invalid/v1"})

    def test_http_tool_call_roundtrip_and_reasoning_not_recorded(self):
        response = {"choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None, "reasoning_content": "private-reasoning",
            "tool_calls": [{"id": "abc", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]}}],
            "usage": {"total_tokens": 123}}
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.return_value = io.BytesIO(json.dumps(response).encode())
            result = self.provider.complete([{"role": "user", "content": "task"}], [], 999)
        request = build.return_value.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["max_tokens"], 999)
        self.assertEqual(body["messages"][0]["content"], "task")
        self.assertEqual(result["message"]["tool_calls"][0]["id"], "abc")
        self.assertNotIn("private-reasoning", json.dumps(result))
        self.assertNotIn("test-only-secret", json.dumps(result))

    def test_http_error_does_not_log_body_or_authorization(self):
        error = urllib.error.HTTPError(self.provider.url, 401, "test-only-secret", {}, None)
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
                self.provider.complete([], [], 100)
        self.assertNotIn("test-only-secret", str(caught.exception))

    def test_refuse_insecure_endpoint_and_unbounded_extra_body(self):
        for extra in ({"LLM_BASE_URL": "http://example.invalid"}, {"LLM_EXTRA_BODY": '{"max_tokens": 999999}'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                ChatProvider({"LLM_API_KEY": "x", "LLM_MODEL": "x", **extra})

    def test_thinking_modes_override_legacy_config_in_http_body(self):
        config = {"LLM_API_KEY": "x", "LLM_MODEL": "x",
                  "LLM_EXTRA_BODY": '{"thinking":{"type":"disabled"}}'}
        response = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        for mode in ("enabled", "disabled"):
            with self.subTest(mode=mode):
                provider = ChatProvider(config, thinking=mode)
                with patch("urllib.request.build_opener") as build:
                    build.return_value.open.return_value = io.BytesIO(json.dumps(response).encode())
                    provider.complete([], [], 100)
                body = json.loads(build.return_value.open.call_args.args[0].data)
                self.assertEqual(provider.thinking, mode)
                self.assertEqual(body["thinking"], {"type": mode})
        self.assertEqual(ChatProvider(config).thinking, "disabled")
        self.assertEqual(ChatProvider({**config, "LLM_EXTRA_BODY": '{"thinking":{"type":"enabled"}}'}).request_body([], [], 100)["thinking"], {"type": "disabled"})
        with self.assertRaises(ValueError):
            ChatProvider(config, thinking="auto")
        with self.assertRaises(ValueError):
            ChatProvider(config, thinking="invalid")
