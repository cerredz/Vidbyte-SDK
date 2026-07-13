"""Context Protocol Header

Description:
    Defines immutable contracts for aggregate candidates and ledger-driven multi-agent orchestration.
Purpose:
    Makes goals, tasks, evidence, blockers, plans, decisions, dispatches, reports, limits, contexts, and results explicit at package boundaries.
Architecture:
    Frozen dataclasses normalize collections to tuples or read-only mappings and validate identifiers and finite controller limits at construction.
Relations:
    Mutated only through `vidbyte.agents.multi.TaskLedger`; consumed by the controller, orchestrator, transfers, tracing, and public exports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from vidbyte.lib.dataclasses.agents import AgentCard, AgentInput, AgentMessage
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason, OrchestratorAction, TaskStatus


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    # Copies the mapping container while deliberately leaving opaque nested values untouched.
    return MappingProxyType(dict(value or {}))


def _require_text(value: str, field_name: str) -> str:
    # Normalizes one required identifier or human-readable field and rejects blanks.
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-empty string.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return cleaned


@dataclass(frozen=True, slots=True)
class CandidateResult:
    """Successful candidate output from one strategy."""

    index: int
    strategy_name: str
    output: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateFailure:
    """Failed candidate execution summary."""

    index: int
    strategy_name: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class EvaluationDecision:
    """Evaluator decision selecting the best candidate output."""

    selected_index: int
    final_output: str
    grades: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class DagNode:
    """A node in a verified multi-agent orchestration DAG."""

    id: str
    question: str
    depends_on: tuple[str, ...] = ()
    preferred_capability: str | None = None


@dataclass(frozen=True, slots=True)
class Verification:
    """Verifier decision for a synthesized multi-agent answer."""

    approved: bool
    score: float
    gaps: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(slots=True)
class NodeState:
    """Mutable execution state for one DAG node."""

    node: DagNode
    output: str | None = None
    failed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProposerSpec:
    """One proposer in a Mixture-of-Agents aggregation: a provider + model, optional label and prompt override."""

    provider: str
    model: str
    label: str | None = None
    system_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class AggregateConfig:
    """Immutable settings for an aggregate (mixture-of-agents) run."""

    synthesis_system_prompt: str | None = None
    synthesis_prompt_template: str | None = None
    max_candidate_chars: int = 8000
    max_concurrency: int | None = None
    per_proposer_timeout: float | None = None
    min_successful: int = 1


@dataclass(frozen=True, slots=True)
class TaskEvidence:
    """Evidence attached to a task report; verification is developer-owned."""

    source: str
    value: Any
    kind: str = "output"
    verified: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Rejects anonymous evidence and freezes only its SDK-owned mapping container.
        object.__setattr__(self, "source", _require_text(self.source, "TaskEvidence.source"))
        object.__setattr__(self, "kind", _require_text(self.kind, "TaskEvidence.kind"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TaskBlocker:
    """Safe, structured reason a task cannot proceed or complete."""

    code: str
    message: str
    retryable: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Keeps blocker identity meaningful without recursively copying developer metadata.
        object.__setattr__(self, "code", _require_text(self.code, "TaskBlocker.code"))
        object.__setattr__(self, "message", _require_text(self.message, "TaskBlocker.message"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Orchestrator-authored declaration of one task in a plan."""

    task_id: str
    goal: str
    owner: str | None = None
    depends_on: tuple[str, ...] = ()
    required: bool = True
    acceptance_criteria: tuple[str, ...] = ()
    payload: Any = None
    max_attempts: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes plan structure before the ledger performs graph-wide validation.
        object.__setattr__(self, "task_id", _require_text(self.task_id, "TaskSpec.task_id"))
        object.__setattr__(self, "goal", _require_text(self.goal, "TaskSpec.goal"))
        if self.owner is not None and not isinstance(self.owner, str):
            raise ValueError("TaskSpec.owner must be a string or None.")
        object.__setattr__(self, "owner", (self.owner.strip() or None) if self.owner else None)
        object.__setattr__(self, "depends_on", tuple(_require_text(item, "TaskSpec.depends_on") for item in self.depends_on))
        object.__setattr__(self, "acceptance_criteria", tuple(_require_text(item, "TaskSpec.acceptance_criteria") for item in self.acceptance_criteria))
        if self.max_attempts is not None and self.max_attempts <= 0:
            raise ValueError("TaskSpec.max_attempts must be greater than zero when provided.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Immutable source-of-truth view of one task's current ledger state."""

    task_id: str
    goal: str
    owner: str | None
    status: TaskStatus = TaskStatus.PENDING
    depends_on: tuple[str, ...] = ()
    required: bool = True
    acceptance_criteria: tuple[str, ...] = ()
    payload: Any = None
    result: Any = None
    evidence: tuple[TaskEvidence, ...] = ()
    blockers: tuple[TaskBlocker, ...] = ()
    attempts: int = 0
    max_attempts: int = 3
    next_action: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Guards state snapshots against impossible counters and mutable SDK containers.
        object.__setattr__(self, "task_id", _require_text(self.task_id, "TaskRecord.task_id"))
        object.__setattr__(self, "goal", _require_text(self.goal, "TaskRecord.goal"))
        object.__setattr__(self, "owner", _require_text(self.owner, "TaskRecord.owner") if self.owner is not None else None)
        object.__setattr__(self, "status", self.status if isinstance(self.status, TaskStatus) else TaskStatus(self.status))
        object.__setattr__(self, "depends_on", tuple(_require_text(item, "TaskRecord.depends_on") for item in self.depends_on))
        object.__setattr__(self, "acceptance_criteria", tuple(_require_text(item, "TaskRecord.acceptance_criteria") for item in self.acceptance_criteria))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        if not all(isinstance(item, TaskEvidence) for item in self.evidence) or not all(isinstance(item, TaskBlocker) for item in self.blockers):
            raise ValueError("TaskRecord evidence and blockers must use TaskEvidence and TaskBlocker values.")
        if self.attempts < 0 or self.max_attempts <= 0:
            raise ValueError("TaskRecord attempts must be non-negative and max_attempts must be positive.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    """Bounded audit entry for one committed ledger transition."""

    index: int
    kind: str
    revision: int
    task_id: str | None = None
    owner: str | None = None
    message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Ensures event ordering fields remain monotonic-compatible and metadata read-only.
        if self.index < 0 or self.revision < 0:
            raise ValueError("LedgerEvent index and revision must be non-negative.")
        object.__setattr__(self, "kind", _require_text(self.kind, "LedgerEvent.kind"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TaskLedgerSnapshot:
    """Structurally read-only snapshot exposed to orchestrators and developers."""

    run_id: str
    goal: str
    plan_summary: str = ""
    verified_facts: tuple[str, ...] = ()
    facts_to_find: tuple[str, ...] = ()
    facts_to_derive: tuple[str, ...] = ()
    educated_guesses: tuple[str, ...] = ()
    tasks: tuple[TaskRecord, ...] = ()
    next_action: str | None = None
    events: tuple[LedgerEvent, ...] = ()
    revision: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freezes ledger-owned sequences and the top-level metadata mapping for safe sharing.
        object.__setattr__(self, "run_id", _require_text(self.run_id, "TaskLedgerSnapshot.run_id"))
        object.__setattr__(self, "goal", _require_text(self.goal, "TaskLedgerSnapshot.goal"))
        for name in ("verified_facts", "facts_to_find", "facts_to_derive", "educated_guesses"):
            object.__setattr__(self, name, tuple(_require_text(item, f"TaskLedgerSnapshot.{name}") for item in getattr(self, name)))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "events", tuple(self.events))
        if not all(isinstance(item, TaskRecord) for item in self.tasks) or not all(isinstance(item, LedgerEvent) for item in self.events):
            raise ValueError("TaskLedgerSnapshot tasks and events must use TaskRecord and LedgerEvent values.")
        if self.revision < 0:
            raise ValueError("TaskLedgerSnapshot.revision must be non-negative.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class OrchestratorPlan:
    """Initial or replacement task plan authored by an orchestrator."""

    plan_summary: str
    tasks: tuple[TaskSpec, ...]
    verified_facts: tuple[str, ...] = ()
    facts_to_find: tuple[str, ...] = ()
    facts_to_derive: tuple[str, ...] = ()
    educated_guesses: tuple[str, ...] = ()
    next_action: str | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        # Requires a meaningful plan summary and freezes all planner-owned sequences.
        object.__setattr__(self, "plan_summary", _require_text(self.plan_summary, "OrchestratorPlan.plan_summary"))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        if not all(isinstance(item, TaskSpec) for item in self.tasks):
            raise ValueError("OrchestratorPlan.tasks must contain TaskSpec values.")
        for name in ("verified_facts", "facts_to_find", "facts_to_derive", "educated_guesses"):
            object.__setattr__(self, name, tuple(_require_text(item, f"OrchestratorPlan.{name}") for item in getattr(self, name)))


@dataclass(frozen=True, slots=True)
class OrchestratorDecision:
    """One validated delegate, replan, or finish instruction from the orchestrator."""

    action: OrchestratorAction
    task_id: str | None = None
    owner: str | None = None
    instruction: str | None = None
    payload: Any = None
    next_action: str | None = None
    final_answer: str | None = None
    loop_detected: bool = False
    progress_made: bool = False
    rationale: str = ""

    def __post_init__(self) -> None:
        # Rejects ambiguous action shapes before the controller mutates the ledger.
        action = self.action if isinstance(self.action, OrchestratorAction) else OrchestratorAction(self.action)
        object.__setattr__(self, "action", action)
        if action is OrchestratorAction.DELEGATE:
            for name in ("task_id", "owner", "instruction"):
                if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                    raise ValueError(f"OrchestratorDecision.{name} is required for delegate actions.")
            if self.final_answer is not None:
                raise ValueError("OrchestratorDecision.final_answer is only valid for finish actions.")
        elif action is OrchestratorAction.REPLAN:
            if any(value is not None for value in (self.task_id, self.owner, self.instruction, self.payload, self.final_answer)):
                raise ValueError("Replan decisions cannot include dispatch or final-answer fields.")
        else:
            if any(value is not None for value in (self.task_id, self.owner, self.instruction, self.payload)):
                raise ValueError("Finish decisions cannot include dispatch fields.")
            if not isinstance(self.final_answer, str) or not self.final_answer.strip():
                raise ValueError("OrchestratorDecision.final_answer must be non-blank for finish actions.")


@dataclass(frozen=True, slots=True)
class AgentDispatch:
    """Developer-visible request passed from the ledger to one worker transfer."""

    run_id: str
    base_revision: int
    task_id: str
    owner: str
    goal: str
    acceptance_criteria: tuple[str, ...] = ()
    instruction: str = ""
    payload: Any = None
    attempt: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates optimistic-concurrency and retry coordinates before worker invocation.
        for name in ("run_id", "task_id", "owner", "goal", "instruction"):
            object.__setattr__(self, name, _require_text(getattr(self, name), f"AgentDispatch.{name}"))
        if self.base_revision < 0 or self.attempt <= 0:
            raise ValueError("AgentDispatch.base_revision must be non-negative and attempt must be positive.")
        object.__setattr__(self, "acceptance_criteria", tuple(self.acceptance_criteria))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class AgentReport:
    """Structured worker outcome accepted by the TaskLedger."""

    task_id: str
    status: TaskStatus
    result: Any = None
    evidence: tuple[TaskEvidence, ...] = ()
    blockers: tuple[TaskBlocker, ...] = ()
    next_action: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Restricts reports to terminal attempt states and freezes SDK-owned containers.
        object.__setattr__(self, "task_id", _require_text(self.task_id, "AgentReport.task_id"))
        status = self.status if isinstance(self.status, TaskStatus) else TaskStatus(self.status)
        if status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED):
            raise ValueError("AgentReport.status must be completed, failed, or blocked.")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        if not all(isinstance(item, TaskEvidence) for item in self.evidence) or not all(isinstance(item, TaskBlocker) for item in self.blockers):
            raise ValueError("AgentReport evidence and blockers must use TaskEvidence and TaskBlocker values.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class MultiAgentSettings:
    """Finite budgets and completion policy for one multi-agent team."""

    max_rounds: int = 20
    max_replans: int = 3
    max_task_attempts: int = 3
    replan_after_stalls: int = 3
    orchestrator_parse_retries: int = 2
    run_timeout_seconds: float | None = None
    orchestrator_timeout_seconds: float | None = None
    worker_timeout_seconds: float | None = None
    require_verified_evidence: bool = False
    allow_partial_finish: bool = False
    return_partial_on_limit: bool = True
    max_events: int = 500

    def __post_init__(self) -> None:
        # Makes every loop finite and rejects invalid timeout or event-history budgets early.
        for name in ("max_rounds", "max_task_attempts", "replan_after_stalls", "max_events"):
            if getattr(self, name) <= 0:
                raise ValueError(f"MultiAgentSettings.{name} must be greater than zero.")
        for name in ("max_replans", "orchestrator_parse_retries"):
            if getattr(self, name) < 0:
                raise ValueError(f"MultiAgentSettings.{name} must be non-negative.")
        for name in ("run_timeout_seconds", "orchestrator_timeout_seconds", "worker_timeout_seconds"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"MultiAgentSettings.{name} must be positive when provided.")


@dataclass(frozen=True, slots=True)
class OrchestrationContext:
    """Explicit context passed to every orchestrator phase."""

    request: AgentInput
    team_instructions: str
    team: tuple[AgentCard, ...]
    ledger: TaskLedgerSnapshot
    settings: MultiAgentSettings
    context: BaseContext | None = None
    history: tuple[AgentMessage, ...] = ()
    round: int = 0
    replans: int = 0
    stalls: int = 0
    last_report: AgentReport | None = None

    def __post_init__(self) -> None:
        # Shares only immutable team/history containers and valid non-negative controller counters.
        if not isinstance(self.request, AgentInput) or not isinstance(self.request.prompt, str) or not self.request.prompt.strip():
            raise ValueError("OrchestrationContext.request must be an AgentInput with a non-blank prompt.")
        object.__setattr__(self, "team_instructions", _require_text(self.team_instructions, "OrchestrationContext.team_instructions"))
        object.__setattr__(self, "team", tuple(self.team))
        object.__setattr__(self, "history", tuple(self.history))
        if not self.team or not all(isinstance(item, AgentCard) for item in self.team):
            raise ValueError("OrchestrationContext.team must contain at least one AgentCard.")
        if not isinstance(self.ledger, TaskLedgerSnapshot) or not isinstance(self.settings, MultiAgentSettings):
            raise ValueError("OrchestrationContext requires TaskLedgerSnapshot and MultiAgentSettings values.")
        if not all(isinstance(item, AgentMessage) for item in self.history):
            raise ValueError("OrchestrationContext.history must contain AgentMessage values.")
        if min(self.round, self.replans, self.stalls) < 0:
            raise ValueError("OrchestrationContext counters must be non-negative.")


@dataclass(frozen=True, slots=True)
class FinalizationContext:
    """Terminal context used to produce the user-facing team answer."""

    orchestration: OrchestrationContext
    stop_reason: MultiAgentStopReason
    completed: bool
    candidate_answer: str | None = None
    finish_decision: OrchestratorDecision | None = None

    def __post_init__(self) -> None:
        # Normalizes the public stop enum while preserving the immutable terminal context.
        if not isinstance(self.orchestration, OrchestrationContext):
            raise ValueError("FinalizationContext.orchestration must be OrchestrationContext.")
        object.__setattr__(self, "stop_reason", self.stop_reason if isinstance(self.stop_reason, MultiAgentStopReason) else MultiAgentStopReason(self.stop_reason))


@dataclass(frozen=True, slots=True)
class MultiAgentResult:
    """Complete observable result of one MultiAgent controller run."""

    content: str
    completed: bool
    stop_reason: MultiAgentStopReason
    ledger: TaskLedgerSnapshot
    rounds: int
    replans: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Keeps terminal counters valid and result metadata structurally read-only.
        object.__setattr__(self, "content", _require_text(self.content, "MultiAgentResult.content"))
        object.__setattr__(self, "stop_reason", self.stop_reason if isinstance(self.stop_reason, MultiAgentStopReason) else MultiAgentStopReason(self.stop_reason))
        if not isinstance(self.ledger, TaskLedgerSnapshot):
            raise ValueError("MultiAgentResult.ledger must be TaskLedgerSnapshot.")
        if self.rounds < 0 or self.replans < 0:
            raise ValueError("MultiAgentResult rounds and replans must be non-negative.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
