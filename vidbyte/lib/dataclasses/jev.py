"""FILE: vidbyte/lib/dataclasses/jev.py

PURPOSE: Defines the validated records for TypeSafe Jev decisions, JevAgent preflight, JevAgent done checks, and JevAgentResponse, including request, claim, and dynamic problem-repair evidence shapes.
ROLE IN CODEBASE: `vidbyte/providers/typesafe.py` builds TypeSafeWireRequest from JevDecisionRequest and JevAnswer values from responses, while `vidbyte/lib/runners/decision.py` passes the typed records through.
ARCHITECTURE NOTE: This module must not import model_configs because that would close an import cycle through ModalityDetector. Records own every shape rule in __post_init__; problem handoff items require unique ids and exactly one reserved original-request completion item. The provider, not these records, turns a wire record into the JSON body (lint S060 bars dict[str, Any] encoders here).
COMMON MODIFICATION PATTERNS: Mirror https://docs.typesafe.ai/api.md exactly: add a field together with its validation, its wire record, and its provider serialization; keep bounds in vidbyte/lib/constants/jev.py. New done-check evidence records and their structured payloads belong beside the other Jev records; items derived from the finished answer need not be fields on JevRunStateRecord.
KNOWN EDGE CASES: State, instructions, and criteria may be a string or JSON structure; noul criteria are optional; score answers carry a probability-weighted `score` that can land between levels; noul answers carry no confidence. JevPreflightQuestion and JevDoneQuestion are deliberately not slotted because every concrete question subclass redeclares its fields with defaults. The clarification, run-state, and handoff payloads are pydantic models because they are the output_schema their generative agents are held to; every field's description is the instruction the model reads for that field, and each done-check section payload carries a SECTION description for the field JevRunState and JevHandoff add when that check is enabled. The records built from those replies hold validated fields only; converting a reply into a record belongs to the agent that asked for it.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, skills/jev-continuation/SKILL.md, https://docs.typesafe.ai/api.md, and https://docs.typesafe.ai/primitives/advanced.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from vidbyte.lib.constants.jev import (
    JEV_CLARIFICATION_MAX_QUESTIONS,
    JEV_CLARIFICATION_MAX_RECOMMENDATIONS,
    JEV_CLARIFICATION_MIN_RECOMMENDATIONS,
    JEV_DELIVERABLE_ID_PATTERN,
    JEV_DONE_CLAIM_ASSERTION_SEPARATOR,
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
    JEV_SPECIALIST_NONE,
)
from vidbyte.lib.enums.jev import (
    JevClaimKind,
    JevDoneCheck,
    JevDoneQuestionKey,
    JevOutputExtentComparator,
    JevOutputExtentUnit,
    JevPreflightPreset,
    JevPreflightQuestionKey,
    JevProblemCheckItemType,
    JevQuestionType,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.agents.pricing import ProviderUsage, UsageRollup

# A frozen JSON value as TypeSafe accepts it: a string, or a read-only mapping / tuple of JSON values.
JevContent = str | Mapping[str, object] | tuple[object, ...]

_API_DOCS = "https://docs.typesafe.ai/api.md"
_DELIVERABLE_ID = re.compile(JEV_DELIVERABLE_ID_PATTERN)


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


@dataclass(frozen=True, slots=True)
class JevNoulScore:
    """How a set of noul answers scored against one threshold: their mean P(yes), the verdict, and the answers used.

    DecisionModelHelper.score_noul builds this; `passed` is True when `score` is at or above the threshold
    and, when a veto is given, no single answer's P(yes) falls below the veto.
    """

    score: float
    passed: bool
    answers: Mapping[str, JevAnswer] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates the score and freezes the answers so a recorded verdict cannot be edited.
        object.__setattr__(self, "score", JevProbability.require(self.score, field_name="noul score"))
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))


class JevText:
    """Shared validation for the prose parts of a fixed Jev question."""

    @staticmethod
    def require(value: object, *, field_name: str) -> str:
        # Returns a non-blank string, raising a detailed ConfigurationError for anything else.
        if not isinstance(value, str) or not value.strip():
            raise JevValidation.error(field_name, "a non-blank string", value)
        return value

    @staticmethod
    def require_all(values: object, *, field_name: str) -> tuple[str, ...]:
        # Returns a non-empty tuple of non-blank strings, raising for any other shape.
        if not isinstance(values, tuple) or not values:
            raise JevValidation.error(field_name, "a non-empty tuple of strings", values)
        return tuple(JevText.require(value, field_name=f"{field_name}[{index}]") for index, value in enumerate(values))


@dataclass(frozen=True, slots=True)
class JevBrief:
    """The instructions of one fixed Jev question, one field per section, in the order Jev reads them.

    `introduction` says in general terms what the question answers; `state` says what each state
    field is and where it comes from; `definitions` define every term a rule uses, parts before the
    whole and without examples; `rules` hold every rule that decides the answer, including the focus;
    `question` is the one positively phrased yes/no question about a named state field.
    """

    introduction: str
    state: str
    definitions: tuple[str, ...]
    rules: tuple[str, ...]
    question: str

    def __post_init__(self) -> None:
        # Requires non-blank text in every section and at least one definition and one rule.
        for field_name in ("introduction", "state", "question"):
            JevText.require(getattr(self, field_name), field_name=f"brief {field_name}")
        JevText.require_all(self.definitions, field_name="brief definitions")
        JevText.require_all(self.rules, field_name="brief rules")

    def render(self) -> str:
        """Return the brief as the one instructions string Jev reads, sections separated by blank lines."""
        definitions = "\n".join(f"- {definition}" for definition in self.definitions)
        rules = "\n".join(f"- {rule}" for rule in self.rules)
        return f"{self.introduction}\n\n{self.state}\n\nDefinitions:\n{definitions}\n\nRules:\n{rules}\n\n{self.question}"


@dataclass(frozen=True, slots=True)
class JevCriterion:
    """One side of a noul question, in the structure of strategy 3: what it covers, what it is not for, and labeled examples.

    `what` opens with the verdict in the question's own defined term ("Choose true when `request`
    states an action.") and then lists the signs Jev can see. `not_for` names the cases that belong
    to the other side. `easy` examples are obvious cases and `boundary` examples sit next to the
    line; each example differs from its partner on the other side only in the tested property.
    """

    what: str
    not_for: str
    easy: tuple[str, ...]
    boundary: tuple[str, ...]

    def __post_init__(self) -> None:
        # Requires non-blank text and at least one easy and one boundary example.
        JevText.require(self.what, field_name="criterion what")
        JevText.require(self.not_for, field_name="criterion not_for")
        JevText.require_all(self.easy, field_name="criterion easy examples")
        JevText.require_all(self.boundary, field_name="criterion boundary examples")

    def to_content(self) -> Mapping[str, object]:
        """Return the structured criterion description TypeSafe accepts as an option description."""
        return {"what": self.what, "not_for": self.not_for, "examples": {"easy": list(self.easy), "boundary": list(self.boundary)}}


@dataclass(frozen=True)
class JevPreflightQuestion:
    """One fixed preflight yes/no question: what Jev reads, what each answer looks like, and the gap a no answer names.

    Every concrete question in `vidbyte/lib/jev/preflight/` subclasses this with a default for every
    field, so each question is its own dataclass constructed with no arguments. `instructions` holds
    every rule; `when_true` and `when_false` only describe what each side looks like and add no rule;
    `gap` is the self-contained sentence JevClarificationAgent reads when this question fails.
    """

    key: JevPreflightQuestionKey
    instructions: JevBrief
    when_true: JevCriterion
    when_false: JevCriterion
    gap: str

    def __post_init__(self) -> None:
        # Requires a registered key, a brief, two criteria, and non-blank gap text.
        if not isinstance(self.key, JevPreflightQuestionKey):
            raise JevValidation.error("preflight question key", "a JevPreflightQuestionKey member", self.key)
        if not isinstance(self.instructions, JevBrief):
            raise JevValidation.error(f"instructions of preflight question {self.key.value!r}", "a JevBrief", self.instructions)
        for field_name in ("when_true", "when_false"):
            if not isinstance(getattr(self, field_name), JevCriterion):
                raise JevValidation.error(f"{field_name} of preflight question {self.key.value!r}", "a JevCriterion", getattr(self, field_name))
        JevText.require(self.gap, field_name=f"gap of preflight question {self.key.value!r}")

    def to_question(self) -> JevQuestion:
        # Builds the noul JevQuestion sent to Jev, named by the key so its answer comes back under it.
        return JevQuestion(
            name=self.key.value,
            question_type=JevQuestionType.NOUL,
            instructions=self.instructions.render(),
            options=(JevOption(name=JEV_NOUL_TRUE, description=self.when_true.to_content()), JevOption(name=JEV_NOUL_FALSE, description=self.when_false.to_content())),
        )


@dataclass(frozen=True, slots=True)
class JevPresetDefinition:
    """The fixed policy one fixed-question preflight flag turns on: which questions it asks and the score it must reach.

    `threshold` is the mean P(yes) the questions must reach. `veto`, when set, fails the preset on its own
    whenever any one question's P(yes) falls below it. `gate`, when set, names the question every other
    question depends on; when it fails, only its gap is reported.
    """

    preset: JevPreflightPreset
    question_keys: tuple[JevPreflightQuestionKey, ...]
    threshold: float
    veto: float | None = None
    gate: JevPreflightQuestionKey | None = None

    def __post_init__(self) -> None:
        # Requires a registered preset, a non-empty tuple of unique keys, probability thresholds, and a gate among the keys.
        if not isinstance(self.preset, JevPreflightPreset):
            raise JevValidation.error("preset definition preset", "a JevPreflightPreset member", self.preset)
        keys = self.question_keys
        if not isinstance(keys, tuple) or not keys or not all(isinstance(key, JevPreflightQuestionKey) for key in keys):
            raise JevValidation.error(f"question_keys of preset {self.preset.value!r}", "a non-empty tuple of JevPreflightQuestionKey members", keys)
        if len(set(keys)) != len(keys):
            raise JevValidation.error(f"question_keys of preset {self.preset.value!r}", "unique question keys", keys)
        object.__setattr__(self, "threshold", JevProbability.require(self.threshold, field_name=f"threshold of preset {self.preset.value!r}"))
        if self.veto is not None:
            object.__setattr__(self, "veto", JevProbability.require(self.veto, field_name=f"veto of preset {self.preset.value!r}"))
        if self.gate is not None and self.gate not in keys:
            raise JevValidation.error(f"gate of preset {self.preset.value!r}", "one of the preset's question keys", self.gate)


@dataclass(frozen=True, slots=True)
class JevPresetResult:
    """The score and answer evidence one enabled fixed-question preset produced.

    `score` is the mean P(yes) of the preset's questions, and `passed` is False only when Jev answered
    and the score fell below the preset's threshold. With `available=False` Jev could not answer,
    `score` is None, and the preset fails open (`passed` stays True).
    """

    preset: JevPreflightPreset
    score: float | None
    passed: bool = True
    answers: Mapping[JevPreflightQuestionKey, JevAnswer] = field(default_factory=dict)
    available: bool = True

    def __post_init__(self) -> None:
        # Validates the score and freezes the answer evidence so a recorded result cannot be edited.
        if self.score is not None:
            object.__setattr__(self, "score", JevProbability.require(self.score, field_name="preset result score"))
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))

    def yes(self) -> dict[JevPreflightQuestionKey, float]:
        """Return each question's P(yes), in the order the preset asked them."""
        return {key: answer.probabilities[JEV_NOUL_TRUE] for key, answer in self.answers.items()}


@dataclass(frozen=True, slots=True)
class JevSpecialist:
    """One agent JevAgent can hand a run to: the title Jev chooses by, the scope Jev reads, and the agent that runs.

    `title` is the Choice option name, `description` is the scope Jev compares the request against, and
    `agent` is the BaseAgent whose own linear loop runs the whole task when Jev chooses this specialist.
    """

    title: str
    description: str
    agent: BaseAgent

    def __post_init__(self) -> None:
        # Validates the option name and scope, and checks the agent by the surface JevRuntime calls.
        # @intent lib-record-holds-an-agent-by-shape
        # vidbyte.lib may not import the agents layer (lint A006 counts function-local imports too), so the
        # agent is annotated under TYPE_CHECKING and validated by its runnable surface instead of isinstance.
        JevText.require(self.title, field_name="JevSpecialist.title")
        if self.title != self.title.strip() or len(self.title) > JEV_MAX_OPTION_NAME_CHARS:
            raise JevValidation.error("JevSpecialist.title", f"a trimmed string of at most {JEV_MAX_OPTION_NAME_CHARS} characters", self.title)
        if self.title == JEV_SPECIALIST_NONE:
            raise JevValidation.error("JevSpecialist.title", f"any title except the reserved way-out option {JEV_SPECIALIST_NONE!r}", self.title)
        JevText.require(self.description, field_name="JevSpecialist.description")
        if not callable(getattr(self.agent, "arun", None)):
            raise JevValidation.error("JevSpecialist.agent", "a BaseAgent (an object with an async arun method)", self.agent)


class JevClarifyingQuestionPayload(BaseModel):
    """One clarifying question as JevClarificationAgent must return it: the question and a few answers to pick from."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, description="One short question for the user about one missing detail of their request.")
    recommendations: list[str] = Field(
        min_length=JEV_CLARIFICATION_MIN_RECOMMENDATIONS,
        max_length=JEV_CLARIFICATION_MAX_RECOMMENDATIONS,
        description="Likely answers the user can pick from, each a complete answer to the question in the user's own terms.",
    )


class JevClarificationPayload(BaseModel):
    """The structured reply JevClarificationAgent must return: its clarifying questions, most important first."""

    model_config = ConfigDict(extra="forbid")

    questions: list[JevClarifyingQuestionPayload] = Field(
        min_length=1,
        max_length=JEV_CLARIFICATION_MAX_QUESTIONS,
        description="The clarifying questions for the user, most important missing detail first.",
    )


class JevSectionPayload(BaseModel):
    """One done check's section of a JevRunState or JevHandoff structured reply.

    SECTION is the description of the field that holds the section, so the model reads why the section
    exists before it reads the section's own field descriptions.
    """

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str]


class JevRunStatePayload(BaseModel):
    """The central structured state JevRunState writes once from the user's request, before the main agent starts.

    JevRunState adds one more field to this model for every enabled done check, typed as that check's
    section payload and described by its SECTION text, so the reply always holds these four fields plus
    exactly the sections the enabled done checks read.
    """

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, description="The goal is the broad result the user wants to exist once the work is over, stated in one or two sentences in the user's own terms. It describes the end state the user cares about, not the steps the agent will take to get there. Write it from the user's request alone and keep the user's own names for things, files, products, and people. Do not add ambitions, improvements, or follow-up work that the request does not ask for. When the request is a question, the goal is that the user has a correct and complete answer to it.")
    objective: str = Field(min_length=1, description="The objective is the concrete, checkable outcome of this one run, narrower than the goal: what the agent must hand back or change before it may stop. Name the artifact, change, or answer, and where it goes, whenever the request says so. It must be specific enough that a reader could look at the agent's final work and say whether the objective was met. Do not restate the goal in other words, and do not list the separate parts of the work here, since those belong to the done-check sections. When the request leaves a detail open, say that it is open rather than choosing a value for the user.")
    mission: str = Field(min_length=1, description="The mission is the agent's overall responsibility while it works on this request: the role it plays and the standard its work must meet. It describes how the agent should behave on the way to the objective, such as working only inside the named project, keeping existing behavior intact, or citing sources, whenever the request sets such a standard. Take the standard from the request itself and from what its words clearly imply about quality, not from general advice about good work. Write it as two to four sentences addressed to the agent. When the request sets no particular standard, say that the agent should do exactly what the request asks and nothing more.")
    what_not_to_do: list[str] = Field(description="What not to do lists every limit the request places on the work: things the user said to avoid, leave unchanged, or keep out of scope. Write each limit as its own short item in the user's terms, and keep only limits that the request states directly or that follow unavoidably from its words. Do not invent cautions, best practices, or safety rules the request does not state, since every item here is treated as a hard constraint. Include limits on scope, such as files, systems, or topics the work must not touch, as well as limits on form, such as length or tone. Return an empty list when the request places no limits on the work.")


class JevDeliverablePayload(BaseModel):
    """One separate output the request asks for, as JevRunState writes it in the multi-part section."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is a short, stable identifier for this deliverable, written in lowercase letters, digits, and underscores and starting with a letter. It must be unique among the deliverables of this request, and it names the deliverable by its subject rather than numbering it. Later steps refer to the deliverable only by this id, so it is copied exactly and never changed after it is written. Keep it under sixty-four characters and free of spaces, capital letters, and punctuation other than underscores.")
    description: str = Field(min_length=1, description="The description says what this one deliverable is, in one or two sentences that follow the user's own wording. It names the thing to be produced or changed and the part of the request it comes from, including any detail the request gives about it, such as a file, a format, a scope, or an audience. It describes only this deliverable, not the other parts of the request or the steps needed to produce it. Do not strengthen, weaken, or widen what the user asked for, and do not fill open details with your own choices. A reader who has not seen the request should understand from the description alone what the user expects to receive.")
    completion_signal: str = Field(min_length=1, description="The completion signal is the visible condition that shows this deliverable is done, written so that it can be checked by reading the agent's final work and the record of its run. It names what must be present, such as a changed file with a stated behavior, a passing test, a part of the answer that covers a stated topic, or a command that was run with its result. It must describe something observable in the work itself, never the agent's intentions, confidence, or claims that the work is finished. It covers the whole deliverable as the request describes it, so a partial result does not meet it, and when the request asks for several of one thing, such as three examples or a test for each endpoint, it names how many must be present. Keep it to one or two sentences that follow the user's wording.")


class JevMultiPartPayload(JevSectionPayload):
    """The multi-part section of the run state: every separate deliverable the request asks for."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The multi-part section breaks the request into the separate deliverables it asks for, so that a later check can confirm each one was produced before the agent stops. It exists because agents often finish one visible part of a request and forget another part that was asked for in passing. Each deliverable is described so that someone reading only the agent's final work and a record of its run could tell whether that deliverable is there. The section records what the request asks for, not how the agent should produce it, and it never adds work the user did not ask for. Fill it from the user's request alone, before any work has started."

    deliverables: list[JevDeliverablePayload] = Field(description="The deliverables are the separate outputs the request asks the agent to produce, one entry per output, in the order the request asks for them. An output is separate when it could be left out while the other outputs are still produced, such as a code change, a test, a migration, a document, an example, or an explanation the user asked for in its own right. Do not split one output into smaller steps, do not merge two outputs the user asked for separately, and do not add outputs the request does not ask for, such as extra tests or documentation the user never mentioned. Steps the agent takes only to produce an output, such as reading files or running a search, are not deliverables. Return an empty list when the request asks for no output at all, such as a greeting.")


class JevTargetOutcomeItemPayload(BaseModel):
    """One distinct target outcome the request asks the agent to establish."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this requested outcome a short stable id in lowercase letters, digits, and underscores, starting with a letter and no longer than sixty-four characters. Derive it from the outcome's subject rather than assigning a position number. Keep ids unique within this section and copy each id unchanged into the handoff. The id connects one request-derived outcome to its evidence and Jev answer. Do not use the id to add meaning that the named fields do not contain.")
    outcome: str = Field(min_length=1, description="State the result the user asks to exist or be true after this task, using the user's own words where possible. Name a result rather than an action the agent may take, such as installing, building, or testing. Keep this one outcome distinct from other independently requested results. Do not infer a broader goal or add a quality target the user did not state. If no separate real target outcome can be identified without guessing, omit the item rather than inventing one.")
    target: str = Field(min_length=1, description="Name the actual object, system, environment, audience, or source whose state the requested outcome concerns. Copy the target from the request or use only a target that follows unambiguously from it. Keep the target distinct from an intermediate tool, test, build, plan, or other method used to reach it. Do not substitute a convenient proxy for the target. Omit this item when the request provides no separate target that can be named faithfully.")
    scope: str = Field(min_length=1, description="Describe the extent of the requested outcome on its target, preserving named files, components, users, environments, versions, quantities, and limits. Keep qualifiers such as all, only, latest, and exact when they affect what the evidence must cover. Do not expand a narrow request or reduce a broad request to match expected evidence. Describe the target area or population, not the agent's sequence of steps. If a meaningful scope cannot be determined from the request, omit the item instead of filling the gap with a guess.")
    completion_criterion: str = Field(min_length=1, description="State one observable condition that would demonstrate the requested outcome on the actual target. Derive the condition from the user's words and name what could be observed, inspected, or measured at that target. Do not use a proxy milestone alone, such as a plan, installation, successful build, or smoke test, as the criterion unless the user requested that milestone itself as the outcome. Do not require extra work or standards absent from the request. Omit the item if no faithful criterion can be stated without inventing requirements.")


class JevTargetOutcomePayload(JevSectionPayload):
    """The target-outcome section of the run state, written from the request before work begins."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "This section lists distinct outcomes the user asks to establish on an actual target, so a later check can tell whether the evidence reaches the requested result rather than stopping at a nearby milestone. It records the user's requested outcome, its target and scope, and one observable completion criterion for each item. The section is filled from the request alone before the main agent begins work, so it must not predict which milestones or evidence the run will produce. Do not treat a build, installation, test, plan, or other step as the user's outcome unless the request itself asks for that result. Return no items when the request has no separate target outcome or when identifying one would require guessing."

    items: list[JevTargetOutcomeItemPayload] = Field(description="List one item per distinct result the user asks to establish on a target whose state is separate from merely producing an answer or other requested output. Each item names the outcome, actual target, requested scope, and a faithful observable completion criterion. Do not list agent activities, tools, plans, builds, installations, or tests as outcomes unless the user requests that result itself. Do not invent a target, scope, or criterion to fill missing request details. Return an empty list when there is no applicable target outcome to judge.")


class JevHandoffPayload(BaseModel):
    """The evidence handoff JevHandoff writes after the main agent tries to finish.

    JevHandoff adds one field to this model for every enabled done check, typed as that check's evidence
    payload and described by its SECTION text, so the reply holds exactly the evidence the enabled checks read.
    """

    model_config = ConfigDict(extra="forbid")


class JevDeliverableEvidencePayload(BaseModel):
    """The evidence the run holds for one deliverable, as JevHandoff writes it in the multi-part section."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is the exact identifier of one deliverable from the run state's multi-part section, copied character for character. Every deliverable in the run state gets exactly one evidence entry, even when the run did no work on it, and no entry may use an id that is not in the run state. The id is how the evidence is matched back to the deliverable it is about, so it is never renamed, merged, or invented. Write the entries in the same order as the deliverables in the run state.")
    evidence: str = Field(min_length=1, description="The evidence is everything in the agent's run that shows whether this deliverable was produced, compiled so that a checker who sees only this text and the deliverable can judge it. Quote or closely reproduce the relevant parts of the run: the final answer's passages about this deliverable, the tool calls that created or changed it with their arguments and outputs, and the results of any command or test that exercised it. Name where each piece comes from, such as the final answer, a response, or a named tool call, and keep the pieces in the order they happened. Report what the run shows, including failed attempts and errors, and never describe work the run does not show or state that the deliverable is complete. When the run shows nothing about this deliverable, say that no part of the run concerns it.")
    missing: str = Field(min_length=1, description="The missing field says what the run does not show for this deliverable, measured against its description and completion signal. List each part of the deliverable that has no evidence, each part whose evidence shows a failure, and each detail the completion signal needs that the run leaves unshown. Write it for the agent that did the work, in plain words it can act on, and name the specific file, section, test, or topic that is missing. Do not repeat the evidence, and do not suggest work beyond what the deliverable asks for. When the evidence covers every part of the completion signal, write that nothing is missing.")


class JevMultiPartEvidencePayload(JevSectionPayload):
    """The multi-part section of the handoff: the evidence for every deliverable the run state lists."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The multi-part evidence section gathers, for each deliverable the run state lists, the parts of the agent's run that show whether that deliverable was produced. A separate checker reads one entry at a time, next to the user's request and that deliverable's description and completion signal, and decides whether the deliverable is done. That checker sees nothing of the run except the evidence written here, so the evidence must be complete, specific, and faithful to what the run actually shows. The section reports observations and never gives a verdict about whether the work is complete. It is filled after the agent tries to finish, from the agent's context window."

    deliverables: list[JevDeliverableEvidencePayload] = Field(description="The deliverables hold one evidence entry for every deliverable in the run state's multi-part section, with the same ids and in the same order. Each entry gathers the parts of the run that bear on that one deliverable and states what the run does not show for it. An entry never borrows evidence from another deliverable unless the same piece of the run truly concerns both, in which case it is repeated in each. Do not add entries for work the run did that no deliverable asks for. Never leave a deliverable out, even when the run did nothing toward it.")


class JevOutputExtentItemPayload(BaseModel):
    """One explicit text-size obligation extracted from the request before work starts."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this extent obligation a stable lowercase id beginning with a letter and containing only letters, digits, and underscores. Derive the id from the output target rather than its position in the request. Use a distinct id for every separately stated target or extent requirement. Copy the same id into the handoff so the checker can match request and evidence. Keep it no longer than sixty-four characters.")
    target: str = Field(min_length=1, description="Name the specific answer or artifact whose text extent the user explicitly constrained. Preserve any file, section, audience, or scope named by the request. Do not replace the target with a count of distinct examples, files, or records, because those are separate output-count obligations. Do not create an extent item from vague words such as detailed, comprehensive, or thorough without an explicit measurable amount. Keep this target recognizable in continuation feedback.")
    amount: int = Field(gt=0, description="Record the positive numeric amount the user explicitly requested for this target. Copy the number faithfully and do not round, convert, strengthen, or weaken it. The amount is interpreted together with the comparator and unit fields. Do not infer an amount from an adjective, an example, or an agent's proposed plan. One item represents one explicit amount requirement.")
    unit: JevOutputExtentUnit = Field(description="Use the text unit explicitly named or unambiguously implied by the request: words, characters, lines, sections, or pages. Preserve distinctions between these units because their counting rules differ. Do not choose a unit merely because it is convenient to measure. For a requested page count, require visible page boundaries such as form-feed markers before code treats the count as deterministic. If the unit or its basis is unclear, do not create an item.")
    comparator: JevOutputExtentComparator = Field(description="Use minimum when the request asks for at least or no fewer than the amount, exact when it asks for exactly the amount, and maximum when it asks for at most or no more than the amount. Preserve the direction of the bound; an exact amount is not a minimum. Do not reinterpret an unqualified number unless the user's wording makes its comparator clear. The comparator determines which observed amounts satisfy this obligation. Keep the original bound available to continuation feedback.")


class JevOutputExtentPayload(JevSectionPayload):
    """The output-extent section of run state, containing only explicit measurable text-size requests."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The output-extent section records explicit measurable text-size obligations from the user's request before the main agent starts work. Each item names one output target, one numeric amount, one unit, and whether the user requested a minimum, exact, or maximum amount. This check concerns the magnitude of text in an output, while separate requested examples, files, records, and other distinct entries are checked as output-count obligations. Do not create quotas from vague adjectives or infer an amount that the user did not give. Return an empty list when the request contains no clear measurable text extent."

    items: list[JevOutputExtentItemPayload] = Field(description="Return one item for each explicit measurable text-size obligation in the request, preserving its target, amount, unit, and comparator. Include word, character, line, section, or page extents only when the requested basis is clear enough to identify. Keep an exact bound distinct from a minimum or maximum bound. Do not include counts of distinct entries, files, examples, or records, and do not invent quotas from words such as detailed or comprehensive. Return an empty list if no explicit measurable text extent was requested.")


class JevOutputExtentEvidenceItemPayload(BaseModel):
    """Observed run evidence and its actionable gap for one requested output extent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Copy the id of one output-extent item from run state character for character. Return exactly one evidence entry for every run-state item, including when the run shows no target output. Do not invent, rename, merge, or omit ids. Preserve the request-state order so item-to-evidence matching is stable. The id links evidence and continuation feedback to one explicit extent obligation.")
    evidence: str = Field(min_length=1, description="Quote or closely reproduce the run's observed text for this target, naming whether it comes from the final answer or a particular artifact/tool result. Preserve enough of the output for the checker to identify which target is present and what text is available. When code measures the raw final answer directly, report that code-side observation instead of asking the handoff model to count or reproduce a large answer. Report observations and failed or superseding attempts without declaring that the requested amount passed. Do not count words, characters, lines, sections, or pages; deterministic code performs supported counting from the raw final answer.")
    missing: str = Field(min_length=1, description="Explain what the run does not show about this target in relation to its requested amount and unit. Name the target and any absent, short, excessive, or otherwise unverified text extent in actionable terms. Preserve whether the request says minimum, exact, or maximum. If the evidence covers the requested extent, say that nothing is missing. This field is continuation feedback only and is never sent to Jev as evidence.")


class JevOutputExtentEvidencePayload(JevSectionPayload):
    """The handoff's output-extent evidence section, with one entry per pre-run obligation."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The output-extent evidence section records what the latest finish attempt shows for every extent obligation written from the request before work began. A checker reads each output target and its observed run evidence separately, while deterministic code measures raw final-answer text when the target and unit permit an unambiguous count. The evidence must identify the target and reproduce relevant observed text without relying on the main agent's claim that it met the amount. The separate missing field helps the main agent continue but is a handoff judgment, not evidence for Jev. Preserve output exactly enough that later code and a recognition check can distinguish the target from unrelated text."

    items: list[JevOutputExtentEvidenceItemPayload] = Field(description="Return one entry for each output-extent item in run state, in the same order and with the same id. Identify the latest evidence that bears on that target, including its source, or state that the run shows no relevant output. Do not summarize the text in a way that changes its amount or claim that the amount passed. Put an actionable account of what remains absent or unverified in missing, which is not sent as Jev evidence. Never omit an item merely because the run did not address it.")
class JevTargetOutcomeEvidenceItemPayload(BaseModel):
    """The observed milestones, direct target evidence, and evidence gap for one requested outcome."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Copy exactly one id from the run state's target-outcome section, preserving its spelling and order. Include one entry for every listed outcome, even when the run shows no relevant activity. Do not add an id for a different outcome or reuse one entry for several outcomes. This id lets the checker match this evidence to its request-derived target, scope, and criterion. A changed or missing id makes the evidence unable to match the intended item.")
    observed_proxy: str = Field(min_length=1, description="Describe any intermediate milestone the run actually observed that could be mistaken for the requested outcome, such as a plan, installation, build, or test result. Quote or closely reproduce the run and name the response or tool result where the milestone appears. If the run shows no such milestone, say that none was observed. Do not say that the milestone proves the target outcome. This field is context for the checker and is not direct evidence that the requested result occurred.")
    direct_evidence: str = Field(min_length=1, description="Quote or closely reproduce what the run directly observed about the requested outcome on its actual target and within its scope. Name the source, such as a tool call and its output, inspected artifact, environment observation, or final-answer content when the answer itself is the requested target. Include relevant failures and later changes so the current target state is clear. If no direct target evidence appears, state that explicitly rather than substituting a proxy milestone. Report observations only and never declare the outcome complete.")
    missing: str = Field(min_length=1, description="Describe what the run does not show about the target outcome, measured against the request-derived target, scope, and completion criterion. Identify the target or scope that remains unobserved and explain which direct observation is absent. Keep this a concise, actionable gap for the main agent rather than a verdict about whether the request was good or the work was valuable. Do not add requirements beyond the request. When the run directly shows the criterion on the actual target, say that no evidence gap remains.")


class JevTargetOutcomeEvidencePayload(JevSectionPayload):
    """The target-outcome section of the handoff, with observations for every listed outcome."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "This section records what the main agent's run observed for each outcome in the request-derived target-outcome section. It separates intermediate proxy milestones from direct evidence about the actual target so that a nearby step cannot stand in for the user's requested result. The checker receives the target, scope, and completion criterion from run state together with the proxy and direct evidence from this section. The section reports observations and a separate actionable gap, never a completion verdict. Fill it after each finish attempt from the current run window, including relevant failed attempts and later state changes."

    items: list[JevTargetOutcomeEvidenceItemPayload] = Field(description="Return one evidence item for every run-state target outcome, preserving each id and the request's ordering. Separate any observed proxy milestone from observations made directly on the actual target. Include the source of each observation, relevant failures, and the latest state shown by the run. Write `missing` separately for the main agent; do not use it as evidence or tell the checker what verdict to choose. If there are no run-state outcomes, return an empty list.")


class JevClaimIdentityPayload(BaseModel):
    """The title, meaning, and stated purpose of a final-answer claim."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, description="Write a short title that names the factual claim from the main agent's final answer. Keep it specific enough to distinguish this claim from other claims about the same task. Derive it from the assertion's subject and preserve important qualifiers from the answer. Do not use the title to add facts that the answer does not state. Use plain words the main agent can recognize in continuation feedback.")
    description: str = Field(min_length=1, description="Describe the claim in the context needed to understand its assertions. Preserve what the main agent actually said, including the subject, result, and meaningful qualifiers. Put independently checkable facts in the assertions list rather than hiding them in a compound description. Do not treat this description as evidence that the claim happened. A reader should understand this claim without seeing another entry.")
    intent: str | None = Field(description="Record the purpose when the user's request or final answer states or clearly explains why this claim matters. Preserve that reason without upgrading an implied benefit or hidden motive into a fact. Use null when neither source gives a clear purpose for the claim. Do not infer intent from implementation details or what a developer probably wanted. This field explains the claim's relevance but does not change what counts as evidence.")


class JevClaimScopePayload(BaseModel):
    """The target boundary and explicit qualifications that limit a parent claim."""

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(min_length=1, description="Name the target and extent covered by this claim, such as a file, command, test selection, result, or part of the final answer. Preserve words such as all, only, latest, and exact version because they affect what evidence must show. State what the claim covers, not how the agent should complete it. Do not widen a narrow target into a repository-wide or universal claim. Keep the scope understandable without relying on another claim entry.")
    qualifications: list[str] = Field(description="List limitations or conditions the main agent explicitly attaches to the claim. Preserve wording about a platform, version, sample, or verification limit when it narrows the assertion. Return an empty list when the answer states no qualifications. Do not add cautionary language or infer limitations from tool evidence. A qualification limits the assertion and must be respected when its criteria are checked.")


class JevClaimAssertionPayload(BaseModel):
    """One independently checkable statement within a parent claim and its completion criteria."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this assertion a short stable id in lowercase letters, digits, and underscores, starting with a letter and no longer than sixty-four characters. Derive it from the fact being asserted rather than assigning a position number. Keep ids unique within the parent claim and copy each id unchanged into the record. Different parents may use the same assertion id because the question name also contains the parent id. The id lets code associate one Jev answer with exactly one assertion.")
    statement: str = Field(min_length=1, description="Write one factual statement from the final answer that can be checked on its own. Preserve its target, scope, tense, and qualifications rather than weakening it to make it easier to support. Split a sentence into separate entries when it states independent facts. Exclude plans, recommendations, opinions, and statements without checkable factual content. This is the exact assertion the Jev question judges.")
    completion_criteria: str = Field(min_length=1, description="State the observable condition the run evidence must meet to support this assertion. Derive the condition from the statement and keep it within the parent claim's scope and qualifications. Make the criterion specific to visible source content, a completed change, a command result, or another recorded fact. Do not add work the answer did not claim or treat the handoff's verdict as evidence. Give one criterion so this assertion cannot pass without a defined check.")


class JevClaimContextPayload(BaseModel):
    """The five named context sections Jev reads to judge one claim assertion."""

    model_config = ConfigDict(extra="forbid")

    identity: JevClaimIdentityPayload = Field(description="The identity section gives the assertion a concise title, faithful description, and any purpose clearly stated by the request or final answer. It helps the checker understand what the main agent meant before comparing that meaning with run evidence. Keep the title and description grounded in the final answer and represent an unstated purpose as null. This section describes the claim and does not establish that the asserted work or result occurred. Keep independent facts in separate assertions even when they share this identity.")
    scope: JevClaimScopePayload = Field(description="The scope section identifies the target and limits of the parent claim, including qualifications the main agent explicitly stated. It tells the checker how broad the evidence must be and which conditions narrow the assertion. Preserve quantified or universal scope exactly because evidence for a subset cannot establish a claim about the whole set. Use an empty qualifications list when the final answer states no limitation. Do not add a restriction that the final answer did not make.")
    kind: JevClaimKind = Field(description="Choose the kind that best describes the factual assertion: source content, an artifact change, a command result, a test result, run activity, or another factual kind. Select based on what the final answer asserts rather than which tool produced the evidence. Use other_fact only when none of the named kinds fits the statement. The kind helps Jev recognize what an appropriate observation looks like but does not count as evidence. Do not make a second support judgment while choosing the kind.")
    output: str | None = Field(description="Name the artifact or result the final answer says the user received, if this assertion concerns an output. Preserve the stated form and target, such as a README section, changed source file, explanation, or test result. Use null for an observation that claims no output was produced. Do not describe an intended output as if the run created it. The evidence and completion criteria determine whether the stated output is shown.")
    assertions: list[JevClaimAssertionPayload] = Field(min_length=1, description="List the distinct factual assertions that make up this parent claim, giving each its own stable id, statement, and completion criteria. Separate facts whenever one could be supported while another remains unsupported. Keep each qualifier attached to the assertion it limits and do not let one assertion borrow another's evidence. Return at least one assertion so every parent claim receives a Jev question. Jev and code evaluate assertions separately, then code combines their outcomes under the parent claim.")


class JevClaimEvidencePayload(BaseModel):
    """One concrete, checkable final-answer claim and the tool-call evidence paired with it."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this parent claim a short stable id in lowercase letters, digits, and underscores, starting with a letter and no longer than sixty-four characters. Derive the id from the claim subject rather than assigning a position number. Use a different id for every parent claim, including claims about the same file. Copy the id unchanged into the frozen record so question names can include it. The parent id groups assertion-level answers for continuation feedback.")
    claim: JevClaimContextPayload = Field(description="Describe the claim through the five context sections identity, scope, kind, output, and assertions. Preserve the final answer's meaning and qualifications, and give every assertion its own completion criteria. Leave missing intent and output explicitly null and unstated qualifications as an empty list. Do not invent claims, purposes, limits, outputs, or supporting facts. This structured claim is the item Jev judges beside the run evidence.")
    evidence: str = Field(min_length=1, description="Pair this claim with the tool calls from the run that bear directly on its exact factual content, including each call's name, relevant arguments, execution state, and output. A read or search result can support a claim about what a file or source contains; a mutating call can support a claim that the agent changed a target; a command result can support a claim about what that command reported. Report calls in the order they happened, including failed attempts and later changes that superseded an earlier result. A claim repeated in the final answer is not evidence. When no tool call supports the claim, state plainly that no supporting tool call was found.")
    missing: str = Field(min_length=1, description="Say what the available tool-call evidence does not show for this parent claim in words the main agent can act on. Name the unsupported target, assertion, action, or successful result instead of repeating the full evidence. If a failed attempt was later replaced by success, describe only what remains unsupported after the later observation. When evidence covers the claim's criteria, say that nothing is missing. This field guides continuation feedback and is not sent as supporting evidence to Jev.")


class JevClaimsEvidencePayload(JevSectionPayload):
    """The claims section of the handoff: concrete final-answer assertions paired with tool-call evidence."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The claims section checks concrete factual assertions in the main agent's final answer about the task, its artifacts, observed results, or work completed during the run. The handoff extracts those claims after the work because their exact statements cannot be known in the pre-run state. Each claim gives Jev five named context sections and one assertion at a time with completion criteria. The handoff pairs every parent claim with run evidence and separately writes an actionable missing note for continuation. This section reports observations and never decides whether a claim is supported."

    claims: list[JevClaimEvidencePayload] = Field(description="Return one entry for every parent claim containing a concrete, independently checkable factual assertion from the final answer. Give each entry a rich claim context and split independent facts into separate assertions so each receives one Jev judgment. Pair the parent with relevant run evidence, or state that no supporting tool call was found. Give each parent and its assertions stable unique ids within their respective scopes. Return an empty list only when the final answer contains no checkable factual claims.")


class JevProblemEvidencePayload(BaseModel):
    """One run-observed problem or the required original-request completion item."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Use a unique stable lowercase id for this observed problem. Use exactly original_request_completion for the required original-request item. Start with a letter and use only lowercase letters, digits, or underscores. Keep the id unchanged because Jev answers are keyed by it.")
    kind: JevProblemCheckItemType = Field(description="Use problem for an issue encountered during this run. Use request_completion for the single item about finishing the user's original request after repairs. The kind selects which completion rule applies. Do not use it to signal whether the item passed.")
    title: str = Field(min_length=1, description="Write a concise name identifying this specific issue or requested outcome. Preserve the target when it distinguishes this item from another. Use plain words the main agent can recognize in feedback. Do not state that the item is complete in its title.")
    description: str = Field(min_length=1, description="Describe the observed problem or requested outcome using the user's request and this run. Preserve the event or result that makes this item checkable. Keep one issue in each problem item. Do not invent a failure or add work beyond the original request.")
    scope: str = Field(min_length=1, description="Name the affected task, artifact, command, validation, or requested work. Preserve the full scope and meaningful qualifiers. Evidence about only part of this scope cannot establish the whole item. Do not narrow the scope to fit the observed result.")
    qualifications: str = Field(min_length=1, description="State explicit limits or conditions that affect what counts as resolving this item. Preserve any stated platform, version, count, or test boundary. Say none when no condition applies. Do not add general cautions or inferred restrictions.")
    repair: str = Field(min_length=1, description="For a problem, describe the repair attempted and the outcome shown in the run. Keep attempts separate from successful changes. For request_completion, state what original work remained or was completed after repairs. A claim that the work is done is not proof of its result.")
    verification: str = Field(min_length=1, description="Report relevant successful revalidation after the repair, or state that no successful verification is shown. The verification must exercise or inspect the affected behavior. For request_completion, report evidence of the requested result after repairs. Do not treat an unrelated successful command as verification.")
    evidence: str = Field(min_length=1, description="Faithfully summarize relevant responses, tool calls, outputs, and final-answer passages in run order. Name the source of each observation where available. Include relevant failures and later repairs or reversals. Never treat intent or a claim as proof that an action succeeded.")
    missing: str = Field(min_length=1, description="Give the main agent an actionable handoff gap for this item. Name the repair, validation, or requested work that the run does not establish. This writer judgment is not shown to Jev as evidence. Say nothing is missing when the evidence covers the completion condition.")


class JevProblemsResolvedEvidencePayload(JevSectionPayload):
    """Dynamic problem items extracted from the completed run."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "Extract every concrete error, failed operation, blocker, or failed validation encountered in this run, then include exactly one request_completion item. Report observed facts and ordered evidence only. Do not omit an issue because a later repair was attempted, and do not invent hypothetical issues. A repair is complete only when relevant evidence shows the fix and successful revalidation. The required request_completion item must judge whether the original user request was completed after the repairs."
    items: list[JevProblemEvidencePayload] = Field(description="Return one entry per observed problem episode. Also return exactly one request_completion entry, even if no problems occurred. Use unique stable ids and reserve original_request_completion for that required item. Retain failed attempts alongside later repair and verification evidence. Do not omit an item because the handoff thinks it is already fixed.")


class JevDeliverableId:
    """Shared validation for the stable item identifiers used by done-check records and questions."""

    @staticmethod
    def require(value: object, *, field_name: str) -> str:
        # Returns a lowercase identifier matching JEV_DELIVERABLE_ID_PATTERN, raising for anything else.
        if not isinstance(value, str) or _DELIVERABLE_ID.fullmatch(value) is None:
            raise JevValidation.error(field_name, "a lowercase identifier of letters, digits, and underscores that starts with a letter (at most 64 characters)", value)
        return value

    @staticmethod
    def require_unique(ids: tuple[str, ...], *, field_name: str) -> None:
        # Rejects a repeated identifier, since every later step matches done-check items by id.
        duplicates = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
        if duplicates:
            raise JevValidation.error(field_name, "unique item ids", f"duplicates {duplicates}")


@dataclass(frozen=True, slots=True)
class JevDeliverable:
    """One separate output the request asks for: a stable id, what it is, and the visible condition that shows it is done."""

    id: str
    description: str
    completion_signal: str

    def __post_init__(self) -> None:
        # Requires an identifier later steps can echo exactly, and non-blank description and signal text.
        JevDeliverableId.require(self.id, field_name="deliverable id")
        JevText.require(self.description, field_name=f"description of deliverable {self.id!r}")
        JevText.require(self.completion_signal, field_name=f"completion_signal of deliverable {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevMultiPart:
    """The multi-part section of a run state: every separate deliverable the request asks for, in request order."""

    deliverables: tuple[JevDeliverable, ...] = ()

    def __post_init__(self) -> None:
        # Requires a tuple of deliverables with unique ids; an empty tuple means the request asks for no output.
        if not isinstance(self.deliverables, tuple) or not all(isinstance(item, JevDeliverable) for item in self.deliverables):
            raise JevValidation.error("multi-part deliverables", "a tuple of JevDeliverable values", self.deliverables)
        JevDeliverableId.require_unique(self.ids(), field_name="multi-part deliverables")

    def ids(self) -> tuple[str, ...]:
        """Return every deliverable id in request order."""
        return tuple(item.id for item in self.deliverables)


@dataclass(frozen=True, slots=True)
class JevOutputExtentAmount:
    """Validate one positive whole-number output bound at a typed Jev boundary."""

    value: int
    field_name: str = "output extent amount"

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool) or self.value < 1:
            raise JevValidation.error(self.field_name, "a positive integer", self.value)


@dataclass(frozen=True, slots=True)
class JevOutputExtentItem:
    """One explicit target and bound on the magnitude of its requested text output."""

    id: str
    target: str
    amount: int
    unit: JevOutputExtentUnit
    comparator: JevOutputExtentComparator

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="output extent id")
        JevText.require(self.target, field_name=f"output extent target {self.id!r}")
        JevOutputExtentAmount(self.amount, field_name=f"output extent amount {self.id!r}")
        if not isinstance(self.unit, JevOutputExtentUnit):
            raise JevValidation.error(f"output extent unit {self.id!r}", "a JevOutputExtentUnit member", self.unit)
        if not isinstance(self.comparator, JevOutputExtentComparator):
            raise JevValidation.error(f"output extent comparator {self.id!r}", "a JevOutputExtentComparator member", self.comparator)


@dataclass(frozen=True, slots=True)
class JevOutputExtent:
    """The explicit text extents requested before work starts, in request order."""

    items: tuple[JevOutputExtentItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(isinstance(item, JevOutputExtentItem) for item in self.items):
            raise JevValidation.error("output extent items", "a tuple of JevOutputExtentItem values", self.items)
        JevDeliverableId.require_unique(self.ids(), field_name="output extent items")

    def ids(self) -> tuple[str, ...]:
        """Return each explicit extent obligation id in request order."""
        return tuple(item.id for item in self.items)


@dataclass(frozen=True, slots=True)
class JevRunStateRecord:
    """The run state JevRunState wrote from the user's request: the central fields and the section of every enabled done check.

    `multi_part` and `target_outcome` are set only when their respective request-derived done checks are enabled, and `usage` is JevRunState's own model usage.
    """

    goal: str
    objective: str
    mission: str
    what_not_to_do: tuple[str, ...] = ()
    multi_part: JevMultiPart | None = None
    output_extent: JevOutputExtent | None = None
    target_outcome: JevTargetOutcome | None = None
    usage: UsageRollup | None = None

    def __post_init__(self) -> None:
        # Requires the central text fields, non-blank limits, and a typed multi-part section when present.
        for field_name in ("goal", "objective", "mission"):
            JevText.require(getattr(self, field_name), field_name=f"run state {field_name}")
        if not isinstance(self.what_not_to_do, tuple):
            raise JevValidation.error("run state what_not_to_do", "a tuple of strings", self.what_not_to_do)
        for index, limit in enumerate(self.what_not_to_do):
            JevText.require(limit, field_name=f"run state what_not_to_do[{index}]")
        if self.multi_part is not None and not isinstance(self.multi_part, JevMultiPart):
            raise JevValidation.error("run state multi_part", "a JevMultiPart or None", self.multi_part)
        if self.output_extent is not None and not isinstance(self.output_extent, JevOutputExtent):
            raise JevValidation.error("run state output_extent", "a JevOutputExtent or None", self.output_extent)
        if self.target_outcome is not None and not isinstance(self.target_outcome, JevTargetOutcome):
            raise JevValidation.error("run state target_outcome", "a JevTargetOutcome or None", self.target_outcome)


@dataclass(frozen=True, slots=True)
class JevTargetOutcomeItem:
    """One requested target result, with its target, scope, and observable completion criterion."""

    id: str
    outcome: str
    target: str
    scope: str
    completion_criterion: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="target outcome id")
        for field_name in ("outcome", "target", "scope", "completion_criterion"):
            JevText.require(getattr(self, field_name), field_name=f"target outcome {self.id!r} {field_name}")


@dataclass(frozen=True, slots=True)
class JevTargetOutcome:
    """Request-derived target outcomes, in the order the user asked for them."""

    items: tuple[JevTargetOutcomeItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(isinstance(item, JevTargetOutcomeItem) for item in self.items):
            raise JevValidation.error("target outcomes", "a tuple of JevTargetOutcomeItem values", self.items)
        JevDeliverableId.require_unique(self.ids(), field_name="target outcomes")

    def ids(self) -> tuple[str, ...]:
        """Return the stable ids of the requested target outcomes."""
        return tuple(item.id for item in self.items)


@dataclass(frozen=True, slots=True)
class JevDeliverableEvidence:
    """What the run shows for one deliverable, and what it does not show, as JevHandoff compiled it."""

    id: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        # Requires the echoed deliverable id and non-blank evidence and missing text.
        JevDeliverableId.require(self.id, field_name="evidence id")
        JevText.require(self.evidence, field_name=f"evidence of deliverable {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of deliverable {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevMultiPartEvidence:
    """The multi-part section of a handoff: one evidence entry per deliverable, in the run state's order."""

    deliverables: tuple[JevDeliverableEvidence, ...] = ()

    def __post_init__(self) -> None:
        # Requires a tuple of evidence entries with unique ids.
        if not isinstance(self.deliverables, tuple) or not all(isinstance(item, JevDeliverableEvidence) for item in self.deliverables):
            raise JevValidation.error("multi-part evidence", "a tuple of JevDeliverableEvidence values", self.deliverables)
        JevDeliverableId.require_unique(self.ids(), field_name="multi-part evidence")

    def ids(self) -> tuple[str, ...]:
        """Return every evidence entry's deliverable id in order."""
        return tuple(item.id for item in self.deliverables)


@dataclass(frozen=True, slots=True)
class JevOutputExtentEvidenceItem:
    """The handoff's observed evidence and continuation gap for one text extent."""

    id: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="output extent evidence id")
        JevText.require(self.evidence, field_name=f"evidence of output extent {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of output extent {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevOutputExtentEvidence:
    """Observed evidence for each requested output extent, in request order."""

    items: tuple[JevOutputExtentEvidenceItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(isinstance(item, JevOutputExtentEvidenceItem) for item in self.items):
            raise JevValidation.error("output extent evidence", "a tuple of JevOutputExtentEvidenceItem values", self.items)
        JevDeliverableId.require_unique(self.ids(), field_name="output extent evidence")

    def ids(self) -> tuple[str, ...]:
        """Return the extent ids represented in the evidence section."""
        return tuple(item.id for item in self.items)


@dataclass(frozen=True, slots=True)
class JevTargetOutcomeEvidenceItem:
    """Observed proxy and direct target evidence for one requested outcome, plus the gap for the main agent."""

    id: str
    observed_proxy: str
    direct_evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="target outcome evidence id")
        for field_name in ("observed_proxy", "direct_evidence", "missing"):
            JevText.require(getattr(self, field_name), field_name=f"target outcome {self.id!r} {field_name}")


@dataclass(frozen=True, slots=True)
class JevTargetOutcomeEvidence:
    """The evidence section for every request-derived target outcome."""

    items: tuple[JevTargetOutcomeEvidenceItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(isinstance(item, JevTargetOutcomeEvidenceItem) for item in self.items):
            raise JevValidation.error("target outcome evidence", "a tuple of JevTargetOutcomeEvidenceItem values", self.items)
        JevDeliverableId.require_unique(self.ids(), field_name="target outcome evidence")

    def ids(self) -> tuple[str, ...]:
        """Return the ids of the target outcomes represented by this evidence."""
        return tuple(item.id for item in self.items)


@dataclass(frozen=True, slots=True)
class JevClaimIdentity:
    """The title, description, and stated intent that identify a factual claim."""

    title: str
    description: str
    intent: str | None = None

    def __post_init__(self) -> None:
        JevText.require(self.title, field_name="claim title")
        JevText.require(self.description, field_name="claim description")
        if self.intent is not None:
            JevText.require(self.intent, field_name="claim intent")


@dataclass(frozen=True, slots=True)
class JevClaimScope:
    """The target scope and explicit qualifications attached to one claim."""

    scope: str
    qualifications: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        JevText.require(self.scope, field_name="claim scope")
        if not isinstance(self.qualifications, tuple):
            raise JevValidation.error("claim qualifications", "a tuple of strings", self.qualifications)
        for index, qualification in enumerate(self.qualifications):
            JevText.require(qualification, field_name=f"claim qualification[{index}]")


@dataclass(frozen=True, slots=True)
class JevClaimAssertion:
    """One independently checkable factual statement and its observable completion criteria."""

    id: str
    statement: str
    completion_criteria: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="claim assertion id")
        JevText.require(self.statement, field_name=f"claim assertion {self.id!r}")
        JevText.require(self.completion_criteria, field_name=f"completion criteria of claim assertion {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevClaimContext:
    """The five context sections Jev reads for each factual assertion in a parent claim."""

    identity: JevClaimIdentity
    scope: JevClaimScope
    kind: JevClaimKind
    output: str | None
    assertions: tuple[JevClaimAssertion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, JevClaimIdentity):
            raise JevValidation.error("claim identity", "a JevClaimIdentity", self.identity)
        if not isinstance(self.scope, JevClaimScope):
            raise JevValidation.error("claim scope", "a JevClaimScope", self.scope)
        if not isinstance(self.kind, JevClaimKind):
            raise JevValidation.error("claim kind", "a JevClaimKind member", self.kind)
        if self.output is not None:
            JevText.require(self.output, field_name="claim output")
        if not isinstance(self.assertions, tuple) or not self.assertions or not all(isinstance(item, JevClaimAssertion) for item in self.assertions):
            raise JevValidation.error("claim assertions", "a non-empty tuple of JevClaimAssertion values", self.assertions)
        JevDeliverableId.require_unique(tuple(item.id for item in self.assertions), field_name="claim assertions")


@dataclass(frozen=True, slots=True)
class JevClaimEvidence:
    """One contextual final-answer claim, run evidence, and an actionable evidence gap."""

    id: str
    claim: JevClaimContext
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        # Requires a stable parent id, typed claim context, and non-blank evidence and gap text.
        JevDeliverableId.require(self.id, field_name="claim evidence id")
        if not isinstance(self.claim, JevClaimContext):
            raise JevValidation.error(f"claim {self.id!r}", "a JevClaimContext", self.claim)
        JevText.require(self.evidence, field_name=f"evidence of claim {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of claim {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevClaimsEvidence:
    """The final-answer claims the handoff found, each paired with evidence from the run's tool calls."""

    claims: tuple[JevClaimEvidence, ...] = ()

    def __post_init__(self) -> None:
        # Requires immutable typed claim entries with unique ids, so answers map back to one claim each.
        if not isinstance(self.claims, tuple) or not all(isinstance(item, JevClaimEvidence) for item in self.claims):
            raise JevValidation.error("claims evidence", "a tuple of JevClaimEvidence values", self.claims)
        JevDeliverableId.require_unique(self.ids(), field_name="claims evidence")

    def ids(self) -> tuple[str, ...]:
        """Return every extracted claim id in final-answer order."""
        return tuple(item.id for item in self.claims)

    def assertion_ids(self) -> tuple[str, ...]:
        """Return each assertion's stable parent.assertion reference in claim and assertion order."""
        return tuple(f"{claim.id}{JEV_DONE_CLAIM_ASSERTION_SEPARATOR}{assertion.id}" for claim in self.claims for assertion in claim.claim.assertions)


@dataclass(frozen=True, slots=True)
class JevProblemResolutionItem:
    """One dynamic issue or original-request completion entry and its evidence."""

    id: str
    kind: JevProblemCheckItemType
    title: str
    description: str
    scope: str
    qualifications: str
    repair: str
    verification: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        # Requires typed item kind, stable identity, and all context/evidence text.
        JevDeliverableId.require(self.id, field_name="problem evidence id")
        if not isinstance(self.kind, JevProblemCheckItemType):
            raise JevValidation.error("problem evidence kind", "a JevProblemCheckItemType", self.kind)
        for field_name in ("title", "description", "scope", "qualifications", "repair", "verification", "evidence", "missing"):
            JevText.require(getattr(self, field_name), field_name=f"problem {self.id!r} {field_name}")


@dataclass(frozen=True, slots=True)
class JevProblemsResolvedEvidence:
    """Dynamic problem evidence with exactly one original-request completion item."""

    items: tuple[JevProblemResolutionItem, ...]

    def __post_init__(self) -> None:
        # @intent every-dynamic-problem-answer-has-one-valid-item
        # Questions are keyed by these ids, and the original request is always a separate required item.
        # Enforcing uniqueness and exactly one reserved completion entry prevents duplicate answers from
        # shadowing an unresolved problem or letting a run with no observed problems skip the original task.
        if not isinstance(self.items, tuple) or not all(isinstance(item, JevProblemResolutionItem) for item in self.items):
            raise JevValidation.error("problem evidence items", "a tuple of JevProblemResolutionItem values", self.items)
        JevDeliverableId.require_unique(self.ids(), field_name="problem evidence")
        completion = tuple(item for item in self.items if item.kind is JevProblemCheckItemType.REQUEST_COMPLETION)
        if len(completion) != 1 or completion[0].id != "original_request_completion":
            raise JevValidation.error("problem evidence completion item", "exactly one request_completion item with id original_request_completion", tuple(item.id for item in completion))
        if any(item.kind is JevProblemCheckItemType.PROBLEM and item.id == "original_request_completion" for item in self.items):
            raise JevValidation.error("problem evidence id", "a problem id other than original_request_completion", "original_request_completion")

    def ids(self) -> tuple[str, ...]:
        """Return all dynamic item ids in handoff order."""
        return tuple(item.id for item in self.items)

    def problem_ids(self) -> tuple[str, ...]:
        """Return only observed problem ids, excluding the original-request item."""
        return tuple(item.id for item in self.items if item.kind is JevProblemCheckItemType.PROBLEM)


@dataclass(frozen=True, slots=True)
class JevHandoffRecord:
    """The evidence JevHandoff compiled from the main agent's run for every enabled done check.

    `multi_part`, `claims`, and `target_outcome` are set only when their respective done checks are enabled, and `usage` is JevHandoff's own model usage.
    `problems_resolved` is set only when that check is enabled; all evidence sections are optional and typed.
    """

    multi_part: JevMultiPartEvidence | None = None
    claims: JevClaimsEvidence | None = None
    output_extent: JevOutputExtentEvidence | None = None
    target_outcome: JevTargetOutcomeEvidence | None = None
    problems_resolved: JevProblemsResolvedEvidence | None = None
    usage: UsageRollup | None = None

    def __post_init__(self) -> None:
        # Requires a typed evidence section for each enabled done check when present.
        if self.multi_part is not None and not isinstance(self.multi_part, JevMultiPartEvidence):
            raise JevValidation.error("handoff multi_part", "a JevMultiPartEvidence or None", self.multi_part)
        if self.claims is not None and not isinstance(self.claims, JevClaimsEvidence):
            raise JevValidation.error("handoff claims", "a JevClaimsEvidence or None", self.claims)
        if self.output_extent is not None and not isinstance(self.output_extent, JevOutputExtentEvidence):
            raise JevValidation.error("handoff output_extent", "a JevOutputExtentEvidence or None", self.output_extent)
        if self.target_outcome is not None and not isinstance(self.target_outcome, JevTargetOutcomeEvidence):
            raise JevValidation.error("handoff target_outcome", "a JevTargetOutcomeEvidence or None", self.target_outcome)
        if self.problems_resolved is not None and not isinstance(self.problems_resolved, JevProblemsResolvedEvidence):
            raise JevValidation.error("handoff problems_resolved", "a JevProblemsResolvedEvidence or None", self.problems_resolved)


@dataclass(frozen=True)
class JevDoneQuestion:
    """One fixed done yes/no question: what Jev reads, what each answer looks like, and the gap a no answer names.

    Every concrete question in `vidbyte/lib/jev/done/` subclasses this with a default for every field, so each
    question is its own dataclass constructed with no arguments. `instructions` holds every rule, and its
    `question` names the checked item through an `{item}` placeholder; `when_true` and `when_false` only
    describe each side; `gap` is the self-contained sentence the main agent reads when this question fails,
    ahead of what the handoff says is missing.
    """

    key: JevDoneQuestionKey
    instructions: JevBrief
    when_true: JevCriterion
    when_false: JevCriterion
    gap: str

    def __post_init__(self) -> None:
        # Requires a registered key, a brief, two criteria, and non-blank gap text.
        if not isinstance(self.key, JevDoneQuestionKey):
            raise JevValidation.error("done question key", "a JevDoneQuestionKey member", self.key)
        if not isinstance(self.instructions, JevBrief):
            raise JevValidation.error(f"instructions of done question {self.key.value!r}", "a JevBrief", self.instructions)
        for field_name in ("when_true", "when_false"):
            if not isinstance(getattr(self, field_name), JevCriterion):
                raise JevValidation.error(f"{field_name} of done question {self.key.value!r}", "a JevCriterion", getattr(self, field_name))
        JevText.require(self.gap, field_name=f"gap of done question {self.key.value!r}")

    def name(self, item: str) -> str:
        """Return the name the question about one checked item is sent under and answered by."""
        return f"{self.key.value}.{item}"

    def to_question(self, item: str) -> JevQuestion:
        # Builds the noul JevQuestion about one checked item: the brief's question names the item, so every
        # item's question can share one request's state and its answer comes back under its own name.
        return JevQuestion(
            name=self.name(item),
            question_type=JevQuestionType.NOUL,
            instructions=replace(self.instructions, question=self.instructions.question.format(item=item)).render(),
            options=(JevOption(name=JEV_NOUL_TRUE, description=self.when_true.to_content()), JevOption(name=JEV_NOUL_FALSE, description=self.when_false.to_content())),
        )


@dataclass(frozen=True, slots=True)
class JevDoneResult:
    """What one enabled done check decided the last time the main agent tried to finish.

    `answers` holds Jev's answer per checked-item id, `score` is their mean P(yes), and `incomplete` names
    the items whose P(yes) fell below the check's threshold. Those items are deliverables for MULTI_PART and
    parent claims for CLAIMS; CLAIMS answers use `parent_id.assertion_id` keys so each assertion stays atomic.
    With `available=False` the run state, the handoff, or Jev was unavailable,
    `score` is None, and the check fails open (`passed` stays True). `usage` is from the one Jev request that
    asked every enabled check's questions at that finish attempt.
    """

    check: JevDoneCheck
    score: float | None
    passed: bool = True
    answers: Mapping[str, JevAnswer] = field(default_factory=dict)
    incomplete: tuple[str, ...] = ()
    available: bool = True
    usage: ProviderUsage | None = None

    def __post_init__(self) -> None:
        # Validates the check and score and freezes the answers so a recorded result cannot be edited.
        if not isinstance(self.check, JevDoneCheck):
            raise JevValidation.error("done result check", "a JevDoneCheck member", self.check)
        if self.score is not None:
            object.__setattr__(self, "score", JevProbability.require(self.score, field_name="done result score"))
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))
        if not isinstance(self.incomplete, tuple):
            raise JevValidation.error("done result incomplete", "a tuple of checked-item ids", self.incomplete)


@dataclass(frozen=True, slots=True)
class JevClarifyingQuestion:
    """One clarifying question returned to the user, with the recommended answers the user can pick from."""

    question: str
    recommendations: tuple[str, ...]

    def __post_init__(self) -> None:
        # Requires a question and at least one recommended answer, all non-blank.
        JevText.require(self.question, field_name="clarifying question")
        JevText.require_all(self.recommendations, field_name="clarifying question recommendations")


@dataclass(frozen=True, slots=True)
class JevClarification:
    """The questions JevClarificationAgent wrote for an unclear request, and the clarity checks behind them.

    `questions` holds each clarifying question with its recommended answers, `gaps` names the failed
    clarity checks weakest first, and `usage` is the clarification agent's own model usage.
    """

    questions: tuple[JevClarifyingQuestion, ...]
    gaps: tuple[JevPreflightQuestionKey, ...]
    usage: UsageRollup | None = None

    @classmethod
    def from_payload(cls, payload: JevClarificationPayload, gaps: tuple[JevPreflightQuestionKey, ...], usage: UsageRollup | None = None) -> JevClarification:
        """Build the frozen record from the agent's validated structured reply."""
        questions = tuple(JevClarifyingQuestion(question=item.question.strip(), recommendations=tuple(text.strip() for text in item.recommendations)) for item in payload.questions)
        return cls(questions=questions, gaps=gaps, usage=usage)

    def render(self) -> str:
        """Return the questions as the plain text the user reads: numbered questions, each followed by its recommendations."""
        blocks = []
        for number, item in enumerate(self.questions, start=1):
            options = "\n".join(f"   - {recommendation}" for recommendation in item.recommendations)
            blocks.append(f"{number}. {item.question}\n{options}")
        return "\n".join(blocks)


@dataclass(slots=True)
class JevAgentResponse:
    """Everything JevAgent's opinionated features produced for its most recent run, read as `JevAgent.response`.

    JevResponse is the only writer: it resets this record at the start of each run and fills it as the
    preflight gate acts. `results` holds one entry per enabled fixed-question preset, `usage` is the one
    preflight Jev call's usage, `clarification` is set only when the gate stopped the run to ask the user, and
    `specialist` is the title of the JevSpecialist that ran the task, or None when the main JevAgent ran it.
    With done checks enabled, `run_state` is the state JevRunState wrote before the main agent started,
    `handoff` is the evidence JevHandoff compiled at the latest finish attempt, `done` holds the latest result
    of every enabled done check, and `continuations` counts how often a failed check sent the agent back to work.
    """

    input: str = ""
    output: str | None = None
    results: dict[JevPreflightPreset, JevPresetResult] = field(default_factory=dict)
    clarification: JevClarification | None = None
    usage: ProviderUsage | None = None
    specialist: str | None = None
    run_state: JevRunStateRecord | None = None
    handoff: JevHandoffRecord | None = None
    done: dict[JevDoneCheck, JevDoneResult] = field(default_factory=dict)
    continuations: int = 0

    @property
    def needs_clarification(self) -> bool:
        """Return True when the gate stopped the run to ask the user clarifying questions."""
        return self.clarification is not None


__all__ = [
    "JevAgentResponse",
    "JevAnswer",
    "JevBrief",
    "JevClaimAssertion",
    "JevClaimAssertionPayload",
    "JevClaimContext",
    "JevClaimContextPayload",
    "JevClaimEvidence",
    "JevClaimEvidencePayload",
    "JevClaimIdentity",
    "JevClaimIdentityPayload",
    "JevClaimScope",
    "JevClaimScopePayload",
    "JevClaimsEvidence",
    "JevClaimsEvidencePayload",
    "JevClarification",
    "JevClarificationPayload",
    "JevClarifyingQuestion",
    "JevClarifyingQuestionPayload",
    "JevContent",
    "JevCriterion",
    "JevDecisionRecord",
    "JevDecisionRequest",
    "JevDeliverable",
    "JevDeliverableEvidence",
    "JevDeliverableEvidencePayload",
    "JevDeliverableId",
    "JevDeliverablePayload",
    "JevDoneQuestion",
    "JevDoneResult",
    "JevHandoffPayload",
    "JevHandoffRecord",
    "JevJson",
    "JevModelCard",
    "JevMultiPart",
    "JevMultiPartEvidence",
    "JevMultiPartEvidencePayload",
    "JevMultiPartPayload",
    "JevNoulScore",
    "JevOption",
    "JevPreflightQuestion",
    "JevPresetDefinition",
    "JevPresetResult",
    "JevProbability",
    "JevProblemEvidencePayload",
    "JevProblemResolutionItem",
    "JevProblemsResolvedEvidence",
    "JevProblemsResolvedEvidencePayload",
    "JevQuestion",
    "JevRunStatePayload",
    "JevRunStateRecord",
    "JevSectionPayload",
    "JevSpecialist",
    "JevTargetOutcome",
    "JevTargetOutcomeEvidence",
    "JevTargetOutcomeEvidenceItem",
    "JevTargetOutcomeEvidenceItemPayload",
    "JevTargetOutcomeEvidencePayload",
    "JevTargetOutcomeItem",
    "JevTargetOutcomeItemPayload",
    "JevTargetOutcomePayload",
    "JevText",
    "JevValidation",
    "TypeSafeWireQuestion",
    "TypeSafeWireRequest",
]
