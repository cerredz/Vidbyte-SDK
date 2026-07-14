"""Context Protocol Header

Path: vidbyte/paradigms/long_running/controller.py
Purpose: Drive the finite durable plan/execute/verify/audit/learn/finalize state machine.
Architecture: LongRunningController creates/resumes one RunLedger, builds run-scoped
services, commits every semantic successor, and returns results from committed heads.
Exports: LongRunningController.
Invariants: One task runs at a time, only verified results unlock dependencies, every
loop is budgeted, drift gates learning, and completion requires a passing final audit.
Do not: Keep hidden mutable controller truth, skip ledger commits, infer write authority,
or report a budget/recovery stop as successful completion.
Related: docs/design/long-running-paradigm.md section 6.10 and paradigm.py.
Tests: Existing paradigm verification plus inline deterministic controller smoke; no new
tests under the approved design-doc-no-tests workflow.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from vidbyte.paradigms.long_running.context import LongRunningContextBroker
from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError, LongRunningPlanError, LongRunningRecoveryRequiredError, LongRunningResumeError
from vidbyte.paradigms.long_running.execution import AttemptIsolationStatus, AttemptIsolator, AttemptLease, TaskExecutionService
from vidbyte.paradigms.long_running.ledger import BehaviorFingerprint, LongRunningEventKind, RunLedger, RunLedgerStore
from vidbyte.paradigms.long_running.planning import LongRunningPlanner, ReadyTaskScheduler, TaskGraphReconciler, TaskGraphValidator
from vidbyte.paradigms.long_running.types import DriftDecision, DriftReview, GoalContract, InterruptedAttemptPolicy, LongRunningResult, LongRunningResumeOptions, LongRunningRunOptions, LongRunningRunStatus, LongRunningSettings, LongRunningState, LongRunningStopReason, LongRunningTask, LongRunningTaskState, LongRunningTaskStatus, LongRunningUsage, TaskAttempt, TaskGraph, TaskResult, VerificationResult
from vidbyte.paradigms.long_running.verification import FinalizationService, ProcedureLearningService, ProcedureValidator, TaskValidator, VerificationService
from vidbyte.procedures import ProcedureLibrary, ProcedureSummary
from vidbyte.procedures.serialization import ProcedureIdentity
from vidbyte.tools.types import ToolPermission


class LongRunningController:
    """Deterministic durable controller for one long-running paradigm configuration."""

    def __init__(self, settings: LongRunningSettings, procedure_library: ProcedureLibrary, ledger_store: RunLedgerStore, *, validators: tuple[TaskValidator, ...] = (), procedure_validators: tuple[ProcedureValidator, ...] = (), attempt_isolator: AttemptIsolator | None = None) -> None:
        # Bind construction-only dependencies; each start/resume creates run-scoped services.
        self.settings = settings
        self.procedure_library = procedure_library
        self.ledger_store = ledger_store
        self.validators = tuple(validators)
        self.procedure_validators = tuple(procedure_validators)
        self.attempt_isolator = attempt_isolator
        self.graph_validator = TaskGraphValidator()
        self.reconciler = TaskGraphReconciler(self.graph_validator)
        self.scheduler = ReadyTaskScheduler()

    async def start(self, prompt: str, options: LongRunningRunOptions) -> LongRunningResult:
        # Create immutable contract/state, persist RUN_STARTED, and accept one valid plan.
        if not prompt.strip():
            raise LongRunningPlanError("Long-running prompt cannot be blank.")
        run_id = options.run_id or f"lr_{uuid4().hex}"
        ProcedureIdentity.validate_id(run_id, field_name="run_id")
        fingerprint = self._fingerprint()
        started_at = ProcedureIdentity.utc_now()
        deadline_at = self._deadline(started_at)
        contract = GoalContract(prompt, options.success_criteria, options.invariants, options.non_goals)
        state = LongRunningState(run_id, LongRunningRunStatus.PLANNING, contract, TaskGraph(0, ()), (), (), (), (), (), LongRunningUsage(), fingerprint, 0, 0, 0, started_at, deadline_at, None, metadata=options.metadata)
        ledger = RunLedger.create(state, self.ledger_store, required=self.settings.require_ledger_persistence)
        broker = LongRunningContextBroker(self.settings, self.procedure_library)
        planner = LongRunningPlanner(broker, self.graph_validator, ledger)
        errors: tuple[str, ...] = ()
        for attempt_number in range(1, self.settings.max_plan_attempts + 1):
            ledger.append(LongRunningEventKind.PLAN_ATTEMPTED, {"attempt_number": attempt_number, "prior_errors": errors}, role="planner")
            try:
                contract, graph = await self._await(state, planner.create(prompt, state, validation_errors=errors))
                task_states = tuple(LongRunningTaskState(task.task_id) for task in graph.tasks)
                state = self._with_usage(replace(state, contract=contract, graph=graph, task_states=task_states, status=LongRunningRunStatus.RUNNING, revision=state.revision + 1), ledger)
                ledger.commit(state, LongRunningEventKind.PLAN_ACCEPTED, {"graph_version": graph.version, "task_count": len(graph.tasks)}, role="planner")
                return await self.run(state, ledger=ledger)
            except LongRunningPlanError as exc:
                errors = (*errors, str(exc))[-self.settings.max_plan_attempts:]
                ledger.append(LongRunningEventKind.PLAN_VALIDATION_FAILED, {"attempt_number": attempt_number, "error": exc.to_context_packet()}, role="planner")
        state = replace(state, status=LongRunningRunStatus.FAILED, stop_reason=LongRunningStopReason.INTERNAL_ERROR, revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.RUN_FAILED, {"reason": "planning attempts exhausted", "validation_errors": errors})
        return self._result(ledger)

    async def resume(self, run_id: str, options: LongRunningResumeOptions) -> LongRunningResult:
        # Rehydrate the newest valid head, reconcile settings/interruption, then continue.
        ledger = RunLedger.resume(run_id, self.ledger_store, required=self.settings.require_ledger_persistence)
        state = ledger.snapshot().state
        if state.status in {LongRunningRunStatus.COMPLETED, LongRunningRunStatus.FAILED}:
            raise LongRunningResumeError("Terminal long-running runs cannot be resumed.", run_id=run_id, details={"status": state.status.value})
        if state.status is LongRunningRunStatus.RECOVERY_REQUIRED:
            authorized = options.interrupted_attempt_policy is InterruptedAttemptPolicy.ACCEPT_CALLER_RECONCILIATION and bool(options.reconciliation_reason.strip())
            if not authorized:
                raise LongRunningResumeError("RECOVERY_REQUIRED resume needs ACCEPT_CALLER_RECONCILIATION and a non-empty reason.", run_id=run_id)
            state = replace(state, status=LongRunningRunStatus.PAUSED, stop_reason=None, revision=state.revision + 1)
            ledger.commit(state, LongRunningEventKind.CHECKPOINTED, {"caller_reconciled_recovery": True, "reason": options.reconciliation_reason.strip()})
        fingerprint = self._fingerprint()
        if fingerprint != state.settings_fingerprint:
            if not options.allow_settings_change or not options.settings_change_reason.strip():
                raise LongRunningResumeError("Resume settings fingerprint differs; explicit typed authorization and reason are required.", run_id=run_id)
            state = replace(state, settings_fingerprint=fingerprint, revision=state.revision + 1)
            ledger.commit(state, LongRunningEventKind.SETTINGS_CHANGE_ACCEPTED, {"reason": options.settings_change_reason.strip(), "old_fingerprint": ledger.snapshot().settings_fingerprint, "new_fingerprint": fingerprint})
        state = await self._reconcile_interrupted(state, ledger, options)
        if state.status is LongRunningRunStatus.RECOVERY_REQUIRED:
            return self._result(ledger)
        state = replace(state, status=LongRunningRunStatus.RUNNING, stop_reason=None, revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.RUN_RESUMED, {"interrupted_attempt_policy": options.interrupted_attempt_policy.value})
        return await self.run(state, ledger=ledger)

    async def run(self, state: LongRunningState, *, ledger: RunLedger | None = None) -> LongRunningResult:
        # Iterate finite task transitions and finalize only after the root audit passes.
        active_ledger = ledger or RunLedger.resume(state.run_id, self.ledger_store, required=self.settings.require_ledger_persistence)
        broker = LongRunningContextBroker(self.settings, self.procedure_library)
        planner = LongRunningPlanner(broker, self.graph_validator, active_ledger)
        execution = TaskExecutionService(broker, self.procedure_library, active_ledger, attempt_isolator=self.attempt_isolator)
        verification = VerificationService(broker, active_ledger, self.validators)
        learning = ProcedureLearningService(broker, self.procedure_library, active_ledger, self.procedure_validators)
        finalization = FinalizationService(broker, active_ledger)
        try:
            while True:
                state = active_ledger.snapshot().state
                stop = self._budget_stop(state, active_ledger)
                if stop is not None:
                    return stop
                task = self.scheduler.next(state.graph, state.task_states)
                if task is None:
                    if state.graph.tasks and all(self._task_state(state, item.task_id).status is LongRunningTaskStatus.VERIFIED for item in state.graph.tasks):
                        return await self._finalize(state, active_ledger, verification, finalization)
                    if state.replan_count < self.settings.max_replans:
                        review = await self._await(state, verification.audit_drift(state))
                        state = self._commit_drift(state, active_ledger, review)
                        state = await self._revise(state, active_ledger, planner, review)
                        continue
                    return self._pause(state, active_ledger, LongRunningStopReason.PARTIAL_BLOCKED, "no ready task and replan budget exhausted")
                state = self._activate(state, active_ledger, task)
                attempts, checks = self._task_history(state, task.task_id)
                try:
                    attempt = await self._await(state, execution.execute(state, task) if not attempts else execution.repair(state, task, attempts[-1], checks[-1]))
                except asyncio.CancelledError:
                    if self._worker_can_side_effect():
                        self._recovery(state, active_ledger, "worker cancelled while non-read side effects may be open")
                    else:
                        self._pause(state, active_ledger, LongRunningStopReason.CANCELLED, "controller task cancelled")
                    raise
                except TimeoutError:
                    if self._worker_can_side_effect():
                        return self._recovery(state, active_ledger, "worker timed out while non-read side effects may be open")
                    return self._pause(state, active_ledger, LongRunningStopReason.TIMEOUT, "controller deadline reached during task execution")
                except Exception as exc:
                    if self._worker_can_side_effect():
                        return self._recovery(state, active_ledger, f"worker failed around non-read tools:{type(exc).__name__}")
                    attempt = self._failed_attempt(state, task, exc, active_ledger)
                state = self._record_attempt(state, active_ledger, task, attempt)
                check = await self._await(state, verification.verify_task(state, task, attempt))
                state = self._record_verification(state, active_ledger, task, attempt, check)
                if check.passed:
                    await self._await(state, execution.accept(attempt, check))
                    state = self._verify_task(state, active_ledger, task, attempt, check)
                    review = await self._await(state, verification.audit_drift(state, check))
                    state = self._commit_drift(state, active_ledger, review, task_id=task.task_id, attempt_id=attempt.attempt_id)
                    if review.invalidate_task_ids:
                        state = self._invalidate(state, active_ledger, review)
                    if review.aligned and task.task_id not in review.invalidate_task_ids:
                        outcomes = learning.record_loaded_outcomes(state, task, attempt, check)
                        promoted = await self._await(state, learning.curate_verify_and_promote(state, task, attempt, check, review))
                        state = self._record_learning(state, active_ledger, outcomes, promoted)
                    if review.decision is DriftDecision.FAIL:
                        return self._pause(state, active_ledger, LongRunningStopReason.PARTIAL_BLOCKED, "global drift auditor rejected committed progress")
                    if review.decision is DriftDecision.REPLAN or review.invalidate_task_ids:
                        if state.replan_count >= self.settings.max_replans:
                            return self._pause(state, active_ledger, LongRunningStopReason.PARTIAL_BLOCKED, "drift requires replan but budget is exhausted")
                        state = await self._revise(state, active_ledger, planner, review)
                    elif review.decision is DriftDecision.SYNTHESIZE:
                        return await self._finalize(state, active_ledger, verification, finalization)
                    continue
                await self._await(state, execution.reject(attempt, check))
                outcomes = learning.record_loaded_outcomes(state, task, attempt, check)
                state = self._record_learning(state, active_ledger, outcomes, ())
                attempts, checks = self._task_history(state, task.task_id)
                no_progress = execution.no_progress(attempts, checks)
                exhausted = self._task_state(state, task.task_id).attempt_count >= self.settings.max_attempts_per_task
                state = self._reject_task(state, active_ledger, task, attempt, check, retry=not exhausted and not no_progress and not check.requires_replan)
                if not exhausted and not no_progress and not check.requires_replan:
                    continue
                review = await self._await(state, verification.audit_drift(state, check))
                state = self._commit_drift(state, active_ledger, review, task_id=task.task_id, attempt_id=attempt.attempt_id)
                if state.replan_count < self.settings.max_replans and review.decision is not DriftDecision.FAIL:
                    state = await self._revise(state, active_ledger, planner, review)
                    continue
                reason = LongRunningStopReason.NO_PROGRESS if no_progress else LongRunningStopReason.VERIFICATION_EXHAUSTED
                return self._pause(state, active_ledger, reason, "task repair/replan budget exhausted")
        except LongRunningRecoveryRequiredError as exc:
            return self._recovery(active_ledger.snapshot().state, active_ledger, str(exc))
        except asyncio.CancelledError:
            current = active_ledger.snapshot().state
            if current.status not in {LongRunningRunStatus.PAUSED, LongRunningRunStatus.RECOVERY_REQUIRED}:
                self._pause(current, active_ledger, LongRunningStopReason.CANCELLED, "controller task cancelled")
            raise
        except TimeoutError:
            return self._pause(active_ledger.snapshot().state, active_ledger, LongRunningStopReason.TIMEOUT, "controller deadline reached")
        except Exception as exc:
            current = active_ledger.snapshot().state
            failed = replace(current, status=LongRunningRunStatus.FAILED, stop_reason=LongRunningStopReason.INTERNAL_ERROR, revision=current.revision + 1)
            active_ledger.commit(failed, LongRunningEventKind.RUN_FAILED, {"error_type": type(exc).__name__})
            raise

    async def _finalize(self, state: LongRunningState, ledger: RunLedger, verification: VerificationService, finalization: FinalizationService) -> LongRunningResult:
        # Run bounded synthesis/audit retries and commit completion only on a pass.
        critique: VerificationResult | None = None
        for attempt_number in range(1, self.settings.max_finalization_attempts + 1):
            candidate = await self._await(state, finalization.synthesize(state, critique))
            state = self._with_usage(replace(state, final_output=candidate, revision=state.revision + 1), ledger)
            ledger.commit(state, LongRunningEventKind.SYNTHESIZED, {"attempt_number": attempt_number, "output_hash": ProcedureIdentity.hash_mapping({"output": candidate})})
            critique = await self._await(state, verification.verify_final(state, candidate))
            state = self._with_usage(replace(state, verifications=(*state.verifications, critique), revision=state.revision + 1), ledger)
            ledger.commit(state, LongRunningEventKind.FINAL_AUDITED, {"attempt_number": attempt_number, "passed": critique.passed, "failure_signature": critique.failure_signature})
            if critique.passed:
                if self.settings.require_procedure_promotion and not state.promoted_procedures:
                    return self._pause(state, ledger, LongRunningStopReason.VERIFICATION_EXHAUSTED, "completion requires at least one promoted or deduplicated procedure")
                state = replace(state, status=LongRunningRunStatus.COMPLETED, stop_reason=LongRunningStopReason.COMPLETED, revision=state.revision + 1)
                ledger.commit(state, LongRunningEventKind.RUN_COMPLETED, {"final_audit_event_id": critique.transcript_event_id})
                return self._result(ledger)
        return self._pause(state, ledger, LongRunningStopReason.VERIFICATION_EXHAUSTED, "final audit attempts exhausted")

    async def _revise(self, state: LongRunningState, ledger: RunLedger, planner: LongRunningPlanner, review: DriftReview) -> LongRunningState:
        # Retry fresh revision plans, then reconcile without erasing verified history.
        errors: list[str] = []
        for attempt_number in range(1, self.settings.max_plan_attempts + 1):
            ledger.append(LongRunningEventKind.PLAN_ATTEMPTED, {"revision_attempt": attempt_number, "prior_errors": tuple(errors)}, role="planner")
            try:
                proposed = await self._await(state, planner.revise(state, review))
                invalidations = {task_id: "; ".join(review.issues) or "global drift review" for task_id in review.invalidate_task_ids}
                graph, task_states = self.reconciler.reconcile(state.graph, state.task_states, proposed, invalidations=invalidations)
                state = self._with_usage(replace(state, graph=graph, task_states=task_states, replan_count=state.replan_count + 1, status=LongRunningRunStatus.RUNNING, revision=state.revision + 1), ledger)
                ledger.commit(state, LongRunningEventKind.PLAN_REVISED, {"graph_version": graph.version, "task_count": len(graph.tasks), "invalidations": invalidations}, role="planner")
                return state
            except LongRunningPlanError as exc:
                errors.append(str(exc))
                ledger.append(LongRunningEventKind.PLAN_VALIDATION_FAILED, {"revision_attempt": attempt_number, "error": exc.to_context_packet()}, role="planner")
        raise LongRunningPlanError("Plan revision attempts were exhausted.", run_id=state.run_id, details={"errors": tuple(errors)})

    async def _reconcile_interrupted(self, state: LongRunningState, ledger: RunLedger, options: LongRunningResumeOptions) -> LongRunningState:
        # Recover ACTIVE tasks conservatively from durable lease evidence or typed authority.
        active = tuple(item for item in state.task_states if item.status is LongRunningTaskStatus.ACTIVE)
        if not active:
            return state
        can_retry_read_only = options.interrupted_attempt_policy is InterruptedAttemptPolicy.RETRY_IF_READ_ONLY and not self._worker_can_side_effect()
        caller_reconciled = options.interrupted_attempt_policy is InterruptedAttemptPolicy.ACCEPT_CALLER_RECONCILIATION and bool(options.reconciliation_reason.strip())
        recovered = False
        if self.attempt_isolator is not None:
            lease = self._latest_open_lease(ledger)
            if lease is not None:
                status = await self.attempt_isolator.recover(lease)
                recovered = status is AttemptIsolationStatus.ROLLED_BACK
                ledger.append(LongRunningEventKind.CHECKPOINTED, {"recovered_isolation_status": status.value, "lease_id": lease.lease_id})
        if not (can_retry_read_only or caller_reconciled or recovered):
            return self._recovery_state(state, ledger, "interrupted ACTIVE attempt requires rollback evidence or typed reconciliation")
        task_states = tuple(replace(item, status=LongRunningTaskStatus.PENDING, invalidation_reason="interrupted-attempt-retry") if item.status is LongRunningTaskStatus.ACTIVE else item for item in state.task_states)
        reason = options.reconciliation_reason.strip() if caller_reconciled else "safe retry after read-only interruption or confirmed rollback"
        state = replace(state, task_states=task_states, status=LongRunningRunStatus.PAUSED, stop_reason=None, revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.CHECKPOINTED, {"interrupted_attempt_reconciled": True, "reason": reason})
        return state

    def _activate(self, state: LongRunningState, ledger: RunLedger, task: LongRunningTask) -> LongRunningState:
        # Mark exactly one ready task ACTIVE before exposing a worker role.
        task_states = tuple(replace(item, status=LongRunningTaskStatus.ACTIVE) if item.task_id == task.task_id else item for item in state.task_states)
        state = replace(state, task_states=task_states, revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.TASK_STARTED, {"definition_hash": task.definition_hash}, task_id=task.task_id)
        return state

    def _record_attempt(self, state: LongRunningState, ledger: RunLedger, task: LongRunningTask, attempt: TaskAttempt) -> LongRunningState:
        # Commit the public attempt and increment task/cycle counters exactly once.
        task_states = tuple(replace(item, attempt_count=item.attempt_count + 1) if item.task_id == task.task_id else item for item in state.task_states)
        state = self._with_usage(replace(state, task_states=task_states, attempts=(*state.attempts, attempt), cycle_count=state.cycle_count + 1, revision=state.revision + 1), ledger)
        ledger.commit(state, LongRunningEventKind.ATTEMPT_RECORDED, {"strategy": attempt.strategy, "loaded_procedures": len(attempt.loaded_procedures), "non_read_tool_succeeded": attempt.non_read_tool_succeeded}, task_id=task.task_id, attempt_id=attempt.attempt_id)
        return state

    def _record_verification(self, state: LongRunningState, ledger: RunLedger, task: LongRunningTask, attempt: TaskAttempt, check: VerificationResult) -> LongRunningState:
        # Commit the combined verifier/validator result before any routing decision.
        state = self._with_usage(replace(state, verifications=(*state.verifications, check), revision=state.revision + 1), ledger)
        ledger.commit(state, LongRunningEventKind.VERIFICATION_COMPLETED, {"passed": check.passed, "failure_signature": check.failure_signature, "requires_replan": check.requires_replan, "transcript_event_id": check.transcript_event_id}, task_id=task.task_id, attempt_id=attempt.attempt_id)
        return state

    def _verify_task(self, state: LongRunningState, ledger: RunLedger, task: LongRunningTask, attempt: TaskAttempt, check: VerificationResult) -> LongRunningState:
        # Materialize a content-addressed verified result and unlock its dependents.
        detail = attempt.summary
        content_hash = ProcedureIdentity.hash_mapping({"task_id": task.task_id, "definition_hash": task.definition_hash, "summary": attempt.summary, "detail": detail, "artifacts": [(item.artifact_id, item.content_hash) for item in attempt.artifacts], "evidence": attempt.evidence})
        result_id = ProcedureIdentity.deterministic_id("result", state.run_id, task.task_id, task.definition_hash, attempt.attempt_id, content_hash)
        verification_event = next(event for event in reversed(ledger.events()) if event.kind is LongRunningEventKind.VERIFICATION_COMPLETED and event.task_id == task.task_id and event.attempt_id == attempt.attempt_id)
        result = TaskResult(result_id, task.task_id, task.definition_hash, attempt.summary, detail, attempt.artifacts, attempt.evidence, verification_event.event_id, content_hash)
        dependency_hashes = tuple((dependency, self._task_state(state, dependency).verified_result_id) for dependency in task.dependencies)
        task_states = tuple(replace(item, status=LongRunningTaskStatus.VERIFIED, verified_result_id=result_id, invalidation_reason="", consumed_dependency_hashes=dependency_hashes) if item.task_id == task.task_id else item for item in state.task_states)
        state = replace(state, task_states=task_states, task_results=(*state.task_results, result), revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.TASK_VERIFIED, {"result_id": result_id, "content_hash": content_hash, "definition_hash": task.definition_hash}, task_id=task.task_id, attempt_id=attempt.attempt_id)
        return state

    def _reject_task(self, state: LongRunningState, ledger: RunLedger, task: LongRunningTask, attempt: TaskAttempt, check: VerificationResult, *, retry: bool) -> LongRunningState:
        # Keep bounded retries pending; otherwise preserve explicit rejected status.
        status = LongRunningTaskStatus.PENDING if retry else LongRunningTaskStatus.REJECTED
        task_states = tuple(replace(item, status=status) if item.task_id == task.task_id else item for item in state.task_states)
        state = replace(state, task_states=task_states, revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.TASK_REJECTED, {"retry": retry, "failure_signature": check.failure_signature}, task_id=task.task_id, attempt_id=attempt.attempt_id)
        if retry:
            ledger.append(LongRunningEventKind.REPAIR_SCHEDULED, {"next_attempt_number": self._task_state(state, task.task_id).attempt_count + 1}, task_id=task.task_id, attempt_id=attempt.attempt_id)
        return state

    def _commit_drift(self, state: LongRunningState, ledger: RunLedger, review: DriftReview, *, task_id: str = "", attempt_id: str = "") -> LongRunningState:
        # Persist the global route decision before invalidation, learning, or synthesis.
        state = self._with_usage(replace(state, drift_reviews=(*state.drift_reviews, review), revision=state.revision + 1), ledger)
        ledger.commit(state, LongRunningEventKind.DRIFT_REVIEWED, {"decision": review.decision.value, "aligned": review.aligned, "issues": review.issues, "invalidate_task_ids": review.invalidate_task_ids}, task_id=task_id, attempt_id=attempt_id, role="auditor")
        return state

    def _invalidate(self, state: LongRunningState, ledger: RunLedger, review: DriftReview) -> LongRunningState:
        # Invalidate named tasks and descendants without deleting historical results.
        reason = "; ".join(review.issues) or "global drift review"
        task_states = self.reconciler.invalidate_descendants(state.graph, state.task_states, review.invalidate_task_ids, reason)
        state = replace(state, task_states=task_states, revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.TASK_INVALIDATED, {"task_ids": review.invalidate_task_ids, "reason": reason})
        return state

    def _record_learning(self, state: LongRunningState, ledger: RunLedger, outcomes: tuple[Any, ...], promoted: tuple[Any, ...]) -> LongRunningState:
        # Add cross-store results to compact state after their intent/completion events exist.
        summaries = tuple(ProcedureSummary(item.ref, item.title, item.summary, item.applicability, item.preconditions, item.tags, item.required_tools) for item in promoted)
        if not outcomes and not summaries:
            return state
        state = replace(state, procedure_outcomes=(*state.procedure_outcomes, *outcomes), promoted_procedures=(*state.promoted_procedures, *summaries), revision=state.revision + 1)
        ledger.commit(state, LongRunningEventKind.CHECKPOINTED, {"procedure_outcomes_added": len(outcomes), "promoted_procedures_added": len(summaries)})
        return state

    def _budget_stop(self, state: LongRunningState, ledger: RunLedger) -> LongRunningResult | None:
        # Enforce runtime, cycles, and observed-token semantics before every stage.
        if state.cycle_count >= self.settings.max_cycles:
            return self._pause(state, ledger, LongRunningStopReason.BUDGET_EXHAUSTED, "maximum controller cycles reached")
        if self._remaining_seconds(state) is not None and self._remaining_seconds(state) <= 0:
            return self._pause(state, ledger, LongRunningStopReason.TIMEOUT, "controller deadline reached")
        if self.settings.max_observed_tokens is not None:
            if self.settings.require_usage_reporting_for_token_budget and state.usage.calls_with_unknown_usage:
                return self._pause(state, ledger, LongRunningStopReason.USAGE_UNAVAILABLE, "provider usage was missing for at least one model call")
            if state.usage.observed_total_tokens >= self.settings.max_observed_tokens:
                return self._pause(state, ledger, LongRunningStopReason.BUDGET_EXHAUSTED, "observed token budget reached")
        return None

    def _pause(self, state: LongRunningState, ledger: RunLedger, reason: LongRunningStopReason, detail: str) -> LongRunningResult:
        # Persist a resumable bounded stop and build the result from the new head.
        current = ledger.snapshot().state
        paused = replace(current, status=LongRunningRunStatus.PAUSED, stop_reason=reason, revision=current.revision + 1)
        ledger.commit(paused, LongRunningEventKind.RUN_PAUSED, {"reason": reason.value, "detail": detail})
        return self._result(ledger)

    def _recovery(self, state: LongRunningState, ledger: RunLedger, detail: str) -> LongRunningResult:
        # Persist a fail-closed recovery boundary and stop all scheduling.
        self._recovery_state(ledger.snapshot().state, ledger, detail)
        return self._result(ledger)

    @staticmethod
    def _recovery_state(state: LongRunningState, ledger: RunLedger, detail: str) -> LongRunningState:
        # Commit recovery-required status without claiming rollback or failure.
        recovered = replace(state, status=LongRunningRunStatus.RECOVERY_REQUIRED, stop_reason=LongRunningStopReason.RECOVERY_REQUIRED, revision=state.revision + 1)
        ledger.commit(recovered, LongRunningEventKind.RECOVERY_REQUIRED, {"detail": detail})
        return recovered

    async def _await(self, state: LongRunningState, awaitable: Any) -> Any:
        # Bound one awaited controller stage by the remaining global deadline.
        remaining = self._remaining_seconds(state)
        if remaining is None:
            return await awaitable
        async with asyncio.timeout(max(0.001, remaining)):
            return await awaitable

    def _with_usage(self, state: LongRunningState, ledger: RunLedger) -> LongRunningState:
        # Recompute observed provider usage from immutable completed-role events.
        input_tokens = 0
        output_tokens = 0
        unknown = 0
        for event in ledger.events():
            if event.kind is not LongRunningEventKind.ROLE_COMPLETED or not event.payload.get("succeeded", True):
                continue
            metadata = event.payload.get("reply_metadata", {})
            usage = metadata.get("usage", {}) if isinstance(metadata, dict) else {}
            if not isinstance(usage, dict):
                usage = {}
            input_value = usage.get("input_tokens", usage.get("prompt_tokens"))
            output_value = usage.get("output_tokens", usage.get("completion_tokens"))
            direct = metadata.get("tokens_used") if isinstance(metadata, dict) else None
            if isinstance(input_value, (int, float)) and isinstance(output_value, (int, float)):
                input_tokens += int(input_value)
                output_tokens += int(output_value)
            elif isinstance(direct, (int, float)):
                output_tokens += int(direct)
            else:
                unknown += 1
        return replace(state, usage=LongRunningUsage(input_tokens, output_tokens, unknown, unknown == 0))

    def _result(self, ledger: RunLedger) -> LongRunningResult:
        # Build the caller view solely from the committed snapshot head.
        snapshot = ledger.snapshot()
        state = snapshot.state
        reason = state.stop_reason or LongRunningStopReason.INTERNAL_ERROR
        return LongRunningResult(state.run_id, state.status, state.status in {LongRunningRunStatus.PAUSED, LongRunningRunStatus.RECOVERY_REQUIRED}, state.final_output, reason, state.status is LongRunningRunStatus.COMPLETED, state.contract, state.graph, state.task_states, state.task_results, state.attempts, state.verifications, state.promoted_procedures, state.procedure_outcomes, state.usage, snapshot, dict(state.metadata))

    def _fingerprint(self) -> str:
        # Include all trusted live components alongside settings and ledger identity.
        components = (*self.validators, *self.procedure_validators, *((self.attempt_isolator,) if self.attempt_isolator is not None else ()))
        procedure_identity = getattr(self.procedure_library.store, "store_identity", None)
        if not callable(procedure_identity):
            raise LongRunningConfigurationError("ProcedureStore must implement store_identity() for durable resume fingerprinting.", details={"store_type": type(self.procedure_library.store).__name__})
        identity = {"ledger": dict(self.ledger_store.store_identity()), "procedures": dict(procedure_identity())}
        return BehaviorFingerprint.for_settings(self.settings, store_identity=identity, extra_components=components)

    def _deadline(self, started_at: str) -> str | None:
        # Derive one immutable UTC deadline from the configured total runtime.
        if self.settings.max_controller_runtime_seconds is None:
            return None
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        return (start + timedelta(seconds=self.settings.max_controller_runtime_seconds)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _remaining_seconds(state: LongRunningState) -> float | None:
        # Return wall-clock deadline remainder for timeout contexts.
        if state.deadline_at is None:
            return None
        deadline = datetime.fromisoformat(state.deadline_at.replace("Z", "+00:00"))
        return (deadline - datetime.now(timezone.utc)).total_seconds()

    @staticmethod
    def _task_state(state: LongRunningState, task_id: str) -> LongRunningTaskState:
        # Resolve one runtime task state or fail on corrupt graph/state joins.
        item = next((candidate for candidate in state.task_states if candidate.task_id == task_id), None)
        if item is None:
            raise LongRunningPlanError("Task graph has no matching runtime state.", run_id=state.run_id, task_id=task_id)
        return item

    @staticmethod
    def _task_history(state: LongRunningState, task_id: str) -> tuple[tuple[TaskAttempt, ...], tuple[VerificationResult, ...]]:
        # Join attempts and task verifications by append order before final-audit entries.
        pairs = tuple((attempt, check) for attempt, check in zip(state.attempts, state.verifications) if attempt.task_id == task_id)
        return tuple(item[0] for item in pairs), tuple(item[1] for item in pairs)

    def _worker_can_side_effect(self) -> bool:
        # Conservatively detect configured non-read worker/repair capabilities.
        if self.settings.worker_include_execution or self.settings.worker_include_write:
            return True
        for role in (self.settings.worker, self.settings.repairer):
            for tool in role.tools:
                spec = getattr(tool, "spec", None)
                if not callable(spec) or spec().permission not in {ToolPermission.READ, ToolPermission.SAFE}:
                    return True
        return False

    @staticmethod
    def _failed_attempt(state: LongRunningState, task: LongRunningTask, exc: Exception, ledger: RunLedger) -> TaskAttempt:
        # Normalize a read-only role exception into auditable failed-attempt evidence.
        task_state = next(item for item in state.task_states if item.task_id == task.task_id)
        number = task_state.attempt_count + 1
        attempt_id = ProcedureIdentity.deterministic_id("attempt", state.run_id, task.task_id, str(number))
        event = ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"succeeded": False, "error_type": type(exc).__name__}, task_id=task.task_id, attempt_id=attempt_id, role="worker")
        return TaskAttempt(attempt_id, task.task_id, number, "execution-error", "", (), (), (), (f"{type(exc).__name__}: {exc}",), event.event_id, None)

    @staticmethod
    def _latest_open_lease(ledger: RunLedger) -> AttemptLease | None:
        # Rehydrate the newest checkpointed OPEN lease for isolator recovery.
        for event in reversed(ledger.events()):
            if event.kind is not LongRunningEventKind.CHECKPOINTED or event.payload.get("isolation_status") != AttemptIsolationStatus.OPEN.value:
                continue
            raw = event.payload.get("lease", {})
            if isinstance(raw, dict) and raw.get("lease_id"):
                return AttemptLease(str(raw.get("isolator_id", "")), str(raw.get("isolator_version", "")), str(raw["lease_id"]), raw.get("metadata", {}))
        return None


__all__ = ["LongRunningController"]
