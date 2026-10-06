# Create Agent

Create a single `Agent` instance and run it with a prompt. The `Agent` is the core building block of the Vidbyte SDK: it wraps a model provider with a system prompt, optional tools, runtime settings, context-window algorithm, middleware, permissions, and history. Every interaction follows the same pattern: define an agent, send a prompt, receive an `AgentMessage` reply.

## Minimum Agent

The simplest possible agent requires just a name, system prompt, provider, and model name. Everything else has sensible defaults.

```python
from vidbyte import Agent

agent = Agent(
    name="helper",
    system_prompt="You are a helpful assistant.",
    provider="openai",
    model_name="gpt-4.1",
)
reply = await agent.arun("Explain quantum computing")
```

## Agent Constructor

The full constructor signature with every available parameter. All parameters are keyword-only.

```python
from vidbyte import Agent, ModelModality

Agent(
    *,                                    # all keyword-only
    name: str,                            # required, non-empty â€” agent identity
    system_prompt: str,                   # required, non-empty â€” defines agent behavior and constraints
    runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR,  # execution runtime: linear, mcts_search, actor_model_p2p, actor_model_broadcast
    provider: str | ModelProvider | None, # "openai", "anthropic", "gemini", "xai", "deepseek", "glm", "minimax", "kimi", "mistral", "openrouter", "elevenlabs", "playai"
    model_name: str | None,              # specific model ID for the provider
    modality: ModelModality = ModelModality.AUTO,  # AUTO, TEXT, IMAGE, VIDEO
    api_key: str | None = None,          # override for provider API key
    temperature: float | None = None,    # model temperature (0.0â€“2.0)
    max_tool_rounds: int | None = None,  # max tool-calling iterations before returning
    max_iterations: int | None = None,   # max total agent loop iterations
    max_tokens: int | None = None,       # max output tokens per model call
    agent_loop_settings: AgentLoopSettings | None = None,  # structured loop settings, including tool error policy
    description: str = "",               # human-readable description for registries and cards
    capabilities: Sequence[str] = (),    # tags for registry discovery (e.g., ["code_generation", "refactoring"])
    metadata: dict[str, Any] | None = None,  # arbitrary key-value metadata for discovery
    tools: Sequence[BaseTool] = (),      # tools the agent can call during execution
    middleware: Sequence[AgentMiddleware] = (),  # runtime policy middleware (deterministic, not model-visible)
    permission_policy: PermissionPolicy | None = None,  # tool permission policy
    runners: Mapping[ModelModality | str, object] | None = None,  # per-modality runners
    context_items: Sequence[ContextItem] = (),  # default context items injected into the agent
    context_manager: ContextManager | None = None,  # explicit context manager
    algorithm: ContextWindowAlgorithm | str | None = None,  # context-window algorithm, e.g. ContextWindow.preset.reflexion
    output_schema: type | Mapping[str, Any] | None = None,  # structured-output schema for providers that support it
    handoff: Handoff | None = None,      # produce a handoff document automatically after each run
)
```

Each parameter has a specific role:
- **Identity** (`name`, `description`, `capabilities`, `metadata`): Used for registry lookup, agent cards, and multi-agent discovery.
- **Model** (`provider`, `model_name`, `api_key`, `temperature`, `modality`): Configures which model to use and how.
- **Runtime** (`runtime`): Selects the execution paradigm — `linear` (default), `mcts_search`, or actor model. See [`skills/agent-runtimes/SKILL.md`](../agent-runtimes/SKILL.md). Note: non-linear runtimes are incompatible with middleware and context-window algorithms and raise `ConfigurationError` if combined.
- **Execution** (`max_tool_rounds`, `max_iterations`, `max_tokens`): Controls resource consumption and loop limits.
- **Capability** (`tools`, `middleware`, `permission_policy`): What the agent can do and how it behaves.
- **Context** (`context_items`, `context_manager`, `algorithm`): Default context and context-window behavior. Per-call context belongs on `AgentInput`.
- **Output / handoff** (`output_schema`, `handoff`): Structured output and automatic handoff-document generation.

## Run the Agent

Agents support both async and sync execution. Async is preferred â€” it does not block the event loop.

```python
# Async (preferred) â€” use in async functions
reply = await agent.arun("Write a haiku about code")
# reply.content -> "Silicon whispers..."

# Sync (blocking) â€” use in synchronous scripts
reply = agent.run("Write a haiku about code")

# Typed input with modality override â€” route to image/video models
from vidbyte import AgentInput
reply = await agent.arun(AgentInput("Create an image of a cat", modality=ModelModality.IMAGE))
```

## Return Type

Both `arun()` and `run()` return `AgentMessage`, which contains the reply content along with sender and recipient metadata:

```python
from vidbyte import AgentMessage
# reply.sender: str     â€” name of the agent that produced this message
# reply.recipient: str  â€” intended recipient (usually "user")
# reply.content: str    â€” the model's text response
# reply.metadata: dict  â€” any extra metadata attached by the agent or runtime
```

## Inspect the Agent

Query the agent's configuration and capabilities at runtime:

```python
card = agent.card()          # AgentCard â€” name, description, capabilities, tool names, modalities
specs = agent.tool_specs()   # tuple[ToolSpec, ...] â€” model-facing tool declarations sent to the provider
```

`agent.card()` is useful for registry discovery and multi-agent orchestration. `agent.tool_specs()` returns the schema the model actually sees.

## Adding Middleware

Middleware is deterministic runtime policy that runs at lifecycle hooks across the agent run (`before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`, `after_tool_call`, `after_iteration`, `after_run`). Each hook receives a read-only `MiddlewareContext` and returns a `MiddlewareDecision`. Middleware is never visible to the model. See [`skills/vidbyte-sdk/middleware.md`](../vidbyte-sdk/middleware.md) for the full hook lifecycle, decision types, and built-in catalog.

```python
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision

class LoggingMiddleware(AgentMiddleware):
    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        print(f"[LOG] Agent '{ctx.agent_name}' about to call model")
        return MiddlewareDecision.continue_()

agent = Agent(
    name="logged-agent",
    system_prompt="You are helpful.",
    provider="openai",
    model_name="gpt-4.1",
    middleware=[LoggingMiddleware()],
)
```

Decisions: `MiddlewareDecision.continue_()` proceeds; `abort(reason)` terminates the run with `AgentExecutionError`; `deny_tool(reason)` blocks a tool in `before_tool_call`; `retry(reason)` retries a failed model call in `on_model_error`; `sleep(seconds)` throttles before proceeding.

### Tool-error policy

Use `AgentLoopSettings(tool_error_policy=ToolErrorPolicy(...))` when failed tool calls should be retried or circuit-broken by runtime policy instead of prompt instructions. Compatible agents auto-register `ToolErrorPolicyMiddleware`.

```python
from vidbyte.agents import AgentLoopSettings, ToolErrorPolicy

agent = Agent(
    name="resilient-tool-user",
    system_prompt="Use tools and recover from transient failures.",
    provider="openai",
    model_name="gpt-4.1",
    agent_loop_settings=AgentLoopSettings(
        tool_error_policy=ToolErrorPolicy(
            max_retries_per_tool_call=2,
            max_total_tool_errors=5,
        ),
    ),
)
```

The default retry gate only retries idempotent transient failures. Terminal tool errors are rendered back to the model with full detail; there is no `ErrorVerbosity` or render-options layer.

## Durable Agent Sessions

Bind an agent to a durable session when its turns need to survive process restarts, branch, rewind, or resume from checkpoints.

```python
from vidbyte import Agent, FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")
agent = Agent(name="researcher", system_prompt="...", provider="openai", model_name="gpt-4.1")

session = agent.persist(store=store)
await agent.arun("start")       # writes one checkpoint through the bound session
await session.arun("continue")  # same persistence path

assert agent.session is session
```

`agent.persist(...)` delegates to `Session(agent, ...)`; persistence is not an agent-constructor side effect. Use `Session.resume(...)` or `sdk.harnesses.sessions.attach(...)` for explicit restore/namespace-client flows.

## Fork an Agent

Create variant agents from a base without re-declaring all configuration. Forking copies the parent's configuration while allowing overrides â€” useful for creating specialized agents that share the same foundation:

```python
child = agent.fork(name="child-agent", temperature=0.2)            # override any constructor kwarg
child_with_history = agent.fork(include_history=True, name="child") # copies parent message history
```

The parent's tools, runtime settings, middleware, and permissions are inherited by the child unless explicitly overridden.

## Sync Run Caveat

`agent.run()` wraps `arun()` synchronously. It will raise an error if called from inside an active `asyncio` event loop. Use `await agent.arun()` in async code.

## Next Steps

- **Add tools**: See [`skills/usage/create_agent_with_tools.md`](create_agent_with_tools.md)
- **Pick a runtime or feature**: See [`skills/usage/available_features.md`](available_features.md)
- **Manage multiple agents**: See [`skills/usage/create_agents.md`](create_agents.md)
- **Build pipelines**: See [`skills/usage/create_pipeline.md`](create_pipeline.md)

