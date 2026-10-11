# Design Doc: CodingAgent max_rewrite_lines

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

`write_text` refuses to replace an existing file that has more lines than a set limit. The model then has to use `replace_text` for targeted edits. A model that rewrites a 1,500-line file from memory often drops functions without noticing; small edits leave the rest of the file untouched. The limit lives on `FileSystemToolConfig.max_overwrite_lines` (default `None`, no limit). `CodingAgent` turns it on with a new keyword, `max_rewrite_lines`, which defaults to 300.

The user's request, verbatim:

> No full rewrites of big files (max_rewrite_lines). What it is: write_text is refused on an existing file over a certain size, so the agent has to use targeted replace_text edits instead. Why it's a good idea: When a model rewrites a 1,500-line file from memory, it often drops functions without noticing. Forcing small edits keeps the rest of the file untouched. (this one is changing the tool, but should also be given to the user to control)

---

## 2. Goals & Non-Goals

### Goals
- `WriteTextTool` refuses to overwrite an existing file that has more lines than `FileSystemToolConfig.max_overwrite_lines`, and leaves the file byte-for-byte unchanged.
- `CodingAgent(max_rewrite_lines=300)` is on by default. `None` turns it off.
- When a limit is set, the `write_text` description tells the model about it in one sentence.

### Non-Goals
- No limit on `append_text`, `replace_text`, or `bash`. A model can still rewrite a file through `bash`. The limit stops the common mistake; it is not a security boundary.
- No byte or character limit, and no per-path override.
- No change to the success output of `write_text`. The `feat/edit-tool-diffs` branch owns that.

---

## 3. Background & Context

`CodingAgentTools.get_tools` already builds one `FileSystemToolConfig(root=root_dir, allow_write=True)` and shares it between `read_lines`, `write_text`, and `replace_text`. `FileSystemToolConfig` is a frozen, slotted dataclass in `vidbyte/lib/dataclasses/filesystem.py` with no `__post_init__` today. `CodingAgentSettings` (`vidbyte/lib/dataclasses/coding.py`) holds and checks every `CodingAgent` argument, so the new keyword is one more checked field there (field guide: Strict Config Dataclasses).

---

## 4. Requirements

### Functional Requirements
1. `FileSystemToolConfig.max_overwrite_lines: int | None = None`. Any value other than `None` must be an `int` that is not a `bool` and is at least 1. Otherwise `ConfigurationError` is raised, and its message and details name `max_overwrite_lines`.
2. `WriteTextTool.execute` runs this check after the path is resolved and before the write. If a limit is set and the target is an existing file with more lines than the limit, the call returns `ToolResult.error` and the file is not touched.
3. Lines are counted from bytes: `data.count(b"\n")`, plus 1 if the file is not empty and does not end with `\n`. This means an undecodable file cannot crash the check, and a CRLF line counts as one line.
4. The refusal names the path as the model gave it, the line count, and the limit. It tells the model to use `replace_text`. It does not suggest deleting the file.
5. A new file, a file at or under the limit, and `replace_text` are not affected.
6. `CodingAgent(..., max_rewrite_lines: int | None = 300)`. `CodingAgentSettings.max_rewrite_lines` checks it by the same rule. The error names `max_rewrite_lines` and is raised before `BaseAgent` builds anything. `CodingAgentTools` passes the value into the shared `FileSystemToolConfig`.
7. With a limit set, the `write_text` description ends with one sentence that names the limit. With no limit, the description is unchanged.

### Non-Functional Requirements
- Performance: the check reads the existing file once, and only when a limit is set and the target exists. The overwrite would cost about the same I/O anyway.
- Security, observability, reliability: no change. A failed `stat` or read becomes the tool's usual error result through the existing `except`.

---

## 5. High-Level Design

```
CodingAgent(max_rewrite_lines=300)
  -> CodingAgentSettings (checks max_rewrite_lines)
  -> CodingAgentTools.get_tools(root, fetch_tool, max_rewrite_lines)
       -> FileSystemToolConfig(root, allow_write=True, max_overwrite_lines=...)  (checks it again, as a lib record)
            -> WriteTextTool.spec()     appends one sentence when set
            -> WriteTextTool.execute()  resolve path -> refusal check -> write
```

The tool config owns the behaviour, so any user of the filesystem tools can turn it on. `CodingAgent` only exposes the setting and changes its default. The two names differ on purpose. `max_overwrite_lines` describes the tool action (overwriting a file). `max_rewrite_lines` is the name the user asked for on the agent.

---

## 6. Detailed Design

### 6.1 FileSystemToolConfig
**File:** `vidbyte/lib/dataclasses/filesystem.py` (Modified)

Add the field `max_overwrite_lines: int | None = None` as the last field. Add a `__post_init__` that raises `ConfigurationError("FileSystemToolConfig max_overwrite_lines must be None or an int of at least 1.", details={"max_overwrite_lines": repr(value)})` for a `bool`, any non-`int`, or a value below 1.

### 6.2 WriteTextTool
**File:** `vidbyte/tools/filesystem/write_text.py` (Modified)

- `spec()` builds the same `ToolSpec` as today. When a limit is set, it returns `dataclasses.replace(spec, description=f"{spec.description} Existing files over {limit:,} lines cannot be replaced whole; change them with replace_text.")`. The base description stays one literal, so the sibling `feat/edit-tool-diffs` edit to that literal merges cleanly.
- `execute()` makes one new step between `target = self._path(path)` and the write: `refusal = self._overwrite_refusal(path, target)`. If it returns text, the step returns `ToolResult.error(self.name, refusal)`.
- `_overwrite_refusal(path, target) -> str | None`:
  1. Return `None` when the limit is `None` or `backend.stat(target).is_file` is false.
  2. Count the lines from `backend.read_binary(target)` as described in requirement 3.
  3. Return `None` when the count is at or under the limit. Otherwise return: "write_text refused: `{path}` already has {n:,} lines, over the {limit:,}-line limit for replacing a whole existing file. Use replace_text to change only the parts that need to change."

Edge cases:
- A directory target, or a missing target, skips the check. The write then behaves exactly as before.
- An empty file has 0 lines.
- A `stat` or read failure becomes an error result through the existing `except`.

### 6.3 CodingAgentSettings / CodingAgent / CodingAgentTools
**Files:** `vidbyte/lib/dataclasses/coding.py`, `vidbyte/agents/coding.py`, `vidbyte/tools/toolsets/coding.py` (Modified)

- `CodingAgentSettings` gets a required field, `max_rewrite_lines: int | None`, placed after `permission_policy`. A new helper, `_check_max_rewrite_lines`, raises `ConfigurationError("CodingAgent max_rewrite_lines must be None or an int of at least 1.", details={"max_rewrite_lines": repr(value)})`. The field has no default of its own: `CodingAgent` always passes it, so the 300 default appears only once, in the signature.
- `CodingAgent.__init__` gets the keyword `max_rewrite_lines: int | None = 300` and passes it into the record.
- `CodingAgentTools.get_tools(root_dir, fetch_tool, max_rewrite_lines)` passes it as `max_overwrite_lines` on the shared config.

Why 300: the repo has no existing line budget to align with. This is the brief's number. A file this size is still small enough for a model to rewrite reliably, and anything larger is where dropped functions start to show up.

---

## 7. Data Model Changes

### 7.1 FileSystemToolConfig
**Change type:** Modified. Adds `max_overwrite_lines: int | None = None` and `__post_init__` validation. Existing callers keep their behaviour.

### 7.2 CodingAgentSettings
**Change type:** Modified. Adds the required field `max_rewrite_lines: int | None`. Code that builds the record directly must now pass it. Inside the repo, only `CodingAgent` builds it.

No migration: these are in-memory records.

---

## 8. API Changes

N/A. There are no HTTP endpoints. The Python API changes are listed in §6 and §7. No new public export is added.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/coding-agent-max-rewrite-lines.md` | This doc |
| MODIFY | `vidbyte/lib/dataclasses/filesystem.py` | Field + validation |
| MODIFY | `vidbyte/tools/filesystem/write_text.py` | Refusal check + spec sentence |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | `max_rewrite_lines` field + check |
| MODIFY | `vidbyte/agents/coding.py` | Keyword, default 300 |
| MODIFY | `vidbyte/tools/toolsets/coding.py` | Pass the limit into the file config |
| MODIFY | `vidbyte/agents/README.md` | Coding Agent section: a few lines |
| MODIFY | `tests/test_filesystem_tools.py` | Tool-level cases |
| CREATE | `tests/features/coding_agent/test_coding_agent_max_rewrite_lines.py` | Agent-level cases |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | Expected signature gains `max_rewrite_lines=300` |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `README.md` | Contract line, test map, file index |
| CREATE | `scripts/test-coding-agent-max-rewrite-lines.py` | Thin Phase 5 runner |

The tools README does not document `FileSystemToolConfig`, so it is not changed.

---

## 10. Testing Plan

### Unit Tests (`tests/test_filesystem_tools.py`, class `WriteTextOverwriteLimitTests`)
- A file at exactly the limit is overwritten. A file one line over is refused, the refusal names the path, the count, the limit, and `replace_text`, and the bytes are unchanged. [Edge Case]
- A new 10,000-line file is written under a limit of 1. [Hidden Assumption]
- `replace_text` on a file over the limit succeeds. [Hidden Assumption]
- `max_overwrite_lines=None`, and a default config, overwrite a big file, and the default config's spec is the unchanged description. [Silent Failure]
- Counting: no trailing newline (`a\nb\nc` is 3 lines), CRLF (3 lines), and invalid UTF-8 bytes (refused, not crashed, and unchanged). Each is tested at limit = count − 1 (refused) and limit = count (allowed). [Silent Failure]
- `0`, `-1`, `True`, `2.5`, and `"300"` raise `ConfigurationError` that names `max_overwrite_lines`. [Hidden Assumption]
- The spec mentions the limit only when one is set. [Silent Failure]

### Integration Tests (`tests/features/coding_agent/test_coding_agent_max_rewrite_lines.py`)
- With the default, `write_text` on a 301-line file returns the refusal to the model, the file is unchanged, and the run continues to `isDone`. The `write_text` spec names 300. [Hidden Failure]
- `max_rewrite_lines=None` lets the same call succeed. [Silent Failure]
- `0`, `-1`, `True`, `2.5`, and `"300"` raise `ConfigurationError` that names `max_rewrite_lines`. [Hidden Assumption]

Only the model runner is scripted (`conftest.py`). The file tools and the loop are real.

### Manual / QA Test Cases
N/A. The scripted-model test covers the end-to-end path offline.

---

## 11. Dependencies & External Services

N/A. No new dependencies.

---

## 12. Rollout & Deployment

- No feature flag. `FileSystemToolConfig` defaults to no limit, so every existing filesystem-tool user is unaffected.
- `CodingAgent` behaviour changes: overwriting an existing file over 300 lines is now refused. Pass `max_rewrite_lines=None` to get the old behaviour.
- Rollback: revert the PR.

---

## 13. Open Questions

- [ ] Optional, not built: give `append_text` the same limit? It cannot drop existing content, so it was left alone.
- [ ] Optional, not built: should the refusal also go in result metadata (count and limit) for dashboards? Today it is only in the error text.

---

## 14. Alternatives Considered

### Alternative 1: Put the limit only on CodingAgent (a wrapper tool)
- What: wrap `write_text` in `CodingAgentTools` and leave the tool alone.
- Why rejected: the user said "this one is changing the tool". A config field is smaller than a wrapper, and other tool users get the option too.

### Alternative 2: One shared validator for both fields
- What: a single helper or small dataclass that both records call.
- Why rejected: the two checks are three lines each, have different field names, and give different error text. A new class or module is more code than the duplicate. It is listed here so a reviewer can ask for it.

### Alternative 3: Limit by bytes
- What: refuse by file size instead of line count.
- Why rejected: the user asked for a line limit. Lines match how the model reads files (`read_lines`).
