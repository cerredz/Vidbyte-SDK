"""Context Protocol Header

Path: vidbyte/paradigms/long_running/execution.py
Purpose: Run one isolated fresh worker/repair attempt and capture authoritative usage.
Architecture: TaskExecutionService owns procedure retrieval, attempt leases, role
events, structured parsing, loaded-ref replacement, and no-progress comparison.
Exports: TaskExecutionService, AttemptIsolationStatus, AttemptLease, AttemptIsolator.
Invariants: Attempts are fresh, load records override model claims, leases checkpoint
before non-read tools, and rejected side effects require rollback or recovery.
Do not: Verify attempts, commit task success, promote procedures, or reuse agents.
Related: docs/design/long-running-paradigm.md section 6.8 and controller.py.
Tests: Existing agent/tool verification plus inline service smoke; no new tests under
the approved design-doc-no-tests workflow.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from vidbyte.paradigms.long_running.context import LongRunningContextBroker, RoleAgentBundle
from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError, LongRunningRecoveryRequiredError
from vidbyte.paradigms.long_running.ledger import LongRunningEventKind, RunLedger
from vidbyte.paradigms.long_running.types import ArtifactRef, LongRunningState, LongRunningTask, TaskAttempt, VerificationResult
from vidbyte.procedures import ProcedureLibrary
from vidbyte.procedures.serialization import ProcedureIdentity
from vidbyte.tools.builtins.output_schema import OutputSchemaBuilder
from vidbyte.tools.types import ToolCallState, ToolPermission, ToolStatus


class AttemptIsolationStatus(str, Enum):
    """Recovered external isolation state for one durable lease."""

    OPEN = "open"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AttemptLease:
    """Serializable lease returned before mutating attempt tools are exposed."""

    isolator_id: str
    isolator_version: str
    lease_id: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Copy serializable metadata so external mutation cannot rewrite recovery evidence.
        object.__setattr__(self, "metadata", dict(self.metadata))


class AttemptIsolator(Protocol):
    """Caller-supplied transaction/sandbox boundary for non-read worker tools."""

    isolator_id: str
    isolator_version: str

    def behavior_fingerprint(self) -> Mapping[str, Any]:
        # Return stable, non-secret behavior fields for resume compatibility.
        ...

    async def begin(self, run_id: str, task: LongRunningTask, attempt_id: str) -> AttemptLease:
        # Open an isolation boundary before any attempt side effect can run.
        ...

    async def recover(self, lease: AttemptLease) -> AttemptIsolationStatus:
        # Reconcile an interrupted durable lease during resume.
        ...

    async def commit(self, lease: AttemptLease, verification: VerificationResult) -> None:
        # Make an independently verified attempt's side effects durable.
        ...

    async def rollback(self, lease: AttemptLease, verification: VerificationResult) -> None:
        # Undo a rejected attempt's side effects or raise when rollback is uncertain.
        ...


class TaskExecutionService:
    """Execute or repair one task in a fresh, bounded role context."""

    def __init__(self, broker: LongRunningContextBroker, procedure_library: ProcedureLibrary, ledger: RunLedger, *, attempt_isolator: AttemptIsolator | None = None) -> None:
        # Bind one active ledger and optional side-effect isolation authority.
        self.broker = broker
        self.procedure_library = procedure_library
        self.ledger = ledger
        self.attempt_isolator = attempt_isolator

    async def execute(self, state: LongRunningState, task: LongRunningTask) -> TaskAttempt:
        # Run the first/new strategy path for one pending task.
        matches = self._matches(task)
        builder = OutputSchemaBuilder()
        bundle = self.broker.build_worker_bundle(state, task, matches, builder)
        return await self._run(state, task, builder, bundle, role="worker", message=self._worker_message(task))

    async def repair(self, state: LongRunningState, task: LongRunningTask, latest_attempt: TaskAttempt, verification: VerificationResult) -> TaskAttempt:
        # Run a fresh repair role with exact last-attempt failure evidence.
        matches = self._matches(task)
        builder = OutputSchemaBuilder()
        bundle = self.broker.build_repairer_bundle(state, task, latest_attempt, verification, matches, builder)
        return await self._run(state, task, builder, bundle, role="repairer", message=self._repair_message(task, latest_attempt, verification))

    def no_progress(self, attempts: Sequence[TaskAttempt], verifications: Sequence[VerificationResult]) -> bool:
        # Detect repeated normalized strategy/failure pairs over the configured window.
        count = self.broker.settings.max_no_progress_cycles
        if len(attempts) < count or len(verifications) < count:
            return False
        pairs = tuple((self._normalize(item.strategy), self._normalize(check.failure_signature)) for item, check in zip(attempts[-count:], verifications[-count:]))
        return bool(pairs) and len(set(pairs)) == 1

    async def accept(self, attempt: TaskAttempt, verification: VerificationResult) -> None:
        # Commit an open isolator lease only after independent verification passes.
        lease = self._lease(attempt)
        if lease is None or self.attempt_isolator is None:
            return
        await self.attempt_isolator.commit(lease, verification)
        self.ledger.append(LongRunningEventKind.CHECKPOINTED, {"isolation_status": AttemptIsolationStatus.COMMITTED.value, "lease_id": lease.lease_id}, task_id=attempt.task_id, attempt_id=attempt.attempt_id)

    async def reject(self, attempt: TaskAttempt, verification: VerificationResult) -> None:
        # Roll back rejected side effects or fail closed when contamination is possible.
        lease = self._lease(attempt)
        if lease is not None and self.attempt_isolator is not None:
            try:
                await self.attempt_isolator.rollback(lease, verification)
            except Exception as exc:
                self.ledger.append(LongRunningEventKind.RECOVERY_REQUIRED, {"reason": "attempt isolator rollback failed", "error_type": type(exc).__name__, "lease_id": lease.lease_id}, task_id=attempt.task_id, attempt_id=attempt.attempt_id)
                raise LongRunningRecoveryRequiredError("Attempt rollback failed; the environment may be contaminated.", run_id=self.ledger.snapshot().run_id, task_id=attempt.task_id, attempt_id=attempt.attempt_id) from exc
            self.ledger.append(LongRunningEventKind.CHECKPOINTED, {"isolation_status": AttemptIsolationStatus.ROLLED_BACK.value, "lease_id": lease.lease_id}, task_id=attempt.task_id, attempt_id=attempt.attempt_id)
            return
        if attempt.non_read_tool_succeeded:
            self.ledger.append(LongRunningEventKind.RECOVERY_REQUIRED, {"reason": "rejected non-read tool succeeded without an isolator", "external_side_effects_not_rolled_back": True}, task_id=attempt.task_id, attempt_id=attempt.attempt_id)
            raise LongRunningRecoveryRequiredError("Rejected attempt used a non-read tool without rollback evidence.", run_id=self.ledger.snapshot().run_id, task_id=attempt.task_id, attempt_id=attempt.attempt_id)

    async def _run(self, state: LongRunningState, task: LongRunningTask, builder: OutputSchemaBuilder, bundle: RoleAgentBundle, *, role: str, message: str) -> TaskAttempt:
        # Checkpoint an optional lease, run one role, record transcript, then parse output.
        attempt_number = self._attempt_number(state, task.task_id)
        attempt_id = ProcedureIdentity.deterministic_id("attempt", state.run_id, task.task_id, str(attempt_number))
        permissions = {spec.name: spec.permission for spec in bundle.agent.tool_specs()}
        has_non_read = any(permission not in {ToolPermission.READ, ToolPermission.SAFE} for permission in permissions.values())
        if has_non_read and self.attempt_isolator is None and not self.broker.settings.unsafe_allow_unisolated_side_effects:
            raise LongRunningConfigurationError("Worker/repair tools include non-read capabilities but no AttemptIsolator was supplied.", run_id=state.run_id, task_id=task.task_id, attempt_id=attempt_id)
        lease = await self._begin_lease(state, task, attempt_id, has_non_read)
        self.ledger.append(LongRunningEventKind.ROLE_STARTED, {"graph_version": state.graph.version, "attempt_number": attempt_number, "has_non_read_tools": has_non_read, "unsafe_unisolated": has_non_read and lease is None}, task_id=task.task_id, attempt_id=attempt_id, role=role)
        try:
            reply = await bundle.agent.arun(message)
        except BaseException as exc:
            self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"succeeded": False, "error_type": type(exc).__name__, "lease": self._lease_mapping(lease)}, task_id=task.task_id, attempt_id=attempt_id, role=role)
            raise
        transcript = bundle.agent.export_state().history
        event = self.ledger.append(LongRunningEventKind.ROLE_COMPLETED, {"succeeded": True, "reply_metadata": dict(reply.metadata), "public_transcript": transcript, "loaded_procedures": self._refs(bundle), "loaded_verified_context": self._verified_refs(bundle), "lease": self._lease_mapping(lease)}, task_id=task.task_id, attempt_id=attempt_id, role=role)
        values = self._values(builder, reply.content)
        return TaskAttempt(attempt_id=attempt_id, task_id=task.task_id, attempt_number=attempt_number, strategy=str(values.get("strategy", "")).strip(), summary=str(values.get("summary", reply.content)).strip(), artifacts=self._artifacts(values.get("artifacts", ())), evidence=self._texts(values.get("evidence", ())), loaded_procedures=() if bundle.procedure_load is None else bundle.procedure_load.loaded_refs, blockers=self._texts(values.get("blockers", ())), transcript_event_id=event.event_id, tokens_used=self._tokens(reply.metadata), isolation_lease=self._lease_mapping(lease), non_read_tool_succeeded=self._non_read_succeeded(bundle, permissions), interrupted=False)

    async def _begin_lease(self, state: LongRunningState, task: LongRunningTask, attempt_id: str, has_non_read: bool) -> AttemptLease | None:
        # Open and durably record a lease before exposing any non-read tool.
        if not has_non_read or self.attempt_isolator is None:
            return None
        lease = await self.attempt_isolator.begin(state.run_id, task, attempt_id)
        if lease.isolator_id != self.attempt_isolator.isolator_id or lease.isolator_version != self.attempt_isolator.isolator_version or not lease.lease_id:
            raise LongRunningConfigurationError("AttemptIsolator returned a malformed or mismatched lease.", run_id=state.run_id, task_id=task.task_id, attempt_id=attempt_id)
        self.ledger.append(LongRunningEventKind.CHECKPOINTED, {"isolation_status": AttemptIsolationStatus.OPEN.value, "lease": self._lease_mapping(lease)}, task_id=task.task_id, attempt_id=attempt_id)
        return lease

    def _matches(self, task: LongRunningTask) -> tuple[Any, ...]:
        # Retrieve compact compatible cards before creating the fresh role context.
        return self.procedure_library.search(task.procedure_query, namespace=self.broker.settings.procedure_namespace, environment_fingerprint=self.broker.settings.environment_fingerprint, available_tools=self.broker.available_tool_names("worker"), limit=self.broker.settings.procedure_search_limit)

    @staticmethod
    def _values(builder: OutputSchemaBuilder, fallback_text: str) -> Mapping[str, Any]:
        # Prefer run-local output tools; accept a single JSON object as fallback.
        values = builder.snapshot().get("values", {})
        if isinstance(values, Mapping) and values:
            return values
        try:
            parsed = json.loads(fallback_text)
        except json.JSONDecodeError:
            return {"summary": fallback_text}
        return parsed if isinstance(parsed, Mapping) else {"summary": fallback_text}

    @staticmethod
    def _artifacts(value: object) -> tuple[ArtifactRef, ...]:
        # Parse public artifact cards and derive stable identity when fields are omitted.
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            return ()
        artifacts: list[ArtifactRef] = []
        for index, raw in enumerate(value):
            if not isinstance(raw, Mapping):
                continue
            uri = str(raw.get("uri", "")).strip()
            summary = str(raw.get("summary", "")).strip()
            content_hash = str(raw.get("content_hash", "")).strip() or ProcedureIdentity.hash_mapping({"uri": uri, "summary": summary})
            artifact_id = str(raw.get("artifact_id", "")).strip() or ProcedureIdentity.deterministic_id("artifact", str(index), uri, content_hash)
            size = raw.get("size_bytes")
            artifacts.append(ArtifactRef(artifact_id, uri, str(raw.get("media_type", "text/plain")), summary, content_hash, None if size is None else int(size)))
        return tuple(artifacts)

    @staticmethod
    def _texts(value: object) -> tuple[str, ...]:
        # Normalize model arrays without splitting one scalar into characters.
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(text for item in value if (text := str(item).strip()))
        text = str(value).strip()
        return (text,) if text else ()

    @staticmethod
    def _tokens(metadata: Mapping[str, Any]) -> int | None:
        # Extract provider-reported total usage without inventing missing accounting.
        direct = metadata.get("tokens_used")
        if isinstance(direct, (int, float)):
            return int(direct)
        usage = metadata.get("usage")
        if isinstance(usage, Mapping):
            total = usage.get("total_tokens", usage.get("total"))
            if isinstance(total, (int, float)):
                return int(total)
            input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
            output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
            if isinstance(input_tokens, (int, float)) and isinstance(output_tokens, (int, float)):
                return int(input_tokens) + int(output_tokens)
        return None

    @staticmethod
    def _non_read_succeeded(bundle: RoleAgentBundle, permissions: Mapping[str, ToolPermission]) -> bool:
        # Use runtime tool-call records, never model self-report, for contamination policy.
        contexts = tuple(getattr(bundle.agent, "_tool_call_contexts", ()))
        for context in contexts:
            permission = permissions.get(context.tool_name)
            succeeded = context.state is ToolCallState.SUCCEEDED or (context.result is not None and context.result.status is ToolStatus.SUCCESS)
            if succeeded and permission not in {None, ToolPermission.READ, ToolPermission.SAFE}:
                return True
        return False

    @staticmethod
    def _refs(bundle: RoleAgentBundle) -> tuple[Mapping[str, Any], ...]:
        # Serialize authoritative exact procedure loads into the public role event.
        refs = () if bundle.procedure_load is None else bundle.procedure_load.loaded_refs
        return tuple({"namespace": ref.namespace, "procedure_id": ref.procedure_id, "version": ref.version, "content_fingerprint": ref.content_fingerprint} for ref in refs)

    @staticmethod
    def _verified_refs(bundle: RoleAgentBundle) -> tuple[str, ...]:
        # Serialize only stable advertised verified-context handles.
        refs = () if bundle.verified_context_load is None else bundle.verified_context_load.loaded_refs
        return tuple(ref.handle() for ref in refs)

    @staticmethod
    def _lease_mapping(lease: AttemptLease | None) -> Mapping[str, Any]:
        # Convert an optional lease to public, serializable recovery fields.
        if lease is None:
            return {}
        return {"isolator_id": lease.isolator_id, "isolator_version": lease.isolator_version, "lease_id": lease.lease_id, "metadata": dict(lease.metadata)}

    @staticmethod
    def _lease(attempt: TaskAttempt) -> AttemptLease | None:
        # Rehydrate a lease from the exact attempt record for commit/rollback.
        raw = attempt.isolation_lease
        if not raw:
            return None
        return AttemptLease(str(raw.get("isolator_id", "")), str(raw.get("isolator_version", "")), str(raw.get("lease_id", "")), raw.get("metadata", {}))

    @staticmethod
    def _attempt_number(state: LongRunningState, task_id: str) -> int:
        # Derive the next attempt number from committed task state.
        item = next((candidate for candidate in state.task_states if candidate.task_id == task_id), None)
        return 1 if item is None else item.attempt_count + 1

    @staticmethod
    def _normalize(value: str) -> str:
        # Collapse insignificant whitespace/case for no-progress comparison.
        return " ".join(value.casefold().split())

    @staticmethod
    def _worker_message(task: LongRunningTask) -> str:
        # Ask the worker for structured public results rather than self-verification.
        return f"Execute only task {task.task_id}. Use output-schema tools to return strategy, summary, artifacts, evidence, and blockers."

    @staticmethod
    def _repair_message(task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult) -> str:
        # Require a materially changed strategy against exact prior failure evidence.
        return f"Repair task {task.task_id} after attempt {attempt.attempt_id}. Failure signature: {verification.failure_signature}. Return strategy, summary, artifacts, evidence, and blockers through output-schema tools."


__all__ = ["AttemptIsolationStatus", "AttemptIsolator", "AttemptLease", "TaskExecutionService"]
