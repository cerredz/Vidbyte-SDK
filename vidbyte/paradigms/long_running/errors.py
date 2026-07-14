"""Context Protocol Header

Path: vidbyte/paradigms/long_running/errors.py
Purpose: Provide typed, repair-oriented failures for durable orchestration boundaries.
Architecture: LongRunningError is the feature root; configuration, planning,
verification, ledger, resume, recovery, and finalization failures are distinct.
Exports: LongRunningError and specialized subclasses.
Invariants: Errors name safe run/task/attempt identifiers without embedding prompts,
credentials, procedure bodies, or raw transcripts.
Do not: Convert expected bounded stop reasons into exceptions or swallow original I/O
and provider causes.
Related: docs/design/long-running-paradigm.md and long_running/ledger.py.
Tests: Existing error/import verification; no new tests by approved workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import VidbyteSdkError


class LongRunningError(VidbyteSdkError):
    """Base failure for an unsafe or invalid long-running harness transition."""

    error_code = "long_running_error"
    violated_invariant = "Long-running execution may advance only from committed, validated, resumable state."
    fix_approach = "Inspect the run/task identifiers and ledger evidence, reconcile the unsafe boundary, then resume or start a new run."
    related_files = ("vidbyte/paradigms/long_running/README.md", "docs/design/long-running-paradigm.md")

    def __init__(self, message: str, *, run_id: str = "", task_id: str = "", attempt_id: str = "", details: Mapping[str, Any] | None = None) -> None:
        # Merge safe structural identifiers into the SDK error detail envelope.
        safe = dict(details or {})
        if run_id:
            safe["run_id"] = run_id
        if task_id:
            safe["task_id"] = task_id
        if attempt_id:
            safe["attempt_id"] = attempt_id
        super().__init__(message, details=safe)

    def to_context_packet(self) -> dict[str, Any]:
        # Render stable diagnostic fields for logs and bounded recovery contexts.
        return {
            "error_type": self.__class__.__name__, "error_code": self.error_code,
            "message": self.message, "violated_invariant": self.violated_invariant,
            "fix_approach": self.fix_approach, "details": dict(self.details),
            "related_files": self.related_files,
        }


class LongRunningConfigurationError(LongRunningError):
    """Settings, options, tools, or live component fingerprints are invalid."""

    error_code = "long_running_configuration_error"


class LongRunningPlanError(LongRunningError):
    """A proposed task graph is malformed, cyclic, conflicting, or contract-breaking."""

    error_code = "long_running_plan_error"


class LongRunningVerificationError(LongRunningError):
    """Verification output cannot be safely aligned with exact task criteria/evidence."""

    error_code = "long_running_verification_error"


class LongRunningLedgerError(LongRunningError):
    """Append-only ledger state, sequence, revision, hash, or persistence failed."""

    error_code = "long_running_ledger_error"
    violated_invariant = "Every controller transition must have one monotonic event and matching post-transition snapshot."


class LongRunningResumeError(LongRunningError):
    """A persisted run cannot be reconstructed or safely continued."""

    error_code = "long_running_resume_error"


class LongRunningRecoveryRequiredError(LongRunningError):
    """External side effects or isolation state require caller reconciliation."""

    error_code = "long_running_recovery_required"
    violated_invariant = "Scheduling must stop when rejected or interrupted non-read side effects cannot be proven rolled back."


class LongRunningFinalizationError(LongRunningError):
    """Synthesis or final audit could not satisfy the immutable root contract."""

    error_code = "long_running_finalization_error"


__all__ = [
    "LongRunningConfigurationError", "LongRunningError", "LongRunningFinalizationError",
    "LongRunningLedgerError", "LongRunningPlanError", "LongRunningRecoveryRequiredError",
    "LongRunningResumeError", "LongRunningVerificationError",
]
