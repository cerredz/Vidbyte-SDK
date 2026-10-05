"""FILE: vidbyte/agents/jev/compute/recognizer.py

PURPOSE: Implements JevComputeRecognizer, which asks Jev which compute situation the main agent's run is in: one focused request per eligible situation, scored against that situation's gate, veto, and threshold, combined into one JevComputeDecision.
ROLE IN CODEBASE: JevComputeController builds one recognizer when any situation is enabled and calls `recognize` after each verified refresh of the run brief; the decision is reported on JevAgent.response.
ARCHITECTURE NOTE: Jev recognizes observable signs; it never decides whether extra compute would help. Code chooses each situation's subject and skips situations the brief cannot show (JevComputeStates), and scoring is fixed policy from JevComputeSituations. Situations are independent, so their requests run concurrently.
COMMON MODIFICATION PATTERNS: Add a situation through its questions and definition in vidbyte/lib/jev/compute/ and its state builder in states.py; this module needs no change.
KNOWN EDGE CASES: An unavailable Jev, a missing answer, or a failed request recognizes nothing for that situation (it never passes), so an outage never spends compute. A gate below the threshold fails the situation whatever the mean.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from vidbyte.agents.jev.brief import JevRunBriefEvents
from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import (
    JevComputeDecision,
    JevComputeSituationResult,
    JevDecisionRequest,
    JevRunBrief,
)
from vidbyte.lib.enums.jev import JevComputeQuestionKey, JevComputeSituation
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev.compute import JevComputeRegistry, JevComputeSituations
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse


class JevComputeRecognizer:
    """Asks Jev which compute situation the run is in, one focused request per eligible situation."""

    def __init__(self, decision: DecisionModelConfig, situations: tuple[JevComputeSituation, ...]) -> None:
        # Fixes the decision model and the enabled situations, in priority order, at JevAgent construction.
        self.decision = decision
        self.situations = situations

    async def recognize(self, iteration: int, request: str, brief: JevRunBrief, events: JevRunBriefEvents) -> JevComputeDecision:
        """Return what Jev recognized for every enabled situation, and the first situation that passed."""
        results = await asyncio.gather(*(self._recognize(situation, JevComputeStates.build(situation, request, brief, events)) for situation in self.situations))
        return JevComputeDecision(iteration=iteration, results=tuple(results), situation=next((result.situation for result in results if result.passed), None))

    async def _recognize(self, situation: JevComputeSituation, state: Mapping[str, object] | None) -> JevComputeSituationResult:
        # Asks one situation's sign questions over its state, or records it as not eligible when it has no state.
        # @intent an-unanswered-situation-is-never-recognized
        # A missing key, a provider failure, or a state Jev cannot accept records the situation as unavailable, and an
        # unavailable situation never passes, so a Jev outage leaves the run exactly as it would be without compute.
        if state is None:
            return JevComputeSituationResult(situation=situation, eligible=False)
        try:
            request = JevDecisionRequest(state=state, questions=JevComputeRegistry.questions(situation))
            decision = await DecisionModelHelper(self.decision).arun(request)
        except VidbyteSdkError:
            return JevComputeSituationResult(situation=situation, available=False)
        return self._score(situation, decision)

    @staticmethod
    def _score(situation: JevComputeSituation, decision: DecisionModelResponse) -> JevComputeSituationResult:
        # Scores the answers against the situation's threshold and veto, then requires the gate sign on its own.
        definition = JevComputeSituations.definition(situation)
        usage = JevUsage.from_usage_payload(decision.usage or {})
        verdict = DecisionModelHelper.score_noul(decision.answers, tuple(key.value for key in definition.question_keys), definition.threshold, definition.veto)
        if verdict is None:
            return JevComputeSituationResult(situation=situation, available=False, usage=usage)
        answers = {JevComputeQuestionKey(name): answer for name, answer in verdict.answers.items()}
        gate_passed = definition.gate is None or answers[definition.gate].probabilities[JEV_NOUL_TRUE] >= definition.threshold
        return JevComputeSituationResult(situation=situation, score=verdict.score, passed=verdict.passed and gate_passed, answers=answers, usage=usage)


__all__ = ["JevComputeRecognizer"]
