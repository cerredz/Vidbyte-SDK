"""Context Protocol Header

Description:
    Defines the base Handoff context primitive.
Purpose:
    Provides a sectioned document object that works as a ContextItem, a handoff
    generation spec, and a filled handoff artifact.
Architecture:
    - Handoff: Base sectioned document primitive with rendering, schema, and fill helpers.
Relations:
    Consumed by vidbyte.agents.handoff.HandoffAgent and re-exported through vidbyte.context.
Similar Files:
    - vidbyte/context/primitives.py: Other standard context item primitives.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class Handoff:
    """Sectioned handoff document that doubles as a ContextItem primitive and HandoffAgent spec."""

    DEFAULT_TITLE: str = "Handoff"
    DEFAULT_INSTRUCTIONS: str = ""

    def __init__(self, *, sections: Mapping[str, str] | None = None, title: str | None = None, instructions: str | None = None, metadata: Mapping[str, Any] | None = None, primitive_id: str | None = None, primitive_frozen: bool = False) -> None:
        self.sections: dict[str, str] = dict(sections) if sections is not None else self.default_sections()
        self.title: str = title if title is not None else self.DEFAULT_TITLE
        self.instructions: str = instructions if instructions is not None else self.DEFAULT_INSTRUCTIONS
        self.kind: str = "handoff"
        self.metadata: dict[str, Any] = dict(metadata or {})
        self.primitive_id: str | None = primitive_id
        self.primitive_frozen: bool = primitive_frozen

    def default_sections(self) -> dict[str, str]:
        """Return the default section map for this handoff variant."""
        return {}

    def to_context_text(self) -> str:
        """Render the handoff as markdown text for context injection."""
        head = self.title if not self.instructions else f"{self.title}\n{self.instructions}"
        if not self.sections:
            return head
        body = "\n\n".join(f"## {title}\n{self._coerce(value)}" for title, value in self.sections.items())
        return f"{head}\n\n{body}"

    def render_section_brief(self) -> str:
        """Render section-title guidance lines for a handoff generator."""
        return "\n".join(f"- {title}: {self._coerce(value)}" for title, value in self.sections.items())

    def fill(self, sections: Mapping[str, str]) -> "Handoff":
        """Return a filled copy of the same concrete handoff class."""
        return type(self)(
            sections=dict(sections),
            title=self.title,
            instructions=self.instructions,
            metadata={**self.metadata, "filled": True},
            primitive_id=self.primitive_id,
            primitive_frozen=self.primitive_frozen,
        )

    @property
    def is_filled(self) -> bool:
        """Return whether this handoff carries produced content."""
        return bool(self.metadata.get("filled", False))

    def section_titles(self) -> tuple[str, ...]:
        """Return the ordered section titles for this handoff."""
        return tuple(self.sections.keys())

    @staticmethod
    def _coerce(value: Any) -> str:
        """Convert section values to strings for rendering."""
        return value if isinstance(value, str) else str(value)


__all__ = [
    "Handoff",
]
