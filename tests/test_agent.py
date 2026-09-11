"""
文件作用：
验证单 Agent 的计划门禁、失败修复、预算退出和交付证据。

整体结构：
1）setUp / run_agent / start：复制修复样例、准备查看与计划步骤，返回运行汇总和 trace；
2）开发闭环用例：让真实测试先失败，再修改源码、补回归并引用验证结果交付；
3）门禁用例：拒绝未查看就计划、未计划就执行、伪造证据、改动后的旧验证和空测试；
4）停止与恢复用例：检查预算前置拦截、模型异常留痕、参数错误回填和缺失用量扣账；
5）空目录用例：验证列目录后可以保存计划并创建首个源文件。

验证手段：
SequenceProvider 提供可控模型回复，文件修改和 Bubblewrap 中的测试真实执行；
只操作临时副本，通过状态、文件和事件断言检查运行器，不冒充真实 LLM 开发实验。
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from mini_coding_agent.agent import Agent, DEFAULT_VERIFY
from mini_coding_agent.workspace import Workspace
from tests.helpers import FIX, PLAN, SequenceProvider, call, finish_last

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/slugify"


class AgentTests(unittest.TestCase):
    # 为每个用例复制独立的缺陷样例，避免一次修复改变其他用例的起点。
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "workspace"
        shutil.copytree(EXAMPLE, self.root, ignore=shutil.ignore_patterns("__pycache__"))
        self.ws = Workspace(self.root)

    # 用预设回复驱动真实工具，返回汇总、事件及可检查请求历史的 Provider。
    def run_agent(self, responses, **options):
        provider = SequenceProvider(responses)
        agent = Agent(self.ws, provider, max_steps=options.pop("max_steps", len(responses)), **options)
        result = agent.run("Fix slugify and verify the documented behavior.")
        events = [json.loads(line) for line in (Path(result["run_dir"]) / "trace.jsonl").read_text().splitlines()]
        return result, events, provider

    # 准备已有项目合法进入修改阶段所需的读文件和保存计划调用。
    def start(self):
        return [call("read_file", path="slugify.py", start_line=1), call("save_plan", **PLAN)]

    # 先观察真实失败再修复和补测，检查成功交付引用了后续回归结果且产物齐全。
    def test_real_failure_repair_regression_delivery(self):
        # 确认反馈确实包含测试失败后才给出修复，避免只回放一串无条件动作。
        def repair_after_failure(messages):
            output = json.loads(messages[-1]["content"])
            self.assertEqual(output["exit_code"], 1)
            self.assertIn("AssertionError", output["output"])
            return call("write_file", path="slugify.py", content=FIX)
        result, events, _ = self.run_agent(self.start() + [
            call("run_shell", command=DEFAULT_VERIFY), repair_after_failure,
            call("write_file", path="test_edges.py", content='import unittest\nfrom slugify import slugify\nclass Edges(unittest.TestCase):\n    def test_empty(self):\n        self.assertEqual(slugify("!!!"), "")\n'),
            call("run_shell", command=DEFAULT_VERIFY), finish_last])
        self.assertEqual(result["status"], "completed", events)
        self.assertEqual(result["changed_files"], ["slugify.py", "test_edges.py"])
        exits = [e["result"]["exit_code"] for e in events if e["event"] == "tool_result" and e["name"] == "run_shell"]
        self.assertEqual(exits, [1, 0])
        report = (Path(result["run_dir"]) / "RUN_REPORT.md").read_text()
        self.assertIn("tool-0003：失败", report)
        self.assertIn("tool-0004：修改 slugify.py", report)
        self.assertIn("tool-0006：执行", report)
        self.assertIn("有效证据：tool-0006", report)
        self.assertIn("AssertionError", report)
        for name in ("PLAN.md", "trace.jsonl", "FINAL.md", "summary.json", "RUN_REPORT.md"):
            self.assertTrue((Path(result["run_dir"]) / name).stat().st_size)

    # 不满足查看和计划前置条件时，修改、执行与伪造证据交付都应被拒绝。
    def test_plan_gate_and_false_delivery_rejected(self):
        result, events, _ = self.run_agent([
            call("write_file", path="slugify.py", content=FIX),
            call("run_shell", command=DEFAULT_VERIFY),
            call("save_plan", **PLAN),
            call("finish", summary="done", verification_id="invented")])
        self.assertEqual(result["status"], "step_budget")
        self.assertNotEqual(self.ws.read("slugify.py"), FIX)
        self.assertEqual(len([e for e in events if e["event"] == "tool_result" and not e["result"]["ok"]]), 4)

    # 完整测试通过后再次改源码，确认旧 Tool ID 不能继续作为交付证据。
    def test_edit_after_verification_invalidates_evidence(self):
        result, events, _ = self.run_agent(self.start() + [
            call("write_file", path="slugify.py", content=FIX), call("run_shell", command=DEFAULT_VERIFY),
            call("write_file", path="slugify.py", content=FIX + "# changed\n"),
            call("finish", summary="done", verification_id="tool-0004")])
        self.assertEqual(result["status"], "step_budget")
        self.assertFalse([e for e in events if e["event"] == "tool_result"][-1]["result"]["ok"])

    # 对比失败测试与零测试两种运行，确认退出码为零也不能让空测试套件通过验收。
    def test_empty_suite_is_not_success(self):
        result, events, _ = self.run_agent(self.start() + [call("run_shell", command="python3 -m unittest"), finish_last],
                                            verify_command="python3 -m unittest")
        # 先检查已有失败测试，再移除临时副本的测试以验证空套件不能交付。
        self.assertNotEqual(result["status"], "completed")
        for path in self.root.glob("test_*.py"):
            path.unlink()
        result, events, _ = self.run_agent(self.start() + [call("run_shell", command=DEFAULT_VERIFY), finish_last])
        shell_result = next(e["result"] for e in events if e["event"] == "tool_result" and e["name"] == "run_shell")
        self.assertEqual(shell_result["exit_code"], 0)
        self.assertFalse(shell_result["verification_accepted"])
        report = (Path(result["run_dir"]) / "RUN_REPORT.md").read_text()
        self.assertIn("命令成功但验收未接受", report)
        self.assertIn("Ran 0 tests", report)
        self.assertEqual(result["status"], "step_budget")

    # 预算不足以发起首轮请求时直接停止，Provider 不应收到任何调用。
    def test_token_budget_stops_before_model_call(self):
        result, _, provider = self.run_agent([call("list_files")], token_budget=1)
        self.assertEqual(result["status"], "token_budget")
        self.assertEqual(provider.seen, [])

    # 模型调用抛出异常时仍保存停止说明，不能因异常丢失交付状态。
    def test_provider_error_still_writes_final(self):
        result, events, _ = self.run_agent([RuntimeError("simulated service unavailable")])
        self.assertEqual(result["status"], "error")
        self.assertIn("service unavailable", (Path(result["run_dir"]) / "FINAL.md").read_text())

    # 注入损坏的工具参数 JSON，确认错误作为反馈进入下一轮而非终止整个循环。
    def test_invalid_arguments_return_to_model_for_recovery(self):
        bad = call("read_file", path="slugify.py", start_line=1)
        bad["message"]["tool_calls"][0]["function"]["arguments"] = "{bad"
        result, _, provider = self.run_agent([bad, call("read_file", path="slugify.py", start_line=1)])
        self.assertEqual(result["status"], "step_budget")
        self.assertFalse(json.loads(provider.seen[-1][-1]["content"])["ok"])

    # 空工作区没有文件可读时，列目录即可进入计划和首个文件创建流程。
    def test_empty_workspace_can_plan_and_create(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        agent = Agent(Workspace(empty), SequenceProvider([call("list_files"), call("save_plan", **PLAN),
                      call("write_file", path="hello.py", content="print('hello')\n")]), max_steps=3)
        result = agent.run("Create a hello world script")
        self.assertEqual(result["changed_files"], ["hello.py"])

    # 模型未返回 usage 时采用预留额扣账，并在事件中明确标记该口径。
    def test_missing_usage_uses_conservative_accounting(self):
        response = call("list_files")
        response.pop("usage")
        result, events, _ = self.run_agent([response])
        self.assertGreater(result["tokens"], 4096)
        self.assertEqual(next(e for e in events if e["event"] == "model_response")["accounting"], "reserved")
