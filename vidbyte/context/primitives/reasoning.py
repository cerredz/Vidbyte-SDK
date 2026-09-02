"""FILE: vidbyte/context/primitives/reasoning.py

PURPOSE:
    Defines bounded problem-space search and error-correction records for
    model-visible reflection between inner-loop iterations.
ROLE IN CODEBASE:
    ProblemSpaceSearchAlgorithm and ErrorCorrectionAlgorithm write these records;
    ContextManager renders them and primitives __init__ re-exports their types.
ARCHITECTURE NOTE:
    The records are immutable and descriptive; shared truncation adds the managed
    context boundary while algorithms retain control of reflection policy.
FUNCTION INVENTORY:
    ProblemSpaceSearchContextItem.to_context_text() renders exploration gaps.
    ErrorCorrectionContextItem.to_context_text() renders authoritative corrections.
COMMON MODIFICATION PATTERNS:
    Add reflection fields before the metadata tail, preserve section order, and
    keep corrections visually distinct from the original context they override.
WHAT NOT TO DO IN THIS FILE:
    Do not perform searches, decide truth, mutate prior messages, or control loop
    transitions; inner-loop algorithms and ContextManager own those operations.
KNOWN EDGE CASES:
    Empty correction collections render an explicit none marker, and oversized
    reflection text is bounded only at render time.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/tree/main/vidbyte/context/primitives
TESTS:
    Existing context algorithm tests plus source compilation and package smoke
    gates cover rendering, importability, and correction integration.
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
        lines = [
            "This primitive carries a bounded note about unexplored parts of a problem. The iteration and search-pass values locate the note within repeated exploration. The following sections name considerations still missing, blind spots, and directions for the next search. Use it to widen investigation before treating the current problem space as complete.",
            "",
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
        ]
        text = "\n".join(lines)
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
            "This primitive carries an authoritative correction for earlier context that conflicts with the system prompt. The iteration and correction-pass values identify when the correction was produced. The summary and correction list state which claims must be replaced or disregarded. Give this notice priority over the flagged context while preserving its role as a correction record.",
            "",
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
