"""
文件作用：
验证 Skill 与 MCP 可独立启用，且核心默认不依赖它们。

整体结构：
ExtensionTests 检查 Skill 按需加载，并通过真实 stdio 进程验证 MCP 握手、发现和工具错误。
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

    def test_extensions_absent_by_default(self):
        agent = Agent(self.ws, SequenceProvider([]))
        self.assertNotIn("load_skill", agent.specs)
        self.assertNotIn("mcp_project_notes", agent.specs)

    def test_skill_loaded_on_demand_and_recorded(self):
        agent = Agent(self.ws, SequenceProvider([call("load_skill", name="test-repair")]), max_steps=1, skill=True)
        summary = agent.run("Inspect available repair guidance")
        events = [json.loads(x) for x in (Path(summary["run_dir"]) / "trace.jsonl").read_text().splitlines()]
        result = next(e["result"] for e in events if e["event"] == "tool_result")
        self.assertIn("运行现有测试", result["content"])
        self.assertIn("name: test-repair", result["content"])
        self.assertIn("回归用例", result["content"])

    def test_actual_mcp_handshake_discovery_and_call(self):
        self.ws.write("PROJECT_NOTES.md", "Add a CLI and one subprocess regression test.")
        events = []
        result = read_notes(self.ws, lambda event, **data: events.append((event, data)))
        self.assertTrue(result["ok"], result)
        self.assertIn("subprocess", result["content"][0]["text"])
        sent = [d["message"]["method"] for e, d in events if e == "mcp_send"]
        self.assertEqual(sent, ["initialize", "notifications/initialized", "tools/list", "tools/call"])
        self.assertEqual(len([e for e, _ in events if e == "mcp_receive"]), 3)

    def test_mcp_missing_notes_is_tool_error(self):
        result = read_notes(self.ws, lambda *a, **k: None)
        self.assertFalse(result["ok"])
        self.assertTrue(result["isError"])
