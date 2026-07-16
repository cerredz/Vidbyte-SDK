"""Context Protocol Header.

Path: vidbyte/lib/dataclasses/specialist_panel.py
Purpose: Separate untrusted model-authored review payloads from trusted runtime report
    provenance and provide the JSON-safe metadata serialization boundary.
Role: SpecialistPanelRuntimeAlgorithm validates outputs against the Pydantic payloads,
    wraps them in frozen records, and attaches SpecialistPanelReport to AgentResult.
Public contracts: finding, requirement-assessment, and review payload models plus
    successful-review, failure, and panel report dataclasses.
Key methods: each to_metadata method emits only JSON-safe public report fields while
    preserving configured role order.
Invariants: Models cannot author role identity, capability grants, provider labels,
    accounting, or timing; runtime records cannot contain raw failed output.
Never: Add producer candidate/evidence text to provenance, accept extra model fields,
    or serialize arbitrary exception/provider objects.
Related: docs/design/context-window-specialist-panel.md and the runtime adapter in
    vidbyte/agents/algorithms/specialist_panel.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


class SpecialistFindingPayload(BaseModel):
    """One evidence-backed defect reported by a specialist."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    severity: Literal["critical", "high", "medium", "low", "info"]
    claim: str = Field(min_length=1, max_length=8_000)
    evidence: str = Field(min_length=1, max_length=16_000)
    recommendation: str = Field(min_length=1, max_length=8_000)
    candidate_excerpt: str | None = Field(default=None, max_length=4_000)


class SpecialistRequirementAssessmentPayload(BaseModel):
    """A specialist's assessment of one configured output requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    requirement: str = Field(min_length=1, max_length=2_000)
    status: Literal["satisfied", "violated", "not_applicable", "uncertain"]
    explanation: str = Field(min_length=1, max_length=8_000)


class SpecialistReviewPayload(BaseModel):
    """Fixed structured envelope returned by every specialist reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    verdict: Literal["pass", "pass_with_findings", "fail"]
    summary: str = Field(min_length=1, max_length=12_000)
    findings: tuple[SpecialistFindingPayload, ...]
    requirement_assessments: tuple[SpecialistRequirementAssessmentPayload, ...]


@dataclass(frozen=True, slots=True)
class SpecialistReviewRecord:
    """Trusted provenance and accounting wrapped around one validated review."""

    specialist_id: str
    responsibility: str
    provider: str
    model: str | None
    tool_names: tuple[str, ...]
    artifact_names: tuple[str, ...]
    output_requirements: tuple[str, ...]
    review: SpecialistReviewPayload
    tokens_used: int | None
    model_call_count: int
    tool_call_count: int
    duration_ms: int

    def to_metadata(self) -> Mapping[str, Any]:
        # Serialize trusted provenance beside JSON-mode validated reviewer data.
        return {
            "specialist_id": self.specialist_id,
            "responsibility": self.responsibility,
            "provider": self.provider,
            "model": self.model,
            "tool_names": list(self.tool_names),
            "artifact_names": list(self.artifact_names),
            "output_requirements": list(self.output_requirements),
            "review": self.review.model_dump(mode="json"),
            "tokens_used": self.tokens_used,
            "model_call_count": self.model_call_count,
            "tool_call_count": self.tool_call_count,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class SpecialistFailureRecord:
    """Content-free classification for one ordinary reviewer failure."""

    specialist_id: str
    responsibility: str
    error_type: Literal["timeout", "execution", "missing_structured_output", "invalid_structured_output", "review_limit"]
    safe_message: str
    duration_ms: int

    def to_metadata(self) -> Mapping[str, Any]:
        # Serialize only trusted identity and the bounded safe failure category.
        return {
            "specialist_id": self.specialist_id,
            "responsibility": self.responsibility,
            "error_type": self.error_type,
            "safe_message": self.safe_message,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class SpecialistPanelReport:
    """Versioned deterministic report for the completed first-round barrier."""

    schema_version: int
    panel_id: str
    candidate_sha256: str
    configured_roles: tuple[str, ...]
    min_successful: int
    reviews: tuple[SpecialistReviewRecord, ...]
    failures: tuple[SpecialistFailureRecord, ...]
    duration_ms: int

    def to_metadata(self) -> Mapping[str, Any]:
        # Preserve configured role order while exposing aggregate panel status.
        return {
            "schema_version": self.schema_version,
            "panel_id": self.panel_id,
            "candidate_sha256": self.candidate_sha256,
            "configured_roles": list(self.configured_roles),
            "min_successful": self.min_successful,
            "successful": len(self.reviews),
            "failed": len(self.failures),
            "partial": bool(self.failures),
            "duration_ms": self.duration_ms,
            "reviews": [dict(review.to_metadata()) for review in self.reviews],
            "failures": [dict(failure.to_metadata()) for failure in self.failures],
        }


__all__ = [
    "SpecialistFailureRecord",
    "SpecialistFindingPayload",
    "SpecialistPanelReport",
    "SpecialistRequirementAssessmentPayload",
    "SpecialistReviewPayload",
    "SpecialistReviewRecord",
]
