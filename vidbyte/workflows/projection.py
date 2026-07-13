"""FILE: vidbyte/workflows/projection.py
PURPOSE: Reconstructs complete workflow run state from append-only events and checkpoints.
ROLE IN CODEBASE: machine.py projects after every append; inspect/resume replay through here.

ARCHITECTURE NOTE:
    WorkflowProjection is mutable only inside one runtime/replay operation. Canonical
    truth remains the immutable event stream; checkpoints are disposable serialized
    caches. Reducer state is decoded through the compiled graph's StateSchema.

PUBLIC API INVENTORY:
    WorkflowProjection: Internal/public inspectable current projection.
    WorkflowProjector: Checkpoint restore plus ordered event reduction.

COMMON MODIFICATION PATTERNS:
    Every new control-changing event needs one explicit reducer branch and, when its
    state survives resume, matching checkpoint serialization.

WHAT NOT TO DO IN THIS FILE:
    1. Do not execute stages, validators, routers, agents, or callbacks.
    2. Do not invent missing events or repair sequence gaps.
    3. Do not use checkpoints without definition/schema compatibility checks.

KNOWN EDGE CASES:
    A stream may end after STAGE_STARTED. That projection is RUNNING at an incomplete
    boundary; machine.py decides to append STAGE_RESTARTED before re-execution.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline replay compares live and cold projections.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import uuid4

from .budget import BudgetSnapshot, UsageReport
from .contracts import (
    PendingRequest,
    PendingRequestKind,
    StageExecution,
    TerminalStatus,
    TransitionRecord,
    ValidationPhase,
    ValidationRecord,
    ValidationResult,
    ValidationStatus,
    WorkflowFeedback,
    WorkflowLifecycleStatus,
)
from .detours import DetourFrame, DetourReturnMode, WorkflowSignal
from .errors import WorkflowErrorRecord, WorkflowPersistenceError
from .events import WorkflowEvent, WorkflowEventType, _thaw_workflow_json
from .persistence import WorkflowCheckpoint


StateT = TypeVar("StateT")


@dataclass
class WorkflowProjection(Generic[StateT]):
    """Complete current run projection derived only from persisted facts."""

    definition_id: str
    run_id: str
    state: StateT
    observations: dict[str, Any]
    metadata: dict[str, Any]
    lifecycle: WorkflowLifecycleStatus = WorkflowLifecycleStatus.RUNNING
    current_stage: str | None = None
    terminal_status: TerminalStatus | None = None
    terminal: str | None = None
    pending: PendingRequest | None = None
    pending_data: dict[str, Any] = field(default_factory=dict)
    usage: UsageReport = field(default_factory=UsageReport.zero)
    budget: BudgetSnapshot = field(default_factory=BudgetSnapshot)
    feedback: list[WorkflowFeedback] = field(default_factory=list)
    stages: list[StageExecution] = field(default_factory=list)
    transitions: list[TransitionRecord] = field(default_factory=list)
    detour_stack: list[DetourFrame] = field(default_factory=list)
    resume_values: dict[str, Any] = field(default_factory=dict)
    unresolved_sends: list[dict[str, Any]] = field(default_factory=list)
    error: WorkflowErrorRecord | None = None
    last_event_sequence: int = 0
    super_step: int = 0
    checkpoint_id: str | None = None
    events: list[WorkflowEvent] = field(default_factory=list)
    observer_errors: list[str] = field(default_factory=list)
    started_at: str = ""
    duration_ms: float = 0.0
    incomplete_stage: bool = False

    def checkpoint(self, definition: Any) -> WorkflowCheckpoint:
        # Serializes a disposable immutable cache at the current canonical sequence.
        if self.last_event_sequence <= 0:
            raise WorkflowPersistenceError("Cannot checkpoint a projection before RUN_STARTED.", details={"run_id": self.run_id})
        return WorkflowCheckpoint(
            checkpoint_id=f"wck_{uuid4().hex}",
            definition_id=self.definition_id,
            run_id=self.run_id,
            event_sequence=self.last_event_sequence,
            super_step=self.super_step,
            state_payload=definition.state_schema.encode(self.state),
            projection_payload=self.to_payload(),
            created_at=datetime.now(timezone.utc).isoformat(),
            state_schema_id=definition.state_schema.fingerprint_id,
        )

    def to_payload(self) -> dict[str, Any]:
        # Converts all resume-relevant projected fields to canonical JSON-ready data.
        return {
            "observations": self.observations,
            "metadata": self.metadata,
            "lifecycle": self.lifecycle.value,
            "current_stage": self.current_stage,
            "terminal_status": self.terminal_status.value if self.terminal_status else None,
            "terminal": self.terminal,
            "pending": _pending_to_dict(self.pending),
            "pending_data": self.pending_data,
            "usage": _usage_to_dict(self.usage),
            "budget": _budget_to_dict(self.budget),
            "feedback": [_feedback_to_dict(item) for item in self.feedback],
            "stages": [_stage_to_dict(item) for item in self.stages],
            "transitions": [_transition_to_dict(item) for item in self.transitions],
            "detour_stack": [_detour_to_dict(item) for item in self.detour_stack],
            "resume_values": self.resume_values,
            "unresolved_sends": self.unresolved_sends,
            "error": _error_to_dict(self.error),
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "incomplete_stage": self.incomplete_stage,
        }


class WorkflowProjector(Generic[StateT]):
    """Strict ordered reducer for workflow events and compatible checkpoints."""

    def replay(self, definition: Any, events: Sequence[WorkflowEvent], *, checkpoint: WorkflowCheckpoint | None = None) -> WorkflowProjection[StateT]:
        # Restores an optional cache, then applies only the subsequent canonical facts.
        projection = self.from_checkpoint(definition, checkpoint) if checkpoint is not None else None
        for event in events:
            if projection is not None and event.sequence <= projection.last_event_sequence:
                continue
            projection = self.apply(definition, projection, event)
        if projection is None:
            raise WorkflowPersistenceError("Workflow event stream is empty.", details={"definition_id": definition.definition_id})
        return projection

    def from_checkpoint(self, definition: Any, checkpoint: WorkflowCheckpoint) -> WorkflowProjection[StateT]:
        # Rehydrates typed state and all resume-relevant control data from one cache.
        payload = _thaw_workflow_json(checkpoint.projection_payload)
        state_payload = _thaw_workflow_json(checkpoint.state_payload)
        projection = WorkflowProjection(
            definition_id=checkpoint.definition_id,
            run_id=checkpoint.run_id,
            state=definition.state_schema.decode(state_payload),
            observations=dict(payload.get("observations", {})),
            metadata=dict(payload.get("metadata", {})),
            lifecycle=WorkflowLifecycleStatus(payload.get("lifecycle", WorkflowLifecycleStatus.RUNNING.value)),
            current_stage=payload.get("current_stage"),
            terminal_status=TerminalStatus(payload["terminal_status"]) if payload.get("terminal_status") else None,
            terminal=payload.get("terminal"),
            pending=_pending_from_dict(payload.get("pending")),
            pending_data=dict(payload.get("pending_data", {})),
            usage=_usage_from_dict(payload.get("usage", {})),
            budget=_budget_from_dict(payload.get("budget", {})),
            feedback=[_feedback_from_dict(item) for item in payload.get("feedback", ())],
            stages=[_stage_from_dict(item) for item in payload.get("stages", ())],
            transitions=[_transition_from_dict(item) for item in payload.get("transitions", ())],
            detour_stack=[_detour_from_dict(item) for item in payload.get("detour_stack", ())],
            resume_values=dict(payload.get("resume_values", {})),
            unresolved_sends=[dict(item) for item in payload.get("unresolved_sends", ())],
            error=_error_from_dict(payload.get("error")),
            last_event_sequence=checkpoint.event_sequence,
            super_step=checkpoint.super_step,
            checkpoint_id=checkpoint.checkpoint_id,
            started_at=str(payload.get("started_at", "")),
            duration_ms=float(payload.get("duration_ms", 0.0)),
            incomplete_stage=bool(payload.get("incomplete_stage", False)),
        )
        return projection

    def apply(self, definition: Any, projection: WorkflowProjection[StateT] | None, event: WorkflowEvent) -> WorkflowProjection[StateT]:
        # Reduces one contiguous event and rejects cross-run or cross-definition facts.
        data = event.payload.to_dict()
        if projection is None:
            if event.event_type is not WorkflowEventType.RUN_STARTED or event.sequence != 1:
                raise WorkflowPersistenceError("A workflow stream must begin with RUN_STARTED at sequence one.", details={"event_type": event.event_type.value, "sequence": event.sequence})
            projection = WorkflowProjection(
                definition_id=event.definition_id,
                run_id=event.run_id,
                state=definition.state_schema.decode(data["state"]),
                observations=dict(data.get("observations", {})),
                metadata=dict(data.get("metadata", {})),
                current_stage=str(data.get("current_stage") or definition.entry),
                started_at=event.occurred_at,
                incomplete_stage=True,
            )
        else:
            self._assert_next(projection, event)
            self._reduce_existing(definition, projection, event, data)
        projection.last_event_sequence = event.sequence
        projection.super_step = event.super_step
        projection.duration_ms = event.elapsed_ms
        projection.events.append(event)
        return projection

    @staticmethod
    def _assert_next(projection: WorkflowProjection[Any], event: WorkflowEvent) -> None:
        # Enforces optimistic stream identity and strict sequence continuity during replay.
        if event.definition_id != projection.definition_id or event.run_id != projection.run_id:
            raise WorkflowPersistenceError("Workflow event identity changed within one stream.", details={"sequence": event.sequence})
        if event.sequence != projection.last_event_sequence + 1:
            raise WorkflowPersistenceError("Workflow event sequence is not contiguous.", details={"expected": projection.last_event_sequence + 1, "actual": event.sequence})

    def _reduce_existing(self, definition: Any, projection: WorkflowProjection[StateT], event: WorkflowEvent, data: Mapping[str, Any]) -> None:
        # Applies the event-specific state transition without executing user code.
        kind = event.event_type
        if kind is WorkflowEventType.LIFECYCLE_CHANGED:
            _set_lifecycle(projection, WorkflowLifecycleStatus(data["lifecycle"]), event)
        elif kind in (WorkflowEventType.STAGE_STARTED, WorkflowEventType.STAGE_RESTARTED):
            projection.current_stage = str(data.get("stage") or event.stage or projection.current_stage)
            projection.budget = _budget_from_dict(data.get("budget", _budget_to_dict(projection.budget)))
            projection.pending_data = {"active_stage": dict(data.get("active_stage", {}))}
            projection.incomplete_stage = True
        elif kind is WorkflowEventType.STAGE_FINISHED:
            if data.get("execution"):
                projection.stages.append(_stage_from_dict(data["execution"]))
            projection.incomplete_stage = True
        elif kind is WorkflowEventType.STAGE_FAILED:
            if data.get("execution"):
                projection.stages.append(_stage_from_dict(data["execution"]))
            projection.incomplete_stage = True
            projection.pending_data = {"active_stage": dict(data.get("active_stage", {}))}
        elif kind is WorkflowEventType.OBSERVATION_RECORDED:
            projection.observations = dict(data.get("observations", projection.observations))
        elif kind is WorkflowEventType.USAGE_RECORDED:
            projection.usage = _usage_from_dict(data.get("usage", {}))
            projection.budget = _budget_from_dict(data.get("budget", _budget_to_dict(projection.budget)))
        elif kind is WorkflowEventType.TRANSITION_SELECTED:
            if data.get("transition"):
                projection.transitions.append(_transition_from_dict(data["transition"]))
            projection.budget = _budget_from_dict(data.get("budget", _budget_to_dict(projection.budget)))
        elif kind is WorkflowEventType.TRANSITION_REJECTED:
            if data.get("transition"):
                projection.transitions.append(_transition_from_dict(data["transition"]))
            if data.get("feedback"):
                projection.feedback.append(_feedback_from_dict(data["feedback"]))
        elif kind in (WorkflowEventType.APPROVAL_REQUESTED, WorkflowEventType.INTERRUPT_REQUESTED):
            projection.pending = _pending_from_dict(data.get("pending"))
            projection.pending_data = dict(data.get("pending_data", {}))
            projection.incomplete_stage = projection.pending_data.get("mode") == "stage"
            _set_lifecycle(projection, WorkflowLifecycleStatus(data["lifecycle"]), event)
        elif kind in (WorkflowEventType.APPROVAL_RESPONDED, WorkflowEventType.INTERRUPT_RESPONDED):
            if data.get("transition"):
                projection.transitions.append(_transition_from_dict(data["transition"]))
            if data.get("resume_key") is not None:
                projection.resume_values[str(data["resume_key"])] = data.get("value")
            projection.pending = None
            projection.pending_data = dict(data.get("pending_data", {}))
            if kind is WorkflowEventType.APPROVAL_RESPONDED:
                projection.pending_data["mode"] = "approval_response"
                projection.pending_data["response_approved"] = bool(data.get("approved"))
                projection.pending_data["response_request_id"] = data.get("request_id")
            elif projection.pending_data.get("mode") == "command":
                projection.pending_data["resume_value"] = data.get("value")
            projection.incomplete_stage = True
            _set_lifecycle(projection, WorkflowLifecycleStatus.RUNNING, event)
        elif kind is WorkflowEventType.DETOUR_ENTERED:
            projection.detour_stack.append(_detour_from_dict(data["frame"]))
            projection.current_stage = str(data["target"])
            projection.budget = _budget_from_dict(data.get("budget", _budget_to_dict(projection.budget)))
            projection.incomplete_stage = False
            projection.pending_data = {}
        elif kind is WorkflowEventType.DETOUR_RETURNED:
            if projection.detour_stack:
                projection.detour_stack.pop()
            projection.current_stage = str(data["target"])
            projection.budget = _budget_from_dict(data.get("budget", _budget_to_dict(projection.budget)))
            if data.get("feedback"):
                projection.feedback.append(_feedback_from_dict(data["feedback"]))
            active = data.get("active_stage")
            projection.incomplete_stage = isinstance(active, Mapping)
            projection.pending_data = {"active_stage": dict(active)} if isinstance(active, Mapping) else {}
        elif kind is WorkflowEventType.SENDS_STARTED:
            projection.unresolved_sends = [dict(item) for item in data.get("sends", ())]
        elif kind in (WorkflowEventType.CHILD_FINISHED, WorkflowEventType.CHILD_SUSPENDED):
            if kind is WorkflowEventType.CHILD_FINISHED:
                completed_key = str(data.get("key", ""))
                projection.unresolved_sends = [item for item in projection.unresolved_sends if str(item.get("key", "")) != completed_key]
            if isinstance(data.get("pending_data"), Mapping):
                projection.pending_data = dict(data["pending_data"])
        elif kind is WorkflowEventType.STATE_COMMITTED:
            projection.state = definition.state_schema.decode(data["state"])
            projection.current_stage = str(data["target"])
            projection.feedback = [_feedback_from_dict(item) for item in data.get("feedback", ())]
            if data.get("transition"):
                projection.transitions.append(_transition_from_dict(data["transition"]))
            projection.pending_data = {}
            projection.incomplete_stage = False
        elif kind is WorkflowEventType.STUCK_DETECTED:
            projection.error = _error_from_dict(data.get("error"))
            projection.incomplete_stage = False
            _set_lifecycle(projection, WorkflowLifecycleStatus.ERROR, event)
        elif kind is WorkflowEventType.CHECKPOINT_WRITTEN:
            projection.checkpoint_id = str(data.get("checkpoint_id")) if data.get("checkpoint_id") else projection.checkpoint_id
        elif kind is WorkflowEventType.RUN_FINISHED:
            _set_lifecycle(projection, WorkflowLifecycleStatus.FINISHED, event)
            projection.terminal = str(data["terminal"])
            projection.terminal_status = TerminalStatus(data["terminal_status"])
            projection.current_stage = None
            projection.pending = None
            projection.incomplete_stage = False
            projection.pending_data = {}
        elif kind in (WorkflowEventType.RUN_FAILED, WorkflowEventType.RUN_CANCELLED):
            target = WorkflowLifecycleStatus.ERROR if kind is WorkflowEventType.RUN_FAILED else WorkflowLifecycleStatus.INTERRUPTED
            _set_lifecycle(projection, target, event)
            projection.error = _error_from_dict(data.get("error"))
            projection.pending = None
            projection.incomplete_stage = False


_LIFECYCLE_TRANSITIONS: Mapping[WorkflowLifecycleStatus, frozenset[WorkflowLifecycleStatus]] = {
    WorkflowLifecycleStatus.RUNNING: frozenset({WorkflowLifecycleStatus.WAITING_FOR_CONFIRMATION, WorkflowLifecycleStatus.INTERRUPTED, WorkflowLifecycleStatus.FINISHED, WorkflowLifecycleStatus.ERROR}),
    WorkflowLifecycleStatus.WAITING_FOR_CONFIRMATION: frozenset({WorkflowLifecycleStatus.RUNNING, WorkflowLifecycleStatus.ERROR, WorkflowLifecycleStatus.INTERRUPTED}),
    WorkflowLifecycleStatus.INTERRUPTED: frozenset({WorkflowLifecycleStatus.RUNNING, WorkflowLifecycleStatus.ERROR}),
    WorkflowLifecycleStatus.FINISHED: frozenset(),
    WorkflowLifecycleStatus.ERROR: frozenset(),
}


def _set_lifecycle(projection: WorkflowProjection[Any], target: WorkflowLifecycleStatus, event: WorkflowEvent) -> None:
    # Rejects event streams whose lifecycle axis makes an undeclared transition.
    current = projection.lifecycle
    if target is current:
        return
    if target not in _LIFECYCLE_TRANSITIONS[current]:
        raise WorkflowPersistenceError("Workflow event attempted an invalid lifecycle transition.", details={"sequence": event.sequence, "event_type": event.event_type.value, "current": current.value, "target": target.value})
    projection.lifecycle = target


def _usage_to_dict(value: UsageReport) -> dict[str, Any]:
    # Serializes additive usage without converting unknown dimensions to zero.
    return {name: getattr(value, name) for name in ("model_calls", "tool_calls", "input_tokens", "output_tokens", "total_tokens", "cost_usd", "provider", "model")}


def _usage_from_dict(value: Mapping[str, Any]) -> UsageReport:
    # Reconstructs usage with defaults suitable for old or partial checkpoint payloads.
    return UsageReport(**{name: value.get(name, default) for name, default in (("model_calls", 0), ("tool_calls", 0), ("input_tokens", 0), ("output_tokens", 0), ("total_tokens", 0), ("cost_usd", 0.0), ("provider", None), ("model", None))})


def _budget_to_dict(value: BudgetSnapshot) -> dict[str, Any]:
    # Serializes every counter charged by BudgetLedger.
    return {"super_steps": value.super_steps, "transitions": value.transitions, "stage_visits": dict(value.stage_visits), "detour_depth": value.detour_depth, "recursion_depth": value.recursion_depth, "usage": _usage_to_dict(value.usage)}


def _budget_from_dict(value: Mapping[str, Any]) -> BudgetSnapshot:
    # Reconstructs layered counters from persisted event/checkpoint evidence.
    return BudgetSnapshot(super_steps=int(value.get("super_steps", 0)), transitions=int(value.get("transitions", 0)), stage_visits=dict(value.get("stage_visits", {})), detour_depth=int(value.get("detour_depth", 0)), recursion_depth=int(value.get("recursion_depth", 0)), usage=_usage_from_dict(value.get("usage", {})))


def _pending_to_dict(value: PendingRequest | None) -> dict[str, Any] | None:
    # Serializes public pending request data without executable schema classes.
    if value is None:
        return None
    return {"request_id": value.request_id, "kind": value.kind.value, "stage": value.stage, "prompt": value.prompt, "metadata": dict(value.metadata)}


def _pending_from_dict(value: Mapping[str, Any] | None) -> PendingRequest | None:
    # Reconstructs one exact external resume token.
    if not value:
        return None
    return PendingRequest(str(value["request_id"]), PendingRequestKind(value["kind"]), str(value["stage"]), str(value["prompt"]), value.get("metadata", {}))


def _feedback_to_dict(value: WorkflowFeedback) -> dict[str, Any]:
    # Serializes structured recovery feedback.
    return {"kind": value.kind, "source": value.source, "code": value.code, "message": value.message, "details": dict(value.details)}


def _feedback_from_dict(value: Mapping[str, Any]) -> WorkflowFeedback:
    # Reconstructs structured recovery feedback.
    return WorkflowFeedback(str(value["kind"]), str(value["source"]), str(value["code"]), str(value.get("message", "")), value.get("details", {}))


def _validation_to_dict(value: ValidationRecord) -> dict[str, Any]:
    # Serializes one validator decision embedded in stage/transition evidence.
    result = value.result
    return {"phase": value.phase.value, "validator": value.validator, "result": {"status": result.status.value, "code": result.code, "feedback": result.feedback, "score": result.score, "details": dict(result.details), "usage": _usage_to_dict(result.usage) if result.usage is not None else None}, "duration_ms": value.duration_ms, "target": value.target}


def _validation_from_dict(value: Mapping[str, Any]) -> ValidationRecord:
    # Reconstructs one validator decision embedded in stage/transition evidence.
    result = value["result"]
    usage = _usage_from_dict(result["usage"]) if isinstance(result.get("usage"), Mapping) else None
    decision = ValidationResult(ValidationStatus(result["status"]), str(result.get("code", "")), str(result.get("feedback", "")), result.get("score"), result.get("details", {}), usage)
    return ValidationRecord(ValidationPhase(value["phase"]), str(value["validator"]), decision, float(value.get("duration_ms", 0.0)), value.get("target"))


def _stage_to_dict(value: StageExecution) -> dict[str, Any]:
    # Serializes one immutable stage-attempt evidence record.
    return {"stage": value.stage, "visit": value.visit, "attempt": value.attempt, "outcome": value.outcome, "accepted": value.accepted, "duration_ms": value.duration_ms, "metadata": dict(value.metadata), "validations": [_validation_to_dict(item) for item in value.validations], "error_type": value.error_type, "error_message": value.error_message, "state_before": value.state_before, "candidate_state": value.candidate_state}


def _stage_from_dict(value: Mapping[str, Any]) -> StageExecution:
    # Reconstructs one immutable stage-attempt evidence record.
    return StageExecution(str(value["stage"]), int(value["visit"]), int(value["attempt"]), value.get("outcome"), bool(value.get("accepted", False)), float(value.get("duration_ms", 0.0)), value.get("metadata", {}), tuple(_validation_from_dict(item) for item in value.get("validations", ())), value.get("error_type"), value.get("error_message"), value.get("state_before"), value.get("candidate_state"))


def _transition_to_dict(value: TransitionRecord) -> dict[str, Any]:
    # Serializes one route selection and guard record.
    return {"sequence": value.sequence, "source": value.source, "target": value.target, "outcome": value.outcome, "accepted": value.accepted, "trigger": value.trigger, "validations": [_validation_to_dict(item) for item in value.validations], "duration_ms": value.duration_ms}


def _transition_from_dict(value: Mapping[str, Any]) -> TransitionRecord:
    # Reconstructs one route selection and guard record.
    return TransitionRecord(int(value["sequence"]), str(value["source"]), str(value["target"]), str(value["outcome"]), bool(value.get("accepted", False)), str(value.get("trigger", "direct")), tuple(_validation_from_dict(item) for item in value.get("validations", ())), float(value.get("duration_ms", 0.0)))


def _detour_to_dict(value: DetourFrame) -> dict[str, Any]:
    # Serializes one bounded detour return address.
    return {"rule_id": value.rule_id, "source_stage": value.source_stage, "target_stage": value.target_stage, "return_mode": value.return_mode.value, "signal": {"signal_type": value.signal.signal_type, "source": value.signal.source, "data": dict(value.signal.data)}, "continuation": dict(value.continuation)}


def _detour_from_dict(value: Mapping[str, Any]) -> DetourFrame:
    # Reconstructs one bounded detour return address.
    signal = value["signal"]
    return DetourFrame(str(value["rule_id"]), str(value["source_stage"]), str(value["target_stage"]), DetourReturnMode(value["return_mode"]), WorkflowSignal(str(signal["signal_type"]), str(signal["source"]), signal.get("data", {})), value.get("continuation", {}))


def _error_to_dict(value: WorkflowErrorRecord | None) -> dict[str, Any] | None:
    # Serializes bounded safe failure evidence.
    return None if value is None else {"error_type": value.error_type, "message": value.message, "details": dict(value.details)}


def _error_from_dict(value: Mapping[str, Any] | None) -> WorkflowErrorRecord | None:
    # Reconstructs bounded safe failure evidence.
    return None if not value else WorkflowErrorRecord(str(value.get("error_type", "WorkflowError")), str(value.get("message", "")), value.get("details", {}))


__all__ = ["WorkflowProjection", "WorkflowProjector"]
