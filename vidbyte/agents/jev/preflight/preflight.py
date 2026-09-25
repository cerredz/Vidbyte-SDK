"""FILE: vidbyte/agents/jev/preflight/preflight.py

PURPOSE: Implements JevPreflight, the gate in front of JevAgent's generative agent: it combines every enabled preset's questions into one Jev request, then one match statement acts on the answers and decides whether the generative agent runs.
ROLE IN CODEBASE: JevAgent builds one JevPreflight from its settings at construction and passes it to JevRuntime, which calls pass_() before the inherited linear loop and stops the run when it returns False.
ARCHITECTURE NOTE: Question text and flags stay in vidbyte/lib/jev/ (JevPreflightRegistry, JevPresets); this class owns asking, scoring, failing open, and the action each preset triggers (JevPreflightTools, JevClarificationAgent), and it reports every outcome through JevResponse.
COMMON MODIFICATION PATTERNS: Add a preset by adding its questions to combine(), its outcome to _outcomes(), and one commented case to the match in pass_(); never add preset checks to JevRuntime.
KNOWN EDGE CASES: No enabled question makes no Jev call; a missing credential, a provider failure, or a local request-validation error marks every preset unavailable; a missing answer marks only its own preset unavailable. Every unavailable preset fails open, so the run continues as the owner configured it.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from vidbyte.agents.jev.preflight.clarification import JevClarificationAgent
from vidbyte.agents.jev.preflight.tools import JevPreflightTools
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE, JEV_PREFLIGHT_REQUEST_FIELD
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevPreflightRun,
    JevPresetResult,
    JevQuestion,
    JevToolSelection,
)
from vidbyte.lib.enums.jev import JevPreflightPreset, JevQuestionType
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.runners.decision import DecisionModelRunner

PresetOutcome = JevPresetResult | JevToolSelection


class JevPreflight:
    """Gate in front of JevAgent's generative agent: one Jev request for every enabled preset, then one match over the outcomes."""

    def __init__(self, settings: JevAgentSettings, response: JevResponse) -> None:
        # Fixes every preflight input when JevAgent is built; nothing about preflight is read at run time.
        # @intent preflight-is-configured-once
        # The owner asked for every preset and threshold to be set in JevAgent's constructor, so the runtime
        # receives this finished gate and never looks at settings itself.
        self.presets: tuple[JevPreflightPreset, ...] = JevPreflightRegistry.validate(settings.preflight)
        self.decision = settings.decision
        self.response = response
        self.tools = JevPreflightTools(settings.tool_selector_threshold)
        self.clarification = JevClarificationAgent(settings) if JevPreflightPreset.CLARITY in self.presets else None

    def combine(self, run: JevPreflightRun) -> JevDecisionRequest | None:
        """Return one Jev request holding every enabled preset's questions, or None when no preset has a question to ask."""
        questions: list[JevQuestion] = []
        for preset in self.presets:
            if preset is JevPreflightPreset.TOOL_SELECTOR:
                questions.extend(self.tools.questions(run.tools))
            else:
                questions.extend(JevPreflightRegistry.questions(preset))
        if not questions:
            return None
        return JevDecisionRequest(state={JEV_PREFLIGHT_REQUEST_FIELD: run.message}, questions=tuple(questions))

    async def pass_(self, run: JevPreflightRun) -> bool:
        """Act on every enabled preset's answers and return True when JevAgent's generative agent should run."""
        answers = await self._ask(run)
        for outcome in self._outcomes(run, answers):
            self.response.preset(outcome)
            match outcome:
                case JevPresetResult(available=False) | JevToolSelection(available=False):
                    # Jev could not answer this preset (no credential, a provider failure, or a missing
                    # answer): fail open and leave the run exactly as the owner configured it.
                    continue
                case JevToolSelection():
                    # Tool selector: the generative agent sees and can call only the tools Jev judged useful.
                    run.tools = self.tools.narrow(run.tools, outcome)
                case JevPresetResult(preset=JevPreflightPreset.CLARITY, passed=False):
                    # The request is unclear: JevClarificationAgent writes simple questions for the user, and the
                    # run stops so the user answers them before any generative-agent tokens are spent.
                    if await self._clarify(run, outcome):
                        return False
                case _:
                    # A preset that passed needs no action.
                    continue
        return True

    async def _ask(self, run: JevPreflightRun) -> Mapping[str, JevAnswer] | None:
        # Sends the one combined request and returns Jev's answers, {} when there was nothing to ask, or None on failure.
        # @intent preflight-fails-open
        # Preflight is advisory: a missing TypeSafe key, a provider failure, or a request Jev cannot accept
        # returns None, which marks every preset unavailable instead of blocking the agent.
        try:
            request = self.combine(run)
            if request is None:
                return {}
            decision = await DecisionModelRunner(self.decision).arun(request)
        except VidbyteSdkError:
            return None
        self.response.preflight_usage(JevUsage.from_usage_payload(decision.usage or {}))
        return decision.answers

    def _outcomes(self, run: JevPreflightRun, answers: Mapping[str, JevAnswer] | None) -> tuple[PresetOutcome, ...]:
        # Turns Jev's answers into one outcome per enabled preset, in the order the owner enabled them.
        return tuple(self.tools.select(run.tools, answers) if preset is JevPreflightPreset.TOOL_SELECTOR else self._score(preset, answers) for preset in self.presets)

    @staticmethod
    def _score(preset: JevPreflightPreset, answers: Mapping[str, JevAnswer] | None) -> JevPresetResult:
        # Scores one fixed-question preset as the mean P(yes) of its questions against the preset's threshold.
        # @intent every-question-is-positive
        # Every question is phrased so yes means satisfied, so the mean needs no inversion; any missing or
        # non-noul answer makes only this preset unavailable, and an unavailable preset never fails.
        definition = JevPresets.definition(preset)
        found = {key: None if answers is None else answers.get(key.value) for key in definition.question_keys}
        noul = {key: answer for key, answer in found.items() if answer is not None and answer.question_type is JevQuestionType.NOUL}
        if len(noul) != len(found):
            return JevPresetResult(preset=preset, score=None, available=False)
        score = math.fsum(answer.probabilities[JEV_NOUL_TRUE] for answer in noul.values()) / len(noul)
        return JevPresetResult(preset=preset, score=score, passed=score >= definition.threshold, answers=noul)

    async def _clarify(self, run: JevPreflightRun, result: JevPresetResult) -> bool:
        # Routes an unclear request to JevClarificationAgent and records its questions; False means it wrote none.
        clarification = None if self.clarification is None else await self.clarification.clarify(run.message, result)
        if clarification is None:
            # The clarifier failed or wrote nothing; fail open like any other preflight outage.
            return False
        self.response.needs_clarification(clarification)
        return True


__all__ = ["JevPreflight"]
