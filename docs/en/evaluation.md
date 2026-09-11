# Evaluation

[中文](../evaluation.md)

On 2026-09-10, six real runs with `deepseek-v4-flash` in local workspaces explored development from scratch, incremental changes to an existing project, budget stops, and Skill/MCP integration. The context strategy was Full History.

This page summarizes the original run records and external checks performed at the time. The public repository includes only the summary, without raw traces or generated project snapshots. These are individual run observations, not a model benchmark, and they do not support statistical conclusions about stable success rates or the superiority of one strategy.

## Tasks and settings

**Job Tracker from scratch**: build a local job-application tracking CLI from an empty directory, including adding, listing, filtering, status updates, details, deletion, SQLite persistence, error handling, and automated tests. Only functional and acceptance requirements were supplied; the agent chose the directory layout, schema, CLI, and implementation order.

**Incremental development**: add duplicate protection for `company + job_id`, CSV export, and status statistics to V1, with duplicate protection disabled when `job_id` is empty. The new requirements conflicted with the global `job_id UNIQUE` constraint that V1 had introduced on its own, requiring changes to implementation, migration logic, and tests.

**Skill + MCP**: load the test-repair skill on demand during a slugify repair task and obtain CLI and subprocess regression requirements through MCP, observing whether the extensions were actually used.

The first run used the old `thinking=auto` setting, and the API returned reasoning tokens; subsequent runs explicitly used `enabled`. There was no Thinking / Non-thinking comparison. Budget handling and length-truncation recovery also changed between the two from-scratch runs, so differences cannot be attributed to a single factor.

## Six runs

| Run | Input cap | Run status | Model / tool calls | Input | Output | Duration |
|---|---:|---|---:|---:|---:|---:|
| V1 initial run, old budget implementation | Old combined budget | TOKEN_BUDGET | 15 / 14 | 83,498 | 16,227 | 63.4 s |
| V1, after budget fix | 250K | SUCCESS | 16 / 21 | 212,229 | 18,417 | 73.1 s |
| V2 incremental | 250K | TOKEN_BUDGET | 12 / 23 | 223,748 | 8,969 | 39.4 s |
| V2, restarted from successful V1 | 800K | TOKEN_BUDGET | 25 / 36 | 767,973 | 21,215 | 95.2 s |
| V2, continuing from the previous workspace | 400K | TOKEN_BUDGET | 18 / 30 | 381,297 | 7,682 | 40.2 s |
| Skill + MCP | 250K | SUCCESS | 8 / 15 | 28,257 | 2,922 | 16.5 s |

Across all six runs: 94 model calls, 139 tool calls, 1,697,002 input tokens, 75,432 output tokens, and 1,772,434 total tokens. Cache hits accounted for 1,605,632 input tokens, approximately 94.6%.

The last five runs had an estimated combined cost of about ¥0.710 using the 2026-09-10 price snapshot in their reports. This is an experimental record, not a bill or current pricing. Cache hits are part of input and reasoning is part of output; neither is counted again.

## External checks and key observations

| Run | External checks at the time | Observation |
|---|---|---|
| V1 initial run | 59 tests: 58 PASS / 1 ERROR | A test lacked a `contextlib` import; the run stopped before full verification |
| V1 successful | 54/54 PASS, smoke checks PASS | Source changes after verification required a full regression rerun before delivery |
| V2 250K | 54 tests: 5 ERROR, smoke checks FAIL | Newly called methods were not yet implemented; work stopped partway through |
| V2 800K | 81 tests: 80 PASS / 1 FAIL, smoke checks PASS | An old test still required globally unique job_id values, conflicting with the new requirement |
| V2 continuation | 97/97 PASS, smoke checks PASS | Code passed external tests, but the run had not completed final delivery |
| Skill + MCP | 16/16 PASS | Method loading, external requirement retrieval, failure repair, and regression all occurred |

External checks ran the full `unittest` suite and, where needed for Job Tracker, `tools/smoke_check.py`. These counts refer to the projects being developed, not Mini Coding Agent's own tests.

The 800K run and the continuation shared a workspace, whose source changed during continuation. The 81-test result comes from the record at that time; the later source cannot serve as a snapshot of that earlier state. Continuation started a new run that read the existing code, rather than recovering the previous session.

### Verification loop from scratch

```text
Inspect empty directory → Save plan → Create project → 54 tests PASS → Smoke PASS
→ Edit source again → Previous verification invalidated → 54 tests PASS → finish
```

This run showed code-enforced gates participating in actual development. The agent also introduced design choices beyond the requirements, which had to be reconsidered when requirements changed.

### Budget mechanics and context limits

The old input reservation once estimated about 56K against actual API input of about 13K, causing a premature stop. After separate accounting and dynamic calibration, the V2 250K stop was explained by 26,252 remaining input tokens versus an estimated 36,941 for the next call.

Incremental tasks generated many source reads, edits, and test outputs, with full history repeatedly carried into later prompts. Even the 800K budget was exhausted, making context growth the main limitation in this experiment. High cache hit rates do not remove cumulative input pressure.

### Run status and code state

The final continuation remained `TOKEN_BUDGET` even though all external tests passed. The harness did not complete currently valid final verification and `finish` within the budget; successful tests afterward cannot retroactively change the run to `SUCCESS`.

## What was observed and what remains unanswered

The experiment observed a complete development loop from scratch, handling of requirement conflicts in an existing project, real failure feedback, verification invalidation and reruns, budget stops, and Skill/MCP participation in the same agent loop.

It did not compare models, establish whether Skill/MCP improved quality or efficiency, or demonstrate that any Context Management strategy outperforms Full History. Repeated runs, a fixed task set, and stronger independent acceptance checks need separate experimental design.

Mini Coding Agent also has **46 offline regression tests** covering workspace boundaries, real sandbox and MCP execution, planning/verification gates, budgets and length truncation, the provider, and reporting. They use controlled model replies and are not presented as real LLM runs. See [Usage](usage.md) to reproduce them.
