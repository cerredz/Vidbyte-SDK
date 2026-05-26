# Tool Request & Response Lifecycle

This traces a `tools/call` request from raw stdin bytes to the response written to stdout.

## Full Trace

```
Client sends:
{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"studio.agents.list","arguments":{}}}
```

### Step 1 — `McpStudioServer.run()` reads the line

`run()` calls `self._read_input(reader)`:

```python
line = await reader.readline()          # b'{"jsonrpc":...}\n'
line_str = line.decode("utf-8").strip() # '{"jsonrpc":...}'
request = json.loads(line_str)          # dict
```

`_read_input` returns the parsed dict. Any malformed JSON here triggers:
```python
McpSchema.mcp_error_response(None, -32700, "Parse error")
```
written to stdout, then `_SKIP` is returned and the loop continues.

### Step 2 — `McpStudioServer._dispatch()` routes to the handler

```python
method = request.get("method")   # "tools/call"
handler = self._handler_map.get("tools/call")  # ToolsCallHandler instance
return await handler.handle(request_id=5, params={"name": "studio.agents.list", "arguments": {}})
```

If `method` is not in `_handler_map`:
```python
McpSchema.mcp_error_response(request_id, -32601, "Method not found: ...")
```

### Step 3 — `ToolsCallHandler.handle()` validates and executes

Located in `vidbyte/mcp_server/server/handlers/tools_call.py`:

```python
tool_name = "studio.agents.list"
arguments = {}
result = await self._registry.execute("studio.agents.list", {})
```

`StudioToolRegistry.execute()` looks up `studio.agents.list` in `_tool_map` and calls:
```python
await tool.execute(ToolCall("studio.agents.list", {}))
```

### Step 4 — `StudioAgentsListTool.execute()` runs the SDK logic

Located in `vidbyte/mcp_server/handlers.py`:

```python
cards = [{"name": ..., "description": ..., ...} for agent_name, agent in self._agents.items()]
return ToolResult.success("studio.agents.list", json.dumps(cards, indent=2))
```

### Step 5 — `ToolsCallHandler` converts the result to MCP format

```python
content = McpSchema.tool_result_to_mcp_content(result)
# → [{"type": "text", "text": "[{\"name\": ...}]"}]

return McpSchema.mcp_tool_success_result(request_id, content)
# → {"jsonrpc":"2.0","id":5,"result":{"content":[{"type":"text","text":"..."}]}}
```

If `result.status == "error"` or `result.output.startswith("Error:")`:
```python
return McpSchema.mcp_tool_error_result(request_id, result.output)
# → {"jsonrpc":"2.0","id":5,"result":{"content":[...],"isError":true}}
```

### Step 6 — `McpStudioServer._write_response()` flushes to stdout

```python
line = json.dumps(response, default=str)
sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
sys.stdout.buffer.flush()
```

Client receives:
```json
{"jsonrpc":"2.0","id":5,"result":{"content":[{"type":"text","text":"[{\"name\":\"my-agent\",...}]"}]}}
```

---

## Error Paths

| What went wrong | Where caught | Response |
|----------------|-------------|----------|
| Invalid JSON | `_read_input` | `{"error":{"code":-32700,"message":"Parse error"}}` |
| Not a JSON object | `_read_input` | `{"error":{"code":-32600,"message":"Invalid request"}}` |
| Unknown method string | `_dispatch` | `{"error":{"code":-32601,"message":"Method not found: ..."}}` |
| Missing/wrong params | handler `.handle()` | `{"error":{"code":-32602,"message":"Invalid params"}}` |
| Tool not found in registry | `StudioToolRegistry.execute` | `ToolResult.error(...)` → `{"result":{"isError":true,...}}` |
| Unexpected exception | `run()` except clause | `{"error":{"code":-32603,"message":"Internal error: ..."}}` |

Note: tool errors (`isError: true`) are NOT JSON-RPC errors — they are successful JSON-RPC responses whose content contains an error flag. The distinction matters for client-side handling.

---

## Key Types

| Type | Module | Purpose |
|------|--------|---------|
| `ToolCall` | `vidbyte.tools.types` | Wraps tool name + arguments dict passed into `execute()` |
| `ToolResult` | `vidbyte.tools.types` | Carries status (`"success"` or `"error"`) + output string |
| `ToolSpec` | `vidbyte.tools.types` | Tool name, description, parameters, permission |
| `McpSchema` | `vidbyte.mcp_server.schema` | All JSON-RPC serialization helpers |
| `StudioToolRegistry` | `vidbyte.mcp_server.handlers` | Maps tool names to `BaseTool` instances |
