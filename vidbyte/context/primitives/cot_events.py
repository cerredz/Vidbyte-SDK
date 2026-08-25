"""Context Protocol Header

FILE: vidbyte/context/primitives/cot_events.py

PURPOSE: Defines the five immutable context records written by the deep
chain-of-thought event tools. Each dataclass stores one structured event and
renders a deterministic, bounded compatibility text block for the next model
turn. This file owns record shape and rendering, not model argument parsing or
ContextManager lifecycle.

ROLE IN CODEBASE: `vidbyte/tools/builtins/cot_events.py` constructs these
records after validating model calls, and `vidbyte/context/manager.py` stores
them by primitive_id. `vidbyte/context/primitives/__init__.py` re-exports the
public classes. Shared titles and bounds come from
`vidbyte/lib/constants/cot_events.py`; truncation helpers come from
`vidbyte/context/primitives/base.py`.

ARCHITECTURE NOTE: These are frozen, slotted dataclasses at the context
primitive boundary. Their fields remain structured for observability while
`to_context_text()` provides the compact text representation required by
existing context-window consumers. Hypothesis and assumption records are
content-keyed ledgers; the other records are append-only events.

FUNCTION INVENTORY: `HypothesisContextItem`, `DecisionContextItem`,
`AssumptionCheckContextItem`, `UncertaintyContextItem`, and
`BacktrackContextItem` are frozen dataclasses. Each `to_context_text()` method
returns deterministic text bounded by the record's max_chars and does not raise
for ordinary field values.

COMMON MODIFICATION PATTERNS: Add a model-facing field to the matching tool
spec and execute builder first, then add the typed dataclass field and render it
in a stable order. Keep primitive_id, kind, max_chars, metadata, and
primitive_frozen compatible with ContextManager's registry contract.

WHAT NOT TO DO IN THIS FILE:
1. Do not parse or normalize model arguments; that belongs to the builtin
   parser.
2. Do not perform ContextManager writes or choose placement; the manager owns
   registry lifecycle.
3. Do not introduce unbounded rendering or provider-specific serialization.
4. Do not change kind strings or ledger identity semantics without updating the
   public tool contract and design document.

KNOWN EDGE CASES: Optional text fields are omitted from rendered output when
blank. Rejected alternatives are rendered from validated option and reason
keys. Every renderer applies the shared max_chars truncation after assembling
its deterministic lines, so long model text cannot grow the context without
bound.

RELATED DOCS: `https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/deep-cot-tools.md`
defines the primitive fields and lifecycle.

AUTO-GENERATED FLAG: No; maintained source code.

TEST FILES: No dedicated feature test file exists in the source PR. Resolver
verification covers dataclass construction, export identity, render bounds,
and registry smoke paths.

CONCURRENCY MODEL: Frozen records are immutable after construction. The
ContextManager registry is mutable and unsynchronized; concurrent replacement
of the same primitive_id is ordered by the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text
from vidbyte.lib.constants.cot_events import (
    ASSUMPTION_CHECK_TITLE,
    BACKTRACK_TITLE,
    DECISION_TITLE,
    DEFAULT_BASIS_TYPE,
    DEFAULT_MAX_CHARS,
    DEFAULT_RETURNABLE,
    DEFAULT_REVERSIBLE,
    DEFAULT_SALVAGE,
    HYPOTHESIS_TITLE,
    UNCERTAINTY_TITLE,
)


@dataclass(frozen=True, slots=True)
class HypothesisContextItem:
    """Record a falsifiable belief, its support, and its resolution path."""

    primitive_id: str
    statement: str
    scope: str
    basis: str
    status: str
    basis_type: str = DEFAULT_BASIS_TYPE
    falsifier: str = ""
    confidence: float | None = None
    next_check: str | None = None
    title: str = HYPOTHESIS_TITLE
    max_chars: int = DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "hypothesis"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Render the hypothesis in deterministic order within max_chars."""
        lines = [
            f"Status: {self.status}",
            f"Basis Type: {self.basis_type}",
            f"Scope: {self.scope}",
            f"Hypothesis: {self.statement}",
            f"Basis: {self.basis}",
            f"Falsifier: {self.falsifier}",
        ]
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        if self.next_check:
            lines.append(f"Next Check: {self.next_check}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DecisionContextItem:
    """Record a selected branch, rejected alternatives, risk, and review boundary."""

    primitive_id: str
    decision: str
    chosen_because: str
    criterion: str
    rejected: tuple[Mapping[str, Any], ...]
    expected_outcome: str
    main_risk: str
    reversible: str = DEFAULT_REVERSIBLE
    confidence: float | None = None
    review_trigger: str | None = None
    title: str = DECISION_TITLE
    max_chars: int = DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "decision"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Render the decision and alternatives in deterministic bounded text."""
        lines = [
            f"Decision: {self.decision}",
            f"Chosen Because: {self.chosen_because}",
            f"Criterion: {self.criterion}",
            f"Expected Outcome: {self.expected_outcome}",
            f"Main Risk: {self.main_risk}",
            f"Reversible: {self.reversible}",
        ]
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        if self.review_trigger:
            lines.append(f"Review Trigger: {self.review_trigger}")
        rejected_lines = tuple(
            f"{entry.get('option', '')} — rejected because {entry.get('reason', '')}"
            for entry in self.rejected
        )
        _extend_section(lines, "Rejected Alternatives", rejected_lines)
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AssumptionCheckContextItem:
    """Record an assumption, its dependency, impact, and verification evidence."""

    primitive_id: str
    assumption: str
    scope: str
    basis: str
    action: str
    impact_if_wrong: str
    dependency: str
    verification_step: str | None
    falsifier: str
    confidence: float | None = None
    title: str = ASSUMPTION_CHECK_TITLE
    max_chars: int = DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "assumption_check"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Render the assumption ledger record in deterministic bounded text."""
        lines = [
            f"Action: {self.action}",
            f"Impact If Wrong: {self.impact_if_wrong}",
            f"Assumption: {self.assumption}",
            f"Scope: {self.scope}",
            f"Basis: {self.basis}",
            f"Dependency: {self.dependency}",
            f"Falsifier: {self.falsifier}",
        ]
        if self.verification_step:
            lines.append(f"Verification Step: {self.verification_step}")
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class UncertaintyContextItem:
    """Record confidence divergence, its source, and the response to uncertainty."""

    primitive_id: str
    next_step: float
    on_track: float
    progress: str
    uncertainty_source: str
    next_action: str
    trigger: str = ""
    blocker: str = ""
    reassessment_condition: str = ""
    title: str = UNCERTAINTY_TITLE
    max_chars: int = DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "uncertainty"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Render the uncertainty reading in deterministic bounded text."""
        divergence = self.on_track - self.next_step
        lines = [
            f"Confidence Next Step: {self.next_step:.2f}",
            f"Confidence On Track: {self.on_track:.2f}",
            f"Divergence (On Track - Next Step): {divergence:.2f}",
            f"Progress: {self.progress}",
            f"Uncertainty Source: {self.uncertainty_source}",
            f"Next Action: {self.next_action}",
        ]
        if self.trigger:
            lines.append(f"Trigger: {self.trigger}")
        if self.blocker:
            lines.append(f"Blocker: {self.blocker}")
        if self.reassessment_condition:
            lines.append(f"Reassessment Condition: {self.reassessment_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class BacktrackContextItem:
    """Record an abandoned path, its evidence, retained value, and replacement plan."""

    primitive_id: str
    abandoning: str
    reason: str
    evidence: str
    attempted_result: str
    replacement_plan: str
    loop_guard: str
    salvage: str = DEFAULT_SALVAGE
    returnable: str = DEFAULT_RETURNABLE
    title: str = BACKTRACK_TITLE
    max_chars: int = DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "backtrack"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Render the backtrack record in deterministic bounded text."""
        lines = [
            f"Abandoning: {self.abandoning}",
            f"Reason: {self.reason}",
            f"Evidence: {self.evidence}",
            f"Attempted Result: {self.attempted_result}",
            f"Salvage: {self.salvage}",
            f"Returnable: {self.returnable}",
            f"Replacement Plan: {self.replacement_plan}",
            f"Loop Guard: {self.loop_guard}",
        ]
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AssumptionCheckContextItem",
    "BacktrackContextItem",
    "DecisionContextItem",
    "HypothesisContextItem",
    "UncertaintyContextItem",
]
