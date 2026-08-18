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
    Written by vidbyte.tools.builtins.cot_meta and re-exported through
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
    """Records a contradiction between two of the agent's own records."""

    record_a: str
    record_b: str
    contradiction: str
    which_is_wrong: str
    resolution: str | None = None
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
        if self.resolution:
            lines.append(f"Resolution: {self.resolution}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class RitualCheckContextItem:
    """Snapshot of which monitoring calls have become reflexive versus still earning their cost."""

    reflexive: tuple[str, ...]
    still_earning: tuple[str, ...]
    blind_spots: str | None = None
    overall: str | None = None
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
        _extend_section(lines, "Reflexive (Called By Habit)", self.reflexive)
        _extend_section(lines, "Still Earning Their Cost", self.still_earning)
        if self.blind_spots:
            lines.append(f"Blind Spots: {self.blind_spots}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class TelemetryGapContextItem:
    """Records an important event no available tool could capture."""

    event: str
    wanted_to_record: str
    closest_tool: str | None = None
    severity: str | None = None
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
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SignalHighlightContextItem:
    """Records which monitoring record most changed the run's direction."""

    record: str
    changed_direction: str
    would_have_happened: str
    surprise: str | None = None
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
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class CalibrationSelfReportContextItem:
    """Snapshot of the agent's self-estimated prediction calibration."""

    predictions_made: int
    estimated_hits: int
    estimated_rate: float
    confidence_in_estimate: float
    bias_self_assessment: str | None = None
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
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class DescriptionDriftContextItem:
    """Records a gap between a tool's spec description and its actual usage."""

    tool: str
    actual_usage: str
    description_wrong_about: str
    suggested_fix: str | None = None
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
