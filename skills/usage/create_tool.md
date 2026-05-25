# Create Tool

Create a tool that agents can call during execution. Tools extend what an agent can do beyond text generation — they let the model interact with external systems, run computation, search code, read files, and more.

The recommended approach is the `@tool` decorator, which wraps any Python function into a `FunctionTool` by auto-inspecting its signature, type hints, and docstring. For advanced use cases, subclass `BaseTool` directly.

## Decorator (Recommended)

The `@tool` decorator is the simplest way to create a tool. It wraps a Python function and generates the tool specification automatically:

```python
from vidbyte import tool, ToolPermission

# Bare decorator — name and description derived from function name and docstring
@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Sunny in {city}"

# Configured decorator — explicit name, description, and permission level
@tool(name="fetch_user", description="Fetch a user by their ID", permission=ToolPermission.READ)
def fetch_user(user_id: int) -> dict:
    """Retrieve user profile from the database."""
    return {"id": user_id, "name": "Alice"}

# Async function — works the same way
@tool
async def search_docs(query: str) -> list[str]:
    """Search the documentation index."""
    await asyncio.sleep(0.1)
    return [f"Result for {query}"]
```

The decorator inspects your function and automatically generates:
- **`name`**: From the function name (or explicit `name=` parameter)
- **`description`**: From the docstring (or explicit `description=` parameter)
- **`parameters`**: From function signature and type hints
- **`permission`**: Defaults to `SAFE` unless specified

## Permission Levels

Every tool declares a permission level. The agent checks each tool call against its permission policy before execution:

```python
from vidbyte import ToolPermission

ToolPermission.SAFE     # read-only, no side effects — default for most tools
ToolPermission.READ     # reads external data (databases, APIs, files)
ToolPermission.WRITE    # mutates data or filesystem (write files, delete, create)
ToolPermission.EXECUTE  # executes arbitrary code or commands (Python exec, shell)
```

The default agent policy allows `SAFE` and `READ` tools, and denies `WRITE` and `EXECUTE`. Override with `permission_policy=PermissionPolicy.allow_all()` or a custom policy.

## BaseTool Subclass (Advanced)

For tools that need custom logic beyond what the decorator provides — custom validation, stateful behavior, or non-standard execution — subclass `BaseTool`:

```python
from vidbyte import BaseTool, ToolSpec, ToolCall, ToolResult, ToolParameter, ToolPermission

class DatabaseTool(BaseTool):
    def spec(self) -> ToolSpec:
        """Define the tool's name, description, parameters, and permission."""
        return ToolSpec(
            name="db_query",
            description="Execute a read-only database query.",
            parameters=[
                ToolParameter(name="sql", type="string", description="SQL SELECT statement"),
            ],
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute the tool with the given call arguments."""
        sql = call.arguments.get("sql", "")
        try:
            result = await run_query(sql)  # your database logic
            return ToolResult.success(self.name, result)
        except Exception as e:
            return ToolResult.error(self.name, str(e))
```

Use `BaseTool` when you need:
- Programmatic parameter definition (vs. function signature introspection)
- Custom error handling and result formatting
- Stateful tools that maintain connections or caches
- Tools that wrap non-Python APIs or SDKs

## Tools Catalog

The `Tools` catalog holds an immutable, deduplicated collection of tools. It's the standard way to group tools for attachment to agents:

```python
from vidbyte import Tools

catalog = Tools([tool1, tool2])
catalog.add(tool3)                     # immutable add — returns new Tools instance
catalog.add(tool3, replace=True)       # replace existing tool by name
catalog.extend([tool4, tool5])         # add multiple tools at once
catalog.without([tool1])               # remove tools — returns new Tools
catalog.names()                        # tuple of tool names ("tool1", "tool2", ...)
catalog.all()                          # tuple of BaseTool instances
catalog.specs()                        # tuple of ToolSpec — sent to the model provider
```

The catalog is immutable by design. Operations like `add()`, `extend()`, and `without()` return new `Tools` instances — the original is never modified. This prevents accidental tool leakage between agents.

## FunctionTool from a Callable

For programmatic construction without the decorator, use `FunctionTool` directly:

```python
from vidbyte import FunctionTool

def my_func(x: int) -> str:
    """Double the value."""
    return str(x * 2)

ft = FunctionTool(my_func, name="double", description="Double an integer")
# Equivalent to @tool above but constructed imperatively
```

This is useful when you already have a callable and want to wrap it without modifying its source.

## Best Practices

- **Use the `@tool` decorator** for simple tools — it handles most cases with zero boilerplate.
- **Set appropriate permission levels** — be honest about what your tool does. `SAFE` tools can't write files.
- **Make docstrings descriptive** — the model uses the description to decide when to call your tool.
- **Use type hints** — they become the parameter schema the model sees. `str`, `int`, `float`, `bool`, `dict`, `list` are all supported.
- **Return simple types** — strings, numbers, dicts, and lists serialize cleanly. Avoid returning complex objects the model can't interpret.
- **Handle errors gracefully** — return `ToolResult.error()` with a clear message instead of letting exceptions propagate.
