"""FILE: vidbyte/agents/jev/motivating_case/__init__.py

PURPOSE: Groups the internal pieces of the motivating-case done check (JevPresets.MotivatingCase).
ROLE IN CODEBASE: JevRuntime imports the builders, ledger, handoff, and policy from here; none of these are public SDK API.
ARCHITECTURE NOTE: Each module has one role: state, evidence ledger, handoff, code checks, Jev questions, policy, and generative builders.
COMMON MODIFICATION PATTERNS: Keep new logic in the module whose role it matches; keep Jev judgments in questions.py and combinations in policy.py.
KNOWN EDGE CASES: Importing this package must not construct a decision runner or resolve credentials.
RELATED DOCS: docs/design/jev-motivating-case.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from vidbyte.agents.jev.motivating_case.builders import (
    MotivatingCaseHandoffBuilderAgent,
    MotivatingCaseStateBuilderAgent,
)
from vidbyte.agents.jev.motivating_case.checks import (
    ScenarioEvidence,
    ScenarioEvidenceChecker,
)
from vidbyte.agents.jev.motivating_case.evidence import RunEvent, RunEventLedger
from vidbyte.agents.jev.motivating_case.handoff import (
    MotivatingCaseHandoff,
    ScenarioExercise,
)
from vidbyte.agents.jev.motivating_case.policy import (
    MotivatingCaseDecision,
    MotivatingCasePolicy,
    ScenarioVerdict,
)
from vidbyte.agents.jev.motivating_case.questions import MotivatingCaseQuestions
from vidbyte.agents.jev.motivating_case.state import (
    MotivatingCaseState,
    MotivatingScenario,
    VerbatimText,
)

__all__ = [
    "MotivatingCaseDecision",
    "MotivatingCaseHandoff",
    "MotivatingCaseHandoffBuilderAgent",
    "MotivatingCasePolicy",
    "MotivatingCaseQuestions",
    "MotivatingCaseState",
    "MotivatingCaseStateBuilderAgent",
    "MotivatingScenario",
    "RunEvent",
    "RunEventLedger",
    "ScenarioEvidence",
    "ScenarioEvidenceChecker",
    "ScenarioExercise",
    "ScenarioVerdict",
    "VerbatimText",
]
