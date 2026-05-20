"""Context Protocol Header

Description:
    Defines structured context state data contracts for compaction tools.
Purpose:
    Lets compaction operate on a small protocol instead of binding to a concrete
    agent loop or provider message format.
Architecture:
    - ContextMessage: Generic role/content/kind message record.
    - ProgressLog: Structured durable summary fields for aggressive compaction.
    - ContextState: Protocol for mutable message stores.
Relations:
    Re-exported by vidbyte.tools.builtins.context.types.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ContextMessage:
    """Generic message record used by compaction tools."""

    role: str
    content: str
    kind: str = "message"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProgressLog:
    """Structured progress preserved during aggressive compaction."""

    completed_tasks: tuple[str, ...] = ()
    touched_files: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()

    def to_markdown(self) -> str:
        """Render the progress log as compact Markdown."""
        sections = (
            ("Completed Tasks", self.completed_tasks),
            ("Touched Files", self.touched_files),
            ("Decisions", self.decisions),
            ("Errors", self.errors),
            ("Next Steps", self.next_steps),
        )
        lines = ["# Compacted Progress Log"]
        for title, items in sections:
            lines.append(f"\n## {title}")
            if items:
                lines.extend(f"- {item}" for item in items)
            else:
                lines.append("- N/A")
        return "\n".join(lines)


class ContextState(Protocol):
    """Protocol for mutable conversation state stores."""

    def messages(self) -> Sequence[ContextMessage]:
        """Return the current message sequence."""

    def replace_messages(self, messages: Sequence[ContextMessage]) -> None:
        """Replace the current message sequence."""
