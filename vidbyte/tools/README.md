# Tools

Tools in the Vidbyte SDK bridge model-requested tool calls to local Python
capabilities, MCP-backed tools, and built-in utilities.

## Role In The SDK

`vidbyte.tools` exposes `@tool`, `FunctionTool`, `BaseTool`, `Tools`,
`ToolExecutor`, compatibility registries, tool specs, tool results, MCP bridges,
security policies, and built-in tools. Agents receive tools locally through
`tools=[...]`, describe them to model providers, execute permitted calls, and add
tool results back into the runtime context.

## Design Philosophy

Tooling should be agent-local, typed, and permission-aware. New application code
should pass tools directly to agents or wrap collections with `Tools`. Legacy
registries remain available for compatibility, but the catalog-first pattern
makes tool availability easier to inspect.

## Description Customization

Built-in tools can expose application-specific model guidance without changing
their execution contract. `BaseTool.customize()` returns a new tool view that
can replace the tool description and descriptions of existing top-level
parameters:

```python
custom_lookup = lookup_tool.customize(
    description="Search our internal documentation.",
    parameter_descriptions={"query": "Use our product terminology."},
)
```

Customization never adds parameters, changes validation, or mutates the
original tool. Use a concrete custom tool or adapter when an application needs
new business inputs or behavior. Use `with_activity()` for a separate typed
model-authored annotation that should be captured and removed before the
wrapped tool executes.

## Usage

```python
from vidbyte import Agent, Tools, tool

@tool
def lookup_user(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

catalog = Tools([lookup_user])
agent = Agent(
    name="tool-user",
    system_prompt="Use tools when they help.",
    provider="openai",
    model_name="gpt-4.1",
    tools=catalog,
)

print(catalog.names())
print(catalog.provider_schemas("openai"))
```

## Key Modules

- `decorators.py`: `@tool` and `vidbyte_tool` function wrappers.
- `function_tool.py`: `FunctionTool` creation from Python callables.
- `customization.py`: Description-only model-facing views over existing tools.
- `catalog.py`: agent-local immutable tool catalog.
- `executor.py`: local tool call execution.
- `security/`: permission policies and sandbox contracts.
- `mcp/`: MCP clients, transports, presets, and bridged tools.
- `builtins/`: code search, context, context primitives, editing, memory, MCP, handoff, pause, and utility tools.
- `builtins/operations/`: priced search and fetch tools plus the executing provider clients.

## Cooperative Pause

`PauseAgentTool` exposes the model-facing `pause_agent` tool. Attach it to the
agent that should wait and configure a maximum duration, for example
`PauseAgentTool(max_seconds=30)`. The tool delegates to the same async
`BaseAgent.pause(seconds)` API used by application code, so the wait yields to
the event loop and task cancellation remains visible. It is a timed wait only;
it does not persist run state or provide durable pause/resume or external run
cancellation.

## Priced Operation Tools

Search and fetch tools subclass `PricedOperationTool`, which carries the
`(operation, provider)` identity the runtime prices against
[`operation_pricing`](../lib/registries/operation_pricing.py). Supply a client
and the tool performs the real provider request; omit it and the tool returns a
priced contract stub, so a tool can be wired into an agent before credentials
exist.

```python
from vidbyte.tools.builtins.operations import BraveClient, BraveSearchTool, RetryPolicy

search = BraveSearchTool(client=BraveClient(api_key, retry=RetryPolicy(max_attempts=3)))
```

The client owns transport policy — timeout, exponential backoff, retryable
status codes, and a response-body ceiling — and never discovers a credential on
its own. A successful call returns two channels on one result: `output` holds a
compact summary for the model's context window, and
`metadata["operation_payload"]` holds the typed `SearchPayload` or
`FetchPayload` the application consumes, each record keeping its undecoded
vendor mapping under `raw`.

Billing is attempt-accurate. A tool declares `units` and `attempts` in
`metadata["operation_usage"]`, and the runtime records one priced operation per
attempt — so three retries of a flat-rate search bill three times, and a call
that exhausts its retries and fails is still billed for the attempts it spent. A
call that never reached the provider declares `units=0` and bills nothing.

## Related Layers

Tools are attached to [`agents`](../agents/README.md), governed by
[`middleware`](../middleware/README.md), exposed through
[`mcp_server`](../mcp_server/README.md), and formatted for
[`providers`](../providers/README.md).
