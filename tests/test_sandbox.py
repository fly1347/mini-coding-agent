"""
文件作用：
通过真实子进程验证命令隔离、超时和输出上限。

整体结构：
SandboxTests 在临时 workspace 中运行探针，检查宿主文件、私有路径、网络及进程终止结果。
"""
import json
import os
from pathlib import Path
import tempfile
import unittest

from mini_coding_agent.sandbox import parse_command, run_command
from mini_coding_agent.workspace import Workspace


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir()
        self.ws = Workspace(self.root)

    def test_actual_isolation_and_private_artifact_masks(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("untouched")
        (self.root / ".mini-agent").mkdir()
        (self.root / ".mini-agent/trace.jsonl").write_text("evidence")
        (self.root / ".env").write_text("secret")
        script = '''import json, os, socket
from pathlib import Path
result = {}
for name, path in [("outside", OUTSIDE), ("system", "/usr/mini-agent-probe"),
                   ("trace", ".mini-agent/trace.jsonl")]:
    try:
        Path(path).write_text("bad")
        result[name] = "WRITTEN"
    except OSError:
        result[name] = "blocked"
try:
    socket.create_connection(("1.1.1.1", 80), timeout=0.2)
    result["network"] = "CONNECTED"
except OSError:
    result["network"] = "blocked"
result["secret_env"] = os.getenv("LLM_API_KEY")
try:
    result["env_file"] = Path(".env").read_text()
except OSError:
    result["env_file"] = "blocked"
Path("allowed.txt").write_text("inside")
print(json.dumps(result))
'''.replace("OUTSIDE", repr(str(outside)))
        self.ws.write("probe.py", script)
        previous = os.environ.get("LLM_API_KEY")
        os.environ["LLM_API_KEY"] = "do-not-forward"
        try:
            result = run_command(self.ws, "python3 probe.py")
        finally:
            if previous is None:
                os.environ.pop("LLM_API_KEY", None)
            else:
                os.environ["LLM_API_KEY"] = previous
        self.assertEqual(result["exit_code"], 0, result)
        observation = json.loads(result["output"])
        self.assertEqual(observation, {"outside": "blocked", "system": "blocked", "trace": "blocked",
                                       "network": "blocked", "secret_env": None,
                                       "env_file": observation["env_file"]})
        self.assertIn(observation["env_file"], ("", "blocked"))
        self.assertEqual(outside.read_text(), "untouched")
        self.assertEqual((self.root / ".mini-agent/trace.jsonl").read_text(), "evidence")
        self.assertEqual((self.root / "allowed.txt").read_text(), "inside")

    def test_timeout_kills_command(self):
        self.ws.write("slow.py", "import time\ntime.sleep(5)\n")
        result = run_command(self.ws, "python3 slow.py", timeout=0.3)
        self.assertEqual(result["termination"], "timeout", result)
        self.assertLess(result["duration_seconds"], 2)

    def test_output_is_bounded(self):
        self.ws.write("noisy.py", 'while True: print("x" * 10000, flush=True)\n')
        result = run_command(self.ws, "python3 noisy.py")
        self.assertEqual(result["termination"], "output_limit", result)
        self.assertLessEqual(len(result["output"]), 16000)

    def test_reject_shell_injection_and_other_executables(self):
        for command in ("bash -c ls", "python3 -c pass", "python3 x.py; touch /tmp/x",
                        "python3 ../x.py", "python3 -m pip install x", "python3 x.py $(id)"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                parse_command(command)
