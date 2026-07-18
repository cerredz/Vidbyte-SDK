"""Context Protocol Header

FILE: vidbyte/context/algorithms/critique_adjudicate_revise.py
PURPOSE: Defines the public configuration and deterministic provenance boundary for
    critique-adjudicate-revise. This file parses untrusted stage JSON, assigns stable
    IDs, grounds evidence, and constructs accepted findings; it never runs models.
ROLE IN CODEBASE: Called by the runtime adapter in
    vidbyte/agents/algorithms/critique_adjudicate_revise.py and exported through the
    context/root namespaces. It reads catalog prompts and shared SDK error/tool types.
ARCHITECTURE NOTE: The adjudicator is allowed to select references, not write accepted
    prose. Runtime-owned copying is the load-bearing quarantine boundary documented in
    docs/design/context-window-critique-adjudicate-revise.md.
FUNCTION INVENTORY: CritiqueAdjudicateReviseAlgorithm validates configuration, parses
    critic/revision output, and validates adjudication references. ReviewStageAccess
    owns exact per-stage allowlists and execution limits. Structured parsing is owned by
    methods and nested helpers on the public dataclasses (no free module functions).
COMMON MODIFICATION PATTERNS: Add schema fields here, update all three prompt assets,
    then update runtime envelope construction and public docs in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not invoke providers; the runtime adapter owns I/O.
    2. Do not accept fenced or substring JSON. 3. Do not let adjudicator-authored text
    cross into AcceptedFinding. 4. Do not normalize evidence before substring checks.
KNOWN EDGE CASES: Empty critic findings are valid; omission findings may cite the task;
    exact Unicode substrings are required; every raw finding must be disposed once.
COMMON ERRORS: ConfigurationError reports static invalid settings. AgentExecutionError
    reports stage output or provenance violations with sanitized structural details.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/context-window-critique-adjudicate-revise.md
TESTS: Existing context-algorithm, prompt-catalog, and runtime regression suites.
CONCURRENCY MODEL: Values are frozen and parser calls use no shared mutable state, so
    one configuration can safely parse concurrent critic results.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.lib.constants.critique_adjudicate_revise import (
    EVIDENCE_SOURCE_KINDS,
    FINDING_CATEGORIES,
    FINDING_SEVERITIES,
    MAX_CANDIDATE_CHARS,
    MAX_CRITICS,
    MAX_EVIDENCE,
    MAX_FIELD_CHARS,
    MAX_FINDINGS,
    MAX_STAGE_INPUT_CHARS,
    MAX_STAGE_ITERATIONS,
    MAX_STAGE_TOOL_CALLS,
    REJECTION_REASONS,
    RESERVED_SOURCES,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.prompts import Prompts


class CriticFailurePolicy(str, Enum):
    """Controls whether critic fan-out requires every result or a configured quorum."""

    REQUIRE_ALL = "require_all"
    REQUIRE_QUORUM = "require_quorum"


class StageFailurePolicy(str, Enum):
    """Controls terminal adjudication and revision failure behavior."""

    RAISE = "raise"
    RETURN_CANDIDATE = "return_candidate"


@dataclass(frozen=True, slots=True)
class ReviewStageAccess:
    """Exact artifacts, tools, and loop bounds available to one isolated stage."""

    allowed_artifact_names: tuple[str, ...] = ()
    allowed_tool_names: tuple[str, ...] = ()
    max_iterations: int = 4
    max_tool_calls: int = 4

    def __post_init__(self) -> None:
        # Normalizes immutable allowlists and rejects ambiguous or unusable limits.
        object.__setattr__(self, "allowed_artifact_names", self._normalize_names(self.allowed_artifact_names, "allowed_artifact_names"))
        object.__setattr__(self, "allowed_tool_names", self._normalize_names(self.allowed_tool_names, "allowed_tool_names"))
        self._require_bounded_positive(self.max_iterations, "max_iterations", MAX_STAGE_ITERATIONS)
        self._require_bounded_positive(self.max_tool_calls, "max_tool_calls", MAX_STAGE_TOOL_CALLS)

    @staticmethod
    def _normalize_names(value: object, field_name: str) -> tuple[str, ...]:
        # Converts a non-string sequence into unique non-empty exact allowlist names.
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ConfigurationError(f"{field_name} must be a sequence of strings.")
        names = tuple(value)
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ConfigurationError(f"{field_name} must contain only non-empty strings.")
        if len(names) != len(set(names)):
            raise ConfigurationError(f"{field_name} must not contain duplicate names.")
        return names

    @staticmethod
    def _require_bounded_positive(value: int, field_name: str, maximum: int) -> None:
        # Requires an integer within a documented denial-of-service safeguard bound.
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ConfigurationError(f"{field_name} must be between 1 and {maximum}.")


@dataclass(frozen=True, slots=True)
class FindingEvidence:
    """One runtime-identified, exact-substring evidence record."""

    evidence_id: str
    source_kind: str
    source_name: str
    locator: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class CriticFinding:
    """One runtime-identified critic finding with structurally grounded evidence."""

    finding_id: str
    critic_id: str
    category: str
    severity: str
    claim: str
    recommendation: str
    evidence: tuple[FindingEvidence, ...]


@dataclass(frozen=True, slots=True)
class AcceptedFinding:
    """Runtime-owned projection of one canonical raw finding and selected evidence."""

    accepted_id: str
    canonical_finding_id: str
    source_finding_ids: tuple[str, ...]
    category: str
    severity: str
    claim: str
    recommendation: str
    evidence: tuple[FindingEvidence, ...]


@dataclass(frozen=True, slots=True)
class _AdjudicationProjection:
    """Validated accepted findings and content-free disposition metadata."""

    accepted: tuple[AcceptedFinding, ...]
    accepted_groups: tuple[tuple[str, ...], ...]
    rejected_groups: tuple[tuple[tuple[str, ...], str], ...]


@dataclass(frozen=True, slots=True)
class CritiqueAdjudicateReviseAlgorithm:
    """Immutable public configuration for critique-adjudicate-revise."""

    critic_count: int = 3
    min_successful_critics: int | None = None
    critic_failure_policy: CriticFailurePolicy = CriticFailurePolicy.REQUIRE_ALL
    adjudication_failure_policy: StageFailurePolicy = StageFailurePolicy.RAISE
    revision_failure_policy: StageFailurePolicy = StageFailurePolicy.RAISE
    critic_access: ReviewStageAccess = field(default_factory=ReviewStageAccess)
    adjudicator_access: ReviewStageAccess = field(default_factory=ReviewStageAccess)
    revision_access: ReviewStageAccess = field(default_factory=ReviewStageAccess)
    allow_parallel_critic_tools: bool = False
    critic_provider: str | None = None
    critic_model: str | None = None
    adjudicator_provider: str | None = None
    adjudicator_model: str | None = None
    revision_provider: str | None = None
    revision_model: str | None = None
    critic_timeout_seconds: float = 90.0
    adjudication_timeout_seconds: float = 90.0
    revision_timeout_seconds: float = 120.0
    max_findings_per_critic: int = 8
    max_evidence_per_finding: int = 4
    max_field_chars: int = 2_000
    max_candidate_chars: int = 100_000
    max_stage_input_chars: int = 250_000
    critic_prompt: str | None = None
    adjudicator_prompt: str | None = None
    reviser_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Coerces policies and validates every static bound before a producer runs.
        object.__setattr__(self, "critic_failure_policy", self._coerce_enum(self.critic_failure_policy, CriticFailurePolicy, "critic_failure_policy"))
        object.__setattr__(self, "adjudication_failure_policy", self._coerce_enum(self.adjudication_failure_policy, StageFailurePolicy, "adjudication_failure_policy"))
        object.__setattr__(self, "revision_failure_policy", self._coerce_enum(self.revision_failure_policy, StageFailurePolicy, "revision_failure_policy"))
        for name in ("critic_access", "adjudicator_access", "revision_access"):
            if not isinstance(getattr(self, name), ReviewStageAccess):
                raise ConfigurationError(f"{name} must be a ReviewStageAccess instance.")
        if not isinstance(self.allow_parallel_critic_tools, bool):
            raise ConfigurationError("allow_parallel_critic_tools must be a bool.")
        self._validate_counts()
        self._validate_limits()
        self._validate_stage_models()
        self._validate_prompt_overrides()
        self._validate_metadata()

    def critic_system_prompt_text(self) -> str:
        # Returns the configured critic role prompt or its catalog-backed default.
        return self.critic_prompt or Prompts().get(Prompt.CRITIQUE_ADJUDICATE_REVISE_CRITIC)

    def adjudicator_system_prompt_text(self) -> str:
        # Returns the configured adjudicator role prompt or its catalog-backed default.
        return self.adjudicator_prompt or Prompts().get(Prompt.CRITIQUE_ADJUDICATE_REVISE_ADJUDICATOR)

    def reviser_system_prompt_text(self) -> str:
        # Returns the configured revision role prompt or its catalog-backed default.
        return self.reviser_prompt or Prompts().get(Prompt.CRITIQUE_ADJUDICATE_REVISE_REVISER)

    def parse_critic_output(self, critic_id: str, payload: str, sources: Mapping[str, str], tool_calls: Sequence[ToolCallContext]) -> tuple[CriticFinding, ...]:
        # Parses one whole critic JSON document and grounds every evidence excerpt.
        return self._StructuredReviewParser(self).parse_critic(critic_id, payload, sources, tool_calls)

    def validate_adjudication(self, payload: str, findings: Sequence[CriticFinding]) -> _AdjudicationProjection:
        # Validates complete one-time dispositions and builds accepted source projections.
        return self._StructuredReviewParser(self).parse_adjudication(payload, findings)

    def build_accepted_findings(self, payload: str, findings: Sequence[CriticFinding]) -> tuple[AcceptedFinding, ...]:
        # Returns only runtime-built accepted findings for public callers.
        return self.validate_adjudication(payload, findings).accepted

    def parse_revision_output(self, payload: str, accepted: Sequence[AcceptedFinding]) -> tuple[str, tuple[str, ...]]:
        # Parses the complete revision object and enforces exact accepted-ID coverage.
        return self._StructuredReviewParser(self).parse_revision(payload, accepted)

    def _validate_counts(self) -> None:
        # Rejects unbounded critic fan-out and internally inconsistent quorum policy.
        if isinstance(self.critic_count, bool) or not isinstance(self.critic_count, int) or not 1 <= self.critic_count <= MAX_CRITICS:
            raise ConfigurationError(f"critic_count must be between 1 and {MAX_CRITICS}.")
        if self.critic_failure_policy is CriticFailurePolicy.REQUIRE_QUORUM:
            if self.min_successful_critics is None:
                raise ConfigurationError("min_successful_critics is required when critic_failure_policy is require_quorum.")
            if isinstance(self.min_successful_critics, bool) or not isinstance(self.min_successful_critics, int) or not 1 <= self.min_successful_critics <= self.critic_count:
                raise ConfigurationError("min_successful_critics must be between 1 and critic_count.")
        elif self.min_successful_critics is not None:
            raise ConfigurationError("min_successful_critics is only valid with critic_failure_policy=require_quorum.")
        if self.critic_count > 1 and self.critic_access.allowed_tool_names and not self.allow_parallel_critic_tools:
            raise ConfigurationError("Parallel critic tools require allow_parallel_critic_tools=True because custom tool concurrency safety is unknown.")

    def _validate_limits(self) -> None:
        # Bounds stage latency, parsed content, candidate size, and serialized input.
        self._require_bounded_positive(self.max_findings_per_critic, "max_findings_per_critic", MAX_FINDINGS)
        self._require_bounded_positive(self.max_evidence_per_finding, "max_evidence_per_finding", MAX_EVIDENCE)
        self._require_bounded_positive(self.max_field_chars, "max_field_chars", MAX_FIELD_CHARS)
        self._require_bounded_positive(self.max_candidate_chars, "max_candidate_chars", MAX_CANDIDATE_CHARS)
        self._require_bounded_positive(self.max_stage_input_chars, "max_stage_input_chars", MAX_STAGE_INPUT_CHARS)
        for name in ("critic_timeout_seconds", "adjudication_timeout_seconds", "revision_timeout_seconds"):
            self._require_positive(getattr(self, name), name)

    def _validate_stage_models(self) -> None:
        # Requires provider/model overrides to be supplied as complete stage pairs.
        for stage in ("critic", "adjudicator", "revision"):
            provider = getattr(self, f"{stage}_provider")
            model = getattr(self, f"{stage}_model")
            if (provider is None) != (model is None):
                raise ConfigurationError(f"{stage}_provider and {stage}_model must both be set or both be omitted.")
            if provider is not None and (not isinstance(provider, str) or not provider.strip()):
                raise ConfigurationError(f"{stage}_provider must be a non-empty string when provided.")
            if model is not None and (not isinstance(model, str) or not model.strip()):
                raise ConfigurationError(f"{stage}_model must be a non-empty string when provided.")

    def _validate_prompt_overrides(self) -> None:
        # Rejects blank role overrides without imposing formatting placeholders.
        for name in ("critic_prompt", "adjudicator_prompt", "reviser_prompt"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ConfigurationError(f"{name} must be a non-empty string when provided.")

    def _validate_metadata(self) -> None:
        # Ensures additive public metadata can be merged and serialized predictably.
        if not isinstance(self.metadata, Mapping):
            raise ConfigurationError("metadata must be a mapping.")
        for key in self.metadata:
            if not isinstance(key, str):
                raise ConfigurationError(f"metadata keys must be strings, found {type(key).__name__}.")

    @staticmethod
    def _coerce_enum(value: object, enum_type: type[Enum], field_name: str) -> Enum:
        # Converts string-compatible public settings into their declared enum type.
        try:
            return enum_type(value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{field_name} has unsupported value {value!r}.") from exc

    @staticmethod
    def _require_positive(value: int | float, field_name: str) -> None:
        # Rejects bools, non-numeric values, and zero-or-negative execution limits.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    @staticmethod
    def _require_bounded_positive(value: int, field_name: str, maximum: int) -> None:
        # Requires an integer within a documented denial-of-service safeguard bound.
        ReviewStageAccess._require_bounded_positive(value, field_name, maximum)

    class _StructuredReviewParser:
        """Strict parser and provenance validator for all downstream model outputs.

        Nested on the public algorithm dataclass so validation helpers stay with the
        config surface rather than as free module functions.
        """

        def __init__(self, algorithm: CritiqueAdjudicateReviseAlgorithm) -> None:
            # Retains immutable bounds while keeping each parse operation stateless.
            self.algorithm = algorithm

        def parse_critic(self, critic_id: str, payload: str, sources: Mapping[str, str], tool_calls: Sequence[ToolCallContext]) -> tuple[CriticFinding, ...]:
            # Converts strict critic JSON into runtime-identified grounded findings.
            root = self._load_object(payload, "critic", {"findings"})
            raw_findings = self._list(root["findings"], "critic.findings", self.algorithm.max_findings_per_critic)
            return tuple(self._parse_finding(critic_id, index, raw, sources, tool_calls) for index, raw in enumerate(raw_findings, start=1))

        def parse_adjudication(self, payload: str, findings: Sequence[CriticFinding]) -> _AdjudicationProjection:
            # Converts reference-only dispositions into canonical accepted projections.
            root = self._load_object(payload, "adjudicator", {"accepted_groups", "rejected_groups"})
            finding_map = {finding.finding_id: finding for finding in findings}
            if len(finding_map) != len(tuple(findings)):
                self._fail("adjudicator", "Runtime supplied duplicate raw finding IDs.", duplicate_count=len(tuple(findings)) - len(finding_map))
            accepted_raw = self._list(root["accepted_groups"], "adjudicator.accepted_groups", len(finding_map))
            rejected_raw = self._list(root["rejected_groups"], "adjudicator.rejected_groups", len(finding_map))
            accepted_groups = tuple(self._parse_accepted_group(raw, finding_map) for raw in accepted_raw)
            rejected_groups = tuple(self._parse_rejected_group(raw, finding_map) for raw in rejected_raw)
            self._validate_complete_coverage(finding_map, accepted_groups, rejected_groups)
            accepted = self._build_accepted(accepted_groups, finding_map)
            accepted_ids = tuple(tuple(group[1]) for group in sorted(accepted_groups, key=lambda group: min(group[1])))
            rejected_ids = tuple((tuple(group[0]), group[1]) for group in sorted(rejected_groups, key=lambda group: min(group[0])))
            return _AdjudicationProjection(accepted=accepted, accepted_groups=accepted_ids, rejected_groups=rejected_ids)

        def parse_revision(self, payload: str, accepted: Sequence[AcceptedFinding]) -> tuple[str, tuple[str, ...]]:
            # Validates a non-empty bounded revision and exact one-time accepted-ID coverage.
            root = self._load_object(payload, "revision", {"revised_candidate", "applied_finding_ids"})
            revised = self._text(root["revised_candidate"], "revision.revised_candidate", self.algorithm.max_candidate_chars, strip=False)
            raw_ids = self._list(root["applied_finding_ids"], "revision.applied_finding_ids", len(tuple(accepted)))
            applied = tuple(self._text(value, "revision.applied_finding_ids[]", self.algorithm.max_field_chars) for value in raw_ids)
            if len(applied) != len(set(applied)):
                self._fail("revision", "applied_finding_ids must not contain duplicates.", applied_count=len(applied))
            expected = tuple(item.accepted_id for item in accepted)
            if set(applied) != set(expected) or len(applied) != len(expected):
                self._fail("revision", "applied_finding_ids must exactly cover every accepted finding once.", expected_count=len(expected), applied_count=len(applied))
            return revised, tuple(sorted(applied))

        def _parse_finding(self, critic_id: str, finding_index: int, raw: object, sources: Mapping[str, str], tool_calls: Sequence[ToolCallContext]) -> CriticFinding:
            # Validates one finding object, assigns its ID, and grounds each evidence item.
            obj = self._object(raw, "critic.finding", {"category", "severity", "claim", "recommendation", "evidence"})
            category = self._enum_text(obj["category"], "critic.finding.category", FINDING_CATEGORIES)
            severity = self._enum_text(obj["severity"], "critic.finding.severity", FINDING_SEVERITIES)
            claim = self._text(obj["claim"], "critic.finding.claim", self.algorithm.max_field_chars)
            recommendation = self._text(obj["recommendation"], "critic.finding.recommendation", self.algorithm.max_field_chars)
            raw_evidence = self._list(obj["evidence"], "critic.finding.evidence", self.algorithm.max_evidence_per_finding, require_nonempty=True)
            finding_id = f"{critic_id}:finding-{finding_index:03d}"
            evidence = tuple(self._parse_evidence(finding_id, index, value, sources, tool_calls) for index, value in enumerate(raw_evidence, start=1))
            return CriticFinding(finding_id=finding_id, critic_id=critic_id, category=category, severity=severity, claim=claim, recommendation=recommendation, evidence=evidence)

        def _parse_evidence(self, finding_id: str, evidence_index: int, raw: object, sources: Mapping[str, str], tool_calls: Sequence[ToolCallContext]) -> FindingEvidence:
            # Validates one exact excerpt against its declared immutable source or tool result.
            obj = self._object(raw, "critic.evidence", {"source_kind", "source_name", "locator", "excerpt"})
            source_kind = self._enum_text(obj["source_kind"], "critic.evidence.source_kind", EVIDENCE_SOURCE_KINDS)
            source_name = self._text(obj["source_name"], "critic.evidence.source_name", self.algorithm.max_field_chars)
            locator = self._text(obj["locator"], "critic.evidence.locator", self.algorithm.max_field_chars)
            excerpt = self._text(obj["excerpt"], "critic.evidence.excerpt", self.algorithm.max_field_chars, strip=False)
            self._ground_evidence(source_kind, source_name, locator, excerpt, sources, tool_calls)
            return FindingEvidence(evidence_id=f"{finding_id}:evidence-{evidence_index:03d}", source_kind=source_kind, source_name=source_name, locator=locator, excerpt=excerpt)

        def _ground_evidence(self, source_kind: str, source_name: str, locator: str, excerpt: str, sources: Mapping[str, str], tool_calls: Sequence[ToolCallContext]) -> None:
            # Enforces source naming and exact-substring grounding before adjudication.
            if source_kind == "task":
                self._ground_named_source(source_name, "original_task", excerpt, sources)
                return
            if source_kind == "candidate":
                self._ground_named_source(source_name, "candidate", excerpt, sources)
                return
            if source_kind == "artifact":
                if source_name in RESERVED_SOURCES or source_name not in sources:
                    self._fail("critic", "Artifact evidence references an unavailable source.", source_kind=source_kind, source_name=source_name)
                if excerpt not in sources[source_name]:
                    self._fail("critic", "Artifact evidence excerpt is not an exact source substring.", source_kind=source_kind, source_name=source_name)
                return
            matched = any(call.tool_name == source_name and call.state is ToolCallState.SUCCEEDED and call.result is not None and excerpt in call.result.output and (call.call_id is None or locator == call.call_id) for call in tool_calls)
            if not matched:
                self._fail("critic", "Tool evidence is not grounded in a successful allow-listed call result.", source_kind=source_kind, source_name=source_name)

        def _ground_named_source(self, source_name: str, expected_name: str, excerpt: str, sources: Mapping[str, str]) -> None:
            # Requires the reserved source name and a byte-equivalent substring match.
            if source_name != expected_name or expected_name not in sources:
                self._fail("critic", "Evidence references the wrong reserved source name.", source_name=source_name, expected_source=expected_name)
            if excerpt not in sources[expected_name]:
                self._fail("critic", "Evidence excerpt is not an exact source substring.", source_name=source_name)

        def _parse_accepted_group(self, raw: object, finding_map: Mapping[str, CriticFinding]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
            # Validates one accepted equivalence group without admitting authored prose.
            obj = self._object(raw, "adjudicator.accepted_group", {"canonical_finding_id", "source_finding_ids", "evidence_ids"})
            canonical = self._text(obj["canonical_finding_id"], "adjudicator.canonical_finding_id", self.algorithm.max_field_chars)
            source_ids = self._id_list(obj["source_finding_ids"], "adjudicator.source_finding_ids", len(finding_map))
            evidence_ids = self._id_list(obj["evidence_ids"], "adjudicator.evidence_ids", max(1, len(finding_map) * self.algorithm.max_evidence_per_finding))
            if canonical not in source_ids:
                self._fail("adjudicator", "canonical_finding_id must belong to source_finding_ids.", canonical_finding_id=canonical)
            if any(finding_id not in finding_map for finding_id in source_ids):
                self._fail("adjudicator", "Accepted group references an unknown finding ID.", source_count=len(source_ids))
            allowed_evidence = {evidence.evidence_id for finding_id in source_ids for evidence in finding_map[finding_id].evidence}
            if any(evidence_id not in allowed_evidence for evidence_id in evidence_ids):
                self._fail("adjudicator", "Accepted group references evidence outside its source findings.", evidence_count=len(evidence_ids))
            return canonical, tuple(sorted(source_ids)), tuple(sorted(evidence_ids))

        def _parse_rejected_group(self, raw: object, finding_map: Mapping[str, CriticFinding]) -> tuple[tuple[str, ...], str]:
            # Validates one bounded rejection disposition over known finding IDs.
            obj = self._object(raw, "adjudicator.rejected_group", {"finding_ids", "reason_code"})
            finding_ids = self._id_list(obj["finding_ids"], "adjudicator.rejected_group.finding_ids", len(finding_map))
            reason = self._enum_text(obj["reason_code"], "adjudicator.rejected_group.reason_code", REJECTION_REASONS)
            if any(finding_id not in finding_map for finding_id in finding_ids):
                self._fail("adjudicator", "Rejected group references an unknown finding ID.", finding_count=len(finding_ids))
            return tuple(sorted(finding_ids)), reason

        def _validate_complete_coverage(self, finding_map: Mapping[str, CriticFinding], accepted_groups: Sequence[tuple[str, tuple[str, ...], tuple[str, ...]]], rejected_groups: Sequence[tuple[tuple[str, ...], str]]) -> None:
            # Requires every raw finding to receive exactly one accepted or rejected disposition.
            covered = [finding_id for _, source_ids, _ in accepted_groups for finding_id in source_ids]
            covered.extend(finding_id for finding_ids, _ in rejected_groups for finding_id in finding_ids)
            if len(covered) != len(set(covered)):
                self._fail("adjudicator", "A raw finding appears in more than one disposition.", disposition_reference_count=len(covered))
            if set(covered) != set(finding_map):
                self._fail("adjudicator", "Every raw finding must appear in exactly one disposition.", expected_count=len(finding_map), covered_count=len(covered))

        def _build_accepted(self, groups: Sequence[tuple[str, tuple[str, ...], tuple[str, ...]]], finding_map: Mapping[str, CriticFinding]) -> tuple[AcceptedFinding, ...]:
            # Sorts groups and copies canonical fields so the judge cannot invent revision prose.
            built: list[AcceptedFinding] = []
            for accepted_index, (canonical_id, source_ids, evidence_ids) in enumerate(sorted(groups, key=lambda group: min(group[1])), start=1):
                canonical = finding_map[canonical_id]
                evidence_map = {evidence.evidence_id: evidence for finding_id in source_ids for evidence in finding_map[finding_id].evidence}
                built.append(AcceptedFinding(accepted_id=f"accepted-{accepted_index:03d}", canonical_finding_id=canonical_id, source_finding_ids=source_ids, category=canonical.category, severity=canonical.severity, claim=canonical.claim, recommendation=canonical.recommendation, evidence=tuple(evidence_map[evidence_id] for evidence_id in evidence_ids)))
            return tuple(built)

        def _load_object(self, payload: str, stage: str, required: set[str]) -> Mapping[str, Any]:
            # Parses the whole model response as JSON and rejects surrounding scratch text.
            if not isinstance(payload, str) or not payload.strip():
                self._fail(stage, "Stage output must be a non-empty JSON object.")
            if len(payload) > self.algorithm.max_stage_input_chars:
                self._fail(stage, "Stage output exceeds the configured structural size limit.", output_chars=len(payload))
            try:
                raw = json.loads(payload)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                self._fail(stage, "Stage output must be one complete JSON document.", error_type=type(exc).__name__)
            return self._object(raw, stage, required)

        def _object(self, value: object, label: str, required: set[str]) -> Mapping[str, Any]:
            # Requires an object with exactly the declared keys and no hidden extension fields.
            if not isinstance(value, dict):
                self._fail(label, "Expected a JSON object.", actual_type=type(value).__name__)
            keys = set(value)
            if keys != required:
                self._fail(label, "JSON object keys do not match the strict schema.", missing=tuple(sorted(required - keys)), unknown=tuple(sorted(keys - required)))
            return value

        def _list(self, value: object, label: str, maximum: int, require_nonempty: bool = False) -> list[Any]:
            # Requires a bounded JSON array and optionally rejects empty collections.
            if not isinstance(value, list):
                self._fail(label, "Expected a JSON array.", actual_type=type(value).__name__)
            if require_nonempty and not value:
                self._fail(label, "Expected at least one array item.")
            if len(value) > maximum:
                self._fail(label, "JSON array exceeds the configured item limit.", item_count=len(value), maximum=maximum)
            return value

        def _id_list(self, value: object, label: str, maximum: int) -> tuple[str, ...]:
            # Parses a non-empty unique ID list without changing identifier text.
            raw = self._list(value, label, maximum, require_nonempty=True)
            ids = tuple(self._text(item, f"{label}[]", self.algorithm.max_field_chars) for item in raw)
            if len(ids) != len(set(ids)):
                self._fail(label, "Identifier list must not contain duplicates.", item_count=len(ids))
            return ids

        def _text(self, value: object, label: str, maximum: int, strip: bool = True) -> str:
            # Requires bounded non-blank text while optionally preserving exact whitespace.
            if not isinstance(value, str) or not value.strip():
                self._fail(label, "Expected a non-empty string.", actual_type=type(value).__name__)
            if len(value) > maximum:
                self._fail(label, "String exceeds the configured character limit.", character_count=len(value), maximum=maximum)
            return value.strip() if strip else value

        def _enum_text(self, value: object, label: str, allowed: frozenset[str]) -> str:
            # Requires one exact lower-case member of a bounded protocol enum.
            text = self._text(value, label, self.algorithm.max_field_chars)
            if text not in allowed:
                self._fail(label, "String is not a supported enum value.", allowed=tuple(sorted(allowed)))
            return text

        @staticmethod
        def _fail(stage: str, message: str, **details: Any) -> None:
            # Raises a stage-specific structural error without echoing untrusted payload text.
            raise AgentExecutionError(f"critique-adjudicate-revise {stage} validation failed: {message}", details={"algorithm": "critique_adjudicate_revise", "stage": stage, **details})


__all__ = [
    "AcceptedFinding",
    "CriticFailurePolicy",
    "CriticFinding",
    "CritiqueAdjudicateReviseAlgorithm",
    "FindingEvidence",
    "ReviewStageAccess",
    "StageFailurePolicy",
]
