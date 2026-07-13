"""Context Protocol Header

Description:
    Implements the run-local TaskLedger for multi-agent orchestration.
Purpose:
    Owns every structural task transition, retry counter, dependency invariant,
    evidence record, blocker, revision, and bounded event exposed to the controller.
Architecture:
    - TaskLedger: Mutable authority with immutable snapshots at every boundary.
    - Pure validation helpers: Check plan identity, ownership, dependencies, and cycles.
Relations:
    Mutated only by vidbyte.agents.multi.agent; read by orchestrators and transfer callbacks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, AgentReport, LedgerEvent, MultiAgentSettings, OrchestratorPlan, TaskBlocker, TaskEvidence, TaskLedgerSnapshot, TaskRecord, TaskSpec
from vidbyte.lib.enums.multi_agent import TaskStatus
from vidbyte.lib.errors import TaskLedgerError


class TaskLedger:
    """Sole mutable structural authority for one isolated multi-agent run."""

    def __init__(self, *, run_id: str, goal: str, owners: Sequence[str], settings: MultiAgentSettings, metadata: Mapping[str, Any] | None = None) -> None:
        # Creates an empty ledger whose first legal structural operation is apply_plan().
        if not isinstance(run_id, str) or not run_id.strip() or not isinstance(goal, str) or not goal.strip():
            raise TaskLedgerError("TaskLedger requires non-empty run_id and goal.")
        if not isinstance(settings, MultiAgentSettings):
            raise TaskLedgerError("TaskLedger.settings must be MultiAgentSettings.", details={"actual_type": type(settings).__name__})
        if not owners or any(not isinstance(owner, str) or not owner.strip() for owner in owners):
            raise TaskLedgerError("TaskLedger owners must contain only non-empty strings.")
        cleaned_owners = tuple(owner.strip() for owner in owners)
        if len(cleaned_owners) != len(set(cleaned_owners)):
            raise TaskLedgerError("TaskLedger owners must be non-empty and unique.", details={"owner_count": len(cleaned_owners)})
        self._run_id = run_id.strip()
        self._goal = goal.strip()
        self._owners = frozenset(cleaned_owners)
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
        self._validate_candidate(candidate)
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
                self._validate_completed_identity(existing, spec)
                candidate[task_id] = existing
            else:
                candidate[task_id] = self._update_unfinished_record(existing, spec)
        for task_id, record in self._tasks.items():
            if task_id not in specs:
                candidate[task_id] = record if record.status is TaskStatus.COMPLETED else replace(record, status=TaskStatus.SUPERSEDED)
        self._validate_candidate(candidate)
        self._commit_plan(plan, candidate, "plan_replaced")
        return self.snapshot()

    # @intent dispatch-revision-gate
    # A dispatch is authorized against one exact snapshot. Requiring its base
    # revision prevents a delayed orchestrator decision from starting work after a
    # replan changed readiness, ownership, or retry state underneath that decision.
    def start_task(self, dispatch: AgentDispatch) -> TaskLedgerSnapshot:
        # Atomically marks one ready task in progress and consumes one task attempt.
        if dispatch.base_revision != self._revision:
            raise TaskLedgerError("Dispatch base_revision is stale.", details={"task_id": dispatch.task_id, "expected_revision": self._revision, "actual_revision": dispatch.base_revision})
        record = self.task(dispatch.task_id)
        if dispatch.owner not in self._owners:
            raise TaskLedgerError("Dispatch owner is not a configured worker.", details={"task_id": dispatch.task_id, "owner": dispatch.owner})
        if record.owner is not None and record.owner != dispatch.owner:
            raise TaskLedgerError("Dispatch owner does not match the planned owner.", details={"task_id": dispatch.task_id, "expected_owner": record.owner, "actual_owner": dispatch.owner})
        if not self.is_ready(dispatch.task_id):
            raise TaskLedgerError("Task is not ready for dispatch.", details={"task_id": dispatch.task_id, "status": record.status.value, "attempts": record.attempts})
        if dispatch.attempt != record.attempts + 1:
            raise TaskLedgerError("Dispatch attempt does not match the next ledger attempt.", details={"task_id": dispatch.task_id, "expected_attempt": record.attempts + 1, "actual_attempt": dispatch.attempt})
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
        self._require_in_progress_owner(record, owner)
        if report.status is TaskStatus.COMPLETED:
            evidence = self._merge_evidence(record.evidence, report.evidence)
            blockers = self._merge_blockers(tuple(blocker for blocker in record.blockers if not blocker.retryable), tuple(blocker for blocker in report.blockers if not blocker.retryable))
            updated = replace(record, status=TaskStatus.COMPLETED, result=report.result, evidence=evidence, blockers=blockers, next_action=report.next_action)
            progress = True
        elif report.status is TaskStatus.FAILED:
            status = TaskStatus.FAILED if record.attempts < record.max_attempts else TaskStatus.BLOCKED
            evidence = self._merge_evidence(record.evidence, report.evidence)
            blockers = self._merge_blockers(record.blockers, report.blockers)
            updated = replace(record, status=status, result=report.result, evidence=evidence, blockers=blockers, next_action=report.next_action)
            progress = len(evidence) > len(record.evidence) or len(blockers) > len(record.blockers) or report.next_action != record.next_action
        else:
            evidence = self._merge_evidence(record.evidence, report.evidence)
            blockers = self._merge_blockers(record.blockers, report.blockers)
            updated = replace(record, status=TaskStatus.BLOCKED, result=report.result, evidence=evidence, blockers=blockers, next_action=report.next_action)
            progress = len(evidence) > len(record.evidence) or len(blockers) > len(record.blockers) or report.next_action != record.next_action
        self._tasks[report.task_id] = updated
        self._commit_event("task_reported", task_id=report.task_id, owner=owner, metadata={"status": updated.status.value, "attempt": updated.attempts})
        return self.snapshot(), progress

    def record_dispatch_failure(self, task_id: str, *, owner: str, blocker: TaskBlocker, blocked: bool = False) -> TaskLedgerSnapshot:
        # Converts a post-start gate, builder, worker, parser, or validator failure into a retryable ledger state.
        record = self.task(task_id)
        self._require_in_progress_owner(record, owner)
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

        def collect(task_id: str) -> None:
            # Adds one required task and every active dependency that could advance it.
            if task_id in needed:
                return
            needed.add(task_id)
            for dependency in self.task(task_id).depends_on:
                collect(dependency)

        for task in self._tasks.values():
            if task.required and task.status is not TaskStatus.SUPERSEDED:
                collect(task.task_id)
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

    def _validate_completed_identity(self, record: TaskRecord, spec: TaskSpec) -> None:
        # Prevents a replan from rewriting the identity of already completed work.
        expected = (record.goal, record.depends_on, record.acceptance_criteria, record.required)
        actual = (spec.goal, spec.depends_on, spec.acceptance_criteria, spec.required)
        owner_changed = spec.owner is not None and spec.owner != record.owner
        if expected != actual or owner_changed:
            raise TaskLedgerError("Replan cannot change the structural identity of a completed task.", details={"task_id": record.task_id})

    def _update_unfinished_record(self, record: TaskRecord, spec: TaskSpec) -> TaskRecord:
        # Applies revised future-work structure while preserving attempts, evidence, blockers, and intermediate result.
        return replace(record, goal=spec.goal, owner=spec.owner, status=TaskStatus.PENDING, depends_on=spec.depends_on, required=spec.required, acceptance_criteria=spec.acceptance_criteria, payload=spec.payload, max_attempts=spec.max_attempts or self._settings.max_task_attempts, next_action=None, metadata=spec.metadata)

    def _merge_evidence(self, existing: tuple[TaskEvidence, ...], incoming: tuple[TaskEvidence, ...]) -> tuple[TaskEvidence, ...]:
        # Deduplicates evidence only when simple identity fields and value equality are safely decidable.
        merged = list(existing)
        for candidate in incoming:
            if not any(self._evidence_matches(item, candidate) for item in merged):
                merged.append(candidate)
        return tuple(merged)

    def _evidence_matches(self, left: TaskEvidence, right: TaskEvidence) -> bool:
        # Avoids trusting arbitrary equality implementations that raise or return non-boolean objects.
        if (left.source, left.kind, left.verified) != (right.source, right.kind, right.verified):
            return False
        try:
            equal = left.value == right.value
        except Exception:
            return False
        return equal if isinstance(equal, bool) else False

    def _merge_blockers(self, existing: tuple[TaskBlocker, ...], incoming: tuple[TaskBlocker, ...]) -> tuple[TaskBlocker, ...]:
        # Retains one safe control record per blocker code/message/retryability tuple.
        merged = list(existing)
        seen = {(item.code, item.message, item.retryable) for item in merged}
        for blocker in incoming:
            key = (blocker.code, blocker.message, blocker.retryable)
            if key not in seen:
                merged.append(blocker)
                seen.add(key)
        return tuple(merged)

    def _validate_candidate(self, candidate: dict[str, TaskRecord]) -> None:
        # Validates owners, references, self-dependencies, duplicate edges, and cycles as one graph.
        for record in candidate.values():
            if record.status is TaskStatus.SUPERSEDED:
                continue
            if record.owner is not None and record.owner not in self._owners:
                raise TaskLedgerError("Plan references an unknown task owner.", details={"task_id": record.task_id, "owner": record.owner})
            if len(record.depends_on) != len(set(record.depends_on)):
                raise TaskLedgerError("Task dependencies must be unique.", details={"task_id": record.task_id})
            for dependency in record.depends_on:
                if dependency == record.task_id or dependency not in candidate:
                    raise TaskLedgerError("Task dependency is missing or self-referential.", details={"task_id": record.task_id, "dependency": dependency})
                if candidate[dependency].status is TaskStatus.SUPERSEDED:
                    raise TaskLedgerError("Active tasks cannot depend on superseded work.", details={"task_id": record.task_id, "dependency": dependency})
        self._validate_acyclic(candidate)

    def _validate_acyclic(self, candidate: dict[str, TaskRecord]) -> None:
        # Uses depth-first coloring to reject dependency cycles before state commit.
        colors: dict[str, int] = {}

        def visit(task_id: str) -> None:
            # Marks one dependency chain and raises when it reaches an active ancestor.
            if colors.get(task_id) == 1:
                raise TaskLedgerError("Task plan contains a dependency cycle.", details={"task_id": task_id})
            if colors.get(task_id) == 2:
                return
            colors[task_id] = 1
            for dependency in candidate[task_id].depends_on:
                visit(dependency)
            colors[task_id] = 2
        for task_id, record in candidate.items():
            if record.status is not TaskStatus.SUPERSEDED:
                visit(task_id)

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

    def _require_in_progress_owner(self, record: TaskRecord, owner: str) -> None:
        # Ensures a report or failure closes only the attempt started for the same worker.
        if record.status is not TaskStatus.IN_PROGRESS or record.owner != owner:
            raise TaskLedgerError("Task report does not match an in-progress owner.", details={"task_id": record.task_id, "status": record.status.value, "expected_owner": record.owner, "actual_owner": owner})


__all__ = ["TaskLedger"]
