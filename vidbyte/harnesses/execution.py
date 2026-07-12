"""FILE: vidbyte/harnesses/execution.py

PURPOSE:
    Wraps an arbitrary harness implementation in one canonical run lifecycle.
    It records the resolved specification, ordered evidence, terminal outcome,
    artifact references, and persistence diagnostics without prescribing an
    agent loop, model provider, tool system, or orchestration strategy.

ROLE IN CODEBASE:
    HarnessClient.load constructs LoadedHarness after config and implementation
    resolution. LoadedHarness.execute owns boundary capture and delegates all
    internal behavior to HarnessImplementation.execute(request, context).

ARCHITECTURE NOTE:
    This module is an execution envelope, not a harness framework. Persistence
    policy is isolated in HarnessPersistenceCoordinator so the implementation
    protocol remains one open method. See the approved design document.

PUBLIC API INVENTORY:
    HarnessContext.emit(), add_artifact(), and link_session() let implementations
    contribute evidence explicitly. LoadedHarness exposes spec, implementation,
    store, and execute().

COMMON MODIFICATION PATTERNS:
    Add envelope behavior around _invoke_implementation and keep implementation
    internals opaque. Add persisted fields through contracts and serialization
    before populating them here.

WHAT NOT TO DO IN THIS FILE:
    1. Do not require harness inheritance, graph nodes, tools, prompts, or models.
    2. Do not infer successful persistence after a best-effort store failure.
    3. Do not persist raw values without HarnessSerializer.safe().
    4. Do not let cleanup failures replace an implementation exception.

KNOWN EDGE CASES:
    Synchronous implementations run inline and therefore cannot be interrupted by
    an asyncio timeout while blocking. Cancellation and timeout cannot fence side
    effects already started. Best-effort stores can retain partial records and
    report every failed operation on the returned terminal run. Context mutation
    is sealed before terminal snapshots so retained background tasks fail closed.

COMMON ERRORS:
    HarnessExecutionError for implementation failures; HarnessTimeoutError for
    explicit deadlines; HarnessStoreError when required persistence fails.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline success/failure/timeout/cancellation/persistence smoke
    verification; no dedicated test file was added in the no-tests workflow.

CONCURRENCY MODEL:
    Each execute call has isolated context state. emit() uses a per-run asyncio
    lock, while the configured HarnessStore owns cross-run backend concurrency.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import uuid4

from vidbyte.harnesses.contracts import (
    HARNESS_SCHEMA_VERSION,
    HarnessArtifactRef,
    HarnessCaptureLevel,
    HarnessCaptureScope,
    HarnessErrorRecord,
    HarnessEvent,
    HarnessExecutionResult,
    HarnessPersistenceMode,
    HarnessRun,
    HarnessRunStatus,
    HarnessSpec,
)
from vidbyte.harnesses.errors import HarnessConfigurationError, HarnessExecutionError, HarnessRunTransitionError, HarnessStoreError, HarnessTimeoutError
from vidbyte.harnesses.registry import HarnessImplementation
from vidbyte.harnesses.serialization import HarnessSerializer
from vidbyte.harnesses.store import HarnessStore

T = TypeVar("T")


class _HarnessDeadlineExpired(Exception):
    """Private marker distinguishing the SDK deadline from implementation timeouts."""


def _utc_now() -> str:
    # Produces a timezone-aware portable timestamp for every persisted boundary.
    return datetime.now(timezone.utc).isoformat()


class HarnessPersistenceCoordinator:
    """Applies required or best-effort policy consistently to store operations."""

    def __init__(self, store: HarnessStore, mode: HarnessPersistenceMode) -> None:
        # Binds one store and tracks safe operation-level failures for one run.
        self._store = store
        self._mode = mode
        self._errors: list[str] = []

    @property
    def errors(self) -> tuple[str, ...]:
        # Returns an immutable snapshot of persistence diagnostics accumulated so far.
        return tuple(self._errors)

    async def put_spec(self, spec: HarnessSpec) -> bool:
        # Persists exact behavior identity according to the configured failure policy.
        return await self._operate("put_spec", lambda: self._store.put_spec(spec))

    async def begin_run(self, run: HarnessRun) -> bool:
        # Creates the running snapshot according to the configured failure policy.
        return await self._operate("begin_run", lambda: self._store.begin_run(run))

    async def append_event(self, event: HarnessEvent) -> bool:
        # Appends one ordered event and reports whether it became canonical evidence.
        return await self._operate("append_event", lambda: self._store.append_event(event))

    async def finish_run(self, run: HarnessRun) -> bool:
        # Writes the terminal snapshot according to the configured failure policy.
        return await self._operate("finish_run", lambda: self._store.finish_run(run))

    async def _operate(self, operation: str, call: Callable[[], Awaitable[T]]) -> bool:
        # Converts arbitrary backend failures into safe policy-aware diagnostics.
        try:
            await call()
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = self._persistence_error(operation, exc)
            self._errors.append(f"{operation}: {type(exc).__name__}")
            if self._mode is HarnessPersistenceMode.REQUIRED:
                raise error from exc
            return False

    def _persistence_error(self, operation: str, error: Exception) -> HarnessStoreError:
        # Preserves typed store failures and safely wraps provider-specific exceptions.
        if isinstance(error, HarnessStoreError):
            return error
        return HarnessStoreError("Required harness persistence operation failed.", details={"operation": operation, "backend_error_type": type(error).__name__})


class HarnessContext:
    """Run-local evidence surface offered to an otherwise arbitrary implementation."""

    def __init__(self, spec: HarnessSpec, run_id: str, coordinator: HarnessPersistenceCoordinator, serializer: HarnessSerializer, capture_level: HarnessCaptureLevel) -> None:
        # Initializes isolated event, artifact, and session-link state for one run.
        self._spec = deepcopy(spec)
        self._run_id = run_id
        self._coordinator = coordinator
        self._serializer = serializer
        self._capture_level = capture_level
        self._next_sequence = 0
        self._event_count = 0
        self._artifacts: list[HarnessArtifactRef] = []
        self._session_ids: list[str] = []
        self._emit_lock = asyncio.Lock()
        self._closed = False

    @property
    def spec(self) -> HarnessSpec:
        # Exposes the exact resolved specification used to construct the implementation.
        return deepcopy(self._spec)

    @property
    def run_id(self) -> str:
        # Exposes the unique execution identifier for implementation-side correlation.
        return self._run_id

    @property
    def event_count(self) -> int:
        # Reports only events confirmed by the canonical store.
        return self._event_count

    @property
    def artifacts(self) -> tuple[HarnessArtifactRef, ...]:
        # Returns the artifact references contributed by this implementation.
        return tuple(self._artifacts)

    @property
    def session_ids(self) -> tuple[str, ...]:
        # Returns durable-session identifiers linked by the implementation.
        return tuple(self._session_ids)

    @property
    def persistence_errors(self) -> tuple[str, ...]:
        # Exposes safe best-effort persistence diagnostics accumulated for this run.
        return self._coordinator.errors

    async def emit(self, event_type: str, payload: Mapping[str, Any] | None = None) -> HarnessEvent:
        # Builds one run-local event and advances sequence only after confirmed persistence.
        normalized_type = self._required_text(event_type, "event_type")
        if payload is not None and not isinstance(payload, Mapping):
            raise HarnessConfigurationError("Harness event payload must be a mapping or null.", details={"actual_type": type(payload).__name__})
        async with self._emit_lock:
            self._assert_open()
            event = self._build_event(normalized_type, payload or {})
            persisted = await self._coordinator.append_event(event)
            if persisted:
                self._next_sequence += 1
                self._event_count += 1
            return event

    def add_artifact(self, uri: str, *, media_type: str | None = None, sha256: str | None = None, metadata: Mapping[str, Any] | None = None) -> HarnessArtifactRef:
        # Registers an external artifact reference without reading or copying its content.
        self._assert_open()
        normalized_uri = self._required_text(uri, "uri")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise HarnessConfigurationError("Harness artifact metadata must be a mapping or null.", details={"actual_type": type(metadata).__name__})
        artifact = HarnessArtifactRef(
            artifact_id=f"hart_{uuid4().hex}",
            uri=normalized_uri,
            media_type=self._optional_text(media_type, "media_type"),
            sha256=self._optional_text(sha256, "sha256"),
            metadata=self._captured_mapping(metadata or {}),
        )
        self._artifacts.append(artifact)
        return artifact

    def link_session(self, session_id: str) -> None:
        # Links one durable Session by identifier while retaining first-seen order.
        self._assert_open()
        normalized = self._required_text(session_id, "session_id")
        if normalized not in self._session_ids:
            self._session_ids.append(normalized)

    def _build_event(self, event_type: str, payload: Mapping[str, Any]) -> HarnessEvent:
        # Constructs the next candidate event without advancing state before persistence.
        return HarnessEvent(
            schema_version=HARNESS_SCHEMA_VERSION,
            event_id=f"hevt_{uuid4().hex}",
            run_id=self._run_id,
            sequence=self._next_sequence,
            event_type=event_type,
            created_at=_utc_now(),
            payload=self._captured_mapping(payload),
        )

    def _captured_mapping(self, value: Mapping[str, Any]) -> Mapping[str, Any]:
        # Applies capture-level minimization and secret-safe JSON projection.
        if self._capture_level is HarnessCaptureLevel.MINIMAL:
            return {}
        projected = self._serializer.safe(value)
        return projected if isinstance(projected, dict) else {}

    def _required_text(self, value: Any, field: str) -> str:
        # Normalizes one required context identifier with actionable field diagnostics.
        if not isinstance(value, str) or not value.strip():
            raise HarnessConfigurationError("Harness context field must be a non-empty string.", details={"field": field, "actual_type": type(value).__name__})
        return value.strip()

    def _optional_text(self, value: Any, field: str) -> str | None:
        # Normalizes optional artifact text and rejects empty or non-string values.
        if value is None:
            return None
        return self._required_text(value, field)

    async def _close(self) -> None:
        # Seals implementation-facing mutation before the terminal snapshot is built.
        async with self._emit_lock:
            self._closed = True

    def _assert_open(self) -> None:
        # Rejects evidence contributed after the wrapper has begun terminalization.
        if self._closed:
            raise HarnessRunTransitionError("Harness context is closed after terminalization.", details={"run_id": self._run_id})


class LoadedHarness:
    """Executable harness implementation bound to exact behavior and run policy."""

    def __init__(self, spec: HarnessSpec, implementation: HarnessImplementation, store: HarnessStore, *, serializer: HarnessSerializer | None = None, capture_level: HarnessCaptureLevel = HarnessCaptureLevel.FULL, persistence_mode: HarnessPersistenceMode = HarnessPersistenceMode.BEST_EFFORT, metadata: Mapping[str, Any] | None = None) -> None:
        # Binds immutable load-time choices while leaving implementation behavior opaque.
        if metadata is not None and not isinstance(metadata, Mapping):
            raise HarnessConfigurationError("Harness default metadata must be a mapping or null.", details={"actual_type": type(metadata).__name__})
        self._spec = deepcopy(spec)
        self._implementation = implementation
        self._store = store
        self._serializer = serializer or HarnessSerializer()
        self._capture_level = capture_level
        self._persistence_mode = persistence_mode
        self._metadata = dict(metadata or {})
        self._capture_scope = self._resolve_capture_scope(implementation)

    @property
    def spec(self) -> HarnessSpec:
        # Returns the deterministic behavior identity shared by repeated runs.
        return deepcopy(self._spec)

    @property
    def implementation(self) -> HarnessImplementation:
        # Returns the arbitrary implementation selected directly or by exact registry.
        return self._implementation

    @property
    def store(self) -> HarnessStore:
        # Returns the canonical persistence port bound at load time.
        return self._store

    async def execute(self, request: Any, *, metadata: Mapping[str, Any] | None = None, timeout_seconds: float | None = None) -> HarnessExecutionResult:
        # Runs one unique execution inside the automatic persistence and evidence envelope.
        timeout = self._validate_timeout(timeout_seconds)
        run_metadata = self._merge_metadata(metadata)
        coordinator = HarnessPersistenceCoordinator(self._store, self._persistence_mode)
        running = self._new_running_run(request, run_metadata, coordinator.errors)
        context = HarnessContext(self._spec, running.run_id, coordinator, self._serializer, self._capture_level)
        await coordinator.put_spec(self._spec)
        running = replace(running, persistence_errors=coordinator.errors)
        try:
            await coordinator.begin_run(running)
            try:
                await context.emit("harness.run.started", {"status": HarnessRunStatus.RUNNING.value})
            except HarnessStoreError as exc:
                await self._complete_problem(running, context, coordinator, HarnessRunStatus.FAILED, exc, "harness.run.failed")
                raise
            try:
                output = await self._invoke_with_timeout(request, context, timeout)
            except _HarnessDeadlineExpired as exc:
                timeout_error = TimeoutError("Harness execution exceeded timeout_seconds.")
                terminal = await self._complete_problem(running, context, coordinator, HarnessRunStatus.TIMED_OUT, timeout_error, "harness.run.timed_out")
                raise HarnessTimeoutError("Harness execution exceeded timeout_seconds.", run=terminal) from exc
            except HarnessStoreError as exc:
                await self._complete_problem(running, context, coordinator, HarnessRunStatus.FAILED, exc, "harness.run.failed")
                raise
            except Exception as exc:
                terminal = await self._complete_problem(running, context, coordinator, HarnessRunStatus.FAILED, exc, "harness.run.failed")
                raise HarnessExecutionError("Harness implementation execution failed.", run=terminal) from exc
            return await self._complete_success(output, running, context, coordinator)
        except asyncio.CancelledError:
            await self._complete_cancellation(running, context, coordinator)
            raise

    async def _invoke_with_timeout(self, request: Any, context: HarnessContext, timeout_seconds: float | None) -> Any:
        # Applies an optional deadline around the open sync-or-async implementation seam.
        if timeout_seconds is None:
            return await self._invoke_implementation(request, context)
        deadline = asyncio.timeout(timeout_seconds)
        try:
            async with deadline:
                result = await self._invoke_implementation(request, context)
        except TimeoutError as exc:
            if deadline.expired():
                raise _HarnessDeadlineExpired from exc
            raise
        if deadline.expired():
            raise _HarnessDeadlineExpired
        return result

    async def _invoke_implementation(self, request: Any, context: HarnessContext) -> Any:
        # Calls the open method directly and awaits only implementations returning awaitables.
        result = self._implementation.execute(request, context)
        return await result if inspect.isawaitable(result) else result

    async def _complete_success(self, output: Any, running: HarnessRun, context: HarnessContext, coordinator: HarnessPersistenceCoordinator) -> HarnessExecutionResult:
        # Records the success boundary, writes the terminal snapshot, and returns raw output.
        try:
            await context.emit("harness.run.succeeded", {"status": HarnessRunStatus.SUCCEEDED.value})
        except HarnessStoreError:
            await context._close()
            terminal = self._terminal_run(running, context, coordinator, HarnessRunStatus.SUCCEEDED, response=output)
            await self._finish_without_masking(coordinator, terminal)
            raise
        await context._close()
        terminal = self._terminal_run(running, context, coordinator, HarnessRunStatus.SUCCEEDED, response=output)
        await coordinator.finish_run(terminal)
        terminal = replace(terminal, persistence_errors=coordinator.errors)
        return HarnessExecutionResult(output=output, run=terminal)

    async def _complete_problem(self, running: HarnessRun, context: HarnessContext, coordinator: HarnessPersistenceCoordinator, status: HarnessRunStatus, error: BaseException, event_type: str) -> HarnessRun:
        # Finalizes failure evidence without allowing cleanup errors to mask the primary cause.
        await self._emit_without_masking(context, event_type, {"status": status.value, "exception_type": type(error).__name__})
        await context._close()
        record = HarnessErrorRecord(exception_type=type(error).__name__, message=self._serializer.safe_error_message(error))
        terminal = self._terminal_run(running, context, coordinator, status, error=record)
        await self._finish_without_masking(coordinator, terminal)
        return replace(terminal, persistence_errors=coordinator.errors)

    async def _complete_cancellation(self, running: HarnessRun, context: HarnessContext, coordinator: HarnessPersistenceCoordinator) -> None:
        # Shields best-effort cancellation finalization while preserving caller cancellation.
        cancellation = asyncio.CancelledError("Harness execution was cancelled.")
        task = asyncio.create_task(self._complete_problem(running, context, coordinator, HarnessRunStatus.CANCELLED, cancellation, "harness.run.cancelled"))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            return

    async def _emit_without_masking(self, context: HarnessContext, event_type: str, payload: Mapping[str, Any]) -> None:
        # Suppresses only persistence cleanup errors after a primary execution failure.
        try:
            await context.emit(event_type, payload)
        except HarnessStoreError:
            return

    async def _finish_without_masking(self, coordinator: HarnessPersistenceCoordinator, terminal: HarnessRun) -> None:
        # Attempts terminal persistence while retaining the original execution outcome.
        try:
            await coordinator.finish_run(terminal)
        except HarnessStoreError:
            return

    def _new_running_run(self, request: Any, metadata: Mapping[str, Any], persistence_errors: tuple[str, ...]) -> HarnessRun:
        # Creates one unique RUNNING snapshot separate from deterministic spec identity.
        return HarnessRun(
            schema_version=HARNESS_SCHEMA_VERSION,
            run_id=f"hrun_{uuid4().hex}",
            spec_id=self._spec.spec_id,
            status=HarnessRunStatus.RUNNING,
            started_at=_utc_now(),
            ended_at=None,
            capture_level=self._capture_level,
            capture_scope=self._capture_scope,
            request=self._capture_value(request),
            metadata=metadata,
            persistence_errors=persistence_errors,
        )

    # @intent immutable-run-terminalization
    # A terminal snapshot is the dataset index for everything the implementation
    # explicitly contributed. Build it once from run-local state, then ask the
    # store to enforce the sole RUNNING-to-terminal transition. Retries must create
    # a new run_id; mutating this record would silently rewrite historical evidence.
    def _terminal_run(self, running: HarnessRun, context: HarnessContext, coordinator: HarnessPersistenceCoordinator, status: HarnessRunStatus, *, response: Any = None, error: HarnessErrorRecord | None = None) -> HarnessRun:
        # Materializes one immutable terminal snapshot from confirmed run-local evidence.
        return replace(
            running,
            status=status,
            ended_at=_utc_now(),
            response=self._capture_value(response),
            error=error,
            artifacts=context.artifacts,
            session_ids=context.session_ids,
            event_count=context.event_count,
            persistence_errors=coordinator.errors,
        )

    def _capture_value(self, value: Any) -> Any:
        # Omits boundary values at minimal capture and safely projects them at full capture.
        return None if self._capture_level is HarnessCaptureLevel.MINIMAL else self._serializer.safe(value)

    def _merge_metadata(self, metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
        # Merges load-time and run-time metadata outside deterministic behavior identity.
        if metadata is not None and not isinstance(metadata, Mapping):
            raise HarnessConfigurationError("Harness execution metadata must be a mapping or null.", details={"actual_type": type(metadata).__name__})
        merged = {**self._metadata, **dict(metadata or {})}
        projected = self._serializer.safe(merged)
        return projected if isinstance(projected, dict) else {}

    def _validate_timeout(self, value: float | None) -> float | None:
        # Requires a positive finite numeric deadline and rejects booleans explicitly.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0 or value == float("inf") or value != value:
            raise HarnessConfigurationError("timeout_seconds must be a positive finite number or null.", details={"actual_type": type(value).__name__, "value": str(value)})
        return float(value)

    def _resolve_capture_scope(self, implementation: HarnessImplementation) -> HarnessCaptureScope:
        # Reads an optional honest instrumentation declaration and defaults to boundary-only.
        value = getattr(implementation, "capture_scope", HarnessCaptureScope.BOUNDARY)
        try:
            return value if isinstance(value, HarnessCaptureScope) else HarnessCaptureScope(value)
        except (TypeError, ValueError) as exc:
            raise HarnessConfigurationError("Harness implementation capture_scope is unsupported.", details={"value": str(value), "allowed": [item.value for item in HarnessCaptureScope]}) from exc


__all__ = ["HarnessContext", "LoadedHarness"]
