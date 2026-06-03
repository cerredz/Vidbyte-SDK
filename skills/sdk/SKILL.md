# Vidbyte SDK

## Paradigm

The Vidbyte SDK is a **Python-native agent framework**. Every interaction follows the same core loop:

1. **Define an Agent** — name, system prompt, model provider, and optional strategy, tools, permissions, or middleware.
2. **Send a Prompt** — a plain string or a typed `AgentInput` with optional modality routing.
3. **Receive a Reply** — an `AgentMessage` with content, sender, recipient, and metadata.

Agents own their execution context: tools, strategy, middleware, history, budget, permissions, and modality routing. Pipelines wire agents together without shared state — they move strings between fully-configured agents.

## Framework Boundaries

| Layer | Responsibility | Key Types |
|-------|---------------|-----------|
| **Agent** | Single model-backed actor with tools, strategy, middleware, and history | `Agent`, `AgentInput`, `AgentMessage`, `AgentCard` |
| **Tool** | Callable capability exposed to the model during execution | `@tool`, `BaseTool`, `Tools`, `ToolSpec`, `ToolCall` |
| **Strategy** | Reasoning/orchestration pattern running inside an agent's loop | `ChainOfThoughtStrategy`, `ReActStrategy`, `MultiAgentConsensusStrategy` |
| **Pipeline** | String-in/string-out wiring between agents (sequential, parallel, conditional, map-reduce) | `SequentialPipeline`, `ParallelPipeline`, `ConditionalPipeline`, `MapReducePipeline` |
| **Middleware** | Deterministic runtime policy code injected into the agent loop; not model-visible | `AgentMiddleware`, `MiddlewareDecision`, built-in middleware under `vidbyte/middleware/builtins/` |
| **Prompt** | Repository-backed text assets, enum-keyed, importable as constants | `Prompts`, `Prompt`, direct string imports |
| **Context** | Runtime budget, permissions, history, artifacts per agent execution | `BaseContext`, `ContextBudget`, `ContextPermissions` |
| **Provider** | Model provider adapters (OpenAI, Anthropic, Gemini, xAI, DeepSeek, GLM, MiniMax) | `ModelProvider`, provider adapters |

## Core Use Cases

- **Single agent with tools**: Wrap a model with custom Python functions it can call during execution.
- **Multi-agent orchestration**: Consensus, AutoGen-style conversation, VMAO, economic gating, evolving selection.
- **Pipelined workflows**: Chain agents sequentially, run them in parallel, route conditionally, or fan-out/fan-in with map-reduce.
- **Reasoning strategies**: Chain-of-thought, step-back, skeleton-of-thought, tree-of-thoughts, reflexion, ReAct, CodeAct.
- **Middleware injection**: Inject deterministic runtime policies (logging, guardrails, rate limiting) via `middleware=[...]` on agents.
- **MCP integration**: Attach external MCP servers as tools to any agent.
- **Modality routing**: Route requests to text, image, or video models automatically or explicitly.
- **Built-in tools**: Code search (glob, grep, semantic), code execution, filesystem operations, document retrieval, context compaction, patch editing.
- **Prompt management**: Access 15 prompt families through enum keys and direct Python imports.

## Middleware

Middleware is **deterministic runtime policy code** injected into the agent loop. It is not exposed to the model, not included in tool specs or agent cards, and must not mutate runtime state directly. Middleware observes, validates, or transforms agent behavior at each lifecycle hook.

### Lifecycle Hooks

`AgentMiddleware` exposes hooks at key points in the agent execution loop:

| Hook | Called When | Use Case |
|------|------------|----------|
| `before_tool_call` | Before the model's tool call is executed | Logging, argument validation, rate limiting |
| `after_tool_call` | After a tool returns a result | Sanitize outputs, enforce output schemas |
| `before_model_call` | Before the model is invoked | Inject system-level context, audit logging |
| `after_model_call` | After the model returns a response | Content filtering, guardrails |

### Building Custom Middleware

Subclass `AgentMiddleware` and override the hooks you need:

```python
from vidbyte import AgentMiddleware, MiddlewareDecision

class RateLimitingMiddleware(AgentMiddleware):
    """Limit tool calls to a maximum per minute."""

    def __init__(self, max_calls_per_minute: int = 60):
        self._max_calls = max_calls_per_minute
        self._call_times: list[float] = []

    async def before_tool_call(self, call):
        now = time.time()
        self._call_times = [t for t in self._call_times if now - t < 60]
        if len(self._call_times) >= self._max_calls:
            return MiddlewareDecision.BLOCK
        self._call_times.append(now)
        return MiddlewareDecision.ALLOW
```

### Attaching Middleware

Middleware is injected directly on the agent constructor:

```python
agent = Agent(
    name="guarded-agent",
    system_prompt="You are helpful.",
    provider="openai",
    model_name="gpt-4.1",
    middleware=[RateLimitingMiddleware(max_calls_per_minute=30)],
)
```

### MiddlewareDecision Values

| Decision | Meaning |
|----------|---------|
| `ALLOW` | Proceed normally |
| `BLOCK` | Stop execution, raise `MiddlewareBlockedError` |
| `SKIP` | Skip this operation silently |

### Built-in Middleware

Built-in middleware lives under `vidbyte/middleware/builtins/` and includes common policies like logging, rate limiting, content filtering, and input/output validation.

## Usage Skill Files

For step-by-step instructions on specific SDK operations, see the usage skill files:

| Skill | File | Description |
|-------|------|-------------|
| Create Agent | [`skills/usage/create_agent.md`](../usage/create_agent.md) | Constructor, run/arun, modality routing, forking |
| Create Tool | [`skills/usage/create_tool.md`](../usage/create_tool.md) | `@tool` decorator, `BaseTool` subclass, `Tools` catalog |
| Create Agent with Tools | [`skills/usage/create_agent_with_tools.md`](../usage/create_agent_with_tools.md) | Attaching tools to agents, permission policy, built-in tools |
| Import Prompt | [`skills/usage/import_prompt.md`](../usage/import_prompt.md) | `Prompts.get()`, direct imports, prompt families, full prompt listing |
| Create Agents | [`skills/usage/create_agents.md`](../usage/create_agents.md) | `AgentRegistry`, multi-agent patterns, capability metadata |
| Create Pipeline | [`skills/usage/create_pipeline.md`](../usage/create_pipeline.md) | Sequential, parallel, conditional, map-reduce pipelines, nesting |
| Available Tools | [`skills/usage/available_tools.md`](../usage/available_tools.md) | Complete catalog of built-in tools (code search, filesystem, MCP) |
| Available Features | [`skills/usage/available_features.md`](../usage/available_features.md) | Strategies, pipelines, middleware, modalities, budgets, providers, MCP, prompts |

## SDK Developer Reference

| Doc | File | Description |
|-----|------|-------------|
| SDK Structure & Rules | `skills/sdk/SKILL.md` (this file) | Package layout, module rules, development guardrails |
| Updating Skill Files | [`skills/sdk/update-skill-files.md`](update-skill-files.md) | When and how to update skill files after repo changes |
| Adding Prompts | [`skills/vidbyte-sdk/adding-prompts.md`](../vidbyte-sdk/adding-prompts.md) | How to add prompt JSON assets, enums, and imports |
| Pipelines (detailed) | [`skills/vidbyte-sdk/pipelines.md`](../vidbyte-sdk/pipelines.md) | Full pipeline reference (topologies, composability, error handling) |
| Full SDK Reference | [`skills/vidbyte-sdk-doc/SKILL.md`](../vidbyte-sdk-doc/SKILL.md) | Exhaustive reference for all subsystems |

---

## Package Structure

Use this reference when modifying the Vidbyte SDK package structure.

### Current Layout

```text
vidbyte/
|-- __init__.py
|-- client.py
|-- agents/
|-- context/
|-- harnesses/
|   `-- client.py
|-- prompts/
|   `-- prompts/
|-- providers/
|   `-- client.py
|-- trace/
|-- pipelines/
|   |-- __init__.py
|   |-- base.py
|   |-- conditional.py
|   |-- map_reduce.py
|   |-- parallel.py
|   |-- sequential.py
|   `-- types.py
|-- middleware/
|   `-- builtins/
|-- strategies/
|   `-- multi_agent/
|-- tools/
|   `-- client.py
|-- shared/
`-- lib/
    |-- dataclasses/
    |-- runners/
    |-- tools/
    |-- enums/
    `-- errors/
```

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Keep agent actor abstractions in `vidbyte/agents/`.
- Keep reasoning and orchestration topologies in `vidbyte/strategies/`.
- Keep multi-agent orchestration implementations in `vidbyte/strategies/multi_agent/`.
- Keep agent-to-agent wiring topologies (pipeline compositions) in `vidbyte/pipelines/`. Pipelines move strings between agents; they do not manage context, budget, or artifacts. Follow `skills/vidbyte-sdk/pipelines.md` when adding or modifying pipeline topology types.
- Keep public context objects in `vidbyte/context/`, but define dataclasses centrally under `vidbyte/lib/dataclasses/`.
- Keep prompt templates in `vidbyte/prompts/prompts/` and expose them through `vidbyte.prompts.Prompts` plus `vidbyte.lib.enums.prompts.Prompt`.
- Follow `skills/vidbyte-sdk/adding-prompts.md` whenever adding or changing prompt assets.
- Keep public trace presets and helper factories under `vidbyte/trace/`.
- Keep provider-neutral tracer protocols under `vidbyte/lib/tracing/`.
- Keep external tracing provider adapters under `vidbyte/providers/tracing/`.
- Keep enum presets under `vidbyte/lib/enums/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK dataclass definitions under `vidbyte/lib/dataclasses/`; package-local type modules should re-export those contracts when stable imports are needed.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep provider-neutral tool formatting helpers under `vidbyte/lib/tools/`.
- Keep middleware runtime policy code under `vidbyte/middleware/`; built-in middleware belongs under `vidbyte/middleware/builtins/`.
- Keep middleware dataclass contracts under `vidbyte/lib/dataclasses/middleware.py`; public middleware modules should re-export stable contracts.
- Keep concrete text/image/video model runners under `vidbyte/lib/runners/`; they are internal or advanced implementation details, not the preferred user-facing docs surface.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Advanced tools are approved under `vidbyte/tools/` when they follow the shared `BaseTool`, `ToolSpec`, `Tools`, and agent-local execution contracts. `ToolRegistry` and `ToolExecutor` are compatibility/lower-level strategy infrastructure, not the preferred public workflow.
- Keep built-in tool categories under `vidbyte/tools/builtins/`; current approved categories are `code_search`, `editing`, `context`, `calculator`, `code_execution`, `document_retrieval`, and `filesystem` via `vidbyte/tools/filesystem/`.
- Keep MCP bridge code under `vidbyte/tools/mcp/`.
- Keep permission and sandbox abstractions under `vidbyte/tools/security/`.
- Mutating or executable tools must declare `WRITE` or `EXECUTE` permissions and be guarded by the agent or compatibility executor permission policy.
- Harnesses should compose strategies through `with_strategy()` and `with_strategies()` rather than exposing single-agent or multi-agent flags.
- Agents package modality routing, model runners, model configuration, strategies, middleware, user-defined role/capability metadata, system prompts, and tools. User-facing examples should pass tools directly into `Agent`/`BaseAgent` with `tools=[...]`.
- User-facing examples should prefer `Agent`/`BaseAgent`, `AgentInput`, `ModelModality`, `VidbyteSDK().agents`, or harness composition instead of direct `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` construction.
- Base contexts should expose `build_context()` and keep file content, tool calls, model responses, memory, permissions, artifacts, budget, and strategy progress metadata distinct.
- Tools are injected into agents or strategies; avoid global mutable tool state for orchestration. Prefer `@tool` and `Tools(...)` for new public examples; keep `@vidbyte_tool`, `ToolRegistry`, and `ToolExecutor` references for compatibility notes only.
- Middleware is injected into agents with `middleware=[...]`; it is deterministic runtime policy code and must not be model-visible or included in tool specs/cards.
- Custom middleware should subclass `AgentMiddleware` and override only needed lifecycle hooks. Middleware should return `MiddlewareDecision` values instead of mutating runtime state directly.
- Concrete `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner` classes are internal/advanced implementation details in user-facing docs. Prefer `Agent`/`BaseAgent` or harness composition in examples.
- Do not add provider network calls, remote protocol transports, or private Vidbyte service logic without a separate approved design.

## Update Skill Files

When you modify the repo, follow `skills/sdk/update-skill-files.md` to know which skill files must be updated and what to include in each update.

