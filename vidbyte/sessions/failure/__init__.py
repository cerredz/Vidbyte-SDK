"""FILE: vidbyte/sessions/failure/__init__.py

PURPOSE: Exposes the Session-owned deterministic failure vocabulary and recovery router.
ROLE IN CODEBASE: Defines the stable import surface for failure contracts, rules, and handlers.
ARCHITECTURE NOTE: Re-exports implementation modules without global registration or runtime side effects.
COMMON MODIFICATION PATTERNS: Add public symbols here only after defining and testing their owning module.
KNOWN EDGE CASES: Keep exports cycle-safe because Session and agent modules import this boundary.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/README.md.
TESTS: python scripts/test-session-failure-vocabulary.py.
"""

from vidbyte.sessions.failure.recovery import (
    AggregateRecovery,
    BaseRecoveryHandler,
    CallbackRecovery,
    CompactRecovery,
    ContinueRecovery,
    FailureRaisedError,
    ForkRecovery,
    HumanReviewRecovery,
    RaiseRecovery,
    RecoveryHandler,
    RecoveryResult,
    StopRecovery,
    TeacherHandoffRecovery,
)
from vidbyte.sessions.failure.router import (
    FailureMetadataNormalizer,
    FailureMiddleware,
    FailureRouter,
)
from vidbyte.sessions.failure.rules import FailureRule, rule
from vidbyte.sessions.failure.types import (
    Failure,
    FailureCode,
    FailureDisposition,
    FailurePhase,
    FailureSafety,
    FailureSeverity,
    FailureStatus,
    RecoveryAttempt,
    RuleErrorMode,
)

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
