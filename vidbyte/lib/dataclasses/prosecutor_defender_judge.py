"""Context Protocol Header

FILE: vidbyte/lib/dataclasses/prosecutor_defender_judge.py
PURPOSE: Defines strict model-authored payloads and immutable SDK-owned debate
records for the prosecutor/defender/judge context-window algorithm.
ROLE IN CODEBASE: Isolated review runtimes validate provider JSON against the
payload models; the runtime adapter converts those payloads into trusted records.
ARCHITECTURE NOTE: Models never own allegation identity or the final verdict.
The SDK assigns IDs and derives survivors from exact ordered decisions.
FUNCTION INVENTORY: Payload classes constrain provider output; record classes
serialize the validated transcript and stage provenance into JSON-safe metadata.
WHAT NOT TO DO: Do not add a judge-authored overall verdict, a defender claim
list, or a judge field that can carry a replacement allegation.
KNOWN EDGE CASES: Empty allegation, defense, and decision lists are valid; exact
one-to-one ordering is enforced by the runtime validator, not these schemas.
RELATED DOCS: docs/design/context-window-prosecutor-defender-judge.md.
TEST FILES: No new tests are authorized by the approved no-tests design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_MAX_PAYLOAD_CHARS = 2_000_000


class EvidenceSource(str, Enum):
    """Permitted source categories for allegation and defense citations."""

    ORIGINAL_TASK = "original_task"
    CANDIDATE = "candidate"
    ARTIFACT = "artifact"
    TOOL = "tool"
    ALLEGATION = "allegation"


class AllegationSeverity(str, Enum):
    """Normalized prosecutor severity labels."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NOTE = "note"


class DefensePosition(str, Enum):
    """Allowed defender positions for one existing allegation."""

    CONCEDE = "concede"
    CONTEST = "contest"
    PARTIAL = "partial"


class JudgeDecision(str, Enum):
    """Allowed judge outcomes for one existing allegation."""

    SURVIVES = "survives"
    REJECTED = "rejected"


class JudgeReasonCode(str, Enum):
    """Reason codes whose polarity is checked by deterministic SDK logic."""

    SUPPORTED_UNREBUTTED = "supported_unrebutted"
    SUPPORTED_AFTER_REBUTTAL = "supported_after_rebuttal"
    CONCEDED = "conceded"
    UNSUPPORTED = "unsupported"
    REBUTTED = "rebutted"
    DUPLICATE = "duplicate"
    OUT_OF_SCOPE = "out_of_scope"


class EvidenceCitationPayload(BaseModel):
    """One model-authored citation whose source and excerpt are revalidated."""

    model_config = ConfigDict(extra="forbid")
    source: EvidenceSource
    source_name: str | None = Field(default=None, max_length=200)
    excerpt: str = Field(min_length=1, max_length=_MAX_PAYLOAD_CHARS)
    support: str = Field(min_length=1, max_length=_MAX_PAYLOAD_CHARS)


class ProsecutorAllegationPayload(BaseModel):
    """One evidence-bearing allegation without an authoritative ID field."""

    model_config = ConfigDict(extra="forbid")
    severity: AllegationSeverity
    category: str = Field(min_length=1, max_length=_MAX_PAYLOAD_CHARS)
    claim: str = Field(min_length=1, max_length=_MAX_PAYLOAD_CHARS)
    candidate_excerpt: str = Field(default="", max_length=_MAX_PAYLOAD_CHARS)
    evidence: list[EvidenceCitationPayload] = Field(min_length=1, max_length=100)
    recommended_fix: str = Field(min_length=1, max_length=_MAX_PAYLOAD_CHARS)


class ProsecutorReportPayload(BaseModel):
    """The prosecutor's bounded summary and allegation list."""

    model_config = ConfigDict(extra="forbid")
    summary: str = Field(default="", max_length=_MAX_PAYLOAD_CHARS)
    allegations: list[ProsecutorAllegationPayload] = Field(default_factory=list, max_length=100)


class DefenseResponsePayload(BaseModel):
    """One allegation-specific response with no field for unrelated claims."""

    model_config = ConfigDict(extra="forbid")
    allegation_id: str = Field(pattern=r"^ALG-[0-9]{3}$")
    position: DefensePosition
    response: str = Field(min_length=1, max_length=_MAX_PAYLOAD_CHARS)
    evidence: list[EvidenceCitationPayload] = Field(default_factory=list, max_length=100)


class DefenderReportPayload(BaseModel):
    """The canonical ordered list of allegation-specific defenses."""

    model_config = ConfigDict(extra="forbid")
    responses: list[DefenseResponsePayload] = Field(default_factory=list, max_length=100)


class JudgeDecisionPayload(BaseModel):
    """One verdict for an existing ID, structurally unable to add a claim."""

    model_config = ConfigDict(extra="forbid")
    allegation_id: str = Field(pattern=r"^ALG-[0-9]{3}$")
    decision: JudgeDecision
    reason_code: JudgeReasonCode
    rationale: str = Field(min_length=1, max_length=_MAX_PAYLOAD_CHARS)


class JudgeReportPayload(BaseModel):
    """The canonical ordered list of per-allegation judge decisions."""

    model_config = ConfigDict(extra="forbid")
    decisions: list[JudgeDecisionPayload] = Field(default_factory=list, max_length=100)


@dataclass(frozen=True, slots=True)
class EvidenceCitationRecord:
    """Validated citation whose excerpt exists in its named source body."""

    source: EvidenceSource
    source_name: str | None
    excerpt: str
    support: str

    def to_dict(self) -> dict[str, Any]:
        # Serializes one trusted citation without provider-private fields.
        return {"source": self.source.value, "source_name": self.source_name, "excerpt": self.excerpt, "support": self.support}


@dataclass(frozen=True, slots=True)
class AllegationRecord:
    """SDK-identified normalized allegation in canonical prosecutor order."""

    allegation_id: str
    severity: AllegationSeverity
    category: str
    claim: str
    candidate_excerpt: str
    evidence: tuple[EvidenceCitationRecord, ...]
    recommended_fix: str

    def to_dict(self) -> dict[str, Any]:
        # Serializes the immutable allegation for downstream stages and metadata.
        return {"allegation_id": self.allegation_id, "severity": self.severity.value, "category": self.category, "claim": self.claim, "candidate_excerpt": self.candidate_excerpt, "evidence": [item.to_dict() for item in self.evidence], "recommended_fix": self.recommended_fix}


@dataclass(frozen=True, slots=True)
class DefenseRecord:
    """Validated response paired to exactly one allegation ID."""

    allegation_id: str
    position: DefensePosition
    response: str
    evidence: tuple[EvidenceCitationRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        # Serializes one defense while preserving allegation identity.
        return {"allegation_id": self.allegation_id, "position": self.position.value, "response": self.response, "evidence": [item.to_dict() for item in self.evidence]}


@dataclass(frozen=True, slots=True)
class JudgeDecisionRecord:
    """Validated judge outcome for exactly one existing allegation ID."""

    allegation_id: str
    decision: JudgeDecision
    reason_code: JudgeReasonCode
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        # Serializes the judge outcome without permitting replacement findings.
        return {"allegation_id": self.allegation_id, "decision": self.decision.value, "reason_code": self.reason_code.value, "rationale": self.rationale}


@dataclass(frozen=True, slots=True)
class DebateStageRecord:
    """Content-free stage provenance and bounded execution accounting."""

    role: str
    status: Literal["completed", "failed", "not_started"]
    provider: str | None = None
    model: str | None = None
    artifact_names: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    stop_reason: str | None = None
    duration_ms: float | None = None
    iteration_count: int = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    tokens_used: int | None = None
    tool_calls: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Serializes safe stage provenance without raw tool arguments or results.
        return {"role": self.role, "status": self.status, "provider": self.provider, "model": self.model, "artifact_names": list(self.artifact_names), "tool_names": list(self.tool_names), "stop_reason": self.stop_reason, "duration_ms": self.duration_ms, "iteration_count": self.iteration_count, "model_call_count": self.model_call_count, "tool_call_count": self.tool_call_count, "tokens_used": self.tokens_used, "tool_calls": [dict(item) for item in self.tool_calls], "metadata": dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class ProsecutorDefenderJudgeReport:
    """Complete successful review transcript and SDK-derived verdict."""

    candidate_sha256: str
    verdict: Literal["pass", "needs_changes"]
    surviving_allegation_ids: tuple[str, ...]
    allegations: tuple[AllegationRecord, ...]
    defenses: tuple[DefenseRecord, ...]
    decisions: tuple[JudgeDecisionRecord, ...]
    stages: tuple[DebateStageRecord, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Builds the versioned JSON-safe metadata envelope for AgentResult.
        return {"schema_version": 1, "status": "reviewed", "reviewed": True, "review_only": True, "candidate_revised": False, "candidate_sha256": self.candidate_sha256, "verdict": self.verdict, "allegation_count": len(self.allegations), "defense_count": len(self.defenses), "decision_count": len(self.decisions), "surviving_allegation_ids": list(self.surviving_allegation_ids), "allegations": [item.to_dict() for item in self.allegations], "defenses": [item.to_dict() for item in self.defenses], "decisions": [item.to_dict() for item in self.decisions], "stages": {stage.role: stage.to_dict() for stage in self.stages}, "metadata": dict(self.metadata)}


__all__ = [
    "AllegationRecord",
    "AllegationSeverity",
    "DebateStageRecord",
    "DefenderReportPayload",
    "DefensePosition",
    "DefenseRecord",
    "DefenseResponsePayload",
    "EvidenceCitationPayload",
    "EvidenceCitationRecord",
    "EvidenceSource",
    "JudgeDecision",
    "JudgeDecisionPayload",
    "JudgeDecisionRecord",
    "JudgeReasonCode",
    "JudgeReportPayload",
    "ProsecutorAllegationPayload",
    "ProsecutorDefenderJudgeReport",
    "ProsecutorReportPayload",
]
