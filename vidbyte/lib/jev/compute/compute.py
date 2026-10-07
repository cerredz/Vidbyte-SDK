"""FILE: vidbyte/lib/jev/compute/compute.py

PURPOSE: Defines JevComputeRegistry, the registry mapping each dynamic-compute option to its ordered evidence questions and validating enabled options.
ROLE IN CODEBASE: JevComputeSettings validates its enabled options here at construction; the recognizer asks `questions(options)` for one combined Jev request.
ARCHITECTURE NOTE: Mirrors JevPreflightRegistry: question content and lookup live here in vidbyte/lib, while the logic that asks Jev and acts on its answers stays in vidbyte/agents/jev/compute/.
COMMON MODIFICATION PATTERNS: Register each option's ordered question tuple in `_questions`; `validate` normalizes options into enum order and removes duplicates.
KNOWN EDGE CASES: An empty option tuple keeps the brief and asks Jev nothing.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.dataclasses.jev import JevComputeQuestion, JevQuestion
from vidbyte.lib.enums.jev import JevComputeQuestionKey, JevDynamicComputeOption
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.compute.situations import (
    CLONE_QUESTIONS,
    FORK_AGENT_QUESTIONS,
    FRESH_AGENT_QUESTIONS,
    SUBAGENT_QUESTIONS,
)


class JevComputeRegistry:
    """Registry mapping each dynamic-compute option to its ordered evidence questions."""

    _questions: Mapping[JevDynamicComputeOption, tuple[JevComputeQuestion, ...]] = MappingProxyType(
        {
            JevDynamicComputeOption.FRESH_AGENT: FRESH_AGENT_QUESTIONS,
            JevDynamicComputeOption.FORK_AGENT: FORK_AGENT_QUESTIONS,
            JevDynamicComputeOption.SUBAGENT: SUBAGENT_QUESTIONS,
            JevDynamicComputeOption.CLONE: CLONE_QUESTIONS,
        }
    )
    _questions_by_key: Mapping[JevComputeQuestionKey, JevComputeQuestion] = MappingProxyType(
        {question.key: question for questions in _questions.values() for question in questions}
    )

    @classmethod
    def get(cls, key: JevComputeQuestionKey) -> JevComputeQuestion:
        """Return the registered question for a key, or raise when none is registered."""
        found = cls._questions_by_key.get(key)
        if found is None:
            raise ConfigurationError(f"Jev compute question {key.value!r} has no registered record.", details={"key": key.value, "registered": [item.value for item in cls._questions_by_key]})
        return found

    @classmethod
    def question_keys(cls, option: JevDynamicComputeOption) -> tuple[JevComputeQuestionKey, ...]:
        """Return one option's question keys in the order its evidence is asked."""
        return tuple(question.key for question in cls._questions[option])

    @classmethod
    def questions(cls, options: Iterable[JevDynamicComputeOption]) -> tuple[JevQuestion, ...]:
        """Return all enabled options' questions in enum order for one shared Jev request."""
        return tuple(question.to_question() for option in options for question in cls._questions[option])

    @classmethod
    def validate(cls, options: Iterable[object]) -> tuple[JevDynamicComputeOption, ...]:
        """Normalize enabled dynamic-compute options into enum order and confirm they have questions."""
        # @intent compute-is-complete-before-the-agent-exists
        # JevComputeSettings calls this at construction, so invalid options fail before the agent is built.
        if isinstance(options, (str, bytes)):
            raise ConfigurationError("JevComputeSettings.dynamic_compute must be an iterable of options, not a string.")
        requested: set[JevDynamicComputeOption] = set()
        for value in options:
            try:
                requested.add(value if isinstance(value, JevDynamicComputeOption) else JevDynamicComputeOption(value))
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(f"Unknown Jev dynamic-compute option: {value!r}.", details={"received": repr(value), "known": [item.value for item in JevDynamicComputeOption]}) from exc
        ordered = tuple(option for option in JevDynamicComputeOption if option in requested)
        for option in ordered:
            if not cls._questions.get(option):
                raise ConfigurationError(f"Jev dynamic-compute option {option.value!r} has no registered questions.")
        return ordered


__all__ = ["JevComputeRegistry"]
