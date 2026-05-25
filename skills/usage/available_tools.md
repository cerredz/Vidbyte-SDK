# Available Tools

Tools included out of the box in the Vidbyte SDK. Every tool is a callable capability that models can invoke during execution. Tools extend what an agent can do beyond text generation — they let agents search code, read files, run calculations, edit files, and more.

Import tools from their category packages under `vidbyte.tools.builtins.*` or `vidbyte.tools.filesystem`.

## Decorator (Create Your Own)

The foundation for all tool creation. The `@tool` decorator wraps any Python function into a `FunctionTool` that agents can call. It automatically inspects the function signature, type hints, and docstring to generate the tool specification. This is the recommended way to create tools for most use cases.

| Tool | Import | Description |
|------|--------|-------------|
| `@tool` | `from vidbyte import tool` | Wrap any Python function into a tool — signature, type hints, and docstring are auto-inspected |
| `@vidbyte_tool` | `from vidbyte import vidbyte_tool` | Alias for `@tool`, same behavior |
| `FunctionTool` | `from vidbyte import FunctionTool` | Imperative construction from a callable — use when you need to build tools programmatically |
| `Tools` | `from vidbyte import Tools` | Immutable tool catalog (Sequence) — the standard way to group tools for an agent |
| `ToolRegistry` | `from vidbyte import ToolRegistry` | Mutable, thread-safe tool registry — used internally and for dynamic tool management |

## Code Search

Code search tools let agents find and understand code in a repository. They support pattern matching (glob), regex search (grep), and semantic search (embeddings). Attach these to software engineering agents so they can navigate unfamiliar codebases.

```python
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
```

| Tool | Description |
|------|-------------|
| `GlobTool(root_dir=".")` | Find files by glob pattern (e.g., `**/*.py`, `src/**/*.ts`). Returns matching file paths. |
| `GrepTool(root_dir=".")` | Search file contents by regex pattern. Returns matching lines with file paths and line numbers. |
| `SemanticSearchTool()` | Semantic (embedding-based) code search. Finds code that is semantically related to a query, not just text matches. |

These are the most commonly used built-in tools for agents that need to understand and modify codebases.

## Editing

Editing tools let agents modify source files with precision. The patch tool uses exact string replacement — find a string in a file and replace it — which is safer and more predictable than line-based editing.

```python
from vidbyte.tools.builtins.editing import PatchTool
```

| Tool | Description |
|------|-------------|
| `PatchTool()` | Exact string-replacement patch editing. Finds an exact string in a file and replaces it with new content. Fails if the old string is not found or appears multiple times. |

## Context

Context tools help agents manage their conversation context to stay within token limits. The context compaction tool summarizes or prunes conversation history so agents can work on long-running tasks without exceeding context windows.

```python
from vidbyte.tools.builtins.context import ContextCompactionTool
```

| Tool | Description |
|------|-------------|
| `ContextCompactionTool()` | Compact conversation context to save tokens. Summarizes older messages so the agent can continue working without losing important context. |

## Computation

Computation tools give agents the ability to evaluate math, execute code in sandboxes, and retrieve documents from indexes. These are useful for agents that need to verify calculations, run code snippets, or search through documentation.

```python
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
```

| Tool | Description |
|------|-------------|
| `CalculatorTool()` | Evaluate mathematical expressions safely. Supports standard arithmetic, functions, and constants. |
| `CodeExecutionTool()` | Execute Python code in a sandboxed environment. Useful for agents that need to test or run code snippets. Requires `EXECUTE` permission. |
| `DocumentRetrievalTool()` | Retrieve documents from a pre-built index. Useful for agents that need to search through documentation or knowledge bases. |

## Filesystem (21 tools)

Filesystem tools give agents full read/write access to the filesystem. They mirror common shell commands (`ls`, `mkdir`, `cp`, `mv`, `rm`, `cat`, `find`, `diff`, `zip`) and operate through a backend abstraction layer. Tools that modify the filesystem (`WRITE` operations) require the appropriate permission policy.

Use these tools for agents that need to create, read, update, or delete files — software engineering agents, data processing agents, or any agent that manages persistent state.

```python
from vidbyte.tools.filesystem import (
    ReadTextTool,     # read file as text
    ReadLinesTool,    # read file as list of lines
    ReadBinaryTool,   # read file as bytes
    WriteTextTool,    # write text to file (WRITE permission)
    AppendTool,       # append text to file (WRITE permission)
    ReplaceTextTool,  # find-and-replace in file (WRITE permission)
    ListDirTool,      # list directory contents
    MakeDirTool,      # create directory (WRITE permission)
    DeleteTool,       # delete file/directory (WRITE permission)
    CopyTool,         # copy file (WRITE permission)
    MoveTool,         # move/rename file (WRITE permission)
    RenameTool,       # rename file (WRITE permission)
    ExistsTool,       # check if path exists
    StatTool,         # file metadata (size, mtime, etc.)
    FindTool,         # recursive file find by name
    TreeTool,         # directory tree display
    DiffTool,         # compute file diffs
    ChecksumTool,     # compute file checksum
    TouchTool,        # create empty file / update mtime (WRITE permission)
    UnzipTool,        # extract zip archive (WRITE permission)
    ZipTool,          # create zip archive (WRITE permission)
)
```

Filesystem tools are organized around a backend system (`vidbyte/lib/tools/filesystem/backends/`) so the same tool works across local filesystems, remote storage, or virtual filesystems.

## MCP Bridge

The MCP (Model Context Protocol) bridge connects external MCP servers to the SDK as native tools. This lets agents use tools from any MCP-compatible server — filesystem servers, database servers, API servers — without the SDK needing to know about them at build time.

```python
from vidbyte.tools.mcp import (
    McpClient,           # JSON-RPC MCP client for communicating with MCP servers
    McpBridgedTool,      # Expose a remote MCP tool as a native SDK tool
    McpStdioTransport,   # Subprocess stdio transport for MCP servers
    McpServerConfig,     # Server command/config wrapper for defining MCP server connections
)
```

Attach MCP servers to agents via `agent.attach_mcp_server(...)` or `agent.with_mcp_server(...)`. Each MCP server's tools become available to the agent as if they were built-in.

## Security

Security tools enforce permission policies and sandbox constraints on tool execution. They ensure agents cannot perform unauthorized operations.

```python
from vidbyte.tools.security import (
    PermissionPolicy,     # Allow/deny rules for tool permissions (SAFE, READ, WRITE, EXECUTE)
    PermissionDecision,   # Result of a permission check — ALLOW, DENY, NEEDS_APPROVAL
)
```

Every tool declares a permission level. The agent evaluates each tool call against its policy. The default policy allows `SAFE` and `READ` tools, and denies `WRITE` and `EXECUTE` tools. Override with `permission_policy=PermissionPolicy.allow_all()` or a custom policy.

## Using the Tools Catalog

Tools are grouped into a `Tools` catalog for clean management. The catalog handles deduplication, incremental updates, and spec generation for model providers.

```python
from vidbyte import Tools

catalog = Tools([GlobTool(root_dir="."), GrepTool(root_dir=".")])
catalog.specs()   # model-facing tool declarations — the schema sent to the model
catalog.names()   # ("glob", "grep", ...)
catalog.all()     # tuple of BaseTool instances
```

The catalog is immutable by design. Operations like `add()` and `without()` return new `Tools` instances — the original is never mutated. This prevents accidental tool leakage between agents.

## Tool Execution Internals

These are internal subsystems that power tool execution. They are not typically used directly but are useful to understand:

- **`ToolExecutor`** — Validates permissions and executes tool calls. Checks each tool call against the agent's permission policy before execution.
- **`ToolsFormatter`** — Translates SDK tool specs to provider-specific schemas (OpenAI function calling, Anthropic tool use, Gemini function declarations, xAI tool format).
- **`IsDoneTool`** — An internal tool auto-injected into every agent so the model can signal when it is finished with tool calling and ready to return a final text response.
