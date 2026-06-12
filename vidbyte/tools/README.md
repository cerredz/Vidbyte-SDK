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

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agents need controlled access to
retrieval, memory, editing, handoff, MCP, and context operations; the tools layer
turns those capabilities into explicit, inspectable contracts.

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
    runner=my_runner,
    tools=catalog,
)

print(catalog.names())
print(catalog.provider_schemas("openai"))
```

Create a class-based tool when execution needs state:

```python
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec

class TenantLookupTool(BaseTool):
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id

    def spec(self) -> ToolSpec:
        return ToolSpec(name="tenant_lookup", description="Look up tenant metadata.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success("tenant_lookup", f"tenant={self.tenant_id}")
```

Attach a preset MCP server when the agent needs external tools:

```python
import os

await agent.attach_preset_mcp_server(
    "github",
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]},
)
```

## Feature Coverage

- Function tools through `@tool` and `FunctionTool.from_function()`.
- Class-based tools through `BaseTool`, `ToolSpec`, `ToolCall`, and `ToolResult`.
- `Tools` catalogs for deterministic names, specs, provider schemas, and prompt descriptions.
- `ToolExecutor` and compatibility `ToolRegistry` for older registry-first code.
- Tool permissions and sandbox policy under `tools.security`.
- MCP clients, transports, presets, attachment helpers, and bridged MCP tools.
- Built-ins for code search, context primitives, editing, handoff, MCP attachment/search, memory providers, and utility tools.
- Provider-specific formatting through `ToolsFormatter`.

## Key Modules

- `decorators.py`: `@tool` and `vidbyte_tool` function wrappers.
- `function_tool.py`: `FunctionTool` creation from Python callables.
- `catalog.py`: agent-local immutable tool catalog.
- `executor.py`: local tool call execution.
- `security/`: permission policies and sandbox contracts.
- `mcp/`: MCP clients, transports, presets, and bridged tools.
- `builtins/`: code search, context, editing, memory, MCP, handoff, and utility tools.

## Related Layers

Tools are attached to [`agents`](../agents/README.md), governed by
[`middleware`](../middleware/README.md), exposed through
[`mcp_server`](../mcp_server/README.md), and formatted for
[`providers`](../providers/README.md).
