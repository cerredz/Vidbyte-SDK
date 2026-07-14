# Create Agent with Tools

For a `LongRunningParadigm`, attach role tools through `AgentRoleSettings` rather
than reusing one stateful `BaseAgent`. Planner/verifier/auditor/synthesizer tools
must be `SAFE` or `READ`. Worker/repair `WRITE` or `EXECUTE` tools require an
`AttemptIsolator` unless the settings explicitly allow unsafe unisolated side
effects. The harness constructs fresh agents and adds bounded procedure and
verified-dependency load tools itself.

Create an agent equipped with tools that it can call during execution. Tools are the primary way to extend an agent beyond text generation — they let the model search files, run code, call APIs, query databases, and more.

When tools are attached, the agent automatically enters a tool-calling loop: the model can request tool executions, the agent runs them, feeds results back to the model, and repeats until the model produces a final text response.

## Basic Example

Create custom tools with the `@tool` decorator and attach them directly to an agent:

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

The SDK ships with prebuilt tools for common software engineering tasks. Import them from their category packages and attach them to agents without writing any tool logic yourself:

```python
from vidbyte import Agent
from vidbyte.tools.builtins.code_search import GrepTool, GlobTool, SemanticSearchTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins import ForkConversationTool

agent = Agent(
    name="dev-agent",
    system_prompt="You are a software engineer with code tools.",
    tools=[
        GrepTool(root_dir="."),       # search file contents by regex
        GlobTool(root_dir="."),       # find files by pattern
        SemanticSearchTool(),         # semantic code search
        CalculatorTool(),             # evaluate math expressions
        CodeExecutionTool(),          # execute Python in sandbox
        ForkConversationTool(),       # run an isolated child conversation now
    ],
    provider="openai",
    model_name="gpt-4.1",
)
```

For a complete catalog of every built-in tool, see [`skills/usage/available_tools.md`](available_tools.md).

## Agent Forking Tool

`ForkConversationTool` lets the model ask the current agent to fork itself and run a focused child branch immediately. It is separate from durable session fork tools: it spends model tokens now, returns the child answer as a tool result, and keeps child state isolated unless the parent incorporates that answer.

```python
from vidbyte import Agent
from vidbyte.tools.builtins import ForkConversationTool

agent = Agent(
    name="planner",
    system_prompt="Fork isolated checks when useful.",
    tools=[ForkConversationTool(allowed_models=["gpt-4.1-mini"])],
    provider="openai",
    model_name="gpt-4.1",
)
```

The tool is non-escalating: model swaps must be allowlisted, extra tools must come from developer-provided `extra_toolsets`, `max_iterations` cannot exceed the parent cap, and permission policy is inherited.

## Session Tools

Session tools let a model checkpoint, fork, rewind, or resume durable threads through a `SessionStore`. They auto-bind to the active `Session`.

```python
from vidbyte import Agent, FileSessionStore, Session
from vidbyte.tools.builtins.sessions import (
    BatchForkTool,
    CheckpointTool,
    ForkTool,
    ResumeAppendTool,
    ResumeOutputTool,
    ResumeReplaceTool,
    RewindTool,
    SessionTool,
)

store = FileSessionStore("./.vidbyte/sessions")
agent = Agent(
    name="durable-worker",
    system_prompt="Use session tools for durable thread operations.",
    tools=[
        CheckpointTool(store),
        ForkTool(store),
        BatchForkTool(store),
        RewindTool(store),
        ResumeReplaceTool(store),
        ResumeAppendTool(store),
        ResumeOutputTool(store),
        SessionTool(store),
    ],
    provider="openai",
    model_name="gpt-4.1",
)
session = Session(agent, store=store)
```

Cross-session reads are gated by `SessionScope`; grant access explicitly when one agent should resume another agent's thread.

## Filesystem Tools

Filesystem tools give agents read/write access to the filesystem. Tools like `WriteTextTool`, `DeleteTool`, and `MakeDirTool` require `WRITE` permission — you must explicitly allow them with a permission policy:

```python
from vidbyte import Agent
from vidbyte.tools.security import PermissionPolicy
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

Every tool declares a permission level (`SAFE`, `READ`, `WRITE`, `EXECUTE`). The agent evaluates each tool call against its permission policy. The default policy allows `SAFE` and `READ` tools, and denies `WRITE` and `EXECUTE` tools — this prevents accidental filesystem modifications or code execution.

```python
from vidbyte import ToolPermission
from vidbyte.tools.security import PermissionPolicy

# Allow everything — use with caution
agent = Agent(..., permission_policy=PermissionPolicy.allow_all())

# Allow specific permissions while blocking others
policy = PermissionPolicy(allowed={ToolPermission.WRITE}, denied={ToolPermission.EXECUTE})
agent = Agent(..., permission_policy=policy)
```

Permission decisions are made per tool call, not per tool. An agent with `WRITE` access can call any `WRITE`-level tool, but can only call specific `EXECUTE`-level tools if `EXECUTE` is in the allowed set.

## Adding Tools After Construction

Tools can be added to an existing agent without re-creating it. `add_tool()` returns `self` for chaining:

```python
agent = Agent(name="base", system_prompt="...", provider="openai", model_name="gpt-4.1")
agent = agent.add_tool(get_time)      # returns self for chaining
agent = agent.add_tool(calculator)
```

This is useful in multi-step agent setup where tools are configured conditionally.

## MCP Tools

External MCP (Model Context Protocol) servers can be attached to agents, making their tools available as if they were built-in. MCP servers can provide filesystem access, database queries, API integrations, and more — without the SDK needing to know about them at build time:

```python
# Attach an MCP filesystem server — its tools become available on the agent
agent = await Agent(
    name="mcp-agent",
    system_prompt="You have filesystem access via MCP.",
    provider="openai",
    model_name="gpt-4.1",
).attach_mcp_server(
    ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/files"],
    name="filesystem",
)
```

## Tool Execution Loop

When tools are present, the agent automatically runs a tool execution loop. This loop is transparent — you call `arun()` once and the agent handles all tool interactions internally:

1. **Format tools** into provider-native schemas (OpenAI function calling, Anthropic tool use, etc.)
2. **Call the model** runner with the user prompt and formatted tool specs
3. **Parse** any tool calls from the model's response
4. **Check** each tool call against the agent's permission policy
5. **Execute** allowed tools and feed their results back to the model as tool response messages
6. **Repeat** from step 2 until the model produces a final text response or `max_tool_rounds` is reached

The internal `isDone` tool is injected automatically so the model can signal when it is finished with tool calling and ready to return a final answer.

## Best Practices

- **Start with built-in tools** before building custom ones. The SDK's prebuilt tools cover common patterns.
- **Set a `max_tool_rounds`** limit to prevent infinite tool-calling loops, especially with agents that have filesystem or code execution access.
- **Use the most restrictive permission policy possible.** Only grant `WRITE` or `EXECUTE` access when your use case requires it.
- **Group tools into a `Tools` catalog** when attaching to multiple agents to avoid duplication and ensure consistency.
- **Use MCP tools** for integrating external systems rather than building custom SDK tools for every API.
- **Use session tools for durable thread operations** and `ForkConversationTool` for immediate isolated child execution.
