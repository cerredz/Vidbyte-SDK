# Add a New Studio Tool to the MCP Server

A "studio tool" is a `BaseTool` subclass that the MCP server exposes under a `studio.*` name. Clients see it in `tools/list` and can invoke it via `tools/call`.

## When to Use This

Add a studio tool when you want to expose a new SDK capability (e.g., `studio.context.list`, `studio.middleware.list`) to MCP clients without adding a new JSON-RPC method.

## Steps

### 1. Write the tool class

Add a new class to `vidbyte/mcp_server/handlers.py`, following the pattern of the existing tools:

```python
class StudioMyFeatureTool(BaseTool):
    def __init__(self, my_dependency: SomeType) -> None:
        # Store the dependency injected at construction time.
        self._dep = my_dependency

    def spec(self) -> ToolSpec:
        # Declare the tool's name, description, parameters, and permission.
        return ToolSpec(
            name="studio.myfeature.action",
            description="One-line description of what this tool does.",
            parameters=(
                ToolParameter(
                    name="param_name",
                    type="string",
                    description="What this parameter controls.",
                    required=True,
                ),
            ),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate inputs, run the operation, return a ToolResult.
        value = str(call.arguments.get("param_name") or "")
        if not value:
            return ToolResult.error("studio.myfeature.action", "Missing param_name.")
        result = self._dep.do_something(value)
        return ToolResult.success("studio.myfeature.action", json.dumps(result, indent=2))
```

**Rules:**
- Tool name must follow the `studio.<namespace>.<verb>` convention.
- Always validate required parameters and return `ToolResult.error(...)` with a clear message.
- Return structured JSON strings from `json.dumps(...)` — never raw Python objects.
- Set `permission=ToolPermission.EXECUTE` for all studio tools.

### 2. Register the tool in StudioToolRegistry

In `StudioToolRegistry._register_builtins()`, add your new tool to the `builtins` list:

```python
def _register_builtins(self) -> None:
    builtins: list[BaseTool] = [
        StudioAgentsListTool(self._agents),
        StudioAgentsRunTool(self._agents),
        # ... existing tools ...
        StudioMyFeatureTool(self._my_dependency),  # ← add here
    ]
    for tool in builtins:
        self._tool_map[tool.spec().name] = tool
```

If your tool needs a new dependency (like a list of items or a mapping), add it to `StudioToolRegistry.__init__` and `McpStudioServer.__init__` in the same way `agents`, `tools`, `strategy_names`, etc. are passed through.

### 3. Verify

Run the MCP tests:

```bash
python -m pytest tests/test_mcp_studio_server.py -v
```

Add a test case to `tests/test_mcp_studio_server.py` for the new tool:

```python
async def test_tools_call_my_feature(self) -> None:
    server = McpStudioServer(...)
    response = await server._dispatch({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "studio.myfeature.action", "arguments": {"param_name": "value"}},
    })
    self.assertNotIn("isError", response.get("result", {}))
```

## What NOT to Do

- Do not hard-code JSON-RPC error dicts — use `McpSchema.mcp_error_response(...)`.
- Do not access `self._tool_registry` directly from a handler — tools only know about their injected dependencies.
- Do not register the tool in `__init__.py` exports — studio tools are internal implementation details.
