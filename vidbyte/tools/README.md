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

## Workflow capability boundaries

`vidbyte.workflows.AgentStage` applies two independent layers to tools:

1. `ToolVisibility` derives the exact catalog whose schemas are sent to the
   model for that stage (`inherit`, `none`, `read_only`, or an exact name set).
2. `ActionPolicy` evaluates every visible call immediately before execution.
   Built-in guards can constrain command prefixes and deny patterns, path
   globs, and estimated changed lines per stage invocation.

Removing a schema is stronger than asking the model not to use a tool, but it
is not a host sandbox. Action guards are defense in depth and do not replace
workspace, filesystem, process, or network isolation. Unknown mutating-tool
impact fails closed in strict edit-budget mode.

Successful workflow agent calls emit bounded authorization evidence. Successful
`patch_file`, `replace_text`, and `write_text` calls can also trigger a declared
file-change detour, which stops the current agent invocation after the tool
boundary and transfers control to a validation stage. External effects are not
rolled back; replay-safe tools should honor the workflow stage idempotency key.

## Key Modules

- `decorators.py`: `@tool` and `vidbyte_tool` function wrappers.
- `function_tool.py`: `FunctionTool` creation from Python callables.
- `catalog.py`: agent-local immutable tool catalog.
- `executor.py`: local tool call execution.
- `security/`: permission policies and sandbox contracts.
- `mcp/`: MCP clients, transports, presets, and bridged tools.
- `builtins/`: code search, context, context primitives, editing, memory, MCP, handoff, and utility tools.

## Related Layers

Tools are attached to [`agents`](../agents/README.md), governed by
[`middleware`](../middleware/README.md), exposed through
[`mcp_server`](../mcp_server/README.md), and formatted for
[`providers`](../providers/README.md).
