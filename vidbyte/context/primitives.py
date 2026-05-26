"""Context Protocol Header

Description:
    Defines public structured context primitives for context management.
Purpose:
    Gives developers standardized, immutable units of context that can be
    collected by a ContextManager and converted into existing SDK context objects.
Architecture:
    - ContextItem: Structural protocol for context primitive implementations.
    - Text/File/Git/Task/Document/Environment/Memory/Progress primitives.
    - Artifact/Response/ToolCall primitives for existing context records.
Relations:
    Used by vidbyte.context.manager and re-exported by vidbyte.context and
    vidbyte.lib.dataclasses for compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ContextItem(Protocol):
    """Structural protocol for context primitives managed by ContextManager."""

    kind: str
    title: str
    metadata: Mapping[str, Any]

    def to_context_text(self) -> str:
        """Return a compact compatibility rendering for BaseContext."""


ContextPrimitive = ContextItem


class ContextPrimitivePlacement(str, Enum):
    """Where a context primitive should be placed in the model-visible window."""

    STICKY = "sticky"
    NORMAL = "normal"
    EPHEMERAL = "ephemeral"


class ContextPrimitiveVisibility(str, Enum):
    """Whether a context primitive should be rendered into model-visible text."""

    MODEL = "model"
    METADATA_ONLY = "metadata_only"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class TextContextItem:
    """Generic extension point for custom context primitives."""

    title: str
    content: str
    kind: str = "text"
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        source = f"\nSource: {self.source}" if self.source else ""
        return f"{self.title}{source}\n{self.content}"


@dataclass(frozen=True, slots=True)
class FileContextItem:
    """Structured file context for explicit developer-supplied files."""

    path: str
    absolute_path: str
    size_bytes: int
    content: str | None = None
    language: str | None = None
    excerpt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "file"
    title: str = "File"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        include_content: bool = False,
        language: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        encoding: str = "utf-8",
    ) -> "FileContextItem":
        resolved = Path(path).resolve()
        content = resolved.read_text(encoding=encoding) if include_content else None
        return cls(
            path=str(path),
            absolute_path=str(resolved),
            size_bytes=resolved.stat().st_size,
            content=content,
            language=language or _language_from_path(resolved),
            metadata=dict(metadata or {}),
        )

    def to_context_text(self) -> str:
        lines = [
            f"File: {self.path}",
            f"Absolute path: {self.absolute_path}",
            f"Size bytes: {self.size_bytes}",
        ]
        if self.language:
            lines.append(f"Language: {self.language}")
        body = self.content if self.content is not None else self.excerpt
        if body is not None:
            lines.append("Content:")
            lines.append(body)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class GitDiffContextItem:
    """Structured git diff context supplied by a caller."""

    diff: str
    files: tuple[str, ...] = ()
    repo_root: str | None = None
    branch: str | None = None
    base_ref: str | None = None
    head_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "git_diff"
    title: str = "Git Diff"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        lines = ["Git diff:"]
        if self.repo_root:
            lines.append(f"Repo root: {self.repo_root}")
        if self.branch:
            lines.append(f"Branch: {self.branch}")
        if self.base_ref or self.head_ref:
            lines.append(f"Range: {self.base_ref or ''}..{self.head_ref or ''}")
        if self.files:
            lines.append("Files:")
            lines.extend(f"- {file}" for file in self.files)
        lines.append("Diff:")
        lines.append(self.diff)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class TaskContextItem:
    """Structured task context for goal, progress, and deterministic checks."""

    goal: str
    status: str = "pending"
    progress: str | None = None
    completed: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    deterministic_checks: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "task"
    title: str = "Task"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 10
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        lines = [f"Task goal: {self.goal}", f"Status: {self.status}"]
        if self.progress:
            lines.append(f"Progress: {self.progress}")
        _extend_section(lines, "Completed", self.completed)
        _extend_section(lines, "Next steps", self.next_steps)
        _extend_section(lines, "Deterministic checks", self.deterministic_checks)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class DocumentContextItem:
    """Structured reference document context."""

    source: str
    content: str
    title: str = "Document"
    document_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "document"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        lines = [f"Document: {self.title}", f"Source: {self.source}"]
        if self.document_id:
            lines.append(f"Document ID: {self.document_id}")
        lines.append("Content:")
        lines.append(self.content)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class EnvironmentContextItem:
    """Structured environment state supplied by the caller."""

    os_name: str | None = None
    cwd: str | None = None
    shell: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "environment"
    title: str = "Environment"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        lines = ["Environment:"]
        if self.os_name:
            lines.append(f"OS: {self.os_name}")
        if self.cwd:
            lines.append(f"CWD: {self.cwd}")
        if self.shell:
            lines.append(f"Shell: {self.shell}")
        if len(lines) == 1:
            lines.append("N/A")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class MemoryContextItem:
    """Structured memory summary context."""

    content: str
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "memory"
    title: str = "Memory"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 30
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        source = f"\nSource: {self.source}" if self.source else ""
        return f"Memory summary:{source}\n{self.content}"


@dataclass(frozen=True, slots=True)
class ProgressContextItem:
    """Structured progress context mirroring ProgressLog fields."""

    completed_tasks: tuple[str, ...] = ()
    touched_files: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "progress"
    title: str = "Progress"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 40
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        lines: list[str] = ["Progress:"]
        _extend_section(lines, "Completed tasks", self.completed_tasks)
        _extend_section(lines, "Touched files", self.touched_files)
        _extend_section(lines, "Decisions", self.decisions)
        _extend_section(lines, "Errors", self.errors)
        _extend_section(lines, "Next steps", self.next_steps)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ArtifactContextItem:
    """Structured artifact context compatible with ContextArtifact."""

    name: str
    content: str
    artifact_type: str = "text"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "artifact"
    title: str = "Artifact"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        return f"{self.name} ({self.artifact_type}):\n{self.content}"


@dataclass(frozen=True, slots=True)
class ResponseContextItem:
    """Structured model or agent response context."""

    content: str
    sender: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "response"
    title: str = "Response"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        prefix = f"Response from {self.sender}:" if self.sender else "Response:"
        return f"{prefix}\n{self.content}"


@dataclass(frozen=True, slots=True)
class ToolCallContextItem:
    """Structured tool-call context compatible with ContextToolCall."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    output: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "tool_call"
    title: str = "Tool Call"
    id: str | None = None
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.EPHEMERAL
    priority: int = 100
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        return f"Tool call: {self.name}\nArguments: {dict(self.arguments)}\nOutput: {self.output}"


@dataclass(frozen=True, slots=True)
class IdentityContextItem:
    """Role and behavior context below the system prompt authority level."""

    role: str
    behavior: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    personality: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "identity"
    title: str = "Identity"
    id: str | None = "identity:agent"
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 0
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        lines = [
            "Identity context (lower authority than the system prompt):",
            f"Role: {self.role}",
        ]
        _extend_section(lines, "Behavior", self.behavior)
        _extend_section(lines, "Constraints", self.constraints)
        if self.personality:
            lines.append(f"Personality: {self.personality}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PlanContextItem:
    """Durable plan context made visible across agent iterations."""

    objective: str
    steps: tuple[str, ...] = ()
    current_step: str | None = None
    risks: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "plan"
    title: str = "Plan"
    id: str | None = "plan:current"
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 20
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str:
        lines = [f"Plan objective: {self.objective}"]
        if self.current_step:
            lines.append(f"Current step: {self.current_step}")
        _extend_section(lines, "Steps", self.steps)
        _extend_section(lines, "Risks", self.risks)
        _extend_section(lines, "Verification", self.verification)
        return "\n".join(lines)


def context_primitive_id(item: ContextItem) -> str:
    """Return an explicit or derived stable ID for a context primitive."""
    explicit = getattr(item, "id", None)
    if explicit:
        return str(explicit)
    kind = str(getattr(item, "kind", type(item).__name__))
    if isinstance(item, FileContextItem):
        return f"file:{item.path}"
    if isinstance(item, TaskContextItem):
        return f"task:{item.goal}"
    if isinstance(item, PlanContextItem):
        return "plan:current"
    if isinstance(item, IdentityContextItem):
        return "identity:agent"
    title = str(getattr(item, "title", type(item).__name__))
    return f"{kind}:{title}"


def context_primitive_placement(item: ContextItem) -> ContextPrimitivePlacement:
    """Coerce an item's placement metadata into an enum value."""
    value = getattr(item, "placement", ContextPrimitivePlacement.NORMAL)
    return value if isinstance(value, ContextPrimitivePlacement) else ContextPrimitivePlacement(str(value))


def context_primitive_priority(item: ContextItem) -> int:
    """Return the numeric priority for deterministic primitive ordering."""
    return int(getattr(item, "priority", 100))


def context_primitive_visibility(item: ContextItem) -> ContextPrimitiveVisibility:
    """Coerce an item's visibility metadata into an enum value."""
    value = getattr(item, "visibility", ContextPrimitiveVisibility.MODEL)
    return value if isinstance(value, ContextPrimitiveVisibility) else ContextPrimitiveVisibility(str(value))


def sort_context_primitives(items: tuple[ContextItem, ...]) -> tuple[ContextItem, ...]:
    """Sort context primitives by placement, priority, and stable ID."""
    placement_rank = {
        ContextPrimitivePlacement.STICKY: 0,
        ContextPrimitivePlacement.NORMAL: 1,
        ContextPrimitivePlacement.EPHEMERAL: 2,
    }
    return tuple(
        sorted(
            items,
            key=lambda item: (
                placement_rank[context_primitive_placement(item)],
                context_primitive_priority(item),
                context_primitive_id(item),
            ),
        )
    )


def _extend_section(lines: list[str], title: str, values: tuple[str, ...]) -> None:
    if not values:
        return
    lines.append(f"{title}:")
    lines.extend(f"- {value}" for value in values)


def _language_from_path(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    return suffix or None


__all__ = [
    "ArtifactContextItem",
    "ContextItem",
    "ContextPrimitive",
    "ContextPrimitivePlacement",
    "ContextPrimitiveVisibility",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "IdentityContextItem",
    "MemoryContextItem",
    "PlanContextItem",
    "ProgressContextItem",
    "ResponseContextItem",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
    "context_primitive_id",
    "context_primitive_placement",
    "context_primitive_priority",
    "context_primitive_visibility",
    "sort_context_primitives",
]
