"""验证费用按真实用量及请求时段计价，缺失数据不误报为零费用。"""
import unittest
from mini_coding_agent.pricing import estimate_cost


def events_at(*times):
    """生成带真实字段形状的请求与用量记录。"""
    events = []
    for step, time in enumerate(times, 1):
        events += [{"event": "model_request", "step": step, "time": time},
                   {"event": "model_response", "step": step, "usage": {
                       "prompt_cache_hit_tokens": 1000000, "prompt_cache_miss_tokens": 1000000,
                       "completion_tokens": 1000000, "completion_tokens_details": {"reasoning_tokens": 100000}}}]
    return events


class PricingTests(unittest.TestCase):
    def test_peak_off_peak_weekend_and_cross_boundary(self):
        summary = {"model": "deepseek-v4-flash", "model_calls": 1}
        for time, expected in [("2026-09-10T03:59:59Z", 10.04),
                               ("2026-09-10T04:00:00Z", 5.02),
                               ("2026-09-12T06:00:00Z", 5.02)]:
            self.assertAlmostEqual(estimate_cost(summary, events_at(time))["amount"], expected)
        summary["model_calls"] = 2
        result = estimate_cost(summary, events_at("2026-09-10T03:59:59Z", "2026-09-10T04:00:00Z"))
        self.assertAlmostEqual(result["amount"], 15.06)

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

    def test_actual_my_create_usage(self):
        events = events_at("2026-09-10T06:10:23Z")
        events[1]["usage"].update(prompt_cache_hit_tokens=43776, prompt_cache_miss_tokens=4359, completion_tokens=5371)
        self.assertAlmostEqual(estimate_cost({"model": "deepseek-v4-flash", "model_calls": 1}, events)["amount"], 0.05343704)
