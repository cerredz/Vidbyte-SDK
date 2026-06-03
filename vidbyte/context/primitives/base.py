"""Context Protocol Header

Description:
    Defines the shared ContextItem protocol and rendering helpers for primitives.
Purpose:
    Gives every context primitive a common structural contract and the small
    formatting helpers they reuse when rendering compatibility text.
Architecture:
    - ContextItem: Structural protocol for context primitive implementations.
    - _extend_section / _truncate_text / _language_from_path: Shared helpers.
Relations:
    Imported by the concrete primitive modules in this package.
"""

from __future__ import annotations

from collections.abc import Mapping
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


def _extend_section(lines: list[str], title: str, values: tuple[str, ...]) -> None:
    if not values:
        return
    lines.append(f"{title}:")
    lines.extend(f"- {value}" for value in values)


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    suffix = "\n...[truncated]"
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)].rstrip() + suffix


def _language_from_path(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    return suffix or None


__all__ = ["ContextItem"]
