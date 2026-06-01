# Design Doc: Filesystem Tool Migration to BaseTool

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-29
**Last Updated:** 2026-05-29

---

## 1. Overview

The vidbyte-sdk exposes 19 filesystem tool classes (e.g., `WriteTextTool`, `ReadTextTool`) from `vidbyte.tools.filesystem`. These tools are publicly exported and appear to be agent-ready, but they cannot be registered in a `Tools` catalog, passed through `ToolExecutor`, or used by any agent. The root cause is that their base class (`FileSystemTool`) does not extend `BaseTool`, their execution method is `run()` instead of `async execute()`, and they use a private, incompatible `ToolResult(value, metadata)` type instead of the SDK's canonical `ToolResult(tool_name, status, output, metadata)`. This design doc captures the full migration plan to make every filesystem tool a first-class, agent-executable `BaseTool`.

---

## 2. Goals & Non-Goals

### Goals
- Make all 19 filesystem tool classes extend `BaseTool` and implement `spec()` + `async execute(call: ToolCall) -> ToolResult`
- Remove the private `ToolResult` type from `vidbyte/lib/dataclasses/tool_types.py` entirely
- Move `FileStat` (the only other type in `tool_types.py`) to `lib/dataclasses/filesystem.py` where it naturally belongs
- Ensure `Tools([WriteTextTool(config)])` and all other filesystem tools register without error and execute correctly through `ToolExecutor`
- Update `tests/test_filesystem_tools.py` to test tools as async agent tools with `ToolCall` + `ToolResult`
- Preserve all existing filesystem behavior (path scoping, permission guards, backend delegation)

### Non-Goals
- Changing the `FileSystemToolConfig`, `FileSystemPermissions`, or `BaseFileSystemBackend` interfaces
- Changing the `LocalFileSystemBackend` implementation
- Adding new filesystem tools beyond the 19 currently exported
- Changing the `BaseTool` contract itself
- Maintaining a `run()` method on any filesystem tool for backward compatibility

---

## 3. Background & Context

The filesystem tool layer was built against a different `ToolResult` contract that pre-dates the agent execution model. `vidbyte/lib/dataclasses/tool_types.py` defines `ToolResult(value: object, metadata)` — a lightweight internal return type suited to library-style calls. The canonical `ToolResult` in `vidbyte/lib/dataclasses/tools.py` has `(tool_name, status, output, metadata)` with `.success()` and `.error()` factory methods, and is what every other tool (`CalculatorTool`, `FunctionTool`, MCP tools, etc.) returns.

`FileSystemTool` was never bridged to the `BaseTool` interface. It has no `spec()` method and no `execute()` method. Passing any filesystem tool to `Tools([...])` causes `_ensure_catalog_tool` in `catalog.py` to call `ensure_tool`, which calls `isinstance(tool, BaseTool)` (false), then `callable(tool)` (false), and raises `TypeError`. The `_SpecOnlyTool` fallback is never reached because the tools also lack `spec()`.

The existing tests in `test_filesystem_tools.py` call `tool.run(...)` and access `.value` on the legacy `ToolResult`, confirming the tools have only ever been tested as standalone library calls, not as agent tools.

---

## 4. Requirements

### Functional Requirements
1. Every class exported from `vidbyte.tools.filesystem` must be an instance of `BaseTool`.
2. Every filesystem tool must implement `spec() -> ToolSpec` returning a named, described spec with typed parameters and a `ToolPermission` level appropriate to the operation.
3. Every filesystem tool must implement `async execute(call: ToolCall) -> ToolResult` using `ToolResult.success()` and `ToolResult.error()` from `vidbyte.lib.dataclasses.tools`.
4. All path scoping, write-permission guards, and backend delegation logic from the existing `run()` methods must be preserved verbatim in `execute()`.
5. `FileStat` must remain importable from `vidbyte.lib.dataclasses` (public surface unchanged) after `tool_types.py` is deleted.
6. `vidbyte/lib/dataclasses/tool_types.py` must be deleted; no code may import from it after the migration.
7. `Tools([WriteTextTool(config), ReadTextTool(config)])` must construct without error.
8. `await tool.execute(ToolCall("write_text", {"path": "f.txt", "content": "x"}))` must return `ToolResult.success(...)` on the happy path.
9. `await tool.execute(ToolCall(...))` must return `ToolResult.error(...)` (not raise) when the backend raises an exception.
10. The `RenameTool` alias (`RenameTool = MoveTool`) must remain in `move.py`.

### Non-Functional Requirements
- No new runtime dependencies are introduced.
- All output fields in `ToolResult` must be human/LLM-readable strings.
- Binary tool output (`ReadBinaryTool`) must be Base64-encoded in the `output` field.
- Structured output (lists from `ListDirTool`, `FindTool`, `TreeTool`, `ReadLinesTool`, `UnzipTool`) must be newline-joined strings.
- Structured dict output (`StatTool`) must be JSON-serialized.
- Execution time per tool is unchanged (no new I/O paths introduced).

---

## 5. High-Level Design

The migration has three coordinated parts: **type cleanup**, **base-class promotion**, and **tool rewrite**.

**Type cleanup** removes the ambiguous `ToolResult` from `tool_types.py` and co-locates `FileStat` with `FileSystemToolConfig` in `lib/dataclasses/filesystem.py`. The central `lib/dataclasses/__init__.py` already imports both `FileStat` and the canonical `ToolResult` — only the source module of `FileStat` changes. No public import surface breaks.

**Base-class promotion** rewrites `FileSystemTool` in `_base_tool.py` to extend `BaseTool`. All shared helpers (`_path`, `_require_write`, `backend`) are preserved. Because `BaseTool` already declares `spec()` and `execute()` as abstract, no additional abstraction is needed in the intermediate class.

**Tool rewrite** replaces the `run()` method in each of the 19 tool classes with `spec()` and `async execute()`. The `execute()` body wraps the existing backend call in a `try/except Exception` and maps success to `ToolResult.success(self.name, ...)` and failure to `ToolResult.error(self.name, str(exc))`. A `ToolCall` argument is used to extract named parameters that previously came from `run()`'s positional/keyword args.

```
Developer code
    └── Tools([WriteTextTool(config)])
            └── _ensure_catalog_tool(tool)
                    └── ensure_tool(tool)  ← isinstance(tool, BaseTool) → True  ✓
                                              tool registered in catalog

    └── await executor.execute(call)
            └── tool = catalog._get(call.tool_name)
            └── await tool.execute(call) → ToolResult.success(...)
```

The `tests/test_filesystem_tools.py` file is updated to use `asyncio.run()`, construct `ToolCall` objects, and assert on `result.status` and `result.output` instead of `result.value`.

---

## 6. Detailed Design

### 6.1 `FileStat` relocation

**File(s):** `vidbyte/lib/dataclasses/filesystem.py`
**Type:** Modified

#### What it does
`FileStat` is portable file metadata returned by the `stat` backend method. It currently lives in `tool_types.py` alongside the private `ToolResult`. Moving it to `filesystem.py` places it next to `FileSystemToolConfig`, the natural owner of filesystem-specific data contracts.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class FileStat:
    """Portable file metadata returned by filesystem stat operations."""
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int | None
    modified_time: float | None
```

#### Logic / Algorithm
1. Copy the `FileStat` dataclass verbatim from `tool_types.py` into `filesystem.py`.
2. Add `FileStat` to `filesystem.py`'s `__all__`.
3. Update `lib/dataclasses/__init__.py` to import `FileStat` from `filesystem` instead of `tool_types`.
4. Delete `tool_types.py`.

#### Edge Cases & Error Handling
- `lib/tools/filesystem/backends/base.py` imports `FileStat` from `vidbyte.lib.dataclasses` (the central `__init__`), so it is unaffected by the source-module change.
- `lib/tools/filesystem/backends/local.py` does the same.

---

### 6.2 `tool_types.py` deletion

**File(s):** `vidbyte/lib/dataclasses/tool_types.py`
**Type:** Deleted

#### What it does
The private `ToolResult(value, metadata)` type defined here conflicts with the canonical `ToolResult(tool_name, status, output, metadata)`. After `FileStat` is moved and all 19 filesystem tool files are rewritten to import from `vidbyte.tools.types`, this file has no remaining consumers and must be deleted.

#### Edge Cases & Error Handling
- Any future accidental re-import of `from vidbyte.lib.dataclasses.tool_types import ToolResult` will raise `ModuleNotFoundError` at import time, making the error immediately visible.

---

### 6.3 `FileSystemTool` base class

**File(s):** `vidbyte/tools/filesystem/_base_tool.py`
**Type:** Modified

#### What it does
The shared base for all 19 filesystem tool classes. After the change it extends `BaseTool`, inheriting the abstract `spec()` / `execute()` contract while providing shared path-resolution and permission-check helpers.

#### Interface / API
```python
from vidbyte.tools.base import BaseTool

class FileSystemTool(BaseTool):
    def __init__(self, config: FileSystemToolConfig) -> None: ...
    def _path(self, path: str | Path) -> Path: ...
    def _require_write(self) -> None: ...
    @property
    def backend(self) -> BaseFileSystemBackend: ...
```

#### Logic / Algorithm
1. Add `from vidbyte.tools.base import BaseTool` import.
2. Change class declaration to `class FileSystemTool(BaseTool):`.
3. Keep `__init__`, `_path`, `_require_write`, and `backend` exactly as they are.
4. Do NOT declare `spec()` or `execute()` — `BaseTool` already marks them abstract.

#### Edge Cases & Error Handling
- `FileSystemTool` itself remains abstract (because it still has `spec()` and `execute()` unimplemented from `BaseTool`). Attempting to instantiate it directly raises `TypeError: Can't instantiate abstract class`.

---

### 6.4 Filesystem tool rewrites (all 19 tool files)

**Files:** Every `.py` file in `vidbyte/tools/filesystem/` except `_base_tool.py`, `base.py`, and `__init__.py`
**Type:** Modified

#### What each tool does
Each tool implements two methods:

1. `spec() -> ToolSpec` — returns the model-facing declaration (name, description, parameters, permission)
2. `async execute(call: ToolCall) -> ToolResult` — extracts arguments from `call.arguments`, calls the backend, returns `ToolResult.success(self.name, ...)` or catches `Exception` and returns `ToolResult.error(self.name, str(exc))`

#### Common import pattern (replaces the old `from vidbyte.lib.dataclasses.tool_types import ToolResult`)
```python
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter
from vidbyte.tools.filesystem._base_tool import FileSystemTool
```

#### Tool-by-tool spec and execute contracts

**AppendTool** (`append_text.py`)
- spec: `name="append_text"`, permission=WRITE, params: `path(string,req)`, `content(string,req)`, `create_parents(boolean,opt)`
- execute output: `str(target)` (the resolved path)

**ChecksumTool** (`checksum.py`)
- spec: `name="checksum"`, permission=READ, params: `path(string,req)`
- execute output: `digest` string (64-char hex)

**CopyTool** (`copy.py`)
- spec: `name="copy"`, permission=WRITE, params: `source(string,req)`, `destination(string,req)`
- execute output: `str(destination_path)`

**DeleteTool** (`delete.py`)
- spec: `name="delete"`, permission=WRITE, params: `path(string,req)`, `recursive(boolean,opt)`
- execute output: `str(target)`

**DiffTool** (`diff.py`)
- spec: `name="diff"`, permission=READ, params: `path(string,req)`, `content(string,opt)`, `other_path(string,opt)`
- execute output: the unified diff string

**ExistsTool** (`exists.py`)
- spec: `name="exists"`, permission=SAFE, params: `path(string,req)`
- execute output: `"true"` or `"false"`

**FindTool** (`find.py`)
- spec: `name="find"`, permission=READ, params: `pattern(string,req)`, `root(string,opt)`
- execute output: newline-joined matched paths

**ListDirTool** (`list_dir.py`)
- spec: `name="list_dir"`, permission=READ, params: `path(string,opt,default=".")`
- execute output: newline-joined directory entries

**MakeDirTool** (`make_dir.py`)
- spec: `name="make_dir"`, permission=WRITE, params: `path(string,req)`, `parents(boolean,opt)`, `exist_ok(boolean,opt)`
- execute output: `str(target)`

**MoveTool** (`move.py`) — `RenameTool = MoveTool` alias preserved
- spec: `name="move"`, permission=WRITE, params: `source(string,req)`, `destination(string,req)`
- execute output: `str(destination_path)`

**ReadBinaryTool** (`read_binary.py`)
- spec: `name="read_binary"`, permission=READ, params: `path(string,req)`
- execute output: Base64-encoded bytes string

**ReadLinesTool** (`read_lines.py`)
- spec: `name="read_lines"`, permission=READ, params: `path(string,req)`, `start(integer,opt)`, `end(integer,opt)`
- execute output: newline-joined selected lines

**ReadTextTool** (`read_text.py`)
- spec: `name="read_text"`, permission=READ, params: `path(string,req)`
- execute output: the full file text

**ReplaceTextTool** (`replace_text.py`)
- spec: `name="replace_text"`, permission=WRITE, params: `path(string,req)`, `search(string,req)`, `replacement(string,req)`
- execute output: `str(target)`

**StatTool** (`stat.py`)
- spec: `name="stat"`, permission=READ, params: `path(string,req)`
- execute output: JSON-serialized `FileStat` fields (via `json.dumps`)

**TouchTool** (`touch.py`)
- spec: `name="touch"`, permission=WRITE, params: `path(string,req)`, `create_parents(boolean,opt)`
- execute output: `str(target)`

**TreeTool** (`tree.py`)
- spec: `name="tree"`, permission=READ, params: `path(string,opt)`, `max_depth(integer,opt)`, `max_entries(integer,opt)`
- execute output: newline-joined tree entries

**WriteTextTool** (`write_text.py`)
- spec: `name="write_text"`, permission=WRITE, params: `path(string,req)`, `content(string,req)`, `create_parents(boolean,opt)`
- execute output: `str(target)` (the resolved path)

**ZipTool** (`zip_tools.py`)
- spec: `name="zip"`, permission=WRITE, params: `source(string,req)`, `destination(string,req)`
- execute output: `str(destination_path)`

**UnzipTool** (`zip_tools.py`)
- spec: `name="unzip"`, permission=WRITE, params: `source(string,req)`, `destination(string,req)`
- execute output: newline-joined extracted file names

#### Logic / Algorithm (common pattern)
```python
async def execute(self, call: ToolCall) -> ToolResult:
    # Extract arguments from call.arguments, applying defaults
    path = call.arguments.get("path", "")
    # ... extract other params ...
    try:
        # Existing permission checks and backend calls
        self._require_write()  # where applicable
        target = self._path(path)
        # ... backend call ...
        return ToolResult.success(self.name, <output_str>, metadata={...})
    except Exception as exc:
        return ToolResult.error(self.name, str(exc))
```

#### Edge Cases & Error Handling
- `ToolExecutionError` raised by permission guards or path checks is caught by the `except Exception` block and returned as `ToolResult.error`.
- Missing required parameters (e.g., empty `path`) are caught when `_path("")` tries to resolve a blank path — the existing `FileSystemPermissions.resolve_scoped_path` handles the resulting path correctly as a relative empty string (resolves to the root).
- `DiffTool`: if both `content` and `other_path` are absent from `call.arguments`, returns `ToolResult.error` (existing `ToolExecutionError` is caught).
- `ReadBinaryTool`: output is Base64-encoded, so binary files are safely represented in the string-typed output field.
- `StatTool`: `json.dumps` of a `FileStat` requires manual serialization since it's a frozen dataclass; use `dataclasses.asdict`.

---

### 6.5 `tests/test_filesystem_tools.py`

**File(s):** `tests/test_filesystem_tools.py`
**Type:** Modified

#### What it does
The existing test calls `tool.run(...)` and asserts on `.value`. After the migration, all tests use `asyncio.run(tool.execute(ToolCall(...)))` and assert on `result.status == ToolStatus.SUCCESS` and `result.output`.

#### Interface / API
```python
import asyncio
from vidbyte.tools.types import ToolCall, ToolStatus

result = asyncio.run(ReadTextTool(config).execute(ToolCall("read_text", {"path": "nested/file.txt"})))
self.assertEqual(result.status, ToolStatus.SUCCESS)
self.assertEqual(result.output, "hello")
```

#### Logic / Algorithm
- Wrap every `asyncio.run(...)` call around individual `execute()` calls.
- Replace `.value` assertions with `.output` string assertions (adjusting for type serialization: booleans become `"true"/"false"`, lists become newline-joined strings, etc.).
- Add assertions that `result.status == ToolStatus.SUCCESS` on happy-path cases.
- Add assertions that `result.status == ToolStatus.ERROR` on error cases (instead of `assertRaises`).

---

## 7. Data Model Changes

### 7.1 `FileStat`

**Change type:** Modified (source module only — no field changes)

```python
# Moves from vidbyte/lib/dataclasses/tool_types.py
# to vidbyte/lib/dataclasses/filesystem.py
@dataclass(frozen=True, slots=True)
class FileStat:
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int | None
    modified_time: float | None
```

**Migration strategy:**
- Forward: `lib/dataclasses/__init__.py` continues to export `FileStat`; only the import source changes from `tool_types` to `filesystem`. All code that imports via `from vidbyte.lib.dataclasses import FileStat` is unaffected.
- Rollback: revert `filesystem.py` additions, restore `tool_types.py`, revert `__init__.py` import change.

### 7.2 `ToolResult` (tool_types variant)

**Change type:** Deleted

The `ToolResult(value, metadata)` dataclass in `tool_types.py` is removed. No public surface exports it. The only consumers are the 19 filesystem tool files, which are all rewritten in this change.

---

## 8. API Changes

N/A — this is a pure SDK internal refactor. No HTTP endpoints are affected.

The public Python API change is that `vidbyte.tools.filesystem.*Tool` instances now satisfy `isinstance(tool, BaseTool)` and can be passed to `Tools(...)`, `ToolExecutor`, and `BaseAgent`. This is an additive (non-breaking) change for agent-use-case code. It is a breaking change only for code that called `tool.run(...)` directly — which was never documented or part of the public contract.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/dataclasses/filesystem.py` | Add `FileStat` dataclass (moved from tool_types.py) |
| DELETE | `vidbyte/lib/dataclasses/tool_types.py` | Remove incompatible private ToolResult; FileStat relocated |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Import `FileStat` from `filesystem` instead of `tool_types` |
| MODIFY | `vidbyte/tools/filesystem/_base_tool.py` | `FileSystemTool` extends `BaseTool` |
| MODIFY | `vidbyte/tools/filesystem/append_text.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/checksum.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/copy.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/delete.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/diff.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/exists.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/find.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/list_dir.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/make_dir.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/move.py` | Add `spec()` + `async execute()`, remove `run()`; keep `RenameTool` alias |
| MODIFY | `vidbyte/tools/filesystem/read_binary.py` | Add `spec()` + `async execute()`, Base64 output, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/read_lines.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/read_text.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/replace_text.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/stat.py` | Add `spec()` + `async execute()`, JSON output, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/touch.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/tree.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/write_text.py` | Add `spec()` + `async execute()`, remove `run()` |
| MODIFY | `vidbyte/tools/filesystem/zip_tools.py` | Add `spec()` + `async execute()` for both ZipTool and UnzipTool, remove `run()` |
| MODIFY | `tests/test_filesystem_tools.py` | Update to use `asyncio.run(tool.execute(ToolCall(...)))` |
| CREATE | `scripts/test-filesystem-tool-migration.py` | Standalone verification script for all test cases |

**Total: 1 DELETE + 23 MODIFY + 1 CREATE = 25 file changes**

---

## 10. Testing Plan

### Unit Tests

**Group: BaseTool registration**
- `describe('FileSystemTool registration')` -> `it('WriteTextTool is an instance of BaseTool after migration')` — [Hidden Assumption]
- `describe('FileSystemTool registration')` -> `it('ReadTextTool registers in Tools catalog without error')` — [Hidden Assumption]
- `describe('FileSystemTool registration')` -> `it('all 19 filesystem tools can be added to a single Tools catalog without TypeError')` — [Hidden Assumption]
- `describe('FileSystemTool registration')` -> `it('filesystem tool names from spec() are unique across all 19 tools')` — [Silent Failure]

**Group: spec() contracts**
- `describe('WriteTextTool.spec()')` -> `it('returns ToolSpec with name write_text and WRITE permission')` — [Silent Failure]
- `describe('ReadTextTool.spec()')` -> `it('returns ToolSpec with name read_text and READ permission')` — [Silent Failure]
- `describe('ExistsTool.spec()')` -> `it('returns ToolSpec with SAFE permission')` — [Silent Failure]
- `describe('WriteTextTool.spec()')` -> `it('lists path and content as required parameters')` — [Edge Case]
- `describe('ReadLinesTool.spec()')` -> `it('lists start and end as optional parameters')` — [Edge Case]

**Group: execute() happy paths**
- `describe('WriteTextTool.execute()')` -> `it('returns ToolResult.success when file is written')` — [Hidden Assumption]
- `describe('ReadTextTool.execute()')` -> `it('returns output equal to file content')` — [Silent Failure]
- `describe('ExistsTool.execute()')` -> `it('returns output "true" for existing path, "false" for missing')` — [Silent Failure]
- `describe('ListDirTool.execute()')` -> `it('returns newline-joined directory entries')` — [Silent Failure]
- `describe('ReadBinaryTool.execute()')` -> `it('returns Base64-encoded output for binary content')` — [Silent Failure]
- `describe('StatTool.execute()')` -> `it('returns JSON-serialized FileStat for existing file')` — [Silent Failure]
- `describe('FindTool.execute()')` -> `it('returns newline-joined matches for glob pattern')` — [Silent Failure]
- `describe('TreeTool.execute()')` -> `it('returns newline-joined tree entries up to max_depth')` — [Edge Case]
- `describe('ChecksumTool.execute()')` -> `it('returns 64-char hex digest for known content')` — [Silent Failure]
- `describe('DiffTool.execute()')` -> `it('returns non-empty diff when content differs')` — [Silent Failure]
- `describe('ReplaceTextTool.execute()')` -> `it('returns success and writes replacement when search appears exactly once')` — [Hidden Assumption]
- `describe('ZipTool.execute()')` -> `it('returns destination path string on success')` — [Silent Failure]
- `describe('UnzipTool.execute()')` -> `it('returns newline-joined list of extracted members')` — [Silent Failure]

**Group: execute() error paths**
- `describe('WriteTextTool.execute()')` -> `it('returns ToolResult.error (not raises) when allow_write=False')` — [Hidden Failure]
- `describe('ReadTextTool.execute()')` -> `it('returns ToolResult.error when file does not exist')` — [Hidden Failure]
- `describe('ReadTextTool.execute()')` -> `it('returns ToolResult.error when path escapes root')` — [Hidden Assumption]
- `describe('DeleteTool.execute()')` -> `it('returns ToolResult.error for non-existent path')` — [Edge Case]
- `describe('DiffTool.execute()')` -> `it('returns ToolResult.error when neither content nor other_path supplied')` — [Edge Case]
- `describe('ReplaceTextTool.execute()')` -> `it('returns ToolResult.error when search appears zero times')` — [Edge Case]
- `describe('ReplaceTextTool.execute()')` -> `it('returns ToolResult.error when search appears more than once')` — [Edge Case]
- `describe('ReadLinesTool.execute()')` -> `it('returns ToolResult.error when start < 1')` — [Edge Case]
- `describe('ReadLinesTool.execute()')` -> `it('returns ToolResult.error when end < start')` — [Edge Case]

**Group: FileStat relocation**
- `describe('FileStat import')` -> `it('FileStat is importable from vidbyte.lib.dataclasses after tool_types.py deletion')` — [Hidden Assumption]
- `describe('FileStat import')` -> `it('FileStat import from vidbyte.lib.dataclasses.filesystem works directly')` — [Hidden Assumption]
- `describe('tool_types deletion')` -> `it('importing from vidbyte.lib.dataclasses.tool_types raises ModuleNotFoundError')` — [Hidden Assumption]

**Group: edge cases**
- `describe('ExistsTool.execute()')` -> `it('returns "false" for a missing path (not raises)')` — [Edge Case]
- `describe('ReadLinesTool.execute()')` -> `it('returns empty output when start is beyond EOF')` — [Edge Case]
- `describe('TreeTool.execute()')` -> `it('returns at most max_entries entries when directory is large')` — [Edge Case]
- `describe('FindTool.execute()')` -> `it('returns empty string output when no files match the pattern')` — [Edge Case]
- `describe('ListDirTool.execute()')` -> `it('returns empty string output for empty directory')` — [Edge Case]

### Integration Tests

**Flows:**
1. `Tools([WriteTextTool(config), ReadTextTool(config)])` → `catalog.names()` includes both → `catalog._get("write_text")` returns the tool → `execute()` writes and reads correctly.
2. `ToolExecutor` receives a `ToolCall("read_text", {"path": "x.txt"})` against a catalog containing `ReadTextTool` — returns `ToolResult.success`.
3. Path traversal attempt through `ToolCall` arguments propagates to `ToolResult.error` without raising.

**Silent failure paths in integration:**
- `_ensure_catalog_tool` must call `isinstance(tool, BaseTool)` which is now True — if it accidentally falls through to `_SpecOnlyTool`, the tool appears registered but always returns an error. Verified by checking `isinstance(catalog[0], _SpecOnlyTool)` is False.
- `ToolResult.status` must be `ToolStatus.SUCCESS`, not `ToolStatus.ERROR`, on the happy path — a test that only checks `output` without checking `status` would miss a silent error return.

**Hidden assumptions surfaced by integration:**
- The `ToolCall.arguments` dict is always a `Mapping` — confirmed by `ToolCall.__post_init__`; default is `{}` not `None`.
- The `Tools` catalog uses `tool.name` (from `BaseTool.name` property which calls `self.spec().name`) — confirmed once `spec()` is implemented.

### Manual / QA Test Cases

1. Given a `FileSystemToolConfig(root="/tmp/test", allow_write=True)`, when `WriteTextTool` is added to a `Tools` catalog and executed via `ToolExecutor`, then the file is written and `ToolResult.status == SUCCESS` — [Hidden Assumption]
2. Given a readonly config (`allow_write=False`), when `WriteTextTool.execute()` is called, then `ToolResult.status == ERROR` and `ToolResult.output` contains "allow_write" — [Edge Case]
3. Given a `ReadBinaryTool` executed on a known file, when `result.output` is Base64-decoded, then it matches the original bytes — [Silent Failure]
4. Given a `StatTool` executed on a missing path, when `result.output` is JSON-parsed, then `exists == false` and `status == SUCCESS` — [Edge Case]
5. Given an agent configured with `tools=[WriteTextTool(config), ReadTextTool(config)]`, when the agent's `Tools` catalog is introspected, then both tool names appear and `describe()` renders human-readable specs — [Hidden Assumption]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `base64` | 3.11+ | Encode binary output for `ReadBinaryTool` | None — stdlib |
| Python stdlib `json` | 3.11+ | Serialize `FileStat` for `StatTool` | None — stdlib |
| Python stdlib `dataclasses` | 3.11+ | `dataclasses.asdict` for FileStat serialization | None — stdlib |
| `vidbyte.tools.base.BaseTool` | Internal | Parent class for `FileSystemTool` | Existing contract; no changes needed |
| `vidbyte.tools.types` (re-exports `vidbyte.lib.dataclasses.tools`) | Internal | `ToolCall`, `ToolResult`, `ToolSpec`, `ToolParameter`, `ToolPermission` | Existing contract; no changes needed |

---

## 12. Rollout & Deployment

- **Breaking change for `run()` callers:** Any external code calling `tool.run(...)` directly will get `AttributeError`. However, since `run()` was never part of the documented public API and the tools were broken for their intended use (agent tools), this is an acceptable break.
- **No feature flags required:** This is a correctness fix, not a gradual rollout.
- **Migration path for existing `run()` callers:** Replace `tool.run(arg1, arg2)` with `asyncio.run(tool.execute(ToolCall(tool.name, {"arg1": arg1, "arg2": arg2})))`.
- **Deployment order:** Single-service SDK; all changes ship in one commit batch.
- **Rollback:** Revert the branch. The changes are isolated to `vidbyte/lib/dataclasses/` and `vidbyte/tools/filesystem/`.

---

## 13. Open Questions

- [ ] `RenameTool` is currently `RenameTool = MoveTool`. Since `MoveTool.spec()` returns `name="move"`, a `RenameTool` instance will have `self.name == "move"`. Should `RenameTool` get its own class with `name="rename"` and a distinct spec, or is the alias acceptable?
- [ ] `ReadBinaryTool` output is Base64 — is this the preferred encoding for binary data in the agent context, or should it be raw hex? Base64 is more compact (~33% overhead vs 100% for hex).
- [ ] Should the `DiffTool` permission be `READ` (reads two files but writes nothing) or `SAFE`? READ is used here since it accesses the file system.
- [ ] `StatTool` for a missing path currently returns a `FileStat(exists=False, ...)` with status=SUCCESS. Is returning a successful result for a missing path the desired behavior, or should it return `ToolResult.error`? Current behavior (matching the old `run()`) is preserved.

---

## 14. Alternatives Considered

### Alternative 1: Keep `run()` and add `execute()` as a thin wrapper
- **What:** Leave all 19 `run()` methods intact, and have `execute()` call `run()` internally by unpacking `call.arguments`.
- **Why rejected:** This doubles the surface area of each tool, keeps the broken `tool_types.ToolResult` in play (since `run()` still returns it), and creates a confusing API where a tool has both `run()` (sync, positional args, wrong ToolResult) and `execute()` (async, ToolCall, right ToolResult). The point is to fix the contract, not wrap it.

### Alternative 2: Move filesystem tools to a separate non-agent namespace
- **What:** Relocate `vidbyte/tools/filesystem/` to `vidbyte/lib/filesystem/` to signal these are library tools not agent tools, and leave them with `run()`.
- **Why rejected:** This abandons the original intent (agent-usable filesystem tools) and requires updating every downstream import. The correct fix is to make them agent-compatible, not to rename the problem away.

### Alternative 3: Delete `tool_types.ToolResult` but keep `FileStat` in `tool_types.py`
- **What:** Remove only `ToolResult` from `tool_types.py`, keep `FileStat` there, keep the `__init__.py` import path.
- **Why rejected:** `FileStat` is a filesystem data contract — it belongs with `FileSystemToolConfig` in `filesystem.py`. Leaving it in `tool_types.py` after its companion `ToolResult` is removed creates a confusingly named module with a single misplaced dataclass.

### Alternative 4: Make `_SpecOnlyTool` in `catalog.py` call `run()` if `execute()` is absent
- **What:** Extend the `_SpecOnlyTool` adapter to detect `run()` and bridge it to `execute()`.
- **Why rejected:** The filesystem tools don't even have `spec()`, so they never reach `_SpecOnlyTool`. Even if they did, bridging `run()` would require knowing the parameter mapping for each tool (positional args → `ToolCall` arguments), which is not introspectable. This is an adapter in the wrong direction.
