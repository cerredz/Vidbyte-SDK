"""FILE: vidbyte/agents/jev/gate/gate.py

PURPOSE: Implements JevPreflightGate, which combines enabled fixed-question presets and optional specialist choice into one Jev request before deciding whether generation may continue.
ROLE IN CODEBASE: `JevAgent` builds the gate from its settings and response writer; `JevRuntime.arun()` calls `pass_()` before the inherited linear loop.
ARCHITECTURE NOTE: Question text and flags stay in vidbyte/lib/jev/ (JevPreflightRegistry, JevPresets); DecisionModelRunner.score_noul turns preset answers into pass or fail. This class owns decision requests, fail-open behavior, clarification, and specialist selection records. Specialist records are metadata; generation remains on the configured JevAgent. The tool selector retains its own path in preflight.py.
COMMON MODIFICATION PATTERNS: Add fixed-question presets through JevPresets and a commented case in pass_(); add descriptive profile-choice context here, without executing candidate agents or adding selection logic to JevRuntime.
KNOWN EDGE CASES: No enabled fixed-question preset makes no Jev call; a missing credential, a provider failure, or a local request-validation error marks every preset unavailable; a missing answer marks only its own preset unavailable. Every unavailable preset fails open, so the run continues as the owner configured it.
RELATED DOCS: `docs/design/jev-agent-profile-routing.md`, `skills/jev-agent/SKILL.md`, and `skills/asking-jev-questions/SKILL.md`.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.gate.clarification import JevClarificationAgent
from vidbyte.agents.jev.prompts import JevPrompt, JevPrompts
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import JEV_PREFLIGHT_REQUEST_FIELD
from vidbyte.lib.dataclasses.jev import (
    JevAgentProbability,
    JevAgentSelection,
    JevAnswer,
    JevDecisionRequest,
    JevOption,
    JevPresetResult,
    JevQuestion,
)
from vidbyte.lib.enums.jev import (
    JevPreflightPreset,
    JevPreflightQuestionKey,
    JevQuestionType,
)
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.runners.decision import DecisionModelRunner


class JevPreflightGate:
    """Gate that sends enabled preflight checks and profile choice in one request before JevAgent generation."""

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings, response: JevResponse, clarification_source: BaseAgent) -> None:
        # Fixes preflight policy and the clarification model when JevAgent is built; profile entries remain decision metadata.
        # @intent preflight-decides-before-linear-generation
        # Clarity checks and optional profile choice share one decision call. A failed clarity check stops the
        # generative loop even if TypeSafe also produced a profile label; do not record that label as selected unless
        # the gate passes. This keeps advisory routing from overriding the user's need to clarify their request.
        self.presets: tuple[JevPreflightPreset, ...] = tuple(preset for preset in JevPreflightRegistry.validate(runtime_settings.preflight) if JevPresets.has_fixed_questions(preset))
        self.settings = settings
        self.decision = runtime_settings.decision
        self.response = response
        self.clarification = JevClarificationAgent(clarification_source) if JevPreflightPreset.CLARITY in self.presets else None

    def combine(self, message: str) -> JevDecisionRequest | None:
        """Return one Jev request holding every enabled preset's questions, or None when no preset has a question to ask."""
        # @intent preflight-only-current-request
        # All checks use only the current message and descriptive profile metadata. Do not include prior
        # conversation or execution settings; neither the classifier nor the profile picker should infer them.
        questions: list[JevQuestion] = []
        for preset in self.presets:
            questions.extend(JevPreflightRegistry.questions(preset))
        questions.extend(self._profile_questions())
        if not questions:
            return None
        state: dict[str, object] = {JEV_PREFLIGHT_REQUEST_FIELD: message}
        if self.settings.agents:
            state["agents"] = tuple({"title": agent.title, "description": agent.description, "metadata": dict(agent.metadata)} for agent in self.settings.agents)
        return JevDecisionRequest(state=state, questions=tuple(questions))

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
        self._record_profile_selection(answers)
        return True

    def _profile_questions(self) -> tuple[JevQuestion, ...]:
        # Profile descriptions are decision context only; they never replace the configured generative agent.
        agents = tuple(self.settings.agents)
        if len(agents) < 2:
            return ()
        criteria = JevPrompts.selection_criteria()
        options = tuple(JevOption(agent.title, {**criteria, "title": agent.title, "description": agent.description, "metadata": dict(agent.metadata)}) for agent in agents)
        return (JevQuestion(name="agent_profile", question_type=JevQuestionType.CHOICE, instructions=JevPrompts.brief(JevPrompt.AGENT_SELECTION_QUESTION).render(), options=options),)

    def _record_profile_selection(self, answers: Mapping[str, JevAnswer] | None) -> None:
        # Records a valid highest-probability label without changing the main agent's linear execution configuration.
        agents = tuple(self.settings.agents)
        if len(agents) < 2 or answers is None or "agent_profile" not in answers:
            return
        answer = answers["agent_profile"]
        if answer.question_type is not JevQuestionType.CHOICE:
            return
        probabilities = answer.probabilities
        titles = tuple(agent.title for agent in agents)
        if set(probabilities) != set(titles):
            return
        ranked = tuple(sorted((JevAgentProbability(agent.title, probabilities[agent.title]) for agent in agents), key=lambda score: -score.probability))
        self.response.selected(JevAgentSelection(title=ranked[0].title, probability=ranked[0].probability, ranked_agents=ranked, usage=self.response.state.usage))

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
