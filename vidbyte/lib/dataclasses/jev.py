"""FILE: vidbyte/lib/dataclasses/jev.py

PURPOSE: Defines the validated, immutable records for TypeSafe Jev decisions: options, questions, requests, normalized answers, and decision-log records.
ROLE IN CODEBASE: `vidbyte/providers/typesafe.py` serializes JevDecisionRequest and builds JevAnswer values, while `vidbyte/lib/runners/decision.py` passes the typed records through.
ARCHITECTURE NOTE: This module must not import model_configs because that would close an import cycle through ModalityDetector. Records own every shape rule in __post_init__; the provider, not these records, builds the wire dict (lint S060 bars dict[str, Any] encoders here).
COMMON MODIFICATION PATTERNS: Add a field together with its validation and its provider serialization; keep bounds in vidbyte/lib/constants/jev.py.
KNOWN EDGE CASES: noul questions must name exactly the true/false options; score options are ordered levels, so their order is part of the contract; probabilities are frozen mappings.
RELATED DOCS: docs/design/jev-agent-scaffold.md and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from vidbyte.lib.constants.jev import (
    JEV_MAX_OPTION_NAME_CHARS,
    JEV_MAX_OPTIONS,
    JEV_MAX_QUESTIONS,
    JEV_MAX_STATE_CHARS,
    JEV_MIN_OPTIONS,
    JEV_NOUL_OPTIONS,
)
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.errors import ConfigurationError


class JevProbability:
    """Shared validation for probability values carried by Jev answers and records."""

    @staticmethod
    def require(value: object, *, field_name: str) -> float:
        # Returns value as a float in [0, 1], raising ConfigurationError for anything else.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ConfigurationError(f"{field_name} must be a probability between 0 and 1.")
        return float(value)

    @staticmethod
    def frozen_distribution(probabilities: Mapping[str, float], *, field_name: str) -> Mapping[str, float]:
        # Validates every probability and returns an immutable copy keyed by option name.
        if not isinstance(probabilities, Mapping) or not probabilities:
            raise ConfigurationError(f"{field_name} must be a non-empty mapping of option names to probabilities.")
        return MappingProxyType({str(name): JevProbability.require(value, field_name=f"{field_name}[{name!r}]") for name, value in probabilities.items()})


@dataclass(frozen=True, slots=True)
class JevOption:
    """One allowed outcome of a Jev question, with an optional criterion describing it."""

    name: str
    description: str | None = None

    def __post_init__(self) -> None:
        # Rejects blank or oversized option names and non-string descriptions.
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigurationError("Jev option names must be non-empty strings.")
        if len(self.name) > JEV_MAX_OPTION_NAME_CHARS:
            raise ConfigurationError(f"Jev option names must be at most {JEV_MAX_OPTION_NAME_CHARS} characters.")
        if self.description is not None and not isinstance(self.description, str):
            raise ConfigurationError("Jev option descriptions must be strings when provided.")


@dataclass(frozen=True, slots=True)
class JevQuestion:
    """One named question Jev answers against the request state."""

    name: str
    question_type: JevQuestionType
    instructions: str
    options: tuple[JevOption, ...]

    def __post_init__(self) -> None:
        # Enforces the per-type option contract TypeSafe's System One endpoint accepts.
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigurationError("Jev question names must be non-empty strings.")
        if not isinstance(self.question_type, JevQuestionType):
            raise ConfigurationError(f"question_type must be one of {JevQuestionType.values()}.")
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ConfigurationError("Jev question instructions must be a non-empty string.")
        if not isinstance(self.options, tuple) or not all(isinstance(option, JevOption) for option in self.options):
            raise ConfigurationError("Jev question options must be a tuple of JevOption values.")
        self._validate_option_set()

    def _validate_option_set(self) -> None:
        # Checks option count, uniqueness, and the fixed noul true/false pair.
        names = self.option_names()
        if len(set(names)) != len(names):
            raise ConfigurationError("Jev question option names must be unique.")
        if self.question_type is JevQuestionType.NOUL:
            if set(names) != set(JEV_NOUL_OPTIONS) or len(names) != len(JEV_NOUL_OPTIONS):
                raise ConfigurationError(f"noul questions take exactly the options {JEV_NOUL_OPTIONS}.")
            return
        if not JEV_MIN_OPTIONS <= len(names) <= JEV_MAX_OPTIONS:
            raise ConfigurationError(f"{self.question_type.value} questions take between {JEV_MIN_OPTIONS} and {JEV_MAX_OPTIONS} options; received {len(names)}.")

    def option_names(self) -> tuple[str, ...]:
        # Returns option names in declaration order, which is the level order for score questions.
        return tuple(option.name for option in self.options)


@dataclass(frozen=True, slots=True)
class JevDecisionRequest:
    """One System One request: a state and the named questions answered against it."""

    state: str
    questions: tuple[JevQuestion, ...]

    def __post_init__(self) -> None:
        # Bounds the state and requires at least one uniquely named question.
        if not isinstance(self.state, str) or not self.state.strip():
            raise ConfigurationError("Jev state must be a non-empty string.")
        if len(self.state) > JEV_MAX_STATE_CHARS:
            raise ConfigurationError(f"Jev state must be at most {JEV_MAX_STATE_CHARS} characters; received {len(self.state)}.")
        if not isinstance(self.questions, tuple) or not all(isinstance(question, JevQuestion) for question in self.questions):
            raise ConfigurationError("Jev questions must be a tuple of JevQuestion values.")
        if not 1 <= len(self.questions) <= JEV_MAX_QUESTIONS:
            raise ConfigurationError(f"A Jev request takes between 1 and {JEV_MAX_QUESTIONS} questions; received {len(self.questions)}.")
        names = [question.name for question in self.questions]
        if len(set(names)) != len(names):
            raise ConfigurationError("Jev question names must be unique within one request.")


@dataclass(frozen=True, slots=True)
class JevAnswer:
    """Jev's normalized answer to one question: the chosen option and a probability per option."""

    question_name: str
    question_type: JevQuestionType
    choice: str
    probabilities: Mapping[str, float]
    confidence: float

    def __post_init__(self) -> None:
        # Freezes the distribution and requires the chosen label to be one of its options.
        object.__setattr__(self, "probabilities", JevProbability.frozen_distribution(self.probabilities, field_name="probabilities"))
        object.__setattr__(self, "confidence", JevProbability.require(self.confidence, field_name="confidence"))
        if self.choice not in self.probabilities:
            raise ConfigurationError("A Jev answer's choice must be one of its probability keys.")

    def ranked(self) -> tuple[tuple[str, float], ...]:
        # Returns (option, probability) pairs from most to least likely, ties kept in option order.
        return tuple(sorted(self.probabilities.items(), key=lambda item: -item[1]))


@dataclass(frozen=True, slots=True)
class JevDecisionRecord:
    """Decision-log entry carrying a state hash rather than the raw classified state."""

    question: str
    answer_type: JevQuestionType
    options: tuple[str, ...]
    choice: str
    probabilities: Mapping[str, float]
    confidence: float
    min_confidence: float | None
    passed_threshold: bool
    model: str
    state_sha256: str
    latency_ms: float

    def __post_init__(self) -> None:
        # Freezes the distribution so a logged record cannot be edited after the fact.
        object.__setattr__(self, "probabilities", JevProbability.frozen_distribution(self.probabilities, field_name="probabilities"))


__all__ = [
    "JevAnswer",
    "JevDecisionRecord",
    "JevDecisionRequest",
    "JevOption",
    "JevProbability",
    "JevQuestion",
]
