"""FILE: tests/test_jev_agent.py

PURPOSE: Verifies the TypeSafe decision substrate and opinionated JevAgent capabilities without network access.
ROLE IN CODEBASE: Covers Jev settings, runtime wiring, multipart state/handoff policy, continuation, provider normalization, and public exports.
ARCHITECTURE NOTE: Scripted transports and runners replace only external model boundaries; production constructors and runtime factories remain under test.
COMMON MODIFICATION PATTERNS: Add cases here whenever a named Jev capability changes settings, runtime policy, fallback behavior, or observability.
KNOWN EDGE CASES: TYPESAFE_API_KEY is cleared where credential timing is tested, and no test may send a live provider request.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-multipart-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_agent.py and python scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import unittest
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent as RootJevAgent
from vidbyte import JevAgentSettings as RootJevAgentSettings
from vidbyte import JevPresets as RootJevPresets
from vidbyte import JevRuntime as RootJevRuntime
from vidbyte import VidbyteSDK, tool
from vidbyte.agents import BaseAgent
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevPresets, JevRuntime
from vidbyte.agents.jev.run_state import (
    JevDeliverableHandoff,
    JevEvidenceReference,
    JevRunHandoff,
    JevRunSnapshot,
    JevRunState,
)
from vidbyte.agents.jev.scope_coverage import (
    JevScopeBreadth,
    JevScopeDimensionHandoff,
    JevScopeHandoff,
    JevScopeUnitRecord,
    JevScopeUnitSource,
)
from vidbyte.agents.jev.scope_coverage.questions import ScopeCoverageQuestions
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_DEFAULT_RETRY_COUNT,
    JEV_DEFAULT_TIMEOUT_SECONDS,
    JEV_MAX_CHOICE_OPTIONS,
    JEV_MAX_SCORE_LEVELS,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevOption,
    JevQuestion,
)
from vidbyte.lib.enums import AgentRuntimeType, JevQuestionType, ModelProvider
from vidbyte.lib.errors import (
    AgentExecutionError,
    ConfigurationError,
    OutputSchemaViolationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.registries.runtimes import RuntimeRegistry
from vidbyte.lib.runners import DecisionModelRunner, TextModelResponse
from vidbyte.tools.security import PermissionPolicy

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
        return self.responses.pop(0)


class RawResponse:
    """OpenAI-shaped raw response wrapper for scripted tool calls."""

    def __init__(self, raw: dict[str, Any]) -> None:
        # Exposes the two response attributes consumed by BaseAgent.
        self.text = ""
        self.raw = raw


def _settings(**overrides: Any) -> JevAgentSettings:
    # Builds valid settings while letting one test replace selected fields.
    values: dict[str, Any] = {
        "name": "jev",
        "system_prompt": "Work carefully.",
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
    }
    values.update(overrides)
    return JevAgentSettings(**values)


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
    """Pins the intentionally narrow, validated settings surface."""

    def test_rejects_blank_identity_fields(self) -> None:
        # [Edge Case] every user-visible identity field must be meaningful.
        for field_name in ("name", "system_prompt", "model_name"):
            with self.subTest(field_name=field_name), self.assertRaises(ConfigurationError):
                _settings(**{field_name: "  "})

    def test_rejects_typesafe_as_generative_provider(self) -> None:
        # [Hidden Assumption] Jev supplies decisions but never the agent's prose response.
        with self.assertRaisesRegex(ConfigurationError, "generative"):
            _settings(provider=ModelProvider.TYPESAFE)
        self.assertEqual(_settings().decision.normalized_provider(), ModelProvider.TYPESAFE)

    def test_rejects_bad_tools_and_nested_settings(self) -> None:
        # [Hidden Failure] strings and unrelated nested objects cannot leak into runtime construction.
        with self.assertRaises(ConfigurationError):
            _settings(tools="lookup")
        for field_name in ("permission_policy", "loop", "decision"):
            with self.subTest(field_name=field_name), self.assertRaises(ConfigurationError):
                _settings(**{field_name: object()})

    def test_normalizes_provider_and_redacts_both_keys(self) -> None:
        # [Silent Failure] canonical provider identity is stored and neither credential appears in repr.
        settings = _settings(api_key="generative-secret", decision=DecisionModelConfig(api_key="decision-secret"))
        rendered = repr(settings)
        self.assertIs(settings.provider, ModelProvider.OPENAI)
        self.assertNotIn("generative-secret", rendered)
        self.assertNotIn("decision-secret", rendered)

    def test_normalizes_tools_and_retains_valid_nested_objects(self) -> None:
        # [Hidden Assumption] iterable tools become immutable while policy and loop objects preserve identity.
        policy = PermissionPolicy()
        loop = AgentLoopSettings(max_iterations=2)
        marker = object()
        settings = _settings(tools=[marker], permission_policy=policy, loop=loop)
        self.assertEqual(settings.tools, (marker,))
        self.assertIs(settings.permission_policy, policy)
        self.assertIs(settings.loop, loop)


class JevAgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Pins runtime specialization while proving the standard loop stays intact."""

    def test_jev_runtime_retains_settings_and_agent_trackers(self) -> None:
        # [Silent Failure] specialized construction keeps settings, usage, and speed identity.
        settings = _settings()
        agent = JevAgent(settings)
        runtime = agent._runtime()
        self.assertIsInstance(runtime, JevRuntime)
        self.assertIs(runtime.jev_settings, settings)
        self.assertIs(runtime.usage_tracker, agent._usage_tracker)
        self.assertIs(runtime.speed_tracker, agent._speed_tracker)

    def test_base_agent_still_resolves_standard_runtime(self) -> None:
        # [Hidden Assumption] the runtime hook is behavior-preserving for every ordinary agent.
        agent = BaseAgent(name="base", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini")
        runtime = agent._runtime()
        self.assertIs(type(runtime), AgentRuntime)

    def test_jev_agent_uses_the_jev_runtime_type(self) -> None:
        # [Silent Failure] JevAgent is the "jev" runtime, resolved through the shared registry.
        self.assertIs(JevAgent(_settings()).runtime_type, AgentRuntimeType.JEV)
        self.assertIs(RuntimeRegistry.resolve(AgentRuntimeType.JEV), JevRuntime)

    def test_plain_base_agent_cannot_build_the_jev_runtime(self) -> None:
        # [Hidden Failure] the jev runtime without JevAgentSettings fails with a message naming JevAgent.
        agent = BaseAgent(name="base", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini", runtime="jev")
        with self.assertRaisesRegex(ConfigurationError, "JevAgent"):
            agent._runtime()

    async def test_no_tool_response_uses_ordinary_final_path(self) -> None:
        # [Edge Case] a plain generative response completes without invoking Jev.
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="ordinary answer", raw={}))
        agent = bind_test_runner(JevAgent(_settings()), runner)
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
        agent = bind_test_runner(JevAgent(_settings(tools=(lookup,))), runner)
        reply = await agent.arun("question")
        self.assertEqual(reply.content, "done")
        self.assertEqual(reply.metadata["tool_call_states"], ("succeeded", "succeeded"))
        self.assertEqual(len(runner.calls), 2)


class JevPublicApiTests(unittest.TestCase):
    """Pins imports, namespace construction, and the closed constructor."""

    def test_root_and_package_exports_are_identical(self) -> None:
        # [Silent Failure] public import paths resolve the same classes rather than compatibility copies.
        self.assertIs(RootJevAgent, JevAgent)
        self.assertIs(RootJevPresets, JevPresets)
        self.assertIs(RootJevAgentSettings, JevAgentSettings)
        self.assertIs(RootJevRuntime, JevRuntime)

    def test_sdk_namespace_constructs_jev_agent(self) -> None:
        # [Silent Failure] the root namespace client exposes the opinionated constructor.
        settings = _settings()
        agent = VidbyteSDK().agents.jev(settings)
        self.assertIsInstance(agent, JevAgent)
        self.assertIs(agent.settings, settings)

    def test_constructor_exposes_only_settings_and_named_done_criteria(self) -> None:
        # [Hidden Assumption] runtime machinery is closed while named done criteria remain configurable.
        parameters = tuple(inspect.signature(JevAgent.__init__).parameters)
        self.assertEqual(parameters, ("self", "settings", "done_criteria"))
        self.assertEqual(inspect.signature(JevAgent.__init__).parameters["done_criteria"].kind, inspect.Parameter.KEYWORD_ONLY)
        for forbidden in ("runtime", "middleware", "algorithm", "fallback", "decisions", "questions"):
            self.assertNotIn(forbidden, parameters)

    def test_done_criteria_rejects_raw_string(self) -> None:
        # [Hidden Assumption] a string-backed enum must still be passed as its named enum member.
        with self.assertRaisesRegex(ConfigurationError, "JevPresets"):
            JevAgent(_settings(), done_criteria="multi_part")

    def test_sdk_namespace_accepts_named_done_criteria(self) -> None:
        # [Silent Failure] the SDK namespace forwards the same preset as the direct constructor.
        agent = VidbyteSDK().agents.jev(_settings(), done_criteria=JevPresets.MultiPart)
        self.assertIs(agent.done_criteria, JevPresets.MultiPart)


def _multipart_state(*deliverables: tuple[str, str, str]) -> JevRunState:
    # Returns a stable generated-state fixture for runtime policy tests.
    return JevRunState.from_payload({
        "goal": "Complete the requested change.",
        "objective": "Deliver each distinct requested output.",
        "mission": "Work through the request and report the result.",
        "what_not_to_do": ["Do not claim unobserved work."],
        "sections": {"constraints": "Respect the original scope."},
        "multi_part": {"deliverables": [
            {"id": item_id, "description": description, "completion_signal": signal}
            for item_id, description, signal in deliverables
        ]},
    })


def _multipart_handoff(*items: tuple[str, str, str, str]) -> JevRunHandoff:
    # Builds one run-handoff fixture with each evidence string tied to a fixture source.
    return JevRunHandoff(tuple(JevDeliverableHandoff(item[0], item[1], (JevEvidenceReference("final_answer", item[2]),), item[3]) for item in items))


class ScriptedMultipartDecisionRunner:
    """Captures one-item Jev requests and returns scripted true probabilities."""

    def __init__(self, *probabilities: float | BaseException) -> None:
        # Retains deterministic outcomes and the exact classification requests.
        self.probabilities = list(probabilities)
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> object:
        # Returns a Jev-shaped response or raises the next scripted provider error.
        from types import SimpleNamespace

        self.requests.append(request)
        probability = self.probabilities.pop(0)
        if isinstance(probability, BaseException):
            raise probability
        answer = JevAnswer(
            question_name=request.questions[0].name,
            question_type=JevQuestionType.NOUL,
            choice="true" if probability >= 0.5 else "false",
            probabilities={"true": probability, "false": 1.0 - probability},
            noul=probability,
        )
        return SimpleNamespace(answer=lambda name: answer if name == answer.question_name else None)


class JevMultipartDoneCriteriaTests(unittest.IsolatedAsyncioTestCase):
    """Tests structured state, per-deliverable classification, and same-loop continuation."""

    async def test_state_is_built_once_and_low_evidence_continues_same_loop(self) -> None:
        # [Hidden Failure] an incomplete first finish gets concrete feedback; the same loop checks again.
        first = _multipart_handoff(("implementation", "incomplete", "Feature code exists.", "Documentation is not written."))
        second = _multipart_handoff(("implementation", "complete", "Feature and documentation are present.", "none"))
        runner = ScriptedRunner(
            TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Implemented the code.", raw={}),
            TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Implementation and docs are complete.", raw={}),
        )
        state = _multipart_state(("implementation", "Implement the feature.", "The feature behavior is implemented."))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), runner)
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        state_builder = AsyncMock(return_value=state)
        handoff_builder = AsyncMock(side_effect=(first, second))
        decisions = ScriptedMultipartDecisionRunner(0.2, 0.95)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", state_builder), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", handoff_builder), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun("Implement the feature and document it.")
        self.assertEqual(reply.content, "Implementation and docs are complete.")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(state_builder.await_count, 1)
        self.assertEqual(handoff_builder.await_count, 2)
        self.assertTrue(reply.metadata["done_criteria"]["complete"])
        self.assertEqual(reply.metadata["done_criteria"]["attempts"], 2)

    async def test_each_jev_request_contains_only_one_deliverable(self) -> None:
        # [Hidden Assumption] code routes two targets into separate Jev states with no unrelated evidence.
        handoff = _multipart_handoff(
            ("implementation", "complete", "Implementation is present.", "none"),
            ("documentation", "complete", "Documentation is present.", "none"),
        )
        state = _multipart_state(
            ("implementation", "Implement the feature.", "The feature is implemented."),
            ("documentation", "Write documentation.", "The requested documentation is written."),
        )
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Done.", raw={}))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), runner)
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        decisions = ScriptedMultipartDecisionRunner(0.91, 0.93)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(return_value=handoff)), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            await agent.arun("Implement and document the feature.")
        self.assertEqual(len(decisions.requests), 2)
        ids = []
        expected_evidence = {"implementation": "Implementation is present.", "documentation": "Documentation is present."}
        for request in decisions.requests:
            payload = json.loads(request.state)
            ids.append(payload["requested_deliverable_id"])
            self.assertEqual(len(payload["initial_state"]["multi_part"]["deliverables"]), 1)
            self.assertEqual(payload["handoff_entry"]["id"], payload["requested_deliverable_id"])
            self.assertEqual(payload["handoff_entry"]["evidence"][0]["excerpt"], expected_evidence[payload["requested_deliverable_id"]])
        self.assertEqual(ids, ["implementation", "documentation"])

    async def test_completion_threshold_is_inclusive_and_below_threshold_retries(self) -> None:
        # [Edge Case] P(true) exactly at 0.8 passes; a slightly lower value does not pass silently.
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        state = _multipart_state(("code", "Implement the feature.", "The feature behavior is present."))
        handoff = _multipart_handoff(("code", "complete", "The feature behavior is implemented.", "none"))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Done.", raw={})))
        decisions = ScriptedMultipartDecisionRunner(0.8)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(return_value=handoff)), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun("Implement the feature.")
        self.assertTrue(reply.metadata["done_criteria"]["complete"])

    async def test_probability_below_threshold_requests_another_iteration(self) -> None:
        # [Silent Failure] a plausible but sub-threshold P(true) cannot be rounded up into completion.
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        state = _multipart_state(("code", "Implement the feature.", "The feature behavior is present."))
        handoff = _multipart_handoff(("code", "complete", "The feature behavior is implemented.", "none"))
        runner = ScriptedRunner(
            TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="First attempt.", raw={}),
            TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Evidence strengthened.", raw={}),
        )
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), runner)
        decisions = ScriptedMultipartDecisionRunner(0.799, 0.95)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(side_effect=(handoff, handoff))), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun("Implement the feature.")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(reply.metadata["done_criteria"]["attempts"], 2)

    async def test_continuation_handoff_keeps_prior_tool_observations(self) -> None:
        # [Silent Failure] both finish snapshots retain earlier successful tool evidence after continuation.
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        @tool
        def lookup(topic: str) -> str:
            """Return a deterministic result for the requested topic."""
            return f"found:{topic}"

        state = _multipart_state(("code", "Implement the feature.", "The feature behavior is present."))
        handoffs = (
            _multipart_handoff(("code", "incomplete", "The lookup result was found.", "Implementation is missing.")),
            _multipart_handoff(("code", "complete", "The feature implementation is present.", "none")),
        )
        runner = ScriptedRunner(
            RawResponse({"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "runtime"}', "call_id": "lookup-1"}]}),
            TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Only looked up the runtime.", raw={}),
            TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Implemented the runtime feature.", raw={}),
        )
        agent = bind_test_runner(JevAgent(_settings(tools=(lookup,)), done_criteria=JevPresets.MultiPart), runner)
        snapshots = []

        async def build_handoff(snapshot: object) -> JevRunHandoff:
            # Retains each snapshot to verify that earlier tool evidence survives continuation.
            snapshots.append(snapshot)
            return handoffs[len(snapshots) - 1]

        decisions = ScriptedMultipartDecisionRunner(0.2, 0.95)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(side_effect=build_handoff)), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun("Implement the feature.")
        self.assertEqual(reply.content, "Implemented the runtime feature.")
        self.assertEqual(len(snapshots), 2)
        self.assertEqual([call["name"] for call in snapshots[0].tool_calls], ["lookup"])
        self.assertEqual(snapshots[0].tool_calls, snapshots[1].tool_calls)

    async def test_real_builders_use_strict_structured_output(self) -> None:
        # [Hidden Failure] production builder subclasses consume the strict state and handoff schemas end to end.
        state_payload = {
            "goal": "Deliver the feature.", "objective": "Implement and document it.", "mission": "Complete both outputs.",
            "what_not_to_do": [], "sections": {"constraints": "Keep the change focused."},
            "multi_part": {"deliverables": [{"id": "code", "description": "Implement the feature.", "completion_signal": "The feature behavior is implemented."}]},
        }
        handoff_payload = {"deliverables": [{"id": "code", "status": "complete", "evidence": [{"source_id": "final_answer", "excerpt": "Implemented and documented."}], "remaining": "none"}]}
        runner = ScriptedRunner(
            TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-4.1-mini", text=json.dumps(state_payload), raw={}, usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}),
            TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-4.1-mini", text="Implemented and documented.", raw={}, usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}),
            TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-4.1-mini", text=json.dumps(handoff_payload), raw={}, usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}),
        )
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), runner)
        decisions = ScriptedMultipartDecisionRunner(0.92)
        from vidbyte.agents.jev import runtime as jev_runtime

        with patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun("Implement and document the feature.")
        self.assertEqual(reply.content, "Implemented and documented.")
        self.assertEqual(len(runner.calls), 3)
        self.assertTrue(reply.metadata["done_criteria"]["complete"])
        self.assertEqual(agent.get_usage().model_call_count, 3)
        self.assertEqual(agent.get_usage().total_tokens, 36)

    async def test_empty_deliverables_skip_handoff_and_type_safe_setup(self) -> None:
        # [Edge Case] an empty multipart section completes without building a handoff or resolving Jev credentials.
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        state = _multipart_state()
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Done.", raw={})))
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", new_callable=AsyncMock) as handoff, patch.object(jev_runtime, "DecisionModelRunner") as decision_runner:
            reply = await agent.arun("A single simple request.")
        handoff.assert_not_awaited()
        decision_runner.assert_not_called()
        self.assertTrue(reply.metadata["done_criteria"]["complete"])

    async def test_is_done_tool_uses_the_same_multipart_gate(self) -> None:
        # [Hidden Failure] the internal isDone path cannot bypass enabled done criteria.
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        state = _multipart_state(("answer", "Answer the question.", "The final answer addresses the request."))
        handoff = _multipart_handoff(("answer", "complete", "The final answer addresses the request.", "none"))
        runner = ScriptedRunner(RawResponse({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "c1"}]}))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), runner)
        decisions = ScriptedMultipartDecisionRunner(0.9)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(return_value=handoff)), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun("Answer the question.")
        self.assertEqual(reply.content, "done")
        self.assertEqual(len(decisions.requests), 1)

    async def test_incomplete_handoff_schema_fails_before_classification(self) -> None:
        # [Hidden Failure] missing, duplicate, and unknown IDs fail closed before any Jev request.
        state = _multipart_state(("code", "Implement.", "Code is implemented."))
        for rows in (
            (),
            (("code", "complete", "evidence", "none"), ("code", "complete", "evidence", "none")),
            (("unknown", "complete", "evidence", "none"),),
        ):
            with self.subTest(rows=rows), self.assertRaises(OutputSchemaViolationError):
                JevRunHandoff.from_payload({"deliverables": [dict(zip(("id", "status", "evidence", "remaining"), (row[0], row[1], [{"source_id": "final_answer", "excerpt": row[2]}], row[3]))) for row in rows]}, state, JevRunSnapshot("request", state, (), (), "evidence"))

    async def test_handoff_order_is_matched_by_identifier(self) -> None:
        # [Silent Failure] reordered generated handoff rows still align with state IDs, not array position.
        state = _multipart_state(("code", "Implement.", "Code exists."), ("docs", "Document.", "Docs exist."))
        handoff = JevRunHandoff.from_payload({"deliverables": [
            {"id": "docs", "status": "complete", "evidence": [{"source_id": "final_answer", "excerpt": "Docs exist."}], "remaining": "none"},
            {"id": "code", "status": "complete", "evidence": [{"source_id": "final_answer", "excerpt": "Code exists."}], "remaining": "none"},
        ]}, state, JevRunSnapshot("request", state, (), (), "Code exists. Docs exist."))
        self.assertEqual([item.id for item in handoff.deliverables], ["code", "docs"])

    async def test_handoff_rejects_unknown_sources_and_invented_excerpts(self) -> None:
        # [Silent Failure] a fluent fabricated sentence cannot enter Jev state as evidence.
        state = _multipart_state(("code", "Implement.", "Code exists."))
        snapshot = JevRunSnapshot("request", state, (), (), "The code exists in this answer.")
        bad_rows = (
            {"id": "code", "status": "complete", "evidence": [{"source_id": "missing_source", "excerpt": "The code exists"}], "remaining": "none"},
            {"id": "code", "status": "complete", "evidence": [{"source_id": "final_answer", "excerpt": "This fabricated evidence is not in the answer."}], "remaining": "none"},
        )
        for row in bad_rows:
            with self.subTest(row=row), self.assertRaises(OutputSchemaViolationError):
                JevRunHandoff.from_payload({"deliverables": [row]}, state, snapshot)

    async def test_provider_failure_does_not_return_agent_success(self) -> None:
        # [Hidden Failure] an unavailable Jev decision service propagates instead of selecting a success policy.
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        state = _multipart_state(("code", "Implement.", "Code exists."))
        handoff = _multipart_handoff(("code", "complete", "Code exists.", "none"))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Done.", raw={})))
        decisions = ScriptedMultipartDecisionRunner(ProviderResponseError("unavailable", provider="typesafe"))
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(return_value=handoff)), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            with self.assertRaises(AgentExecutionError) as raised:
                await agent.arun("Implement the feature.")
        self.assertEqual(raised.exception.details["error_type"], "ProviderResponseError")

    async def test_state_output_rejects_duplicates_and_missing_fields(self) -> None:
        # [Hidden Failure] model output that looks like JSON but omits state fields or repeats IDs is rejected.
        valid = {
            "goal": "Goal", "objective": "Objective", "mission": "Mission", "what_not_to_do": [], "sections": {},
            "multi_part": {"deliverables": [{"id": "code", "description": "Code", "completion_signal": "Code exists."}]},
        }
        with self.assertRaises(OutputSchemaViolationError):
            JevRunState.from_payload({"goal": "only one field"})
        duplicate = {**valid, "multi_part": {"deliverables": [*valid["multi_part"]["deliverables"], valid["multi_part"]["deliverables"][0]]}}
        with self.assertRaises(OutputSchemaViolationError):
            JevRunState.from_payload(duplicate)

    async def test_metadata_maps_each_deliverable_to_its_probability(self) -> None:
        # [Silent Failure] final metadata preserves the exact identifier/probability association.
        state = _multipart_state(("code", "Implement.", "Code exists."), ("docs", "Document.", "Docs exist."))
        handoff = _multipart_handoff(("code", "complete", "Code exists.", "none"), ("docs", "complete", "Docs exist.", "none"))
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Done.", raw={}))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.MultiPart), runner)
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        decisions = ScriptedMultipartDecisionRunner(0.91, 0.84)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(return_value=handoff)), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun("Implement and document.")
        rows = reply.metadata["done_criteria"]["multi_part"]["deliverables"]
        self.assertEqual(rows["code"]["probability"], 0.91)
        self.assertEqual(rows["docs"]["probability"], 0.84)


WEB_CLI_API = "Add CSV export to the web, CLI, and API clients."
ALL_PROVIDERS = "Add CSV export to all our model providers."


def _scope_dimension(**overrides: Any) -> dict[str, Any]:
    # Builds one valid named-list dimension payload over WEB_CLI_API, letting a test replace fields.
    values: dict[str, Any] = {
        "id": "clients",
        "request_quote": "Add CSV export to the web, CLI, and API clients",
        "requested_change": "Add CSV export",
        "unit_noun": "client",
        "membership_rule": "a client named in the request",
        "breadth": "named_list",
        "universe": "named_in_request",
        "named_units": ["web", "CLI", "API"],
        "excluded_units": [],
        "partial_allowed_quote": "",
        "deliverable_id": "",
    }
    values.update(overrides)
    return values


def _scope_state(request: str, *dimensions: dict[str, Any], presets: tuple[JevPresets, ...] = (JevPresets.ScopeCoverage,), deliverables: tuple[dict[str, str], ...] = ()) -> JevRunState:
    # Builds a request-grounded generated state through the production validator.
    payload: dict[str, Any] = {
        "goal": "Complete the requested change.",
        "objective": "Reach every requested member.",
        "mission": "Work through the request and report the result.",
        "what_not_to_do": [],
        "sections": {},
        "scope": {"dimensions": list(dimensions)},
    }
    if JevPresets.MultiPart in presets:
        payload["multi_part"] = {"deliverables": list(deliverables)}
    return JevRunState.from_payload(payload, presets=presets, original_request=request)


def _unit(name: str, *work: str, source: JevScopeUnitSource = JevScopeUnitSource.NAMED_IN_REQUEST) -> JevScopeUnitRecord:
    # Builds one unit record whose work excerpts cite the first iteration.
    return JevScopeUnitRecord(name, source, tuple(JevEvidenceReference("iteration_1", item) for item in work))


def _scope_handoff(*units: JevScopeUnitRecord, dimension_id: str = "clients", enumeration: tuple[str, ...] = (), deliverables: tuple[JevDeliverableHandoff, ...] = ()) -> JevRunHandoff:
    # Builds a run handoff whose scope section accounts for one dimension.
    account = JevScopeDimensionHandoff(dimension_id, tuple(JevEvidenceReference("tool_call_1", item) for item in enumeration), units, (), ())
    return JevRunHandoff(deliverables, JevScopeHandoff((account,)))


def _distribution(winner: str, probability: float, options: tuple[str, ...]) -> dict[str, float]:
    # Spreads the remaining probability evenly so the distribution sums to one.
    rest = (1.0 - probability) / (len(options) - 1)
    return {option: (probability if option == winner else rest) for option in options}


UNIT_OPTIONS = ("applied", "attempted", "examined_only", "none")
STATEMENT_OPTIONS = ("claims_all", "reports_partial", "silent")
BREADTH_OPTIONS = ("every_member", "named_list", "one_example", "single_target")


class ScriptedChoiceDecisionRunner:
    """Answers Jev requests from a per-question script and records every request."""

    def __init__(self, **scripts: list[dict[str, float] | float]) -> None:
        # Retains one queue of distributions (choice) or P(true) values (noul) per question name.
        self.scripts = {name: list(values) for name, values in scripts.items()}
        self.requests: list[JevDecisionRequest] = []

    def names(self) -> list[str]:
        # Returns the question name of every recorded request in order.
        return [request.questions[0].name for request in self.requests]

    async def arun(self, request: JevDecisionRequest) -> object:
        # Returns a Jev-shaped response for the next scripted value of this question.
        from types import SimpleNamespace

        self.requests.append(request)
        question = request.questions[0]
        value = self.scripts[question.name].pop(0)
        if question.question_type is JevQuestionType.NOUL:
            answer = JevAnswer(question.name, JevQuestionType.NOUL, "true" if value >= 0.5 else "false", {"true": value, "false": 1.0 - value}, noul=value)
        else:
            answer = JevAnswer(question.name, JevQuestionType.CHOICE, max(value, key=value.get), value, confidence=max(value.values()))
        return SimpleNamespace(answer=lambda name: answer if name == answer.question_name else None)


def _text(text: str) -> TextModelResponse:
    # Builds one scripted final text response.
    return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


class JevScopeCoverageDoneCriteriaTests(unittest.IsolatedAsyncioTestCase):
    """Tests scope state grounding, per-unit classification, continuation, and disclosure."""

    async def _run(self, request: str, state: JevRunState, handoffs: tuple[JevRunHandoff, ...], decisions: ScriptedChoiceDecisionRunner, *texts: str, done_criteria: Any = JevPresets.ScopeCoverage) -> tuple[Any, ScriptedRunner, Any, Any]:
        # Runs one JevAgent with scripted builders, model replies, and Jev answers.
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        runner = ScriptedRunner(*(_text(item) for item in texts))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=done_criteria), runner)
        state_builder = AsyncMock(return_value=state)
        handoff_builder = AsyncMock(side_effect=handoffs)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", state_builder), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", handoff_builder), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun(request)
        return reply, runner, state_builder, handoff_builder

    async def test_named_list_partial_continues_until_every_member_is_covered(self) -> None:
        # [Hidden Failure] web alone cannot finish a web/CLI/API request; the same loop continues with the missing members.
        state = _scope_state(WEB_CLI_API, _scope_dimension())
        first = _scope_handoff(_unit("web", "Added export to web."), _unit("CLI"), _unit("API"))
        second = _scope_handoff(_unit("web", "Added export to web."), _unit("CLI", "Added export to CLI."), _unit("API", "Added export to API."))
        decisions = ScriptedChoiceDecisionRunner(
            unit_coverage=[_distribution("applied", 0.9, UNIT_OPTIONS)] * 4,
            coverage_statement=[_distribution("silent", 0.8, STATEMENT_OPTIONS)],
        )
        reply, runner, state_builder, handoff_builder = await self._run(WEB_CLI_API, state, (first, second), decisions, "Added export to web.", "All three clients export CSV.")
        self.assertEqual(reply.content, "All three clients export CSV.")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(state_builder.await_count, 1)
        self.assertEqual(handoff_builder.await_count, 2)
        self.assertEqual(decisions.names(), ["unit_coverage", "coverage_statement", "unit_coverage", "unit_coverage", "unit_coverage"])
        feedback = json.dumps(runner.calls[1])
        self.assertIn("CLI, API", feedback)
        report = reply.metadata["done_criteria"]
        self.assertTrue(report["complete"])
        self.assertEqual(report["attempts"], 2)
        self.assertEqual(report["scope_coverage"]["outcome"], "complete")
        self.assertEqual(report["scope_coverage"]["dimensions"]["clients"]["covered_units"], ["web", "CLI", "API"])

    async def test_overclaiming_final_answer_is_named_in_feedback(self) -> None:
        # [Silent Failure] "all clients done" with one client worked gets feedback that names the overclaim.
        state = _scope_state(WEB_CLI_API, _scope_dimension())
        first = _scope_handoff(_unit("web", "Added export to web."), _unit("CLI"), _unit("API"))
        second = _scope_handoff(_unit("web", "Added export to web."), _unit("CLI", "Added export to CLI."), _unit("API", "Added export to API."))
        decisions = ScriptedChoiceDecisionRunner(
            unit_coverage=[_distribution("applied", 0.9, UNIT_OPTIONS)] * 4,
            coverage_statement=[_distribution("claims_all", 0.9, STATEMENT_OPTIONS)],
        )
        _, runner, _, _ = await self._run(WEB_CLI_API, state, (first, second), decisions, "Every client exports CSV.", "Every client exports CSV.")
        self.assertIn("says the change reached every client", json.dumps(runner.calls[1]))

    async def test_units_below_threshold_and_examined_only_units_are_uncovered(self) -> None:
        # [Edge Case] P(applied) at exactly 0.8 covers; 0.79 does not, and neither does an examined-only unit.
        state = _scope_state(WEB_CLI_API, _scope_dimension())
        handoff = _scope_handoff(_unit("web", "a"), _unit("CLI", "b"), _unit("API", "c"))
        decisions = ScriptedChoiceDecisionRunner(
            unit_coverage=[_distribution("applied", 0.8, UNIT_OPTIONS), _distribution("applied", 0.79, UNIT_OPTIONS), _distribution("examined_only", 0.9, UNIT_OPTIONS)] + [_distribution("applied", 0.9, UNIT_OPTIONS)] * 3,
            coverage_statement=[_distribution("silent", 0.9, STATEMENT_OPTIONS)],
        )
        _, runner, _, _ = await self._run(WEB_CLI_API, state, (handoff, handoff), decisions, "a b c", "a b c")
        feedback = json.dumps(runner.calls[1])
        self.assertIn("finished for: CLI, API.", feedback)

    async def test_one_example_request_is_not_checked(self) -> None:
        # [Edge Case] "show one example" never triggers a continuation or a handoff.
        request = "Show an example provider that supports CSV export."
        state = _scope_state(request, _scope_dimension(request_quote="Show an example provider", breadth="one_example", universe="found_in_workspace", named_units=[], unit_noun="provider"))
        decisions = ScriptedChoiceDecisionRunner(scope_breadth=[_distribution("one_example", 0.9, BREADTH_OPTIONS)])
        reply, runner, _, handoff_builder = await self._run(request, state, (), decisions, "Here is the OpenAI example.")
        self.assertEqual(len(runner.calls), 1)
        handoff_builder.assert_not_awaited()
        self.assertEqual(decisions.names(), ["scope_breadth"])
        report = reply.metadata["done_criteria"]["scope_coverage"]
        self.assertEqual(report["outcome"], "not_checked")
        self.assertFalse(report["dimensions"]["clients"]["checked"])

    async def test_breadth_review_widens_a_mislabeled_group_and_requires_a_listing(self) -> None:
        # [Hidden Failure] a builder that labels "all our providers" as one example is corrected, then the unlisted universe continues the run.
        state = _scope_state(ALL_PROVIDERS, _scope_dimension(id="providers", request_quote="all our model providers", breadth="one_example", universe="found_in_workspace", named_units=[], unit_noun="model provider"))
        seen_states: list[JevRunState] = []
        handoffs = (
            _scope_handoff(dimension_id="providers"),
            _scope_handoff(_unit("openai", "Added export to openai.", source=JevScopeUnitSource.FOUND_BY_RUN), dimension_id="providers", enumeration=("openai.py",)),
        )
        decisions = ScriptedChoiceDecisionRunner(
            scope_breadth=[_distribution("every_member", 0.7, BREADTH_OPTIONS)],
            unit_coverage=[_distribution("applied", 0.9, UNIT_OPTIONS)],
            coverage_statement=[_distribution("silent", 0.9, STATEMENT_OPTIONS)],
        )
        from unittest.mock import AsyncMock

        from vidbyte.agents.jev import runtime as jev_runtime

        original_init = jev_runtime.JevRunHandoffBuilderAgent.__init__

        def capture_init(builder: Any, *, source_agent: Any, settings: Any, state: JevRunState) -> None:
            # Records the reviewed state the runtime hands to the handoff builder.
            seen_states.append(state)
            original_init(builder, source_agent=source_agent, settings=settings, state=state)

        runner = ScriptedRunner(_text("Added export to openai."), _text("Listed and updated every provider."))
        agent = bind_test_runner(JevAgent(_settings(), done_criteria=JevPresets.ScopeCoverage), runner)
        with patch.object(jev_runtime.JevRunStateBuilderAgent, "build_state", AsyncMock(return_value=state)), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "__init__", capture_init), patch.object(jev_runtime.JevRunHandoffBuilderAgent, "build_handoff", AsyncMock(side_effect=handoffs)), patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun(ALL_PROVIDERS)
        dimension = seen_states[0].scope.dimensions[0]
        self.assertIs(dimension.breadth, JevScopeBreadth.EVERY_MEMBER)
        self.assertTrue(dimension.breadth_upgraded)
        self.assertIn("never listed every model provider", json.dumps(runner.calls[1]))
        self.assertTrue(reply.metadata["done_criteria"]["complete"])
        self.assertTrue(reply.metadata["done_criteria"]["scope_coverage"]["dimensions"]["providers"]["breadth_upgraded"])

    async def test_request_that_allows_partial_coverage_is_not_checked(self) -> None:
        # [Edge Case] "just the web one for now" is permission; no Jev call and no continuation follow.
        request = "Add CSV export to the web, CLI, and API clients, but just the web one for now."
        state = _scope_state(request, _scope_dimension(partial_allowed_quote="just the web one for now"))
        decisions = ScriptedChoiceDecisionRunner()
        reply, runner, _, handoff_builder = await self._run(request, state, (), decisions, "Web exports CSV.")
        self.assertEqual(len(runner.calls), 1)
        handoff_builder.assert_not_awaited()
        self.assertEqual(decisions.requests, [])
        self.assertEqual(reply.metadata["done_criteria"]["scope_coverage"]["outcome"], "not_checked")

    async def test_disclosed_gap_is_accepted_after_the_coverage_attempts(self) -> None:
        # [Edge Case] after two coverage continuations, an answer that reports the gap may end the run as a partial result.
        state = _scope_state(WEB_CLI_API, _scope_dimension(named_units=["web", "CLI"], request_quote="the web, CLI"))
        handoff = _scope_handoff(_unit("web", "Added export to web."), _unit("CLI"))
        decisions = ScriptedChoiceDecisionRunner(
            unit_coverage=[_distribution("applied", 0.9, UNIT_OPTIONS)] * 3,
            coverage_statement=[_distribution("silent", 0.9, STATEMENT_OPTIONS), _distribution("silent", 0.9, STATEMENT_OPTIONS), _distribution("reports_partial", 0.9, STATEMENT_OPTIONS)],
        )
        reply, runner, _, _ = await self._run(WEB_CLI_API, state, (handoff,) * 3, decisions, "web", "web", "Web is done; the CLI is not done.")
        self.assertEqual(len(runner.calls), 3)
        report = reply.metadata["done_criteria"]
        self.assertFalse(report["complete"])
        self.assertEqual(report["scope_coverage"]["outcome"], "partial_disclosed")
        self.assertEqual(report["scope_coverage"]["dimensions"]["clients"]["uncovered_units"], ["CLI"])

    async def test_silent_gap_gets_one_disclosure_request_then_is_accepted_as_undisclosed(self) -> None:
        # [Silent Failure] a silent partial answer is asked once to report the gap; the runtime never rewrites the output.
        state = _scope_state(WEB_CLI_API, _scope_dimension(named_units=["web", "CLI"], request_quote="the web, CLI"))
        handoff = _scope_handoff(_unit("web", "Added export to web."), _unit("CLI"))
        decisions = ScriptedChoiceDecisionRunner(
            unit_coverage=[_distribution("applied", 0.9, UNIT_OPTIONS)] * 4,
            coverage_statement=[_distribution("silent", 0.9, STATEMENT_OPTIONS)] * 4,
        )
        reply, runner, _, _ = await self._run(WEB_CLI_API, state, (handoff,) * 4, decisions, "web", "web", "web", "Web export works.")
        self.assertEqual(len(runner.calls), 4)
        self.assertIn("state plainly in your final answer", json.dumps(runner.calls[3]))
        self.assertEqual(reply.content, "Web export works.")
        self.assertEqual(reply.metadata["done_criteria"]["scope_coverage"]["outcome"], "partial_undisclosed")

    async def test_combined_presets_share_one_state_and_one_handoff_per_attempt(self) -> None:
        # [Hidden Assumption] two presets cost one state call and one handoff call; each reports its own subsection.
        presets = (JevPresets.MultiPart, JevPresets.ScopeCoverage)
        state = _scope_state(WEB_CLI_API, _scope_dimension(deliverable_id="export"), presets=presets, deliverables=({"id": "export", "description": "Add CSV export.", "completion_signal": "CSV export exists."},))
        deliverable = JevDeliverableHandoff("export", "complete", (JevEvidenceReference("final_answer", "CSV export exists."),), "none")
        handoff = _scope_handoff(_unit("web", "a"), _unit("CLI", "b"), _unit("API", "c"), deliverables=(deliverable,))
        decisions = ScriptedChoiceDecisionRunner(evidence_matches_completion_signal=[0.95], unit_coverage=[_distribution("applied", 0.9, UNIT_OPTIONS)] * 3)
        reply, runner, state_builder, handoff_builder = await self._run(WEB_CLI_API, state, (handoff,), decisions, "CSV export exists.", done_criteria=(JevPresets.ScopeCoverage, JevPresets.MultiPart))
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(state_builder.await_count, 1)
        self.assertEqual(handoff_builder.await_count, 1)
        report = reply.metadata["done_criteria"]
        self.assertEqual(report["presets"], ["multi_part", "scope_coverage"])
        self.assertTrue(report["multi_part"]["complete"])
        self.assertTrue(report["scope_coverage"]["complete"])

    async def test_real_builders_ground_scope_in_the_request_end_to_end(self) -> None:
        # [Hidden Failure] production builders compose the scope schema, and handoff citations resolve against real tool outputs.
        @tool
        def edit(target: str) -> str:
            """Apply the requested change to one target."""
            return f"edited:{target}"

        request = "Add CSV export to the web and CLI clients."
        state_payload = {
            "goal": "CSV export.", "objective": "Both clients export CSV.", "mission": "Change both clients.", "what_not_to_do": [], "sections": {},
            "scope": {"dimensions": [_scope_dimension(request_quote="the web and CLI clients", named_units=["web", "CLI"])]},
        }
        handoff_payload = {"scope": {"dimensions": [{
            "dimension_id": "clients",
            "enumeration": [],
            "units": [
                {"unit": "web", "source": "named_in_request", "work": [{"source_id": "tool_call_1", "excerpt": "edited:web"}]},
                {"unit": "CLI", "source": "named_in_request", "work": [{"source_id": "tool_call_2", "excerpt": "edited:CLI"}]},
            ],
            "narrowing": [],
            "coverage_claims": [{"source_id": "final_answer", "excerpt": "web and CLI"}],
        }]}}
        runner = ScriptedRunner(
            _text(json.dumps(state_payload)),
            RawResponse({"output": [{"type": "function_call", "name": "edit", "arguments": '{"target": "web"}', "call_id": "e1"}]}),
            RawResponse({"output": [{"type": "function_call", "name": "edit", "arguments": '{"target": "CLI"}', "call_id": "e2"}]}),
            _text("Added CSV export to web and CLI."),
            _text(json.dumps(handoff_payload)),
        )
        agent = bind_test_runner(JevAgent(_settings(tools=(edit,)), done_criteria=JevPresets.ScopeCoverage), runner)
        decisions = ScriptedChoiceDecisionRunner(unit_coverage=[_distribution("applied", 0.9, UNIT_OPTIONS)] * 2)
        from vidbyte.agents.jev import runtime as jev_runtime

        with patch.object(jev_runtime, "DecisionModelRunner", return_value=decisions):
            reply = await agent.arun(request)
        self.assertEqual(reply.content, "Added CSV export to web and CLI.")
        self.assertEqual(len(runner.calls), 5)
        self.assertIn("## `scope`", json.dumps(runner.calls[0]))
        self.assertTrue(reply.metadata["done_criteria"]["complete"])


class JevScopeCoverageContractTests(unittest.TestCase):
    """Tests request grounding, handoff validation, and the done_criteria surface without running an agent."""

    def test_state_rejects_scope_text_not_quoted_from_the_request(self) -> None:
        # [Hidden Failure] an invented quote, an invented unit, or an impossible named list fails closed.
        for overrides in (
            {"request_quote": "every client in the company"},
            {"named_units": ["web", "desktop"]},
            {"named_units": ["web"], "request_quote": "the web"},
            {"deliverable_id": "missing"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(OutputSchemaViolationError):
                _scope_state(WEB_CLI_API, _scope_dimension(**overrides))

    def test_state_quote_check_ignores_case_and_whitespace_only(self) -> None:
        # [Edge Case] formatting differences are tolerated; the words themselves must match.
        state = _scope_state(WEB_CLI_API, _scope_dimension(request_quote="add csv export to   the WEB, cli, and api clients"))
        self.assertEqual(state.scope.dimensions[0].named_units, ("web", "CLI", "API"))

    def test_handoff_rejects_a_missing_named_unit_and_miscited_sources(self) -> None:
        # [Silent Failure] a handoff that drops a named member or cites the final answer as work never reaches Jev.
        state = _scope_state(WEB_CLI_API, _scope_dimension())
        snapshot = JevRunSnapshot(WEB_CLI_API, state, ("Added export to web.",), (), "All clients are done.")

        def payload(units: list[dict[str, Any]]) -> dict[str, Any]:
            # Wraps unit rows in one otherwise valid scope handoff.
            return {"scope": {"dimensions": [{"dimension_id": "clients", "enumeration": [], "units": units, "narrowing": [], "coverage_claims": []}]}}

        named = [{"unit": name, "source": "named_in_request", "work": []} for name in ("web", "CLI", "API")]
        JevRunHandoff.from_payload(payload(named), state, snapshot)
        with self.assertRaises(OutputSchemaViolationError):
            JevRunHandoff.from_payload(payload(named[:2]), state, snapshot)
        final_as_work = [{**named[0], "work": [{"source_id": "final_answer", "excerpt": "All clients are done."}]}, *named[1:]]
        with self.assertRaises(OutputSchemaViolationError):
            JevRunHandoff.from_payload(payload(final_as_work), state, snapshot)

    def test_unit_sources_are_recomputed_and_exclusions_are_not_required(self) -> None:
        # [Hidden Assumption] a "found" unit absent from the listing is demoted, and an excluded unit is never required.
        request = "Add retries to every provider adapter except Cohere."
        state = _scope_state(request, _scope_dimension(id="providers", request_quote="every provider adapter", breadth="every_member", universe="found_in_workspace", named_units=[], excluded_units=["Cohere"], unit_noun="provider adapter"))
        listing = {"name": "ls", "arguments": {}, "state": "succeeded", "output": "openai.py anthropic.py cohere.py"}
        snapshot = JevRunSnapshot(request, state, (), (listing,), "Done.")
        handoff = JevRunHandoff.from_payload({"scope": {"dimensions": [{
            "dimension_id": "providers",
            "enumeration": [{"source_id": "tool_call_1", "excerpt": "openai.py anthropic.py cohere.py"}],
            "units": [
                {"unit": "openai", "source": "found_by_run", "work": []},
                {"unit": "anthropic", "source": "found_by_run", "work": []},
                {"unit": "cohere", "source": "found_by_run", "work": []},
                {"unit": "gemini", "source": "found_by_run", "work": []},
            ],
            "narrowing": [],
            "coverage_claims": [],
        }]}}, state, snapshot)
        account = handoff.scope.dimensions[0]
        self.assertIs(account.units[3].source, JevScopeUnitSource.MENTIONED_BY_AGENT)
        self.assertEqual([item.unit for item in account.required_units(state.scope.dimensions[0])], ["openai", "anthropic"])

    def test_unit_question_state_holds_only_its_own_unit_and_work(self) -> None:
        # [Hidden Assumption] Jev judges one unit at a time and never sees the request, other units, or the run.
        from vidbyte.lib.dataclasses.jev import JevJson

        state = _scope_state(WEB_CLI_API, _scope_dimension())
        request = ScopeCoverageQuestions.unit_request(state.scope.dimensions[0], _unit("CLI", "Read the CLI module."))
        payload = JevJson.thaw(request.state)
        self.assertEqual(sorted(payload), ["requested_change", "unit", "unit_noun", "work_record"])
        self.assertEqual(payload["unit"], "CLI")
        self.assertEqual(payload["work_record"], [{"source_id": "iteration_1", "excerpt": "Read the CLI module."}])
        self.assertEqual([option.name for option in request.questions[0].options], list(UNIT_OPTIONS))

    def test_done_criteria_accepts_distinct_preset_tuples_only(self) -> None:
        # [Edge Case] tuples are normalized to declaration order; empty, duplicate, and raw-string tuples are rejected.
        agent = JevAgent(_settings(), done_criteria=(JevPresets.ScopeCoverage, JevPresets.MultiPart))
        self.assertEqual(agent.done_presets, (JevPresets.MultiPart, JevPresets.ScopeCoverage))
        for bad in ((), (JevPresets.MultiPart, JevPresets.MultiPart), ("scope_coverage",), [JevPresets.MultiPart]):
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                JevAgent(_settings(), done_criteria=bad)


if __name__ == "__main__":
    unittest.main()
