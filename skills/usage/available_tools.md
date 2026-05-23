# Available Tools

Tools included out of the box in the Vidbyte SDK. Import from their category packages.

## Decorator (Create Your Own)

| Tool | Import | Description |
|------|--------|-------------|
| `@tool` | `from vidbyte import tool` | Wrap any Python function into a tool |
| `@vidbyte_tool` | `from vidbyte import vidbyte_tool` | Alias, same behavior |
| `FunctionTool` | `from vidbyte import FunctionTool` | Imperative construction from a callable |
| `Tools` | `from vidbyte import Tools` | Immutable tool catalog (Sequence) |
| `ToolRegistry` | `from vidbyte import ToolRegistry` | Mutable, thread-safe tool registry |

## Code Search

```python
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
```

| Tool | Description |
|------|-------------|
| `GlobTool(root_dir=".")` | Find files by glob pattern |
| `GrepTool(root_dir=".")` | Search file contents by regex |
| `SemanticSearchTool()` | Semantic (embedding-based) code search |

## Editing

```python
from vidbyte.tools.builtins.editing import PatchTool
```

| Tool | Description |
|------|-------------|
| `PatchTool()` | Exact string-replacement patch editing |

## Context

```python
from vidbyte.tools.builtins.context import ContextCompactionTool
```

| Tool | Description |
|------|-------------|
| `ContextCompactionTool()` | Compact conversation context to save tokens |

## Computation

```python
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
```

| Tool | Description |
|------|-------------|
| `CalculatorTool()` | Evaluate mathematical expressions |
| `CodeExecutionTool()` | Execute Python code in a sandbox |
| `DocumentRetrievalTool()` | Retrieve documents from an index |

## Filesystem (19 tools)

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
    FindTool,         # recursive file find
    TreeTool,         # directory tree display
    DiffTool,         # compute file diffs
    ChecksumTool,     # compute file checksum
    TouchTool,        # create empty file / update mtime (WRITE permission)
    UnzipTool,        # extract zip archive (WRITE permission)
    ZipTool,          # create zip archive (WRITE permission)
)
```

## MCP Bridge

```python
from vidbyte.tools.mcp import (
    McpClient,         # JSON-RPC MCP client
    McpBridgedTool,    # Expose remote MCP tool as native SDK tool
    McpStdioTransport, # Subprocess stdio transport for MCP servers
    McpServerConfig,   # Server command/config wrapper
)
```

Attach MCP servers to agents via `agent.attach_mcp_server(...)`.

## Security

```python
from vidbyte.tools.security import (
    PermissionPolicy,     # Allow/deny tool permission rules
    PermissionDecision,   # Result of permission check
)
```

## Using Tools Catalog

```python
from vidbyte import Tools

catalog = Tools([GlobTool(root_dir="."), GrepTool(root_dir=".")])
catalog.specs()   # model-facing tool declarations
catalog.names()   # ("glob", "grep", ...)
catalog.all()     # tuple of BaseTool instances
```

## Tool Execution Internals

- `ToolExecutor` validates permissions and executes tool calls.
- `ToolsFormatter` translates SDK tool specs to provider-specific schemas (OpenAI, Anthropic, Gemini, xAI).
- Internal `IsDoneTool` is auto-injected to let models signal completion.
