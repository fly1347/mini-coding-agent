"""验证报告的真实用量口径、缺失覆盖、退出状态以及不复制源码的阅读边界。"""
import json
from pathlib import Path
import tempfile
import unittest

from mini_coding_agent.agent import Agent
from mini_coding_agent.reporting import cell, usage_summary
from mini_coding_agent.workspace import Workspace
from tests.helpers import SequenceProvider, call


class ReportingTests(unittest.TestCase):
    def test_mixed_provider_usage_and_partial_coverage(self):
        events = [{"event": "model_response", "usage": usage} for usage in [
            {"prompt_tokens": 100, "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20,
             "completion_tokens": 30, "total_tokens": 130},
            {"prompt_tokens": 200, "prompt_tokens_details": {"cached_tokens": 150},
             "completion_tokens": 40, "completion_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 240},
            None]]
        result = usage_summary(events)
        self.assertEqual(result["prompt_tokens"], 300)
        self.assertEqual(result["cache_hit_tokens"], 230)
        self.assertEqual(result["cache_miss_tokens"], 20)  # 不从 prompt - hit 推导缺失字段。
        self.assertEqual(result["completion_tokens"], 70)
        self.assertEqual(result["total_tokens"], 370)
        self.assertEqual(result["reasoning_tokens"], 0)
        self.assertEqual(result["reported_calls"]["reasoning_tokens"], 1)
        self.assertEqual(result["reported_calls"]["prompt_tokens"], 2)
        self.assertEqual(result["model_responses"], 3)

    def test_missing_invalid_and_duplicate_aliases(self):
        result = usage_summary([{"event": "model_response", "usage": {
            "total_tokens": True, "prompt_tokens": -1, "completion_tokens": "2",
            "prompt_cache_hit_tokens": 5, "prompt_tokens_details": {"cached_tokens": 5},
            "completion_tokens_details": "invalid"}}])
        self.assertIsNone(result["total_tokens"])
        self.assertIsNone(result["prompt_tokens"])
        self.assertIsNone(result["completion_tokens"])
        self.assertIsNone(result["reasoning_tokens"])
        self.assertEqual(result["cache_hit_tokens"], 5)
        self.assertIsNone(usage_summary([])["total_tokens"])

    def test_all_incomplete_exits_have_honest_reports(self):
        for responses, options, status, calls in [
            ([call("list_files")], {"token_budget": 1}, "token_budget", 0),
            ([call("list_files")], {}, "step_budget", 1),
            ([RuntimeError("service unavailable")], {}, "error", 1),
            ([KeyboardInterrupt()], {}, "interrupted", 1),
        ]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                result = Agent(Workspace(Path(tmp)), SequenceProvider(responses), max_steps=1, **options).run("创建程序")
                root = Path(result["run_dir"])
                report = (root / "RUN_REPORT.md").read_text()
                self.assertEqual(json.loads((root / "summary.json").read_text()), result)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["model_calls"], calls)
                self.assertIn(f"**{status}**", report)
                self.assertIn("没有当前有效", report)
                self.assertIn("未提供", report)
                self.assertNotIn("有效证据：", report)

    def test_reserved_budget_is_not_reported_usage(self):
        response = call("list_files")
        response["usage"] = None
        with tempfile.TemporaryDirectory() as tmp:
            result = Agent(Workspace(Path(tmp)), SequenceProvider([response]), max_steps=1).run("创建程序")
            self.assertGreater(result["tokens"], 0)
            self.assertIsNone(result["usage"]["total_tokens"])
            self.assertEqual(result["usage"]["reported_calls"]["total_tokens"], 0)

    def test_table_escapes_multiline_and_markup(self):
        self.assertEqual(cell("a|b\n<script>`"), "a&#124;b &lt;script&gt;&#96;")
        self.assertEqual(cell("abcdef", 3), "abc…")

    def test_run_summary_timing_and_outer_report_survive_rerun(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(Path(tmp))
            provider = SequenceProvider([])
            provider.extra = {"thinking": {"type": "disabled"}}
            with patch("mini_coding_agent.agent.time.monotonic", side_effect=[10, 52.8]):
                first = Agent(workspace, provider, token_budget=1).run("创建一个 CLI")
            first_path = Path(first["run_dir"]) / "RUN_REPORT.md"
            preserved = first_path.read_bytes()
            report = (workspace.root / "RUN_REPORT.md").read_text()
            self.assertIn("# Mini Coding Agent 运行报告", report)
            self.assertIn("- 总耗时：42.8 s", report)
            self.assertIn("- Thinking：disabled", report)
            self.assertIn(f"- Run ID：{first_path.parent.name}", report)
            self.assertIn(f"](.mini-agent/runs/{first_path.parent.name}/trace.jsonl)", report)
            self.assertEqual(workspace.snapshot(), {})
            with self.assertRaises(ValueError):
                workspace.write("RUN_REPORT.md", "overwrite evidence")
            second = Agent(workspace, SequenceProvider([]), token_budget=1).run("另一次任务")
            self.assertNotEqual(first["run_dir"], second["run_dir"])
            self.assertEqual(first_path.read_bytes(), preserved)
            self.assertIn("另一次任务", (workspace.root / "RUN_REPORT.md").read_text())
            self.assertEqual(workspace.snapshot(), {})

    def test_demo_default_task_names_and_explicit_destination(self):
        from unittest.mock import patch
        from scripts import demo
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            for extra, expected in [([], "slugify-create-20260910-141023"),
                                    (["--task-name", "job-tracker-v2"], "job-tracker-v2-20260910-141023"),
                                    (["--dest", str(project / "manual")], "manual")]:
                with self.subTest(extra=extra), patch.object(demo, "PROJECT", project), \
                     patch.object(demo.time, "strftime", return_value="20260910-141023"), \
                     patch.object(demo, "load_config", return_value={}), \
                     patch.object(demo, "ChatProvider"), patch.object(demo, "Agent") as agent, \
                     patch("sys.argv", ["demo.py", "--env-file", "unused", *extra]):
                    agent.return_value.run.return_value = {"status": "completed"}
                    self.assertEqual(demo.main(), 0)
                    root = agent.call_args.args[0].root
                    self.assertEqual(root.name, expected)
                    self.assertEqual(list(root.iterdir()), [])
                    with self.assertRaises(FileExistsError):
                        demo.main()


    def test_cli_and_demo_forward_thinking_modes(self):
        from unittest.mock import patch
        from mini_coding_agent import __main__ as cli
        from scripts import demo
        with tempfile.TemporaryDirectory() as tmp:
            for module in (cli, demo):
                for mode in (None, "enabled", "disabled"):
                    destination = Path(tmp) / (module.__name__ + str(mode))
                    if module is cli:
                        destination.mkdir()
                        argv = ["mini_coding_agent", str(destination), "创建程序"]
                    else:
                        argv = ["demo.py", "--dest", str(destination), "--env-file", "unused"]
                    if mode is not None:
                        argv += ["--thinking", mode]
                    argv += ["--max-input-tokens", "200000",
                             "--max-output-tokens", "40000", "--max-output-per-call", "6000"]
                    with self.subTest(entry=module.__name__, mode=mode), \
                         patch("sys.argv", argv), patch.object(module, "load_config", return_value={}), \
                         patch.object(module, "ChatProvider") as provider, patch.object(module, "Agent") as agent:
                        agent.return_value.run.return_value = {"status": "completed"}
                        self.assertEqual(module.main(), 0)
                        provider.assert_called_once_with({}, thinking=mode or "disabled")
                        self.assertEqual(agent.call_args.kwargs["max_input_tokens"], 200000)
                        self.assertEqual(agent.call_args.kwargs["max_output_tokens"], 40000)
                        self.assertEqual(agent.call_args.kwargs["max_output_per_call"], 6000)
