"""Epistemic challenge context primitives for general problem solving.

FILE:
    vidbyte/context/primitives/epistemics.py
PURPOSE:
    Preserve challenges to assumptions, mental or causal models, and evidence
    so unresolved uncertainty remains visible across agent iterations.
ROLE IN CODEBASE:
    Supplies descriptive ContextItem implementations for ContextManager without
    deciding truth, source authority, or sufficient proof.
ARCHITECTURE NOTE:
    Frozen, slotted dataclasses keep the records lightweight; each renderer is
    deterministic and applies the shared context-size bound once at the end.
FUNCTION INVENTORY:
    AssumptionChallengeContextItem, ModelChallengeContextItem, and
    EvidenceChallengeContextItem render distinct epistemic disputes.
COMMON MODIFICATION PATTERNS:
    Add opaque evidence or model fields before the lifecycle tail, preserve
    balanced ordering, and render tuple fields with _extend_section.
WHAT NOT TO DO IN THIS FILE:
    Do not clamp confidence, authenticate evidence, select a winning model, or
    register automatic investigation or enforcement behavior here.
KNOWN EDGE CASES:
    Confidence values outside zero-to-one are preserved; empty evidence sections
    mean only that nothing was recorded, not that no evidence exists.
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
class AssumptionChallengeContextItem:
    """Challenge an assumption with its basis, evidence, and falsifier."""

    assumption: str
    basis: str | None = None
    confidence: float | None = None
    evidence: tuple[str, ...] = ()
    falsifier: str | None = None
    validation_method: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Assumption Challenge"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "assumption_challenge"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries an assumption that the current reasoning depends on. Basis and evidence show why it was accepted, while confidence indicates how strongly it is held. The falsifier and validation method define what could disprove or test it. Use the resolution condition to track when the assumption no longer needs active scrutiny.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Assumption: {self.assumption}")
        if self.basis:
            lines.append(f"Basis: {self.basis}")
        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")
        _extend_section(lines, "Evidence", self.evidence)
        if self.falsifier:
            lines.append(f"Falsifier: {self.falsifier}")
        if self.validation_method:
            lines.append(f"Validation Method: {self.validation_method}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class ModelChallengeContextItem:
    """Challenge a mental or causal model against competing explanations."""

    model: str
    questionable_relationships: tuple[str, ...] = ()
    competing_models: tuple[str, ...] = ()
    distinguishing_observations: tuple[str, ...] = ()
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Model Challenge"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "model_challenge"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries a challenge to the model used to explain a system or relationship. Questionable relationships identify links that may be wrong, and competing models provide alternative explanations. Distinguishing observations identify evidence that could tell those models apart. Use this record before relying on a model whose structure has not been separated from its alternatives.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Model: {self.model}")
        _extend_section(
            lines, "Questionable Relationships", self.questionable_relationships
        )
        _extend_section(lines, "Competing Models", self.competing_models)
        _extend_section(
            lines, "Distinguishing Observations", self.distinguishing_observations
        )
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class EvidenceChallengeContextItem:
    """Expose balanced evidence and weaknesses around a contested claim."""

    claim: str
    supporting_evidence: tuple[str, ...] = ()
    counterevidence: tuple[str, ...] = ()
    provenance_issues: tuple[str, ...] = ()
    freshness_concerns: tuple[str, ...] = ()
    bias_risks: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    observation_inference_gap: str | None = None
    status: str = "open"
    severity: str = "concern"
    raised_by: str | None = None
    owner: str | None = None
    resolution_condition: str | None = None
    title: str = "Evidence Challenge"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "evidence_challenge"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders this problem-solving record in deterministic order, bounded by max_chars.
        lines = [
            "This primitive carries an audit of evidence supporting a claim. Supporting and counterevidence show the balance of observations, while provenance and freshness concerns qualify their reliability. Bias risks, missing evidence, and the observation-inference gap identify how the claim could be overstated. Use the resolution condition to decide when the evidence review is sufficient.",
            "",
            f"Status: {self.status}",
            f"Severity: {self.severity}",
        ]
        if self.raised_by:
            lines.append(f"Raised by: {self.raised_by}")
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        lines.append(f"Claim: {self.claim}")
        _extend_section(lines, "Supporting Evidence", self.supporting_evidence)
        _extend_section(lines, "Counterevidence", self.counterevidence)
        _extend_section(lines, "Provenance Issues", self.provenance_issues)
        _extend_section(lines, "Freshness Concerns", self.freshness_concerns)
        _extend_section(lines, "Bias Risks", self.bias_risks)
        _extend_section(lines, "Missing Evidence", self.missing_evidence)
        if self.observation_inference_gap:
            lines.append(f"Observation-Inference Gap: {self.observation_inference_gap}")
        if self.resolution_condition:
            lines.append(f"Resolution Condition: {self.resolution_condition}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "AssumptionChallengeContextItem",
    "EvidenceChallengeContextItem",
    "ModelChallengeContextItem",
]
