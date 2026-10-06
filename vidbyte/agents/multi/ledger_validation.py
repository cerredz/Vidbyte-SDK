"""Context Protocol Header

Description:
    Validates TaskLedger configuration, dispatches, replans, and dependency graphs.
Purpose:
    Keeps validation guards out of mutation methods so ledger transitions read as
    validate first, then commit core state.
Architecture:
    TaskLedgerValidator owns configuration, ownership, readiness, identity, and DAG checks.
Relations:
    Constructed and used only by TaskLedger.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, MultiAgentSettings, TaskRecord, TaskSpec
from vidbyte.lib.enums.multi_agent import TaskStatus
from vidbyte.lib.errors import TaskLedgerError


class TaskLedgerValidator:
    """Validate ledger boundaries without mutating candidate or live state."""

    def __init__(self, owners: frozenset[str]) -> None:
        self._owners = owners

    @classmethod
    def validate_configuration(cls, run_id: str, goal: str, owners: Sequence[str], settings: MultiAgentSettings) -> tuple[str, ...]:
        # Configuration guards execute before TaskLedger stores mutable state.
        cls._validate_identity(run_id, goal)
        cls._validate_settings(settings)
        return cls._validate_owners(owners)

    def validate_dispatch(self, dispatch: AgentDispatch, record: TaskRecord, revision: int, is_ready: Callable[[str], bool]) -> None:
        # Dispatch validation is deliberately ordered from stale snapshot to attempt number.
        self._validate_dispatch_revision(dispatch, revision)
        self._validate_dispatch_owner(dispatch, record)
        self._validate_dispatch_readiness(dispatch, record, is_ready)
        self._validate_dispatch_attempt(dispatch, record)

    def validate_candidate(self, candidate: dict[str, TaskRecord]) -> None:
        # Validate every active task before performing the graph-wide cycle check.
        for record in candidate.values():
            if record.status is TaskStatus.SUPERSEDED:
                continue
            self._validate_candidate_owner(record)
            self._validate_candidate_dependencies(record, candidate)
        self._validate_acyclic(candidate)

    def validate_completed_identity(self, record: TaskRecord, spec: TaskSpec) -> None:
        # Completed work cannot be relabeled or assigned to a different owner by replan.
        expected = (record.goal, record.depends_on, record.acceptance_criteria, record.required)
        actual = (spec.goal, spec.depends_on, spec.acceptance_criteria, spec.required)
        owner_changed = spec.owner is not None and spec.owner != record.owner
        if expected != actual or owner_changed:
            raise TaskLedgerError("Replan cannot change the structural identity of a completed task.", details={"task_id": record.task_id})

    def require_in_progress_owner(self, record: TaskRecord, owner: str) -> None:
        # Reports and dispatch failures may close only the exact live owner attempt.
        if record.status is not TaskStatus.IN_PROGRESS or record.owner != owner:
            raise TaskLedgerError("Task report does not match an in-progress owner.", details={"task_id": record.task_id, "status": record.status.value, "expected_owner": record.owner, "actual_owner": owner})

    @classmethod
    def _validate_identity(cls, run_id: str, goal: str) -> None:
        # Ledger identity must be explicit before any structural mutation.
        if not isinstance(run_id, str) or not run_id.strip() or not isinstance(goal, str) or not goal.strip():
            raise TaskLedgerError("TaskLedger requires non-empty run_id and goal.")

    @classmethod
    def _validate_settings(cls, settings: MultiAgentSettings) -> None:
        # Retry and event limits come only from the shared immutable settings contract.
        if not isinstance(settings, MultiAgentSettings):
            raise TaskLedgerError("TaskLedger.settings must be MultiAgentSettings.", details={"actual_type": type(settings).__name__})

    @classmethod
    def _validate_owners(cls, owners: Sequence[str]) -> tuple[str, ...]:
        # Owner ids are worker lookup keys and therefore non-empty and unique.
        if not owners or any(not isinstance(owner, str) or not owner.strip() for owner in owners):
            raise TaskLedgerError("TaskLedger owners must contain only non-empty strings.")
        cleaned = tuple(owner.strip() for owner in owners)
        if len(cleaned) != len(set(cleaned)):
            raise TaskLedgerError("TaskLedger owners must be non-empty and unique.", details={"owner_count": len(cleaned)})
        return cleaned

    def _validate_dispatch_revision(self, dispatch: AgentDispatch, revision: int) -> None:
        # Stale decisions cannot start work after a plan-changing commit.
        if dispatch.base_revision != revision:
            raise TaskLedgerError("Dispatch base_revision is stale.", details={"task_id": dispatch.task_id, "expected_revision": revision, "actual_revision": dispatch.base_revision})

    def _validate_dispatch_owner(self, dispatch: AgentDispatch, record: TaskRecord) -> None:
        # Dispatch ownership must be configured and compatible with the plan.
        if dispatch.owner not in self._owners:
            raise TaskLedgerError("Dispatch owner is not a configured worker.", details={"task_id": dispatch.task_id, "owner": dispatch.owner})
        if record.owner is not None and record.owner != dispatch.owner:
            raise TaskLedgerError("Dispatch owner does not match the planned owner.", details={"task_id": dispatch.task_id, "expected_owner": record.owner, "actual_owner": dispatch.owner})

    def _validate_dispatch_readiness(self, dispatch: AgentDispatch, record: TaskRecord, is_ready: Callable[[str], bool]) -> None:
        # Only pending or retryable failed tasks with complete dependencies may start.
        if not is_ready(dispatch.task_id):
            raise TaskLedgerError("Task is not ready for dispatch.", details={"task_id": dispatch.task_id, "status": record.status.value, "attempts": record.attempts})

    def _validate_dispatch_attempt(self, dispatch: AgentDispatch, record: TaskRecord) -> None:
        # Semantic attempt numbers are ledger-owned and strictly monotonic.
        if dispatch.attempt != record.attempts + 1:
            raise TaskLedgerError("Dispatch attempt does not match the next ledger attempt.", details={"task_id": dispatch.task_id, "expected_attempt": record.attempts + 1, "actual_attempt": dispatch.attempt})

    def _validate_candidate_owner(self, record: TaskRecord) -> None:
        # Every planned owner must map to one configured worker.
        if record.owner is not None and record.owner not in self._owners:
            raise TaskLedgerError("Plan references an unknown task owner.", details={"task_id": record.task_id, "owner": record.owner})

    def _validate_candidate_dependencies(self, record: TaskRecord, candidate: dict[str, TaskRecord]) -> None:
        # Dependency edges must be unique, present, non-self, and active.
        if len(record.depends_on) != len(set(record.depends_on)):
            raise TaskLedgerError("Task dependencies must be unique.", details={"task_id": record.task_id})
        for dependency in record.depends_on:
            if dependency == record.task_id or dependency not in candidate:
                raise TaskLedgerError("Task dependency is missing or self-referential.", details={"task_id": record.task_id, "dependency": dependency})
            if candidate[dependency].status is TaskStatus.SUPERSEDED:
                raise TaskLedgerError("Active tasks cannot depend on superseded work.", details={"task_id": record.task_id, "dependency": dependency})

    def _validate_acyclic(self, candidate: dict[str, TaskRecord]) -> None:
        # Depth-first coloring rejects cycles before the candidate can replace live state.
        colors: dict[str, int] = {}
        for task_id, record in candidate.items():
            if record.status is not TaskStatus.SUPERSEDED:
                self._visit_candidate(task_id, candidate, colors)

    def _visit_candidate(self, task_id: str, candidate: dict[str, TaskRecord], colors: dict[str, int]) -> None:
        # Active ancestors identify cycles; completed nodes can be skipped on later visits.
        if colors.get(task_id) == 1:
            raise TaskLedgerError("Task plan contains a dependency cycle.", details={"task_id": task_id})
        if colors.get(task_id) == 2:
            return
        colors[task_id] = 1
        for dependency in candidate[task_id].depends_on:
            self._visit_candidate(dependency, candidate, colors)
        colors[task_id] = 2


__all__ = ["TaskLedgerValidator"]
