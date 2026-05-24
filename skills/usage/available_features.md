# Available Features

Features, strategies, middleware, pipelines, tools, and orchestration primitives included out of the box in the Vidbyte SDK.

## Root SDK Client

The `VidbyteSDK` client is the top-level entry point to all namespace clients. Each sub-client provides access to a different subsystem of the SDK.

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
# sdk.agents       -> AgentClient        — create and manage agents
# sdk.tools        -> ToolsClient        — access and catalog tools
# sdk.strategies   -> StrategyClient     — browse available strategies
# sdk.harnesses    -> HarnessClient      — compose harness integrations
# sdk.providers    -> ProvidersClient    — manage model providers
```

## Strategies

Strategies control **how** an agent reasons through a prompt. They run inside the agent's execution loop and shape the reasoning process — from simple chain-of-thought to multi-agent consensus. You select a strategy based on the complexity of the task and the reasoning depth required.

### Reasoning Strategies

Reasoning strategies guide the model to think step-by-step before producing a final answer. Use them for tasks that require analysis, planning, or structured reasoning.

- **ChainOfThoughtStrategy** — The model generates explicit reasoning steps before its final response. Best for analytical tasks, math, and logic.
- **StepBackStrategy** — The model first extracts abstract principles from the question, then applies them. Best for questions that benefit from first-principles thinking.
- **ChainOfDraftStrategy** — A compact variant that produces minimal draft reasoning steps. Best when token budget is tight.
- **SkeletonOfThoughtStrategy** — Generates a skeletal outline first, then expands each section into a complete response. Best for long-form structured content.

```python
from vidbyte import (
    ChainOfThoughtStrategy,
    StepBackStrategy,
    ChainOfDraftStrategy,
    SkeletonOfThoughtStrategy,
)
```

Usage:
```python
agent = Agent(
    name="reasoner",
    system_prompt="You reason carefully.",
    strategy=ChainOfThoughtStrategy(),
    provider="openai",
    model_name="gpt-4.1",
)
```

### Sampling Strategies

Sampling strategies run the model multiple times and select, filter, or converge the results. Use them when you need consistency, reliability, or want to explore solution space.

- **SelfConsistencyStrategy** — Runs multiple independent samples and picks the most consistent answer. Best for ambiguous problems where a single sample might be wrong.
- **BudgetForcingStrategy** — Bounded retry attempts within a cost budget. Best when you want to try multiple times but cap spending.
- **AnswerConvergenceStrategy** — Repeats until successive answers converge. Best when you need a stable, reliable result.

```python
from vidbyte import (
    SelfConsistencyStrategy,
    BudgetForcingStrategy,
    AnswerConvergenceStrategy,
)
```

### Agent Loop Strategies

Agent loop strategies change the overall execution flow beyond single-prompt reasoning.

- **PlanAndExecuteStrategy** — The agent first creates a plan, then iterates through each step executing and refining. Best for multi-step tasks like software development.
- **SelfRefinementStrategy** — The agent creates a response, critiques it, then refines. Best for creative work that benefits from iterative improvement.

```python
from vidbyte import (
    PlanAndExecuteStrategy,
    SelfRefinementStrategy,
)
```

### Routing Strategies

Routing strategies dynamically select which paradigm or approach to use based on the prompt content.

- **ParadigmRouterStrategy** — Prompt-guided paradigm selection. The model itself decides which reasoning style to apply.

```python
from vidbyte import ParadigmRouterStrategy
```

### Other Single-Agent Strategies

- **TreeOfThoughtsStrategy** — Branches into multiple reasoning paths, evaluates each, and synthesizes the best. Best for creative problem-solving and exploration.
- **ReActStrategy** — Interleaves reasoning and tool actions in a loop. Best when the agent needs to interact with external tools.
- **CodeActStrategy** — An extension of ReAct that generates and executes code actions. Best for tasks requiring computation or code execution.
- **ReflexionStrategy** — Reflective retry: the agent reflects on failures and refines its approach. Best for self-correcting workflows.

```python
from vidbyte import (
    TreeOfThoughtsStrategy,
    ReActStrategy,
    CodeActStrategy,
    ReflexionStrategy,
)
```

## Multi-Agent Strategies

Multi-agent strategies orchestrate multiple agents working together — through consensus, conversation, verification, economic gating, or evolving selection. Use them when a single agent's perspective is insufficient and you want competing or collaborating viewpoints.

Import from `vidbyte.strategies.multi_agent`:

```python
from vidbyte.strategies.multi_agent import (
    MultiAgentConsensusStrategy,              # multiple candidates propose, evaluator picks best
    AutoGenConversationStrategy,              # AutoGen-style message passing between agents
    VerifiedMultiAgentOrchestrationStrategy,  # VMAO: plan → execute → verify with multiple agents
    EconomicGateStrategy,                     # cost-benefit routing: cheaper agents first, escalate if needed
    EvolvingOrchestrationStrategy,            # policy-driven agent selection that adapts over time
)
```

A multi-agent strategy is used the same way as any strategy — pass it to `Agent(strategy=...)`.

## Pipelines

Pipelines wire agents together by connecting outputs to inputs. Each pipeline stage is a fully-configured agent or another pipeline. Pipelines move strings between stages and do not manage shared context, budget, or artifacts — each agent carries its own configuration, strategy, tools, and history.

Use pipelines to compose multi-agent workflows where one agent's full output (including its strategy and tool calls) feeds into the next agent.

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

## Middleware

Middleware is **deterministic runtime policy code** that runs inside the agent execution loop. It observes, validates, filters, or transforms agent behavior at lifecycle hooks — but it is never exposed to the model. Middleware is injected on the agent constructor via `middleware=[...]`.

Use middleware for cross-cutting concerns that should not be part of the model's prompt or tool definitions: logging, rate limiting, content filtering, input validation, and guardrails.

### Lifecycle Hooks

| Hook | When Called | Returns |
|------|------------|---------|
| `before_model_call` | Before the model is invoked | `MiddlewareDecision` (ALLOW / BLOCK / SKIP) |
| `after_model_call` | After the model returns a response | `MiddlewareDecision` |
| `before_tool_call` | Before a tool is executed | `MiddlewareDecision` |
| `after_tool_call` | After a tool returns a result | `MiddlewareDecision` |

### Built-in Middleware

Built-in middleware lives under `vidbyte/middleware/builtins/` and provides common policies out of the box:
- **Logging middleware** — Records all model calls, tool calls, and results for audit trails.
- **Rate limiting middleware** — Caps the number of tool calls or model invocations per time window.
- **Content filtering middleware** — Blocks or sanitizes model outputs that match forbidden patterns.
- **Input/Output validation middleware** — Validates tool call arguments and tool results against schemas.

### Building Custom Middleware

Subclass `AgentMiddleware` and override only the hooks you need:

```python
from vidbyte import AgentMiddleware, MiddlewareDecision

class CustomGuardMiddleware(AgentMiddleware):
    async def before_tool_call(self, call):
        if "dangerous" in str(call.arguments):
            return MiddlewareDecision.BLOCK
        return MiddlewareDecision.ALLOW

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

## Prompt Collection

The SDK includes a built-in prompt catalog with 15 prompt families covering reasoning, planning, orchestration, and more. Prompts are repository-backed text assets accessible through enum keys and direct Python imports — no API keys or network calls needed.

### Accessing Prompts

Prompts can be accessed two ways:

1. **Via `Prompts.get()` with enum keys:**
   ```python
   from vidbyte import Prompts, Prompt
   text = Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)
   ```

2. **Via direct string imports:**
   ```python
   from vidbyte.prompts import chain_of_thought_reason_prompt
   ```

### Using Prompts with Agents

Prompts are designed to be used as system prompts or task prompts on agents:

```python
from vidbyte import Agent, Prompts, Prompt

prompts = Prompts()
agent = Agent(
    name="reasoner",
    system_prompt=prompts.get(Prompt.CHAIN_OF_THOUGHT_SYSTEM_PROMPT),
    provider="openai",
    model_name="gpt-4.1",
)
reply = await agent.arun(prompts.get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT))
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
# TIGHT:       3 model calls,   4k tokens,  30s timeout
# BALANCED:    8 model calls,  16k tokens, 120s timeout
# EXPLORATORY: 20 model calls, 64k tokens, 300s timeout

# Permission presets control what the agent can do
permissions = ContextPermissions.from_preset(PermissionPreset.READ_ONLY)
# READ_ONLY:  can read files, no tools, no write
# TOOLS_ONLY: tools allowed, no filesystem access
# TRUSTED:    full access — read, write, execute
```

## Provider Support

The SDK supports multiple model providers through a unified interface. Switch providers by changing a single parameter — no code changes needed.

```python
from vidbyte import ModelProvider

ModelProvider.OPENAI      # GPT-4, GPT-4o, O1, O3, etc.
ModelProvider.ANTHROPIC   # Claude 3.5 Sonnet, Claude 3 Opus, etc.
ModelProvider.GEMINI      # Gemini 1.5 Pro, Gemini 1.5 Flash, etc.
ModelProvider.XAI         # Grok models
ModelProvider.DEEPSEEK    # DeepSeek V3, DeepSeek R1, etc.
ModelProvider.GLM         # GLM models
ModelProvider.MINIMAX     # MiniMax models
```

## Agent Forking

Create variant agents from a base without re-declaring all configuration. Forking copies the parent's configuration while allowing overrides — useful for creating specialized agents that share the same foundation.

```python
child = agent.fork(name="child", temperature=0.1)                # override any kwarg
child_with_context = agent.fork(include_history=True, name="ctx") # copies message history
```

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

## Strategy Composability

`StrategyMixin` allows hosts to compose multiple strategies together. Harnesses and other hosts use `with_strategy()` and `with_strategies()` to attach one or more strategies programmatically, enabling flexible strategy layering.

```python
from vidbyte import StrategyMixin

# Harnesses and other hosts use with_strategy() / with_strategies()
# to attach one or more strategies programmatically.
```

## Error Hierarchy

The SDK has a structured error hierarchy so you can catch errors at the right level of granularity:

```python
from vidbyte import (
    VidbyteSdkError,             # base — catch-all for SDK errors
    AgentExecutionError,         # agent failures during arun/run
    PipelineExecutionError,      # pipeline construction or runtime failures
    StrategyExecutionError,      # strategy execution failures
    ToolExecutionError,          # tool runtime errors (invalid args, execution failure)
    PermissionDeniedError,       # permission policy violations
    ConfigurationError,          # invalid agent or SDK configuration
    McpError,                    # MCP base error (connection, transport, protocol)
    # ... and more
)
```

All errors inherit from `VidbyteSdkError` so you can catch the base class if you don't need fine-grained handling.
