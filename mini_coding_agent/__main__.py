"""
文件作用：
提供命令行入口，将 workspace、开发任务和运行预算交给 Agent。

整体结构：
1）main：解析参数、加载配置并启动一次任务；
2）退出码：区分成功交付、未完成和启动配置错误。
"""
import argparse
from pathlib import Path
import sys

from .agent import Agent, DEFAULT_VERIFY
from .provider import ChatProvider, load_config
from .workspace import Workspace


def main():
    """解析命令行并启动一次任务，将交付状态转换为退出码。"""
    parser = argparse.ArgumentParser(description="A one-day Mini Coding Agent (Python + Bubblewrap)")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("task", help="natural language development task")
    parser.add_argument("--task-title", help="报告摘要中的简短任务标题")
    parser.add_argument("--thinking", choices=("enabled", "disabled"), default="disabled",
                        help="思考模式：默认 disabled（非思考）；显式 enabled 开启思考")
    parser.add_argument("--env-file", type=Path, help="explicit LLM_* config file; never passed to tools")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--token-budget", type=int, help="兼容旧总预算：可选附加上限")
    parser.add_argument("--verify-command", default=DEFAULT_VERIFY)
    parser.add_argument("--command-timeout", type=float, default=20)
    parser.add_argument("--skill", action="store_true", help="enable the optional test-repair skill")
    parser.add_argument("--mcp", action="store_true", help="enable the bundled stdio project-notes MCP tool")
    parser.add_argument("--max-input-tokens", type=int, default=250000)
    parser.add_argument("--max-output-tokens", type=int, default=50000)
    parser.add_argument("--max-output-per-call", type=int, default=8192)
    args = parser.parse_args()
    try:
        provider = ChatProvider(load_config(args.env_file), thinking=args.thinking)
        agent = Agent(Workspace(args.workspace), provider, max_steps=args.max_steps,
                      token_budget=args.token_budget, max_input_tokens=args.max_input_tokens,
                      max_output_tokens=args.max_output_tokens, max_output_per_call=args.max_output_per_call, verify_command=args.verify_command,
                      command_timeout=args.command_timeout, skill=args.skill, mcp=args.mcp, task_title=args.task_title)
        result = agent.run(args.task)
    except (ValueError, OSError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    print(f"\n{result['status']} — {args.workspace.resolve()}/RUN_REPORT.md")
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
