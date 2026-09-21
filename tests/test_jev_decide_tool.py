"""FILE: tests/test_jev_decide_tool.py

PURPOSE:
    Verifies the TypeSafe Jev integration end to end without network access: the
    provider registry and runner catalog entries, DecisionModelConfig and the Jev
    records, TypeSafeProvider's wire shape and answer normalization, JevUsage
    pricing, the ModelBackedTool metering seam, and the jev_decide tool's parsing,
    rendering, fail-open behavior, redaction, and decision records.
ROLE IN CODEBASE:
    Covers every case in docs/design/jev-decide-tool.md section 10;
    scripts/test_jev_decide_tool.py runs this module case by case.
ARCHITECTURE NOTE:
    A scripted fake transport stands in for HttpTransport, and agent-level tests
    bind a scripted text runner through tests/agent_test_support.py.
COMMON MODIFICATION PATTERNS:
    Add a case next to the behavior it pins and label its failure category in the
    test name's docstring.
KNOWN EDGE CASES:
    TYPESAFE_API_KEY is cleared for every test so a developer's real key can never
    reach a test or change its outcome.
RELATED DOCS:
    docs/design/jev-decide-tool.md
TESTS:
    python -m pytest tests/test_jev_decide_tool.py and python scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from vidbyte.agents.pricing import JevUsage, UsageTracker
from vidbyte.agents.pricing.records import UsageRecordingIntegrity
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_MAX_OPTIONS
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevOption, JevQuestion
from vidbyte.lib.dataclasses.jev_settings import JevDecideSettings
from vidbyte.lib.dataclasses.tool_model_usage import ToolModelCall
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError, ProviderResponseError, ProviderSelectionError, UnsupportedProviderError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.runners import Runner
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.providers import ModelProviders, TypeSafeProvider
from vidbyte.tools import JevDecideTool, ModelBackedTool, ToolActivity, ToolCall, ToolResult
from pydantic import BaseModel

API_KEY = "ts-test-key-123456"
USAGE = {"input_tokens": 1200, "output_tokens": 4}


class ScriptedTransport:
    """Fake HttpTransport that records each request and replays scripted responses or errors."""

    def __init__(self, *responses: HttpResponse | BaseException) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> HttpResponse:
        self.requests.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def ok(body: dict[str, Any]) -> HttpResponse:
    return HttpResponse(status_code=200, body=json.dumps(body), headers={})


def status(code: int) -> HttpResponse:
    return HttpResponse(status_code=code, body=json.dumps({"error": {"message": f"status {code}"}}), headers={})


def choice_body(choice: str = "b", probabilities: dict[str, float] | None = None, confidence: float = 0.8) -> dict[str, Any]:
    probs = probabilities or {"a": 0.1, "b": 0.8, "c": 0.1}
    return {"model": "jev-latest", "answers": {"decision": {"choice": choice, "probabilities": probs, "confidence": confidence}}, "usage": USAGE}


def choice_question(options: tuple[str, ...] = ("a", "b", "c"), name: str = "decision") -> JevQuestion:
    return JevQuestion(name=name, question_type=JevQuestionType.CHOICE, instructions="Pick one.", options=tuple(JevOption(o) for o in options))


def config(**kwargs: Any) -> DecisionModelConfig:
    kwargs.setdefault("api_key", API_KEY)
    return DecisionModelConfig(**kwargs)


def tool_with(transport: ScriptedTransport, **settings: Any) -> JevDecideTool:
    decision = config()
    return JevDecideTool(settings=JevDecideSettings(decision=decision, **settings), runner=DecisionModelRunner(decision, transport=transport))


def decide_call(**arguments: Any) -> ToolCall:
    arguments.setdefault("question", "Which option fits?")
    arguments.setdefault("options", ["a", "b", "c"])
    return ToolCall(tool_name="jev_decide", arguments=arguments, call_id="c1")


class _Env(unittest.IsolatedAsyncioTestCase):
    """Clears TYPESAFE_API_KEY for every test."""

    def setUp(self) -> None:
        patcher = patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("TYPESAFE_API_KEY", None)
        self.addCleanup(patcher.stop)


class ProviderRegistrationTests(_Env):
    def test_typesafe_is_registered_with_default_model_key_and_endpoint(self) -> None:
        """[Hidden Assumption] the provider maps line up across the registry."""
        self.assertEqual(ModelProvider.TYPESAFE.value, "typesafe")
        self.assertEqual(ProviderModelRegistry.default_model(ModelProvider.TYPESAFE), "jev-latest")
        self.assertEqual(ProviderModelRegistry.get_api_key_env_var(ModelProvider.TYPESAFE), "TYPESAFE_API_KEY")
        self.assertEqual(ProviderModelRegistry.get_default_endpoint(ModelProvider.TYPESAFE), "https://api.typesafe.ai/v1")
        self.assertIn("jev-latest", ProviderModelRegistry.models_for_provider(ModelProvider.TYPESAFE))

    def test_runner_build_refuses_decision_model(self) -> None:
        """[Hidden Assumption] an agent cannot select Jev as its main model."""
        with self.assertRaisesRegex(ConfigurationError, "decision model"):
            Runner(provider="typesafe", model_name="jev-latest").build()

    def test_typesafe_key_never_makes_jev_an_active_text_provider(self) -> None:
        """[Hidden Failure] a set key must not route text work to a decision model."""
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": API_KEY, "OPENAI_API_KEY": "sk-x"}):
            active = ProviderModelRegistry.resolve_active(None, None)
        self.assertNotIn("typesafe", active)

    def test_decision_factory_rejects_other_providers(self) -> None:
        """[Hidden Assumption] the decision factory only builds decision adapters."""
        self.assertIsInstance(ModelProviders.decision(config()), TypeSafeProvider)
        with self.assertRaises(UnsupportedProviderError):
            DecisionModelConfig(provider="openai", api_key=API_KEY)

        class _Openai:
            def normalized_provider(self) -> ModelProvider:
                return ModelProvider.OPENAI

        with self.assertRaises(ProviderSelectionError):
            ModelProviders.decision(_Openai())  # type: ignore[arg-type]


class DecisionConfigTests(_Env):
    def test_rejects_bad_retry_and_timeout(self) -> None:
        """[Edge Case] retry_count must be a non-negative int, timeout positive."""
        for bad in (-1, True, 1.5):
            with self.assertRaises(ConfigurationError):
                DecisionModelConfig(retry_count=bad)  # type: ignore[arg-type]
        for bad in (0, -2.0, "10"):
            with self.assertRaises(ConfigurationError):
                DecisionModelConfig(timeout_seconds=bad)  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            DecisionModelConfig(model="  ")

    def test_missing_key_raises_only_at_validate(self) -> None:
        """[Hidden Assumption] configs build without a key; validate() demands one."""
        cfg = DecisionModelConfig()
        with self.assertRaisesRegex(ConfigurationError, "TYPESAFE_API_KEY"):
            cfg.validate()
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": API_KEY}):
            cfg.validate()


class JevRecordTests(_Env):
    def test_choice_option_count_bounds(self) -> None:
        """[Edge Case] 1 option fails, 255 succeeds, 256 fails."""
        with self.assertRaises(ConfigurationError):
            choice_question(("only",))
        self.assertEqual(len(choice_question(tuple(f"o{i}" for i in range(JEV_MAX_OPTIONS))).options), JEV_MAX_OPTIONS)
        with self.assertRaises(ConfigurationError):
            choice_question(tuple(f"o{i}" for i in range(JEV_MAX_OPTIONS + 1)))

    def test_duplicate_and_blank_options_rejected(self) -> None:
        """[Edge Case] option names are unique and non-blank."""
        with self.assertRaises(ConfigurationError):
            choice_question(("a", "a"))
        with self.assertRaises(ConfigurationError):
            JevOption("   ")

    def test_noul_requires_true_false(self) -> None:
        """[Hidden Assumption] noul questions carry exactly true/false."""
        JevQuestion(name="q", question_type=JevQuestionType.NOUL, instructions="?", options=(JevOption("true"), JevOption("false")))
        with self.assertRaises(ConfigurationError):
            JevQuestion(name="q", question_type=JevQuestionType.NOUL, instructions="?", options=(JevOption("yes"), JevOption("no")))

    def test_request_bounds(self) -> None:
        """[Edge Case] blank state, zero questions, and duplicate names fail."""
        q = choice_question()
        with self.assertRaises(ConfigurationError):
            JevDecisionRequest(state="  ", questions=(q,))
        with self.assertRaises(ConfigurationError):
            JevDecisionRequest(state="s", questions=())
        with self.assertRaises(ConfigurationError):
            JevDecisionRequest(state="s", questions=(q, q))


class TypeSafeProviderTests(_Env):
    async def run_request(self, transport: ScriptedTransport, *questions: JevQuestion, **cfg: Any):
        runner = DecisionModelRunner(config(**cfg), transport=transport)
        return await runner.arun(JevDecisionRequest(state="the state", questions=questions or (choice_question(),)))

    async def test_posts_systemone_with_bearer_auth_and_choice_criteria(self) -> None:
        """[Silent Failure] wrong URL, auth, or criteria shape would still 'work' against a fake."""
        transport = ScriptedTransport(ok(choice_body()))
        question = JevQuestion(name="decision", question_type=JevQuestionType.CHOICE, instructions="Pick.", options=(JevOption("a", "first"), JevOption("b"), JevOption("c")))
        await self.run_request(transport, question)
        sent = transport.requests[0]
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(sent["headers"]["authorization"], f"Bearer {API_KEY}")
        self.assertEqual(sent["timeout_seconds"], 10.0)
        self.assertIn("max_response_bytes", sent)
        self.assertNotIn("retry_count", sent)
        body = sent["json_body"]
        self.assertEqual(body["model"], "jev-latest")
        self.assertEqual(body["state"], "the state")
        self.assertEqual(body["questions"]["decision"], {"type": "choice", "instructions": "Pick.", "criteria": {"a": "first", "b": None, "c": None}})

    async def test_retry_only_when_configured(self) -> None:
        """[Hidden Assumption] retries need an idempotency key and target 429/529 only."""
        transport = ScriptedTransport(ok(choice_body()))
        await self.run_request(transport, retry_count=2)
        sent = transport.requests[0]
        self.assertEqual(sent["retry_count"], 2)
        self.assertEqual(sent["retry_status_codes"], (429, 529))
        self.assertTrue(sent["idempotency_key"])

    async def test_score_criteria_preserve_level_order(self) -> None:
        """[Silent Failure] reordered levels would silently invert a scale."""
        levels = ("low", "mid", "high")
        question = JevQuestion(name="decision", question_type=JevQuestionType.SCORE, instructions="Rate.", options=tuple(JevOption(x) for x in levels))
        transport = ScriptedTransport(ok({"answers": {"decision": {"score": "high", "probabilities": {"low": 0.1, "mid": 0.2, "high": 0.7}, "confidence": 0.7}}, "usage": USAGE}))
        await self.run_request(transport, question)
        self.assertEqual(transport.requests[0]["json_body"]["questions"]["decision"]["criteria"], ["low", "mid", "high"])

    async def test_noul_expands_to_true_false_distribution(self) -> None:
        """[Silent Failure] p(true) must become a two-option distribution with max confidence."""
        question = JevQuestion(name="decision", question_type=JevQuestionType.NOUL, instructions="?", options=(JevOption("true"), JevOption("false")))
        transport = ScriptedTransport(ok({"answers": {"decision": {"noul": 0.2}}, "usage": USAGE}))
        answer = (await self.run_request(transport, question)).answer("decision")
        self.assertEqual(answer.choice, "false")
        self.assertAlmostEqual(answer.probabilities["true"], 0.2)
        self.assertAlmostEqual(answer.probabilities["false"], 0.8)
        self.assertAlmostEqual(answer.confidence, 0.8)

    async def test_score_index_answers_normalize_to_labels(self) -> None:
        """[Hidden Assumption] score may answer with an index and digit-string keys."""
        question = JevQuestion(name="decision", question_type=JevQuestionType.SCORE, instructions="Rate.", options=tuple(JevOption(x) for x in ("low", "mid", "high")))
        transport = ScriptedTransport(ok({"answers": {"decision": {"score": 1, "probabilities": {"0": 0.2, "1": 0.7, "2": 0.1}}}, "usage": USAGE}))
        answer = (await self.run_request(transport, question)).answer("decision")
        self.assertEqual(answer.choice, "mid")
        self.assertEqual(dict(answer.probabilities), {"low": 0.2, "mid": 0.7, "high": 0.1})
        self.assertAlmostEqual(answer.confidence, 0.7)

    async def test_missing_answer_raises_with_usage(self) -> None:
        """[Hidden Failure] a missing answer must raise, and still carry billed usage."""
        transport = ScriptedTransport(ok({"answers": {}, "usage": USAGE}))
        with self.assertRaises(ProviderResponseError) as caught:
            await self.run_request(transport)
        self.assertEqual(caught.exception.details["usage"], USAGE)

    async def test_unknown_choice_raises(self) -> None:
        """[Silent Failure] a label outside the option set must not be accepted."""
        transport = ScriptedTransport(ok(choice_body(choice="zzz")))
        with self.assertRaises(ProviderResponseError):
            await self.run_request(transport)

    async def test_bad_probabilities_raise(self) -> None:
        """[Silent Failure] probabilities outside [0,1] or non-numeric must not pass."""
        for probs in ({"a": 0.1, "b": 1.5, "c": 0.0}, {"a": 0.1, "b": "high", "c": 0.0}):
            transport = ScriptedTransport(ok(choice_body(probabilities=probs, confidence=0.5)))
            with self.assertRaises(ProviderResponseError):
                await self.run_request(transport)
        transport = ScriptedTransport(ok(choice_body(choice="b", probabilities={"a": 0.5, "c": 0.5})))
        with self.assertRaises(ProviderResponseError):
            await self.run_request(transport)

    async def test_auth_failure_is_provider_request_error_with_status(self) -> None:
        """[Hidden Failure] non-2xx responses surface their status code."""
        transport = ScriptedTransport(status(401))
        with self.assertRaises(ProviderRequestError) as caught:
            await self.run_request(transport)
        self.assertEqual(caught.exception.status_code, 401)


class JevUsageTests(_Env):
    def test_parses_and_derives_total(self) -> None:
        """[Edge Case] total is the sum when both counts are reported."""
        usage = JevUsage.from_usage_payload({"input_tokens": 10, "output_tokens": 2})
        self.assertEqual((usage.input_tokens, usage.output_tokens, usage.total_tokens), (10, 2, 12))
        partial = JevUsage.from_usage_payload({"input_tokens": 10})
        self.assertIsNone(partial.total_tokens)

    def test_no_token_fields_is_none(self) -> None:
        """[Edge Case] an empty usage payload is unpriceable, not zero."""
        self.assertIsNone(JevUsage.from_usage_payload({}))
        self.assertIsNone(JevUsage.from_usage_payload({"input_tokens": True}))

    def test_cost_prices_input_only(self) -> None:
        """[Silent Failure] output tokens are free; input is $0.042/M."""
        pricing = ModelPricingRegistry.default().resolve(ModelProvider.TYPESAFE, "jev-latest")
        self.assertIsNotNone(pricing)
        self.assertAlmostEqual(JevUsage.from_usage_payload({"input_tokens": 1_000_000, "output_tokens": 500_000}).cost_usd(pricing), 0.042)
        self.assertEqual(JevUsage.from_usage_payload({"input_tokens": 0, "output_tokens": 999}).cost_usd(pricing), 0.0)

    def test_usage_class_and_tracker_binding(self) -> None:
        """[Hidden Assumption] the tracker resolves TypeSafe to JevUsage and prices it."""
        self.assertIs(ModelProvider.TYPESAFE.usage_class(), JevUsage)
        tracker = UsageTracker()
        record = tracker.record_call(ToolModelCall(provider=ModelProvider.TYPESAFE, model="jev-latest", usage=USAGE))
        self.assertEqual(record.provider, "typesafe")
        self.assertAlmostEqual(record.cost_usd, 1200 * 0.042 / 1_000_000)


class ModelBackedToolTests(_Env):
    def test_model_calls_ignores_malformed_entries(self) -> None:
        """[Hidden Assumption] only ToolModelCall entries reach the ledger."""
        good = ToolModelCall(provider=ModelProvider.TYPESAFE, model="jev-latest", usage=USAGE)
        result = ToolResult.success("t", "x", metadata={"model_usage": (good, {"provider": "typesafe"}, "junk")})
        self.assertEqual(ModelBackedTool.model_calls(result), (good,))
        self.assertEqual(ModelBackedTool.model_calls(ToolResult.success("t", "x", metadata={"model_usage": "nope"})), ())
        self.assertEqual(ModelBackedTool.model_calls(ToolResult.success("t", "x")), ())
        with self.assertRaises(ConfigurationError):
            ToolModelCall(provider="typesafe", model="jev-latest", usage=USAGE)  # type: ignore[arg-type]


class JevDecideToolTests(_Env):
    async def test_invalid_options_rejected_without_network(self) -> None:
        """[Edge Case] 1 option, 256 options, and a non-list never reach TypeSafe."""
        transport = ScriptedTransport()
        tool = tool_with(transport)
        for options in (["only"], [f"o{i}" for i in range(JEV_MAX_OPTIONS + 1)], 7, "not json", [{"description": "no name"}]):
            result = await tool.execute(decide_call(options=options))
            self.assertEqual(result.metadata["error"], "invalid_arguments", options if not isinstance(options, list) else len(options))
        for bad in ({"question": "  "}, {"answer_type": "noul"}):
            result = await tool.execute(decide_call(**bad))
            self.assertEqual(result.metadata["error"], "invalid_arguments")
        self.assertEqual(transport.requests, [])

    async def test_options_as_json_string_or_objects(self) -> None:
        """[Edge Case] both option encodings parse to the same criteria."""
        transport = ScriptedTransport(ok(choice_body()), ok(choice_body()))
        tool = tool_with(transport)
        await tool.execute(decide_call(options=json.dumps(["a", "b", "c"])))
        await tool.execute(decide_call(options=[{"name": "a", "description": "first"}, {"name": "b"}, "c"]))
        self.assertEqual(transport.requests[0]["json_body"]["questions"]["decision"]["criteria"], {"a": None, "b": None, "c": None})
        self.assertEqual(transport.requests[1]["json_body"]["questions"]["decision"]["criteria"], {"a": "first", "b": None, "c": None})

    async def test_blank_state_falls_back_to_question(self) -> None:
        """[Edge Case] a missing state judges the question text itself."""
        transport = ScriptedTransport(ok(choice_body()))
        await tool_with(transport).execute(decide_call(state="   "))
        self.assertEqual(transport.requests[0]["json_body"]["state"], "Which option fits?")

    async def test_renders_full_ranked_distribution(self) -> None:
        """[Silent Failure] the agent must see every option's probability, highest first."""
        transport = ScriptedTransport(ok(choice_body(choice="b", probabilities={"a": 0.25, "b": 0.6, "c": 0.15}, confidence=0.6)))
        result = await tool_with(transport).execute(decide_call(state="evidence"))
        self.assertEqual(result.status.value, "success")
        lines = result.output.splitlines()
        self.assertIn("jev_decide: b", lines[0])
        self.assertEqual(lines[2:5], ["- b: 0.600", "- a: 0.250", "- c: 0.150"])
        self.assertNotIn("below the configured threshold", result.output)
        record = result.metadata["jev_decision"]
        self.assertTrue(record.passed_threshold)
        self.assertIsNone(record.min_confidence)
        self.assertEqual(record.options, ("a", "b", "c"))
        self.assertEqual(len(record.state_sha256), 64)
        self.assertNotIn("evidence", repr(record))

    async def test_below_threshold_is_flagged(self) -> None:
        """[Silent Failure] a low-confidence answer must not read as decided."""
        transport = ScriptedTransport(ok(choice_body(confidence=0.55, probabilities={"a": 0.3, "b": 0.55, "c": 0.15})))
        result = await tool_with(transport, min_confidence=0.8).execute(decide_call())
        self.assertIn("below the configured threshold 0.800", result.output)
        self.assertFalse(result.metadata["jev_decision"].passed_threshold)
        with self.assertRaises(ConfigurationError):
            JevDecideSettings(min_confidence=1.5)

    async def test_missing_key_disables_without_network(self) -> None:
        """[Hidden Assumption] no key means the tool is off, not failing, and stays off."""
        tool = JevDecideTool()
        first = await tool.execute(decide_call())
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": API_KEY}):
            second = await tool.execute(decide_call())
        for result in (first, second):
            self.assertEqual(result.status.value, "error")
            self.assertEqual(result.metadata["error"], "jev_unavailable")
            self.assertIn("Make this judgment yourself", result.output)
            self.assertEqual(ModelBackedTool.model_calls(result), ())

    async def test_401_disables_but_429_does_not(self) -> None:
        """[Hidden Failure] auth failure is sticky; rate limiting is transient."""
        transport = ScriptedTransport(status(429), status(529), ok(choice_body()), status(401))
        tool = tool_with(transport)
        self.assertEqual((await tool.execute(decide_call())).metadata["error"], "jev_rate_limited")
        self.assertEqual((await tool.execute(decide_call())).metadata["error"], "jev_rate_limited")
        self.assertEqual((await tool.execute(decide_call())).status.value, "success")
        self.assertEqual((await tool.execute(decide_call())).metadata["error"], "jev_unauthorized")
        after = await tool.execute(decide_call())
        self.assertEqual(after.metadata["error"], "jev_unavailable")
        self.assertEqual(len(transport.requests), 4)

    async def test_network_error_and_422_fail_open(self) -> None:
        """[Hidden Failure] transport exceptions become tool errors, never raised."""
        transport = ScriptedTransport(ProviderRequestError("boom", provider="http"), status(422), status(500))
        tool = tool_with(transport)
        codes = [(await tool.execute(decide_call())).metadata["error"] for _ in range(3)]
        self.assertEqual(codes, ["jev_request_failed", "jev_invalid_request", "jev_request_failed"])

    async def test_bad_response_is_still_billed(self) -> None:
        """[Silent Failure] a billed call with an unreadable answer must still report usage."""
        transport = ScriptedTransport(ok({"answers": {"decision": {"choice": "nope", "probabilities": {"a": 1.0}}}, "usage": USAGE}))
        result = await tool_with(transport).execute(decide_call())
        self.assertEqual(result.metadata["error"], "jev_bad_response")
        calls = ModelBackedTool.model_calls(result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(dict(calls[0].usage), USAGE)

    async def test_state_is_redacted_before_sending(self) -> None:
        """[Hidden Assumption] credentials and the configured key never leave the process."""
        transport = ScriptedTransport(ok(choice_body()))
        state = f"db password=hunter2 and Authorization: Bearer abc.def and raw {API_KEY} end"
        await tool_with(transport).execute(decide_call(state=state))
        sent = transport.requests[0]["json_body"]["state"]
        for secret in ("hunter2", "abc.def", API_KEY):
            self.assertNotIn(secret, sent)
        self.assertIn("<redacted>", sent)
        self.assertIn("end", sent)

    async def test_on_decision_errors_are_swallowed(self) -> None:
        """[Hidden Failure] a failing observer never fails the tool call."""
        seen: list[object] = []

        def observer(record: object) -> None:
            seen.append(record)
            raise RuntimeError("observer broke")

        decision = config()
        tool = JevDecideTool(settings=JevDecideSettings(decision=decision), runner=DecisionModelRunner(decision, transport=ScriptedTransport(ok(choice_body()))), on_decision=observer)
        result = await tool.execute(decide_call())
        self.assertEqual(result.status.value, "success")
        self.assertEqual(len(seen), 1)

    async def test_api_key_never_in_output_or_metadata(self) -> None:
        """[Silent Failure] the key must not leak through any result surface."""
        for response in (ok(choice_body()), status(401)):
            result = await tool_with(ScriptedTransport(response)).execute(decide_call())
            self.assertNotIn(API_KEY, result.output)
            self.assertNotIn(API_KEY, repr(result.metadata))

    def test_spec_contract(self) -> None:
        """[Edge Case] four parameters, each described in four to five sentences."""
        spec = JevDecideTool().spec()
        self.assertEqual(spec.name, "jev_decide")
        self.assertEqual([p.name for p in spec.parameters], ["question", "options", "state", "answer_type"])
        self.assertEqual(spec.required_parameter_names(), ("question", "options"))
        for text in [spec.description, *(p.description for p in spec.parameters)]:
            sentences = [s for s in text.replace("?", ".").split(". ") if s.strip()]
            self.assertTrue(4 <= len(sentences) <= 5, (len(sentences), text))


class FakeResponse:
    def __init__(self, raw: dict[str, Any], usage: dict[str, Any] | None = None) -> None:
        self.text = ""
        self.raw = raw
        self.provider = "openai"
        self.model = "gpt-5.4-mini"
        self.usage = usage


class ScriptedRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.responses.pop(0)


def function_call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]}


MAIN_USAGE = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}


def two_step_runner() -> ScriptedRunner:
    return ScriptedRunner([
        FakeResponse(function_call("jev_decide", {"question": "Which?", "options": ["a", "b", "c"], "state": "evidence"}, "call_1"), MAIN_USAGE),
        FakeResponse(function_call("isDone", {"final_answer": "done"}, "call_2"), MAIN_USAGE),
    ])


class Purpose(BaseModel):
    purpose: str


class AgentIntegrationTests(_Env):
    async def test_agent_rollup_includes_priced_jev_call(self) -> None:
        """[Silent Failure] without the runtime hook the run succeeds with Jev unbilled."""
        runner = two_step_runner()
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[tool_with(ScriptedTransport(ok(choice_body())))])
        reply = await agent.arun("task")
        self.assertEqual(reply.content, "done")
        usage = agent.get_usage()
        jev = [record for record in usage.calls if record.provider == "typesafe"]
        self.assertEqual(len(jev), 1)
        self.assertAlmostEqual(jev[0].cost_usd, 1200 * 0.042 / 1_000_000)
        self.assertEqual(usage.model_call_count, 3)
        self.assertTrue(usage.cost_complete)
        second_call = json.dumps(runner.calls[1]["kwargs"].get("messages"), default=str)
        self.assertIn("jev_decide: b", second_call)

    async def test_failed_jev_call_completes_run_without_record(self) -> None:
        """[Hidden Failure] a Jev outage leaves the run intact and unbilled."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=two_step_runner(), tools=[tool_with(ScriptedTransport(status(529)))])
        reply = await agent.arun("task")
        self.assertEqual(reply.content, "done")
        self.assertEqual([r for r in agent.get_usage().calls if r.provider == "typesafe"], [])

    async def test_activity_wrapped_tool_is_still_metered(self) -> None:
        """[Hidden Assumption] wrappers are unwrapped before the ModelBackedTool check."""
        wrapped = tool_with(ScriptedTransport(ok(choice_body()))).with_activity(ToolActivity(schema=Purpose, description="Why you are asking.", required=False))
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=two_step_runner(), tools=[wrapped])
        await agent.arun("task")
        self.assertEqual(len([r for r in agent.get_usage().calls if r.provider == "typesafe"]), 1)

    async def test_tracker_error_marks_rollup_corrupted(self) -> None:
        """[Hidden Failure] a metering bug must flag the ledger, not fail the run."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=two_step_runner(), tools=[tool_with(ScriptedTransport(ok(choice_body())))])
        original = UsageTracker.record_call

        def flaky(self: UsageTracker, response: object):
            if isinstance(response, ToolModelCall):
                raise RuntimeError("ledger broke")
            return original(self, response)

        with patch.object(UsageTracker, "record_call", flaky):
            reply = await agent.arun("task")
        self.assertEqual(reply.content, "done")
        self.assertIs(agent.get_usage().recording_integrity, UsageRecordingIntegrity.CORRUPTED)


if __name__ == "__main__":
    unittest.main()
