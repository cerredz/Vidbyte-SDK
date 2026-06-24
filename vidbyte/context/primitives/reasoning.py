"""Context Protocol Header

Description:
    Defines reasoning context primitives for inner-loop reflection algorithms.
Purpose:
    Gives the problem-space search and error-correction algorithms typed,
    bounded context units that render model-visible reflection for the next call.
Architecture:
    - ProblemSpaceSearchContextItem: Ordered unconsidered/blind-spot/direction sections.
    - ErrorCorrectionContextItem: Authoritative correction notice sections.
Relations:
    Written by ProblemSpaceSearchAlgorithm and ErrorCorrectionAlgorithm and
    re-exported through vidbyte.context.primitives.
Similar Files:
    - `vidbyte/context/primitives/checkpoints.py`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _truncate_text


@dataclass(frozen=True, slots=True)
class ProblemSpaceSearchContextItem:
    """Structured problem-space exploration context written between iterations."""

    primitive_id: str
    iteration: int
    note_index: int
    unconsidered: str
    blind_spots: str
    next_directions: str
    title: str = "Problem-Space Search"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "problem_space_search"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the exploration sections in deterministic order, bounded by max_chars.
        text = "\n".join(
            (
                f"Iteration: {self.iteration}",
                f"Search Pass: {self.note_index}",
                "",
                "### Not Yet Considered",
                self.unconsidered,
                "",
                "### Blind Spots",
                self.blind_spots,
                "",
                "### Next Directions To Explore",
                self.next_directions,
            )
        )
        return _truncate_text(text, self.max_chars)


@dataclass(frozen=True, slots=True)
class ErrorCorrectionContextItem:
    """Authoritative correction notice that overrides context contradicting the system prompt."""

    primitive_id: str
    iteration: int
    pass_index: int
    corrections: tuple[str, ...]
    summary: str
    title: str = "Correction Notice"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "error_correction"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders an authoritative override note listing each correction, bounded by max_chars.
        lines = [
            "The following statements earlier in this context are incorrect or contradict the",
            "original system prompt. Treat this notice as authoritative and disregard the",
            "flagged content going forward.",
            "",
            f"Iteration: {self.iteration}",
            f"Correction Pass: {self.pass_index}",
        ]
        if self.summary:
            lines.extend(("", "### Summary", self.summary))
        lines.append("")
        lines.append("### Corrections")
        if self.corrections:
            lines.extend(f"- {correction}" for correction in self.corrections)
        else:
            lines.append("- None.")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "ErrorCorrectionContextItem",
    "ProblemSpaceSearchContextItem",
]
