# Design Doc: CodingAgent reads the root MAP.md (the REPO_MAP section)

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

`CodingAgent` already reads the root folder's `AGENTS.md` once, at construction, and shows it to the model right after the system prompt. This change does the same for a root `MAP.md`: a short, human-written map of where things live in the repository (folders, entry points, and where new code goes). The text fills the reserved `REPO_MAP` section, so the model sees the layout before its first turn and does not spend turns running `ls` and `find`. It is on by default and turned off with `load_map=False`. To avoid copying the AGENTS.md code, both loaders become thin subclasses of one small shared base class.

---

## 2. Goals & Non-Goals

### Goals
- Load `<root_dir>/MAP.md` into the `REPO_MAP` section, with exactly the AGENTS.md behavior (lookup, cap, decoding, truncation note, errors).
- Add a `load_map: bool = True` keyword and settings field, checked as a real bool.
- Share the find, read, decode, and truncate code between the two loaders, without changing AGENTS.md behavior.
- Document `MAP.md` as a CodingAgent convention.

### Non-Goals
- Generating a file list from the tree. The user asked for a human-written file.
- Accepting other names, such as `REPO_MAP.md` (see Open Questions).
- Walking parent folders, merging nested maps, or re-reading per run.
- Any CLI surface. The SDK runs agents from Python only.

---

## 3. Background & Context

The user's words: "Repo file map (repo_map). What it is: Gives the model a list of the repo's files at the start [...] Agents usually spend their first few turns running ls and find just to learn the layout. A file list up front skips that. [...] (note, want to make this a new standards, we should simply read the "map.md" file of the repo, same functionality as agents.md."

Draft PR #769 (the base of this branch) added `CodingContextWindow`, the `CodingContextSection` enum with `REPO_MAP` reserved, and `AgentsMdLoader`. A section takes one loader file, its reserved enum member, and one entry in the `sections` tuple in `CodingAgent.__init__`. `AgentsMdLoader` already holds every step `MAP.md` needs, but its file name, cap, section, title, and switch are hard-coded.

---

## 4. Requirements

### Functional Requirements
1. `CodingAgent(..., load_map=True)` is a new keyword; `CodingAgentSettings.load_map: bool = True` holds it.
2. `load_map` that is not a real `bool` (for example `"yes"`, `1`, `None`) raises `ConfigurationError` naming `load_map`.
3. With `load_map=False`, the root folder is not listed or read for the map.
4. Only `<root_dir>`'s direct children are looked at. The exact name `MAP.md` wins; else the first case-insensitive match in sorted order (so `map.md` is found); else no section.
5. The file is read once, at construction, capped at `CODING_MAP_MD_MAX_BYTES` (32,768) bytes, decoded as UTF-8 with replacement characters and no byte-order mark. A cut never splits a character, and a cut file ends with the same `read_lines` truncation note AGENTS.md uses, naming the map's file.
6. A missing, empty, or whitespace-only file adds no section.
7. A present file that is not a readable regular file (a directory, an unreadable file) raises `ConfigurationError` naming its path.
8. The section is `CodingContextSection.REPO_MAP` (`coding:repo_map`), titled `Repository map (<file name>)`, with the file path as its source. It renders after AGENTS.md (enum order) and before the user message.
9. AGENTS.md behavior does not change; `test_coding_agent_agents_md.py` passes unchanged.

### Non-Functional Requirements
- Performance: one directory listing and one bounded read at construction; nothing per run.
- Security: the read never exceeds the cap, so a huge file cannot fill the context.
- Observability and reliability: N/A beyond the loud `ConfigurationError` for a broken file, which is inherited from the shared code.

---

## 5. High-Level Design

The four steps in `AgentsMdLoader` (find, read capped, decode, add truncation note) move unchanged into a new base class, `RootFileLoader`, in `vidbyte/agents/coding_context/root_file.py`. Each subclass sets four class attributes (`FILE_NAME`, `MAX_BYTES`, `SECTION`, `TITLE`) and overrides one method, `_enabled(settings)`, which returns its own settings switch. `AgentsMdLoader` becomes such a subclass with its current values, and the new `MapMdLoader` in `map_md.py` is the second one.

```
CodingAgent.__init__
  settings = CodingAgentSettings(..., load_agents, load_map)
  sections = (AgentsMdLoader.load(settings), MapMdLoader.load(settings))
                     \                         /
                      RootFileLoader.load (shared steps)
  CodingContextWindow.build(sections, context_manager)  -> AGENTS.md, then MAP.md, after the system prompt
```

No change to `CodingContextWindow` or the enum is needed: the enum's declaration order already puts `REPO_MAP` after `AGENTS_MD` (and after `ENVIRONMENT` if that sibling lands).

---

## 6. Detailed Design

### 6.1 RootFileLoader

**File(s):** `vidbyte/agents/coding_context/root_file.py`
**Type:** New file

The body of today's `AgentsMdLoader`, with its constants replaced by class attributes:

```python
class RootFileLoader:
    FILE_NAME: ClassVar[str]
    MAX_BYTES: ClassVar[int]
    SECTION: ClassVar[CodingContextSection]
    TITLE: ClassVar[str]

    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None: ...
    @staticmethod
    def _enabled(settings: CodingAgentSettings) -> bool: ...   # subclass returns its switch; base raises NotImplementedError
    @classmethod
    def _find_file(cls, root: Path) -> Path | None: ...
    @classmethod
    def _read_capped(cls, path: Path) -> tuple[bytes, int]: ...
    @staticmethod
    def _decode(data: bytes, *, truncated: bool) -> tuple[str, int]: ...
    @staticmethod
    def _with_truncation_note(text: str, name: str, shown_bytes: int, total_bytes: int) -> str: ...
```

`load` returns `CodingContextSectionText(section=cls.SECTION, title=f"{cls.TITLE} ({path.name})", content=text, source=str(path))`. Error messages and details are the existing ones, with `cls.FILE_NAME` in place of the AGENTS.md constant, so AGENTS.md's errors are byte-identical.

### 6.2 AgentsMdLoader

**File(s):** `vidbyte/agents/coding_context/agents_md.py`
**Type:** Modified

Becomes a subclass: `FILE_NAME = CODING_AGENTS_MD_FILE_NAME`, `MAX_BYTES = CODING_AGENTS_MD_MAX_BYTES`, `SECTION = AGENTS_MD`, `TITLE = "Repository instructions"`, `_enabled` returns `settings.load_agents`.

### 6.3 MapMdLoader

**File(s):** `vidbyte/agents/coding_context/map_md.py`
**Type:** New file

`FILE_NAME = CODING_MAP_MD_FILE_NAME` (`"MAP.md"`), `MAX_BYTES = CODING_MAP_MD_MAX_BYTES` (32,768), `SECTION = REPO_MAP`, `TITLE = "Repository map"`, `_enabled` returns `settings.load_map`.

### 6.4 Settings and constructor

**File(s):** `vidbyte/lib/dataclasses/coding.py`, `vidbyte/agents/coding.py`, `vidbyte/lib/constants/coding.py`
**Type:** Modified

- `CodingAgentSettings.load_map: bool = True`, plus one `isinstance(self.load_map, bool)` check in `_check_context_switches` with the same message shape as `load_agents`.
- `CodingAgent.__init__` gains `load_map: bool = True` after `load_agents`, passes it to the settings, and adds `MapMdLoader.load(settings)` to the `sections` tuple.
- Two constants next to the AGENTS.md ones: `CODING_MAP_MD_FILE_NAME = "MAP.md"` and `CODING_MAP_MD_MAX_BYTES = 32_768`.

#### Edge Cases & Error Handling
All inherited from the shared steps: missing or blank file gives `None`; a directory, dangling link, or unreadable file raises `ConfigurationError` with `details["path"]`; an unlistable root raises naming the root and `MAP.md`; invalid UTF-8 becomes U+FFFD.

---

## 7. Data Model Changes

### 7.1 CodingAgentSettings

**Change type:** Modified

```python
load_map: bool = True
```

**Migration strategy:** N/A - an in-process record with a defaulted field; existing callers are unaffected.

---

## 8. API Changes

N/A - no HTTP endpoints. The Python API change is one keyword, `CodingAgent(..., load_map: bool = True)`, and the settings field above. No root `vidbyte` export changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/coding_context/root_file.py` | Shared base with the find/read/decode/truncate steps |
| MODIFY | `vidbyte/agents/coding_context/agents_md.py` | Becomes a thin subclass |
| CREATE | `vidbyte/agents/coding_context/map_md.py` | `MapMdLoader` for the `REPO_MAP` section |
| MODIFY | `vidbyte/lib/constants/coding.py` | `MAP.md` file name and cap |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | `load_map` field and its bool check |
| MODIFY | `vidbyte/agents/coding.py` | `load_map` keyword and the sections-tuple entry |
| MODIFY | `vidbyte/agents/coding_context/README.md` | The `MAP.md` convention and the shared base |
| MODIFY | `vidbyte/agents/README.md` | Coding Agent section: `MAP.md` and `load_map` |
| CREATE | `tests/features/coding_agent/test_coding_agent_map_md.py` | Feature tests |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains `load_map` |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `README.md` | Pack contract and file index |
| CREATE | `scripts/test-coding-agent-map-md.py` | Thin Phase-5 runner |
| CREATE | `docs/design/coding-agent-map-md.md` | This document |

---

## 10. Testing Plan

All tests run offline through the real `BaseAgent` loop with the scripted model, and assert on the system string and prompt the model receives. `test_coding_agent_agents_md.py` is the regression guard for the refactor and must pass unchanged.

### Unit Tests
- MAP.md alone renders after the system prompt and before the user message, with its title and source, and not in the user prompt — [Silent Failure]
- With AGENTS.md and MAP.md both present, AGENTS.md renders first and each appears once — [Hidden Failure]
- Missing, empty, or whitespace-only MAP.md adds no section and no primitives zone — [Edge Case]
- Lowercase `map.md` is found and titled by its real name — [Hidden Assumption]
- A 40 KiB MAP.md whose cap falls inside a 3-byte character shows only whole characters and the MAP.md truncation note — [Silent Failure]
- A directory named MAP.md raises `ConfigurationError` naming the path — [Hidden Failure]
- `load_map=False` with a directory named MAP.md constructs fine and shows nothing (the file is never touched) — [Hidden Assumption]
- `load_map` of `"yes"`, `1`, or `None` raises `ConfigurationError` naming `load_map` — [Hidden Assumption]

### Integration Tests
Covered above: every case builds a real `CodingAgent` and runs one turn, so the loader, the window, and `BaseAgent`'s rendering are exercised together.

### Manual / QA Test Cases
1. Given a project with `MAP.md` and `AGENTS.md`, when a `CodingAgent` is built on it and run, then the request shows the instructions, then the map, then the user message — [Hidden Failure]

---

## 11. Dependencies & External Services

N/A - standard library only (`os`, `codecs`, `pathlib`), as today.

---

## 12. Rollout & Deployment

- Feature flag: `load_map`, default `True`.
- Not breaking: a repository without `MAP.md` sends exactly the same request as before. A repository with a broken `MAP.md` (for example a folder of that name) now fails construction, the same rule AGENTS.md follows.
- Rollback: revert the PR, or pass `load_map=False`.

---

## 13. Open Questions

- [ ] **Q-1 (not built).** vidbyte-sdk's own map is named `REPO_MAP.md`, which its `AGENTS.md` links to, so a `CodingAgent` on this repository would not load it. Should `REPO_MAP.md` be accepted as a fallback name, or should the repository's file be renamed to `MAP.md`? This PR loads `MAP.md` only.

---

## 14. Alternatives Considered

### Alternative 1: A second, copied loader
- What: Copy `AgentsMdLoader` into `map_md.py` with new constants.
- Why rejected: About 80 duplicated lines that would drift; the brief asks to share the code.

### Alternative 2: Parameterize `AgentsMdLoader.load` with arguments
- What: `load(settings, file_name, cap, ...)`.
- Why rejected: Breaks the loader contract `load(settings)` that `CodingAgent` and the window's README rely on.

### Alternative 3: Name the switch as a string attribute (`SWITCH = "load_map"`) read with `getattr`
- What: One less method per subclass.
- Why rejected: A typo fails only at run time and type checkers cannot see it; a one-line `_enabled` override is typed.
