"""
文件作用：
把一次运行的真实 API 用量换算为人民币参考费用，供运行报告展示估算依据。

整体结构：
1）SOURCE / SNAPSHOT_DATE / PRICES：记录价格来源、快照日期及三类高峰单价；
2）estimate_cost：按 step 对齐请求时间和响应用量，逐调用选择北京时间高峰或空闲档；
3）结果：返回合计金额、档位和价格依据，数据不齐时返回 amount=None 及原因。

计费口径：
仅计缓存命中、未命中和输出三类用量；历史记录也按本价格快照补算，
不查询实时价格，不使用预算预留，也不代替实际账单。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
SNAPSHOT_DATE = "2026-09-10"
# 每百万 tokens 的人民币单价，顺序为缓存命中、未命中、输出；此处存高峰价。
PRICES = {
    "deepseek-flash": (0.04, 2.0, 8.0),
    "deepseek-v4-flash": (0.04, 2.0, 8.0),
    "deepseek-v4-flash-vision-exp": (0.04, 2.0, 8.0),
    "deepseek-v4-pro": (0.30, 9.0, 27.0),
}


# 逐调用估算并记录参考价；缺少模型价格或计费用量时不造金额。
def estimate_cost(summary, events):
    from .reporting import usage_summary
    result = {"currency": "CNY", "amount": None, "pricing_date": SNAPSHOT_DATE, "source": SOURCE}
    rates = PRICES.get(summary.get("model"))
    if rates is None:
        return {**result, "reason": "该模型尚无参考单价"}
    requests = {e["step"]: e["time"] for e in events if e["event"] == "model_request"}
    responses = [e for e in events if e["event"] == "model_response"]
    if len(responses) != summary["model_calls"] or len(requests) != summary["model_calls"]:
        return {**result, "reason": "存在未返回用量的调用"}
    total = 0.0
    tiers = set()
    for event in responses:
        usage = usage_summary([event])
        counts = [usage[k] for k in ("cache_hit_tokens", "cache_miss_tokens", "completion_tokens")]
        if any(value is None for value in counts):
            return {**result, "reason": "缺少缓存命中、未命中或输出用量"}
        try:
            moment = datetime.fromisoformat(requests[event["step"]].replace("Z", "+00:00"))
            if moment.tzinfo is None:
                raise ValueError("missing timezone")
            local = moment.astimezone(ZoneInfo("Asia/Shanghai"))
        except (ValueError, KeyError):
            return {**result, "reason": "缺少有效的请求时间"}
        # 逐请求选档，跨高峰边界的一次 Run 不能整体套用同一个折扣。
        peak = local.weekday() < 5 and (9 <= local.hour < 12 or 14 <= local.hour < 18)
        tiers.add("高峰" if peak else "空闲")
        total += sum(count * rate for count, rate in zip(counts, rates)) / 1_000_000 * (1 if peak else 0.5)
    return {**result, "amount": round(total, 8), "peak_cny_per_million": list(rates),
            "tiers": sorted(tiers), "basis": "官方参考价；按请求发起时段估算，历史运行也按本价格快照补算，非实际账单"}
