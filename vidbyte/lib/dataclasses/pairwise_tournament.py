"""Context Protocol Header

FILE: vidbyte/lib/dataclasses/pairwise_tournament.py
PURPOSE: Defines the strict model-facing decision schema and immutable, content-free
    records emitted by the pairwise-tournament context-window algorithm.
ROLE IN CODEBASE: The public configuration references PairwiseJudgePayload as the
    provider-native output contract; the runtime adapter builds the trusted records;
    callers consume the final report through AgentResult metadata.
ARCHITECTURE NOTE: Model-authored values stop at slot-level decisions. Candidate IDs,
    bracket state, advancement, source provenance, and fallback policy remain trusted
    coordinator data and are never accepted from a judge response.
FUNCTION INVENTORY: PairwiseTournamentReport.to_metadata() renders the public,
    JSON-safe report without candidate, prompt, evidence, rationale, or error bodies.
COMMON MODIFICATION PATTERNS: Add structural report fields here and populate them in
    vidbyte/agents/algorithms/pairwise_tournament.py in the same change.
WHAT NOT TO DO: Do not add candidate text, judge rationale, tool payloads, provider
    responses, or exception messages to any trusted record.
KNOWN EDGE CASES: An abstention has no winner candidate; failed/cancelled legs retain
    only an exception type; lower-seed advancement is explicitly non-consensus.
RELATED DOCS: docs/design/context-window-pairwise-tournament.md.
TESTS: Existing repository tests plus approval-gated manual tournament checks; this
    no-tests feature intentionally adds no test file.
CONCURRENCY MODEL: Records are frozen snapshots assembled after candidate, leg, and
    round barriers, so concurrent tasks never mutate shared report state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


class PairwiseCriterionAssessment(BaseModel):
    """One bounded criterion assessment supplied by a judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion: str = Field(min_length=1, max_length=80)
    assessment: str = Field(min_length=1, max_length=1000)
    satisfied: bool | None = None


class PairwiseJudgePayload(BaseModel):
    """Strict provider-native output accepted from one position-balanced judge leg."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    winner_slot: Literal["A", "B", "abstain"]
    summary: str = Field(min_length=1, max_length=4000)
    criteria: tuple[PairwiseCriterionAssessment, ...] = Field(default=(), max_length=16)


@dataclass(frozen=True, slots=True)
class PairwiseCandidateRecord:
    """Trusted content-free provenance for one successful producer candidate."""

    candidate_id: str
    digest: str
    source_id: str
    provider: str
    model: str
    duration_ms: int
    tokens_used: int | None = None
    model_call_count: int = 0
    tool_call_count: int = 0


@dataclass(frozen=True, slots=True)
class PairwiseLegRecord:
    """Trusted structural outcome for one judge orientation."""

    leg_id: str
    attempt: int
    orientation: Literal["A_B", "B_A"]
    winner_slot: Literal["A", "B", "abstain"] | None
    winner_candidate_id: str | None
    status: Literal["decided", "abstained", "failed", "cancelled"]
    duration_ms: int
    tokens_used: int | None = None
    model_call_count: int = 0
    tool_call_count: int = 0
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class PairwiseMatchRecord:
    """Trusted structural outcome for one bracket match."""

    match_id: str
    round_index: int
    match_index: int
    candidate_ids: tuple[str, str]
    legs: tuple[PairwiseLegRecord, ...]
    winner_candidate_id: str
    resolution: Literal["judge_consensus", "policy_lower_seed", "failure_lower_seed"]
    judge_consensus: bool
    duration_ms: int


@dataclass(frozen=True, slots=True)
class PairwiseRoundRecord:
    """Trusted snapshot of one completed bracket round."""

    round_index: int
    entrant_ids: tuple[str, ...]
    matches: tuple[PairwiseMatchRecord, ...]
    bye_candidate_id: str | None
    advancing_ids: tuple[str, ...]
    duration_ms: int


@dataclass(frozen=True, slots=True)
class PairwiseTournamentReport:
    """Versioned, bounded, content-free report attached to the winning result."""

    schema_version: str
    status: Literal["completed"]
    seeding: str
    candidate_records: tuple[PairwiseCandidateRecord, ...]
    omitted_source_ids: tuple[str, ...]
    seed_order: tuple[str, ...]
    seed_hashes: tuple[str, ...]
    rounds: tuple[PairwiseRoundRecord, ...]
    winner_candidate_id: str
    winner_digest: str
    winner_source_id: str
    winner_provider: str
    winner_model: str
    candidate_count: int
    match_count: int
    judge_leg_count: int
    fallback_count: int
    candidate_tokens_used: int | None
    judge_tokens_used: int | None
    candidate_model_call_count: int
    candidate_tool_call_count: int
    judge_model_call_count: int
    judge_tool_call_count: int
    duration_ms: int
    configured_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        # Converts frozen structural records to a JSON-safe mapping for AgentResult metadata.
        return asdict(self)


__all__ = [
    "PairwiseCandidateRecord",
    "PairwiseCriterionAssessment",
    "PairwiseJudgePayload",
    "PairwiseLegRecord",
    "PairwiseMatchRecord",
    "PairwiseRoundRecord",
    "PairwiseTournamentReport",
]
