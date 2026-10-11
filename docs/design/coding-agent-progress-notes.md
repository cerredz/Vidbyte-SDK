Stacked on #769

# Design Doc: CodingAgent progress notes

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

A `CodingAgent` starts every run with no memory of the last one. This change gives it a local notes file, `<root_dir>/.vidbyte/progress.md`. The agent creates the file from a tiny template the first time and never overwrites it after that. It shows the file's text to the model as a new context section, `PROGRESS_NOTES`, together with a short instruction: keep this file up to date as you work. A second run on the same folder then starts from where the first one stopped. The folder holds a `.gitignore` containing `*`, so git never sees the notes. The feature is on by default and is turned off with `progress_notes=False`.

---

## 2. Goals & Non-Goals

### Goals
- Add a `progress_notes: bool = True` keyword on `CodingAgent`, stored as a field on `CodingAgentSettings` that must be a real bool.
- Add `CodingContextSection.PROGRESS_NOTES = "coding:progress_notes"` as the last member, so the notes render last, closest to the user's task.
- Add `ProgressNotesLoader.load(settings)`. It creates `.vidbyte/progress.md` and `.vidbyte/.gitignore` when they are missing, never overwrites either one, and returns the section: a short instruction followed by the file's text, capped at 32 KiB.
- When the root cannot be written, return no section and raise nothing.

### Non-Goals
- Resetting the notes for each run, keeping notes outside the repository, a dedicated notes tool, refreshing the section during a run, and committing or cleaning up the notes. These are listed in §13 as optional questions only.
- Making `.vidbyte/progress.md` a repository convention. It is the agent's own local working file.
- Any CLI surface. The feature is the Python API only.
- Editing `agents_md.py` (the map-md sibling is refactoring it).

---

## 3. Background & Context

- PR #769 added `CodingContextWindow`, which places each loader's `CodingContextSectionText` right after the system prompt in `CodingContextSection` order. This feature is one more loader on that helper.
- The user's words: "A notes file, such as .vidbyte/progress.md, loaded at the start like AGENTS.md. The agent is told to update it as it works... (dont want to make this a standard, but the agent should locally get a progress.md file that it can update throughout the run)".
- The agent already has `write_text` and `replace_text` over the root folder, so it needs no new tool to edit the file.
- The trick of a folder that ignores itself comes from pytest's `.pytest_cache`, which writes a `.gitignore` containing `*` inside its own folder.

---

## 4. Requirements

### Functional Requirements
1. `CodingAgent(..., progress_notes=True)` is the default; `progress_notes` must be a real `bool`, or construction raises `ConfigurationError` naming `progress_notes`.
2. With the switch on, construction makes sure `<root>/.vidbyte/` exists, then creates `<root>/.vidbyte/.gitignore` with the text `*` and `<root>/.vidbyte/progress.md` with the template, each only when it is missing.
3. An existing `progress.md` or `.vidbyte/.gitignore` is never overwritten.
4. The loader returns a section titled `Progress notes (.vidbyte/progress.md)`, with the file path as its source. Its content is the instruction, a blank line, and the file's current text.
5. At most 32,768 bytes of the file are read. A longer file is cut, a character split by the cut is dropped, and a line says the notes were cut and how to read the rest.
6. The section renders as primitive `coding:progress_notes`, after every other coding section and before the user message.
7. When creating the folder or a file, or reading the notes, fails with an `OSError` (a read-only checkout, a permission error, a folder where the file should be), the loader returns `None` and construction goes on.
8. With `progress_notes=False`, nothing is created or read and no section is added.

### Non-Functional Requirements
- Performance: two small file creations at most and one bounded read at construction.
- Security: the files stay under the resolved root folder; nothing is committed, and the user's own `.gitignore` is never touched.
- Observability: N/A - the section in the request is the observable result.
- Reliability: the default is on, so a read-only checkout must never fail construction (FR-7).

---

## 5. High-Level Design

One new loader file, `vidbyte/agents/coding_context/progress_notes.py`, follows the three-step pattern of #769: it returns its own enum member, and `CodingAgent.__init__` adds `ProgressNotesLoader.load(settings)` to its `sections` tuple. The window does the placing. The fixed strings (folder name, file name, cap, template, ignore text, instruction, cut note) go in `vidbyte/lib/constants/coding.py`.

```
CodingAgent.__init__
  -> CodingAgentSettings(progress_notes=...)            # checks the bool
  -> ProgressNotesLoader.load(settings)
       mkdir .vidbyte; create .gitignore and progress.md if missing ("x" mode)
       read progress.md (capped) -> CodingContextSectionText | None
  -> CodingContextWindow.build(sections, context_manager)
       places coding:progress_notes last among the sections
```

Files are created with exclusive-create mode (`"xb"`), so an existing file is never overwritten, even one created a moment earlier by another process. The read is deliberately simpler than `AgentsMdLoader`'s: it reads one byte past the cap to learn whether the file is longer, and decodes with errors ignored, which drops a character split by the cut. Notes are small and written by the agent, so this is enough. Every step sits in one `try` that turns an `OSError` into "no section".

---

## 6. Detailed Design

### 6.1 ProgressNotesLoader

**File(s):** `vidbyte/agents/coding_context/progress_notes.py`
**Type:** New file

#### Interface / API
```python
class ProgressNotesLoader:
    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None: ...
```

#### Logic / Algorithm
1. If `settings.progress_notes` is false, return `None`.
2. Inside `try`: `mkdir(exist_ok=True)` the `.vidbyte` folder; `_create_if_missing` the `.gitignore` and the template `progress.md`; `_read_capped` the notes.
3. On `OSError`, return `None`.
4. Return `CodingContextSectionText(PROGRESS_NOTES, "Progress notes (.vidbyte/progress.md)", f"{instruction}\n\n{text}", source=str(path))`.

#### Edge Cases & Error Handling
- If `.vidbyte` is a file, `mkdir` raises `FileExistsError`, and the loader returns `None`.
- If `progress.md` is a folder, the create is skipped and the read raises `OSError`, so the loader returns `None`.
- If the file is blank, the section still renders, because the instruction is never blank.
- If both files already exist on a read-only root, nothing is written, so the section is shown even though the agent cannot update it. The read-only check works by trying to write a missing file.

### 6.2 Settings, enum, constants, CodingAgent

- `vidbyte/lib/dataclasses/coding.py` adds `progress_notes: bool = True`, plus one `isinstance(..., bool)` check in `_check_context_switches`.
- `vidbyte/lib/enums/coding.py` adds the last member, `PROGRESS_NOTES = "coding:progress_notes"`, and updates the docstring.
- `vidbyte/lib/constants/coding.py` adds the `CODING_PROGRESS_NOTES_*` constants.
- `vidbyte/agents/coding.py` adds the `progress_notes: bool = True` keyword, passes it into the settings, and adds `ProgressNotesLoader.load(settings)` to `sections`.

---

## 7. Data Model Changes

### 7.1 CodingAgentSettings
**Change type:** Modified. Adds `progress_notes: bool = True`, which must be a real `bool`.

### 7.2 CodingContextSection
**Change type:** Modified. Appends `PROGRESS_NOTES = "coding:progress_notes"` as the last member.

Migration: N/A - in-memory records only.

---

## 8. API Changes

N/A - no HTTP endpoints. The Python API gains the `CodingAgent(progress_notes: bool = True)` keyword, `CodingContextSection.PROGRESS_NOTES`, and the `CODING_PROGRESS_NOTES_*` constants.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/coding_context/progress_notes.py` | The loader |
| MODIFY | `vidbyte/lib/enums/coding.py` | `PROGRESS_NOTES` member |
| MODIFY | `vidbyte/lib/constants/coding.py` | Folder, file, cap, template, ignore text, instruction, cut note |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | `progress_notes` field and check |
| MODIFY | `vidbyte/agents/coding.py` | Keyword and `sections` entry |
| MODIFY | `vidbyte/agents/coding_context/README.md` | List the section |
| MODIFY | `vidbyte/agents/README.md` | Document the switch and the read-only behavior |
| CREATE | `tests/features/coding_agent/test_coding_agent_progress_notes.py` | Feature tests |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains `progress_notes` |
| MODIFY | `tests/features/coding_agent/test_coding_agent_agents_md.py` | `test_without_agents_md_the_request_equals_a_plain_base_agents`, `test_load_agents_false_shows_no_agents_md`, `test_load_agents_false_never_touches_the_file`, `test_parent_folder_agents_md_is_not_searched`, and `test_blank_file_adds_no_section` assert no context manager or no primitives zone, so they pass `progress_notes=False` |
| MODIFY | `tests/features/coding_agent/test_coding_agent_acceptance.py` | `test_caller_read_only_policy_denies_bash_and_write_without_side_effects` asserts an empty root, so it passes `progress_notes=False` |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `test_coding_agent_exports_the_same_state_as_an_equivalent_base_agent` compares `context_summary` with a manager-less `BaseAgent`, so it passes `progress_notes=False` |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `README.md` | Pack index |
| CREATE | `scripts/test-coding-agent-progress-notes.py` | Thin Phase-5 runner |

---

## 10. Testing Plan

### Unit and integration tests (`test_coding_agent_progress_notes.py`, offline scripted model)
- A fresh root gets both files: the template is shown in the section, and the section renders after `AGENTS.md` and before the user message. [Edge Case]
- An existing `progress.md` is shown unchanged and its bytes are not rewritten. [Silent Failure]
- An existing `.vidbyte/.gitignore` is not overwritten. [Silent Failure]
- In a git repository (skipped when there is no git), `git status --porcelain --untracked-files=all` shows nothing from `.vidbyte/`, and no root `.gitignore` is created. [Hidden Failure]
- End to end: the scripted model runs `replace_text` on `.vidbyte/progress.md`, and a second `CodingAgent` on the same root shows the updated text. [Hidden Assumption]
- A read-only root (`Path.mkdir` patched to raise `PermissionError`) gives no section and does not raise. [Hidden Failure]
- With `progress_notes=False`, no `.vidbyte` folder is created and no section is added. [Edge Case]
- A non-bool `progress_notes` (`"yes"`, `1`, `None`) raises `ConfigurationError`. [Hidden Assumption]
- A `progress.md` over the cap is truncated with the cut note, no more than the cap is shown, and the file on disk is unchanged. [Edge Case]

### Manual / QA
1. Run a `CodingAgent` on a scratch git repository, then check `git status`: `.vidbyte/` is not listed. [Hidden Failure]

---

## 11. Dependencies & External Services

N/A - standard library only (`pathlib`). The git test uses the local `git` binary when present.

---

## 12. Rollout & Deployment

- No feature flag; the `progress_notes` switch is the control.
- Behaviour change: every `CodingAgent` with a writable root now creates `.vidbyte/` there and gets one more section, so the request is no longer byte-identical to a plain `BaseAgent`'s. Pass `progress_notes=False` to restore the old request.
- Rollback: revert the PR.

---

## 13. Open Questions

All of these are optional and none is built:
- [ ] Q-1 (optional): reset the notes at the start of each run, or on request?
- [ ] Q-2 (optional): keep the notes outside the repository (for example, a per-user cache)?
- [ ] Q-3 (optional): add a dedicated notes tool instead of `write_text` / `replace_text`?
- [ ] Q-4 (optional): refresh the section during a run after the agent edits the file?
- [ ] Q-5 (optional): commit the notes, or clean them up when a task finishes?
- [ ] Q-6 (optional): on a read-only root where both files already exist, the section is still shown. Should the loader check writability explicitly?
- [ ] Q-7 (optional): an agent built with a policy that denies WRITE (`permission_policy=PermissionPolicy()`) still gets `.vidbyte/` created at construction, but it cannot update the notes. Should notes be skipped under such a policy?
- [ ] Q-8 (optional): vidbyte-cli's task board also writes to `.vidbyte/` in the project folder (`.vidbyte/task-board`). The `*` ignore hides those checkpoints from git too. Is that wanted, or should the notes live in their own subfolder?

---

## 14. Alternatives Considered

### Add `.vidbyte/` to the user's root `.gitignore`
- Why rejected: that edits a tracked file the user owns. A folder that ignores itself touches nothing of theirs.

### Copy `AgentsMdLoader`'s incremental decoder and size check
- Why rejected: the brief forbids editing `agents_md.py`, and copying it duplicates code. The notes are small and written by the agent, so one bounded read with errors ignored is enough.

### Fail construction when the root cannot be written
- Why rejected: the switch is on by default, so read-only use of `CodingAgent` would break.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
