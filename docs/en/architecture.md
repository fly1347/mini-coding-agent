# Architecture

[中文](../architecture.md) | **English**

Mini Coding Agent is a synchronous, single-agent local development loop. The model chooses the next action; the harness checks whether it is allowed, executes tools, feeds back real results, and determines when delivery is permitted.

```text
CLI: task, workspace, configuration
          ↓
    Agent Loop ←───────────────┐
          ↓                    │
 Provider: model request       │
          ↓                    │
 Tool Calls                    │
          ↓                    │
 Argument and phase checks     │
          ↓                    │
 File tools / Bubblewrap / Skill / MCP
          ↓                    │
     Tool Results ─────────────┘
          ↓
   Verify & Stop → Trace / Summary / Report
```

## Module boundaries

| File | Responsibility |
|---|---|
| [__main__.py](../../mini_coding_agent/__main__.py) | CLI options, model configuration, workspace, and exit codes |
| [agent.py](../../mini_coding_agent/agent.py) | Tool definitions and dispatch, agent loop, state gates, exits, and artifacts |
| [provider.py](../../mini_coding_agent/provider.py) | Standard-library HTTP requests, tool-call responses, and usage |
| [workspace.py](../../mini_coding_agent/workspace.py) | Path boundaries, file operations, search, and source fingerprints |
| [sandbox.py](../../mini_coding_agent/sandbox.py) | Command parsing, Bubblewrap mounts, timeouts, and resource limits |
| [budget.py](../../mini_coding_agent/budget.py) | Input reservation calibrated against recent actual usage |
| [reporting.py](../../mini_coding_agent/reporting.py) / [pricing.py](../../mini_coding_agent/pricing.py) | Usage normalization, reports, and cost estimates using dated prices |
| [mcp_notes.py](../../mini_coding_agent/mcp_notes.py) / [mcp_server.py](../../mini_coding_agent/mcp_server.py) | Stdio MCP client and read-only server for a fixed project-notes tool |

## How a turn proceeds

1. Check remaining steps and budgets, reserving input and output capacity for the next call.
2. The provider sends the full messages and tool schemas, then returns the model message, tool calls, usage, and finish reason.
3. Record actual usage. If the budget has been reached, stop without executing tools from that response.
4. Validate and execute tool calls, appending results to messages by call ID. Tool errors also return to the model as feedback.
5. The model continues inspecting, editing, or verifying based on the latest results. Only a valid `finish` produces success.

When `finish_reason=length`, the entire batch of tool calls is discarded to avoid executing truncated arguments. The next prompt asks for smaller edits while still allowing multiple complete, compact tool calls.

## Tools and gates

| Tool | Action and constraints |
|---|---|
| `list_files` / `read_file` / `search` | List files, read file segments, and search text |
| `save_plan` | Save the goal, steps, and verification approach; an empty workspace must first be listed, and an existing project requires at least one file read |
| `write_file` / `replace_text` | Create files or replace exact text; requires a plan, and changes invalidate previous verification |
| `run_shell` | Run controlled Python commands after a plan exists; return output, exit code, and termination reason |
| `finish` | Reference a currently valid verification tool ID, with the source fingerprint still matching verification time |
| `load_skill` | Load the fixed test-repair skill on demand when enabled |
| `mcp_project_notes` | Retrieve project notes through a separate process when enabled |

Final verification requires an exact match with the configured command, a successful exit without timeout, and no source changes during execution. Unittest must also discover actual tests. Any source change after verification requires verification again.

The gates check execution facts and source versions. Whether test assertions fully express the requirements still needs external review.

## Two execution boundaries

**Workspace** constrains file tools: it rejects out-of-bounds paths, symbolic links, hard links, and special files, and hides configuration and runner-reserved files. Limits are 1,000 source files and 256 KiB per file.

**Bubblewrap** constrains executed programs: the target workspace is writable, while system Python and runtime libraries are read-only. Networking is isolated, the environment is cleared, paths such as `.git`, `.env*`, and `.mini-agent` are hidden, and the API key is not passed to the execution process.

Execution limits cover CPU, address space, file size, timeout, and output volume. Missing Bubblewrap or namespace permissions cause failure; there is no fallback to execution without isolation. See [Design decisions](design-decisions.md) for the full scope.

## Budgets and context

The current strategy is Full History: messages, tool calls, and tool results keep accumulating, without summarization, truncation, or retrieval-based context selection.

The initial input estimate is `ceil(UTF-8 request bytes / 3) + 512`. Subsequent estimates use the largest valid `prompt_tokens / request bytes` ratio from the last five calls, with a 20% margin and 512 extra tokens. Requested output is the smaller of the per-call cap and remaining output budget.

Actual API input and output are accumulated separately. Cache tokens belong to input; reasoning tokens belong to output. If usage is missing, only the missing side is charged its reservation, while reports preserve missing actual usage and coverage information.

## Extensions and run artifacts

Skills provide reusable working methods without adding tool permissions. MCP brings in external information through `initialize → tools/list → tools/call`. The current implementation supports only the required stdio subset of the fixed 2025-06-18 protocol version; the server reads `PROJECT_NOTES.md` inside the workspace.

Both extensions are disabled by default and leave the main loop unchanged. The MCP implementation is a minimal protocol experiment, not a general-purpose client or plugin system.

Every run generates a plan, trace, summary, delivery statement, and Chinese report. Success, budget stops, exceptions, and interruptions all leave results. Earlier logs in the same workspace are retained, but source code is neither rolled back nor snapshotted automatically. See [Usage](usage.md) for paths and reading order.
