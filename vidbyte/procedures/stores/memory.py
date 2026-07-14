"""Context Protocol Header

Path: vidbyte/procedures/stores/memory.py
Purpose: Provide an ephemeral, thread-safe procedure store for local and small runs.
Architecture: InMemoryProcedureStore owns version chains and exact-ref outcomes behind
one reentrant lock so allocation/check/write operations cannot interleave.
Exports: InMemoryProcedureStore.
Invariants: Versions are contiguous, records are immutable, CAS checks the latest audit
version, and outcome ids cannot be reused for different content.
Do not: Use this backend for durable cross-process memory or bypass ProcedureLibrary
when creating VERIFIED records.
Related: vidbyte/procedures/store.py and stores/file.py.
Tests: Existing SDK verification and inline smoke checks; no new tests by approval.
Concurrency: Thread-safe within one process; all data disappears with the store object.
"""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from typing import Any

from vidbyte.procedures.contracts import ProcedureOutcome, ProcedureRecord, ProcedureRef
from vidbyte.procedures.errors import ProcedureNotFoundError, ProcedureStoreConflictError
from vidbyte.procedures.serialization import ProcedureCodec, ProcedureIdentity


class InMemoryProcedureStore:
    """Append-only in-process procedure store."""

    def __init__(self) -> None:
        # Keep every mutable collection behind the same lock for atomic chain operations.
        self._chains: dict[tuple[str, str], list[ProcedureRecord]] = {}
        self._outcomes: dict[tuple[str, str, int, str], dict[str, ProcedureOutcome]] = {}
        self._lock = RLock()

    def put(self, record: ProcedureRecord, *, expected_latest_version: int | None) -> None:
        # Append exactly the next version after checking the caller's observed head.
        key = (record.namespace, record.procedure_id)
        with self._lock:
            chain = self._chains.setdefault(key, [])
            actual_latest = chain[-1].version if chain else None
            if actual_latest != expected_latest_version:
                raise ProcedureStoreConflictError(
                    "Procedure chain changed before the append could commit.",
                    details={"namespace": record.namespace, "procedure_id": record.procedure_id, "expected_latest_version": expected_latest_version, "actual_latest_version": actual_latest},
                )
            expected_version = 1 if actual_latest is None else actual_latest + 1
            if record.version != expected_version:
                raise ProcedureStoreConflictError(
                    "Procedure version is not the next immutable chain version.",
                    details={"namespace": record.namespace, "procedure_id": record.procedure_id, "expected_version": expected_version, "actual_version": record.version},
                )
            chain.append(record)

    def get(self, namespace: str, procedure_id: str, version: int) -> ProcedureRecord:
        # Return one exact historical record without substituting another version.
        with self._lock:
            chain = self._chains.get((namespace, procedure_id), ())
            for record in chain:
                if record.version == version:
                    return record
        raise ProcedureNotFoundError(
            "Procedure audit version was not found.",
            details={"namespace": namespace, "procedure_id": procedure_id, "version": version},
        )

    def latest(self, namespace: str, procedure_id: str) -> ProcedureRecord:
        # Return the latest audit version even when it is candidate or rejected.
        with self._lock:
            chain = self._chains.get((namespace, procedure_id), ())
            if chain:
                return chain[-1]
        raise ProcedureNotFoundError(
            "Procedure identity was not found.",
            details={"namespace": namespace, "procedure_id": procedure_id},
        )

    def versions(self, namespace: str, procedure_id: str) -> tuple[ProcedureRecord, ...]:
        # Snapshot the immutable chain so callers cannot mutate store-owned containers.
        with self._lock:
            return tuple(self._chains.get((namespace, procedure_id), ()))

    def list_ids(self, namespace: str) -> tuple[str, ...]:
        # Return deterministic identity order for stable search ranking.
        with self._lock:
            return tuple(sorted(procedure_id for record_namespace, procedure_id in self._chains if record_namespace == namespace))

    def list_latest(self, namespace: str) -> tuple[ProcedureRecord, ...]:
        # Return one latest audit record per id in deterministic id order.
        with self._lock:
            return tuple(self._chains[(namespace, procedure_id)][-1] for procedure_id in self.list_ids(namespace))

    def find_by_operation(self, namespace: str, learning_operation_id: str) -> tuple[ProcedureRecord, ...]:
        # Locate prior idempotent writes without assuming they are chain heads.
        with self._lock:
            matches = [record for (record_namespace, _), chain in self._chains.items() if record_namespace == namespace for record in chain if record.learning_operation_id == learning_operation_id]
        return tuple(sorted(matches, key=lambda record: (record.procedure_id, record.version)))

    def append_outcome(self, outcome: ProcedureOutcome) -> bool:
        # Append once by outcome id and reject same-id content conflicts.
        key = self._outcome_key(outcome.procedure)
        with self._lock:
            bucket = self._outcomes.setdefault(key, {})
            existing = bucket.get(outcome.outcome_id)
            if existing is not None:
                if ProcedureCodec.outcome_to_dict(existing) != ProcedureCodec.outcome_to_dict(outcome):
                    raise ProcedureStoreConflictError(
                        "Procedure outcome id was reused for different content.",
                        details={"outcome_id": outcome.outcome_id, "procedure_id": outcome.procedure.procedure_id},
                    )
                return False
            bucket[outcome.outcome_id] = outcome
            return True

    def outcomes(self, procedure: ProcedureRef) -> tuple[ProcedureOutcome, ...]:
        # Return exact-ref outcomes in deterministic creation/id order.
        with self._lock:
            values = tuple(self._outcomes.get(self._outcome_key(procedure), {}).values())
        return tuple(sorted(values, key=lambda outcome: (outcome.created_at, outcome.outcome_id)))

    def store_identity(self) -> Mapping[str, Any]:
        # Identify ephemeral procedure persistence without unstable object identity.
        return {"type": "memory", "schema_version": ProcedureIdentity.SCHEMA_VERSION}

    @staticmethod
    def _outcome_key(procedure: ProcedureRef) -> tuple[str, str, int, str]:
        # Include the fingerprint so replacement versions cannot inherit old failures.
        return (procedure.namespace, procedure.procedure_id, procedure.version, procedure.content_fingerprint)


__all__ = ["InMemoryProcedureStore"]
