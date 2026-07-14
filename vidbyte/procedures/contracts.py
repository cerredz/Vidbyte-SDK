"""Context Protocol Header

Path: vidbyte/procedures/contracts.py
Purpose: Define immutable procedure-learning, verification, retrieval, and outcome
contracts without owning persistence or promotion policy.
Architecture: Candidates enter the library; versioned records leave it; ProcedureRef
pins every later load/outcome to exact immutable content.
Exports: ProcedureStatus, candidate/record/ref/summary/match/outcome contracts,
verification contracts, limits, and promotion authority protocol.
Invariants: CANDIDATE input cannot claim status or verification; VERIFIED records carry
task, drift, exact-fingerprint, and fidelity provenance; public records are frozen.
Do not: Infer active heads, mutate stores, or authorize promotion in this module.
Related: docs/design/long-running-paradigm.md sections 6.1-6.2.
Tests: Existing package verification plus inline smoke checks; no new test pack under
the explicitly approved no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ProcedureStatus(str, Enum):
    """Lifecycle status for one immutable record version."""

    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ProcedureCandidate:
    """Untrusted candidate content staged by a curator or application."""

    namespace: str
    title: str
    summary: str
    body: str
    applicability: tuple[str, ...]
    preconditions: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    tags: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    environment_fingerprint: str = ""
    source_run_id: str = ""
    source_task_id: str = ""
    source_attempt_id: str = ""
    source_evidence_event_ids: tuple[str, ...] = ()
    proposed_procedure_id: str | None = None

    def __post_init__(self) -> None:
        # Normalize model/caller text before the library hashes or validates content.
        for name in ("namespace", "title", "summary", "body", "environment_fingerprint", "source_run_id", "source_task_id", "source_attempt_id"):
            object.__setattr__(self, name, str(getattr(self, name)).strip())
        for name in ("applicability", "preconditions", "expected_outcomes", "tags", "required_tools", "source_evidence_event_ids"):
            object.__setattr__(self, name, self._text_tuple(getattr(self, name)))
        if self.proposed_procedure_id is not None:
            object.__setattr__(self, "proposed_procedure_id", self.proposed_procedure_id.strip() or None)

    @staticmethod
    def _text_tuple(values: Sequence[object]) -> tuple[str, ...]:
        # Preserve item order while removing blank collection entries.
        return tuple(text for item in values if (text := str(item).strip()))


@dataclass(frozen=True, slots=True)
class ProcedureLimits:
    """Deterministic candidate bounds enforced before staging."""

    max_title_chars: int = 200
    max_summary_chars: int = 1200
    max_body_chars: int = 20000
    max_list_items: int = 32
    max_list_item_chars: int = 500


@dataclass(frozen=True, slots=True)
class ProcedureCheckResult:
    """One deterministic or model-backed procedure-fidelity check."""

    validator_id: str
    validator_version: str
    config_fingerprint: str
    required: bool
    passed: bool
    evidence: tuple[str, ...] = ()
    error_code: str = ""
    error_message: str = ""
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class ProcedureVerificationEvidence:
    """Provenance required to promote an exact staged candidate."""

    run_id: str
    task_id: str
    attempt_id: str
    source_task_verification_event_id: str
    source_drift_review_event_id: str
    candidate_content_fingerprint: str
    criteria: tuple[str, ...]
    observations: tuple[str, ...]
    source_task_validator_results: tuple[ProcedureCheckResult, ...]
    procedure_fidelity_results: tuple[ProcedureCheckResult, ...]
    verifier_name: str
    verified_at: str
    evidence_hash: str


@dataclass(frozen=True, slots=True)
class ProcedureRef:
    """Stable handle for one exact immutable procedure version."""

    namespace: str
    procedure_id: str
    version: int
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProcedureRecord:
    """One immutable audit version in a procedure identity chain."""

    schema_version: int
    procedure_id: str
    version: int
    namespace: str
    learning_operation_id: str
    status: ProcedureStatus
    title: str
    summary: str
    body: str
    applicability: tuple[str, ...]
    preconditions: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    tags: tuple[str, ...]
    required_tools: tuple[str, ...]
    environment_fingerprint: str
    content_fingerprint: str
    source_run_id: str
    source_task_id: str
    source_attempt_id: str
    source_evidence_event_ids: tuple[str, ...]
    verification: ProcedureVerificationEvidence | None
    reason: str
    created_at: str
    supersedes_version: int | None

    @property
    def ref(self) -> ProcedureRef:
        # Pin consumers to this version and fingerprint instead of a mutable latest id.
        return ProcedureRef(self.namespace, self.procedure_id, self.version, self.content_fingerprint)


@dataclass(frozen=True, slots=True)
class ProcedureSummary:
    """Compact retrieval card that omits the full procedure body."""

    ref: ProcedureRef
    title: str
    summary: str
    applicability: tuple[str, ...]
    preconditions: tuple[str, ...]
    tags: tuple[str, ...]
    required_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProcedureMatch:
    """Ranked compact procedure card."""

    summary: ProcedureSummary
    score: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProcedureOutcome:
    """Immutable observed result for an exact loaded procedure ref."""

    outcome_id: str
    procedure: ProcedureRef
    run_id: str
    task_id: str
    attempt_id: str
    succeeded: bool
    suspected_failure: bool
    reason: str
    created_at: str


class ProcedurePromotionAuthority(Protocol):
    """Application authority that revalidates evidence against committed state."""

    def authorize(self, candidate: ProcedureRecord, evidence: ProcedureVerificationEvidence) -> None:
        # Reject promotion by raising when ledger evidence is absent, stale, or misaligned.
        ...


__all__ = [
    "ProcedureCandidate", "ProcedureCheckResult", "ProcedureLimits", "ProcedureMatch",
    "ProcedureOutcome", "ProcedurePromotionAuthority", "ProcedureRecord", "ProcedureRef",
    "ProcedureStatus", "ProcedureSummary", "ProcedureVerificationEvidence",
]
