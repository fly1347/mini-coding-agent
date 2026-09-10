"""输入预留估算：记录最近五次 API prompt/请求字节比例，加余量预测下一轮。

估计只用于预算门禁与缺失 usage 的保守扣账，不充当真实用量或计费值。
"""
from collections import deque
import json
import math


def serialized_bytes(value):
    """按与 HTTP 请求相同的 UTF-8 JSON 编码计算字节数。"""
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


class InputEstimator:
    """单次 Run 内校准，避免混用其他模型或运行的观测值。"""
    def __init__(self):
        self.ratios = deque(maxlen=5)

    def estimate(self, size):
        """首轮按 bytes/3+512；随后用近期最大实测比例乘 1.2 加 512。"""
        ratio = max(self.ratios) * 1.2 if self.ratios else 1 / 3
        return math.ceil(size * ratio) + 512, ratio

    def observe(self, prompt_tokens, size):
        """只接受合理的正整数 prompt 观测；异常比例不污染近期窗口。"""
        if type(prompt_tokens) is int and prompt_tokens > 0 and size > 0:
            ratio = prompt_tokens / size
            if 0.02 <= ratio <= 2.0:
                self.ratios.append(ratio)
