# Create Agent

Create a single `Agent` instance and run it with a prompt. The `Agent` is the core building block of the Vidbyte SDK â€” it wraps a model provider with a system prompt, optional tools, strategy, middleware, permissions, and history. Every interaction follows the same pattern: define an agent, send a prompt, receive an `AgentMessage` reply.

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
    provider: str | ModelProvider | None, # "openai", "anthropic", "gemini", "xai", "deepseek", "glm", "minimax"
    model_name: str | None,              # specific model ID for the provider
    modality: ModelModality = ModelModality.AUTO,  # AUTO, TEXT, IMAGE, VIDEO
    api_key: str | None = None,          # override for provider API key
    temperature: float | None = None,    # model temperature (0.0â€“2.0)
    max_tool_rounds: int | None = None,  # max tool-calling iterations before returning
    max_iterations: int | None = None,   # max total agent loop iterations
    max_tokens: int | None = None,       # max output tokens per model call
    description: str = "",               # human-readable description for registries and cards
    capabilities: Sequence[str] = (),    # tags for registry discovery (e.g., ["code_generation", "refactoring"])
    metadata: dict[str, Any] | None = None,  # arbitrary key-value metadata for discovery
    tools: Sequence[BaseTool] = (),      # tools the agent can call during execution
    middleware: Sequence[AgentMiddleware] = (),  # runtime policy middleware
    trace: TraceOption | None = None,    # optional continual trace artifact config
    permission_policy: PermissionPolicy | None = None,  # tool permission policy
    runners: Mapping[ModelModality | str, object] | None = None,  # per-modality runners
)
```

Each parameter has a specific role:
- **Identity** (`name`, `description`, `capabilities`, `metadata`): Used for registry lookup, agent cards, and multi-agent discovery.
- **Model** (`provider`, `model_name`, `api_key`, `temperature`, `modality`): Configures which model to use and how.
- **Execution** (`max_tool_rounds`, `max_iterations`, `max_tokens`): Controls resource consumption and loop limits.
- **Capability** (`tools`, `middleware`, `permission_policy`): What the agent can do and how it behaves.
- **Trace artifact** (`trace`): Optional user-visible continual trace metadata returned in `reply.metadata`.

## Add Continual Trace

Use `trace=TraceOption.continual(...)` when the agent should return a structured artifact describing what it did:

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.prebuilt import ActionTrace

agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    trace=TraceOption.continual(ActionTrace),
)

reply = await agent.arun("Complete the task")
trace = reply.metadata["trace"]
```

Use `trace=` for user-visible run artifacts. Use `tracer=` only for observability spans. See [`skills/usage/use_continual_trace.md`](use_continual_trace.md).

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
# reply.metadata: dict  â€” any extra metadata attached by the agent or strategy
```

## Inspect the Agent

Query the agent's configuration and capabilities at runtime:

```python
card = agent.card()          # AgentCard â€” name, description, capabilities, tool names, modalities
specs = agent.tool_specs()   # tuple[ToolSpec, ...] â€” model-facing tool declarations sent to the provider
```

`agent.card()` is useful for registry discovery and multi-agent orchestration. `agent.tool_specs()` returns the schema the model actually sees.

## Adding Middleware

Middleware is deterministic runtime policy that runs at specific lifecycle hooks (before/after model calls, before/after tool calls). It is never visible to the model:

```python
from vidbyte import AgentMiddleware, MiddlewareDecision

class LoggingMiddleware(AgentMiddleware):
    async def before_model_call(self, agent, prompt):
        print(f"[LOG] Agent '{agent.name}' about to call model")
        return MiddlewareDecision.ALLOW

agent = Agent(
    name="logged-agent",
    system_prompt="You are helpful.",
    provider="openai",
    model_name="gpt-4.1",
    middleware=[LoggingMiddleware()],
)
```

## Fork an Agent

Create variant agents from a base without re-declaring all configuration. Forking copies the parent's configuration while allowing overrides â€” useful for creating specialized agents that share the same foundation:

```python
child = agent.fork(name="child-agent", temperature=0.2)            # override any constructor kwarg
child_with_history = agent.fork(include_history=True, name="child") # copies parent message history
```

The parent's tools, strategy, middleware, and permissions are inherited by the child unless explicitly overridden.

## Sync Run Caveat

`agent.run()` wraps `arun()` synchronously. It will raise an error if called from inside an active `asyncio` event loop. Use `await agent.arun()` in async code.

## Next Steps

- **Add tools**: See [`skills/usage/create_agent_with_tools.md`](create_agent_with_tools.md)
- **Add continual trace**: See [`skills/usage/use_continual_trace.md`](use_continual_trace.md)
- **Add a strategy**: See [`skills/usage/available_features.md`](available_features.md)
- **Manage multiple agents**: See [`skills/usage/create_agents.md`](create_agents.md)
- **Build pipelines**: See [`skills/usage/create_pipeline.md`](create_pipeline.md)

