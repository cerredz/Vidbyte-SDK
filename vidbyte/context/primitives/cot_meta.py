"""Context Protocol Header

Description:
    Defines the meta-monitoring primitives — records about the monitoring
    records themselves.
Purpose:
    Gives the cot_meta tools typed, bounded context units tracking disputes
    between records, ritualized versus earning tool calls, telemetry gaps,
    direction-changing signals, self-reported calibration, and description
    drift between tool specs and actual usage.
Architecture:
    - RecordDisputeContextItem, RitualCheckContextItem, TelemetryGapContextItem,
      SignalHighlightContextItem, CalibrationSelfReportContextItem,
      DescriptionDriftContextItem: frozen, slotted dataclasses with
      deterministic renderers bounded by max_chars.
Relations:
    Written by vidbyte.tools.builtins.cot.meta and re-exported through
    vidbyte.context.primitives.
Similar Files:
    - `vidbyte/context/primitives/cot_events.py`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text

_DEFAULT_MAX_CHARS = 2000


@dataclass(frozen=True, slots=True)
class RecordDisputeContextItem:
    """Records a contradiction between two of the agent's own records.

    An unflagged contradiction between two prior records is worse than
    either record alone, since every downstream reader — including the
    agent itself later in the run — is left trusting both simultaneously.
    This primitive names the two conflicting records, the exact point of
    conflict, an honest adjudication of which side is wrong, how the
    contradiction was actually noticed, and, when applicable, what
    reconciles the dispute.
    """

    record_a: str
    record_b: str
    contradiction: str
    which_is_wrong: str
    resolution: str | None = None
    discovered_via: str | None = None
    title: str = "Record Dispute"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "record_dispute"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the two conflicting records and the adjudication, bounded by max_chars.
        lines = [
            f"Which Is Wrong: {self.which_is_wrong}",
            f"Record A: {self.record_a}",
            f"Record B: {self.record_b}",
            f"Contradiction: {self.contradiction}",
        ]
        if self.discovered_via:
            lines.append(f"Discovered Via: {self.discovered_via}")
        if self.resolution:
            lines.append(f"Resolution: {self.resolution}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class RitualCheckContextItem:
    """Snapshot of which monitoring calls have become reflexive versus still earning their cost.

    A monitoring call that never changes what happens next has become a
    ritual, and rituals cost tokens and attention while producing only the
    appearance of vigilance. This snapshot names the calls that have become
    reflexive, the calls still genuinely earning their keep, the moments the
    telemetry itself failed to capture, the sample of calls the audit
    actually reviewed, and an overall verdict on whether the monitoring
    weight is currently justified. Each call replaces the previous snapshot.
    """

    reflexive: tuple[str, ...]
    still_earning: tuple[str, ...]
    blind_spots: str | None = None
    overall: str | None = None
    sample_size: int | None = None
    time_window: str | None = None
    title: str = "Ritual Check"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "ritual_check"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the reflexive and earning call sets, bounded by max_chars.
        lines: list[str] = []
        if self.overall:
            lines.append(f"Overall: {self.overall}")
        if self.sample_size is not None:
            lines.append(f"Sample Size: {self.sample_size}")
        if self.time_window:
            lines.append(f"Time Window: {self.time_window}")
        _extend_section(lines, "Reflexive (Called By Habit)", self.reflexive)
        _extend_section(lines, "Still Earning Their Cost", self.still_earning)
        if self.blind_spots:
            lines.append(f"Blind Spots: {self.blind_spots}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class TelemetryGapContextItem:
    """Records an important event no available tool could capture.

    This primitive is the monitoring system's own feedback channel: it
    exists specifically to say what the other tools cannot. Each entry
    describes the event, the record that was wanted for it, the closest
    existing tool that was considered and rejected, how severe the gap is,
    how often this kind of gap recurs, and any workaround used in place of a
    proper record.
    """

    event: str
    wanted_to_record: str
    closest_tool: str | None = None
    severity: str | None = None
    frequency: str | None = None
    workaround_used: str | None = None
    title: str = "Telemetry Gap"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "telemetry_gap"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the uncapturable event and the record that was wanted, bounded by max_chars.
        lines = [
            f"Event: {self.event}",
            f"Wanted To Record: {self.wanted_to_record}",
        ]
        if self.closest_tool:
            lines.append(f"Closest Tool: {self.closest_tool}")
        if self.severity:
            lines.append(f"Severity: {self.severity}")
        if self.frequency:
            lines.append(f"Frequency: {self.frequency}")
        if self.workaround_used:
            lines.append(f"Workaround Used: {self.workaround_used}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SignalHighlightContextItem:
    """Records which monitoring record most changed the run's direction.

    Most records describe the run as it happens; a few actually steer it,
    and without an explicit marker the two are indistinguishable to a later
    reader. This primitive names the steering record, how much it actually
    changed direction, the counterfactual of what would have happened
    without it, its downstream effect, when it was noticed, and how the
    record compared to expectations at the time.
    """

    record: str
    changed_direction: str
    would_have_happened: str
    surprise: str | None = None
    downstream_effect: str | None = None
    discovered_when: str | None = None
    title: str = "Signal Highlight"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "signal_highlight"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the direction-changing record and its counterfactual, bounded by max_chars.
        lines = [
            f"Changed Direction: {self.changed_direction}",
            f"Record: {self.record}",
            f"Would Have Happened Otherwise: {self.would_have_happened}",
        ]
        if self.surprise:
            lines.append(f"Surprise: {self.surprise}")
        if self.downstream_effect:
            lines.append(f"Downstream Effect: {self.downstream_effect}")
        if self.discovered_when:
            lines.append(f"Discovered When: {self.discovered_when}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CalibrationSelfReportContextItem:
    """Snapshot of the agent's self-estimated prediction calibration.

    Periodically self-auditing against a track record of actual predictions
    is what turns calibration from a vague self-image into something
    checkable. This snapshot holds the raw counts and estimated hit rate, a
    confidence rating on the estimate itself, a self-diagnosed direction of
    bias, and how that self-diagnosis has moved since the previous report.
    Each call replaces the previous snapshot.
    """

    predictions_made: int
    estimated_hits: int
    estimated_rate: float
    confidence_in_estimate: float
    bias_self_assessment: str | None = None
    trend: str | None = None
    title: str = "Calibration Self-Report"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "calibration_self_report"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the self-estimated hit rate and bias assessment, bounded by max_chars.
        lines = [
            f"Predictions Made: {self.predictions_made}",
            f"Estimated Hits: {self.estimated_hits}",
            f"Estimated Rate: {self.estimated_rate:.2f}",
            f"Confidence In Estimate: {self.confidence_in_estimate:.2f}",
        ]
        if self.bias_self_assessment:
            lines.append(f"Bias Self-Assessment: {self.bias_self_assessment}")
        if self.trend:
            lines.append(f"Trend: {self.trend}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DescriptionDriftContextItem:
    """Records a gap between a tool's spec description and its actual usage.

    The agent is the only participant who experiences a tool's description
    from the consuming side, which makes this record a form of feedback that
    cannot originate anywhere else. Each entry names the tool, how it is
    actually being used, exactly where the stated description diverges from
    that usage, how often the mismatch recurs, whether it is actively
    causing incorrect calls, and an optional suggested replacement for the
    description text itself.
    """

    tool: str
    actual_usage: str
    description_wrong_about: str
    suggested_fix: str | None = None
    frequency: str | None = None
    blocking: str | None = None
    title: str = "Description Drift"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "description_drift"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the drifted tool and how its description misleads, bounded by max_chars.
        lines = [
            f"Tool: {self.tool}",
            f"Actual Usage: {self.actual_usage}",
            f"Description Wrong About: {self.description_wrong_about}",
        ]
        if self.frequency:
            lines.append(f"Frequency: {self.frequency}")
        if self.blocking:
            lines.append(f"Blocking: {self.blocking}")
        if self.suggested_fix:
            lines.append(f"Suggested Fix: {self.suggested_fix}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "CalibrationSelfReportContextItem",
    "DescriptionDriftContextItem",
    "RecordDisputeContextItem",
    "RitualCheckContextItem",
    "SignalHighlightContextItem",
    "TelemetryGapContextItem",
]
