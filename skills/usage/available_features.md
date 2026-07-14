# Available Features

## Durable long-running paradigm

`LongRunningParadigm` handles broad multi-stage goals with a validated dependency
DAG, one fresh context per role call, independently verified task results, global
drift review, downstream invalidation, finite retry/replan/finalization budgets,
and append-only resumable state.

```python
from vidbyte import LongRunningParadigm, LongRunningRunOptions

result = LongRunningParadigm().run(
    "Complete the broad goal.",
    run_options=LongRunningRunOptions(
        success_criteria=("Every required outcome has evidence.",),
    ),
)
```

Use `FileRunLedgerStore` and `FileProcedureStore` for process-restart durability.
Only verified, aligned, fidelity-checked procedures become retrievable across
runs. Non-read worker tools require an `AttemptIsolator` or an explicit unsafe
opt-in, which still stops on ambiguous rejected/interrupted side effects.

Features, runtimes, middleware, pipelines, tools, durable sessions, artifact sources, and orchestration primitives included out of the box in the Vidbyte SDK.

## Root SDK Client

The `VidbyteSDK` client is the top-level entry point to all namespace clients. Each sub-client provides access to a different subsystem of the SDK.

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
# sdk.agents       -> AgentClient        — create and manage agents
# sdk.tools        -> ToolsClient        — access and catalog tools
# sdk.harnesses    -> HarnessClient      — compose harness integrations
# sdk.providers    -> ProvidersClient    — manage model providers
```

## Pipelines

Pipelines wire agents together by connecting outputs to inputs. Each pipeline stage is a fully-configured agent or another pipeline. Pipelines move strings between stages and do not manage shared context, budget, or artifacts — each agent carries its own configuration, runtime, tools, and history.

Use pipelines to compose multi-agent workflows where one agent's full output (including runtime/tool-call results) feeds into the next agent.

### Pipeline Types

| Pipeline | Pattern | Behavior |
|----------|---------|----------|
| `SequentialPipeline` | Chain | Stages run in order — output of stage N becomes the prompt for stage N+1 |
| `ParallelPipeline` | Fan-out | All stages run concurrently with the same input — outputs joined with a separator |
| `ConditionalPipeline` | Route | A predicate inspects the prompt and routes to the appropriate branch agent |
| `MapReducePipeline` | Fan-out → Fan-in | Map stages run concurrently on the same input, then a reduce stage synthesizes their joined output |
| `BasePipeline` | Custom | Abstract base — inherit to build custom pipeline topologies |

### Chaining Patterns

**Sequential (Chain):** A planning agent's output drives a coding agent, whose output drives a testing agent. Each stage builds on the previous.

**Parallel (Fan-out):** The same problem is given to three agents with different approaches (functional, OOP, data-oriented). Their outputs are combined into one analysis.

**Conditional (Route):** A classifier inspects the prompt — if it's a coding task, route to the coding agent; if it's a research task, route to the research agent.

**Map-Reduce (Fan-out → Fan-in):** Multiple agents each analyze a different aspect of the input concurrently, then a reducer agent synthesizes all their findings into a single answer.

```python
from vidbyte import (
    SequentialPipeline,
    ParallelPipeline,
    ConditionalPipeline,
    MapReducePipeline,
    BasePipeline,
)
```

For detailed usage examples, see [`skills/usage/create_pipeline.md`](create_pipeline.md).

## Ledger-Driven Multi-Agent Teams

`MultiAgent` is a `BaseAgent`-compatible facade for open-ended work that needs a manager to own the overall goal, delegate ready tasks, evaluate evidence, and replan after stalls or failures. Unlike a pipeline, a team shares an immutable view of a run-local `TaskLedger` and can choose a different next action after every worker report.

Developers keep fine-grained control over the worker boundary with `AgentBinding` and `AgentTransfer`: request builders decide what each worker receives, report parsers decide what comes back, and validators decide whether evidence is verified. `MultiAgentSettings` bounds rounds, retries, stalls, replans, events, and timeouts.

```python
from vidbyte import Agent, AgentBinding, AgentTransfer, MultiAgent, MultiAgentSettings

team = MultiAgent(
    name="delivery-team",
    system_prompt="Own the goal, delegate bounded tasks, and finish from verified evidence.",
    orchestrator=Agent(name="manager", system_prompt="Manage the task ledger.", provider="openai", model_name="gpt-4.1"),
    agents=[
        AgentBinding(
            Agent(name="researcher", system_prompt="Research assigned tasks.", provider="openai", model_name="gpt-4.1"),
            transfer=AgentTransfer(),
        )
    ],
    settings=MultiAgentSettings(max_rounds=12, replan_after_stalls=2),
)

reply = await team.arun("Produce an evidence-backed launch recommendation.")
```

The facade intentionally does not support tools, MCP attachment, structured output, or durable sessions; configure those capabilities on manager and worker agents. See [`skills/vidbyte-sdk/multi-agent.md`](../vidbyte-sdk/multi-agent.md) for contracts, lifecycle, custom payloads, gates, and error behavior.

## Middleware

Middleware is **deterministic runtime policy code** that runs inside the agent execution loop. It observes, validates, filters, or transforms agent behavior at lifecycle hooks — but it is never exposed to the model. Middleware is injected on the agent constructor via `middleware=[...]`.

Use middleware for cross-cutting concerns that should not be part of the model's prompt or tool definitions: logging, rate limiting, content filtering, input validation, and guardrails.

### Lifecycle Hooks

Each hook receives a read-only `MiddlewareContext` and returns a `MiddlewareDecision`. There are nine hooks across the run:

| Hook | When Called |
|------|------------|
| `before_run` | Before the runtime starts |
| `before_iteration` | Before each loop iteration |
| `before_model_call` | Before the model is invoked |
| `after_model_response` | After a successful model response |
| `on_model_error` | When a model call raises |
| `before_tool_call` | Before a tool is executed |
| `after_tool_call` | After a tool returns or is denied |
| `after_iteration` | After each loop iteration |
| `after_run` | Before the final result is returned |

Decisions: `MiddlewareDecision.continue_()`, `abort(reason)`, `deny_tool(reason)` (in `before_tool_call`), `retry(reason)` (in `on_model_error`), and `sleep(seconds)`.

### Built-in Middleware

Built-in middleware lives under `vidbyte/middleware/builtins/`. Security/defense: `CanaryTripwireMiddleware`, `ConfusedDeputyGuardMiddleware`, `HoneypotToolMiddleware`. Budgets: `TokenBudgetMiddleware`, `CostBudgetMiddleware`. Reliability: `ModelRetryMiddleware`, `ExponentialBackoffRetryMiddleware`, `CircuitBreakerMiddleware`, `ToolErrorPolicyMiddleware`. Safety/observability: `LoopDetectionMiddleware`, `RuntimeLimitMiddleware`, `ToolPolicyMiddleware`, `TokenRateLimitMiddleware`, `AuditLogMiddleware`. Compaction: `ToolResultCompactionMiddleware`, `MessageHistoryCompactionMiddleware`, `SummaryCompactionMiddleware`. See [`skills/vidbyte-sdk/middleware.md`](../vidbyte-sdk/middleware.md) for the full catalog and arguments.

> Context compaction is **middleware**, not a tool. Use the compaction middlewares above; the legacy `ContextCompactionTool` is for manual/legacy flows only.

### Tool Error Policy

`AgentLoopSettings(tool_error_policy=ToolErrorPolicy(...))` auto-registers `ToolErrorPolicyMiddleware` on compatible agent loops. The policy retries transient tool failures, gates retries to idempotent tools by default, applies exponential backoff, enforces optional max total tool errors, and can continue or abort on terminal failures. Terminal tool errors are rendered with full detail; there is no separate verbosity/render-options API.

```python
from vidbyte import Agent
from vidbyte.agents import AgentLoopSettings, ToolErrorPolicy

agent = Agent(
    name="robust-worker",
    system_prompt="Use tools carefully.",
    provider="openai",
    model_name="gpt-4.1",
    agent_loop_settings=AgentLoopSettings(
        tool_error_policy=ToolErrorPolicy(max_retries_per_tool_call=2),
    ),
)
```

### Building Custom Middleware

Subclass `AgentMiddleware` and override only the hooks you need:

```python
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision

class CustomGuardMiddleware(AgentMiddleware):
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        if ctx.tool_call and "dangerous" in str(ctx.tool_call.arguments):
            return MiddlewareDecision.deny_tool(reason="blocked dangerous argument")
        return MiddlewareDecision.continue_()

agent = Agent(
    name="guarded",
    system_prompt="You are helpful.",
    provider="openai",
    model_name="gpt-4.1",
    middleware=[CustomGuardMiddleware()],
)
```

## Tools

The SDK includes a rich catalog of built-in tools and a framework for building your own. Tools are callable capabilities that the model can invoke during execution — they extend what an agent can do beyond text generation.

### Built-in Tools

The SDK ships with prebuilt tool categories covering code search, code execution, filesystem operations, document retrieval, context compaction, patch editing, and calculation. These are ready to attach to any agent.

For a complete catalog of every built-in tool, see [`skills/usage/available_tools.md`](available_tools.md).

### Building Custom Tools

Create your own tools using the `@tool` decorator or by subclassing `BaseTool`. Custom tools can wrap any Python function — API calls, database queries, file operations, or computation. For detailed instructions, see [`skills/usage/create_tool.md`](create_tool.md).

**Decorator (simple):**
```python
from vidbyte import tool

@tool
def get_stock_price(symbol: str) -> float:
    """Get the current stock price for a symbol."""
    return fetch_from_api(symbol)
```

**BaseTool subclass (advanced):**
```python
from vidbyte import BaseTool, ToolSpec, ToolCall, ToolResult

class StockPriceTool(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(name="stock_price", description="Get stock price", ...)

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(self.name, fetch_from_api(call.arguments["symbol"]))
```

## Durable Sessions

Durable sessions persist agent state as a checkpoint DAG through `Session`, `SessionStore`, and `SessionScope`. They support per-turn or manual checkpoints, cold-process resume, rewind/edit, single and batch fork, cross-thread resume, tags/name resolution, usage rollups, trace capture, and portable zip export/import.

```python
from vidbyte import Agent, FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")
agent = Agent(name="researcher", system_prompt="...", provider="openai", model_name="gpt-4.1")
session = agent.persist(store=store)

await session.arun("start the research")
branches = session.batch_fork(3)
session.tag("research-main")
bundle = session.export()
usage = session.usage()
```

Attach session tools such as `CheckpointTool`, `ForkTool`, `BatchForkTool`, `RewindTool`, `ResumeAppendTool`, `ResumeOutputTool`, `ResumeReplaceTool`, and `SessionTool` when the model itself should manipulate durable threads.

## Artifact Sources and Repository Artifacts

The `vidbyte.sources` package provides deterministic artifact-to-context loaders and fetchers for public documents such as `llms.txt`. Repository artifacts also include `artifacts/file_index.md`, a generated source map for fast agent navigation across SDK packages, tests, skills, prompts, and design docs.

Use sources when a caller needs explicit trust boundaries, content hashing, caching, or selection over external or repository-backed documents.

## Prompt Collection

The SDK includes a built-in prompt catalog with 51 prompts across 19 prompt families covering orchestration, handoffs, reflexion, actor-runtime personas, goals, evals, templates, and more. Prompts are repository-backed text assets accessible through enum keys and direct Python imports — no API keys or network calls needed.

### Accessing Prompts

Prompts can be accessed two ways:

1. **Via `Prompts.get()` with enum keys:**
   ```python
   from vidbyte import Prompts, Prompt
   text = Prompts().get(Prompt.GOALS_GOAL_PROMPT)
   ```

2. **Via direct string imports:**
   ```python
   from vidbyte.prompts import goals_goal_prompt
   ```

### Using Prompts with Agents

Prompts are designed to be used as system prompts or task prompts on agents:

```python
from vidbyte import Agent, Prompts, Prompt

prompts = Prompts()
agent = Agent(
    name="goal-driven",
    system_prompt=prompts.get(Prompt.GOALS_GOAL_PROMPT),
    provider="openai",
    model_name="gpt-4.1",
)
reply = await agent.arun(prompts.get(Prompt.CONTEXT_ENGINEERING_GUIDELINE_PROMPT))
```

For a complete listing of every available prompt, prompt family, and import name, see [`skills/usage/import_prompt.md`](import_prompt.md).

## Modality Routing

Agents auto-detect and route to the correct runner by modality. The SDK supports text, image, and video generation through a unified agent interface — you don't need separate agent instances per modality.

```python
from vidbyte import ModelModality

ModelModality.AUTO   # detect from model name or input (default)
ModelModality.TEXT   # force text generation
ModelModality.IMAGE  # force image generation
ModelModality.VIDEO  # force video generation

# Set default modality on agent
agent = Agent(..., modality=ModelModality.TEXT)

# Override per-call
reply = await agent.arun(AgentInput("Create a logo", modality=ModelModality.IMAGE))
```

## Context Budgets & Permissions

Context budgets and permissions control resource consumption and agent capabilities at runtime. They are configured per-agent and enforced during execution.

- **Budgets** limit token usage, call counts, and execution time. Choose from `TIGHT`, `BALANCED`, or `EXPLORATORY` presets.
- **Permissions** control what an agent can do — read files, use tools, execute code. Choose from `READ_ONLY`, `TOOLS_ONLY`, or `TRUSTED` presets.

```python
from vidbyte import ContextBudget, ContextPermissions, BudgetPreset, PermissionPreset

# Budget presets control resource consumption
budget = ContextBudget.from_preset(BudgetPreset.BALANCED)
# TIGHT:       small model-call / token / time budget
# BALANCED:    moderate budget (default for most agents)
# EXPLORATORY: large budget for long-running work
# UNBOUNDED:   no budget limits

# Permission presets control what the agent can do
permissions = ContextPermissions.from_preset(PermissionPreset.READ_ONLY)
# SANDBOXED:  most restrictive — no reads, no tools, no write
# READ_ONLY:  can read files, no tools, no write
# TOOLS_ONLY: tools allowed, no filesystem access
# TRUSTED:    full access — read, write, execute
```

## Provider Support

The SDK supports multiple model providers through a unified interface. Switch providers by changing a single parameter — no code changes needed.

```python
from vidbyte.lib.enums import ModelProvider

ModelProvider.OPENAI      # GPT-4, GPT-4o, O-series, etc.
ModelProvider.ANTHROPIC   # Claude Opus, Sonnet, Haiku, etc.
ModelProvider.GEMINI      # Gemini Pro / Flash, etc.
ModelProvider.XAI         # Grok models
ModelProvider.DEEPSEEK    # DeepSeek V3, DeepSeek R1, etc.
ModelProvider.GLM         # GLM models
ModelProvider.MINIMAX     # MiniMax models
ModelProvider.OPENROUTER  # OpenRouter-hosted models (OpenAI-compatible)
ModelProvider.ELEVENLABS  # ElevenLabs (audio)
ModelProvider.PLAYAI      # PlayAI (audio)
```

## Agent Forking

Create variant agents from a base without re-declaring all configuration. Forking copies the parent's configuration while allowing overrides — useful for creating specialized agents that share the same foundation.

```python
child = agent.fork(name="child", temperature=0.1)                # override any kwarg
child_with_context = agent.fork(include_history=True, name="ctx") # copies message history
```

`ForkConversationTool` exposes immediate child execution to the model while keeping the same non-escalation rules as `BaseAgent.fork(...)`: model changes must be allowlisted, extra tools must come from developer-provided toolsets, permission policy is inherited, and child state stays isolated unless its returned answer is incorporated into the parent.

## MCP Server Attachment

Attach external MCP (Model Context Protocol) servers to agents at runtime. MCP servers expose tools (filesystem, database, APIs) that the agent can call as if they were native SDK tools.

```python
# Async attachment — connects immediately
agent = await Agent(name="mcp-agent", system_prompt="...").attach_mcp_server(
    ["python", "my_server.py"],
    name="my-server",
)

# Sync builder — lazy connection on first arun
agent = Agent(name="mcp-agent", system_prompt="...").with_mcp_server(
    ["python", "my_server.py"],
    name="my-server",
)

# Cleanup
await agent.close_mcp_servers()
```

## Error Hierarchy

The SDK has a structured error hierarchy so you can catch errors at the right level of granularity:

```python
from vidbyte.lib.errors import (
    VidbyteSdkError,             # base — catch-all for SDK errors
    AgentExecutionError,         # agent failures during arun/run
    PipelineExecutionError,      # pipeline construction or runtime failures
    ToolExecutionError,          # tool runtime errors (invalid args, execution failure)
    PermissionDeniedError,       # permission policy violations
    ConfigurationError,          # invalid agent or SDK configuration
    McpError,                    # MCP base error (connection, transport, protocol)
    # ... and more
)
```

All errors inherit from `VidbyteSdkError` so you can catch the base class if you don't need fine-grained handling.
