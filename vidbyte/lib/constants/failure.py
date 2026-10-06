"""FILE: vidbyte/lib/constants/failure.py

PURPOSE: Owns named operational bounds for the Session failure vocabulary and recovery handlers.
ROLE IN CODEBASE: vidbyte/lib/dataclasses/failure.py and vidbyte/lib/dataclasses/failure_recovery.py
    import these constants instead of embedding bare numeric literals in validation logic.
ARCHITECTURE NOTE: Values here are policy defaults and bounds, never pricing or transport config.
COMMON MODIFICATION PATTERNS: Add one named constant per new bounded field; never inline a literal.
WHAT NOT TO DO: Do not add provider pricing, timeouts unrelated to failure routing, or UI text here.
KNOWN EDGE CASES: DEFAULT_MAX_HISTORY bounds both the failure ledger and the recovery-attempt ledger.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/vocabulary.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

DEFAULT_MAX_HISTORY: int = 512
DEFAULT_TEACHER_HANDOFF_MAX_ATTEMPTS: int = 1
DEFAULT_HUMAN_REVIEW_QUEUE: str = "default"
DEFAULT_FORK_LABEL: str = "failure-fork"

__all__ = [
    "DEFAULT_FORK_LABEL",
    "DEFAULT_HUMAN_REVIEW_QUEUE",
    "DEFAULT_MAX_HISTORY",
    "DEFAULT_TEACHER_HANDOFF_MAX_ATTEMPTS",
]
