"""Decision challenge context primitives for general problem solving.

FILE
    vidbyte/context/primitives/decisions.py
PURPOSE
    Keep questionable decisions, competitive alternatives, and consequential
    tradeoffs visible instead of allowing them to disappear after selection.
ROLE IN CODEBASE
    Supplies descriptive ContextItem implementations that ContextManager can
    place and persist without becoming a decision engine.
ARCHITECTURE NOTE
    Each frozen, slotted record renders its own fields in a stable order and
    delegates only bullet formatting and final truncation to shared helpers.
FUNCTION INVENTORY
    DecisionChallengeContextItem, AlternativeChallengeContextItem, and
    TradeoffContextItem render three complementary forms of decision scrutiny.
COMMON MODIFICATION PATTERNS
    Add descriptive decision fields before the shared lifecycle tail and keep
    benefits, costs, uncertainty, and downstream effects explicitly separated.
WHAT NOT TO DO
    Do not score alternatives, synthesize rejection rationales, enforce reopen
    conditions, or register these records as automatic model tools here.
KNOWN EDGE CASES
    Confidence is descriptive and unbounded; tradeoff lists need not be balanced
    or quantified; a counterexample is recorded but never executed.
RELATED DOCS
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/general-problem-solving-context-primitives.md
TESTS
    The approved no-tests workflow uses package compilation and import/render
    smoke checks described in the design document.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text


@dataclass(frozen=True, slots=True)
class DecisionChallengeContextItem:
    """Record uncertainty, failure modes, and reopening criteria for a decision."""

    decision: str
    rationale: str | None = None
    uncertainties: tuple[str, ...] = ()
    confidence: float | None = None
    failure_modes: tuple[str, ...] = ()
    reopen_condition: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Decision Challenge"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "decision_challenge"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [f"Status: {self.status}", f"Severity: {self.severity}"]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Decision: {self.decision}")
        if self.rationale:
            lines.append(f"Rationale: {self.rationale}")
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        _extend_section(lines, "Uncertainties", self.uncertainties)
        _extend_section(lines, "Failure Modes", self.failure_modes)
        if self.reopen_condition:
            lines.append(f"Reopen Condition: {self.reopen_condition}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AlternativeChallengeContextItem:
    """Preserve a competitive alternative and why it may beat a decision."""

    target_decision: str
    alternative: str
    mechanism: str | None = None
    why_competitive: str | None = None
    rejection_rationale: str | None = None
    counterexample: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Alternative Challenge"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "alternative_challenge"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [f"Status: {self.status}", f"Severity: {self.severity}"]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.extend(
            (
                f"Target Decision: {self.target_decision}",
                f"Alternative: {self.alternative}",
            )
        )
        if self.mechanism:
            lines.append(f"Mechanism: {self.mechanism}")
        if self.why_competitive:
            lines.append(f"Why Competitive: {self.why_competitive}")
        if self.rejection_rationale:
            lines.append(f"Rejection Rationale: {self.rejection_rationale}")
        if self.counterexample:
            lines.append(f"Counterexample: {self.counterexample}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class TradeoffContextItem:
    """Make benefits, costs, affected parties, and downstream effects explicit."""

    choice: str
    benefits: tuple[str, ...] = ()
    costs: tuple[str, ...] = ()
    affected_parties: tuple[str, ...] = ()
    externalities: tuple[str, ...] = ()
    opportunity_costs: tuple[str, ...] = ()
    second_order_effects: tuple[str, ...] = ()
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Tradeoff"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "tradeoff"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [f"Status: {self.status}", f"Severity: {self.severity}"]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Choice: {self.choice}")
        _extend_section(lines, "Benefits", self.benefits)
        _extend_section(lines, "Costs", self.costs)
        _extend_section(lines, "Affected Parties", self.affected_parties)
        _extend_section(lines, "Externalities", self.externalities)
        _extend_section(lines, "Opportunity Costs", self.opportunity_costs)
        _extend_section(lines, "Second-Order Effects", self.second_order_effects)
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AlternativeChallengeContextItem",
    "DecisionChallengeContextItem",
    "TradeoffContextItem",
]
