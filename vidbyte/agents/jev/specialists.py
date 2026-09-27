"""FILE: vidbyte/agents/jev/specialists.py

PURPOSE: Selects the best configured JevAgent profile from the current request and exposes the full relative probability ranking.
ROLE IN CODEBASE: `Jev.generate_reply()` calls `JevAgentRouter.select()` after preflight and before `BaseAgent.generate_reply()` resolves the selected model; this router calls `DecisionModelRunner` and reads the validated profile catalog.
ARCHITECTURE NOTE: Profile selection is a Jev capability, not runtime loop policy. Prompt wording is loaded from `vidbyte/prompts/jev/` through `JevPrompts`, and output records live in `vidbyte/lib/dataclasses/jev.py`.
FUNCTION INVENTORY: `JevAgentRouter.select(message)` returns the highest-probability `JevAgentSelection` or propagates TypeSafe errors; `decision_request(message)` builds the typed request; `_rank_profiles(probabilities)` selects a stable maximum.
COMMON MODIFICATION PATTERNS: Change question semantics in the Markdown prompt and this request builder together; add response fields to the lib record and `JevResponse` writer in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not execute a candidate or mutate the coordinator; `Jev` applies its settings. 2. Do not add a confidence threshold or no-match fallback; the caller selected an always-best policy.
KNOWN EDGE CASES: Exact probability ties preserve settings order; a malformed or incomplete distribution raises instead of choosing arbitrarily; low maxima are still selected.
RELATED DOCS: `docs/design/jev-agent-profile-routing.md`, `skills/jev-agent/SKILL.md`, and `skills/asking-jev-questions/SKILL.md`.
TESTS: `tests/test_jev_agent.py` and `scripts/test-jev-agent-profile-routing.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vidbyte.agents.jev.prompts import JevPrompt, JevPrompts
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing import ProviderUsage
from vidbyte.lib.constants.jev import JEV_PREFLIGHT_REQUEST_FIELD
from vidbyte.lib.dataclasses.jev import (
    JevAgent,
    JevAgentProbability,
    JevAgentSelection,
    JevDecisionRequest,
    JevOption,
    JevQuestion,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse

_JEV_PROFILE_QUESTION = "agent_profile"


@dataclass(frozen=True, slots=True)
class JevAgentRoute:
    """Carries the public profile selection and raw decision response for exact usage accounting."""

    selection: JevAgentSelection
    decision_response: DecisionModelResponse


class JevAgentRouter:
    """Ranks configured profiles for one request without executing or changing any candidate."""

    def __init__(self, settings: JevAgentSettings, decision: DecisionModelConfig) -> None:
        # Keeps only the validated catalog and decision configuration needed for a single selection call.
        self._agents = tuple(settings.agents)
        self._decision = decision

    async def select(self, message: str) -> JevAgentRoute:
        """Ask TypeSafe to compare every profile, then select the largest returned probability."""
        # @intent route-to-highest-profile-probability
        # The coordinator has no separate general profile, so one candidate must handle the task whenever
        # routing succeeds. The choice distribution is the relative policy signal; code selects its maximum
        # and the stable profile order breaks exact ties rather than introducing a hidden confidence floor.
        decision = await DecisionModelRunner(self._decision).arun(self.decision_request(message))
        answer = decision.answer(_JEV_PROFILE_QUESTION)
        probabilities = answer.probabilities
        self._validate_answer(answer.question_type, probabilities)
        usage_type = decision.provider.usage_class()
        usage = None if usage_type is None else usage_type.from_usage_payload(decision.usage or {})
        selection = self._rank_profiles(probabilities, usage)
        return JevAgentRoute(selection=selection, decision_response=decision)

    def decision_request(self, message: str) -> JevDecisionRequest:
        """Build the one structured Choice request from this prompt and the configured profile records."""
        # @intent route-only-from-explicit-profile-data
        # TypeSafe may see the user's request, but provider secrets and candidate model settings are not
        # evidence of task fit. Keep the external request limited to the current prompt and profile fields.
        if not isinstance(message, str) or not message.strip():
            raise ConfigurationError("Jev profile routing requires a non-blank current request.")
        profiles = tuple(self._profile_state(agent) for agent in self._agents)
        question = self._selection_question()
        return JevDecisionRequest(
            state={JEV_PREFLIGHT_REQUEST_FIELD: message, "agents": profiles},
            questions=(question,),
        )

    def _selection_question(self) -> JevQuestion:
        # Keeps instructions fixed and profiles as state/options so request text cannot rewrite the rubric.
        criteria = JevPrompts.selection_criteria()
        options = tuple(JevOption(agent.title, self._profile_option(agent, criteria)) for agent in self._agents)
        return JevQuestion(
            name=_JEV_PROFILE_QUESTION,
            question_type=JevQuestionType.CHOICE,
            instructions=JevPrompts.brief(JevPrompt.AGENT_SELECTION_QUESTION).render(),
            options=options,
        )

    @staticmethod
    def _profile_state(agent: JevAgent) -> Mapping[str, object]:
        # Projects only the explicit routing fields; provider settings and secrets never enter TypeSafe state.
        return {
            "title": agent.title,
            "description": agent.description,
            "metadata": dict(agent.metadata),
        }

    @staticmethod
    def _profile_option(agent: JevAgent, criteria: Mapping[str, object]) -> Mapping[str, object]:
        # Couples the option label to the same profile fields included in the named state.
        return {**dict(criteria), "title": agent.title, "description": agent.description, "metadata": dict(agent.metadata)}

    def _validate_answer(self, question_type: JevQuestionType, probabilities: Mapping[str, float]) -> None:
        # Rejects provider output that cannot describe exactly one score for every configured profile.
        titles = tuple(agent.title for agent in self._agents)
        if question_type is not JevQuestionType.CHOICE or set(probabilities) != set(titles):
            raise ConfigurationError(
                "TypeSafe returned an invalid Jev profile selection distribution.",
                details={"expected_titles": titles, "received_titles": tuple(probabilities), "question_type": question_type.value},
            )

    def _rank_profiles(self, probabilities: Mapping[str, float], usage: ProviderUsage | None) -> JevAgentSelection:
        # Sorts stably by probability so equal scores use the caller's configured profile order.
        scores = tuple(JevAgentProbability(agent.title, probabilities[agent.title]) for agent in self._agents)
        ranked = tuple(sorted(scores, key=lambda score: -score.probability))
        return JevAgentSelection(title=ranked[0].title, probability=ranked[0].probability, ranked_agents=ranked, usage=usage)


__all__ = ["JevAgentRoute", "JevAgentRouter"]
