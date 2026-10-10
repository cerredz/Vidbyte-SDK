"""FILE: vidbyte/providers/openai_decisions.py

PURPOSE: The OpenAI Decisions wire: `OpenAIDecisionsRequest` builds and encodes the `{model, input, questions[]}` body (noul as `predicate`, choice with `choices`, score with `levels`), `OpenAIDecisionsAnswers` turns the `answers` array into JevAnswer records matched by `name`, and `OpenAIDecisionsProvider` sends direct decision calls to OpenAI's POST /v1/decisions (or any host that mirrors it, such as Vercel AI Gateway by endpoint override).
ROLE IN CODEBASE: `ModelProviders.decision()` builds `OpenAIDecisionsProvider` for `ModelProvider.OPENAI` and `vidbyte/lib/runners/decision.py` calls `run_decision`; the wire records come from `vidbyte/lib/dataclasses/jev.py` and the HTTP call and failure wording from `vidbyte/providers/decisions.py`.
ARCHITECTURE NOTE: The records stay encoder-free: only `OpenAIDecisionsRequest.encode` turns a wire record into JSON, and HTTP goes through `vidbyte.lib.http` via `DecisionHttpCall`. Answers normalize onto the same JevAnswer shapes the System One wire produces, so `DecisionModelHelper` reads both alike. Imports only `vidbyte.lib` and `vidbyte.providers.decisions` (A006).
COMMON MODIFICATION PATTERNS: When OpenAI changes the Decisions API, update the wire records, `OpenAIDecisionsRequest`, and `OpenAIDecisionsAnswers` together and extend the scripted-transport tests; wire literals belong in `vidbyte/lib/constants/jev.py`.
KNOWN EDGE CASES: `input`, `instructions`, and option descriptions are strings on this wire, so structured content is sent as JSON text. A predicate has no criteria slot, so noul option descriptions are refused before the call rather than dropped. Answers arrive as an array in any order; a `refusal` answer, a duplicate, missing, or extra name, a wrong type, or a malformed distribution is a ProviderResponseError carrying the billed usage. Score entries without `label` use `value` as the level index. No response-level `model` echo is documented, so the response reports the requested model id, which is what the ledger prices. There is no model-list endpoint or managed run, so `list_models` and `close_run` raise; the URL comes from OpenAI's direct endpoint, never `DecisionModelConfig.resolved_endpoint()`, whose managed branch points at the Vidbyte gateway (C017).
RELATED DOCS: vidbyte/providers/README.md ("Decision providers"), docs/spec/decision-model-providers/spec.md, https://developers.openai.com/api/docs/guides/decisions.
TESTS: tests/features/decision_model_providers/test_decision_openai_wire.py, tests/features/decision_model_providers/test_decision_failures.py, and tests/features/decision_model_providers/test_decision_usage_metering.py.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_NO_RETRIES,
    JEV_NOUL_FALSE,
    JEV_NOUL_TRUE,
    JEV_NOUL_YES_THRESHOLD,
    OPENAI_DECISIONS_PATH,
    OPENAI_DECISIONS_PREDICATE_TYPE,
    OPENAI_DECISIONS_REFUSAL_TYPE,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevContent,
    JevDecisionRequest,
    JevJson,
    JevModelCard,
    JevOption,
    JevProbability,
    JevQuestion,
    JevValidation,
    OpenAIDecisionsWireQuestion,
    OpenAIDecisionsWireRequest,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.providers.decisions import DecisionFailures, DecisionHttpCall

# The host name every OpenAI Decisions message carries.
_LABEL = "OpenAI"


class OpenAIDecisionsRequest:
    """Builds the typed OpenAI Decisions body from a validated JevDecisionRequest and encodes it as plain JSON."""

    @staticmethod
    def build(config: DecisionModelConfig, request: JevDecisionRequest) -> OpenAIDecisionsWireRequest:
        # Returns the {model, input, questions} body with the questions in request order.
        # @intent wire-shape-owned-by-provider
        # The records stay encoder-free; this is the only place the OpenAI Decisions body is shaped, so an
        # API change is a one-file edit plus its scripted-transport tests.
        questions = tuple(OpenAIDecisionsRequest.question(question) for question in request.questions)
        return OpenAIDecisionsWireRequest(model=config.resolved_model(), input=OpenAIDecisionsRequest.text(request.state, field_name="state"), questions=questions)

    @staticmethod
    def question(question: JevQuestion) -> OpenAIDecisionsWireQuestion:
        # Returns one wire question: a noul becomes an option-free predicate; choice and score carry their options.
        # @intent predicate-criteria-are-refused-not-dropped
        # A predicate has only instructions, so sending a noul whose true/false options carry criteria would
        # silently ignore the caller's rubric; the call is refused before anything is sent.
        instructions = OpenAIDecisionsRequest.text(question.instructions, field_name=f"instructions of question {question.name!r}")
        if question.question_type is not JevQuestionType.NOUL:
            return OpenAIDecisionsWireQuestion(type=question.question_type.value, name=question.name, instructions=instructions, options=question.options)
        if any(option.description is not None for option in question.options):
            raise ConfigurationError(f"OpenAI predicate questions take instructions only; question {question.name!r} carries true/false criteria — move them into its instructions.")
        return OpenAIDecisionsWireQuestion(type=OPENAI_DECISIONS_PREDICATE_TYPE, name=question.name, instructions=instructions)

    @staticmethod
    def text(value: JevContent, *, field_name: str) -> str:
        # Returns a string unchanged and structured content as JSON text, because this wire takes strings only.
        if isinstance(value, str):
            return value
        try:
            return json.dumps(JevJson.thaw(value), ensure_ascii=False)
        except RecursionError as exc:
            raise JevValidation.error(field_name, "JSON nested shallowly enough to encode", "structure deeper than Python's recursion limit") from exc

    @staticmethod
    def encode(wire: OpenAIDecisionsWireRequest) -> dict[str, object]:
        # Turns the wire record into the documented JSON: choice options become `choices` keyed by `value`, score
        # levels become `levels` keyed by `label` (lowest first), and a predicate carries no options.
        questions: list[dict[str, object]] = []
        for question in wire.questions:
            entry: dict[str, object] = {"type": question.type, "name": question.name, "instructions": question.instructions}
            if question.type == JevQuestionType.CHOICE.value:
                entry["choices"] = [OpenAIDecisionsRequest.option(option, key="value") for option in question.options]
            elif question.type == JevQuestionType.SCORE.value:
                entry["levels"] = [OpenAIDecisionsRequest.option(option, key="label") for option in question.options]
            questions.append(entry)
        return {"model": wire.model, "input": wire.input, "questions": questions}

    @staticmethod
    def option(option: JevOption, *, key: str) -> dict[str, object]:
        # Returns one choice or level entry, sending a description only when the option has one.
        if option.description is None:
            return {key: option.name}
        return {key: option.name, "description": OpenAIDecisionsRequest.text(option.description, field_name=f"description of option {option.name!r}")}


class OpenAIDecisionsAnswers:
    """Turns the OpenAI Decisions `answers` array into JevAnswer records, rejecting any drift from the documented contract."""

    def __init__(self, usage: Mapping[str, Any] | None) -> None:
        # Keeps the usage so every normalization failure still reports the billed call.
        self._usage = usage

    def normalize(self, request: JevDecisionRequest, parsed: Mapping[str, Any]) -> Mapping[str, JevAnswer]:
        # Returns exactly one JevAnswer per requested question, keyed by question name, whatever the array order.
        # @intent every-question-gets-exactly-one-answer
        # A partial, repeated, or extra answer would let a caller act on a decision OpenAI never made, so any
        # mismatch with the questions sent fails the whole call with the billed usage attached.
        answers = parsed.get("answers")
        if not isinstance(answers, list):
            raise self.error(f"{_LABEL} response has no `answers` array; received {JevValidation.describe(answers)}.")
        by_name = self._by_name(answers)
        names = [question.name for question in request.questions]
        missing = [name for name in names if name not in by_name]
        unexpected = sorted(name for name in by_name if name not in names)
        if missing or unexpected:
            raise self.error(f"{_LABEL} answers do not match the questions sent: missing {missing}, unexpected {unexpected}.")
        return MappingProxyType({question.name: self._answer(question, by_name[question.name]) for question in request.questions})

    def error(self, message: str) -> ProviderResponseError:
        # Builds a ProviderResponseError whose details keep the usage of the call that was billed.
        # @intent billed-calls-stay-billable-on-bad-answers
        # OpenAI charges for a request even when its answer fails our normalization (a refusal included), so
        # the usage rides on the error for the caller to report; dropping it would under-bill.
        error = ProviderResponseError(message, provider=ModelProvider.OPENAI.value)
        if isinstance(self._usage, Mapping):
            error.details["usage"] = dict(self._usage)
        return error

    def _by_name(self, answers: list[object]) -> dict[str, Mapping[str, Any]]:
        # Indexes the answers array by each entry's `name`, rejecting non-object entries and repeated names.
        by_name: dict[str, Mapping[str, Any]] = {}
        for entry in answers:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
                raise self.error(f"{_LABEL} answer entry has no string `name`; received {JevValidation.describe(entry)}.")
            if entry["name"] in by_name:
                raise self.error(f"{_LABEL} answered question {entry['name']!r} more than once.")
            by_name[entry["name"]] = entry
        return by_name

    def _answer(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Rejects a refusal or a wrong type tag, then dispatches to the normalizer for the question's type.
        expected = OPENAI_DECISIONS_PREDICATE_TYPE if question.question_type is JevQuestionType.NOUL else question.question_type.value
        if raw.get("type") == OPENAI_DECISIONS_REFUSAL_TYPE:
            raise self.error(f"{_LABEL} refused question {question.name!r}.")
        if raw.get("type") != expected:
            raise self.error(f"{_LABEL} answer for {question.name!r} has type {raw.get('type')!r}, but the question was sent as {expected!r}.")
        try:
            if question.question_type is JevQuestionType.NOUL:
                return self._predicate(question, raw)
            if question.question_type is JevQuestionType.SCORE:
                return self._score(question, raw)
            return self._choice(question, raw)
        except ConfigurationError as exc:
            raise self.error(f"{_LABEL} answer for {question.name!r} was malformed: {exc.message}") from exc

    def _predicate(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Expands the scalar `probability` (P(true)) into the same true/false answer a System One noul produces.
        p_yes = JevProbability.require(raw.get("probability"), field_name=f"probability of answer to {question.name!r}")
        choice = JEV_NOUL_TRUE if p_yes >= JEV_NOUL_YES_THRESHOLD else JEV_NOUL_FALSE
        return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities={JEV_NOUL_TRUE: p_yes, JEV_NOUL_FALSE: 1.0 - p_yes}, noul=p_yes)

    def _choice(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Reads `choice`, the `probabilities` array keyed by each entry's `value`, and `confidence`.
        entries = self._entries(question, raw.get("probabilities"))
        probabilities = self._distribution(question, [(entry.get("value"), entry.get("probability")) for entry in entries])
        choice = raw.get("choice")
        if choice not in probabilities:
            raise self.error(f"{_LABEL} chose {choice!r} for {question.name!r}, outside its options {list(question.option_names())}.")
        return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities=probabilities, confidence=raw.get("confidence"))

    def _score(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Reads the `probabilities` array keyed by level label (or by `value` as the level index), `score`, and `confidence`.
        names = question.option_names()
        entries = self._entries(question, raw.get("probabilities"))
        probabilities = self._distribution(question, [(self._level(names, entry), entry.get("probability")) for entry in entries])
        choice = max(names, key=lambda name: probabilities[name])
        return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities=probabilities, confidence=raw.get("confidence"), score=raw.get("score"))

    def _entries(self, question: JevQuestion, raw: object) -> list[Mapping[str, Any]]:
        # Returns the `probabilities` array, raising unless it is a list of objects.
        if not isinstance(raw, list) or not all(isinstance(entry, Mapping) for entry in raw):
            raise self.error(f"{_LABEL} answer for {question.name!r} has no `probabilities` array of objects; received {JevValidation.describe(raw)}.")
        return raw

    def _distribution(self, question: JevQuestion, pairs: list[tuple[object, object]]) -> dict[str, float]:
        # Returns a distribution over exactly the question's options, in option order, each value a probability.
        names = question.option_names()
        keys = [key for key, _ in pairs]
        missing = [name for name in names if name not in keys]
        unexpected = sorted(str(key) for key in keys if key not in names)
        if missing or unexpected:
            raise self.error(f"{_LABEL} `probabilities` for {question.name!r} do not match its options: missing {missing}, unexpected {unexpected}.")
        if len(keys) != len(names):
            raise self.error(f"{_LABEL} `probabilities` for {question.name!r} list an option more than once.")
        values = {key: value for key, value in pairs if isinstance(key, str)}
        return {name: JevProbability.require(values[name], field_name=f"probability {name!r} of answer to {question.name!r}") for name in names}

    @staticmethod
    def _level(names: tuple[str, ...], entry: Mapping[str, Any]) -> object:
        # Returns the entry's `label`, else the level its integer `value` indexes, else None (reported as unexpected).
        label = entry.get("label")
        if isinstance(label, str):
            return label
        value = entry.get("value")
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(names):
            return names[value]
        return None


class OpenAIDecisionsProvider:
    """Decision adapter for OpenAI's Decisions API (and hosts that mirror it by endpoint override)."""

    provider = ModelProvider.OPENAI

    def __init__(self, *, decision_config: DecisionModelConfig | None = None, response_parser: HttpResponseParser | None = None, **_: Any) -> None:
        # Stores the decision config; other factory kwargs are accepted and ignored.
        self._decision_config = decision_config
        self._parser = response_parser or HttpResponseParser()

    async def run_decision(self, *, request: JevDecisionRequest, transport: HttpTransport, config: DecisionModelConfig | None = None) -> DecisionModelResponse:
        # POSTs one Decisions request and returns its normalized answers, the requested model id, and raw usage.
        # @intent one-guarded-decision-call
        # Every failure funnels through one try: a missing or foreign config and refused criteria stay configuration
        # errors, a normalization failure (a refusal included) keeps its billed usage, transport and HTTP failures
        # are rewritten per documented status, and anything unanticipated becomes a ProviderResponseError instead
        # of a bare exception. Cancellation is a BaseException and propagates untouched.
        usage: Mapping[str, Any] | None = None
        resolved: DecisionModelConfig | None = None
        try:
            # Use the per-call config when one is given (it must be an OpenAI config), else the adapter's own.
            resolved = self._config_for(config)
            # Send one POST to /decisions; the transport retries it with the same idempotency key.
            response = await self._call(resolved, request).send(transport)
            parsed = self._parser.parse_json_response(response, provider=self.provider.value)
            # Read the usage first, so a refused or malformed answer below still reports the billed call.
            raw_usage = parsed.get("usage")
            usage = raw_usage if isinstance(raw_usage, Mapping) else None
            answers = OpenAIDecisionsAnswers(usage).normalize(request, parsed)
            # OpenAI documents no response-level model echo, so the ledger prices the model id that was requested.
            return DecisionModelResponse(provider=self.provider, model=resolved.resolved_model(), answers=answers, raw=parsed, usage=usage)
        except ProviderResponseError:
            raise
        except (ProviderConfigurationError, ConfigurationError):
            raise
        except ProviderRequestError as exc:
            raise DecisionFailures.transport_error(exc, operation="decision", provider=self.provider, label=_LABEL, config=resolved) from exc
        except Exception as exc:
            raise DecisionFailures.unexpected(exc, operation="decision", provider=self.provider, usage=usage) from exc

    async def list_models(self, *, transport: HttpTransport, config: DecisionModelConfig | None = None) -> tuple[JevModelCard, ...]:
        # Refuses without a network call: the Decisions API publishes no model-list endpoint.
        # @intent missing-capabilities-are-refused-not-faked
        # An empty tuple would read as "this account has no models", so the caller is told to pin `model` instead.
        raise ProviderConfigurationError(f"{_LABEL} publishes no model-list endpoint; pass DecisionModelConfig.model explicitly.", provider=self.provider.value)

    async def close_run(self, *, run_id: str, transport: HttpTransport, config: DecisionModelConfig | None = None) -> None:
        # Refuses without a network call: only the managed TypeSafe gateway has runs to close.
        # @intent missing-capabilities-are-refused-not-faked
        # Silently succeeding would hide a caller that believes it is settling a managed run.
        raise ProviderConfigurationError(f"{_LABEL} decisions have no managed runs to close.", provider=self.provider.value)

    def _config_for(self, config: DecisionModelConfig | None) -> DecisionModelConfig:
        # Resolves the active config: the per-call one when given, else the adapter's, refusing another provider's.
        # @intent per-call-config-stays-on-this-host
        # Another provider's config would post its key to OpenAI's host, so it is refused before any URL or header is built.
        resolved = config or self._decision_config
        if resolved is None:
            raise ProviderConfigurationError("OpenAIDecisionsProvider requires a DecisionModelConfig: pass config= to the call or decision_config= to the adapter.", provider=self.provider.value)
        other = resolved.normalized_provider()
        if other is not self.provider:
            raise ProviderConfigurationError(f"{_LABEL} adapter received a config for provider '{other.value}'.", provider=self.provider.value)
        return resolved

    def _call(self, config: DecisionModelConfig, request: JevDecisionRequest) -> DecisionHttpCall:
        # Returns the bearer-authenticated POST /decisions call with the configured timeout and retries.
        # @intent decisions-retry-with-an-idempotency-key
        # A decision has no side effects, so the key only satisfies the transport's POST retry guard and is never sent as a header.
        idempotency_key = uuid.uuid4().hex if config.retry_count > JEV_NO_RETRIES else None
        body = OpenAIDecisionsRequest.encode(OpenAIDecisionsRequest.build(config, request))
        headers = self._parser.bearer_headers(config.resolved_api_key())
        # The URL is OpenAI's endpoint (an explicit override first); managed mode is TypeSafe-only, so it never applies here.
        endpoint = ProviderModelRegistry.resolve_endpoint(self.provider, config.endpoint)
        return DecisionHttpCall(method="POST", url=f"{endpoint}{OPENAI_DECISIONS_PATH}", headers=headers, timeout_seconds=config.timeout_seconds, json_body=body, retry_count=config.retry_count, idempotency_key=idempotency_key)


__all__ = ["OpenAIDecisionsAnswers", "OpenAIDecisionsProvider", "OpenAIDecisionsRequest"]
