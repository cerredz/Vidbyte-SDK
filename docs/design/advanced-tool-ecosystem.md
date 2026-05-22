# Design Doc: Advanced Tool Ecosystem

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-20
**Last Updated:** 2026-05-20

---

## 1. Overview

Add a concrete, dependency-free tool foundation to `vidbyte-sdk` and implement the first advanced tool categories: code search, MCP bridging, permissions and sandbox abstractions, exact patch/edit tools, and context compaction tools. The implementation will preserve the previously designed `BaseTool` direction while making these tools usable in the current minimal SDK scaffold.

---

## 2. Goals & Non-Goals

### Goals

- Add the core tool contract: `BaseTool`, `ToolSpec`, `ToolCall`, `ToolResult`, `ToolRegistry`, and `ToolExecutor`.
- Add code search tools for glob, grep/regex, and semantic-style indexed search with strict path and result-size guardrails.
- Add an MCP bridge that can discover remote JSON-RPC tools and expose them as native SDK tools.
- Add permission metadata, permission policies, and a secure executor wrapper before risky tool execution.
- Add sandbox transport interfaces so executable or mutating tools can target isolated backends later without changing tool APIs.
- Add an exact-match patch tool that edits one file block only when the search block is found exactly once and returns a unified diff.
- Add context compaction tools with multiple strategies:
  - clear full conversation except system prompt plus a structured progress log
  - remove all tool calls
  - remove the last N tool calls
  - remove a percentage of tool calls
  - summarize selected history through an injected summarizer
- Keep the implementation Python 3.11 standard-library only.
- Add focused `unittest` coverage for each new tool category and security boundary.

### Non-Goals

- No live vector database, external embedding service, or model-provider integration in this PR.
- No Docker, E2B, Fly.io, WASM runtime, or remote sandbox provider dependency in this PR.
- No SSE MCP transport in the first implementation; define transport interfaces and implement stdio JSON-RPC first.
- No destructive file operations such as delete, move, or recursive write tools.
- No automatic user prompting UI for permissions; this PR provides policy hooks and deterministic allow/deny behavior.
- No implementation of full agent loops or prompt strategies beyond tool contracts needed by future agents.

---

## 3. Background & Context

- The current repo is a minimal Python SDK scaffold. `VidbyteSDK` exposes `harnesses`, `tools`, and `providers`, but `ToolsClient` is currently empty.
- Existing local design docs already point toward a `BaseTool` / `ToolRegistry` / `ToolExecutor` architecture, but the source files do not exist yet.
- `pyproject.toml` declares Python `>=3.11` and has no runtime dependencies. This design preserves that constraint.
- `skills/vidbyte-sdk/SKILL.md` currently says not to add concrete tool implementations until the structure is approved. This design is the approval artifact for the advanced tool layer.
- Every created or modified Python file should follow the existing design direction for Context Protocol Headers.

---

## 4. Requirements

### Functional Requirements

1. The SDK must expose `sdk.tools.registry` and `sdk.tools.executor`.
2. `BaseTool.spec()` must return a `ToolSpec`.
3. `BaseTool.execute(call)` must be async and return `ToolResult`.
4. `ToolExecutor` must validate tool availability, required parameters, and permission policy before executing.
5. Code search tools must resolve all paths under a configured root and reject traversal outside that root.
6. Code search tools must cap output by `max_results`, `max_chars`, and per-match context lines.
7. `GrepTool` must support literal and regex matching.
8. `GlobTool` must return matching relative paths without file contents.
9. `SemanticSearchTool` must search an in-memory chunk index using an injectable embedding provider, with a deterministic token-overlap fallback when no provider is supplied.
10. MCP stdio clients must initialize, list tools, call tools, and convert remote tool schemas into native `ToolSpec` objects.
11. MCP bridge failures must return `ToolResult` errors rather than crashing the caller where possible.
12. Tools must declare a permission level: `SAFE`, `READ`, `WRITE`, or `EXECUTE`.
13. Permission policies must support deny-by-default for `WRITE` and `EXECUTE`.
14. Patch tool must only write when `search_block` appears exactly once.
15. Patch tool must return a unified diff after applying a change.
16. Context compaction tools must operate on a structured conversation state protocol rather than a specific agent implementation.
17. Context compaction must preserve system messages unless explicitly configured otherwise.
18. Context compaction must support structured progress logs containing completed tasks, touched files, decisions, errors, and next steps.

### Non-Functional Requirements

- Security: no tool may read or write outside its configured root.
- Security: mutating tools must require `WRITE`; executable/sandbox-backed tools must require `EXECUTE`.
- Reliability: all tool errors return structured `ToolResult` failures with concise messages.
- Performance: search tools must short-circuit once limits are reached.
- Maintainability: package exports must use explicit `__all__`.
- Compatibility: Python `>=3.11`, no runtime dependencies.
- Testability: MCP and sandbox behavior must be testable with fake transports.
- Context safety: large file contents, large tool logs, and full histories must never be returned by default.

---

## 5. High-Level Design

The feature adds a real `vidbyte.tools` foundation and then layers advanced built-ins on top. The registry owns tool discovery, the executor owns validation and policy enforcement, and each tool owns only its own domain logic.

```text
VidbyteSDK
`-- ToolsClient
    |-- ToolRegistry
    |-- SecureToolExecutor
    |
    |-- builtins/code_search
    |   |-- GlobTool
    |   |-- GrepTool
    |   `-- SemanticSearchTool
    |
    |-- builtins/editing
    |   `-- PatchTool
    |
    |-- builtins/context
    |   `-- ContextCompactionTool
    |
    |-- mcp
    |   |-- McpStdioClient
    |   `-- McpBridgedTool
    |
    `-- security
        |-- PermissionPolicy
        `-- SandboxTransport
```

Code search tools share root-scoped path resolution and truncation helpers. MCP tools use a bridge pattern: one client discovers remote tools, then creates native `McpBridgedTool` wrappers for registration. Permission checks live in the executor so security policy is consistent across native and bridged tools. Compaction tools treat context as a list-like state object and apply named strategies to produce smaller history while preserving critical invariants.

---

## 6. Detailed Design

### 6.1 Tool Core Types

**File(s):** `vidbyte/lib/dataclasses/tools.py`, `vidbyte/tools/types.py`, `vidbyte/tools/base.py`
**Type:** New file

#### What it does

Defines the public contract all native and bridged tools use. Dataclass definitions live under `vidbyte/lib/dataclasses/`, while `vidbyte/tools/types.py` remains a compatibility re-export surface.

#### Interface / API

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"

class ToolPermission(str, Enum):
    SAFE = "safe"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"

@dataclass(frozen=True, slots=True)
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True

@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ToolCall:
    tool_name: str
    arguments: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    status: ToolStatus
    output: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

class BaseTool:
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def validate_call(self, call: ToolCall) -> str | None: ...
```

#### Logic / Algorithm

1. `BaseTool.name` is derived from `spec().name`.
2. `validate_call()` checks required parameter names from `ToolSpec`.
3. `ToolSpec.to_prompt_str()` renders compact model-facing documentation.
4. `ToolResult.error(...)` and `ToolResult.success(...)` class helpers reduce repeated result construction.

#### Edge Cases & Error Handling

- Empty tool names raise `ValueError`.
- Missing required parameters return validation errors before execution.
- Results should be printable and safe for prompt insertion.

---

### 6.2 Registry And Executor

**File(s):** `vidbyte/tools/registry.py`, `vidbyte/tools/executor.py`, `vidbyte/tools/client.py`, `vidbyte/tools/__init__.py`
**Type:** New file, Modified

#### What it does

Adds tool registration, lookup, prompt rendering, and execution.

#### Interface / API

```python
class ToolRegistry:
    def register(self, tool: BaseTool) -> None: ...
    def get(self, name: str) -> BaseTool: ...
    def all(self) -> tuple[BaseTool, ...]: ...
    def specs(self) -> tuple[ToolSpec, ...]: ...
    def specs_as_prompt_str(self) -> str: ...

class ToolExecutor:
    def __init__(self, registry: ToolRegistry, permission_policy: PermissionPolicy | None = None) -> None: ...
    async def execute_call(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

1. `ToolRegistry.register()` rejects duplicate names.
2. `ToolExecutor.execute_call()` resolves the tool.
3. The executor asks the permission policy whether the tool's permission is allowed.
4. The executor validates arguments using `tool.validate_call(call)`.
5. The executor awaits `tool.execute(call)` and catches exceptions into error results.

#### Edge Cases & Error Handling

- Unknown tool names return an error result.
- Permission denial returns an error result with `permission_denied` metadata.
- Tool exceptions are caught and summarized.

---

### 6.3 Code Search Base

**File(s):** `vidbyte/tools/builtins/code_search/base.py`
**Type:** New file

#### What it does

Provides shared safe path resolution, ignored-directory handling, text-file detection, line context, and truncation.

#### Interface / API

```python
class BaseCodeSearchTool(BaseTool):
    def __init__(
        self,
        root_dir: str | Path,
        *,
        ignore_patterns: Sequence[str] | None = None,
        max_file_bytes: int = 1_000_000,
    ) -> None: ...

    def resolve_under_root(self, path: str = ".") -> Path: ...
    def iter_files(self, subdir: str = ".", extensions: Sequence[str] = ()) -> Iterator[Path]: ...
    def read_text_lines(self, path: Path) -> list[str]: ...
```

#### Logic / Algorithm

1. Resolve `root_dir` at construction.
2. Resolve every requested path against root before use.
3. Reject paths outside root using `Path.resolve()` and `relative_to()`.
4. Skip `.git`, `node_modules`, `__pycache__`, virtualenv folders, binary-looking files, and oversized files.
5. Return relative paths in outputs.

#### Edge Cases & Error Handling

- Broken symlinks are skipped.
- Symlinks that resolve outside root are rejected.
- Decode failures are skipped and counted in metadata.

---

### 6.4 Glob Tool

**File(s):** `vidbyte/tools/builtins/code_search/glob.py`
**Type:** New file

#### What it does

Finds files by glob pattern without reading contents.

#### Interface / API

```python
class GlobTool(BaseCodeSearchTool):
    # parameters: pattern, subdir, max_results
```

#### Logic / Algorithm

1. Validate `pattern`, `subdir`, and `max_results`.
2. Resolve `subdir` under root.
3. Use `Path.glob()` or `Path.rglob()` depending on the pattern.
4. Filter ignored directories and unsafe resolved paths.
5. Return newline-separated relative paths up to `max_results`.

#### Edge Cases & Error Handling

- Empty matches return a successful result with `No files matched`.
- Truncated results include a clear truncation note and total returned count.

---

### 6.5 Grep Tool

**File(s):** `vidbyte/tools/builtins/code_search/grep.py`
**Type:** New file

#### What it does

Searches text files for literal or regex matches and returns line-numbered snippets.

#### Interface / API

```python
class GrepTool(BaseCodeSearchTool):
    # parameters: pattern, subdir, regex, extensions, context_lines, max_results
```

#### Logic / Algorithm

1. Compile regex when `regex=True`; otherwise escape the literal pattern.
2. Walk files from `iter_files()`.
3. Read files line-by-line.
4. For each match, collect line number plus bounded surrounding context.
5. Stop at `max_results`.
6. Return grouped snippets in `path:line` format.

#### Edge Cases & Error Handling

- Invalid regex returns an error result.
- Binary and oversized files are skipped.
- `context_lines` is capped, for example at 5.

---

### 6.6 Semantic Search Tool

**File(s):** `vidbyte/tools/builtins/code_search/semantic.py`
**Type:** New file

#### What it does

Indexes code chunks and returns the most relevant chunks for a natural-language query.

#### Interface / API

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...

class SemanticSearchTool(BaseCodeSearchTool):
    def __init__(
        self,
        root_dir: str | Path,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        chunk_lines: int = 80,
        overlap_lines: int = 10,
    ) -> None: ...

    def rebuild_index(self) -> None: ...
```

#### Logic / Algorithm

1. Chunk text files by line ranges.
2. If an embedding provider exists, embed chunks and queries and rank by cosine similarity.
3. If no provider exists, use deterministic token-overlap ranking as a dependency-free fallback.
4. Return top `max_results` chunks with file path, line range, score, and truncated text.
5. Rebuild index lazily on first call or explicitly through `rebuild_index()`.

#### Edge Cases & Error Handling

- Empty index returns a clear message.
- Embedding dimension mismatches return an error result.
- Chunk text is capped by `max_chars_per_result`.

---

### 6.7 MCP Client And Bridge

**File(s):** `vidbyte/tools/mcp/types.py`, `vidbyte/tools/mcp/transport.py`, `vidbyte/tools/mcp/client.py`, `vidbyte/tools/mcp/bridge.py`, `vidbyte/tools/mcp/__init__.py`
**Type:** New file

#### What it does

Implements a minimal JSON-RPC MCP client over stdio and wraps remote MCP tools as native `BaseTool` instances.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class McpToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, Any]

class McpTransport(Protocol):
    async def request(self, method: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]: ...

class McpStdioTransport:
    async def start(self) -> None: ...
    async def request(self, method: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]: ...
    async def close(self) -> None: ...

class McpClient:
    async def initialize(self) -> None: ...
    async def list_tools(self) -> tuple[McpToolDefinition, ...]: ...
    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> ToolResult: ...

class McpBridgedTool(BaseTool):
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

#### Logic / Algorithm

1. Start the configured MCP server process with stdio pipes.
2. Send `initialize`.
3. Send `tools/list`.
4. Convert each JSON Schema property into `ToolParameter`.
5. Register each `McpBridgedTool` in `ToolRegistry`.
6. On execution, send `tools/call` with remote name and arguments.
7. Convert MCP content parts into one bounded text output.

#### Edge Cases & Error Handling

- Invalid JSON-RPC responses raise `McpProtocolError`.
- Remote tool errors convert to `ToolStatus.ERROR`.
- Output is truncated by a bridge-level `max_output_chars`.
- Server process cleanup runs on close.

---

### 6.8 Permissions And Sandbox Interfaces

**File(s):** `vidbyte/tools/security/permissions.py`, `vidbyte/tools/security/sandbox.py`, `vidbyte/tools/security/__init__.py`
**Type:** New file

#### What it does

Separates authorization and execution isolation from individual tool logic.

#### Interface / API

```python
class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"

@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    allowed: frozenset[ToolPermission] = frozenset({ToolPermission.SAFE, ToolPermission.READ})

    def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision: ...

class SandboxTransport(Protocol):
    async def run(self, request: SandboxRequest) -> SandboxResult: ...
```

#### Logic / Algorithm

1. Tool specs declare permissions.
2. Executor consults policy before validation and execution.
3. Default policy allows `SAFE` and `READ`, denies `WRITE` and `EXECUTE`.
4. Tests can inject an allow-all policy.
5. Sandbox interfaces define how future code execution or patching tools can route through isolated environments.

#### Edge Cases & Error Handling

- Permission denial does not call `tool.execute()`.
- Sandbox timeout and non-zero exit codes are represented in `SandboxResult`.
- No real host shell execution is introduced by this PR.

---

### 6.9 Patch Tool

**File(s):** `vidbyte/tools/builtins/editing/patch.py`, `vidbyte/tools/builtins/editing/__init__.py`
**Type:** New file

#### What it does

Applies exact search/replace patches inside root-scoped text files.

#### Interface / API

```python
class PatchTool(BaseTool):
    def __init__(self, root_dir: str | Path, *, encoding: str = "utf-8") -> None: ...
    # parameters: file_path, search_block, replace_block
```

#### Logic / Algorithm

1. Resolve `file_path` under root.
2. Read file text.
3. Count occurrences of `search_block`.
4. If count is 0, return an error result.
5. If count is greater than 1, return an ambiguous patch error.
6. Replace the block once.
7. Write the updated file.
8. Generate a unified diff with `difflib.unified_diff`.
9. Return the diff and metadata including changed line counts.

#### Edge Cases & Error Handling

- Empty `search_block` is rejected.
- Binary/decode failures return errors.
- Files outside root are rejected.
- Tool permission is `WRITE`.

---

### 6.10 Context Compaction Types

**File(s):** `vidbyte/tools/builtins/context/types.py`
**Type:** New file

#### What it does

Defines state and message protocols for compaction without depending on a specific agent loop.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ContextMessage:
    role: str
    content: str
    kind: str = "message"  # message, tool_call, tool_result, summary
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ProgressLog:
    completed_tasks: tuple[str, ...] = ()
    touched_files: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()

class ContextState(Protocol):
    def messages(self) -> Sequence[ContextMessage]: ...
    def replace_messages(self, messages: Sequence[ContextMessage]) -> None: ...
```

#### Logic / Algorithm

1. Tools accept a `ContextState` instance at construction.
2. Compaction strategies read messages and write back a new sequence.
3. Progress logs are encoded as structured Markdown or JSON-like text in a summary message.

#### Edge Cases & Error Handling

- Unknown message kinds are treated as normal messages.
- Empty histories remain valid.
- System messages are preserved by default.

---

### 6.11 Context Compaction Strategies

**File(s):** `vidbyte/tools/builtins/context/compaction.py`, `vidbyte/tools/builtins/context/__init__.py`
**Type:** New file

#### What it does

Implements multiple compaction modes as explicit strategies.

#### Interface / API

```python
class CompactionMode(str, Enum):
    CLEAR_EXCEPT_SYSTEM_AND_LOG = "clear_except_system_and_log"
    REMOVE_ALL_TOOL_CALLS = "remove_all_tool_calls"
    REMOVE_LAST_N_TOOL_CALLS = "remove_last_n_tool_calls"
    REMOVE_TOOL_CALL_PERCENTAGE = "remove_tool_call_percentage"
    SUMMARIZE_RANGE = "summarize_range"

class Summarizer(Protocol):
    async def summarize(self, messages: Sequence[ContextMessage]) -> str: ...

class ContextCompactionTool(BaseTool):
    def __init__(self, state: ContextState, *, summarizer: Summarizer | None = None) -> None: ...
```

#### Logic / Algorithm

1. `CLEAR_EXCEPT_SYSTEM_AND_LOG`:
   - Keep messages with `role == "system"`.
   - Build or accept a `ProgressLog`.
   - Replace all non-system history with one summary message containing structured progress.
2. `REMOVE_ALL_TOOL_CALLS`:
   - Remove messages where `kind` is `tool_call` or `tool_result`.
   - Keep user, assistant, system, and summary messages.
3. `REMOVE_LAST_N_TOOL_CALLS`:
   - Find tool-call/tool-result messages from the end of history.
   - Remove the last `n` tool messages.
4. `REMOVE_TOOL_CALL_PERCENTAGE`:
   - Compute `ceil(tool_message_count * percentage)`.
   - Remove that many oldest or newest tool messages based on an `order` argument.
5. `SUMMARIZE_RANGE`:
   - Keep system messages and the last `keep_last` messages.
   - Send the selected middle range to the injected summarizer.
   - Replace the range with one summary message.

#### Edge Cases & Error Handling

- Percentages must be between 0 and 1.
- `n <= 0` is a no-op success.
- `SUMMARIZE_RANGE` without a summarizer returns an error result.
- Compaction output includes before/after message counts and removed tool-call counts.

---

### 6.12 Builtin Package Exports

**File(s):** `vidbyte/tools/builtins/__init__.py`, `vidbyte/tools/builtins/code_search/__init__.py`
**Type:** New file

#### What it does

Exports built-in tool classes for simple imports and client registration.

#### Interface / API

```python
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.context import ContextCompactionTool
```

#### Logic / Algorithm

1. Use explicit `__all__`.
2. Avoid auto-registering filesystem-mutating tools by default.

#### Edge Cases & Error Handling

- Imports should not touch the filesystem or start subprocesses.

---

### 6.13 SDK Root And Documentation

**File(s):** `vidbyte/client.py`, `vidbyte/__init__.py`, `README.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified

#### What it does

Exposes the new tool architecture and documents usage patterns.

#### Interface / API

```python
from vidbyte import VidbyteSDK
from vidbyte.tools.builtins.code_search import GrepTool

sdk = VidbyteSDK()
sdk.tools.registry.register(GrepTool(root_dir="."))
```

#### Logic / Algorithm

1. `ToolsClient` initializes a registry and secure executor.
2. README documents registering code search and patch tools.
3. SDK skill notes that advanced tools are now allowed under the approved categories.

#### Edge Cases & Error Handling

- Existing `VidbyteSDK().tools` construction remains compatible.

---

## 7. Data Model Changes

### 7.1 Tool Dataclasses And Enums

**Change type:** New

```python
ToolStatus
ToolPermission
ToolParameter
ToolSpec
ToolCall
ToolResult
```

**Migration strategy:** N/A - in-memory SDK types only.

### 7.2 MCP Types

**Change type:** New

```python
McpToolDefinition
McpRequest
McpResponse
```

**Migration strategy:** N/A - protocol wrapper types only.

### 7.3 Context Types

**Change type:** New

```python
ContextMessage
ProgressLog
CompactionMode
```

**Migration strategy:** N/A - in-memory context abstractions only.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints.

Python SDK public API additions:

```python
from vidbyte.tools import BaseTool, ToolRegistry, ToolExecutor, ToolSpec, ToolCall, ToolResult
from vidbyte.tools.security import PermissionPolicy, ToolPermission
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.context import ContextCompactionTool, CompactionMode
from vidbyte.tools.mcp import McpClient, McpStdioTransport, McpBridgedTool
from vidbyte.lib.tools import ToolsFormatter
```

Modified SDK client:

```python
sdk = VidbyteSDK()
sdk.tools.registry
sdk.tools.executor
```

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/advanced-tool-ecosystem.md` | Design doc for this feature |
| MODIFY | `README.md` | Document tool registration and advanced built-ins |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update SDK structure guidance for approved tool categories |
| MODIFY | `vidbyte/__init__.py` | Export public tool types where appropriate |
| MODIFY | `vidbyte/client.py` | Preserve root SDK construction with richer `ToolsClient` |
| MODIFY | `vidbyte/tools/__init__.py` | Export core tool contracts |
| MODIFY | `vidbyte/tools/client.py` | Add registry, executor, and registration helpers |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export tool/MCP/security errors |
| CREATE | `vidbyte/lib/errors/base.py` | SDK error hierarchy for tools and transports |
| CREATE | `vidbyte/lib/dataclasses/__init__.py` | Central dataclass exports |
| CREATE | `vidbyte/lib/dataclasses/tools.py` | Tool dataclasses and permission/status enums |
| CREATE | `vidbyte/lib/dataclasses/context.py` | Context message and progress-log dataclasses |
| CREATE | `vidbyte/lib/dataclasses/mcp.py` | MCP protocol dataclasses |
| CREATE | `vidbyte/lib/dataclasses/security.py` | Permission policy dataclass |
| CREATE | `vidbyte/lib/dataclasses/sandbox.py` | Sandbox request and result dataclasses |
| CREATE | `vidbyte/lib/dataclasses/code_search.py` | Internal code-search chunk dataclass |
| CREATE | `vidbyte/lib/tools/__init__.py` | Shared tool helper exports |
| CREATE | `vidbyte/lib/tools/formatter.py` | Provider-specific tool schema formatter and parser |
| CREATE | `vidbyte/tools/types.py` | Tool type compatibility re-exports |
| CREATE | `vidbyte/tools/base.py` | Abstract `BaseTool` contract |
| CREATE | `vidbyte/tools/registry.py` | Tool registry |
| CREATE | `vidbyte/tools/executor.py` | Tool execution pipeline |
| CREATE | `vidbyte/tools/builtins/__init__.py` | Built-in tool exports |
| CREATE | `vidbyte/tools/builtins/code_search/__init__.py` | Code search exports |
| CREATE | `vidbyte/tools/builtins/code_search/base.py` | Shared path safety and search helpers |
| CREATE | `vidbyte/tools/builtins/code_search/glob.py` | Glob search tool |
| CREATE | `vidbyte/tools/builtins/code_search/grep.py` | Grep/regex search tool |
| CREATE | `vidbyte/tools/builtins/code_search/semantic.py` | Indexed semantic-style search tool |
| CREATE | `vidbyte/tools/builtins/editing/__init__.py` | Editing tool exports |
| CREATE | `vidbyte/tools/builtins/editing/patch.py` | Exact-match patch tool |
| CREATE | `vidbyte/tools/builtins/context/__init__.py` | Context tool exports |
| CREATE | `vidbyte/tools/builtins/context/types.py` | Context type compatibility re-exports |
| CREATE | `vidbyte/tools/builtins/context/compaction.py` | Context compaction tool and strategies |
| CREATE | `vidbyte/tools/mcp/__init__.py` | MCP exports |
| CREATE | `vidbyte/tools/mcp/types.py` | MCP type compatibility re-exports |
| CREATE | `vidbyte/tools/mcp/transport.py` | MCP transport protocol and stdio transport |
| CREATE | `vidbyte/tools/mcp/client.py` | MCP JSON-RPC client |
| CREATE | `vidbyte/tools/mcp/bridge.py` | Native wrapper for remote MCP tools |
| CREATE | `vidbyte/tools/security/__init__.py` | Security exports |
| CREATE | `vidbyte/tools/security/permissions.py` | Permission policy and decisions |
| CREATE | `vidbyte/tools/security/sandbox.py` | Sandbox transport protocol types |
| CREATE | `tests/test_tool_core.py` | Tool types, registry, and executor tests |
| CREATE | `tests/test_code_search_tools.py` | Glob, grep, semantic search tests |
| CREATE | `tests/test_patch_tool.py` | Exact patch and diff tests |
| CREATE | `tests/test_security_executor.py` | Permission policy tests |
| CREATE | `tests/test_mcp_bridge.py` | Fake MCP transport and bridged tool tests |
| CREATE | `tests/test_context_compaction_tools.py` | Compaction strategy tests |

Summary: 40 files created, 7 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_tool_core.py` -> verifies `ToolSpec` XML rendering, provider tool formatting/parsing, required parameter validation, duplicate registry rejection, unknown tool errors, and successful async execution.
- `tests/test_code_search_tools.py` -> verifies path traversal rejection, ignored directories, `max_results` truncation, invalid regex handling, glob matching, grep snippets, and semantic fallback ranking.
- `tests/test_patch_tool.py` -> verifies exact replacement, no-match errors, multi-match ambiguity errors, traversal rejection, empty search rejection, and unified diff output.
- `tests/test_security_executor.py` -> verifies default policy allows `SAFE`/`READ`, denies `WRITE`/`EXECUTE`, does not call denied tools, and allow-all policy enables patch tests.
- `tests/test_mcp_bridge.py` -> uses a fake transport to verify `initialize`, `tools/list`, schema-to-`ToolSpec` mapping, `tools/call`, remote error conversion, and output truncation.
- `tests/test_context_compaction_tools.py` -> verifies each compaction mode: clear except system/log, remove all tool calls, remove last N tool calls, remove percentage of tool calls, summarize range, no-op behavior, and invalid parameters.

### Integration Tests

- Use temporary directories to register `GlobTool`, `GrepTool`, `SemanticSearchTool`, and `PatchTool` in a real `ToolRegistry`, then run them through `ToolExecutor`.
- Use fake MCP transport through `McpClient` and register generated `McpBridgedTool` instances.
- No live MCP servers, remote sandboxes, provider APIs, or model calls are required.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte`.
2. Run `python -m unittest discover -s tests`.
3. Register `GrepTool(root_dir=".")`, search for `VidbyteSDK`, and confirm bounded path/line output.
4. Register `PatchTool(root_dir=tempdir)` with an allow-write policy, patch a temp file, and confirm the returned unified diff.
5. Create an in-memory context state with system, assistant, user, and tool messages; run each compaction mode and confirm system messages remain.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | Dataclasses, pathlib, regex, difflib, asyncio, subprocess, unittest | Lower ergonomics than dedicated MCP/vector packages |
| MCP JSON-RPC protocol shape | stdio `initialize`, `tools/list`, `tools/call` | Dynamic tool discovery and execution | MCP details may evolve; keep transport isolated |

No package dependencies are added.

---

## 12. Rollout & Deployment

- This is a package-only SDK change; no deployed service is updated.
- The feature is additive and should not break `VidbyteSDK().tools`.
- Mutating tools are not registered by default with write permission enabled.
- Rollout sequence:
  1. Commit this design doc first in the feature branch.
  2. Implement core tool types, registry, executor, and security policy.
  3. Implement code search and patch tools.
  4. Implement context compaction tools.
  5. Implement MCP transport/client/bridge.
  6. Add tests and documentation.
- Rollback is reverting the feature branch merge commit.

---

## 13. Open Questions

- [ ] Should `ToolsClient` auto-register safe read-only tools like glob and grep when a root is provided, or require explicit registration for every built-in?
- [ ] Should patching be allowed through the normal local filesystem when `WRITE` is granted, or should all writes eventually route through a sandbox transport?
- [ ] Should `SemanticSearchTool` expose the token-overlap fallback as a separate `KeywordSearchTool` to avoid overstating semantic capability without embeddings?
- [ ] Should MCP stdio server configuration live in code only for now, or should the SDK support a config-file loader in this first PR?
- [ ] What exact structured progress-log fields should compaction preserve beyond completed tasks, touched files, decisions, errors, and next steps?

---

## 14. Alternatives Considered

### Alternative 1: Implement only the five advanced categories without core tool contracts

- What: Add standalone classes for grep, MCP, patching, security, and compaction.
- Why rejected: The current repo lacks `BaseTool`, registry, and executor source files. Advanced tools need a shared contract to be useful and testable.

### Alternative 2: Add third-party MCP and embedding dependencies

- What: Depend on a packaged MCP client and a vector/embedding library.
- Why rejected: The SDK is currently dependency-free. Protocol interfaces plus stdio/fallback implementations preserve that constraint and leave room for optional adapters later.

### Alternative 3: Put permission checks inside every tool

- What: Have `PatchTool`, MCP tools, code execution, and future tools each enforce permissions themselves.
- Why rejected: Security policy belongs in the executor so all tools, including dynamically bridged MCP tools, are checked consistently.

### Alternative 4: Make compaction mutate raw provider messages directly

- What: Couple compaction to one provider's chat message format.
- Why rejected: The SDK does not have a final agent state shape yet. A small `ContextState` protocol lets current and future harnesses adapt without locking into OpenAI, Anthropic, or internal message schemas.

### Alternative 5: Use fuzzy patching

- What: Let `PatchTool` apply approximate matches when indentation or whitespace differs.
- Why rejected: Fuzzy edits are dangerous in agent workflows. Exact single-match replacement is safer, auditable, and easy to validate with a unified diff.
