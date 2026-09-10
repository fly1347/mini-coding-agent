"""覆盖分账预算、实测比例校准与截断后的多工具恢复，不依赖模型 API。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mini_coding_agent.agent import Agent
from mini_coding_agent.budget import InputEstimator, serialized_bytes
from mini_coding_agent.workspace import Workspace
from tests.helpers import SequenceProvider, call, PLAN


def response(prompt=80, completion=20, **extra):
    """生成有完整分账用量的无工具响应。"""
    return {"message": {"role": "assistant", "content": "继续"}, "usage": {
        "prompt_tokens": prompt, "completion_tokens": completion,
        "prompt_cache_hit_tokens": prompt // 2, "prompt_cache_miss_tokens": prompt - prompt // 2,
        "total_tokens": prompt + completion}, **extra}


class BudgetTests(unittest.TestCase):
    def run_agent(self, responses, **options):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        provider = SequenceProvider(responses)
        agent = Agent(Workspace(Path(tmp.name)), provider, max_steps=len(responses), **options)
        result = agent.run("创建并验证小程序")
        events = [json.loads(line) for line in (Path(result['run_dir']) / 'trace.jsonl').read_text().splitlines()]
        return result, events, provider

    def test_separate_usage_and_cache_not_double_counted(self):
        result, _, _ = self.run_agent([response(100, 10), response(200, 20)])
        self.assertEqual(result['usage']['prompt_tokens'], 300)
        self.assertEqual(result['usage']['completion_tokens'], 30)
        self.assertEqual(result['usage']['total_tokens'], 330)
        self.assertEqual(result['usage']['cache_hit_tokens'], 150)
        self.assertEqual(result['budget_usage'], {'input_tokens': 300, 'output_tokens': 30})
        report = (Path(result['run_dir']) / 'RUN_REPORT.md').read_text()
        self.assertIn('Input Tokens：300 / 250,000', report)
        self.assertIn('Output Tokens：30 / 50,000', report)

    def test_output_clamp_and_reaching_budget_stops_tools(self):
        last = call('write_file', path='should_not_exist.py', content='bad')
        last['usage'] = {'prompt_tokens': 80, 'completion_tokens': 4}
        result, events, _ = self.run_agent([response(80, 6), last], max_output_tokens=10, max_output_per_call=8)
        self.assertEqual([e['output_limit'] for e in events if e['event'] == 'model_request'], [8, 4])
        self.assertEqual(result['status'], 'token_budget')
        self.assertEqual(result['tool_calls'], 0)
        self.assertIn('Output 已达预算', result['stop_reason'])

    def test_input_actual_overrun_recorded_without_tools(self):
        item = call('list_files')
        item['usage'] = {'prompt_tokens': 101, 'completion_tokens': 1}
        with patch.object(InputEstimator, 'estimate', return_value=(10, 0.1)):
            result, _, provider = self.run_agent([item, response()], max_input_tokens=100)
        self.assertEqual(result['status'], 'token_budget')
        self.assertEqual(result['usage']['prompt_tokens'], 101)
        self.assertEqual(result['tool_calls'], 0)
        self.assertEqual(len(provider.seen), 1)
        self.assertIn('不执行本轮工具', result['stop_reason'])

    def test_input_gate_explains_estimate_and_remaining(self):
        with patch.object(InputEstimator, 'estimate', return_value=(24300, 0.3)):
            result, events, provider = self.run_agent([response()], max_input_tokens=18100)
        self.assertEqual(len(provider.seen), 0)
        self.assertIn('24,300', result['stop_reason'])
        self.assertIn('18,100', result['stop_reason'])
        self.assertEqual(next(e for e in events if e['event'] == 'budget_stop')['phase'], 'before_call')

    def test_calibration_recent_window_and_abnormal_ratios(self):
        estimator = InputEstimator()
        self.assertEqual(estimator.estimate(56000)[0], 19179)
        estimator.observe(13000, 56000)
        self.assertEqual(estimator.estimate(56000)[0], 16112)
        estimator.observe(100000000, 100)
        self.assertEqual(len(estimator.ratios), 1)
        for _ in range(5):
            estimator.observe(10000, 56000)
        self.assertEqual(estimator.estimate(56000)[0], 12512)

    def test_growing_history_about_100k_does_not_false_stop(self):
        def growing(messages):
            # 模拟大量读文件结果进入完整历史：实际 prompt 约为序列化字节数四分之一。
            prompt = serialized_bytes({'messages': messages}) // 4
            item = response(prompt, 100)
            item['message']['content'] = 'x' * 3500
            return item
        result, events, _ = self.run_agent([growing] * 15)
        self.assertEqual(result['model_calls'], 15)
        self.assertEqual(result['status'], 'step_budget')
        self.assertGreater(result['usage']['prompt_tokens'], 80000)
        self.assertLess(result['usage']['prompt_tokens'], 120000)
        request = [e for e in events if e['event'] == 'model_request'][-1]
        self.assertGreater(request['serialized_request_bytes'], 50000)
        self.assertLess(request['input_reservation'], request['serialized_request_bytes'] / 2)

    def test_length_skips_truncated_calls_then_allows_multiple(self):
        bad = call('write_file', path='truncated.py', content='do not execute')
        bad['finish_reason'] = 'length'
        multiple = call('write_file', path='a.py', content='a=1\n')
        second = call('write_file', path='b.py', content='b=2\n')['message']['tool_calls'][0]
        second['id'] = 'second'
        multiple['message']['tool_calls'].append(second)
        result, _, provider = self.run_agent([call('list_files'), call('save_plan', **PLAN), bad, multiple])
        self.assertEqual(result['changed_files'], ['a.py', 'b.py'])
        self.assertEqual(result['tool_calls'], 4)
        recovery = provider.seen[-1][-1]['content']
        self.assertNotIn('one tool call at a time', recovery)
        self.assertIn('Multiple complete tool calls are allowed', recovery)
        self.assertIn('replace_text', recovery)

    def test_missing_usage_reserves_only_missing_side(self):
        item = response()
        del item['usage']['completion_tokens']
        result, _, _ = self.run_agent([item], max_output_per_call=100)
        self.assertEqual(result['budget_usage'], {'input_tokens': 80, 'output_tokens': 100})
        self.assertIsNone(result['usage']['completion_tokens'])
