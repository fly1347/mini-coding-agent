# Mini Coding Agent

**中文** | [English](README.en.md)

一个用 **Python 标准库**实现的最小 Coding Agent：根据自然语言任务查看仓库、规划、修改代码、运行测试，并根据真实反馈继续修复，直到验证交付或触发预算停止。

```text
任务 → 查看与计划 → 修改代码 ⇄ 执行与反馈 → 验证 → 交付
```

## 核心实现

- **开发闭环**：文件检索与编辑、真实 Python 执行、失败修复与回归。
- **运行时约束**：修改前必须有计划；源码变化使旧验证失效，完成声明必须引用有效验证。
- **执行边界**：Workspace 路径检查 + Bubblewrap 隔离，执行进程禁网、清空环境。
- **预算与报告**：Input / Output 分账，记录真实 Usage、工具轨迹与中文运行报告。
- **可选扩展**：按需加载测试修复 Skill，通过 stdio MCP 获取项目说明。

## 真实运行结果

2026-09-10，使用 `deepseek-v4-flash` 完成 0→1、增量开发及扩展接入实验。

| 场景 | Run 状态 | 外部测试结果 | 观察 |
|---|---|---|---|
| 从空目录开发 Job Tracker CLI | SUCCESS | 54/54 + Smoke 通过 | 验证后再次改动，必须重跑回归 |
| 已有项目增量开发，最后一轮接力 | TOKEN_BUDGET | 97/97 + Smoke 通过 | 软件已全绿，Run 尚未完成最终交付 |
| 测试修复 + Skill / MCP | SUCCESS | 16/16 通过 | 方法、外部说明与失败反馈进入同一循环 |

**主要限制是 Full History 的上下文增长**：增量任务的三轮运行分别耗尽 250K、800K、400K Input 预算。以上为单次运行观察；完整六轮数据与结论边界见 [实验结果](docs/evaluation.md)。

## 快速运行

需要 Linux / WSL2、Python 3.10+、Bubblewrap，并允许创建 user/network namespaces。Python 部分无第三方依赖。

在仓库根目录准备模型配置：

```bash
cp .env.example .env
# 填入 API Key，并确认端点和模型名称。
python3 scripts/demo.py --env-file .env --thinking enabled
```

演示从空目录创建 slugify 库、CLI 和测试；结果位于 `runs/`，首读生成的 `RUN_REPORT.md`。真实运行会产生 API 用量。模型端点需支持当前请求格式，详见 [配置与用法](docs/usage.md)。

使用自己的工作区：

```bash
python3 -m mini_coding_agent /absolute/path/to/workspace \
  "修复日期解析边界，补充测试并完成回归验证" \
  --env-file .env --thinking enabled
```

离线验证：

```bash
python3 -m unittest discover -s tests -v
```

## 仓库导航

```text
mini_coding_agent/   Agent Loop、模型接口、工具、隔离、预算与报告
scripts/            演示与样例交付验收
examples/           测试修复用的最小 slugify 项目
skills/             可选 test-repair Skill
tests/              离线回归测试
docs/               用法、架构、实验结果与设计取舍
```

- [使用指南](docs/usage.md)：配置、参数、演示与运行产物。
- [架构](docs/architecture.md)：模块职责、工具和运行时门禁。
- [实验结果](docs/evaluation.md)：任务、六轮数据与关键观察。
- [设计取舍](docs/design-decisions.md)：实现选择、已知限制与后续方向。

适合小型、可信的本地 Python 项目；当前保留单 Agent 与完整历史，不提供 Session 恢复或生产级多租户隔离。按 [MIT License](LICENSE) 发布。
