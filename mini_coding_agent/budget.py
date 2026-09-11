"""
文件作用：
为 Agent 下一次模型请求估算输入预留，减少按请求字节数直接扣 Token 带来的提前停止。

整体结构：
1）serialized_bytes：按 HTTP 请求使用的 UTF-8 JSON 编码计算请求大小；
2）InputEstimator.observe：保存最近五次有效 prompt_tokens / 请求字节数比例；
3）InputEstimator.estimate：首次按 bytes/3 估算，之后取窗口最大比例并留余量。

使用边界：
估算器每次 Run 独立创建；预留值用于调用前门禁及缺失 usage 的扣账，
不作为 API 真实用量或计费值。累计预算和是否停止由 agent.py 决定。
"""
from collections import deque
import json
import math


# 按与 HTTP 请求相同的 UTF-8 JSON 编码计算字节数。
def serialized_bytes(value):
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


class InputEstimator:
    """单次 Run 内校准，避免混用其他模型或运行的观测值。"""
    def __init__(self):
        self.ratios = deque(maxlen=5)

    # 按请求字节数返回（预留 Token 数，采用比例），校准后留 20% 和 512 Token 余量。
    def estimate(self, size):
        ratio = max(self.ratios) * 1.2 if self.ratios else 1 / 3
        return math.ceil(size * ratio) + 512, ratio

    # 只接受合理的正整数 prompt 观测；异常比例不污染近期窗口。
    def observe(self, prompt_tokens, size):
        if type(prompt_tokens) is int and prompt_tokens > 0 and size > 0:
            ratio = prompt_tokens / size
            if 0.02 <= ratio <= 2.0:
                self.ratios.append(ratio)
