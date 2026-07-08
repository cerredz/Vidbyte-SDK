"""Context Protocol Header

Description:
    Defines the shared ContextItem protocol and rendering helpers for primitives.
Purpose:
    Gives every context primitive a common structural contract and the small
    formatting helpers they reuse when rendering compatibility text.
Architecture:
    - ContextItem: Structural protocol for context primitive implementations.
    - CREATE_TOOL_COMMON_FIELDS: Shared model-facing create-tool argument strings.
    - _extend_section / _truncate_text / _language_from_path: Shared helpers.
Relations:
    Imported by the concrete primitive modules in this package.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Shared create-tool argument strings consumed by the primitive create registry.
# Primitive-specific field strings live on each dataclass as TOOL_CREATE_META.
CREATE_TOOL_COMMON_FIELDS: dict[str, dict[str, Any]] = {
    "primitive_id": {
        "type": "string",
        "required": True,
        "description": (
            "primitive_id is the stable registry key for this context window primitive "
            "(for example 'plan:current' or 'doc:spec'). primitive_id does identify the "
            "slot the create tool writes to: reusing an existing id intentionally overwrites "
            "that primitive unless it is frozen."
        ),
    },
    "title": {
        "type": "string",
        "required": False,
        "description": (
            "title is an optional human-readable label shown next to the primitive in the "
            "rendered context window zone. title does control display naming only; it does "
            "not change the registry key (use primitive_id for identity)."
        ),
    },
    "placement": {
        "type": "string",
        "required": False,
        "enum": (
            "top_of_context",
            "end_of_context",
            "top_of_conversation",
            "end_of_conversation",
        ),
        "default": "end_of_context",
        "description": (
            "placement is where this primitive should render relative to other context and "
            "conversation content. placement does choose one of top_of_context, end_of_context, "
            "top_of_conversation, or end_of_conversation (default end_of_context) so the agent "
            "can prioritize what the model sees first on the next loop iteration."
        ),
    },
}


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
    if max_chars <= 0:
        return value
    if len(value) <= max_chars:
        return value
    suffix = "\n...[truncated]"
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)].rstrip() + suffix


def _language_from_path(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    return suffix or None


__all__ = ["CREATE_TOOL_COMMON_FIELDS", "ContextItem"]
