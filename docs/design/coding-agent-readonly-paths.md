# Design Doc: CodingAgent readonly_paths

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

`CodingAgent` gets one new keyword, `readonly_paths`: a list of glob patterns, relative to `root_dir`, naming files the model may read but never edit through `write_text` or `replace_text`. The typical value is `["tests/**"]`. When a model is told "make the tests pass", it sometimes edits the tests instead of the code. With the tests read-only, the only way to pass is to fix the code. One small middleware enforces it: before a `write_text` or `replace_text` call runs, it resolves the call's `path` exactly as the tool will, and denies the call with a message that names the file and the pattern.

The user's request, verbatim:

> Protected test files (readonly_paths). What it is: A list of paths the agent can read but never edit, such as tests/**. Why it's a good idea: It pairs with verify_command. When an agent is told "make the tests pass", it sometimes edits the tests instead of the code. With the tests read-only, the only way to pass is to actually fix the bug (can prob implement with a custom middleware hook for the agent that crossreferences the set of files names user inputted).

---

## 2. Goals & Non-Goals

### Goals
- `CodingAgent(readonly_paths=["tests/**"], ...)` denies `write_text` and `replace_text` on any matching file, whatever spelling of the path the model uses, and leaves the file untouched.
- The model sees a denial that names the file and the pattern, so it changes course instead of retrying.
- Reads, searches, and edits of other files work as before.
- With `readonly_paths` empty (the default), the agent is byte-identical to today: no middleware is added.

### Non-Goals
- **bash.** Bash is deliberately unconfined in this agent; it can still edit protected files. Bash commands are never parsed.
- **Caller-supplied tools** are not checked.
- No new glob dialect: `fnmatch.fnmatchcase` only. No other options, no public export of the middleware.

---

## 3. Background & Context

`CodingAgent` (`vidbyte/agents/coding.py`) builds a validated `CodingAgentSettings` (`vidbyte/lib/dataclasses/coding.py`), builds `CodingAgentTools`, and calls `BaseAgent.__init__`. Its header forbids overriding any `BaseAgent` method, so the protection cannot live in the agent's loop. `BaseAgent` already accepts a `middleware` keyword (arriving in `**kwargs`), and `AgentRuntime._process_tool_call` asks the middleware pipeline `before_tool_call` before running any tool. A `DENY_TOOL` decision becomes a `DENIED` tool result whose model-visible text is `Tool denied by middleware: <reason>`. `ToolPolicyMiddleware` (`vidbyte/middleware/builtins/tool_policy.py`) is the existing pattern for denying by tool name.

The file tools resolve their `path` argument with `FileSystemPermissions.resolve_scoped_path(config, path)` (`vidbyte/tools/filesystem/_base_tool.py:_path`), which joins it to the resolved root, resolves `..` and symlinks, and raises when the result leaves the root.

The repository has fixed the bare-string-split bug four times recently (#743, #756, #757, #758): `tuple("tests/**")` silently becomes a tuple of characters. The new field must reject a bare string.

---

## 4. Requirements

### Functional Requirements
1. `CodingAgent.__init__` takes a keyword-only `readonly_paths: Sequence[str] = ()`.
2. `CodingAgentSettings.readonly_paths` holds it. `__post_init__` raises `ConfigurationError` naming `readonly_paths` when the value is a bare `str` or not a sequence, or when any entry is not a `str` or is blank. After construction the field is a `tuple[str, ...]`.
3. Each entry is a glob relative to `root_dir`, written with `/`, matched with `fnmatch.fnmatchcase` against the target's root-relative POSIX path. In fnmatch `*` also matches `/`, so `tests/*` and `tests/**` both cover everything under `tests/`.
4. For a `write_text` or `replace_text` call, the middleware resolves the `path` argument with `FileSystemPermissions.resolve_scoped_path` over a `FileSystemToolConfig` with the same root. `./tests/x.py`, `src/../tests/x.py`, an absolute path inside root, and on Windows `tests\x.py` all resolve to the same file.
5. Comparison is case-insensitive on Windows: `os.path.normcase` is applied to both the target and the pattern.
6. If resolution raises (outside root, invalid path), the middleware continues, so the tool reports its own error unchanged.
7. On a match, the call is denied with the reason `` `<path>` is read-only for this run (readonly_paths: `<pattern>`). ... `` and metadata `{"path", "readonly_path"}`. The tool body never runs.
8. `CodingAgent` appends the middleware after the caller's own `middleware`, keeping the caller's order, and only when `readonly_paths` is non-empty.

### Non-Functional Requirements
- Performance: one path resolution and at most N `fnmatch` calls per edit call. Other tool calls are a name check.
- Security: the check sees the same resolved file the tool writes, so path spelling cannot slip past it. Bash and caller tools are documented gaps (Non-Goals).
- Observability: the denial is recorded as a `DENIED` tool-call state and a middleware event with the path and pattern in metadata.
- Reliability: the middleware keeps `AgentMiddleware`'s default `fail_closed = True`; an unexpected error aborts the run instead of letting the edit through.

---

## 5. High-Level Design

```
CodingAgent.__init__(readonly_paths=[...], middleware=[caller...])
  -> CodingAgentSettings  (validates readonly_paths, stores tuple)
  -> if settings.readonly_paths:
       kwargs["middleware"] = (*caller middleware, ReadonlyPathsMiddleware(root, patterns))
  -> BaseAgent.__init__(..., **kwargs)

run loop: model calls write_text(path="./tests/test_api.py")
  -> AgentRuntime: permission policy -> middleware.before_tool_call
       caller middleware ... -> ReadonlyPathsMiddleware
            resolve_scoped_path(config, path) -> <root>/tests/test_api.py
            relative POSIX "tests/test_api.py" ~ fnmatchcase(normcase) "tests/**"
            -> MiddlewareDecision.deny_tool(reason, metadata)
  -> DENIED ToolResult "Tool denied by middleware: `tests/test_api.py` is read-only ..."
```

One new file, `vidbyte/middleware/builtins/readonly_paths.py`, holds `ReadonlyPathsMiddleware`. REPO_MAP has no CodingAgent-specific folder; it describes `vidbyte/middleware/builtins/` as "the shipped set of policy middleware ... enforcing tool-use policy", which is what this is. It is imported from its module and not added to the `builtins` package exports or the root `vidbyte` export, so the public API contract does not change.

The middleware takes the root folder and the already-validated patterns, not the settings record: the record holds API keys, and the agent must not keep it (CodingAgent "WHAT NOT TO DO" 4).

---

## 6. Detailed Design

### 6.1 CodingAgentSettings.readonly_paths

**File(s):** `vidbyte/lib/dataclasses/coding.py`
**Type:** Modified

#### What it does
Validates the raw `readonly_paths` value and stores it as a tuple.

#### Interface / API
```python
readonly_paths: Sequence[str] = ()   # a tuple[str, ...] after __post_init__

def _readonly_paths(self) -> tuple[str, ...]: ...
```

#### Logic / Algorithm
1. If the value is a `str` or not a `Sequence`, raise `ConfigurationError("CodingAgent readonly_paths must be a list or tuple of glob strings such as ['tests/**'], not a single string.", details={"readonly_paths_type": ...})`.
2. If any entry is not a `str` or is blank after `strip()`, raise `ConfigurationError("CodingAgent readonly_paths entries must be non-blank strings.", details={"bad_entries": [repr(...)]})`.
3. Store `tuple(value)` with `object.__setattr__`.

The field keeps the raw `Sequence[str]` type for the same reason `root_dir` keeps `Path | str`: converting before the record sees it would split a bare string. The docstring says so.

#### Edge Cases & Error Handling
- `()` and `[]` are valid and mean "no protection".
- `b"tests/**"` is not a `str`, but it is a `Sequence`, so it fails at step 2 (its entries are `int`).

### 6.2 ReadonlyPathsMiddleware

**File(s):** `vidbyte/middleware/builtins/readonly_paths.py`
**Type:** New file

#### What it does
Denies `write_text` and `replace_text` calls whose resolved target matches a pattern.

#### Interface / API
```python
class ReadonlyPathsMiddleware(AgentMiddleware):
    def __init__(self, root_dir: Path, readonly_paths: tuple[str, ...]) -> None: ...
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    def _target(self, path: object) -> str | None: ...
    def _matching_pattern(self, target: str) -> str | None: ...
```

#### Logic / Algorithm
1. `before_tool_call`: if there is no tool call or its name is not `write_text`/`replace_text`, continue.
2. `_target`: resolve `call.arguments.get("path", "")` with `FileSystemPermissions.resolve_scoped_path(FileSystemToolConfig(root=root_dir), path)`, then return it relative to the resolved root as a POSIX string. Any exception returns `None`.
3. `None` means the tool will reject the path itself: continue.
4. `_matching_pattern`: return the first pattern where `fnmatch.fnmatchcase(os.path.normcase(target), os.path.normcase(pattern))`.
5. No match: continue. A match: `MiddlewareDecision.deny_tool(reason, metadata={"path": target, "readonly_path": pattern})`.

#### Edge Cases & Error Handling
- A symlink inside root that points at a protected file resolves to the protected file and is denied, because the tool would write through it.
- A pattern naming a folder without a wildcard (`tests`) matches only that exact path; `tests/**` is the documented form.
- A non-string `path` (the model sent a list) raises inside resolution and continues; the tool returns its own error.

### 6.3 CodingAgent wiring

**File(s):** `vidbyte/agents/coding.py`
**Type:** Modified

Adds `readonly_paths: Sequence[str] = ()`, passes it to `CodingAgentSettings`, and, only when `settings.readonly_paths` is non-empty, sets `kwargs["middleware"] = (*kwargs.get("middleware", ()), ReadonlyPathsMiddleware(settings.root_dir, settings.readonly_paths))`. With no patterns, `kwargs` is untouched. A non-linear runtime with `readonly_paths` fails in `BaseAgent` with its existing "does not support middleware" `ConfigurationError`, so the protection is never silently dropped.

---

## 7. Data Model Changes

### 7.1 CodingAgentSettings

**Change type:** Modified

```python
readonly_paths: Sequence[str] = ()  # stored as tuple[str, ...]
```

**Migration strategy:** N/A - in-memory record with a default; nothing is persisted. `export_state()` does not include middleware, so `RunState` is unchanged.

---

## 8. API Changes

N/A - no HTTP endpoints. The Python API change is one keyword on `CodingAgent.__init__`: `readonly_paths: Sequence[str] = ()`. No new public export.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/middleware/builtins/readonly_paths.py` | `ReadonlyPathsMiddleware` |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | `readonly_paths` field and its checks |
| MODIFY | `vidbyte/agents/coding.py` | New keyword; append the middleware |
| MODIFY | `vidbyte/agents/README.md` | Document the setting in "Coding Agent" |
| CREATE | `tests/features/coding_agent/test_coding_agent_readonly_paths.py` | Feature tests |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains `readonly_paths` (the signature test pins every keyword) |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `README.md` | Contract, failure modes, file index (lint S020) |
| CREATE | `scripts/test-coding-agent-readonly-paths.py` | Thin runner for the pytest file |
| CREATE | `docs/design/coding-agent-readonly-paths.md` | This document |

---

## 10. Testing Plan

All tests are offline, in `tests/features/coding_agent/test_coding_agent_readonly_paths.py`, driving the real `BaseAgent` loop through the scripted model in `conftest.py`.

### Unit Tests
- `write_text` and `replace_text` on `tests/test_api.py` with `readonly_paths=["tests/**"]` (a list) are `denied`, the file is byte-identical, and each tool message names `` `tests/test_api.py` `` and `` `tests/**` `` — [Silent Failure]
- Path variants are denied and the file is unchanged: `./tests/test_api.py`, `src/../tests/test_api.py`, the absolute path, a new file `tests/test_new.py` (not created); on Windows also `tests\test_api.py` and `TESTS/test_api.py` — [Hidden Assumption]
- On Windows, `readonly_paths=["Generated/**"]` denies `write_text("GENERATED/out.py", create_parents=True)` where the folder does not exist yet, so only `normcase` can match it — [Hidden Assumption]
- `write_text` to `src/app.py` succeeds and `read_lines` on the protected file returns its text — [Edge Case]
- `write_text("../outside.py")` with `readonly_paths=["*"]` returns exactly the message a plain `CodingAgent` returns — [Hidden Failure]
- `readonly_paths=()` and the default add no middleware; the caller's middleware tuple is passed through as is — [Edge Case]
- `"tests/**"`, `["tests/**", 5]`, and `["tests/**", "  "]` raise `ConfigurationError` naming `readonly_paths` — [Silent Failure]
- A caller's recording middleware sits first in `agent.middleware` and sees the `write_text` call that ours then denies — [Hidden Assumption]

### Integration Tests
Every test above is an integration test: the real runtime, middleware pipeline, permission policy, and file tools run; only the model is scripted.

### Manual / QA Test Cases
1. Given `CodingAgent(root_dir="proj", readonly_paths=["tests/**"])` and a real model, when told "make the tests pass" with a failing test, then any attempt to edit `tests/` shows the denial and the model edits source files instead — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `fnmatch`, `os.path` | stdlib | Matching and case folding | None |

---

## 12. Rollout & Deployment

- No feature flag; the default `()` keeps today's behavior.
- Not breaking. Callers that restore with `BaseAgent.restore(state, tools=...)` must also pass `middleware=CodingAgent(...).middleware` to keep the protection (README note).
- Rollback: revert the PR.

---

## 13. Open Questions

- [ ] Optional, not built: reject patterns that can never match, such as `./tests/**`, absolute patterns, or patterns with `\` on POSIX?
- [ ] Optional, not built: export `ReadonlyPathsMiddleware` from `vidbyte.middleware.builtins` for use on other agents?

---

## 14. Alternatives Considered

### Alternative 1: Wrap write_text and replace_text in a tool view
- What: a `_ToolWrapper` in `CodingAgentTools` that checks the path inside `execute`.
- Why rejected: the user suggested a middleware hook; middleware is where deterministic tool policy lives in this SDK, and the denial is recorded as a `DENIED` state rather than a tool error.

### Alternative 2: Match the raw `path` argument
- What: `fnmatch` the string the model sent.
- Why rejected: `./tests/x.py`, `src/../tests/x.py`, absolute paths, and backslashes would all slip through. Resolving exactly as the tool does closes that.

### Alternative 3: `pathlib.PurePath.match` or `glob`-style `**`
- What: a glob dialect where `*` stops at `/`.
- Why rejected: the brief asks for one dialect, `fnmatch`, where `tests/**` and `tests/*` both mean "everything under tests".
