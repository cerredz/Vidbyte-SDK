# Create Agent

Create a single `Agent` instance and run it with a prompt.

## Minimum Agent

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

```python
from vidbyte import Agent, ModelModality

Agent(
    *,                                    # all keyword-only
    name: str,                            # required, non-empty
    system_prompt: str,                   # required, non-empty
    provider: str | ModelProvider | None, # "openai", "anthropic", "gemini", "xai", "deepseek", "glm", "minimax"
    model_name: str | None,
    modality: ModelModality = ModelModality.AUTO,  # AUTO, TEXT, IMAGE, VIDEO
    api_key: str | None = None,
    temperature: float | None = None,
    max_tool_rounds: int | None = None,
    max_iterations: int | None = None,
    max_tokens: int | None = None,
    description: str = "",
    capabilities: Sequence[str] = (),
    metadata: dict[str, Any] | None = None,
    runners: Mapping[ModelModality | str, object] | None = None,  # per-modality runners
)
```

## Run the Agent

```python
# Async (preferred)
reply = await agent.arun("Write a haiku about code")
# reply.content -> "Silicon whispers..."

# Sync (blocking)
reply = agent.run("Write a haiku about code")

# Typed input with modality override
from vidbyte import AgentInput
reply = await agent.arun(AgentInput("Create an image of a cat", modality=ModelModality.IMAGE))
```

## Return Type

`arun()` and `run()` return `AgentMessage`:
```python
from vidbyte import AgentMessage
# reply.sender: str
# reply.recipient: str
# reply.content: str
# reply.metadata: dict
```

## Inspect the Agent

```python
card = agent.card()          # AgentCard with name, description, capabilities, tool names, modalities
specs = agent.tool_specs()   # tuple[ToolSpec, ...] - model-facing tool declarations
```

## Fork an Agent

```python
child = agent.fork(name="child-agent", temperature=0.2)            # override any constructor kwarg
child_with_history = agent.fork(include_history=True, name="child") # copies parent message history
```

## Sync Run Caveat

`agent.run()` wraps `arun()` synchronously. It will raise an error if called from inside an active `asyncio` event loop. Use `await agent.arun()` in async code.
