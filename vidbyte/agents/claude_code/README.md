# `vidbyte/agents/claude_code`

## Folder Description / Intent

This folder holds `ClaudeCodeHarnessAgent`, an agent object that **is one Claude Code conversation** on the user's own machine. Its first `arun` starts a Claude Code session in print mode, and every later `arun` on the same object resumes that session, so the object is the thread. Each turn runs the user's own `claude` executable under the user's own Claude login or API key, so **Anthropic bills the user's account directly**; the SDK only starts the process and reads its answer.

It is the Anthropic twin of [`CodexHarnessAgent`](../codex/README.md) for bring-your-own-key callers. vidbyte-cli's `agents suggest` runs every generator and critic turn of an Anthropic user through it, and the CLI's runtimes can reuse it. The surface is deliberately smaller than Codex's: typed record in (`ClaudeCodeRunInput`), typed record out (`ClaudeCodeRunResult`), one closed failure vocabulary (`ClaudeCodeFailureKind`). The public names and fields are pinned by the cross-repo suggest-BYOK contract; optional fields may be added, names are never changed.

The design and the live-observed wire shape it is built on are in `docs/design/claude-code-harness-agent.md`.

## Requirements

- Claude Code installed and on `PATH` (`claude --version` works), or `claude_bin` pointing at the executable. On Windows the native installer's `claude.exe` is required: an npm `claude.cmd` batch launcher is refused, because `cmd.exe` would re-read its arguments.
- Claude Code signed in (`claude auth login`), or `ANTHROPIC_API_KEY` (or a Bedrock/Vertex setup) in the environment. The SDK never reads, stores or prints the credential.
- Checked against Claude Code 2.1.314. An older build that lacks one of the flags below fails with `EXIT_NONZERO` and a message telling the user to run `claude update`.

No extra Python package is needed.

## Quick start

```python
import asyncio

from vidbyte import (
    ClaudeCodeHarnessAgent,
    ClaudeCodeHarnessAgentSettings,
    ClaudeCodeRunInput,
)

agent = ClaudeCodeHarnessAgent(
    ClaudeCodeHarnessAgentSettings(
        name="suggestion-generator",
        instructions="You are a product strategist. Answer only through the structured output.",
        model="sonnet",                      # None: Claude Code's built-in default
        effort="high",                       # low | medium | high | xhigh | max
        output_schema={
            "type": "object",
            "properties": {"ideas": {"type": "array", "items": {"type": "string"}}},
            "required": ["ideas"],
        },
    )
)


async def main() -> None:
    first = await agent.arun(ClaudeCodeRunInput(prompt="Suggest three growth ideas for a CLI tool."))
    print(first.output["ideas"], first.session_id)
    # Same object, same conversation: Claude Code remembers the first turn.
    second = await agent.arun(ClaudeCodeRunInput(prompt="Rank the ideas you gave by effort."))
    print(second.output, second.usage.output_tokens, second.cost_usd, second.model)
    agent.close()   # removes the temporary folder the agent made


asyncio.run(main())
```

`run()` is the synchronous twin; inside an event loop use `await arun()`. A plain string is accepted as a prompt.

## Settings (`ClaudeCodeHarnessAgentSettings`)

| Field | Default | What it does |
|---|---|---|
| `name` | required | A label for the agent. |
| `instructions` | required | The system prompt. Written to a private temporary file and passed with `--system-prompt-file`, so 50 KB instructions never meet the Windows command-line limit. |
| `model` | `None` | `--model`. Any name Claude Code accepts: aliases (`haiku`, `sonnet`, `opus`), full names, Bedrock/Vertex ids. `None` keeps Claude Code's built-in default for the account (the user's own default-model setting is not read, because no user settings load). |
| `output_schema` | `None` | A JSON Schema for an object, sent as `--json-schema`. The answer then arrives in `result.output` as a dict. |
| `effort` | `None` | `--effort`, as a `ClaudeCodeEffort` or its text. |
| `allowed_tools` | `()` | Built-in Claude Code tools the turn may use (`"Read"`, `"Grep"`, ...). Empty means `--tools ""`: every built-in tool is off, a read-only advisor. Named tools are also pre-approved, because print mode cannot ask anyone. |
| `workspace` | `None` | The folder Claude Code runs in (must exist). `None` makes one empty temporary folder on the first run and keeps it for the agent's life. |
| `claude_bin` | `None` | Path to the `claude` executable; `None` looks up `claude` in the `PATH` folders (never the current folder). |
| `timeout_seconds` | `600.0` | The time bound of one run; past it the whole process tree is stopped. |
| `session_id` | `None` | Optional addition: resume a saved session. Requires `workspace`, because Claude Code finds a session only from the folder it ran in. |

## What every run does

1. Refuses an attachment Claude Code cannot take (`UNSUPPORTED_INPUT`) and a missing `claude` (`NOT_INSTALLED`) before anything starts.
2. Starts `claude --print --input-format=stream-json --output-format=stream-json --verbose --safe-mode --setting-sources= --strict-mcp-config --disable-slash-commands --system-prompt-file=<private file> --tools=<...> [--allowed-tools=...] [--model=...] [--effort=...] [--json-schema=...] --session-id=<new uuid4> | --resume=<id>` in the workspace.
3. Writes one stream-json user message to stdin (each image as a base64 block, then the prompt) and closes it.
4. Reads the stream-json events: the `init` event (the run is refused if it shows a tool or MCP server the settings did not allow) and the final `result` event.

**Isolation.** `--safe-mode` and `--setting-sources=` load none of the user's hooks, plugins, CLAUDE.md files, auto-memory or settings; `--strict-mcp-config` loads no MCP server; `--disable-slash-commands` loads no skill or command. `--bare` is not used: it ignores the Claude login. The child inherits the caller's environment (the user's own key and `CLAUDE_CONFIG_DIR` keep working) minus the variables a parent Claude Code session sets for its children (`CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_MESSAGING_*`, `CLAUDE_EFFORT`, ...), because the CLI is often run from inside a Claude Code session.

**Disk.** The instructions file lives in its own private temporary folder and is removed after every run, including on cancellation. The workspace is left as the caller gave it. Claude Code itself keeps the conversation transcript under `~/.claude/projects/<folder key>/`.

## Reading the result (`ClaudeCodeRunResult`)

| Field | Meaning |
|---|---|
| `output` | The structured output dict when `output_schema` is set, else `None`. |
| `text` | Claude Code's final text (with a schema, the same object as JSON text). |
| `session_id` | The session; equals `agent.session_id` after the first success. |
| `usage` | `ClaudeCodeUsage(input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens)` for **this run alone**. |
| `cost_usd` | Claude Code's own reported cost of **this run alone** (informational: the user's account pays it). `None` only when an agent resumed a saved session and Claude Code omitted its per-run cost. |
| `model` | The model that wrote most of this run's output. |
| `num_turns`, `duration_ms` | Optional additions: model turns in the run and its wall time as Claude Code reported them. |
| `session_cost_usd` | Optional addition: Claude Code's cumulative cost for the whole session. |

Claude Code's `total_cost_usd` grows over a resumed session, so it is reported as `session_cost_usd`, never as `cost_usd`; summing `cost_usd` over runs gives the session total.

## Errors

Every runtime failure is one `ClaudeCodeAgentError` (from `vidbyte` and `vidbyte.lib.errors`, a `VidbyteSdkError`) with `kind`, `session_id`, `exit_code`, `likely_cause` and `next_step`. Its message says what happened, quotes Claude Code's own words (credentials scrubbed), the likely cause and the next step. Cancellation is never wrapped. Bad settings raise `ConfigurationError` at construction.

| `kind` | When |
|---|---|
| `NOT_INSTALLED` | No `claude` on `PATH`, `claude_bin` missing or not runnable, or only a Windows batch launcher found. |
| `NOT_AUTHENTICATED` | Claude Code reported a login or key problem (`Not logged in · Please run /login`, an invalid key, HTTP 401/403). |
| `TIMEOUT` | The run passed `timeout_seconds`; the process tree was stopped. |
| `EXIT_NONZERO` | Any other failure Claude Code reported: API errors, overload, an unknown session in this folder, an unknown flag (old Claude Code). |
| `SCHEMA_VIOLATION` | `output_schema` was set but Claude Code returned no structured object. |
| `UNSUPPORTED_INPUT` | An attachment other than png, jpeg, gif or webp images, or (Windows) an `output_schema` too long for the command line. Text files are the caller's to inline in the prompt. |
| `MALFORMED_OUTPUT` | No final result event, another session's answer, output past the cap, or a session that started with tools or MCP servers the settings did not allow. |

A failed run never changes `agent.session_id`: a failed first run starts a fresh session next time, and a failed resume can be retried on the same session.

## Blast Radius

The public names are re-exported from this package, `vidbyte.agents` and the root `vidbyte` package, and listed in `contracts/sdk-public-api.json`, which vidbyte-cli vendors (its lint rule C028 accepts root imports only). The records live in `vidbyte/lib/dataclasses/claude_code.py`, the enums in `vidbyte/lib/enums/claude_code.py`, every fixed value and wire key in `vidbyte/lib/constants/claude_code.py`, and `ClaudeCodeAgentError` in `vidbyte/lib/errors/base.py`. Process work goes through the canonical `CliArgv` and `CliRunner` in `vidbyte/lib/process/`, unchanged. Lint rule C012 exempts the `model` field because its vocabulary is Claude Code's, not the SDK catalog's. Tests live in `tests/features/claude_code_agent/`.

## Non-Goals

- Reimplementing Claude Code's loop, tools or permissions.
- Middleware, context managers, fallback chains or `AgentMessage` results (the Codex agent's surface); port them here only when a caller needs them.
- Pricing the run with Vidbyte's rate table: the cost is Claude Code's own report.
- Forking sessions, text-file attachments, and `vidbyte.sessions` persistence (the session id plus the workspace is the durable handle).

## File Index

- `__init__.py` - Re-exports the public surface: the agent, its settings, the four records, the two enums and the error.
- `agent.py` - `ClaudeCodeHarnessAgent`, the facade. Its narrated `arun` orders every step of a run and keeps the session id and running cost total. Open it to change the run lifecycle.
- `settings.py` - `ClaudeCodeHarnessAgentSettings`, validated at construction. Open it to add a setting.
- `command.py` - `ClaudeCodeCommand`: the argv, the stdin message, unsupported media types and the Windows command-line length. Open it to add a flag.
- `launcher.py` - `ClaudeCodeLauncher`: finds `claude` on `PATH` or `claude_bin` and refuses batch launchers.
- `workspace.py` - `ClaudeCodeWorkspace`: the agent's working folder and each run's private instructions file.
- `wire.py` - `ClaudeCodeWire`: reads the stream-json events into a result or the failure they mean. Open it when Claude Code's output changes.
- `failures.py` - `ClaudeCodeFailures`: builds each error with its scrubbed quote, likely cause and next step.

## Logs

- 2026-10-30 - Created for vidbyte-sdk 0.4.2 (suggest BYOK). The wire shape was observed live on Claude Code 2.1.314 before the parser was written: `--bare` ignores the OAuth login; a login failure has `is_error` true with `subtype` "success"; a schema violation has no `structured_output` key; `total_cost_usd` is cumulative after a resume while `model_usage_since_last_result` is per run; resume works only from the same folder; images work through stream-json input.
