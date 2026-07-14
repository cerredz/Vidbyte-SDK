"""Context Protocol Header

Path: vidbyte/paradigms/long_running/ledger.py
Purpose: Persist a monotonic append-only event chain and compact post-transition state
so long runs can resume after context loss, process failure, or handoff.
Architecture: LongRunningCodec handles safe tagged JSON; RunLedger is the transition
authority; in-memory and atomic file stores implement one RunLedgerStore protocol;
BehaviorFingerprint protects resume semantics from silent configuration drift.
Exports: event/snapshot/store contracts, stores, RunLedger, codec, and fingerprinting.
Invariants: Every event sequence is contiguous, state revision is monotonic, event and
snapshot hashes agree, immutable envelopes precede mutable state heads, and secrets are
redacted from persisted/fingerprinted mappings.
Do not: Treat ledger commits and ProcedureStore mutations as one transaction; use the
controller's intent/reconciliation saga around cross-store effects.
Related: docs/design/long-running-paradigm.md section 6.5 and long_running/controller.py.
Tests: Existing SDK verification plus inline persistence/resume smoke checks; no new
tests or verification scripts under the approved design-doc-no-tests workflow.
Concurrency: In-memory operations hold one RLock; file writes support one writer process
per root and concurrent completed-file readers.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError, LongRunningLedgerError, LongRunningResumeError
from vidbyte.paradigms.long_running.types import (
    ArtifactRef, CriterionResult, DriftDecision, DriftReview, EvidenceRecord, GoalContract,
    InterruptedAttemptPolicy, LongRunningResult, LongRunningResumeOptions,
    LongRunningRunOptions, LongRunningRunStatus, LongRunningSettings, LongRunningState,
    LongRunningStopReason, LongRunningTask, LongRunningTaskState,
    LongRunningTaskStatus, LongRunningUsage, ProcedureValidationContext, TaskAttempt,
    TaskGraph, TaskResult, TaskValidationContext, ValidatorResult, VerificationResult,
)
from vidbyte.paradigms.types import AgentRoleSettings
from vidbyte.procedures import (
    ProcedureCheckResult, ProcedureOutcome, ProcedureRecord, ProcedureRef,
    ProcedureStatus, ProcedureSummary, ProcedureVerificationEvidence,
)
from vidbyte.procedures.serialization import ProcedureIdentity


class LongRunningEventKind(str, Enum):
    """Stable event names for every durable controller boundary."""

    RUN_STARTED = "run_started"
    RUN_RESUMED = "run_resumed"
    SETTINGS_CHANGE_ACCEPTED = "settings_change_accepted"
    PLAN_ATTEMPTED = "plan_attempted"
    PLAN_VALIDATION_FAILED = "plan_validation_failed"
    PLAN_ACCEPTED = "plan_accepted"
    TASK_STARTED = "task_started"
    ROLE_STARTED = "role_started"
    ROLE_COMPLETED = "role_completed"
    ATTEMPT_RECORDED = "attempt_recorded"
    VERIFICATION_COMPLETED = "verification_completed"
    REPAIR_SCHEDULED = "repair_scheduled"
    TASK_VERIFIED = "task_verified"
    TASK_REJECTED = "task_rejected"
    DRIFT_REVIEWED = "drift_reviewed"
    PLAN_REVISED = "plan_revised"
    TASK_INVALIDATED = "task_invalidated"
    PROCEDURE_LEARNING_INTENT = "procedure_learning_intent"
    PROCEDURE_STAGED = "procedure_staged"
    PROCEDURE_FIDELITY_VERIFIED = "procedure_fidelity_verified"
    PROCEDURE_PROMOTED = "procedure_promoted"
    PROCEDURE_REJECTED = "procedure_rejected"
    PROCEDURE_RETIRED = "procedure_retired"
    PROCEDURE_LEARNING_COMPLETED = "procedure_learning_completed"
    PROCEDURE_OUTCOME_INTENT = "procedure_outcome_intent"
    PROCEDURE_OUTCOME_COMPLETED = "procedure_outcome_completed"
    SYNTHESIZED = "synthesized"
    FINAL_AUDITED = "final_audited"
    CHECKPOINTED = "checkpointed"
    RUN_PAUSED = "run_paused"
    RECOVERY_REQUIRED = "recovery_required"
    RUN_FAILED = "run_failed"
    RUN_COMPLETED = "run_completed"


@dataclass(frozen=True, slots=True)
class LongRunningEvent:
    """One immutable transition event linked to its post-transition state hash."""

    schema_version: int
    event_id: str
    run_id: str
    seq: int
    revision: int
    kind: LongRunningEventKind
    created_at: str
    state_hash_after: str
    previous_event_hash: str = ""
    task_id: str = ""
    attempt_id: str = ""
    role: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Copy event payloads so caller mutation cannot rewrite in-memory audit history.
        object.__setattr__(self, "payload", dict(self.payload or {}))


@dataclass(frozen=True, slots=True)
class RunLedgerSnapshot:
    """Fast durable head for one run and its compact committed state."""

    schema_version: int
    run_id: str
    revision: int
    last_event_seq: int
    state: LongRunningState
    settings_fingerprint: str
    last_event_hash: str
    created_at: str
    updated_at: str


class RunLedgerStore(Protocol):
    """Persistence boundary for event-plus-snapshot transition envelopes."""

    def create(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent) -> None:
        # Persist the first envelope and head for a previously unknown run id.
        ...

    def commit(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent, *, expected_last_event_seq: int) -> None:
        # Atomically compare the current sequence and append one transition.
        ...

    def load(self, run_id: str) -> RunLedgerSnapshot:
        # Reconstruct the newest valid envelope-backed state head.
        ...

    def events(self, run_id: str) -> tuple[LongRunningEvent, ...]:
        # Return the immutable event chain in sequence order.
        ...

    def store_identity(self) -> Mapping[str, Any]:
        # Return stable non-secret storage identity for resume fingerprinting.
        ...


class LongRunningCodec:
    """Tagged, deterministic, secret-scrubbing JSON codec for ledger values."""

    SCHEMA_VERSION = 1
    _SECRET_KEYS = ("api_key", "apikey", "secret", "password", "credential", "access_token", "auth_token", "bearer_token", "refresh_token")
    _DATACLASSES = {
        cls.__name__: cls for cls in (
            AgentRoleSettings, ArtifactRef, CriterionResult, DriftReview, EvidenceRecord, GoalContract,
            LongRunningEvent, LongRunningResult, LongRunningResumeOptions,
            LongRunningRunOptions, LongRunningSettings, LongRunningState,
            LongRunningTask, LongRunningTaskState, LongRunningUsage,
            ProcedureCheckResult, ProcedureOutcome, ProcedureRecord, ProcedureRef,
            ProcedureSummary, ProcedureValidationContext, ProcedureVerificationEvidence,
            RunLedgerSnapshot, TaskAttempt, TaskGraph, TaskResult,
            TaskValidationContext, ValidatorResult, VerificationResult,
        )
    }
    _ENUMS = {
        cls.__name__: cls for cls in (
            DriftDecision, InterruptedAttemptPolicy, LongRunningEventKind,
            LongRunningRunStatus, LongRunningStopReason, LongRunningTaskStatus,
            ProcedureStatus,
        )
    }

    @classmethod
    def encode(cls, value: Any) -> Any:
        # Recursively tag immutable contracts while dropping unsafe live object details.
        if isinstance(value, Enum):
            return {"__enum__": value.__class__.__name__, "value": value.value}
        if is_dataclass(value) and not isinstance(value, type):
            return {"__type__": value.__class__.__name__, **{item.name: cls.encode(getattr(value, item.name)) for item in fields(value)}}
        if isinstance(value, Mapping):
            return {str(key): "[redacted]" if cls._is_secret_key(str(key)) else cls.encode(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return {"__tuple__": [cls.encode(item) for item in value]}
        if isinstance(value, list):
            return [cls.encode(item) for item in value]
        if isinstance(value, set | frozenset):
            return {"__tuple__": [cls.encode(item) for item in sorted(value, key=str)]}
        if isinstance(value, Path):
            return {"__path__": str(value)}
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return {"__dropped_type__": f"{value.__class__.__module__}.{value.__class__.__qualname__}"}

    @classmethod
    def decode(cls, value: Any) -> Any:
        # Reconstruct known contracts and fail closed on unknown tagged schema types.
        if isinstance(value, list):
            return [cls.decode(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "__tuple__" in value:
            return tuple(cls.decode(item) for item in value["__tuple__"])
        if "__path__" in value:
            return Path(str(value["__path__"]))
        if "__enum__" in value:
            enum_cls = cls._ENUMS.get(str(value["__enum__"]))
            if enum_cls is None:
                raise LongRunningResumeError("Ledger contains an unknown enum type.", details={"enum_type": value["__enum__"]})
            return enum_cls(value["value"])
        if "__type__" in value:
            type_name = str(value["__type__"])
            dataclass_type = cls._DATACLASSES.get(type_name)
            if dataclass_type is None:
                raise LongRunningResumeError("Ledger contains an unknown dataclass type.", details={"dataclass_type": type_name})
            kwargs = {key: cls.decode(item) for key, item in value.items() if key != "__type__"}
            try:
                return dataclass_type(**kwargs)
            except (TypeError, ValueError) as exc:
                raise LongRunningResumeError("Ledger dataclass payload does not match schema v1.", details={"dataclass_type": type_name}) from exc
        if "__dropped_type__" in value:
            return dict(value)
        return {str(key): cls.decode(item) for key, item in value.items()}

    @classmethod
    def dumps(cls, value: Any) -> str:
        # Produce canonical JSON for content hashing and byte-equivalent replay checks.
        return json.dumps(cls.encode(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def loads(cls, text: str) -> Any:
        # Parse JSON then restore only registered schema-v1 values.
        try:
            return cls.decode(json.loads(text))
        except json.JSONDecodeError as exc:
            raise LongRunningResumeError("Ledger file is not valid JSON.") from exc

    @classmethod
    def hash_value(cls, value: Any) -> str:
        # Hash the exact canonical persisted projection rather than live object identity.
        return hashlib.sha256(cls.dumps(value).encode("utf-8")).hexdigest()

    @classmethod
    def _is_secret_key(cls, key: str) -> bool:
        # Match credential fields without redacting token budgets/usage counters.
        normalized = key.casefold().replace("-", "_")
        return any(normalized == part or normalized.endswith(f"_{part}") for part in cls._SECRET_KEYS)


class BehaviorFingerprint:
    """Build deterministic non-secret settings/component fingerprints for resume."""

    @classmethod
    def for_settings(cls, settings: LongRunningSettings, *, store_identity: Mapping[str, Any], extra_components: Sequence[object] = ()) -> str:
        # Fingerprint all behavior-changing limits, roles, stores, and trusted components.
        role_names = ("planner", "worker", "repairer", "verifier", "curator", "procedure_verifier", "synthesizer", "auditor")
        roles = {name: cls._role(name, getattr(settings, name), settings.component_fingerprints) for name in role_names}
        scalar = {
            item.name: LongRunningCodec.encode(getattr(settings, item.name))
            for item in fields(settings)
            if item.name not in role_names and item.name != "component_fingerprints"
        }
        components = [cls._component(f"component.{index}", component, settings.component_fingerprints) for index, component in enumerate(extra_components)]
        return LongRunningCodec.hash_value({"settings": scalar, "roles": roles, "store": dict(store_identity), "components": components, "schema": LongRunningCodec.SCHEMA_VERSION})

    @classmethod
    def _role(cls, role_name: str, role: Any, overrides: Mapping[str, str]) -> Mapping[str, Any]:
        # Exclude credentials while fingerprinting prompts, models, tools, middleware, and runners.
        model_name = tuple(role.model_name) if isinstance(role.model_name, Sequence) and not isinstance(role.model_name, str) else role.model_name
        agent_options = LongRunningCodec.encode(role.agent_options)
        if "__dropped_type__" in LongRunningCodec.dumps(agent_options):
            raise LongRunningConfigurationError("Role agent_options contain live values without a stable fingerprint.", details={"role": role_name})
        return {
            "name": role.name, "system_prompt_hash": cls._text_hash(role.system_prompt or ""),
            "provider": role.provider, "model_name": model_name, "temperature": role.temperature,
            "max_tokens": role.max_tokens, "agent_options": agent_options,
            "runner": None if role.runner is None else cls._component(f"{role_name}.runner", role.runner, overrides),
            "tools": tuple(cls._tool(f"{role_name}.tool.{index}", tool, overrides) for index, tool in enumerate(role.tools)),
            "middleware": tuple(cls._component(f"{role_name}.middleware.{index}", item, overrides, allow_public_config=True) for index, item in enumerate(role.middleware)),
        }

    @classmethod
    def _tool(cls, key: str, tool: object, overrides: Mapping[str, str]) -> Mapping[str, Any]:
        # Prefer stable ToolSpec data so tool behavior changes invalidate resume.
        spec_method = getattr(tool, "spec", None)
        if callable(spec_method):
            try:
                return {"class": cls._class_name(tool), "spec": LongRunningCodec.encode(spec_method())}
            except Exception as exc:
                raise LongRunningConfigurationError("Tool spec could not be fingerprinted safely.", details={"component_key": key, "error_type": exc.__class__.__name__}) from exc
        return cls._component(key, tool, overrides)

    @classmethod
    def _component(cls, key: str, component: object, overrides: Mapping[str, str], *, allow_public_config: bool = False) -> Mapping[str, Any]:
        # Require a stable provider, explicit override, or deterministic primitive config.
        fingerprint_method = getattr(component, "behavior_fingerprint", None)
        if callable(fingerprint_method):
            behavior = fingerprint_method()
            if not isinstance(behavior, Mapping) or not behavior:
                raise LongRunningConfigurationError("Live component behavior_fingerprint() must return a non-empty mapping.", details={"component_key": key, "component_class": cls._class_name(component)})
            return {"class": cls._class_name(component), "behavior": LongRunningCodec.encode(behavior)}
        if key in overrides:
            return {"class": cls._class_name(component), "override": str(overrides[key])}
        if allow_public_config:
            public = {name: value for name, value in vars(component).items() if not name.startswith("_") and not LongRunningCodec._is_secret_key(name)} if hasattr(component, "__dict__") else {}
            encoded = LongRunningCodec.encode(public)
            if "__dropped_type__" not in LongRunningCodec.dumps(encoded):
                return {"class": cls._class_name(component), "config": encoded}
        raise LongRunningConfigurationError("Live component has no stable behavior fingerprint.", details={"component_key": key, "component_class": cls._class_name(component)})

    @staticmethod
    def _class_name(component: object) -> str:
        # Return a diagnostic class label without using ephemeral object identity.
        return f"{component.__class__.__module__}.{component.__class__.__qualname__}"

    @staticmethod
    def _text_hash(text: str) -> str:
        # Hash prompt content without storing it in the fingerprint payload.
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class InMemoryRunLedgerStore:
    """Thread-safe ephemeral event-envelope store."""

    def __init__(self) -> None:
        # Keep heads and events behind one lock for whole-transition atomicity.
        self._snapshots: dict[str, RunLedgerSnapshot] = {}
        self._events: dict[str, list[LongRunningEvent]] = {}
        self._lock = RLock()

    def create(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent) -> None:
        # Create one run only when id, sequence, state, and hashes agree.
        self._validate_envelope(snapshot, event)
        with self._lock:
            if snapshot.run_id in self._snapshots:
                raise LongRunningLedgerError("Run id already exists in ledger store.", run_id=snapshot.run_id)
            self._snapshots[snapshot.run_id] = snapshot
            self._events[snapshot.run_id] = [event]

    def commit(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent, *, expected_last_event_seq: int) -> None:
        # Compare sequence and append event/head together under one reentrant lock.
        self._validate_envelope(snapshot, event)
        with self._lock:
            current = self._snapshots.get(snapshot.run_id)
            if current is None:
                raise LongRunningLedgerError("Run id does not exist in ledger store.", run_id=snapshot.run_id)
            if current.last_event_seq != expected_last_event_seq:
                raise LongRunningLedgerError("Ledger sequence changed before commit.", run_id=snapshot.run_id, details={"expected_last_event_seq": expected_last_event_seq, "actual_last_event_seq": current.last_event_seq})
            self._events[snapshot.run_id].append(event)
            self._snapshots[snapshot.run_id] = snapshot

    def load(self, run_id: str) -> RunLedgerSnapshot:
        # Return the immutable snapshot head or fail with a typed resume error.
        with self._lock:
            snapshot = self._snapshots.get(run_id)
            if snapshot is None:
                raise LongRunningResumeError("Long-running run id was not found.", run_id=run_id)
            return snapshot

    def events(self, run_id: str) -> tuple[LongRunningEvent, ...]:
        # Snapshot the immutable event list for caller audit.
        with self._lock:
            if run_id not in self._events:
                raise LongRunningResumeError("Long-running run id was not found.", run_id=run_id)
            return tuple(self._events[run_id])

    def store_identity(self) -> Mapping[str, Any]:
        # Identify the ephemeral adapter without including object identity.
        return {"type": "memory", "schema_version": LongRunningCodec.SCHEMA_VERSION}

    @staticmethod
    def _validate_envelope(snapshot: RunLedgerSnapshot, event: LongRunningEvent) -> None:
        # Reject internally inconsistent transition pairs before mutating store state.
        _validate_transition_envelope(snapshot, event)


class FileRunLedgerStore:
    """One-writer-process atomic JSON event-envelope store."""

    _RUN_ID = re.compile(r"^lr_[0-9a-f]{16,64}$")

    def __init__(self, root: str | Path) -> None:
        # Resolve the root and claim one writer process for append/version allocation.
        self.root = Path(root).resolve()
        self._runs_root = self.root / "runs"
        self._writer_lock_path = self.root / ".writer.lock"
        self._lock = RLock()
        try:
            self._runs_root.mkdir(parents=True, exist_ok=True)
            self._claim_writer()
        except OSError as exc:
            raise LongRunningLedgerError("File run ledger could not initialize its root.", details={"root_name": self.root.name}) from exc
        atexit.register(self.close)

    def close(self) -> None:
        # Release only this process's writer claim and leave foreign/stale locks intact.
        with self._lock:
            try:
                if self._writer_lock_path.exists() and self._writer_lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                    self._writer_lock_path.unlink()
            except OSError:
                return

    def create(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent) -> None:
        # Write the immutable first envelope before the replaceable state head.
        _validate_transition_envelope(snapshot, event)
        with self._lock:
            self._assert_writer()
            run_dir = self._run_path(snapshot.run_id)
            if run_dir.exists():
                raise LongRunningLedgerError("Run id already exists in file ledger.", run_id=snapshot.run_id)
            (run_dir / "events").mkdir(parents=True, exist_ok=False)
            self._write_envelope(run_dir, snapshot, event)
            self._atomic_write(run_dir / "state.json", snapshot)

    def commit(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent, *, expected_last_event_seq: int) -> None:
        # Compare the recovered durable head, append envelope, then advance state.json.
        _validate_transition_envelope(snapshot, event)
        with self._lock:
            self._assert_writer()
            current = self.load(snapshot.run_id)
            if current.last_event_seq != expected_last_event_seq:
                raise LongRunningLedgerError("File ledger sequence changed before commit.", run_id=snapshot.run_id, details={"expected_last_event_seq": expected_last_event_seq, "actual_last_event_seq": current.last_event_seq})
            run_dir = self._run_path(snapshot.run_id)
            self._write_envelope(run_dir, snapshot, event)
            self._atomic_write(run_dir / "state.json", snapshot)

    def load(self, run_id: str) -> RunLedgerSnapshot:
        # Rebuild the valid chain from immutable envelopes and repair a lagging head.
        run_dir = self._run_path(run_id)
        events_dir = run_dir / "events"
        if not events_dir.is_dir():
            raise LongRunningResumeError("Long-running run id was not found.", run_id=run_id)
        envelopes = self._load_envelopes(run_id, events_dir)
        if not envelopes:
            raise LongRunningResumeError("Long-running run has no valid transition envelopes.", run_id=run_id)
        latest = envelopes[-1][1]
        head_path = run_dir / "state.json"
        if head_path.is_file():
            head = self._read_snapshot(head_path, run_id)
            if head.last_event_seq > latest.last_event_seq:
                raise LongRunningResumeError("Ledger head points beyond its immutable event chain.", run_id=run_id)
            if head.last_event_seq == latest.last_event_seq and LongRunningCodec.hash_value(head) != LongRunningCodec.hash_value(latest):
                raise LongRunningResumeError("Ledger head disagrees with its immutable transition envelope.", run_id=run_id)
        if not head_path.is_file() or self._read_snapshot(head_path, run_id).last_event_seq < latest.last_event_seq:
            with self._lock:
                self._assert_writer()
                self._atomic_write(head_path, latest)
        return latest

    def events(self, run_id: str) -> tuple[LongRunningEvent, ...]:
        # Validate and return the event half of every immutable envelope.
        events_dir = self._run_path(run_id) / "events"
        if not events_dir.is_dir():
            raise LongRunningResumeError("Long-running run id was not found.", run_id=run_id)
        return tuple(event for event, _ in self._load_envelopes(run_id, events_dir))

    def store_identity(self) -> Mapping[str, Any]:
        # Fingerprint the resolved root without exposing its full private path.
        return {"type": "file", "schema_version": LongRunningCodec.SCHEMA_VERSION, "root_hash": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()}

    def _load_envelopes(self, run_id: str, events_dir: Path) -> tuple[tuple[LongRunningEvent, RunLedgerSnapshot], ...]:
        # Validate monotonic sequence, hash linkage, and post-state agreement in order.
        paths = sorted((path for path in events_dir.glob("*.json") if path.name.split("-", 1)[0].isdigit()), key=lambda path: int(path.name.split("-", 1)[0]))
        output: list[tuple[LongRunningEvent, RunLedgerSnapshot]] = []
        previous_hash = ""
        for expected_seq, path in enumerate(paths, start=1):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                event = LongRunningCodec.decode(raw["event"])
                snapshot = LongRunningCodec.decode(raw["snapshot"])
            except (OSError, KeyError, json.JSONDecodeError, LongRunningResumeError) as exc:
                raise LongRunningResumeError("Ledger transition envelope is corrupt.", run_id=run_id, details={"envelope_file": path.name}) from exc
            if not isinstance(event, LongRunningEvent) or not isinstance(snapshot, RunLedgerSnapshot):
                raise LongRunningResumeError("Ledger transition envelope has the wrong schema types.", run_id=run_id, details={"envelope_file": path.name})
            if event.seq != expected_seq or event.previous_event_hash != previous_hash:
                raise LongRunningResumeError("Ledger transition sequence or hash link is non-monotonic.", run_id=run_id, details={"expected_seq": expected_seq, "actual_seq": event.seq})
            _validate_transition_envelope(snapshot, event)
            previous_hash = snapshot.last_event_hash
            output.append((event, snapshot))
        return tuple(output)

    def _read_snapshot(self, path: Path, run_id: str) -> RunLedgerSnapshot:
        # Decode one state head and reject any schema/type mismatch.
        try:
            value = LongRunningCodec.loads(path.read_text(encoding="utf-8"))
        except (OSError, LongRunningResumeError) as exc:
            raise LongRunningResumeError("Ledger state head is corrupt.", run_id=run_id) from exc
        if not isinstance(value, RunLedgerSnapshot):
            raise LongRunningResumeError("Ledger state head has the wrong schema type.", run_id=run_id)
        return value

    def _write_envelope(self, run_dir: Path, snapshot: RunLedgerSnapshot, event: LongRunningEvent) -> None:
        # Persist the crash-recovery authority once; never replace an existing sequence.
        path = run_dir / "events" / f"{event.seq:012d}-{event.event_id}.json"
        if path.exists():
            raise LongRunningLedgerError("Ledger event sequence file already exists.", run_id=event.run_id, details={"event_seq": event.seq})
        self._atomic_write(path, {"event": event, "snapshot": snapshot})

    def _run_path(self, run_id: str) -> Path:
        # Validate externally supplied run ids before constructing a filesystem path.
        if not self._RUN_ID.fullmatch(run_id):
            raise LongRunningResumeError("Run id must match lr_<lowercase-hex>.", run_id=run_id)
        return self._contained(self._runs_root / run_id)

    def _contained(self, path: Path) -> Path:
        # Reject path traversal before any ledger filesystem access.
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise LongRunningLedgerError("Run ledger path escaped its configured root.", details={"root_name": self.root.name}) from exc
        return resolved

    def _claim_writer(self) -> None:
        # @intent single-writer-run-ledger
        # Envelope-first writes recover crashes, but sequence allocation is still a
        # multi-record transaction. Claim one process so two controllers cannot append
        # different events at the same sequence and both believe they own the head.
        try:
            descriptor = os.open(self._writer_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            owner = self._writer_lock_path.read_text(encoding="utf-8").strip()
            if owner == str(os.getpid()):
                return
            raise LongRunningLedgerError("File run ledger root is already claimed by another writer process.", details={"root_name": self.root.name})
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
            handle.flush()
            os.fsync(handle.fileno())

    def _assert_writer(self) -> None:
        # Detect a missing or replaced writer claim before a durable mutation.
        try:
            owner = self._writer_lock_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise LongRunningLedgerError("File run ledger writer claim is unavailable.", details={"root_name": self.root.name}) from exc
        if owner != str(os.getpid()):
            raise LongRunningLedgerError("File run ledger writer claim changed unexpectedly.", details={"root_name": self.root.name})

    def _atomic_write(self, path: Path, value: Any) -> None:
        # Write/fsync/replace a complete JSON value so readers never see partial data.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            encoded = LongRunningCodec.encode(value)
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(encoded, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise LongRunningLedgerError("Ledger JSON file could not commit atomically.", details={"file_name": path.name}) from exc


class RunLedger:
    """Controller-owned monotonic ledger transition facade."""

    def __init__(self, snapshot: RunLedgerSnapshot, store: RunLedgerStore, *, required: bool = True) -> None:
        # Bind one recovered head to its store and persistence failure policy.
        self._snapshot = snapshot
        self.store = store
        self.required = required

    @classmethod
    def create(cls, state: LongRunningState, store: RunLedgerStore, *, required: bool = True) -> "RunLedger":
        # Create revision-zero state plus the first immutable RUN_STARTED envelope.
        if state.revision != 0:
            raise LongRunningLedgerError("New run state must start at revision zero.", run_id=state.run_id, details={"revision": state.revision})
        state_hash = LongRunningCodec.hash_value(state)
        created_at = ProcedureIdentity.utc_now()
        event = cls._event(state, LongRunningEventKind.RUN_STARTED, {}, seq=1, previous_event_hash="", state_hash=state_hash, created_at=created_at)
        event_hash = LongRunningCodec.hash_value(event)
        snapshot = RunLedgerSnapshot(LongRunningCodec.SCHEMA_VERSION, state.run_id, state.revision, 1, state, state.settings_fingerprint, event_hash, created_at, created_at)
        store.create(snapshot, event)
        return cls(snapshot, store, required=required)

    @classmethod
    def resume(cls, run_id: str, store: RunLedgerStore, *, required: bool = True) -> "RunLedger":
        # Load the newest valid envelope-backed snapshot for continuation.
        return cls(store.load(run_id), store, required=required)

    def append(self, kind: LongRunningEventKind, payload: Mapping[str, Any], *, task_id: str = "", attempt_id: str = "", role: str = "") -> LongRunningEvent:
        # Append an observation without changing state revision or semantic state.
        return self._commit_snapshot(self._snapshot.state, kind, payload, task_id=task_id, attempt_id=attempt_id, role=role, expect_revision_increment=False)

    def commit(self, state: LongRunningState, kind: LongRunningEventKind, payload: Mapping[str, Any], *, task_id: str = "", attempt_id: str = "", role: str = "") -> LongRunningEvent:
        # Commit one semantic successor state and its matching transition event.
        return self._commit_snapshot(state, kind, payload, task_id=task_id, attempt_id=attempt_id, role=role, expect_revision_increment=True)

    def snapshot(self) -> RunLedgerSnapshot:
        # Return the immutable current head for result construction and auditing.
        return self._snapshot

    def events(self) -> tuple[LongRunningEvent, ...]:
        # Return the store-validated event chain for this run.
        return self.store.events(self._snapshot.run_id)

    def _commit_snapshot(self, state: LongRunningState, kind: LongRunningEventKind, payload: Mapping[str, Any], *, task_id: str, attempt_id: str, role: str, expect_revision_increment: bool) -> LongRunningEvent:
        # Build one complete event/snapshot pair before exposing the next role to state.
        expected_revision = self._snapshot.revision + (1 if expect_revision_increment else 0)
        if state.revision != expected_revision:
            raise LongRunningLedgerError("Successor state revision does not match transition type.", run_id=state.run_id, details={"expected_revision": expected_revision, "actual_revision": state.revision})
        seq = self._snapshot.last_event_seq + 1
        state_hash = LongRunningCodec.hash_value(state)
        created_at = ProcedureIdentity.utc_now()
        event = self._event(state, kind, payload, seq=seq, previous_event_hash=self._snapshot.last_event_hash, state_hash=state_hash, created_at=created_at, task_id=task_id, attempt_id=attempt_id, role=role)
        event_hash = LongRunningCodec.hash_value(event)
        snapshot = RunLedgerSnapshot(LongRunningCodec.SCHEMA_VERSION, state.run_id, state.revision, seq, state, state.settings_fingerprint, event_hash, self._snapshot.created_at, created_at)
        try:
            self.store.commit(snapshot, event, expected_last_event_seq=self._snapshot.last_event_seq)
        except Exception:
            if self.required:
                raise
            return event
        self._snapshot = snapshot
        return event

    @staticmethod
    def _event(state: LongRunningState, kind: LongRunningEventKind, payload: Mapping[str, Any], *, seq: int, previous_event_hash: str, state_hash: str, created_at: str, task_id: str = "", attempt_id: str = "", role: str = "") -> LongRunningEvent:
        # Derive one stable event id from committed public state and transition metadata.
        payload_hash = LongRunningCodec.hash_value(dict(payload))
        event_id = ProcedureIdentity.deterministic_id("event", state.run_id, str(seq), kind.value, state_hash, payload_hash)
        return LongRunningEvent(LongRunningCodec.SCHEMA_VERSION, event_id, state.run_id, seq, state.revision, kind, created_at, state_hash, previous_event_hash, task_id, attempt_id, role, payload)


def _validate_transition_envelope(snapshot: RunLedgerSnapshot, event: LongRunningEvent) -> None:
    # Prove that one event and its post-state snapshot describe the same transition.
    if snapshot.schema_version != LongRunningCodec.SCHEMA_VERSION or event.schema_version != LongRunningCodec.SCHEMA_VERSION:
        raise LongRunningLedgerError("Ledger transition uses an unsupported schema version.", run_id=snapshot.run_id)
    if snapshot.run_id != event.run_id or snapshot.state.run_id != event.run_id:
        raise LongRunningLedgerError("Ledger transition run ids do not agree.", run_id=event.run_id)
    if snapshot.last_event_seq != event.seq or snapshot.revision != event.revision or snapshot.state.revision != event.revision:
        raise LongRunningLedgerError("Ledger transition sequence/revision fields do not agree.", run_id=event.run_id, details={"event_seq": event.seq, "snapshot_seq": snapshot.last_event_seq, "event_revision": event.revision, "snapshot_revision": snapshot.revision})
    if event.state_hash_after != LongRunningCodec.hash_value(snapshot.state):
        raise LongRunningLedgerError("Ledger event state hash does not match its snapshot.", run_id=event.run_id, details={"event_seq": event.seq})
    if snapshot.last_event_hash != LongRunningCodec.hash_value(event):
        raise LongRunningLedgerError("Ledger snapshot event hash does not match its event.", run_id=event.run_id, details={"event_seq": event.seq})


__all__ = [
    "BehaviorFingerprint", "FileRunLedgerStore", "InMemoryRunLedgerStore",
    "LongRunningCodec", "LongRunningEvent", "LongRunningEventKind", "RunLedger",
    "RunLedgerSnapshot", "RunLedgerStore",
]
