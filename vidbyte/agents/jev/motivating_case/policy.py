"""FILE: vidbyte/agents/jev/motivating_case/policy.py

PURPOSE: Evaluates one finish attempt for the motivating-case check: verify evidence, ask Jev, combine answers, and write feedback.
ROLE IN CODEBASE: JevRuntime calls MotivatingCasePolicy.evaluate from its finish-attempt review and acts on the returned decision.
ARCHITECTURE NOTE: Jev answers only recognition questions; thresholds, outcome combination, and every feedback sentence are code over run-state fields.
COMMON MODIFICATION PATTERNS: Tune thresholds in vidbyte/lib/constants/jev.py against a labeled set; add outcomes to JevScenarioOutcome and handle them here.
KNOWN EDGE CASES: Implied scenarios never block; a blocked case passes only when the reply discloses it; a missing answer counts as "not shown".
RELATED DOCS: docs/design/jev-motivating-case.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.jev.motivating_case.checks import (
    ScenarioEvidence,
    ScenarioEvidenceChecker,
)
from vidbyte.agents.jev.motivating_case.evidence import RunEventLedger
from vidbyte.agents.jev.motivating_case.handoff import MotivatingCaseHandoff
from vidbyte.agents.jev.motivating_case.questions import (
    ASSERTS_EXPECTED,
    CODE_HANDLES_CASE,
    DISCLOSES_UNVERIFIED,
    ENVIRONMENT_BLOCKED,
    OUTCOME_PASSED,
    OUTCOME_RESULT,
    RECALL_GUARD,
    SETUP_BUILDS_CASE,
    MotivatingCaseQuestions,
)
from vidbyte.agents.jev.motivating_case.state import (
    MotivatingCaseState,
    MotivatingScenario,
)
from vidbyte.lib.constants.jev import (
    JEV_MOTIVATING_CASE_ASSERTS_THRESHOLD,
    JEV_MOTIVATING_CASE_BLOCKED_THRESHOLD,
    JEV_MOTIVATING_CASE_DISCLOSED_THRESHOLD,
    JEV_MOTIVATING_CASE_HANDLES_THRESHOLD,
    JEV_MOTIVATING_CASE_PASSED_THRESHOLD,
    JEV_MOTIVATING_CASE_RECALL_THRESHOLD,
    JEV_MOTIVATING_CASE_SETUP_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevAnswer
from vidbyte.lib.enums import JevExerciseMode, JevQuestionType, JevScenarioOutcome
from vidbyte.lib.runners.decision import DecisionModelRunner


@dataclass(frozen=True, slots=True)
class ScenarioVerdict:
    """Code-combined result for one scenario, with the Jev probabilities that produced it."""

    scenario: MotivatingScenario
    evidence: ScenarioEvidence
    outcome: JevScenarioOutcome
    disclosed: bool
    probabilities: Mapping[str, Any] = field(default_factory=dict)

    def needs_work(self) -> bool:
        # A user-named case that was never exercised holds the run open.
        return self.scenario.blocks_finish() and self.outcome is JevScenarioOutcome.NOT_EXERCISED

    def needs_disclosure(self) -> bool:
        # A user-named case the environment blocked may finish only once the reply says it was not verified.
        return self.scenario.blocks_finish() and self.outcome is JevScenarioOutcome.BLOCKED and not self.disclosed

    def metadata(self) -> dict[str, Any]:
        # Public, credential-free record for AgentResult metadata.
        return {"role": self.scenario.role.value, "outcome": self.outcome.value, "disclosed": self.disclosed, "answers": dict(self.probabilities), **self.evidence.facts()}


@dataclass(frozen=True, slots=True)
class MotivatingCaseDecision:
    """Result of reviewing one finish attempt."""

    verdicts: tuple[ScenarioVerdict, ...]
    prior_continuations: int

    def accepted(self) -> bool:
        # The attempt is accepted when no user-named case needs work or disclosure.
        return not any(verdict.needs_work() or verdict.needs_disclosure() for verdict in self.verdicts)

    def feedback(self) -> str:
        # Writes continuation feedback entirely from run-state fields and code facts.
        lines = ["The motivating-case check found requested edge cases that this run has not verified yet."]
        for verdict in self.verdicts:
            if verdict.needs_work():
                lines.append(self._work_line(verdict))
            elif verdict.needs_disclosure():
                lines.append(f'- {verdict.scenario.id}: this case could not be run here. Tell the user in your final answer that this case was not verified: {verdict.scenario.condition}.')
        lines.append("Continue the task, then give your final answer again.")
        return "\n".join(lines)

    def metadata(self) -> dict[str, Any]:
        # Summarizes the latest review for result metadata.
        # @intent report-latest-review-only
        # Metadata holds the latest review plus the continuation count, which is what threshold tuning needs without growing per attempt.
        return {"prior_continuations": self.prior_continuations, "accepted": self.accepted(), "scenarios": {verdict.scenario.id: verdict.metadata() for verdict in self.verdicts}}

    @staticmethod
    def _work_line(verdict: ScenarioVerdict) -> str:
        # Explains what is missing for one scenario and what does not count.
        scenario, evidence = verdict.scenario, verdict.evidence
        parts = [f'- {scenario.id}: the request is about "{scenario.source_quote}". Exercise this case: {scenario.condition} (target: {scenario.target}).']
        parts.append(f"A check that only covers this nearby case does not count: {scenario.near_miss}.")
        if evidence.stale and evidence.outcome_event_id:
            parts.append(f"The run at {evidence.outcome_event_id} happened before later file changes, so run the check again.")
        elif evidence.setup_event_id and evidence.outcome_event_id and not evidence.run_ok:
            parts.append(f"The run at {evidence.outcome_event_id} did not complete successfully for this check.")
        elif evidence.setup_event_id and not evidence.outcome_event_id:
            parts.append(f"The setup at {evidence.setup_event_id} was never run.")
        elif evidence.setup_event_id:
            parts.append(f"The closest check found ({evidence.setup_event_id}) does not build this case or did not pass.")
        if scenario.expected_behavior:
            parts.append(f"Check for the expected behavior: {scenario.expected_behavior}.")
        if scenario.exercise_mode is not JevExerciseMode.RUN:
            parts.append("If it cannot be run here, show the code that handles it.")
        parts.append("If the environment prevents running it, say so in your final answer.")
        return " ".join(parts)


class MotivatingCasePolicy:
    """Owns the fixed questions, thresholds, and combination rule of the motivating-case check."""

    def __init__(self, runner: DecisionModelRunner) -> None:
        # Binds one decision runner for every Jev request this run makes.
        self._runner = runner
        self._questions = MotivatingCaseQuestions()

    async def request_names_boundary(self, request: str) -> tuple[bool, float]:
        # Recall guard: reports whether Jev sees a boundary situation in a request the builder found none in.
        # @intent recall-guard-low-bar
        # A rebuild costs one generative call while a missed scenario silently disables the check, so the guard fires at a low threshold.
        response = await self._runner.arun(self._questions.recall_guard(request))
        probability = response.answer(RECALL_GUARD).noul or 0.0
        return probability >= JEV_MOTIVATING_CASE_RECALL_THRESHOLD, probability

    async def evaluate(self, state: MotivatingCaseState, ledger: RunEventLedger, handoff: MotivatingCaseHandoff, final_output: str, prior_continuations: int) -> MotivatingCaseDecision:
        # Verifies evidence in code, asks each scenario's batched questions concurrently, and combines the answers.
        # @intent one-request-per-scenario
        # Each scenario's questions share one state and are batched; scenarios run concurrently because their answers are independent.
        checker = ScenarioEvidenceChecker(ledger)
        exercises = handoff.by_id()
        evidence = [checker.check(scenario, exercises[scenario.id]) for scenario in state.scenarios]
        verdicts = await asyncio.gather(*(self._verdict(state, scenario, item, final_output) for scenario, item in zip(state.scenarios, evidence, strict=True)))
        return MotivatingCaseDecision(tuple(verdicts), prior_continuations)

    async def _verdict(self, state: MotivatingCaseState, scenario: MotivatingScenario, evidence: ScenarioEvidence, final_output: str) -> ScenarioVerdict:
        # Asks the applicable questions for one scenario and maps the answers to an outcome.
        # @intent unasked-means-not-shown
        # A question is only asked when its excerpt exists, so a missing answer must count as absent evidence, never as a pass.
        request = self._questions.scenario_request(state, scenario, evidence, final_output)
        answers: Mapping[str, JevAnswer] = {}
        if request is not None:
            answers = (await self._runner.arun(request)).answers
        outcome = self._outcome(state, scenario, evidence, answers)
        disclosed = self._noul(answers, DISCLOSES_UNVERIFIED) >= JEV_MOTIVATING_CASE_DISCLOSED_THRESHOLD
        return ScenarioVerdict(scenario, evidence, outcome, disclosed, self._probabilities(answers))

    def _outcome(self, state: MotivatingCaseState, scenario: MotivatingScenario, evidence: ScenarioEvidence, answers: Mapping[str, JevAnswer]) -> JevScenarioOutcome:
        # The combination rule from the design: exercised, then inspected, then blocked, else not exercised.
        if self._exercised(scenario, evidence, answers):
            return JevScenarioOutcome.EXERCISED
        if scenario.exercise_mode is not JevExerciseMode.RUN and self._noul(answers, CODE_HANDLES_CASE) >= JEV_MOTIVATING_CASE_HANDLES_THRESHOLD:
            return JevScenarioOutcome.INSPECTED
        if state.testing_restriction_quote is not None or self._noul(answers, ENVIRONMENT_BLOCKED) >= JEV_MOTIVATING_CASE_BLOCKED_THRESHOLD:
            return JevScenarioOutcome.BLOCKED
        return JevScenarioOutcome.NOT_EXERCISED

    def _exercised(self, scenario: MotivatingScenario, evidence: ScenarioEvidence, answers: Mapping[str, JevAnswer]) -> bool:
        # Requires a code-verified current run, a setup that builds the case, a passing result, and the expected assertion.
        if not evidence.run_ok or self._noul(answers, SETUP_BUILDS_CASE) < JEV_MOTIVATING_CASE_SETUP_THRESHOLD:
            return False
        result = answers.get(OUTCOME_RESULT)
        if result is None or result.probabilities.get(OUTCOME_PASSED, 0.0) < JEV_MOTIVATING_CASE_PASSED_THRESHOLD:
            return False
        return not scenario.expected_behavior or self._noul(answers, ASSERTS_EXPECTED) >= JEV_MOTIVATING_CASE_ASSERTS_THRESHOLD

    @staticmethod
    def _noul(answers: Mapping[str, JevAnswer], name: str) -> float:
        # Reads P(yes), treating an unasked question as "not shown".
        answer = answers.get(name)
        if answer is None or answer.noul is None:
            return 0.0
        return answer.noul

    @staticmethod
    def _probabilities(answers: Mapping[str, JevAnswer]) -> dict[str, Any]:
        # Keeps P(yes) for nouls and the full distribution for choices, for metadata and threshold tuning.
        return {name: (answer.noul if answer.question_type is JevQuestionType.NOUL else dict(answer.probabilities)) for name, answer in answers.items()}


__all__ = ["MotivatingCaseDecision", "MotivatingCasePolicy", "ScenarioVerdict"]
