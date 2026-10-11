# Design Doc: Edit tools show the diff of what they changed

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

`write_text` and `replace_text` return only the absolute path of the file they wrote. After this change, the success output keeps that path as its first line and then shows what changed. `replace_text` and a `write_text` over an existing file show a unified diff, capped at 80 lines. A `write_text` that creates a file shows `created, N lines`, and a write that changes nothing shows `no changes`. The model sees its edit land on the same turn, so it can catch a wrong edit right away, for example when `replace_text` hit the wrong one of two similar blocks. There is no setting and no flag: every user of these two tools gets the new output.

User request, verbatim:

> Show the diff after every edit (show_edit_diffs). What it is: After write_text or replace_text, the tool result shows a small diff of what actually changed, instead of just "ok". Why it's a good idea: The model sees its edit land and catches mistakes immediately. For example, if replace_text matched the wrong one of two similar blocks, the diff makes that obvious on the same turn. The SDK already has a filesystem diff tool to build this on. (this is not really a feature to add to give user access to, it is really just changing the way a tool works)

---

## 2. Goals & Non-Goals

### Goals
- Both edit tools return the path, then a diff of the change, on success.
- Reuse `BaseFileSystemBackend.diff_text`, the method the `diff` tool already uses.
- Cap the diff at one module-level constant, with a `[diff truncated: N more lines]` marker.
- A failed write returns the same error as today, with no diff.

### Non-Goals
- No setting, flag, or config field. The cap is not configurable.
- No change to tool metadata, the `diff` tool's parameters, or any other filesystem tool.
- No change to `PatchTool` or `append_text`.

---

## 3. Background & Context

- `vidbyte/tools/filesystem/write_text.py` and `replace_text.py` both return `str(target)` as the success output. The model cannot see what its edit did without a second `read_lines` call.
- `LocalFileSystemBackend.diff_text(left, right_content, *, encoding, label)` already returns a unified diff between a file on disk and proposed text. It reads the file with `Path.read_text`, which turns CRLF into LF. `replace_text` builds its new text from the same LF-normalized read, so a one-line edit on a CRLF file diffs as one line.
- A probe on `main` found one bug the feature would expose: when a file has no trailing newline, `difflib.unified_diff` leaves the last content line without a newline. The next diff line then joins onto it, for example `-alpha beta+alpha gamma` on one line. Files without a trailing newline are common in model-written content, so the diff must be fixed in `diff_text` itself. The fix uses git's `\ No newline at end of file` marker. The `diff` tool gets the same fix.
- Constraint: the sibling branch `feat/coding-agent-max-rewrite-lines` adds a refusal check at the start of `WriteTextTool.execute`. This change touches only the success path and the spec description of `write_text`, so the two merge cleanly.

---

## 4. Requirements

### Functional Requirements
1. `replace_text` success output is `<path>\n<diff>`. The diff is computed from the new text before the write, while the old file is still on disk.
2. `write_text` over an existing file returns `<path>\n<diff>`.
3. `write_text` that creates a file returns `<path>\ncreated, N lines`, where N is `len(content.splitlines())`.
4. A write whose new text equals the old text returns `<path>\nno changes`. This covers both tools (`replace_text` can replace text with the same text).
5. A diff longer than `EDIT_DIFF_MAX_LINES` (80) lines keeps its first 80 lines and then shows `[diff truncated: N more lines]`, where N is the number of lines cut.
6. If the write fails, the result is the same error result as today, with no diff.
7. `write_text` over an existing file that is not valid text in the configured encoding still writes, as it does today. Its output says no diff could be shown, instead of failing the write on a decode error.
8. `diff_text` ends every content line with a newline. When a side has no final newline, the diff adds `\ No newline at end of file` after that line.
9. Each tool's `spec()` description gains one sentence saying the result includes a diff of the change.

### Non-Functional Requirements
- Performance: `difflib` diffs two fully different 20,000-line files in about 0.01 s locally, so diffing every overwrite adds no meaningful time. `replace_text` already reads the whole file.
- Context cost: the cap bounds each result to about 80 diff lines plus the path. A new file is never echoed back.
- Security: none. The diff only shows content of a file inside the scoped root, which the tool already writes.
- Observability: N/A. The output is the model-facing tool result, and metadata is unchanged.

---

## 5. High-Level Design

`FileSystemTool`, the shared base class of both edit tools, gains one helper, `_edit_diff(target, new_content)`, and the module constant `EDIT_DIFF_MAX_LINES = 80`. The helper calls `self.backend.diff_text` with the configured encoding, and returns either `no changes`, the diff, or the capped diff with its marker. Both tools call it after they know the new text and before they write. Each tool then writes and returns `f"{target}\n{change}"`. `write_text` uses the helper only when `self.backend.stat(target).is_file`. Otherwise it reports `created, N lines`.

```
replace_text.execute: read -> count matches -> build updated -> _edit_diff(target, updated) -> write -> "<path>\n<diff>"
write_text.execute:   resolve -> is_file? _edit_diff(target, content) : "created, N lines" -> write -> "<path>\n<change>"
_edit_diff:           backend.diff_text -> "" ? "no changes" : cap at EDIT_DIFF_MAX_LINES
```

The diff is computed before the write, so a failing write raises out of `execute` before the success result is built, and the existing `except` returns the same error as today. The shared helper sits on the base class because both tools inherit from it. That gives one constant and one place to change the output shape.

---

## 6. Detailed Design

### 6.1 FileSystemTool edit diff helper

**File(s):** `vidbyte/tools/filesystem/_base_tool.py`
**Type:** Modified

#### Interface / API
```python
EDIT_DIFF_MAX_LINES = 80

def _edit_diff(self, target: Path, new_content: str) -> str:
```

#### Logic / Algorithm
1. Call `self.backend.diff_text(target, new_content, encoding=self._config.encoding, label=str(target))`. On `UnicodeDecodeError`, return `no diff: the old file is not valid <encoding> text`.
2. An empty diff returns `no changes`.
3. Split the diff on `\n` (not `splitlines`, which would also split on form feeds inside a line). If there are more than `EDIT_DIFF_MAX_LINES` lines, keep the first `EDIT_DIFF_MAX_LINES` and add `[diff truncated: N more lines]`.
4. Return the lines joined with `\n`.

#### Edge Cases & Error Handling
- A missing file is never passed in: `write_text` checks `is_file` first, and `replace_text` already requires an existing file.
- Any other read error propagates to the tool's `except` and becomes an error result, as a failed read does today in `replace_text`.

### 6.2 WriteTextTool

**File(s):** `vidbyte/tools/filesystem/write_text.py`
**Type:** Modified

Add one line before the write: `change = self._edit_diff(target, content) if self.backend.stat(target).is_file else f"created, {len(content.splitlines())} lines"`. The success output becomes `f"{target}\n{change}"`. The spec description gains: "The result shows a diff of the change, or the line count of a new file." A directory target is not a file, so it takes the `created` branch, and the write then fails with today's error.

### 6.3 ReplaceTextTool

**File(s):** `vidbyte/tools/filesystem/replace_text.py`
**Type:** Modified

Add `change = self._edit_diff(target, updated)` after `updated` is built and before the write. The success output becomes `f"{target}\n{change}"`. The spec description gains: "The result shows a diff of the change."

### 6.4 LocalFileSystemBackend.diff_text

**File(s):** `vidbyte/lib/tools/filesystem/backends/local.py`
**Type:** Modified

Join the `unified_diff` lines so that a line without a newline becomes `f"{line}\n\\ No newline at end of file\n"`. Every other line is unchanged.

---

## 7. Data Model Changes

N/A. No dataclass, enum, or config field changes.

---

## 8. API Changes

N/A for HTTP. The model-facing contract changes:

| Tool | Before (success output) | After |
|------|-------------------------|-------|
| `replace_text` | `<path>` | `<path>\n<unified diff or "no changes">` |
| `write_text`, existing file | `<path>` | `<path>\n<unified diff or "no changes">` |
| `write_text`, new file | `<path>` | `<path>\ncreated, N lines` |
| `diff` | joined last line on a missing final newline | `\ No newline at end of file` marker |

Error outputs and metadata are unchanged.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/tools/filesystem/_base_tool.py` | `EDIT_DIFF_MAX_LINES` and `_edit_diff` |
| MODIFY | `vidbyte/tools/filesystem/write_text.py` | Created line or diff; spec sentence |
| MODIFY | `vidbyte/tools/filesystem/replace_text.py` | Diff; spec sentence |
| MODIFY | `vidbyte/lib/tools/filesystem/backends/local.py` | Fix the joined last line with git's marker |
| MODIFY | `tests/test_filesystem_tools.py` | Edit-diff tests |
| MODIFY | `tests/features/coding_agent/test_coding_agent_acceptance.py` | Model sees the `-`/`+` lines |
| MODIFY | `tests/features/coding_agent/FEATURE.md` | Test suite map and observable outcome |
| CREATE | `scripts/test_edit_tool_diffs.py` | Phase 5 runner over the two test files |
| CREATE | `docs/design/edit-tool-diffs.md` | This doc |

---

## 10. Testing Plan

### Unit Tests (`tests/test_filesystem_tools.py`, new `EditToolDiffTests`)
- `replace_text` on a CRLF file changes one line and shows exactly one `-` and one `+` content line; the bytes stay CRLF. — [Silent Failure]
- `replace_text` on a file with two similar blocks shows a hunk whose context names the block that was hit. — [Hidden Failure]
- `write_text` on a new file returns exactly `<path>\ncreated, 3 lines`, with no `@@`. — [Edge Case]
- `write_text` with the file's own content returns `<path>\nno changes`; `replace_text` with `search == replacement` does too. — [Edge Case]
- `write_text` whose backend write raises `PermissionError` returns exactly that error text, no diff, and the file is unchanged. — [Hidden Failure]
- `replace_text` with a search that is not found returns the old error with no diff. — [Hidden Assumption]
- A 200-line rewrite returns 80 diff lines and `[diff truncated: N more lines]`, with N equal to the full diff length minus 80. — [Edge Case]
- A UTF-8 edit (`café` to `naïve 🙂`) diffs with the exact characters. — [Hidden Assumption]
- A file without a trailing newline shows `-alpha beta` and `+alpha gamma` as separate lines, each followed by the marker. — [Silent Failure]
- `write_text` over an existing Latin-1 file still writes and reports that no diff could be shown. — [Hidden Assumption]

### Integration Tests
- `tests/features/coding_agent/test_coding_agent_acceptance.py`: the scripted model calls `write_text`, then `replace_text`, through `CodingAgent`'s real loop. The tool messages the model receives contain `created, 1 lines`, then `-alpha beta` and `+alpha gamma`. — [Hidden Failure]: the diff could be built but dropped between the tool result and the model message.

### Manual / QA Test Cases
N/A. The tests above drive the real tools and the real agent loop.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `difflib` | stdlib | Unified diff, already used by `diff_text` | None |

---

## 12. Rollout & Deployment

- No feature flag, by request.
- Behavior change: any caller that parsed the success output as a bare path breaks. The repository has no such caller, and the path stays on the first line, so `output.splitlines()[0]` keeps working.
- Rollback: revert the PR.

---

## 13. Open Questions

- [ ] Optional, not built: add a `diff_truncated` bool to the result metadata.

---

## 14. Alternatives Considered

### Alternative 1: Hand-rolled `difflib` in the tools
- What: build the diff inside each tool from the in-memory old and new text.
- Why rejected: the brief asks to reuse `diff_text`, and two diff paths would drift.

### Alternative 2: A new lib helper class or a constants module
- What: put the cap in `vidbyte/lib/constants/` or a `vidbyte/lib/tools/filesystem/` helper next to `LineEndings`.
- Why rejected: it needs a new file, a header, and an export for one integer and one ten-line method that only these two tools use. The shared base class they both inherit is the smaller single place.

### Alternative 3: Diff after the write
- What: diff from a saved copy of the old text after writing.
- Why rejected: it needs a second read and keeps the old text in memory. Diffing before the write uses the file still on disk.
