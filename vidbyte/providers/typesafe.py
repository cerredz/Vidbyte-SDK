"""FILE: vidbyte/providers/typesafe.py

PURPOSE: Provider adapter for TypeSafe's System One endpoint: serializes a JevDecisionRequest, sends it, and normalizes Jev's answers into JevAnswer records.
ROLE IN CODEBASE: `ModelProviders.decision()` builds this adapter and `vidbyte/lib/runners/decision.py` calls `run_decision`; the jev_decide tool in `vidbyte/tools/classifier/` sits on top of that runner.
ARCHITECTURE NOTE: This module owns the wire shape in both directions; the request and answer records in vidbyte/lib/dataclasses/jev.py stay free of dict encoders, and HTTP goes through vidbyte.lib.http only.
COMMON MODIFICATION PATTERNS: When TypeSafe changes its API, update _TypeSafePayloadBuilder and _TypeSafeAnswerNormalizer together and extend the scripted-transport tests.
KNOWN EDGE CASES: A score answer may name its level as a label or as an index, and its probability keys may be labels or digit strings; both forms normalize to labels. A malformed answer raises ProviderResponseError carrying the billed usage in details["usage"].
RELATED DOCS: docs/design/jev-decide-tool.md and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_decide_tool.py and scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_MAX_RESPONSE_BYTES,
    JEV_NO_RETRIES,
    JEV_NOUL_FALSE,
    JEV_NOUL_TRUE,
    JEV_RETRY_STATUS_CODES,
    JEV_SYSTEMONE_PATH,
)
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevQuestion
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import DecisionModelResponse


class _TypeSafePayloadBuilder:
    """Builds the System One JSON body from a validated JevDecisionRequest."""

    @staticmethod
    def build(config: DecisionModelConfig, request: JevDecisionRequest) -> dict[str, Any]:
        # Returns {model, state, questions} with one criteria entry per named question.
        # @intent wire-shape-owned-by-provider
        # The records stay encoder-free; this is the only place the System One body is shaped,
        # so an API change is a one-file edit plus its scripted-transport tests.
        questions = {question.name: _TypeSafePayloadBuilder._question(question) for question in request.questions}
        return {"model": config.model, "state": request.state, "questions": questions}

    @staticmethod
    def _question(question: JevQuestion) -> dict[str, Any]:
        # Score criteria are an ordered level list; noul and choice criteria map option to description.
        if question.question_type is JevQuestionType.SCORE:
            criteria: Any = list(question.option_names())
        else:
            criteria = {option.name: option.description for option in question.options}
        return {"type": question.question_type.value, "instructions": question.instructions, "criteria": criteria}


class _TypeSafeAnswerNormalizer:
    """Turns System One answers into JevAnswer records, rejecting any contract drift."""

    def __init__(self, provider: str, usage: Mapping[str, Any] | None) -> None:
        # Keeps the usage so every normalization failure still reports the billed call.
        self._provider = provider
        self._usage = usage

    def normalize(self, request: JevDecisionRequest, parsed: Mapping[str, Any]) -> Mapping[str, JevAnswer]:
        # Returns one JevAnswer per requested question, keyed by question name.
        answers = parsed.get("answers")
        if not isinstance(answers, Mapping):
            raise self.error("TypeSafe response did not include an answers object.")
        normalized: dict[str, JevAnswer] = {}
        for question in request.questions:
            raw = answers.get(question.name)
            if not isinstance(raw, Mapping):
                raise self.error(f"TypeSafe response is missing an answer for question {question.name!r}.")
            normalized[question.name] = self._answer(question, raw)
        return MappingProxyType(normalized)

    def error(self, message: str) -> ProviderResponseError:
        # Builds a ProviderResponseError whose details keep the usage of the call that was billed.
        # @intent billed-calls-stay-billable-on-bad-answers
        # TypeSafe charges for a request even when its answer fails our normalization, so
        # the usage rides on the error for the tool to report; dropping it would under-bill.
        error = ProviderResponseError(message, provider=self._provider)
        if isinstance(self._usage, Mapping):
            error.details["usage"] = dict(self._usage)
        return error

    def _answer(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Dispatches one raw answer to the normalizer for its question type.
        try:
            if question.question_type is JevQuestionType.NOUL:
                return self._noul(question, raw)
            probabilities = self._distribution(question, raw.get("probabilities"))
            choice = self._chosen_label(question, raw.get(question.question_type.value))
            confidence = raw.get("confidence", probabilities.get(choice))
            return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities=probabilities, confidence=confidence)
        except ConfigurationError as exc:
            raise self.error(f"TypeSafe answer for {question.name!r} was malformed: {exc.message}") from exc

    def _noul(self, question: JevQuestion, raw: Mapping[str, Any]) -> JevAnswer:
        # Expands a single P(true) into a two-option distribution with its confidence.
        probability = raw.get("noul")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise self.error(f"TypeSafe noul answer for {question.name!r} was not a number.")
        p_true = float(probability)
        probabilities = {JEV_NOUL_TRUE: p_true, JEV_NOUL_FALSE: 1.0 - p_true}
        choice = JEV_NOUL_TRUE if p_true >= 0.5 else JEV_NOUL_FALSE
        try:
            return JevAnswer(question_name=question.name, question_type=question.question_type, choice=choice, probabilities=probabilities, confidence=max(p_true, 1.0 - p_true))
        except ConfigurationError as exc:
            raise self.error(f"TypeSafe noul answer for {question.name!r} was malformed: {exc.message}") from exc

    def _distribution(self, question: JevQuestion, raw: object) -> dict[str, float]:
        # Keeps probabilities for known options only, resolving index keys to labels.
        if not isinstance(raw, Mapping) or not raw:
            raise self.error(f"TypeSafe answer for {question.name!r} did not include probabilities.")
        distribution: dict[str, float] = {}
        for key, value in raw.items():
            label = self._label_for(question, key)
            if label is not None:
                distribution[label] = value
        if not distribution:
            raise self.error(f"TypeSafe probabilities for {question.name!r} named no known option.")
        return distribution

    def _chosen_label(self, question: JevQuestion, raw: object) -> str:
        # Resolves the chosen option, accepting a label or a level index; unknown values raise.
        label = self._label_for(question, raw)
        if label is None:
            raise self.error(f"TypeSafe chose an option outside the allowed set for {question.name!r}.")
        return label

    @staticmethod
    def _label_for(question: JevQuestion, value: object) -> str | None:
        # Maps a label, an int index, or a digit-string index onto an option name, else None.
        names = question.option_names()
        if isinstance(value, str) and value in names:
            return value
        index: int | None = None
        if isinstance(value, int) and not isinstance(value, bool):
            index = value
        elif isinstance(value, str) and value.isdigit():
            index = int(value)
        if index is not None and 0 <= index < len(names):
            return names[index]
        return None


class TypeSafeProvider:
    """Decision-only provider adapter for TypeSafe's Jev models."""

    provider = ModelProvider.TYPESAFE

    def __init__(self, *, decision_config: DecisionModelConfig | None = None, response_parser: HttpResponseParser | None = None, **_: Any) -> None:
        # Stores the decision config; other factory kwargs are accepted and ignored.
        self._decision_config = decision_config
        self._parser = response_parser or HttpResponseParser()

    async def run_decision(self, *, request: JevDecisionRequest, transport: HttpTransport, config: DecisionModelConfig | None = None) -> DecisionModelResponse:
        # POSTs one System One request and returns its normalized answers and raw usage.
        # @intent response-usage-survives-normalization
        # Usage is read before answers are normalized so a malformed answer still reports the
        # billed call; the timeout is passed explicitly so no Jev call can hang the agent loop.
        config = self._config_for(config)
        response = await transport.request(timeout_seconds=config.timeout_seconds, **self._request_arguments(config, request))
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        raw_usage = parsed.get("usage")
        usage = raw_usage if isinstance(raw_usage, Mapping) else None
        answers = _TypeSafeAnswerNormalizer(self.provider.value, usage).normalize(request, parsed)
        raw_model = parsed.get("model")
        model = raw_model if isinstance(raw_model, str) and raw_model.strip() else config.model
        return DecisionModelResponse(provider=self.provider, model=model, answers=answers, raw=parsed, usage=usage)

    def _config_for(self, config: DecisionModelConfig | None) -> DecisionModelConfig:
        # Resolves the active config, raising when neither the call nor the adapter supplied one.
        resolved = config or self._decision_config
        if resolved is None:
            raise ProviderConfigurationError("TypeSafeProvider requires a DecisionModelConfig.", provider=self.provider.value)
        return resolved

    def _request_arguments(self, config: DecisionModelConfig, request: JevDecisionRequest) -> dict[str, Any]:
        # Builds the transport call with a bounded body, the configured timeout, and optional retries.
        # @intent decisions-retry-only-when-asked
        # A decision has no side effects, so a retried POST cannot duplicate anything; the
        # per-request idempotency key only satisfies the transport's POST retry guard. The
        # default retry_count of 0 keeps the tool fail-open instead of waiting on 429/529.
        arguments: dict[str, Any] = {
            "method": "POST",
            "url": f"{config.resolved_endpoint()}{JEV_SYSTEMONE_PATH}",
            "headers": self._parser.bearer_headers(config.resolved_api_key()),
            "json_body": _TypeSafePayloadBuilder.build(config, request),
            "max_response_bytes": JEV_MAX_RESPONSE_BYTES,
        }
        if config.retry_count > JEV_NO_RETRIES:
            arguments.update(retry_count=config.retry_count, retry_status_codes=JEV_RETRY_STATUS_CODES, idempotency_key=uuid.uuid4().hex)
        return arguments


__all__ = ["TypeSafeProvider"]
