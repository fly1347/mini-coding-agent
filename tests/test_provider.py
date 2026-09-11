"""
文件作用：
验证 HTTP 模型适配与凭据处理，不发送真实 API 请求。

整体结构：
1）setUp：用虚构凭据与无效域名创建待测 ChatProvider；
2）响应与错误用例：检查请求参数和 Tool Call 解析，确保结果与异常不泄露密钥或推理正文；
3）配置用例：拒绝 HTTP 明文端点和越过白名单的额外请求字段；
4）Thinking 用例：检查显式模式覆盖旧配置、默认关闭，以及无效档位被拒绝。

验证手段：
替换 urllib 的 opener，用内存字节流和 HTTPError 模拟响应，再检查实际构造的请求。
测试不连接模型服务；能验证适配代码行为，不能证明某个远端模型支持这些请求字段。
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

    # 模拟含工具调用和私有推理的响应，检查请求构造正确且返回结果只保留公开字段。
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

    # 把测试密钥放进 HTTP 错误信息，确认对外异常只报告状态码而不回显敏感内容。
    def test_http_error_does_not_log_body_or_authorization(self):
        error = urllib.error.HTTPError(self.provider.url, 401, "test-only-secret", {}, None)
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
                self.provider.complete([], [], 100)
        self.assertNotIn("test-only-secret", str(caught.exception))

    # 分别注入不安全端点和额度覆盖字段，确认配置校验在请求发出前拒绝它们。
    def test_refuse_insecure_endpoint_and_unbounded_extra_body(self):
        for extra in ({"LLM_BASE_URL": "http://example.invalid"}, {"LLM_EXTRA_BODY": '{"max_tokens": 999999}'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                ChatProvider({"LLM_API_KEY": "x", "LLM_MODEL": "x", **extra})

    # 检查两档显式选择与默认关闭都落实到 HTTP 请求体，并拒绝旧 auto 和非法值。
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
