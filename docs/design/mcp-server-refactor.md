# Design Doc: MCP Server Refactor + Skills

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

This change refactors the `vidbyte/mcp_server/` package for clarity and extensibility, then adds MCP-server-specific developer skill files. The refactor converts `schema.py` from a bag of free functions into a `McpSchema` class, splits `server.py` into a proper package where `run()` delegates to a `_read_input()` / `_dispatch()` pair, and moves each JSON-RPC method handler into its own file under `vidbyte/mcp_server/server/handlers/`. After the code is clean, a new `skills/mcp-server/` directory documents how to add tools, add handlers, and understand the request/response flow.

---

## 2. Goals & Non-Goals

### Goals
- Convert `schema.py` module-level functions into static methods on a `McpSchema` class.
- Break `McpStudioServer.run()` into `_read_input()` (stdin reading + JSON parsing) and `_dispatch()` (method routing switch).
- Move each JSON-RPC method handler (`initialize`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`) into its own file under `vidbyte/mcp_server/server/handlers/`.
- Convert `vidbyte/mcp_server/server.py` into a package (`server/`) so handlers can live as siblings.
- Update all internal import sites that reference the old free functions.
- Add `skills/mcp-server/` with practical, actionable skill files covering the MCP server's subatomic extension points.
- Preserve all existing public import paths (`vidbyte.mcp_server.server.McpStudioServer`, etc.).
- Preserve all existing runtime behavior and test coverage.

### Non-Goals
- Adding new MCP methods or studio tools (that is a separate feature).
- Changing the JSON-RPC wire format or protocol version.
- Modifying `vidbyte/mcp_server/handlers.py` (the `StudioToolRegistry` and studio tool classes) beyond updating import references.
- Publishing the SDK or changing `pyproject.toml`.
- Writing new tests beyond verifying the refactored code still passes the existing suite.

---

## 3. Background & Context

PR #47 (now merged) shipped a working `McpStudioServer`. The implementation is correct but grew organically: `schema.py` is a flat module of 8 unrelated functions, and `server.py` has a single `run()` method that handles stdin setup, JSON parsing, type validation, dispatch, and error handling all inline. As the MCP feature set grows, this layout will make it hard to:

- Add a new JSON-RPC method without editing the monolithic `run()`.
- Understand at a glance what methods the server supports.
- Add new schema helpers without polluting the module namespace.

The refactor puts each handler in the obvious place (its own file) and makes `McpSchema` a proper object so callers always have a single import target.

The skills gap is also real: nothing in `skills/` currently explains how to add a tool to the MCP server, how the request/response lifecycle works, or where to put a new handler. These skill files will unblock future contributors.

---

## 4. Requirements

### Functional Requirements
1. `from vidbyte.mcp_server.server import McpStudioServer` must still work after the refactor.
2. `from vidbyte.mcp_server import McpStudioServer` must still work.
3. `McpSchema` class must expose every function currently in `schema.py` as a static method with identical signatures and behavior.
4. `McpStudioServer.run()` must call `self._read_input(reader)` and `self._dispatch(request)` explicitly rather than inlining that logic.
5. `_read_input()` must handle: EOF (return sentinel indicating break), empty lines (return sentinel indicating continue), JSON parse errors (write error response + return skip sentinel), and invalid request type (write error response + return skip sentinel).
6. `_dispatch()` must use a dict-based handler map (switch pattern) over handler instances, one per JSON-RPC method.
7. Each of the five JSON-RPC handlers must live in a dedicated file under `vidbyte/mcp_server/server/handlers/`.
8. All existing tests must pass without modification.
9. Skills must exist for: adding a new MCP tool, adding a new JSON-RPC handler, and understanding the tool request/response flow.

### Non-Functional Requirements
- No new runtime dependencies beyond what already exists (asyncio, json, pydantic, existing vidbyte subpackages).
- Import chains must not create circular dependencies.
- Each handler file must be self-contained enough to understand in isolation.
- Skill files must be actionable (copy-pasteable templates, not just prose).

---

## 5. High-Level Design

The refactor has two independent axes: schema and server.

**Schema axis.** `schema.py` keeps the same filename but its 8 module-level functions move inside a `McpSchema` class as `@staticmethod` methods. All internal callers (`handlers.py`, the new `server/` package) are updated to use `McpSchema.<method>(...)`. No behavior changes.

**Server axis.** `server.py` is deleted and replaced by a `server/` package. The package exposes `McpStudioServer` through `server/__init__.py`, which just re-exports it from `server/core.py`. `core.py` contains the refactored class: `run()` is now a thin loop that calls `_read_input()` then `_dispatch()`. The `_dispatch()` method holds a `dict[str, BaseHandler]` map built at `__init__` time; each value is an instance of a handler class imported from `server/handlers/<name>.py`.

```
McpStudioServer.run()
  └─► _connect_stdin()       # asyncio StreamReader setup
  └─► loop:
        _read_input(reader)  # decode + parse + validate → dict | _EOF | _SKIP
        _dispatch(request)   # dict lookup → handler.handle(request_id, params)
          ├─► InitializeHandler.handle()
          ├─► ToolsListHandler.handle()
          ├─► ToolsCallHandler.handle()
          ├─► PromptsListHandler.handle()
          └─► PromptsGetHandler.handle()
        _write_response(response)
```

**Skills axis.** A new `skills/mcp-server/` directory. The `SKILL.md` gives an architectural map; `add-tool.md`, `add-handler.md`, and `tool-request-response.md` are step-by-step how-tos.

---

## 6. Detailed Design

### 6.1 McpSchema class

**File:** `vidbyte/mcp_server/schema.py`
**Type:** Modified

#### What it does
Centralizes all MCP JSON-RPC serialization helpers as static methods on a single class, eliminating the flat module namespace.

#### Interface / API
```python
class McpSchema:
    @staticmethod
    def tool_spec_to_mcp_tool(spec: ToolSpec) -> dict[str, Any]: ...

    @staticmethod
    def tool_result_to_mcp_content(result: ToolResult) -> list[dict[str, Any]]: ...

    @staticmethod
    def mcp_result_response(request_id: int | str | None, result: dict[str, Any]) -> dict[str, Any]: ...

    @staticmethod
    def mcp_error_response(request_id: int | str | None, code: int, message: str) -> dict[str, Any]: ...

    @staticmethod
    def mcp_tool_error_result(request_id: int | str | None, error_text: str) -> dict[str, Any]: ...

    @staticmethod
    def mcp_tool_success_result(request_id: int | str | None, content: list[dict[str, Any]]) -> dict[str, Any]: ...

    @staticmethod
    def parameters_from_input_schema(parameters: tuple[ToolParameter, ...]) -> dict[str, dict[str, Any]]: ...
```

#### Logic / Algorithm
Each method is a direct lift of the existing function body with no changes to logic. The only difference is the `@staticmethod` decorator and the containing class.

#### Edge Cases & Error Handling
- All edge cases are identical to the existing functions.
- No instance state is needed; `@staticmethod` is correct.

---

### 6.2 server/ package

**File:** `vidbyte/mcp_server/server/` (new directory replacing `server.py`)
**Type:** New (server.py deleted)

#### What it does
Replaces the single `server.py` module with a package that separates concerns: `__init__.py` re-exports the public class, `core.py` owns the I/O loop, and `handlers/` owns individual method dispatchers.

---

### 6.3 McpStudioServer (core.py)

**File:** `vidbyte/mcp_server/server/core.py`
**Type:** New

#### What it does
Houses `McpStudioServer`. Keeps `__init__`, `run()`, `close()`, and `_write_response()` essentially unchanged. Adds `_connect_stdin()`, `_read_input()`, and `_dispatch()`. Removes the five `_handle_*` methods (moved to handler files).

#### Interface / API
```python
class _EOF:
    """Sentinel: stdin closed, break the loop."""

class _SKIP:
    """Sentinel: empty line or parse error already handled, continue the loop."""

class McpStudioServer:
    def __init__(self, *, name, version, agents, tools, strategy_names, pipeline_names, prompt_content) -> None: ...
    async def run(self) -> None: ...
    async def close(self) -> None: ...
    def _write_response(self, response: dict[str, Any]) -> None: ...
    async def _connect_stdin(self) -> asyncio.StreamReader: ...
    async def _read_input(self, reader: asyncio.StreamReader) -> dict[str, Any] | _EOF | _SKIP: ...
    async def _dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]: ...
```

#### Logic / Algorithm — `run()`
1. Call `self._connect_stdin()` to get a `StreamReader`.
2. Loop while `not self._shutdown`:
   a. `result = await self._read_input(reader)`.
   b. If `result is _EOF`: `break`.
   c. If `result is _SKIP`: `continue`.
   d. `try: response = await self._dispatch(result)` / `except Exception: response = McpSchema.mcp_error_response(result.get("id"), JSONRPC_INTERNAL_ERROR, ...)`.
   e. `self._write_response(response)`.

#### Logic / Algorithm — `_connect_stdin()`
1. `loop = asyncio.get_running_loop()`.
2. Create `asyncio.StreamReader` + `asyncio.StreamReaderProtocol`.
3. `await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)`.
4. Return the reader. On exception, raise so `run()` can exit.

#### Logic / Algorithm — `_read_input()`
1. `line = await reader.readline()`.
2. If `not line`: return `_EOF()`.
3. `line_str = line.decode("utf-8").strip()`.
4. If `not line_str`: return `_SKIP()`.
5. Try `json.loads(line_str)`; on `JSONDecodeError`: write parse error response, return `_SKIP()`.
6. If not `Mapping`: write invalid-request error response, return `_SKIP()`.
7. Return the parsed dict.

#### Logic / Algorithm — `_dispatch()`
1. Extract `method`, `request_id`, `params` from request.
2. If `method` is not `str`: return `McpSchema.mcp_error_response(...)` with `JSONRPC_INVALID_REQUEST`.
3. Look up `self._handler_map.get(method)`.
4. If `None`: return `McpSchema.mcp_error_response(...)` with `JSONRPC_METHOD_NOT_FOUND`.
5. Return `await handler.handle(request_id, params)`.

`_handler_map` is built in `__init__` as:
```python
self._handler_map: dict[str, _BaseHandler] = {
    "initialize":   InitializeHandler(self._name, self._version, self._set_initialized),
    "tools/list":   ToolsListHandler(self._tool_registry),
    "tools/call":   ToolsCallHandler(self._tool_registry),
    "prompts/list": PromptsListHandler(self._tool_registry),
    "prompts/get":  PromptsGetHandler(self._tool_registry),
}
```

#### Edge Cases & Error Handling
- `_connect_stdin()` failure propagates up and `run()` returns early (preserves existing behavior).
- `_read_input()` never raises; all error paths write an error response and return `_SKIP`.
- Handler exceptions bubble up to `run()` where they are caught and turned into `JSONRPC_INTERNAL_ERROR` responses.

---

### 6.4 server/__init__.py

**File:** `vidbyte/mcp_server/server/__init__.py`
**Type:** New

#### What it does
Re-exports `McpStudioServer` so `from vidbyte.mcp_server.server import McpStudioServer` continues to work.

```python
from vidbyte.mcp_server.server.core import McpStudioServer
__all__ = ["McpStudioServer"]
```

---

### 6.5 Handler base class

**File:** `vidbyte/mcp_server/server/handlers/__init__.py`
**Type:** New

#### What it does
Defines `_BaseHandler` as a simple ABC that all handler classes inherit. This gives `_dispatch()` a typed contract to program against.

```python
from abc import ABC, abstractmethod
from typing import Any

class _BaseHandler(ABC):
    @abstractmethod
    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]: ...
```

---

### 6.6 InitializeHandler

**File:** `vidbyte/mcp_server/server/handlers/initialize.py`
**Type:** New

#### What it does
Handles the MCP `initialize` handshake. Sets the server-initialized flag and returns server capabilities.

#### Interface / API
```python
class InitializeHandler(_BaseHandler):
    def __init__(self, name: str, version: str, on_initialized: Callable[[], None]) -> None: ...
    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. Call `self._on_initialized()` to flip the server's `_server_initialized` flag.
2. Return `McpSchema.mcp_result_response(request_id, {"protocolVersion": ..., "capabilities": ..., "serverInfo": ...})`.

---

### 6.7 ToolsListHandler

**File:** `vidbyte/mcp_server/server/handlers/tools_list.py`
**Type:** New

#### What it does
Handles `tools/list` — returns all registered studio tool definitions converted to MCP format.

#### Interface / API
```python
class ToolsListHandler(_BaseHandler):
    def __init__(self, registry: StudioToolRegistry) -> None: ...
    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. Call `self._registry.tool_specs()`.
2. Map each spec through `McpSchema.tool_spec_to_mcp_tool()`.
3. Return `McpSchema.mcp_result_response(request_id, {"tools": [...]})`.

---

### 6.8 ToolsCallHandler

**File:** `vidbyte/mcp_server/server/handlers/tools_call.py`
**Type:** New

#### What it does
Handles `tools/call` — validates params, delegates execution to the registry, and converts the result.

#### Interface / API
```python
class ToolsCallHandler(_BaseHandler):
    def __init__(self, registry: StudioToolRegistry) -> None: ...
    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. Validate `params` is a `Mapping`; return `JSONRPC_INVALID_PARAMS` error if not.
2. Extract `tool_name` and `arguments`.
3. Validate `tool_name` is non-empty; return `JSONRPC_INVALID_PARAMS` error if not.
4. `await self._registry.execute(tool_name, arguments)`.
5. Convert result with `McpSchema.tool_result_to_mcp_content()`.
6. Return `mcp_tool_error_result` or `mcp_tool_success_result` based on result status.

---

### 6.9 PromptsListHandler

**File:** `vidbyte/mcp_server/server/handlers/prompts_list.py`
**Type:** New

#### What it does
Handles `prompts/list` — returns a list of available prompt names from the tool registry's prompt content map.

#### Interface / API
```python
class PromptsListHandler(_BaseHandler):
    def __init__(self, registry: StudioToolRegistry) -> None: ...
    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. Iterate `self._registry._prompt_content.items()`.
2. Build list of `{"name": key, "description": ...}` dicts.
3. Return `McpSchema.mcp_result_response(request_id, {"prompts": [...]})`.

---

### 6.10 PromptsGetHandler

**File:** `vidbyte/mcp_server/server/handlers/prompts_get.py`
**Type:** New

#### What it does
Handles `prompts/get` — returns the content of a named prompt.

#### Interface / API
```python
class PromptsGetHandler(_BaseHandler):
    def __init__(self, registry: StudioToolRegistry) -> None: ...
    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. Validate `params` is a `Mapping`; return `JSONRPC_INVALID_PARAMS` error if not.
2. Extract `name`.
3. Look up content in `self._registry._prompt_content`.
4. Return `McpSchema.mcp_result_response` with messages array.

---

### 6.11 handlers.py (import update only)

**File:** `vidbyte/mcp_server/handlers.py`
**Type:** Modified (import update only)

#### What it does
Updates the single `from vidbyte.mcp_server.schema import tool_spec_to_mcp_tool` to `from vidbyte.mcp_server.schema import McpSchema`, and replaces the two call sites `tool_spec_to_mcp_tool(...)` with `McpSchema.tool_spec_to_mcp_tool(...)`.

---

### 6.12 MCP Server Skills

**Files:** `skills/mcp-server/SKILL.md`, `add-tool.md`, `add-handler.md`, `tool-request-response.md`
**Type:** New

#### What they do
- `SKILL.md`: architectural map of `vidbyte/mcp_server/` after the refactor — what each file is responsible for, how the layers connect.
- `add-tool.md`: step-by-step instructions + template for adding a new studio tool (a new `BaseTool` subclass registered with `StudioToolRegistry`).
- `add-handler.md`: step-by-step instructions + template for adding a new JSON-RPC method handler (new handler class in `handlers/`, new entry in `_handler_map`).
- `tool-request-response.md`: annotated walkthrough of a `tools/call` request from stdin bytes to response bytes, including all the layers it passes through.

---

## 7. Data Model Changes

N/A — no schema, database, or dataclass changes.

---

## 8. API Changes

N/A — the JSON-RPC wire format is unchanged. All MCP method names, request shapes, and response shapes remain identical.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/mcp_server/schema.py` | Wrap 8 free functions in `McpSchema` class as `@staticmethod` |
| DELETE | `vidbyte/mcp_server/server.py` | Replaced by `server/` package |
| CREATE | `vidbyte/mcp_server/server/__init__.py` | Re-export `McpStudioServer`; preserves existing import path |
| CREATE | `vidbyte/mcp_server/server/core.py` | Refactored `McpStudioServer` with `_read_input` / `_dispatch` |
| CREATE | `vidbyte/mcp_server/server/handlers/__init__.py` | `_BaseHandler` ABC |
| CREATE | `vidbyte/mcp_server/server/handlers/initialize.py` | `InitializeHandler` |
| CREATE | `vidbyte/mcp_server/server/handlers/tools_list.py` | `ToolsListHandler` |
| CREATE | `vidbyte/mcp_server/server/handlers/tools_call.py` | `ToolsCallHandler` |
| CREATE | `vidbyte/mcp_server/server/handlers/prompts_list.py` | `PromptsListHandler` |
| CREATE | `vidbyte/mcp_server/server/handlers/prompts_get.py` | `PromptsGetHandler` |
| MODIFY | `vidbyte/mcp_server/handlers.py` | Update import + 2 call sites to use `McpSchema` |
| CREATE | `skills/mcp-server/SKILL.md` | Architectural overview of the MCP server |
| CREATE | `skills/mcp-server/add-tool.md` | How to add a new studio tool |
| CREATE | `skills/mcp-server/add-handler.md` | How to add a new JSON-RPC method handler |
| CREATE | `skills/mcp-server/tool-request-response.md` | Request/response lifecycle walkthrough |

Total: 3 modified, 1 deleted, 10 created = **14 file operations**.

---

## 10. Testing Plan

### Unit Tests

`describe('McpSchema')`:
- `it('tool_spec_to_mcp_tool returns correct MCP shape for a spec with required params')` — [Edge Case]
- `it('tool_spec_to_mcp_tool omits required key when no required params')` — [Silent Failure]
- `it('mcp_error_response includes code and message under error key')` — [Hidden Assumption]
- `it('mcp_tool_error_result sets isError=True')` — [Hidden Assumption]
- `it('tool_spec_to_mcp_tool handles spec with zero parameters')` — [Edge Case]

`describe('_read_input')`:
- `it('returns _EOF when reader returns empty bytes')` — [Edge Case]
- `it('returns _SKIP and writes parse error when line is not valid JSON')` — [Hidden Failure]
- `it('returns _SKIP and writes invalid-request error when parsed value is not a Mapping')` — [Hidden Failure]
- `it('returns _SKIP for blank lines without writing any response')` — [Edge Case]
- `it('returns parsed dict for valid JSON-RPC line')` — [Silent Failure — verifies no mutation]

`describe('_dispatch')`:
- `it('routes initialize to InitializeHandler')` — [Hidden Assumption]
- `it('routes tools/list to ToolsListHandler')` — [Hidden Assumption]
- `it('returns METHOD_NOT_FOUND for unknown method strings')` — [Edge Case]
- `it('returns INVALID_REQUEST when method key is missing')` — [Edge Case]
- `it('returns INVALID_REQUEST when method is an integer')` — [Hidden Assumption]

`describe('InitializeHandler')`:
- `it('calls on_initialized callback exactly once')` — [Hidden Failure]
- `it('returns protocol version 2024-11-05')` — [Silent Failure]

`describe('ToolsCallHandler')`:
- `it('returns INVALID_PARAMS when params is not a Mapping')` — [Edge Case]
- `it('returns INVALID_PARAMS when tool name is missing')` — [Edge Case]
- `it('returns isError response when registry raises')` — [Hidden Failure]
- `it('returns isError response when ToolResult.status is error')` — [Silent Failure]

`describe('PromptsGetHandler')`:
- `it('returns INVALID_PARAMS when params is not a Mapping')` — [Edge Case]
- `it('returns empty messages content when prompt name not found')` — [Silent Failure]

### Integration Tests
- Full round-trip: send `initialize` → `tools/list` → `tools/call` over a mocked stdin reader, verify stdout responses are valid JSON-RPC.
- Send malformed JSON followed by a valid request; verify the malformed line gets an error response and the valid request still dispatches correctly — [Hidden Failure: parser error must not corrupt server state].
- Send a `tools/call` for an unknown tool name; verify the response has `isError: True` and the server keeps running — [Hidden Assumption: unknown tool does not crash the loop].
- Existing `tests/` test suite must pass without modification after the refactor.

### Manual / QA Test Cases
1. Given a default `McpStudioServer()` started via `python -m vidbyte.mcp_server`, when `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}` is sent to stdin, then stdout emits a valid JSON-RPC response with `protocolVersion` — [Hidden Assumption: package init works after server.py → server/ rename].
2. Given the server is running, when an invalid JSON line is sent, then a parse error response is emitted and the next valid request still works — [Hidden Failure].
3. Given a server with no agents or tools registered, when `tools/list` is called, then an empty `tools` array is returned (not an error) — [Edge Case].

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| asyncio | stdlib | stdio StreamReader | None — already used |
| json | stdlib | JSON-RPC serialization | None — already used |
| pydantic | >=2,<3 | ToolSpec / ToolResult types | None — already pinned |
| vidbyte.mcp_server.handlers | internal | StudioToolRegistry | None — not modified structurally |

---

## 12. Rollout & Deployment

- No feature flags. This is a pure refactor; all behavior is preserved.
- Not a breaking change for any external consumer: the public import path `from vidbyte.mcp_server import McpStudioServer` and `from vidbyte.mcp_server.server import McpStudioServer` both continue to work.
- No migration needed.
- Rollback: revert the PR. The previous `server.py` file will be restored from git history.

---

## 13. Open Questions

- [ ] Should `_BaseHandler` be in `handlers/__init__.py` or a separate `handlers/base.py`? (Currently: `__init__.py` for minimal file count.)
- [ ] Should `_EOF` / `_SKIP` sentinels be module-level singletons or classes instantiated per call? (Currently: classes, instantiated per call — simpler `isinstance` checks but creates small objects.)
- [ ] Should `InitializeHandler` receive a direct callback (`on_initialized`) or a mutable flag object? Direct callback is more testable but requires a small lambda at construction time. (Currently: callback, for testability.)
- [ ] After refactor, should `skills/sdk/SKILL.md` be updated to document the `server/` package layout? (Leaning yes, but out of scope here.)

---

## 14. Alternatives Considered

### Alternative 1: Keep schema.py as module-level functions, add a module-level `McpSchema` alias object
- What: Create a `McpSchema = types.SimpleNamespace(tool_spec_to_mcp_tool=tool_spec_to_mcp_tool, ...)` at the bottom of the file.
- Why rejected: Doesn't satisfy the intent of having a proper class with methods; still leaves the free functions polluting the module; loses `isinstance` checks and type safety.

### Alternative 2: Keep server.py as a single file, just extract methods inline
- What: Keep `server.py`, add `_read_input()` and `_dispatch()` as methods, keep all `_handle_*` methods in the same file.
- Why rejected: Doesn't satisfy the requirement to move handlers to `vidbyte/mcp_server/server/handlers/`. The file would still be 250+ lines with all handler logic inline.

### Alternative 3: Use a `match` statement instead of a dict-based handler map for dispatch
- What: Python 3.10+ `match method:` with `case "initialize":` branches.
- Why rejected: The dict map is more extensible (handlers are registered as data, not code) and easier to introspect or override in tests. Python 3.11 is required per pyproject.toml so match would work syntactically, but the dict pattern is idiomatic here.

### Alternative 4: Put all handlers in a single `handlers/` `__init__.py`
- What: One `handlers/__init__.py` file exporting all five handler classes.
- Why rejected: The explicit goal is one file per handler for discoverability — you should be able to find `tools/call` logic by navigating to `tools_call.py`.
