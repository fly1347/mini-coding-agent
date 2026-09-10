"""
文件作用：
为运行器测试构造确定性的模型回复，不替代真实工具执行。

整体结构：
1）call / PLAN / FIX：准备工具调用和小型修复样例；
2）SequenceProvider：依次返回预设回复并保存请求；
3）finish_last：引用上一次工具结果尝试交付。
"""
import json


def call(tool_name, **arguments):
    """构造一条指定工具调用的模型回复。"""
    return {"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call-test", "type": "function", "function": {
            "name": tool_name, "arguments": json.dumps(arguments)}}]}, "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}}


PLAN = dict(goal="Fix slugify to satisfy the documented ASCII slug contract.",
            steps="Run baseline tests; inspect failures; fix normalization; add regression tests; rerun all tests.",
            validation="python3 -m unittest discover -s . -v; require all existing and new tests to pass.")
FIX = 'import re\n\ndef slugify(text: str) -> str:\n    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")\n'


class SequenceProvider:
    """仅控制测试中的模型回复，文件和命令工具仍真实执行。"""
    model = "scripted-test-double"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.seen = []

    def complete(self, messages, tools, max_tokens):
        """记录本次请求，并返回下一条预设回复或异常。"""
        self.seen.append(json.loads(json.dumps(messages)))
        item = next(self.responses)
        if isinstance(item, BaseException):
            raise item
        return item(messages) if callable(item) else item


def finish_last(messages):
    """从上次工具结果中取得证据 ID，构造交付请求。"""
    result = json.loads(messages[-1]["content"])
    return call("finish", summary="Implemented normalization; real regression command passed.",
                verification_id=result["tool_id"])
