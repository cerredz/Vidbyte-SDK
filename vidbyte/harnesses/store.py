"""FILE: vidbyte/harnesses/store.py

PURPOSE:
    Defines the asynchronous HarnessStore port and shared collision, lifecycle,
    ordering, filtering, and lookup invariants. Concrete backends implement raw
    record operations while this file keeps behavior identical across providers.

ROLE IN CODEBASE:
    LoadedHarness and HarnessContext write through HarnessStore. Memory/file
    stores subclass BaseHarnessStore, dataset export queries the protocol, and
    future closed/public database adapters may implement either contract.

ARCHITECTURE NOTE:
    Harness events are a separate append stream from terminal run snapshots.
    This store must not be replaced by SessionStore, whose checkpoint DAG serves
    resumability rather than trajectory capture. See the approved design doc.

PUBLIC API INVENTORY:
    HarnessStore protocol methods put_spec(), get_spec(), begin_run(),
    append_event(), finish_run(), get_run(), events(), and list_runs().
    BaseHarnessStore implements those invariants over abstract raw methods.

COMMON MODIFICATION PATTERNS:
    Add query behavior to the protocol/base first, then implement raw support in
    every backend and update dataset/docs. Keep lifecycle validation centralized.

WHAT NOT TO DO IN THIS FILE:
    1. Do not serialize backend-specific payloads; HarnessSerializer owns shape.
    2. Do not execute implementations or select persistence policy.
    3. Do not mutate terminal runs or accept event sequence gaps.
    4. Do not add Session checkpoint semantics.

KNOWN EDGE CASES:
    One BaseHarnessStore instance serializes operations with an asyncio lock.
    Custom protocol-only stores own equivalent atomicity. A persisted RUNNING run
    can remain after process death and is intentionally visible as incomplete.

COMMON ERRORS:
    HarnessSpecCollisionError, HarnessRunConflictError,
    HarnessRunTransitionError, HarnessEventSequenceError, HarnessStoreError.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by memory/file lifecycle and event-order smoke verification; no
    dedicated test file was added under the approved no-tests workflow.

CONCURRENCY MODEL:
    BaseHarnessStore uses one coarse asyncio.Lock per instance so read-check-write
    invariants are atomic for concurrent tasks in one process.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from vidbyte.harnesses.contracts import HarnessEvent, HarnessRun, HarnessRunStatus, HarnessSpec
from vidbyte.harnesses.errors import (
    HarnessEventSequenceError,
    HarnessRunConflictError,
    HarnessRunTransitionError,
    HarnessSpecCollisionError,
    HarnessStoreError,
)

_TERMINAL_STATUSES = frozenset({
    HarnessRunStatus.SUCCEEDED,
    HarnessRunStatus.FAILED,
    HarnessRunStatus.CANCELLED,
    HarnessRunStatus.TIMED_OUT,
})


@runtime_checkable
class HarnessStore(Protocol):
    """Structural asynchronous contract for canonical harness persistence."""

    async def put_spec(self, spec: HarnessSpec) -> HarnessSpec:
        # Persists one content-addressed specification idempotently.
        ...

    async def get_spec(self, spec_id: str) -> HarnessSpec:
        # Retrieves one specification or raises a typed store failure.
        ...

    async def begin_run(self, run: HarnessRun) -> HarnessRun:
        # Creates one unique RUNNING run linked to an existing specification.
        ...

    async def append_event(self, event: HarnessEvent) -> HarnessEvent:
        # Appends the next monotonic event to a RUNNING execution.
        ...

    async def finish_run(self, run: HarnessRun) -> HarnessRun:
        # Replaces a RUNNING record exactly once with a terminal snapshot.
        ...

    async def get_run(self, run_id: str) -> HarnessRun:
        # Retrieves one running or terminal execution by unique id.
        ...

    async def events(self, run_id: str) -> list[HarnessEvent]:
        # Retrieves the ordered event stream for one existing run.
        ...

    async def list_runs(self, *, spec_id: str | None = None, status: HarnessRunStatus | None = None, limit: int | None = None) -> list[HarnessRun]:
        # Lists deterministic run snapshots matching optional filters.
        ...


class BaseHarnessStore(ABC):
    """Shared store invariants built over backend-specific raw operations."""

    def __init__(self) -> None:
        # Serializes public read-check-write operations for one backend instance.
        self._operation_lock = asyncio.Lock()

    async def put_spec(self, spec: HarnessSpec) -> HarnessSpec:
        # Writes a new spec or returns the existing semantically identical record.
        async with self._operation_lock:
            existing = await self._read_spec(spec.spec_id)
            if existing is None:
                await self._write_spec(spec)
                return spec
            if dict(existing.resolved_config) != dict(spec.resolved_config):
                raise HarnessSpecCollisionError("Harness spec ID resolves to conflicting behavior config.", details={"spec_id": spec.spec_id})
            return existing

    async def get_spec(self, spec_id: str) -> HarnessSpec:
        # Retrieves one specification and reports a safe missing-record error.
        async with self._operation_lock:
            spec = await self._read_spec(spec_id)
            if spec is None:
                raise HarnessStoreError("Harness specification was not found.", details={"spec_id": spec_id})
            return spec

    async def begin_run(self, run: HarnessRun) -> HarnessRun:
        # Validates and creates one unique RUNNING execution record.
        async with self._operation_lock:
            await self._assert_spec_exists(run.spec_id)
            self._assert_running_shape(run)
            if await self._read_run(run.run_id) is not None:
                raise HarnessRunConflictError("Harness run ID already exists.", details={"run_id": run.run_id, "spec_id": run.spec_id})
            await self._write_run(run)
            return run

    async def append_event(self, event: HarnessEvent) -> HarnessEvent:
        # Enforces run identity, RUNNING state, and exact next event sequence.
        async with self._operation_lock:
            run = await self._require_run(event.run_id)
            if run.status is not HarnessRunStatus.RUNNING:
                raise HarnessRunTransitionError("Cannot append an event to a terminal harness run.", details={"run_id": event.run_id, "status": run.status.value})
            current = await self._read_events(event.run_id)
            expected = len(current)
            if event.sequence != expected:
                raise HarnessEventSequenceError("Harness event sequence is not the next monotonic value.", details={"run_id": event.run_id, "expected": expected, "actual": event.sequence})
            await self._write_event(event)
            return event

    async def finish_run(self, run: HarnessRun) -> HarnessRun:
        # Validates and persists the only allowed RUNNING-to-terminal transition.
        async with self._operation_lock:
            existing = await self._require_run(run.run_id)
            self._assert_terminal_transition(existing, run)
            event_count = len(await self._read_events(run.run_id))
            if run.event_count != event_count:
                raise HarnessRunTransitionError("Harness terminal event_count does not match persisted events.", details={"run_id": run.run_id, "expected": event_count, "actual": run.event_count})
            await self._write_run(run)
            return run

    async def get_run(self, run_id: str) -> HarnessRun:
        # Retrieves one run through the shared typed missing-record behavior.
        async with self._operation_lock:
            return await self._require_run(run_id)

    async def events(self, run_id: str) -> list[HarnessEvent]:
        # Returns ordered events after first confirming the run exists.
        async with self._operation_lock:
            await self._require_run(run_id)
            return sorted(await self._read_events(run_id), key=lambda event: event.sequence)

    async def list_runs(self, *, spec_id: str | None = None, status: HarnessRunStatus | None = None, limit: int | None = None) -> list[HarnessRun]:
        # Filters stable run snapshots and applies the requested non-negative limit.
        self._validate_limit(limit)
        async with self._operation_lock:
            runs = await self._read_all_runs()
        filtered = [run for run in runs if (spec_id is None or run.spec_id == spec_id) and (status is None or run.status is status)]
        ordered = sorted(filtered, key=lambda run: (run.started_at, run.run_id))
        return ordered if limit is None else ordered[:limit]

    async def _assert_spec_exists(self, spec_id: str) -> None:
        # Requires begin_run to reference a previously persisted specification.
        if await self._read_spec(spec_id) is None:
            raise HarnessRunConflictError("Harness run references an unknown specification.", details={"spec_id": spec_id})

    async def _require_run(self, run_id: str) -> HarnessRun:
        # Returns one run or raises a safe typed lookup failure.
        run = await self._read_run(run_id)
        if run is None:
            raise HarnessRunConflictError("Harness run was not found.", details={"run_id": run_id})
        return run

    def _assert_running_shape(self, run: HarnessRun) -> None:
        # Rejects terminal fields on the initial persisted run snapshot.
        if run.status is not HarnessRunStatus.RUNNING or run.ended_at is not None:
            raise HarnessRunTransitionError("Harness begin_run requires RUNNING status and no ended_at.", details={"run_id": run.run_id, "status": run.status.value, "has_ended_at": run.ended_at is not None})
        if run.event_count != 0:
            raise HarnessRunTransitionError("Harness begin_run requires event_count zero.", details={"run_id": run.run_id, "event_count": run.event_count})

    # @intent immutable-terminal-run-history
    # A terminal harness run is future training/evaluation evidence. Reopening or
    # overwriting it would silently change the historical trajectory after users
    # may already have exported or scored it. The only legal mutation is one
    # RUNNING-to-terminal transition with the original spec, start time, and run id.
    # Any retry/idempotency feature must add a new explicit contract rather than
    # weakening this guard and making history mutable.
    def _assert_terminal_transition(self, existing: HarnessRun, terminal: HarnessRun) -> None:
        # Enforces one immutable RUNNING-to-terminal lifecycle transition.
        if existing.status is not HarnessRunStatus.RUNNING:
            raise HarnessRunTransitionError("Harness run is already terminal.", details={"run_id": terminal.run_id, "status": existing.status.value})
        if terminal.status not in _TERMINAL_STATUSES or terminal.ended_at is None:
            raise HarnessRunTransitionError("Harness finish_run requires a terminal status and ended_at.", details={"run_id": terminal.run_id, "status": terminal.status.value, "has_ended_at": terminal.ended_at is not None})
        if existing.spec_id != terminal.spec_id or existing.started_at != terminal.started_at:
            raise HarnessRunConflictError("Harness terminal run changed immutable identity fields.", details={"run_id": terminal.run_id, "expected_spec_id": existing.spec_id, "actual_spec_id": terminal.spec_id})

    def _validate_limit(self, limit: int | None) -> None:
        # Rejects boolean, negative, and non-integer run-list limits.
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0):
            raise HarnessStoreError("Harness run list limit must be a non-negative integer or null.", details={"actual_type": type(limit).__name__, "value": str(limit)})

    @abstractmethod
    async def _write_spec(self, spec: HarnessSpec) -> None:
        # Persists one specification without applying shared collision rules.
        raise NotImplementedError

    @abstractmethod
    async def _read_spec(self, spec_id: str) -> HarnessSpec | None:
        # Reads one specification by id or returns None.
        raise NotImplementedError

    @abstractmethod
    async def _write_run(self, run: HarnessRun) -> None:
        # Persists one running or terminal run snapshot by id.
        raise NotImplementedError

    @abstractmethod
    async def _read_run(self, run_id: str) -> HarnessRun | None:
        # Reads one run snapshot by id or returns None.
        raise NotImplementedError

    @abstractmethod
    async def _read_all_runs(self) -> list[HarnessRun]:
        # Reads every run snapshot for shared filtering and ordering.
        raise NotImplementedError

    @abstractmethod
    async def _write_event(self, event: HarnessEvent) -> None:
        # Appends one event after shared sequence validation.
        raise NotImplementedError

    @abstractmethod
    async def _read_events(self, run_id: str) -> list[HarnessEvent]:
        # Reads every event for one run in any backend-native order.
        raise NotImplementedError


__all__ = ["BaseHarnessStore", "HarnessStore"]
