"""Context Protocol Header

Path: vidbyte/procedures/__init__.py
Purpose: Expose the reusable verified-procedure memory layer as one public namespace.
Architecture: Contracts and library policy are backend-neutral; stores remain explicit.
Exports: Procedure contracts, errors, rankers, library, protocol, and reference stores.
Invariants: Importing the namespace performs no persistence or model work.
Do not: Add long-running task-controller policy here; it belongs in paradigms.
Related: vidbyte/procedures/README.md and vidbyte/paradigms/long_running.
Tests: Existing public import verification; no new tests by approved workflow.
"""

from vidbyte.procedures.contracts import (
    ProcedureCandidate, ProcedureCheckResult, ProcedureLimits, ProcedureMatch,
    ProcedureOutcome, ProcedurePromotionAuthority, ProcedureRecord, ProcedureRef,
    ProcedureStatus, ProcedureSummary, ProcedureVerificationEvidence,
)
from vidbyte.procedures.errors import (
    ProcedureError, ProcedureNotFoundError, ProcedurePromotionError,
    ProcedureStoreConflictError, ProcedureStoreError, ProcedureValidationError,
    ProcedureVersionError,
)
from vidbyte.procedures.library import LexicalProcedureRanker, ProcedureLibrary, ProcedureRanker
from vidbyte.procedures.store import ProcedureStore
from vidbyte.procedures.stores import FileProcedureStore, InMemoryProcedureStore

__all__ = [
    "FileProcedureStore", "InMemoryProcedureStore", "LexicalProcedureRanker",
    "ProcedureCandidate", "ProcedureCheckResult", "ProcedureError", "ProcedureLibrary",
    "ProcedureLimits", "ProcedureMatch", "ProcedureNotFoundError", "ProcedureOutcome",
    "ProcedurePromotionAuthority", "ProcedurePromotionError", "ProcedureRanker",
    "ProcedureRecord", "ProcedureRef", "ProcedureStatus", "ProcedureStore",
    "ProcedureStoreConflictError", "ProcedureStoreError", "ProcedureSummary",
    "ProcedureValidationError", "ProcedureVerificationEvidence", "ProcedureVersionError",
]
