"""Context Protocol Header

Path: vidbyte/procedures/store.py
Purpose: Define the persistence contract consumed by ProcedureLibrary.
Architecture: ProcedureStore exposes immutable version chains, operation lookup,
compare-and-swap writes, and exact-version outcome append/query methods.
Exports: ProcedureStore.
Invariants: put never mutates a prior version; append_outcome is idempotent by id;
normal active-head semantics remain a library concern.
Do not: Add model retrieval, ranking, promotion authority, or file layout here.
Related: stores/memory.py, stores/file.py, and procedures/library.py.
Tests: Existing protocol/import verification; no new tests by approved workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from vidbyte.procedures.contracts import ProcedureOutcome, ProcedureRecord, ProcedureRef


class ProcedureStore(Protocol):
    """Trusted append-only persistence adapter for procedure audit records."""

    def put(self, record: ProcedureRecord, *, expected_latest_version: int | None) -> None:
        # Append one immutable version after an exact chain-head comparison.
        ...

    def get(self, namespace: str, procedure_id: str, version: int) -> ProcedureRecord:
        # Load one historical audit record by exact version.
        ...

    def latest(self, namespace: str, procedure_id: str) -> ProcedureRecord:
        # Load the numerically latest audit record, not the active verified head.
        ...

    def versions(self, namespace: str, procedure_id: str) -> tuple[ProcedureRecord, ...]:
        # Return the full immutable identity chain in version order.
        ...

    def list_ids(self, namespace: str) -> tuple[str, ...]:
        # Return stable procedure ids known in one namespace.
        ...

    def list_latest(self, namespace: str) -> tuple[ProcedureRecord, ...]:
        # Return each identity's latest audit record for diagnostics.
        ...

    def find_by_operation(self, namespace: str, learning_operation_id: str) -> tuple[ProcedureRecord, ...]:
        # Find idempotent mutations previously applied for one SDK operation id.
        ...

    def append_outcome(self, outcome: ProcedureOutcome) -> bool:
        # Append an immutable outcome, returning False only for an identical replay.
        ...

    def outcomes(self, procedure: ProcedureRef) -> tuple[ProcedureOutcome, ...]:
        # Return outcomes pinned to one exact version and fingerprint.
        ...

    def store_identity(self) -> Mapping[str, Any]:
        # Return stable non-secret adapter identity for durable resume fingerprints.
        ...


__all__ = ["ProcedureStore"]
