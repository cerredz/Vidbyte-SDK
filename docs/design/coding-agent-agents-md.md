# Design Doc: CodingAgent loads AGENTS.md, plus the shared coding context window

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-10
**Last Updated:** 2026-10-10

---

## 1. Overview

`CodingAgent` gains one opinionated keyword, `load_agents: bool = True`. When it is on, the agent reads `<root_dir>/AGENTS.md` once, at construction, and places its text in the model's context right after the system prompt, so the model follows the rules a team already wrote down ("use uv, not pip", "run lint/run.py before committing") instead of guessing. The read is plain deterministic code with no model involvement, only the root folder is read, and the text is capped at 32 KiB (32,768 bytes, Codex's default) with a visible truncation line. The section is placed through a new shared helper, `CodingContextWindow`, which owns the whole coding-agent context window on top of the existing `ContextManager` abstraction: system prompt, then AGENTS.md, then the environment context, map.md, and setup-command results that three sibling features will add, then the user prompt. Adding one of those sections takes one loader file, one already-reserved enum member, and one line in `CodingAgent.__init__`.

---

## 2. Goals & Non-Goals

### Goals
- `CodingAgent(load_agents=True)` (the default) shows the root folder's AGENTS.md to the model on every run, after the system prompt and before the user message.
- Read only `<root_dir>/AGENTS.md`; accept a lowercase `agents.md` (any case variant) when the exact name is absent; choose deterministically when several variants exist.
- Read once, at construction, from the resolved absolute root, so a later `chdir` does not change what is loaded.
- Cap the text at 32,768 bytes without splitting a UTF-8 character, and tell the model where the cut is and how to read the rest with `read_lines`.
- `load_agents` is a strictly validated field on `CodingAgentSettings`; `"yes"`, `1`, and `None` fail with a `ConfigurationError` that names the field.
- A shared, ordered coding context window (`CodingContextWindow`) built on `ContextManager.place_after_system_prompt`, with the section order fixed by one enum, so the three sibling sections plug in without changing this PR's files.
- An agent whose root has no AGENTS.md sends a byte-identical request to today's.

### Non-Goals
- Walking parent folders or merging nested AGENTS.md files (the user narrowed this to "just read the root repo's agents.md file").
- Re-reading AGENTS.md on each run, watching it for edits, or exposing a reload method.
- A configurable cap, a CLI flag (`vidbyte/cli/coding.py` is not touched), or a `restore()` path that keeps the section.
- Implementing the environment-context, map.md, or setup-command sections. Their enum members are reserved here; their loaders are their own PRs.
- A new primitive type with "binding instructions" wording (decided against in §14; Q-2).
- Rebinding caller tools that write to the caller's context manager (§6.4 edge cases; Q-1).
- Non-linear runtimes and Codex agents: `CodingAgent` passes them through `BaseAgent` unchanged, as before.

---

## 3. Background & Context

- **Why now.** `CodingAgent` merged in #747 (main `57639080`). It has seven tools and no default system prompt, so the model knows nothing about the repository's own rules unless the caller pastes them into the prompt. AGENTS.md is the de facto place teams write those rules, and both Codex and Claude Code load it automatically.
- **The user's words.** "Before the agent does anything, it reads the repo's AGENTS.md and adds it to what the model sees. [...] A size cap (about 32 KB) keeps a huge file from filling the context." "This should be done deterministically in code, just read the root repo's "agents.md" file and load it into the context window after the system prompt." "(for all things we append to context window, should prob be done through helper class that formats/structured entire coding agent context window that using the context window manager abstraction of the repo), contex window will become something like system prompt, agents.md, environment context, ...(more features), user prompt."
- **Current state, verified in code.**
  - `ContextManager.place_after_system_prompt(item)` (`vidbyte/context/manager.py:92`) registers a primitive at `ContextWindowPlacement.TOP_OF_CONTEXT`. `render_primitives_zone()` (`:202`) renders TOP items first, in registry insertion order, under `## Context Window Primitives`, each with a `### [<primitive_id>] <title>` header.
  - `AgentRuntime._build_system_string` (`vidbyte/agents/runtime.py:1437`) joins, in order: the fixed header (`System prompt:` + the caller's prompt + the agentic-loop note + the tool listing), the loop-budget block (only when budgets are set), the primitives zone of the agent's own `context_manager` and of the per-run input manager, and the context body. The user's message is sent separately (the runner's `prompt`), after the system string. A probe in this worktree confirmed the shape: the scripted runner receives `system` and `tools`, with the user message as the positional prompt.
  - `BaseAgent._merged_context_manager` (`vidbyte/agents/base.py:1482`) rebuilds a manager from `.items()` only, which drops registry primitives, but it only feeds the context body. The runtime itself is built with `context_manager=self.context_manager` (`base.py:1303`), so placed primitives on the agent's own manager do render. A test proves this on the request the scripted model receives.
  - `AgentForker._context_manager` (`vidbyte/agents/fork.py:78`) copies the parent's manager, so a fork keeps any placed section with no extra code.
  - `TextContextItem` (`vidbyte/context/primitives/documents.py:42`) renders the shared managed-context intro, a generic paragraph that says the content "contains the actual prose or instruction supplied by the caller", then the title, an optional `Source:` line, and the content.
- **Constraints.** AGENTS.md Styles 1–4 (one-level call chains, narrated main functions, small single-purpose classes, validated frozen dataclasses); Placement Rules (records in `vidbyte/lib/dataclasses/coding.py`, enums in `vidbyte/lib/enums/coding.py`); the CodingAgent header's WHAT NOT TO DO list (no `BaseAgent` override, no default system prompt, no keys from env, no settings record on the agent); field guide "Strict Config Dataclasses" (every check lives in the record, `__init__` raises nothing), "Prebuilt Agents", "Comment Format" (72-column comment blocks), "Blocking Lint Invariants"; lint rules A001, A002, A006, A007, C001, C002, C007, C008, S020, S061; `scripts/check_context_write_paths.py` (managed context is written only through `ContextManager` public APIs).

---

## 4. Requirements

### Functional Requirements
1. `CodingAgent.__init__` accepts `load_agents: bool = True` and `context_manager: ContextManager | None = None` as explicit keyword-only parameters; every other `BaseAgent` keyword still passes through `**kwargs`.
2. `CodingAgentSettings` gains `load_agents: bool = True`. `__post_init__` raises `ConfigurationError` naming `load_agents` unless the value is a real `bool` (`"yes"`, `1`, `0`, `None` are rejected).
3. With `load_agents=False`, nothing under the root folder is listed or read for AGENTS.md.
4. With `load_agents=True`, the loader lists `root_dir` once and looks only at its direct children. No parent folder is searched.
5. The exact name `AGENTS.md` wins. If it is absent, a child whose name lowercases to `agents.md` is used; if several such variants exist, the first in sorted order is used.
6. A missing file adds no section and raises nothing.
7. A found name that is not a readable regular file (a directory, a dangling symlink, a FIFO) or that cannot be opened or read raises `ConfigurationError` at construction, with the path in the message and in `details["path"]`. A root folder that cannot be listed raises `ConfigurationError` naming the root.
8. At most `CODING_AGENTS_MD_MAX_BYTES` (32,768) bytes are read. The bytes are decoded as UTF-8 with replacement characters for invalid bytes and a leading byte-order mark removed. When the file is longer than the cap, the cut moves back to the last whole character, and a final line states the shown and total byte counts and says to read the rest with `read_lines` from the right line.
9. An empty or whitespace-only file (after decoding) adds no section.
10. The section renders as primitive `coding:agents_md`, titled `Repository instructions (<actual file name>)`, with `Source: <absolute path>`, placed after the system prompt.
11. `CodingContextWindow.build(sections, context_manager)`:
    1. ignores `None` entries;
    2. raises `ConfigurationError` for an entry that is not a `CodingContextSectionText`, for a section kind given twice, and for a `context_manager` that is neither `None` nor a `ContextManager`;
    3. with no sections, returns the caller's `context_manager` object unchanged (or `None`);
    4. otherwise returns a new `ContextManager` whose registry holds the sections in `CodingContextSection` declaration order, each at `TOP_OF_CONTEXT` with the enum value as its primitive id, followed by the caller's registry entries with their own placements, plus the caller's unmanaged items and metadata;
    5. never changes the caller's manager.
12. When the caller's manager already holds a primitive whose id equals a section placed by the window, the window's section wins and the caller's entry is not carried over.
13. `fork()` keeps the section (inherited through `AgentForker`'s manager copy).
14. A sibling section is added with: one loader class in its own file under `vidbyte/agents/coding_context/`, the already-reserved enum member, and one entry in the `sections` tuple in `CodingAgent.__init__` (plus its import). No other file of this PR changes.

### Non-Functional Requirements
- **Performance.** One directory listing and at most one 32 KiB read per construction; nothing per run. The file handle never reads more than the cap.
- **Scalability.** The cap bounds the context cost of AGENTS.md at roughly 8k tokens regardless of file size.
- **Security.** The file is never executed or interpreted. It is the repository's own content shown to a model that already has unsandboxed bash in the same folder, so it adds no new capability. A symlinked AGENTS.md is followed, as Codex does; the target is still capped.
- **Observability.** The rendered section carries its absolute source path, and `agent.context_manager.get_by_id("coding:agents_md")` exposes it. No logging is added (no logger exists on `CodingAgent`).
- **Reliability.** A broken-but-present AGENTS.md fails loudly at construction instead of being silently skipped. A missing one is normal and silent.

---

## 5. High-Level Design

`CodingAgent.__init__` keeps its flat shape and gains two steps between building the tools and calling `BaseAgent.__init__`. First it collects context sections: a tuple with one entry per loader, each loader returning a validated `CodingContextSectionText` or `None`. Today the tuple holds only `AgentsMdLoader.load(settings)`. Then it hands the tuple and the caller's own `context_manager` to `CodingContextWindow.build`, and passes the result to `BaseAgent` as `context_manager`. Nothing else in `CodingAgent` changes, and it still overrides no `BaseAgent` method.

The window puts the sections into a fresh `ContextManager` through `place_after_system_prompt`, in the declaration order of `CodingContextSection`, using each member's value (`coding:agents_md`, ...) as the stable primitive id. It then copies in the caller's registry entries with their placements, after ours, and the caller's unmanaged items and metadata. The runtime already renders the agent's own manager's TOP items right after the fixed system header, so the order the model sees is exactly the order the user asked for. When no loader produced a section, the window returns the caller's manager (or `None`) untouched, so the request is byte-identical to today's.

```
CodingAgent.__init__ (vidbyte/agents/coding.py)
  1. CodingAgentSettings(..., load_agents)            vidbyte/lib/dataclasses/coding.py   (validates)
  2. CodingAgentTools(settings)                       vidbyte/tools/toolsets/coding.py
  3. sections = (AgentsMdLoader.load(settings),       vidbyte/agents/coding_context/agents_md.py
                 # siblings: EnvironmentLoader.load(settings), ...)
  4. window = CodingContextWindow.build(sections,     vidbyte/agents/coding_context/window.py
                                        context_manager)
  5. BaseAgent.__init__(tools=..., context_manager=window, **kwargs)

Every run: AgentRuntime._build_system_string
  [System prompt + agentic-loop note + tool listing]
  [loop budgets, only when set]
  ## Context Window Primitives
    ### [coding:agents_md]      Repository instructions (AGENTS.md)   <- this PR
    ### [coding:environment]    (reserved)
    ### [coding:repo_map]       (reserved)
    ### [coding:setup_results]  (reserved)
    ### [caller TOP items], then [caller END items]
  [context body]
then the user message (the conversation)
```

### Adding a section (the contract for the sibling PRs)

The environment-context, map.md, and setup-command features each add one section. Each takes exactly three things, and no file this PR adds changes:

1. **One loader class in its own file**, `vidbyte/agents/coding_context/<section>.py`, with `@classmethod load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None`. It reads what it needs from the validated settings (including its own switch), does its work once, bounds its own text, and returns `None` when there is nothing to add. Copy the shape of `agents_md.py`: A001 header, narrated `load`, one level of helpers.
2. **Its reserved enum member**: return `CodingContextSectionText(section=CodingContextSection.ENVIRONMENT | REPO_MAP | SETUP_RESULTS, title=..., content=..., source=...)`. The enum already declares the member and its position, so it does not change.
3. **One line in `CodingAgent.__init__`**: import the loader from its module and add `<Loader>.load(settings)` to the `sections` tuple. The tuple's order does not matter; the enum decides the render order.

A section's own on/off switch belongs to that feature, not to this helper: a keyword on `CodingAgent`, a `bool` field on `CodingAgentSettings`, and one `isinstance(..., bool)` check in `CodingAgentSettings._check_context_switches`. The same steps are in `vidbyte/agents/coding_context/README.md` and the "Coding Agent" section of `vidbyte/agents/README.md`.

**Key decisions.** (a) The section order is an enum, not a list in code: a sibling uses its reserved member and never reorders anything. (b) The enum value is the primitive id, so there is no id-building code to keep in sync. (c) `TextContextItem` is reused rather than adding a primitive (§14). (d) The window copies the caller's manager instead of editing it, so one manager shared by several agents never gains another agent's AGENTS.md. (e) The loader takes the whole `CodingAgentSettings` record, so every loader has the same one-argument shape and reads its own switch from it. (f) The new package lives in the agents layer, because sibling loaders need tools and process code (setup commands) that the context layer may not import without a cycle.

---

## 6. Detailed Design

### 6.1 CodingContextSection

**File(s):** `vidbyte/lib/enums/coding.py`, `vidbyte/lib/enums/__init__.py`
**Type:** New file; Modified (export)

#### What it does
Closed set of coding context-window sections. Declaration order is render order. Each value is the section's stable primitive id.

#### Interface / API
```python
class CodingContextSection(str, Enum):
    AGENTS_MD = "coding:agents_md"
    ENVIRONMENT = "coding:environment"
    REPO_MAP = "coding:repo_map"
    SETUP_RESULTS = "coding:setup_results"
```

#### Logic / Algorithm
No behavior. The docstring states that render order is declaration order, that AGENTS_MD is filled by `AgentsMdLoader`, and that ENVIRONMENT, REPO_MAP, and SETUP_RESULTS are reserved for the environment-context, repository-map, and setup-command sections, each filled by its own loader; a member with no loader never appears.

#### Edge Cases & Error Handling
None. Adding a member later in the middle changes render order on purpose; that is the only way order changes.

### 6.2 Constants

**File(s):** `vidbyte/lib/constants/coding.py`
**Type:** New file

#### Interface / API
```python
CODING_AGENTS_MD_FILE_NAME = "AGENTS.md"
CODING_AGENTS_MD_MAX_BYTES = 32_768
```
Not re-exported from `vidbyte/lib/constants/__init__.py`, matching `jev.py` (single consumer, imported from its module).

### 6.3 CodingAgentSettings.load_agents and CodingContextSectionText

**File(s):** `vidbyte/lib/dataclasses/coding.py`
**Type:** Modified

#### What it does
`CodingAgentSettings` gets the `load_agents` switch and its check. A new frozen record, `CodingContextSectionText`, is one rendered section: the contract between loaders and the window.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class CodingAgentSettings:
    ...existing fields...
    load_agents: bool = True

    def _check_context_switches(self) -> None:
        """Raise unless every context-section switch is a real bool."""

@dataclass(frozen=True, slots=True)
class CodingContextSectionText:
    section: CodingContextSection
    title: str
    content: str
    source: str | None = None
```

#### Logic / Algorithm
1. `CodingAgentSettings.__post_init__` gains a fourth narrated step that calls `_check_context_switches()`: `isinstance(self.load_agents, bool)` or `ConfigurationError("CodingAgent load_agents must be True or False.", details={"parameter": "load_agents", "load_agents_type": ...})`. A sibling switch adds one more `isinstance` check in this helper.
2. `CodingContextSectionText.__post_init__` checks: `section` is a `CodingContextSection`; `title` and `content` are non-blank strings; `source` is `None` or a non-blank string. Each error names the field.

#### Edge Cases & Error Handling
- `load_agents=1` is rejected even though `1 == True`; this is C007's "strict bool switch".
- Content is not capped by the record; each loader owns its own bound.

### 6.4 CodingContextWindow

**File(s):** `vidbyte/agents/coding_context/window.py`
**Type:** New file

#### What it does
Builds the `ContextManager` a `CodingAgent` hands to `BaseAgent`: the coding sections first, in section order, then the caller's own context.

#### Interface / API
```python
class CodingContextWindow:
    @classmethod
    def build(cls, sections: Sequence[CodingContextSectionText | None], context_manager: ContextManager | None) -> ContextManager | None: ...
    @staticmethod
    def _present_sections(sections) -> tuple[CodingContextSectionText, ...]: ...
    @staticmethod
    def _check_manager(context_manager) -> None: ...
    @staticmethod
    def _in_render_order(sections) -> tuple[CodingContextSectionText, ...]: ...
    @staticmethod
    def _new_manager(context_manager) -> ContextManager: ...
    @staticmethod
    def _place_sections(window, sections) -> None: ...
    @staticmethod
    def _carry_over_registry(window, context_manager, sections) -> None: ...
```

#### Logic / Algorithm (narrated main function `build`)
1. Keep the sections a loader produced (drop `None`), refusing anything that is not a section record and any section kind given twice (`_present_sections`).
2. Refuse a `context_manager` that is not a `ContextManager` (`_check_manager`).
3. With no sections, return the caller's manager unchanged, or `None`.
4. Sort the sections by enum declaration order (`_in_render_order`, a dict lookup over `tuple(CodingContextSection)`, no lambda).
5. Build a new manager holding the caller's unmanaged items and metadata (`_new_manager`; `ContextManager.__post_init__` copies both, so nothing is shared mutably).
6. Place each section after the system prompt as `TextContextItem(title, content, source, primitive_id=section.value)` (`_place_sections`).
7. Carry over the caller's registry entries in their order with their own placements, skipping an id the window already placed (`_carry_over_registry`, using only `registry_items()`, `placement_for()`, and `upsert()`).
8. Return the new manager.

#### Edge Cases & Error Handling
- No sections and no caller manager → `None` (byte-identical request).
- No sections and a caller manager → that same object (today's behavior, including tools bound to it).
- Caller primitive with a reserved id that the window placed → the window's section wins (FR-12).
- Caller primitive frozen → carried over as-is; `upsert` into the new manager has no prior entry, so it does not raise.
- **Known limitation (Q-1).** When a section is loaded and the caller passed a manager, the agent renders a copy. Tools that write to the caller's manager object (for example `ContextWindowFactory(manager).build()`) keep writing to the caller's object, which this agent no longer renders. This is the cost of "never mutate the caller's manager"; it is documented in the CodingAgent header and README, and the fix (rebind such tools as `fork()` does) is left as Q-1.

### 6.5 AgentsMdLoader

**File(s):** `vidbyte/agents/coding_context/agents_md.py`
**Type:** New file

#### What it does
Reads the root folder's AGENTS.md once, capped at 32 KiB, into the `AGENTS_MD` section.

#### Interface / API
```python
class AgentsMdLoader:
    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None: ...
    @staticmethod
    def _find_file(root: Path) -> Path | None: ...
    @staticmethod
    def _read_capped(path: Path) -> tuple[bytes, int]: ...
    @staticmethod
    def _decode(data: bytes, *, truncated: bool) -> tuple[str, int]: ...
    @staticmethod
    def _with_truncation_note(text: str, name: str, shown_bytes: int, total_bytes: int) -> str: ...
```

#### Logic / Algorithm (narrated main function `load`)
1. If `settings.load_agents` is false, return `None` without touching the filesystem.
2. `_find_file(settings.root_dir)`: `os.listdir(root)` (an `OSError` becomes `ConfigurationError` naming the root); keep names whose `.lower()` equals `agents.md`; prefer the exact `AGENTS.md`, else the first sorted match; `None` when there is no match. One listing serves every platform: on Windows it also yields the real on-disk case for the title.
3. If no file, return `None`.
4. `_read_capped(path)`: if `not path.is_file()`, raise `ConfigurationError` naming the path ("not a readable regular file"); else open in binary mode, take the total size from `os.fstat`, read at most `CODING_AGENTS_MD_MAX_BYTES`; an `OSError` becomes `ConfigurationError` naming the path, chained with `from`.
5. `_decode(data, truncated=total > len(data))`: an incremental `utf-8-sig` decoder with `errors="replace"`, `final=not truncated`; a trailing partial character stays in the decoder's buffer and is not emitted; the shown byte count is `len(data) - len(pending)`.
6. If the decoded text is blank, return `None`.
7. If the shown bytes are fewer than the total, append the note via `_with_truncation_note`: `[<name> was truncated at <shown> of <total> bytes. Read the rest with the read_lines tool (path "<name>"), starting at line <n>.]`, where `n = text.count("\n") + 1` (the partial line, if any, is re-read in full).
8. Return `CodingContextSectionText(section=AGENTS_MD, title=f"Repository instructions ({path.name})", content=text, source=str(path))`.

#### Edge Cases & Error Handling
- Missing file → `None`. Empty, whitespace-only, or BOM-plus-whitespace file → `None`.
- Exactly 32,768 bytes → no truncation note.
- Invalid UTF-8 → U+FFFD replacement characters, no error.
- A multibyte character straddling the cap → dropped from the shown text; the note's byte count says where the cut is.
- AGENTS.md is a directory, a dangling symlink, or unreadable → `ConfigurationError` with the path.
- Edits after construction are not seen until a new agent is built (documented).
- The file growing or shrinking during the read is not handled beyond the cap.

### 6.6 CodingAgent

**File(s):** `vidbyte/agents/coding.py`
**Type:** Modified

#### Interface / API
```python
def __init__(self, *, root_dir: str | Path, firecrawl_api_key: str | None = None, browserbase_api_key: str | None = None, parallel_api_key: str | None = None, tavily_api_key: str | None = None, tools: Sequence[object] | Tools = (), permission_policy: PermissionPolicy | None = None, load_agents: bool = True, context_manager: ContextManager | None = None, **kwargs: Any) -> None
```

#### Logic / Algorithm
Existing steps unchanged, plus: `load_agents` goes into `CodingAgentSettings`; after the tools are built, `sections = (AgentsMdLoader.load(settings),)`; `context_window = CodingContextWindow.build(sections, context_manager)`; `super().__init__(..., context_manager=context_window, **kwargs)`. Every step keeps its narration comment. `__init__` still raises nothing itself and stores nothing new on the agent. The header's PURPOSE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, and TESTS are updated.

#### Edge Cases & Error Handling
- `BaseAgent.restore(state, tools=...)` and a cold session resume rebuild a plain `BaseAgent` without the section (documented, Q-4).
- `export_state()["context_summary"]["has_context_manager"]` is `True` when a section was loaded, as for any `BaseAgent` with a manager.
- Tools bound to a primitive (`binds_to_primitive`: fork, handoff, reasoning tools) start routing into the manager when a section is loaded, as they do on any `BaseAgent` with a manager. None of the seven coding tools binds to a primitive.

### 6.7 Package marker and READMEs

**File(s):** `vidbyte/agents/coding_context/__init__.py`, `vidbyte/agents/coding_context/README.md`, `vidbyte/agents/README.md`
**Type:** New, New, Modified

- `__init__.py` holds only the A001 header; it exports nothing, so a sibling loader never edits it. Callers import `vidbyte.agents.coding_context.window` and `.agents_md` directly.
- The package README states the contract, the render order, the three steps to add a section, and notes for agents. It deliberately has no `## File Index` heading, so S020 does not require a sibling to edit it.
- `vidbyte/agents/README.md`, "Coding Agent" section: the `load_agents` keyword, what is loaded, the cap, read-once, the caller-manager behavior, and the three steps.

---

## 7. Data Model Changes

### 7.1 CodingAgentSettings

**Change type:** Modified

```python
load_agents: bool = True   # new, last field; strict bool
```

### 7.2 CodingContextSectionText

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class CodingContextSectionText:
    section: CodingContextSection
    title: str
    content: str
    source: str | None = None
```

### 7.3 CodingContextSection

**Change type:** New (enum, see §6.1)

**Migration strategy:** N/A - in-process objects only; nothing is persisted. `RunState` is unchanged.

---

## 8. API Changes

N/A - no HTTP endpoints; this is an in-process library change. The Python API changes are:

### 8.1 `CodingAgent.__init__`

**Change type:** Modified (two new keyword-only parameters)

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `load_agents` | `bool` | `True` | Read `<root_dir>/AGENTS.md` once and show it after the system prompt. |
| `context_manager` | `ContextManager \| None` | `None` | Was a `BaseAgent` keyword through `**kwargs`; now named so it can be merged. Same meaning. |

**Error cases:**
| Error | Condition |
|--------|-----------|
| `ConfigurationError` (names `load_agents`) | `load_agents` is not a real bool |
| `ConfigurationError` (names the path) | AGENTS.md is present but is not a readable regular file, or cannot be read |
| `ConfigurationError` (names `context_manager`) | `context_manager` is neither `None` nor a `ContextManager` |

No root `vidbyte` export changes, so `contracts/sdk-public-api.json` is not regenerated.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/coding-agent-agents-md.md` | This design doc |
| CREATE | `vidbyte/lib/enums/coding.py` | `CodingContextSection` (Placement Rules: enums) |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export the public enum (Placement Rules) |
| CREATE | `vidbyte/lib/constants/coding.py` | `CODING_AGENTS_MD_FILE_NAME`, `CODING_AGENTS_MD_MAX_BYTES` (A007, brief) |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | `load_agents` field and check; `CodingContextSectionText` |
| CREATE | `vidbyte/agents/coding_context/__init__.py` | Package marker (no exports) |
| CREATE | `vidbyte/agents/coding_context/window.py` | `CodingContextWindow` |
| CREATE | `vidbyte/agents/coding_context/agents_md.py` | `AgentsMdLoader` |
| CREATE | `vidbyte/agents/coding_context/README.md` | Contract and the three steps for siblings |
| MODIFY | `vidbyte/agents/coding.py` | Two keywords, two steps, header |
| MODIFY | `vidbyte/agents/README.md` | Coding Agent section |
| CREATE | `tests/features/coding_agent/test_coding_agent_agents_md.py` | Feature tests (source of truth) |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains the two keywords (the file's own COMMON MODIFICATION PATTERNS require it) |
| MODIFY | `tests/features/coding_agent/FEATURE.md` | Contract, invariants, failure modes, suite map |
| MODIFY | `tests/features/coding_agent/README.md` | File index and log |
| CREATE | `scripts/test-coding-agent-agents-md.py` | Phase-5 runner over the pytest file (repo names these scripts with hyphens) |

---

## 10. Testing Plan

All tests are offline: the scripted tool-calling model from `conftest.py` (wrapped to also record the user prompt), real temporary folders, no network, no keys. Assertions are made on the `system` string and prompt the scripted model actually receives, plus `agent.context_manager` public APIs.

### Unit Tests
- `AgentsMdLoader` / agent → `it renders AGENTS.md after the system prompt and before the user message` — [Silent Failure]
- agent → `it sends the same request as an equivalent BaseAgent when the root has no AGENTS.md, with no primitives zone and context_manager None` — [Silent Failure]
- agent → `it never reads AGENTS.md when load_agents=False` (a file is ignored, and an AGENTS.md directory that would raise is never touched) — [Hidden Assumption]
- agent → `it loads a lowercase agents.md when AGENTS.md is absent` — [Edge Case]
- agent → `it prefers AGENTS.md over agents.md` (skipped on a case-insensitive filesystem) — [Hidden Assumption]
- agent → `it does not search parent folders` — [Hidden Assumption]
- agent → `it cuts a 40 KiB file at 32,768 bytes with a truncation line, and a 2-, 3-, or 4-byte character straddling the cap is dropped, not garbled` — [Edge Case]
- agent → `it adds no truncation line to a file of exactly 32,768 bytes` — [Edge Case]
- agent → `it adds no section for an empty, whitespace-only, or BOM-plus-whitespace file` — [Edge Case]
- agent → `it decodes invalid UTF-8 with replacement characters` — [Hidden Failure]
- agent → `it raises ConfigurationError naming the path when AGENTS.md is a directory` — [Hidden Failure]
- agent → `it raises ConfigurationError naming the path, chained from the PermissionError, when AGENTS.md cannot be opened` (`Path.open` patched, so it runs on every platform) — [Hidden Failure]
- settings → `load_agents "yes", 1, 0, None, "false" raise ConfigurationError naming load_agents` — [Hidden Assumption]
- agent → `a caller context_manager's placed primitives render after AGENTS.md, its unmanaged items still reach the body, and the caller's manager is unchanged after construction and a run` — [Hidden Failure]
- agent → `fork() keeps the AGENTS.md section` — [Hidden Failure]
- agent → `a chdir after construction does not change which AGENTS.md is shown` — [Hidden Assumption]
- agent → `an edit to AGENTS.md after construction is not seen by that agent` — [Silent Failure]
- `CodingContextWindow` → `sections passed out of order render in enum order, None entries ignored` — [Silent Failure]
- `CodingContextWindow` → `no sections returns the caller's manager object, or None` — [Silent Failure]
- `CodingContextWindow` → `a non-record entry, a repeated section, or a non-manager context_manager raises ConfigurationError` — [Hidden Assumption]
- `CodingContextWindow` → `a caller primitive with a placed section's id does not replace the section` — [Hidden Failure]
- `CodingContextSectionText` → `blank title, blank content, non-enum section, or blank source raises ConfigurationError naming the field` — [Hidden Assumption]
- contract → `EXPECTED_SIGNATURE` includes `load_agents=True` and `context_manager=None` — [Hidden Assumption]

### Integration Tests
- The tests above drive `CodingAgent` through `BaseAgent.run`, `AgentRuntime`, and the real `ContextManager`, so the window, the runtime's system-string assembly, and fork are tested together. Only the model runner is faked.
- The silent path between components is `BaseAgent._merged_context_manager` dropping registry primitives; the first test proves the section still reaches the model.
- The existing feature-pack tests run unchanged (tmp roots have no AGENTS.md) and prove the byte-identical path, except the one `EXPECTED_SIGNATURE` edit.

### Manual / QA Test Cases
1. Given this repository as `root_dir` (its AGENTS.md is about 13 KB), when a `CodingAgent` runs with a scripted model, then the system string contains `### [coding:agents_md] Repository instructions (AGENTS.md)` after the tool listing — [Silent Failure]
2. Given a 100 KB AGENTS.md, when the agent is built, then the section ends with the truncation line and `read_lines` with the named start line returns the continuation — [Edge Case]
3. Given `AGENTS.md` as a folder, when the agent is built, then construction fails naming that folder — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `codecs`, `os` | 3.11+ | Incremental UTF-8 decode, directory listing, `fstat` | None |
| `vidbyte.context.manager.ContextManager` | in-repo | Placement API and rendering | Registry order is dict insertion order; the window relies on it, as `render_primitives_zone` does |
| `vidbyte.context.primitives.TextContextItem` | in-repo | Rendered section | Its generic paragraph is shared with every text primitive (Q-2) |

No new third-party dependency, network call, or service.

---

## 12. Rollout & Deployment

- **Feature flag.** `load_agents=True` by default (the user asked for an opinionated default); `load_agents=False` turns it off per agent.
- **Breaking change.** For callers whose `root_dir` has an AGENTS.md, the model now sees it, and `agent.context_manager` is a new manager when they passed one. A broken AGENTS.md (a directory) now fails construction. The SDK is alpha. Callers without AGENTS.md see no change.
- **Deployment order.** Single package. The three sibling PRs branch from this branch.
- **Rollback.** Revert the PR, or pass `load_agents=False`.

---

## 13. Open Questions

Optional controls surfaced by self-critique. None is built in this PR.
- [ ] **Q-1.** When a section is loaded and the caller passes a `context_manager`, should `CodingAgent` rebind caller tools that write to that manager (as `AgentForker._clone_tool` does with `rebind_context_manager`), so `ContextWindowFactory` tools keep working? Default: no; documented limitation.
- [ ] **Q-2.** Should AGENTS.md render through a dedicated primitive whose text says these are the repository's binding instructions, instead of `TextContextItem`'s generic paragraph? Default: no (§14).
- [ ] **Q-3.** Should the 32 KiB cap be configurable, or should nested/parent AGENTS.md files be merged as Codex does? Default: no; fixed constant, root only.
- [ ] **Q-4.** Should `restore()` / session resume rebuild the section? Default: no; restore returns a plain `BaseAgent` already (spec NG-11).
- [ ] **Q-5.** Should `vidbyte-sdk coding run` get a `--no-agents-md` flag? Default: no (the field guide records that the CLI is being removed).

---

## 14. Alternatives Considered

### Alternative 1: A dedicated `RepositoryInstructionsContextItem` primitive
- What: a new primitive whose rendered text calls the content the repository's binding instructions.
- Why rejected: `TextContextItem`'s paragraph already says the content "contains the actual prose or instruction supplied by the caller" and that its meaning "comes from its body", and the title names it "Repository instructions", so the wording does not mislead. A new primitive is a new dataclass, which the Placement Rules put in `vidbyte/lib/dataclasses/`, where it cannot import the context layer's intro helper; it would also become a second contract for every sibling section. Kept as Q-2.

### Alternative 2: Edit the caller's `context_manager` in place
- What: insert the sections into the caller's manager (re-inserting its entries after ours to fix the order).
- Why rejected: the brief requires that the caller's manager never changes; a manager shared by several agents would otherwise gain one agent's AGENTS.md for all. Its one advantage, keeping tools bound to the caller's manager working, is kept as Q-1.

### Alternative 3: Append AGENTS.md to the system prompt string
- What: `system_prompt + "\n\n" + agents_md`.
- Why rejected: the user asked to go through the context-window-manager abstraction; it would change `export_state()["system_prompt"]`, violating the CodingAgent invariant that it adds no default system prompt, and it gives siblings no ordered slot.

### Alternative 4: Exact-name lookup first, directory listing only as fallback
- What: check `root / "AGENTS.md"` exists, list only when absent.
- Why rejected: on Windows the exact lookup reports the lowercase file under the wrong name; one listing gives the same answer everywhere with the real name, at the cost of one `listdir` of the root.

### Alternative 5: Put the helper in `vidbyte/context/`
- What: treat the coding window as a context-layer template, like `vidbyte/tools/toolsets/coding.py` for tools.
- Why rejected: sibling loaders (setup commands) need process and tool code; the context layer importing the tools layer risks the cycle A006 forbids. The agents layer sits above both.

### Alternative 6: A sorted list of loaders inside the window
- What: the window owns the loader list and calls each one.
- Why rejected: every sibling would then edit the window; with the enum order and a tuple in `CodingAgent.__init__`, a sibling adds one line and no file of this PR changes.
