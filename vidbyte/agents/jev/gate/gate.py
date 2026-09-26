"""FILE: vidbyte/agents/jev/gate/gate.py

PURPOSE: Implements JevPreflightGate, the gate in front of JevAgent's generative agent: it combines every enabled fixed-question preset's questions into one Jev request, then one match statement acts on the answers and decides whether the generative agent runs.
ROLE IN CODEBASE: JevAgent builds one JevPreflightGate from its settings at construction and passes it to JevRuntime, which calls pass_() before the inherited linear loop and stops the run when it returns False.
ARCHITECTURE NOTE: Question text and flags stay in vidbyte/lib/jev/ (JevPreflightRegistry, JevPresets), and DecisionModelRunner.score_noul turns answers into a pass or fail; this class owns asking, failing open, and the action each preset triggers (JevClarificationAgent), and it reports every outcome through JevResponse. The tool selector is not a gate case: it keeps its own path in vidbyte/agents/jev/preflight.py.
COMMON MODIFICATION PATTERNS: Add a fixed-question preset by adding its definition to JevPresets and one commented case to the match in pass_(); never add preset checks to JevRuntime.
KNOWN EDGE CASES: No enabled fixed-question preset makes no Jev call; a missing credential, a provider failure, or a local request-validation error marks every preset unavailable; a missing answer marks only its own preset unavailable. Every unavailable preset fails open, so the run continues as the owner configured it.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.agents.jev.gate.clarification import JevClarificationAgent
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import JEV_PREFLIGHT_REQUEST_FIELD
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevPresetResult,
    JevQuestion,
)
from vidbyte.lib.enums.jev import JevPreflightPreset, JevPreflightQuestionKey
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.runners.decision import DecisionModelRunner


class JevPreflightGate:
    """Gate in front of JevAgent's generative agent: one Jev request for every enabled fixed-question preset, then one match over the outcomes."""

    def __init__(self, settings: JevAgentSettings, response: JevResponse) -> None:
        # Fixes every preflight input when JevAgent is built; nothing about preflight is read at run time.
        # @intent preflight-is-configured-once
        # The owner asked for every preset and threshold to be set in JevAgent's constructor, so the runtime
        # receives this finished gate and never looks at settings itself.
        self.presets: tuple[JevPreflightPreset, ...] = tuple(preset for preset in JevPreflightRegistry.validate(settings.preflight) if JevPresets.has_fixed_questions(preset))
        self.decision = settings.decision
        self.response = response
        self.clarification = JevClarificationAgent(settings) if JevPreflightPreset.CLARITY in self.presets else None

    def combine(self, message: str) -> JevDecisionRequest | None:
        """Return one Jev request holding every enabled preset's questions, or None when no preset has a question to ask."""
        questions: list[JevQuestion] = []
        for preset in self.presets:
            questions.extend(JevPreflightRegistry.questions(preset))
        if not questions:
            return None
        return JevDecisionRequest(state={JEV_PREFLIGHT_REQUEST_FIELD: message}, questions=tuple(questions))

    async def pass_(self, message: str) -> bool:
        """Act on every enabled preset's answers and return True when JevAgent's generative agent should run."""
        answers = await self._ask(message)
        for outcome in (self._score(preset, answers) for preset in self.presets):
            self.response.preset(outcome)
            match outcome:
                case JevPresetResult(available=False):
                    # Jev could not answer this preset (no credential, a provider failure, or a missing
                    # answer): fail open and leave the run exactly as the owner configured it.
                    continue
                case JevPresetResult(preset=JevPreflightPreset.CLARITY, passed=False):
                    # The request is unclear: JevClarificationAgent writes simple questions for the user, and the
                    # run stops so the user answers them before any generative-agent tokens are spent.
                    if await self._clarify(message, outcome):
                        return False
                case _:
                    # A preset that passed needs no action.
                    continue
        return True

    async def _ask(self, message: str) -> Mapping[str, JevAnswer] | None:
        # Sends the one combined request and returns Jev's answers, {} when there was nothing to ask, or None on failure.
        # @intent preflight-fails-open
        # Preflight is advisory: a missing TypeSafe key, a provider failure, or a request Jev cannot accept
        # returns None, which marks every preset unavailable instead of blocking the agent.
        try:
            request = self.combine(message)
            if request is None:
                return {}
            decision = await DecisionModelRunner(self.decision).arun(request)
        except VidbyteSdkError:
            return None
        self.response.preflight_usage(JevUsage.from_usage_payload(decision.usage or {}))
        return decision.answers

    @staticmethod
    def _score(preset: JevPreflightPreset, answers: Mapping[str, JevAnswer] | None) -> JevPresetResult:
        # Scores one fixed-question preset through DecisionModelRunner.score_noul against the preset's threshold and veto.
        # @intent a-missing-answer-fails-open
        # Any missing or non-noul answer makes only this preset unavailable, and an unavailable preset never fails.
        definition = JevPresets.definition(preset)
        verdict = DecisionModelRunner.score_noul(answers, tuple(key.value for key in definition.question_keys), definition.threshold, definition.veto)
        if verdict is None:
            return JevPresetResult(preset=preset, score=None, available=False)
        evidence = {JevPreflightQuestionKey(name): answer for name, answer in verdict.answers.items()}
        return JevPresetResult(preset=preset, score=verdict.score, passed=verdict.passed, answers=evidence)

    async def _clarify(self, message: str, result: JevPresetResult) -> bool:
        # Routes an unclear request to JevClarificationAgent and records its questions; False means it wrote none.
        clarification = None if self.clarification is None else await self.clarification.clarify(message, result)
        if clarification is None:
            # The clarifier failed or wrote nothing; fail open like any other preflight outage.
            return False
        self.response.needs_clarification(clarification)
        return True


__all__ = ["JevPreflightGate"]
