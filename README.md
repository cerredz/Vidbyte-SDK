# Vidbyte SDK

[![PyPI version](https://img.shields.io/pypi/v/vidbyte-sdk.svg)](https://pypi.org/project/vidbyte-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/vidbyte-sdk.svg)](https://pypi.org/project/vidbyte-sdk/)
[![Publish to PyPI](https://github.com/cerredz/Vidbyte-SDK/actions/workflows/publish.yml/badge.svg)](https://github.com/cerredz/Vidbyte-SDK/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Vidbyte is an agent engineering platform for building, evaluating, instrumenting,
and distributing AI workflows. The Vidbyte SDK is the Python package surface for
that platform: it gives developers composable agents, tools, middleware, context
management, MCP server integration, prompts, evals, provider adapters, pipelines,
validated workflows, and tracing primitives.

This repository is intentionally focused on reusable SDK abstractions. Private
Vidbyte service logic, proprietary learning systems, hosted scoring, and database
access remain outside this package.

## What You Can Build

- Agent applications with explicit system prompts, provider/model configuration, tools, context, and trace behavior.
- Tool-using agents with local Python functions, MCP-backed tools, permission policies, and provider-native schemas.
- Runtime policies with deterministic middleware for rate limits, budgets, retries, audit logs, compaction, and safety checks.
- Durable agent sessions that checkpoint, resume, fork, batch fork, tag, export/import, and summarize usage across long-running work.
- MCP Studio servers that expose Vidbyte agents, tools, prompts, and pipelines to MCP-compatible clients.
- Local eval suites with reusable graders, concurrency controls, and run registries.
- Agent pipelines that compose specialized agents through sequential, parallel, conditional, and map-reduce topologies.
- Typed state-machine workflows with validation gates, conditional branches, cycles, retries, and declared jumps.
- Prompt libraries, context-window algorithms, and trace artifacts that make long-running agent work easier to inspect.

## Layer Guide

| Layer | Role |
|-------|------|
| [`vidbyte.agents`](vidbyte/agents/README.md) | Executable agent actors, runtimes, inferred runner selection, handoff, and agent registries |
| [`vidbyte.cli`](vidbyte/cli/README.md) | Unified console command for SDK developer surfaces, currently `vidbyte-sdk skills` |
| [`vidbyte.context`](vidbyte/context/README.md) | Structured context items, context windows, compaction, algorithms, and handoff models |
| [`vidbyte.evals`](vidbyte/evals/README.md) | Local eval cases, suites, runners, graders, registries, and result summaries |
| [`vidbyte.harnesses`](vidbyte/harnesses/README.md) | Namespace boundary for custom harness integrations |
| [`vidbyte.lib`](vidbyte/lib/README.md) | Shared dataclasses, enums, registries, errors, runners, config, and tracing contracts |
| [`vidbyte.mcp_server`](vidbyte/mcp_server/README.md) | Stdio MCP Studio server for exposing agents, tools, prompts, and pipelines |
| [`vidbyte.middleware`](vidbyte/middleware/README.md) | Deterministic runtime hooks and built-in policy, safety, retry, budget, and compaction middleware |
| [`vidbyte.paradigms`](vidbyte/paradigms/README.md) | Thin runnable paradigm harness scaffolding built from agents, tools, context, prompts, middleware, trace, pipelines, and evals |
| [`vidbyte.pipelines`](vidbyte/pipelines/README.md) | Multi-agent pipeline topologies with a string-in/string-out contract |
| [`vidbyte.prompts`](vidbyte/prompts/README.md) | Static prompt assets, enum-keyed lookup, direct imports, and prompt families |
| [`vidbyte.providers`](vidbyte/providers/README.md) | Provider adapter factories for text, image, video, audio, embeddings, and streaming |
| `vidbyte.sessions` | Durable checkpoint-DAG persistence, stores, scope, usage rollups, and portable bundles |
| `vidbyte.sources` | Artifact-to-context loaders for public documents, llms.txt, fetch/cache, hashing, and selection |
| [`vidbyte.shared`](vidbyte/shared/README.md) | Reserved shared namespace; currently no stable public symbols |
| [`vidbyte.tools`](vidbyte/tools/README.md) | Tool contracts, decorators, catalogs, execution, MCP bridges, and permissions |
| [`vidbyte.trace`](vidbyte/trace/README.md) | Trace facade, debug tracer, provider tracers, and continual trace artifacts |
| [`vidbyte.workflows`](vidbyte/workflows/README.md) | Typed state graphs with validate-before-commit stages, branches, guards, and execution records |

## Status

> **Alpha — active development.** APIs may change between minor versions.

Install the latest alpha from PyPI:

```bash
pip install vidbyte-sdk
```

Pin the first public release when reproducibility matters:

```bash
pip install vidbyte-sdk==0.1.0
```

Verify the installed distribution and prompt assets:

```bash
python -c "from importlib.metadata import version; import vidbyte; from vidbyte import Prompts; print(version('vidbyte-sdk'), vidbyte.__version__, len(Prompts().keys()))"
```

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.harnesses
sdk.paradigms
sdk.agents
sdk.tools
sdk.providers
```

## Agents and Runner Inference

Use agents as the public entry point for model execution. Agents infer the
concrete runner type from the configured provider and model name, so callers
normally pass plain strings to `run()` and `arun()` without configuring runner
objects or modalities.

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()

image_agent = sdk.agents.base(
    name="asset-generator",
    system_prompt="Create useful product assets.",
    provider="openai",
    model_name="gpt-image-1",
)

reply = image_agent.run("A clean product mockup on a white desk")
print(reply.content)
```

## Multi-Agent Orchestration

Use `MultiAgent` when open-ended work needs a manager that owns the overall goal,
tracks evidence and blockers in a shared `TaskLedger`, delegates one ready task
per round, and replans after failure:

```python
from vidbyte import BaseAgent, MultiAgent, MultiAgentSettings

manager = BaseAgent(
    name="manager",
    system_prompt="Plan, delegate, track progress, and recover from blockers.",
    provider="openai",
    model_name="gpt-4.1",
)
researcher = BaseAgent(
    name="researcher",
    system_prompt="Research the assigned task and return evidence.",
    provider="openai",
    model_name="gpt-4.1",
)
team = MultiAgent(
    name="research-team",
    system_prompt="Produce a grounded answer and expose uncertainty.",
    orchestrator=manager,
    agents=[researcher],
    settings=MultiAgentSettings(max_rounds=12, max_replans=2),
)

reply = await team.arun("Investigate the release risk and recommend next steps.")
```

Wrap workers in `AgentBinding` / `AgentTransfer` to define the exact request,
report parser, validator, dispatch gate, subtype-aware fork factory, and closer.
`MultiAgent` is serial and run-local; its facade cannot own tools, MCP servers,
or durable sessions. Use pipelines for fixed string flow and `vidbyte.workflows`
when Python code must own a deterministic state machine.

For custom agents, pass an explicit `system_prompt`, provider/model config, and tools into `Agent` or `BaseAgent`.
Semantic labels such as roles belong in agent metadata when callers need them.

## Paradigm Harnesses

`vidbyte.paradigms` is the SDK namespace for thin runnable paradigm harnesses:
high-level agentic engineering patterns that compose agents, tools, context,
prompts, middleware, trace, pipelines, and evals into an opinionated execution
loop.

The first concrete paradigm is `ContextMinimalFanoutParadigm`. It runs a
four-stage pipeline — a context-extraction agent, a splitter agent, an
adversarial de-overlap agent, and parallel implementation agents — so one large
request is turned into non-overlapping, context-rich prompts that each run in a
fresh, smaller agent context.

```python
from vidbyte import ContextMinimalFanoutParadigm

harness = ContextMinimalFanoutParadigm(
    default_tool_root=".",
    implementation_tools=[my_patch_tool],
    splitter_model_name="claude-opus-4-8",
    implementation_model_name="claude-sonnet-5",
    max_concurrency=4,
)
result = harness.run("Implement the requested repo change.")
```

## Context Objects

Context dataclasses are exposed through `vidbyte.context` and centralized internally under `vidbyte.lib.dataclasses`.

```python
from vidbyte.context import BaseContext, ContextBudget, ContextPermissions
from vidbyte.lib.enums import BudgetPreset, PermissionPreset

context = BaseContext(
    file_paths=["README.md"],
    run_metadata={"phase": "draft"},
    budget=ContextBudget.from_preset(BudgetPreset.BALANCED),
    permissions=ContextPermissions.from_preset(PermissionPreset.READ_ONLY),
)
context.build_context()
```

## Context Management

Use `ContextManager` and context items when you want reusable, structured context
instead of assembling raw prompt strings yourself. Use `ContextWindow` presets
when you want an agent to run with an SDK-provided context-window algorithm.

```python
from vidbyte import Agent, ContextManager
from vidbyte.context.primitives import FileContextItem, TaskContextItem

context = ContextManager([
    TaskContextItem(
        goal="Fix failing tests",
        progress="Reviewed the runtime context builder.",
        deterministic_checks=("python -m unittest discover -s tests",),
    ),
    FileContextItem.from_path("README.md", include_content=True),
])

agent = Agent(
    name="repo-analyst",
    system_prompt="Use the supplied context before answering.",
    provider="openai",
    model_name="gpt-4.1",
    context_manager=context,
)
```

Context-window algorithms are attached as a single agent option. The default
keeps existing behavior; presets can change how runtime context grows between
model calls.

```python
from vidbyte import ContextWindow

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    algorithm=ContextWindow.preset.no_raw_tool_outputs,
)
```

For long-running direct loops, trajectory checkpoints can periodically write a
bounded runtime checkpoint into the context window through managed context
primitives. Checkpoints summarize observable runtime state only; their score is
a deterministic heuristic, not an external correctness grade.

```python
agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    algorithm=ContextWindow.preset.trajectory_checkpoints,
)
```

Two reasoning algorithms periodically pause a direct loop to reflect on the run
so far. `problem_space_search` runs an explorer pass every N iterations
(default 5) that surfaces angles the agent has not yet considered — blind spots,
unexplored approaches, and next directions — and injects them as a bounded note.
`error_correction` runs an auditor pass every N iterations (default 4) that
treats the original system prompt as ground truth, flags context that
contradicts it, prunes its own stale managed primitives, and writes a single
authoritative correction notice. Both update the context window through managed
primitives only; they never rewrite prior conversation history.

```python
agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    algorithm=ContextWindow.preset.problem_space_search,  # or ContextWindow.preset.error_correction
)
```

For a verdict-only adversarial review, `prosecutor_defender_judge` runs the
normal producer once and then uses three fresh contexts in strict sequence. The
prosecutor emits evidence-backed allegations, the defender answers those exact
allegation IDs, and the judge decides which IDs survive. The candidate is never
revised: `output`, `structured`, `calls`, strategy name, and existing metadata
remain the producer's values.

```python
from vidbyte import ContextWindow

agent = Agent(
    name="reviewed-producer",
    system_prompt="Produce the requested artifact.",
    provider="openai",
    model_name="gpt-4.1",
    algorithm=ContextWindow.preset.prosecutor_defender_judge,
)

reply = await agent.arun("Evaluate this implementation against the requirements.")
debate = reply.metadata["prosecutor_defender_judge"]
print(debate["verdict"], debate["surviving_allegation_ids"])
```

By default, review roles receive no producer artifacts or tools and never
receive producer history, scratch reasoning, middleware, options, system prompt,
memory, or context-manager state. Advanced callers can construct
`ProsecutorDefenderJudgeAlgorithm` with separate `DebateStageSettings` for each
role. Artifact names are exact allowlists; tool names must resolve to non-bound
`SAFE` or `READ` tools. Review adds three sequential model calls by default and
uses stage-local timeout, iteration, token, and tool-call limits. Failures raise
unless `ProsecutorDefenderJudgeFailurePolicy.RETURN_CANDIDATE` is explicitly
selected, in which case the unchanged candidate carries marked no-verdict
`review_failed` metadata.

Per-call context can be supplied with `AgentInput` without mutating the agent's
default context:

```python
from vidbyte import AgentInput
from vidbyte.context.primitives import TextContextItem

reply = await agent.arun(
    AgentInput(
        "Review the current task.",
        context_items=(TextContextItem(title="Reviewer note", content="Focus on public API compatibility."),),
    )
)
```

## Sources and Repository Artifacts

Use `vidbyte.sources` when a public document or repository artifact should become explicit context with fetch/caching policy, content hashing, selection, and trust boundaries. `llms.txt` support is built in for agent-facing documentation bundles.

The repository also includes [`artifacts/file_index.md`](artifacts/file_index.md), a generated source map for fast navigation across SDK packages, tests, skills, prompts, and design docs. Update it when structure changes materially.

## Tracing

Use `Trace` presets when you want agent runs to emit trace spans without wiring
provider adapters manually. `Trace.off()` disables tracing, `Trace.debug()` keeps
an in-memory event list for local inspection, and provider helpers wrap the
existing tracing adapters.

```python
from vidbyte import Agent, Trace

events = []

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    trace=Trace.debug(events),
)
```

Semantic trace profiles add SDK-owned prebuilt spans for agents, runtimes,
context-window work, algorithms, middleware decisions, tool calls, parsers, and
aggregate agents. The default profile keeps the current high-signal tree
(`agent.run`, `llm.call`, `tool.call`) and adds parser/tool/stop metadata. The
verbose profile adds runtime iteration, context-window, algorithm, aggregate,
and middleware-decision spans.

```python
from vidbyte import Trace, TraceProfile

trace = Trace.profile(
    inner=Trace.debug(events),
    profile=TraceProfile.verbose().with_components(middleware="decisions_only"),
)

agent = Agent(
    name="observed-worker",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    trace=trace,
)
```

Provider-backed tracing uses the existing optional adapters:

```python
agent = Agent(
    name="observed-agent",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    trace=Trace.langfuse(public_key="...", secret_key="..."),
)
```

For LangSmith, use `Trace.langsmith_default(...)` as the recommended
single-agent preset. It emits `agent.run`, `llm.call`, and `tool.call` runs
with LangSmith-native run types and includes prompt, tool schema, tool input,
and output fields for browser inspection. `Trace.langsmith_verbose(...)` uses
the verbose semantic profile for runtime iteration, context-window, algorithm,
aggregate, parser, and middleware-decision spans.

```python
agent = Agent(
    name="observed-agent",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    trace=Trace.langsmith_default(project="vidbyte-agents"),
)
```

Semantic LangSmith helpers translate Vidbyte span kinds into LangSmith run
types (`chain`, `llm`, `tool`, `retriever`, `embedding`, `prompt`, and
`parser`). Multi-agent grouping into one LangSmith trace is handled separately
by session tracing; `Trace.langsmith_default(...)` is the default single-agent
preset.

Use a semantic session tracer when several agents should appear under one
provider root:

```python
from vidbyte import Agent, Trace

trace = Trace.langsmith_session(
    project="research",
    name="research-run",
)

async with trace.async_session(run_id=run_id):
    planner = Agent(name="planner", system_prompt="Plan the work.", provider="openai", model_name="gpt-4.1", trace=trace)
    writer = Agent(name="writer", system_prompt="Draft the answer.", provider="openai", model_name="gpt-4.1", trace=trace)
    await planner.arun("Plan the release note")
    await writer.arun("Write the release note")
```

`Trace.continual(...)` is a validated first-step capture preset for future
trace-to-context feedback. It records lifecycle events and stores settings, but
does not yet inject trace memory into the agent context.

```python
agent = Agent(
    name="continual-agent",
    system_prompt="Preserve useful run context.",
    provider="openai",
    model_name="gpt-4.1",
    trace=Trace.continual(["tool_calls", "failures"], max_memory_chars=1200),
)
```

### Continual Trace Agent

For a structured, continually-updated handoff artifact, pass
`trace_option=TraceOption.continual(schema)`. While the main agent runs, a dedicated
`ContinualTraceAgent` is invoked as middleware every `every_n_iterations` and once at
the end. It reads a read-only snapshot of the main run and fills your schema through a
validating `updateTrace` tool: array fields are appended to, object fields deep-merged,
scalar fields replaced, and unknown keys dropped. The artifact is returned on
`reply.metadata["trace"]` (and `agent.last_trace`) and is never written into the main
agent's context window. This is orthogonal to the `trace=` observability tracers.

Schemas can be a Pydantic model (recommended — typed and described), a `TraceSchema`,
or a `{field: description}` mapping. A prebuilt `ActionTrace` is included.

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.continual import ActionTrace

agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    trace_option=TraceOption.continual(ActionTrace, every_n_iterations=5, max_trace_iterations=3),
)
reply = await agent.arun("Fix the failing tests")
trace_artifact = reply.metadata["trace"]   # {"goal": ..., "actions_taken": [...], "mistakes": [...], "current_status": ...}
```

Define a custom typed schema with Pydantic:

```python
from pydantic import BaseModel, Field
from vidbyte import TraceOption

class DebugTraceModel(BaseModel):
    goal: str = Field(description="What the agent is trying to fix.")
    mistakes: list[str] = Field(default_factory=list, description="Failed attempts and dead ends, appended over time.")
    current_status: str = Field(description="The latest state and immediate next step.")

agent = Agent(..., trace_option=TraceOption.continual(DebugTraceModel))
```

Continual tracing is fail-open (trace failures never abort the main run) and is only
supported on the default linear runtime.

## Swappable Agent Runtimes

The Vidbyte SDK decouples the core `BaseAgent` class from the execution loop. Developers can select different agent runtime loop paradigms at initialization:

* **MCTS Search**: Non-linear tree search (Monte Carlo Tree Search) exploring parallel reasoning paths.
* **Actor Model**: Asynchronous, concurrent message-passing loops (supporting Point-to-Point and Broadcast topologies).

```python
from vidbyte import BaseAgent
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.agents.runtimes.configs import ActorRuntime

# Monte Carlo Tree Search runtime
search_agent = BaseAgent(
    name="search-agent",
    system_prompt="Explore reasoning branches.",
    runtime=AgentRuntimeType.MCTS_SEARCH,
)

# Asynchronous Actor Model swarm (Point-to-Point topology)
actor_swarm = BaseAgent(
    name="swarm-coordinator",
    system_prompt="Coordinate parallel specialized sub-actors.",
    runtime=ActorRuntime(
        worker_model="gpt-4o-mini",
        dynamic_actors=True,
        max_loop=30,
        termination_mode="quiescence",
    ),
)
```

For more details on runtimes, see the [Agent Runtimes Skill Guide](skills/agent-runtimes/SKILL.md).

### Tools

The SDK tool path is agent-local: create or import tools, pass them into an agent, and let the agent describe, format, and execute them when the model asks for a tool call.

```python
from vidbyte import Agent, tool
from vidbyte.tools.builtins import ForkConversationTool
from vidbyte.tools.builtins.code_search import GrepTool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    """Look up one user's metric."""
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[GrepTool(root_dir="."), ForkConversationTool(allowed_models=["gpt-4.1-mini"]), lookup_metric],
    max_iterations=8,
    max_tokens=16_000,
)

reply = await agent.arun("Find where tools are formatted.")
```

The runtime builds the context window, appends a short agentic-loop prompt after the system prompt, sends tool schemas to the model, executes permitted tool calls, appends tool results back into the ordered message context, and repeats until the model calls the internal `isDone` tool. If the model returns ordinary text without a tool call, that text is preserved as assistant history and the loop continues. `max_iterations` and `max_tokens` are optional safeguards; `max_tokens` uses provider-reported usage when available.

`ForkConversationTool` is agent-native: it lets the model ask the current agent to run an isolated child conversation immediately through `BaseAgent.fork(...)`. It is separate from durable session forks, inherits permission policy, requires allowlisted model swaps, and only exposes developer-provided extra toolsets.

### Middleware

Middleware gives direct text agents deterministic runtime hooks for authorization, rate limiting, retry, audit logging, and other policies. Middleware is not model-visible and does not appear in tool specs or agent cards.

```python
from vidbyte import Agent, AgentMiddleware, MiddlewareDecision
from vidbyte.middleware.builtins import ToolPolicyMiddleware, ToolResultCompactionMiddleware

class TenantPermissionMiddleware(AgentMiddleware):
    def __init__(self, db):
        self.db = db

    async def before_run(self, ctx):
        if not await self.db.can_start_agent(ctx.metadata["tenant_id"], ctx.agent_name):
            return MiddlewareDecision.abort("tenant_cannot_start_agent")
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx):
        if not await self.db.can_call_tool(ctx.metadata["tenant_id"], ctx.tool_call.tool_name):
            return MiddlewareDecision.deny_tool("tenant_cannot_call_tool")
        return MiddlewareDecision.continue_()

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    middleware=[
        TenantPermissionMiddleware(db),
        ToolPolicyMiddleware(allow_tools={"lookup_metric"}),
        ToolResultCompactionMiddleware.truncate(max_chars=600),
    ],
)
```

Subclass `AgentMiddleware` and override only the hooks you need, such as `before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`, `after_tool_call`, `after_iteration`, or `after_run`. Built-ins are available from `vidbyte.middleware.builtins`, including `TokenBudgetMiddleware`, `TokenRateLimitMiddleware`, `RuntimeLimitMiddleware`, `ToolPolicyMiddleware`, `AuditLogMiddleware`, `ModelRetryMiddleware`, `ToolErrorPolicyMiddleware`, `ToolResultCompactionMiddleware`, `MessageHistoryCompactionMiddleware`, `SummaryCompactionMiddleware`, and `TraceReplacementCompactionMiddleware` (folds a continual-trace artifact back into history; e.g. `TraceReplacementCompactionMiddleware.keep_recent_tail(keep_last_groups=2)`). `TokenBudgetMiddleware(max_tokens=...)` is a hard cap by default; set `allow_final_response_over_budget=True` to permit one final over-budget model call with an injected instruction to answer immediately. This is separate from `Agent(max_tokens=...)`, which remains a runtime hard cap.

Use structured loop settings for tool-error retry/abort policy:

```python
from vidbyte import Agent
from vidbyte.agents import AgentLoopSettings, ToolErrorPolicy

agent = Agent(
    name="resilient-worker",
    system_prompt="Use tools and recover from transient failures.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    agent_loop_settings=AgentLoopSettings(
        tool_error_policy=ToolErrorPolicy(max_retries_per_tool_call=2, max_total_tool_errors=5),
    ),
)
```

The default policy retries idempotent transient tool failures and renders terminal tool errors with full detail.

Use `ToolSettings` for simple, universal tool-use guardrails. These are enforced directly by the runtime (not middleware), the same way loop budgets like `max_tool_calls` are:

```python
from vidbyte import Agent
from vidbyte.agents import AgentLoopSettings, ToolSettings

agent = Agent(
    name="repo-worker",
    system_prompt="Use tools carefully.",
    runner=my_runner,
    tools=[search, delete_file],
    agent_loop_settings=AgentLoopSettings(
        tool_settings=ToolSettings(
            denied_tools={"delete_file"},   # blocked by name, incl. dynamically attached tools
            max_calls=20,                   # total tool-call budget for the run
            max_calls_per_tool={"search": 5},
            max_calls_per_iteration=4,      # hard-stop if a single model turn fans out too many tools
            max_identical_calls=3,          # hard-stop when the same tool+args fingerprint repeats
            max_consecutive_failures=5,     # hard-stop after N failed tools in a row
            max_error_calls=20,             # run-wide hard-stop on failed tool executions
            tool_timeout_seconds=30.0,      # per-call timeout; timeouts count as failures
            sliding_window_max_calls=10,    # hard-stop if too many tools in the last K iterations
            sliding_window_iterations=3,    # K for the sliding window (required with max above)
            result_max_chars=8000,          # cap model-visible tool output; raw result is preserved
            on_deny="continue",             # "continue" injects a denial the model sees; "abort" stops the run
        ),
    ),
)
```

`denied_tools` is useful even when tools are passed explicitly: it documents team policy and blocks tools acquired dynamically by name. Internal runtime tools (such as the completion tool) are never blocked. With `on_deny="continue"` (default), a denied or over-per-tool-budget call is recorded as a denied tool result the model sees, and the run continues; with `on_deny="abort"` the run stops with stop reason `tool_settings_denied`. Budget-class limits hard-stop the run with dedicated stop reasons: `max_calls` / `max_tool_calls`, `max_calls_per_iteration`, `max_identical_calls`, `max_consecutive_failures`, `max_error_calls`, and `sliding_window_max_calls`. `on_deny` does **not** soft-continue those budgets. `tool_timeout_seconds` cancels hung tool awaits best-effort via `asyncio.wait_for` and records a failed tool result that counts toward failure budgets. `sliding_window_max_calls` and `sliding_window_iterations` must both be set or both omitted. `result_max_chars` truncates only the model-visible tool result while the raw `ToolResult` remains available in runtime metadata. `ToolSettings.max_calls` and `AgentLoopSettings.max_tool_calls` map to the same budget and must match if both are set. `ToolSettings` complements, and does not replace, `PermissionPolicy`.

Compaction middleware supports deterministic provider-message pruning without hidden model calls. Examples include `trim_to_token_budget`, `trim_with_provider_boundaries`, `delete_messages`, `tool_output_sliding_window`, `clear_tool_results_except`, `head_tail_tool_preview`, `scrub_bloat`, `summary_with_backrefs`, `selective_prune`, `salience_score_eviction`, `query_relevance_filter`, and `context_snapshot_branch_trim`.

```python
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware

agent = Agent(
    name="bounded-agent",
    system_prompt="Keep working context compact.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    middleware=[
        MessageHistoryCompactionMiddleware.trim_to_token_budget(max_tokens=8000),
        MessageHistoryCompactionMiddleware.query_relevance_filter(query=None, keep_recent=4),
    ],
)
```

Advanced built-ins are grouped by category:

- `vidbyte.tools.builtins.code_search`: `GlobTool`, `GrepTool`, `SemanticSearchTool`
- `vidbyte.tools.builtins.editing`: `PatchTool`
- `vidbyte.tools.builtins.context`: `ContextCompactionTool` for legacy/manual compaction tool use; new agent code should prefer compaction middleware.
- `vidbyte.tools.builtins.fork`: `ForkConversationTool`
- `vidbyte.tools.builtins.handoff`: `CreateHandoffTool`
- `vidbyte.tools.builtins.sessions`: `CheckpointTool`, `ForkTool`, `BatchForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, `ResumeOutputTool`, `SessionTool`
- `vidbyte.tools.builtins.providers`: provider/database helper tools
- `vidbyte.tools.mcp`: `McpClient`, `McpStdioTransport`, `McpBridgedTool`
- `vidbyte.tools.security`: `PermissionPolicy`, `ToolPermission`, sandbox transport protocols

`Tools` is the catalog/inspection helper for showing the model or a developer which tools are available:

```python
from vidbyte.tools import Tools

catalog = Tools([lookup_metric])
print(catalog.describe())
openai_tools = catalog.provider_schemas("openai")
```

The default permission policy allows `SAFE` and `READ` tools. Mutating or executable tools require an explicit permission policy on the agent:

```python
from vidbyte import Agent
from vidbyte.tools.security import PermissionPolicy

agent = Agent(
    name="trusted-worker",
    system_prompt="Work inside the configured sandbox.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[write_tool],
    permission_policy=PermissionPolicy.allow_all(),
)
```

`ToolRegistry`, `ToolExecutor`, and `vidbyte_tool` remain available for compatibility with older examples. New user-facing code should prefer `Tools`, `@tool`, and agent-local `tools=[...]`.

## Registries

The SDK keeps discovery and compatibility catalogs under `vidbyte.lib.registries`.
Use these when you need to inspect supported SDK capabilities, bridge older code, or
register local runtime objects without hardcoding lookups.

| Registry | Purpose |
|----------|---------|
| `AgentRegistry` | Registers live agents and finds them by name, capability, tool name, or metadata. |
| `ProviderModelRegistry` | Centralizes provider defaults, API key env vars, endpoints, model validation, and active provider resolution. |
| `Prompts` / `PromptRecord` | Loads prompt assets and exposes prompt text, descriptions, families, and direct import names. |
| `RuntimeRegistry` | Resolves `AgentRuntimeType` enum values to concrete runtime classes. |
| `ToolRegistry` | Thread-safe compatibility wrapper around the newer agent-local `Tools` catalog. |
| `ActorRegistry` / `actor_registry` | Registers and discovers actor-runtime role classes. |

```python
from vidbyte import tool
from vidbyte.lib.enums import AgentRuntimeType, ModelProvider
from vidbyte.lib.registries import ProviderModelRegistry, RuntimeRegistry, ToolRegistry, actor_registry

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

default_openai_model = ProviderModelRegistry.default_model(ModelProvider.OPENAI)
openai_env_var = ProviderModelRegistry.get_api_key_env_var("openai")
runtime_cls = RuntimeRegistry.resolve(AgentRuntimeType.LINEAR)
tool_registry = ToolRegistry([lookup_metric])
known_actor_roles = actor_registry.list()
```

Use `AgentRegistry` for application-local agent discovery:

```python
from vidbyte import Agent
from vidbyte.lib.registries import AgentRegistry

registry = AgentRegistry()
registry.register(
    Agent(
        name="researcher",
        system_prompt="Answer directly and cite uncertainty.",
        provider="openai",
        model_name="gpt-4.1",
    )
)

agent = registry.get("researcher")
matches = registry.find(capability="research")
```

## MCP Servers

Vidbyte supports MCP in two directions: expose Vidbyte agents and tools to an
external MCP client, or attach third-party MCP servers as tools on a Vidbyte agent.

### Vidbyte as an MCP Studio Server

Install the SDK in the Python environment your MCP client will launch, then use the
console entry point:

```bash
vidbyte-mcp-server
```

The equivalent module command is:

```bash
python -m vidbyte.mcp_server
```

The server speaks stdio JSON-RPC and is meant to be launched by an MCP client such
as Claude Code, Cursor, Codex, or another MCP-compatible host. For project-specific
agents, tools, and prompts, create a launcher script and point the MCP client at it:

```python
import asyncio
from vidbyte import McpStudioServer, Prompts
from my_project.agents import code_agent, research_agent
from my_project.tools import database_tool

async def main() -> None:
    prompts = Prompts()
    server = McpStudioServer(
        name="my-vidbyte-studio",
        agents={"coder": code_agent, "researcher": research_agent},
        tools=[database_tool],
        pipeline_names=["sequential", "parallel", "map-reduce"],
        prompt_content={key.value: text for key, text in prompts.all().items()},
    )
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

The Studio server exposes these built-in MCP tools:

- `studio.agents.list`
- `studio.agents.run`
- `studio.tools.list`
- `studio.strategies.list`
- `studio.strategies.run`
- `studio.prompts.list`
- `studio.prompts.get`
- `studio.pipelines.list`

It also supports MCP-native `prompts/list` and `prompts/get` for clients that use
the prompt protocol directly.

### Preset MCP Servers for Agents

Use `McpPresetRegistry` when you want to discover or build third-party MCP server
configs without memorizing subprocess commands. Presets define command templates
and required environment variables; they do not store secrets or guarantee host
packages are installed. The core discovery methods are
`McpPresetRegistry.get()`, `McpPresetRegistry.list_presets()`, and
`McpPresetRegistry.build_config()`.

```python
import os
from vidbyte import Agent
from vidbyte.tools.mcp.presets import McpPresetRegistry

github = McpPresetRegistry.get("github")
all_search_servers = McpPresetRegistry.list_presets("Search & Web Research")

github_config = McpPresetRegistry.build_config(
    "github",
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]},
)

agent = Agent(
    name="repo-analyst",
    system_prompt="Use repository tools when they help.",
    provider="openai",
    model_name="gpt-4.1",
).with_preset_mcp_server(
    "github",
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]},
)
```

Use eager attachment when you want to connect and discover tools immediately:

```python
await agent.attach_preset_mcp_server(
    "linear",
    env={"LINEAR_API_KEY": os.environ["LINEAR_API_KEY"]},
)
```

Raw MCP server configs are still supported when you need a custom command:

```python
await agent.attach_mcp_server(
    ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."],
    name="local-filesystem",
)
```

The current preset catalog contains 201 presets:

| Category | Presets |
|----------|---------|
| Search & Web Research | `apify`, `brave-search`, `browserbase`, `duckduckgo`, `exa`, `firecrawl`, `google-search`, `jina-reader`, `linkup`, `perplexity`, `playwright`, `puppeteer`, `scrapingbee`, `searxng`, `serper`, `tavily`, `you-search`, `zenrows` |
| Version Control, Development & Task Tracking | `asana`, `bitbucket`, `circleci`, `clickup`, `datadog`, `docker`, `github`, `github-actions`, `gitlab`, `jenkins`, `jira`, `kubernetes`, `linear`, `monday`, `newrelic`, `pagerduty`, `sentry`, `sonarqube`, `terraform`, `travis-ci`, `trello`, `vercel` |
| Databases & Cache | `cassandra`, `chromadb`, `clickhouse`, `cockroachdb`, `dynamodb`, `elasticsearch`, `faunadb`, `firebase`, `milvus`, `mongodb`, `mysql`, `neon`, `pinecone`, `planetscale`, `postgres`, `qdrant`, `redis`, `sqlite`, `supabase`, `timescaledb`, `turso`, `weaviate` |
| Productivity, Office & CRM | `airtable`, `basecamp`, `coda`, `confluence`, `evernote`, `freshservice`, `gmail`, `google-calendar`, `google-drive`, `google-sheets`, `hubspot`, `intercom`, `notion`, `obsidian-vault`, `onedrive`, `outlook`, `pipedrive`, `salesforce`, `smartsheet`, `todoist`, `zendesk`, `zoho-crm` |
| Document Parsers & Media Utilities | `camelot`, `docling`, `docx-parser`, `epub-reader`, `exiftool`, `ffmpeg`, `graphviz`, `imagemagick`, `libreoffice`, `markitdown`, `pandoc`, `pdf-parser`, `pptx-parser`, `tesseract-ocr`, `unstructured`, `video-transcript`, `whisper`, `xlsx-parser` |
| Communication & Chat | `discord`, `line-messaging`, `mailgun`, `mandrill`, `mattermost`, `postmark`, `pushover`, `resend`, `rocketchat`, `sendgrid`, `slack`, `teams`, `telegram`, `twilio`, `whatsapp`, `zoom` |
| Cloud Platforms, Hosting & Infrastructure | `aws-cloudwatch`, `aws-ec2`, `aws-lambda`, `aws-rds`, `aws-s3`, `azure-blob`, `azure-devops`, `azure-vm`, `cloudflare`, `digitalocean`, `fly-io`, `gcp-bigquery`, `gcp-compute`, `gcp-storage`, `heroku`, `linode`, `netlify`, `railway`, `render`, `vultr` |
| AI Platforms & Creative APIs | `anthropic-agent`, `assembly-ai`, `cohere-search`, `deepgram`, `elevenlabs`, `fal-ai`, `groq`, `heygen`, `huggingface`, `langsmith`, `midjourney`, `mistral`, `openai-agent`, `replicate`, `runway`, `stability-ai`, `suno`, `together-ai` |
| Reference & Academic | `arxiv`, `crossref`, `devdocs`, `docker-hub`, `geonames`, `mdn`, `npm-registry`, `open-library`, `open-meteo`, `pubchem`, `pubmed`, `pypi`, `semantic-scholar`, `stackoverflow`, `wikipedia`, `wolfram-alpha` |
| Native System & Utilities | `base64-tools`, `csv-parser`, `datetime`, `env-inspector`, `git`, `hashing-tools`, `http-client`, `json-validator`, `local-filesystem`, `markdown-linter`, `os-command`, `process-manager`, `python-sandbox`, `regex-tester`, `sequential-thinking`, `sqlite-sandbox`, `system-diagnostics`, `toml-parser`, `uuid-generator`, `webhook-sender`, `xml-parser`, `yaml-validator` |
| E-Commerce & Payments | `paypal`, `shopify`, `square`, `stripe`, `woocommerce` |
| Automation & Workflow | `n8n`, `zapier` |

## CLI

The SDK installs a unified `vidbyte-sdk` command. Its first command group wraps the
packaged skills registry:

```bash
vidbyte-sdk --version
vidbyte-sdk skills list
vidbyte-sdk skills show decompose-fanout
vidbyte-sdk skills install decompose-fanout --dest .claude/skills
```

`vidbyte-sdk skills install` writes the selected skill folder under the destination
directory and refuses to overwrite an existing non-empty skill folder unless
`--force` is passed.

## Durable Sessions

Durable sessions are a harness-level primitive that make any agent persistent
with `continue`, `resume`, and `fork` over an append-only checkpoint DAG. The
agent stays pure — persistence lives in a `Session` wrapper, so it works for
every runtime. Attach an agent in one line:

```python
from vidbyte import Agent, FileSessionStore, Session

agent = Agent(name="researcher", system_prompt="Investigate carefully.", provider="openai", model_name="gpt-4.1")
store = FileSessionStore(root="./.vidbyte/sessions")
session = agent.persist(store=store, policy=Session.PER_TURN_POLICY)
reply = await session.arun("Investigate the failing test")
print(session.id, session.head)              # session id + latest checkpoint id
assert agent.session is session
```

Sessions are also reachable through the harness namespace
(`sdk.harnesses.sessions.attach(agent, store=...)`). Resuming reconstructs the
agent from a checkpoint; because live tools and middleware cannot be serialized,
you re-supply them at resume time (the rehydration contract):

`Session.policy_options()` and `Session.trace_options()` list the accepted hard
strings for `policy=` and `trace=`. The same strings are available as class
constants such as `Session.PER_TURN_POLICY`, `Session.MANUAL_POLICY`, and
`Session.AUTO_TRACE`.

```python
from vidbyte.sessions import FileSessionStore

store = FileSessionStore(root="./.vidbyte/sessions")
session = Session(agent, store=store)
await session.arun("first step")

# later / cold process - re-supply non-serializable parts
session = Session.resume(store, session_id, tools=[grep])
session = Session.continue_(store, session_id)           # == resume(head)
branch = Session.fork_from(store, checkpoint_id)         # new id + parent lineage
branches = session.batch_fork(3)                                   # child records only
session.rewind(to=checkpoint_id)                                    # time-travel
session.edit(lambda history: history[:-1])                         # state editing
```

Tags, usage rollups, and portable bundles are first-class:

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
session.tag("research-main", "july-release")
resolved_id = store.resolve("research-main")
recent = store.list_sessions(agent_name="researcher", tag="july-release")

rollup = session.usage(prices={"gpt-4.1": 0.00001})
print(rollup.tokens, rollup.tool_calls, rollup.cost)

bundle = session.export()
copy_id = sdk.harnesses.sessions.import_(store, bundle, new_id="se_copy")
```

Importing with `new_id=` rewrites only session ids; checkpoint ids and parent links stay intact.

Stores are pluggable behind one `SessionStore` protocol. The local stores
(`InMemorySessionStore`, `FileSessionStore` with atomic JSON writes) ship in
`vidbyte.sessions`; database-backed stores (`SqliteSessionStore` using stdlib
`sqlite3`, plus `MongoDbSessionStore`, `SupabaseSessionStore`,
`PostgresSessionStore`) live in `vidbyte.lib.providers` and import their drivers
lazily (SQLite excepted, since `sqlite3` is stdlib), so the SDK core needs no
database dependency.

When saving, a session reads the agent's existing trace settings and persists the
continual-trace artifact onto each checkpoint. Control it with the `trace`
option: `TraceCapture.AUTO` (default — capture when the agent has tracing
enabled), `OFF`, `ARTIFACT`, or `FULL` (artifact plus raw span events). Trace
data is a derived observation stored alongside the checkpoint; it never feeds
`resume`, which always restores the agent's raw history as source of truth.

### Prebuilt session tools

Prebuilt tools under `vidbyte/tools/builtins/sessions/` let an agent
checkpoint, fork, rewind, and resume its own or another agent's thread, gated by
`SessionScope` (own runs by default). `Session` auto-binds any of these found on
the wrapped agent.

```python
from vidbyte.tools.builtins import (
    BatchForkTool, CheckpointTool, ForkTool, RewindTool,
    ResumeReplaceTool, ResumeAppendTool, ResumeOutputTool, SessionTool,
)

agent = Agent(name="researcher", system_prompt="...", provider="openai", model_name="gpt-4.1",
              tools=[CheckpointTool(store), ForkTool(store), BatchForkTool(store), RewindTool(store),
                     ResumeReplaceTool(store), ResumeAppendTool(store), ResumeOutputTool(store),
                     SessionTool(store)])
session = Session(agent, store=store)
```

- `CheckpointTool` — snapshot the current thread (or copy an in-scope session's head as a labeled checkpoint).
- `ForkTool` — branch a new session from the current head or any in-scope checkpoint.
- `BatchForkTool` — create 1-64 child sessions from the same checkpoint without running those children.
- `RewindTool` — time-travel the current session's head to an earlier checkpoint.
- `ResumeReplaceTool` — replace the current context window with another agent's thread state (own-thread: rewind).
- `ResumeAppendTool` — append another agent's full context window into the current one.
- `ResumeOutputTool` — append only another agent's final output; errors if that thread is not `COMPLETED`.
- `SessionTool` — central combined tool: `create_checkpoint` / `fork_current` / `list_my_runs` / `read_run`.

Persisting a checkpoint is fail-open: a store write failure is recorded in the
reply metadata but never ends the run.

## Prompts

Prompts are repository-backed text assets exposed through an enum-keyed accessor
and direct Python imports. The catalog currently includes 51 prompt assets across
19 families, including handoff, reflexion, evals, prompt templates, goals,
actor-runtime personas, trajectory checkpoints, and multi-agent orchestration.

```python
from vidbyte.prompts import Prompts
from vidbyte.lib.enums.prompts import Prompt

prompts = Prompts()
prompt_text = prompts.get(Prompt.REFLEXION_AGENT_SYSTEM_PROMPT)
```

Direct import names are generated from prompt enum values by replacing dots with
underscores:

```python
from vidbyte.prompts import handoff_system_prompt, templates_persona, evals_llm_judge

system_prompt = handoff_system_prompt
persona_template = templates_persona
judge_prompt = evals_llm_judge
```

Use the catalog methods when you need discovery:

```python
from vidbyte import Prompts

prompts = Prompts()
keys = prompts.keys()
descriptions = prompts.descriptions()
import_names = prompts.import_names()
reflexion_prompts = prompts.family("reflexion")
all_prompt_text = prompts.all()
```

The same discovery calls are available directly as `Prompts().keys()`,
`Prompts().descriptions()`, `Prompts().import_names()`, `Prompts().family(...)`,
and `Prompts().all()`.

Prompt lookup accepts `Prompt` enum members, not raw strings. The SDK prompt
catalog is a static asset collection; runtime prompt overrides should be passed
through the agent or runner API that consumes the text.

## Evals

`vidbyte.evals` provides small building blocks for writing local eval scripts:
`EvalCase` defines prompts and expectations, `EvalSuite` groups cases,
`EvalRunner` executes a target with concurrency controls, and graders score each
output. The runner accepts agents and runner-like objects that expose `arun()`,
`run()`, or `generate_reply()`.

```python
from vidbyte import Agent, ContainsGrader, EvalCase, EvalRunner, EvalSuite

agent = Agent(
    name="qa",
    system_prompt="Answer concisely.",
    provider="openai",
    model_name="gpt-4.1",
)

suite = EvalSuite("smoke", [
    EvalCase(prompt="Capital of France?", expected="Paris", tags=("geography",)),
    EvalCase(prompt="2 + 2?", expected="4", tags=("math",)),
])

runner = EvalRunner(agent, default_grader=ContainsGrader(), concurrency=4)
result = await runner.arun(suite)

print(result.pass_rate, result.mean_score, result.p95_latency_ms)
```

Built-in graders cover common script-writing needs:

| Grader | Use |
|--------|-----|
| `ExactMatchGrader` | Exact string matches with stripping and case controls. |
| `ContainsGrader` | Substring expectations. |
| `RegexMatchGrader` | Regex pattern assertions. |
| `JSONSchemaGrader` | JSON parsing and structure checks. |
| `LLMJudgeGrader` | Model-judged open-ended outputs using an injected judge runner. |
| `RubricGrader` | Weighted rubric scoring using an injected judge runner. |

Eval cases can also use prebuilt templates: reusable bundles made from one or
more graders. `grader` remains the low-level escape hatch; when `grader` is not
set, `templates` are resolved before the runner falls back to `default_grader`.

```python
from vidbyte.evals import EvalCase, EvalSuite, templates as T

suite = EvalSuite("support-smoke", [
    EvalCase(
        prompt="What is our refund window?",
        expected="30 days",
        templates=(T.short_answer_fact(), T.safe_customer_support()),
    ),
    EvalCase(
        prompt="Return routing JSON.",
        expected={"category": "billing"},
        templates=(T.structured_json(schema={
            "type": "object",
            "required": ["category"],
            "properties": {"category": {"type": "string"}},
        }),),
    ),
])
```

Built-in template bundles include `short_answer_fact`, `multiple_choice`,
`structured_json`, `classification`, `numeric_answer`,
`concise_grounded_answer`, and `safe_customer_support`. Custom templates can
subclass `EvalTemplate` and return any `BaseGrader` from `build_grader()`.

Suites can be loaded from JSON or CSV files and filtered by tags:

```python
from vidbyte.evals import EvalSuite

suite = EvalSuite.from_json("evals/smoke.json")
focused = suite.filter(["geography"])
result = await runner.arun(focused)
```

JSON suites can specify templates by name or by name plus options:

```json
{
  "name": "support-smoke",
  "cases": [
    {
      "prompt": "Pick the best option.",
      "expected": "B",
      "templates": [
        {
          "name": "multiple_choice",
          "options": { "choices": ["A", "B", "C", "D"] }
        }
      ]
    }
  ]
}
```

Use `EvalClient` through `VidbyteSDK.evals` when you want a convenience factory and
a local SQLite-backed registry for recording and comparing runs:

```python
from vidbyte import VidbyteSDK, ContainsGrader, EvalCase

sdk = VidbyteSDK()
suite = sdk.evals.suite("smoke", [EvalCase(prompt="2 + 2?", expected="4")])
runner = sdk.evals.runner(agent, grader=ContainsGrader())
result = await runner.arun(suite)
sdk.evals.registry.record(result)
```

## Validated Workflows

Use `vidbyte.workflows` when Python code must control which stages are legal,
validate typed candidate state before it becomes committed state, and support
bounded loops, branches, retries, and jumps. This is the control-flow layer for
harnesses such as context -> spec -> implementation -> verification.

Stages and validators return semantic outcome codes; only the compiled graph
maps those codes to destinations. A deterministic schema check and a
probabilistic verifier agent therefore use the same gate contract without giving
either one permission to choose an arbitrary next stage.

```python
from dataclasses import dataclass, replace

from vidbyte import CallableStage, CallableValidator, MachineStatus
from vidbyte import StageResult, StateGraph, ValidationResult


@dataclass(frozen=True)
class HarnessState:
    request: str
    context: str = ""
    spec: str = ""


async def gather_context(ctx):
    ctx.ledger.setdefault("files_visited", set()).add("vidbyte/agents/base.py")
    return StageResult(replace(ctx.state, context="relevant SDK contracts"))


def context_is_sufficient(ctx):
    if ctx.candidate_state.context:
        return ValidationResult.passed()
    return ValidationResult.rejected("needs_more_context", "Collect more repository evidence.")


async def write_spec(ctx):
    return StageResult(replace(ctx.state, spec=f"Use {ctx.state.context}"))


graph = StateGraph(HarnessState, name="software-engineering-harness")
graph.add_stage(
    "context",
    CallableStage(gather_context),
    validators=(CallableValidator(context_is_sufficient),),
)
graph.add_stage("spec", CallableStage(write_spec))
graph.add_terminal("done", status=MachineStatus.SUCCEEDED)
graph.set_entry("context")
graph.add_transition("context", "spec")
graph.add_transition("context", "context", on="needs_more_context")
graph.add_transition("spec", "done")

result = await graph.compile().arun(HarnessState(request="Add a state machine"))
```

Candidate state is cloned and committed only after stage validators and selected
transition guards pass. Rejected candidates are discarded; structured feedback
and the explicitly non-transactional run ledger remain available to the recovery
stage. This in-memory transaction does not roll back filesystem, network, model,
or tool side effects, so stages that perform external work still need idempotency,
candidate artifacts, or compensation.

Use `AgentStage` to adapt a `BaseAgent`, and `AgentValidator` for a verifier agent
whose Pydantic verdict maps to `ValidationResult`. Verifier failures block by
default, but an LLM judgment remains probabilistic. See the
[`vidbyte.workflows` guide](vidbyte/workflows/README.md) for adapters, guard and
branch APIs, retry/error policies, records, and the full layer boundary.

## Pipelines

Pipelines compose agents across agent boundaries. The contract is string-in and
string-out: one stage's output becomes another stage's prompt. Each agent keeps
its own tools, middleware, context, and history; the pipeline layer does not add
shared context, budgets, artifacts, streaming, retries, or voting.

Use `SequentialPipeline` for chain workflows:

```python
from vidbyte import SequentialPipeline

pipeline = SequentialPipeline([planner_agent, coder_agent, reviewer_agent])
result = await pipeline.run("Build a small caching layer")
```

Use `ParallelPipeline` when every stage should receive the same prompt and the
outputs should be joined:

```python
from vidbyte import ParallelPipeline

pipeline = ParallelPipeline([security_agent, performance_agent, style_agent])
result = await pipeline.run("Review this diff")
```

Use `ConditionalPipeline` to route by a synchronous predicate:

```python
from vidbyte import ConditionalPipeline

def route(prompt: str) -> str:
    return "code" if "implement" in prompt.lower() else "research"

pipeline = ConditionalPipeline(
    predicate=route,
    branches={"code": code_agent, "research": research_agent},
)
result = await pipeline.run("Implement binary search")
```

Use `MapReducePipeline` for fan-out followed by a reducer:

```python
from vidbyte import MapReducePipeline

pipeline = MapReducePipeline(
    map_stages=[security_agent, performance_agent, style_agent],
    reduce_stage=summarizer_agent,
)
result = await pipeline.run("Review this service for production readiness")
```

Pipelines can be nested because every pipeline is also a valid pipeline stage:

```python
from vidbyte import MapReducePipeline, ParallelPipeline, SequentialPipeline

pipeline = SequentialPipeline([
    planner_agent,
    ParallelPipeline([solver_a, solver_b]),
    MapReducePipeline(map_stages=[reviewer_a, reviewer_b], reduce_stage=summarizer_agent),
])
```

For synchronous scripts, call `run_sync()` outside an active event loop:

```python
result = pipeline.run_sync("Draft a release plan")
```

## Package Structure

```text
artifacts/
|-- file_index.md
vidbyte/
|-- client.py
|-- agents/
|-- cli/
|-- context/
|-- evals/
|-- harnesses/
|   `-- client.py
|-- mcp_server/
|-- paradigms/
|-- prompts/
|   `-- prompts/
|-- providers/
|   `-- client.py
|-- pipelines/
|-- workflows/
|-- sessions/
|-- sources/
|-- trace/
|   |-- base.py
|   |-- debug.py
|   |-- session.py
|   `-- continual/
|-- middleware/
|   `-- builtins/
|-- tools/
|   |-- client.py
|   |-- catalog.py
|   |-- base.py
|   |-- registry.py
|   |-- executor.py
|   |-- builtins/
|   |-- mcp/
|   `-- security/
|-- shared/
`-- lib/
    |-- dataclasses/
    |-- registries/
    |-- runners/
    |-- tools/
    |-- enums/
    `-- errors/
```

## Public Boundary

The SDK should contain reusable public namespace scaffolding and developer-facing abstractions.

Private Vidbyte service implementations, proprietary learning evaluations, prompts, scoring logic, adaptive sequencing, and database access should stay outside this package.

## Local Verification

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import Agent, Tools, VidbyteSDK, tool; sdk = VidbyteSDK(); print(Agent.__name__, Tools.__name__, type(sdk.agents).__name__, callable(tool))"
```

## Contributing and Support

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and pull-request guidance. Use the
[bug report](https://github.com/cerredz/Vidbyte-SDK/issues/new?template=bug_report.yml) or
[feature request](https://github.com/cerredz/Vidbyte-SDK/issues/new?template=feature_request.yml)
forms for public project feedback.

Please report vulnerabilities privately according to [SECURITY.md](SECURITY.md). Participation in
the project is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Release history is available
from [GitHub Releases](https://github.com/cerredz/Vidbyte-SDK/releases), and design documentation is
kept under [docs](docs/).
