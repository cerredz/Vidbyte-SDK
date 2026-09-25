"""FILE: vidbyte/lib/jev/preflight/__init__.py

PURPOSE: Exposes JevPreflight and every fixed preflight question dataclass from the canonical preflight folder.
ROLE IN CODEBASE: JevAgentSettings and JevRuntime import JevPreflight from here; tests import the question dataclasses to pin their contract.
ARCHITECTURE NOTE: This folder is the one home for preflight questions and the logic that asks them; flags live in vidbyte/lib/jev/presets.py and records in vidbyte/lib/dataclasses/jev.py.
COMMON MODIFICATION PATTERNS: Export each new preset's question module here alongside the existing clarity questions.
KNOWN EDGE CASES: Importing this package builds the question registry but never resolves credentials or constructs a decision runner.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from vidbyte.lib.jev.preflight.clarity import (
    CLARITY_QUESTIONS,
    ClarityCompletionQuestion,
    ClarityConsistencyQuestion,
    ClarityConstraintsQuestion,
    ClarityDeliverableQuestion,
    ClarityGoalQuestion,
    ClarityInformationQuestion,
    ClarityPrioritiesQuestion,
    ClarityReferencesQuestion,
    ClarityScopeQuestion,
    ClaritySingleReadingQuestion,
    ClarityTargetQuestion,
    ClarityTimeContextQuestion,
)
from vidbyte.lib.jev.preflight.preflight import JevPreflight

__all__ = [
    "CLARITY_QUESTIONS",
    "ClarityCompletionQuestion",
    "ClarityConsistencyQuestion",
    "ClarityConstraintsQuestion",
    "ClarityDeliverableQuestion",
    "ClarityGoalQuestion",
    "ClarityInformationQuestion",
    "ClarityPrioritiesQuestion",
    "ClarityReferencesQuestion",
    "ClarityScopeQuestion",
    "ClaritySingleReadingQuestion",
    "ClarityTargetQuestion",
    "ClarityTimeContextQuestion",
    "JevPreflight",
]
