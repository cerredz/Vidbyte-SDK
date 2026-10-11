"""FILE: vidbyte/agents/jev/compute/recognizer.py

PURPOSE: Ask Jev which enabled dynamic-compute option best fits the main agent's current run evidence.
ROLE IN CODEBASE: JevComputeController builds one recognizer and calls recognize after every verified run-brief update.
ARCHITECTURE NOTE: All enabled option questions share one request and one evidence state; code chooses the highest complete mean P(true) above the common threshold.
COMMON MODIFICATION PATTERNS: Register fixed option questions in vidbyte/lib/jev/compute/ and keep selection policy here.
KNOWN EDGE CASES: Provider errors and incomplete option answers produce no selection; enum order breaks score ties.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD
from vidbyte.lib.dataclasses.jev import (
    JevComputeDecision,
    JevComputeOptionResult,
    JevDecisionRequest,
    JevRunBrief,
    JevRunFacts,
)
from vidbyte.lib.enums.jev import JevDynamicComputeOption
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev.compute import JevComputeRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper


class JevComputeRecognizer:
    """Ask Jev once which enabled dynamic-compute option best fits the current evidence."""

    def __init__(self, decision: DecisionModelConfig, dynamic_compute: tuple[JevDynamicComputeOption, ...]) -> None:
        self.decision = decision
        self.dynamic_compute = dynamic_compute

    async def recognize(
        self,
        iteration: int,
        request: str,
        brief: JevRunBrief,
        facts: JevRunFacts,
        events: JevRunEventLog,
    ) -> JevComputeDecision:
        """Evaluate all enabled options in one request and select the highest qualifying mean P(true)."""
        # @intent one-request-compares-options-on-the-same-state
        # Shared questions and state make option means comparable; missing answers cannot qualify an option.
        if not self.dynamic_compute:
            return JevComputeDecision(iteration=iteration, results=(), option=None)

        state = JevComputeStates.build(request, brief, facts, events)
        questions = JevComputeRegistry.questions(self.dynamic_compute)
        try:
            decision = await DecisionModelHelper(self.decision).arun(JevDecisionRequest(state=state, questions=questions))
        except VidbyteSdkError:
            return JevComputeDecision(
                iteration=iteration,
                results=tuple(JevComputeOptionResult(option=option) for option in self.dynamic_compute),
                option=None,
            )

        usage = JevUsage.from_usage_payload(decision.usage or {})
        results: list[JevComputeOptionResult] = []
        for option in self.dynamic_compute:
            keys = JevComputeRegistry.question_keys(option)
            verdict = DecisionModelHelper.score_noul(
                decision.answers,
                tuple(key.value for key in keys),
                threshold=JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD,
            )
            answers = {
                key: decision.answers[key.value]
                for key in keys
                if key.value in decision.answers
            }
            results.append(JevComputeOptionResult(option=option, score=None if verdict is None else verdict.score, answers=answers))

        qualifying: list[tuple[float, JevComputeOptionResult]] = []
        for result in results:
            score = result.score
            if score is not None and score >= JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD:
                qualifying.append((score, result))
        candidate = max(qualifying, key=lambda item: item[0], default=None)
        return JevComputeDecision(
            iteration=iteration,
            results=tuple(results),
            option=None if candidate is None else candidate[1].option,
            usage=usage,
        )


__all__ = ["JevComputeRecognizer"]
