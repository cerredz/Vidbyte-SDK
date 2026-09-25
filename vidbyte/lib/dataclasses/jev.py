"""FILE: vidbyte/lib/dataclasses/jev.py

PURPOSE: Defines the validated records for TypeSafe Jev decisions (JSON content, options, questions, requests, normalized answers, wire bodies, model cards, and decision-log records) and for JevAgent preflight (the question base, preset definitions, preset results, and the run-local response).
ROLE IN CODEBASE: `vidbyte/providers/typesafe.py` builds TypeSafeWireRequest from JevDecisionRequest and JevAnswer values from responses, while `vidbyte/lib/runners/decision.py` passes the typed records through.
ARCHITECTURE NOTE: This module must not import model_configs because that would close an import cycle through ModalityDetector. Records own every shape rule in __post_init__; the provider, not these records, turns a wire record into the JSON body (lint S060 bars dict[str, Any] encoders here).
COMMON MODIFICATION PATTERNS: Mirror https://docs.typesafe.ai/api.md exactly: add a field together with its validation, its wire record, and its provider serialization; keep bounds in vidbyte/lib/constants/jev.py.
KNOWN EDGE CASES: State, instructions, and criteria may be a string or JSON structure; noul criteria are optional; score answers carry a probability-weighted `score` that can land between levels; noul answers carry no confidence. JevPreflightQuestion is deliberately not slotted because every concrete question subclass redeclares its fields with defaults.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, https://docs.typesafe.ai/api.md, and https://docs.typesafe.ai/primitives/advanced.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from vidbyte.lib.constants.jev import (
    JEV_MAX_CHOICE_OPTIONS,
    JEV_MAX_OPTION_NAME_CHARS,
    JEV_MAX_QUESTIONS,
    JEV_MAX_SCORE_LEVELS,
    JEV_MAX_STATE_CHARS,
    JEV_MIN_CHOICE_OPTIONS,
    JEV_MIN_SCORE_LEVELS,
    JEV_NOUL_FALSE,
    JEV_NOUL_OPTIONS,
    JEV_NOUL_TRUE,
    JEV_PROBABILITY_SUM_TOLERANCE,
)
from vidbyte.lib.enums.jev import (
    JevPreflightPreset,
    JevPreflightQuestionKey,
    JevQuestionType,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.pricing import ProviderUsage

# A frozen JSON value as TypeSafe accepts it: a string, or a read-only mapping / tuple of JSON values.
JevContent = str | Mapping[str, object] | tuple[object, ...]

_API_DOCS = "https://docs.typesafe.ai/api.md"


class JevValidation:
    """Builds the detailed ConfigurationError every Jev record raises: field, expectation, received value, and a fix."""

    @staticmethod
    def error(field_name: str, expected: str, received: object, *, hint: str | None = None) -> ConfigurationError:
        # Returns an error naming the field, what TypeSafe accepts, what arrived, and how to fix it.
        # @intent errors-say-exactly-what-went-wrong
        # A caller reading only the message must learn which field failed, the documented rule, and
        # the offending value, so every record funnels through this one formatter.
        shown = JevValidation.describe(received)
        message = f"Invalid Jev {field_name}: expected {expected}; received {shown}."
        if hint:
            message = f"{message} {hint}"
        return ConfigurationError(message, details={"field": field_name, "expected": expected, "received": shown, "docs": _API_DOCS})

    @staticmethod
    def describe(value: object) -> str:
        # Renders a value as its type plus a short repr so messages stay readable for large inputs.
        rendered = repr(value)
        if len(rendered) > 80:
            rendered = f"{rendered[:77]}..."
        return f"{type(value).__name__} {rendered}"


class JevJson:
    """Validates and freezes the JSON content TypeSafe accepts for state, instructions, and criteria."""

    @staticmethod
    def content(value: object, *, field_name: str) -> JevContent:
        # Returns a non-empty string, mapping, or sequence as frozen JSON; anything else raises.
        # @intent structured-content-is-first-class
        # TypeSafe documents state, instructions, and criteria as `string | object | array`, so a
        # string-only record would block structured state and structured rubrics the API supports.
        if isinstance(value, str):
            if not value.strip():
                raise JevValidation.error(field_name, "a non-blank string, JSON object, or JSON array", value)
            return value
        if isinstance(value, (Mapping, list, tuple)):
            if not value:
                raise JevValidation.error(field_name, "a non-empty JSON object or array", value, hint="Send the content as a string when there is no structure.")
            try:
                return cast(JevContent, JevJson.freeze(value, field_name=field_name))
            except RecursionError as exc:
                raise JevValidation.error(field_name, "JSON nested shallowly enough to encode", "structure deeper than Python's recursion limit") from exc
        raise JevValidation.error(field_name, "a string, JSON object (mapping), or JSON array (list/tuple)", value)

    @staticmethod
    def freeze(value: object, *, field_name: str) -> object:
        # Recursively validates one JSON value and returns it with mappings and lists made read-only.
        if value is None or isinstance(value, (bool, str, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise JevValidation.error(field_name, "a finite JSON number", value, hint="JSON has no NaN or infinity.")
            return value
        if isinstance(value, Mapping):
            frozen: dict[str, object] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise JevValidation.error(f"{field_name} key", "a string JSON object key", key)
                frozen[key] = JevJson.freeze(item, field_name=f"{field_name}[{key!r}]")
            return MappingProxyType(frozen)
        if isinstance(value, (list, tuple)):
            return tuple(JevJson.freeze(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value))
        raise JevValidation.error(field_name, "a JSON value (string, number, boolean, null, mapping, or list)", value)

    @staticmethod
    def thaw(value: object) -> object:
        # Returns the plain dict/list form of a frozen JSON value so it can be JSON-encoded.
        if isinstance(value, Mapping):
            return {key: JevJson.thaw(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [JevJson.thaw(item) for item in value]
        return value

    @staticmethod
    def char_length(value: JevContent) -> int:
        # Measures content as sent: the string itself, or the compact JSON encoding of a structure.
        if isinstance(value, str):
            return len(value)
        return len(json.dumps(JevJson.thaw(value), separators=(",", ":")))


class JevProbability:
    """Shared validation for probability values carried by Jev answers and records."""

    @staticmethod
    def require(value: object, *, field_name: str) -> float:
        # Returns value as a float in [0, 1], raising a detailed ConfigurationError for anything else.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise JevValidation.error(field_name, "a probability: a finite number between 0 and 1", value)
        return float(value)

    @staticmethod
    def frozen_distribution(probabilities: object, *, field_name: str) -> Mapping[str, float]:
        # Validates every probability and returns an immutable copy keyed by option name.
        if not isinstance(probabilities, Mapping) or not probabilities:
            raise JevValidation.error(field_name, "a non-empty mapping of option names to probabilities", probabilities)
        frozen: dict[str, float] = {}
        for name, value in probabilities.items():
            if not isinstance(name, str):
                raise JevValidation.error(f"{field_name} key", "an option name string", name)
            frozen[name] = JevProbability.require(value, field_name=f"{field_name}[{name!r}]")
        return MappingProxyType(frozen)

    @staticmethod
    def require_normalized(probabilities: Mapping[str, float], *, field_name: str) -> None:
        # Raises unless the distribution sums to 1 within the rounding tolerance TypeSafe's floats need.
        total = math.fsum(probabilities.values())
        if abs(total - 1.0) > JEV_PROBABILITY_SUM_TOLERANCE:
            raise JevValidation.error(field_name, f"probabilities that sum to 1 (within {JEV_PROBABILITY_SUM_TOLERANCE})", f"a sum of {total:.6f}")


@dataclass(frozen=True, slots=True)
class JevOption:
    """One Choice option, Score level, or Noul criterion, with an optional (possibly structured) description.

    For Choice the name is the criteria key and the description its rubric (null when omitted).
    For Score the name is the level label answers are keyed by, and the wire level is the
    description when given, else the name. For Noul the name must be `true` or `false`.
    """

    name: str
    description: JevContent | None = None

    def __post_init__(self) -> None:
        # Rejects blank or oversized names and freezes a string or structured description.
        if not isinstance(self.name, str) or not self.name.strip():
            raise JevValidation.error("option name", "a non-blank string", self.name)
        if len(self.name) > JEV_MAX_OPTION_NAME_CHARS:
            raise JevValidation.error("option name", f"at most {JEV_MAX_OPTION_NAME_CHARS} characters", f"{len(self.name)} characters")
        if self.description is not None:
            object.__setattr__(self, "description", JevJson.content(self.description, field_name=f"description of option {self.name!r}"))


@dataclass(frozen=True, slots=True)
class JevQuestion:
    """One named question Jev answers against the request state.

    The name is the key answers come back under; TypeSafe never shows it to the model.
    """

    name: str
    question_type: JevQuestionType
    instructions: JevContent
    options: tuple[JevOption, ...] = ()

    def __post_init__(self) -> None:
        # Enforces the per-type criteria contract of POST /v1/systemone.
        if not isinstance(self.name, str) or not self.name.strip():
            raise JevValidation.error("question name", "a non-blank string", self.name)
        if not isinstance(self.question_type, JevQuestionType):
            raise JevValidation.error(f"question_type of {self.name!r}", f"a JevQuestionType member ({', '.join(JevQuestionType.values())})", self.question_type, hint="Pass JevQuestionType(value) to convert a string.")
        object.__setattr__(self, "instructions", JevJson.content(self.instructions, field_name=f"instructions of question {self.name!r}"))
        if not isinstance(self.options, tuple) or not all(isinstance(option, JevOption) for option in self.options):
            raise JevValidation.error(f"options of question {self.name!r}", "a tuple of JevOption values", self.options)
        self._validate_option_set()

    def _validate_option_set(self) -> None:
        # Checks uniqueness, then the documented option count or noul key set for this question type.
        names = self.option_names()
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise JevValidation.error(f"options of question {self.name!r}", "unique option names", f"duplicates {duplicates}")
        if self.question_type is JevQuestionType.NOUL:
            unknown = [name for name in names if name not in JEV_NOUL_OPTIONS]
            if unknown:
                raise JevValidation.error(f"criteria of noul question {self.name!r}", f"only the optional keys {JEV_NOUL_OPTIONS}", f"unknown keys {unknown}", hint="Omit options entirely to send no criteria.")
            return
        low, high, noun = (JEV_MIN_SCORE_LEVELS, JEV_MAX_SCORE_LEVELS, "levels") if self.question_type is JevQuestionType.SCORE else (JEV_MIN_CHOICE_OPTIONS, JEV_MAX_CHOICE_OPTIONS, "options")
        if not low <= len(names) <= high:
            raise JevValidation.error(f"{noun} of {self.question_type.value} question {self.name!r}", f"between {low} and {high} {noun}", f"{len(names)} {noun}")

    def option_names(self) -> tuple[str, ...]:
        # Returns declared option names in order, which is the low-to-high level order for score questions.
        return tuple(option.name for option in self.options)

    def outcome_names(self) -> tuple[str, ...]:
        # Returns the labels an answer's probabilities are keyed by: true/false for noul, else the option names.
        return JEV_NOUL_OPTIONS if self.question_type is JevQuestionType.NOUL else self.option_names()


@dataclass(frozen=True, slots=True)
class JevDecisionRequest:
    """One System One request: a string or structured state and the named questions answered against it."""

    state: JevContent
    questions: tuple[JevQuestion, ...]

    def __post_init__(self) -> None:
        # Freezes and bounds the state and requires at least one uniquely named question.
        state = JevJson.content(self.state, field_name="state")
        object.__setattr__(self, "state", state)
        length = JevJson.char_length(state)
        if length > JEV_MAX_STATE_CHARS:
            raise JevValidation.error("state", f"at most {JEV_MAX_STATE_CHARS} characters (TypeSafe's own limit is 32k tokens for the state plus the longest question)", f"{length} characters")
        if not isinstance(self.questions, tuple) or not all(isinstance(question, JevQuestion) for question in self.questions):
            raise JevValidation.error("questions", "a tuple of JevQuestion values", self.questions)
        if not 1 <= len(self.questions) <= JEV_MAX_QUESTIONS:
            raise JevValidation.error("questions", f"between 1 and {JEV_MAX_QUESTIONS} questions", f"{len(self.questions)} questions")
        names = [question.name for question in self.questions]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise JevValidation.error("questions", "unique question names (answers are keyed by name)", f"duplicates {duplicates}")


@dataclass(frozen=True, slots=True)
class JevAnswer:
    """Jev's normalized answer to one question.

    `choice` is the highest-probability label: the API's `choice` for Choice, the most likely level
    for Score, and `true` when P(yes) >= 0.5 for Noul. `confidence` is TypeSafe's own value and is
    None for Noul, which the API documents as carrying none. `score` is the probability-weighted
    level index (Score only) and `noul` the raw P(yes) (Noul only).
    """

    question_name: str
    question_type: JevQuestionType
    choice: str
    probabilities: Mapping[str, float]
    confidence: float | None = None
    score: float | None = None
    noul: float | None = None

    def __post_init__(self) -> None:
        # Freezes the distribution, checks it sums to 1, and enforces which fields each answer type carries.
        field_name = f"answer to {self.question_name!r}"
        probabilities = JevProbability.frozen_distribution(self.probabilities, field_name=f"probabilities of {field_name}")
        JevProbability.require_normalized(probabilities, field_name=f"probabilities of {field_name}")
        object.__setattr__(self, "probabilities", probabilities)
        if self.choice not in probabilities:
            raise JevValidation.error(f"choice of {field_name}", f"one of its probability keys {sorted(probabilities)}", self.choice)
        if self.question_type is JevQuestionType.NOUL:
            self._require_noul_fields(field_name)
            return
        if self.noul is not None:
            raise JevValidation.error(f"noul of {field_name}", "None for a non-noul answer", self.noul)
        object.__setattr__(self, "confidence", JevProbability.require(self.confidence, field_name=f"confidence of {field_name}"))
        if self.question_type is JevQuestionType.SCORE:
            self._require_score(field_name, len(probabilities))
        elif self.score is not None:
            raise JevValidation.error(f"score of {field_name}", "None for a choice answer", self.score)

    def _require_noul_fields(self, field_name: str) -> None:
        # Requires the raw P(yes) and rejects the confidence and score fields a noul answer never has.
        object.__setattr__(self, "noul", JevProbability.require(self.noul, field_name=f"noul of {field_name}"))
        if self.confidence is not None or self.score is not None:
            raise JevValidation.error(f"confidence/score of {field_name}", "None: TypeSafe returns neither for noul answers", (self.confidence, self.score))
        if set(self.probabilities) != set(JEV_NOUL_OPTIONS):
            raise JevValidation.error(f"probabilities of {field_name}", f"exactly the keys {JEV_NOUL_OPTIONS}", sorted(self.probabilities))

    def _require_score(self, field_name: str, levels: int) -> None:
        # Requires a finite weighted score inside the level index range [0, levels - 1].
        value = self.score
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= levels - 1:
            raise JevValidation.error(f"score of {field_name}", f"a number between 0 and {levels - 1} (the level index range)", value)
        object.__setattr__(self, "score", float(value))

    def ranked(self) -> tuple[tuple[str, float], ...]:
        # Returns (option, probability) pairs from most to least likely, ties kept in option order.
        return tuple(sorted(self.probabilities.items(), key=lambda item: -item[1]))


@dataclass(frozen=True, slots=True)
class TypeSafeWireQuestion:
    """One entry of the request `questions` map, field for field as POST /v1/systemone defines it.

    `criteria` is a frozen JSON value: a mapping for Choice and Noul, a tuple of levels for Score,
    or None when a Noul question sends no criteria.
    """

    type: str
    instructions: JevContent
    criteria: JevContent | None = None

    def __post_init__(self) -> None:
        # Rejects an unknown type string; instructions and criteria were validated on JevQuestion.
        if self.type not in JevQuestionType.values():
            raise JevValidation.error("wire question type", f"one of {JevQuestionType.values()}", self.type)


@dataclass(frozen=True, slots=True)
class TypeSafeWireRequest:
    """The POST /v1/systemone request body, field for field."""

    model: str
    state: JevContent
    questions: Mapping[str, TypeSafeWireQuestion]

    def __post_init__(self) -> None:
        # Freezes the question map so the body cannot change between building and sending it.
        if not isinstance(self.model, str) or not self.model.strip():
            raise JevValidation.error("wire model", "a non-blank model name", self.model)
        if not self.questions or not all(isinstance(question, TypeSafeWireQuestion) for question in self.questions.values()):
            raise JevValidation.error("wire questions", "a non-empty mapping of TypeSafeWireQuestion values", self.questions)
        object.__setattr__(self, "questions", MappingProxyType(dict(self.questions)))


@dataclass(frozen=True, slots=True)
class JevModelCard:
    """One entry of GET /v1/models: a model ID or alias accepted by the request `model` field."""

    name: str
    description: str
    release_date: str

    def __post_init__(self) -> None:
        # Requires every documented field to be a string and the name to be usable as a model value.
        if not isinstance(self.name, str) or not self.name.strip():
            raise JevValidation.error("model card name", "a non-blank string", self.name)
        for field_name in ("description", "release_date"):
            if not isinstance(getattr(self, field_name), str):
                raise JevValidation.error(f"model card {field_name}", "a string", getattr(self, field_name))


@dataclass(frozen=True, slots=True)
class JevDecisionRecord:
    """Decision-log entry carrying a state hash rather than the raw classified state."""

    question: str
    answer_type: JevQuestionType
    options: tuple[str, ...]
    choice: str
    probabilities: Mapping[str, float]
    confidence: float | None
    min_confidence: float | None
    passed_threshold: bool
    model: str
    state_sha256: str
    latency_ms: float
    score: float | None = None
    noul: float | None = None

    def __post_init__(self) -> None:
        # Freezes the distribution so a logged record cannot be edited after the fact.
        object.__setattr__(self, "probabilities", JevProbability.frozen_distribution(self.probabilities, field_name=f"probabilities of record {self.question!r}"))
        for field_name in ("confidence", "min_confidence"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, JevProbability.require(value, field_name=f"{field_name} of record {self.question!r}"))


@dataclass(frozen=True)
class JevPreflightQuestion:
    """One fixed preflight yes/no question: what Jev reads, what each answer means, and what to ask the user when it fails.

    Every concrete question in `vidbyte/lib/jev/preflight/` subclasses this with a default for every
    field, so each question is its own dataclass constructed with no arguments. `instructions` is the
    whole brief Jev reads (definition, boundary, focus, then the question); `when_true` and
    `when_false` are the noul criteria; `clarification` is what the agent asks the user when this is
    the weakest answer of a failing preset.
    """

    key: JevPreflightQuestionKey
    instructions: str
    when_true: str
    when_false: str
    clarification: str

    def __post_init__(self) -> None:
        # Requires a registered key and non-blank text for every part of the question.
        if not isinstance(self.key, JevPreflightQuestionKey):
            raise JevValidation.error("preflight question key", "a JevPreflightQuestionKey member", self.key)
        for field_name in ("instructions", "when_true", "when_false", "clarification"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise JevValidation.error(f"{field_name} of preflight question {self.key.value!r}", "a non-blank string", value)

    def to_question(self) -> JevQuestion:
        # Builds the noul JevQuestion sent to Jev, named by the key so its answer comes back under it.
        return JevQuestion(
            name=self.key.value,
            question_type=JevQuestionType.NOUL,
            instructions=self.instructions,
            options=(JevOption(name=JEV_NOUL_TRUE, description=self.when_true), JevOption(name=JEV_NOUL_FALSE, description=self.when_false)),
        )


@dataclass(frozen=True, slots=True)
class JevPresetDefinition:
    """The fixed policy one preflight flag turns on: which questions it asks and the score it must reach."""

    preset: JevPreflightPreset
    question_keys: tuple[JevPreflightQuestionKey, ...]
    threshold: float

    def __post_init__(self) -> None:
        # Requires a registered preset, a non-empty tuple of unique keys, and a probability threshold.
        if not isinstance(self.preset, JevPreflightPreset):
            raise JevValidation.error("preset definition preset", "a JevPreflightPreset member", self.preset)
        keys = self.question_keys
        if not isinstance(keys, tuple) or not keys or not all(isinstance(key, JevPreflightQuestionKey) for key in keys):
            raise JevValidation.error(f"question_keys of preset {self.preset.value!r}", "a non-empty tuple of JevPreflightQuestionKey members", keys)
        if len(set(keys)) != len(keys):
            raise JevValidation.error(f"question_keys of preset {self.preset.value!r}", "unique question keys", keys)
        object.__setattr__(self, "threshold", JevProbability.require(self.threshold, field_name=f"threshold of preset {self.preset.value!r}"))


@dataclass(frozen=True, slots=True)
class JevPresetResult:
    """The score and answer evidence one enabled preflight preset produced.

    `score` is the mean P(yes) of the preset's questions, or None with `available=False` when Jev
    could not be asked and the run failed open.
    """

    score: float | None
    answers: Mapping[JevPreflightQuestionKey, JevAnswer] = field(default_factory=dict)
    available: bool = True

    def __post_init__(self) -> None:
        # Validates the score and freezes the answer evidence so a recorded result cannot be edited.
        if self.score is not None:
            object.__setattr__(self, "score", JevProbability.require(self.score, field_name="preset result score"))
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))


@dataclass(slots=True)
class JevResponse:
    """Run-local Jev state for one JevAgent run, returned under the agent result's `jev_response` metadata key.

    `results` holds one entry per enabled preset, and `usage` is the one preflight Jev call's usage.
    """

    input: str
    output: str | None = None
    results: dict[JevPreflightPreset, JevPresetResult] = field(default_factory=dict)
    needs_clarification: bool = False
    usage: ProviderUsage | None = None


__all__ = [
    "JevAnswer",
    "JevContent",
    "JevDecisionRecord",
    "JevDecisionRequest",
    "JevJson",
    "JevModelCard",
    "JevOption",
    "JevPreflightQuestion",
    "JevPresetDefinition",
    "JevPresetResult",
    "JevProbability",
    "JevQuestion",
    "JevResponse",
    "JevValidation",
    "TypeSafeWireQuestion",
    "TypeSafeWireRequest",
]
