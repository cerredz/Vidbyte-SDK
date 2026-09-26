"""FILE: vidbyte/lib/jev/preflight/__init__.py

PURPOSE: Exposes JevPreflightRegistry and every fixed preflight question dataclass from the canonical preflight question folder.
ROLE IN CODEBASE: JevAgentSettings and JevPreflightGate (vidbyte/agents/jev/gate/) import JevPreflightRegistry from here; tests import the question dataclasses to pin their contract.
ARCHITECTURE NOTE: This folder is the one home for fixed preflight questions and their registry; flags live in vidbyte/lib/jev/presets.py, records in vidbyte/lib/dataclasses/jev.py, and the logic that asks and acts on the questions in vidbyte/agents/jev/gate/.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before writing or changing any question (see README.md in this folder), then export each new preset's question module here alongside the existing clarity questions.
KNOWN EDGE CASES: Importing this package builds the question registry but never resolves credentials or constructs a decision runner.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from vidbyte.lib.jev.preflight.clarity import (
    CLARITY_QUESTIONS,
    ClarityActionQuestion,
    ClarityCompletionQuestion,
    ClarityConsistencyQuestion,
    ClarityConstraintsQuestion,
    ClarityDeliverableQuestion,
    ClarityInformationQuestion,
    ClarityObjectQuestion,
    ClarityPrioritiesQuestion,
    ClarityReferencesQuestion,
    ClarityScopePartsQuestion,
    ClarityScopeSizeQuestion,
    ClaritySingleReadingQuestion,
    ClarityTargetQuestion,
    ClarityTimeContextQuestion,
)
from vidbyte.lib.jev.preflight.preflight import JevPreflightRegistry

__all__ = [
    "CLARITY_QUESTIONS",
    "ClarityActionQuestion",
    "ClarityCompletionQuestion",
    "ClarityConsistencyQuestion",
    "ClarityConstraintsQuestion",
    "ClarityDeliverableQuestion",
    "ClarityInformationQuestion",
    "ClarityObjectQuestion",
    "ClarityPrioritiesQuestion",
    "ClarityReferencesQuestion",
    "ClarityScopePartsQuestion",
    "ClarityScopeSizeQuestion",
    "ClaritySingleReadingQuestion",
    "ClarityTargetQuestion",
    "ClarityTimeContextQuestion",
    "JevPreflightRegistry",
]
