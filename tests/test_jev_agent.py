"""FILE: tests/test_jev_agent.py

PURPOSE: Verifies the TypeSafe decision substrate, Jev profile catalog, temporary main-agent settings, and probability-ranked routing without network access.
ROLE IN CODEBASE: Covers the JEV decision contract and `docs/design/jev-agent-profile-routing.md`, including profile validation, runtime wiring, provider normalization, public exports, and selected-settings restoration.
ARCHITECTURE NOTE: Scripted transports and runners replace only external model boundaries; production constructors and runtime factories remain under test.
COMMON MODIFICATION PATTERNS: Add cases here whenever profiles, ranking, temporary settings, runtime policy, or response observability change.
KNOWN EDGE CASES: TYPESAFE_API_KEY is cleared where credential timing is tested, and no test may send a live provider request.
RELATED DOCS: `docs/design/jev-agent-profile-routing.md`, `tests/features/jev-agent-profile-routing/FEATURE.md`, and `skills/jev-agent/SKILL.md`.
TESTS: python -m pytest tests/test_jev_agent.py and python scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import unittest
from dataclasses import fields
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import OfflineTestAgent, bind_test_runner
from vidbyte import Jev as RootJev
from vidbyte import JevSpecialist as RootJevProfile
from vidbyte import JevAgentSettings as RootJevAgentSettings
from vidbyte import JevRuntime as RootJevRuntime
from vidbyte import VidbyteSDK, tool
from vidbyte.agents import BaseAgent
from vidbyte.agents.jev import Jev, JevAgentSettings, JevRuntime, JevRuntimeSettings
from vidbyte.agents.jev.specialists import JevSpecialist as JevProfile
from vidbyte.agents.jev.prompts import JevPrompt, JevPrompts
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_AGENT_MAX_COUNT,
    JEV_AGENT_MAX_DESCRIPTION_CHARS,
    JEV_DEFAULT_RETRY_COUNT,
    JEV_DEFAULT_TIMEOUT_SECONDS,
    JEV_MAX_CHOICE_OPTIONS,
    JEV_MAX_SCORE_LEVELS,
)
from vidbyte.lib.dataclasses.jev import (
    JevAgentProbability,
    JevAgentSelection,
    JevAnswer,
    JevDecisionRequest,
    JevOption,
    JevQuestion,
)
from vidbyte.lib.enums import AgentRuntimeType, JevQuestionType, ModelProvider
from vidbyte.lib.errors import (
    AgentExecutionError,
    ConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.registries.runtimes import RuntimeRegistry
from vidbyte.lib.runners import DecisionModelRunner, TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse

API_KEY = "typesafe-test-key"


class ScriptedTransport:
    """Records one request and returns scripted HTTP responses."""

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


class ScriptedRunner:
    """Minimal synchronous generative runner used by agent-loop tests."""

    def __init__(self, *responses: object) -> None:
        # Retains model responses and records invocation options.
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Returns the next response exactly as a production runner would.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class RawResponse:
    """OpenAI-shaped raw response wrapper for scripted tool calls."""

    def __init__(self, raw: dict[str, Any]) -> None:
        # Exposes the two response attributes consumed by BaseAgent.
        self.text = ""
        self.raw = raw


def _profile(title: str = "general", description: str = "Handles general requests.", runner: object | None = None, tools: tuple[object, ...] = ()) -> JevProfile:
    # Builds a decision-only profile; generation always uses JevAgentSettings.
    return JevProfile(title=title, description=description, metadata={"team": title.lower()})


def _settings(agents: tuple[JevProfile, ...] | list[JevProfile] | None = None) -> JevAgentSettings:
    # Provides one linear generation configuration while keeping optional routing metadata explicit.
    return JevAgentSettings(name="general", system_prompt="Handle general requests.", provider="openai", model_name="gpt-4.1-mini", agents=() if agents is None else agents)


def _question() -> JevQuestion:
    # Builds the three-way choice question shared by provider tests.
    return JevQuestion(
        name="decision",
        question_type=JevQuestionType.CHOICE,
        instructions="Choose.",
        options=(JevOption("a"), JevOption("b"), JevOption("c")),
    )


def _score_question() -> JevQuestion:
    # Builds a three-level score question whose last level carries a structured description.
    return JevQuestion(
        name="frustration",
        question_type=JevQuestionType.SCORE,
        instructions="How frustrated is the customer?",
        options=(JevOption("calm"), JevOption("frustrated"), JevOption("angry", description={"signals": ["caps", "threats"]})),
    )


def _score_answer() -> dict[str, Any]:
    # Builds the documented score answer: weighted score, index legend, and index-keyed probabilities.
    return {"type": "score", "score": 1.05, "legend": {"0": "calm", "1": "frustrated", "2": "angry"}, "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}, "confidence": 0.92}


def _response(body: dict[str, Any], status_code: int = 200) -> HttpResponse:
    # Encodes one fake HTTP response.
    return HttpResponse(status_code=status_code, body=json.dumps(body), headers={})


def _choice_body(**answer_overrides: Any) -> dict[str, Any]:
    # Builds a documented Choice response body, letting one test corrupt a single answer field.
    answer = {"type": "choice", "choice": "b", "probabilities": {"a": 0.1, "b": 0.7, "c": 0.2}, "confidence": 0.7}
    answer.update(answer_overrides)
    return {"model": "jev-1.13.0", "answers": {"decision": answer}, "usage": {"input_tokens": 12, "output_tokens": 1}}


def _runner(*responses: HttpResponse | BaseException, **config: Any) -> tuple[DecisionModelRunner, ScriptedTransport]:
    # Builds a keyed decision runner over a scripted transport.
    transport = ScriptedTransport(*responses)
    return DecisionModelRunner(DecisionModelConfig(api_key=API_KEY, **config), transport=transport), transport


def _specialist_response(choice: str, probabilities: dict[str, float]) -> DecisionModelResponse:
    # Builds one normalized Choice response for the agent-profile selection question.
    answer = JevAnswer(question_name="agent_profile", question_type=JevQuestionType.CHOICE, choice=choice, probabilities=probabilities, confidence=max(probabilities.values()))
    return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-latest", answers={"agent_profile": answer}, raw={}, usage={"input_tokens": 12, "output_tokens": 3})


def _specialist_template(name: str = "research", runner: object | None = None, tools: tuple[object, ...] = ()) -> BaseAgent:
    # Creates one valid specialist template and optionally binds an offline runner retained across forks.
    agent = OfflineTestAgent(name=name, system_prompt=f"Handle {name} tasks.", provider="openai", model_name="gpt-4.1-mini", tools=tools)
    return bind_test_runner(agent, runner) if runner is not None else agent


class DecisionFoundationTests(unittest.IsolatedAsyncioTestCase):
    """Pins credential timing, record validation, provider output, and pricing."""

    def test_config_constructs_without_api_key_but_runner_does_not(self) -> None:
        # [Hidden Assumption] shape validation is credential-free while execution setup resolves the key.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            config = DecisionModelConfig()
            self.assertEqual(config.normalized_provider(), ModelProvider.TYPESAFE)
            with self.assertRaisesRegex(ConfigurationError, "TYPESAFE_API_KEY"):
                DecisionModelRunner(config)

    def test_request_rejects_blank_state_and_duplicate_question_names(self) -> None:
        # [Edge Case] invalid request identity fails before any provider call.
        question = _question()
        with self.assertRaises(ConfigurationError):
            JevDecisionRequest(state=" ", questions=(question,))
        with self.assertRaises(ConfigurationError):
            JevDecisionRequest(state="state", questions=(question, question))

    async def test_provider_preserves_choice_probabilities(self) -> None:
        # [Silent Failure] each option probability remains attached to the requested question.
        runner, transport = _runner(_response(_choice_body()))
        result = await runner.arun(JevDecisionRequest(state="state", questions=(_question(),)))
        self.assertEqual(result.answer("decision").choice, "b")
        self.assertEqual(dict(result.answer("decision").probabilities), {"a": 0.1, "b": 0.7, "c": 0.2})
        self.assertEqual(result.answer("decision").confidence, 0.7)
        self.assertEqual(result.model, "jev-1.13.0")
        self.assertEqual(transport.requests[0]["json_body"]["state"], "state")
        self.assertEqual(transport.requests[0]["json_body"]["questions"]["decision"]["criteria"], {"a": None, "b": None, "c": None})

    async def test_provider_rejects_missing_answer(self) -> None:
        # [Hidden Failure] malformed provider output cannot become an empty or partial success.
        transport = ScriptedTransport(_response({"answers": {}, "usage": {"input_tokens": 4, "output_tokens": 1}}))
        runner = DecisionModelRunner(DecisionModelConfig(api_key=API_KEY), transport=transport)
        with self.assertRaises(ProviderResponseError):
            await runner.arun(JevDecisionRequest(state="state", questions=(_question(),)))

    def test_usage_and_pricing_keep_input_and_output_roles(self) -> None:
        # [Silent Failure] input is billed at the Jev rate while output remains free.
        usage = JevUsage.from_usage_payload({"input_tokens": 1_000_000, "output_tokens": 500_000})
        pricing = ModelPricingRegistry.default().resolve(ModelProvider.TYPESAFE, "jev-latest")
        self.assertIsNotNone(usage)
        self.assertEqual((usage.input_tokens, usage.output_tokens), (1_000_000, 500_000))
        self.assertAlmostEqual(usage.cost_usd(pricing), 0.042)

    def test_versioned_and_alias_models_are_priced(self) -> None:
        # [Silent Failure] responses name the versioned model, which must not fall out of the price table.
        registry = ModelPricingRegistry.default()
        for model in ("jev-1.13.0", "jev-latest", "jev-preview"):
            with self.subTest(model=model):
                pricing = registry.resolve(ModelProvider.TYPESAFE, model)
                self.assertIsNotNone(pricing)
                self.assertEqual((pricing.input_per_million, pricing.output_per_million), (0.042, 0.0))

    def test_cache_looking_usage_fields_do_not_discount_jev_input(self) -> None:
        # [Hidden Assumption] TypeSafe publishes no cache tier, so every input token bills at the full rate.
        usage = JevUsage.from_usage_payload({"input_tokens": 1_000_000, "output_tokens": 0, "cached_input_tokens": 900_000, "input_tokens_details": {"cached_tokens": 900_000}})
        pricing = ModelPricingRegistry.default().resolve(ModelProvider.TYPESAFE, "jev-1.13.0")
        self.assertIsNone(usage.cached_input_tokens)
        self.assertIsNone(usage.cache_hit_rate)
        self.assertAlmostEqual(usage.cost_usd(pricing), 0.042)

    def test_config_defaults_use_a_60_second_timeout_and_sdk_retries(self) -> None:
        # [Hidden Assumption] review asked for 60 seconds; retries follow the TypeSafe SDK's default of two.
        config = DecisionModelConfig()
        self.assertEqual((config.timeout_seconds, config.retry_count), (60.0, 2))
        self.assertEqual((JEV_DEFAULT_TIMEOUT_SECONDS, JEV_DEFAULT_RETRY_COUNT), (60.0, 2))


class DecisionRecordContractTests(unittest.TestCase):
    """Pins record validation to https://docs.typesafe.ai/api.md, with errors that name the failure."""

    def test_structured_state_instructions_and_criteria_are_accepted_and_frozen(self) -> None:
        # [Edge Case] state, instructions, and criteria accept JSON objects and arrays, frozen against later mutation.
        state = {"ticket": {"body": "Payouts failing", "tags": ["billing"]}}
        instructions = {"potential_duplicate": {"name": "John"}, "question": "Same person as `potential_duplicate`?"}
        question = JevQuestion(name="dup", question_type=JevQuestionType.CHOICE, instructions=instructions, options=(JevOption("yes", {"means": "same"}), JevOption("no")))
        request = JevDecisionRequest(state=state, questions=(question,))
        state["ticket"]["tags"].append("mutated")
        self.assertEqual(request.state["ticket"]["tags"], ("billing",))
        with self.assertRaises(TypeError):
            request.state["new"] = 1  # type: ignore[index]

    def test_noul_criteria_are_optional_and_limited_to_true_false(self) -> None:
        # [Edge Case] the API documents noul criteria as optional true/false descriptions.
        JevQuestion(name="urgent", question_type=JevQuestionType.NOUL, instructions="Urgent?")
        JevQuestion(name="urgent", question_type=JevQuestionType.NOUL, instructions="Urgent?", options=(JevOption("true", "time-sensitive"),))
        with self.assertRaisesRegex(ConfigurationError, "unknown keys"):
            JevQuestion(name="urgent", question_type=JevQuestionType.NOUL, instructions="Urgent?", options=(JevOption("maybe"),))

    def test_documented_option_limits(self) -> None:
        # [Edge Case] Choice accepts up to 255 options and Score between 2 and 10 levels.
        choice_options = tuple(JevOption(f"o{index}") for index in range(JEV_MAX_CHOICE_OPTIONS))
        JevQuestion(name="big", question_type=JevQuestionType.CHOICE, instructions="Pick.", options=choice_options)
        with self.assertRaisesRegex(ConfigurationError, "between 2 and 255 options"):
            JevQuestion(name="big", question_type=JevQuestionType.CHOICE, instructions="Pick.", options=(*choice_options, JevOption("extra")))
        levels = tuple(JevOption(f"l{index}") for index in range(JEV_MAX_SCORE_LEVELS + 1))
        with self.assertRaisesRegex(ConfigurationError, "between 2 and 10 levels"):
            JevQuestion(name="scale", question_type=JevQuestionType.SCORE, instructions="Rate.", options=levels)

    def test_many_questions_fit_in_one_request(self) -> None:
        # [Edge Case] speculative fan-out sends many questions per call, so the local cap stays generous.
        questions = tuple(JevQuestion(name=f"q{index}", question_type=JevQuestionType.NOUL, instructions="Relevant?") for index in range(500))
        self.assertEqual(len(JevDecisionRequest(state="state", questions=questions).questions), 500)

    def test_errors_name_field_expectation_and_received_value(self) -> None:
        # [Hidden Failure] a caller can repair the input from the message alone.
        with self.assertRaises(ConfigurationError) as caught:
            JevQuestion(name="q", question_type="choice", instructions="Pick.", options=(JevOption("a"), JevOption("b")))  # type: ignore[arg-type]
        self.assertIn("question_type of 'q'", caught.exception.message)
        self.assertIn("received str 'choice'", caught.exception.message)
        self.assertIn("JevQuestionType(value)", caught.exception.message)
        self.assertEqual(caught.exception.details["field"], "question_type of 'q'")
        with self.assertRaisesRegex(ConfigurationError, r"duplicates \['a'\]"):
            JevQuestion(name="q", question_type=JevQuestionType.CHOICE, instructions="Pick.", options=(JevOption("a"), JevOption("a")))
        with self.assertRaisesRegex(ConfigurationError, "finite JSON number"):
            JevDecisionRequest(state={"x": float("nan")}, questions=(_question(),))

    def test_noul_answers_carry_no_confidence(self) -> None:
        # [Silent Failure] TypeSafe documents no confidence for noul, so none may be invented.
        with self.assertRaisesRegex(ConfigurationError, "neither for noul"):
            JevAnswer(question_name="n", question_type=JevQuestionType.NOUL, choice="true", probabilities={"true": 0.9, "false": 0.1}, confidence=0.9, noul=0.9)

    def test_answer_probabilities_must_sum_to_one(self) -> None:
        # [Hidden Failure] a distribution that does not sum to 1 is contract drift, not an answer.
        with self.assertRaisesRegex(ConfigurationError, "sum to 1"):
            JevAnswer(question_name="c", question_type=JevQuestionType.CHOICE, choice="a", probabilities={"a": 0.9, "b": 0.9}, confidence=0.5)


class TypeSafeProviderContractTests(unittest.IsolatedAsyncioTestCase):
    """Pins wire serialization, answer normalization, and failure mapping against the documented API."""

    async def test_structured_request_serializes_to_plain_documented_json(self) -> None:
        # [Silent Failure] frozen content is thawed back to JSON and optional noul criteria are omitted.
        noul = JevQuestion(name="urgent", question_type=JevQuestionType.NOUL, instructions="Urgent?")
        body = {"model": "jev-1.13.0", "answers": {"urgent": {"type": "noul", "noul": 0.95}, "frustration": _score_answer()}, "usage": {"input_tokens": 300, "output_tokens": 20}}
        runner, transport = _runner(_response(body))
        await runner.arun(JevDecisionRequest(state={"chat": ["hi", "help"]}, questions=(noul, _score_question())))
        sent = transport.requests[0]["json_body"]
        json.dumps(sent)
        self.assertEqual(sent["state"], {"chat": ["hi", "help"]})
        self.assertNotIn("criteria", sent["questions"]["urgent"])
        self.assertEqual(sent["questions"]["frustration"]["criteria"], ["calm", "frustrated", {"signals": ["caps", "threats"]}])

    async def test_score_answer_maps_index_keys_and_keeps_weighted_score(self) -> None:
        # [Silent Failure] the documented score answer (float score, index-keyed probabilities) normalizes to level labels.
        body = {"model": "jev-1.13.0", "answers": {"frustration": _score_answer()}, "usage": {"input_tokens": 304, "output_tokens": 18}}
        runner, _ = _runner(_response(body))
        answer = (await runner.arun(JevDecisionRequest(state="state", questions=(_score_question(),)))).answer("frustration")
        self.assertEqual(answer.choice, "frustrated")
        self.assertEqual(answer.score, 1.05)
        self.assertEqual(answer.confidence, 0.92)
        self.assertEqual(dict(answer.probabilities), {"calm": 0.0, "frustrated": 0.95, "angry": 0.05})

    async def test_noul_answer_expands_without_confidence(self) -> None:
        # [Silent Failure] noul keeps its raw P(yes) and invents no confidence.
        noul = JevQuestion(name="urgent", question_type=JevQuestionType.NOUL, instructions="Urgent?")
        runner, _ = _runner(_response({"model": "jev-1.13.0", "answers": {"urgent": {"type": "noul", "noul": 0.3}}, "usage": {"input_tokens": 5, "output_tokens": 1}}))
        answer = (await runner.arun(JevDecisionRequest(state="state", questions=(noul,)))).answer("urgent")
        self.assertEqual((answer.choice, answer.noul, answer.confidence), ("false", 0.3, None))

    async def test_contract_drift_raises_with_billed_usage(self) -> None:
        # [Hidden Failure] a wrong type tag, a partial distribution, or an unknown choice is never a partial success.
        drifts = ({"type": "score"}, {"probabilities": {"a": 0.3, "b": 0.7}}, {"choice": "z"})
        for drift in drifts:
            with self.subTest(drift=drift):
                runner, _ = _runner(_response(_choice_body(**drift)))
                with self.assertRaises(ProviderResponseError) as caught:
                    await runner.arun(JevDecisionRequest(state="state", questions=(_question(),)))
                self.assertEqual(caught.exception.details["usage"], {"input_tokens": 12, "output_tokens": 1})

    async def test_default_config_retries_documented_statuses_with_an_idempotency_key(self) -> None:
        # [Hidden Assumption] POST retries are only legal with a key, and 529 is among the retried statuses.
        runner, transport = _runner(_response(_choice_body()))
        await runner.arun(JevDecisionRequest(state="state", questions=(_question(),)))
        sent = transport.requests[0]
        self.assertEqual((sent["retry_count"], sent["timeout_seconds"]), (2, 60.0))
        self.assertIsNotNone(sent["idempotency_key"])
        self.assertTrue({408, 429, 500, 529} <= set(sent["retry_status_codes"]))

    async def test_http_failures_explain_the_documented_status(self) -> None:
        # [Hidden Failure] 401, 422, 429, 529, and a missing response each name their cause and fix.
        cases = (
            (_response({"error": "bad key"}, 401), "API key"),
            (_response({"error": "questions.q.criteria"}, 422), r"invalid \(422\)"),
            (_response({"error": "slow down"}, 429), "rate limit"),
            (_response({"error": "busy"}, 529), "overloaded"),
            (ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http"), "no response arrived"),
        )
        for scripted, pattern in cases:
            with self.subTest(pattern=pattern):
                runner, _ = _runner(scripted)
                with self.assertRaisesRegex(ProviderRequestError, pattern):
                    await runner.arun(JevDecisionRequest(state="state", questions=(_question(),)))

    async def test_unexpected_errors_are_wrapped_and_cancellation_propagates(self) -> None:
        # [Hidden Failure] an unanticipated exception becomes a provider error; cancellation is never swallowed.
        runner, _ = _runner(RuntimeError("boom"))
        with self.assertRaisesRegex(ProviderResponseError, "unexpected RuntimeError: boom"):
            await runner.arun(JevDecisionRequest(state="state", questions=(_question(),)))
        runner, _ = _runner(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await runner.arun(JevDecisionRequest(state="state", questions=(_question(),)))

    async def test_list_models_returns_model_cards(self) -> None:
        # [Silent Failure] GET /v1/models entries become typed cards usable as DecisionModelConfig.model.
        runner, transport = _runner(_response({"models": [{"name": "jev-latest", "description": "Flagship", "release_date": "2026-09-01"}]}))
        cards = await runner.alist_models()
        self.assertEqual([card.name for card in cards], ["jev-latest"])
        self.assertEqual((transport.requests[0]["method"], transport.requests[0]["url"]), ("GET", "https://api.typesafe.ai/v1/models"))


class JevSettingsTests(unittest.TestCase):
    """Pins main-agent configuration, descriptive profile metadata, and separate runtime policy."""

    def test_settings_only_accept_the_agent_catalog(self) -> None:
        # [Hidden Assumption] the settings keep main linear execution separate from TypeSafe policy.
        self.assertIn("name", {item.name for item in fields(JevAgentSettings)})
        self.assertIn("agents", {item.name for item in fields(JevAgentSettings)})

    def test_freezes_one_or_many_profiles_and_rejects_empty_catalog(self) -> None:
        # [Edge Case] one profile skips routing, and no profile catalog keeps ordinary Jev generation available.
        profile = _profile()
        settings = JevAgentSettings(name="general", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", agents=[profile])
        self.assertEqual(settings.agents, (profile,))
        self.assertEqual(JevAgentSettings(name="general", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini").agents, ())

    def test_profile_fields_are_trimmed_unique_and_json_frozen(self) -> None:
        # [Edge Case] profile identity, scope, and nested metadata remain stable after caller mutation.
        metadata = {"scope": ["research"]}
        profile = JevProfile(title="Research", description="Find and summarize sources.", metadata=metadata)
        metadata["scope"].append("mutated")
        self.assertEqual(profile.metadata["scope"], ("research",))
        with self.assertRaises(ConfigurationError):
            JevProfile(title=" ", description="Research.", metadata={})
        with self.assertRaises(ConfigurationError):
            JevProfile(title="Research", description=" ", metadata={})
        duplicate = _profile("Research", "Writes code.")
        with self.assertRaises(ConfigurationError):
            JevAgentSettings(name="general", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", agents=(profile, duplicate))

    def test_profile_and_catalog_limits_match_provider_bounds(self) -> None:
        # [Edge Case] the catalog uses every Choice option and rejects one beyond the provider limit.
        template = _specialist_template()
        self.assertEqual(JEV_AGENT_MAX_COUNT, JEV_MAX_CHOICE_OPTIONS)
        exact_limit = tuple(JevProfile(title=f"agent-{index}", description="Researches questions.", metadata={}) for index in range(JEV_AGENT_MAX_COUNT))
        JevAgentSettings(name="general", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", agents=exact_limit)
        with self.assertRaises(ConfigurationError):
            over_limit = (*exact_limit, JevProfile(title="agent-over", description="Researches questions.", metadata={}))
            JevAgentSettings(name="general", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", agents=over_limit)
        with self.assertRaises(ConfigurationError):
            large = JevProfile(title="Large", description="x" * (JEV_AGENT_MAX_DESCRIPTION_CHARS + 1), metadata={})
            JevAgentSettings(name="general", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", agents=(large,))
        oversized = tuple(JevProfile(title=f"scope-{index}", description="x" * JEV_AGENT_MAX_DESCRIPTION_CHARS) for index in range(32))
        with self.assertRaisesRegex(ConfigurationError, "metadata must fit"):
            JevAgentSettings(name="general", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", agents=oversized)

    def test_profile_records_contain_only_decision_metadata(self) -> None:
        profile = _profile()
        self.assertEqual((profile.title, profile.description), ("general", "Handles general requests."))
        self.assertFalse(hasattr(profile, "agent"))

    def test_runtime_controls_remain_separate_and_validate_thresholds(self) -> None:
        # [Edge Case] runtime-wide controls retain their original defaults and validate finite thresholds.
        runtime = JevRuntimeSettings()
        self.assertEqual(runtime.decision.normalized_provider(), ModelProvider.TYPESAFE)
        self.assertEqual(runtime.tool_selector_threshold, 0.2)
        for threshold in (True, float("nan"), -0.01, 1.01):
            with self.subTest(threshold=threshold), self.assertRaises(ConfigurationError):
                JevRuntimeSettings(tool_selector_threshold=threshold)


class JevAgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Pins runtime specialization while proving the standard loop stays intact."""

    def test_jev_runtime_receives_the_agents_gate_and_trackers(self) -> None:
        # [Silent Failure] each run-local runtime receives Jev's precomputed gate result and agent-owned trackers.
        agent = Jev(_settings())
        runtime = agent._runtime()
        self.assertIsInstance(runtime, JevRuntime)
        self.assertIs(runtime.preflight, agent.preflight)
        self.assertIs(runtime.runtime_settings, agent.runtime_settings)
        self.assertIs(runtime.response.state, agent.response)
        self.assertIs(runtime.usage_tracker, agent._usage_tracker)
        self.assertIs(runtime.speed_tracker, agent._speed_tracker)

    def test_base_agent_still_resolves_standard_runtime(self) -> None:
        # [Hidden Assumption] the runtime hook is behavior-preserving for every ordinary agent.
        agent = BaseAgent(name="base", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini")
        runtime = agent._runtime()
        self.assertIs(type(runtime), AgentRuntime)

    def test_jev_agent_uses_the_jev_runtime_type(self) -> None:
        # [Silent Failure] JevAgent is the "jev" runtime, resolved through the shared registry.
        self.assertIs(Jev(_settings()).runtime_type, AgentRuntimeType.JEV)
        self.assertIs(RuntimeRegistry.resolve(AgentRuntimeType.JEV), JevRuntime)

    def test_plain_base_agent_cannot_build_the_jev_runtime(self) -> None:
        # [Hidden Failure] the jev runtime without JevAgent's preflight gate fails with a message naming JevAgent.
        agent = BaseAgent(name="base", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", runtime="jev")
        with self.assertRaisesRegex(ConfigurationError, "JevAgent"):
            agent._runtime()

    async def test_no_tool_response_uses_ordinary_final_path(self) -> None:
        # [Edge Case] a plain generative response completes without invoking Jev.
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="ordinary answer", raw={}))
        agent = Jev(_settings())
        bind_test_runner(agent, runner)
        reply = await agent.arun("question")
        self.assertEqual(reply.content, "ordinary answer")
        self.assertEqual(len(runner.calls), 1)

    async def test_tool_call_then_completion_uses_ordinary_loop(self) -> None:
        # [Hidden Failure] JevRuntime preserves the established tool execution and continuation behavior.
        @tool
        def lookup(topic: str) -> str:
            """Look up one topic."""
            return f"found:{topic}"

        runner = ScriptedRunner(
            RawResponse({"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "sdk"}', "call_id": "c1"}]}),
            RawResponse({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "c2"}]}),
        )
        agent = Jev(JevAgentSettings(name="main", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", tools=(lookup,)))
        bind_test_runner(agent, runner)
        reply = await agent.arun("question")
        self.assertEqual(reply.content, "done")
        self.assertEqual(reply.metadata["tool_call_states"], ("succeeded", "succeeded"))
        self.assertEqual(len(runner.calls), 2)

    async def test_preflight_selects_profile_metadata_but_keeps_the_linear_generator(self) -> None:
        # Profile routing chooses a semantic label; it never forks or swaps the main model configuration.
        coding = _profile("Coding", "Implements and debugs software changes.")
        research = _profile("Research", "Researches source-backed questions.")
        settings = _settings((coding, research))
        agent = Jev(settings, runtime_settings=JevRuntimeSettings(decision=DecisionModelConfig(api_key=API_KEY)))
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="main", text="linear answer", raw={}))
        bind_test_runner(agent, runner)
        before = (agent.name, agent.system_prompt, agent.runner_config)
        decision_runner = AsyncMock()
        decision_runner.arun.return_value = _specialist_response("Research", {"Coding": 0.1, "Research": 0.9})

        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", return_value=decision_runner):
            reply = await agent.arun("Find research on this SDK.")

        request = decision_runner.arun.await_args.args[0]
        self.assertEqual(request.questions[-1].name, "agent_profile")
        self.assertEqual(tuple(option.name for option in request.questions[-1].options), ("Coding", "Research"))
        self.assertEqual(reply.content, "linear answer")
        self.assertEqual(agent.response.selection.title, "Research")
        self.assertEqual((agent.name, agent.system_prompt, agent.runner_config), before)
        self.assertEqual(len(runner.calls), 1)

    async def test_inconsistent_choice_uses_maximum_and_exact_ties_keep_catalog_order(self) -> None:
        # [Silent Failure] code trusts option probabilities rather than a mismatched declared choice.
        profiles = tuple(_profile(f"Agent {index}", f"Handles type {index} work.") for index in range(4))
        agent = Jev(_settings(profiles))
        decision_runner = AsyncMock()
        decision_runner.arun.return_value = _specialist_response("Agent 3", {f"Agent {index}": 0.25 for index in range(4)})
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", return_value=decision_runner):
            with patch.object(agent, "_runner_for_model", return_value=(ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="answer", raw={})), "text")):
                await agent.arun("Do the task.")
        self.assertEqual(agent.response.selection.title, "Agent 0")
        self.assertEqual(agent.response.selection.probability, 0.25)

    async def test_incomplete_profile_distribution_does_not_record_a_selection(self) -> None:
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="main", text="answer", raw={}))
        agent = Jev(_settings((_profile("First", "Handles first work."), _profile("Second", "Handles second work."))))
        bind_test_runner(agent, runner)
        incomplete = _specialist_response("First", {"First": 1.0})
        decision_runner = AsyncMock()
        decision_runner.arun.return_value = incomplete
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", return_value=decision_runner):
            await agent.arun("Do this task.")
        self.assertIsNone(agent.response.selection)
        self.assertEqual(len(runner.calls), 1)

    async def test_one_profile_skips_routing_and_uses_its_configured_runner(self) -> None:
        # [Hidden Assumption] a single-profile request does not require TypeSafe credentials or selection.
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="single profile", raw={}))
        agent = Jev(_settings((_profile("Solo", "Handles all tasks."),)))
        bind_test_runner(agent, runner)
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner") as decision_runner:
            reply = await agent.arun("Do this.")
        decision_runner.assert_not_called()
        self.assertEqual(reply.content, "single profile")
        self.assertIsNone(agent.response.selection)

    async def test_decision_failure_is_surfaced_without_running_a_candidate(self) -> None:
        # [Hidden Failure] a failed choice must never silently run an arbitrary profile.
        runner = ScriptedRunner()
        agent = Jev(_settings((_profile("First", "Handles first work."), _profile("Second", "Handles second work."))))
        bind_test_runner(agent, runner)
        decision_runner = AsyncMock()
        decision_runner.arun.side_effect = RuntimeError("decision unavailable")
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", return_value=decision_runner):
            with self.assertRaisesRegex(AgentExecutionError, "failed to generate") as caught:
                await agent.arun("Do this task.")
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)
        self.assertEqual(runner.calls, [])
        self.assertIsNone(agent.response.selection)

    async def test_closed_gate_never_reaches_profile_router(self) -> None:
        # [Hidden Assumption] an unclear request spends neither routing nor candidate-model tokens.
        runner = ScriptedRunner()
        profiles = (_profile("First", "Handles first work."), _profile("Second", "Handles second work."))
        agent = Jev(_settings(profiles))
        bind_test_runner(agent, runner)
        decision_runner = AsyncMock()
        with patch.object(agent.preflight, "pass_", AsyncMock(return_value=False)), patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", return_value=decision_runner):
            await agent.arun("Do this task.")
        decision_runner.arun.assert_not_awaited()
        self.assertIsNone(agent.response.selection)
        self.assertEqual(runner.calls, [])

    async def test_profile_selection_never_overlays_main_configuration_on_failure(self) -> None:
        runner = ScriptedRunner(RuntimeError("model failed"))
        agent = Jev(_settings((_profile("First", "Handles first work."), _profile("Second", "Handles second work."))), runtime_settings=JevRuntimeSettings(decision=DecisionModelConfig(api_key=API_KEY)))
        bind_test_runner(agent, runner)
        initial = (agent.name, agent.system_prompt, agent.runner_config, agent.tools, agent.metadata)
        decision_runner = AsyncMock()
        decision_runner.arun.return_value = _specialist_response("Second", {"First": 0.1, "Second": 0.9})
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", return_value=decision_runner):
            with self.assertRaises(AgentExecutionError):
                await agent.arun("Do second work.")
        self.assertEqual((agent.name, agent.system_prompt, agent.runner_config, agent.tools, agent.metadata), initial)

    def test_profile_routing_does_not_add_mutable_runtime_coordination(self) -> None:
        agent = Jev(_settings((_profile("First", "Handles first work."), _profile("Second", "Handles second work."))))
        self.assertFalse(hasattr(agent, "_profile_semaphore"))

    async def test_cancellation_leaves_main_configuration_unchanged(self) -> None:
        class WaitingRunner:
            def __init__(self) -> None:
                # Signals when model execution begins and remains blocked until the test cancels it.
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def arun(self, prompt: str, **kwargs: Any) -> object:
                # Waits so cancellation exercises Jev's finally restoration path.
                self.started.set()
                await self.release.wait()
                return TextModelResponse(provider=ModelProvider.OPENAI, model="waiting", text="finished", raw={})

        waiting = WaitingRunner()
        agent = Jev(_settings((_profile("First", "Handles first work."), _profile("Second", "Handles second work."))))
        bind_test_runner(agent, waiting)
        original = (agent.name, agent.system_prompt, agent.runner_config)
        decision_runner = AsyncMock()
        decision_runner.arun.return_value = _specialist_response("Second", {"Second": 0.9, "First": 0.1})
        with patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", return_value=decision_runner):
            task = asyncio.create_task(agent.arun("second task"))
            await waiting.started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual((agent.name, agent.system_prompt, agent.runner_config), original)


class JevPromptRegistryTests(unittest.TestCase):
    """Pins that every fixed Jev prompt is a Markdown asset reached through the registry."""

    def test_every_registered_prompt_has_markdown_text(self) -> None:
        # [Silent Failure] a registry member without an asset would only fail on its first runtime decision.
        for prompt in JevPrompt:
            with self.subTest(prompt=prompt.name):
                text = JevPrompts.get(prompt)
                self.assertTrue(text)
                self.assertEqual(text, text.strip())

    def test_prompt_enum_is_owned_by_the_shared_jev_enum_module(self) -> None:
        from vidbyte.lib.enums.jev import JevPrompt as CanonicalJevPrompt

        self.assertIs(JevPrompt, CanonicalJevPrompt)

    def test_profile_question_has_a_complete_brief_and_structured_criteria(self) -> None:
        # [Hidden Assumption] the dynamic profile question keeps the named state and criteria sections intact.
        brief = JevPrompts.brief(JevPrompt.AGENT_SELECTION_QUESTION)
        self.assertIn("`request`", brief.state)
        self.assertIn("metadata", brief.state)
        self.assertIn("ignore", " ".join(brief.rules).lower())
        criteria = JevPrompts.selection_criteria()
        self.assertIn("what", criteria)
        self.assertIn("not_for", criteria)
        self.assertIn("examples", criteria)

    def test_rejects_non_member_lookup(self) -> None:
        # [Edge Case] raw strings are not prompt names; callers must use the closed enum.
        with self.assertRaises(ConfigurationError):
            JevPrompts.get("specialist_question")  # type: ignore[arg-type]


class JevPublicApiTests(unittest.TestCase):
    """Pins imports, namespace construction, and the closed constructor."""

    def test_root_and_package_exports_are_identical(self) -> None:
        # [Silent Failure] public import paths resolve the same classes rather than compatibility copies.
        self.assertIs(RootJev, Jev)
        self.assertIs(RootJevProfile, JevProfile)
        self.assertIs(RootJevAgentSettings, JevAgentSettings)
        self.assertIs(RootJevRuntime, JevRuntime)

    def test_sdk_namespace_constructs_jev_agent(self) -> None:
        # [Silent Failure] the root namespace client exposes the opinionated constructor.
        settings = _settings()
        agent = VidbyteSDK().agents.jev(settings, runtime_settings=JevRuntimeSettings())
        self.assertIsInstance(agent, Jev)
        self.assertIs(agent.settings, settings)

    def test_constructor_exposes_only_settings(self) -> None:
        # [Hidden Assumption] only the typed profile and runtime settings objects customize Jev.
        parameters = tuple(inspect.signature(Jev.__init__).parameters)
        self.assertEqual(parameters, ("self", "settings", "runtime_settings"))
        for forbidden in ("runtime", "middleware", "algorithm", "fallback", "decisions", "agents"):
            self.assertNotIn(forbidden, parameters)


if __name__ == "__main__":
    unittest.main()
