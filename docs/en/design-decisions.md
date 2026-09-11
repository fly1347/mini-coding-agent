# Design decisions

[中文](../design-decisions.md) | **English**

This project first implements a working software development loop that can build, execute, repair, and verify, then uses real tasks to identify its limitations. Its current scope is small local Python projects; future capabilities are driven by experimental questions.

## Why a single agent and the standard library

A single synchronous loop makes the relationship between model decisions, tool actions, and environmental feedback easy to follow. Standard-library HTTP, file operations, unittest, and subprocess are sufficient for this experiment, reducing setup requirements and making the harness's implementation responsibilities visible.

Tools provide actions, skills provide methods, and MCP connects external capabilities; all three are consumed in the same loop. This iteration introduces no framework abstractions, general plugin discovery, reviewer, or multi-agent orchestration.

## Why planning and verification are gates

Asking the model to plan first and test last in a prompt does not guarantee that execution follows those rules. The harness therefore checks workspace inspection, plan saving, and final verification in code.

In a real Job Tracker run, the agent changed source code after 54 tests passed. That invalidated the earlier verification and required another regression run before delivery. In a separate continuation run, external checks passed 97 tests, but the run exhausted its budget before completing final verification and `finish`, so it remained `TOKEN_BUDGET`.

These cases show why the software's current test status and the agent's completion of its delivery contract need separate reporting. Gates cannot determine whether tests cover every requirement, so independent acceptance checks remain valuable.

## Why budget handling and truncation recovery changed

The old input estimator roughly treated UTF-8 bytes as tokens. It once reserved about 56K when the actual API input was about 13K, causing a substantially premature stop. Input and output are now accounted for separately, and API usage dynamically calibrates the next input reservation.

The old truncation recovery prompt required one tool call at a time, and subsequent calls became fragmented. The current implementation discards tools from truncated responses, asks for smaller edits, and allows multiple complete small calls. The per-call output cap increased from 4,096 to 8,192.

These changes came from real run feedback. Several settings changed together, so this experiment did not isolate their individual effects.

## Why retain Full History for now

Full history makes continuous feedback observable and avoids introducing summary state too early. Existing repositories, however, require substantial reading, and every later request carries that history again, rapidly increasing cumulative input. High cache hit rates can affect cost but do not reduce input consumption in the budget ledger.

Three incremental runs stopped with input budgets of 250K, 800K, and 400K, exposing the context-growth limit. There are no comparative results for alternative strategies yet, so this explicit baseline is retained.

The next priority is Context Management. It needs evaluation across completion rate, continuity, usage, cost, time, and rework, with multiple tasks and repeated runs. Lower token usage alone is not evidence of a better strategy.

## Current boundaries

| Area | Limitation |
|---|---|
| Execution environment | Linux / WSL2 + Bubblewrap; only controlled Python scripts and unittest, without dependency installation, shell pipelines, or service orchestration |
| Isolation | Intended for trusted small projects; no total disk quota, comprehensive syscall policy, or production multitenant guarantees |
| File tools | At most 1,000 files and 256 KiB per file; no links, special files, or large-repository indexing |
| Command resources | Default timeout of 20 seconds; CPU time 20 seconds, address space 512 MiB, individual file size 8 MiB; execution terminates when output exceeds 1 MiB |
| State continuity | No persistent session recovery, automatic rollback, or concurrent runs in the same workspace; a new run starts from the current source |
| Model interface | Tested with deepseek-v4-flash; requests explicitly include thinking, with no promise that all compatible endpoints work |
| Budgets and costs | Input reservation is not an exact tokenizer; missing usage, over-budget responses, and failed requests affect cost guarantees |
| Verification | Checks command execution and source versions, not all requirement semantics; the model can also write incorrect tests |

## Next directions

1. **Context Management**: control history growth in long tasks and assess information loss and completion rate.
2. **Session / Recovery**: preserve task state and distinguish conversation recovery from continuation based only on existing code.
3. **Repo Exploration**: reduce indiscriminate file reading and improve navigation in existing repositories.
4. **Reviewer / Subagent**: introduce independent review after defining clear review criteria, then verify its benefits.

See [Evaluation](evaluation.md) for the corresponding experiments and data.
