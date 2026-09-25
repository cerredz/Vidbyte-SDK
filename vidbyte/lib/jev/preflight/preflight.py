"""FILE: vidbyte/lib/jev/preflight/preflight.py

PURPOSE: Owns every piece of JevAgent's preflight logic: the registry of preflight questions, validation of the user's enabled flags, combining questions into one Jev request, and running, scoring, and failing open.
ROLE IN CODEBASE: JevAgentSettings calls JevPreflight.validate at construction and JevRuntime calls JevPreflight.run before the inherited linear loop; nothing else in the agent layer knows a preflight question exists.
ARCHITECTURE NOTE: Questions are dataclasses in this folder, flags and their policy live in vidbyte/lib/jev/presets.py, and records live in vidbyte/lib/dataclasses/jev.py; usage parsing goes through ModelProvider.usage_class so this lib module never imports the agents layer.
COMMON MODIFICATION PATTERNS: Register a new preset's questions by adding its question tuple to _questions; keep scoring and clarification selection here rather than in JevRuntime.
KNOWN EDGE CASES: No enabled preset makes no Jev call; a missing credential, a provider failure, or a malformed answer fails open with every enabled preset marked unavailable and never blocks the agent.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE, JEV_PREFLIGHT_REQUEST_FIELD
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevPreflightQuestion,
    JevPresetResult,
    JevQuestion,
    JevResponse,
)
from vidbyte.lib.enums.jev import (
    JevPreflightPreset,
    JevPreflightQuestionKey,
    JevQuestionType,
)
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.preflight.clarity import CLARITY_QUESTIONS
from vidbyte.lib.jev.presets import JevPresets
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse

if TYPE_CHECKING:
    from vidbyte.agents.pricing import ProviderUsage

PresetResults = dict[JevPreflightPreset, JevPresetResult]


class JevPreflight:
    """Registry over every preflight question and the single owner of JevAgent's preflight logic."""

    _questions: Mapping[JevPreflightQuestionKey, JevPreflightQuestion] = MappingProxyType({question.key: question for question in CLARITY_QUESTIONS})

    @classmethod
    def get(cls, key: JevPreflightQuestionKey | str) -> JevPreflightQuestion:
        """Return the registered question for a key (enum member or its string value)."""
        try:
            resolved = key if isinstance(key, JevPreflightQuestionKey) else JevPreflightQuestionKey(key)
        except ValueError as exc:
            raise ConfigurationError(f"Unknown Jev preflight question key: {key!r}.", details={"received": repr(key)}) from exc
        found = cls._questions.get(resolved)
        if found is None:
            raise ConfigurationError(f"Jev preflight question {resolved.value!r} has no registered dataclass.", details={"key": resolved.value, "registered": [item.value for item in cls._questions]})
        return found

    @classmethod
    def validate(cls, presets: Iterable[object]) -> tuple[JevPreflightPreset, ...]:
        """Normalize the user's enabled flags and confirm every question they ask is registered here."""
        # @intent preflight-is-complete-before-the-agent-exists
        # JevAgentSettings calls this at construction, so a flag whose questions are not all registered
        # fails when the agent is built rather than failing open, unnoticed, on every run.
        normalized = JevPresets.normalize(presets)
        for preset in normalized:
            for key in JevPresets.definition(preset).question_keys:
                cls.get(key)
        return normalized

    @classmethod
    def combine(cls, presets: Iterable[JevPreflightPreset]) -> tuple[JevQuestion, ...]:
        """Return every enabled preset's questions, in preset then question order, for one Jev request."""
        return tuple(cls.get(key).to_question() for preset in presets for key in JevPresets.definition(preset).question_keys)

    @classmethod
    async def run(cls, message: str, *, presets: tuple[JevPreflightPreset, ...], decision: DecisionModelConfig) -> JevResponse:
        """Ask Jev every enabled preset's questions in one request and return the run-local response."""
        # @intent preflight-fails-open
        # Preflight is advisory: a missing TypeSafe key, a provider failure, or a malformed answer marks
        # every enabled preset unavailable and lets the agent run as if preflight were off, never blocking it.
        if not presets:
            return JevResponse(input=message)
        try:
            request = JevDecisionRequest(state={JEV_PREFLIGHT_REQUEST_FIELD: message}, questions=cls.combine(presets))
            decision_response = await DecisionModelRunner(decision).arun(request)
            results, clarification = cls._score(presets, decision_response.answers)
        except VidbyteSdkError:
            return JevResponse(input=message, results={preset: JevPresetResult(score=None, available=False) for preset in presets})
        return JevResponse(input=message, output=clarification, results=results, needs_clarification=clarification is not None, usage=cls._usage(decision_response))

    @classmethod
    def _score(cls, presets: tuple[JevPreflightPreset, ...], answers: Mapping[str, JevAnswer]) -> tuple[PresetResults, str | None]:
        # Scores each preset as its mean P(yes) and returns the clarification of the weakest failing question.
        # @intent lowest-answer-drives-the-clarification
        # Every question is phrased so yes means satisfied, so the mean needs no inversion; when any preset
        # falls below its threshold the agent asks about the single weakest answer instead of listing them all.
        results: PresetResults = {}
        weakest: tuple[float, JevPreflightQuestionKey] | None = None
        for preset in presets:
            definition = JevPresets.definition(preset)
            preset_answers = {key: cls._answer(answers, key) for key in definition.question_keys}
            yes = {key: answer.probabilities[JEV_NOUL_TRUE] for key, answer in preset_answers.items()}
            score = math.fsum(yes.values()) / len(yes)
            results[preset] = JevPresetResult(score=score, answers=preset_answers)
            if score < definition.threshold:
                candidate = min((probability, key) for key, probability in yes.items())
                weakest = candidate if weakest is None else min(weakest, candidate)
        return results, None if weakest is None else cls.get(weakest[1]).clarification

    @staticmethod
    def _answer(answers: Mapping[str, JevAnswer], key: JevPreflightQuestionKey) -> JevAnswer:
        # Returns the noul answer Jev gave for one question key, rejecting a missing or mistyped answer.
        found = answers.get(key.value)
        if found is None or found.question_type is not JevQuestionType.NOUL:
            raise ConfigurationError(f"Jev returned no noul answer for preflight question {key.value!r}.", details={"key": key.value, "answered": sorted(answers)})
        return found

    @staticmethod
    def _usage(response: DecisionModelResponse) -> ProviderUsage | None:
        # Parses the decision call's usage with the provider's own usage class (JevUsage for TypeSafe).
        usage_class = response.provider.usage_class()
        if usage_class is None or not response.usage:
            return None
        return usage_class.from_usage_payload(response.usage)


__all__ = ["JevPreflight"]
