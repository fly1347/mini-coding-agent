# 架构

[English](en/architecture.md)

Mini Coding Agent 是一个同步、单 Agent 的本地开发循环。模型决定下一步动作，Harness 检查动作是否合法、执行工具、回填真实结果，并判断何时可以交付。

```text
CLI：任务、工作区、配置
          ↓
    Agent Loop ←───────────────┐
          ↓                    │
 Provider：模型请求            │
          ↓                    │
 Tool Calls                    │
          ↓                    │
 参数与运行阶段检查            │
          ↓                    │
 文件工具 / Bubblewrap / Skill / MCP
          ↓                    │
     Tool Results ─────────────┘
          ↓
   验证与停止 → Trace / Summary / Report
```

## 模块边界

| 文件 | 职责 |
|---|---|
| [__main__.py](../mini_coding_agent/__main__.py) | CLI 参数、模型配置、工作区与退出码 |
| [agent.py](../mini_coding_agent/agent.py) | 工具定义与分派、Agent Loop、状态门禁、退出与产物 |
| [provider.py](../mini_coding_agent/provider.py) | 标准库 HTTP 请求、工具调用响应与 Usage |
| [workspace.py](../mini_coding_agent/workspace.py) | 路径边界、文件操作、搜索和源码指纹 |
| [sandbox.py](../mini_coding_agent/sandbox.py) | 命令解析、Bubblewrap 挂载、超时和资源约束 |
| [budget.py](../mini_coding_agent/budget.py) | 根据近期实际 Usage 校准输入预留 |
| [reporting.py](../mini_coding_agent/reporting.py) / [pricing.py](../mini_coding_agent/pricing.py) | 用量归一化、报告与带日期的费用估算 |
| [mcp_notes.py](../mini_coding_agent/mcp_notes.py) / [mcp_server.py](../mini_coding_agent/mcp_server.py) | 固定项目说明工具的 stdio MCP 客户端与只读服务 |

## 一轮如何推进

1. 调用前检查剩余轮数和预算，为下一轮输入、输出预留额度。
2. Provider 发送完整 messages 和工具 schema，返回模型消息、Tool Calls、Usage 与结束原因。
3. 记录实际用量；若已达到预算则停止，不执行该响应中的工具。
4. 校验并执行 Tool Calls，将结果按调用 ID 加回 messages。工具错误也作为反馈返回模型。
5. 模型根据最新结果继续查看、修改或验证；只有合法 `finish` 才产生成功状态。

`finish_reason=length` 时整批工具调用被丢弃，避免执行截断参数。下一轮提示缩小 edit，仍允许多个完整、紧凑的工具调用。

## 工具与门禁

| 工具 | 动作与约束 |
|---|---|
| `list_files` / `read_file` / `search` | 列目录、分段读取、文本搜索 |
| `save_plan` | 保存目标、步骤、验证方案；空目录需先列目录，已有项目至少读取一个文件 |
| `write_file` / `replace_text` | 创建或精确替换文件；必须已有计划，修改使旧验证失效 |
| `run_shell` | 已有计划后运行受控 Python 命令，返回输出、退出码与终止原因 |
| `finish` | 引用当前有效的验证 Tool ID，且源码指纹仍与验证时一致 |
| `load_skill` | 启用后按需读取固定 test-repair Skill |
| `mcp_project_notes` | 启用后通过独立进程获取项目说明 |

最终验证要求命令与配置完全一致、正常退出且未超时，执行期间源码未变化；unittest 还必须实际发现测试。验证完成后再次改动源码，必须重新验证。

门禁验证的是执行事实和源码版本。测试断言是否完整表达需求，仍需要外部检查。

## 两层执行边界

**Workspace** 约束文件工具：拒绝越界路径、符号链接、硬链接和特殊文件，遮蔽配置与运行器保留文件；最多 1,000 个源文件、单文件 256 KiB。

**Bubblewrap** 约束运行后的程序：目标工作区可写，系统 Python 与运行库只读；隔离网络、清空环境，隐藏 `.git`、`.env*`、`.mini-agent` 等路径，API Key 不传入执行进程。

执行限制包含 CPU、地址空间、文件大小、超时和输出量。缺少 Bubblewrap 或 namespace 权限就失败，没有无隔离后备路径。完整适用边界见 [设计取舍](design-decisions.md)。

## 预算与上下文

当前使用 Full History：messages、Tool Calls 和 Tool Results 持续追加，没有摘要、截断或检索式上下文选择。

输入估算首次使用 `ceil(UTF-8 请求字节数 / 3) + 512`；之后用最近五次有效 `prompt_tokens / 请求字节数` 比例中的最大值，增加 20% 和 512 tokens 余量。输出请求取单次上限与剩余额度中的较小值。

API 返回的真实输入和输出分别累计，缓存属于输入、reasoning 属于输出。缺少 Usage 时仅对缺失侧使用预留额扣账，报告保留实际用量的缺失和覆盖范围。

## 扩展与运行产物

Skill 提供可复用工作方法，不增加工具权限。MCP 通过 `initialize → tools/list → tools/call` 接入外部信息，当前只实现固定 2025-06-18 协议版本中所需的 stdio 子集，服务读取工作区内 `PROJECT_NOTES.md`。

两项扩展默认关闭，不改变主循环。MCP 是最小协议体验，并非通用客户端或插件系统。

每次运行生成计划、trace、summary、交付说明与中文报告。成功、预算停止、异常和中断都留下结果；同一工作区的旧日志保留，源码不自动回滚或快照。路径与阅读顺序见 [使用指南](usage.md)。
