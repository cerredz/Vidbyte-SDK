"""FILE: vidbyte/sessions/failure/__init__.py

PURPOSE: Exposes the Session-owned deterministic failure vocabulary and recovery router.
ROLE IN CODEBASE: Defines the stable import surface for failure contracts, rules, and handlers.
ARCHITECTURE NOTE: The vocabulary itself (codes, enums, Failure, RecoveryResult) lives in
    vidbyte.lib.enums.failure and vidbyte.lib.dataclasses.failure; this package re-exports it
    alongside the Session-specific router, rule decorator, and recovery handlers so existing
    `from vidbyte.sessions.failure import ...` and `from vidbyte import ...` call sites keep working.
    FailureMiddleware is re-exported here from vidbyte.middleware.builtins even though router.py
    itself cannot import it (A006 forbids vidbyte.sessions -> vidbyte.middleware at the concrete-module
    level); a package __init__ facade is outside that dependency graph, so the re-export is safe here.
COMMON MODIFICATION PATTERNS: Add public symbols here only after defining and testing their owning module.
KNOWN EDGE CASES: Keep exports cycle-safe because Session and agent modules import this boundary.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/README.md.
TESTS: python scripts/test-session-failure-vocabulary.py.
"""

from vidbyte.lib.dataclasses.failure import (
    Failure,
    FailureSafety,
    RecoveryAttempt,
    RecoveryHandler,
    RecoveryResult,
)
from vidbyte.lib.enums.failure import (
    FailureCode,
    FailureDisposition,
    FailurePhase,
    FailureSeverity,
    FailureStatus,
    RuleErrorMode,
)
from vidbyte.lib.errors import FailureRaisedError
from vidbyte.middleware.builtins.session_failure_router import FailureMiddleware
from vidbyte.sessions.failure.recovery import (
    AggregateRecovery,
    BaseRecoveryHandler,
    CallbackRecovery,
    CompactRecovery,
    ContinueRecovery,
    ForkRecovery,
    HumanReviewRecovery,
    RaiseRecovery,
    StopRecovery,
    TeacherHandoffRecovery,
)
from vidbyte.sessions.failure.router import (
    FailureMetadataNormalizer,
    FailureRouter,
)
from vidbyte.sessions.failure.rules import FailureRule, rule

__all__ = [
    "AggregateRecovery",
    "BaseRecoveryHandler",
    "CallbackRecovery",
    "CompactRecovery",
    "ContinueRecovery",
    "Failure",
    "FailureCode",
    "FailureDisposition",
    "FailureMetadataNormalizer",
    "FailureMiddleware",
    "FailurePhase",
    "FailureRaisedError",
    "FailureRouter",
    "FailureRule",
    "FailureSafety",
    "FailureSeverity",
    "FailureStatus",
    "ForkRecovery",
    "HumanReviewRecovery",
    "RaiseRecovery",
    "RecoveryAttempt",
    "RecoveryHandler",
    "RecoveryResult",
    "RuleErrorMode",
    "StopRecovery",
    "TeacherHandoffRecovery",
    "rule",
]
