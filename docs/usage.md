# 使用指南

[English](en/usage.md)

源码运行、Demo 和测试命令从仓库根目录执行，无需先安装本项目。首次使用建议运行预制 Demo，再切换到自己的小型项目。

## 安装与依赖

仓库提供 `pyproject.toml`，声明 Python 3.10+、MIT 许可证、构建方式和 `mini-coding-agent` 命令入口。Python 运行依赖为空（`dependencies = []`），因此不另放空的 `requirements.txt`。Bubblewrap 是需要单独安装的系统依赖，模型配置使用仓库中的 [.env.example](../.env.example)。

如需在仓库目录外使用命令，可从仓库根目录安装到虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
mini-coding-agent --help
```

安装后，`mini-coding-agent` 与 `python -m mini_coding_agent` 都可用；配置文件请使用明确路径，例如 `--env-file /absolute/path/to/model.env`。Skill 和 MCP 服务随 Python 包分发，Demo、样例与测试从源码仓库运行。构建依赖 setuptools 不属于运行依赖。

开发时可使用 `python -m pip install -e .`。如需自行构建源码包和 wheel：

```bash
python -m pip install build
python -m build
```

产物写入 `dist/`。这些命令从源码安装或构建，不要求项目已发布到 PyPI。

## 环境与模型配置

- Linux / WSL2，Python 3.10+。
- 已安装 Bubblewrap（`bwrap`），系统允许 user/network namespaces。隔离不可用时执行失败，不会退回宿主裸执行。
- HTTPS Chat Completions 端点，支持 function tools、`tool_choice`、`max_tokens` 和当前显式 `thinking` 请求字段。

```bash
cp .env.example .env
```

编辑 `.env`，填入 `LLM_API_KEY`，确认 `LLM_BASE_URL` 与 `LLM_MODEL`。示例采用实验时的 DeepSeek 配置，模型名称以账户实际可用项为准。仅接口形式相近不代表其他端点能直接运行，尤其需检查 `thinking` 字段兼容性。

配置为简单的 `KEY=value`，不会执行 shell 或展开变量。当前进程的 `LLM_*` 环境变量优先于文件；程序只读取显式 `--env-file`，不会自动查找工作区内的 `.env`。

配置放在目标工作区外；API Key 只用于主进程请求，不传给执行沙箱。仓库根目录 `.env` 已由 Git 忽略。

## 三种预制体验

```bash
# 从空目录创建 slugify 库、CLI、测试和说明。
python3 scripts/demo.py --env-file .env --thinking enabled

# 修复样例中已有的缺陷。
python3 scripts/demo.py --env-file .env --mode repair

# 同一修复任务中加载 Skill，并通过 MCP 获得额外 CLI 验收要求。
python3 scripts/demo.py --env-file .env --mode repair --skill --mcp
```

Demo 每次创建 `runs/<任务名>-<时间戳>/`；`--task-name` 修改任务短名，`--dest` 指定新目录。已有目标目录会被拒绝，原始 `examples/slugify/` 保持不变。样例故意含缺陷，其测试失败是 repair 的起点。

三条命令都会调用真实模型；扩展模式还增加任务要求，因此不能直接用两轮费用差异判断 Skill/MCP 的效果。

## 自定义开发任务

```bash
python3 -m mini_coding_agent /absolute/path/to/workspace \
  "实现 CSV 导出，保留已有行为，补充测试并完整验证" \
  --env-file .env --thinking enabled \
  --max-input-tokens 250000 --max-output-tokens 50000
```

工作区可以为空，也可以是已有项目。任务应说明需求、约束与验收目标；程序结构和实施顺序可由 Agent 决定。

默认最终验证命令为 `python3 -m unittest discover -s . -v`。使用项目自检程序时可指定：

```bash
python3 -m mini_coding_agent /absolute/path/to/workspace \
  "完成 README 中的需求并通过自检" \
  --env-file .env --verify-command "python3 check.py"
```

自检脚本应有真实断言，失败时返回非零。允许的执行命令是相对路径 Python 脚本和 `python3 -m unittest`；不支持 shell 管道、安装依赖或任意命令。

## 参数与停止条件

| 参数 | 默认值 | 作用 |
|---|---:|---|
| `--thinking` | `disabled` | 显式选择 `enabled` / `disabled`，覆盖配置文件中的旧 thinking 设置 |
| `--max-steps` | 30 | 模型调用轮数上限 |
| `--max-input-tokens` | 250000 | 累计输入预算，包含缓存命中部分 |
| `--max-output-tokens` | 50000 | 累计输出预算 |
| `--max-output-per-call` | 8192 | 单次输出上限，同时受剩余输出预算约束 |
| `--command-timeout` | 20 秒 | CLI 执行命令的超时限制，最多 60 秒 |
| `--task-title` | 任务首句 | CLI 运行报告的短标题 |
| `--skill` / `--mcp` | 关闭 | 启用各自扩展 |

Demo 提供常用预算和扩展开关；各入口完整参数见 `--help`。旧 `--token-budget` 仅作为显式附加的总量限制保留。

输入预留是调用前估算，账本优先使用 API 实际 Usage；缺少某侧 Usage 时才对该侧按预留额扣账。一次请求可能使实际输入超过预算后再停止，预算不等于精确费用硬上限。

达到预算、轮数上限或运行异常时会保留报告。`TOKEN_BUDGET` 不能当成成功，工作区也不会自动回滚；可以检查当前代码后发起新的 Run，但新 Run 不恢复旧对话。

## 阅读输出

```text
<workspace>/
├── RUN_REPORT.md                 最新一次运行的阅读入口
└── .mini-agent/runs/<run-id>/
    ├── PLAN.md                   显式开发计划
    ├── trace.jsonl               模型与工具事件
    ├── summary.json              状态、用量、预算和调用统计
    ├── FINAL.md                  交付声明或停止说明
    └── RUN_REPORT.md             该次运行的固定报告
```

先读报告中的状态、修改清单、失败反馈和最终验证，再按 Tool ID 查 trace。`summary.json` 的 `usage` 是实际返回的统计，`budget_usage` 是预算扣账；缺失值不当作零，缓存和 reasoning 不在总量之外重复相加。

同一工作区会保留各次运行日志，但业务代码继续变化，不自动形成每轮源码快照。报告中的预估费用使用代码内注明日期的价格快照，不代表实际账单。私有推理正文不持久化。

## 验证与样例验收

项目自身测试不调用真实模型，但会实际执行文件操作、Bubblewrap 和 MCP 进程：

```bash
python3 -m unittest discover -s tests -v
```

对 Demo 生成的 slugify 项目，可以在临时沙箱副本中增加独立断言：

```bash
python3 scripts/check_delivery.py runs/你的创建目录 --created
python3 scripts/check_delivery.py runs/你的修复目录
python3 scripts/check_delivery.py runs/你的扩展目录 --cli
```

这是 slugify 样例专用验收器，不是任意项目的通用评审器。repair 模式还检查原始测试方法未被改弱；对自己的任务仍需检查需求覆盖与测试质量。

## 测试、样例与脚本各自做什么

`tests/` 验证 Agent 本身；`examples/` 是交给 Agent 修复的输入项目；`scripts/` 提供体验和验收入口。

| 文件 | 用途 |
|---|---|
| `tests/test_agent.py` | 开发循环、计划门禁、空测试拒绝、修改后验证失效及异常退出 |
| `tests/test_budget.py` | 输入估算与分账、缺失用量、超额停止、长度截断恢复 |
| `tests/test_workspace.py` | 文件读写、路径越界、配置隔离、链接与特殊文件拒绝 |
| `tests/test_sandbox.py` | 实际隔离、命令限制、超时和输出量限制 |
| `tests/test_provider.py` | HTTP 请求与工具响应、Thinking 设置、凭据和错误处理 |
| `tests/test_reporting.py` | 用量统计、退出报告、参数传递、目录命名及多轮报告保留 |
| `tests/test_extensions.py` | Skill 按需加载、MCP 真实进程握手与调用、默认关闭行为 |
| `tests/test_pricing.py` | 价格快照的计算规则、跨时段计价、缺失值处理 |
| `tests/helpers.py` / `tests/__init__.py` | 可控模型回复和测试包标记，使回归稳定且不产生 API 用量 |
| `examples/slugify/` | README 定义任务，源码故意带缺陷，三项基线测试供修复前后比较 |
| `scripts/demo.py` | 准备独立工作区，体验从零创建或已有项目修复，以及 Skill/MCP |
| `scripts/check_delivery.py` | 对 slugify 交付另加独立断言；repair 模式还检查原测试未被修改 |

当前共 46 项离线测试。保留两份用途不同的测试：Agent 自身回归验证运行机制，样例测试为 Agent 提供真实失败反馈。Demo 与 Agent 测试都使用修复样例，因此它不是可随意删除的展示附件。

每次运行自动生成报告；发布版不提供旧日志补报告脚本。运行后新建的 `runs/` 仍由 Git 忽略。
