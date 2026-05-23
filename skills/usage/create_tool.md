# Create Tool

Create a tool that agents can call during execution.

## Decorator (Recommended)

The `@tool` decorator wraps a Python function into a `FunctionTool`. It inspects function signature, type hints, and docstring.

```python
from vidbyte import tool, ToolPermission

# Bare decorator - name/description derived from function
@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Sunny in {city}"

# Configured decorator
@tool(name="fetch_user", description="Fetch a user by their ID", permission=ToolPermission.READ)
def fetch_user(user_id: int) -> dict:
    """Retrieve user profile from the database."""
    return {"id": user_id, "name": "Alice"}

# Async function
@tool
async def search_docs(query: str) -> list[str]:
    """Search the documentation index."""
    await asyncio.sleep(0.1)
    return [f"Result for {query}"]
```

## Permission Levels

```python
from vidbyte import ToolPermission

ToolPermission.SAFE     # read-only, no side effects (default)
ToolPermission.READ     # reads external data
ToolPermission.WRITE    # mutates data or filesystem
ToolPermission.EXECUTE  # executes arbitrary code/commands
```

## BaseTool Subclass (Advanced)

```python
from vidbyte import BaseTool, ToolSpec, ToolCall, ToolResult, ToolParameter, ToolPermission

class DatabaseTool(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="db_query",
            description="Execute a read-only database query.",
            parameters=[
                ToolParameter(name="sql", type="string", description="SQL SELECT statement"),
            ],
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        sql = call.arguments.get("sql", "")
        try:
            result = await run_query(sql)  # your logic
            return ToolResult.success(self.name, result)
        except Exception as e:
            return ToolResult.error(self.name, str(e))
```

## Tools Catalog

The `Tools` catalog holds a normalized collection of tools.

```python
from vidbyte import Tools

catalog = Tools([tool1, tool2])
catalog.add(tool3)                     # immutable add, returns new Tools
catalog.add(tool3, replace=True)       # replace existing by name
catalog.extend([tool4, tool5])         # add multiple
catalog.without([tool1])               # remove tools
catalog.names()                        # tuple of tool names
catalog.all()                          # tuple of BaseTool instances
catalog.specs()                        # tuple of ToolSpec
```

## FunctionTool from a Callable

```python
from vidbyte import FunctionTool

def my_func(x: int) -> str:
    """Double the value."""
    return str(x * 2)

ft = FunctionTool(my_func, name="double", description="Double an integer")
# Equivalent to @tool above but constructed imperatively
```
