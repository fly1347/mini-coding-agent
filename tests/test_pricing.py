"""
文件作用：
验证费用估算使用真实字段与请求发起时段，区分确定的零费用和数据不足时无法估算。

整体结构：
1）events_at：构造按 step 配对的请求时间与三类计费用量；
2）时段用例：覆盖工作日高峰、午间空闲、周末及同一 Run 跨档位的逐调用计费；
3）缺失用例：区分零调用、无响应、计费用量缺项和未知模型；
4）历史数值用例：用固定的创建任务用量核对金额计算。

验证边界：
时间与用量都是固定夹具，不访问模型或价格服务；仅验证代码内价格快照的计算，
不验证该快照是否仍是当前价格，也不复现一次真实模型运行。
"""
import unittest
from mini_coding_agent.pricing import estimate_cost


# 生成带真实字段形状的请求与用量记录。
def events_at(*times):
    events = []
    for step, time in enumerate(times, 1):
        events += [{"event": "model_request", "step": step, "time": time},
                   {"event": "model_response", "step": step, "usage": {
                       "prompt_cache_hit_tokens": 1000000, "prompt_cache_miss_tokens": 1000000,
                       "completion_tokens": 1000000, "completion_tokens_details": {"reasoning_tokens": 100000}}}]
    return events


class PricingTests(unittest.TestCase):
    # 用边界前后和周末的请求时间验证单次选档，再检查跨档位运行按调用分别相加。
    def test_peak_off_peak_weekend_and_cross_boundary(self):
        summary = {"model": "deepseek-v4-flash", "model_calls": 1}
        for time, expected in [("2026-09-10T03:59:59Z", 10.04),
                               ("2026-09-10T04:00:00Z", 5.02),
                               ("2026-09-12T06:00:00Z", 5.02)]:
            self.assertAlmostEqual(estimate_cost(summary, events_at(time))["amount"], expected)
        summary["model_calls"] = 2
        result = estimate_cost(summary, events_at("2026-09-10T03:59:59Z", "2026-09-10T04:00:00Z"))
        self.assertAlmostEqual(result["amount"], 15.06)

    # 零调用可以报零费用，有调用却缺数据或模型价格时必须返回未知金额。
    def test_unknown_missing_and_no_calls(self):
        summary = {"model": "deepseek-v4-flash", "model_calls": 0}
        self.assertEqual(estimate_cost(summary, [])["amount"], 0)
        summary["model_calls"] = 1
        self.assertIsNone(estimate_cost(summary, [])["amount"])
        events = events_at("2026-09-10T06:00:00Z")
        events[1]["usage"].pop("prompt_cache_hit_tokens")
        self.assertIsNone(estimate_cost(summary, events)["amount"])
        summary["model"] = "unknown"
        self.assertIsNone(estimate_cost(summary, events)["amount"])

    # 用创建任务的固定用量记录核对参考费用计算。
    def test_actual_my_create_usage(self):
        events = events_at("2026-09-10T06:10:23Z")
        events[1]["usage"].update(prompt_cache_hit_tokens=43776, prompt_cache_miss_tokens=4359, completion_tokens=5371)
        self.assertAlmostEqual(estimate_cost({"model": "deepseek-v4-flash", "model_calls": 1}, events)["amount"], 0.05343704)
