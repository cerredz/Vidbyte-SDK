"""Context Protocol Header

Description:
    Defines the deep chain-of-thought event context primitives.
Purpose:
    Gives the five model-callable CoT monitoring tools typed, bounded context
    units that keep each emitted reasoning event visible across future turns.
Architecture:
    - HypothesisContextItem, DecisionContextItem, AssumptionCheckContextItem,
      UncertaintyContextItem, BacktrackContextItem: frozen, slotted dataclasses
      with deterministic renderers bounded by max_chars.
    - PredictionContextItem, GoalCheckContextItem, CounterfactualContextItem,
      AssumptionsSnapshotContextItem, FailureScanContextItem, WhyContextItem:
      batch-2 monitoring primitives in the same shape.
Relations:
    Written by vidbyte.tools.builtins.cot_events tools and re-exported through
    vidbyte.context.primitives.
Similar Files:
    - `vidbyte/context/primitives/epistemics.py`
    - `vidbyte/context/primitives/checkpoints.py`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text

_HYPOTHESIS_TITLE = "Hypothesis"
_DECISION_TITLE = "Decision"
_ASSUMPTION_CHECK_TITLE = "Assumption Check"
_UNCERTAINTY_TITLE = "Uncertainty Reading"
_BACKTRACK_TITLE = "Backtrack"
_DEFAULT_MAX_CHARS = 2000


@dataclass(frozen=True, slots=True)
class HypothesisContextItem:
    """Records a falsifiable belief the agent holds, its basis, and its current status."""

    primitive_id: str
    statement: str
    basis: str
    status: str
    basis_type: str = "inference"
    title: str = _HYPOTHESIS_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "hypothesis"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the hypothesis record in deterministic order, bounded by max_chars.
        lines = [
            f"Status: {self.status}",
            f"Basis Type: {self.basis_type}",
            f"Hypothesis: {self.statement}",
            f"Basis: {self.basis}",
        ]
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DecisionContextItem:
    """Records one chosen branch, the deciding reason, and the alternatives rejected."""

    primitive_id: str
    decision: str
    chosen_because: str
    rejected: tuple[Mapping[str, Any], ...] = ()
    reversible: str = "yes"
    confidence: float | None = None
    title: str = _DECISION_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "decision"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the decision record with its rejected alternatives, bounded by max_chars.
        lines = [
            f"Decision: {self.decision}",
            f"Chosen Because: {self.chosen_because}",
            f"Reversible: {self.reversible}",
        ]
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        rejected_lines = tuple(
            f"{entry.get('option', '')} — rejected because {entry.get('reason', '')}"
            for entry in self.rejected
        )
        _extend_section(lines, "Rejected Alternatives", rejected_lines)
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AssumptionCheckContextItem:
    """Records reliance on an unverified assumption or the act of verifying or falsifying one."""

    primitive_id: str
    assumption: str
    action: str
    impact_if_wrong: str
    verification_step: str | None = None
    title: str = _ASSUMPTION_CHECK_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "assumption_check"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the assumption ledger record in deterministic order, bounded by max_chars.
        lines = [
            f"Action: {self.action}",
            f"Impact If Wrong: {self.impact_if_wrong}",
            f"Assumption: {self.assumption}",
        ]
        if self.verification_step:
            lines.append(f"Verification Step: {self.verification_step}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class UncertaintyContextItem:
    """Records one calibration snapshot: next-step confidence, on-track confidence, and velocity."""

    primitive_id: str
    next_step: float
    on_track: float
    progress: str
    trigger: str = ""
    title: str = _UNCERTAINTY_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "uncertainty"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the uncertainty reading with both confidences and velocity, bounded by max_chars.
        divergence = self.on_track - self.next_step
        lines = [
            f"Confidence Next Step: {self.next_step:.2f}",
            f"Confidence On Track: {self.on_track:.2f}",
            f"Divergence (On Track - Next Step): {divergence:.2f}",
            f"Progress: {self.progress}",
        ]
        if self.trigger:
            lines.append(f"Trigger: {self.trigger}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class BacktrackContextItem:
    """Records the abandonment of an approach, why, and what work carries forward."""

    primitive_id: str
    abandoning: str
    reason: str
    salvage: str = "nothing"
    returnable: str = "yes"
    title: str = _BACKTRACK_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "backtrack"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the backtrack record in deterministic order, bounded by max_chars.
        lines = [
            f"Abandoning: {self.abandoning}",
            f"Reason: {self.reason}",
            f"Salvage: {self.salvage}",
            f"Returnable: {self.returnable}",
        ]
        return _truncate_text("\n".join(lines), self.max_chars)


_PREDICTION_TITLE = "Prediction"
_GOAL_CHECK_TITLE = "Goal Check"
_COUNTERFACTUAL_TITLE = "Counterfactual"
_ASSUMPTIONS_TITLE = "Current Assumptions"
_FAILURE_SCAN_TITLE = "Failure Scan"
_WHY_TITLE = "Why Retrospective"
_DEFAULT_LIKELIHOOD = "medium"


@dataclass(frozen=True, slots=True)
class PredictionContextItem:
    """Records one forward-looking, falsifiable forecast and its resolution trigger.

    A prediction is only useful when it could turn out wrong, so this
    primitive pairs the forecast with the trigger that settles it and the
    confidence behind it. When they matter, it also records the stakes if
    the prediction misses, what kind of outcome it concerns, and what it was
    actually grounded in, so a later reader can judge calibration by
    category rather than only in aggregate.
    """

    primitive_id: str
    predicts: str
    by_when: str
    confidence: float
    stakes: str | None = None
    basis: str | None = None
    category: str | None = None
    title: str = _PREDICTION_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "prediction"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the prediction, its trigger, and confidence, bounded by max_chars.
        lines = [
            f"Predicts: {self.predicts}",
            f"Resolved By: {self.by_when}",
            f"Confidence: {self.confidence:.2f}",
        ]
        if self.category:
            lines.append(f"Category: {self.category}")
        if self.stakes:
            lines.append(f"Stakes: {self.stakes}")
        if self.basis:
            lines.append(f"Basis: {self.basis}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class GoalCheckContextItem:
    """Records one goal-drift attestation comparing current activity to the original goal.

    Detail work quietly rewrites an agent's own memory of the objective, so
    this primitive forces a side-by-side comparison between the original
    request and what is actually happening right now. Beyond the alignment
    verdict, it can record what caused the drift and how many steps have
    passed since the previous check, which together turn a single
    attestation into a trend a later reader can track.
    """

    primitive_id: str
    original_goal: str
    current_activity: str
    still_serves: str
    pivot_to: str | None = None
    drift_cause: str | None = None
    steps_since_last_check: int | None = None
    title: str = _GOAL_CHECK_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "goal_check"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the drift attestation, bounded by max_chars.
        lines = [
            f"Still Serves Goal: {self.still_serves}",
            f"Original Goal: {self.original_goal}",
            f"Current Activity: {self.current_activity}",
        ]
        if self.steps_since_last_check is not None:
            lines.append(f"Steps Since Last Check: {self.steps_since_last_check}")
        if self.drift_cause:
            lines.append(f"Drift Cause: {self.drift_cause}")
        if self.pivot_to:
            lines.append(f"Pivot To: {self.pivot_to}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CounterfactualContextItem:
    """Records the model's hindsight about a branch not taken.

    This is deliberately labeled as hindsight rather than ground truth: the
    branch was never actually observed, so the record pairs the guess with a
    confidence level and, when applicable, whether the untaken branch is
    still reachable now. Read across a run, these records reveal whether an
    agent's branch choices are systematically good, which a single instance
    cannot show on its own.
    """

    primitive_id: str
    outcome: str
    alternative: str
    would_have: str
    confidence: float | None = None
    lesson: str | None = None
    reversible: str | None = None
    title: str = _COUNTERFACTUAL_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "counterfactual"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the actual outcome, the untaken branch, and its predicted result, bounded by max_chars.
        lines = [
            f"What Happened: {self.outcome}",
            f"Branch Not Taken: {self.alternative}",
            f"Would Have: {self.would_have}",
        ]
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        if self.reversible:
            lines.append(f"Reversible: {self.reversible}")
        if self.lesson:
            lines.append(f"Lesson: {self.lesson}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class AssumptionsSnapshotContextItem:
    """Records the current full set of assumptions the run is proceeding under.

    Assumptions do their damage while they stay implicit, so this snapshot
    exists to make the complete unverified foundation visible at once rather
    than scattered across individual decisions. Alongside the raw list, it
    can record an overall risk rating, how many entries have actually been
    checked, confidence that the list is exhaustive, and what changed since
    the previous snapshot, so a reader comparing two snapshots can see
    exactly how the foundation shifted. Each call replaces the previous one.
    """

    primitive_id: str
    assumptions: tuple[str, ...]
    scope: str | None = None
    risk_level: str | None = None
    verified_count: int | None = None
    confidence_in_completeness: float | None = None
    last_changed: str | None = None
    title: str = _ASSUMPTIONS_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "assumptions_snapshot"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the current assumption list, bounded by max_chars.
        lines: list[str] = []
        if self.scope:
            lines.append(f"Scope: {self.scope}")
        if self.risk_level:
            lines.append(f"Risk Level: {self.risk_level}")
        if self.verified_count is not None:
            lines.append(f"Verified Count: {self.verified_count}")
        if self.confidence_in_completeness is not None:
            lines.append(f"Confidence In Completeness: {self.confidence_in_completeness:.2f}")
        _extend_section(lines, "Current Assumptions", self.assumptions)
        if self.last_changed:
            lines.append(f"Last Changed: {self.last_changed}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class FailureScanContextItem:
    """Records the current premortem scan of what could go wrong at this stage.

    Writing failures down before they happen is what turns them from
    surprises into choices, so this primitive holds the current scan's
    entries alongside an overall risk verdict, whether any high-likelihood
    entry still lacks mitigation, confidence in the scan's own completeness,
    and what changed relative to the previous scan. Each call replaces the
    previous one, keeping the record aligned with the stage actually in
    progress.
    """

    primitive_id: str
    failures: tuple[Mapping[str, Any], ...]
    stage: str | None = None
    overall_risk: str | None = None
    blocking: str | None = None
    confidence: float | None = None
    previous_delta: str | None = None
    title: str = _FAILURE_SCAN_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "failure_scan"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the current failure scan with likelihoods, bounded by max_chars.
        lines: list[str] = []
        if self.stage:
            lines.append(f"Stage: {self.stage}")
        if self.overall_risk:
            lines.append(f"Overall Risk: {self.overall_risk}")
        if self.blocking:
            lines.append(f"Blocking: {self.blocking}")
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        if self.failures:
            lines.append("Could Go Wrong:")
            for entry in self.failures:
                likelihood = str(entry.get("likelihood", _DEFAULT_LIKELIHOOD))
                failure = str(entry.get("failure", ""))
                lines.append(f"- [{likelihood}] {failure}")
                mitigation = str(entry.get("mitigation", "") or "")
                if mitigation:
                    lines.append(f"  Mitigation: {mitigation}")
        if self.previous_delta:
            lines.append(f"Previous Delta: {self.previous_delta}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class WhyContextItem:
    """Records a retrospective on why the actions taken so far were taken.

    The tool log already shows what happened; this primitive captures the
    reasoning that is otherwise lost, along with an honest verdict on
    whether re-examining that reasoning revealed anything that should
    change. It can also record what prompted the retrospective, how many
    steps it actually covers, and how confident the agent is in the
    rationale it just reconstructed.
    """

    primitive_id: str
    why: str
    reconsider: str
    change: str | None = None
    trigger: str | None = None
    steps_covered: int | None = None
    confidence_in_rationale: float | None = None
    title: str = _WHY_TITLE
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "why"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the rationale retrospective and its reconsider verdict, bounded by max_chars.
        lines = [
            f"Reconsider: {self.reconsider}",
        ]
        if self.trigger:
            lines.append(f"Trigger: {self.trigger}")
        if self.steps_covered is not None:
            lines.append(f"Steps Covered: {self.steps_covered}")
        if self.confidence_in_rationale is not None:
            lines.append(f"Confidence In Rationale: {self.confidence_in_rationale:.2f}")
        lines.extend(("### Why", self.why))
        if self.change:
            lines.extend(("", "### Change", self.change))
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AssumptionCheckContextItem",
    "AssumptionsSnapshotContextItem",
    "BacktrackContextItem",
    "CounterfactualContextItem",
    "DecisionContextItem",
    "FailureScanContextItem",
    "GoalCheckContextItem",
    "HypothesisContextItem",
    "PredictionContextItem",
    "UncertaintyContextItem",
    "WhyContextItem",
]
