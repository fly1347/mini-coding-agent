"""
文件作用：
验证 Skill 与 MCP 可独立启用，且核心默认不依赖它们。

整体结构：
1）setUp：为每个用例准备独立的临时工作区；
2）默认与 Skill 用例：检查扩展默认不注册，显式启用后可加载中文方法并记录工具结果；
3）MCP 成功用例：写入项目说明，核对初始化、通知、工具发现、调用的消息顺序与返回内容；
4）MCP 缺失用例：说明文件不存在时应返回工具错误，而不是成功的空内容。

验证手段：
Skill 用可控模型回复触发；MCP 真正启动 Bubblewrap 内的 stdio 服务并完成协议往返。
这些检查不请求模型 API，也不证明扩展会提高开发质量或效率。
"""
import json
from pathlib import Path
import tempfile
import unittest

from mini_coding_agent.agent import Agent
from mini_coding_agent.mcp_notes import read_notes
from mini_coding_agent.workspace import Workspace
from tests.helpers import SequenceProvider, call


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws = Workspace(self.root)

    # 未显式启用时不注册 Skill 和 MCP 工具，保持核心循环独立可用。
    def test_extensions_absent_by_default(self):
        agent = Agent(self.ws, SequenceProvider([]))
        self.assertNotIn("load_skill", agent.specs)
        self.assertNotIn("mcp_project_notes", agent.specs)

    # 用一次 load_skill 调用检查中文方法实际读出，且结果已进入运行 trace。
    def test_skill_loaded_on_demand_and_recorded(self):
        agent = Agent(self.ws, SequenceProvider([call("load_skill", name="test-repair")]), max_steps=1, skill=True)
        summary = agent.run("Inspect available repair guidance")
        events = [json.loads(x) for x in (Path(summary["run_dir"]) / "trace.jsonl").read_text().splitlines()]
        result = next(e["result"] for e in events if e["event"] == "tool_result")
        self.assertIn("运行现有测试", result["content"])
        self.assertIn("name: test-repair", result["content"])
        self.assertIn("回归用例", result["content"])

    # 通过真实 MCP 进程读取项目说明，同时核对协议顺序、响应次数和返回内容。
    def test_actual_mcp_handshake_discovery_and_call(self):
        self.ws.write("PROJECT_NOTES.md", "Add a CLI and one subprocess regression test.")
        events = []
        result = read_notes(self.ws, lambda event, **data: events.append((event, data)))
        self.assertTrue(result["ok"], result)
        self.assertIn("subprocess", result["content"][0]["text"])
        sent = [d["message"]["method"] for e, d in events if e == "mcp_send"]
        self.assertEqual(sent, ["initialize", "notifications/initialized", "tools/list", "tools/call"])
        self.assertEqual(len([e for e, _ in events if e == "mcp_receive"]), 3)

    # 项目说明缺失时保留 MCP 的 isError，并将外层结果标记为失败。
    def test_mcp_missing_notes_is_tool_error(self):
        result = read_notes(self.ws, lambda *a, **k: None)
        self.assertFalse(result["ok"])
        self.assertTrue(result["isError"])
