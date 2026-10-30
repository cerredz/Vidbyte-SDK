# Design Doc: Claude Code Harness Agent (`vidbyte.agents.claude_code`)

**Status:** Implemented in this pull request
**Author:** Claude
**Created:** 2026-10-30
**Last Updated:** 2026-10-30

---

## 1. Overview

`vidbyte.agents.codex.CodexHarnessAgent` lets a caller run turns on the Codex installed on the user's
machine, so OpenAI bills the user's own account. There is no equivalent for Anthropic users. This change
adds `vidbyte.agents.claude_code.ClaudeCodeHarnessAgent`: an agent object that **is** one Claude Code
conversation. Its first `arun` starts a Claude Code session in print mode, and every later `arun` on the
same object resumes that session. Each turn runs the user's own `claude` executable, under the user's own
Claude login or API key, so Anthropic bills the user directly.

The first consumer is vidbyte-cli's `agents suggest` (CLI 0.3.4), which becomes a bring-your-own-key agent:
every generator, critic and extra-compute turn runs on the user's Codex or Claude Code, and Vidbyte charges
1 cent per requested suggestion (`runtime.suggestion@2`). The CLI's runtimes, which today refuse every host
but Codex, can reuse the same primitive later, so it is built as a general SDK agent and not as a
suggest-only adapter.

The public names and fields are fixed by the cross-repo contract
(`.runs/suggest-byok-2026-10-29/contract.md` §2, outside this repository). This document records what was
observed on the real Claude Code before any parser was written, and the choices made from it.

---

## 2. Goals & Non-Goals

### Goals

- `ClaudeCodeHarnessAgent(settings).arun(ClaudeCodeRunInput(prompt, images))` returns a validated
  `ClaudeCodeRunResult` with the structured output, the final text, the session id, per-run token usage,
  the per-run cost Claude Code reports, and the model that answered.
- The agent object is the thread: the first run mints a session id (`--session-id <uuid4>`), later runs
  resume it (`--resume <id>`), and runs on one object never overlap.
- The spawned Claude Code runs none of the user's hooks, plugins, MCP servers, skills, slash commands,
  CLAUDE.md files or auto-memory, and no built-in tool unless the caller names it.
- Images reach Claude as base64 content blocks.
- Every failure is one `ClaudeCodeAgentError` with a closed `ClaudeCodeFailureKind` and a message that says
  what happened and what the user does next. No credential is ever printed, logged or put in an error.
- Fully testable offline with a fake `claude` executable on a temporary `PATH`.

### Non-Goals

- Reimplementing Claude Code's loop, tools or permission system. Claude Code owns them.
- The Vidbyte middleware, context-manager, fallback-chain and `AgentMessage` surface of `CodexHarnessAgent`.
  The contract pins a smaller record-in, record-out API, which is what the suggestion agent and the
  runtimes need. Those Codex features can be ported later behind the same object if a caller needs them.
- Pricing Claude Code usage against Vidbyte's own rate table. The cost is Claude Code's own report and is
  informational: the user's Anthropic account pays it.
- Forking sessions. Claude Code supports `--fork-session`, but no caller needs it yet.
- Text-file attachments. Inlining a text file into the prompt is the caller's job (contract §2).

---

## 3. Background & Context

- `CodexHarnessAgent` (`vidbyte/agents/codex/`) wraps the `openai-codex` app-server SDK. Claude Code has no
  Python SDK dependency in this package, and the Claude Agent SDK would add a Node runtime dependency, so
  this agent drives the `claude` executable directly, as the native harness threads
  (`vidbyte/harnesses/native/{grok,opencode,muse}`) drive their vendors' executables.
- `vidbyte/lib/process/` already owns the canonical way to start a vendor CLI: `CliArgv` (argv from flag
  records, values joined so none can become a flag), `CliRunner` (time bound, output caps, stdin pipe that
  is closed after the text, no inherited stdin, whole-tree stop on timeout and cancellation, Windows `PATH`
  lookup that skips the current folder). This agent uses those helpers unchanged (AGENTS.md principle 5).
- vidbyte-cli lint rule C028 (`sdk-public-surface-only`, blocking, baseline 9) rejects any new import of a
  module below `vidbyte`, and any name missing from `vidbyte.__all__`. The CLI therefore needs every name in
  the contract on the **root** surface, so they are exported from `vidbyte` (and listed in
  `contracts/sdk-public-api.json`) as well as from `vidbyte.agents.claude_code`.

---

## 4. Observed wire shape (Claude Code 2.1.314, Windows 11, 2026-10-30)

Eight live invocations were made with the `haiku` alias (`claude-haiku-5-5`) from an empty temporary
folder, with `ANTHROPIC_API_KEY`, the other provider keys and the parent session's coupling variables
removed from the child's environment, so Claude Code used this machine's Claude login. Six reached the
model (total cost under $0.002). The raw outputs were kept outside the repository.

### 4.1 `--output-format json` (one object on stdout)

Keys of the result object: `type` (`"result"`), `subtype`, `is_error`, `result`, `structured_output` (only
when `--json-schema` succeeded), `session_id`, `usage`, `modelUsage`, `total_cost_usd`, `num_turns`,
`stop_reason`, `terminal_reason`, `duration_ms`, `duration_api_ms`, `api_error_status`,
`permission_denials`, `fast_mode_state`, `fast_mode_disabled_reason`, `first_content_frame_ms`,
`queued_turn_count`, `result_index`, `safety_stops`, `subagent_stats`, `time_to_request_ms`, `ttft_ms`,
`ttft_stream_ms`, `uuid`.

- **There is no top-level model field.** The model appears only as the key of `modelUsage`
  (`{"claude-haiku-5-5": {"inputTokens", "outputTokens", "cacheReadInputTokens",
  "cacheCreationInputTokens", "costUSD", "thinkingTokens", ...}}`).
- With `--json-schema`, a valid answer is the parsed object in `structured_output`, `result` is the same
  object as JSON text, `stop_reason` is `"tool_use"` and `num_turns` is 2 (structured output is a tool
  call named `StructuredOutput`).
- `usage` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, plus
  `output_tokens_details`, `cache_creation`, `iterations`, `service_tier`, ...) is **this process's run
  only**, summed over the run's turns (`iterations` holds only the last turn).
- **`total_cost_usd` and `modelUsage` are cumulative over the whole session after a resume.** A resumed
  run reported `total_cost_usd` 0.00033846 = the first run's 0.0002519 + its own 0.0000866 (checked against
  the per-token rates), while its `usage` held only its own tokens.

### 4.2 `--output-format stream-json --verbose` (one JSON object per line)

Events seen: `system/init`, `system/thinking_tokens`, `assistant` (with `message.model` and
`message.content` blocks: `thinking`, `text`, `tool_use`), `user` (the `StructuredOutput` tool result),
`rate_limit_event`, and a final `result` event with every key of §4.1 **plus
`model_usage_since_last_result`**, the per-model usage and `costUSD` of this run alone. The `init` event
carries `session_id`, `model`, `cwd`, `tools`, `mcp_servers`, `plugins`, `skills`, `slash_commands`,
`agents`, `apiKeySource`, `permissionMode`, `claude_code_version` and, when auto-memory is on,
`memory_paths`.

### 4.3 Resume

`--resume <id>` from **the same working folder** continued the conversation (a codeword given in run 1 came
back in run 2) and reported the same `session_id`. Transcripts live in
`~/.claude/projects/<folder key>/<session id>.jsonl`, keyed by the working folder, and an id unknown in the
current folder fails with exit 1, empty stdout and stderr `No conversation found with session ID: <id>`.
The agent therefore keeps one working folder for its whole life.

### 4.4 Authentication and `--bare`

`--bare` reads only `ANTHROPIC_API_KEY` or an `apiKeyHelper` (its own help says OAuth and the keychain are
never read). With no key, the run failed in 0.6 s with exit 1 and:

```json
{"type": "result", "subtype": "success", "is_error": true, "result": "Not logged in · Please run /login",
 "terminal_reason": "api_error", "api_error_status": null, "total_cost_usd": 0, "modelUsage": {}}
```

So `--bare` would break every user who signed in with a Claude subscription, and is **not used**. This
object is also the not-authenticated shape: `is_error` is true while `subtype` still says `"success"`, so
the parser reads `is_error`, never `subtype`.

### 4.5 Isolation from the user's customizations

This machine's user settings register 21 hooks (SessionStart, UserPromptSubmit, Stop, ... that report to
external dashboards) and one user MCP server. A run with
`--setting-sources "" --strict-mcp-config --disable-slash-commands`, `--include-hook-events` and one harmless
`echo {}` hook passed through `--settings` as a positive control showed:

- only the two control hook events (SessionStart, UserPromptSubmit), none of the user's hooks;
- `init.tools: []`, `init.mcp_servers: []`, `init.skills: []`, `init.slash_commands: []`;
- `init.plugins`: only Claude Code's four built-in plugins (`...@builtin`);
- `init.apiKeySource: "none"` (OAuth login in use, as wanted);
- an independent trace: the user's hook logger (`~/.litmus/turns/`) wrote no file during the eight
  invocations, although it writes one per prompt in normal sessions.

The same run with `--safe-mode` added fired **no** hooks at all (not even the `--settings` control), dropped
`init.memory_paths` (auto-memory off), and used 650 input tokens against 651 without it, so neither run
loaded the user's 2.4 KB `~/.claude/CLAUDE.md` (it would add roughly 500 tokens). The remaining ~600-token
floor is Claude Code's own built-in context.

**Chosen:** `--safe-mode --setting-sources "" --strict-mcp-config --disable-slash-commands`. Safe mode is the
documented switch for "all customizations (CLAUDE.md, skills, installed plugins, hooks, MCP servers, custom
commands and agents, output styles, ...) disabled" with "auth, model selection, built-in tools ... working
normally", and it also covers a caller-supplied workspace whose project CLAUDE.md or auto-memory the plain
flags were not observed to exclude. The three explicit flags stay as defence in depth, so isolation never
rests on one flag. A Claude Code too old to know one of these flags fails loudly (§6.6), never silently.

### 4.6 Tools

`--tools ""` gave `init.tools: []`; with `--json-schema` it gave `["StructuredOutput"]` only, so structured
output works with every built-in tool disabled.

### 4.7 Images

`--input-format stream-json` with one stdin line
`{"type": "user", "message": {"role": "user", "content": [{"type": "text", ...}, {"type": "image",
"source": {"type": "base64", "media_type": "image/png", "data": "<base64>"}}]}}` (a 32x32 red PNG) and
`--json-schema` answered `{"answer": "red"}` through `StructuredOutput`. Images are supported, so `arun`
never raises the contract's fallback "images unsupported" error; it raises `UNSUPPORTED_INPUT` only for a
media type the Messages API does not accept.

### 4.8 Schema violation

An unsatisfiable schema (`minimum 5`, `maximum 3`) ran four turns and ended with exit 0, `is_error: false`,
`subtype: "success"`, `stop_reason: "end_turn"`, prose in `result`, and **no `structured_output` key**.
A schema violation is therefore detected only by the missing (or non-object) `structured_output`.

### 4.9 Long instructions and the command line

vidbyte-cli's critic prompt (`critic.md`) is 51,918 bytes, above Windows' 32,767-character command-line
limit, so the instructions cannot travel in `--system-prompt`. They go through `--system-prompt-file`,
which `--help` does not list but the binary defines ("Read system prompt from a file"; it is also named in
`--bare`'s help). The prompt and images go through stdin, so only the JSON schema is free text on argv; a
command line that would still pass the Windows limit is refused before launch (§6.6).

### 4.10 End-to-end check of the shipped command line

The opt-in live test (`tests/features/claude_code_agent/test_claude_code_live.py`, two `haiku` turns through
`ClaudeCodeHarnessAgent` itself, `ANTHROPIC_API_KEY` removed) passed on 2.1.314. That confirms the parts the
probes did not run directly: `--system-prompt-file`, the joined `--tools=` and `--setting-sources=` (the
wire's `init` check would have refused any tool besides `StructuredOutput`), `--safe-mode` with the OAuth
login, `--json-schema` over stream-json, resume from the agent's own folder (the second turn recalled the
codeword), and a per-run cost below the session total on the resumed turn. The session transcript Claude
Code saved for that run has no hook entries. Its saved API request bodies contain neither a distinctive
word from the user's `~/.claude/CLAUDE.md` nor the user's hook commands, so neither reached the model.

---

## 5. High-Level Design

```
ClaudeCodeHarnessAgent.arun(ClaudeCodeRunInput)
  ├─ ClaudeCodeCommand.refuse_unsupported(input)          media types, before any launch
  ├─ ClaudeCodeLauncher.resolve(settings)                 claude_bin or PATH, batch refused
  ├─ ClaudeCodeWorkspace.folder()                         caller's folder or one temp folder per agent
  ├─ ClaudeCodeWorkspace.instructions_file(instructions)  private temp file, removed after the run
  ├─ ClaudeCodeCommand.argv(...) / .stdin(...)            flags joined, prompt+images as one stdin line
  ├─ CliRunner().run(CliInvocation)                       vidbyte/lib/process (timeout, caps, tree stop)
  └─ ClaudeCodeWire.read(outcome, ...)                    classify failure or build ClaudeCodeRunResult
```

Records live in `vidbyte/lib/dataclasses/claude_code.py`, enums in `vidbyte/lib/enums/claude_code.py`,
fixed values in `vidbyte/lib/constants/claude_code.py`, the error in `vidbyte/lib/errors/base.py`, and the
settings object in the agent's own `settings.py` (AGENTS.md placement exception 1). `ClaudeCodeFailures`
builds every error with a scrubbed message.

---

## 6. Detailed Design

### 6.1 Public API (contract §2 plus optional additions)

```python
ClaudeCodeHarnessAgentSettings(
    name: str,
    instructions: str,                      # non-blank; sent through --system-prompt-file
    model: str | None = None,               # None: Claude Code's built-in default for the account
    output_schema: Mapping | None = None,   # JSON Schema object -> --json-schema
    effort: ClaudeCodeEffort | str | None = None,   # low|medium|high|xhigh|max -> --effort
    allowed_tools: tuple[str, ...] = (),    # () -> --tools "" ; names -> --tools and --allowed-tools
    workspace: str | Path | None = None,    # existing folder; None -> one fresh empty temp folder
    claude_bin: str | Path | None = None,   # None -> `claude` on PATH
    timeout_seconds: float = 600.0,
    session_id: str | None = None,          # OPTIONAL ADDITION: resume a saved session (needs workspace)
)
ClaudeCodeImage(media_type: str, data_base64: str)
ClaudeCodeRunInput(prompt: str, images: tuple[ClaudeCodeImage, ...] = ())
ClaudeCodeUsage(input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens)
ClaudeCodeRunResult(
    output: Mapping | None, text: str, session_id: str, usage: ClaudeCodeUsage,
    cost_usd: float | None, model: str,
    num_turns: int = 0, duration_ms: int = 0, session_cost_usd: float | None = None,  # OPTIONAL ADDITIONS
)
ClaudeCodeAgentError(AgentExecutionError)   # .kind, .session_id, .exit_code, .likely_cause, .next_step
ClaudeCodeFailureKind: NOT_INSTALLED, NOT_AUTHENTICATED, TIMEOUT, EXIT_NONZERO, SCHEMA_VIOLATION,
                       UNSUPPORTED_INPUT, MALFORMED_OUTPUT
ClaudeCodeEffort: LOW, MEDIUM, HIGH, XHIGH, MAX
```

`ClaudeCodeAgentError` derives from `AgentExecutionError`, which derives from `VidbyteSdkError`, so it is a
`VidbyteSdkError` as the contract requires and is caught by the same handlers as `CodexAgentError` and
`NativeThreadError`. The agent also has `session_id` (None until the first run succeeds), `workspace`,
`run()` (the synchronous twin) and `close()` (removes the temp folder the agent made).

`cost_usd` is **this run's** cost: the sum of `model_usage_since_last_result[*].costUSD`. When an older
Claude Code omits that field, it is `total_cost_usd` minus the session total the agent saw last, and None
when the agent has no such baseline (its first run resumed a saved `session_id`). `session_cost_usd` is
Claude Code's cumulative `total_cost_usd`. Reporting the cumulative figure as `cost_usd` would make a
caller that sums per-run costs (as the suggestion agent's usage summary does) count earlier turns again.

`model` is the model with the most output tokens in this run's `model_usage_since_last_result`, else the
last assistant message's `message.model`, else `init.model`.

### 6.2 Command line

Every option is one `--flag=value` element (`CliOptionStyle.JOINED`), so no value can become a flag and no
argv element is empty (`CliInvocation` refuses empty elements; commander parses `--tools=` exactly as
`--tools ""`). Order: `--print`, `--input-format=stream-json`, `--output-format=stream-json`, `--verbose`,
`--safe-mode`, `--setting-sources=`, `--strict-mcp-config`, `--disable-slash-commands`,
`--system-prompt-file=<private temp file>`, `--tools=<names or empty>`, `--allowed-tools=<names>` (only
when names are given, so the named tools run without a permission prompt nobody can answer),
`--model=`, `--effort=`, `--json-schema=<compact JSON>`, then `--session-id=<new uuid4>` or
`--resume=<id>`.

### 6.3 Standard input

One stream-json line, then EOF (`CliRunner` closes the pipe): a user message whose content is each image
block (in the order given) followed by one text block. Anthropic recommends images before the text that
refers to them.

### 6.4 Environment

The child inherits the caller's environment (`CliRunner`), so the user's own `ANTHROPIC_API_KEY`,
`CLAUDE_CODE_OAUTH_TOKEN`, Bedrock/Vertex settings and `CLAUDE_CONFIG_DIR` keep working: that is the
bring-your-own-key path. The variables a parent Claude Code session sets for its own children are removed
(`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`,
`CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ATTENDED`,
`CLAUDE_CODE_EXECPATH`, `CLAUDE_EFFORT`, `CLAUDE_PID`), because the CLI is often run from inside a Claude
Code session: inherited, they would tie the thread to the parent's messaging socket and run it at the
parent's effort level. The SDK never changes `os.environ`.

### 6.5 Workspace and instructions file

`workspace=None` creates one empty folder (`tempfile.mkdtemp`) on the first run and reuses it, because a
resume only finds its transcript from the same folder (§4.3). The instructions file is written to a
separate private temp folder for each run and removed in a `finally`, so the workspace stays exactly as the
caller left it (the probes left every working folder empty). `close()` removes the agent's own temp folder;
after it, the next run would start a new folder and therefore cannot resume, so the agent forgets its
session id.

### 6.6 Failure classification (first match wins)

| Condition | Kind |
|---|---|
| a media type outside png/jpeg/gif/webp; a Windows command line over 32,767 characters | `UNSUPPORTED_INPUT` (before launch) |
| no `claude` on PATH; `claude_bin` missing or not runnable; a `.cmd`/`.bat` launcher on Windows | `NOT_INSTALLED` |
| the run passed `timeout_seconds` (the whole process tree is stopped) | `TIMEOUT` |
| stdout passed the output cap | `MALFORMED_OUTPUT` |
| a result with `is_error` (or a failed exit) whose text names a login/API-key problem (`Not logged in`, `/login`, `Invalid API key`, `authentication_error`, `OAuth token`), or `api_error_status` 401/403 | `NOT_AUTHENTICATED` |
| any other `is_error` result, or a non-zero exit (unknown session, unknown option, API error) | `EXIT_NONZERO` |
| no `result` event, no session id, a session id other than the one requested, or `init` showing a tool or MCP server the settings did not allow | `MALFORMED_OUTPUT` |
| `output_schema` set but `structured_output` missing or not an object | `SCHEMA_VIOLATION` |

Messages say what happened, the likely cause and the next step (for example `claude auth login`,
`claude update`, raising `timeout_seconds`), and quote at most 500 characters of Claude Code's own text,
scrubbed: values of credential variables present in the environment are replaced first, then the shared
`HarnessRedactor` assignment scrub runs, then `sk-ant-` style tokens are masked. An unknown-option error
says the installed Claude Code is older than the flags this SDK needs.

### 6.7 Concurrency and cancellation

One `asyncio.Semaphore(1)` per agent (the SDK bans `asyncio.Lock`) spans the whole run, because the session
id and cost baseline are written after the process exits. Distinct agents run concurrently. Cancellation
propagates unchanged after `CliRunner` stops the process tree, and the instructions file is still removed.

---

## 7. Alternatives considered

- **`--bare`**: rejected; it ignores the OAuth login (§4.4).
- **`--output-format json`**: simpler, but it has no per-run cost or model and its cost is cumulative after
  a resume (§4.1), and it cannot be paired with stream-json image input in one code path.
- **Instructions in `--system-prompt`**: rejected; 52 KB instructions overflow the Windows command line.
- **Prompt as a positional argument**: same limit, and the prompt would be visible in process listings.
- **Using the Claude Agent SDK**: adds a Node dependency and the `@anthropic-ai/claude-agent-sdk` package,
  for what three flags and one stdin line already do.
- **Reusing `hostkit.NativeLauncher` and `NativeErrorFactory`**: both are typed to `NativeThreadError` and
  the native harness vocabulary; the contract fixes a separate error type, so this agent has a small
  launcher of its own that applies the same rules (PATH only, batch launchers refused).

---

## 8. Testing

Offline (`tests/features/claude_code_agent/`): a fake `claude` (`fake_claude.py`, run as `claude.exe` through
pip's console-script launcher on Windows and as a script on POSIX, on a `PATH` that holds only the test's
folder) records argv, cwd, stdin, the instructions file text and the inherited variable names, keeps a
session store keyed by working folder, and replays the observed shapes of §4. Tests cover structured
output, resume on the second `arun`, every `ClaudeCodeFailureKind`, the timeout and tree stop, `--tools=`
with no tools, the isolation flags and removed variables, images, cost and model selection, credential
scrubbing, settings validation, and the public surface. A live test runs two turns on the real Claude Code
only when `VIDBYTE_LIVE_CLAUDE_CODE=1`.

---

## 9. Changes outside the feature

- `lint/rules/c012_provider_model_registry_validation.py`: one `_EXEMPT_FIELDS` entry for
  `ClaudeCodeHarnessAgentSettings.model`. That is the rule's documented path for a field whose vocabulary
  is owned outside the SDK catalog, as the Codex CLI model fields are. Claude Code resolves its own aliases
  and third-party provider ids.
- `tests/features/harness_threads/test_harness_threads_surface.py`: the INV-23 probe asserted that every
  name added to `vidbyte.__all__` since the merge base is a native-harness name. That was #1036's branch
  guard: vacuous on `main`, and it fails every later branch that adds a root export, as #1209 found for the
  tools guard in the same file. The probe keeps its durable checks: `import vidbyte` starts no process,
  leaves `vidbyte.harnesses.native` unloaded, and keeps main's root names in main's order. C016 and
  `contracts/sdk-public-api.json` govern additions.

---

## 10. Rollout

Ships in vidbyte-sdk 0.4.2 (the release pull request bumps the version). vidbyte-cli 0.3.4 imports the
names from the root `vidbyte` package lazily and fails free on an older SDK.
