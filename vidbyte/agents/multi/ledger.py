"""Context Protocol Header

Description:
    Implements the run-local TaskLedger for multi-agent orchestration.
Purpose:
    Owns every structural task transition, retry counter, dependency invariant,
    evidence record, blocker, revision, and bounded event exposed to the controller.
Architecture:
    - TaskLedger: Mutable authority with immutable snapshots at every boundary.
    - Validation methods: Check plan identity, ownership, dependencies, and cycles.
Relations:
    Mutated by multi-agent runtime collaborators; read by orchestrators and transfers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.agents.multi.ledger_reports import TaskLedgerReportReducer
from vidbyte.agents.multi.ledger_validation import TaskLedgerValidator
from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, AgentReport, LedgerEvent, MultiAgentSettings, OrchestratorPlan, TaskBlocker, TaskLedgerSnapshot, TaskRecord, TaskSpec
from vidbyte.lib.enums.multi_agent import TaskStatus
from vidbyte.lib.errors import TaskLedgerError


class TaskLedger:
    """Sole mutable structural authority for one isolated multi-agent run."""

    def __init__(self, *, run_id: str, goal: str, owners: Sequence[str], settings: MultiAgentSettings, metadata: Mapping[str, Any] | None = None) -> None:
        # Creates an empty ledger whose first legal structural operation is apply_plan().
        cleaned_owners = TaskLedgerValidator.validate_configuration(run_id, goal, owners, settings)
        self._run_id = run_id.strip()
        self._goal = goal.strip()
        self._owners = frozenset(cleaned_owners)
        self._validator = TaskLedgerValidator(self._owners)
        self._reports = TaskLedgerReportReducer()
        self._settings = settings
        self._metadata = dict(metadata or {})
        self._tasks: dict[str, TaskRecord] = {}
        self._plan_summary = ""
        self._verified_facts: tuple[str, ...] = ()
        self._facts_to_find: tuple[str, ...] = ()
        self._facts_to_derive: tuple[str, ...] = ()
        self._educated_guesses: tuple[str, ...] = ()
        self._next_action: str | None = None
        self._events: list[LedgerEvent] = []
        self._revision = 0
        self._event_index = 0

    @property
    def revision(self) -> int:
        # Returns the optimistic-concurrency revision of the latest committed state.
        return self._revision

    @property
    def latest_event(self) -> LedgerEvent | None:
        # Returns the newest retained event without exposing the mutable event list.
        return self._events[-1] if self._events else None

    # @intent atomic-plan-commit
    # A plan is the structural contract every later dispatch relies on. Validate the
    # complete candidate graph before replacing live state so a malformed manager
    # response cannot leave half-created tasks or a revision that describes no
    # coherent plan. Callers may safely retry planning after any rejection.
    def apply_plan(self, plan: OrchestratorPlan, *, replan: bool = False) -> TaskLedgerSnapshot:
        # Validates and commits the first plan as one revision.
        if replan:
            return self.apply_replan(plan)
        if self._tasks:
            raise TaskLedgerError("apply_plan may only initialize an empty TaskLedger.", details={"revision": self._revision})
        if not plan.tasks:
            raise TaskLedgerError("An initial orchestrator plan must contain at least one task.")
        candidate = {spec.task_id: self._new_record(spec) for spec in self._unique_specs(plan.tasks)}
        self._validator.validate_candidate(candidate)
        self._commit_plan(plan, candidate, "plan_applied")
        return self.snapshot()

    # @intent replan-preserves-evidence
    # Replanning may change future work but must never rewrite completed facts or
    # recycle a task id for a different responsibility. Keeping completed outputs,
    # evidence, and structural identity makes the ledger auditable across manager
    # failures; omitted unfinished tasks are superseded instead of silently deleted.
    def apply_replan(self, plan: OrchestratorPlan) -> TaskLedgerSnapshot:
        # Builds a replacement plan while carrying compatible state and superseding omissions.
        if not self._tasks:
            raise TaskLedgerError("apply_replan requires an existing plan.")
        if not plan.tasks and not self.all_required_complete():
            raise TaskLedgerError("A replan may be empty only after all required work is complete.")
        specs = {spec.task_id: spec for spec in self._unique_specs(plan.tasks)}
        candidate: dict[str, TaskRecord] = {}
        for task_id, spec in specs.items():
            existing = self._tasks.get(task_id)
            if existing is None:
                candidate[task_id] = self._new_record(spec)
            elif existing.status is TaskStatus.SUPERSEDED:
                raise TaskLedgerError("A superseded task id cannot be revived; replanned work requires a new task id.", details={"task_id": task_id})
            elif existing.status is TaskStatus.COMPLETED:
                self._validator.validate_completed_identity(existing, spec)
                candidate[task_id] = existing
            else:
                candidate[task_id] = self._update_unfinished_record(existing, spec)
        for task_id, record in self._tasks.items():
            if task_id not in specs:
                candidate[task_id] = record if record.status is TaskStatus.COMPLETED else replace(record, status=TaskStatus.SUPERSEDED)
        self._validator.validate_candidate(candidate)
        self._commit_plan(plan, candidate, "plan_replaced")
        return self.snapshot()

    # @intent dispatch-revision-gate
    # A dispatch is authorized against one exact snapshot. Requiring its base
    # revision prevents a delayed orchestrator decision from starting work after a
    # replan changed readiness, ownership, or retry state underneath that decision.
    def start_task(self, dispatch: AgentDispatch) -> TaskLedgerSnapshot:
        # Atomically marks one ready task in progress and consumes one task attempt.
        record = self.task(dispatch.task_id)
        self._validator.validate_dispatch(dispatch, record, self._revision, self.is_ready)
        self._tasks[dispatch.task_id] = replace(record, owner=dispatch.owner, status=TaskStatus.IN_PROGRESS, attempts=dispatch.attempt)
        self._commit_event("task_started", task_id=dispatch.task_id, owner=dispatch.owner, metadata={"attempt": dispatch.attempt})
        return self.snapshot()

    # @intent report-closes-in-progress
    # Every ordinary worker outcome must close the in-progress state in one commit.
    # Failed attempts remain retryable only while budget remains; exhausted failures
    # become blocked so the manager must replan instead of looping indefinitely.
    def apply_report(self, report: AgentReport, *, owner: str) -> tuple[TaskLedgerSnapshot, bool]:
        # Commits one accepted worker report and returns whether substantive completion occurred.
        record = self.task(report.task_id)
        self._validator.require_in_progress_owner(record, owner)
        updated, progress = self._reports.apply(record, report)
        self._tasks[report.task_id] = updated
        self._commit_event("task_reported", task_id=report.task_id, owner=owner, metadata={"status": updated.status.value, "attempt": updated.attempts})
        return self.snapshot(), progress

    def record_dispatch_failure(self, task_id: str, *, owner: str, blocker: TaskBlocker, blocked: bool = False) -> TaskLedgerSnapshot:
        # Converts a post-start gate, builder, worker, parser, or validator failure into a retryable ledger state.
        record = self.task(task_id)
        self._validator.require_in_progress_owner(record, owner)
        retryable = not blocked and blocker.retryable and record.attempts < record.max_attempts
        status = TaskStatus.FAILED if retryable else TaskStatus.BLOCKED
        self._tasks[task_id] = replace(record, status=status, blockers=(*record.blockers, blocker))
        self._commit_event("dispatch_failed", task_id=task_id, owner=owner, message=blocker.message, metadata={"status": status.value, "code": blocker.code})
        return self.snapshot()

    def record_decision_rejection(self, message: str, *, task_id: str | None = None, owner: str | None = None) -> TaskLedgerSnapshot:
        # Records an invalid or premature manager decision without mutating task state.
        self._commit_event("decision_rejected", task_id=task_id, owner=owner, message=message)
        return self.snapshot()

    def set_next_action(self, next_action: str | None) -> TaskLedgerSnapshot:
        # Commits the manager's concise next-action hint as observable planning state.
        self._next_action = next_action.strip() if isinstance(next_action, str) and next_action.strip() else None
        self._commit_event("next_action_updated", message=self._next_action or "")
        return self.snapshot()

    def task(self, task_id: str) -> TaskRecord:
        # Returns one immutable task record or a typed ledger error for unknown ids.
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise TaskLedgerError("Task id is not present in the ledger.", details={"task_id": task_id}) from exc

    def is_ready(self, task_id: str) -> bool:
        # Derives readiness from stored state, remaining attempts, and completed dependencies.
        record = self.task(task_id)
        if record.status not in (TaskStatus.PENDING, TaskStatus.FAILED) or record.attempts >= record.max_attempts:
            return False
        return all(self.task(dependency).status is TaskStatus.COMPLETED for dependency in record.depends_on)

    def all_required_complete(self, *, require_verified_evidence: bool = False) -> bool:
        # Returns true only when every non-superseded required task and its dependencies completed.
        required = (task for task in self._tasks.values() if task.required and task.status is not TaskStatus.SUPERSEDED)
        return all(task.status is TaskStatus.COMPLETED and all(self.task(dep).status is TaskStatus.COMPLETED for dep in task.depends_on) and (not require_verified_evidence or any(evidence.verified for evidence in task.evidence)) for task in required)

    def required_tasks_have_verified_evidence(self) -> bool:
        # Enforces the optional finish gate without treating unverified worker prose as proof.
        required = (task for task in self._tasks.values() if task.required and task.status is not TaskStatus.SUPERSEDED)
        return all(any(evidence.verified for evidence in task.evidence) for task in required)

    def required_work_is_unrecoverable(self) -> bool:
        # Detects a post-replan required-task closure with no completed state and no legal next dispatch.
        if self.all_required_complete():
            return False
        needed: set[str] = set()
        for task in self._tasks.values():
            if task.required and task.status is not TaskStatus.SUPERSEDED:
                self._collect_required_dependency(task.task_id, needed)
        return not any(self.is_ready(task_id) for task_id in needed)

    def snapshot(self) -> TaskLedgerSnapshot:
        # Copies ledger-owned containers into the immutable public snapshot contract.
        return TaskLedgerSnapshot(run_id=self._run_id, goal=self._goal, plan_summary=self._plan_summary, verified_facts=self._verified_facts, facts_to_find=self._facts_to_find, facts_to_derive=self._facts_to_derive, educated_guesses=self._educated_guesses, tasks=tuple(self._tasks.values()), next_action=self._next_action, events=tuple(self._events), revision=self._revision, metadata=self._metadata)

    def _new_record(self, spec: TaskSpec) -> TaskRecord:
        # Converts one planner spec into a fresh pending record with an effective retry budget.
        return TaskRecord(task_id=spec.task_id, goal=spec.goal, owner=spec.owner, depends_on=spec.depends_on, required=spec.required, acceptance_criteria=spec.acceptance_criteria, payload=spec.payload, max_attempts=spec.max_attempts or self._settings.max_task_attempts, metadata=spec.metadata)

    def _unique_specs(self, specs: tuple[TaskSpec, ...]) -> tuple[TaskSpec, ...]:
        # Rejects duplicate task ids before any dict construction can silently overwrite one.
        ids = [spec.task_id for spec in specs]
        if len(ids) != len(set(ids)):
            raise TaskLedgerError("Orchestrator plan contains duplicate task ids.", details={"task_count": len(ids), "unique_task_count": len(set(ids))})
        return tuple(specs)

    def _update_unfinished_record(self, record: TaskRecord, spec: TaskSpec) -> TaskRecord:
        # Applies revised future-work structure while preserving attempts, evidence, blockers, and intermediate result.
        return replace(record, goal=spec.goal, owner=spec.owner, status=TaskStatus.PENDING, depends_on=spec.depends_on, required=spec.required, acceptance_criteria=spec.acceptance_criteria, payload=spec.payload, max_attempts=spec.max_attempts or self._settings.max_task_attempts, next_action=None, metadata=spec.metadata)

    def _commit_plan(self, plan: OrchestratorPlan, candidate: dict[str, TaskRecord], kind: str) -> None:
        # Swaps the validated candidate and all planner facts before recording one revision event.
        self._tasks = candidate
        self._plan_summary = plan.plan_summary
        self._verified_facts = plan.verified_facts
        self._facts_to_find = plan.facts_to_find
        self._facts_to_derive = plan.facts_to_derive
        self._educated_guesses = plan.educated_guesses
        self._next_action = plan.next_action
        self._commit_event(kind, message=plan.plan_summary, metadata={"task_count": len(plan.tasks)})

    def _commit_event(self, kind: str, task_id: str | None = None, owner: str | None = None, message: str = "", metadata: dict[str, Any] | None = None) -> None:
        # Advances revision and monotonic event index while retaining only the configured tail.
        self._revision += 1
        event = LedgerEvent(index=self._event_index, kind=kind, revision=self._revision, task_id=task_id, owner=owner, message=message, metadata=metadata or {})
        self._event_index += 1
        self._events.append(event)
        if len(self._events) > self._settings.max_events:
            self._events = self._events[-self._settings.max_events :]

    def _collect_required_dependency(self, task_id: str, needed: set[str]) -> None:
        # Add one required task and every active dependency that could advance it.
        if task_id in needed:
            return
        needed.add(task_id)
        for dependency in self.task(task_id).depends_on:
            self._collect_required_dependency(dependency, needed)

__all__ = ["TaskLedger"]
