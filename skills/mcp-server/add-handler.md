# Add a New JSON-RPC Method Handler

A JSON-RPC method handler responds to a specific MCP method string (e.g., `"resources/list"`). Add one when you need to implement a new top-level MCP protocol method — not just a new tool.

## When to Use This (vs. add-tool.md)

| You want to... | Use |
|---------------|-----|
| Expose a new SDK capability clients can call via `tools/call` | `add-tool.md` |
| Add a new MCP protocol method (e.g., `resources/list`, `sampling/createMessage`) | This file |

## Steps

### 1. Create the handler file

Create `vidbyte/mcp_server/server/handlers/<method_name>.py`. Use underscores for slashes, e.g., `resources_list.py` for `resources/list`:

```python
"""Context Protocol Header

Description:
    Handles the MCP <method> request (method: "<method>").
Purpose:
    <one line on what this returns to the client>
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler

JSONRPC_INVALID_PARAMS = -32602


class MyMethodHandler(_BaseHandler):
    """Handles the MCP <method> request."""

    def __init__(self, dependency: SomeType) -> None:
        # Store whatever the handler needs to build its response.
        self._dep = dependency

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        # Validate params, build response, return it.
        if not isinstance(params, Mapping):
            return McpSchema.mcp_error_response(request_id, JSONRPC_INVALID_PARAMS, "Invalid params")
        # ... business logic ...
        return McpSchema.mcp_result_response(request_id, {"key": "value"})
```

**Rules:**
- Inherit from `_BaseHandler` (imported from `vidbyte.mcp_server.server.handlers`).
- Always accept `(self, request_id, params)` — `params` may be `None` if the client sends no params.
- Always use `McpSchema` for building responses — never raw dicts.
- Validate params before using them; return `JSONRPC_INVALID_PARAMS` on bad input.

### 2. Register in the handler map

In `vidbyte/mcp_server/server/core.py`, import your handler and add it to `_handler_map` in `__init__`:

```python
from vidbyte.mcp_server.server.handlers.my_method import MyMethodHandler

# Inside McpStudioServer.__init__:
self._handler_map: dict[str, _BaseHandler] = {
    "initialize":      InitializeHandler(...),
    "tools/list":      ToolsListHandler(...),
    "tools/call":      ToolsCallHandler(...),
    "prompts/list":    PromptsListHandler(...),
    "prompts/get":     PromptsGetHandler(...),
    "my/method":       MyMethodHandler(self._some_dependency),  # ← add here
}
```

### 3. Expose the capability in initialize (if needed)

If the MCP protocol requires advertising the capability, update `InitializeHandler.handle()` in `vidbyte/mcp_server/server/handlers/initialize.py`:

```python
return McpSchema.mcp_result_response(
    request_id,
    {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},
            "prompts": {},
            "resources": {},   # ← add if needed
        },
        "serverInfo": {"name": self._name, "version": self._version},
    },
)
```

### 4. Verify

```bash
python -m pytest tests/test_mcp_studio_server.py -v
```

Add a test that dispatches the new method directly:

```python
async def test_my_method(self) -> None:
    server = McpStudioServer(...)
    response = await server._dispatch({
        "jsonrpc": "2.0", "id": 1,
        "method": "my/method",
        "params": {...},
    })
    self.assertIn("result", response)
```

## Error Constants

Use these constants from `vidbyte.mcp_server.server.core` (or define locally in the handler):

| Constant | Code | When to use |
|----------|------|-------------|
| `JSONRPC_PARSE_ERROR` | -32700 | Malformed JSON (handled in `_read_input`, not handlers) |
| `JSONRPC_INVALID_REQUEST` | -32600 | Request is not a Mapping |
| `JSONRPC_METHOD_NOT_FOUND` | -32601 | No handler for the method (handled in `_dispatch`) |
| `JSONRPC_INVALID_PARAMS` | -32602 | Handler received bad params |
| `JSONRPC_INTERNAL_ERROR` | -32603 | Unexpected exception (caught in `run()`) |
