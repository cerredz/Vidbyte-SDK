"""FILE: vidbyte/providers/systemone.py

PURPOSE: The System One wire for every host that serves it: `SystemOneRequest` builds and encodes the `{model, state, questions}` body, `SystemOneAnswers` turns the `answers` map into JevAnswer records in the host's name, and `SystemOneProvider` sends direct decision calls to Perplexity, OpenRouter, Liquid AI, Baseten, meraGPT, Cloudflare, and Microsoft Foundry.
ROLE IN CODEBASE: `ModelProviders.decision()` builds `SystemOneProvider` for the seven direct System One hosts and `vidbyte/lib/runners/decision.py` calls `run_decision`; `vidbyte/providers/typesafe.py` reuses `SystemOneRequest`, `SystemOneAnswers`, and the TypeSafe row of `SystemOneProvider.HOSTS` and adds only TypeSafe's managed gateway, model list, and run close.
ARCHITECTURE NOTE: One adapter class serves every host; the differences live in one `SystemOneHost` row per provider (display name, path, auth scheme, and two wire quirks) defined in `vidbyte/lib/dataclasses/jev.py`. The records stay encoder-free: only `SystemOneRequest.encode` turns a wire record into JSON, and HTTP goes through `vidbyte.lib.http` via `DecisionHttpCall`. Imports only `vidbyte.lib` and `vidbyte.providers.decisions` (A006).
COMMON MODIFICATION PATTERNS: A new System One host is a `ModelProvider` member, registry rows, a path constant in `vidbyte/lib/constants/jev.py`, and one `HOSTS` row here; set `model_from_request=True` unless the vendor documents the `model` it echoes. When the System One API changes, update the wire records, `SystemOneRequest`, and `SystemOneAnswers` together and extend the scripted-transport tests.
KNOWN EDGE CASES: OpenRouter rejects a noul question without criteria, so its row sends `{"true": null, "false": null}`. Score answers key probabilities by level index strings and carry a weighted `score` between levels; both normalize onto level labels. Noul answers carry no confidence. A malformed answer raises ProviderResponseError carrying the billed usage. Hosts with an undocumented `model` echo report the requested model id, because the ledger prices `DecisionModelResponse.model`. No host but TypeSafe has a model list or managed runs, so `list_models` and `close_run` raise.
RELATED DOCS: vidbyte/providers/README.md ("Decision providers"), docs/spec/decision-model-providers/spec.md, https://docs.typesafe.ai/api.md, https://docs.perplexity.ai/api-reference/decisions-post, https://www.baseten.co/library/mercury-decide/, https://developers.cloudflare.com/workers-ai/models/clef/, https://docs.liquid.ai/lfm/models/d1, https://meragpt.com/docs.
TESTS: tests/features/decision_model_providers/test_decision_systemone_wire.py, tests/features/decision_model_providers/test_decision_failures.py, tests/features/decision_model_providers/test_decision_usage_metering.py, and tests/test_jev_agent.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, ClassVar

from vidbyte.lib.constants.jev import (
    BASETEN_DECISIONS_PATH,
    CLOUDFLARE_CLEF_PATH,
    FOUNDRY_SYSTEMONE_PATH,
    JEV_NO_RETRIES,
    JEV_NOUL_FALSE,
    JEV_NOUL_TRUE,
    JEV_NOUL_YES_THRESHOLD,
    JEV_SYSTEMONE_PATH,
    PERPLEXITY_DECISIONS_PATH,
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
    SystemOneHost,
    TypeSafeWireQuestion,
    TypeSafeWireRequest,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import (
    DecisionAuthScheme,
    DecisionModelMode,
    JevQuestionType,
    ModelProvider,
)
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.providers.decisions import DecisionFailures, DecisionHttpCall


class SystemOneRequest:
    """Builds the typed System One wire body from a validated JevDecisionRequest and encodes it as plain JSON."""

    @staticmethod
    def build(config: DecisionModelConfig, request: JevDecisionRequest, *, host: SystemOneHost) -> TypeSafeWireRequest:
        # Returns the {model, state, questions} body with one wire question per named question.
        # @intent wire-shape-owned-by-provider
        # The records stay encoder-free; this is the only place the System One body is shaped for every
        # System One host, so an API change is a one-file edit plus its scripted-transport tests.
        questions = {question.name: SystemOneRequest.question(question, host=host) for question in request.questions}
        return TypeSafeWireRequest(model=config.resolved_model(), state=request.state, questions=questions)

    @staticmethod
    def question(question: JevQuestion, *, host: SystemOneHost) -> TypeSafeWireQuestion:
        # Returns one wire question: its type, its instructions, and the criteria its type defines.
        return TypeSafeWireQuestion(type=question.question_type.value, instructions=question.instructions, criteria=SystemOneRequest.criteria(question, host=host))

    @staticmethod
    def criteria(question: JevQuestion, *, host: SystemOneHost) -> JevContent | None:
        # Score levels are an ordered array; Choice and Noul map option to description; an optionless Noul sends none,
        # except to a host that rejects a Noul without criteria, which receives both keys with null descriptions.
        if question.question_type is JevQuestionType.SCORE:
            return tuple(option.name if option.description is None else option.description for option in question.options)
        if not question.options and question.question_type is JevQuestionType.NOUL and host.noul_criteria_required:
            return MappingProxyType({JEV_NOUL_TRUE: None, JEV_NOUL_FALSE: None})
        if not question.options:
            return None
        return MappingProxyType({option.name: option.description for option in question.options})

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


class SystemOneAnswers:
    """Turns System One answers into JevAnswer records, rejecting any drift from the documented contract in the host's name."""

    def __init__(self, usage: Mapping[str, Any] | None, *, provider: ModelProvider, label: str) -> None:
        # Keeps the usage so every normalization failure still reports the billed call, plus who answered.
        self._usage = usage
        self._provider = provider
        self._label = label

    def normalize(self, request: JevDecisionRequest, parsed: Mapping[str, Any]) -> Mapping[str, JevAnswer]:
        # Returns exactly one JevAnswer per requested question, keyed by question name.
        # @intent every-question-gets-exactly-one-answer
        # A partial or extra answer map would let a caller act on a decision the host never made, so any
        # mismatch with the questions sent fails the whole call with the billed usage attached.
        answers = parsed.get("answers")
        if not isinstance(answers, Mapping):
            raise self.error(f"{self._label} response has no `answers` object; received {JevValidation.describe(answers)}.")
        names = [question.name for question in request.questions]
        missing = [name for name in names if name not in answers]
        unexpected = sorted(str(key) for key in answers if key not in names)
        if missing or unexpected:
            raise self.error(f"{self._label} answers do not match the questions sent: missing {missing}, unexpected {unexpected}.")
        return MappingProxyType({question.name: self._answer(question, answers[question.name]) for question in request.questions})

    def model(self, parsed: Mapping[str, Any], *, host: SystemOneHost, fallback: str) -> str:
        # Returns the model id the ledger prices: the documented echo, or the requested id when the echo is undocumented.
        # @intent the-priced-model-is-one-the-pricebook-knows
        # The ledger prices DecisionModelResponse.model, so a host whose echo is undocumented or caller-chosen
        # reports the requested id (the fallback); a documented echo stays required, as it always was for TypeSafe.
        if host.model_from_request:
            return fallback
        model = parsed.get("model")
        if not isinstance(model, str) or not model.strip():
            raise self.error(f"{self._label} response has no `model` string naming the version that answered; received {JevValidation.describe(model)}.")
        return model

    def error(self, message: str) -> ProviderResponseError:
        # Builds a ProviderResponseError whose details keep the usage of the call that was billed.
        # @intent billed-calls-stay-billable-on-bad-answers
        # Hosts charge for a request even when its answer fails our normalization, so the usage
        # rides on the error for the caller to report; dropping it would under-bill.
        error = ProviderResponseError(message, provider=self._provider.value)
        if isinstance(self._usage, Mapping):
            error.details["usage"] = dict(self._usage)
        return error

    def _answer(self, question: JevQuestion, raw: object) -> JevAnswer:
        # Checks the answer's type tag, then dispatches to the normalizer for its question type.
        if not isinstance(raw, Mapping):
            raise self.error(f"{self._label} answer for {question.name!r} is not an object; received {JevValidation.describe(raw)}.")
        if raw.get("type") != question.question_type.value:
            raise self.error(f"{self._label} answer for {question.name!r} has type {raw.get('type')!r}, but the question was {question.question_type.value!r}.")
        try:
            if question.question_type is JevQuestionType.NOUL:
                return self._noul(question, raw)
            if question.question_type is JevQuestionType.SCORE:
                return self._score(question, raw)
            return self._choice(question, raw)
        except ConfigurationError as exc:
            raise self.error(f"{self._label} answer for {question.name!r} was malformed: {exc.message}") from exc

    def _choice(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Reads `choice`, `probabilities` over every option, and `confidence`.
        probabilities = self._distribution(question, raw.get("probabilities"), question.option_names())
        choice = raw.get("choice")
        if choice not in probabilities:
            raise self.error(f"{self._label} chose {choice!r} for {question.name!r}, outside its options {list(question.option_names())}.")
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
            raise self.error(f"{self._label} answer for {question.name!r} has no `{label}` object; received {JevValidation.describe(raw)}.")
        missing = [key for key in keys if key not in raw]
        unexpected = sorted(str(key) for key in raw if key not in keys)
        if missing or unexpected:
            raise self.error(f"{self._label} `{label}` for {question.name!r} do not match its options: missing {missing}, unexpected {unexpected}.")
        return {key: raw[key] for key in keys}


class SystemOneProvider:
    """Decision adapter for the direct System One hosts; the config's provider picks the host row it serves."""

    # One row per System One host (spec section 9.1). Paths come from vidbyte/lib/constants/jev.py; only
    # TypeSafe and Perplexity document the `model` they echo, so every other row prices the requested id.
    HOSTS: ClassVar[Mapping[ModelProvider, SystemOneHost]] = MappingProxyType({
        ModelProvider.TYPESAFE: SystemOneHost(display_name="TypeSafe", path=JEV_SYSTEMONE_PATH),
        ModelProvider.PERPLEXITY: SystemOneHost(display_name="Perplexity", path=PERPLEXITY_DECISIONS_PATH),
        ModelProvider.OPENROUTER: SystemOneHost(display_name="OpenRouter", path=JEV_SYSTEMONE_PATH, noul_criteria_required=True, model_from_request=True),
        ModelProvider.LIQUID: SystemOneHost(display_name="Liquid AI", path=JEV_SYSTEMONE_PATH, model_from_request=True),
        ModelProvider.BASETEN: SystemOneHost(display_name="Baseten", path=BASETEN_DECISIONS_PATH, auth_scheme=DecisionAuthScheme.API_KEY, model_from_request=True),
        ModelProvider.MERAGPT: SystemOneHost(display_name="meraGPT", path=JEV_SYSTEMONE_PATH, model_from_request=True),
        ModelProvider.CLOUDFLARE: SystemOneHost(display_name="Cloudflare", path=CLOUDFLARE_CLEF_PATH, model_from_request=True),
        ModelProvider.FOUNDRY: SystemOneHost(display_name="Microsoft Foundry", path=FOUNDRY_SYSTEMONE_PATH, model_from_request=True),
    })

    provider: ModelProvider

    def __init__(self, *, decision_config: DecisionModelConfig | None = None, response_parser: HttpResponseParser | None = None, **_: Any) -> None:
        # Stores the config and parser and binds this adapter to the host row of the config's provider.
        # @intent the-config-names-the-host
        # The adapter's identity (provider, path, auth scheme, wire quirks) comes from its config, so a missing
        # config, a provider without a System One row, or a managed config fails here, not as a KeyError on the first call.
        if decision_config is None:
            raise ProviderConfigurationError("SystemOneProvider requires a DecisionModelConfig: pass decision_config= to the adapter.", provider="systemone")
        provider = decision_config.normalized_provider()
        host = self.HOSTS.get(provider)
        if host is None:
            raise ProviderConfigurationError(f"SystemOneProvider has no System One host row for provider '{provider.value}'; build its adapter with ModelProviders.decision().", provider=provider.value)
        if decision_config.mode is DecisionModelMode.VIDBYTE_MANAGED:
            raise ProviderConfigurationError("SystemOneProvider sends direct calls only; managed TypeSafe decisions go through TypeSafeProvider.", provider=provider.value)
        self.provider = provider
        self._host = host
        self._decision_config = decision_config
        self._parser = response_parser or HttpResponseParser()

    async def run_decision(self, *, request: JevDecisionRequest, transport: HttpTransport, config: DecisionModelConfig | None = None) -> DecisionModelResponse:
        # POSTs one System One request to this host and returns its normalized answers, priced model id, and raw usage.
        # @intent one-guarded-decision-call
        # Every failure funnels through one try: a missing or foreign config stays a configuration error, a
        # normalization failure keeps its billed usage, transport and HTTP failures are rewritten per documented
        # status in this host's name, and anything unanticipated becomes a ProviderResponseError instead of a
        # bare exception. Cancellation is a BaseException and propagates untouched.
        usage: Mapping[str, Any] | None = None
        resolved: DecisionModelConfig | None = None
        try:
            # Use the per-call config when one is given (it must be for this host), else the adapter's own.
            resolved = self._config_for(config)
            # Send one POST to this host's path; the transport retries it with the same idempotency key.
            response = await self._call(resolved, request).send(transport)
            parsed = self._parser.parse_json_response(response, provider=self.provider.value)
            # Read the usage first, so a malformed answer below still reports the billed call.
            raw_usage = parsed.get("usage")
            usage = raw_usage if isinstance(raw_usage, Mapping) else None
            normalizer = SystemOneAnswers(usage, provider=self.provider, label=self._host.display_name)
            # One answer per question, then the model id the ledger prices: the echo or the requested id.
            answers = normalizer.normalize(request, parsed)
            model = normalizer.model(parsed, host=self._host, fallback=resolved.resolved_model())
            return DecisionModelResponse(provider=self.provider, model=model, answers=answers, raw=parsed, usage=usage)
        except ProviderResponseError:
            raise
        except (ProviderConfigurationError, ConfigurationError):
            raise
        except ProviderRequestError as exc:
            raise DecisionFailures.transport_error(exc, operation="decision", provider=self.provider, label=self._host.display_name, config=resolved) from exc
        except Exception as exc:
            raise DecisionFailures.unexpected(exc, operation="decision", provider=self.provider, usage=usage) from exc

    async def list_models(self, *, transport: HttpTransport, config: DecisionModelConfig | None = None) -> tuple[JevModelCard, ...]:
        # Refuses without a network call: the direct System One hosts publish no model-list endpoint.
        # @intent missing-capabilities-are-refused-not-faked
        # An empty tuple would read as "this account has no models", so the caller is told to pin `model` instead.
        raise ProviderConfigurationError(f"{self._host.display_name} publishes no model-list endpoint; pass DecisionModelConfig.model explicitly.", provider=self.provider.value)

    async def close_run(self, *, run_id: str, transport: HttpTransport, config: DecisionModelConfig | None = None) -> None:
        # Refuses without a network call: only the managed TypeSafe gateway has runs to close.
        # @intent missing-capabilities-are-refused-not-faked
        # Silently succeeding would hide a caller that believes it is settling a managed run.
        raise ProviderConfigurationError(f"{self._host.display_name} decisions have no managed runs to close.", provider=self.provider.value)

    def _config_for(self, config: DecisionModelConfig | None) -> DecisionModelConfig:
        # Resolves the active config: the per-call one when given, else the adapter's, refusing another provider's.
        # @intent per-call-config-stays-on-this-host
        # The host row, URL, and auth scheme were bound at construction; another provider's config would post its
        # key to this host, so it is refused before any URL or header is built.
        resolved = config or self._decision_config
        other = resolved.normalized_provider()
        if other is not self.provider:
            raise ProviderConfigurationError(f"{self._host.display_name} adapter received a config for provider '{other.value}'.", provider=self.provider.value)
        return resolved

    def _call(self, config: DecisionModelConfig, request: JevDecisionRequest) -> DecisionHttpCall:
        # Returns the POST to this host's path with the key in the host's authorization scheme and the configured retries.
        # @intent decisions-retry-with-an-idempotency-key
        # A direct decision has no side effects, so the key only satisfies the transport's POST retry guard;
        # it is never sent as a header (only the managed TypeSafe gateway replays billed answers by key).
        idempotency_key = uuid.uuid4().hex if config.retry_count > JEV_NO_RETRIES else None
        body = SystemOneRequest.encode(SystemOneRequest.build(config, request, host=self._host))
        key = config.resolved_api_key()
        headers = self._parser.bearer_headers(key)
        headers["authorization"] = f"{self._host.auth_scheme.value} {key}"
        return DecisionHttpCall(method="POST", url=f"{config.resolved_endpoint()}{self._host.path}", headers=headers, timeout_seconds=config.timeout_seconds, json_body=body, retry_count=config.retry_count, idempotency_key=idempotency_key)


__all__ = ["SystemOneAnswers", "SystemOneProvider", "SystemOneRequest"]
