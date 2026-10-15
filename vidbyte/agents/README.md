# Agents

The Vidbyte SDK uses agents as the executable actor abstraction for AI workflows.
An agent combines a system prompt, provider/model configuration, optional
tools, structured context, tracing, runtime configuration, and handoff behavior.

## Role In The SDK

`vidbyte.agents` is the layer most application code touches first. It exposes
`Agent` / `BaseAgent`, `AgentInput`, agent messages, local registries, handoff
agents, and swappable runtime implementations. Agents normalize input, build a
context window, infer the runner from provider/model configuration, execute tools when the
runtime requests them, and return an `AgentMessage`.

For open-ended team work, `vidbyte.agents.multi` exposes `MultiAgent`, a
`BaseAgent`-compatible facade whose manager plans against a shared immutable
ledger snapshot, delegates one worker per round, and can replan after failure.

## Design Philosophy

Agents are explicit composition objects rather than hidden global state. The SDK
keeps the prompt, tools, context manager, middleware, trace settings, and runner
inference visible at construction time so developers can reason about what the model sees
and what local capabilities it can call.

The default linear runtime is the compatibility path for middleware and continual
trace artifacts. Non-linear runtimes such as search and actor-model execution are
separate runtime choices with narrower compatibility rules.

## Usage

```python
from vidbyte import Agent, tool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="analyst",
    system_prompt="Answer directly and cite uncertainty.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
)

reply = await agent.arun("Summarize user 42.")
print(reply.content)
```

For a cooperative, bounded wait, add the built-in to the agent that should
pause and choose its developer-owned maximum:

```python
from vidbyte.tools.builtins import PauseAgentTool

agent = Agent(
    name="paced-agent",
    system_prompt="Use the pause tool when pacing is part of the workflow.",
    tools=[PauseAgentTool(max_seconds=30)],
)

await agent.pause(2)  # Direct async API; does not block unrelated tasks.
```

The model-facing `pause_agent` tool pauses the agent it is attached to. A parent
agent can reach a target agent through the existing `target_agent.as_tool()`
composition path; the tool does not accept an arbitrary agent id. This is a
timed cooperative wait, not durable pause/resume state or external run
cancellation.

Use `AgentInput` when a single run needs additional metadata or context items:

```python
from vidbyte import AgentInput
from vidbyte.context.primitives import TextContextItem

reply = await agent.arun(
    AgentInput(
        "Review this change.",
        context_items=(TextContextItem(title="Reviewer note", content="Focus on API compatibility."),),
    )
)
```

## Coding Agent

`CodingAgent` is a `BaseAgent` that takes every `BaseAgent` keyword unchanged plus a required `root_dir`, and starts with seven tools over that folder: `bash`, `read_lines`, `write_text`, `replace_text`, `glob`, `grep`, and one web-fetch tool. By default it also shows the folder's `AGENTS.md`, a short block of environment facts, and `MAP.md` to the model, and keeps its own progress notes file.

```python
from vidbyte import CodingAgent

agent = CodingAgent(
    name="coder",
    system_prompt="Make the smallest change that fixes the task.",
    root_dir="my-project",            # an existing folder, resolved once
    firecrawl_api_key="fc-your-key",  # optional; picks the web-fetch provider
    load_agents=True,                 # default; shows my-project/AGENTS.md to the model
    load_environment=True,            # default; shows the OS, date, shell, and tools to the model
    load_map=True,                    # default; shows my-project/MAP.md to the model
    setup_commands=["uv sync"],       # optional; run once in my-project before the first turn
    progress_notes=True,              # default; keeps my-project/.vidbyte/coding-agent/progress.md
    provider="openai",
    model_name="gpt-4.1",
)
```

The key you pass picks the web-fetch tool: `firecrawl_api_key`, `browserbase_api_key`, `parallel_api_key`, or `tavily_api_key`, at most one; with none, it is `direct_http_fetch`. Keys are never read from the environment. On a `CodingAgent`, a keyed fetch returns each page's text in `output`, after the provider's summary.

`readonly_paths=["tests/**"]` lets the model read matching files but never edit them with `write_text` or `replace_text`, so "make the tests pass" cannot be met by editing the tests. Each entry is an `fnmatch` glob relative to `root_dir`, written with `/`; `*` also matches `/`, so `tests/*` and `tests/**` both cover everything under `tests/`. The path is resolved as the tool resolves it (case-insensitively on Windows), and a denied call names the file and the pattern. `bash` and your own tools are not checked.

Pass `verify_command` (for example `"python -m pytest -q"`) and the run may not finish until that command passes. At every finish attempt, a plain answer or an `isDone` call that the output contracts accept, the agent runs `bash -c <command>` once in `root_dir`, with the same bash, 600-second limit, and 50,000-byte output cap as the `bash` tool. Exit code 0 ends the run as usual. Otherwise the model reads `Not done yet: the verification command ... failed (exit code N)` and the command's output, and keeps working. After `max_verify_attempts` failures (default 3) the run ends without raising: `content` is the model's last answer and `stop_reason` is `contract_unsatisfied`. `metadata["verify_command"]` reports `passed`, `attempts`, and `last_exit_code`. The command is yours, not the model's: it is not sanitized, it runs even under a read-only policy, and the model's own `bash` calls never trigger it. Without bash, a `CodingAgent` with `verify_command` fails at construction.

The constructor gathers its own arguments into one `CodingAgentSettings` (`vidbyte/lib/dataclasses/coding.py`), which checks the root folder, the keys, the verification settings, the caller's tools, the policy, the read-only patterns, and the rewrite limit when it is created, so a bad argument fails before `BaseAgent` builds anything. The seven tools come from `CodingAgentTools` (`vidbyte/tools/toolsets/coding.py`), a `Tools` catalog with `authenticate_tools(settings)`, which gives the one key to its fetch provider, and `get_tools(root_dir, fetch_tool)`, which returns the seven in order. With `verify_command` set, it appends one `VerifyCommandMiddleware` (`vidbyte/middleware/builtins/verify_command.py`) after your own `middleware`; the runtime calls its `review_finish` hook at both finish points, so `CodingAgent` still overrides no `BaseAgent` method.

When it is built, the agent reads `<root_dir>/AGENTS.md`, or a case variant such as `agents.md` when that exact name is absent, and places the text right after the system prompt and before your message, so the model follows the rules the repository already wrote down. Parent folders are never searched. The file is read once: later edits are seen only by a new agent, and a later change of working directory changes nothing. At most 32,768 bytes are shown, cut at a whole character; a longer file ends with a line that gives the cut and the `read_lines` call that reads the rest. A missing or blank file adds nothing, while a file that is there but cannot be read, such as a folder named `AGENTS.md`, fails construction with a `ConfigurationError` naming its path. Pass `load_agents=False` to turn this off; `load_agents` must be a real `bool`.

The agent also shows an environment section after `AGENTS.md`: the OS family (Windows, macOS, or Linux) and version, the CPU, today's date and time zone, the root folder, the manifests, lockfiles, and build files in it with the languages and package managers they imply, the dependency names its `pyproject.toml`, `requirements.txt`, `package.json`, and `Cargo.toml` declare, which dependency folders (`.venv`, `node_modules`) are already installed, and whether it is in a git repository and on which branch. It says which bash the `bash` tool runs; on Windows that is Git Bash, so the section tells the model to write POSIX commands, not PowerShell. One `bash -c` probe, run with that same bash in the root folder, lists the system package managers (such as `brew`, `apt-get`, or `winget`) and the common tools bash finds on its own `PATH` (git, python, node, cargo, and so on) with the first line of each version. The probe runs once per process for a given bash and `PATH`, with a 15-second limit. No bash, a timeout, a failing probe, or a malformed manifest never raises: the section says what failed and keeps every other fact. No environment-variable value, user name, or host name is shown. The loader only gathers these facts; the section is an `EnvironmentContextItem` (`vidbyte/context/primitives/documents.py`), which writes every line the model reads, and `agent.context_manager.get_by_id("coding:environment")` returns it with each fact as a typed field. Pass `load_environment=False` to turn this off; it must be a real `bool`.

The agent reads `<root_dir>/MAP.md` (or `map.md`) the same way, with the same rules and cap, and shows it right after the environment section. `MAP.md` is a convention for repositories that a `CodingAgent` works in: a short, human-written map of where things live, such as the main folders, the entry points, and where new code goes, so the model can open the right file instead of spending its first turns on `ls` and `find`. Other names, such as `REPO_MAP.md`, are not read. Pass `load_map=False` to turn it off; `load_map` must be a real `bool`.

`setup_commands`, a list of command strings such as `["uv sync", "npm ci"]`, run once while the agent is built, in order, each as `bash -c <command>` in `root_dir`, so the environment is ready before the first turn. Construction waits for them, up to the bash tool's 600-second limit each. The first command that fails, times out, or cannot start stops the run, and the rest are not run. Nothing raises: the model gets a short note after `AGENTS.md`, the environment section, and `MAP.md`, and before the progress notes, with one line per command and, for the failed one, the last 30 lines of its output (at most 8,192 bytes). Without bash, nothing runs and the note says so. A bare string such as `setup_commands="uv sync"` fails with a `ConfigurationError`. The commands are not run again by `run()`, `fork()`, or `restore()`.

The agent also keeps its own notes file, `<root_dir>/.vidbyte/coding-agent/progress.md`, so a second run picks up where the first stopped. When it is built, the agent creates the file from a short template (Done, Next, Decisions) if it is missing, and creates `.vidbyte/coding-agent/.gitignore` holding `*` so git never sees that folder. Your own `.gitignore`, `.vidbyte/` itself, and other tools' files there (such as vidbyte-cli's task board) are never touched. Neither file is ever overwritten. The notes, capped at 32,768 bytes, are shown last among the sections, after a short instruction to read them first and to update them with `write_text` or `replace_text` after each meaningful step. They are read once, when the agent is built. If the root folder cannot be written, for example a read-only checkout, the agent gets no notes section and construction still succeeds. Pass `progress_notes=False` to turn this off; nothing is then created. `progress_notes` must be a real `bool`.

`CodingContextWindow` (`vidbyte/agents/coding_context/`) places the text and owns the order of everything a `CodingAgent` adds after the system prompt: `AGENTS.md`, then the environment context as that feature lands, then the repository map (`MAP.md`), then the setup-command results, then the progress notes, then the content of your own `context_manager`. It never changes your manager: when a section is loaded, the agent gets a new manager with your content after the sections. Adding a section takes three steps, described in that folder's README:

1. Write one loader class in its own file in `vidbyte/agents/coding_context/`, with `load(settings) -> CodingContextSectionText | None`.
2. Return the section's reserved `CodingContextSection` member (`ENVIRONMENT`, `REPO_MAP`, or `SETUP_RESULTS`); the enum's order is the render order.
3. Add `<Loader>.load(settings)` to the `sections` tuple in `CodingAgent.__init__`.

- The default policy allows every tool, including tools you add; pass `permission_policy=PermissionPolicy()` for a read-only agent.
- `write_text` refuses to replace an existing file with more than `max_rewrite_lines` lines (300 by default), so the model edits big files with `replace_text` instead of rewriting them from memory. New files and `replace_text` are not limited, and the `write_text` description tells the model the limit. Pass `max_rewrite_lines=None` to turn it off. The limit is `FileSystemToolConfig.max_overwrite_lines` on the tool itself.
- `bash` is not confined to `root_dir`, and it runs unsandboxed with the inherited environment. The SDK undoes nothing a tool did, so keep the folder under version control.
- A background process must redirect both its standard output and its standard error, or the call waits for the time limit and the process is killed.
- Each command is limited to 600 seconds and 50,000 bytes of output (the first bytes are kept). `ToolSettings.tool_timeout_seconds` and `ToolSettings.result_max_chars` remain the agent-wide controls.
- `fork()` returns a plain `BaseAgent` with the same middleware and the `AGENTS.md` section, so a fork verifies too. `CodingAgent.restore(state)` raises `TypeError` (no `root_dir`), so restore with `BaseAgent.restore(state, tools=CodingAgent(...).tools.all(), middleware=agent.middleware)`; exported state holds no middleware, so without `middleware=` the restored agent neither verifies nor keeps `readonly_paths`. Restore does not bring the section back either.
- When `AGENTS.md` is loaded and you pass `context_manager`, tools bound to your manager object, such as `ContextWindowFactory` tools, write to a manager the agent no longer renders.
- On Windows, `bash` needs Git for Windows, and a timed-out or cancelled command is not stopped (only Git's launcher is killed), so it may keep running after the call returns.

## Model Fallback

An agent can declare an ordered chain of backup models. Array index sets precedence:
index 0 is tried first, and the runtime advances one step each time a model call
fails with a provider-level error.

```python
from vidbyte import Agent

agent = Agent(
    name="analyst",
    system_prompt="Answer directly.",
    provider="openai",
    model_name="gpt-5.2",
    fallback=[
        "gpt-5-mini",                 # bare name inherits provider, api_key, temperature
        "anthropic/claude-sonnet-5",  # provider-prefixed, overrides the provider
    ],
)
```

Entries may also be `FallbackModel` objects when a backup needs its own credentials,
and the whole chain can be passed as a settings object alongside `AgentLoopSettings`:

```python
from vidbyte.agents import FallbackModel
from vidbyte.agents.settings import AgentFallbackSettings

agent = Agent(
    name="analyst",
    system_prompt="Answer directly.",
    provider="openai",
    model_name="gpt-5.2",
    fallback=AgentFallbackSettings(
        models=[FallbackModel(provider="anthropic", model="claude-sonnet-5", api_key=ANTHROPIC_KEY)],
        enabled=True,
    ),
)
```

Rules worth knowing:

- **Only provider-level failures trigger a switch** — `ProviderRequestError`,
  `ProviderResponseError`, `ProviderConfigurationError`, `ProviderSelectionError`,
  `UnsupportedProviderError`, and `TimeoutError`. Tool errors, permission denials,
  and cancellation propagate untouched. Override with `AgentFallbackSettings(fallback_on=...)`.
- **Retries happen first.** Retry middleware exhausts its budget on the current model
  before the chain advances, and the chain does not reset that budget.
- **Same-wire-format switches keep the transcript.** OpenAI, DeepSeek, xAI, and
  OpenRouter share one payload shape, so an in-flight run carries its tool history over
  intact. Switching across wire formats (OpenAI ↔ Anthropic ↔ Gemini) resets the
  transcript and restarts from the original prompt, because the accumulated messages are
  in the previous provider's shape. Tools already executed may run again in that case;
  the run reports `context_reset: True`.
- **Every switch is visible.** A run that fell back reports
  `AgentResult.metadata["fallback"]` with the ordered attempt log and final model, and
  emits an `agent.fallback` span. A clean run reports no `fallback` key at all.
- **The chain is per-run.** Falling back on one call never pins later calls to the backup.
- When every model fails, the agent raises `AllModelsFailedError` carrying every attempt
  and every error, chained from the first failure.
- Fallback requires the linear runtime and an agent with its own `provider`/`model_name`;
  both are rejected at construction otherwise. `fork()` inherits the chain, and
  `AgentForkSettings(fallback=...)` overrides it.

## Durable Sessions

Agents can opt into durable sessions without moving persistence into the agent constructor:

```python
from vidbyte import FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")
session = agent.persist(store=store)
reply = await agent.arun("Continue the investigation.")
print(agent.session is session)
```

`agent.persist(...)` delegates to `vidbyte.sessions.Session(agent, ...)`. Once bound, direct `agent.arun(...)` and `agent.run(...)` calls record checkpoints with the same policy as `session.arun(...)` and `session.run(...)`; `agent.session` returns the current session or `None`.

`MultiAgent` is intentionally excluded from durable sessions because its
orchestrator, transfer callbacks, worker factories, and live ledger cannot be
encoded by `RunState` without changing behavior on restore.

## Ledger-Driven Teams

```python
from vidbyte import AgentBinding, AgentTransfer, MultiAgent

team = MultiAgent(
    name="team",
    system_prompt="Own the goal, surface blockers, and finish with evidence.",
    orchestrator=manager_agent,
    agents=[
        AgentBinding(
            researcher_agent,
            transfer=AgentTransfer(report_validator=verify_research_report),
        )
    ],
)

reply = await team.arun("Investigate the incident and recommend a response.")
ledger = team.last_ledger
```

The default transfer sends deterministic JSON and treats non-blank worker text
as completed but unverified evidence. Use a report validator to mark evidence
verified. Use pipelines for fixed text flow and workflows for code-owned state
machines; use `MultiAgent` when the manager must own progress and recovery.

## Output Connectors

Send each finished reply to chat channels, email, issue trackers and code
hosts (including comments and update-in-place), docs workspaces, CI job
summaries, social-post drafts, CRM tasks, or any HTTPS webhook (optionally
signed) by passing connectors as `outputs=`:

```python
from vidbyte import Agent, GitHubIssueOutput, OutputDeliveryError, SlackOutput

agent = Agent(
    name="checkout-scout",
    system_prompt="Find the worst bug in the checkout flow.",
    provider="openai",
    model_name="gpt-4.1",
    output_schema=BugReport,  # a model with title and body fields
    outputs=[
        SlackOutput(),                                         # reads SLACK_WEBHOOK_URL
        GitHubIssueOutput(repo="acme/shop", labels=("bug",)),  # reads GITHUB_TOKEN
    ],
)
try:
    reply = agent.run("Scan checkout")
except OutputDeliveryError as err:
    reply = err.reply  # recorded already; err.failed lists what did not send
print(reply.metadata["deliveries"])
```

Delivery runs once per run, after the reply passes the output-schema check and
before queued follow-ups, with every connector sending at once. A blank reply
or a run stopped by a budget, guard, or middleware sends nothing. Forks never
deliver, but a user agent that carries its own outputs delivers on its own
runs even as a Jev specialist, an AggregateAgent proposer, or a pipeline
stage. See [`output/README.md`](output/README.md) for the delivery rules and
[`../lib/outputs/README.md`](../lib/outputs/README.md) for each provider's
credential and limits.

## Key Modules

- `base.py`: `BaseAgent`, inferred runner construction, tool binding, context assembly, trace setup, and runtime dispatch.
- `client.py`: namespace client used by `VidbyteSDK().agents`.
- `fallback.py`: `AgentFallback`, the ordered model chain and the transforms that route a run to the next model.
- `settings/fallback.py`: `AgentFallbackSettings`, the validated developer-facing chain configuration.
- `runtimes/`: linear, search, and actor-model runtime components.
- `handoff.py`: structured handoff generation from a completed agent run.
- `coding.py`: `CodingAgent`, a `BaseAgent` preloaded with bash, read, write, edit, glob, grep, and one web-fetch tool over one root folder; its checks live in `CodingAgentSettings` and its tools in `CodingAgentTools`.
- `coding_context/`: `CodingContextWindow` and one loader per section (`AgentsMdLoader`), which build the context a `CodingAgent` shows after its system prompt.
- `skills/`: `SkillLoader` and one resolver per source, the agent-agnostic loader that turns declarative skill entries into `SkillDocument`s for `JevAgent`'s skill preload and for any caller that imports `SkillLoader` from the package root.
- `multi/`: ledger-driven manager/worker orchestration and transfer controls.
- `output/`: the `OutputConnector` contract, reply shaping, and `OutputDispatcher`, which delivers each finished reply to the configured `outputs`.
- `types.py`: agent messages, input envelopes, cards, and specs.

## Related Layers

Agents compose with [`context`](../context/README.md), [`tools`](../tools/README.md),
[`middleware`](../middleware/README.md), [`providers`](../providers/README.md),
[`pipelines`](../pipelines/README.md), and [`trace`](../trace/README.md).
