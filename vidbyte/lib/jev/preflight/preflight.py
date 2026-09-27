"""FILE: vidbyte/lib/jev/preflight/preflight.py

PURPOSE: Defines JevPreflightRegistry, the registry over every fixed preflight question dataclass, plus validation that every flag a user enables can be asked.
ROLE IN CODEBASE: JevAgentSettings calls JevPreflightRegistry.validate at construction, and JevPreflightGate (vidbyte/agents/jev/gate/gate.py) reads questions from here when it combines one Jev request; the preflight logic itself lives in the agent layer.
ARCHITECTURE NOTE: Questions are dataclasses in this folder, flags and their policy live in vidbyte/lib/jev/presets.py, and records live in vidbyte/lib/dataclasses/jev.py; this lib module never imports the agents layer and never calls Jev.
COMMON MODIFICATION PATTERNS: Register a new preset's questions by adding its question tuple to _questions; keep scoring in DecisionModelRunner.score_noul and the actions taken on answers in JevPreflightGate, not here.
KNOWN EDGE CASES: A preset without fixed questions (TOOL_SELECTOR) contributes nothing here; its questions are built per run from the tool catalog.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.dataclasses.jev import JevPreflightQuestion, JevQuestion
from vidbyte.lib.enums.jev import JevPreflightPreset, JevPreflightQuestionKey
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.preflight.clarity import CLARITY_QUESTIONS
from vidbyte.lib.jev.presets import JevPresets


class JevPreflightRegistry:
    """Registry over every fixed preflight question, keyed by JevPreflightQuestionKey."""

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
    def questions(cls, preset: JevPreflightPreset) -> tuple[JevQuestion, ...]:
        """Return one fixed preset's questions as Jev questions, in the order the preset asks them."""
        return tuple(cls.get(key).to_question() for key in JevPresets.definition(preset).question_keys)

    @classmethod
    def validate(cls, presets: Iterable[object]) -> tuple[JevPreflightPreset, ...]:
        """Normalize the user's enabled flags and confirm every fixed question they ask is registered here."""
        # @intent preflight-is-complete-before-the-agent-exists
        # JevAgentSettings calls this at construction, so a flag whose questions are not all registered
        # fails when the agent is built rather than failing open, unnoticed, on every run.
        normalized = JevPresets.normalize(presets)
        for preset in normalized:
            if JevPresets.has_fixed_questions(preset):
                cls.questions(preset)
        return normalized


__all__ = ["JevPreflightRegistry"]
