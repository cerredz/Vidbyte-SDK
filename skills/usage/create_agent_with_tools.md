# Create Agent with Tools

Create an agent equipped with tools that it can call during execution.

## Basic Example

```python
from vidbyte import Agent, tool

@tool
def get_time():
    """Return the current server time."""
    from datetime import datetime
    return datetime.now().isoformat()

@tool
def calculator(expression: str) -> float:
    """Evaluate a mathematical expression."""
    return eval(expression)

agent = Agent(
    name="tool-agent",
    system_prompt="You have access to tools. Use get_time for the current time and calculator for math.",
    tools=[get_time, calculator],
    provider="openai",
    model_name="gpt-4.1",
)

reply = await agent.arun("What is 15 * 23 plus the current time?")
```

## Built-in Tools

```python
from vidbyte import Agent
from vidbyte.tools.builtins.code_search import GrepTool, GlobTool, SemanticSearchTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool

agent = Agent(
    name="dev-agent",
    system_prompt="You are a software engineer with code tools.",
    tools=[
        GrepTool(root_dir="."),
        GlobTool(root_dir="."),
        SemanticSearchTool(),
        CalculatorTool(),
        CodeExecutionTool(),
    ],
    provider="openai",
    model_name="gpt-4.1",
)
```

## Filesystem Tools

```python
from vidbyte import Agent
from vidbyte.tools.filesystem import (
    ReadTextTool, WriteTextTool, ListDirTool, MakeDirTool,
    DeleteTool, CopyTool, MoveTool, ExistsTool,
)

agent = Agent(
    name="fs-agent",
    system_prompt="You manage files on disk.",
    tools=[
        ReadTextTool(),
        WriteTextTool(),
        ListDirTool(),
        MakeDirTool(),
        DeleteTool(),
    ],
    permission_policy=PermissionPolicy.allow_all(),  # needed for WRITE/EXECUTE tools
    provider="openai",
    model_name="gpt-4.1",
)
```

## Permission Policy

Tools declare a permission level. The agent evaluates each tool call against its policy. Default policy allows `SAFE` and `READ`, denies `WRITE` and `EXECUTE`.

```python
from vidbyte import PermissionPolicy, ToolPermission

# Allow everything
agent = Agent(..., permission_policy=PermissionPolicy.allow_all())

# Allow specific
policy = PermissionPolicy(allowed={ToolPermission.WRITE}, denied={ToolPermission.EXECUTE})
agent = Agent(..., permission_policy=policy)
```

## Adding Tools After Construction

```python
agent = Agent(name="base", system_prompt="...", provider="openai", model_name="gpt-4.1")
agent = agent.add_tool(get_time)   # returns self for chaining
agent = agent.add_tool(calculator)
```

## Tool Execution Loop

When tools are present, the agent runs an automatic tool loop:
1. Formats tools into provider-native schemas
2. Calls the model runner with the prompt + tools
3. Parses any tool calls from the model response
4. Checks each tool call against the permission policy
5. Executes allowed tools and feeds results back to the model
6. Repeats until a final text response or `max_tool_rounds` is reached

The internal `isDone` tool is injected automatically so the model can signal when it is finished.
