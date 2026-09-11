# Usage

[中文](../usage.md) | **English**

Run all commands from the repository root. No Python package installation is needed. Start with a prepared demo before moving to your own small project.

## Environment and model configuration

- Linux / WSL2 with Python 3.10+.
- Bubblewrap (`bwrap`) installed, with user/network namespaces permitted. If isolation is unavailable, execution fails instead of falling back to unisolated execution on the host.
- An HTTPS Chat Completions endpoint supporting function tools, `tool_choice`, `max_tokens`, and the current explicit `thinking` request field.

```bash
cp .env.example .env
```

Edit `.env`, fill in `LLM_API_KEY`, and confirm `LLM_BASE_URL` and `LLM_MODEL`. The example uses the DeepSeek configuration from the experiment; use a model available to your account. A similar API shape does not guarantee another endpoint will work, especially with the `thinking` field.

Configuration uses simple `KEY=value` entries, without shell execution or variable expansion. The current process's `LLM_*` environment variables take precedence over the file. The program reads only an explicitly supplied `--env-file`; it does not automatically discover `.env` inside the workspace.

Keep configuration outside the target workspace. The API key is used only for requests from the main process and is not passed to the execution sandbox. Git ignores `.env` at the repository root.

## Three prepared demos

```bash
# Create a slugify library, CLI, tests, and documentation from an empty directory.
python3 scripts/demo.py --env-file .env --thinking enabled

# Repair existing defects in the example.
python3 scripts/demo.py --env-file .env --mode repair

# Load a skill and obtain additional CLI acceptance requirements through MCP.
python3 scripts/demo.py --env-file .env --mode repair --skill --mcp
```

Each demo creates `runs/<task-name>-<timestamp>/`. Use `--task-name` to change the short task name or `--dest` to choose a new directory. Existing destination directories are rejected, and the original `examples/slugify/` stays unchanged. The example deliberately contains defects; failing tests are the starting point for repair.

All three commands call a real model. Extension mode also adds task requirements, so the cost difference between two runs cannot directly establish the effect of Skill/MCP.

## Custom development tasks

```bash
python3 -m mini_coding_agent /absolute/path/to/workspace \
  "Implement CSV export, preserve existing behavior, add tests, and fully verify" \
  --env-file .env --thinking enabled \
  --max-input-tokens 250000 --max-output-tokens 50000
```

The workspace can be empty or contain an existing project. Describe requirements, constraints, and acceptance goals in the task; the agent can decide the program structure and implementation order.

The default final verification command is `python3 -m unittest discover -s . -v`. To use a project's own check script:

```bash
python3 -m mini_coding_agent /absolute/path/to/workspace \
  "Complete the requirements in README and pass the project checks" \
  --env-file .env --verify-command "python3 check.py"
```

Check scripts should contain real assertions and return a nonzero exit code on failure. Allowed execution commands are Python scripts specified by relative path and `python3 -m unittest`. Shell pipelines, dependency installation, and arbitrary commands are unsupported.

## Options and stop conditions

| Option | Default | Purpose |
|---|---:|---|
| `--thinking` | `disabled` | Explicitly select `enabled` / `disabled`, overriding legacy thinking settings in the configuration file |
| `--max-steps` | 30 | Maximum number of model-call turns |
| `--max-input-tokens` | 250000 | Cumulative input budget, including cache hits |
| `--max-output-tokens` | 50000 | Cumulative output budget |
| `--max-output-per-call` | 8192 | Per-call output cap, also constrained by remaining output budget |
| `--command-timeout` | 20 seconds | CLI command execution timeout, up to 60 seconds |
| `--task-title` | First sentence of the task | Short title for the CLI run report |
| `--skill` / `--mcp` | Off | Enable the corresponding extension |

The demo exposes common budget and extension options; see `--help` for the full options of each entry point. The legacy `--token-budget` remains only as an explicitly added combined limit.

Input reservation is an estimate made before a call. The ledger prefers actual API usage and charges the reservation only for a side whose usage is missing. A request may push actual input over budget before execution stops, so the budget is not an exact hard cap on cost.

Reports are retained when a budget or step limit is reached or a run encounters an error. `TOKEN_BUDGET` is not success, and the workspace is not automatically rolled back. You can inspect the current code and start another run, but it will not restore the previous conversation.

## Reading outputs

```text
<workspace>/
├── RUN_REPORT.md                 Entry point for the latest run
└── .mini-agent/runs/<run-id>/
    ├── PLAN.md                   Explicit development plan
    ├── trace.jsonl               Model and tool events
    ├── summary.json              Status, usage, budgets, and call statistics
    ├── FINAL.md                  Delivery statement or stop explanation
    └── RUN_REPORT.md             Saved report for this run
```

Start with the report's status, changes, failure feedback, and final verification, then look up tool IDs in the trace. In `summary.json`, `usage` represents actual returned statistics and `budget_usage` represents budget charges. Missing values are not treated as zero; cache and reasoning tokens are not added again on top of the totals.

Run logs are retained in the same workspace, but application code continues changing without automatic per-run source snapshots. Estimated costs in reports use the dated price snapshot recorded in the code and do not represent actual bills. Private reasoning text is not persisted.

## Verification and example acceptance checks

The project's own tests do not call a real model, but do perform actual file operations and execute Bubblewrap and MCP processes:

```bash
python3 -m unittest discover -s tests -v
```

For demo-generated slugify projects, add independent assertions in a temporary sandbox copy:

```bash
python3 scripts/check_delivery.py runs/your-create-directory --created
python3 scripts/check_delivery.py runs/your-repair-directory
python3 scripts/check_delivery.py runs/your-extension-directory --cli
```

This acceptance checker is specific to the slugify example, not a general reviewer for arbitrary projects. Repair mode also checks that original test methods have not been weakened. Your own tasks still require review of requirement coverage and test quality.

## Roles of tests, examples, and scripts

`tests/` verifies the agent itself; `examples/` contains the input project the agent repairs; `scripts/` provides demo and acceptance entry points.

| File | Purpose |
|---|---|
| `tests/test_agent.py` | Development loop, planning gate, rejection of empty test suites, verification invalidation after edits, and exceptional exits |
| `tests/test_budget.py` | Input estimation and separate accounting, missing usage, over-budget stops, and length-truncation recovery |
| `tests/test_workspace.py` | File reads/writes, out-of-bounds paths, configuration isolation, and rejection of links and special files |
| `tests/test_sandbox.py` | Real isolation, command restrictions, timeouts, and output limits |
| `tests/test_provider.py` | HTTP requests and tool responses, thinking settings, credentials, and error handling |
| `tests/test_reporting.py` | Usage statistics, exit reports, argument forwarding, directory naming, and retention of reports across runs |
| `tests/test_extensions.py` | On-demand skill loading, MCP handshake and calls with real processes, and behavior with extensions disabled by default |
| `tests/test_pricing.py` | Price-snapshot calculations, pricing across time periods, and missing-value handling |
| `tests/helpers.py` / `tests/__init__.py` | Controlled model replies and test package marker for stable regression without API usage |
| `examples/slugify/` | README defines the task; source deliberately contains defects, with three baseline tests for before/after repair comparison |
| `scripts/demo.py` | Prepare an independent workspace for creation from scratch, repair of an existing project, and Skill/MCP |
| `scripts/check_delivery.py` | Add independent assertions to slugify deliveries; repair mode also checks that original tests remain unchanged |

There are currently 46 offline tests. The two sets of tests serve different purposes: the agent's regression suite verifies runtime mechanics, while example tests provide real failure feedback to the agent. Both demos and agent tests use the repair example, so it is a functional fixture rather than a disposable display attachment.

Every run generates reports automatically. The public release does not include a script for generating reports from old logs. Newly created `runs/` directories remain ignored by Git.
