"""
文件作用：
默认从空目录创建程序；也可复制带缺陷的样例，体验真实模型修复过程。

整体结构：
1）CREATE_TASK / TASK：分别定义空目录创建与已有样例修复任务；
2）main：加载配置、创建独立 workspace，按开关准备 MCP 说明并启动 Agent。

已存在的目标目录不会被覆盖，运行会产生真实 API 用量。
"""
import argparse
from pathlib import Path
import re
import shutil
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from mini_coding_agent.agent import Agent
from mini_coding_agent.provider import ChatProvider, load_config
from mini_coding_agent.workspace import Workspace

TASK = """修复 README.md 中描述的 slugify 行为，并补充边界回归测试。
请先查看仓库、保存开发计划，然后运行现有测试，观察真实失败再修改代码。
不要删除或弱化已有测试。修改后运行完整测试，成功后交付简洁报告。
如启用了 test-repair Skill，请先加载它；如启用了 MCP，请读取项目说明并满足其中的验收要求。"""


CREATE_TASK = """从当前空 workspace 开始，创建一个纯标准库 Python 项目：
实现 slugify.py 中的 slugify(text: str) -> str：先转小写，将连续的非 ASCII a-z/0-9
字符替换为一个短横线，去掉首尾短横线；空文本或纯标点得到空字符串。
实现 cli.py，用 argparse 接收一个标题参数并打印结果。写中文 README、文件作用注释。
先 list_files 确认空目录，再 save_plan。采用测试先行：先创建 unittest 测试并执行，
观察源码尚未实现时的真实失败，再创建实现，按实际反馈修正；不要故意写坏实现来制造失败。
测试至少覆盖空输入、大小写、连续分隔符、首尾分隔符、数字、非 ASCII 字符以及 subprocess CLI。
例子：'  Hello, WORLD!!  ' -> 'hello-world'；'中文' -> ''；'A___B' -> 'a-b'。
保留符合约定的断言，最后运行 python3 -m unittest discover -s . -v，成功后 finish 交付。
默认无需 Skill 或 MCP；如启用它们，请按需加载并满足补充说明。"""


# 创建新的演示 workspace，按扩展开关运行真实模型任务。
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thinking", choices=("enabled", "disabled"), default="disabled",
                        help="思考模式：默认 disabled（非思考）；显式 enabled 开启思考")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--dest", type=Path, help="显式指定新的 workspace，已有目录拒绝覆盖")
    parser.add_argument("--task-name", help="自动目录名的任务短名，默认 slugify-create 或 slugify-repair")
    parser.add_argument("--mode", choices=("create", "repair"), default="create", help="create 从空目录开发（默认）；repair 修复旧样例")
    parser.add_argument("--skill", action="store_true")
    parser.add_argument("--mcp", action="store_true")
    parser.add_argument("--token-budget", type=int, help="兼容旧总预算：可选附加上限")
    parser.add_argument("--max-input-tokens", type=int, default=250000)
    parser.add_argument("--max-output-tokens", type=int, default=50000)
    parser.add_argument("--max-output-per-call", type=int, default=8192)
    args = parser.parse_args()
    if args.dest is None:
        task_name = args.task_name or f"slugify-{args.mode}"
        if not re.fullmatch(r"[\w-]+", task_name):
            parser.error("任务短名只允许文字、数字、下划线和短横线")
        args.dest = PROJECT / "runs" / f"{task_name}-{time.strftime('%Y%m%d-%H%M%S')}"
    provider = ChatProvider(load_config(args.env_file), thinking=args.thinking)
    if args.mode == "create":
        args.dest.mkdir(parents=True, exist_ok=False)
    else:
        shutil.copytree(PROJECT / "examples/slugify", args.dest, ignore=shutil.ignore_patterns("__pycache__"))
    if args.mcp:
        (args.dest / "PROJECT_NOTES.md").write_text(
            "# Project notes\n\n验收补充：添加 cli.py，使用 argparse 接收一个标题参数，"
            "打印 slugify 的结果。至少添加一个 subprocess CLI 回归测试。"
            "例如 python3 cli.py 'Hello, WORLD!' 应输出 hello-world。\n", encoding="utf-8")
    print(f"Workspace: {args.dest.resolve()}", flush=True)
    summary = Agent(Workspace(args.dest), provider, skill=args.skill, mcp=args.mcp,
                    token_budget=args.token_budget, max_input_tokens=args.max_input_tokens,
                    max_output_tokens=args.max_output_tokens, max_output_per_call=args.max_output_per_call,
                    task_title="创建 slugify CLI" if args.mode == "create" else "修复 slugify").run(CREATE_TASK if args.mode == "create" else TASK)
    print(f"{summary['status']}: {args.dest.resolve()}/RUN_REPORT.md")
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
