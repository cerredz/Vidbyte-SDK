# Tools

## Folder Intent

This folder owns the top-level tool contract, decorator, catalog, executor, adapters, and namespace client. It bridges model-requested tool calls to local Python callables, agent-as-tool wrappers, dynamic actor helpers, and compatibility surfaces.

## Non-Goals

This pass does not document or modify subfolders such as builtins, mcp, filesystem, or security; those folders own their own specialized tool families.

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

## File Index

- `__init__.py`: Exports the public tool contracts and namespace client. Gives SDK users stable imports for implementing, registering, and executing native or bridged tools. Key symbols: AgentTool, BaseTool, FunctionTool, ToolCall, ToolCallContext, ToolCallState.
- `_internal.py`: Owns internal behavior inside the vidbyte/tools layer. Key symbols: IsDoneTool, with_internal_agent_tools, IS_DONE_TOOL_NAME.
- `adapters.py`: Normalizes supported tool-like objects into BaseTool instances. Key symbols: ensure_tool, ensure_tools.
- `agent_tool.py`: Wraps an agent so another agent can call it as a tool. Key symbols: AgentTool.
- `base.py`: Defines the abstract base class and structural protocol for all Vidbyte SDK tools. Provides shared call validation and a small async execution contract while supporting both class-based and protocol-based developer tools. Key symbols: BaseTool, ToolLike.
- `catalog.py`: Defines the public Tools catalog for agent-local tool inspection and lookup. Replaces registry-first public usage with a lightweight catalog that can describe tools, expose provider schemas, and support internal agent lookup. Key symbols: Tools.
- `client.py`: Provides the SDK namespace client for tool operations. Owns the default registry and executor exposed from VidbyteSDK().tools without auto-registering potentially environment-specific tools. Key symbols: ToolsClient.
- `continual_trace.py`: Defines the internal tool used by the continual trace agent. Provides one model-visible updateTrace function that validates trace updates against the schema and deterministically merges them (append for arrays, deep merge for objects, replace for scalars) into the accumulated artifact. Key symbols: UpdateTraceTool, UPDATE_TRACE_TOOL_NAME.
- `decorators.py`: Provides decorators that turn user callables into SDK tools. Key symbols: tool, vidbyte_tool.
- `dynamic_actor.py`: Defines the DynamicActorTool allowing active actors to dynamically spawn sub-actors. Enables autonomous model-driven agent creation during execution to solve sub-tasks. Key symbols: DynamicActorTool.
- `executor.py`: Implements the standard tool execution pipeline. Centralizes lookup, permission checks, call validation, async execution, and exception normalization so concrete tools stay focused on domain logic. Key symbols: ToolExecutor.
- `function_tool.py`: Adapts Python callables into Vidbyte ToolSpec, validation, and execution contracts. Key symbols: FunctionTool.
- `mixins.py`: Owns mixins behavior inside the vidbyte/tools layer. Key symbols: ToolMixin.
- `types.py`: Re-exports public tool data contracts from the SDK dataclass namespace. Preserves existing `vidbyte.tools.types` imports while keeping dataclass definitions under `vidbyte.lib.dataclasses`. Key symbols: ToolCall, ToolCallContext, ToolCallState, ToolParameter, ToolPermission, ToolResult.

## Subfolder Routing

- `builtins/`: Specialized built-in tools; outside this pass.
- `filesystem/`: Filesystem tool family; outside this pass.
- `mcp/`: MCP bridge and transport helpers; outside this pass.
- `security/`: Permission and sandbox policy; outside this pass.

## Logs

- 2026-07-07: New user-facing code should prefer Tools and @tool while legacy registry compatibility remains available for older examples.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
