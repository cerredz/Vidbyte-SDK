"""Closure and escalation context primitives for general problem solving.

FILE
    vidbyte/context/primitives/closure.py
PURPOSE
    Preserve unproductive repetition, premature completion concerns, and risks
    that require explicit ownership, acceptance, review, or escalation.
ROLE IN CODEBASE
    Supplies descriptive ContextItem implementations for ContextManager without
    controlling termination, authenticating authority, or accepting risk.
ARCHITECTURE NOTE
    Each frozen, slotted record renders a stable, bounded snapshot; lifecycle
    fields remain caller-managed strings shared with the other new primitives.
FUNCTION INVENTORY
    ProcessStallContextItem, CompletionGateContextItem, and
    RiskEscalationContextItem render closure and escalation concerns.
COMMON MODIFICATION PATTERNS
    Add descriptive closure fields before the lifecycle tail and preserve the
    distinction between evidence, validation, ownership, and authorization.
WHAT NOT TO DO
    Do not block agent completion, infer accepted risk, authenticate an acceptor,
    validate repetition counts, or execute an escape or escalation action.
KNOWN EDGE CASES
    Repetition counts may be zero or negative; a named acceptor is merely a
    recorded assertion; accepted risk requires an explicit lifecycle status.
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
class ProcessStallContextItem:
    """Record repeated activity, missing novelty, drift, and an escape action."""

    activity: str
    repeated_pattern: str
    repetition_count: int = 0
    last_new_information: str | None = None
    observed_drift: str | None = None
    escape_action: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Process Stall"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "process_stall"
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
                f"Activity: {self.activity}",
                f"Repeated Pattern: {self.repeated_pattern}",
                f"Repetition Count: {self.repetition_count}",
            )
        )
        if self.last_new_information:
            lines.append(f"Last New Information: {self.last_new_information}")
        if self.observed_drift:
            lines.append(f"Observed Drift: {self.observed_drift}")
        if self.escape_action:
            lines.append(f"Escape Action: {self.escape_action}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CompletionGateContextItem:
    """Challenge a completion claim against outcome evidence and validation."""

    claimed_result: str
    desired_outcome: str
    completion_condition: str | None = None
    current_evidence: tuple[str, ...] = ()
    missing_validation: tuple[str, ...] = ()
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Completion Gate"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "completion_gate"
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
                f"Claimed Result: {self.claimed_result}",
                f"Desired Outcome: {self.desired_outcome}",
            )
        )
        if self.completion_condition:
            lines.append(f"Completion Condition: {self.completion_condition}")
        _extend_section(lines, "Current Evidence", self.current_evidence)
        _extend_section(lines, "Missing Validation", self.missing_validation)
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class RiskEscalationContextItem:
    """Record unresolved risk, mitigation, acceptance, review, and escalation."""

    risk: str
    impact: str | None = None
    mitigations: tuple[str, ...] = ()
    authorized_acceptor: str | None = None
    expires_or_review: str | None = None
    escalation_trigger: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Risk Escalation"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "risk_escalation"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [f"Status: {self.status}", f"Severity: {self.severity}"]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Risk: {self.risk}")
        if self.impact:
            lines.append(f"Impact: {self.impact}")
        _extend_section(lines, "Mitigations", self.mitigations)
        if self.authorized_acceptor:
            lines.append(f"Authorized Acceptor: {self.authorized_acceptor}")
        if self.expires_or_review:
            lines.append(f"Expires or Review: {self.expires_or_review}")
        if self.escalation_trigger:
            lines.append(f"Escalation Trigger: {self.escalation_trigger}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "CompletionGateContextItem",
    "ProcessStallContextItem",
    "RiskEscalationContextItem",
]
