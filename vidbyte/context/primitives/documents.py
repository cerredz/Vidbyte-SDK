"""FILE: vidbyte/context/primitives/documents.py

PURPOSE:
    Defines immutable text, file, diff, document, environment, and memory
    records that carry source material into a later context-window iteration.
ROLE IN CODEBASE:
    ContextManager renders these records, create-tool registry builders construct
    the create-enabled types, and vidbyte.context.primitives re-exports them.
ARCHITECTURE NOTE:
    Dataclasses own source-oriented field rendering while shared helpers add the
    managed-context boundary; filesystem reads are isolated to FileContextItem.
FUNCTION INVENTORY:
    TextContextItem, FileContextItem, GitDiffContextItem, DocumentContextItem,
    EnvironmentContextItem, and MemoryContextItem each render one record type.
COMMON MODIFICATION PATTERNS:
    Keep source metadata before body content, preserve excerpt fallback behavior,
    and retain TOOL_CREATE_META synchronization for create-enabled records.
WHAT NOT TO DO IN THIS FILE:
    Do not place records, mutate ContextManager state, or validate source truth;
    registry, placement, and caller-owned freshness belong elsewhere.
KNOWN EDGE CASES:
    File content may be absent in favor of an excerpt, environment values may be
    missing, and optional source metadata is omitted when empty.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/tree/main/vidbyte/context/primitives
TESTS:
    Existing context primitive registry tests plus source/package smoke gates cover
    imports, create-tool rendering, and context integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from vidbyte.context.primitives.base import _language_from_path, _with_context_intro


@dataclass(frozen=True, slots=True)
class TextContextItem:
    """Generic extension point for custom context primitives."""

    title: str
    content: str
    kind: str = "text"
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str | None = None
    primitive_frozen: bool = False

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "text",
        "tool_name": "context_create_text",
        "default_title": "Text",
        "description": (
            "context_create_text is the typed create tool for free-form TextContextItem entries "
            "in the managed context window registry. context_create_text does insert or overwrite "
            "a text primitive by primitive_id (with optional source attribution) so the agent can "
            "park arbitrary notes, policies, intermediate writing, or standing instructions that "
            "re-render into the ## Context Window Primitives zone on every subsequent loop iteration."
        ),
        "fields": {
            "content": {
                "type": "string",
                "required": True,
                "description": (
                    "content is the free-form body of the text primitive. content does become the "
                    "main prose shown when this primitive renders into the context window; put the "
                    "full note, policy, or intermediate text here rather than burying it in title."
                ),
            },
            "source": {
                "type": "string",
                "required": False,
                "description": (
                    "source is an optional attribution label for where the text came from. source does "
                    "record provenance (for example 'user', 'tool:search', or a document path) so the "
                    "model can trust and cite the note without changing the body."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders title, optional source, and content.
        source = f"\nSource: {self.source}" if self.source else ""
        lines = [
            "This primitive carries free-form text intended to remain available in the next context-window iteration. The title identifies the kind of note being preserved, while the optional source records where it came from. The content line contains the actual prose or instruction supplied by the caller. Read this as a text record whose meaning comes from its body rather than from structured task or evidence fields.",
            "",
            f"{self.title}{source}",
            self.content,
        ]
        return _with_context_intro("\n".join(lines))


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
    primitive_id: str | None = None
    primitive_frozen: bool = False

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        include_content: bool = False,
        language: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        encoding: str = "utf-8",
    ) -> FileContextItem:
        # Constructs a FileContextItem by reading filesystem metadata and optionally content.
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
        # Renders file path, language, and content or excerpt.
        lines = [
            "This primitive carries a file snapshot for code or document-oriented work. The path and absolute path identify the source location, and the size and language describe the captured file. The following content is either the full file body or the selected excerpt when full content is absent. Use this record to reason about source material, not as proof that the file still matches the live filesystem.",
            "",
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
        return _with_context_intro("\n".join(lines))


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
    primitive_id: str | None = None
    primitive_frozen: bool = False

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "git_diff",
        "tool_name": "context_create_git_diff",
        "default_title": "Git Diff",
        "description": (
            "context_create_git_diff is the typed create tool for GitDiffContextItem change-set "
            "snapshots in the managed context window registry. context_create_git_diff does insert "
            "or overwrite a git-diff primitive by primitive_id with the raw patch plus optional "
            "files/branch/range metadata so the agent can keep the exact code changes under "
            "review visible while planning or reviewing edits."
        ),
        "fields": {
            "diff": {
                "type": "string",
                "required": True,
                "description": (
                    "diff is the raw unified git patch text for the change set. diff does hold the "
                    "full +/- hunk content the model should reason over; paste the complete patch "
                    "rather than a high-level summary."
                ),
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": (
                    "files is the optional list of paths touched by the diff. files does give a "
                    "quick inventory of changed files so the model can scope review without parsing "
                    "every hunk header."
                ),
            },
            "repo_root": {
                "type": "string",
                "required": False,
                "description": (
                    "repo_root is an optional path or label for the repository root of this diff. "
                    "repo_root does situate the patch when multiple repos or worktrees are in play."
                ),
            },
            "branch": {
                "type": "string",
                "required": False,
                "description": (
                    "branch is the optional current branch name associated with the diff. branch does "
                    "label which line of development the patch belongs to."
                ),
            },
            "base_ref": {
                "type": "string",
                "required": False,
                "description": (
                    "base_ref is the optional starting ref (commit, branch, or tag) for the diff range. "
                    "base_ref does mark the left side of a base..head comparison."
                ),
            },
            "head_ref": {
                "type": "string",
                "required": False,
                "description": (
                    "head_ref is the optional ending ref for the diff range. head_ref does mark the "
                    "right side of a base..head comparison together with base_ref."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders repo context, range, changed files, and raw diff.
        lines = [
            "This primitive carries a repository change set for reviewing implementation state. Repository, branch, range, and file entries locate the change within version control. The diff section contains the textual modifications that a reviewer should inspect. Treat the diff as captured context whose freshness depends on the caller's snapshot time.",
            "",
            "Git diff:",
        ]
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
        return _with_context_intro("\n".join(lines))


@dataclass(frozen=True, slots=True)
class DocumentContextItem:
    """Structured reference document context."""

    source: str
    content: str
    title: str = "Document"
    document_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "document"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "document",
        "tool_name": "context_create_document",
        "default_title": "Document",
        "description": (
            "context_create_document is the typed create tool for reference DocumentContextItem "
            "entries in the managed context window registry. context_create_document does insert or "
            "overwrite a document primitive by primitive_id with a source label and full content so "
            "the agent can keep long-form reference material (specs, notes, retrieved passages) "
            "available across iterations without re-fetching it each turn."
        ),
        "fields": {
            "source": {
                "type": "string",
                "required": True,
                "description": (
                    "source is the origin label for the document (path, URL, or human label). source "
                    "does tell the model where the body came from so it can weigh authority and "
                    "re-open the original later if needed."
                ),
            },
            "content": {
                "type": "string",
                "required": True,
                "description": (
                    "content is the full document body to store. content does become the primary "
                    "reference text rendered into the context window for this primitive."
                ),
            },
            "document_id": {
                "type": "string",
                "required": False,
                "description": (
                    "document_id is an optional external identifier (ticket id, CMS id, hash, etc.). "
                    "document_id does link this context entry back to an upstream system without "
                    "replacing the registry primitive_id."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders document title, source, optional ID, and content.
        lines = [
            "This primitive carries a named document from an explicit source. The title, source, and optional document ID identify the reference before its body is shown. The content section contains the document text that later reasoning may quote or compare. Use the source metadata to distinguish this record from free-form notes or transient responses.",
            "",
            f"Document: {self.title}",
            f"Source: {self.source}",
        ]
        if self.document_id:
            lines.append(f"Document ID: {self.document_id}")
        lines.append("Content:")
        lines.append(self.content)
        return _with_context_intro("\n".join(lines))


@dataclass(frozen=True, slots=True)
class EnvironmentContextItem:
    """Structured environment state supplied by the caller."""

    os_name: str | None = None
    cwd: str | None = None
    shell: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "environment"
    title: str = "Environment"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "environment",
        "tool_name": "context_create_environment",
        "default_title": "Environment",
        "description": (
            "context_create_environment is the typed create tool for EnvironmentContextItem runtime "
            "snapshots in the managed context window registry. context_create_environment does insert "
            "or overwrite an environment primitive by primitive_id with OS, working directory, and "
            "shell facts so the agent can keep host assumptions visible while issuing shell or path "
            "sensitive tool calls."
        ),
        "fields": {
            "os_name": {
                "type": "string",
                "required": False,
                "description": (
                    "os_name is the optional operating system name or family (for example 'Windows', "
                    "'Linux', 'Darwin'). os_name does orient path separators, shell conventions, and "
                    "platform-specific commands."
                ),
            },
            "cwd": {
                "type": "string",
                "required": False,
                "description": (
                    "cwd is the optional current working directory path. cwd does anchor relative "
                    "paths and default locations for subsequent file or shell operations."
                ),
            },
            "shell": {
                "type": "string",
                "required": False,
                "description": (
                    "shell is the optional active shell name (for example 'bash', 'zsh', 'powershell'). "
                    "shell does guide command syntax and quoting choices in later tool calls."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders OS, working directory, and shell if set.
        lines = [
            "This primitive carries execution-environment context relevant to interpreting commands and paths. The following fields identify the operating system, current working directory, and shell when those values are known. Missing values mean the caller did not provide that detail, not that the environment has no such value. Use this record to qualify operational assumptions made from the other context.",
            "",
            "Environment:",
        ]
        if self.os_name:
            lines.append(f"OS: {self.os_name}")
        if self.cwd:
            lines.append(f"CWD: {self.cwd}")
        if self.shell:
            lines.append(f"Shell: {self.shell}")
        if len(lines) == 1:
            lines.append("N/A")
        return _with_context_intro("\n".join(lines))


@dataclass(frozen=True, slots=True)
class MemoryContextItem:
    """Structured memory summary context."""

    content: str
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "memory"
    title: str = "Memory"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    TOOL_CREATE_META: ClassVar[dict[str, Any]] = {
        "key": "memory",
        "tool_name": "context_create_memory",
        "default_title": "Memory",
        "description": (
            "context_create_memory is the typed create tool for MemoryContextItem durable summaries "
            "in the managed context window registry. context_create_memory does insert or overwrite a "
            "memory primitive by primitive_id so the agent can persist distilled facts, decisions, or "
            "user preferences that should survive across turns without replaying the full transcript."
        ),
        "fields": {
            "content": {
                "type": "string",
                "required": True,
                "description": (
                    "content is the memory summary body. content does store the compressed knowledge "
                    "the agent wants to keep online — write durable facts, not ephemeral scratch notes."
                ),
            },
            "source": {
                "type": "string",
                "required": False,
                "description": (
                    "source is an optional attribution for where the memory was derived. source does "
                    "record provenance (conversation turn, prior tool, external store) so the model "
                    "can re-validate or refresh the memory later."
                ),
            },
        },
    }

    def to_context_text(self) -> str:
        # Renders memory summary with optional source attribution.
        source = f"\nSource: {self.source}" if self.source else ""
        lines = [
            "This primitive carries a retained memory summary for later reasoning. The optional source identifies the origin of the memory, and the following body preserves the remembered content. A memory summary is durable context but is not independently verified by this renderer. Treat it as a clue to incorporate or validate rather than as a current observation.",
            "",
            f"Memory summary:{source}",
            self.content,
        ]
        return _with_context_intro("\n".join(lines))


__all__ = [
    "DocumentContextItem",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "MemoryContextItem",
    "TextContextItem",
]
