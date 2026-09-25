"""FILE: vidbyte/lib/jev/preflight/registry.py

PURPOSE: Registers every fixed JevAgent preflight question and owns looking them up, validating them, combining them into one request, and running that request.
ROLE IN CODEBASE: JevPreflightSecurity in `vidbyte/agents/jev/preflight.py` calls JevPreflightRegistry.run for the SECURITY preset; tests call validate to pin the question shape.
ARCHITECTURE NOTE: Question text lives in the per-preset modules beside this file; the registry is the only place that turns them into wire questions, so every preset shares one naming rule and one batched request.
COMMON MODIFICATION PATTERNS: Register a new preset's question tuple in _QUESTIONS; keep result mapping and actions in the agents-layer preflight class that consumes the answers.
KNOWN EDGE CASES: TOOL_SELECTOR builds its questions from the caller's tools at run time, so it has no fixed entry here; get raises for an unregistered key.
RELATED DOCS: docs/design/jev-preflight-sensitive-data.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_sensitive_preflight.py.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType

from vidbyte.lib.constants.jev import (
    JEV_NOUL_FALSE,
    JEV_NOUL_TRUE,
    JEV_PREFLIGHT_MAX_SENTENCES,
    JEV_PREFLIGHT_MIN_SENTENCES,
    JEV_PREFLIGHT_STATE_REQUEST_FIELD,
)
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevOption,
    JevPreflightQuestion,
    JevQuestion,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums.jev import (
    JevPreflightPreset,
    JevQuestionType,
    JevSecurityCategory,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.preflight.security import SECURITY_QUESTIONS
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class JevPreflightRegistry:
    """Read-only registry over the fixed questions of every JevAgent preflight preset."""

    _QUESTIONS: Mapping[JevPreflightPreset, tuple[JevPreflightQuestion, ...]] = MappingProxyType(
        {JevPreflightPreset.SECURITY: SECURITY_QUESTIONS}
    )

    @classmethod
    def questions(cls, preset: JevPreflightPreset) -> tuple[JevPreflightQuestion, ...]:
        """Return a preset's questions in declaration order, which is also the response flag order."""
        found = cls._QUESTIONS.get(preset)
        if found is None:
            raise ConfigurationError(f"Jev preflight preset {preset!r} has no fixed questions.", details={"registered": sorted(cls._QUESTIONS)})
        return found

    @classmethod
    def get(cls, key: str) -> JevPreflightQuestion:
        """Return the registered question for one key, such as JevSecurityCategory.HEALTH."""
        for questions in cls._QUESTIONS.values():
            for question in questions:
                if question.key == key:
                    return question
        raise ConfigurationError(f"No Jev preflight question is registered for key {key!r}.")

    @classmethod
    def validate(cls) -> None:
        """Raise ConfigurationError unless every registered question is unique, complete, and four to five sentences."""
        keys = [question.key for questions in cls._QUESTIONS.values() for question in questions]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ConfigurationError("Jev preflight question keys must be unique across presets.", details={"duplicates": duplicates})
        security_keys = {question.key for question in cls.questions(JevPreflightPreset.SECURITY)}
        missing = sorted(set(JevSecurityCategory) - security_keys)
        if missing:
            raise ConfigurationError("Every JevSecurityCategory needs exactly one security question.", details={"missing": missing})
        for questions in cls._QUESTIONS.values():
            for question in questions:
                sentences = len(_SENTENCE_BOUNDARY.split(question.instructions.strip()))
                if not JEV_PREFLIGHT_MIN_SENTENCES <= sentences <= JEV_PREFLIGHT_MAX_SENTENCES:
                    raise ConfigurationError(
                        f"Jev preflight question {question.key!r} has {sentences} sentences; write {JEV_PREFLIGHT_MIN_SENTENCES} to {JEV_PREFLIGHT_MAX_SENTENCES}.",
                        details={"key": question.key, "sentences": sentences},
                    )

    @classmethod
    def combine(cls, preset: JevPreflightPreset, questions: tuple[JevPreflightQuestion, ...]) -> tuple[JevQuestion, ...]:
        """Build one noul wire question per preflight question, named `<preset>.<key>`, with structured criteria."""
        return tuple(
            JevQuestion(
                name=cls.wire_name(preset, question.key),
                question_type=JevQuestionType.NOUL,
                instructions=question.instructions,
                options=(
                    JevOption(name=JEV_NOUL_TRUE, description={"what": question.true_what, "examples": question.true_examples}),
                    JevOption(name=JEV_NOUL_FALSE, description={"what": question.false_what, "examples": question.false_examples}),
                ),
            )
            for question in questions
        )

    @staticmethod
    def wire_name(preset: JevPreflightPreset, key: str) -> str:
        """Return the answer key TypeSafe uses for one preflight question."""
        return f"{preset.value}.{key}"

    @classmethod
    async def run(cls, preset: JevPreflightPreset, message: str, decision: DecisionModelConfig) -> DecisionModelResponse:
        """Ask every question of one preset about the request text in a single batched Jev call."""
        request = JevDecisionRequest(
            state={JEV_PREFLIGHT_STATE_REQUEST_FIELD: message},
            questions=cls.combine(preset, cls.questions(preset)),
        )
        return await DecisionModelRunner(decision).arun(request)


__all__ = ["JevPreflightRegistry"]
