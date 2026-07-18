"""Execution and feedback challenge context primitives.

FILE
    vidbyte/context/primitives/execution.py
PURPOSE
    Preserve protected constraints, fragile dependencies, intervention risks,
    and missing feedback loops during execution in any problem domain.
ROLE IN CODEBASE
    Supplies descriptive ContextItem implementations that make execution risks
    model-visible while leaving enforcement and recovery to callers.
ARCHITECTURE NOTE
    Frozen, slotted records separate observations from conclusions and render
    deterministically before applying one shared size bound.
FUNCTION INVENTORY
    InvariantContextItem, DependencyContextItem, InterventionRiskContextItem,
    and FeedbackGapContextItem cover constraints, dependencies, effects, and
    observation respectively.
COMMON MODIFICATION PATTERNS
    Add opaque domain fields before the lifecycle tail, preserve semantic
    distinctions between similarly named concepts, and render in stable order.
WHAT NOT TO DO
    Do not enforce invariants, invoke fallbacks, interpret units or thresholds,
    or imply that a documented recovery action ran successfully.
KNOWN EDGE CASES
    The shared owner resolves the record while dependency_owner identifies the
    dependency's owner; recovery and containment remain descriptive only.
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
class InvariantContextItem:
    """Record a protected invariant, observed state, and possible violation."""

    invariant: str
    scope: str | None = None
    observed_state: str | None = None
    violation_evidence: tuple[str, ...] = ()
    consequence: str | None = None
    check_method: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Invariant"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "invariant"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [f"Status: {self.status}", f"Severity: {self.severity}"]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Invariant: {self.invariant}")
        if self.scope:
            lines.append(f"Scope: {self.scope}")
        if self.observed_state:
            lines.append(f"Observed State: {self.observed_state}")
        _extend_section(lines, "Violation Evidence", self.violation_evidence)
        if self.consequence:
            lines.append(f"Consequence: {self.consequence}")
        if self.check_method:
            lines.append(f"Check Method: {self.check_method}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DependencyContextItem:
    """Record a plan dependency, its ownership, fragility, and fallback."""

    objective_or_plan: str
    dependency: str
    required_condition: str | None = None
    dependency_owner: str | None = None
    fragility: str | None = None
    fallback: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Dependency"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "dependency"
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
                f"Objective or Plan: {self.objective_or_plan}",
                f"Dependency: {self.dependency}",
            )
        )
        if self.required_condition:
            lines.append(f"Required Condition: {self.required_condition}")
        if self.dependency_owner:
            lines.append(f"Dependency Owner: {self.dependency_owner}")
        if self.fragility:
            lines.append(f"Fragility: {self.fragility}")
        if self.fallback:
            lines.append(f"Fallback: {self.fallback}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class InterventionRiskContextItem:
    """Separate intended, reversible, and irreversible effects of an intervention."""

    intervention: str
    intended_effect: str | None = None
    reversible_effects: tuple[str, ...] = ()
    irreversible_effects: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    containment: str | None = None
    recovery: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Intervention Risk"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "intervention_risk"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [f"Status: {self.status}", f"Severity: {self.severity}"]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Intervention: {self.intervention}")
        if self.intended_effect:
            lines.append(f"Intended Effect: {self.intended_effect}")
        _extend_section(lines, "Reversible Effects", self.reversible_effects)
        _extend_section(lines, "Irreversible Effects", self.irreversible_effects)
        _extend_section(lines, "Uncertainties", self.uncertainties)
        if self.containment:
            lines.append(f"Containment: {self.containment}")
        if self.recovery:
            lines.append(f"Recovery: {self.recovery}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class FeedbackGapContextItem:
    """Record what feedback is needed to observe an intervention's outcome."""

    intervention: str
    expected_outcome: str
    observable_signals: tuple[str, ...] = ()
    measurement_method: str | None = None
    observation_cadence: str | None = None
    response_threshold: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Feedback Gap"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "feedback_gap"
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
                f"Intervention: {self.intervention}",
                f"Expected Outcome: {self.expected_outcome}",
            )
        )
        _extend_section(lines, "Observable Signals", self.observable_signals)
        if self.measurement_method:
            lines.append(f"Measurement Method: {self.measurement_method}")
        if self.observation_cadence:
            lines.append(f"Observation Cadence: {self.observation_cadence}")
        if self.response_threshold:
            lines.append(f"Response Threshold: {self.response_threshold}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "DependencyContextItem",
    "FeedbackGapContextItem",
    "InterventionRiskContextItem",
    "InvariantContextItem",
]
