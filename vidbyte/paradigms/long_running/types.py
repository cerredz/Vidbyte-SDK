"""Context Protocol Header

Path: vidbyte/paradigms/long_running/types.py
Purpose: Define immutable public contracts for durable planning, attempts, verification,
drift, state, options, settings, usage, and final results.
Architecture: Task definitions are separate from runtime task states; every accepted
result and procedure use is pinned by hashes/refs; settings compose shared role config.
Exports: Long-running enums, dataclasses, and BehaviorFingerprintProvider.
Invariants: The original prompt is retained exactly, caller contract entries retain
their text/order, task definition hashes exclude mutable state, and records are frozen.
Do not: Perform model calls, ledger I/O, graph routing, or procedure promotion here.
Related: docs/design/long-running-paradigm.md sections 6.4-6.10.
Tests: Existing import/settings verification plus inline smoke checks; no new tests by
the explicitly approved design-doc-no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from vidbyte.paradigms.types import AgentRoleSettings
from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError
from vidbyte.procedures import ProcedureOutcome, ProcedureRecord, ProcedureRef, ProcedureSummary
from vidbyte.procedures.serialization import ProcedureIdentity

if TYPE_CHECKING:
    from vidbyte.paradigms.long_running.ledger import RunLedgerSnapshot


class LongRunningTaskStatus(str, Enum):
    """Runtime status for one immutable task definition."""

    PENDING = "pending"
    ACTIVE = "active"
    VERIFIED = "verified"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    BLOCKED = "blocked"


class LongRunningStopReason(str, Enum):
    """Finite reason a controller returned or paused."""

    COMPLETED = "completed"
    PARTIAL_BLOCKED = "partial_blocked"
    VERIFICATION_EXHAUSTED = "verification_exhausted"
    NO_PROGRESS = "no_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIMEOUT = "timeout"
    USAGE_UNAVAILABLE = "usage_unavailable"
    RECOVERY_REQUIRED = "recovery_required"
    CANCELLED = "cancelled"
    INTERNAL_ERROR = "internal_error"


class LongRunningRunStatus(str, Enum):
    """Durable lifecycle state for one run."""

    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETED = "completed"
    FAILED = "failed"


class InterruptedAttemptPolicy(str, Enum):
    """Caller-selected resume policy for an incomplete attempt."""

    FAIL_CLOSED = "fail_closed"
    RETRY_IF_READ_ONLY = "retry_if_read_only"
    ACCEPT_CALLER_RECONCILIATION = "accept_caller_reconciliation"


class DriftDecision(str, Enum):
    """Bounded global-auditor routing decision."""

    CONTINUE = "continue"
    REPLAN = "replan"
    SYNTHESIZE = "synthesize"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class GoalContract:
    """Immutable root request and acceptance boundary."""

    original_prompt: str
    success_criteria: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Preserve exact caller text while freezing collection order and rejecting blanks.
        if not self.original_prompt.strip():
            raise ValueError("GoalContract.original_prompt cannot be blank.")
        object.__setattr__(self, "success_criteria", _exact_text_tuple(self.success_criteria))
        object.__setattr__(self, "invariants", _exact_text_tuple(self.invariants))
        object.__setattr__(self, "non_goals", _exact_text_tuple(self.non_goals))

    def with_planner_additions(self, *, success_criteria: Sequence[str] = (), invariants: Sequence[str] = (), non_goals: Sequence[str] = ()) -> "GoalContract":
        # Append non-duplicates after caller entries without weakening or replacing them.
        return replace(
            self,
            success_criteria=_append_unique(self.success_criteria, success_criteria),
            invariants=_append_unique(self.invariants, invariants),
            non_goals=_append_unique(self.non_goals, non_goals),
        )


@dataclass(frozen=True, slots=True)
class LongRunningTask:
    """Immutable subproblem definition in the task dependency DAG."""

    task_id: str
    title: str
    instructions: str
    dependencies: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    procedure_query: str
    priority: int = 0
    owned_paths: tuple[str, ...] = ()
    read_only_paths: tuple[str, ...] = ()
    verification_expectations: tuple[str, ...] = ()
    expected_artifacts: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    definition_hash: str = ""

    def __post_init__(self) -> None:
        # Normalize model-authored definition fields and compute a stable content hash.
        for name in ("task_id", "title", "instructions", "procedure_query"):
            object.__setattr__(self, name, str(getattr(self, name)).strip())
        for name in ("dependencies", "acceptance_criteria", "owned_paths", "read_only_paths", "verification_expectations", "expected_artifacts", "notes"):
            object.__setattr__(self, name, _text_tuple(getattr(self, name)))
        if not self.definition_hash:
            object.__setattr__(self, "definition_hash", self.compute_definition_hash())

    def compute_definition_hash(self) -> str:
        # Hash definition content only so runtime status cannot rewrite plan identity.
        return ProcedureIdentity.hash_mapping({
            "task_id": self.task_id, "title": self.title, "instructions": self.instructions,
            "dependencies": list(self.dependencies), "acceptance_criteria": list(self.acceptance_criteria),
            "procedure_query": self.procedure_query, "priority": self.priority,
            "owned_paths": list(self.owned_paths), "read_only_paths": list(self.read_only_paths),
            "verification_expectations": list(self.verification_expectations),
            "expected_artifacts": list(self.expected_artifacts), "notes": list(self.notes),
        })


@dataclass(frozen=True, slots=True)
class LongRunningTaskState:
    """Mutable-in-successor-record runtime state for one task id."""

    task_id: str
    status: LongRunningTaskStatus = LongRunningTaskStatus.PENDING
    attempt_count: int = 0
    verified_result_id: str = ""
    invalidation_reason: str = ""
    consumed_dependency_hashes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TaskGraph:
    """Immutable versioned task-definition DAG."""

    version: int
    tasks: tuple[LongRunningTask, ...]
    rationale: str = ""

    def __post_init__(self) -> None:
        # Freeze task ordering because scheduler tie-breaking depends on it.
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "rationale", self.rationale.strip())

    def task(self, task_id: str) -> LongRunningTask | None:
        # Resolve one definition without exposing a mutable index.
        return next((task for task in self.tasks if task.task_id == task_id), None)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Content-addressed artifact reference produced by an attempt."""

    artifact_id: str
    uri: str
    media_type: str
    summary: str
    content_hash: str
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    """Parsed public result of one fresh worker or repair role run."""

    attempt_id: str
    task_id: str
    attempt_number: int
    strategy: str
    summary: str
    artifacts: tuple[ArtifactRef, ...]
    evidence: tuple[str, ...]
    loaded_procedures: tuple[ProcedureRef, ...]
    blockers: tuple[str, ...]
    transcript_event_id: str
    tokens_used: int | None
    isolation_lease: Mapping[str, Any] = field(default_factory=dict)
    non_read_tool_succeeded: bool = False
    interrupted: bool = False

    def __post_init__(self) -> None:
        # Freeze evidence, refs, artifacts, and serializable isolation metadata.
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "evidence", _text_tuple(self.evidence))
        object.__setattr__(self, "loaded_procedures", tuple(self.loaded_procedures))
        object.__setattr__(self, "blockers", _text_tuple(self.blockers))
        object.__setattr__(self, "isolation_lease", dict(self.isolation_lease))


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Committed verified result for one exact task definition."""

    result_id: str
    task_id: str
    definition_hash: str
    summary: str
    detail: str
    artifacts: tuple[ArtifactRef, ...]
    evidence: tuple[str, ...]
    verification_event_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ValidatorResult:
    """Normalized result from one trusted task validator."""

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
class CriterionResult:
    """Verifier judgment for one stable acceptance criterion."""

    criterion_id: str
    criterion: str
    passed: bool
    observations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Combined model and deterministic validation result."""

    passed: bool
    criteria: tuple[CriterionResult, ...]
    evidence: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    repair_instructions: tuple[str, ...] = ()
    failure_signature: str = ""
    suspected_procedures: tuple[ProcedureRef, ...] = ()
    requires_replan: bool = False
    validator_results: tuple[ValidatorResult, ...] = ()
    transcript_event_id: str = ""


@dataclass(frozen=True, slots=True)
class DriftReview:
    """Independent global alignment judgment after local task verification/failure."""

    decision: DriftDecision
    aligned: bool
    issues: tuple[str, ...] = ()
    invalidate_task_ids: tuple[str, ...] = ()
    proposed_work: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Content-addressed public evidence captured in the append-only ledger."""

    evidence_id: str
    kind: str
    source_event_id: str
    content_hash: str
    summary: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Copy caller mappings so later mutation cannot rewrite verification evidence.
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True, slots=True)
class TaskValidationContext:
    """Trusted deterministic validator input for one exact task attempt."""

    run_id: str
    contract: GoalContract
    task: LongRunningTask
    attempt: TaskAttempt
    evidence: tuple[EvidenceRecord, ...]
    artifact_refs: tuple[ArtifactRef, ...]
    workspace_root: str
    deadline_at: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProcedureValidationContext:
    """Trusted procedure-validator input pinned to source task/drift evidence."""

    run_id: str
    contract: GoalContract
    task: LongRunningTask
    attempt: TaskAttempt
    task_verification: VerificationResult
    drift_review: DriftReview
    candidate: ProcedureRecord
    source_event_ids: tuple[str, ...]
    source_records: tuple[EvidenceRecord, ...]
    available_tools: tuple[str, ...]
    environment_fingerprint: str
    deadline_at: str | None


@dataclass(frozen=True, slots=True)
class LongRunningRunOptions:
    """Typed start-only caller inputs that form the immutable goal contract."""

    run_id: str | None = None
    success_criteria: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Preserve exact contract text and copy caller metadata.
        object.__setattr__(self, "success_criteria", _exact_text_tuple(self.success_criteria))
        object.__setattr__(self, "invariants", _exact_text_tuple(self.invariants))
        object.__setattr__(self, "non_goals", _exact_text_tuple(self.non_goals))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class LongRunningResumeOptions:
    """Typed caller authority for settings change and interrupted-attempt recovery."""

    allow_settings_change: bool = False
    settings_change_reason: str = ""
    interrupted_attempt_policy: InterruptedAttemptPolicy = InterruptedAttemptPolicy.FAIL_CLOSED
    reconciliation_reason: str = ""


class BehaviorFingerprintProvider(Protocol):
    """Stable safe configuration description for durable resume compatibility."""

    def behavior_fingerprint(self) -> Mapping[str, Any]:
        # Return deterministic non-secret behavior fields, never object ids or credentials.
        ...


@dataclass(frozen=True, slots=True)
class LongRunningUsage:
    """Observed provider token usage and completeness marker."""

    observed_input_tokens: int = 0
    observed_output_tokens: int = 0
    calls_with_unknown_usage: int = 0
    complete: bool = True

    @property
    def observed_total_tokens(self) -> int:
        # Return only provider-reported input plus output tokens.
        return self.observed_input_tokens + self.observed_output_tokens


@dataclass(frozen=True, slots=True)
class LongRunningState:
    """Compact committed controller state stored at every ledger head."""

    run_id: str
    status: LongRunningRunStatus
    contract: GoalContract
    graph: TaskGraph
    task_states: tuple[LongRunningTaskState, ...]
    task_results: tuple[TaskResult, ...]
    attempts: tuple[TaskAttempt, ...]
    verifications: tuple[VerificationResult, ...]
    drift_reviews: tuple[DriftReview, ...]
    usage: LongRunningUsage
    settings_fingerprint: str
    revision: int
    cycle_count: int
    replan_count: int
    started_at: str
    deadline_at: str | None
    stop_reason: LongRunningStopReason | None
    promoted_procedures: tuple[ProcedureSummary, ...] = ()
    procedure_outcomes: tuple[ProcedureOutcome, ...] = ()
    final_output: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze every aggregate and copy safe metadata for append-only successor records.
        for name in ("task_states", "task_results", "attempts", "verifications", "drift_reviews", "promoted_procedures", "procedure_outcomes"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class LongRunningSettings:
    """Construction settings and hard bounds for every controller role and loop."""

    planner: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-planner"))
    worker: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-worker"))
    repairer: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-repairer"))
    verifier: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-verifier"))
    curator: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-curator"))
    procedure_verifier: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-procedure-verifier"))
    synthesizer: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-synthesizer"))
    auditor: AgentRoleSettings = field(default_factory=lambda: AgentRoleSettings(name="long-running-auditor"))
    max_tasks: int = 32
    max_plan_attempts: int = 3
    max_attempts_per_task: int = 3
    max_replans: int = 4
    max_cycles: int = 128
    max_no_progress_cycles: int = 2
    max_controller_runtime_seconds: float | None = None
    max_observed_tokens: int | None = None
    require_usage_reporting_for_token_budget: bool = True
    procedure_search_limit: int = 5
    max_procedure_body_chars: int = 20000
    retire_after_suspected_failures: int = 3
    max_finalization_attempts: int = 2
    require_procedure_promotion: bool = False
    include_minimal_toolset: bool = True
    worker_include_execution: bool = False
    worker_include_write: bool = False
    unsafe_allow_unisolated_side_effects: bool = False
    default_tool_root: str | Path = "."
    procedure_namespace: str = "default"
    environment_fingerprint: str = ""
    component_fingerprints: Mapping[str, str] = field(default_factory=dict)
    max_visible_tool_result_chars: int = 4000
    max_role_messages: int = 80
    max_role_history_chars: int = 60000
    max_context_capsule_chars: int = 48000
    max_contract_chars: int = 20000
    max_task_instructions_chars: int = 12000
    max_plan_summary_chars: int = 12000
    max_dependency_summary_chars: int = 4000
    max_task_result_detail_chars: int = 16000
    max_artifact_excerpt_chars: int = 12000
    max_procedure_card_chars: int = 1200
    max_loaded_procedures_per_role: int = 3
    max_loaded_procedure_chars_per_role: int = 30000
    max_loaded_verified_context_items_per_role: int = 3
    max_loaded_verified_context_chars_per_role: int = 30000
    max_latest_evidence_chars: int = 12000
    max_procedure_verification_evidence_chars: int = 30000
    max_visible_context_tokens: int | None = None
    require_ledger_persistence: bool = True

    def __post_init__(self) -> None:
        # Normalize path/mappings and fail before a run can inherit invalid hard bounds.
        object.__setattr__(self, "default_tool_root", Path(self.default_tool_root))
        object.__setattr__(self, "procedure_namespace", self.procedure_namespace.strip())
        object.__setattr__(self, "environment_fingerprint", self.environment_fingerprint.strip())
        object.__setattr__(self, "component_fingerprints", dict(self.component_fingerprints))
        self._validate()

    def with_overrides(self, **overrides: Any) -> "LongRunningSettings":
        # Return a new validated settings object without mutating harness defaults.
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)

    def _validate(self) -> None:
        # Reject unsafe sizes, missing role names, and impossible aggregate relationships.
        positive = {
            name: getattr(self, name) for name in (
                "max_tasks", "max_plan_attempts", "max_attempts_per_task", "max_replans", "max_cycles",
                "max_no_progress_cycles", "procedure_search_limit", "max_procedure_body_chars",
                "retire_after_suspected_failures", "max_finalization_attempts", "max_visible_tool_result_chars",
                "max_role_messages", "max_role_history_chars", "max_context_capsule_chars", "max_contract_chars",
                "max_task_instructions_chars", "max_plan_summary_chars", "max_dependency_summary_chars",
                "max_task_result_detail_chars", "max_artifact_excerpt_chars", "max_procedure_card_chars",
                "max_loaded_procedures_per_role", "max_loaded_procedure_chars_per_role",
                "max_loaded_verified_context_items_per_role", "max_loaded_verified_context_chars_per_role",
                "max_latest_evidence_chars", "max_procedure_verification_evidence_chars",
            )
        }
        invalid = tuple(name for name, value in positive.items() if int(value) < 1)
        if invalid:
            raise LongRunningConfigurationError("LongRunningSettings values must be positive.", details={"fields": invalid})
        for name in ("max_controller_runtime_seconds", "max_observed_tokens", "max_visible_context_tokens"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise LongRunningConfigurationError("Optional LongRunningSettings budget must be positive when set.", details={"field": name})
        if not self.procedure_namespace:
            raise LongRunningConfigurationError("LongRunningSettings.procedure_namespace cannot be blank.")
        try:
            ProcedureIdentity.validate_id(self.procedure_namespace, field_name="procedure_namespace")
        except Exception as exc:
            raise LongRunningConfigurationError("LongRunningSettings.procedure_namespace is invalid.", details={"namespace": self.procedure_namespace}) from exc
        roles = (self.planner, self.worker, self.repairer, self.verifier, self.curator, self.procedure_verifier, self.synthesizer, self.auditor)
        if any(not role.name for role in roles):
            raise LongRunningConfigurationError("Every long-running role must have a non-empty name.")


@dataclass(frozen=True, slots=True)
class LongRunningResult:
    """Caller-facing result built only from committed ledger state."""

    run_id: str
    status: LongRunningRunStatus
    resumable: bool
    final_output: str
    stop_reason: LongRunningStopReason
    succeeded: bool
    contract: GoalContract
    graph: TaskGraph
    task_states: tuple[LongRunningTaskState, ...]
    task_results: tuple[TaskResult, ...]
    attempts: tuple[TaskAttempt, ...]
    verifications: tuple[VerificationResult, ...]
    promoted_procedures: tuple[ProcedureSummary, ...]
    procedure_outcomes: tuple[ProcedureOutcome, ...]
    usage: LongRunningUsage
    ledger: "RunLedgerSnapshot"
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _text_tuple(values: Sequence[object]) -> tuple[str, ...]:
    # Normalize model-authored list items for deterministic hashes and comparisons.
    return tuple(text for item in values if (text := str(item).strip()))


def _exact_text_tuple(values: Sequence[object]) -> tuple[str, ...]:
    # Filter blank caller entries while preserving every retained character verbatim.
    return tuple(text for item in values if (text := str(item)) and text.strip())


def _append_unique(existing: Sequence[str], additions: Sequence[str]) -> tuple[str, ...]:
    # Preserve caller order/text and append only normalized non-duplicate planner entries.
    output = list(existing)
    seen = {item.strip().casefold() for item in existing}
    for item in additions:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            output.append(text)
            seen.add(key)
    return tuple(output)


__all__ = [
    "AgentRoleSettings", "ArtifactRef", "BehaviorFingerprintProvider", "CriterionResult",
    "DriftDecision", "DriftReview", "EvidenceRecord", "GoalContract",
    "InterruptedAttemptPolicy", "LongRunningResult", "LongRunningResumeOptions",
    "LongRunningRunOptions", "LongRunningRunStatus", "LongRunningSettings",
    "LongRunningState", "LongRunningStopReason", "LongRunningTask",
    "LongRunningTaskState", "LongRunningTaskStatus", "LongRunningUsage",
    "ProcedureValidationContext", "TaskAttempt", "TaskGraph", "TaskResult",
    "TaskValidationContext", "ValidatorResult", "VerificationResult",
]
