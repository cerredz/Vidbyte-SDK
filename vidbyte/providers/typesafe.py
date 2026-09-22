"""FILE: vidbyte/providers/typesafe.py

PURPOSE: Provider adapter for TypeSafe's System One API: builds the typed wire body for a JevDecisionRequest, sends it, normalizes Jev's answers into JevAnswer records, and lists the models an account can use.
ROLE IN CODEBASE: `ModelProviders.decision()` builds this adapter and `vidbyte/lib/runners/decision.py` calls `run_decision` and `list_models` for programmatic Jev decisions.
ARCHITECTURE NOTE: This module owns the wire shape in both directions. Builders return the TypeSafeWireRequest/TypeSafeWireQuestion records from vidbyte/lib/dataclasses/jev.py; only _TypeSafeJsonBody turns one into the plain JSON the transport sends, and HTTP goes through vidbyte.lib.http only.
COMMON MODIFICATION PATTERNS: When TypeSafe changes its API, update the wire records, _TypeSafePayloadBuilder, and _TypeSafeAnswerNormalizer together and extend the scripted-transport tests.
KNOWN EDGE CASES: Score answers key probabilities by level index strings and carry a weighted `score` between levels; both normalize onto level labels. Noul answers carry no confidence. A malformed answer raises ProviderResponseError carrying the billed usage in details["usage"].
RELATED DOCS: docs/design/jev-agent-scaffold.md, https://docs.typesafe.ai/api.md, and https://docs.typesafe.ai/models.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_MAX_RESPONSE_BYTES,
    JEV_MODELS_PATH,
    JEV_NO_RETRIES,
    JEV_NOUL_FALSE,
    JEV_NOUL_TRUE,
    JEV_NOUL_YES_THRESHOLD,
    JEV_RETRY_BACKOFF_SECONDS,
    JEV_RETRY_STATUS_CODES,
    JEV_STATUS_OVERLOADED,
    JEV_STATUS_RATE_LIMITED,
    JEV_STATUS_REQUEST_TIMEOUT,
    JEV_STATUS_SERVER_ERROR_FLOOR,
    JEV_STATUS_UNAUTHORIZED,
    JEV_STATUS_UNPROCESSABLE,
    JEV_SYSTEMONE_PATH,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevContent,
    JevDecisionRequest,
    JevJson,
    JevModelCard,
    JevProbability,
    JevQuestion,
    JevValidation,
    TypeSafeWireQuestion,
    TypeSafeWireRequest,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponse, HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import DecisionModelResponse

_PROVIDER = ModelProvider.TYPESAFE.value


class _TypeSafePayloadBuilder:
    """Builds the typed System One wire body from a validated JevDecisionRequest."""

    @staticmethod
    def build(config: DecisionModelConfig, request: JevDecisionRequest) -> TypeSafeWireRequest:
        # Returns the {model, state, questions} body with one wire question per named question.
        # @intent wire-shape-owned-by-provider
        # The records stay encoder-free; this is the only place the System One body is shaped,
        # so an API change is a one-file edit plus its scripted-transport tests.
        questions = {question.name: _TypeSafePayloadBuilder.question(question) for question in request.questions}
        return TypeSafeWireRequest(model=config.model, state=request.state, questions=questions)

    @staticmethod
    def question(question: JevQuestion) -> TypeSafeWireQuestion:
        # Returns one wire question: its type, its instructions, and the criteria its type defines.
        return TypeSafeWireQuestion(type=question.question_type.value, instructions=question.instructions, criteria=_TypeSafePayloadBuilder.criteria(question))

    @staticmethod
    def criteria(question: JevQuestion) -> JevContent | None:
        # Score levels are an ordered array; Choice and Noul map option to description; an optionless Noul sends none.
        if question.question_type is JevQuestionType.SCORE:
            return tuple(option.name if option.description is None else option.description for option in question.options)
        if not question.options:
            return None
        return MappingProxyType({option.name: option.description for option in question.options})


class _TypeSafeJsonBody:
    """Turns a TypeSafe wire record into the plain JSON mapping the HTTP transport encodes."""

    @staticmethod
    def encode(wire: TypeSafeWireRequest) -> dict[str, object]:
        # Thaws frozen content and omits absent optional criteria, matching the documented request body.
        questions: dict[str, object] = {}
        for name, question in wire.questions.items():
            entry: dict[str, object] = {"type": question.type, "instructions": JevJson.thaw(question.instructions)}
            if question.criteria is not None:
                entry["criteria"] = JevJson.thaw(question.criteria)
            questions[name] = entry
        return {"model": wire.model, "state": JevJson.thaw(wire.state), "questions": questions}


@dataclass(frozen=True, slots=True)
class _TypeSafeHttpCall:
    """One fully resolved HTTP call to the TypeSafe API; headers stay out of repr because they carry the key."""

    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)
    timeout_seconds: float
    json_body: Mapping[str, object] | None = None
    retry_count: int = JEV_NO_RETRIES
    idempotency_key: str | None = None

    async def send(self, transport: HttpTransport) -> HttpResponse:
        # Sends this call with TypeSafe's bounded body size, retry statuses, and backoff.
        return await transport.request(method=self.method, url=self.url, headers=self.headers, json_body=self.json_body, timeout_seconds=self.timeout_seconds, retry_count=self.retry_count, backoff_seconds=JEV_RETRY_BACKOFF_SECONDS, retry_status_codes=JEV_RETRY_STATUS_CODES, max_response_bytes=JEV_MAX_RESPONSE_BYTES, idempotency_key=self.idempotency_key)


class _TypeSafeCallBuilder:
    """Builds the typed HTTP calls for each TypeSafe endpoint from a resolved config."""

    def __init__(self, parser: HttpResponseParser) -> None:
        # Keeps the parser that formats the bearer-auth headers.
        self._parser = parser

    def decision(self, config: DecisionModelConfig, request: JevDecisionRequest) -> _TypeSafeHttpCall:
        # Returns the POST /systemone call with the configured timeout and optional retries.
        # @intent decisions-retry-with-an-idempotency-key
        # A decision has no side effects, so a retried POST cannot duplicate anything; the
        # per-request idempotency key only satisfies the transport's POST retry guard.
        retrying = config.retry_count > JEV_NO_RETRIES
        body = _TypeSafeJsonBody.encode(_TypeSafePayloadBuilder.build(config, request))
        return _TypeSafeHttpCall(method="POST", url=f"{config.resolved_endpoint()}{JEV_SYSTEMONE_PATH}", headers=self._parser.bearer_headers(config.resolved_api_key()), timeout_seconds=config.timeout_seconds, json_body=body, retry_count=config.retry_count, idempotency_key=uuid.uuid4().hex if retrying else None)

    def models(self, config: DecisionModelConfig) -> _TypeSafeHttpCall:
        # Returns the GET /models call; GET is idempotent, so retries need no key.
        # @intent model-list-retries-without-a-key
        # The transport only demands an idempotency key for non-idempotent methods, so the
        # configured retry count applies to this read as-is.
        return _TypeSafeHttpCall(method="GET", url=f"{config.resolved_endpoint()}{JEV_MODELS_PATH}", headers=self._parser.bearer_headers(config.resolved_api_key()), timeout_seconds=config.timeout_seconds, retry_count=config.retry_count)


class _TypeSafeFailures:
    """Rewrites transport and unexpected failures into errors that say what TypeSafe reported and how to fix it."""

    @staticmethod
    def transport_error(exc: ProviderRequestError, *, operation: str, config: DecisionModelConfig | None) -> ProviderRequestError:
        # Maps each documented HTTP status (and a missing response) to a specific, actionable message.
        # @intent http-failures-name-cause-and-fix
        # The generic transport error only says a request failed; TypeSafe documents what 401,
        # 422, 429, and 529 mean, so the rewritten message tells the caller which knob to turn.
        status = exc.status_code
        timeout = f"{config.timeout_seconds}s" if config is not None else "configured"
        retries = config.retry_count if config is not None else JEV_NO_RETRIES
        if status is None:
            reason = f"no response arrived (network failure or the {timeout} timeout elapsed); raise DecisionModelConfig.timeout_seconds or retry_count if this recurs"
        elif status == JEV_STATUS_UNAUTHORIZED:
            reason = "TypeSafe rejected the API key (401); check TYPESAFE_API_KEY or DecisionModelConfig.api_key"
        elif status == JEV_STATUS_UNPROCESSABLE:
            reason = "TypeSafe rejected the request body as invalid (422); the response excerpt names the offending field"
        elif status == JEV_STATUS_RATE_LIMITED:
            reason = f"TypeSafe's rate limit was exceeded (429) after {retries} retries; back off or raise DecisionModelConfig.retry_count"
        elif status == JEV_STATUS_OVERLOADED or status >= JEV_STATUS_SERVER_ERROR_FLOOR:
            reason = f"TypeSafe is overloaded or failing ({status}) after {retries} retries; retry after a short delay"
        elif status == JEV_STATUS_REQUEST_TIMEOUT:
            reason = f"TypeSafe timed out the request (408) after {retries} retries"
        else:
            reason = f"TypeSafe returned HTTP {status}"
        return ProviderRequestError(f"TypeSafe {operation} request failed: {reason}. Underlying error: {exc.message}", provider=_PROVIDER, status_code=status, response_excerpt=exc.response_excerpt)

    @staticmethod
    def unexpected(exc: Exception, *, operation: str, usage: Mapping[str, Any] | None) -> ProviderResponseError:
        # Wraps an error no specific branch anticipated, keeping any billed usage for the caller.
        # @intent no-bare-exception-escapes-the-provider
        # Callers catch SDK errors to fail open; a stray TypeError from a drifted payload must
        # arrive as a ProviderResponseError, not as an exception type they never expected.
        error = ProviderResponseError(f"TypeSafe {operation} failed with an unexpected {type(exc).__name__}: {exc}", provider=_PROVIDER)
        if usage is not None:
            error.details["usage"] = dict(usage)
        return error


class _TypeSafeAnswerNormalizer:
    """Turns System One answers into JevAnswer records, rejecting any drift from the documented contract."""

    def __init__(self, usage: Mapping[str, Any] | None) -> None:
        # Keeps the usage so every normalization failure still reports the billed call.
        self._usage = usage

    def normalize(self, request: JevDecisionRequest, parsed: Mapping[str, Any]) -> Mapping[str, JevAnswer]:
        # Returns exactly one JevAnswer per requested question, keyed by question name.
        answers = parsed.get("answers")
        if not isinstance(answers, Mapping):
            raise self.error(f"TypeSafe response has no `answers` object; received {JevValidation.describe(answers)}.")
        names = [question.name for question in request.questions]
        missing = [name for name in names if name not in answers]
        unexpected = sorted(str(key) for key in answers if key not in names)
        if missing or unexpected:
            raise self.error(f"TypeSafe answers do not match the questions sent: missing {missing}, unexpected {unexpected}.")
        return MappingProxyType({question.name: self._answer(question, answers[question.name]) for question in request.questions})

    def error(self, message: str) -> ProviderResponseError:
        # Builds a ProviderResponseError whose details keep the usage of the call that was billed.
        # @intent billed-calls-stay-billable-on-bad-answers
        # TypeSafe charges for a request even when its answer fails our normalization, so
        # the usage rides on the error for the caller to report; dropping it would under-bill.
        error = ProviderResponseError(message, provider=_PROVIDER)
        if isinstance(self._usage, Mapping):
            error.details["usage"] = dict(self._usage)
        return error

    def _answer(self, question: JevQuestion, raw: object) -> JevAnswer:
        # Checks the answer's type tag, then dispatches to the normalizer for its question type.
        if not isinstance(raw, Mapping):
            raise self.error(f"TypeSafe answer for {question.name!r} is not an object; received {JevValidation.describe(raw)}.")
        if raw.get("type") != question.question_type.value:
            raise self.error(f"TypeSafe answer for {question.name!r} has type {raw.get('type')!r}, but the question was {question.question_type.value!r}.")
        try:
            if question.question_type is JevQuestionType.NOUL:
                return self._noul(question, raw)
            if question.question_type is JevQuestionType.SCORE:
                return self._score(question, raw)
            return self._choice(question, raw)
        except ConfigurationError as exc:
            raise self.error(f"TypeSafe answer for {question.name!r} was malformed: {exc.message}") from exc

    def _choice(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Reads `choice`, `probabilities` over every option, and `confidence`.
        probabilities = self._distribution(question, raw.get("probabilities"), question.option_names())
        choice = raw.get("choice")
        if choice not in probabilities:
            raise self.error(f"TypeSafe chose {choice!r} for {question.name!r}, outside its options {list(question.option_names())}.")
        return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities=probabilities, confidence=raw.get("confidence"))

    def _score(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Maps index-keyed probabilities and legend onto level labels and keeps the weighted score.
        names = question.option_names()
        indices = tuple(str(index) for index in range(len(names)))
        by_index = self._distribution(question, raw.get("probabilities"), indices)
        self._keyed(question, raw.get("legend"), indices, label="legend")
        probabilities = {names[int(index)]: value for index, value in by_index.items()}
        choice = max(names, key=lambda name: probabilities[name])
        return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities=probabilities, confidence=raw.get("confidence"), score=raw.get("score"))

    def _noul(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Expands the single P(yes) into a true/false distribution without inventing a confidence.
        p_yes = JevProbability.require(raw.get("noul"), field_name=f"noul of answer to {question.name!r}")
        choice = JEV_NOUL_TRUE if p_yes >= JEV_NOUL_YES_THRESHOLD else JEV_NOUL_FALSE
        return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities={JEV_NOUL_TRUE: p_yes, JEV_NOUL_FALSE: 1.0 - p_yes}, noul=p_yes)

    def _distribution(self, question: JevQuestion, raw: object, keys: tuple[str, ...]) -> dict[str, float]:
        # Returns the `probabilities` object over exactly the expected keys, each validated as a probability.
        values = self._keyed(question, raw, keys, label="probabilities")
        return {key: JevProbability.require(value, field_name=f"probability {key!r} of answer to {question.name!r}") for key, value in values.items()}

    def _keyed(self, question: JevQuestion, raw: object, keys: tuple[str, ...], *, label: str) -> dict[str, object]:
        # Returns raw's values in key order, raising unless raw maps exactly the expected keys.
        if not isinstance(raw, Mapping):
            raise self.error(f"TypeSafe answer for {question.name!r} has no `{label}` object; received {JevValidation.describe(raw)}.")
        missing = [key for key in keys if key not in raw]
        unexpected = sorted(str(key) for key in raw if key not in keys)
        if missing or unexpected:
            raise self.error(f"TypeSafe `{label}` for {question.name!r} do not match its options: missing {missing}, unexpected {unexpected}.")
        return {key: raw[key] for key in keys}


class _TypeSafeModelListNormalizer:
    """Turns a GET /models body into JevModelCard records."""

    @staticmethod
    def normalize(parsed: Mapping[str, Any]) -> tuple[JevModelCard, ...]:
        # Returns one card per listed model, raising ProviderResponseError on any malformed entry.
        # @intent model-list-drift-is-an-error
        # A partially parsed list would silently hide models, so any malformed entry fails the call.
        models = parsed.get("models")
        if not isinstance(models, list):
            raise ProviderResponseError(f"TypeSafe model list has no `models` array; received {JevValidation.describe(models)}.", provider=_PROVIDER)
        cards: list[JevModelCard] = []
        for index, entry in enumerate(models):
            if not isinstance(entry, Mapping):
                raise ProviderResponseError(f"TypeSafe model list entry {index} is not an object; received {JevValidation.describe(entry)}.", provider=_PROVIDER)
            name, description, release_date = (entry.get(key) for key in ("name", "description", "release_date"))
            if not isinstance(name, str) or not isinstance(description, str) or not isinstance(release_date, str):
                raise ProviderResponseError(f"TypeSafe model list entry {index} needs string name, description, and release_date; received {JevValidation.describe(dict(entry))}.", provider=_PROVIDER)
            try:
                cards.append(JevModelCard(name=name, description=description, release_date=release_date))
            except ConfigurationError as exc:
                raise ProviderResponseError(f"TypeSafe model list entry {index} was malformed: {exc.message}", provider=_PROVIDER) from exc
        return tuple(cards)


class TypeSafeProvider:
    """Decision-only provider adapter for TypeSafe's Jev models."""

    provider = ModelProvider.TYPESAFE

    def __init__(self, *, decision_config: DecisionModelConfig | None = None, response_parser: HttpResponseParser | None = None, **_: Any) -> None:
        # Stores the decision config; other factory kwargs are accepted and ignored.
        self._decision_config = decision_config
        self._parser = response_parser or HttpResponseParser()
        self._calls = _TypeSafeCallBuilder(self._parser)

    async def run_decision(self, *, request: JevDecisionRequest, transport: HttpTransport, config: DecisionModelConfig | None = None) -> DecisionModelResponse:
        # POSTs one System One request and returns its normalized answers, versioned model, and raw usage.
        # @intent one-guarded-decision-call
        # Every failure funnels through one try: missing config or key stays a configuration error,
        # a normalization failure keeps its billed usage, transport and HTTP failures are rewritten
        # per documented status, and anything unanticipated becomes a ProviderResponseError instead
        # of a bare exception. Cancellation is a BaseException and propagates untouched.
        usage: Mapping[str, Any] | None = None
        resolved: DecisionModelConfig | None = None
        try:
            resolved = self._config_for(config)
            response = await self._calls.decision(resolved, request).send(transport)
            parsed = self._parser.parse_json_response(response, provider=_PROVIDER)
            raw_usage = parsed.get("usage")
            usage = raw_usage if isinstance(raw_usage, Mapping) else None
            answers = _TypeSafeAnswerNormalizer(usage).normalize(request, parsed)
            model = parsed.get("model")
            if not isinstance(model, str) or not model.strip():
                raise _TypeSafeAnswerNormalizer(usage).error(f"TypeSafe response has no `model` string naming the version that answered; received {JevValidation.describe(model)}.")
            return DecisionModelResponse(provider=self.provider, model=model, answers=answers, raw=parsed, usage=usage)
        except (ProviderResponseError, ProviderConfigurationError, ConfigurationError):
            raise
        except ProviderRequestError as exc:
            raise _TypeSafeFailures.transport_error(exc, operation="decision", config=resolved) from exc
        except Exception as exc:
            raise _TypeSafeFailures.unexpected(exc, operation="decision", usage=usage) from exc

    async def list_models(self, *, transport: HttpTransport, config: DecisionModelConfig | None = None) -> tuple[JevModelCard, ...]:
        # GETs the model IDs and aliases the account can send in the request `model` field.
        # @intent one-guarded-model-list-call
        # Same single-try failure mapping as run_decision, so both endpoints fail the same way.
        resolved: DecisionModelConfig | None = None
        try:
            resolved = self._config_for(config)
            response = await self._calls.models(resolved).send(transport)
            return _TypeSafeModelListNormalizer.normalize(self._parser.parse_json_response(response, provider=_PROVIDER))
        except (ProviderResponseError, ProviderConfigurationError, ConfigurationError):
            raise
        except ProviderRequestError as exc:
            raise _TypeSafeFailures.transport_error(exc, operation="model list", config=resolved) from exc
        except Exception as exc:
            raise _TypeSafeFailures.unexpected(exc, operation="model list", usage=None) from exc

    def _config_for(self, config: DecisionModelConfig | None) -> DecisionModelConfig:
        # Resolves the active config, raising when neither the call nor the adapter supplied one.
        # @intent per-call-config-wins
        # A per-call config overrides the adapter's, so one adapter can serve several model pins.
        resolved = config or self._decision_config
        if resolved is None:
            raise ProviderConfigurationError("TypeSafeProvider requires a DecisionModelConfig: pass config= to the call or decision_config= to the adapter.", provider=_PROVIDER)
        return resolved


__all__ = ["TypeSafeProvider"]
