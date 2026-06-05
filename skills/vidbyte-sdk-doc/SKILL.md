---
name: vidbyte-sdk-doc
description: Comprehensive reference for the Vidbyte SDK repository, including public APIs, package layout, design docs, subsystem responsibilities, contribution guardrails, and verification commands.
---

# Vidbyte SDK Doc

## When To Use This Skill

Use this skill when working inside the `vidbyte-sdk` repository and you need the complete local map of what the SDK offers, where code belongs, how the design docs relate to the current implementation, and what to verify before handing off changes.

This skill is a repository reference, not a replacement for reading the code. Current source and tests are authoritative. Design docs explain intent and history, but some docs are historical or superseded by later API consolidation.

## Source Of Truth

Read sources in this order when making a change:

1. Current code under `vidbyte/`.
2. Tests under `tests/`.
3. `README.md` and existing skill docs under `skills/`.
4. Design docs under `docs/design/`.

When these sources disagree, trust current code and tests first. Use design docs to understand why a subsystem exists, what risks were considered, and what public compatibility guarantees were intended.

Do not claim a feature exists just because a design doc describes it. Confirm the implementation exists under `vidbyte/` or `tests/` first.

## Repository Snapshot

- Package name: `vidbyte-sdk`.
- Root Python package: `vidbyte`.
- Python requirement: `>=3.11`.
- Build backend: `setuptools.build_meta`.
- Runtime dependency in `pyproject.toml`: `pydantic>=2,<3`.
- Package data: JSON prompt files under `vidbyte.prompts.prompts`.
- Test framework: Python `unittest`.
- Normal verification:
  - `python -m compileall vidbyte`
  - `python -m unittest discover -s tests`
  - `python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.agents).__name__)"`
- Public boundary: reusable SDK abstractions only. Private Vidbyte service logic, proprietary evaluations, customer data, database access, and private scoring logic stay outside this package.

## Package Map

```text
vidbyte/
|-- __init__.py          Root public exports.
|-- client.py            VidbyteSDK namespace client.
|-- agents/              Agent actors, runtime, runtimes (linear/search/actor), context-algorithm dispatcher, handoff agent, registry, MCP attach mixin.
|-- context/             Public context primitives (package), manager, presets, context-window algorithms, handoff primitives, compaction, templates.
|-- evals/               Eval suites, graders, runner, registry.
|-- harnesses/           Minimal namespace for future/custom harness integrations.
|-- middleware/          Runtime middleware: base, pipeline, builtins, compaction engine/strategies.
|-- pipelines/           String-in/string-out agent wiring: sequential, parallel, conditional, map_reduce.
|-- prompts/             JSON/Markdown-backed prompt catalog and prompt bundles.
|-- providers/           Provider adapters and provider selection helpers.
|-- trace/               Tracer client, debug tracer, continual tracing.
|-- tools/               Tool contracts, catalog, registry/executor, decorators, built-ins, filesystem, MCP, security.
|-- shared/              Shared SDK namespace placeholder.
`-- lib/                 Central dataclasses, enums, errors, config, HTTP, runners, templates, tools, agents helpers.
```

> There is no `vidbyte/strategies/` package. The former strategy layer was replaced by **agent runtimes** (`vidbyte/agents/runtimes/`) and **context-window algorithms** (`vidbyte/context/algorithms/`). `StrategyResult` remains only as the internal runtime result dataclass in `vidbyte/lib/dataclasses/strategies.py`.

Keep central contracts under `vidbyte/lib/` when they are shared by multiple packages. Public package modules often re-export those contracts for stable imports.

## Public Import Surface

`vidbyte.__init__` is the broad convenience import surface. It currently exposes:

- Root client: `VidbyteSDK`.
- Agents: `Agent`, `BaseAgent`, `AgentClient`, `AgentInput`, `AgentCard`, `AgentMessage`, `AgentRegistry`, `AgentRunnerConfig`, `AgentSpec`.
- Contexts: `BaseContext`, `BaseAgentContext`, `ContextBudget`, `ContextPermissions`, `ContextManager`, `ContextWindow`, `ContextWindowAlgorithm`, `ToolResultAdmission`, `ContextItem`, `TextContextItem`, `FileContextItem`, `GitDiffContextItem`, `TaskContextItem`, `DocumentContextItem`, `EnvironmentContextItem`, `MemoryContextItem`, `ProgressContextItem`, `ArtifactContextItem`, `ResponseContextItem`, `ToolCallContextItem`, `TrajectoryCheckpointContextItem`, `PlanContextItem`.
- Context-window algorithms: `ReflexionAlgorithm`, `TrajectoryCheckpointAlgorithm`, `MultiProviderAgenticGraderAlgorithm`, `InnerContextWindowAlgorithm`.
- Handoffs: `Handoff`, `EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`, `HandoffAgent`.
- Runtime config: `AgentRuntimeConfig`, `AgentRuntimeStats`.
- Pipelines: `BasePipeline`, `SequentialPipeline`, `ParallelPipeline`, `ConditionalPipeline`, `MapReducePipeline`, `PipelineNode`, `PipelineExecutionError`.
- Middleware (root exports): `AgentMiddleware`, `MiddlewarePipeline`, `MiddlewareContext`, `MiddlewareDecision`, `MiddlewareAction`, `MiddlewareEvent`, `MiddlewareHook`, `MiddlewareTransform`, plus built-ins `AuditLogMiddleware`, `ModelRetryMiddleware`, `RuntimeLimitMiddleware`, `TokenRateLimitMiddleware`, `ToolPolicyMiddleware`, `CanaryTripwireMiddleware`, `ConfusedDeputyGuardMiddleware`, `HoneypotToolMiddleware`, `ToolResultCompactionMiddleware`, `MessageHistoryCompactionMiddleware`, `SummaryCompactionMiddleware`. Other built-ins (`TokenBudgetMiddleware`, `CostBudgetMiddleware`, `CircuitBreakerMiddleware`/`CircuitState`, `LoopDetectionMiddleware`, `ExponentialBackoffRetryMiddleware`) are imported from `vidbyte.middleware`.
- Evals: `BaseGrader`, `ContainsGrader`, `ExactMatchGrader`, `RegexMatchGrader`, `JSONSchemaGrader`, `LLMJudgeGrader`, `RubricGrader`, `GraderResult`.
- Enums: `BudgetPreset`, `PermissionPreset`, `Prompt`, `ModelModality`. (`AgentRuntimeType` is imported from `vidbyte.lib.enums`.)
- Prompts: `Prompts`.
- Tools: `BaseTool`, `Tools`, `FunctionTool`, `ToolCall`, `ToolCallContext`, `ToolCallState`, `ToolExecutor`, `ToolParameter`, `ToolPermission`, `ToolRegistry`, `ToolResult`, `ToolSpec`, `ToolStatus`, `ToolMixin`, `ToolsFormatter`, `tool`, `vidbyte_tool`.
- MCP: `McpServerConfig`, `McpServerHandle`, `McpToolPermission`.
- MCP errors: `McpError`, `McpConnectionError`, `McpInitializeError`, `McpToolDiscoveryError`, `McpToolExecutionError`, `McpAttachmentError`.

> The exact `__all__` is authoritative in `vidbyte/__init__.py`; the list above is a curated summary. There are **no** `BaseStrategy`/`ChainOfThoughtStrategy`/`MultiAgentConsensusStrategy` public exports anymore.

Root exports are meant for common imports. More specialized built-ins should still be imported from their category packages.

## Root SDK Client

`vidbyte.client.VidbyteSDK` is a namespace aggregator. It constructs:

- `sdk.agents`: `AgentClient`.
- `sdk.harnesses`: `HarnessClient`.
- `sdk.tools`: `ToolsClient`.
- `sdk.providers`: `ProvidersClient`.

There is no `sdk.strategies` namespace. Reasoning/orchestration is configured per-agent via `runtime=` and `algorithm=`, and agents are wired together with pipelines. The root client should stay light. Feature-specific behavior belongs in the feature package.

## Agents And Modality Routing

Primary files:

- `vidbyte/agents/base.py`
- `vidbyte/agents/client.py`
- `vidbyte/agents/mixins.py`
- `vidbyte/agents/runtime.py`, `vidbyte/agents/runtimes/`, `vidbyte/agents/context_algorithms.py`, `vidbyte/agents/algorithms/`
- `vidbyte/agents/handoff.py`
- `vidbyte/agents/types.py`
- `vidbyte/lib/registries/agents.py` (`AgentRegistry`)
- `vidbyte/lib/dataclasses/agents.py`
- `vidbyte/lib/agents/modality_detector.py`

Primary concepts:

- `Agent = BaseAgent` is the ergonomic alias.
- `BaseAgent` is the executable actor. It owns name, system prompt, runtime selection, context-window algorithm, runner settings, explicit runners by modality, tools, permission policy, middleware, MCP attachment state, history, metadata, and capabilities.
- `AgentInput` is a typed input wrapper with `prompt`, `modality`, `metadata`, optional `context_items`, and optional `context_manager`.
- `AgentMessage` is the in-process message payload passed between agents.
- `AgentCard` exposes local capability metadata: description, system prompt, capabilities, tool names, MCP server/tool names, modalities, and metadata.
- `AgentSpec` is a construction-friendly description block.
- `AgentRunnerConfig` captures primitive runner configuration for provider, model, modality, temperature, run ID, API key, and extra options.
- `AgentRegistry` registers agents by name, returns all agents/cards, and can find agents by capability.

Agent execution:

- `BaseAgent.generate_reply()` is async and returns an `AgentMessage`.
- `BaseAgent.arun()` is the async ergonomic alias.
- `BaseAgent.run()` is the sync wrapper and rejects use from an active event loop.
- The agent runs under its configured `AgentRuntime` (linear by default), which owns the per-iteration loop, middleware dispatch, tool execution, and tracing.
- Direct runner execution supports `run()`, `arun()`, or a callable runner; the runtime requires an executable runner.
- Agent context is built as `BaseAgentContext` and includes system prompt, agent name, history, files, runtime/algorithm metadata, tool calls, responses, budget, artifacts, memory, permissions, and metadata.

Modality routing:

- `ModelModality` supports `auto`, `text`, `image`, and `video`.
- `ModalityDetector` coerces modality strings, detects modality from known model names and model-name patterns, resolves call/input/default priority, and creates the correct internal runner.
- `BaseAgent` resolves modality from explicit call request, typed input modality, agent default, or model-name detection.
- Text is the fallback when all modality inputs remain `auto`.
- Runner creation uses `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` with filtered config options.

Agent tool loop:

- Agent-local tools are normalized into a `Tools` catalog.
- When tools are present, the agent formats provider-native tool schemas, calls the runner, parses tool calls from provider output, checks permissions, validates calls, executes tools, formats tool results back into provider messages, and repeats until a final non-tool response or `max_tool_rounds`.
- Tool-call lifecycle is recorded with `ToolCallContext` and states `requested`, `succeeded`, `failed`, or `denied`.
- Permission denials return tool error results rather than bypassing the policy.

MCP attachment:

- `McpAttachableMixin` gives agents async and sync builder APIs for attaching MCP servers.
- Pending MCP configs can be connected lazily before execution.
- Attached remote tools are bridged into native `BaseTool` objects.
- Agents should close MCP servers through `close_mcp_servers()` or async context manager usage.

## Agent Runtimes

The former `vidbyte/strategies/` layer no longer exists. An agent's execution paradigm is chosen with `runtime=AgentRuntimeType.<name>` (or the string value), and reasoning behaviors that transform the context window are attached with `algorithm=ContextWindow.preset.<name>`. See `skills/agent-runtimes/SKILL.md` and `skills/vidbyte-sdk/adding-context-window-algorithms.md`.

Primary files:

- `vidbyte/agents/runtime.py` — `AgentRuntime` (generic per-iteration loop, middleware/tracing/tool execution).
- `vidbyte/agents/runtimes/` — `linear.py`, `search.py` (MCTS), `actor/` (actor model broker/inbox/message/actor).
- `vidbyte/agents/context_algorithms.py` — `AgentRuntimeContextAlgorithms` dispatcher mapping a configured algorithm to its runtime adapter.
- `vidbyte/agents/algorithms/` — runtime adapters (e.g. `reflexion.py`, multi-provider grader).
- `vidbyte/lib/enums/agent_runtime.py` — `AgentRuntimeType`.
- `vidbyte/lib/dataclasses/strategies.py` — `StrategyResult` (internal runtime result: `output`, `strategy_name`, optional metadata).

`AgentRuntimeType` values:

- `LINEAR` (default) — sequential reason/act/model loop. Fully compatible with middleware and context-window algorithms.
- `MCTS_SEARCH` (`mcts_search`) — Monte Carlo tree search over reasoning paths.
- `ACTOR_MODEL`, `ACTOR_MODEL_P2P`, `ACTOR_MODEL_BROADCAST` — concurrent multi-actor message-passing swarm.

Non-linear runtimes (MCTS, actor) are structurally incompatible with middleware and context-window algorithms; combining them raises `ConfigurationError` at construction.

Public runtime exports (from `vidbyte.agents.runtimes`): `LinearRuntime`, `MctsSearchRuntime`, `ActorRuntime`, the runtime components (`LinearAgentRuntime`, `SearchTreeRuntimeComponent`, `PointToPointActorRuntime`, `BroadcastActorRuntime`), and prebuilt actor personas (`PlannerActor`, `ReviewerActor`, `GeneratorActor`, `CriticActor`, `ReasonerActor`, `SummarizationActor`, `DecomposerActor`, `ExplorerActor`, `TradeoffActor`, `HypothesisGeneratorActor`, `RefinerActor`, `SafetyActor`, `FinalAnswerActor`, `PrebuiltActor`). Actor personas are backed by the `actor_runtime` prompt family.

## Context-Window Algorithms

Context-window algorithms are SDK-selected runtime behaviors that transform what the model sees during a run. They are attached with `algorithm=ContextWindow.preset.<name>` and dispatched by `AgentRuntimeContextAlgorithms`.

Primary files:

- `vidbyte/context/algorithms/` — public config dataclasses (`reflexion.py`, `trajectory_checkpoints.py`, `multi_provider_agentic_grader.py`, `tool_results.py`).
- `vidbyte/context/presets.py` — `ContextWindow.preset.<name>` registration.
- `vidbyte/context/runtime.py` — inner-loop context-window lifecycle (`InnerContextWindowAlgorithm`, `ContextWindowRunContext`).

Public algorithm config exports: `ReflexionAlgorithm`, `TrajectoryCheckpointAlgorithm`, `MultiProviderAgenticGraderAlgorithm`, `InnerContextWindowAlgorithm`, `ContextWindowAlgorithm`. Each algorithm also has a model-callable **tool** equivalent (`ReflexionTool`, `TrajectoryCheckpointTool`); see `skills/vidbyte-sdk/context-algorithm-to-tool.md`.

## Tools

Primary files:

- `vidbyte/tools/base.py`
- `vidbyte/tools/catalog.py`
- `vidbyte/tools/decorators.py`
- `vidbyte/tools/function_tool.py`
- `vidbyte/tools/adapters.py`
- `vidbyte/tools/registry.py`
- `vidbyte/tools/executor.py`
- `vidbyte/tools/mixins.py`
- `vidbyte/tools/types.py`
- `vidbyte/lib/dataclasses/tools.py`
- `vidbyte/lib/tools/formatter.py`

Preferred public model:

- Use `Tools(...)`, `@tool`, `@vidbyte_tool`, and `Agent(..., tools=[...])` for new public examples.
- `ToolRegistry` and `ToolExecutor` remain supported compatibility/lower-level infrastructure.
- Avoid global mutable tool state for orchestration. Tools should be injected into agents or namespace clients.

Tool contracts:

- `BaseTool` requires `spec()` and async `execute(call)`.
- `ToolLike` is the structural protocol for objects shaped like tools.
- `ToolSpec` describes a model-facing tool: name, description, parameters, permission, metadata, and optional JSON input schema.
- `ToolParameter` describes individual parameters.
- `ToolCall` is a runtime tool invocation.
- `ToolResult` has `success()`, `error()`, and `failure()` helpers.
- `ToolPermission` levels are `safe`, `read`, `write`, and `execute`.
- `ToolStatus` is `success` or `error`.
- `ToolCallContext` records agent-managed tool-call lifecycle.

`Tools` catalog:

- Sequence-like catalog of normalized `BaseTool` objects.
- Preserves deterministic insertion order.
- Rejects duplicate names unless replacing through `add(..., replace=True)`.
- Exposes `all()`, `names()`, `specs()`, `describe()`, `provider_schemas(provider_or_model)`, `add()`, `extend()`, and internal `_get(name)`.
- Adapts spec-only legacy objects into a non-executable wrapper for compatibility.

Custom function tools:

- `@tool` and `@vidbyte_tool` wrap Python callables in `FunctionTool`.
- The decorator can be used bare or configured with `name`, `description`, and `permission`.
- `FunctionTool` inspects signatures, docstrings, and type hints, builds a Pydantic-backed args model, validates runtime arguments, and executes sync or async functions.
- Use `ToolPermission.WRITE` or `ToolPermission.EXECUTE` for mutating or executable tools.

Registry and executor:

- `ToolRegistry` registers normalized tools, provides lookup, lists all tools, returns specs, and supports bulk registration.
- `ToolExecutor` validates registry lookup, permission policy, required args, and tool execution.
- Default executor policy allows `SAFE` and `READ`; mutating or executable tools require explicit permission policy.
- `ToolsClient` owns both a `Tools` catalog and compatibility `ToolRegistry`/`ToolExecutor` under `VidbyteSDK().tools`.

Formatter:

- `ToolsFormatter` converts `ToolSpec` to provider schemas for OpenAI, Anthropic, Grok/xAI, and Gemini.
- It parses provider-native tool calls back into `ToolCall`.
- It formats tool results back into provider-specific message/content structures.

Built-in tool groups:

- `vidbyte.tools.builtins.calculator.CalculatorTool`
- `vidbyte.tools.builtins.code_execution.CodeExecutionTool`
- `vidbyte.tools.builtins.document_retrieval.DocumentRetrievalTool`
- `vidbyte.tools.builtins.code_search`: `GlobTool`, `GrepTool`, `SemanticSearchTool`
- `vidbyte.tools.builtins.editing`: `PatchTool`
- `vidbyte.tools.builtins.context`: `ContextCompactionTool`, compaction modes and related types — **legacy/manual** only; prefer compaction middleware (`vidbyte/middleware/compaction/`)
- `vidbyte.tools.builtins.context_primitives`: `ContextUpsertTool`, `ContextListTool`, `ContextRemoveTool`
- `vidbyte.tools.builtins.reflexion.ReflexionTool`, `vidbyte.tools.builtins.trajectory_checkpoint.TrajectoryCheckpointTool` (model-callable forms of the context-window algorithms)
- `vidbyte.tools.builtins.memory`: Cognee, Letta, Mem0, Supermemory, and Zep memory tools — see `skills/vidbyte-sdk/memory-tools.md`
- `vidbyte.tools.builtins.mcp`: `AttachMcpServerTool`, `SearchMcpServersTool`

## Filesystem Tools

Primary files:

- `vidbyte/tools/filesystem/`
- `vidbyte/lib/dataclasses/filesystem.py`
- `vidbyte/lib/tools/filesystem/permissions.py`
- `vidbyte/lib/tools/filesystem/backends/base.py`
- `vidbyte/lib/tools/filesystem/backends/local.py`

Public filesystem tools:

- `AppendTool`
- `ChecksumTool`
- `CopyTool`
- `DeleteTool`
- `DiffTool`
- `ExistsTool`
- `FindTool`
- `ListDirTool`
- `MakeDirTool`
- `MoveTool`
- `RenameTool`
- `ReadBinaryTool`
- `ReadLinesTool`
- `ReadTextTool`
- `ReplaceTextTool`
- `StatTool`
- `TouchTool`
- `TreeTool`
- `UnzipTool`
- `WriteTextTool`
- `ZipTool`

Filesystem rules:

- Use `FileSystemToolConfig` for root and path restrictions.
- Use `FileSystemPermissions` for read/write/delete style permission checks.
- Filesystem tools should report errors through `ToolResult.error()` rather than throwing raw filesystem exceptions through the public tool boundary.
- Mutating filesystem tools must be guarded by `WRITE` or stronger permissions.

## MCP Integration

Primary files:

- `vidbyte/tools/mcp/types.py`
- `vidbyte/tools/mcp/transport.py`
- `vidbyte/tools/mcp/client.py`
- `vidbyte/tools/mcp/bridge.py`
- `vidbyte/tools/mcp/attach.py`
- `vidbyte/agents/mixins.py`
- `vidbyte/lib/dataclasses/mcp.py`
- `vidbyte/lib/errors/base.py`

Public MCP surface:

- `McpServerConfig`: server command/configuration.
- `McpServerHandle`: live process connection wrapper.
- `McpToolPermission`: permission mapping for remote tools.
- `McpToolDefinition`: discovered remote tool metadata.
- `McpTransport`: transport protocol.
- `McpStdioTransport`: subprocess stdio transport.
- `McpClient`: JSON-RPC initialize, tool discovery, and tool call client.
- `McpToolBridge` and `McpBridgedTool`: wrappers that expose remote MCP tools as native SDK tools.
- `attach_mcp_server()`: creates a connected server handle.

MCP errors:

- `McpError`
- `McpConnectionError`
- `McpInitializeError`
- `McpToolDiscoveryError`
- `McpToolExecutionError`
- `McpAttachmentError`

Lifecycle expectations:

- Attach MCP servers explicitly to agents or other mixin owners.
- Close server handles after use.
- Treat remote tools as tools with permission requirements; do not bypass SDK permission policy.

## Providers, Configs, Runners, And HTTP

Primary files:

- `vidbyte/providers/`
- `vidbyte/lib/config/`
- `vidbyte/lib/http/`
- `vidbyte/lib/runners/`
- `vidbyte/lib/enums/model_provider.py`
- `vidbyte/lib/enums/model_modality.py`

Provider enum:

- `ModelProvider.OPENAI`
- `ModelProvider.ANTHROPIC`
- `ModelProvider.GEMINI`
- `ModelProvider.XAI`
- `ModelProvider.DEEPSEEK`
- `ModelProvider.GLM`
- `ModelProvider.MINIMAX`
- `ModelProvider.OPENROUTER`
- `ModelProvider.ELEVENLABS`
- `ModelProvider.PLAYAI`

Provider adapters:

- `OpenAIProvider`: text, image, and video job APIs.
- `AnthropicProvider`: text API.
- `GeminiProvider`: text API.
- `XAIProvider`: OpenAI-compatible text plus image support.
- `OpenRouterProvider`: OpenAI-compatible aggregator provider.
- `ElevenLabsProvider`, `PlayAIProvider`: audio providers.
- `OpenAICompatibleProvider`: base for OpenAI-compatible text providers.
- `DeepSeekProvider`, `GLMProvider`, `MiniMaxProvider`: compatible text providers.
- `ModelProviders`: central factory for text/image/video/audio/embedding provider selection.
- `tool_spec_to_provider_schema()` translates SDK tool specs to provider-specific schema shapes.

Model configs:

- `TextModelConfig`: provider, model, API key, system, messages, sampling, response format, tools, tool choice/config, safety settings, cached content, thinking config, metadata, extra body, endpoint, timeout.
- `ImageModelConfig`: provider, model, API key, size, quality, response format, count, background, output format/compression, extra body, endpoint, timeout.
- `VideoModelConfig`: provider, model, API key, size, seconds, extra body, endpoint, timeout.
- Configs validate provider, model, sampling bounds, positive limits, timeout, and API key resolution.
- API keys resolve explicit config values before provider-specific environment variables from config constants.

HTTP:

- `HttpTransport` owns standard-library HTTP request behavior.
- `HttpResponse` captures status, body, and headers.
- `HttpResponseParser` parses JSON and raises provider response errors on malformed responses.

Runners:

- `TextModelRunner` validates `TextModelConfig`, creates a provider through `ModelProviders.text()`, and calls `run_text()`.
- `ImageModelRunner` validates `ImageModelConfig`, creates a provider through `ModelProviders.image()`, and calls `run_image()`.
- `VideoModelRunner` validates `VideoModelConfig`, creates a provider through `ModelProviders.video()`, creates video jobs, and can fetch job status.
- Runner response dataclasses live in `vidbyte/lib/runners/types.py`: `TextModelResponse`, `GeneratedImage`, `ImageModelResponse`, and `VideoModelJob`.
- `vidbyte/lib/runners/router.py` keeps compatibility wrappers around `ModalityDetector`.

## Prompts

Primary files:

- `vidbyte/prompts/catalog.py`
- `vidbyte/prompts/__init__.py`
- `vidbyte/prompts/registry.py`
- `vidbyte/prompts/prompts/*.json`
- `vidbyte/lib/enums/prompts.py`
- `skills/vidbyte-sdk/adding-prompts.md`

Prompt model:

- Prompts are plain JSON repository assets, not runtime-overridable prompt files.
- Each prompt family JSON must contain `name`, `description`, `key`, and `prompts`.
- `Prompt` enum values are `<family_key>.<prompt_key>`.
- `Prompts().get(Prompt.X)` returns a string and requires a `Prompt` enum member.
- `Prompts().keys()` returns all enum keys.
- `Prompts().descriptions()` returns descriptions keyed by enum.
- `Prompts().all()` returns all prompt text keyed by enum.
- `Prompts().family(family_key)` returns one prompt family keyed by leaf prompt name.
- `Prompts().import_names()` returns generated direct import names.
- `vidbyte.prompts.registry` is a compatibility re-export for `PromptRecord` and `Prompts`.

Current prompt families (13 families, 34 prompts — authoritative source is `vidbyte/lib/enums/prompts.py`):

- `agentic_loop`
- `handoff`
- `context_engineering`
- `expert_prompting`
- `goals`
- `mimic_behavior`
- `reflexion`
- `prompt_engineering`
- `evals`
- `multi_provider_agentic_grader`
- `templates`
- `actor_runtime` (15 actor-persona prompts)
- `trajectory_checkpoints`

Prompt assets and bundles:

- Prompt assets live under `vidbyte/prompts/prompts/`, as either inline-JSON families or a per-family folder with a JSON descriptor plus Markdown bodies (see `skills/vidbyte-sdk/adding-prompts.md`).
- `vidbyte/prompts/catalog.py` holds the `Prompts` catalog loader.
- The full listing with enum names and direct-import names is in `skills/usage/import_prompt.md`.

When adding prompts:

- Follow `skills/vidbyte-sdk/adding-prompts.md`.
- Add one JSON file per prompt family under `vidbyte/prompts/prompts/`.
- Add enum members under `vidbyte/lib/enums/prompts.py`.
- Ensure direct imports are exposed from `vidbyte.prompts`.
- Update tests for enum lookup, direct imports, descriptions, and any consumers of the family.

## Context And Dataclasses

Primary files:

- `vidbyte/context/__init__.py`
- `vidbyte/context/manager.py`
- `vidbyte/context/primitives/` (package: `base.py`, `checkpoints.py`, `documents.py`, `records.py`, `tasks.py`)
- `vidbyte/context/presets.py`
- `vidbyte/context/window.py`
- `vidbyte/context/algorithms/`
- `vidbyte/context/runtime.py`
- `vidbyte/lib/dataclasses/`
- `vidbyte/tools/types.py`
- `vidbyte/agents/types.py`

Central rule:

- Shared infrastructure dataclasses live under `vidbyte/lib/dataclasses/`; public context item primitives live under the `vidbyte/context/primitives/` package. See `skills/vidbyte-sdk/context-primitives.md`.
- Package-local `types.py` modules and package `__init__` files re-export stable contracts.
- Prefer extending central dataclasses rather than duplicating type definitions in feature packages.

Context dataclasses:

- `ContextMessage`: generic message record for compaction.
- `ContextBudget`: optional model/tool/token/latency/cost budgets.
- `ContextPermissions`: read/tool/write/network/exposure flags.
- `ContextToolCall`: structured tool call record separate from model responses.
- `ProgressLog`: compact task/progress summary with Markdown rendering.
- `ContextState`: mutable conversation-state protocol.
- `ContextResponse`: model or agent response record.
- `ContextArtifact`: text/file artifact record.
- `ContextItem`: structural protocol for standardized context items.
- `ContextManager`: ordered collection and compatibility bridge for context items.
- `ContextWindow`: public namespace for context-window algorithm presets.
- `ContextWindowAlgorithm`: named runtime admission behavior attached to an agent with `algorithm=...`.
- `ToolResultAdmission`: enum for how tool results are admitted into model-visible context.
- `BaseContext`: baseline context with `build_context()`, context items, and optional file content rendering.
- `BaseAgentContext`: context built by agents.
- Standard context item dataclasses (in `vidbyte/context/primitives/`): `TextContextItem`, `FileContextItem`, `GitDiffContextItem`, `TaskContextItem`, `PlanContextItem`, `DocumentContextItem`, `EnvironmentContextItem`, `MemoryContextItem`, `ProgressContextItem`, `ArtifactContextItem`, `ResponseContextItem`, `ToolCallContextItem`, and `TrajectoryCheckpointContextItem`.

Context management rules:

- Context items store structured meaning; the current compatibility path renders through existing `BaseContext.build_context()`.
- Import context item primitives from `vidbyte.context.primitives`; `vidbyte.lib.dataclasses.context_items` is a compatibility re-export only.
- `ContextManager` owns item collection, ordered utilities, and conversion into existing context dataclass fields.
- Keep context-window presets in `vidbyte/context/presets.py`, algorithm implementations under `vidbyte/context/algorithms/`, and `vidbyte/context/window.py` as the thin `ContextWindow.preset.<name>` namespace.
- Agents may receive default `context_items`/`context_manager`; per-call context belongs on `AgentInput`.
- Agents may receive `algorithm=ContextWindow.preset.<name>` to opt into SDK-provided context-window behavior. Initial presets focus on tool-result admission between model calls, including raw, compacted, and hidden raw tool outputs.
- Rich custom renderers, ranking, redaction, summarization, and open-ended compaction policies are not part of the foundation layer and require a separate approved design.

Budget and permission presets:

- `BudgetPreset.TIGHT`, `BALANCED`, `EXPLORATORY`, `UNBOUNDED`.
- `PermissionPreset.SANDBOXED`, `READ_ONLY`, `TOOLS_ONLY`, `TRUSTED`.
- Presets create default `ContextBudget` and `ContextPermissions` objects through `from_preset()`.

Other dataclass groups:

- Agents: `AgentRunnerConfig`, `AgentInput`, `AgentCard`, `AgentMessage`, `AgentSpec`; `AgentInput` can carry context items/managers and `AgentSpec` can carry context items/managers plus an algorithm preset.
- Tools: `ToolParameter`, `ToolSpec`, `ToolCall`, `ToolResult`, `ToolCallContext`.
- Multi-agent: `CandidateResult`, `CandidateFailure`, `EvaluationDecision`, `DagNode`, `Verification`, `NodeState`.
- Model configs: `TextModelConfig`, `ImageModelConfig`, `VideoModelConfig`.
- Runners: `TextModelResponse`, `GeneratedImage`, `ImageModelResponse`, `VideoModelJob`.
- Filesystem: `FileSystemToolConfig`.
- Security: `PermissionDecision`, `PermissionPolicy`.
- Sandbox: `SandboxRequest`, `SandboxResult`, `SandboxTransport`.
- MCP: `McpToolDefinition`.
- Code search: internal `_CodeChunk`.

## Enums And Errors

Enums live under `vidbyte/lib/enums/`:

- `BudgetPreset`
- `PermissionPreset`
- `ModelProvider`
- `ModelModality`
- `ModelNameModality`
- `Platform`
- `Prompt`

Error classes live under `vidbyte/lib/errors/base.py` and are re-exported through `vidbyte.lib.errors`:

- Base: `VidbyteSdkError`.
- Tool errors: `ToolRegistryError`, `ToolExecutionError`, `ToolRegistrationError`, `PermissionDeniedError`.
- MCP errors: `McpError`, `McpConnectionError`, `McpInitializeError`, `McpToolDiscoveryError`, `McpToolExecutionError`, `McpAttachmentError`, `McpProtocolError`.
- Agent and pipeline errors: `AgentExecutionError`, `AgentRegistryError`, `PipelineExecutionError`.
- Provider/config errors: `ConfigurationError`, `UnsupportedProviderError`, `ProviderSelectionError`, `ProviderRequestError`, `ProviderConfigurationError`, `ProviderResponseError`.
- Tracing errors: `TracerConfigurationError`.

Errors should carry useful details where the existing class supports them. Public boundaries should raise SDK-specific errors rather than leaking arbitrary lower-level exceptions when practical.

## Harnesses And Shared Namespace

`vidbyte/harnesses/client.py` currently contains a minimal `HarnessClient` namespace. Harnesses are intentionally not where multi-agent topology flags belong. Compose behavior through agent runtimes, context-window algorithms, and pipelines instead.

`vidbyte/shared/` is currently a placeholder namespace for shared SDK scaffolding.

## Design Doc Index

Use these docs for background and intent. Confirm current implementation before acting on them.

- `docs/design/sdk-consolidated.md`: describes merging several parallel SDK PRs into a unified SDK branch. Useful for understanding why multiple subsystems landed together.
- `docs/design/agent-abstractions.md`: early design for tools, prompt registry, prompt translations, strategies, and harness integrations. Historical in parts because prompt and tool APIs were later simplified/consolidated.
- `docs/design/remove-strategies.md`: removal of the `vidbyte/strategies/` layer in favor of agent runtimes and context-window algorithms — read this to understand the strategy→runtime migration.
- `docs/design/non-linear-agent-runtimes.md`, `docs/design/actor-model-runtime-redesign.md`, `docs/design/feat-advanced-runtimes-and-registries.md`: the agent-runtime model (linear, MCTS, actor).
- `docs/design/agent-runtime-middleware.md`, `docs/design/middleware-builtins-expansion.md`, `docs/design/concurrent-middleware-safety.md`, `docs/design/security-middleware-tripwire-deputy-honeypot.md`: the middleware subsystem and built-ins.
- `docs/design/context-compaction-middleware.md`, `docs/design/truncate-tool-results-compaction.md`: compaction moved from tools to middleware.
- `docs/design/handoff-agent.md`: handoff documents and the handoff agent.
- `docs/design/context-window-primitives.md`, `docs/design/context-window-templates.md`, `docs/design/context-algorithms-as-tools.md`, `docs/design/agentic-trajectory-checkpoints.md`, `docs/design/multi-provider-agentic-grader.md`: context primitives and context-window algorithms.
- `docs/design/sdk-evals.md`: eval suites, graders, and runner.
- `docs/design/memory-provider-tools.md`: memory tool providers (Cognee, Letta, Mem0, Supermemory, Zep).
- `docs/design/structured-output.md`, `docs/design/new-runners.md`, `docs/design/agent-tracing-observability.md`, `docs/design/trace-facade.md`: structured output, new runners (audio/embedding/streaming), and tracing.
- `docs/design/advanced-tool-ecosystem.md`: dependency-free tool foundation, code search, MCP bridge, permissions/sandbox, patch/edit tools, and context compaction. Its own supersession note says later tool API docs update the public mental model.
- `docs/design/custom-function-tools.md`: decorator-first function tool API with Pydantic validation and integration into registries, strategies, agents, providers, and harnesses. Superseded in public examples by `@tool`, `Tools`, and agent-local tools.
- `docs/design/mcp-server-attachment.md`: attaching MCP servers to agents and harnesses, lifecycle management, and bridged remote tools.
- `docs/design/prompt-interface-simplification.md`: current simplified prompt surface with `Prompts`, `Prompt`, direct text imports, no raw string lookup, and no runtime prompt overrides.
- `docs/design/agent-tool-api-consolidation.md`: current public tool mental model around `Tools`, `@tool`, and `Agent(..., tools=[...])`; `ToolRegistry` and `ToolExecutor` remain compatibility surfaces.
- `docs/design/agent-modality-routing.md`: agent-facing routing for text/image/video via modality detection and typed inputs, keeping concrete runners mostly internal/advanced.
- `docs/design/prompt-description-enhancement.md`: expands prompt JSON descriptions into richer 6-8 sentence descriptions.

If local-only docs such as `minimal-agent-runtime.md` or `pipelines.md` are present in a checkout, treat them as design context unless their implementation files also exist on that branch. Do not document them as current runtime APIs without verifying source files.

## Test Suite Map

Use tests as executable examples for expected behavior:

The `tests/` directory is authoritative; representative files include:

- Agents/runtime: `test_agent_base.py`, `test_agent_abstractions.py`, `test_agent_runtime.py`, `test_agent_modality_routing.py`, `test_agent_registry.py`, `test_agent_tool.py`, `test_agent_tool_loop.py`, `test_handoff_agent.py`.
- Middleware: `test_agent_middleware.py`, `test_middleware_builtins.py`, `test_new_middleware_builtins.py`, `test_security_middleware.py`, `test_concurrent_middleware.py`, `test_context_compaction_middleware.py`.
- Context/algorithms: `test_context_management.py`, `test_context_dataclasses.py`, `test_context_primitives_binding.py`, `test_context_primitives_builtins.py`, `test_context_primitives_registry.py`, `test_context_window_templates.py`, `test_inner_context_window_algorithms.py`, `test_reflexion_algorithm.py`, `test_trajectory_checkpoint_algorithm.py`, `test_context_algorithm_tools.py`, `test_context_compaction_tools.py`, `test_multi_provider_agentic_grader.py`.
- Pipelines: `test_pipelines.py`.
- Tools: `test_tools_catalog.py`, `test_tool_core.py`, `test_tool_mixin.py`, `test_custom_function_tools.py`, `test_tool_registry_custom_inputs.py`, `test_code_search_tools.py`, `test_patch_tool.py`, `test_filesystem_tools.py`, `test_security_executor.py`, `test_memory_tools.py`, `test_mcp_discovery_tools.py`.
- Evals: `test_evals.py`.
- MCP: `test_mcp_attachment.py`, `test_mcp_bridge.py`, `test_mcp_studio_server.py`.
- Providers/runners: `test_text_model_runner.py`, `test_streaming_text_runner.py`, `test_image_video_runners.py`, `test_audio_runner.py`, `test_embedding_runner.py`, `test_openrouter_provider.py`, `test_provider_tool_schema_translation.py`, `test_model_registry.py`, `test_config_validation.py`.
- Prompts: `test_prompts_interface.py`.
- Tracing: `test_tracing.py`, `test_trace_facade.py`.

Run `ls tests/` for the complete, current list.

## Development Guardrails

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep reusable shared dataclasses under `vidbyte/lib/dataclasses/`.
- Keep compatibility re-export modules stable unless a design doc explicitly approves a breaking change.
- Keep prompt assets in `vidbyte/prompts/prompts/` and access them through `Prompts` and `Prompt`.
- Keep model provider configs under `vidbyte/lib/config/`.
- Keep provider-neutral formatting helpers under `vidbyte/lib/tools/`.
- Keep internal model runners under `vidbyte/lib/runners/`; public examples should usually prefer agent-facing APIs.
- Keep agent execution runtimes under `vidbyte/agents/runtimes/` and context-window algorithms under `vidbyte/context/algorithms/` + `vidbyte/agents/algorithms/`.
- Keep tools under `vidbyte/tools/` and built-ins grouped by category.
- Keep MCP code under `vidbyte/tools/mcp/`.
- Keep permission and sandbox abstractions under `vidbyte/tools/security/`.
- Mutating or executable tools must declare `WRITE` or `EXECUTE` permission and be checked by policy.
- Avoid network calls in tests unless the repository already has a mocked transport path. Provider tests should use fake transports.
- Avoid adding private service logic, database access, customer data, or proprietary scoring systems.
- Prefer standard library solutions unless an approved design adds a dependency.
- Use existing unittest style unless a separate approved design changes the test framework.
- Update README and skill docs when public usage patterns change.

## Verification Commands

Run these before handoff for most changes:

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.agents).__name__)"
```

For prompt changes, also verify:

```bash
python -m unittest tests.test_prompts_interface
```

For tool changes, run the relevant focused tests first:

```bash
python -m unittest tests.test_tools_catalog tests.test_tool_core tests.test_custom_function_tools tests.test_security_executor
```

For provider changes, run provider and runner tests:

```bash
python -m unittest tests.test_text_model_runner tests.test_image_video_runners tests.test_provider_tool_schema_translation
```

## Common Change Playbooks

Adding a prompt:

1. Add or update one prompt family in `vidbyte/prompts/prompts/` (inline JSON, or a folder with a JSON descriptor plus Markdown bodies).
2. Add matching enum members in `vidbyte/lib/enums/prompts.py`.
3. Ensure direct imports are exposed from `vidbyte.prompts`.
4. Add or update prompt tests (`tests/test_prompts_interface.py`).

Adding a tool:

1. Decide whether it is a function tool, a `BaseTool` subclass, or a built-in category tool.
2. Define a clear `ToolSpec` with accurate parameters and permission.
3. Return `ToolResult.success()` or `ToolResult.error()`.
4. Ensure it works with `Tools`, `ToolRegistry`, and agent-local execution when relevant.
5. Add permission and validation tests.

Adding a provider:

1. Add enum support in `ModelProvider`.
2. Add config constants for API key env var and endpoint.
3. Implement or extend provider adapter behavior.
4. Register it in `ModelProviders` for the supported modalities.
5. Add fake transport tests for payload construction and response parsing.

Adding a context-window algorithm:

1. Add the public config dataclass under `vidbyte/context/algorithms/` and register a preset in `vidbyte/context/presets.py`.
2. Add the runtime adapter under `vidbyte/agents/algorithms/` and wire it through `AgentRuntimeContextAlgorithms`.
3. Keep `AgentRuntime.arun()` thin (dispatcher delegation + fallback).
4. Attach a structured algorithm trace to `StrategyResult.metadata`.
5. Follow `skills/vidbyte-sdk/adding-context-window-algorithms.md` and add tests with fake runners.

Adding an agent runtime:

1. Implement the runtime under `vidbyte/agents/runtimes/` and add an `AgentRuntimeType` value.
2. Decide middleware / context-window-algorithm compatibility; raise `ConfigurationError` for unsupported combinations.
3. Follow `skills/agent-runtimes/SKILL.md` and add tests.

Adding an agent-facing capability:

1. Prefer extending `BaseAgent` only when the behavior belongs to all agents.
2. Keep modality selection in `ModalityDetector` or runner routing helpers.
3. Preserve direct runner and runtime delegation behavior.
4. Preserve tool loop permission checks and structured context records.
5. Add tests around sync/async calls, modality, tools, and metadata.

Adding a dataclass:

1. Put shared dataclasses under `vidbyte/lib/dataclasses/`.
2. Re-export through package-local `types.py` or `__init__.py` only when it is stable public surface.
3. Keep dataclasses immutable with `frozen=True, slots=True` where the surrounding code uses that pattern.
4. Add tests for defaults, validation, rendering, and compatibility imports when relevant.
