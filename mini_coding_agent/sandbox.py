"""
文件作用：
在 Linux Bubblewrap 隔离环境中执行受控命令，限制写入范围、时间和输出。

整体结构：
1）parse_command：把允许的命令解析成 argv；
2）sandbox_argv：组装挂载、环境清理和命名空间参数；
3）_limits / run_command：设置资源限制，收集执行结果并清理子进程。

职责边界：
隔离不可用就报错，不退回宿主直接执行；本模块不判断开发任务是否完成。
"""
from __future__ import annotations

import os
from pathlib import Path
import resource
import selectors
import shlex
import shutil
import signal
import subprocess
import time

from .workspace import Workspace


# 解析受控 Python 命令，拒绝不支持的程序、参数和 shell 语法。
def parse_command(command: str) -> list[str]:
    argv = shlex.split(command)
    if not argv or argv[0] != "python3" or len(argv) < 2:
        raise ValueError("allowed: python3 <relative-script.py> [args] or python3 -m unittest ...")
    if argv[1] == "-m":
        if len(argv) < 3 or argv[2] != "unittest":
            raise ValueError("only the unittest module is allowed")
    elif argv[1].startswith("-") or not argv[1].endswith(".py"):
        raise ValueError("only Python scripts and unittest are allowed; no -c or shell syntax")
    for arg in argv[1:]:
        if any(c in arg for c in (";", "|", "&", "`", "$", "\n", "<", ">")):
            raise ValueError("shell operators and expansion are not supported")
        if arg.startswith("/") or ".." in Path(arg).parts:
            raise ValueError("command arguments must use workspace-relative paths")
    return argv


# 构造隔离挂载与干净环境，可为 MCP 使用只读 workspace。
def sandbox_argv(ws: Workspace, argv: list[str], *, readonly=False, server: Path | None = None) -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("Bubblewrap is required (Linux/WSL2); no unsandboxed fallback")
    args = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL"]
    for directory in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(directory).exists():
            args += ["--ro-bind", directory, directory]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
             "--ro-bind" if readonly else "--bind", str(ws.root), "/workspace"]
    if server:
        args += ["--ro-bind", str(server), "/mcp_server.py"]
    for path in ws.protected_paths():
        destination = "/workspace/" + str(path.relative_to(ws.root))
        # 用空的只读挂载遮蔽 Git 元数据、凭据和运行证据。
        if path.is_dir():
            args += ["--tmpfs", destination, "--remount-ro", destination]
        else:
            args += ["--ro-bind", "/dev/null", destination]
    args += ["--chdir", "/workspace", "--clearenv", "--setenv", "PATH", "/usr/bin:/bin",
             "--setenv", "HOME", "/tmp", "--setenv", "LANG", "C.UTF-8",
             "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--", *argv]
    return args


# 在子进程执行前设置 CPU、内存、文件和句柄上限。
def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


# 运行隔离命令，收集有界输出，并在超时或中断时终止进程。
def run_command(ws: Workspace, command: str, timeout: float = 20) -> dict:
    argv = parse_command(command)
    if argv[1] != "-m":
        ws.path(argv[1])
    args = sandbox_argv(ws, argv)
    started = time.monotonic()
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env={"PATH": "/usr/bin:/bin"},
                               start_new_session=True, preexec_fn=_limits)
    output = bytearray()
    total = 0
    reason = None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map():
            if time.monotonic() - started >= timeout:
                reason = "timeout"
                break
            for key, _ in selector.select(min(0.1, timeout)):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    break
                total += len(chunk)
                output.extend(chunk)
                if len(output) > 16000:
                    del output[:-16000]
                if total > 1024 * 1024:
                    reason = "output_limit"
                    break
            if reason:
                break
    except BaseException:
        reason = "interrupted"
        raise
    finally:
        selector.close()
        # 主命令退出后，仍持有输出管道的后代进程也需要限时清理。
        if process.poll() is None:
            if not reason:
                try:
                    process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
                except subprocess.TimeoutExpired:
                    reason = "timeout"
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        process.stdout.close()
    text = output.decode("utf-8", errors="replace")
    return {"command": command, "exit_code": process.returncode, "output": text,
            "termination": reason, "truncated": total > 16000,
            "duration_seconds": round(time.monotonic() - started, 3),
            "sandbox_error": text.startswith("bwrap:")}
