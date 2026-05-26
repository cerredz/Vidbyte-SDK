# MCP Server

## Architecture

The MCP server exposes Vidbyte SDK capabilities as MCP tools over a stdio JSON-RPC 2.0 transport. Three layers handle everything:

```
stdin bytes
    │
    ▼
McpStudioServer._read_input()       ← decode, parse, validate
    │
    ▼
McpStudioServer._dispatch()         ← method → handler lookup
    │
    ├─ InitializeHandler             vidbyte/mcp_server/server/handlers/initialize.py
    ├─ ToolsListHandler              vidbyte/mcp_server/server/handlers/tools_list.py
    ├─ ToolsCallHandler              vidbyte/mcp_server/server/handlers/tools_call.py
    ├─ PromptsListHandler            vidbyte/mcp_server/server/handlers/prompts_list.py
    └─ PromptsGetHandler             vidbyte/mcp_server/server/handlers/prompts_get.py
    │
    ▼
McpStudioServer._write_response()   ← serialize to stdout
```

## File Map

| File | Responsibility |
|------|---------------|
| `vidbyte/mcp_server/__init__.py` | Public re-export of `McpStudioServer` |
| `vidbyte/mcp_server/__main__.py` | CLI entry point (`python -m vidbyte.mcp_server`) |
| `vidbyte/mcp_server/schema.py` | `McpSchema` class — all JSON-RPC serialization helpers |
| `vidbyte/mcp_server/handlers.py` | `StudioToolRegistry` + 8 studio `BaseTool` subclasses |
| `vidbyte/mcp_server/server/__init__.py` | Re-exports `McpStudioServer` and error constants |
| `vidbyte/mcp_server/server/core.py` | `McpStudioServer` — I/O loop, `_read_input`, `_dispatch` |
| `vidbyte/mcp_server/server/handlers/__init__.py` | `_BaseHandler` ABC |
| `vidbyte/mcp_server/server/handlers/initialize.py` | `initialize` method handler |
| `vidbyte/mcp_server/server/handlers/tools_list.py` | `tools/list` method handler |
| `vidbyte/mcp_server/server/handlers/tools_call.py` | `tools/call` method handler |
| `vidbyte/mcp_server/server/handlers/prompts_list.py` | `prompts/list` method handler |
| `vidbyte/mcp_server/server/handlers/prompts_get.py` | `prompts/get` method handler |

## Two Distinct "Handler" Concepts

**Don't confuse these two things:**

- `vidbyte/mcp_server/handlers.py` — **Studio tools**: `StudioAgentsListTool`, `StudioToolsListTool`, etc. These are `BaseTool` subclasses that get called when a client sends `tools/call`. They wrap SDK capabilities (agent list, tool list, strategy list, etc.).

- `vidbyte/mcp_server/server/handlers/*.py` — **JSON-RPC method handlers**: `InitializeHandler`, `ToolsListHandler`, etc. These are `_BaseHandler` subclasses that handle the MCP protocol level (which JSON-RPC method was called). `ToolsCallHandler` is the one that delegates to studio tools.

## McpSchema

All JSON-RPC serialization goes through `McpSchema` static methods:

```python
from vidbyte.mcp_server.schema import McpSchema

McpSchema.mcp_result_response(request_id, {"key": "value"})
McpSchema.mcp_error_response(request_id, -32601, "Method not found: foo")
McpSchema.mcp_tool_success_result(request_id, content_list)
McpSchema.mcp_tool_error_result(request_id, "Something went wrong")
McpSchema.tool_spec_to_mcp_tool(tool.spec())
McpSchema.tool_result_to_mcp_content(tool_result)
```

Never build raw JSON-RPC dicts by hand — always use `McpSchema`.

## Skill Files

| Skill | File |
|-------|------|
| Add a new studio tool | [`add-tool.md`](add-tool.md) |
| Add a new JSON-RPC method handler | [`add-handler.md`](add-handler.md) |
| Trace a tools/call request end-to-end | [`tool-request-response.md`](tool-request-response.md) |
