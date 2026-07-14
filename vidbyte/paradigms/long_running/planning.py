"""Context Protocol Header

Path: vidbyte/paradigms/long_running/planning.py
Purpose: Parse, validate, schedule, and safely reconcile dependency-aware task graphs.
Architecture: LongRunningPlanner owns fresh planner calls; TaskGraphValidator owns
structural policy; ReadyTaskScheduler is pure; TaskGraphReconciler preserves verified
definitions and makes invalidation/removed work explicit in runtime state.
Exports: planner, validator, reconciler, scheduler.
Invariants: Task ids/definitions are stable, dependencies form a DAG, overlapping writers
are dependency ordered, and verified nodes cannot be silently rewritten.
Do not: Execute tasks, mutate ledger state, verify outputs, or erase historical states.
Related: docs/design/long-running-paradigm.md section 6.7 and controller.py.
Tests: Existing paradigm verification plus inline graph smoke checks; no new tests under
the approved design-doc-no-tests workflow.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import PurePath
from typing import TYPE_CHECKING, Any

from vidbyte.paradigms.long_running.errors import LongRunningPlanError
from vidbyte.paradigms.long_running.types import (
    DriftReview, GoalContract, LongRunningState, LongRunningTask,
    LongRunningTaskState, LongRunningTaskStatus, TaskGraph,
)
from vidbyte.tools.builtins.output_schema import OutputSchemaBuilder

if TYPE_CHECKING:
    from vidbyte.paradigms.long_running.context import LongRunningContextBroker
    from vidbyte.paradigms.long_running.ledger import RunLedger


class LongRunningPlanner:
    """Fresh-agent planner for initial graphs and bounded revisions."""

    def __init__(self, broker: "LongRunningContextBroker", validator: "TaskGraphValidator", ledger: "RunLedger | None" = None) -> None:
        # Bind role construction and deterministic validation without retaining agent history.
        self.broker = broker
        self.validator = validator
        self.ledger = ledger

    async def create(self, prompt: str, state: LongRunningState, *, validation_errors: Sequence[str] = ()) -> tuple[GoalContract, TaskGraph]:
        # Run a fresh planner and merge non-duplicative additions after caller contract text.
        builder = OutputSchemaBuilder()
        agent = self.broker.build_planner(state, builder, validation_errors=validation_errors)
        self._role_started(state, "create")
        reply = await agent.arun(self._create_message(prompt, validation_errors))
        self._role_completed(state, agent, reply.metadata, "create")
        values = self._values(builder, reply.content)
        contract = state.contract.with_planner_additions(
            success_criteria=self._texts(values.get("success_criteria", ())),
            invariants=self._texts(values.get("invariants", ())),
            non_goals=self._texts(values.get("non_goals", ())),
        )
        graph = self._graph(values, version=max(1, state.graph.version + 1))
        self.validator.validate(graph, max_tasks=self.broker.settings.max_tasks)
        self.broker.ensure_graph_fits(state, graph)
        return contract, graph

    async def revise(self, state: LongRunningState, review: DriftReview) -> TaskGraph:
        # Run a fresh planner against committed state and exact drift findings.
        builder = OutputSchemaBuilder()
        agent = self.broker.build_planner(state, builder, validation_errors=review.issues)
        self._role_started(state, "revise")
        reply = await agent.arun(self._revision_message(state, review))
        self._role_completed(state, agent, reply.metadata, "revise")
        graph = self._graph(self._values(builder, reply.content), version=state.graph.version + 1)
        self.validator.validate(graph, max_tasks=self.broker.settings.max_tasks)
        self.broker.ensure_graph_fits(state, graph)
        return graph

    def _role_started(self, state: LongRunningState, operation: str) -> None:
        # Journal planner calls when the service is attached to an active run ledger.
        if self.ledger is not None:
            from vidbyte.paradigms.long_running.ledger import LongRunningEventKind
            self.ledger.append(LongRunningEventKind.ROLE_STARTED, {"operation": operation, "graph_version": state.graph.version}, role="planner")

    def _role_completed(self, state: LongRunningState, agent: Any, metadata: Mapping[str, Any], operation: str) -> None:
        # Persist the public planner transcript before parsing or accepting its graph.
        if self.ledger is not None:
            from vidbyte.paradigms.long_running.ledger import LongRunningEventKind
            self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"operation": operation, "public_transcript": agent.export_state().history, "reply_metadata": dict(metadata)}, role="planner")

    def _graph(self, values: Mapping[str, Any], *, version: int) -> TaskGraph:
        # Convert structured task mappings into immutable definitions.
        raw_tasks = values.get("tasks", ())
        if not isinstance(raw_tasks, Sequence) or isinstance(raw_tasks, (str, bytes, bytearray)):
            raise LongRunningPlanError("Planner output must contain a tasks array.")
        tasks = tuple(self._task(item) for item in raw_tasks if isinstance(item, Mapping))
        if len(tasks) != len(raw_tasks):
            raise LongRunningPlanError("Every planner task must be a structured object.")
        return TaskGraph(version=version, tasks=tasks, rationale=str(values.get("rationale", "")))

    @classmethod
    def _task(cls, raw: Mapping[str, Any]) -> LongRunningTask:
        # Normalize one planner object while keeping runtime state out of definitions.
        return LongRunningTask(
            task_id=str(raw.get("task_id", raw.get("id", ""))),
            title=str(raw.get("title", "")), instructions=str(raw.get("instructions", "")),
            dependencies=cls._texts(raw.get("dependencies", ())),
            acceptance_criteria=cls._texts(raw.get("acceptance_criteria", ())),
            procedure_query=str(raw.get("procedure_query", "")), priority=int(raw.get("priority", 0)),
            owned_paths=cls._texts(raw.get("owned_paths", ())),
            read_only_paths=cls._texts(raw.get("read_only_paths", ())),
            verification_expectations=cls._texts(raw.get("verification_expectations", ())),
            expected_artifacts=cls._texts(raw.get("expected_artifacts", ())),
            notes=cls._texts(raw.get("notes", ())),
        )

    @staticmethod
    def _values(builder: OutputSchemaBuilder, fallback_text: str) -> Mapping[str, Any]:
        # Prefer authoritative output-tool state, then accept one explicit JSON object.
        values = builder.snapshot().get("values", {})
        if isinstance(values, Mapping) and values.get("tasks"):
            return values
        try:
            parsed = json.loads(fallback_text)
        except json.JSONDecodeError as exc:
            raise LongRunningPlanError("Planner did not produce structured task-graph output.") from exc
        if not isinstance(parsed, Mapping):
            raise LongRunningPlanError("Planner JSON output must be an object.")
        return parsed

    @staticmethod
    def _texts(value: object) -> tuple[str, ...]:
        # Normalize structured arrays and one scalar without retaining blank items.
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(text for item in value if (text := str(item).strip()))
        text = str(value).strip()
        return (text,) if text else ()

    @staticmethod
    def _create_message(prompt: str, validation_errors: Sequence[str]) -> str:
        # Request one compact graph while fencing prior validation feedback as data.
        feedback = "\n".join(f"- {item}" for item in validation_errors) or "- None"
        return "\n".join((
            "<exact_user_prompt>", prompt, "</exact_user_prompt>",
            "<prior_plan_validation_errors>", feedback, "</prior_plan_validation_errors>",
            "Use output-schema tools to return success_criteria, invariants, non_goals, rationale, and tasks.",
            "Each task object needs task_id, title, instructions, dependencies, acceptance_criteria, procedure_query, priority, owned_paths, read_only_paths, verification_expectations, expected_artifacts, and notes.",
        ))

    @staticmethod
    def _revision_message(state: LongRunningState, review: DriftReview) -> str:
        # Supply exact contract plus compact committed graph/drift state for revision.
        tasks = [{"task_id": task.task_id, "title": task.title, "definition_hash": task.definition_hash} for task in state.graph.tasks]
        return "\n".join((
            "Revise the task graph without changing the exact root contract or silently rewriting verified nodes.",
            f"Current graph: {json.dumps(tasks, sort_keys=True)}",
            f"Drift decision: {review.decision.value}",
            f"Drift issues: {json.dumps(review.issues)}",
            f"Explicit invalidations: {json.dumps(review.invalidate_task_ids)}",
            "Return the complete replacement graph using the same structured task fields.",
        ))


class TaskGraphValidator:
    """Deterministic structural and path-ownership validator for candidate graphs."""

    _TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def validate(self, graph: TaskGraph, *, max_tasks: int) -> None:
        # Enforce task completeness, ids, DAG shape, hashes, limits, and writer ordering.
        errors = list(self.conflicts(graph))
        if graph.version < 1:
            errors.append("graph version must be positive")
        if not graph.tasks:
            errors.append("graph must contain at least one task")
        if len(graph.tasks) > max_tasks:
            errors.append(f"graph has {len(graph.tasks)} tasks; maximum is {max_tasks}")
        ids = [task.task_id for task in graph.tasks]
        if len(ids) != len(set(ids)):
            errors.append("task ids must be unique")
        known = set(ids)
        for task in graph.tasks:
            errors.extend(self._task_errors(task, known))
        errors.extend(self._cycle_errors(graph))
        if errors:
            raise LongRunningPlanError("Task graph validation failed.", details={"graph_version": graph.version, "conflicts": tuple(dict.fromkeys(errors))})

    def conflicts(self, graph: TaskGraph) -> tuple[str, ...]:
        # Report overlapping writer paths that are not ordered by dependency reachability.
        conflicts: list[str] = []
        for index, left in enumerate(graph.tasks):
            for right in graph.tasks[index + 1:]:
                if self._paths_overlap(left.owned_paths, right.owned_paths) and not self._ordered(graph, left.task_id, right.task_id):
                    conflicts.append(f"overlapping owned paths require dependency ordering: {left.task_id} <-> {right.task_id}")
        return tuple(conflicts)

    def descendants(self, graph: TaskGraph, task_ids: Sequence[str]) -> tuple[str, ...]:
        # Compute transitive dependents for downstream invalidation.
        selected = set(task_ids)
        changed = True
        while changed:
            changed = False
            for task in graph.tasks:
                if task.task_id not in selected and selected.intersection(task.dependencies):
                    selected.add(task.task_id)
                    changed = True
        return tuple(task.task_id for task in graph.tasks if task.task_id in selected)

    def _task_errors(self, task: LongRunningTask, known: set[str]) -> tuple[str, ...]:
        # Validate one definition without mixing graph traversal into the checks.
        errors: list[str] = []
        if not self._TASK_ID.fullmatch(task.task_id):
            errors.append(f"invalid task id: {task.task_id!r}")
        if not task.title or not task.instructions or not task.acceptance_criteria or not task.procedure_query:
            errors.append(f"task {task.task_id} is missing title/instructions/criteria/procedure_query")
        if task.task_id in task.dependencies:
            errors.append(f"task {task.task_id} depends on itself")
        missing = tuple(item for item in task.dependencies if item not in known)
        if missing:
            errors.append(f"task {task.task_id} has missing dependencies: {', '.join(missing)}")
        if task.definition_hash != task.compute_definition_hash():
            errors.append(f"task {task.task_id} definition hash is stale")
        return tuple(errors)

    @staticmethod
    def _cycle_errors(graph: TaskGraph) -> tuple[str, ...]:
        # Detect cycles with a bounded depth-first color traversal.
        dependencies = {task.task_id: task.dependencies for task in graph.tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> bool:
            # Traverse one dependency node while detecting a back-edge color.
            if task_id in visiting:
                return True
            if task_id in visited:
                return False
            visiting.add(task_id)
            cyclic = any(visit(dependency) for dependency in dependencies.get(task_id, ()))
            visiting.remove(task_id)
            visited.add(task_id)
            return cyclic

        cyclic_ids = tuple(task_id for task_id in dependencies if visit(task_id))
        return (f"task graph contains a dependency cycle involving: {', '.join(cyclic_ids)}",) if cyclic_ids else ()

    @classmethod
    def _paths_overlap(cls, left: Sequence[str], right: Sequence[str]) -> bool:
        # Treat equal and ancestor/descendant normalized paths as writer conflicts.
        left_parts = tuple(cls._path_parts(path) for path in left)
        right_parts = tuple(cls._path_parts(path) for path in right)
        return any(a == b or a[:len(b)] == b or b[:len(a)] == a for a in left_parts for b in right_parts if a and b)

    @staticmethod
    def _path_parts(path: str) -> tuple[str, ...]:
        # Normalize separators/case for conservative cross-platform ownership checks.
        return tuple(part.casefold() for part in PurePath(path.replace("\\", "/")).parts if part not in {".", ""})

    @staticmethod
    def _ordered(graph: TaskGraph, left: str, right: str) -> bool:
        # Return true when either task transitively depends on the other.
        dependencies = {task.task_id: set(task.dependencies) for task in graph.tasks}

        def reaches(start: str, target: str) -> bool:
            # Walk transitive dependencies to prove one writer is ordered after another.
            pending = list(dependencies.get(start, ()))
            seen: set[str] = set()
            while pending:
                current = pending.pop()
                if current == target:
                    return True
                if current not in seen:
                    seen.add(current)
                    pending.extend(dependencies.get(current, ()))
            return False

        return reaches(left, right) or reaches(right, left)


class TaskGraphReconciler:
    """Preserve verified history while accepting a validated replacement graph."""

    def __init__(self, validator: TaskGraphValidator) -> None:
        # Share descendant semantics with graph validation.
        self.validator = validator

    def reconcile(self, current: TaskGraph, states: Sequence[LongRunningTaskState], proposed: TaskGraph, *, invalidations: Mapping[str, str]) -> tuple[TaskGraph, tuple[LongRunningTaskState, ...]]:
        # Reject silent verified rewrites and construct explicit successor runtime states.
        state_by_id = {state.task_id: state for state in states}
        current_by_id = {task.task_id: task for task in current.tasks}
        for task in proposed.tasks:
            prior = current_by_id.get(task.task_id)
            prior_state = state_by_id.get(task.task_id)
            if prior and prior_state and prior_state.status is LongRunningTaskStatus.VERIFIED and prior.definition_hash != task.definition_hash and task.task_id not in invalidations:
                raise LongRunningPlanError("Revised graph silently changed a verified task definition.", task_id=task.task_id, details={"current_hash": prior.definition_hash, "proposed_hash": task.definition_hash})
        next_states = [self._state_for(task, state_by_id.get(task.task_id), invalidations.get(task.task_id, "")) for task in proposed.tasks]
        proposed_ids = {task.task_id for task in proposed.tasks}
        for state in states:
            if state.task_id not in proposed_ids:
                next_states.append(replace(state, status=LongRunningTaskStatus.BLOCKED, invalidation_reason="removed-by-replan"))
        return proposed, tuple(next_states)

    def invalidate_descendants(self, graph: TaskGraph, states: Sequence[LongRunningTaskState], task_ids: Sequence[str], reason: str) -> tuple[LongRunningTaskState, ...]:
        # Mark named tasks and transitive dependents invalid without erasing results/evidence.
        affected = set(self.validator.descendants(graph, task_ids))
        return tuple(replace(state, status=LongRunningTaskStatus.INVALIDATED, invalidation_reason=reason, verified_result_id="") if state.task_id in affected else state for state in states)

    @staticmethod
    def _state_for(task: LongRunningTask, prior: LongRunningTaskState | None, invalidation_reason: str) -> LongRunningTaskState:
        # Reuse compatible state or create a fresh pending state for a new definition.
        if prior is None:
            return LongRunningTaskState(task.task_id)
        if invalidation_reason:
            return replace(prior, status=LongRunningTaskStatus.PENDING, invalidation_reason=invalidation_reason, verified_result_id="")
        if prior.status is LongRunningTaskStatus.INVALIDATED:
            return replace(prior, status=LongRunningTaskStatus.PENDING, verified_result_id="")
        return prior


class ReadyTaskScheduler:
    """Pure deterministic scheduler for one ready task at a time."""

    def next(self, graph: TaskGraph, states: Sequence[LongRunningTaskState]) -> LongRunningTask | None:
        # Select highest priority then stable id among pending tasks with verified deps.
        status = {state.task_id: state.status for state in states}
        ready = [task for task in graph.tasks if status.get(task.task_id, LongRunningTaskStatus.PENDING) is LongRunningTaskStatus.PENDING and all(status.get(dependency) is LongRunningTaskStatus.VERIFIED for dependency in task.dependencies)]
        return sorted(ready, key=lambda task: (-task.priority, task.task_id))[0] if ready else None


__all__ = ["LongRunningPlanner", "ReadyTaskScheduler", "TaskGraphReconciler", "TaskGraphValidator"]
