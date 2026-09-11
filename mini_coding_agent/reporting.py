"""
文件作用：
从一次运行的 summary 和公开 trace 生成中文 RUN_REPORT.md，
让读者先看交付状态与用量，再按工具证据复盘修改、失败和最终验证。

整体结构：
1）FIELDS / usage_summary：统一 API 用量字段别名，累计有效值并记录各字段覆盖次数；
2）cell：把事件文本转为转义、限长的单行 Markdown 表格内容；
3）write_report：整理运行摘要、真实用量、费用、改动、工具时间线和验证链路，写入报告；
4）write_report.count：为用量数字区分未提供、部分返回和完整返回。

展示边界：
用量缺失不当零，预算扣账不当真实 usage；费用由 pricing.py 按日期快照估算。
报告摘录操作和执行证据，不复制源码或私有推理，也不把时间先后当成修复因果。
"""
from __future__ import annotations

from datetime import datetime
import html
from pathlib import Path
import json
import re

from .pricing import estimate_cost


FIELDS = {
    "prompt_tokens": ("prompt_tokens",),
    "cache_hit_tokens": ("prompt_cache_hit_tokens", "cache_hit_tokens", "prompt_tokens_details.cached_tokens"),
    "cache_miss_tokens": ("prompt_cache_miss_tokens", "cache_miss_tokens"),
    "completion_tokens": ("completion_tokens",),
    "reasoning_tokens": ("completion_tokens_details.reasoning_tokens", "reasoning_tokens"),
    "total_tokens": ("total_tokens",),
}


# 仅累计 provider 返回的非负整数，并标注每个字段覆盖的响应次数。
def usage_summary(events):
    responses = [e for e in events if e["event"] == "model_response"]
    totals = dict.fromkeys(FIELDS)
    coverage = dict.fromkeys(FIELDS, 0)
    for event in responses:
        usage = dict(event.get("usage") or {})
        if all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        for field, aliases in FIELDS.items():
            for alias in aliases:
                value = usage
                for part in alias.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if type(value) is int and value >= 0:
                    totals[field] = (totals[field] or 0) + value
                    coverage[field] += 1
                    break  # 同一响应的别名只认一个，避免缓存等字段重复累计。
    return {**totals, "reported_calls": coverage, "model_responses": len(responses)}


# 把任意文本变成有长度限制的单行 Markdown 表格内容。
def cell(value, limit=240):
    text = " ".join(str(value).split())
    if len(text) > limit:
        text = text[:limit] + "…"
    return html.escape(text).replace("|", "&#124;").replace("`", "&#96;")


# 将汇总与事件组织为 run_dir/RUN_REPORT.md，按结论、用量和验证证据引导阅读。
def write_report(run_dir, summary, events, delivery):
    usage = summary["usage"]
    cost = summary.get("cost_estimate") or estimate_cost(summary, events)
    cost_text = f"**¥{cost['amount']:.6f}**" if cost["amount"] is not None else "暂无法估算（" + cost["reason"] + "）"
    start = next((e for e in events if e["event"] == "start"), {})
    began = summary.get("started_at") or start.get("started_at") or start.get("time")
    duration = summary.get("duration_seconds")
    estimated = False
    if duration is None:
        # 旧记录没有单调时钟耗时，只能用事件时间戳补算，并在报告中标出精度差异。
        ended = next((e.get("time") for e in reversed(events) if e["event"] == "end"), None)
        if began and ended:
            duration = (datetime.fromisoformat(ended.replace("Z", "+00:00")) -
                        datetime.fromisoformat(began.replace("Z", "+00:00"))).total_seconds()
            estimated = True
    original_run = Path(summary["run_dir"])
    run_name = summary.get("run_name") or original_run.parents[2].name
    thinking = summary.get("thinking", start.get("thinking"))
    thinking_text = str(thinking) if thinking is not None else "请求档位未记录"
    reasoning = usage.get("reasoning_tokens")
    if reasoning is not None and reasoning > 0:
        thinking_text += f"（实际返回 reasoning tokens：{reasoning:,}）"
    elif reasoning == 0:
        thinking_text += "（已返回的 reasoning tokens 为 0）"

    # 展示累计数字，同时保留缺失与部分返回的含义。
    def count(field):
        value = usage[field]
        if value is None:
            return "未提供"
        suffix = "（部分返回）" if usage["reported_calls"][field] < summary["model_calls"] else ""
        return f"{value:,}{suffix}"

    input_limit = f" / {summary['max_input_tokens']:,}" if "max_input_tokens" in summary else ""
    output_limit = f" / {summary['max_output_tokens']:,}" if "max_output_tokens" in summary else ""
    task_title = summary.get("task_title") or re.split(r"[。；;\n]", summary["task"])[0]
    state = "SUCCESS" if summary["status"] == "completed" else summary["status"].upper()
    elapsed = "未记录" if duration is None else f"{duration:.1f} s" + ("（历史时间戳估算，秒级精度）" if estimated else "")
    lines = ["# Mini Coding Agent 运行报告", "", "## 运行摘要", "",
             f"- 日期：{cell(began[:10] if began else '未记录')}（{cell(began or '时区未记录')}）",
             f"- Run：{cell(run_name)}", f"- Run ID：{cell(summary.get('run_id', original_run.name))}",
             f"- 任务：{cell(task_title, 24)}", f"- 模型：{cell(summary['model'] or '未提供')}",
             f"- Thinking：{cell(thinking_text)}",
             f"- 最终状态：{state}（原始状态：**{summary['status']}**）",
             f"- 模型调用：{summary['model_calls']}", f"- Tool 调用：{summary['tool_calls']}",
             f"- Input Tokens：{count('prompt_tokens')}{input_limit}",
             f"- Cache Hit / Miss：{count('cache_hit_tokens')} / {count('cache_miss_tokens')}",
             f"- Output Tokens：{count('completion_tokens')}{output_limit}", f"- Total Tokens：{count('total_tokens')}",
             f"- 预估费用（人民币）：{cost_text}",
             f"- 总耗时：{elapsed}", "",
             "总耗时覆盖运行初始化后的模型、工具执行与最终文件盘点，不含随后报告落盘；新运行使用单调时钟计时。", "",
             "## 任务与结果", "", summary["task"], "",
             "模型交付说明或运行器退出原因（模型陈述需结合下方证据复核）：", "", delivery,
             "", "## Token 用量", "", "| 指标 | 已报告累计值 | 覆盖响应 / 调用 |", "|---|---:|---:|"]
    labels = ["输入 prompt", "缓存命中 cache hit", "缓存未命中 cache miss", "输出 completion", "推理 reasoning", "总量 total"]
    for field, label in zip(FIELDS, labels):
        value = usage[field]
        lines.append(f"| {label} | {value if value is not None else '未提供'} | {usage['reported_calls'][field]} / {summary['model_calls']} |")
    if summary.get("stop_reason"):
        lines += ["", "## 停止原因", "", summary["stop_reason"]]
    if "budget_usage" in summary:
        charged = summary["budget_usage"]
        lines += ["", "## 预算扣账", "",
                  f"Input：{charged['input_tokens']:,} / {summary['max_input_tokens']:,}；"
                  f"Output：{charged['output_tokens']:,} / {summary['max_output_tokens']:,}；"
                  f"单次 Output 上限：{summary['max_output_per_call']:,}。",
                  "真实用量见上表；仅在 API 缺少某类 usage 时，该类预算扣账使用本轮预留额。"]
    lines += ["", f"预算扣账 tokens：{summary['tokens']}（包含缺失 usage 时的保守预留，不等于真实用量）。",
              "覆盖不足时累计值只是已返回部分；缺失不记作 0。cache 是输入的细分，reasoning 是输出的细分，不重复相加。",
              f"费用依据：[{cost['pricing_date']} 官方人民币参考价]({cost['source']})。"
              "按每次请求的北京时间工作日高峰（9–12、14–18）或空闲档，分别计算缓存命中、未命中和输出费用；reasoning 不重复计费。",
              "历史运行也按这份参考价补算，不代表当时实际扣款；不保存私有推理正文。", "", "## 修改文件", ""]
    lines += [f"- {cell(p)}" for p in summary["changed_files"]] or ["- 无修改。"]
    lines += ["", "## 关键 Tool 时间线", "", "| 时间（UTC） | Tool ID | 操作 / 对象 | 结果 | 耗时（秒） |",
              "|---|---|---|---|---:|"]
    starts, chain, failures = {}, [], []
    for event in events:
        if event["event"] == "tool_start":
            starts[event["tool_id"]] = event
        if event["event"] != "tool_result":
            continue
        tool_id, name, result = event["tool_id"], event["name"], event["result"]
        try:
            args = json.loads(starts.get(tool_id, {}).get("arguments", "{}"))
        except (ValueError, TypeError):
            args = {}
        if not isinstance(args, dict):
            args = {}
        target = args.get("path", args.get("command", args.get("name", "")))
        failed = not result.get("ok", False) or result.get("exit_code", 0) != 0 or bool(result.get("termination"))
        outcome = ("失败：" + str(result.get("error", result.get("termination") or "执行未通过"))) if failed else "成功"
        rejected = (name == "run_shell" and args.get("command") == summary["verify_command"]
                    and result.get("verification_accepted") is False and not failed)
        if rejected:
            outcome = "命令成功但验收未接受（空测试或执行期间源码变化等）"
        if "exit_code" in result:
            outcome += f"；exit={result['exit_code']}；verification={result.get('verification_accepted', False)}"
        lines.append(f"| {cell(event['time'])} | {tool_id} | {cell(name + ' ' + str(target))} | {cell(outcome)} | {event.get('duration_seconds', '未记录')} |")
        if failed or rejected:
            chain.append(f"- {tool_id}：失败（{cell(name)}）；{cell(outcome)}。")
            excerpt = result.get("output") or result.get("error") or "无输出"
            failures.append(f"- {tool_id} 输出末尾：{cell(str(excerpt)[-1200:], 1200)}")
        elif name in {"write_file", "replace_text"}:
            chain.append(f"- {tool_id}：修改 {cell(target)}。")
        elif name == "run_shell":
            chain.append(f"- {tool_id}：执行 {cell(target)}；{cell(outcome)}。")
    if not starts:
        lines.append("| — | — | 没有工具调用 | — | — |")
    lines += ["", "## 失败 → 修改 → 再验证", "", "以下按实际发生顺序列出，不据此推断修改一定解决了某个失败。", ""]
    lines += chain or ["- 未发生修改或执行；没有可展示的修复链。"]
    if failures:
        lines += ["", "### 失败输出摘录", "", *failures]
    else:
        lines += ["", "未观察到失败，不构造虚假的失败修复过程。"]
    verification = summary["verification"]
    lines += ["", "## 最终 Verification", "", f"要求的完整验收命令：{cell(summary['verify_command'])}", ""]
    if verification:
        verified_result = next((e["result"] for e in reversed(events)
                                if e["event"] == "tool_result" and e["tool_id"] == verification["tool_id"]), {})
        lines += [f"- 有效证据：{verification['tool_id']}；{cell(verification['command'])}。",
                  f"- 输出末尾：{cell(str(verified_result.get('output', '未记录'))[-600:], 600)}",
                  "- 运行器已接受：exit 0、未终止、unittest 非空、执行期间源码未变化。",
                  f"- 完成交付门禁：{'通过' if summary['status'] == 'completed' else '未完成交付，不能仅凭一次验证宣称完成'}。"]
    else:
        lines += ["- 没有当前有效的完整验收证据，不能宣称任务完成。"]
    lines += ["", "测试通过不等于需求语义已被完全证明，仍应复核改动和测试质量。",
              "", "进一步复盘：[计划](PLAN.md) · [交付](FINAL.md) · [结构化汇总](summary.json) · [原始轨迹](trace.jsonl)", ""]
    (run_dir / "RUN_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
