# Vidbyte SDK

Vidbyte is an agent engineering platform for building, evaluating, instrumenting,
and distributing AI workflows. The Vidbyte SDK is the Python package surface for
that platform: it gives developers composable agents, tools, middleware, context
management, MCP server integration, prompts, evals, provider adapters, pipelines,
and tracing primitives.

This repository is intentionally focused on reusable SDK abstractions. Private
Vidbyte service logic, proprietary learning systems, hosted scoring, and database
access remain outside this package.

## What You Can Build

- Agent applications with explicit system prompts, runners, tools, context, and trace behavior.
- Tool-using agents with local Python functions, MCP-backed tools, permission policies, and provider-native schemas.
- Runtime policies with deterministic middleware for rate limits, budgets, retries, audit logs, compaction, and safety checks.
- MCP Studio servers that expose Vidbyte agents, tools, prompts, and pipelines to MCP-compatible clients.
- Local eval suites with reusable graders, concurrency controls, and run registries.
- Agent pipelines that compose specialized agents through sequential, parallel, conditional, and map-reduce topologies.
- Prompt libraries, context-window algorithms, and trace artifacts that make long-running agent work easier to inspect.

## Layer Guide

| Layer | Role |
|-------|------|
| [`vidbyte.agents`](vidbyte/agents/README.md) | Executable agent actors, runtimes, modality routing, handoff, and agent registries |
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
| [`vidbyte.shared`](vidbyte/shared/README.md) | Reserved shared namespace; currently no stable public symbols |
| [`vidbyte.tools`](vidbyte/tools/README.md) | Tool contracts, decorators, catalogs, execution, MCP bridges, and permissions |
| [`vidbyte.trace`](vidbyte/trace/README.md) | Trace facade, debug tracer, provider tracers, and continual trace artifacts |

## Status

> **Alpha — active development.** APIs may change between minor versions.

Install from PyPI:

```bash
pip install vidbyte-sdk
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

## Agents and Modalities

Use agents as the public entry point for model execution. Agents infer execution
modality from the configured model name when possible, so callers normally pass
plain strings to `run()` and `arun()`. If the model name is unknown and no
explicit override is provided, execution falls back to text; prompt text is not
semantically classified.

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

Multi-agent execution is modeled as composition:

- `vidbyte.agents` contains actor objects such as `BaseAgent`, `AgentInput`, and `AgentRegistry`.
- Custom harnesses stay outside the base SDK until their public contracts are explicitly defined.

```python
from vidbyte import BaseAgent

agent = BaseAgent(
    name="researcher",
    system_prompt="Answer directly and cite uncertainty.",
    provider="openai",
    model_name="gpt-4.1",
)

reply = await agent.arun("Draft a concise release note")
```

For custom agents, pass an explicit `system_prompt`, model config, runner, and tools into `Agent` or `BaseAgent`.
Semantic labels such as roles belong in agent metadata when callers need them.

## Paradigm Harnesses

`vidbyte.paradigms` reserves the SDK namespace for future thin runnable paradigm
harnesses: high-level agentic engineering patterns that compose agents, tools,
context, prompts, middleware, trace, pipelines, and evals into an opinionated
execution loop. This release adds scaffolding only; no concrete paradigm
harnesses ship yet.

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
    runner=my_runner,
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
    runner=my_runner,
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
    runner=my_runner,
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
    runner=my_runner,
    tools=[lookup_metric],
    algorithm=ContextWindow.preset.problem_space_search,  # or ContextWindow.preset.error_correction
)
```

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
    runner=my_runner,
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
    runner=my_runner,
    trace=trace,
)
```

Provider-backed tracing uses the existing optional adapters:

```python
agent = Agent(
    name="observed-agent",
    system_prompt="Work carefully.",
    runner=my_runner,
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
    planner = Agent(name="planner", system_prompt="Plan the work.", runner=planner_runner, trace=trace)
    writer = Agent(name="writer", system_prompt="Draft the answer.", runner=writer_runner, trace=trace)
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
    runner=my_runner,
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
    runner=my_runner,
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
from vidbyte.tools.builtins.code_search import GrepTool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    """Look up one user's metric."""
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when they help answer precisely.",
    runner=my_runner,
    tools=[GrepTool(root_dir="."), lookup_metric],
    max_iterations=8,
    max_tokens=16_000,
)

reply = await agent.arun("Find where tools are formatted.")
```

The runtime builds the context window, appends a short agentic-loop prompt after the system prompt, sends tool schemas to the model, executes permitted tool calls, appends tool results back into the ordered message context, and repeats until the model calls the internal `isDone` tool. If the model returns ordinary text without a tool call, that text is preserved as assistant history and the loop continues. `max_iterations` and `max_tokens` are optional safeguards; `max_tokens` uses provider-reported usage when available.

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
    runner=my_runner,
    tools=[lookup_metric],
    middleware=[
        TenantPermissionMiddleware(db),
        ToolPolicyMiddleware(allow_tools={"lookup_metric"}),
        ToolResultCompactionMiddleware.truncate(max_chars=600),
    ],
)
```

Subclass `AgentMiddleware` and override only the hooks you need, such as `before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`, `after_tool_call`, `after_iteration`, or `after_run`. Built-ins are available from `vidbyte.middleware.builtins`, including `TokenBudgetMiddleware`, `TokenRateLimitMiddleware`, `RuntimeLimitMiddleware`, `ToolPolicyMiddleware`, `AuditLogMiddleware`, `ModelRetryMiddleware`, `ToolResultCompactionMiddleware`, `MessageHistoryCompactionMiddleware`, `SummaryCompactionMiddleware`, and `TraceReplacementCompactionMiddleware` (folds a continual-trace artifact back into history; e.g. `TraceReplacementCompactionMiddleware.keep_recent_tail(keep_last_groups=2)`). `TokenBudgetMiddleware(max_tokens=...)` is a hard cap by default; set `allow_final_response_over_budget=True` to permit one final over-budget model call with an injected instruction to answer immediately. This is separate from `Agent(max_tokens=...)`, which remains a runtime hard cap.

Compaction middleware supports deterministic provider-message pruning without hidden model calls. Examples include `trim_to_token_budget`, `trim_with_provider_boundaries`, `delete_messages`, `tool_output_sliding_window`, `clear_tool_results_except`, `head_tail_tool_preview`, `scrub_bloat`, `summary_with_backrefs`, `selective_prune`, `salience_score_eviction`, `query_relevance_filter`, and `context_snapshot_branch_trim`.

```python
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware

agent = Agent(
    name="bounded-agent",
    system_prompt="Keep working context compact.",
    runner=my_runner,
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
    runner=my_runner,
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

## Durable Sessions

Durable sessions are a harness-level primitive that make any agent persistent
with `continue`, `resume`, and `fork` over an append-only checkpoint DAG. The
agent stays pure — persistence lives in a `Session` wrapper, so it works for
every runtime. Attach an agent in one line:

```python
from vidbyte import Agent, Session

agent = Agent(name="researcher", system_prompt="Investigate carefully.", provider="openai", model_name="gpt-4.1")
session = Session(agent)                      # defaults to an in-memory store
reply = await session.arun("Investigate the failing test")
print(session.id, session.head)              # session id + latest checkpoint id
```

Sessions are also reachable through the harness namespace
(`sdk.harnesses.sessions.attach(agent, store=...)`). Resuming reconstructs the
agent from a checkpoint; because live runners, tools, and middleware cannot be
serialized, you re-supply them at resume time (the rehydration contract):

```python
from vidbyte.sessions import FileSessionStore

store = FileSessionStore(root="./.vidbyte/sessions")
session = Session(agent, store=store)
await session.arun("first step")

# later / cold process — re-supply non-serializable parts
session = Session.resume(store, session_id, tools=[grep], runner=my_runner)
session = Session.continue_(store, session_id, runner=my_runner)   # == resume(head)
branch = Session.fork_from(store, checkpoint_id, runner=my_runner) # new id + parent lineage
session.rewind(to=checkpoint_id)                                    # time-travel
session.edit(lambda history: history[:-1])                         # state editing
```

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
    CheckpointTool, ForkTool, RewindTool,
    ResumeReplaceTool, ResumeAppendTool, ResumeOutputTool, SessionTool,
)

agent = Agent(name="researcher", system_prompt="...", provider="openai", model_name="gpt-4.1",
              tools=[CheckpointTool(store), ForkTool(store), RewindTool(store),
                     ResumeReplaceTool(store), ResumeAppendTool(store), ResumeOutputTool(store),
                     SessionTool(store)])
session = Session(agent, store=store)
```

- `CheckpointTool` — snapshot the current thread (or copy an in-scope session's head as a labeled checkpoint).
- `ForkTool` — branch a new session from the current head or any in-scope checkpoint.
- `RewindTool` — time-travel the current session's head to an earlier checkpoint.
- `ResumeReplaceTool` — replace the current context window with another agent's thread state (own-thread: rewind).
- `ResumeAppendTool` — append another agent's full context window into the current one.
- `ResumeOutputTool` — append only another agent's final output; errors if that thread is not `COMPLETED`.
- `SessionTool` — central combined tool: `create_checkpoint` / `fork_current` / `list_my_runs` / `read_run`.

Persisting a checkpoint is fail-open: a store write failure is recorded in the
reply metadata but never ends the run.

## Prompts

Prompts are repository-backed text assets exposed through an enum-keyed accessor
and direct Python imports. The catalog currently includes 34 prompt assets across
13 families, including handoff, reflexion, evals, prompt templates, goals,
actor-runtime personas, and trajectory checkpoints.

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
vidbyte/
|-- client.py
|-- agents/
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
