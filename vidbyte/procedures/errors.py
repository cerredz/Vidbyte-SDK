"""Context Protocol Header

Path: vidbyte/procedures/errors.py
Purpose: Give every procedure boundary a typed, repair-oriented SDK failure.
Architecture: ProcedureError is the feature root; store, version, promotion,
validation, conflict, and lookup failures communicate distinct invariants.
Exports: ProcedureError and specialized subclasses.
Invariants: Details are safe structured identifiers, never procedure bodies, secrets,
or raw filesystem contents; context packets remain JSON-like.
Do not: Catch and erase the original exception at I/O boundaries.
Related: vidbyte/lib/errors/base.py and docs/design/long-running-paradigm.md.
Tests: Existing exception/import verification; no new tests by approved workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import VidbyteSdkError


class ProcedureError(VidbyteSdkError):
    """Base failure for procedure learning and retrieval."""

    error_code = "procedure_error"
    violated_invariant = "Procedure operations must preserve immutable, verified, version-pinned state."
    fix_approach = "Inspect the safe details, correct the candidate/store/evidence mismatch, and retry idempotently."
    related_files = ("vidbyte/procedures/README.md", "docs/design/long-running-paradigm.md")

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        # Preserve safe dynamic identifiers without copying candidate bodies into errors.
        super().__init__(message, details=details)

    def to_context_packet(self) -> dict[str, Any]:
        # Render a stable repair packet suitable for logs or an agent context window.
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "violated_invariant": self.violated_invariant,
            "fix_approach": self.fix_approach,
            "details": dict(self.details),
            "related_files": self.related_files,
        }


class ProcedureValidationError(ProcedureError):
    """Candidate content or identifiers violate the public procedure contract."""

    error_code = "procedure_validation_error"


class ProcedureStoreError(ProcedureError):
    """Persistence failed or the durable store contained conflicting data."""

    error_code = "procedure_store_error"
    violated_invariant = "A store mutation must be atomic, append-only, and compare-and-swap safe."


class ProcedureStoreConflictError(ProcedureStoreError):
    """A concurrent or stale writer attempted an incompatible chain update."""

    error_code = "procedure_store_conflict"


class ProcedureVersionError(ProcedureError):
    """A record schema/version or exact content fingerprint is unsupported."""

    error_code = "procedure_version_error"


class ProcedurePromotionError(ProcedureError):
    """Promotion evidence or authority did not prove the exact candidate."""

    error_code = "procedure_promotion_error"
    violated_invariant = "Only an exact candidate with task, aligned-drift, and fidelity evidence may become VERIFIED."


class ProcedureNotFoundError(ProcedureError):
    """No active compatible verified procedure matched the requested handle."""

    error_code = "procedure_not_found"


__all__ = [
    "ProcedureError", "ProcedureNotFoundError", "ProcedurePromotionError",
    "ProcedureStoreConflictError", "ProcedureStoreError", "ProcedureValidationError",
    "ProcedureVersionError",
]
