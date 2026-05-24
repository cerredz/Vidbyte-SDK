# Design Doc: Context Management Foundation

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-24
**Last Updated:** 2026-05-24

---

## 1. Overview

This feature adds the foundation for a central context management abstraction in `vidbyte-sdk`: standardized context item dataclasses, a developer-facing `ContextManager` that stores and organizes those items, and integration points so agents and harness-facing code can receive managed context without each subsystem inventing its own shape. The first PR intentionally does not add dedicated renderer classes or compaction policies; it focuses on durable context storage, collection utilities, compatibility with existing `BaseContext.build_context()`, and public imports.

---

## 2. Goals & Non-Goals

### Goals

- Add standardized out-of-the-box context item dataclasses for common model-visible context units: files, git diffs, tasks, documents, environment state, memory, progress, artifacts, responses, and tool calls.
- Add a central `ContextManager` abstraction that stores context items, supports simple item utilities, preserves insertion order, and can produce a compatible `StrategyContext` / `BaseAgentContext` using the existing context dataclass layer.
- Let developers create custom context items easily through a generic `TextContextItem` and a small `ContextItem` protocol.
- Integrate context items and context managers into `BaseContext`, `StrategyContext`, `BaseAgent`, `AgentInput`, `AgentSpec`, and `AgentRuntime` without breaking existing callers.
- Add public re-exports through `vidbyte.context`, `vidbyte.lib.dataclasses`, and root `vidbyte` for common context management types.
- Add focused tests covering context item construction, manager operations, agent-level context propagation, per-call context propagation, and compatibility imports.
- Update README and SDK skill docs so future agents know this is the approved context-management foundation.

### Non-Goals

- No dedicated renderer abstraction in this PR. Existing `BaseContext.build_context()` remains the only prompt-text formatting path.
- No context compaction rules, ranking algorithms, token-budget pruning, summarization, redaction policies, or relevance scoring in this PR.
- No model/provider-specific message rendering.
- No file tree crawling, git subprocess invocation, workspace scanning, or live environment source collection in this PR.
- No changes to `vidbyte.pipelines`; pipelines remain string-in/string-out and must not manage context, budget, artifacts, or item objects.
- No persistent context store, database layer, or remote service integration.

---

## 3. Background & Context

The repo already has a context layer centered on `vidbyte/lib/dataclasses/context.py`. It defines `BaseContext`, `StrategyContext`, `BaseAgentContext`, `ContextBudget`, `ContextPermissions`, `ContextToolCall`, `ContextResponse`, `ContextArtifact`, `ProgressLog`, and `build_context()`. Public context re-exports live in `vidbyte/context/__init__.py`, while root convenience exports live in `vidbyte/__init__.py`.

Agent execution already builds a `BaseAgentContext` through `AgentRuntime.build_context(...)`. `BaseAgent.generate_reply(...)` normalizes input, resolves modality, builds agent context, and passes that context to either a strategy or direct runner loop. The current runtime preserves system prompt, history, file paths, tools, and budget, but drops many richer `BaseContext` fields such as metadata, tool calls, responses, artifacts, memory, permissions, and strategy metadata. Existing tests intentionally assert some of this narrow behavior, so this feature must update those tests alongside the new contract.

The SDK skill docs establish several important constraints: public context objects belong in `vidbyte/context/`, shared dataclasses belong under `vidbyte/lib/dataclasses/`, and pipelines must remain string-only. Existing docs also reserve compaction as either a built-in tool (`ContextCompactionTool`) or future runtime capability, but the user explicitly asked to defer rendering and compaction to a later PR.

This feature therefore adds a structural foundation, not the full context-window compiler. It standardizes what "a piece of context" is and how agents accept it. Later PRs can add rich renderers and compaction policies on top of these stable item contracts.

---

## 4. Requirements

### Functional Requirements

1. The SDK must expose a `ContextItem` protocol for objects that can be converted into existing context dataclass fields.
2. The SDK must expose a generic `TextContextItem` for simple custom context pieces.
3. The SDK must expose out-of-the-box item dataclasses: `FileContextItem`, `GitDiffContextItem`, `TaskContextItem`, `DocumentContextItem`, `EnvironmentContextItem`, `MemoryContextItem`, `ProgressContextItem`, `ArtifactContextItem`, `ResponseContextItem`, and `ToolCallContextItem`.
4. Context item dataclasses must be immutable with `frozen=True, slots=True` to match existing dataclass style.
5. `FileContextItem.from_path(...)` must create a file item from an explicit path without doing workspace crawling.
6. `FileContextItem.from_path(...)` must optionally include file text and must store path, absolute path, file size, language hint, and metadata.
7. `ContextManager` must preserve deterministic insertion order.
8. `ContextManager` must support `add(...)`, `extend(...)`, `remove(...)`, `clear(...)`, `items()`, `by_kind(...)`, and `to_context(...)`.
9. `ContextManager` must accept context items at construction time.
10. `ContextManager.to_context(...)` must produce a `StrategyContext` by merging manager-owned items with optional base context fields.
11. `ContextManager` must bridge standardized items into existing `BaseContext` fields: files into `file_paths` / `ContextArtifact`, tasks/progress into metadata or artifacts, documents into artifacts, memory into `memory`, responses into `responses`, tool calls into `tool_calls`, and generic text into artifacts or metadata.
12. `BaseContext` must gain a `context_items` field while preserving all existing constructor call sites.
13. `BaseContext.build_context()` must include `context_items` through the compatibility bridge, without introducing a new renderer class.
14. `AgentInput` must accept `context_items` and `context_manager` as explicit fields rather than requiring metadata-only plumbing.
15. `AgentSpec` must accept default `context_items` and `context_manager` construction metadata.
16. `BaseAgent.__init__` must accept default `context_items` and `context_manager`.
17. `BaseAgent.fork(...)` must preserve default context items and context manager unless explicitly overridden.
18. `BaseAgent.generate_reply(...)` must merge agent-level context items, input-level context items, and base context items into the runtime-built context.
19. `AgentRuntime.build_context(...)` must preserve richer base context fields while adding managed context items.
20. `Strategy` APIs must remain source compatible: strategies continue to receive `context=BaseAgentContext`.
21. Root exports and package-local exports must include the new stable context management types.
22. README and skill docs must document the approved foundation and explicitly state that rendering/compaction are deferred.

### Non-Functional Requirements

- Performance: item management must be in-memory and linear over the number of explicitly provided items; no implicit filesystem walking or git subprocess calls.
- Scalability: large item content can exist, but this PR does not prune or summarize it. Callers remain responsible for input size until future compaction.
- Security: file content is only read when the developer explicitly calls `FileContextItem.from_path(include_content=True)` or passes content directly. No automatic secret scanning or redaction is implemented in this PR.
- Reliability: missing files in `FileContextItem.from_path(...)` must raise ordinary filesystem exceptions at construction time rather than silently producing incomplete items.
- Observability: `ContextManager.to_context(...)` must preserve manager metadata so callers can inspect where context came from.
- Compatibility: existing `StrategyContext(...)`, `BaseAgent(...)`, and `AgentInput(...)` calls without context-management arguments must continue to work.

---

## 5. High-Level Design

The feature creates a small context-management foundation layered on the existing context dataclasses. The central new concept is `ContextItem`: an immutable, structured representation of one unit of context. The central manager stores these items, provides simple collection utilities, and converts them into the existing `StrategyContext` shape so existing agent and strategy code can continue to work.

The data flow is:

```text
Developer / AgentInput / BaseAgent
        |
        v
ContextItem instances + optional ContextManager
        |
        v
ContextManager.add/extend/to_context
        |
        v
StrategyContext / BaseAgentContext
        |
        v
Existing BaseContext.build_context()
        |
        v
Runner or Strategy
```

This PR deliberately uses the existing `BaseContext.build_context()` formatter as the final text path. It does not add `ContextRenderer`, `ContextRenderResult`, compaction policies, ranking policies, or token-budget pruning. Those are planned for a later PR, once stable item contracts and agent integration exist.

The main design decision is to keep context items data-shaped and manager-owned. Items store meaning and metadata; the manager owns organization and compatibility conversion; the existing context object owns final text formatting for now.

---

## 6. Detailed Design

### 6.1 Context Item Dataclasses

**File(s):** `vidbyte/lib/dataclasses/context_items.py`
**Type:** New file

#### What it does

Defines standardized, immutable context item dataclasses and a `ContextItem` protocol. These are the typed atoms that developers and SDK internals can pass around before rendering exists.

#### Interface / API

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ContextItem(Protocol):
    kind: str
    title: str
    metadata: Mapping[str, Any]

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class TextContextItem:
    title: str
    content: str
    kind: str = "text"
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class FileContextItem:
    path: str
    absolute_path: str
    size_bytes: int
    content: str | None = None
    language: str | None = None
    excerpt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "file"
    title: str = "File"

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        include_content: bool = False,
        language: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        encoding: str = "utf-8",
    ) -> "FileContextItem": ...

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class GitDiffContextItem:
    diff: str
    files: tuple[str, ...] = ()
    repo_root: str | None = None
    branch: str | None = None
    base_ref: str | None = None
    head_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "git_diff"
    title: str = "Git Diff"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class TaskContextItem:
    goal: str
    status: str = "pending"
    progress: str | None = None
    completed: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    deterministic_checks: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "task"
    title: str = "Task"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class DocumentContextItem:
    source: str
    content: str
    title: str = "Document"
    document_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "document"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class EnvironmentContextItem:
    os_name: str | None = None
    cwd: str | None = None
    shell: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "environment"
    title: str = "Environment"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class MemoryContextItem:
    content: str
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "memory"
    title: str = "Memory"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ProgressContextItem:
    completed_tasks: tuple[str, ...] = ()
    touched_files: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "progress"
    title: str = "Progress"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ArtifactContextItem:
    name: str
    content: str
    artifact_type: str = "text"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "artifact"
    title: str = "Artifact"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ResponseContextItem:
    content: str
    sender: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "response"
    title: str = "Response"

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ToolCallContextItem:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    output: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "tool_call"
    title: str = "Tool Call"

    def to_context_text(self) -> str: ...
```

#### Logic / Algorithm

1. Keep each dataclass immutable and self-contained.
2. Implement `to_context_text()` with compact plain-text output only for compatibility with existing `BaseContext` artifacts.
3. `FileContextItem.from_path(...)` resolves the absolute path, stats the file, optionally reads UTF-8 text, and returns a structured item.
4. No item performs background discovery, traversal, ranking, redaction, or compaction.

#### Edge Cases & Error Handling

- `FileContextItem.from_path(...)` raises `FileNotFoundError`, `PermissionError`, or `UnicodeDecodeError` normally when explicit file access fails.
- Empty content is allowed because empty files/documents can be meaningful context.
- Metadata is accepted as a mapping and copied by callers only where needed; this mirrors existing dataclass style.

---

### 6.2 Context Manager

**File(s):** `vidbyte/context/manager.py`
**Type:** New file

#### What it does

Defines the central `ContextManager` abstraction. It owns a deterministic collection of context items and converts them into existing context dataclass fields.

#### Interface / API

```python
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.dataclasses.context import BaseContext, StrategyContext
from vidbyte.lib.dataclasses.context_items import ContextItem


@dataclass(slots=True)
class ContextManager:
    context_items: Sequence[ContextItem] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def add(self, item: ContextItem) -> "ContextManager": ...
    def extend(self, items: Iterable[ContextItem]) -> "ContextManager": ...
    def remove(self, item: ContextItem) -> "ContextManager": ...
    def clear(self) -> "ContextManager": ...
    def items(self) -> tuple[ContextItem, ...]: ...
    def by_kind(self, kind: str) -> tuple[ContextItem, ...]: ...
    def to_context(self, base_context: BaseContext | None = None, **overrides: Any) -> StrategyContext: ...
```

#### Logic / Algorithm

1. Store items internally as a tuple to preserve order and avoid accidental caller mutation.
2. `add`, `extend`, `remove`, and `clear` mutate the manager instance and return `self`, matching simple SDK builder-style ergonomics.
3. `items()` returns a tuple snapshot.
4. `by_kind(kind)` filters items by their `kind` attribute.
5. `to_context(...)` starts from an optional base context, applies overrides, and converts known item types into the current `StrategyContext` fields.
6. Unknown protocol-compatible items become `ContextArtifact(name=item.title, content=item.to_context_text(), artifact_type=item.kind, metadata=item.metadata)`.
7. The resulting `StrategyContext.context_items` contains all original items for future renderer/compaction PRs.

#### Edge Cases & Error Handling

- `remove(item)` raises `ValueError` if the item is not present, matching tuple/list semantics.
- `to_context(...)` accepts no manager-wide compaction or render options in this PR.
- Unknown item implementations must provide `kind`, `title`, `metadata`, and `to_context_text()` or they will fail structurally when used.

---

### 6.3 Existing Context Dataclasses

**File(s):** `vidbyte/lib/dataclasses/context.py`
**Type:** Modified

#### What it does

Extends `BaseContext` with a `context_items` field and bridges those items into existing `build_context()` behavior.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class BaseContext:
    ...
    context_items: Sequence[ContextItem] = ()

    def build_context(self) -> str: ...
```

#### Logic / Algorithm

1. Import `ContextItem` for type annotations.
2. Add `context_items: Sequence[ContextItem] = ()`.
3. In `build_context()`, after existing structured fields, include a compatibility section for `context_items` by calling `item.to_context_text()`.
4. Preserve all existing field names and default behavior.

#### Edge Cases & Error Handling

- If an item has malformed `to_context_text()`, the exception propagates. This is acceptable for custom developer items in the foundation PR.
- Existing contexts without items render exactly as before except for any intentional runtime propagation test updates.

---

### 6.4 Public Context Exports

**File(s):** `vidbyte/context/__init__.py`, `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes stable context management types importable from the public context package, central dataclass package, and root convenience namespace.

#### Interface / API

```python
from vidbyte.context import ContextManager, FileContextItem, TaskContextItem
from vidbyte.lib.dataclasses import ContextItem, TextContextItem
from vidbyte import ContextManager, DocumentContextItem
```

#### Logic / Algorithm

1. Re-export all new dataclasses and `ContextManager`.
2. Keep `__all__` sorted consistently with existing style.
3. Avoid exporting future renderer/compaction names.

#### Edge Cases & Error Handling

- N/A - export-only changes.

---

### 6.5 Agent Dataclasses

**File(s):** `vidbyte/lib/dataclasses/agents.py`, `vidbyte/agents/types.py`
**Type:** Modified

#### What it does

Adds explicit context-management fields to agent-facing input/spec dataclasses so developers do not have to smuggle context through metadata.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AgentInput:
    prompt: str
    modality: ModelModality | str = ModelModality.AUTO
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None


@dataclass(frozen=True, slots=True)
class AgentSpec:
    name: str
    system_prompt: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None
```

#### Logic / Algorithm

1. Add optional fields with defaults at the end of each dataclass to preserve positional compatibility.
2. Use tuple defaults for item sequences.
3. Re-export unchanged from `vidbyte.agents.types`.

#### Edge Cases & Error Handling

- Existing `AgentInput("prompt")` calls remain valid.
- Existing `AgentInput(prompt, modality, metadata)` positional calls remain valid because new fields are appended.

---

### 6.6 BaseAgent Integration

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Allows agents to carry default context items or a context manager and merge those defaults with per-call context.

#### Interface / API

```python
class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        ...
        context_items: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
        ...
    ) -> None: ...

    def fork(
        self,
        *,
        ...
        context_items: Sequence[ContextItem] | None = None,
        context_manager: ContextManager | None = None,
    ) -> BaseAgent: ...
```

#### Logic / Algorithm

1. Store `self.context_items` as a tuple.
2. Store `self.context_manager` as provided or create a manager from `context_items` only when needed.
3. `_normalize_input(...)` returns prompt, modality, metadata, input context items, and input context manager.
4. `_build_context(...)` receives input-level items/managers and passes them to `AgentRuntime.build_context(...)`.
5. `fork(...)` preserves or overrides context settings.
6. `card()` may include a lightweight `context_item_count` metadata value, but must not expose full context item content.

#### Edge Cases & Error Handling

- Agent-level context and per-call context are merged for the single run only.
- Per-call context does not mutate the agent's default context.
- If both a manager and items are supplied, items are appended after manager items to preserve explicit call ordering.

---

### 6.7 AgentRuntime Integration

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Uses `ContextManager` as the central assembly path when building `BaseAgentContext`.

#### Interface / API

```python
def build_context(
    self,
    message: str,
    *,
    base_context: StrategyContext | None,
    history: Sequence[AgentMessage],
    agent_history: Sequence[AgentMessage],
    agent_metadata: Mapping[str, Any],
    existing_tool_calls: Sequence[ToolCallContext],
    input_metadata: Mapping[str, Any] | None = None,
    modality: ModelModality | None = None,
    context_items: Sequence[ContextItem] = (),
    context_manager: ContextManager | None = None,
) -> BaseAgentContext: ...
```

#### Logic / Algorithm

1. Build a manager from base context items, agent/input items, and optional provided managers.
2. Preserve existing prompt wrapping through `append_agentic_loop_prompt(...)`.
3. Preserve existing history ordering: explicit history first, then agent history.
4. Preserve tools as `self.tools.specs()`.
5. Preserve base context fields: file paths, strategy metadata, tool calls, responses, budget, artifacts, memory, permissions, metadata, and context items.
6. Merge metadata in deterministic order: base context metadata, agent metadata, input metadata, runtime-derived metadata.
7. Return `BaseAgentContext`, not a new context class.

#### Edge Cases & Error Handling

- `message` remains unused by the first foundation implementation unless needed for metadata; no query-based ranking is added.
- Existing tool-call contexts are converted into context records where compatible, while runtime metadata still records live tool calls separately.
- The agentic-loop prompt remains applied exactly once.

---

### 6.8 Harness Client Documentation Surface

**File(s):** `vidbyte/harnesses/client.py`, `README.md`
**Type:** Modified

#### What it does

Keeps harnesses minimal but documents that custom harnesses should accept a `ContextManager` rather than adding many context flags.

#### Interface / API

```python
# No new concrete harness factory is required in this PR.
```

#### Logic / Algorithm

1. Add docstring/comment guidance to `HarnessClient` if appropriate.
2. Document recommended harness composition in README.

#### Edge Cases & Error Handling

- N/A - no executable harness behavior changes are planned.

---

### 6.9 Documentation And Skill Updates

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`, `skills/vidbyte-sdk-doc/SKILL.md`
**Type:** Modified

#### What it does

Documents the context-management foundation and repository guardrails.

#### Interface / API

```python
from vidbyte import Agent, ContextManager, FileContextItem, TaskContextItem

agent = Agent(
    name="coder",
    system_prompt="Work carefully.",
    context_items=[TaskContextItem(goal="Fix failing tests")],
)
```

#### Logic / Algorithm

1. README adds a short "Context Management" section after existing context objects.
2. `skills/vidbyte-sdk/SKILL.md` updates layout and rules for context items/manager.
3. `skills/vidbyte-sdk-doc/SKILL.md` updates package map, public import surface, context/dataclass section, and playbooks.

#### Edge Cases & Error Handling

- Docs must explicitly say rich rendering and compaction policies are deferred.

---

## 7. Data Model Changes

### 7.1 ContextItem Protocol

**Change type:** New

```python
@runtime_checkable
class ContextItem(Protocol):
    kind: str
    title: str
    metadata: Mapping[str, Any]

    def to_context_text(self) -> str: ...
```

**Migration strategy:** N/A - new optional protocol.

---

### 7.2 Standard Context Item Dataclasses

**Change type:** New

```python
TextContextItem
FileContextItem
GitDiffContextItem
TaskContextItem
DocumentContextItem
EnvironmentContextItem
MemoryContextItem
ProgressContextItem
ArtifactContextItem
ResponseContextItem
ToolCallContextItem
```

**Migration strategy:** N/A - new optional dataclasses.

---

### 7.3 BaseContext.context_items

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class BaseContext:
    ...
    context_items: Sequence[ContextItem] = ()
```

**Migration strategy:** Forward migration is automatic because the field has a default. Rollback removes the optional field and new tests/imports.

---

### 7.4 AgentInput And AgentSpec Context Fields

**Change type:** Modified

```python
context_items: tuple[ContextItem, ...] = ()
context_manager: ContextManager | None = None
```

**Migration strategy:** Forward migration is automatic because fields are appended with defaults. Rollback removes these optional fields and associated agent plumbing.

---

## 8. API Changes

### 8.1 Python SDK Public Imports

**Change type:** New

**Request:**

```python
from vidbyte import ContextManager, FileContextItem, TaskContextItem
```

**Response:**

```python
manager = ContextManager([TaskContextItem(goal="Implement feature")])
context = manager.to_context()
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python import/API surface only; errors are normal Python exceptions |

---

### 8.2 Agent Construction Context

**Change type:** Modified

**Request:**

```python
agent = Agent(
    name="coder",
    system_prompt="Work carefully.",
    context_items=[TaskContextItem(goal="Fix failing tests")],
)
```

**Response:**

```python
reply = await agent.arun("Continue")
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid item objects fail structurally when the manager tries to use them |

---

### 8.3 AgentInput Per-Call Context

**Change type:** Modified

**Request:**

```python
reply = await agent.arun(
    AgentInput(
        "Review this change",
        context_items=[FileContextItem.from_path("README.md", include_content=True)],
    )
)
```

**Response:**

```python
reply.content
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | File construction errors are raised before the agent call |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-management-foundation.md` | Approved design doc for this feature |
| CREATE | `vidbyte/lib/dataclasses/context_items.py` | Standardized context item dataclasses and protocol |
| CREATE | `vidbyte/context/manager.py` | Central `ContextManager` abstraction |
| CREATE | `tests/test_context_management.py` | Unit tests for items, manager, exports, and context bridging |
| MODIFY | `vidbyte/lib/dataclasses/context.py` | Add `context_items` to `BaseContext` and compatibility rendering through existing `build_context()` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add context item/manager fields to `AgentInput` and `AgentSpec` |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Re-export new context item dataclasses |
| MODIFY | `vidbyte/context/__init__.py` | Re-export `ContextManager` and context item dataclasses |
| MODIFY | `vidbyte/agents/base.py` | Accept default context items/manager and merge per-call context |
| MODIFY | `vidbyte/agents/runtime.py` | Build `BaseAgentContext` through the new context manager foundation |
| MODIFY | `vidbyte/__init__.py` | Add root convenience exports |
| MODIFY | `tests/test_context_dataclasses.py` | Cover `context_items` compatibility in existing context build behavior |
| MODIFY | `tests/test_agent_base.py` | Cover agent default and per-call context propagation |
| MODIFY | `tests/test_agent_runtime.py` | Update context-building expectations for richer preserved fields |
| MODIFY | `README.md` | Document context management foundation usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update SDK structure/rules for context manager and items |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Update repository reference skill for new context management surface |

---

## 10. Testing Plan

### Unit Tests

- `tests/test_context_management.py` -> `test_text_context_item_renders_plain_text`: verifies generic custom item text shape.
- `tests/test_context_management.py` -> `test_file_context_item_from_path_without_content`: verifies path, absolute path, size, and absent content.
- `tests/test_context_management.py` -> `test_file_context_item_from_path_with_content`: verifies explicit content loading.
- `tests/test_context_management.py` -> `test_context_manager_preserves_order`: verifies deterministic item ordering.
- `tests/test_context_management.py` -> `test_context_manager_filters_by_kind`: verifies `by_kind(...)`.
- `tests/test_context_management.py` -> `test_context_manager_to_context_bridges_standard_items`: verifies tasks/documents/files/memory/responses/tool calls become compatible `StrategyContext` fields.
- `tests/test_context_management.py` -> `test_context_manager_merges_base_context`: verifies base context fields are preserved and item-derived fields are appended.
- `tests/test_context_management.py` -> `test_public_imports`: verifies imports from `vidbyte`, `vidbyte.context`, and `vidbyte.lib.dataclasses`.
- `tests/test_context_dataclasses.py` -> add coverage that `BaseContext(context_items=[...]).build_context()` includes item text through the compatibility path.
- `tests/test_agent_base.py` -> add coverage that `BaseAgent(context_items=[...])` passes items into strategy context.
- `tests/test_agent_base.py` -> add coverage that `AgentInput(context_items=[...])` passes per-call items without mutating agent defaults.
- `tests/test_agent_runtime.py` -> update context construction test to expect metadata, strategy metadata, existing tool calls, memory/artifacts/responses/permissions, and context items to be preserved.

### Integration Tests

- Use existing fake strategies/runners in `tests/test_agent_base.py` and `tests/test_agent_runtime.py`; no real provider or network dependency.
- Run `python -m unittest tests.test_context_management tests.test_context_dataclasses tests.test_agent_base tests.test_agent_runtime`.
- Run full test discovery before handoff: `python -m unittest discover -s tests`.

### Manual / QA Test Cases

1. Create `ContextManager([TaskContextItem(goal="x")])`, call `to_context().build_context()`, and verify task text appears.
2. Create an `Agent` with default `TaskContextItem`, run it with a fake strategy, and verify the strategy receives a `BaseAgentContext` containing the item.
3. Create an `AgentInput` with a `FileContextItem`, run it with a fake strategy, and verify the agent default items are unchanged after the call.
4. Import `ContextManager`, `FileContextItem`, and `TaskContextItem` from root `vidbyte`.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `dataclasses`, `pathlib`, `typing` | Python >=3.11 | Context item contracts and explicit file item construction | Low |
| Existing `pydantic>=2,<3` | Existing runtime dependency | N/A - no new use in this feature | None |

---

## 12. Rollout & Deployment

- No feature flag is needed; this is an additive SDK API.
- This is not intended to be a breaking change because all new constructor fields have defaults.
- Deployment is normal package release after tests pass.
- Rollback procedure: remove new context item/manager files, remove export additions, remove agent/context dataclass fields, and revert tests/docs in the manifest.
- Later PR rollout path: add dedicated renderers, render diagnostics, compaction policies, ranking/redaction transforms, and optional source collectors on top of `ContextItem` and `ContextManager`.

---

## 13. Open Questions

- [ ] Should `ContextManager.add(...)` mutate and return `self`, or return a new manager? The proposed implementation mutates for ergonomic builder-style usage, while the context item dataclasses remain immutable.
- [ ] Should `BaseAgent.card()` expose `context_item_count` in metadata, or avoid mentioning context entirely? The proposed implementation allows only count metadata, never content.
- [ ] Should `ContextManager.to_context(...)` return `StrategyContext` always, or preserve the input context subclass when passed a `BaseAgentContext`? The proposed implementation returns `StrategyContext`; `AgentRuntime` wraps that into `BaseAgentContext`.
- [ ] Should `FileContextItem.from_path(include_content=True)` reject binary-looking files? The proposed implementation uses normal text decoding and lets `UnicodeDecodeError` surface.

---

## 14. Alternatives Considered

### Alternative 1: Add Rich Renderers In The First PR

- What: Introduce `ContextRenderer`, XML/Markdown renderers, render diagnostics, ordering policies, and item-specific render strategies immediately.
- Why rejected: The user explicitly asked to defer rendered behavior and compaction to the next PR. Adding renderers now would make the foundation harder to review and blur the contract between stored context and prompt formatting.

### Alternative 2: Put Context Management Into Pipelines

- What: Extend pipeline stages to pass `ContextManager` or `ContextBundle` objects instead of plain strings.
- Why rejected: Repo skills and pipeline docs explicitly say pipelines move strings only and do not manage context, budgets, or artifacts. Context belongs at the agent/strategy/context layer.

### Alternative 3: Make Each Context Item Responsible For Loading, Ranking, Rendering, And Compaction

- What: Give every item type behavior-heavy methods for collection, formatting, summarization, and pruning.
- Why rejected: That would turn context items into miniature managers. The selected design keeps items data-shaped and centralizes management logic in `ContextManager`.

### Alternative 4: Store Context Items Only In Metadata

- What: Avoid new dataclass fields and pass everything through `metadata["context_items"]`.
- Why rejected: The user wants standardized first-class primitives. Metadata-only plumbing is less discoverable, harder to type, and easier for agents/runtimes to drop accidentally.

### Alternative 5: Implement Live Workspace/Git Sources Now

- What: Add sources that inspect OS, shell, git branch, git diffs, and workspace tree automatically.
- Why rejected: The user asked for the foundation and standardized items first. Live sources introduce IO policy, permissions, freshness, redaction, and platform edge cases better handled after the item/manager contracts are stable.
