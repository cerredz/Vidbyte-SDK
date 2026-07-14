"""Context Protocol Header

Path: vidbyte/paradigms/long_running/verification.py
Purpose: Independently verify tasks/finals, audit drift, and gate procedure learning.
Architecture: VerificationService combines fresh read-only roles with trusted validators;
ProcedureLearningService journals cross-store mutations; ledger authority rechecks the
committed source task/drift/fingerprint; FinalizationService synthesizes verified work.
Exports: validator protocols and verification, learning, authority, finalization services.
Invariants: Criteria match exactly, required validators fail closed, drift precedes
learning, and only exact loaded procedure refs receive outcomes.
Do not: Trust worker self-assessment, promote candidates from stale state, or teach from
locally passing work that the global auditor invalidated.
Related: docs/design/long-running-paradigm.md section 6.9 and controller.py.
Tests: Existing tool/agent verification plus inline lifecycle smoke; no new tests under
the approved design-doc-no-tests workflow.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from vidbyte.paradigms.long_running.context import LongRunningContextBroker
from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError, LongRunningVerificationError
from vidbyte.paradigms.long_running.ledger import LongRunningEventKind, RunLedger
from vidbyte.paradigms.long_running.types import CriterionResult, DriftDecision, DriftReview, LongRunningState, LongRunningTask, LongRunningTaskStatus, ProcedureValidationContext, TaskAttempt, TaskValidationContext, ValidatorResult, VerificationResult
from vidbyte.procedures import ProcedureCheckResult, ProcedureLibrary, ProcedureOutcome, ProcedureRecord, ProcedureRef, ProcedureStatus, ProcedureVerificationEvidence
from vidbyte.procedures.serialization import ProcedureIdentity
from vidbyte.tools.builtins.output_schema import OutputSchemaBuilder
from vidbyte.tools.builtins.procedures import StageProcedureTool


class TaskValidator(Protocol):
    """Trusted deterministic inspection contract for one exact task attempt."""

    validator_id: str
    validator_version: str
    required: bool
    timeout_seconds: float

    def behavior_fingerprint(self) -> Mapping[str, Any]:
        # Return stable non-secret validator configuration.
        ...

    async def validate(self, context: TaskValidationContext) -> ValidatorResult:
        # Return an evidence-backed result for the exact context.
        ...


class ProcedureValidator(Protocol):
    """Trusted deterministic inspection contract for one exact staged candidate."""

    validator_id: str
    validator_version: str
    required: bool
    timeout_seconds: float

    def behavior_fingerprint(self) -> Mapping[str, Any]:
        # Return stable non-secret validator configuration.
        ...

    async def validate(self, context: ProcedureValidationContext) -> ProcedureCheckResult:
        # Return a fidelity result for the exact candidate and source evidence.
        ...


class VerificationService:
    """Combine fresh model inspection with timeout-bounded trusted validators."""

    def __init__(self, broker: LongRunningContextBroker, ledger: RunLedger, validators: Sequence[TaskValidator] = ()) -> None:
        # Validate stable unique validator identities before any model or command work.
        self.broker = broker
        self.ledger = ledger
        self.validators = tuple(validators)
        self._require_unique(self.validators, "task validator")

    async def verify_task(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt) -> VerificationResult:
        # Require an exact criterion judgment and combine it with trusted checks.
        builder = OutputSchemaBuilder()
        agent = self.broker.build_verifier(state, task, attempt, builder)
        self.ledger.append(LongRunningEventKind.ROLE_STARTED, {"criteria_count": len(task.acceptance_criteria)}, task_id=task.task_id, attempt_id=attempt.attempt_id, role="verifier")
        reply = await agent.arun(self._verify_message(task, attempt))
        event = self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"public_transcript": agent.export_state().history, "reply_metadata": dict(reply.metadata)}, task_id=task.task_id, attempt_id=attempt.attempt_id, role="verifier")
        values = self._values(builder, reply.content)
        criteria, structural_violations = self._criteria(task, values.get("criteria", ()))
        validator_results = await self._task_validators(state, task, attempt)
        violations = (*structural_violations, *self._texts(values.get("violations", ())), *(result.error_message or f"validator {result.validator_id} failed" for result in validator_results if result.required and not result.passed))
        passed = bool(criteria) and all(item.passed for item in criteria) and not violations and all(not item.required or item.passed for item in validator_results)
        signature = str(values.get("failure_signature", "")).strip()
        if not passed and not signature:
            signature = ProcedureIdentity.hash_mapping({"criteria": [(item.criterion_id, item.passed) for item in criteria], "violations": list(violations), "validators": [(item.validator_id, item.passed, item.error_code) for item in validator_results]})
        suspected = self._suspected(values.get("suspected_procedures", ()), attempt.loaded_procedures)
        return VerificationResult(passed, criteria, self._texts(values.get("evidence", ())), tuple(violations), self._texts(values.get("repair_instructions", ())), signature, suspected, bool(values.get("requires_replan", False)), validator_results, event.event_id)

    async def audit_drift(self, state: LongRunningState, latest: VerificationResult | None = None) -> DriftReview:
        # Run one fresh global contract comparison with a bounded decision vocabulary.
        builder = OutputSchemaBuilder()
        agent = self.broker.build_auditor(state, builder, latest)
        self.ledger.append(LongRunningEventKind.ROLE_STARTED, {"graph_version": state.graph.version}, role="auditor")
        reply = await agent.arun("Audit committed progress against the exact root contract. Return decision, aligned, issues, invalidate_task_ids, proposed_work, and rationale through output-schema tools.")
        self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"public_transcript": agent.export_state().history, "reply_metadata": dict(reply.metadata)}, role="auditor")
        values = self._values(builder, reply.content)
        try:
            decision = DriftDecision(str(values.get("decision", DriftDecision.FAIL.value)).strip().lower())
        except ValueError:
            decision = DriftDecision.FAIL
        known = {task.task_id for task in state.graph.tasks}
        requested = self._texts(values.get("invalidate_task_ids", ()))
        unknown = tuple(item for item in requested if item not in known)
        issues = (*self._texts(values.get("issues", ())), *((f"auditor named unknown task id {item}" for item in unknown)))
        aligned = bool(values.get("aligned", False)) and not unknown and decision is not DriftDecision.FAIL
        return DriftReview(decision, aligned, tuple(issues), tuple(item for item in requested if item in known), self._texts(values.get("proposed_work", ())), str(values.get("rationale", "")).strip())

    async def verify_final(self, state: LongRunningState, candidate: str) -> VerificationResult:
        # Reuse the fail-closed criterion/validator path against the actual root output.
        criteria = state.contract.success_criteria or ("The final output satisfies the exact original prompt and invariants.",)
        task = LongRunningTask("final", "Final root contract audit", "Inspect the synthesized candidate against the exact root contract.", (), criteria, "final root verification")
        attempt_id = ProcedureIdentity.deterministic_id("final-attempt", state.run_id, str(state.revision), ProcedureIdentity.hash_mapping({"candidate": candidate}))
        attempt = TaskAttempt(attempt_id, task.task_id, 1, "final-synthesis", candidate, (), (candidate,), (), (), "", None)
        return await self.verify_task(state, task, attempt)

    async def _task_validators(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt) -> tuple[ValidatorResult, ...]:
        # Run validators serially with individual timeouts and normalize every failure.
        context = TaskValidationContext(state.run_id, state.contract, task, attempt, (), attempt.artifacts, str(self.broker.settings.default_tool_root), state.deadline_at)
        results: list[ValidatorResult] = []
        for validator in self.validators:
            started = time.monotonic()
            fingerprint = self._fingerprint(validator)
            try:
                async with asyncio.timeout(float(validator.timeout_seconds)):
                    result = await validator.validate(context)
                if result.validator_id != validator.validator_id or result.validator_version != validator.validator_version or result.required != bool(validator.required) or result.config_fingerprint != fingerprint:
                    raise ValueError("validator result identity/configuration does not match the registered validator")
                results.append(result)
            except TimeoutError:
                results.append(ValidatorResult(validator.validator_id, validator.validator_version, fingerprint, bool(validator.required), False, error_code="timeout", error_message="Validator exceeded its declared timeout.", duration_ms=int((time.monotonic() - started) * 1000)))
            except Exception as exc:
                results.append(ValidatorResult(validator.validator_id, validator.validator_version, fingerprint, bool(validator.required), False, error_code="exception", error_message=f"{type(exc).__name__}: {exc}", duration_ms=int((time.monotonic() - started) * 1000)))
        return tuple(results)

    @classmethod
    def _criteria(cls, task: LongRunningTask, raw: object) -> tuple[tuple[CriterionResult, ...], tuple[str, ...]]:
        # Require one ordered, exact-text result for every stable criterion id.
        expected = tuple((cls.criterion_id(task.task_id, index, text), text) for index, text in enumerate(task.acceptance_criteria))
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            raw = ()
        parsed = tuple(item for item in raw if isinstance(item, Mapping))
        violations: list[str] = []
        results: list[CriterionResult] = []
        if len(parsed) != len(expected):
            violations.append(f"verifier returned {len(parsed)} criterion results; expected {len(expected)}")
        for index, (criterion_id, criterion) in enumerate(expected):
            item = parsed[index] if index < len(parsed) else {}
            if str(item.get("criterion_id", "")) != criterion_id or str(item.get("criterion", "")) != criterion:
                violations.append(f"criterion result {index} did not preserve exact id/text/order")
            results.append(CriterionResult(criterion_id, criterion, bool(item.get("passed", False)), cls._texts(item.get("observations", ())), cls._texts(item.get("evidence_refs", ())), cls._texts(item.get("violations", ()))))
        return tuple(results), tuple(violations)

    @staticmethod
    def criterion_id(task_id: str, index: int, criterion: str) -> str:
        # Derive stable criterion identity from task id, position, and exact text.
        return ProcedureIdentity.deterministic_id("criterion", task_id, str(index), criterion)

    @staticmethod
    def _suspected(raw: object, loaded: Sequence[ProcedureRef]) -> tuple[ProcedureRef, ...]:
        # Accept only exact refs that were authoritatively loaded during this attempt.
        loaded_by_key = {(item.namespace, item.procedure_id, item.version, item.content_fingerprint): item for item in loaded}
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            return ()
        selected: list[ProcedureRef] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            key = (str(item.get("namespace", "")), str(item.get("procedure_id", "")), int(item.get("version", 0)), str(item.get("content_fingerprint", "")))
            ref = loaded_by_key.get(key)
            if ref is not None and ref not in selected:
                selected.append(ref)
        return tuple(selected)

    @staticmethod
    def _verify_message(task: LongRunningTask, attempt: TaskAttempt) -> str:
        # Advertise exact stable criterion ids so the verifier cannot reorder silently.
        criteria = [{"criterion_id": VerificationService.criterion_id(task.task_id, index, text), "criterion": text} for index, text in enumerate(task.acceptance_criteria)]
        return f"Verify attempt {attempt.attempt_id}. Return exactly these criteria in order: {json.dumps(criteria, ensure_ascii=False)}. Also return evidence, violations, repair_instructions, failure_signature, suspected_procedures, and requires_replan."

    @staticmethod
    def _values(builder: OutputSchemaBuilder, fallback: str) -> Mapping[str, Any]:
        # Prefer authoritative output-tool state, then accept one JSON object.
        values = builder.snapshot().get("values", {})
        if isinstance(values, Mapping) and values:
            return values
        try:
            parsed = json.loads(fallback)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}

    @staticmethod
    def _texts(value: object) -> tuple[str, ...]:
        # Normalize one scalar or array without splitting strings into characters.
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(text for item in value if (text := str(item).strip()))
        text = str(value).strip()
        return (text,) if text else ()

    @staticmethod
    def _fingerprint(validator: object) -> str:
        # Hash stable behavior fields and fail closed when the component omits them.
        provider = getattr(validator, "behavior_fingerprint", None)
        if not callable(provider):
            raise LongRunningConfigurationError("Validator must implement behavior_fingerprint().", details={"validator_type": type(validator).__name__})
        value = provider()
        if not isinstance(value, Mapping) or not value:
            raise LongRunningConfigurationError("Validator behavior_fingerprint() must return a non-empty mapping.", details={"validator_type": type(validator).__name__})
        return ProcedureIdentity.hash_mapping(dict(value))

    @staticmethod
    def _require_unique(validators: Sequence[object], label: str) -> None:
        # Reject duplicate stable ids because evidence combination would become ambiguous.
        ids = tuple(str(getattr(item, "validator_id", "")).strip() for item in validators)
        if any(not item for item in ids) or len(ids) != len(set(ids)):
            raise LongRunningConfigurationError(f"Every {label} must have a unique non-empty validator_id.", details={"validator_ids": ids})


class LedgerProcedurePromotionAuthority:
    """Revalidate procedure evidence against the active committed run ledger."""

    def __init__(self, ledger: RunLedger) -> None:
        # Bind the active ledger rather than trusting stale service arguments.
        self.ledger = ledger

    def authorize(self, candidate: ProcedureRecord, evidence: ProcedureVerificationEvidence) -> None:
        # Require current verified task, matching events, aligned drift, and exact fingerprint.
        snapshot = self.ledger.snapshot()
        state = snapshot.state
        task_state = next((item for item in state.task_states if item.task_id == evidence.task_id), None)
        if state.run_id != evidence.run_id or task_state is None or task_state.status is not LongRunningTaskStatus.VERIFIED:
            raise LongRunningVerificationError("Procedure source task is not VERIFIED in the active ledger.", run_id=evidence.run_id, task_id=evidence.task_id, attempt_id=evidence.attempt_id)
        if candidate.content_fingerprint != evidence.candidate_content_fingerprint:
            raise LongRunningVerificationError("Procedure candidate fingerprint changed after fidelity verification.", run_id=evidence.run_id, task_id=evidence.task_id)
        events = {event.event_id: event for event in self.ledger.events()}
        verification_event = events.get(evidence.source_task_verification_event_id)
        drift_event = events.get(evidence.source_drift_review_event_id)
        if verification_event is None or verification_event.kind is not LongRunningEventKind.VERIFICATION_COMPLETED or verification_event.task_id != evidence.task_id or verification_event.attempt_id != evidence.attempt_id or not bool(verification_event.payload.get("passed")):
            raise LongRunningVerificationError("Procedure evidence does not reference a passing task-verification event.", run_id=evidence.run_id, task_id=evidence.task_id)
        if drift_event is None or drift_event.kind is not LongRunningEventKind.DRIFT_REVIEWED or not bool(drift_event.payload.get("aligned")) or evidence.task_id in tuple(drift_event.payload.get("invalidate_task_ids", ())):
            raise LongRunningVerificationError("Procedure evidence does not reference an aligned non-invalidating drift review.", run_id=evidence.run_id, task_id=evidence.task_id)
        latest_drift = next((event for event in reversed(self.ledger.events()) if event.kind is LongRunningEventKind.DRIFT_REVIEWED), None)
        if latest_drift is None or latest_drift.event_id != drift_event.event_id:
            raise LongRunningVerificationError("Procedure evidence does not reference the latest applicable drift review.", run_id=evidence.run_id, task_id=evidence.task_id)
        fidelity = next((event for event in reversed(self.ledger.events()) if event.kind is LongRunningEventKind.PROCEDURE_FIDELITY_VERIFIED and event.payload.get("candidate", {}).get("content_fingerprint") == candidate.content_fingerprint), None)
        if fidelity is None or not bool(fidelity.payload.get("passed")):
            raise LongRunningVerificationError("Procedure promotion lacks a passing committed fidelity event.", run_id=evidence.run_id, task_id=evidence.task_id)


class ProcedureLearningService:
    """Curate, verify, promote, and account for exact loaded procedures."""

    def __init__(self, broker: LongRunningContextBroker, library: ProcedureLibrary, ledger: RunLedger, validators: Sequence[ProcedureValidator] = ()) -> None:
        # Bind cross-store services and reject ambiguous procedure validator ids.
        self.broker = broker
        self.library = library
        self.ledger = ledger
        self.validators = tuple(validators)
        VerificationService._require_unique(self.validators, "procedure validator")

    async def curate_verify_and_promote(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult, drift: DriftReview) -> tuple[ProcedureRecord, ...]:
        # Stage candidates, fidelity-check exact versions, and promote through a ledger saga.
        if not verification.passed or not drift.aligned or task.task_id in drift.invalidate_task_ids:
            return ()
        source_events = self._source_events(task, attempt, verification)
        stage_tool = StageProcedureTool(self.library, run_id=state.run_id, task_id=task.task_id, attempt_id=attempt.attempt_id, namespace=self.broker.settings.procedure_namespace, environment_fingerprint=self.broker.settings.environment_fingerprint, max_body_chars=self.broker.settings.max_procedure_body_chars, allowed_evidence_event_ids=source_events)
        builder = OutputSchemaBuilder()
        bundle = self.broker.build_curator_bundle(state, task, attempt, builder, (stage_tool,))
        self.ledger.append(LongRunningEventKind.ROLE_STARTED, {"source_event_ids": source_events}, task_id=task.task_id, attempt_id=attempt.attempt_id, role="curator")
        reply = await bundle.agent.arun("Extract only genuinely reusable successful procedures. Use procedure_stage for each candidate; zero candidates is valid.")
        self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"public_transcript": bundle.agent.export_state().history, "reply_metadata": dict(reply.metadata), "staged_refs": [self._ref_mapping(ref) for ref in stage_tool.staged_refs]}, task_id=task.task_id, attempt_id=attempt.attempt_id, role="curator")
        promoted: list[ProcedureRecord] = []
        for ref in stage_tool.staged_refs:
            candidate = self._candidate(ref)
            self.ledger.append(LongRunningEventKind.PROCEDURE_STAGED, {"candidate": self._ref_mapping(ref)}, task_id=task.task_id, attempt_id=attempt.attempt_id)
            try:
                evidence = await self._fidelity_evidence(state, task, attempt, verification, drift, candidate, source_events)
                operation_id = ProcedureIdentity.deterministic_id("promote", candidate.namespace, candidate.procedure_id, str(candidate.version), candidate.content_fingerprint, evidence.evidence_hash)
                self.ledger.append(LongRunningEventKind.PROCEDURE_LEARNING_INTENT, {"operation_id": operation_id, "candidate": self._ref_mapping(candidate.ref), "evidence_hash": evidence.evidence_hash}, task_id=task.task_id, attempt_id=attempt.attempt_id)
                record = self.library.promote(candidate.ref, evidence, operation_id=operation_id, authority=LedgerProcedurePromotionAuthority(self.ledger))
                self.ledger.append(LongRunningEventKind.PROCEDURE_PROMOTED, {"record": self._ref_mapping(record.ref), "status": record.status.value}, task_id=task.task_id, attempt_id=attempt.attempt_id)
                self.ledger.append(LongRunningEventKind.PROCEDURE_LEARNING_COMPLETED, {"operation_id": operation_id, "record": self._ref_mapping(record.ref)}, task_id=task.task_id, attempt_id=attempt.attempt_id)
                promoted.append(record)
            except Exception as exc:
                operation_id = ProcedureIdentity.deterministic_id("reject", candidate.namespace, candidate.procedure_id, str(candidate.version), candidate.content_fingerprint)
                try:
                    rejected = self.library.reject(candidate.ref, f"fidelity-or-promotion-failed:{type(exc).__name__}", operation_id=operation_id)
                    rejected_ref = self._ref_mapping(rejected.ref)
                except Exception:
                    rejected_ref = self._ref_mapping(candidate.ref)
                self.ledger.append(LongRunningEventKind.PROCEDURE_REJECTED, {"candidate": rejected_ref, "error_type": type(exc).__name__}, task_id=task.task_id, attempt_id=attempt.attempt_id)
        return tuple(promoted)

    def record_loaded_outcomes(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult) -> tuple[ProcedureOutcome, ...]:
        # Record success for every loaded ref or failure only for explicitly suspected refs.
        selected = attempt.loaded_procedures if verification.passed else verification.suspected_procedures
        outcomes: list[ProcedureOutcome] = []
        for ref in selected:
            suspected = not verification.passed
            reason = "verified task and aligned drift" if verification.passed else f"suspected by verifier:{verification.failure_signature}"
            outcome_id = ProcedureIdentity.deterministic_id("outcome", state.run_id, task.task_id, attempt.attempt_id, ref.namespace, ref.procedure_id, str(ref.version), ref.content_fingerprint, str(verification.passed))
            outcome = ProcedureOutcome(outcome_id, ref, state.run_id, task.task_id, attempt.attempt_id, verification.passed, suspected, reason, ProcedureIdentity.utc_now())
            self.ledger.append(LongRunningEventKind.PROCEDURE_OUTCOME_INTENT, {"outcome_id": outcome_id, "procedure": self._ref_mapping(ref), "succeeded": outcome.succeeded, "suspected_failure": outcome.suspected_failure}, task_id=task.task_id, attempt_id=attempt.attempt_id)
            retired = self.library.record_outcome(outcome, retire_after_suspected_failures=self.broker.settings.retire_after_suspected_failures)
            self.ledger.append(LongRunningEventKind.PROCEDURE_OUTCOME_COMPLETED, {"outcome_id": outcome_id, "retired": None if retired is None else self._ref_mapping(retired.ref)}, task_id=task.task_id, attempt_id=attempt.attempt_id)
            outcomes.append(outcome)
        return tuple(outcomes)

    async def _fidelity_evidence(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult, drift: DriftReview, candidate: ProcedureRecord, source_events: tuple[str, ...]) -> ProcedureVerificationEvidence:
        # Combine one fresh model fidelity check with every required trusted validator.
        builder = OutputSchemaBuilder()
        agent = self.broker.build_procedure_verifier(state, task, attempt, candidate, builder)
        self.ledger.append(LongRunningEventKind.ROLE_STARTED, {"candidate": self._ref_mapping(candidate.ref)}, task_id=task.task_id, attempt_id=attempt.attempt_id, role="procedure_verifier")
        reply = await agent.arun("Verify the exact staged procedure against successful source evidence. Return passed, observations, criteria, and violations through output-schema tools.")
        role_event = self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"public_transcript": agent.export_state().history, "reply_metadata": dict(reply.metadata), "candidate_fingerprint": candidate.content_fingerprint}, task_id=task.task_id, attempt_id=attempt.attempt_id, role="procedure_verifier")
        values = VerificationService._values(builder, reply.content)
        observations = VerificationService._texts(values.get("observations", ()))
        criteria = VerificationService._texts(values.get("criteria", ())) or ("Candidate faithfully captures the verified successful procedure.",)
        model_result = ProcedureCheckResult("long_running_model_fidelity", "1", candidate.content_fingerprint, True, bool(values.get("passed", False)) and bool(observations), observations, "" if values.get("passed", False) else "model_fidelity_failed", "; ".join(VerificationService._texts(values.get("violations", ()))), 0)
        deterministic = await self._procedure_validators(state, task, attempt, verification, drift, candidate, source_events)
        checks = (model_result, *deterministic)
        event = self.ledger.append(LongRunningEventKind.PROCEDURE_FIDELITY_VERIFIED, {"candidate": self._ref_mapping(candidate.ref), "passed": all(not item.required or item.passed for item in checks), "role_event_id": role_event.event_id, "checks": [(item.validator_id, item.passed) for item in checks]}, task_id=task.task_id, attempt_id=attempt.attempt_id)
        task_event, drift_event = self._verification_and_drift_events(task.task_id, attempt.attempt_id)
        task_checks = tuple(ProcedureCheckResult(item.validator_id, item.validator_version, item.config_fingerprint, item.required, item.passed, item.evidence, item.error_code, item.error_message, item.duration_ms) for item in verification.validator_results)
        payload = {"candidate": candidate.content_fingerprint, "criteria": criteria, "observations": observations, "task_event": task_event, "drift_event": drift_event, "checks": [(item.validator_id, item.passed, item.config_fingerprint) for item in checks], "fidelity_event": event.event_id}
        return ProcedureVerificationEvidence(state.run_id, task.task_id, attempt.attempt_id, task_event, drift_event, candidate.content_fingerprint, criteria, observations, task_checks, tuple(checks), "long-running-procedure-verifier", ProcedureIdentity.utc_now(), ProcedureIdentity.hash_mapping(payload))

    async def _procedure_validators(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult, drift: DriftReview, candidate: ProcedureRecord, source_events: tuple[str, ...]) -> tuple[ProcedureCheckResult, ...]:
        # Normalize procedure validator timeout, exception, and identity failures.
        context = ProcedureValidationContext(state.run_id, state.contract, task, attempt, verification, drift, candidate, source_events, (), tuple(spec.name for spec in self.broker.build_worker_bundle(state, task, (), OutputSchemaBuilder()).agent.tool_specs()), self.broker.settings.environment_fingerprint, state.deadline_at)
        results: list[ProcedureCheckResult] = []
        for validator in self.validators:
            started = time.monotonic()
            fingerprint = VerificationService._fingerprint(validator)
            try:
                async with asyncio.timeout(float(validator.timeout_seconds)):
                    result = await validator.validate(context)
                if result.validator_id != validator.validator_id or result.validator_version != validator.validator_version or result.required != bool(validator.required) or result.config_fingerprint != fingerprint:
                    raise ValueError("procedure validator result identity/configuration mismatch")
                results.append(result)
            except TimeoutError:
                results.append(ProcedureCheckResult(validator.validator_id, validator.validator_version, fingerprint, bool(validator.required), False, (), "timeout", "Procedure validator exceeded its declared timeout.", int((time.monotonic() - started) * 1000)))
            except Exception as exc:
                results.append(ProcedureCheckResult(validator.validator_id, validator.validator_version, fingerprint, bool(validator.required), False, (), "exception", f"{type(exc).__name__}: {exc}", int((time.monotonic() - started) * 1000)))
        return tuple(results)

    def _source_events(self, task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult) -> tuple[str, ...]:
        # Build the exact successful public evidence allowlist for staging.
        task_event, drift_event = self._verification_and_drift_events(task.task_id, attempt.attempt_id)
        return tuple(dict.fromkeys((attempt.transcript_event_id, verification.transcript_event_id, task_event, drift_event)))

    def _verification_and_drift_events(self, task_id: str, attempt_id: str) -> tuple[str, str]:
        # Resolve newest passing verification and aligned drift events for the source.
        events = self.ledger.events()
        verification = next((event for event in reversed(events) if event.kind is LongRunningEventKind.VERIFICATION_COMPLETED and event.task_id == task_id and event.attempt_id == attempt_id and bool(event.payload.get("passed"))), None)
        drift = next((event for event in reversed(events) if event.kind is LongRunningEventKind.DRIFT_REVIEWED and bool(event.payload.get("aligned")) and task_id not in tuple(event.payload.get("invalidate_task_ids", ()))), None)
        if verification is None or drift is None:
            raise LongRunningVerificationError("Procedure learning requires committed passing verification and aligned drift events.", run_id=self.ledger.snapshot().run_id, task_id=task_id, attempt_id=attempt_id)
        return verification.event_id, drift.event_id

    def _candidate(self, ref: ProcedureRef) -> ProcedureRecord:
        # Re-read the exact staged version and fingerprint before fidelity work.
        record = self.library.store.get(ref.namespace, ref.procedure_id, ref.version)
        if record.status is not ProcedureStatus.CANDIDATE or record.content_fingerprint != ref.content_fingerprint:
            raise LongRunningVerificationError("Staged candidate changed or is no longer a candidate.", run_id=self.ledger.snapshot().run_id, task_id=record.source_task_id, attempt_id=record.source_attempt_id)
        return record

    @staticmethod
    def _ref_mapping(ref: ProcedureRef) -> Mapping[str, Any]:
        # Serialize exact version identity for events and idempotent sagas.
        return {"namespace": ref.namespace, "procedure_id": ref.procedure_id, "version": ref.version, "content_fingerprint": ref.content_fingerprint}


class FinalizationService:
    """Synthesize caller output only from committed verified task results."""

    def __init__(self, broker: LongRunningContextBroker, ledger: RunLedger) -> None:
        # Bind fresh finalizer construction and its active audit ledger.
        self.broker = broker
        self.ledger = ledger

    async def synthesize(self, state: LongRunningState, critique: VerificationResult | None = None) -> str:
        # Run a fresh synthesis role with verified handles/summaries and prior critique only.
        builder = OutputSchemaBuilder()
        agent = self.broker.build_synthesizer(state, builder, critique)
        self.ledger.append(LongRunningEventKind.ROLE_STARTED, {"verified_results": len(state.task_results)}, role="synthesizer")
        reply = await agent.arun("Synthesize the final caller-facing answer from VERIFIED, non-invalidated results. Return final_output through output-schema tools.")
        self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"public_transcript": agent.export_state().history, "reply_metadata": dict(reply.metadata)}, role="synthesizer")
        values = VerificationService._values(builder, reply.content)
        return str(values.get("final_output", reply.content)).strip()


__all__ = ["FinalizationService", "LedgerProcedurePromotionAuthority", "ProcedureLearningService", "ProcedureValidator", "TaskValidator", "VerificationService"]
