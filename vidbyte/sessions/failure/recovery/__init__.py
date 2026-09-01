"""FILE: vidbyte/sessions/failure/recovery/__init__.py

PURPOSE: Exposes parameterized Session failure recovery contracts and built-ins.
ROLE IN CODEBASE: Keeps recovery imports stable while allowing new modes under this package.
ARCHITECTURE NOTE: Recovery handlers return bounded RecoveryResult objects and never register globally.
COMMON MODIFICATION PATTERNS: Add a handler module, export its public class, and cover its error posture.
KNOWN EDGE CASES: Preserve sync/async callback support and fail-open/closed handler behavior.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from vidbyte.sessions.failure.recovery.base import (
    BaseRecoveryHandler,
    FailureRaisedError,
    RecoveryHandler,
    RecoveryResult,
)
from vidbyte.sessions.failure.recovery.builtins import (
    AggregateRecovery,
    CallbackRecovery,
    CompactRecovery,
    ContinueRecovery,
    ForkRecovery,
    HumanReviewRecovery,
    RaiseRecovery,
    StopRecovery,
    TeacherHandoffRecovery,
)

__all__ = [
    "AggregateRecovery",
    "BaseRecoveryHandler",
    "CallbackRecovery",
    "CompactRecovery",
    "ContinueRecovery",
    "FailureRaisedError",
    "ForkRecovery",
    "HumanReviewRecovery",
    "RaiseRecovery",
    "RecoveryHandler",
    "RecoveryResult",
    "StopRecovery",
    "TeacherHandoffRecovery",
]
