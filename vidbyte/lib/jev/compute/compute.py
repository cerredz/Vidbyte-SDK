"""FILE: vidbyte/lib/jev/compute/compute.py

PURPOSE: Defines JevComputeRegistry, the registry over every fixed compute sign question, keyed by JevComputeQuestionKey, with the lookup and validation JevComputeSettings and the recognizer use.
ROLE IN CODEBASE: JevComputeSettings validates its enabled situations here at construction; the recognizer asks `questions(situation)` for the Jev questions of each situation it checks.
ARCHITECTURE NOTE: Mirrors JevPreflightRegistry: question content and lookup live here in vidbyte/lib, while the logic that asks Jev and acts on its answers stays in vidbyte/agents/jev/compute/.
COMMON MODIFICATION PATTERNS: Register a new situation's question tuple in `_questions`; `validate` then checks that every key the situation's definition lists has a registered question.
KNOWN EDGE CASES: `validate` returns situations in priority order with duplicates removed, whatever order the caller gave, and accepts an empty tuple, which keeps the brief but asks Jev nothing.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.dataclasses.jev import JevComputeQuestion, JevQuestion
from vidbyte.lib.enums.jev import JevComputeQuestionKey, JevComputeSituation
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.compute.each_of_several import EACH_OF_SEVERAL_QUESTIONS
from vidbyte.lib.jev.compute.repeating import REPEATING_QUESTIONS
from vidbyte.lib.jev.compute.self_contained_step import SELF_CONTAINED_STEP_QUESTIONS
from vidbyte.lib.jev.compute.situations import JevComputeSituations


class JevComputeRegistry:
    """Registry over every fixed compute sign question, keyed by JevComputeQuestionKey."""

    _questions: Mapping[JevComputeQuestionKey, JevComputeQuestion] = MappingProxyType(
        {question.key: question for question in (*REPEATING_QUESTIONS, *EACH_OF_SEVERAL_QUESTIONS, *SELF_CONTAINED_STEP_QUESTIONS)}
    )

    @classmethod
    def get(cls, key: JevComputeQuestionKey) -> JevComputeQuestion:
        """Return the registered question for a key, or raise when none is registered."""
        found = cls._questions.get(key)
        if found is None:
            raise ConfigurationError(f"Jev compute question {key.value!r} has no registered dataclass.", details={"key": key.value, "registered": [item.value for item in cls._questions]})
        return found

    @classmethod
    def questions(cls, situation: JevComputeSituation) -> tuple[JevQuestion, ...]:
        """Return one situation's sign questions as Jev questions, in the order its definition lists them."""
        return tuple(cls.get(key).to_question() for key in JevComputeSituations.definition(situation).question_keys)

    @classmethod
    def validate(cls, situations: Iterable[object]) -> tuple[JevComputeSituation, ...]:
        """Normalize enabled situations into priority order and confirm every question they ask is registered."""
        # @intent compute-is-complete-before-the-agent-exists
        # JevComputeSettings calls this at construction, so an unknown situation or one whose questions are not all
        # registered fails when the agent is built, rather than recognizing nothing, unnoticed, on every run.
        if isinstance(situations, (str, bytes)):
            raise ConfigurationError("Jev compute situations must be an iterable of situations, not a string.")
        requested: set[JevComputeSituation] = set()
        for value in situations:
            try:
                requested.add(value if isinstance(value, JevComputeSituation) else JevComputeSituation(value))
            except ValueError as exc:
                raise ConfigurationError(f"Unknown Jev compute situation: {value!r}.", details={"received": repr(value), "known": [item.value for item in JevComputeSituation]}) from exc
        ordered = tuple(situation for situation in JevComputeSituations.all() if situation in requested)
        for situation in ordered:
            cls.questions(situation)
        return ordered


__all__ = ["JevComputeRegistry"]
