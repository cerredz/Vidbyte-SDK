"""FILE: vidbyte/agents/jev/motivating_case/questions.py

PURPOSE: Builds the fixed Jev questions and named-field states for the motivating-case done check.
ROLE IN CODEBASE: MotivatingCasePolicy sends one request for the recall guard and one batched request per scenario at each finish attempt.
ARCHITECTURE NOTE: Every question is a single recognition step written per skills/asking-jev-questions/SKILL.md: definitions come from the run state, excerpts are code-verified, and code combines the answers.
COMMON MODIFICATION PATTERNS: Change wording only with a labeled example that motivates it; keep each question one judgment with `true` meaning yes.
KNOWN EDGE CASES: A question is omitted when the excerpt it judges is missing, so code must treat an absent answer as "not shown".
RELATED DOCS: docs/design/jev-motivating-case.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.motivating_case.checks import ScenarioEvidence
from vidbyte.agents.jev.motivating_case.state import (
    MotivatingCaseState,
    MotivatingScenario,
)
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevOption, JevQuestion
from vidbyte.lib.enums import JevExerciseMode, JevQuestionType

RECALL_GUARD = "request_names_unusual_situation"
SETUP_BUILDS_CASE = "setup_builds_case"
OUTCOME_RESULT = "outcome_result"
ASSERTS_EXPECTED = "asserts_expected"
CODE_HANDLES_CASE = "code_handles_case"
ENVIRONMENT_BLOCKED = "environment_blocked"
DISCLOSES_UNVERIFIED = "discloses_unverified"

OUTCOME_PASSED = "passed"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"
OUTCOME_UNCLEAR = "unclear"


class MotivatingCaseQuestions:
    """Builds Jev requests whose state holds only verified, named excerpts."""

    def recall_guard(self, request: str) -> JevDecisionRequest:
        # Asks whether the raw request names a boundary situation, to catch a state builder that listed none.
        # @intent recall-guard-reads-raw-request
        # The guard sees the raw request, not the builder output, so it can disagree with a builder that missed the case.
        question = JevQuestion(
            name=RECALL_GUARD,
            question_type=JevQuestionType.NOUL,
            instructions=(
                "An unusual situation is a specific input or condition outside the ordinary use of a feature, such as an empty list, "
                "a missing value, a repeated or retried call, a timeout, two conflicting records, or a failure from another service. "
                "A general request to add or change a feature, with no such situation named, does not count. "
                "Judge only the words in `request`, and ignore how urgent or confident it sounds. "
                "Does `request` name an unusual situation that the work must handle?"
            ),
        )
        return JevDecisionRequest(state={"request": request}, questions=(question,))

    def scenario_request(self, state: MotivatingCaseState, scenario: MotivatingScenario, evidence: ScenarioEvidence, final_output: str) -> JevDecisionRequest | None:
        # Batches every applicable question for one scenario; returns None when there is nothing to judge.
        # @intent state-holds-only-verified-excerpts
        # Definitions go in instructions and only code-verified excerpts go in state, so run content cannot rewrite the rules.
        fields: dict[str, object] = {}
        questions: list[JevQuestion] = []
        if evidence.setup_excerpt:
            fields["setup_excerpt"] = evidence.setup_excerpt
            questions.append(self._setup_builds_case(state, scenario))
            if scenario.expected_behavior:
                questions.append(self._asserts_expected(scenario))
        if evidence.outcome_excerpt:
            fields["outcome_excerpt"] = evidence.outcome_excerpt
            fields["case_name"] = evidence.case_name or "the check being run"
            questions.append(self._outcome_result())
        if evidence.inspection_excerpt and scenario.exercise_mode is not JevExerciseMode.RUN:
            fields["code_excerpt"] = evidence.inspection_excerpt
            questions.append(self._code_handles_case(scenario))
        if evidence.blocker_excerpt:
            fields["blocker_excerpt"] = evidence.blocker_excerpt
            questions.append(self._environment_blocked())
        if final_output.strip():
            fields["final_reply"] = final_output
            questions.append(self._discloses_unverified(scenario))
        if not questions:
            return None
        return JevDecisionRequest(state=fields, questions=tuple(questions))

    @staticmethod
    def _setup_builds_case(state: MotivatingCaseState, scenario: MotivatingScenario) -> JevQuestion:
        # One judgment: does the verified setup construct the target case rather than a neighbor or the easy case?
        return JevQuestion(
            name=SETUP_BUILDS_CASE,
            question_type=JevQuestionType.NOUL,
            instructions=(
                f"`setup_excerpt` is code or a command from the agent's run. The target case is: {scenario.condition} (applied to {scenario.target}). "
                "The excerpt matches when it creates that input or state and passes it to the target. "
                f"It does not match when it only creates this nearby case: {scenario.near_miss}; or the ordinary case: {state.ordinary_flow}; "
                "or when it replaces the target with a mock or stub. "
                "Judge only the values and calls shown, and ignore test names, comments, or messages that say what they test. "
                "Does `setup_excerpt` create the target case and pass it to the target?"
            ),
        )

    @staticmethod
    def _asserts_expected(scenario: MotivatingScenario) -> JevQuestion:
        # One judgment: does the setup check the result the user asked for, not merely run the case?
        return JevQuestion(
            name=ASSERTS_EXPECTED,
            question_type=JevQuestionType.NOUL,
            instructions=(
                f"The expected behavior for this case is: {scenario.expected_behavior}. "
                "A check asserts it when it compares the result against that behavior, for example with an equality check, an expected exception, or an expected return value. "
                "Running the case without checking its result does not count, and neither does checking a different behavior. "
                "Judge only the assertions shown in `setup_excerpt`. "
                "Does `setup_excerpt` check for the expected behavior?"
            ),
        )

    @staticmethod
    def _outcome_result() -> JevQuestion:
        # A choice with a way out, because runner output can report pass, fail, skip, or nothing at all.
        return JevQuestion(
            name=OUTCOME_RESULT,
            question_type=JevQuestionType.CHOICE,
            instructions=(
                "`outcome_excerpt` is output from a command that ran `case_name`. "
                "Choose the result the output reports for that check, or for the whole run that contains it. "
                "A run that stopped before any check ran, such as an import or syntax error, counts as failed. "
                "Judge only the text of `outcome_excerpt`. "
                "What result does `outcome_excerpt` report for `case_name`?"
            ),
            options=(
                JevOption(OUTCOME_PASSED, {"what": "The output reports the check, or the whole run containing it, as successful.", "not_for": "Output that shows any failure or error for the check.", "examples": ["1 passed in 0.12s", "OK", "All tests passed"]}),
                JevOption(OUTCOME_FAILED, {"what": "The output reports a failure, an error, or a crash before checks ran.", "not_for": "Checks reported as skipped.", "examples": ["1 failed", "AssertionError", "ModuleNotFoundError"]}),
                JevOption(OUTCOME_SKIPPED, {"what": "The output reports the check as skipped, deselected, or not collected.", "not_for": "Checks that ran and failed.", "examples": ["1 skipped", "collected 0 items", "deselected"]}),
                JevOption(OUTCOME_UNCLEAR, {"what": "The output reports no result for the check.", "not_for": "Output that reports any of the other results.", "examples": ["(the command produced no output)"]}),
            ),
        )

    @staticmethod
    def _code_handles_case(scenario: MotivatingScenario) -> JevQuestion:
        # One judgment for inspect modes: does the shown code contain a branch for this exact case?
        return JevQuestion(
            name=CODE_HANDLES_CASE,
            question_type=JevQuestionType.NOUL,
            instructions=(
                "`code_excerpt` is source code the agent read or wrote. "
                f"It handles the target case when it contains a branch, check, or guard that runs for this case: {scenario.condition}; and gives a defined result for it. "
                "A catch-all error handler that catches every exception does not count as handling this case. "
                "Judge only the code shown, and ignore comments that describe what it handles. "
                "Does `code_excerpt` contain code that handles the target case?"
            ),
        )

    @staticmethod
    def _environment_blocked() -> JevQuestion:
        # One judgment: is the quoted output an environment limitation rather than the agent's own failure?
        return JevQuestion(
            name=ENVIRONMENT_BLOCKED,
            question_type=JevQuestionType.NOUL,
            instructions=(
                "`blocker_excerpt` is output from a tool call in the agent's run. "
                "A blocker shows that the environment cannot run the check, such as a missing program, missing credentials, no network access, or a denied permission. "
                "A failing test, a syntax error, or a bug in the agent's own code is not a blocker. "
                "Judge only the text shown. "
                "Does `blocker_excerpt` show that the environment prevented the check from running?"
            ),
        )

    @staticmethod
    def _discloses_unverified(scenario: MotivatingScenario) -> JevQuestion:
        # One judgment over the candidate reply; code reads it only when the case was not exercised.
        return JevQuestion(
            name=DISCLOSES_UNVERIFIED,
            question_type=JevQuestionType.NOUL,
            instructions=(
                f"The case is: {scenario.condition}. "
                "A sentence discloses it when it tells the user that this case was not run or not verified, or that it still needs to be checked. "
                "A sentence that describes what was tested, or says the work is done, does not disclose it. "
                "Judge only the text of `final_reply`. "
                "Does `final_reply` contain a sentence telling the user that this case was not verified?"
            ),
        )


__all__ = [
    "ASSERTS_EXPECTED",
    "CODE_HANDLES_CASE",
    "DISCLOSES_UNVERIFIED",
    "ENVIRONMENT_BLOCKED",
    "MotivatingCaseQuestions",
    "OUTCOME_FAILED",
    "OUTCOME_PASSED",
    "OUTCOME_RESULT",
    "OUTCOME_SKIPPED",
    "OUTCOME_UNCLEAR",
    "RECALL_GUARD",
    "SETUP_BUILDS_CASE",
]
