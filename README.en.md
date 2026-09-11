# Mini Coding Agent

[中文](README.md)

A minimal coding agent built with the **Python standard library**. Given a natural-language task, it inspects a repository, plans changes, edits code, runs tests, and uses real feedback to keep fixing problems until it delivers verified work or stops at its budget limit.

```text
Task → Inspect & Plan → Edit Code ⇄ Execute & Observe → Verify → Deliver
```

## Core implementation

- **Development loop**: file search and editing, real Python execution, failure repair, and regression testing.
- **Runtime gates**: a plan is required before changes; source changes invalidate earlier verification, and completion must reference valid verification.
- **Execution boundaries**: workspace path checks plus Bubblewrap isolation, with networking disabled and the execution environment cleared.
- **Budgets and reports**: separate input/output accounting, actual API usage, tool traces, and Chinese run reports.
- **Optional extensions**: load a test-repair skill on demand and retrieve project notes through stdio MCP.

## Real run results

On 2026-09-10, experiments with `deepseek-v4-flash` covered development from scratch, incremental changes, and extension integration.

| Scenario | Run status | External test results | Observation |
|---|---|---|---|
| Build a Job Tracker CLI from an empty directory | SUCCESS | 54/54 + smoke checks passed | Changes after verification required another regression run |
| Incremental development, final continuation run | TOKEN_BUDGET | 97/97 + smoke checks passed | The software passed tests, but the run had not completed final delivery |
| Test repair + Skill / MCP | SUCCESS | 16/16 passed | Methods, external notes, and failure feedback entered the same loop |

**The main limitation is context growth with Full History**: three incremental runs exhausted input budgets of 250K, 800K, and 400K. These are individual run observations; see [Evaluation](docs/en/evaluation.md) for all six runs and the limits of the conclusions.

## Quick start

Requires Linux / WSL2, Python 3.10+, Bubblewrap, and permission to create user/network namespaces. The Python code has no third-party dependencies.

Run directly from source, or install the `mini-coding-agent` command with `python -m pip install .`; see [Installation and dependencies](docs/en/usage.md#installation-and-dependencies). Project metadata and build configuration are in [pyproject.toml](pyproject.toml).

Prepare the model configuration at the repository root:

```bash
cp .env.example .env
# Fill in the API key and confirm the endpoint and model name.
python3 scripts/demo.py --env-file .env --thinking enabled
```

The demo creates a slugify library, CLI, and tests from an empty directory. Results appear under `runs/`; start with the generated `RUN_REPORT.md`. Live runs consume API usage. The model endpoint must support the current request format; see [Usage](docs/en/usage.md).

Use your own workspace:

```bash
python3 -m mini_coding_agent /absolute/path/to/workspace \
  "Fix date-parsing edge cases, add tests, and complete regression verification" \
  --env-file .env --thinking enabled
```

Offline verification:

```bash
python3 -m unittest discover -s tests -v
```

## Repository guide

```text
mini_coding_agent/   Agent loop, model interface, tools, isolation, budgets, reports
scripts/            Demos and example delivery checks
examples/           Minimal slugify project for test repair
mini_coding_agent/skills/  Bundled optional test-repair skill
tests/              Offline regression tests
docs/               Chinese usage, architecture, evaluation, and design decisions
docs/en/            English documentation
```

- [Usage](docs/en/usage.md): configuration, options, demos, and run artifacts.
- [Architecture](docs/en/architecture.md): module responsibilities, tools, and runtime gates.
- [Evaluation](docs/en/evaluation.md): tasks, six runs, and key observations.
- [Design decisions](docs/en/design-decisions.md): implementation choices, known limits, and next steps.

Intended for small, trusted local Python projects. The current implementation uses a single agent and full history, without session recovery or production-grade multitenant isolation. Released under the [MIT License](LICENSE).
