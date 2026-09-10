"""从已有运行证据补生成人看报告，不调用模型、不修改原始证据。

读取 trace 和 summary，兼容旧统计字段；通过独占创建拒绝覆盖已有报告。
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from mini_coding_agent.reporting import usage_summary, write_report


def render(source: Path, task_title=None):
    """在原证据目录新增 RUN_REPORT.md，历史 summary 的缺失字段仅在内存补全。"""
    events = [json.loads(line) for line in (source / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    start = next(e for e in events if e["event"] == "start")
    if task_title:
        summary["task_title"] = task_title
    summary.update(task=start["task"], model=start.get("model"), verify_command=start["verify_command"],
                   model_calls=sum(e["event"] == "model_request" for e in events), usage=usage_summary(events))
    delivery = next((e["result"]["summary"] for e in reversed(events)
                     if e["event"] == "tool_result" and e["name"] == "finish" and e["result"].get("delivered")),
                    "本次未完成交付；退出详情见原始 FINAL.md 与 trace.jsonl。")
    with tempfile.TemporaryDirectory() as tmp:
        write_report(Path(tmp), summary, events, delivery)
        text = (Path(tmp) / "RUN_REPORT.md").read_text(encoding="utf-8")
    note = ("> 来源：使用 Mini Coding Agent 的 reporting.py，从本目录已有 trace.jsonl 和 summary.json "
            "离线补生成；未调用模型，未改写原始证据。模型交付说明引用原工具结果。\n\n")
    text = text.replace("# Mini Coding Agent 运行报告\n\n", "# Mini Coding Agent 运行报告\n\n" + note, 1)
    destination = source / "RUN_REPORT.md"
    with destination.open("x", encoding="utf-8") as output:
        output.write(text)
    return destination


def main():
    """接受一份原始 run 或 evidence 目录，补生成人看报告。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--task-title", help="摘要中的简短任务标题，完整任务保留在正文")
    args = parser.parse_args()
    try:
        print(render(args.source, args.task_title))
    except FileExistsError:
        parser.exit(1, "RUN_REPORT.md 已存在，拒绝覆盖。\n")


if __name__ == "__main__":
    main()
