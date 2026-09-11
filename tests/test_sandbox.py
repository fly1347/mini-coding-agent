"""
文件作用：
通过真实子进程验证命令隔离、超时和输出上限。

整体结构：
1）setUp：创建临时母目录与其中的 workspace，分别作为越界目标和可写区域；
2）隔离探针：尝试写宿主、系统和证据路径，访问网络、凭据，再验证普通工作区写入；
3）资源用例：用休眠和持续输出脚本检查超时终止、输出上限及返回文本截断；
4）命令用例：直接调用 parse_command，拒绝 shell 注入、越界脚本和未开放的执行方式。

验证边界：
执行探针使用真实 Bubblewrap 子进程，需要系统允许相应命名空间；命令解析不模拟沙箱。
这里只检查已列举的隔离行为，不构成对任意恶意程序或生产多租户安全性的证明。
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

    # 在同一个真实探针中检查越界、网络与凭据隔离，并确认允许的工作区写入仍成功。
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
        # 注入可识别的假密钥验证环境清理，随后恢复母进程原值，避免污染其他测试。
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

    # 给长休眠脚本设置短超时，检查执行被及时终止并明确报告 timeout。
    def test_timeout_kills_command(self):
        self.ws.write("slow.py", "import time\ntime.sleep(5)\n")
        result = run_command(self.ws, "python3 slow.py", timeout=0.3)
        self.assertEqual(result["termination"], "timeout", result)
        self.assertLess(result["duration_seconds"], 2)

    # 持续输出触发 output_limit，返回给调用方的文本也必须保持有界。
    def test_output_is_bounded(self):
        self.ws.write("noisy.py", 'while True: print("x" * 10000, flush=True)\n')
        result = run_command(self.ws, "python3 noisy.py")
        self.assertEqual(result["termination"], "output_limit", result)
        self.assertLessEqual(len(result["output"]), 16000)

    # 在启动进程前拒绝 shell 语法、目录穿越、内联代码和依赖安装命令。
    def test_reject_shell_injection_and_other_executables(self):
        for command in ("bash -c ls", "python3 -c pass", "python3 x.py; touch /tmp/x",
                        "python3 ../x.py", "python3 -m pip install x", "python3 x.py $(id)"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                parse_command(command)
