"""FILE: tests/features/decision_model_providers/decision_fixtures.py

PURPOSE: Shared offline fixtures for the decision-model-providers feature pack: a scripted transport, the spec's customer request, System One and OpenAI Decisions response builders, and a keyed runner factory.
ROLE IN CODEBASE: Imported by every test module in tests/features/decision_model_providers/; it never imports the new provider modules at import time so a missing implementation fails one test, not the whole collection.
ARCHITECTURE NOTE: Only HttpTransport.request is replaced (ScriptedTransport); DecisionModelConfig, ProviderModelRegistry, JevAnswer validation, HttpResponseParser, pricing, and the usage ledger stay real. New ModelProvider members are resolved by name at call time with provider_member().
COMMON MODIFICATION PATTERNS: Add a builder here when a new wire shape or host row joins the spec; keep expected URLs, env vars, and default models in HOST_ROWS so one table drives the contract and wire tests.
KNOWN EDGE CASES: Cloudflare and Foundry have no default endpoint, so decision_config() injects a tenant endpoint for them unless the test overrides it; scripted responses that omit `model` use OMIT_MODEL rather than None.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 4, 8.5, 9.1, and 13; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevOption, JevQuestion
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners.decision import DecisionModelRunner

KEY = "decision-test-key"
STATE = "Customer: my order arrived broken and support ignored two emails."
USAGE = {"input_tokens": 300, "output_tokens": 2}
OMIT_MODEL = object()

CLOUDFLARE_TENANT = "https://api.cloudflare.com/client/v4/accounts/abc/ai"
FOUNDRY_TENANT = "https://my-resource.services.ai.azure.com"


@dataclass(frozen=True, slots=True)
class HostRow:
    """What spec section 9.1 promises for one provider: identity, endpoint, credential, default model, and host flags."""

    member: str
    display_name: str
    base_url: str
    path: str
    auth_scheme: str
    env_var: str
    default_model: str
    noul_criteria_required: bool
    model_from_request: bool
    adapter: str


HOST_ROWS: dict[str, HostRow] = {
    "TYPESAFE": HostRow("TYPESAFE", "TypeSafe", "https://api.typesafe.ai/v1", "/systemone", "Bearer", "TYPESAFE_API_KEY", "jev-latest", False, False, "TypeSafeProvider"),
    "PERPLEXITY": HostRow("PERPLEXITY", "Perplexity", "https://api.perplexity.ai/v1", "/decisions", "Bearer", "PERPLEXITY_API_KEY", "pplx-decider-v1.1-27b", False, False, "SystemOneProvider"),
    "OPENROUTER": HostRow("OPENROUTER", "OpenRouter", "https://openrouter.ai/api/v1", "/systemone", "Bearer", "OPENROUTER_API_KEY", "typesafe/jev-1.13", True, True, "SystemOneProvider"),
    "LIQUID": HostRow("LIQUID", "Liquid AI", "https://api.liquid.ai/decisions/v1", "/systemone", "Bearer", "LIQUID_API_KEY", "d1", False, True, "SystemOneProvider"),
    "BASETEN": HostRow("BASETEN", "Baseten", "https://inference.baseten.co/v1", "/decisions", "Api-Key", "BASETEN_API_KEY", "inception/mercury-decide", False, True, "SystemOneProvider"),
    "MERAGPT": HostRow("MERAGPT", "meraGPT", "https://meragpt.com/v1", "/systemone", "Bearer", "MERAGPT_API_KEY", "sd-1", False, True, "SystemOneProvider"),
    "CLOUDFLARE": HostRow("CLOUDFLARE", "Cloudflare", CLOUDFLARE_TENANT, "/run/@cf/cloudflare/clef", "Bearer", "CLOUDFLARE_API_TOKEN", "clef", False, True, "SystemOneProvider"),
    "FOUNDRY": HostRow("FOUNDRY", "Microsoft Foundry", FOUNDRY_TENANT, "/providers/microsoft/v1/systemone", "Bearer", "FOUNDRY_API_KEY", "microsoft-decision-1", False, True, "SystemOneProvider"),
    "OPENAI": HostRow("OPENAI", "OpenAI", "https://api.openai.com/v1", "/decisions", "Bearer", "OPENAI_API_KEY", "gpt-6-luna", False, True, "OpenAIDecisionsProvider"),
}
SYSTEM_ONE_DIRECT = ("PERPLEXITY", "OPENROUTER", "LIQUID", "BASETEN", "MERAGPT", "CLOUDFLARE", "FOUNDRY")
NEW_MEMBERS = ("PERPLEXITY", "CLOUDFLARE", "FOUNDRY", "LIQUID", "BASETEN", "MERAGPT")
TENANT_ENDPOINTS = {"CLOUDFLARE": CLOUDFLARE_TENANT, "FOUNDRY": FOUNDRY_TENANT}


class ScriptedTransport:
    """Records every request and replays scripted HTTP responses or raises scripted exceptions."""

    def __init__(self, *responses: HttpResponse | BaseException) -> None:
        # Retains deterministic provider responses and all outbound arguments.
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Records the request before returning the next response or raising a scripted exception.
        self.requests.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def provider_member(name: str) -> ModelProvider:
    # Resolves a ModelProvider member by its spec name at call time (AttributeError until the member exists).
    return getattr(ModelProvider, name)


def expected_url(name: str) -> str:
    # Returns the full decision URL spec section 9.1 promises for one host.
    row = HOST_ROWS[name]
    return f"{row.base_url}{row.path}"


def response(body: dict[str, Any], status_code: int = 200) -> HttpResponse:
    # Encodes one JSON HTTP response.
    return HttpResponse(status_code=status_code, body=json.dumps(body), headers={})


def raw_response(body: str, status_code: int) -> HttpResponse:
    # Encodes one non-JSON HTTP response (an HTML gateway page, for example).
    return HttpResponse(status_code=status_code, body=body, headers={})


def noul_question(name: str = "refund", instructions: Any = "Should this customer receive a refund?", options: tuple[JevOption, ...] = ()) -> JevQuestion:
    # Builds the yes/no question of the spec's section 4 snippet.
    return JevQuestion(name=name, question_type=JevQuestionType.NOUL, instructions=instructions, options=options)


def choice_question(name: str = "team", options: tuple[JevOption, ...] = (JevOption("billing"), JevOption("logistics"), JevOption("support"))) -> JevQuestion:
    # Builds the three-way choice question of the spec's section 4 snippet.
    return JevQuestion(name=name, question_type=JevQuestionType.CHOICE, instructions="Which team owns the next step?", options=options)


def score_question(name: str = "frustration") -> JevQuestion:
    # Builds a three-level score question, lowest level first.
    return JevQuestion(name=name, question_type=JevQuestionType.SCORE, instructions="How frustrated is the customer?", options=(JevOption("calm"), JevOption("frustrated"), JevOption("angry")))


def customer_request(*questions: JevQuestion, state: Any = STATE) -> JevDecisionRequest:
    # Builds the section 4 request (refund noul + team choice) unless the test supplies its own questions.
    return JevDecisionRequest(state=state, questions=questions or (noul_question(), choice_question()))


def systemone_noul(p_yes: float) -> dict[str, Any]:
    # One System One noul answer.
    return {"type": "noul", "noul": p_yes}


def systemone_choice(choice: str = "billing", probabilities: dict[str, float] | None = None, confidence: float = 0.7) -> dict[str, Any]:
    # One System One choice answer over the section 4 team options.
    return {"type": "choice", "choice": choice, "probabilities": probabilities or {"billing": 0.7, "logistics": 0.2, "support": 0.1}, "confidence": confidence}


def systemone_score() -> dict[str, Any]:
    # One documented System One score answer: weighted score, index legend, index-keyed probabilities.
    return {"type": "score", "score": 1.05, "legend": {"0": "calm", "1": "frustrated", "2": "angry"}, "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}, "confidence": 0.92}


def systemone_body(answers: dict[str, Any], *, model: Any = "pplx-decider-v1.1-27b", usage: dict[str, Any] | None | object = USAGE) -> dict[str, Any]:
    # Builds a System One response body; OMIT_MODEL / OMIT_MODEL-style sentinels drop the optional keys.
    body: dict[str, Any] = {"answers": answers}
    if model is not OMIT_MODEL:
        body["model"] = model
    if usage is not OMIT_MODEL:
        body["usage"] = usage
    return body


def openai_predicate(name: str, probability: float) -> dict[str, Any]:
    # One OpenAI Decisions predicate answer.
    return {"type": "predicate", "name": name, "probability": probability}


def openai_choice(name: str = "team", choice: str = "billing", probabilities: list[dict[str, Any]] | None = None, confidence: float = 0.7) -> dict[str, Any]:
    # One OpenAI Decisions choice answer with its array-shaped distribution.
    distribution = probabilities or [{"value": "billing", "probability": 0.7}, {"value": "logistics", "probability": 0.2}, {"value": "support", "probability": 0.1}]
    return {"type": "choice", "name": name, "choice": choice, "probabilities": distribution, "confidence": confidence}


def openai_score(name: str = "frustration", probabilities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    # One OpenAI Decisions score answer with value/label/probability entries.
    distribution = probabilities or [{"value": 0, "label": "calm", "probability": 0.0}, {"value": 1, "label": "frustrated", "probability": 0.95}, {"value": 2, "label": "angry", "probability": 0.05}]
    return {"type": "score", "name": name, "score": 1.05, "probabilities": distribution, "confidence": 0.92}


def openai_body(answers: list[dict[str, Any]], *, model: Any = "gpt-6-luna", usage: dict[str, Any] | None | object = USAGE) -> dict[str, Any]:
    # Builds an OpenAI Decisions response body: an answers array plus optional model echo and usage.
    body: dict[str, Any] = {"answers": answers}
    if model is not OMIT_MODEL:
        body["model"] = model
    if usage is not OMIT_MODEL:
        body["usage"] = usage
    return body


def decision_config(member: str, **overrides: Any) -> DecisionModelConfig:
    # Builds a keyed direct-mode config for one provider, adding the tenant endpoint the host needs.
    values: dict[str, Any] = {"provider": provider_member(member), "api_key": KEY}
    if member in TENANT_ENDPOINTS:
        values["endpoint"] = TENANT_ENDPOINTS[member]
    values.update(overrides)
    return DecisionModelConfig(**values)


def scripted_runner(member: str, *responses: HttpResponse | BaseException, **overrides: Any) -> tuple[DecisionModelRunner, ScriptedTransport]:
    # Builds a keyed decision runner for one provider over a scripted transport.
    transport = ScriptedTransport(*responses)
    return DecisionModelRunner(decision_config(member, **overrides), transport=transport), transport


def sorted_json(value: Any) -> str:
    # Canonical JSON text so two wire bodies can be compared byte for byte.
    return json.dumps(value, sort_keys=True)


__all__ = [
    "CLOUDFLARE_TENANT",
    "FOUNDRY_TENANT",
    "HOST_ROWS",
    "HostRow",
    "KEY",
    "NEW_MEMBERS",
    "OMIT_MODEL",
    "STATE",
    "SYSTEM_ONE_DIRECT",
    "ScriptedTransport",
    "TENANT_ENDPOINTS",
    "USAGE",
    "choice_question",
    "customer_request",
    "decision_config",
    "expected_url",
    "noul_question",
    "openai_body",
    "openai_choice",
    "openai_predicate",
    "openai_score",
    "provider_member",
    "raw_response",
    "response",
    "score_question",
    "scripted_runner",
    "sorted_json",
    "systemone_body",
    "systemone_choice",
    "systemone_noul",
    "systemone_score",
]
