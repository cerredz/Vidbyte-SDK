"""FILE: tests/test_jev_agent.py

PURPOSE: Verifies the TypeSafe decision substrate and the first opinionated JevAgent scaffold without network access.
ROLE IN CODEBASE: Covers docs/design/jev-agent-scaffold.md section 10, including settings, runtime wiring, provider normalization, public exports, and ordinary loop behavior.
ARCHITECTURE NOTE: Scripted transports and runners replace only external model boundaries; production constructors and runtime factories remain under test.
COMMON MODIFICATION PATTERNS: Add cases here whenever a named Jev capability changes settings, runtime policy, fallback behavior, or observability.
KNOWN EDGE CASES: TYPESAFE_API_KEY is cleared where credential timing is tested, and no test may send a live provider request.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_agent.py and python scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import inspect
import json
import os
import unittest
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent as RootJevAgent
from vidbyte import JevAgentSettings as RootJevAgentSettings
from vidbyte import JevRuntime as RootJevRuntime
from vidbyte import VidbyteSDK, tool
from vidbyte.agents import BaseAgent
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevRuntime
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevOption, JevQuestion
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.runners import DecisionModelRunner, TextModelResponse
from vidbyte.tools.security import PermissionPolicy

API_KEY = "typesafe-test-key"


class ScriptedTransport:
    """Records one request and returns scripted HTTP responses."""

    def __init__(self, *responses: HttpResponse) -> None:
        # Retains deterministic provider responses and all outbound arguments.
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Records the request before returning the next response.
        self.requests.append(kwargs)
        return self.responses.pop(0)


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


def _response(body: dict[str, Any]) -> HttpResponse:
    # Encodes one successful fake HTTP response.
    return HttpResponse(status_code=200, body=json.dumps(body), headers={})


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
        transport = ScriptedTransport(_response({
            "model": "jev-latest",
            "answers": {"decision": {"choice": "b", "probabilities": {"a": 0.1, "b": 0.7, "c": 0.2}, "confidence": 0.7}},
            "usage": {"input_tokens": 12, "output_tokens": 1},
        }))
        config = DecisionModelConfig(api_key=API_KEY)
        result = await DecisionModelRunner(config, transport=transport).arun(JevDecisionRequest(state="state", questions=(_question(),)))
        self.assertEqual(result.answer("decision").choice, "b")
        self.assertEqual(dict(result.answer("decision").probabilities), {"a": 0.1, "b": 0.7, "c": 0.2})
        self.assertEqual(transport.requests[0]["json_body"]["state"], "state")

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
        # [Hidden Assumption] the protected hooks are behavior-preserving for every ordinary agent.
        agent = BaseAgent(name="base", system_prompt="Work.", provider="openai", model_name="gpt-4.1-mini")
        runtime = agent._runtime()
        self.assertIs(type(runtime), AgentRuntime)

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
        self.assertIs(RootJevAgentSettings, JevAgentSettings)
        self.assertIs(RootJevRuntime, JevRuntime)

    def test_sdk_namespace_constructs_jev_agent(self) -> None:
        # [Silent Failure] the root namespace client exposes the opinionated constructor.
        settings = _settings()
        agent = VidbyteSDK().agents.jev(settings)
        self.assertIsInstance(agent, JevAgent)
        self.assertIs(agent.settings, settings)

    def test_constructor_exposes_only_settings(self) -> None:
        # [Hidden Assumption] runtime machinery and generic decisions are not user customization points.
        parameters = tuple(inspect.signature(JevAgent.__init__).parameters)
        self.assertEqual(parameters, ("self", "settings"))
        for forbidden in ("runtime", "middleware", "algorithm", "fallback", "decisions"):
            self.assertNotIn(forbidden, parameters)


if __name__ == "__main__":
    unittest.main()
