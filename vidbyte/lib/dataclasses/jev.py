"""FILE: vidbyte/lib/dataclasses/jev.py

PURPOSE: Defines validated TypeSafe decision, preflight, and response records, continuation run-state and handoff records, output extent and count obligations, cumulative user-obligation inventories, discovered-item inventories and evidence, report/action alignment evidence, and negative-coverage inspection evidence.
ROLE IN CODEBASE: `vidbyte/providers/typesafe.py` builds TypeSafeWireRequest from JevDecisionRequest and JevAnswer values from responses, while `vidbyte/lib/runners/decision.py` passes the typed records through.
ARCHITECTURE NOTE: This module must not import model_configs because that would close an import cycle through ModalityDetector. Records own every shape rule in __post_init__; problem evidence requires unique ids and exactly one reserved original-request completion item. The provider, not these records, turns a wire record into the JSON body (lint S060 bars dict[str, Any] encoders here).
COMMON MODIFICATION PATTERNS: Mirror https://docs.typesafe.ai/api.md exactly: add a field together with its validation, structured payload, and provider serialization; keep bounds in vidbyte/lib/constants/jev.py. Request-derived output-count obligations belong on JevRunStateRecord; candidate output-count evidence belongs on JevHandoffRecord. Other request-derived definitions and post-run evidence belong on the corresponding run-state and handoff records. Report/action alignment evidence is handoff-only because eligible plans and final accounts exist after work. Consequentially changed assumptions are handoff-only: retain the explicit premise, later observation, affected work, and subsequent revision for each candidate. Negative-coverage run state lists only requested inspection targets; handoff records target-matched inspection evidence separately from a clean or incomplete final-answer report. Required actions are extracted only from explicit user instructions; the run-state records their observable completion conditions and explicit predecessors, and the handoff records trace-backed success evidence.
KNOWN EDGE CASES: State, instructions, and criteria may be a string or JSON structure; noul criteria are optional; score answers carry a probability-weighted `score` that can land between levels; noul answers carry no confidence. Scope evidence distinguishes requested members, workspace inventory, and unsupported mentions. Completion evidence is one handoff-only whole-task item. PHASE_PROGRESS is omitted when no substantive outcome stage exists; INPUT_SET_COVERAGE is omitted when no explicitly bounded input target exists. JevPreflightQuestion and JevDoneQuestion are deliberately not slotted because concrete subclasses redeclare defaulted fields. Pydantic payload descriptions are the instructions generative agents receive; records built from those replies hold validated values, and conversion remains with the agent that requested the reply. Report/action candidates compare an explicit earlier plan with recorded execution, the final account, and request relevance; they do not turn an agent plan into a user requirement. Include a consequential assumption even when later work recovers or makes dependent work irrelevant; Jev judges whether the work was revised or became irrelevant.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-negative-coverage.md, docs/design/jev-required-actions-done-criteria.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-report-action-alignment.md, docs/design/jev-assumption-reconciliation-done-criteria.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-input-set-coverage.md, docs/design/jev-output-count-done-criteria.md, docs/design/jev-cumulative-obligations-done-check.md, skills/jev-continuation/SKILL.md, https://docs.typesafe.ai/api.md, and https://docs.typesafe.ai/primitives/advanced.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and tests/test_jev_done.py.
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
    JEV_DISCOVERED_ITEM_SOURCE_MAX_CHARS,
    JEV_DISCOVERED_ITEM_TOTAL_SOURCE_MAX_CHARS,
    JEV_DONE_CLAIM_ASSERTION_SEPARATOR,
    JEV_DONE_COMPLETION_ITEM_ID,
    JEV_MAX_CHOICE_OPTIONS,
    JEV_MAX_OPTION_NAME_CHARS,
    JEV_MAX_QUESTIONS,
    JEV_MAX_SCORE_LEVELS,
    JEV_MAX_STATE_CHARS,
    JEV_MIN_CHOICE_OPTIONS,
    JEV_MIN_OBLIGATION_STATUS_REASON_CHARS,
    JEV_MIN_OBLIGATION_TURN_INDEX,
    JEV_MIN_SCORE_LEVELS,
    JEV_MOTIVATING_CASE_MAX_SCENARIOS,
    JEV_NOUL_FALSE,
    JEV_NOUL_OPTIONS,
    JEV_NOUL_TRUE,
    JEV_PROBABILITY_SUM_TOLERANCE,
    JEV_SPECIALIST_NONE,
)
from vidbyte.lib.enums.jev import (
    JevBoundaryKind,
    JevClaimKind,
    JevCompletionStatus,
    JevDoneCheck,
    JevDoneQuestionKey,
    JevExerciseMode,
    JevOutputExtentComparator,
    JevOutputExtentUnit,
    JevPreflightPreset,
    JevPreflightQuestionKey,
    JevProblemCheckItemType,
    JevQuestionType,
    JevScenarioRole,
    JevScopeBreadth,
    JevScopeUnitSource,
    JevScopeUniverse,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.agents.pricing import ProviderUsage, UsageRollup

# A frozen JSON value as TypeSafe accepts it: a string, or a read-only mapping / tuple of JSON values.
JevContent = str | Mapping[str, object] | tuple[object, ...]

_API_DOCS = "https://docs.typesafe.ai/api.md"
_DELIVERABLE_ID = re.compile(JEV_DELIVERABLE_ID_PATTERN)


def _normalize_scope_text(value: str) -> str:
    """Collapse whitespace and case for scope-name and request-quote matching."""
    return " ".join(value.split()).casefold()


def _require_scope_member_names(values: object, field_name: str) -> None:
    """Validate one immutable scope-member list and its normalized uniqueness."""
    # @intent scope-member-names-stay-unique
    # The two request member lists define coverage boundaries, so malformed or duplicate names
    # must fail before they can create ambiguous per-member obligations.
    if not isinstance(values, tuple):
        raise JevValidation.error(f"scope {field_name}", "a tuple of strings", values)
    for index, value in enumerate(values):
        JevText.require(value, field_name=f"scope {field_name}[{index}]")
    normalized = tuple(_normalize_scope_text(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise JevValidation.error(f"scope {field_name}", "unique member names", values)


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

class JevCumulativeObligationPayload(BaseModel):
    """One user obligation and its current status across the supplied user turns."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this obligation a short stable id in lowercase letters, digits, and underscores, starting with a letter and no longer than sixty-four characters. Derive it from what the user asked for rather than its position in the conversation. Keep it unique across all obligation entries, including entries the user later cancels or replaces. Copy it unchanged into the frozen record so evidence and Jev answers can refer to exactly this obligation.")
    source_turn: int = Field(ge=0, description="The source turn is the zero-based position of the user message that first introduced this obligation in the ordered user-turn input. The current request is the last turn and earlier turns are in the order supplied by the caller. Use the first turn that asked for this specific result, not the turn that later clarified or cancelled it. This index makes the obligation's origin visible during review and continuation without pretending omitted turns were supplied.")
    related_turns: list[int] = Field(default_factory=list, description="Related turns are later user-message indices that clarify, narrow, or add a compatible qualification to this same obligation. Include each user turn whose wording changed or refined this requirement while remaining compatible with its source. Do not use this field for unrelated additions or cancellations; a cancellation or incompatible replacement belongs in status_turn. Use exact positions in the ordered user-turn list supplied for this run; do not infer turns from unavailable history.")
    instruction: str = Field(min_length=1, description="The instruction is the user's obligation, in the user's terms, with any clarifications from later user turns incorporated while preserving the original request's scope. It names what must be done, answered, preserved, or avoided, but does not add tasks the user never requested. Keep requirements that can be omitted independently as separate obligations, and keep qualifications attached to the obligation they limit. A reader who sees only this field should understand what the active or inactive entry refers to.")
    completion_signal: str = Field(min_length=1, description="The completion signal is the observable result that would satisfy this obligation, derived from what the user actually asked for. It states what the finished answer, changed artifact, command result, or other requested outcome must show. It must include clarifications that narrow or specify the earlier instruction, without turning suggestions or examples into requirements. Do not invent a test, file, format, or quality bar that the user did not require.")
    active: bool = Field(description="Active is true when the latest supplied user turns still require this obligation. An earlier obligation remains active when later turns add another requirement, clarify it, repeat only part of the request, or simply do not mention it again. Set it false only when a later user explicitly cancels it or explicitly replaces it with an incompatible instruction. A later clarification that can be satisfied together with the earlier instruction does not deactivate either requirement.")
    status_turn: int | None = Field(default=None, ge=JEV_MIN_OBLIGATION_TURN_INDEX, description="The status turn is the zero-based user-message index that explicitly cancelled or incompatibly replaced this obligation. It is required for an inactive entry and must be later than source_turn; leave it null for an active entry. The turn-level inventory question uses this link to verify that an inactive status points to actual user wording. Its index must point to the exact user message in that supplied list, not to an agent or tool event.")
    status_reason: str = Field(min_length=JEV_MIN_OBLIGATION_STATUS_REASON_CHARS, description="The status reason cites the user-turn wording that supports the current active or inactive status. For an active obligation, explain that no supplied later turn explicitly cancelled or incompatibly replaced it, including when later turns omit it. For an inactive obligation, quote or closely restate the explicit cancellation or the incompatible replacement and identify its turn. Do not use the agent's omission, lack of progress, or handoff evidence as a reason to make a user obligation inactive.")

class JevCumulativeObligationsPayload(JevSectionPayload):
    """The cumulative-obligations section of run state across the supplied user turns."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The cumulative-obligations section identifies each distinct user requirement across the ordered user turns supplied for this run, including additions and clarifications. A later turn does not erase an earlier requirement by failing to repeat it; only explicit cancellation or an incompatible replacement deactivates it. Each entry preserves source_turn, any related clarification turns, and status_turn when explicitly cancelled or replaced. Every entry is checked after the main agent finishes, and a separate question compares each actual user turn against the full generated inventory so omitted obligations cannot disappear merely because the run-state writer left them out. Use only user messages supplied to this run and the current request, without inventing missing conversation history."

    obligations: list[JevCumulativeObligationPayload] = Field(description="The obligations list contains one entry for each independently checkable user requirement found across the supplied user turns. Preserve the order in which each obligation first appeared and use source_turn to identify that turn. Merge later wording into the same entry when it only clarifies an existing requirement, and list those clarification indices in related_turns; keep additions as separate entries when they can be completed independently. Retain cancelled and replaced entries with active false, status_turn set to the actual change turn, and a user-grounded status_reason. The independent per-turn inventory questions compare the actual turn text with this complete list, so do not omit a direct requirement because it seems minor or was not repeated. Do not turn the agent's plan, assumptions, or implementation choices into user obligations.")

class JevDiscoveredItemPayload(BaseModel):
    """One concrete item found in one recorded tool output and its requested processing evidence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=JEV_DELIVERABLE_ID_PATTERN,
        description="The id is a short stable identifier for this concrete item, written in lowercase letters, digits, and underscores and starting with a letter. It is unique across every discovery output in this finish attempt, including repeated appearances of the same item. Derive it from the item's identity rather than its position in a result list, and preserve it exactly in the inventory and evidence. Keep it under sixty-four characters and do not use source-specific numeric positions as identity when the output provides a stable record, page, issue, or file identifier. This id lets code send a separate recognition question and continuation focus for this item.",
    )
    identity: str = Field(
        min_length=1,
        description="Identity names the specific discovered record, page, document, search hit, issue, file, or other concrete collection member. Include a stable source-provided key or locator when the output has one, and enough title or context to distinguish the item when it does not. Preserve the source's meaningful qualifiers and do not combine sibling items into a range or group. This field identifies what the user asked to be processed, not evidence that processing happened. A checker must be able to find the same item in `source_output` from this description.",
    )
    requested_processing: str = Field(
        min_length=1,
        description="Requested processing states what the user's all-items instruction requires the agent to do to this one discovered item. Derive the action from the original request and the item's kind, without expanding it into extra quality work or weakening an explicit action. Keep the operation and its target together so the evidence can be checked against one item. If the request asks only to inspect or summarize each item, do not claim it asks for edits or external actions. This field is the obligation Jev checks against `processing_evidence`.",
    )
    completion_criteria: str = Field(
        min_length=1,
        description="Completion criteria names the visible result that counts as the requested processing for this item. It must follow the request and be concrete enough to compare with recorded responses, tool calls, and outputs. Include all parts the request requires for this item, but do not infer that an unrecorded action happened. A partial result, an intention, or a summary that gives no visible processing result does not meet the criterion. The same criterion is carried into continuation focus when this item fails.",
    )
    processing_evidence: str = Field(
        min_length=1,
        description="Processing evidence quotes or closely reproduces the parts of the run that show the requested action for this item. Name where each observation came from, such as a response, tool call and result, final answer passage, or command output, and preserve later failures or reversals that affect the latest result. Evidence about a neighboring item does not count unless the output clearly applies to both. A claim that the item was handled is not itself evidence when the requested result should be visible in the run. If no relevant work appears, say so plainly.",
    )
    missing: str = Field(
        min_length=1,
        description="Missing says what the run does not show for this one item's requested processing and gives the main agent an actionable next step. Name the exact operation, output, or result that remains unshown, using the user's scope. Do not repeat the full evidence or add unrelated work. When the evidence shows the requested result in full, state that nothing is missing. This is a handoff note for continuation and is not part of Jev's recognition state.",
    )

class JevDiscoveredItemBatchPayload(JevSectionPayload):
    """The post-run section containing every bounded recorded tool output and the items derived from each."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = (
        "The discovered-item section contains candidate inventories derived after work from recorded tool outputs, with one source id for every tool call, including calls whose output contains no collection. Code retains each bounded raw output directly from the run, so the handoff does not need to reproduce it. Each candidate has its identity, the processing requested by the user, the completion condition, and evidence from the run. Jev checks candidates against the original recorded output and separately checks whether the run shows requested processing for each item. When a recorded output is too large to compare safely or a source id is missing, the check is unavailable and the run is allowed to finish."
    )

    batches: list[JevDiscoveredItemBatchEntryPayload] = Field(
        description="Batches provide one candidate inventory for every tool call in the recorded run, including outputs that show no collection. Each source_id is the stable call id supplied in the context window and must be copied exactly. Code pairs that id with the original raw output, so the handoff does not reproduce, truncate, or summarize source text. Candidates lists every concrete member of a collection visible in that output when the user's request asks to process the collection's members, with one entry per item and no merged or inferred items. When the output contains no such in-scope members, candidates is empty and the source still remains in the batch list. Do not omit an output or state that the inventory is complete; Jev checks the candidate list against the full source output supplied by code."
    )

class JevDiscoveredItemBatchEntryPayload(BaseModel):
    """One source call id and its generated inventory of concrete discovered items."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(
        min_length=1,
        description="The source_id identifies one tool call in the recorded run and must be copied exactly from its context metadata. It is unique within this handoff and follows the chronological order of the calls. Every tool call appears once, whether it discovered items or not. Do not invent or skip identifiers because code compares them with the original call sequence. A mismatch makes this check unavailable rather than validating a partial source set.",
    )
    candidates: list[JevDiscoveredItemPayload] = Field(
        description="Candidates contains one item for each concrete collection member visibly present in source_output that falls under the user's request to process all items. Include source-provided ids or locations in identity, and do not merge several records into one candidate. Do not include links or records merely mentioned as prose unless the request and output make them collection members to process. Use an empty list when this output contains no such collection members, and never use an empty list to conceal a partial or uncertain inventory. The separate inventory question checks whether this list accounts for the full recorded output."
    )

class JevInputExhaustionObligationPayload(BaseModel):
    """One request-derived obligation to exhaust a dynamically discovered input collection."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is a short stable key for one collection traversal obligation. It uses lowercase letters, digits, and underscores, starts with a letter, and is unique within this section. Derive it from the collection's subject rather than a position number. Copy it unchanged into the handoff so each question maps to exactly one obligation. Keep it under sixty-four characters.")
    collection: str = Field(min_length=1, description="The collection names the dynamically discovered or paginated source the user explicitly asks the agent to inspect completely. Preserve the source's own names and distinguish separate collections when the request names them. Do not invent a source, endpoint, or collection that the request does not state or clearly require. Describe the collection itself rather than its individual members. Keep this text stable enough for continuation feedback to identify the same work.")
    scope: str = Field(min_length=1, description="The scope records the extent of this collection traversal required by the user's request. Preserve exhaustive words such as all, every, entire, through the end, and any stated filters or dates. Do not turn a sample or an expressly bounded subset into a request to inspect the full source. Do not widen the request beyond its own terms. This scope tells the handoff and Jev which collection's boundary matters.")
    unit: str = Field(min_length=1, description="The unit identifies what one visited identifier represents when source totals are compared with observed work. It may be a result, record, page, batch, or another collection member named or clearly implied by the request. Use the narrowest unit that can be tied to trace evidence and a source-reported total. Do not mix page totals with record identifiers or otherwise compare unlike units. If the request leaves the unit open, state that it must be identified from the source evidence instead of guessing.")
    expected_total: int | None = Field(ge=0, description="This is a total explicitly stated in the user's request for the named collection and the same unit recorded in `unit`. Copy it only when the request gives a numeric scope such as a stated number of pages, records, or results. Do not estimate or derive a count from examples, samples, or the source's later output. Use null when the request gives no numeric total. Code compares distinct visited identifiers with this requested boundary before using a source-reported total.")
    exhaustion_condition: str = Field(min_length=1, description="The exhaustion condition states the observable stopping rule the user asked for or that the source protocol itself reports. It can describe reaching a known total or receiving a source response that explicitly says there are no more results. Do not treat the absence of another tool call as a stopping rule. Do not create a total, endpoint, cursor, or termination signal absent from the request. Keep this condition narrow enough to decide whether this one collection was traversed fully.")


class JevInputExhaustionPayload(JevSectionPayload):
    """The pre-run section listing explicit obligations to exhaust dynamic input collections."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The input-exhaustion section records each collection the request explicitly requires the agent to traverse completely, where the collection's membership or extent may be discovered during work. It separates these dynamic traversals from finite named inputs that can be checked as individual deliverables. Each entry states the collection, requested scope, traversal unit, any numeric total stated by the user, and the stopping condition that would establish exhaustion. The entries are written from the request before the main agent begins, so they must not invent a source or a universe. When the user states a total, preserve it in `expected_total` so code can compare it with distinct visited identifiers. The handoff later supplies trace evidence for every id in this section, and each id receives one Jev judgment."

    collections: list[JevInputExhaustionObligationPayload] = Field(description="List one stable obligation for each dynamically discovered or paginated collection the request explicitly asks to inspect exhaustively. Preserve separate sources and scopes as separate entries when the request names them. Include the collection, scope, comparable traversal unit, any explicit requested total, and the requested or source-defined stopping condition. Do not add ordinary finite named files or a sample request to this list. Return an empty list when the request has no explicit dynamic exhaustive traversal.")
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

class JevMotivatingScenarioPayload(BaseModel):
    """One request-derived boundary scenario the continuation gate may check."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="A short stable id for this scenario, unique within this section and copied exactly by the handoff. Use lowercase letters, digits, and underscores, beginning with a letter. Keep the id tied to the case, not its position in the list. The same id joins this request-derived definition to evidence written after the agent works. Never rename or reuse an id for a different condition.")
    role: JevScenarioRole = Field(description="The role says whether the request directly centers this condition, separately requests it, or only implies it. Use motivating when the user explicitly says this is the reason for the task. Use requested when the user directly asks for this case without saying it motivates the whole task. Use implied only for a condition inferred from the request but not directly required. Implied entries may be reported but do not block a finish attempt.")
    kind: JevBoundaryKind = Field(description="The kind gives a short category for this unusual situation, such as empty input, a retry, a failure path, or conflicting state. Choose the closest category that describes the condition, not the feature or implementation area. Use other when none of the named categories fits. This label helps organize the report but does not replace the condition text that defines what Jev will judge.")
    source_quote: str = Field(min_length=1, description="The source quote is the exact wording in the user's request that names or implies this scenario. Copy a continuous passage from the request and do not paraphrase it. This quote grounds the scenario in the user’s words and lets code reject invented conditions. Keep punctuation and wording; line wrapping and repeated whitespace may differ. Do not quote the whole request when a shorter passage names the condition.")
    target: str = Field(min_length=1, description="The target says what component, behavior, or operation the case applies to, using the request's own names. A reader should know which part of the work must receive this input or state. Do not invent a target the request does not identify; when the target is implicit, use the nearest named feature. Keep this separate from the condition so the case can be described as applying a condition to a target.")
    condition: str = Field(min_length=1, description="The condition describes the exact input or state that makes this scenario different from ordinary use. State observable values or relationships, including empty, missing, repeated, conflicting, out-of-order, or failed values when the request names them. Keep it specific enough that later evidence can show whether the case was actually constructed or inspected. Do not weaken the condition into a broad phrase such as edge case or unusual input.")
    near_miss: str = Field(min_length=1, description="The near miss is a plausible easier case that resembles this scenario but does not meet its condition. Describe the exact value, state, or behavior that would make the case easier. It gives the checker a boundary example and helps distinguish the requested case from ordinary coverage. Do not use the target condition itself as the near miss, and do not invent an extra requirement for the user.")
    expected_behavior: str = Field(description="Expected behavior is the outcome the request explicitly names for this condition, if it names one. Copy the expected result in the user's terms and keep it observable, such as a returned value, error, state change, or displayed message. Return an empty string when the request gives no expected result rather than supplying a design choice. A later check may require a test or other evidence of that outcome when this field is non-empty.")
    literal_inputs: list[str] = Field(description="Literal inputs are exact values or short strings copied from the request that can help locate a setup or execution in the run. Include only values that identify this scenario, and return an empty list when the request names none. Do not create representative values that the user did not supply. Each value must appear verbatim in the source quote or another part of the request.")
    exercise_mode: JevExerciseMode = Field(description="The exercise mode says what kind of evidence the request permits for this case. Use run when the case needs to be executed, run_or_inspect when either a relevant execution or inspection of the handling code can show it, and inspect_only when the request forbids or cannot require execution. Read explicit testing limits from the request; do not infer a restriction from missing credentials or a difficult environment. This field changes which evidence can satisfy the check.")


class JevMotivatingCasePayload(JevSectionPayload):
    """The motivating-case section of the request-derived run state."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The motivating-case section records unusual input conditions the user's request explicitly asks the agent to handle. Each scenario preserves the user's wording, describes the exact condition and a nearby easier case, and states what kind of evidence may show that the case was handled. The handoff later adds evidence from the current run under the same scenario ids, and Jev checks one scenario at a time. Implied scenarios may be reported for context but cannot hold a run open. Write this section from the user's request alone before the main agent starts work."

    ordinary_flow: str = Field(min_length=1, description="Ordinary flow describes the expected common case of the target feature so the unusual scenario can be distinguished from it. Write a short description grounded in the request and avoid adding implementation details not supplied by the user. The ordinary flow is context for comparison only and is not a substitute for the requested case. Do not copy the near miss into this field unless it truly is the usual path. Keep the description understandable without code knowledge that is absent from the request.")
    testing_restriction_quote: str = Field(description="This field holds exact request wording that forbids or limits running tests or commands, or an empty string when there is no such restriction. Quote the smallest continuous passage that states the limit. Do not infer a restriction from environment limitations, missing tools, or the agent's own caution. Code validates non-empty text against the request so a fabricated restriction cannot make a missing run acceptable. The handoff and question use this only to understand which evidence the user allowed.")
    scenarios: list[JevMotivatingScenarioPayload] = Field(max_length=JEV_MOTIVATING_CASE_MAX_SCENARIOS, description="Scenarios list the user-motivating and separately requested unusual conditions, plus clearly implied cases for context, in request order. Include only cases that change the input, state, timing, access, or failure behavior from the ordinary flow. Give every scenario a unique id and a verbatim source quote; code checks both. Do not turn normal requirements into edge cases or add hypothetical robustness work. Return an empty list when the request names no unusual condition.")


class JevPhaseStagePayload(BaseModel):
    """One outcome stage explicitly required by the request, written before the agent begins work."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is a stable lowercase identifier for one request-required outcome stage. Use letters, digits, and underscores, begin with a letter, and keep it within sixty-four characters. Give each distinct outcome stage a unique id derived from its subject rather than its position. Copy the same id into the handoff evidence entry so the two records can be matched exactly. Do not encode a success verdict, blocker, or priority in the id.")
    stage: str = Field(min_length=1, description="Name the outcome stage in the user's terms, identifying the kind of substantive work the request requires. Use a free-form description derived from this request rather than choosing from a fixed phase taxonomy. Work such as research or analysis is an outcome stage when the user asks to receive research or analysis, even if it could prepare other work in another request. Do not list preliminary actions that only help reach a different requested result as outcome stages. Keep this field short enough to recognize in continuation feedback.")
    required_result: str = Field(min_length=1, description="Describe the transition from preparation into the requested stage and the result the agent must produce or reach within it. Ground the result in an explicit request outcome, not an assumed best practice or an invented workflow. Name an intermediate result only when the request itself requires that result as work. Do not require a later implementation, test, review, or verification stage unless the request asks for it. Preserve the user's scope and qualifiers so partial progress is not mistaken for the whole requested stage.")
    request_scope: str = Field(min_length=1, description="Record the target, boundaries, audience, and quantity that the request attaches to this stage. Keep names, files, sources, products, ranges, and qualifiers in the user's own terms when they are present. Include only scope needed to identify this stage, leaving unrelated request outcomes to their own entries. Do not broaden a narrow instruction or create a new target from general conventions. When the request leaves a boundary open, record that it is unspecified instead of deciding it.")
    output_criterion: str = Field(min_length=1, description="State an observable criterion showing that the requested outcome stage has actually been entered or reached. Describe the substantive result or action the run must show, not planning, promises, or preparation that merely precedes it. Accept a final answer as the output when the requested stage itself is an answer, report, comparison, or recommendation. Do not require a separate artifact or verification result unless the request names one. A concrete blocker or exhausted budget belongs in the handoff evidence and is handled as a stopping condition, not as a result criterion.")


class JevPhaseProgressPayload(JevSectionPayload):
    """The phase-progress run-state section: only outcome stages the request itself requires."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The phase-progress section identifies substantive outcome stages that the user's request requires, so the finish check can see whether the run moved beyond preparation into the requested work. It is written once from the request before the main agent starts and cannot be revised to fit what the run later did. Stage names and results come from the request rather than a fixed list of work phases. A requested research or analysis result remains an outcome even when similar activity could serve as preparation for a different request. Return an empty stages list when no meaningful transition into a requested outcome can be identified."
    stages: list[JevPhaseStagePayload] = Field(description="List each distinct substantive outcome stage that the request requires, in request order, with one entry per independently judgeable stage. Keep preparation steps out when they only gather context or plan how to produce a later requested result. Include research, analysis, planning, verification, or other activity as an outcome only when the user asks for that activity or its result. Preserve separate stages when the request requires them independently, but do not split one outcome into mechanical substeps. Return an empty list when the request has no meaningful staged outcome to check.")


class JevPhaseStageEvidencePayload(BaseModel):
    """The run evidence and separate actionable gap for one request-required outcome stage."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id must exactly match one stage id from the phase-progress run state. Copy it character for character, preserving the original request order. Provide one evidence entry for every state stage, including a stage with no related activity. Do not invent an id for unrelated run activity or omit a stage because the run did nothing on it. The id links one Jev judgment and one continuation focus line to the same requested outcome.")
    evidence: str = Field(min_length=1, description="Compile the observed run material that bears on whether the stage was entered or reached, including responses, tool calls and outputs, command results, and the final answer. Identify what was preparatory and what, if anything, performed or produced the request-required stage. Report the sequence and latest state faithfully, including failures, removed results, and evidence that the work remained actionable. Include direct evidence of a genuine blocker or exhausted budget, such as a tool or runtime result, while treating a bare claim of being blocked as a claim rather than corroboration. Never decide that the stage passed or include the separate missing judgment in this field.")
    missing: str = Field(min_length=1, description="State in plain actionable language what the run does not show about this requested outcome stage. Identify the missing transition or result by reference to the stage's required result and output criterion. Distinguish a voluntary finish after preparation from an observed blocker or exhausted budget, and do not call a reported but unsupported constraint genuine. Do not require verification, artifacts, or later work that the request did not ask for. When the evidence shows the stage or a concrete blocking condition, say that nothing remains actionable for this stage.")


class JevPhaseProgressEvidencePayload(JevSectionPayload):
    """The phase-progress handoff section: observations for every outcome stage listed before work began."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The phase-progress evidence section gathers what the actual run shows about every outcome stage from the run state. It lets a separate checker distinguish preparatory activity from the work the user requested without inferring a universal workflow. The checker sees only each stage's request-derived identity and criteria plus the evidence written here. Each entry reports observations and a separate missing note for the main agent, never a Jev verdict. Compile it after every finish attempt from the current run window, including its latest answer and any failures or blockers."
    stages: list[JevPhaseStageEvidencePayload] = Field(description="Return one evidence entry for each phase-progress stage in the run state, with exactly matching ids and request order. Report the activity that occurred and whether it remained preparatory or reached the requested stage's observable criterion. Include evidence of a concrete constraint when it prevented further progress, and separate that from the agent's own statement that it cannot continue. Keep the missing note useful to the main agent but do not copy it into Jev's state projection. Return an entry even when the run contains no work related to that stage.")
class JevInputTargetPayload(BaseModel):
    """One explicitly bounded input target and the requested action to perform on it."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is a unique lowercase identifier for this one input target. Derive it from the target identity using letters, digits, and underscores. Keep it stable when the handoff repeats the target. Do not merge independently requested targets under one id. This id is how code joins one question and one evidence record to the obligation.")
    identity: str = Field(min_length=1, description="The identity names the exact input or finite group the user asked the agent to engage. Copy the names, keys, category labels, source names, or membership rule that define it. It comes from the user's request, not from what the agent later happened to inspect. Do not add members based on convention or guesswork. This identity lets evidence be matched to the intended input rather than a similarly named one.")
    scope: str = Field(min_length=1, description="The scope states the complete explicit boundary that applies to this target. Preserve requested extent, category, date bounds, exclusions, and completeness words such as all, each, or whole. It comes from the user request and must not be narrowed to fit the available evidence. When no additional boundary is stated, describe the target itself as the full scope. This field determines how much evidence Jev must see before recognizing engagement.")
    action: str = Field(min_length=1, description="The action states what the user asked the agent to do with this input. Use the request's meaning, such as read, inspect, review, compare, or process. Do not substitute an output the user requested for the action on the source. Do not add a stronger action than the request states. The action determines what kind of recorded operation and output can count as engagement.")
    engagement_signal: str = Field(min_length=1, description="The engagement signal describes observations that would show the requested action over the complete scope. It is derived from the user's wording and the input type, not from later claims of completion. Distinguish content access from locating a path or listing a title. Match the depth requested, so a preview does not stand for a full review. Jev uses this signal with the request, target, scope, and evidence to recognize whether engagement occurred.")


class JevInputSetCoveragePayload(JevSectionPayload):
    """The request-derived, explicitly bounded input targets this check requires the run to engage."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The input-set coverage section lists each distinct input target the user explicitly bounded and asked the agent to read, inspect, review, compare, or process. Include finite named targets and finite user-defined scopes, including all members when the request explicitly requires every member of a known bounded set. Do not turn an open-ended or dynamically paginated collection into guessed targets; those are outside this check. Extract these obligations from the user's request before work starts, preserve stable ids, and state the requested action, target identity, scope, and observable engagement signal for each. This section concerns inputs the agent must engage, not outputs it must create. Return an empty list when the request contains no explicitly bounded input-engagement obligation."

    targets: list[JevInputTargetPayload] = Field(description="The targets are separate input-engagement obligations the request explicitly bounds. Preserve their order from the request and split independently named inputs so each receives a separate evidence judgment. A single finite category or range may remain one target when its membership rule is fully stated. Do not add inputs only implied by good practice or guess members of an unknown collection. An empty list means no explicit bounded input-engagement obligation was requested, and no Jev question is asked for this check.")
class JevOutputCountObligationPayload(BaseModel):
    """One explicit numeric quantity required inside a requested output or group."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="A stable lowercase identifier unique among output-count obligations. It names the output or group rather than its position. Copy it unchanged into the handoff so code can match evidence back to request state. Use only letters, digits, and underscores, starting with a letter. Do not combine independent quantities under one id.")
    description: str = Field(min_length=1, description="Describe the output quantity the user asked for, preserving the user's scope and wording. Include the group or category when the quantity applies per group. Do not add another output obligation or turn an example into a requirement. A reader should know which requested output this count belongs to. This is request context, not evidence that any output exists.")
    target_count: int = Field(ge=1, description="The exact positive integer the request requires for this scope. Copy an explicit number from the request and do not estimate, round, or substitute a default. A per-group quantity has one obligation for each group, with its own target. Do not infer a target from examples or from how much work appears reasonable. This is the deterministic threshold used to interpret the handoff count.")
    distinct: bool = Field(description="Set true when the request requires different items rather than repeated instances, including a request whose meaning clearly requires distinct results. Set false only when repetitions are valid under the user's wording. This is a classification of the request, not a judgment about completed output. Deterministic code uses this flag when deriving the observed count. Jev still checks the candidate values and keys against the textual distinctness rule.")
    unit: str = Field(min_length=1, description="Name the kind of output unit being counted, such as entries, examples, files, sections, or words. Preserve a more specific unit when the request defines one. Do not mix different unit kinds in one obligation. The unit explains how observed entries correspond to the target. It does not establish that entries were produced.")
    scope: str = Field(min_length=1, description="State the exact output or group within which this quantity applies. Preserve group names, topics, destinations, formats, and other boundaries from the request. For quantities requested separately in several groups, keep each group's scope distinct. Do not widen a group or count entries from sibling groups toward it. This scope limits the evidence Jev may recognize.")
    distinctness: str = Field(min_length=1, description="State whether the request requires distinct items and what makes two entries distinct, using the user's stated meaning. When distinctness is not required, say that repetitions count only if the request permits them. Do not invent a semantic distinction the request does not imply. The handoff proposes stable distinct keys and code counts unique keys; Jev checks whether entries and keys fit this rule. This is a rule, not proof that the target was reached.")
    completion_criteria: str = Field(min_length=1, description="Describe the visible output condition that satisfies the numeric obligation. Include its exact target, unit, scope, and distinctness rule without adding unrelated quality requirements. State what final-answer or artifact evidence can establish that the quantity exists. Do not treat a final-answer claim, plan, or count label alone as proof. This criterion keeps evidence interpretation consistent.")


class JevOutputCountPayload(JevSectionPayload):
    """Request-derived section containing every explicit numeric output obligation."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The output-count section records explicit numeric quantities inside requested outputs, including quantities scoped per topic or group. Each obligation preserves its target, unit, scope, and distinctness rule so the handoff can gather matching evidence. It complements the separate-deliverable section: one deliverable can contain several count obligations, while its existence alone does not satisfy its requested quantity. Extract obligations from the user's request before work starts, even if the final answer never claims a count. Return an empty list when no explicit output quantity is requested."
    obligations: list[JevOutputCountObligationPayload] = Field(description="List one entry for every explicit numeric quantity required within a requested output, in request order. Split independent group quantities so one group's entries cannot satisfy another group's target. Include requested counts of files, examples, records, words, sections, or other output units when the request makes the target explicit. Do not duplicate an obligation already represented by a separate output unless the quantity applies within that output. Return an empty list when the request specifies no numeric output quantity.")


class JevOutputCountEntryPayload(BaseModel):
    """One candidate output unit and the run evidence that shows it exists."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="A stable identifier for one candidate unit within its obligation. It is not reused for another unit. Do not use ids to inflate the count by listing one unit more than once. The id is only a reference and does not prove that the unit exists. Keep entries in the order they appear in the output.")
    value: str = Field(min_length=1, description="Reproduce or identify the candidate output unit closely enough to judge whether it belongs to the requested scope. Preserve content that matters to the unit's identity and meaning. Do not hide possible repetition in a broad summary. A candidate must be visible in the final answer, an artifact, or a successful recorded operation. Plans and assertions that an item exists are not candidates.")
    distinct_key: str = Field(min_length=1, description="Provide the stable key deterministic code uses to count distinct candidates. Candidates that represent the same requested item must use the same key, including semantic duplicates with different wording when distinct results are required. Distinct candidates must use different keys. Normalize only differences that do not make a new requested item. Jev receives the candidate values and keys to recognize whether grouping follows the obligation's distinctness rule.")
    evidence: str = Field(min_length=1, description="Identify where this candidate appears in the run and quote enough surrounding content to verify it. Cite a final-answer passage, artifact path and content, or successful tool output as appropriate. Preserve failures and later edits that remove or replace the candidate. Do not use the handoff's own conclusion as evidence. If no run evidence shows the candidate, do not include it as an entry.")


class JevOutputCountEvidencePayloadItem(BaseModel):
    """Evidence candidates associated with one output-count obligation id."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id exactly matches one output-count obligation in run state. It is copied unchanged so code can reject missing, duplicated, or invented obligation evidence. It names the quantity being evidenced, not an individual candidate. Provide one record per obligation in original order. Do not omit an obligation because no work was done for it.")
    entries: list[JevOutputCountEntryPayload] = Field(description="List observed candidate units for this obligation in output order. Include repeated candidates when visible and assign the same distinct key when they represent one item under the obligation's rule, so code does not count them twice. Each entry needs content and direct run evidence. Do not add candidates that appear only in plans, summaries, or handoff analysis. Return an empty list when no candidate unit is visible.")
    missing: str = Field(min_length=1, description="Describe the gap between requested quantity and visible output in plain, actionable terms. This summary is for the continuation message and is never supplied as Jev evidence. Name the group and quantity still missing when determinable. Do not claim completion based on a count or final-answer assertion. Write a concise sentence even when evidence appears complete.")


class JevOutputCountEvidencePayload(JevSectionPayload):
    """Handoff section listing countable output units for each request-derived quantity obligation."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The output-count evidence section lists candidate output units observed in the run for every obligation from run state. Each candidate includes content, a distinctness key, and the run evidence where it appears; code derives the observed distinct count from those keys. The section covers the original request's quantity even when the final answer says nothing about how many items it produced. Candidate selection and distinct-key assignment prepare evidence and are not a completion verdict. The handoff must represent partial work faithfully and never rely on its own missing summary as proof."
    obligations: list[JevOutputCountEvidencePayloadItem] = Field(description="Provide one evidence record for every output-count obligation in run-state order. Keep candidates inside the exact obligation scope and include every visible qualifying unit, including repeats that code can exclude by shared distinct key. Preserve candidate content and source evidence so Jev can recognize relevance and distinctness. Do not let entries from other groups satisfy this obligation. An empty entries list means no candidate output unit is shown for that obligation.")


class JevRequiredActionPayload(BaseModel):
    """One explicitly requested procedure or action the required-actions check will verify."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this required action a short stable id in lowercase letters, digits, and underscores, starting with a letter and no longer than sixty-four characters. Derive the id from the requested action or its target rather than from its position in the list. Keep every id unique in this request and copy it unchanged into the handoff and Jev question name. Do not change an id between finish attempts because the run-state list is written once. The id connects the explicit request, its evidence, its answer, and any continuation focus.")
    action: str = Field(min_length=1, description="Describe one action or procedure the user explicitly requires, using the user's words and naming its target. Keep it distinct from the output the action may help produce, because producing an output is checked separately. Include a tool, operation, review, phase, retry, or delegation only when the request states that requirement. Do not add conventional or merely helpful steps that the user did not request. Each entry describes exactly one required action so it can receive one Jev judgment.")
    completion_signal: str = Field(min_length=1, description="State the observable condition in the run that would show this exact action was successfully completed. Include the successful result that the user asked for, such as a completed review, a tool result, a classification, a returned delegation result, or a resolved failure. A call attempt, plan, intention, failed result, unanswered delegation, or final-answer claim by itself is not successful completion. Keep this condition within the action's stated target and scope. Do not require extra work or stronger proof than the request states.")
    predecessors: list[str] = Field(description="List the ids of actions that the user explicitly requires to happen before this action. Preserve a stated sequence or dependency, but do not infer an order from a generally sensible workflow or from the order in which actions appear in the request. Use an empty list when the user states no prerequisite for this action. Every listed id must identify a different action in this same section and must precede this item in the section. This field makes explicit dependencies available to deterministic code without asking Jev to reason across several actions.")


class JevRequiredActionsPayload(JevSectionPayload):
    """The run-state section of required actions explicitly named in the request."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The required-actions section records procedures and actions the user explicitly requires the agent to perform, so a plausible final answer cannot conceal skipped work. It describes one action at a time, with its target, successful observable completion condition, and only the dependencies the user explicitly ordered. This section is not a plan and does not expand the request into every step that might be useful. Read the request before deciding whether an action is truly required, and omit ordinary helpful work the user did not specifically require. Fill the section from the request alone before the main agent begins its work."

    actions: list[JevRequiredActionPayload] = Field(description="List each distinct action or procedural obligation the user explicitly states, preserving request order except where a stated dependency requires putting its predecessor first. Include required reviews, named operations or tools, prescribed phases, requested delegation and result return, and a required retry or resolution only when the request says so. Do not infer procedures from best practice, from the requested output, or from what an agent would usually do. Record a predecessor only when the user explicitly says one action follows or depends on another, and leave predecessors empty otherwise. Return an empty list when the request names no action or procedure beyond producing an answer or output.")


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

class JevCumulativeObligationEvidenceEntryPayload(BaseModel):
    """Run evidence and status context for one cumulative obligation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is copied exactly from one obligation in the run state's cumulative-obligations section, whether active or explicitly inactive. Every obligation gets exactly one evidence entry. Do not rename, merge, or invent ids because the caller matches this evidence back to the user instruction. Keep entries in the same first-request order as all obligations.")
    evidence: str = Field(min_length=1, description="The evidence is what the main agent's run shows about this exact obligation. Quote or closely reproduce relevant response text, tool calls with arguments and outputs, and the final answer in the order they occurred. Include failed attempts and later corrections, and report the latest state without claiming that a user obligation was cancelled. When nothing in the run concerns the obligation, say so directly.")
    missing: str = Field(min_length=1, description="For an active obligation, name the parts the evidence does not show or shows were not completed, using the instruction and completion signal to identify the remaining answer, artifact, condition, or detail. For an inactive obligation, say whether the run shows any relevant work but do not judge whether the user actually cancelled it; Jev compares the status reason and status_turn with the supplied messages. Do not mark work as cancelled because the main agent omitted it or later user turns did not repeat it. When an active obligation's evidence shows every part in its latest state, say that nothing is missing.")

class JevCumulativeUserTurnEvidenceEntryPayload(BaseModel):
    """Observed run material associated with one supplied user turn, without a completion judgment."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is `turn_` followed by the zero-based index of one supplied user turn, such as `turn_0`. Include exactly one evidence entry for every turn in `user_turns` and preserve their order. Do not omit a turn because no work addressed it; state that no relevant run material was found. The numeric suffix must match that message's zero-based position in the supplied list exactly.")
    evidence: str = Field(min_length=1, description="Record observations from the current main-agent run that may bear on requirements in this user turn: relevant response passages, final-answer text, tool calls with arguments and outputs, and command or test results, in their run order. Quote or closely reproduce the actual observed material and identify where it appeared. Include failed attempts and later changes. Do not decide whether a user requirement was represented, fulfilled, cancelled, or missing; do not infer an action or result that the run did not show. When no run material bears on this turn, say so directly. This is a generative evidence summary and may omit observations; the Jev question must judge only the evidence actually reported here.")

class JevCumulativeObligationEvidencePayload(JevSectionPayload):
    """Evidence compiled for each obligation that remains active in the supplied user history."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The cumulative-obligation evidence section gathers what the main agent's run shows for every obligation in the run state, including entries marked inactive, and separately records observed run material for every supplied user turn. Obligation entries are paired with the exact instruction and completion signal they concern. Per-turn entries gather observations that may show whether a requirement omitted from the obligation list was nevertheless completed. These are observations only, never a completion or cancellation verdict."

    obligations: list[JevCumulativeObligationEvidenceEntryPayload] = Field(description="The obligations list contains one evidence entry for every obligation in the run state's cumulative-obligations section, with the same ids and order. For an active obligation, report only observations that bear on it and state what remains unshown. For an inactive obligation, report the user wording that supposedly cancelled or replaced it so the checker can compare that reason with user_turns. Repeat shared evidence when it independently supports more than one obligation, but do not use evidence for one to stand in for another. Include an entry even when the run did nothing toward an active obligation.")
    turns: list[JevCumulativeUserTurnEvidenceEntryPayload] = Field(description="The turns list contains one observation entry for every exact supplied user message and the current request, with ids `turn_0`, `turn_1`, and so on in the same order as `user_turns`. Gather current run material that may bear on any direct requirement in that turn, even if the obligation list has no corresponding entry. Include actual response text, final answer passages, tool arguments and outputs, and command or test results; retain failures and later changes. This field reports only what the run shows and does not decide whether a missing requirement was fulfilled. Never leave a turn out or infer that work happened because it was requested.")

class JevInputExhaustionEvidencePayload(BaseModel):
    """Trace observations JevHandoff compiles for one collection traversal obligation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is copied character for character from one input-exhaustion run-state obligation. Every expected obligation gets exactly one evidence entry, including one with no traversal activity. Do not rename, merge, omit, or invent ids. This key lets code compare the handoff with the pre-run obligation list. Keep its order the same as the run-state entries.")
    evidence: str = Field(min_length=1, description="The evidence quotes or closely reproduces relevant observations from the main agent's actual responses, tool arguments, tool outputs, and final answer. Name the source of each observation and keep events in the order they occurred, including retries, failures, and later progress. Include only facts present in the trace and distinguish source-reported values from the agent's statements. Do not use a final-answer claim or this handoff's missing summary as proof of traversal. If the trace contains no relevant activity, state that explicitly.")
    unit_type: str | None = Field(description="The unit type names what each listed visited identifier represents, such as a result, record, page, or batch. It must match the comparable unit in the obligation before code compares the identifier count with a reported total. Derive it from explicit trace evidence rather than guessing from a tool name. Use null when the trace does not establish a comparable unit. A mismatch or unknown value cannot prove count-based exhaustion.")
    visited_unit_ids: list[str] = Field(description="List distinct identifiers for collection members that the trace shows the agent actually retrieved or processed. Use source identifiers where available and stable page or batch identifiers only when those are the unit being compared. Do not count a requested unit, a search snippet, a failed retrieval, a repeated identifier, or an unverified handoff claim as visited. Preserve identifiers exactly and use an empty list when no unit is trace-backed. Code deduplicates these values before comparing a source-reported total.")
    source_reported_total: int | None = Field(ge=0, description="This is a numeric total that a source response in the trace explicitly reports for the same `unit_type` as the visited identifiers. Copy the number only when the output states it as the total for this collection and unit. Do not calculate a total from samples, page counts, estimates, or the agent's unsupported summary. Use null when no comparable source-reported total appears. A present total is compared deterministically with distinct visited ids, and it does not cancel a failed fetch or open continuation.")
    last_position: str | None = Field(description="The last position records the latest page, cursor, offset, batch, or member identifier that a successful trace event shows the agent reached. Quote the concrete value and identify its kind when possible. Do not infer a position from the order of tool calls alone. Use null when no successful traversal position is visible. Continuation feedback uses this field to tell the main agent where to resume.")
    outstanding_continuation: str | None = Field(description="This field records a next-page link, cursor, token, offset, continuation marker, or other source instruction still present in the latest successful response. Include the exact value or a faithful short excerpt and identify its source response. Use null only when the latest trace evidence explicitly shows no outstanding continuation or the source explicitly marks its end. Do not use null merely because the agent made no later request. A non-null value is evidence that traversal has not ended.")
    terminal_evidence: str | None = Field(description="This field contains a source response or tool output that affirmatively marks the end of the requested collection, such as an explicit end-of-results signal or a protocol response with no next position. Quote or closely reproduce the signal and identify its source. Do not treat a first page, a sample, a search snippet, a failed call, or silence about a next page as terminal. Use null when the trace has no affirmative end signal. Jev may recognize whether the supplied signal establishes the stated exhaustion condition, but it must not invent one.")
    failed_retrievals: list[str] = Field(description="List each retrieval of a requested collection unit that failed, timed out, was rejected, or returned no usable result and remains unresolved, with the unit or position and the trace output. Exclude a failure when a later successful retry shows that same unit was retrieved, but retain every attempt in `evidence`. Use an empty list when no unresolved collection retrieval failed. A listed failure is evidence that the traversal obligation remains incomplete. Never describe a failed attempt as a visited unit.")
    missing: str = Field(min_length=1, description="The missing field tells the main agent which requested traversal evidence or collection work remains absent, based on the current trace and the run-state obligation. Name the unvisited units when the source identifies them, or the exact unresolved boundary such as an outstanding cursor or missing terminal response. Give a concise gap rather than restating all evidence. When a known count matches and no continuation or failure remains, say that no traversal gap is shown. This field is for continuation feedback and is never included in Jev's state.")
    next_step: str = Field(min_length=1, description="The next step gives the main agent one actionable continuation instruction grounded in the latest trace position or gap. When a cursor, page, or offset remains, name how to resume from that value; when a retrieval failed, retry or recover that specific unit; when neither is known, identify the evidence needed to establish the source's end. Do not ask for work outside the run-state scope. If no work is missing, state that no next traversal step is indicated.")


class JevInputExhaustionEvidenceSection(JevSectionPayload):
    """The handoff section pairing each dynamic traversal obligation with trace observations."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The input-exhaustion evidence section reports what the current run trace shows for every dynamic collection obligation in run state. For each collection it preserves source evidence, distinct visited unit identifiers, any comparable source total, the latest position, any outstanding continuation, terminal evidence, and failed retrievals. Code adds a deterministic count comparison when the total and unit type are comparable, while Jev recognizes whether the supplied evidence establishes the stated exhaustion condition. The handoff reports observations and an actionable missing note but does not decide that a collection is exhausted. A readable handoff without completion evidence remains incomplete and can trigger a continuation; only missing or malformed evidence is unavailable. The missing note is reserved for continuation feedback and is excluded from Jev's state."

    collections: list[JevInputExhaustionEvidencePayload] = Field(description="Return one evidence entry for every input-exhaustion obligation in the run state, using the exact same ids and order. Include all trace-backed traversal evidence and preserve failures, latest cursors, source totals, and affirmative terminal signals without turning silence into an end marker. Never omit an obligation because the main agent did nothing for it. Do not add collections the run state did not request. Write the missing note and next step for the main agent, not as a verdict for Jev.")


class JevNegativeCoverageTargetPayload(BaseModel):
    """One research, audit, review, testing, or source-inspection target requested by the user."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is a short stable identifier for this requested inspection target, using lowercase letters, digits, and underscores. It must be unique among the targets and is copied exactly into the handoff so one question addresses this target alone. Derive it from the target's subject instead of its position in the list. Keep it under sixty-four characters. Never use this id to add a target the user did not ask to inspect.")
    target: str = Field(min_length=1, description="The target names the file, source, subject, system, test selection, or other thing the user asked to inspect. Preserve the exact breadth and qualifiers in the request, including 'all', named subsets, or specified versions. Include enough context to recognize what material counts as this target. Do not turn a request for inspection into a request to produce any particular finding. Do not include unrelated targets.")
    inspection_signal: str = Field(min_length=1, description="The inspection signal says what visible action or evidence would show that this target was actually inspected. Ground it in the user's request and the kind of target, such as reading the named source, running the requested tests, or examining the specified material. It describes evidence of review, not a successful result or a non-empty finding list. Keep the requested scope intact, so evidence about a sample does not show inspection of an entire target. This signal guides the handoff writer and does not itself prove that inspection happened.")


class JevNegativeCoveragePayload(JevSectionPayload):
    """The request-derived targets whose no-findings conclusions need inspection evidence."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The negative-coverage section lists targets the user explicitly asked the agent to inspect, such as research subjects, audit scopes, review targets, tests, or source files. The later done check focuses on a narrow reporting risk: saying or implying that a requested target has no findings or is clear when the run does not show that it was inspected. It also checks an explicit report that a requested inspection remains incomplete, so the continuation can ask the agent to finish it. A target is an inspection subject, not a required finding, and an empty findings list is a valid outcome when supported by inspection. Fill this section from the request before the main agent starts, and do not add work that the request does not ask to inspect."

    inspections: list[JevNegativeCoverageTargetPayload] = Field(description="The inspections list contains one entry for each distinct target the user directly asks the agent to examine, review, audit, research, inspect, or test for findings. Keep separate targets separate when inspecting one does not establish that another was inspected. Combine only repeated references to the same target and preserve the broadest scope the user actually requested. Exclude ordinary implementation deliverables and targets mentioned only as background unless the request asks for their inspection. Return an empty list when the request asks for no inspection.")


class JevNegativeCoverageEvidencePayload(JevSectionPayload):
    """The run evidence and final-answer conclusion associated with each requested inspection target."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The negative-coverage evidence section reports, for every requested inspection target, what the final answer says about findings and what the run shows about actually inspecting the target. It exists to catch an unsupported all-clear conclusion when the user asked for inspection, while allowing a properly inspected target to have no findings. It also records when the answer honestly says that inspection was not completed, because that requested work remains a useful continuation focus. The section contains observations from the run and the answer, not a verdict about whether the done check should pass. Include every target from the run-state section, even when the agent did no inspection and reported no conclusion."

    inspections: list[JevNegativeCoverageEvidenceItemPayload] = Field(description="The inspections list has exactly one entry for every target in the run state's negative-coverage section, with the same ids and order. Each entry quotes or closely describes any no-findings, all-clear, or incomplete statement in the final answer and separately reports run evidence that the requested target was examined. Include command, test, tool, source, or answer evidence only when it visibly bears on that target and requested scope. An empty finding result is not evidence that an inspection occurred. Never omit a target or borrow inspection evidence from a different target.")


class JevNegativeCoverageEvidenceItemPayload(BaseModel):
    """One target's inspection evidence, absence conclusion, and explicit incompletion report."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is copied exactly from one request-derived inspection target. It connects this evidence to the single target Jev judges. Every requested inspection target must appear once, in order, and no other ids are permitted. Do not invent an id or rename one to fit the final answer. This field associates evidence but does not decide whether it is sufficient.")
    inspection: str = Field(min_length=1, description="Inspection describes the run evidence that shows whether the requested target was actually examined. Cite visible tool calls, opened or quoted source, test commands and results, retrieved material, or another concrete observation in the recorded run. State plainly when the run shows no inspection evidence for this target. A result that says zero findings counts only when there is also evidence that the target was examined at the requested scope. Do not treat a plan or promise to inspect as an inspection.")
    negative_conclusion: str = Field(description="The negative conclusion quotes or closely describes any final-answer wording that says or implies there were no findings, no issues, nothing notable, an all-clear result, or that the target was clean. Include only the target's conclusion and preserve qualifiers such as 'in the files checked' or 'based on the sample'. Use an empty string when the final answer makes no such conclusion for this target. Do not infer a negative conclusion merely from silence or from a missing list of findings. The wording is evidence of what was reported, not evidence that the inspection happened.")
    incomplete_report: str = Field(description="The incomplete report quotes or describes a final-answer statement that the requested inspection was not performed, was only partly performed, or remains blocked or unfinished. Preserve which part of the target remains unchecked and any stated limitation. Use an empty string when the answer does not explicitly report incomplete inspection. Do not confuse an honest incomplete report with an all-clear conclusion. This field helps continuation finish work the user asked for and is not evidence that the target was inspected.")
    missing: str = Field(min_length=1, description="Missing states the gap between the requested inspection signal and the inspection evidence visible in the run. Name the target portion, source, test, or review action that lacks evidence, and say when nothing is missing. Do not ask the agent to manufacture a finding or change an evidence-supported empty result. Keep this note actionable for continuation and faithful to the request's scope. This is the handoff writer's own summary and is kept out of Jev's evidence fields.")


JevNegativeCoverageEvidencePayload.model_rebuild()
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
class JevInputTargetEvidencePayload(BaseModel):
    """Successful and unsuccessful observations about one requested input-engagement obligation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id is copied character for character from one run-state input target. Every run-state target must have exactly one evidence record with the same id. Do not add, omit, merge, or rename targets. This stable key joins each evidence record to the matching Jev question. The handoff is unavailable if its ids do not match the request-derived list.")
    evidence: str = Field(min_length=1, description="The evidence reports recorded tool calls and outputs that bear on this target, in run order. Quote or closely reproduce the output that shows what content was actually available or what operation completed. Include failed attempts when they explain why the requested extent is absent. Distinguish full content from a listing, metadata, or excerpt. When there is no relevant call, state that the run contains no evidence for this target.")
    missing: str = Field(min_length=1, description="The missing field names what the evidence does not show for this target. Identify the requested action, scope, or depth still uncovered in plain language the main agent can act on. This is a handoff writer's feedback field, not evidence about the run. Jev must never receive this value in its state, because it is already a generated judgment. If the evidence shows the entire requested engagement, say that nothing is missing.")


class JevInputSetCoverageEvidencePayload(JevSectionPayload):
    """The handoff evidence for each request-derived bounded input target."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The input-set coverage evidence section records what the main agent's tool calls and outputs show for each target listed in the run state's input-set coverage section. It must preserve exact target ids and include all targets, including those with no work or only failed attempts. Report observations at the depth the request asks for: locating a path is not reading its content, a listing is not reviewing each member, and an excerpt is not full-document review unless the request asks only for an excerpt. The section is evidence for a later recognition question and does not decide whether coverage is adequate. The separate missing field is used only to focus continuation feedback and is excluded from Jev's evidence state."

    targets: list[JevInputTargetEvidencePayload] = Field(description="The targets contain exactly one evidence entry for every target in the run-state section. Preserve the target order and copy each id exactly so deterministic code can validate the correspondence. Gather only observations that relate directly to that target, and repeat an observation only when the recorded operation truly covers multiple targets. Include successful and failed call results and state any uncovered extent in `missing`. The handoff is unavailable when any target is omitted, added, renamed, or reordered from the run-state list.")


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


class JevRequiredActionEvidencePayload(BaseModel):
    """Trace evidence for one explicitly required action, including indices of cited tool calls."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Copy the exact id of one action from the run-state required-actions section. Return one evidence entry for every action, even when the run contains no related event. Do not add an id that the run state does not contain, and do not rename or merge action ids. Keep the entries in the same order as the run-state actions so each one maps back without inference. The id is used to find the evidence, Jev answer, and continuation focus for this action.")
    evidence: str = Field(min_length=1, description="Quote or closely reproduce direct observations from the run that bear on successful completion of this action. Include relevant tool names and arguments, call execution states and outputs, command or test results, and observable delegation or returned-result evidence, with the source and trace-call index named. Preserve successful and failed attempts in their run order, and state when the run contains no relevant evidence. A call attempt, a plan, a final-answer assertion, or a summary is not itself proof that the requested action succeeded. Report observations only and do not give a completion verdict.")
    trace_indices: list[int] = Field(description="List the zero-based indices of tool calls in the supplied trace that directly support this action's evidence. The trace labels each tool call with its index, and the indices must be copied exactly rather than estimated or renumbered. Include failed attempts when they are relevant, and include a later successful call separately when one exists. Return an empty list when no tool call directly supports the action, even if the final answer discusses it. Code uses these exact indices only to enforce an order the user explicitly requested, not to decide whether a call succeeded.")
    completion_trace_index: int | None = Field(description="Give the zero-based trace index of the successful tool call that directly shows this action's completion, when such a call exists. The index must also appear in `trace_indices` and must refer to a call whose recorded state is succeeded. Use null when the recorded run has no successful tool call that directly shows completion, including when it shows only an attempt, a failure, or words in the final answer. Do not choose an earlier failed call when a later call is the one that completed the action. Deterministic code uses this field only for explicit user-stated ordering, while Jev judges whether the cited evidence meets the action's completion condition.")
    output_source: str | None = Field(default=None, description="Name the actual main-agent response or final-answer section that contains a substantive output proving this action, when one exists. Use `response[n]` with the zero-based response index, or `final_answer` for the final answer; do not cite a sentence that merely claims or summarizes completion. The cited source must contain the exact excerpt copied into `output_excerpt`, so code can check that the output is really present. Use null when no direct output excerpt supports the action. An empty source or an unsupported source name is not direct evidence.")
    output_excerpt: str | None = Field(default=None, description="Copy a concise, exact excerpt of substantive output from the source named in `output_source`, such as the actual classification table, analysis, or requested written result. Do not copy a sentence that only says the action was done, is complete, or will be done. The excerpt must appear verbatim in the recorded response or final answer, which code validates before it can count as evidence. Use null when the run contains no substantive output excerpt for this action. This field supplements tool evidence and cannot substitute for a successful trace index when the user explicitly required an observable order.")
    missing: str = Field(min_length=1, description="Tell the main agent what successful part of this requested action the run does not show, in words it can act on. Name a missing review, operation result, classification, returned delegation result, or resolution when that is the stated completion condition. A failed attempt remains missing until the run shows the requested successful result. Do not repeat the evidence or request additional actions the user did not ask for. When the evidence shows the action completed, say that nothing is missing.")


class JevRequiredActionsEvidencePayload(JevSectionPayload):
    """The handoff section with trace evidence for every explicitly required action."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The required-actions evidence section gathers what the run directly records for each action listed before work began. A separate checker reads one action and its successful completion condition beside only the evidence gathered for that action. The handoff has access to the main agent's ordered tool calls, including their arguments, state, and outputs, along with responses and the final answer. It must identify the exact tool-call indices when citing calls so code can enforce an explicitly requested order. This section reports observations and actionable gaps, never a verdict, and is compiled anew at each finish attempt."

    actions: list[JevRequiredActionEvidencePayload] = Field(description="Return exactly one evidence entry for each action in the run state's required-actions section, keeping the same ids and order. Quote direct trace observations, including successful command or test output and returned delegation results when they bear on an action. List the exact trace-call indices supporting each action, or an empty list when no call supports it. Preserve failures and unsuccessful attempts so a call that did not complete the requested action cannot look successful. Do not omit an action because the run has no evidence for it, and do not create requirements or evidence beyond the run state and trace.")


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


class JevMotivatingScenarioEvidencePayload(BaseModel):
    """The current run evidence and actionable gap for one motivating scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="The id exactly matches one scenario from the run state's motivating_case section. Keep every id character-for-character so the checker can join the evidence to the definition it concerns. Include every scenario once, including cases with no related work. Do not add or merge scenarios, and keep entries in the same order as the run state. The id is only a reference and carries no judgment about whether the work succeeded.")
    evidence: str = Field(min_length=1, description="Evidence reproduces the relevant parts of the current run that show whether this exact scenario was constructed, executed, inspected, and checked for expected behavior. Include the pertinent setup or code, tool call and output, command or test result, later changes that could make an earlier result stale, and final-answer disclosure when present. Keep failed and successful attempts in order and name where each excerpt came from. Do not rely on the agent's conclusion or claims; report only what the run contains. When no related work appears, say so plainly.")
    missing: str = Field(min_length=1, description="Missing names the specific step the run does not show for this scenario, written as concise instructions the main agent can act on. It may identify an absent setup, a near-miss input, an unrun or failed check, a missing expected-behavior assertion, or code that was changed after the last successful run. Do not use this field as evidence for Jev; it is continuation guidance from the handoff writer. When the evidence shows the allowed form of exercise and its result in the latest state, say that nothing is missing. Do not ask for work outside the request.")


class JevMotivatingCaseEvidencePayload(JevSectionPayload):
    """The handoff evidence for every scenario in the run state's motivating-case section."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "This section reports what the main agent's current run shows for each motivating scenario in the run state. It gives the exact scenario id, the setup or inspection evidence, the latest relevant execution outcome, and any specific part that remains unshown. It must include every scenario, including ones the agent did not work on. This evidence is compiled after each finish attempt from the same run's responses, tool calls, outputs, and final answer. It reports observations only and does not decide whether a scenario is complete."

    scenarios: list[JevMotivatingScenarioEvidencePayload] = Field(description="Return one evidence entry for every scenario in the run state's motivating_case section, in the same order and with exactly the same ids. Reproduce the relevant run evidence for each case, or say no part of the run concerns it. Preserve failures and later attempts so the latest state is clear. The evidence field is what Jev reads; the missing field is only guidance for the main agent. Never omit a scenario, even when there is nothing to report, and never invent an event, command, or result.")


class JevScopeDimensionPayload(BaseModel):
    """One request-derived group whose members may each need the requested change."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="A unique lowercase id for this scope group, starting with a letter and using only letters, digits, and underscores.")
    request_quote: str = Field(min_length=1, description="Copy a short exact phrase from the user's request that names this group or asks for its coverage. Do not paraphrase it.")
    requested_change: str = Field(min_length=1, description="State the change the user asks to reach each member of this group. Preserve the request's scope and do not add work.")
    unit_noun: str = Field(min_length=1, description="Name the kind of member in this group, such as provider, endpoint, or README.")
    membership_rule: str = Field(min_length=1, description="Explain how to recognize one member of this group from its name or context, using only details supported by the request.")
    breadth: JevScopeBreadth = Field(description="Choose whether the user asks for every member, a named list, one example, or one target.")
    universe: JevScopeUniverse = Field(description="Choose whether members are named in the request, must be found in the workspace, or belong to an open-ended group.")
    named_units: list[str] = Field(description="Copy each member explicitly named in the request. Use an empty list when none are named.")
    excluded_units: list[str] = Field(description="Copy members the request explicitly excludes. Use an empty list when none are excluded.")
    partial_allowed_quote: str = Field(default="", description="Copy the exact request phrase that permits a partial result, or use an empty string when the request requires the full scope.")


class JevScopeCoveragePayload(JevSectionPayload):
    """The request-derived scope groups recorded before the main agent starts work."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The scope coverage section identifies groups of related targets where the user's request asks the same change to reach multiple members. Record only groups and limits grounded in the original request. Later, the handoff gathers work for each named member and any members the run found in the workspace. A group that asks for one target, one example, or explicitly allows a partial result does not block completion."

    dimensions: list[JevScopeDimensionPayload] = Field(description="Return one entry for each independent group the request asks the change to cover. Keep separate groups separate. Return an empty list when the request does not ask for multi-member coverage.")


class JevScopeUnitEvidencePayload(BaseModel):
    """The handoff's report of work on one member of a scope group."""

    model_config = ConfigDict(extra="forbid")

    unit: str = Field(min_length=1, description="Name one member exactly as named in the request or found in the workspace.")
    work: str = Field(description="Report the relevant run evidence for the requested change on this member, including what was changed and any result. Use an empty string when the run shows no work on this member. Do not infer completion from a plan or claim.")


class JevScopeDimensionEvidencePayload(BaseModel):
    """The handoff's evidence for one checked scope group."""

    model_config = ConfigDict(extra="forbid")

    dimension_id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Copy the exact id of one checked scope group from the run state.")
    enumeration: list[str] = Field(description="List the members the run explicitly enumerated from workspace evidence. Use an empty list when no enumeration is shown.")
    units: list[JevScopeUnitEvidencePayload] = Field(description="Include each member named in the run-state request group, even when its work field is empty, and each additional workspace member the run enumerated. Do not add members that were only mentioned without workspace evidence.")


class JevScopeCoverageEvidencePayload(JevSectionPayload):
    """The handoff's per-member work report for each checked scope group."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The scope coverage evidence section reports what the run did for each checked group in the run state. It includes each request-named member, any additional member the run enumerated from the workspace, and the evidence for the requested change on that member. It also records the enumerated workspace members so code can distinguish a member found in the run from an unsupported mention. This section reports observations and does not decide whether the requested change is complete."

    dimensions: list[JevScopeDimensionEvidencePayload] = Field(description="Return exactly one entry for each checked scope dimension in the run state, using the same ids and order. Do not leave out a named member even when there is no work to report for it.")


class JevCompletionEvidencePayload(BaseModel):
    """One whole-task completion status and the observations that support or contradict it."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Use the fixed id `task_completion` for this single whole-task item. The same id is required at every finish attempt so its Jev answer and continuation feedback remain stable. Do not create a separate item for each requested deliverable or factual assertion. This item is required even when the final answer is empty or says nothing about completion. The id identifies the scope of the judgment and is not itself evidence.")
    completion_status: JevCompletionStatus = Field(description="Choose the status communicated by the final answer for the original request as a whole. Use complete when the answer explicitly says the task is finished or ends with a result and no caveat, so it implies completion. Use incomplete when the answer says requested work remains, blocked when it names an obstacle preventing progress, and unclear only when its status cannot reasonably be read either way. This field records the answer's message and never proves that any external action occurred.")
    requested_outcomes: list[str] = Field(description="List the distinct outcomes the original user request requires before the task can be considered complete. Preserve the user's scope, quantities, targets, and constraints, and do not add expected best practices or work from the agent's plan. Include informational answers and artifacts requested in the response as outcomes alongside external changes. Keep this list complete enough to reveal when only part of the request is shown, and return an empty list when the request asks for no result. These requested outcomes define what the evidence must cover but do not establish that any outcome happened.")
    completed_work: list[str] = Field(description="List only requested outcomes for which the run contains a visible result or artifact. Name the specific tool output, command result, file content, or delivered answer passage that shows each outcome. Do not use an assistant's statement that it completed, checked, searched, or changed something as evidence of that action. Preserve partial scope and failed or later-reversed results rather than describing them as finished. Return an empty list when the run shows no requested outcome completed.")
    unfinished_or_blocked: list[str] = Field(description="List requested outcomes that the run does not show completed, or that have a recorded failure or blocker. Name the specific missing part, failed result, or obstacle and keep it within the user's request. Do not infer a blocker from silence alone when the run provides no observation about it. A complete run may return an empty list. This field provides context for judging an incomplete or blocked status and is not a substitute for evidence.")
    evidence: str = Field(min_length=1, description="Compile the relevant observations from actual run artifacts and tool-call inputs and outputs, naming their source and order. Include the delivered final-answer passage when it is itself a requested text outcome, but do not treat the answer's own completion claim as proof of external work. Report attempted commands, tool failures, successful outputs, and later changes that may reverse earlier results. Distinguish a visible artifact from an agent's description of an artifact that the run does not show. If no useful observation exists, say that the run contains no observable evidence for the requested outcomes.")
    missing: str = Field(min_length=1, description="Write the actionable gap between the completion status communicated by the answer and the work the run actually shows. Name requested outcomes that remain unsupported, or say that the answer should report its incomplete or blocked status when it implies full completion without evidence. Do not repeat the evidence or add tasks the user did not request. If the status is supported, say that no completion-status gap remains. This field is for continuation feedback only and must not be included in Jev's evidence state.")


class JevCompletionEvidenceSectionPayload(JevSectionPayload):
    """The completion-evidence section of the handoff, with one item per finish attempt."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "This section records whether the final answer communicates that the user's whole request is complete, incomplete, blocked, or unclear. It exists to catch a finished-sounding answer whose requested outcomes are not shown in the run. It always contains one stable task_completion item, including when the final answer omits a status or is empty. Its context fields describe the answer and requested outcomes, while evidence contains only observations from the run and never the handoff's own verdict. The handoff compiles this section at every finish attempt from the original request, the final answer, the responses, and the actual tool-call record."

    items: list[JevCompletionEvidencePayload] = Field(min_length=1, max_length=1, description="Return exactly one item with id task_completion for the entire request, not one item per deliverable or factual assertion. Set its completion_status from what the final answer states or implies, treating an unqualified terminal answer as complete and an empty answer as incomplete. Include every requested outcome and identify which outcomes actual run observations show. Keep the status description and missing note separate from the evidence string so a checker can distinguish an agent's words from external observations. Always return the item, including when no tool calls or no explicit completion claim exist.")



class JevReportActionAlignmentEvidencePayload(BaseModel):
    """One material candidate for comparing a visible plan, observed work, and the final account."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this candidate a short stable id in lowercase letters, digits, and underscores, starting with a letter and no longer than sixty-four characters. Derive it from the action or outcome whose account may differ from the run. Keep every id unique in this handoff so Jev's answer maps to exactly one candidate. Copy the id unchanged into the frozen record and the question name. Do not use an id to imply that a discrepancy has already been proven.")
    plan: str = Field(min_length=1, description="Quote or closely reproduce an explicit plan, promise, or commitment that appears in a main-agent response before the final account. Include an item only when that visible plan is later referred to or implied as carried out by the final account. Do not infer a plan from the user's request, a tool call, or what an agent normally might do. Preserve what action was proposed and any limit or condition attached to it. Do not treat a planned action as proof that it happened or as a user requirement by itself.")
    execution: str = Field(min_length=1, description="Describe the actual actions and results recorded during this run that bear on this candidate. Use tool names, arguments, execution states, outputs, and delivered artifact content or state when those observations are available. Distinguish a requested or attempted action from a successful result, and include relevant failed attempts and later reversals. If no action or result is recorded, say so plainly rather than inferring completion from the plan or report. This field describes observed execution and does not decide whether the request required the action.")
    final_account: str = Field(min_length=1, description="Quote or closely reproduce how the main agent's final answer describes this step, result, or overall completion. Keep enough of the original wording to preserve whether it says the work was completed, changed, abandoned, unnecessary, or remains open. Do not rewrite an uncertain statement as a definite completion claim or omit a qualifier that changes its meaning. When the final answer does not mention the candidate, state that it gives no account of this step. This field is the retrospective account being compared with execution, not evidence that the described action occurred.")
    request_relevance: str = Field(min_length=1, description="Explain how this candidate relates to the original user request and its stated constraints. Identify whether the action itself was required, whether it was merely one possible route to a requested outcome, or whether later evidence shows it was unnecessary or superseded. Preserve the user's scope instead of adding a best-practice requirement the user did not ask for. Say when the available request gives no reason to treat the plan step as required. This field prevents an abandoned plan from being mistaken for unfinished user work solely because it was planned.")
    evidence: str = Field(min_length=1, description="Provide the underlying observations that let a checker compare the visible plan, actual execution, final account, and request relevance. Identify where each observation came from, including a main-agent response, a named tool call and result, or a delivered artifact visible in the run. Put observations in the order they occurred and preserve failed attempts, successful replacements, and later reversals. Do not use the plan or final account as proof that an action occurred, and do not state a verdict about alignment. When the run contains no relevant observation, say that no supporting execution evidence is recorded.")
    missing: str = Field(min_length=1, description="Tell the main agent exactly what remains unreconciled between the visible commitment, recorded execution, final account, and the user's actual request. Name whether the agent should produce still-required work, correct an inaccurate completion statement, or accurately explain a justified plan change. Do not ask it to carry out a plan step that the request does not require or that later work made unnecessary. If the account already matches the observed work and the request's requirements, say that nothing remains to reconcile. This field is guidance for the main agent and is never sent to Jev as evidence.")


class JevReportActionAlignmentEvidenceSectionPayload(JevSectionPayload):
    """The handoff section containing material report and execution comparisons discovered after work."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "This section is generated at each finish attempt because the main agent's visible plan, its actual work, and its final account only exist after execution. Include one candidate for each material plan or commitment that is explicit in an earlier main-agent response and that the final account refers to or implies was carried out. Include both aligned and potentially misaligned cases so this handoff does not decide the question Jev will answer. The candidate must also say how the planned action relates to the original request so an unnecessary or superseded plan step is not treated as required work. Distinguish observed actions and results from claims about them, and return an empty list when no eligible visible plan/account relationship exists."

    items: list[JevReportActionAlignmentEvidencePayload] = Field(description="Return one entry for each material plan or commitment that appears explicitly in an earlier main-agent response and that the final account refers to or implies was carried out. Include aligned items as well as items that may be inaccurate so the handoff does not choose the verdict, and give each a distinct stable id. Do not infer a plan from the original request, from a tool call, or from common practice; if no earlier explicit commitment exists, create no item. For each candidate, fill plan, execution, final_account, request_relevance, evidence, and missing with the distinctions described by those fields. A plan step that changed or was abandoned can still be included when the final account refers to it, but describe whether the request still requires the result and whether the account states the change accurately. Return an empty list when no eligible visible plan/account relationship exists, including when a plan was never referred to or implied as carried out in the final account.")


class JevAssumptionEvidencePayload(BaseModel):
    """One consequential assumption explicitly used, then contradicted by later run evidence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Give this changed assumption a stable lowercase id made of letters, digits, and underscores, beginning with a letter and no longer than sixty-four characters. Choose an id that distinguishes this premise from every other qualifying premise in the same handoff. Use the same id in the shared Jev state and in continuation feedback. Do not use a number alone or include punctuation other than underscores. This id links one Jev answer to exactly one assumption entry.")
    original_assumption: str = Field(min_length=1, description="State the specific premise the main agent explicitly used to guide consequential work before later evidence changed it. Ground the wording in an early main-agent response or tool context that is visible in this run. Preserve its scope and certainty as the agent expressed them, without upgrading a tentative possibility into a fact. Do not infer a hidden belief from a plan, implementation choice, or outcome alone. Include an item only when the premise was used and later run evidence concretely contradicts or materially changes it.")
    original_basis: str = Field(min_length=1, description="Describe the visible information that the main agent gave as the basis for the original assumption, quoting or closely paraphrasing its early response or tool context. Identify where that basis appears in the run so the item can be traced to an observable source. Keep the original basis distinct from later observations, even when both concern the same subject. Do not supply a plausible rationale that the agent never stated. If the run shows no explicit basis, explain that the basis was not stated while preserving only the directly visible assumption and use of it.")
    later_observation: str = Field(min_length=1, description="Report the concrete observation later in this run that contradicts or materially changes the original assumption. Identify its source, such as a tool output, command result, document content, or later response grounded in an observation. State what the observation shows without interpreting whether the downstream work was repaired. A plan change, another unverified statement, or a possibility alone is not a concrete observation. Include the item only when this later observation changes the premise that guided the affected work.")
    affected_work: str = Field(min_length=1, description="Name the downstream decision, artifact, conclusion, or action that depended on the original assumption. Ground the dependency in observable run context rather than assuming that work was related merely because it happened later. Identify the concrete target, such as a chosen approach, edited file, answer conclusion, or requested operation, when the run makes one visible. If evidence later indicates that the work no longer matters, preserve that work here so Jev can judge whether it was made irrelevant. Do not omit affected work because it was subsequently changed, left alone, or abandoned.")
    revision: str = Field(min_length=1, description="Report what the run shows happened to the affected work after the later observation, using actions and results rather than a verdict. Include observable edits, changed decisions, corrected conclusions, follow-up checks, unchanged work, or an explicit reason the work became irrelevant when the run supplies it. Acknowledging the changed premise is not itself evidence that dependent work was revisited. Do not state that the assumption was reconciled, that repair was adequate, or that revalidation is required. Preserve unresolved or absent downstream action as an observation for Jev to judge.")
    evidence: str = Field(min_length=1, description="Gather the relevant run observations for this one assumption, with source labels and in the order they occurred. Include the early response or tool context that made the premise explicit and consequential, the later concrete observation that changed it, and any later action or result concerning dependent work. Quote or closely reproduce enough context for a checker who sees only these fields to recognize whether the work was revisited. Report contradictions, unchanged outcomes, and missing observations faithfully without offering a completion verdict. The final answer's assertion that work was fixed is not evidence unless the run also shows the action or result.")
    missing: str = Field(min_length=1, description="Write a separate, actionable summary for the main agent of what the run does not show about reconciling this changed assumption with its dependent work. Name the decision, artifact, conclusion, or consequence that appears unrevisited, or say that the evidence shows no dependent work remained relevant. Keep this field separate from the quoted observations in evidence. Do not let this summary decide Jev's answer, and do not include it in the state sent to Jev. When the run shows an observable revision or that the work is irrelevant, state what observation supports that summary without claiming more than the run shows.")


class JevAssumptionsReconciledPayload(JevSectionPayload):
    """The post-run assumptions section: materially changed premises and their downstream work."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "The assumptions section records consequential premises the main agent explicitly used and later concrete run evidence contradicted or materially changed. It is derived after the work because only the main agent's responses and tool context show which premises actually guided this run. Include each qualifying premise whether dependent work was later revised, left unchanged, or became irrelevant, because those outcomes are judged separately. Exclude uncertainty or lack of verification by itself, and exclude plan changes without a concretely changed premise. Report the assumption, its basis, the later observation, affected work, subsequent actions, and source evidence without deciding whether the work was reconciled."

    items: list[JevAssumptionEvidencePayload] = Field(description="Return one item for each materially consequential assumption that the run visibly shows the main agent used and later concrete run evidence contradicted or materially changed. Require an explicit early main-agent response or tool-context source for the assumption and an identifiable downstream decision, artifact, conclusion, or action that depended on it. Include the item regardless of whether later work was revised, unchanged, abandoned, or made irrelevant; the separate Jev question judges that outcome. Do not include an assumption that was merely uncertain, unverified, or considered as a possibility, and do not treat a plan change alone as evidence of a mistaken premise. Return an empty list only when the run contains no qualifying changed assumption, not because every qualifying assumption was reconciled.")


class JevGuaranteedNextActionPayload(BaseModel):
    """One candidate follow-on obligation and its observed run evidence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="Use a unique lowercase identifier for this candidate, starting with a letter and using only letters, digits, and underscores. Keep the id stable within this response so the two Jev questions can refer to the same candidate. Do not reuse an id for a different action. The id carries no judgment about whether the action is necessary. Keep it under sixty-four characters.")
    outcome: str = Field(min_length=1, description="Quote or closely reproduce the concrete end state the user requested. Keep the user's scope and qualifications, and do not broaden the outcome into general quality advice. This field gives Jev the goal the candidate action is claimed to serve. It is context, not evidence that the action is necessary. If the request names no concrete outcome, do not create a candidate.")
    trigger: str = Field(min_length=1, description="Describe the condition observed in this run that is claimed to make follow-on work relevant. Cite the response, tool call, result, or final answer that shows the condition, using enough detail to locate it in `evidence`. Do not use a hypothetical, an unobserved condition, or an expectation about what may happen later. A trigger alone does not prove that the action is necessary. If the run contains no direct observation, omit the candidate.")
    action: str = Field(min_length=1, description="Name one concrete remaining action that could address the observed trigger and satisfy the requested outcome. Keep it within the user's request and the authority already granted; do not add optional cleanup, polish, external publication, or irreversible work without authorization. Do not combine alternatives or a list of steps in one action. The field is only a proposed candidate and is not proof of necessity. If several plausible authorized actions could satisfy the outcome, omit the candidate.")
    necessity_basis: str = Field(min_length=1, description="Explain for the handoff record why the request and observed trigger are claimed to entail this action, and why no plausible authorized alternative reaches the same outcome. This is candidate-generation rationale only and must never be copied into Jev's state or treated as proof. It must be grounded in the request and observed run, not general convention or likely usefulness. If the explanation relies on an unstated assumption, permission, or future event, omit the candidate. Jev independently judges necessity from the request and observed evidence.")
    evidence: str = Field(min_length=1, description="Compile the direct run evidence for the trigger and whether the action has already been completed. Include relevant responses, tool calls and outputs, command or test results, and the final answer, in the order they occurred. Preserve failures and later successful attempts, and state the latest observed status of the action. Do not rely on the main agent's unsupported completion claim or on this payload's necessity rationale. When evidence is ambiguous or absent, say so plainly.")
    missing: str = Field(min_length=1, description="State the concrete evidence gap that remains if the action has not been completed. Name the action and what the run does not show, using facts from `evidence` only. If the evidence shows that the action is complete, say that nothing is missing. Do not introduce another action, recommend optional work, or repeat the necessity rationale. This text is supplied to the main agent only when Jev independently accepts necessity and finds the action unfinished.")


class JevGuaranteedNextActionsEvidencePayload(JevSectionPayload):
    """Dynamic candidates for necessary follow-on obligations found in the observed run."""

    model_config = ConfigDict(extra="forbid")

    SECTION: ClassVar[str] = "This section contains zero or more candidate follow-on obligations derived after the main agent has worked. Each candidate names a requested outcome, an observed trigger, one proposed action, the handoff's private rationale for proposing it, and evidence from the run. The rationale is not sent to Jev and is never proof of necessity; Jev sees the user's original request, the outcome, the trigger, the action, and direct evidence. Jev separately judges whether the action is logically required with no plausible authorized alternative and whether the action remains unfinished. The handoff must omit uncertain candidates, explicitly ordered sequences, and broad phase-progress judgments; it must not predict likely work, infer future triggers, or invent user authorization. An empty list means the handoff found no candidate it could state with this evidence."

    actions: list[JevGuaranteedNextActionPayload] = Field(description="Return one candidate only when the user's request names a concrete outcome, the run directly shows a trigger that leaves that outcome unmet, and one concrete in-scope action appears to be required to reach it. Include a short private necessity rationale for audit, but Jev must independently assess necessity from the request and run evidence without receiving that rationale. Include all direct evidence needed to judge both the trigger and whether the action is already complete. Omit explicitly ordered sequences and phase-progress steps, which belong to separate checks. Omit any candidate with a plausible authorized alternative, unclear scope or permission, an unobserved condition, optional polish, or speculative dependency. Return an empty list when no candidate satisfies these conditions.")
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
class JevMotivatingScenario:
    """One request-derived boundary condition, its distinguishing case, and its permitted exercise mode."""

    id: str
    role: JevScenarioRole
    kind: JevBoundaryKind
    source_quote: str
    target: str
    condition: str
    near_miss: str
    expected_behavior: str | None
    literal_inputs: tuple[str, ...]
    exercise_mode: JevExerciseMode

    def __post_init__(self) -> None:
        # Validates the stable identifier, closed vocabularies, and request-derived scenario text.
        JevDeliverableId.require(self.id, field_name="motivating scenario id")
        for name, enum_type in (("role", JevScenarioRole), ("kind", JevBoundaryKind), ("exercise_mode", JevExerciseMode)):
            if not isinstance(getattr(self, name), enum_type):
                raise JevValidation.error(f"motivating scenario {name}", f"a {enum_type.__name__} member", getattr(self, name))
        for name in ("source_quote", "target", "condition", "near_miss"):
            JevText.require(getattr(self, name), field_name=f"motivating scenario {self.id!r} {name}")
        if self.expected_behavior is not None:
            JevText.require(self.expected_behavior, field_name=f"motivating scenario {self.id!r} expected_behavior")
        if not isinstance(self.literal_inputs, tuple):
            raise JevValidation.error("motivating scenario literal_inputs", "a tuple of strings", self.literal_inputs)
        for index, value in enumerate(self.literal_inputs):
            JevText.require(value, field_name=f"motivating scenario {self.id!r} literal_inputs[{index}]")

    def blocks_finish(self) -> bool:
        """Return whether the user named this scenario as motivating or requested work."""
        return self.role is not JevScenarioRole.IMPLIED


@dataclass(frozen=True, slots=True)
class JevMotivatingCase:
    """The motivating-case section written once from the user's request."""

    ordinary_flow: str
    testing_restriction_quote: str | None
    scenarios: tuple[JevMotivatingScenario, ...]
    recall_guard_probability: float | None = None
    builder_disagreement: bool = False

    def __post_init__(self) -> None:
        # Requires typed, unique scenario definitions and a tuple that cannot change during the run.
        # @intent request-scenarios-remain-joinable
        # Stable unique ids connect each request-derived condition to its later evidence, so the
        # immutable record rejects malformed definitions before any completion check can read them.
        JevText.require(self.ordinary_flow, field_name="motivating-case ordinary_flow")
        if self.testing_restriction_quote is not None:
            JevText.require(self.testing_restriction_quote, field_name="motivating-case testing restriction")
        if not isinstance(self.scenarios, tuple) or not all(isinstance(item, JevMotivatingScenario) for item in self.scenarios):
            raise JevValidation.error("motivating-case scenarios", "a tuple of JevMotivatingScenario values", self.scenarios)
        JevDeliverableId.require_unique(tuple(item.id for item in self.scenarios), field_name="motivating-case scenarios")
        if len(self.scenarios) > JEV_MOTIVATING_CASE_MAX_SCENARIOS:
            raise JevValidation.error("motivating-case scenarios", f"at most {JEV_MOTIVATING_CASE_MAX_SCENARIOS} entries", len(self.scenarios))
        if self.recall_guard_probability is not None:
            object.__setattr__(self, "recall_guard_probability", JevProbability.require(self.recall_guard_probability, field_name="motivating-case recall guard probability"))
        if not isinstance(self.builder_disagreement, bool):
            raise JevValidation.error("motivating-case builder_disagreement", "a bool", self.builder_disagreement)

    def ids(self, *, blocking_only: bool = False) -> tuple[str, ...]:
        """Return scenario ids in request order, optionally omitting implied scenarios."""
        return tuple(item.id for item in self.scenarios if not blocking_only or item.blocks_finish())


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
class JevCumulativeObligation:
    """One requested obligation, its origin, observable completion signal, and latest user-directed status."""

    id: str
    source_turn: int
    related_turns: tuple[int, ...]
    instruction: str
    completion_signal: str
    active: bool
    status_turn: int | None
    status_reason: str

    def __post_init__(self) -> None:
        # Every obligation remains addressable even after cancellation so history can distinguish omission from revocation.
        JevDeliverableId.require(self.id, field_name="cumulative obligation id")
        if isinstance(self.source_turn, bool) or not isinstance(self.source_turn, int) or self.source_turn < 0:
            raise JevValidation.error("cumulative obligation source_turn", "a non-negative integer", self.source_turn)
        if not isinstance(self.related_turns, tuple) or any(not _is_integer_index(index) or index <= self.source_turn for index in self.related_turns):
            raise JevValidation.error("cumulative obligation related_turns", "a tuple of later non-negative user-turn indices", self.related_turns)
        if self.status_turn is not None and (isinstance(self.status_turn, bool) or not isinstance(self.status_turn, int) or self.status_turn <= self.source_turn):
            raise JevValidation.error("cumulative obligation status_turn", "None or a later non-negative user-turn index", self.status_turn)
        for field_name in ("instruction", "completion_signal", "status_reason"):
            JevText.require(getattr(self, field_name), field_name=f"cumulative obligation {self.id!r} {field_name}")
        if not isinstance(self.active, bool):
            raise JevValidation.error("cumulative obligation active", "a boolean", self.active)
        if (self.active and self.status_turn is not None) or (not self.active and self.status_turn is None):
            raise JevValidation.error("cumulative obligation status_turn", "None for an active obligation and present for an inactive obligation", self.status_turn)

@dataclass(frozen=True, slots=True)
class JevCumulativeObligations:
    """All independently checkable user obligations from the supplied turns, including explicitly inactive ones."""

    obligations: tuple[JevCumulativeObligation, ...] = ()
    user_turns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.obligations, tuple) or not all(isinstance(item, JevCumulativeObligation) for item in self.obligations):
            raise JevValidation.error("cumulative obligations", "a tuple of JevCumulativeObligation values", self.obligations)
        JevDeliverableId.require_unique(self.ids(), field_name="cumulative obligations")
        if not isinstance(self.user_turns, tuple):
            raise JevValidation.error("cumulative obligation user turns", "a tuple of strings", self.user_turns)
        for index, turn in enumerate(self.user_turns):
            JevText.require(turn, field_name=f"cumulative obligation user turn[{index}]")
        if self.user_turns and any(item.source_turn >= len(self.user_turns) or any(index >= len(self.user_turns) for index in (*item.related_turns, *((item.status_turn,) if item.status_turn is not None else ()))) for item in self.obligations):
            raise JevValidation.error("cumulative obligation turn link", "source, related, and status indices into the supplied user_turns", self.obligations)

    def ids(self, *, active_only: bool = False) -> tuple[str, ...]:
        """Return obligation ids in first-request order, optionally limiting them to active obligations."""
        return tuple(item.id for item in self.obligations if item.active or not active_only)

@dataclass(frozen=True, slots=True)
class JevScopeDimension:
    """One request-named group and the breadth of coverage it requires."""

    id: str
    request_quote: str
    requested_change: str
    unit_noun: str
    membership_rule: str
    breadth: JevScopeBreadth
    universe: JevScopeUniverse
    named_units: tuple[str, ...] = ()
    excluded_units: tuple[str, ...] = ()
    partial_allowed_quote: str = ""
    breadth_upgraded: bool = False

    def __post_init__(self) -> None:
        # @intent scope-labels-preserve-requested-coverage
        # Breadth and universe decide whether a scope can hold completion open; reject contradictory
        # labels and duplicate members so malformed state cannot quietly narrow that obligation.
        JevDeliverableId.require(self.id, field_name="scope dimension id")
        for field_name in ("request_quote", "requested_change", "unit_noun", "membership_rule"):
            JevText.require(getattr(self, field_name), field_name=f"scope {field_name}")
        if not isinstance(self.breadth, JevScopeBreadth) or not isinstance(self.universe, JevScopeUniverse):
            raise JevValidation.error("scope labels", "JevScopeBreadth and JevScopeUniverse members", (self.breadth, self.universe))
        for field_name in ("named_units", "excluded_units"):
            _require_scope_member_names(getattr(self, field_name), field_name)
        if not isinstance(self.partial_allowed_quote, str):
            raise JevValidation.error("scope partial_allowed_quote", "a string", self.partial_allowed_quote)
        if self.partial_allowed_quote:
            JevText.require(self.partial_allowed_quote, field_name="scope partial_allowed_quote")
        if not isinstance(self.breadth_upgraded, bool):
            raise JevValidation.error("scope breadth_upgraded", "a boolean", self.breadth_upgraded)
        if self.breadth is JevScopeBreadth.NAMED_LIST and (self.universe is not JevScopeUniverse.NAMED_IN_REQUEST or len(self.named_units) < 2):
            raise JevValidation.error("scope breadth and universe", "named_list with at least two request-named members", (self.breadth, self.universe, self.named_units))
        if self.universe is JevScopeUniverse.NAMED_IN_REQUEST and not self.named_units:
            raise JevValidation.error("scope named_units", "at least one member for a named_in_request universe", self.named_units)

    def is_checked(self) -> bool:
        """Return whether this request dimension requires a continuation gate."""
        return self.breadth.is_checked() and not self.partial_allowed_quote

    def is_excluded(self, unit: str) -> bool:
        """Return whether the user excluded this member from the requested change."""
        return _normalize_scope_text(unit) in {_normalize_scope_text(value) for value in self.excluded_units}

    def required_named_units(self) -> tuple[str, ...]:
        """Return request-named members that are not explicitly excluded."""
        return tuple(unit for unit in self.named_units if not self.is_excluded(unit))

    def upgraded(self, breadth: JevScopeBreadth) -> JevScopeDimension:
        """Widen a narrow builder label without creating an invalid named-list scope."""
        # @intent breadth-review-only-widens-request-scope
        # A separate request-only review may repair an under-read breadth, but it must never narrow
        # user-named coverage or invent a named list whose members were not in the request.
        if breadth is JevScopeBreadth.NAMED_LIST and (self.universe is not JevScopeUniverse.NAMED_IN_REQUEST or len(self.named_units) < 2):
            breadth = JevScopeBreadth.EVERY_MEMBER
        universe = self.universe
        if universe is JevScopeUniverse.NAMED_IN_REQUEST and not self.named_units:
            universe = JevScopeUniverse.FOUND_IN_WORKSPACE
        return replace(self, breadth=breadth, universe=universe, breadth_upgraded=True)


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
class JevScopeCoverage:
    """The request-derived scope dimensions for one run."""

    dimensions: tuple[JevScopeDimension, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, tuple) or not all(isinstance(item, JevScopeDimension) for item in self.dimensions):
            raise JevValidation.error("scope dimensions", "a tuple of JevScopeDimension values", self.dimensions)
        JevDeliverableId.require_unique(tuple(item.id for item in self.dimensions), field_name="scope dimensions")

    def checked_dimensions(self) -> tuple[JevScopeDimension, ...]:
        """Return the dimensions that require multi-member coverage."""
        return tuple(item for item in self.dimensions if item.is_checked())

    @classmethod
    def from_payload(cls, payload: JevScopeCoveragePayload, original_request: str) -> JevScopeCoverage:
        """Build a typed scope section, rejecting quotes and member names absent from the request."""
        # @intent scope-definitions-stay-grounded-in-request
        # Only request text can create or exclude required members; a generated dimension cannot
        # manufacture broader work or claim that the user allowed partial coverage.
        request = _normalize_scope_text(original_request)
        dimensions = []
        for item in payload.dimensions:
            quoted = (item.request_quote, *item.named_units, *item.excluded_units)
            if item.partial_allowed_quote:
                quoted = (*quoted, item.partial_allowed_quote)
            for quote in quoted:
                if _normalize_scope_text(quote) not in request:
                    raise JevValidation.error("scope request quote", "an exact phrase present in the original request", quote)
            dimensions.append(JevScopeDimension(
                id=item.id,
                request_quote=item.request_quote.strip(),
                requested_change=item.requested_change.strip(),
                unit_noun=item.unit_noun.strip(),
                membership_rule=item.membership_rule.strip(),
                breadth=item.breadth,
                universe=item.universe,
                named_units=tuple(value.strip() for value in item.named_units),
                excluded_units=tuple(value.strip() for value in item.excluded_units),
                partial_allowed_quote=item.partial_allowed_quote.strip(),
            ))
        return cls(tuple(dimensions))


@dataclass(frozen=True, slots=True)
class JevScopeUnitEvidence:
    """The reported work for one member of a checked scope group."""

    unit: str
    source: JevScopeUnitSource
    work: str

    def __post_init__(self) -> None:
        JevText.require(self.unit, field_name="scope evidence unit")
        if not isinstance(self.source, JevScopeUnitSource):
            raise JevValidation.error("scope evidence source", "a JevScopeUnitSource member", self.source)
        if not isinstance(self.work, str):
            raise JevValidation.error("scope evidence work", "a string, empty when no work is shown", self.work)


@dataclass(frozen=True, slots=True)
class JevScopeDimensionEvidence:
    """The handoff's enumeration and work records for one scope dimension."""

    dimension_id: str
    enumeration: tuple[str, ...]
    units: tuple[JevScopeUnitEvidence, ...]

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.dimension_id, field_name="scope evidence dimension id")
        if not isinstance(self.enumeration, tuple) or not isinstance(self.units, tuple):
            raise JevValidation.error("scope dimension evidence", "tuple values for enumeration and units", (self.enumeration, self.units))
        for index, name in enumerate(self.enumeration):
            JevText.require(name, field_name=f"scope enumeration[{index}]")
        enumerated_names = tuple(_normalize_scope_text(name) for name in self.enumeration)
        if len(set(enumerated_names)) != len(enumerated_names):
            raise JevValidation.error("scope enumeration", "unique member names", self.enumeration)
        if not all(isinstance(item, JevScopeUnitEvidence) for item in self.units):
            raise JevValidation.error("scope evidence units", "a tuple of JevScopeUnitEvidence values", self.units)
        names = tuple(_normalize_scope_text(item.unit) for item in self.units)
        if len(set(names)) != len(names):
            raise JevValidation.error("scope evidence units", "unique unit names", names)

    def required_units(self, dimension: JevScopeDimension) -> tuple[JevScopeUnitEvidence, ...]:
        """Return request-named units and, for a closed workspace group, run-enumerated units."""
        # @intent only-identified-members-count-as-covered
        # A member counts only when the request named it or the run enumerated it for a closed
        # workspace group; an unsupported mention cannot satisfy the user's coverage requirement.
        included = []
        for unit in self.units:
            if dimension.is_excluded(unit.unit):
                continue
            if unit.source is JevScopeUnitSource.NAMED_IN_REQUEST:
                included.append(unit)
            elif (
                dimension.breadth is JevScopeBreadth.EVERY_MEMBER
                and dimension.universe is JevScopeUniverse.FOUND_IN_WORKSPACE
                and unit.source is JevScopeUnitSource.FOUND_BY_RUN
            ):
                included.append(unit)
        return tuple(included)


def _scope_dimension_evidence_from_payload(
    dimension: JevScopeDimension,
    item: JevScopeDimensionEvidencePayload,
) -> JevScopeDimensionEvidence:
    """Normalize evidence for one checked dimension from the handoff payload."""
    # @intent handoff-membership-origin-is-recomputed
    # Recompute each member's source from the request and run inventory so an agent's unsupported
    # label cannot turn a claimed or unenumerated member into evidence of completed coverage.
    enumeration = tuple(value.strip() for value in item.enumeration)
    enumerated = {_normalize_scope_text(value) for value in enumeration}
    units: list[JevScopeUnitEvidence] = []
    provided: set[str] = set()
    for unit in item.units:
        name = unit.unit.strip()
        normalized = _normalize_scope_text(name)
        if normalized in provided:
            raise JevValidation.error(f"scope handoff units for {dimension.id!r}", "unique member names", name)
        provided.add(normalized)
        if any(normalized == _normalize_scope_text(named) for named in dimension.named_units):
            source = JevScopeUnitSource.NAMED_IN_REQUEST
        elif normalized in enumerated:
            source = JevScopeUnitSource.FOUND_BY_RUN
        else:
            source = JevScopeUnitSource.MENTIONED_BY_AGENT
        units.append(JevScopeUnitEvidence(name, source, unit.work.strip()))

    if dimension.breadth is JevScopeBreadth.EVERY_MEMBER and dimension.universe is JevScopeUniverse.FOUND_IN_WORKSPACE:
        for name in enumeration:
            normalized = _normalize_scope_text(name)
            if normalized not in provided:
                source = (
                    JevScopeUnitSource.NAMED_IN_REQUEST
                    if any(normalized == _normalize_scope_text(named) for named in dimension.named_units)
                    else JevScopeUnitSource.FOUND_BY_RUN
                )
                units.append(JevScopeUnitEvidence(name, source, ""))
                provided.add(normalized)

    for named in dimension.required_named_units():
        if _normalize_scope_text(named) not in provided:
            units.append(JevScopeUnitEvidence(named, JevScopeUnitSource.NAMED_IN_REQUEST, ""))
    return JevScopeDimensionEvidence(item.dimension_id, enumeration, tuple(units))


@dataclass(frozen=True, slots=True)
class JevScopeCoverageEvidence:
    """The complete handoff section for all checked scope dimensions."""

    dimensions: tuple[JevScopeDimensionEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, tuple) or not all(isinstance(item, JevScopeDimensionEvidence) for item in self.dimensions):
            raise JevValidation.error("scope coverage evidence", "a tuple of JevScopeDimensionEvidence values", self.dimensions)
        JevDeliverableId.require_unique(tuple(item.dimension_id for item in self.dimensions), field_name="scope evidence dimensions")

    def by_id(self) -> Mapping[str, JevScopeDimensionEvidence]:
        """Return dimension evidence keyed by the request-state id."""
        return {item.dimension_id: item for item in self.dimensions}

    def question_items(self, scope: JevScopeCoverage) -> tuple[tuple[str, JevScopeDimension, JevScopeUnitEvidence], ...]:
        """Return stable question ids and evidence for every required member, including members with no work."""
        evidence_by_id = self.by_id()
        items = []
        for dimension in scope.checked_dimensions():
            account = evidence_by_id[dimension.id]
            for index, unit in enumerate(account.required_units(dimension)):
                items.append((f"{dimension.id}.{index}", dimension, unit))
        return tuple(items)

    def inventory_gaps(self, scope: JevScopeCoverage) -> tuple[str, ...]:
        """Return checked workspace-wide groups for which the run supplied no enumeration."""
        evidence_by_id = self.by_id()
        return tuple(
            dimension.id
            for dimension in scope.checked_dimensions()
            if dimension.breadth is JevScopeBreadth.EVERY_MEMBER
            and dimension.universe is JevScopeUniverse.FOUND_IN_WORKSPACE
            and not evidence_by_id[dimension.id].enumeration
        )

    @classmethod
    def from_payload(cls, payload: JevScopeCoverageEvidencePayload, scope: JevScopeCoverage) -> JevScopeCoverageEvidence:
        """Validate handoff dimension ids and normalize unsupported source labels to mentions."""
        # @intent handoff-cannot-assert-its-own-membership-source
        # Recompute each member's source from the request and run inventory so an agent's unsupported
        # label cannot turn a claimed or unenumerated member into evidence of completed coverage.
        checked = scope.checked_dimensions()
        expected = {item.id: item for item in checked}
        actual_ids = tuple(item.dimension_id for item in payload.dimensions)
        if len(set(actual_ids)) != len(actual_ids) or set(actual_ids) != set(expected):
            raise JevValidation.error("scope handoff dimension ids", f"exactly {sorted(expected)}", actual_ids)
        by_id = {
            item.dimension_id: _scope_dimension_evidence_from_payload(expected[item.dimension_id], item)
            for item in payload.dimensions
        }
        return cls(tuple(by_id[item.id] for item in checked))
@dataclass(frozen=True, slots=True)
class JevPhaseStage:
    """One requested outcome stage and the request-derived criterion for reaching it."""

    id: str
    stage: str
    required_result: str
    request_scope: str
    output_criterion: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="phase stage id")
        for field_name in ("stage", "required_result", "request_scope", "output_criterion"):
            JevText.require(getattr(self, field_name), field_name=f"phase stage {self.id!r} {field_name}")


@dataclass(frozen=True, slots=True)
class JevPhaseProgress:
    """The request-derived stages a run is expected to enter, in request order."""

    stages: tuple[JevPhaseStage, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stages, tuple) or not all(isinstance(item, JevPhaseStage) for item in self.stages):
            raise JevValidation.error("phase-progress stages", "a tuple of JevPhaseStage values", self.stages)
        JevDeliverableId.require_unique(self.ids(), field_name="phase-progress stages")

    def ids(self) -> tuple[str, ...]:
        """Return every request-required stage id in order."""
        return tuple(item.id for item in self.stages)

@dataclass(frozen=True, slots=True)
class JevInputTarget:
    """One stable input target, its boundary, and the action the user requested on it."""

    id: str
    identity: str
    scope: str
    action: str
    engagement_signal: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="input target id")
        for field_name in ("identity", "scope", "action", "engagement_signal"):
            JevText.require(getattr(self, field_name), field_name=f"input target {self.id!r} {field_name}")


@dataclass(frozen=True, slots=True)
class JevInputSetCoverage:
    """The explicitly bounded input-engagement obligations in request order."""

    targets: tuple[JevInputTarget, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.targets, tuple) or not all(isinstance(item, JevInputTarget) for item in self.targets):
            raise JevValidation.error("input-set targets", "a tuple of JevInputTarget values", self.targets)
        JevDeliverableId.require_unique(self.ids(), field_name="input-set targets")

    def ids(self) -> tuple[str, ...]:
        """Return every input target id in request order."""
        return tuple(item.id for item in self.targets)


@dataclass(frozen=True, slots=True)
class JevNegativeCoverageTarget:
    """One requested target and the visible signal that would show it was inspected."""

    id: str
    target: str
    inspection_signal: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="negative-coverage target id")
        JevText.require(self.target, field_name=f"negative-coverage target {self.id!r}")
        JevText.require(self.inspection_signal, field_name=f"inspection signal of target {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevNegativeCoverage:
    """Inspection targets extracted from the request before the main agent starts work."""

    inspections: tuple[JevNegativeCoverageTarget, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.inspections, tuple) or not all(isinstance(item, JevNegativeCoverageTarget) for item in self.inspections):
            raise JevValidation.error("negative-coverage inspections", "a tuple of JevNegativeCoverageTarget values", self.inspections)
        JevDeliverableId.require_unique(self.ids(), field_name="negative-coverage inspections")

    def ids(self) -> tuple[str, ...]:
        """Return target ids in request order."""
        return tuple(item.id for item in self.inspections)


@dataclass(frozen=True, slots=True)
class JevRequiredAction:
    """One explicitly requested action, its observable completion condition, and explicit predecessors."""

    id: str
    action: str
    completion_signal: str
    predecessors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="required action id")
        JevText.require(self.action, field_name=f"required action {self.id!r}")
        JevText.require(self.completion_signal, field_name=f"completion signal of required action {self.id!r}")
        if not isinstance(self.predecessors, tuple):
            raise JevValidation.error("required action predecessors", "a tuple of action ids", self.predecessors)
        JevDeliverableId.require_unique(self.predecessors, field_name=f"predecessors of required action {self.id!r}")
        for predecessor in self.predecessors:
            JevDeliverableId.require(predecessor, field_name=f"predecessor of required action {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevRequiredActions:
    """Request-derived required actions in the order the user explicitly stated them."""

    actions: tuple[JevRequiredAction, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple) or not all(isinstance(item, JevRequiredAction) for item in self.actions):
            raise JevValidation.error("required actions", "a tuple of JevRequiredAction values", self.actions)
        identifiers = self.ids()
        JevDeliverableId.require_unique(identifiers, field_name="required actions")
        position = {identifier: index for index, identifier in enumerate(identifiers)}
        for action in self.actions:
            for predecessor in action.predecessors:
                if predecessor not in position or position[predecessor] >= position[action.id]:
                    raise JevValidation.error("required action predecessor", "an existing action earlier in the request-state order", predecessor)

    def ids(self) -> tuple[str, ...]:
        """Return every required action id in request order."""
        return tuple(item.id for item in self.actions)


@dataclass(frozen=True, slots=True)
class JevRunStateRecord:
    """The run state JevRunState wrote from the user's request: central fields and enabled check sections.

    `negative_coverage` records each requested inspection target, and `required_actions` lists explicitly requested procedures; request-derived fields are otherwise present only when their check has items. `multi_part`, `target_outcome`,
    `motivating_case`, `scope_coverage`, `phase_progress`, and `input_set_coverage` retain their per-check
    rules; `output_count` holds each explicit numeric output obligation, and `cumulative_obligations` preserves explicit requirements across the supplied user turns with source and status links. `usage` is JevRunState's own model usage.
    """

    goal: str
    objective: str
    mission: str
    what_not_to_do: tuple[str, ...] = ()
    multi_part: JevMultiPart | None = None
    target_outcome: JevTargetOutcome | None = None
    usage: UsageRollup | None = None
    motivating_case: JevMotivatingCase | None = None
    scope_coverage: JevScopeCoverage | None = None
    phase_progress: JevPhaseProgress | None = None
    input_set_coverage: JevInputSetCoverage | None = None
    output_count: JevOutputCount | None = None
    output_extent: JevOutputExtent | None = None
    input_exhaustion: JevInputExhaustion | None = None

    negative_coverage: JevNegativeCoverage | None = None

    required_actions: JevRequiredActions | None = None
    cumulative_obligations: JevCumulativeObligations | None = None

    def __post_init__(self) -> None:
        # Requires the central text fields, non-blank limits, and a typed multi-part section when present.
        for field_name in ("goal", "objective", "mission"):
            JevText.require(getattr(self, field_name), field_name=f"run state {field_name}")
        if not isinstance(self.what_not_to_do, tuple):
            raise JevValidation.error("run state what_not_to_do", "a tuple of strings", self.what_not_to_do)
        for index, limit in enumerate(self.what_not_to_do):
            JevText.require(limit, field_name=f"run state what_not_to_do[{index}]")
        _require_optional_jev_sections((
            ("run state multi_part", self.multi_part, JevMultiPart),
            ("run state target_outcome", self.target_outcome, JevTargetOutcome),
            ("run state motivating_case", self.motivating_case, JevMotivatingCase),
            ("run state scope_coverage", self.scope_coverage, JevScopeCoverage),
            ("run state phase_progress", self.phase_progress, JevPhaseProgress),
            ("run state input_set_coverage", self.input_set_coverage, JevInputSetCoverage),
            ("run state output_count", self.output_count, JevOutputCount),
            ("run state output_extent", self.output_extent, JevOutputExtent),
            ("run state input_exhaustion", self.input_exhaustion, JevInputExhaustion),
            ("run state negative_coverage", self.negative_coverage, JevNegativeCoverage),
            ("run state required_actions", self.required_actions, JevRequiredActions),
            ("run state cumulative_obligations", self.cumulative_obligations, JevCumulativeObligations),
        ))


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
class JevCumulativeObligationEvidence:
    """Observed run evidence and a concrete gap for one active user obligation."""

    id: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="cumulative obligation evidence id")
        JevText.require(self.evidence, field_name=f"evidence of cumulative obligation {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of cumulative obligation {self.id!r}")

@dataclass(frozen=True, slots=True)
class JevCumulativeUserTurnEvidence:
    """Observed run material associated with one supplied user turn, without a completion judgment."""

    id: str
    evidence: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="cumulative user-turn evidence id")
        JevText.require(self.evidence, field_name=f"evidence of cumulative user turn {self.id!r}")

@dataclass(frozen=True, slots=True)
class JevCumulativeObligationsEvidence:
    """Handoff evidence for every obligation and supplied user turn, in their source order."""

    obligations: tuple[JevCumulativeObligationEvidence, ...] = ()
    turns: tuple[JevCumulativeUserTurnEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.obligations, tuple) or not all(isinstance(item, JevCumulativeObligationEvidence) for item in self.obligations):
            raise JevValidation.error("cumulative obligations evidence", "a tuple of JevCumulativeObligationEvidence values", self.obligations)
        if not isinstance(self.turns, tuple) or not all(isinstance(item, JevCumulativeUserTurnEvidence) for item in self.turns):
            raise JevValidation.error("cumulative user-turn evidence", "a tuple of JevCumulativeUserTurnEvidence values", self.turns)
        JevDeliverableId.require_unique(self.ids(), field_name="cumulative obligations evidence")
        JevDeliverableId.require_unique(self.turn_ids(), field_name="cumulative user-turn evidence")

    def ids(self) -> tuple[str, ...]:
        """Return each evidence id in first-request order."""
        return tuple(item.id for item in self.obligations)

    def turn_ids(self) -> tuple[str, ...]:
        """Return each source-turn evidence id in chronological order."""
        return tuple(item.id for item in self.turns)

@dataclass(frozen=True, slots=True)
class JevDiscoveredItem:
    """One dynamically discovered collection item, its requested operation, and observed run evidence."""

    id: str
    identity: str
    requested_processing: str
    completion_criteria: str
    processing_evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="discovered item id")
        for name in (
            "identity",
            "requested_processing",
            "completion_criteria",
            "processing_evidence",
            "missing",
        ):
            JevText.require(
                getattr(self, name), field_name=f"discovered item {self.id!r} {name}"
            )

@dataclass(frozen=True, slots=True)
class JevDiscoveredItemBatch:
    """A verbatim bounded tool output and the candidate items the handoff derived from it."""

    source_id: str
    source_output: str
    candidates: tuple[JevDiscoveredItem, ...]

    def __post_init__(self) -> None:
        JevText.require(self.source_id, field_name="discovered-item source id")
        if not isinstance(self.source_output, str):
            raise JevValidation.error(
                "discovered-item source output", "a string", self.source_output
            )
        if len(self.source_output) > JEV_DISCOVERED_ITEM_SOURCE_MAX_CHARS:
            raise JevValidation.error(
                "discovered-item source output",
                f"at most {JEV_DISCOVERED_ITEM_SOURCE_MAX_CHARS} characters",
                self.source_output,
            )
        if not isinstance(self.candidates, tuple) or not all(
            isinstance(item, JevDiscoveredItem) for item in self.candidates
        ):
            raise JevValidation.error(
                "discovered-item candidates",
                "a tuple of JevDiscoveredItem values",
                self.candidates,
            )
        JevDeliverableId.require_unique(
            tuple(item.id for item in self.candidates),
            field_name=f"candidates in source {self.source_id!r}",
        )

@dataclass(frozen=True, slots=True)
class JevDiscoveredItemEvidence:
    """All tool-call outputs and the candidate inventories derived from them for one finish attempt."""

    batches: tuple[JevDiscoveredItemBatch, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.batches, tuple) or not all(
            isinstance(item, JevDiscoveredItemBatch) for item in self.batches
        ):
            raise JevValidation.error(
                "discovered-item batches",
                "a tuple of JevDiscoveredItemBatch values",
                self.batches,
            )
        JevDeliverableId.require_unique(
            tuple(item.source_id for item in self.batches),
            field_name="discovered-item source ids",
        )
        JevDeliverableId.require_unique(
            self.item_ids(), field_name="discovered item ids"
        )
        if (
            sum(len(item.source_output) for item in self.batches)
            > JEV_DISCOVERED_ITEM_TOTAL_SOURCE_MAX_CHARS
        ):
            raise JevValidation.error(
                "discovered-item source outputs",
                f"at most {JEV_DISCOVERED_ITEM_TOTAL_SOURCE_MAX_CHARS} total characters",
                self.batches,
            )

    def item_ids(self) -> tuple[str, ...]:
        """Return every item id in source and item order."""
        return tuple(item.id for batch in self.batches for item in batch.candidates)

    def items(self) -> tuple[JevDiscoveredItem, ...]:
        """Return all candidates in the order their tool outputs recorded them."""
        return tuple(item for batch in self.batches for item in batch.candidates)

@dataclass(frozen=True, slots=True)
class JevInputExhaustionEvidence:
    """Trace evidence for one dynamic traversal obligation, including boundaries and the next actionable step."""

    id: str
    evidence: str
    unit_type: str | None
    visited_unit_ids: tuple[str, ...]
    source_reported_total: int | None
    last_position: str | None
    outstanding_continuation: str | None
    terminal_evidence: str | None
    failed_retrievals: tuple[str, ...]
    missing: str
    next_step: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="input-exhaustion evidence id")
        JevText.require(self.evidence, field_name=f"input-exhaustion evidence of {self.id!r}")
        if self.unit_type is not None:
            JevText.require(self.unit_type, field_name=f"input-exhaustion unit type of {self.id!r}")
        if not isinstance(self.visited_unit_ids, tuple):
            raise JevValidation.error(f"visited ids of {self.id!r}", "a tuple of strings", self.visited_unit_ids)
        for index, identifier in enumerate(self.visited_unit_ids):
            JevText.require(identifier, field_name=f"visited id {index} of {self.id!r}")
        if self.source_reported_total is not None and (type(self.source_reported_total) is not int or self.source_reported_total < 0):
            raise JevValidation.error(f"source total of {self.id!r}", "a non-negative integer or None", self.source_reported_total)
        for field_name in ("last_position", "outstanding_continuation", "terminal_evidence"):
            value = getattr(self, field_name)
            if value is not None:
                JevText.require(value, field_name=f"{field_name} of input-exhaustion evidence {self.id!r}")
        if not isinstance(self.failed_retrievals, tuple):
            raise JevValidation.error(f"failed retrievals of {self.id!r}", "a tuple of strings", self.failed_retrievals)
        for index, failure in enumerate(self.failed_retrievals):
            JevText.require(failure, field_name=f"failed retrieval {index} of {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of input-exhaustion evidence {self.id!r}")
        JevText.require(self.next_step, field_name=f"next step of input-exhaustion evidence {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevInputExhaustionEvidenceSet:
    """The ordered handoff observations for each request-derived dynamic collection traversal."""

    collections: tuple[JevInputExhaustionEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.collections, tuple) or not all(isinstance(item, JevInputExhaustionEvidence) for item in self.collections):
            raise JevValidation.error("input-exhaustion evidence", "a tuple of JevInputExhaustionEvidence values", self.collections)
        JevDeliverableId.require_unique(self.ids(), field_name="input-exhaustion evidence")

    def ids(self) -> tuple[str, ...]:
        """Return each evidenced obligation id in handoff order."""
        return tuple(item.id for item in self.collections)

@dataclass(frozen=True, slots=True)
class JevNegativeCoverageEvidenceItem:
    """The run's inspection evidence and final-answer conclusion for one requested target."""

    id: str
    inspection: str
    negative_conclusion: str
    incomplete_report: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="negative-coverage evidence id")
        JevText.require(self.inspection, field_name=f"inspection evidence for target {self.id!r}")
        for name in ("negative_conclusion", "incomplete_report"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise JevValidation.error(f"{name} of target {self.id!r}", "a string (empty when absent)", value)
        JevText.require(self.missing, field_name=f"missing of target {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevNegativeCoverageEvidence:
    """One handoff evidence entry per request-derived inspection target."""

    inspections: tuple[JevNegativeCoverageEvidenceItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.inspections, tuple) or not all(isinstance(item, JevNegativeCoverageEvidenceItem) for item in self.inspections):
            raise JevValidation.error("negative-coverage evidence", "a tuple of JevNegativeCoverageEvidenceItem values", self.inspections)
        JevDeliverableId.require_unique(self.ids(), field_name="negative-coverage evidence")

    def ids(self) -> tuple[str, ...]:
        """Return evidenced target ids in handoff order."""
        return tuple(item.id for item in self.inspections)

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
class JevMotivatingScenarioEvidence:
    """Evidence and an actionable missing note for one motivating scenario."""

    id: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        # Requires a stable scenario id and non-blank observations and continuation guidance.
        JevDeliverableId.require(self.id, field_name="motivating scenario evidence id")
        JevText.require(self.evidence, field_name=f"motivating scenario {self.id!r} evidence")
        JevText.require(self.missing, field_name=f"motivating scenario {self.id!r} missing")


@dataclass(frozen=True, slots=True)
class JevMotivatingCaseEvidence:
    """Handoff evidence for the scenarios in one finish attempt."""

    scenarios: tuple[JevMotivatingScenarioEvidence, ...] = ()

    def __post_init__(self) -> None:
        # Requires immutable evidence entries with unique ids so the question can map to one scenario each.
        if not isinstance(self.scenarios, tuple) or not all(isinstance(item, JevMotivatingScenarioEvidence) for item in self.scenarios):
            raise JevValidation.error("motivating-case evidence", "a tuple of JevMotivatingScenarioEvidence values", self.scenarios)
        JevDeliverableId.require_unique(tuple(item.id for item in self.scenarios), field_name="motivating-case evidence")

    def ids(self) -> tuple[str, ...]:
        """Return all echoed scenario ids in order."""
        return tuple(item.id for item in self.scenarios)


@dataclass(frozen=True, slots=True)
class JevPhaseStageEvidence:
    """Observed run evidence and a separate gap for one requested outcome stage."""

    id: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="phase evidence id")
        JevText.require(self.evidence, field_name=f"evidence of phase stage {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of phase stage {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevPhaseProgressEvidence:
    """The handoff evidence entries for each phase-progress stage, in run-state order."""

    stages: tuple[JevPhaseStageEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stages, tuple) or not all(isinstance(item, JevPhaseStageEvidence) for item in self.stages):
            raise JevValidation.error("phase-progress evidence", "a tuple of JevPhaseStageEvidence values", self.stages)
        JevDeliverableId.require_unique(self.ids(), field_name="phase-progress evidence")

    def ids(self) -> tuple[str, ...]:
        """Return every evidence entry's phase stage id in order."""
        return tuple(item.id for item in self.stages)

@dataclass(frozen=True, slots=True)
class JevInputTargetEvidence:
    """Evidence from the main run for one requested input target and an actionable missing note."""

    id: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="input evidence id")
        JevText.require(self.evidence, field_name=f"evidence of input target {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of input target {self.id!r}")

@dataclass(frozen=True, slots=True)
class JevInputSetCoverageEvidence:
    """Evidence entries for each request-derived input target, in the run-state order."""

    targets: tuple[JevInputTargetEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.targets, tuple) or not all(isinstance(item, JevInputTargetEvidence) for item in self.targets):
            raise JevValidation.error("input-set evidence", "a tuple of JevInputTargetEvidence values", self.targets)
        JevDeliverableId.require_unique(self.ids(), field_name="input-set evidence")

    def ids(self) -> tuple[str, ...]:
        """Return every input evidence id in order."""
        return tuple(item.id for item in self.targets)
@dataclass(frozen=True, slots=True)
class JevOutputCountObligation:
    """One numeric output obligation extracted from the original request."""

    id: str
    description: str
    target_count: int
    distinct: bool
    unit: str
    scope: str
    distinctness: str
    completion_criteria: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="output-count obligation id")
        for field_name in ("description", "unit", "scope", "distinctness", "completion_criteria"):
            JevText.require(getattr(self, field_name), field_name=f"output-count obligation {self.id!r} {field_name}")
        if isinstance(self.target_count, bool) or not isinstance(self.target_count, int) or self.target_count < 1:
            raise JevValidation.error(f"output-count obligation {self.id!r} target_count", "a positive integer", self.target_count)
        if not isinstance(self.distinct, bool):
            raise JevValidation.error(f"output-count obligation {self.id!r} distinct", "a boolean", self.distinct)


@dataclass(frozen=True, slots=True)
class JevOutputCount:
    """The request-derived numeric output obligations for one run."""

    obligations: tuple[JevOutputCountObligation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.obligations, tuple) or not all(isinstance(item, JevOutputCountObligation) for item in self.obligations):
            raise JevValidation.error("output-count obligations", "a tuple of JevOutputCountObligation values", self.obligations)
        JevDeliverableId.require_unique(self.ids(), field_name="output-count obligations")

    def ids(self) -> tuple[str, ...]:
        """Return stable obligation ids in request order."""
        return tuple(item.id for item in self.obligations)


@dataclass(frozen=True, slots=True)
class JevOutputCountEntry:
    """One output unit candidate, its distinctness key, and its source evidence."""

    id: str
    value: str
    distinct_key: str
    evidence: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="output-count entry id")
        for field_name in ("value", "distinct_key", "evidence"):
            JevText.require(getattr(self, field_name), field_name=f"output-count entry {self.id!r} {field_name}")


@dataclass(frozen=True, slots=True)
class JevOutputCountEvidenceItem:
    """The handoff's evidence and candidate output units for one obligation."""

    id: str
    entries: tuple[JevOutputCountEntry, ...] = ()
    missing: str = ""

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="output-count evidence id")
        if not isinstance(self.entries, tuple) or not all(isinstance(item, JevOutputCountEntry) for item in self.entries):
            raise JevValidation.error(f"output-count evidence {self.id!r} entries", "a tuple of JevOutputCountEntry values", self.entries)
        JevText.require(self.missing, field_name=f"output-count evidence {self.id!r} missing")
        JevDeliverableId.require_unique(tuple(item.id for item in self.entries), field_name=f"output-count entries for {self.id!r}")

@dataclass(frozen=True, slots=True)
class JevOutputCountEvidence:
    """Count evidence for every request-derived output quantity, in obligation order."""

    obligations: tuple[JevOutputCountEvidenceItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.obligations, tuple) or not all(isinstance(item, JevOutputCountEvidenceItem) for item in self.obligations):
            raise JevValidation.error("output-count evidence", "a tuple of JevOutputCountEvidenceItem values", self.obligations)
        JevDeliverableId.require_unique(self.ids(), field_name="output-count evidence")

    def ids(self) -> tuple[str, ...]:
        """Return obligation ids in handoff order."""
        return tuple(item.id for item in self.obligations)

@dataclass(frozen=True, slots=True)
class JevRequiredActionEvidence:
    """What the run shows for one required action, the successful trace call when available, and its gap."""

    id: str
    evidence: str
    trace_indices: tuple[int, ...]
    completion_trace_index: int | None
    missing: str
    output_source: str | None = None
    output_excerpt: str | None = None

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="required-action evidence id")
        JevText.require(self.evidence, field_name=f"evidence of required action {self.id!r}")
        JevText.require(self.missing, field_name=f"missing of required action {self.id!r}")
        if not isinstance(self.trace_indices, tuple):
            raise JevValidation.error("required-action trace indices", "a tuple of non-negative integers", self.trace_indices)
        if any(not _is_integer_index(index) or index < 0 for index in self.trace_indices):
            raise JevValidation.error("required-action trace indices", "a tuple of non-negative integers", self.trace_indices)
        if tuple(sorted(set(self.trace_indices))) != self.trace_indices:
            raise JevValidation.error("required-action trace indices", "unique indices in ascending trace order", self.trace_indices)
        if self.completion_trace_index is not None:
            if isinstance(self.completion_trace_index, bool) or not isinstance(self.completion_trace_index, int) or self.completion_trace_index < 0:
                raise JevValidation.error("required-action completion trace index", "a non-negative integer or None", self.completion_trace_index)
            if self.completion_trace_index not in self.trace_indices:
                raise JevValidation.error("required-action completion trace index", "an index also listed in trace_indices", self.completion_trace_index)
        if (self.output_source is None) != (self.output_excerpt is None):
            raise JevValidation.error("required-action output evidence", "both output_source and output_excerpt or neither", (self.output_source, self.output_excerpt))
        if self.output_source is not None:
            if not re.fullmatch(r"response\[\d+\]|final_answer", self.output_source):
                raise JevValidation.error("required-action output source", "response[n] or final_answer", self.output_source)
            JevText.require(self.output_excerpt, field_name=f"output excerpt for required action {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevRequiredActionsEvidence:
    """The handoff evidence for every request-derived required action, in run-state order."""

    actions: tuple[JevRequiredActionEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple) or not all(isinstance(item, JevRequiredActionEvidence) for item in self.actions):
            raise JevValidation.error("required-actions evidence", "a tuple of JevRequiredActionEvidence values", self.actions)
        JevDeliverableId.require_unique(self.ids(), field_name="required-actions evidence")

    def ids(self) -> tuple[str, ...]:
        """Return every evidence id in request order."""
        return tuple(item.id for item in self.actions)


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
class JevCompletionEvidence:
    """The whole-task completion status, requested outcomes, observed work, and separate continuation gap."""

    id: str
    completion_status: JevCompletionStatus
    requested_outcomes: tuple[str, ...]
    completed_work: tuple[str, ...]
    unfinished_or_blocked: tuple[str, ...]
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        # Requires the stable task item id, typed status, and immutable non-blank outcome lists.
        if self.id != JEV_DONE_COMPLETION_ITEM_ID:
            raise JevValidation.error("completion evidence id", f"the fixed id {JEV_DONE_COMPLETION_ITEM_ID!r}", self.id)
        if not isinstance(self.completion_status, JevCompletionStatus):
            raise JevValidation.error("completion status", "a JevCompletionStatus member", self.completion_status)
        for field_name in ("requested_outcomes", "completed_work", "unfinished_or_blocked"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise JevValidation.error(f"completion evidence {field_name}", "a tuple of strings", value)
            for index, text in enumerate(value):
                JevText.require(text, field_name=f"completion evidence {field_name}[{index}]")
        JevText.require(self.evidence, field_name="completion evidence observations")
        JevText.require(self.missing, field_name="completion evidence gap")


@dataclass(frozen=True, slots=True)
class JevGuaranteedNextAction:
    """One candidate follow-on action with its request outcome, observed trigger, and evidence gap."""

    id: str
    outcome: str
    trigger: str
    action: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="guaranteed next action id")
        for field_name in ("outcome", "trigger", "action", "evidence", "missing"):
            JevText.require(getattr(self, field_name), field_name=f"{field_name} of guaranteed next action {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevReportActionAlignmentItem:
    """One immutable candidate pairing a visible plan, recorded execution, final account, request relevance, and evidence."""

    id: str
    plan: str
    execution: str
    final_account: str
    request_relevance: str
    evidence: str
    missing: str

    # @intent alignment-candidates-need-complete-evidence
    # Each candidate is the unit Jev judges, so its id and every context field must be
    # valid before the handoff can expose it. Rejecting blank fields here prevents a
    # missing observation from being mistaken for a favorable report/action match.
    # Keep `missing` as continuation guidance, distinct from evidence Jev receives.
    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="report/action alignment id")
        for field_name in ("plan", "execution", "final_account", "request_relevance", "evidence", "missing"):
            JevText.require(getattr(self, field_name), field_name=f"{field_name} for report/action alignment {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevReportActionAlignment:
    """The post-run report/action comparison candidates compiled for one finish attempt."""

    items: tuple[JevReportActionAlignmentItem, ...] = ()

    # @intent alignment-answers-must-map-to-unique-candidates
    # Jev answers are keyed by candidate id. Requiring typed items and unique ids
    # ensures every answer maps to exactly one observed plan/report relationship;
    # duplicate ids could overwrite evidence and silently skip a candidate.
    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(isinstance(item, JevReportActionAlignmentItem) for item in self.items):
            raise JevValidation.error("report/action alignment items", "a tuple of JevReportActionAlignmentItem values", self.items)
        JevDeliverableId.require_unique(self.ids(), field_name="report/action alignment items")

    def ids(self) -> tuple[str, ...]:
        """Return every candidate id in handoff order."""
        return tuple(item.id for item in self.items)




@dataclass(frozen=True, slots=True)
class JevAssumptionEvidence:
    """One explicitly used assumption later contradicted, its dependent work, and run observations."""

    id: str
    original_assumption: str
    original_basis: str
    later_observation: str
    affected_work: str
    revision: str
    evidence: str
    missing: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="assumption evidence id")
        for field_name in ("original_assumption", "original_basis", "later_observation", "affected_work", "revision", "evidence", "missing"):
            JevText.require(getattr(self, field_name), field_name=f"{field_name} of assumption {self.id!r}")


@dataclass(frozen=True, slots=True)
class JevAssumptionsReconciledEvidence:
    """The post-run list of materially changed assumptions, with one stable item id per premise."""

    items: tuple[JevAssumptionEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(isinstance(item, JevAssumptionEvidence) for item in self.items):
            raise JevValidation.error("assumptions evidence", "a tuple of JevAssumptionEvidence values", self.items)
        JevDeliverableId.require_unique(self.ids(), field_name="assumptions evidence")

    def ids(self) -> tuple[str, ...]:
        """Return every changed assumption id in handoff order."""
        return tuple(item.id for item in self.items)


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
        # @intent dynamic-problem-records-preserve-typed-evidence
        # Requires typed item kind, stable identity, and all context/evidence text.
        JevDeliverableId.require(self.id, field_name="problem evidence id")
        if not isinstance(self.kind, JevProblemCheckItemType):
            raise JevValidation.error("problem evidence kind", "a JevProblemCheckItemType", self.kind)
        for field_name in ("title", "description", "scope", "qualifications", "repair", "verification", "evidence", "missing"):
            JevText.require(getattr(self, field_name), field_name=f"problem {self.id!r} {field_name}")


@dataclass(frozen=True, slots=True)
class JevGuaranteedNextActions:
    """Dynamic necessary follow-on candidates and their unique ids."""

    actions: tuple[JevGuaranteedNextAction, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple) or not all(isinstance(item, JevGuaranteedNextAction) for item in self.actions):
            raise JevValidation.error("guaranteed next actions", "a tuple of JevGuaranteedNextAction values", self.actions)
        JevDeliverableId.require_unique(self.ids(), field_name="guaranteed next actions")

    def ids(self) -> tuple[str, ...]:
        """Return candidate ids in handoff order."""
        return tuple(item.id for item in self.actions)


@dataclass(frozen=True, slots=True)
class JevProblemsResolvedEvidence:
    """Dynamic problem evidence with exactly one original-request completion item."""

    items: tuple[JevProblemResolutionItem, ...]

    # @intent problem-evidence-keeps-request-completion-distinct
    # Each observed problem gets its own answer, and the original request is judged separately even when no errors
    # occurred. Without the unique reserved completion item, repairs could pass while requested work remains undone.
    def __post_init__(self) -> None:
        # @intent a-done-verdict-needs-one-original-request-item
        # Keeps each question id unique and requires the reserved completion item exactly once.
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
    """The evidence JevHandoff compiled from the main agent's run for enabled done checks.

    Each optional typed section is present only for its check. `negative_coverage` carries one inspection account per requested target and separates inspection evidence from the final answer's negative or incomplete report. `guaranteed_next_actions` holds post-run candidate actions and is handoff-only; `required_actions` pairs request-derived action definitions with trace-backed completion evidence. Existing sections include `multi_part`,
    `claims`, `target_outcome`, `motivating_case`, `scope_coverage`, `problems_resolved`,
    `completion_evidence`, `phase_progress`, and `input_set_coverage` and request-derived `input_exhaustion`; `output_count` carries candidate
    output units and direct evidence for numeric obligations, and `output_extent` carries text-size evidence; `report_action_alignment` and `assumptions_reconciled` carry post-run comparisons; `negative_coverage` carries per-target inspection evidence and answer reports. Completion evidence and changed assumptions are
    handoff-only; input-exhaustion, input-set, and output-count evidence are matched to their run-state ids. `cumulative_obligations` reports observations for each obligation and supplied user turn without deciding completion. `discovered_item_coverage` retains bounded source outputs and their candidate inventories for separate source and item judgments. `usage` is this
    agent's model usage.
    """

    multi_part: JevMultiPartEvidence | None = None
    claims: JevClaimsEvidence | None = None
    target_outcome: JevTargetOutcomeEvidence | None = None
    problems_resolved: JevProblemsResolvedEvidence | None = None
    usage: UsageRollup | None = None
    motivating_case: JevMotivatingCaseEvidence | None = None
    scope_coverage: JevScopeCoverageEvidence | None = None
    completion_evidence: JevCompletionEvidence | None = None
    phase_progress: JevPhaseProgressEvidence | None = None
    input_set_coverage: JevInputSetCoverageEvidence | None = None
    output_count: JevOutputCountEvidence | None = None
    output_extent: JevOutputExtentEvidence | None = None
    report_action_alignment: JevReportActionAlignment | None = None
    assumptions_reconciled: JevAssumptionsReconciledEvidence | None = None
    input_exhaustion: JevInputExhaustionEvidenceSet | None = None

    negative_coverage: JevNegativeCoverageEvidence | None = None
    guaranteed_next_actions: JevGuaranteedNextActions | None = None

    required_actions: JevRequiredActionsEvidence | None = None
    cumulative_obligations: JevCumulativeObligationsEvidence | None = None
    discovered_item_coverage: JevDiscoveredItemEvidence | None = None

    def __post_init__(self) -> None:
        # Requires a typed evidence section for each enabled done check when present.
        _require_optional_jev_sections((
            ("handoff multi_part", self.multi_part, JevMultiPartEvidence),
            ("handoff phase_progress", self.phase_progress, JevPhaseProgressEvidence),
            ("handoff claims", self.claims, JevClaimsEvidence),
            ("handoff target_outcome", self.target_outcome, JevTargetOutcomeEvidence),
            ("handoff scope_coverage", self.scope_coverage, JevScopeCoverageEvidence),
            ("handoff completion_evidence", self.completion_evidence, JevCompletionEvidence),
            ("handoff input_set_coverage", self.input_set_coverage, JevInputSetCoverageEvidence),
            ("handoff problems_resolved", self.problems_resolved, JevProblemsResolvedEvidence),
            ("handoff motivating_case", self.motivating_case, JevMotivatingCaseEvidence),
            ("handoff output_count", self.output_count, JevOutputCountEvidence),
            ("handoff output_extent", self.output_extent, JevOutputExtentEvidence),
            ("handoff report_action_alignment", self.report_action_alignment, JevReportActionAlignment),
            ("handoff assumptions_reconciled", self.assumptions_reconciled, JevAssumptionsReconciledEvidence),
            ("handoff input_exhaustion", self.input_exhaustion, JevInputExhaustionEvidenceSet),
            ("handoff negative_coverage", self.negative_coverage, JevNegativeCoverageEvidence),
            ("handoff guaranteed_next_actions", self.guaranteed_next_actions, JevGuaranteedNextActions),
            ("handoff required_actions", self.required_actions, JevRequiredActionsEvidence),
            ("handoff cumulative_obligations", self.cumulative_obligations, JevCumulativeObligationsEvidence),
            ("handoff discovered_item_coverage", self.discovered_item_coverage, JevDiscoveredItemEvidence),
        ))


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
    items below the check threshold or with missing work evidence. These may be deliverables for MULTI_PART,
    numeric obligations for OUTPUT_COUNT, parent claims for CLAIMS, target outcomes, motivating cases, scope
    members, request-required phases, bounded input targets, dynamic collection ids for INPUT_EXHAUSTION, observed problems, or the fixed `task_completion`
    item for COMPLETION_EVIDENCE. GUARANTEED_NEXT_ACTIONS is handoff-only: for each candidate it asks separately whether the request and observed trigger require the action and whether evidence shows the action remains unfinished; both affirmative scores must meet the threshold for any candidate to trigger continuation. CLAIMS answers use `parent_id.assertion_id` keys so each assertion stays
    atomic. Completion evidence and assumptions-reconciled evidence are handoff-only, not request-derived run-state sections. A changed assumption remains a judgment item even when downstream work later recovered or became irrelevant. Assumptions-reconciled evidence is also handoff-only; it preserves changed premises and dependent work even when a later recovery or changed scope makes that work irrelevant.

    With `available=False` the run state, handoff, or Jev was unavailable, `score` is None, and the check fails
    Changed assumptions are handoff-only, and a recovery or irrelevant downstream result remains part of the item Jev judges.
    open (`passed` stays True). `usage` is from the one Jev request that asked every enabled check's questions.
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


@dataclass(frozen=True, slots=True)
class JevInputExhaustionObligation:
    """One request-derived collection traversal, with the scope and stopping condition that define completion."""

    id: str
    collection: str
    scope: str
    unit: str
    expected_total: int | None
    exhaustion_condition: str

    def __post_init__(self) -> None:
        JevDeliverableId.require(self.id, field_name="input-exhaustion obligation id")
        for field_name in ("collection", "scope", "unit", "exhaustion_condition"):
            JevText.require(getattr(self, field_name), field_name=f"input-exhaustion {field_name} for {self.id!r}")
        if self.expected_total is not None and (type(self.expected_total) is not int or self.expected_total < 0):
            raise JevValidation.error(f"expected total of {self.id!r}", "a non-negative integer or None", self.expected_total)


@dataclass(frozen=True, slots=True)
class JevInputExhaustion:
    """The ordered set of dynamic collection traversals the user's request explicitly requires."""

    collections: tuple[JevInputExhaustionObligation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.collections, tuple) or not all(isinstance(item, JevInputExhaustionObligation) for item in self.collections):
            raise JevValidation.error("input-exhaustion collections", "a tuple of JevInputExhaustionObligation values", self.collections)
        JevDeliverableId.require_unique(self.ids(), field_name="input-exhaustion obligations")

    def ids(self) -> tuple[str, ...]:
        """Return every stable obligation id in request order."""
        return tuple(item.id for item in self.collections)


def _is_integer_index(value: object) -> bool:
    """Return whether a trace or turn index is an int without accepting bool as its subclass."""
    return isinstance(value, int) and not isinstance(value, bool)


def _require_optional_jev_sections(sections: tuple[tuple[str, object, type[object]], ...]) -> None:
    """Validate typed optional JEV sections in the order their record declares them."""
    for field_name, value, expected in sections:
        if value is not None and not isinstance(value, expected):
            raise JevValidation.error(field_name, f"a {expected.__name__} or None", value)


__all__ = [
    "JevAgentResponse",
    "JevAnswer",
    "JevAssumptionEvidence",
    "JevAssumptionEvidencePayload",
    "JevAssumptionsReconciledEvidence",
    "JevAssumptionsReconciledPayload",
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
    "JevCompletionEvidence",
    "JevCompletionEvidencePayload",
    "JevCompletionEvidenceSectionPayload",
    "JevContent",
    "JevCriterion",
    "JevCumulativeObligation",
    "JevCumulativeObligationEvidence",
    "JevCumulativeObligationEvidenceEntryPayload",
    "JevCumulativeObligationEvidencePayload",
    "JevCumulativeObligationPayload",
    "JevCumulativeObligations",
    "JevCumulativeObligationsEvidence",
    "JevCumulativeObligationsPayload",
    "JevCumulativeUserTurnEvidence",
    "JevCumulativeUserTurnEvidenceEntryPayload",
    "JevDecisionRecord",
    "JevDecisionRequest",
    "JevDeliverable",
    "JevDeliverableEvidence",
    "JevDeliverableEvidencePayload",
    "JevDeliverableId",
    "JevDeliverablePayload",
    "JevDiscoveredItem",
    "JevDiscoveredItemBatch",
    "JevDiscoveredItemBatchEntryPayload",
    "JevDiscoveredItemBatchPayload",
    "JevDiscoveredItemEvidence",
    "JevDiscoveredItemPayload",
    "JevDoneQuestion",
    "JevDoneResult",
    "JevGuaranteedNextAction",
    "JevGuaranteedNextActionPayload",
    "JevGuaranteedNextActions",
    "JevGuaranteedNextActionsEvidencePayload",
    "JevHandoffPayload",
    "JevHandoffRecord",
    "JevInputExhaustion",
    "JevInputExhaustionEvidence",
    "JevInputExhaustionEvidencePayload",
    "JevInputExhaustionEvidenceSection",
    "JevInputExhaustionEvidenceSet",
    "JevInputExhaustionObligation",
    "JevInputExhaustionObligationPayload",
    "JevInputExhaustionPayload",
    "JevInputSetCoverage",
    "JevInputSetCoverageEvidence",
    "JevInputSetCoverageEvidencePayload",
    "JevInputSetCoveragePayload",
    "JevInputTarget",
    "JevInputTargetEvidence",
    "JevInputTargetEvidencePayload",
    "JevInputTargetPayload",
    "JevJson",
    "JevModelCard",
    "JevMotivatingCase",
    "JevMotivatingCaseEvidence",
    "JevMotivatingCaseEvidencePayload",
    "JevMotivatingCasePayload",
    "JevMotivatingScenario",
    "JevMotivatingScenarioEvidence",
    "JevMotivatingScenarioEvidencePayload",
    "JevMotivatingScenarioPayload",
    "JevMultiPart",
    "JevMultiPartEvidence",
    "JevMultiPartEvidencePayload",
    "JevMultiPartPayload",
    "JevNegativeCoverage",
    "JevNegativeCoverageEvidence",
    "JevNegativeCoverageEvidenceItem",
    "JevNegativeCoverageEvidenceItemPayload",
    "JevNegativeCoverageEvidencePayload",
    "JevNegativeCoveragePayload",
    "JevNegativeCoverageTarget",
    "JevNegativeCoverageTargetPayload",
    "JevNoulScore",
    "JevOption",
    "JevOutputCount",
    "JevOutputCountEntry",
    "JevOutputCountEntryPayload",
    "JevOutputCountEvidence",
    "JevOutputCountEvidenceItem",
    "JevOutputCountEvidencePayload",
    "JevOutputCountEvidencePayloadItem",
    "JevOutputCountObligation",
    "JevOutputCountObligationPayload",
    "JevOutputCountPayload",
    "JevOutputExtent",
    "JevOutputExtentAmount",
    "JevOutputExtentEvidence",
    "JevOutputExtentEvidenceItem",
    "JevOutputExtentEvidenceItemPayload",
    "JevOutputExtentEvidencePayload",
    "JevOutputExtentItem",
    "JevOutputExtentItemPayload",
    "JevOutputExtentPayload",
    "JevPhaseProgress",
    "JevPhaseProgressEvidence",
    "JevPhaseProgressEvidencePayload",
    "JevPhaseProgressPayload",
    "JevPhaseStage",
    "JevPhaseStageEvidence",
    "JevPhaseStageEvidencePayload",
    "JevPhaseStagePayload",
    "JevPreflightQuestion",
    "JevPresetDefinition",
    "JevPresetResult",
    "JevProbability",
    "JevProblemEvidencePayload",
    "JevProblemResolutionItem",
    "JevProblemsResolvedEvidence",
    "JevProblemsResolvedEvidencePayload",
    "JevQuestion",
    "JevReportActionAlignment",
    "JevReportActionAlignmentEvidencePayload",
    "JevReportActionAlignmentEvidenceSectionPayload",
    "JevReportActionAlignmentItem",
    "JevRequiredAction",
    "JevRequiredActionEvidence",
    "JevRequiredActionEvidencePayload",
    "JevRequiredActionPayload",
    "JevRequiredActions",
    "JevRequiredActionsEvidence",
    "JevRequiredActionsEvidencePayload",
    "JevRequiredActionsPayload",
    "JevRunStatePayload",
    "JevRunStateRecord",
    "JevScopeCoverage",
    "JevScopeCoverageEvidence",
    "JevScopeCoverageEvidencePayload",
    "JevScopeCoveragePayload",
    "JevScopeDimension",
    "JevScopeDimensionEvidence",
    "JevScopeDimensionEvidencePayload",
    "JevScopeDimensionPayload",
    "JevScopeUnitEvidence",
    "JevScopeUnitEvidencePayload",
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
