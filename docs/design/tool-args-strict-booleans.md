# Strict boolean tool arguments

## Summary

Several model-facing tools read their declared `type="boolean"` arguments with
Python truthiness, `bool(call.arguments.get(name, default))`. The runtime hands
tools the arguments exactly as the model sent them, and models sometimes send
booleans as JSON strings. `bool("false")` is `True`, so an explicit "no" turns
into "yes" on destructive operations: `delete(path="reports", recursive="false")`
deletes a non-empty folder recursively, and `mongodb_delete_documents(many="false")`
deletes every match. `bool(None)` also turns a JSON `null` into `False` even where
the documented default is `True` (`make_dir` `parents` / `exist_ok`).

This change makes those arguments strict: absent or `null` means the documented
default, a real JSON boolean means itself, and anything else is refused with the
tool's normal error result before any side effect happens.

## Flow chart

```mermaid
flowchart TD
    A[Tool call arrives with model-written arguments] --> B{Boolean argument value}
    B -- missing or null --> C[Use the documented default]
    B -- true or false --> D[Use the value as given]
    B -- anything else, e.g. "false", 0, "yes" --> E[Raise ToolExecutionError naming the field]
    C --> F[Run the operation]
    D --> F
    E --> G[Tool returns its normal error result; no file or database change]
```

## Usage example

```python
from vidbyte.tools.filesystem import DeleteTool, FileSystemToolConfig
from vidbyte.tools.types import ToolCall

tool = DeleteTool(FileSystemToolConfig(root="workspace", allow_write=True))

# A stringly "false" is refused instead of being read as True.
result = await tool.execute(ToolCall("delete", {"path": "reports", "recursive": "false"}))
assert result.status.value == "error"
assert "'recursive' must be a boolean (true/false)" in result.output  # reports/ still exists

# Real booleans and omitted values behave exactly as before.
await tool.execute(ToolCall("delete", {"path": "reports", "recursive": True}))
```

## How it works

One protected static helper, `BaseTool._resolve_bool_argument(call, name, *, default)`,
lives on the tool base class in `vidbyte/tools/base.py`, so every built-in tool
family (filesystem, provider operation, code search) can reach it without a new
module or a cross-package import. It mirrors the existing `_resolve_bool` in
`vidbyte/tools/builtins/fork/fork.py`: `None` returns the default, a real `bool`
returns itself, and anything else raises `ToolExecutionError` naming the field.
It is a tool-call argument normalizer on a `BaseTool` (verb `resolve`), which is
the shape lint rule C008 treats as a model-facing argument reader rather than a
config validator.

Each call site reads the flag inside the code path that already turns errors into
`ToolResult.error`, and before the side effect:

- Filesystem tools read the flag as the first step inside their existing `try`.
- MongoDB tools read the flag as an argument of the store call, which Python
  evaluates before calling the store; `ProviderOperationTool._result` also catches
  `ToolExecutionError` so the refusal comes back as a tool error.
- `grep` reads `regex` inside its existing `try` and returns an
  `invalid_argument` error.

## Files changed

- `vidbyte/tools/base.py` - the shared helper.
- `vidbyte/tools/filesystem/delete.py`, `make_dir.py`, `write_text.py`, `append_text.py`, `touch.py`.
- `vidbyte/tools/builtins/providers/mongodb.py` (`unique`, `many`) and `_base.py` (catch `ToolExecutionError`).
- `vidbyte/tools/builtins/code_search/grep.py` (`regex`).
- Tests: `tests/test_filesystem_tools.py`, `tests/test_code_search_tools.py`, new `tests/test_mongodb_tools.py`.

`fork.py` is unchanged.

## Risks and open questions

- A caller that relied on `"true"` strings or `0`/`1` being accepted now gets an
  error. That is intended: the declared type is boolean, and the error tells the
  model exactly how to retry.

## Verification

- Regression tests: `delete` with `recursive="false"` on a non-empty directory
  errors and the directory survives; `make_dir` with `parents=None` uses the
  default `True`; `mongodb_delete_documents` / `mongodb_update_documents` with
  `many="false"` are refused without calling the store; `grep` with
  `regex="false"` is refused.
- `python lint/run.py`, `python scripts/run_ci.py`, remote CI.
- Reproduction probe `a306_fs_string_bool_args.py` prints `BAD total 0`.
