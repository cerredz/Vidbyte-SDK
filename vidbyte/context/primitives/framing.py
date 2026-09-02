"""General problem-framing context primitives.

FILE:
    vidbyte/context/primitives/framing.py
PURPOSE:
    Preserve challenges to a problem's frame, objectives, boundaries, meanings,
    and represented perspectives as bounded model-visible context.
ROLE IN CODEBASE:
    Supplies caller- or worker-authored records consumed structurally by
    ContextManager; it does not decide whether a challenge is correct.
ARCHITECTURE NOTE:
    Each frozen, slotted dataclass implements ContextItem structurally and owns
    deterministic rendering so no domain policy enters the context manager.
FUNCTION INVENTORY:
    ProblemFrameContextItem, ObjectiveGapContextItem,
    ObjectiveConflictContextItem, BoundaryContextItem, AmbiguityContextItem,
    and PerspectiveGapContextItem each render one adversarial concern.
COMMON MODIFICATION PATTERNS:
    Add descriptive fields before the shared lifecycle tail, then render them in
    stable order and apply _truncate_text exactly once.
WHAT NOT TO DO IN THIS FILE:
    Do not enforce boundaries, infer missing perspectives, validate lifecycle
    strings, or register these records as model-creatable tools in this module.
KNOWN EDGE CASES:
    Required strings may be empty; tuple sections are normally omitted when
    empty; custom status and severity strings are preserved.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/general-problem-solving-context-primitives.md
TESTS:
    The approved no-tests workflow uses package compilation and import/render
    smoke checks described in the design document.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text


@dataclass(frozen=True, slots=True)
class ProblemFrameContextItem:
    """Challenge a stated problem frame against the underlying need."""

    current_frame: str
    underlying_need: str
    affected_parties: tuple[str, ...] = ()
    suspected_proxy: str | None = None
    alternative_frames: tuple[str, ...] = ()
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Problem Frame"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "problem_frame"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries a challenge to the way a problem has been framed. Current frame and underlying need distinguish the stated issue from the need beneath it. Affected parties, suspected proxy, and alternative frames reveal who or what the current framing may omit. Use this record before optimizing a proxy that may not represent the real problem.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.extend(
            (
                f"Current Frame: {self.current_frame}",
                f"Underlying Need: {self.underlying_need}",
            )
        )
        _extend_section(lines, "Affected Parties", self.affected_parties)
        if self.suspected_proxy:
            lines.append(f"Suspected Proxy: {self.suspected_proxy}")
        _extend_section(lines, "Alternative Frames", self.alternative_frames)
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ObjectiveGapContextItem:
    """Record what remains unresolved between an objective and its outcome."""

    objective: str
    desired_outcome: str
    unresolved_parts: tuple[str, ...] = ()
    completion_condition: str | None = None
    next_evidence: tuple[str, ...] = ()
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Objective Gap"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "objective_gap"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries an unresolved gap between an objective and its desired outcome. Unresolved parts identify what remains incomplete, while completion condition defines what would count as enough. Next evidence points to observations that can reduce the gap. Use the status and resolution condition to keep unfinished objectives visible.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.extend(
            (f"Objective: {self.objective}", f"Desired Outcome: {self.desired_outcome}")
        )
        _extend_section(lines, "Unresolved Parts", self.unresolved_parts)
        if self.completion_condition:
            lines.append(f"Completion Condition: {self.completion_condition}")
        _extend_section(lines, "Next Evidence", self.next_evidence)
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ObjectiveConflictContextItem:
    """Expose objectives that cannot currently be satisfied together."""

    objectives: tuple[str, ...]
    conflict: str
    affected_parties: tuple[str, ...] = ()
    decision_needed: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Objective Conflict"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "objective_conflict"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries a conflict among objectives that cannot all be satisfied under current conditions. The objectives section names the competing aims, and the conflict states the incompatibility that connects them. Affected parties show who bears the tension, while decision needed identifies the next choice. Use this record to surface prioritization instead of silently sacrificing an objective.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        if self.objectives:
            _extend_section(lines, "Objectives", self.objectives)
        else:
            lines.append("Objectives:")
        lines.append(f"Conflict: {self.conflict}")
        _extend_section(lines, "Affected Parties", self.affected_parties)
        if self.decision_needed:
            lines.append(f"Decision Needed: {self.decision_needed}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class BoundaryContextItem:
    """Record a scope, authority, policy, ethical, or other boundary concern."""

    boundary_type: str
    boundary: str
    challenged_action: str | None = None
    non_goals: tuple[str, ...] = ()
    authority_required: str | None = None
    escalation_path: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Boundary"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "boundary"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries a challenged boundary around an action or scope. Boundary type and boundary state the governing limit, while challenged action identifies what may cross it. Non-goals, authority required, and escalation path describe exclusions and the route for exceptions. Use this record to keep scope and authority explicit before proceeding.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.extend(
            (f"Boundary Type: {self.boundary_type}", f"Boundary: {self.boundary}")
        )
        if self.challenged_action:
            lines.append(f"Challenged Action: {self.challenged_action}")
        _extend_section(lines, "Non-Goals", self.non_goals)
        if self.authority_required:
            lines.append(f"Authority Required: {self.authority_required}")
        if self.escalation_path:
            lines.append(f"Escalation Path: {self.escalation_path}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AmbiguityContextItem:
    """Preserve competing interpretations and their practical consequences."""

    term: str
    context: str
    interpretations: tuple[str, ...] = ()
    consequences: tuple[str, ...] = ()
    clarification_needed: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Ambiguity"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "ambiguity"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries an ambiguity that could change the meaning of the work. Term and context establish what is unclear, while interpretations preserve the plausible readings. Consequences show why the distinction matters, and clarification needed identifies the next question. Use this record to avoid committing to one interpretation without acknowledging the alternatives.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.extend((f"Term: {self.term}", f"Context: {self.context}"))
        _extend_section(lines, "Interpretations", self.interpretations)
        _extend_section(lines, "Consequences", self.consequences)
        if self.clarification_needed:
            lines.append(f"Clarification Needed: {self.clarification_needed}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class PerspectiveGapContextItem:
    """Record perspectives or value judgments absent from current reasoning."""

    subject: str
    missing_perspectives: tuple[str, ...] = ()
    affected_parties: tuple[str, ...] = ()
    likely_blind_spots: tuple[str, ...] = ()
    value_judgments: tuple[str, ...] = ()
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Perspective Gap"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "perspective_gap"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries a perspective gap around a subject or decision. Missing perspectives identify viewpoints not yet represented, and affected parties show who may experience the consequences. Likely blind spots and value judgments expose assumptions that a single viewpoint can hide. Use this record to broaden review before treating the current account as complete.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Subject: {self.subject}")
        _extend_section(lines, "Missing Perspectives", self.missing_perspectives)
        _extend_section(lines, "Affected Parties", self.affected_parties)
        _extend_section(lines, "Likely Blind Spots", self.likely_blind_spots)
        _extend_section(lines, "Value Judgments", self.value_judgments)
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AmbiguityContextItem",
    "BoundaryContextItem",
    "ObjectiveConflictContextItem",
    "ObjectiveGapContextItem",
    "PerspectiveGapContextItem",
    "ProblemFrameContextItem",
]
