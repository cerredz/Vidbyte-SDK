"""FILE: vidbyte/sessions/failure/recovery/__init__.py

PURPOSE: Exposes parameterized Session failure recovery contracts and built-ins.
ROLE IN CODEBASE: Keeps recovery imports stable while one file per recovery category grows independently.
ARCHITECTURE NOTE: Recovery handlers return bounded RecoveryResult objects and never register globally.
COMMON MODIFICATION PATTERNS: Add a new category as its own module, export its public class here.
KNOWN EDGE CASES: Preserve sync/async callback support and fail-open/closed handler behavior.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from vidbyte.lib.dataclasses.failure import RecoveryHandler, RecoveryResult
from vidbyte.lib.errors import FailureRaisedError
from vidbyte.sessions.failure.recovery.aggregate_recovery import AggregateRecovery
from vidbyte.sessions.failure.recovery.base import BaseRecoveryHandler
from vidbyte.sessions.failure.recovery.callback_recovery import CallbackRecovery
from vidbyte.sessions.failure.recovery.compact_recovery import CompactRecovery
from vidbyte.sessions.failure.recovery.continue_recovery import ContinueRecovery
from vidbyte.sessions.failure.recovery.fork_recovery import ForkRecovery
from vidbyte.sessions.failure.recovery.human_review_recovery import HumanReviewRecovery
from vidbyte.sessions.failure.recovery.raise_recovery import RaiseRecovery
from vidbyte.sessions.failure.recovery.stop_recovery import StopRecovery
from vidbyte.sessions.failure.recovery.teacher_handoff_recovery import TeacherHandoffRecovery

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
