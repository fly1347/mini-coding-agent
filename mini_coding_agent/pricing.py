"""按有日期的 DeepSeek 官方人民币参考价估算费用，不代替实际账单。

逐模型请求按北京时间工作日高峰/空闲档计算；仅用真实返回的三类计费用量。
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


def estimate_cost(summary, events):
    """逐调用估算并记录参考价；缺少模型价格或计费用量时不造金额。"""
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
        peak = local.weekday() < 5 and (9 <= local.hour < 12 or 14 <= local.hour < 18)
        tiers.add("高峰" if peak else "空闲")
        total += sum(count * rate for count, rate in zip(counts, rates)) / 1_000_000 * (1 if peak else 0.5)
    return {**result, "amount": round(total, 8), "peak_cny_per_million": list(rates),
            "tiers": sorted(tiers), "basis": "官方参考价；按请求发起时段估算，历史运行也按本价格快照补算，非实际账单"}
