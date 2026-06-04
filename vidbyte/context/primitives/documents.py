"""Context Protocol Header

Description:
    Defines document- and environment-style context primitives.
Purpose:
    Gives developers immutable units of textual context such as raw text, files,
    git diffs, reference documents, environment state, and memory summaries.
Architecture:
    - Text/File/GitDiff/Document/Environment/Memory context primitives.
Relations:
    Re-exported through vidbyte.context.primitives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidbyte.context.primitives.base import _language_from_path


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

    def to_context_text(self) -> str:
        # Renders title, optional source, and content.
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
    ) -> "FileContextItem":
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
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders repo context, range, changed files, and raw diff.
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

    def to_context_text(self) -> str:
        # Renders document title, source, optional ID, and content.
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
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders OS, working directory, and shell if set.
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
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders memory summary with optional source attribution.
        source = f"\nSource: {self.source}" if self.source else ""
        return f"Memory summary:{source}\n{self.content}"


__all__ = [
    "DocumentContextItem",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "MemoryContextItem",
    "TextContextItem",
]
