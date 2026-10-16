"""Context Protocol Header

Description:
    Tests for the Multi-Provider Agentic Grader context-window algorithm.
Purpose:
    Validates concurrent execution across multiple providers, meta-grading choice parsing,
    API key validation, and failure scenarios.
Architecture:
    - MultiProviderAgenticGraderTests: IsolatedAsyncioTestCase suite testing all aspects of the algorithm.
Key Functions / Test Cases:
    - test_preset_exposes_algorithm_correctly: Validates context window presets exposure.
    - test_dispatcher_detects_and_returns_runtime_grader: Verifies registry and dispatcher linkage.
    - test_single_provider_configured: Validates single active provider fallback.
    - test_empty_or_blank_responses_all_providers: Assures error handling when all endpoints are dead.
    - test_grader_filler_parsing: Assures meta-grader verbatim output matching works correctly.
    - test_grader_keeps_the_winners_structured_output: Assures the selected trial's output_schema instance is returned.
    - test_select_winner_prefers_faithful_match: Assures the grader's exact choice is not overridden by substring candidates.
    - test_grader_prompt_with_an_unknown_placeholder_is_refused_at_construction: Assures an unrenderable grader_prompt fails before any trial.
    - test_grader_prompt_with_escaped_braces_renders_them_literally: Assures {{ }} in grader_prompt renders as literal braces.
    - test_isdone_trials_are_graded_on_their_final_answers: Assures an isDone finish is graded on its final_answer, not its tool-call text.
    - test_direct_agent_grader_runners_carry_its_keys_and_mode: Assures a DIRECT BaseAgent's trial and grader runners get its matched keys and mode.
    - GraderTrialsStayOnTheirProviderTests: Assures a down provider's trial drops out instead of running on the agent's fallback model under its name.
    - ExplicitProviderKeyCheckTests: Assures resolve_active demands a provider's own key only in DIRECT mode, counting a matched key.
Relations:
    Validates MultiProviderAgenticGraderAlgorithm and MultiProviderAgenticGraderRuntimeAlgorithm within the test framework.
Similar Files:
    - tests/test_reflexion_algorithm.py: Parallel verification suite for Reflexion.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch
from typing import Any

from pydantic import BaseModel

from vidbyte import BaseAgent, ContextWindow, ContextWindowAlgorithm, MultiProviderAgenticGraderAlgorithm
from vidbyte.agents import AgentFallback, FallbackModel
from vidbyte.agents.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.enums import TextModelMode
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError, ProviderRequestError
from vidbyte.middleware import ModelRetryMiddleware
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, ProviderKeys
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.config.constants import API_KEY_ENV_VARS
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult

# Dummy, format-valid provider keys; nothing here is a real credential and no request leaves the process.
_DEEPSEEK_TEST_KEY = "sk-test-deepseek"
_GEMINI_TEST_KEY = "AIza" + "t" * 35


class FakeResponse:
    """Mock model response carrier."""

    def __init__(self, text: str, raw: Any = None) -> None:
        # Carrier for mock response text content and an optional provider-native payload.
        self.text = text
        self.raw = raw


class FakeRunner:
    """Mock model runner."""

    def __init__(self, output: str, raw: Any = None) -> None:
        # Initializes a fake runner with specified output.
        self.output = output
        self.raw = raw
        self.calls: list[dict[str, Any]] = []

    async def arun(self, prompt: str, **kwargs: Any) -> FakeResponse:
        # Simulates a runner execution and tracks arguments.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return FakeResponse(self.output, self.raw)


class DownRunner:
    """Mock runner for a provider that is down: every request fails with a fallback-eligible 503."""

    def __init__(self, provider: str) -> None:
        # Records each request so a test can count how often the down provider was tried.
        self.provider = provider
        self.calls: list[dict[str, Any]] = []

    async def arun(self, prompt: str, **kwargs: Any) -> FakeResponse:
        # Fails the way a provider outage reaches the runtime.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        raise ProviderRequestError(f"{self.provider} is down", provider=self.provider, status_code=503)


class ScriptedFallbackChain(AgentFallback):
    """The agent's chain deepseek -> gemini, whose backup is a scripted runner, so no real runner is built."""

    def __init__(self, backup: FakeRunner) -> None:
        super().__init__([FallbackModel(provider="deepseek", model="deepseek-chat"), FallbackModel(provider="gemini", model="gemini-3.5-flash")])
        self.backup = backup

    def build_runner(self, index: int) -> object:
        return self.backup


async def _invoke_runner_helper(runner: Any, prompt: str, **kwargs: Any) -> Any:
    # Awaits the fake runner's arun implementation for test execution.
    return await runner.arun(prompt, **kwargs)


class Ticket(BaseModel):
    """Small output_schema used to check the grader keeps the winner's validated instance."""

    title: str
    urgency: int


class MultiProviderAgenticGraderTests(unittest.IsolatedAsyncioTestCase):
    """Test suite for Multi-Provider Agentic Grader context-window algorithm."""

    def setUp(self) -> None:
        # Setup clean test context before each run.
        self.original_env = dict(os.environ)
        for env_var in API_KEY_ENV_VARS.values():
            os.environ.pop(env_var, None)

    def tearDown(self) -> None:
        # Restore environment variables after each run.
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_preset_exposes_algorithm_correctly(self) -> None:
        # Validates that preset resolves to MultiProviderAgenticGraderAlgorithm correctly.
        preset = ContextWindow.preset.multi_provider_agentic_grader
        self.assertEqual(preset.name, "multi_provider_agentic_grader")
        self.assertIsInstance(preset.multi_provider_agentic_grader, MultiProviderAgenticGraderAlgorithm)

    def test_dispatcher_detects_and_returns_runtime_grader(self) -> None:
        # Ensures dispatcher correctly identifies the grader algorithm.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.multi_provider_agentic_grader,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)
        self.assertEqual(dispatcher.detect_algorithm(), "multi_provider_agentic_grader")
        self.assertTrue(dispatcher.is_algorithm("multi_provider_agentic_grader"))
        self.assertIsInstance(dispatcher.return_algorithm(), MultiProviderAgenticGraderRuntimeAlgorithm)

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_single_provider_configured(self, mock_create_runner: MagicMock) -> None:
        # [Edge Case] Single provider configured: Runs and returns single output properly.
        os.environ["OPENAI_API_KEY"] = "fake-key"
        runner_loop = FakeRunner("candidate output text")
        runner_grader = FakeRunner("candidate output text")
        mock_create_runner.side_effect = [runner_loop, runner_grader]

        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.multi_provider_agentic_grader,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}),
            context=context,
        )

        self.assertEqual(result.output, "candidate output text")
        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["total_runs"], 1)
        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["grader_decision"]["selected_provider"], "openai")

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_empty_or_blank_responses_all_providers(self, mock_create_runner: MagicMock) -> None:
        # [Edge Case] Empty or blank response from all providers: Throws AgentExecutionError.
        os.environ["OPENAI_API_KEY"] = "fake-key"
        mock_create_runner.side_effect = Exception("API connection failure")

        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.multi_provider_agentic_grader,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        with self.assertRaises(AgentExecutionError):
            await runtime.arun(
                "task",
                handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}),
                context=context,
            )

    async def test_missing_api_key_for_explicit_provider(self) -> None:
        # [Hidden Failure] Missing API key for explicitly requested provider: Throws ConfigurationError.
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)

        algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"openai": "gpt-4o"})
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindowAlgorithm(name="multi_provider_agentic_grader", multi_provider_agentic_grader=algorithm),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        # Only a DIRECT agent must hold the provider's own key; the gateway modes can run on the Vidbyte key.
        with self.assertRaises(ConfigurationError) as ctx:
            await runtime.arun(
                "task",
                handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}, model_mode=TextModelMode.DIRECT),
                context=context,
            )
        self.assertIn("Missing API key for explicitly requested provider 'openai'", str(ctx.exception))

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_concurrency_provider_crash(self, mock_create_runner: MagicMock) -> None:
        # [Hidden Failure] Concurrency provider crash: Still works if at least one provider succeeds.
        os.environ["OPENAI_API_KEY"] = "fake-openai-key"
        os.environ["ANTHROPIC_API_KEY"] = "fake-anthropic-key"

        algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"openai": "gpt-4o", "anthropic": "claude-sonnet-5"})
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindowAlgorithm(name="multi_provider_agentic_grader", multi_provider_agentic_grader=algorithm),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        runner_openai = FakeRunner("openai response output")
        runner_grader = FakeRunner("Here is the chosen answer: openai response output")

        def mock_creator(modality: str, provider: str, model: str, **kwargs: Any) -> Any:
            # Side effect function to crash Anthropic and succeed OpenAI/Grader.
            if provider == "anthropic":
                raise Exception("Anthropic crashed")
            if provider == "openai" and model == "gpt-4o" and kwargs.get("grader") is None:
                return runner_openai
            return runner_grader

        mock_create_runner.side_effect = mock_creator

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}),
            context=context,
        )

        self.assertEqual(result.output, "openai response output")
        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["total_runs"], 1)
        self.assertIn("openai", result.metadata["multi_provider_agentic_grader"]["candidates"])
        self.assertNotIn("anthropic", result.metadata["multi_provider_agentic_grader"]["candidates"])

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_grader_filler_parsing(self, mock_create_runner: MagicMock) -> None:
        # [Silent Failure] Grader returns filler or explanation: Extracts exact verbatim candidate output.
        os.environ["OPENAI_API_KEY"] = "fake-key"
        runner_loop = FakeRunner("candidate answer")
        runner_grader = FakeRunner("The best answer out of all candidate outputs is: candidate answer")
        mock_create_runner.side_effect = [runner_loop, runner_grader]

        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.multi_provider_agentic_grader,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}),
            context=context,
        )

        self.assertEqual(result.output, "candidate answer")
        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["grader_decision"]["selected_provider"], "openai")

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_grader_keeps_the_winners_structured_output(self, mock_create_runner: MagicMock) -> None:
        # [Silent Failure] BaseAgent raises OutputSchemaViolationError when structured is None, so the winner's instance must survive.
        os.environ["OPENAI_API_KEY"] = "fake-openai-key"
        os.environ["ANTHROPIC_API_KEY"] = "fake-anthropic-key"
        openai_json = '{"title": "Payment failed", "urgency": 3}'
        anthropic_json = '{"title": "Card declined", "urgency": 2}'
        runners = {
            ("openai", "gpt-4o"): FakeRunner(openai_json),
            ("anthropic", "claude-sonnet-5"): FakeRunner(anthropic_json),
            ("openai", "gpt-4.1-mini"): FakeRunner(anthropic_json),
        }
        mock_create_runner.side_effect = lambda modality, provider, model, **kwargs: runners[(provider, model)]

        algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"openai": "gpt-4o", "anthropic": "claude-sonnet-5"}, grader_model="gpt-4.1-mini")
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindowAlgorithm(name="multi_provider_agentic_grader", multi_provider_agentic_grader=algorithm),
            output_schema=Ticket,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}),
            context=context,
        )

        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["grader_decision"]["selected_provider"], "anthropic")
        self.assertEqual(result.structured, Ticket(title="Card declined", urgency=2))

    async def test_default_execution_with_zero_api_keys(self) -> None:
        # [Hidden Assumption] Default execution with zero API keys: Throws ConfigurationError.
        for provider_enum in API_KEY_ENV_VARS.keys():
            os.environ.pop(API_KEY_ENV_VARS[provider_enum], None)

        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.multi_provider_agentic_grader,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        with self.assertRaises(ConfigurationError) as ctx:
            await runtime.arun(
                "task",
                handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}),
                context=context,
            )
        self.assertIn("No model providers have API keys configured in the environment", str(ctx.exception))

    def test_registry_default_model_invalid_provider(self) -> None:
        # [Edge Case] default_model raises ConfigurationError when queried with an invalid/unregistered provider.
        from vidbyte.lib.registries.models import ProviderModelRegistry
        from unittest.mock import MagicMock

        fake_provider = MagicMock()
        fake_provider.value = "fake_provider_not_registered"

        with self.assertRaises(ConfigurationError) as ctx:
            ProviderModelRegistry.default_model(fake_provider)
        self.assertIn("No default model registered for provider 'fake_provider_not_registered'", str(ctx.exception))

    def test_registry_resolve_active_missing_keys(self) -> None:
        # [Hidden Failure] resolve_active raises ConfigurationError if no API keys are set in the environment.
        from vidbyte.lib.registries.models import ProviderModelRegistry

        for env_var in API_KEY_ENV_VARS.values():
            os.environ.pop(env_var, None)

        with self.assertRaises(ConfigurationError) as ctx:
            ProviderModelRegistry.resolve_active(provider_models=None, options=None)
        self.assertIn("No model providers have API keys configured in the environment", str(ctx.exception))

    def test_registry_resolve_active_environment_uses_text_defaults(self) -> None:
        # [Silent Failure] Environment discovery only activates text defaults for the grader.
        from vidbyte.lib.registries.models import ProviderModelRegistry
        from vidbyte.lib.enums import ModelProvider, ModelModality
        from vidbyte.lib.agents.modality_detector import ModalityDetector

        env_values = {env_var: "fake-key" for env_var in API_KEY_ENV_VARS.values()}
        with patch.dict(os.environ, env_values, clear=False):
            resolved = ProviderModelRegistry.resolve_active(provider_models=None, options=None)

        self.assertNotIn(ModelProvider.ELEVENLABS.value, resolved)
        self.assertNotIn(ModelProvider.PLAYAI.value, resolved)
        for provider_name, model_name in resolved.items():
            modality = ModalityDetector.detect_modality(model_name)
            self.assertEqual(
                modality,
                ModelModality.TEXT,
                f"Resolved model '{model_name}' for provider '{provider_name}' did not resolve to TEXT modality."
            )

    def test_registry_resolve_active_explicit_provider_models(self) -> None:
        # [Hidden Assumption] resolve_active successfully returns explicit provider models, bypassing env checks when credentials supplied.
        from vidbyte.lib.registries.models import ProviderModelRegistry

        explicit_map = {"openai": "gpt-5.5", "anthropic": "claude-sonnet-4-6"}
        os.environ["OPENAI_API_KEY"] = "fake-openai-key"
        os.environ["ANTHROPIC_API_KEY"] = "fake-anthropic-key"

        resolved = ProviderModelRegistry.resolve_active(provider_models=explicit_map, options=None)
        self.assertEqual(resolved, explicit_map)


    def test_select_winner_prefers_faithful_match(self) -> None:
        # [Logic] The grader's exact choice wins over a candidate whose text is a substring of it, in any dict order.
        selector = MultiProviderAgenticGraderRuntimeAlgorithm(MagicMock(), MultiProviderAgenticGraderAlgorithm())
        handle = RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {})
        long_answer = "The answer is 42, because 6 x 7 = 42."
        for candidates in ({"deepseek": "42", "anthropic": long_answer}, {"anthropic": long_answer, "deepseek": "42"}):
            self.assertEqual(selector._select_winner(candidates, FakeResponse(long_answer), handle), (long_answer, "anthropic"))
        # The longest candidate quoted inside grader filler is the most specific match.
        quoted = FakeResponse(f"Best answer: {long_answer}")
        self.assertEqual(selector._select_winner({"deepseek": "42", "anthropic": long_answer}, quoted, handle), (long_answer, "anthropic"))
        # Empty candidates never win, and the shortest candidate containing the grader output is preferred.
        self.assertEqual(selector._select_winner({"openai": "", "deepseek": "42 is it", "anthropic": long_answer}, FakeResponse("42"), handle), ("42 is it", "deepseek"))
        # With no match at all, the grader's own text is returned.
        self.assertEqual(selector._select_winner({"openai": "  ", "deepseek": "7"}, FakeResponse("unrelated"), handle), ("unrelated", "grader_raw"))

    def test_grader_prompt_with_an_unknown_placeholder_is_refused_at_construction(self) -> None:
        # [Hidden Failure] An example JSON object is an unknown {name} to str.format, so it is refused before any trial is paid for.
        with self.assertRaises(ConfigurationError) as ctx:
            MultiProviderAgenticGraderAlgorithm(grader_prompt='{request}\n{candidates}\nReply as JSON like {"winner": "openai"}.')
        self.assertIn('"winner"', str(ctx.exception))

    def test_grader_prompt_with_escaped_braces_renders_them_literally(self) -> None:
        # [Edge Case] Escaped braces construct and reach the grader as a literal JSON example.
        algorithm = MultiProviderAgenticGraderAlgorithm(grader_prompt='{request}\n{candidates}\nReply as JSON like {{"winner": "openai"}}.')
        self.assertEqual(algorithm.render_grader_prompt("task", "cands"), 'task\ncands\nReply as JSON like {"winner": "openai"}.')

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_isdone_trials_are_graded_on_their_final_answers(self, mock_create_runner: MagicMock) -> None:
        # [Silent Failure] A trial that finishes through isDone is graded on its final_answer, not on its tool-call turn's text.
        os.environ["DEEPSEEK_API_KEY"] = "fake-deepseek-key"
        os.environ["GEMINI_API_KEY"] = "fake-gemini-key"
        deepseek_answer = "Canberra (from deepseek)."
        gemini_answer = "Canberra (from gemini)."
        # DeepSeek's OpenAI-compatible wire reads the tool-call arguments JSON as the turn's text; Gemini's reads as empty.
        deepseek_arguments = json.dumps({"final_answer": deepseek_answer})
        runner_deepseek = FakeRunner(deepseek_arguments, raw={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "isDone", "arguments": deepseek_arguments}}]}}]})
        runner_gemini = FakeRunner("", raw={"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "isDone", "args": {"final_answer": gemini_answer}}}]}}]})
        runner_grader = FakeRunner(gemini_answer)
        mock_create_runner.side_effect = lambda modality, provider, model, **kwargs: {"deepseek": runner_deepseek, "gemini": runner_gemini}.get(provider, runner_grader)

        algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"deepseek": "deepseek-chat", "gemini": "gemini-3.5-flash"}, grader_provider="openai", grader_model="gpt-4o")
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindowAlgorithm(name="multi_provider_agentic_grader", multi_provider_agentic_grader=algorithm),
        )
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=FakeRunner("ignored"), provider="openai", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {}),
            context=context,
        )

        grader_metadata = result.metadata["multi_provider_agentic_grader"]
        self.assertEqual(grader_metadata["candidates"], {"deepseek": deepseek_answer, "gemini": gemini_answer})
        self.assertIn(deepseek_answer, runner_grader.calls[0]["prompt"])
        self.assertIn(gemini_answer, runner_grader.calls[0]["prompt"])
        self.assertEqual(grader_metadata["grader_decision"]["selected_provider"], "gemini")
        self.assertEqual(result.output, gemini_answer)

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_direct_agent_grader_runners_carry_its_keys_and_mode(self, mock_create_runner: MagicMock) -> None:
        # [Silent Failure] A child runner built without the agent's keys and mode falls back to AUTO and bills the Vidbyte gateway.
        runners = {"deepseek": FakeRunner("Canberra (from deepseek)."), "gemini": FakeRunner("Canberra (from gemini).")}
        grader_runner = FakeRunner("Canberra (from gemini).")
        mock_create_runner.side_effect = lambda modality, provider, model, **kwargs: grader_runner if model == "deepseek-v4-pro" else runners[provider]
        keys = ProviderKeys(providers=("deepseek", "gemini"), keys=(_DEEPSEEK_TEST_KEY, _GEMINI_TEST_KEY))
        algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"deepseek": "deepseek-chat", "gemini": "gemini-3.5-flash"}, grader_provider="deepseek", grader_model="deepseek-v4-pro")
        # No provider variable is set, so the agent's api_keys are the only keys there are.
        agent = BaseAgent(name="worker", system_prompt="Work.", provider="deepseek", model_name="deepseek-chat", api_keys=keys, model_mode=TextModelMode.DIRECT, max_iterations=1, algorithm=ContextWindowAlgorithm(name="multi_provider_agentic_grader", multi_provider_agentic_grader=algorithm))

        result = await agent.arun("Capital of Australia?")

        self.assertEqual(result.content, "Canberra (from gemini).")
        self.assertEqual(sorted((call.kwargs["provider"], call.kwargs["model"]) for call in mock_create_runner.call_args_list), [("deepseek", "deepseek-chat"), ("deepseek", "deepseek-v4-pro"), ("gemini", "gemini-3.5-flash")])
        for call in mock_create_runner.call_args_list:
            self.assertIs(call.kwargs["api_keys"], agent.runner_config.api_keys)
            self.assertIs(call.kwargs["mode"], TextModelMode.DIRECT)


class GraderTrialsStayOnTheirProviderTests(unittest.IsolatedAsyncioTestCase):
    """A trial stands for one provider, so the agent's fallback chain never answers in a down provider's name."""

    DEEPSEEK_ANSWER = "Canberra (from deepseek)."
    GEMINI_ANSWER = "Canberra (from gemini)."

    def setUp(self) -> None:
        # Hide every provider variable; the gateway mode needs no provider key and no request leaves the process.
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for env_var in API_KEY_ENV_VARS.values():
            os.environ.pop(env_var, None)
        self.deepseek = DownRunner("deepseek")
        self.gemini = FakeRunner(self.GEMINI_ANSWER)
        # The agent's backup is the same Gemini model the grader compares, so it writes the same answer.
        self.backup = FakeRunner(self.GEMINI_ANSWER)
        self.grader = FakeRunner(self.GEMINI_ANSWER)

    def _runtime(self, *, algorithm: ContextWindowAlgorithm | None = None, middleware: tuple[Any, ...] = (), fallback: AgentFallback | None = None) -> AgentRuntime:
        # A one-iteration runtime for an agent whose primary is deepseek.
        return AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), config=AgentRuntimeConfig(max_iterations=1), algorithm=algorithm, middleware=middleware, fallback=fallback)

    def _handle(self, runner: Any) -> RunnerHandle:
        return RunnerHandle(runner=runner, provider="deepseek", invoke=_invoke_runner_helper, extract_text=lambda r: getattr(r, "text", str(r)), extract_metadata=lambda r: {})

    async def _grade_with_deepseek_down(self) -> tuple[StrategyResult, AgentRuntime]:
        # The agent declares deepseek -> gemini; the grader compares deepseek and gemini and deepseek answers 503.
        algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"deepseek": "deepseek-chat", "gemini": "gemini-3.5-flash"}, grader_provider="openai", grader_model="gpt-4.1-mini")
        runtime = self._runtime(algorithm=ContextWindowAlgorithm(name="multi_provider_agentic_grader", multi_provider_agentic_grader=algorithm), fallback=ScriptedFallbackChain(self.backup))
        runners = {"deepseek": self.deepseek, "gemini": self.gemini, "openai": self.grader}
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        with patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner", side_effect=lambda modality, provider, model, **kwargs: runners[provider]):
            result = await runtime.arun("task", handle=self._handle(FakeRunner("ignored")), context=context)
        return result, runtime

    async def test_down_provider_drops_out_instead_of_running_on_the_fallback_model(self) -> None:
        # [Silent Failure] The deepseek trial failed over to Gemini, so Gemini's text was stored and graded as deepseek's.
        result, runtime = await self._grade_with_deepseek_down()

        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["candidates"], {"gemini": self.GEMINI_ANSWER})
        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["total_runs"], 1)
        # The down provider was tried once and its trial never reached the agent's backup model.
        self.assertEqual(len(self.deepseek.calls), 1)
        self.assertEqual(self.backup.calls, [])
        # No model switch happened, so none is reported and none is remembered for the rest of the run.
        self.assertNotIn("fallback", result.metadata)
        self.assertIsNone(runtime._fallback_handle)
        self.assertEqual(runtime._fallback_progress, (0, [], [], False))

    async def test_healthy_provider_keeps_its_candidate_and_wins(self) -> None:
        # [Silent Failure] With Gemini's text under both names, the grader's pick was reported as the down provider.
        result, _ = await self._grade_with_deepseek_down()

        grader_metadata = result.metadata["multi_provider_agentic_grader"]
        self.assertEqual(grader_metadata["candidates"]["gemini"], self.GEMINI_ANSWER)
        self.assertEqual(grader_metadata["grader_decision"]["selected_provider"], "gemini")
        self.assertEqual(result.output, self.GEMINI_ANSWER)
        self.assertEqual(len(self.gemini.calls), 1)

    async def test_pinned_run_reraises_the_provider_error_and_leaves_the_chain_untouched(self) -> None:
        runtime = self._runtime(fallback=ScriptedFallbackChain(self.backup))
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        with self.assertRaises(ProviderRequestError):
            await runtime._arun_once("task", handle=self._handle(self.deepseek), context=context, pin_model=True)

        self.assertEqual(self.backup.calls, [])
        self.assertIsNone(runtime._fallback_handle)
        self.assertEqual(runtime._fallback_progress, (0, [], [], False))

    async def test_pinned_run_stops_on_a_spent_retry_budget_like_an_agent_without_a_chain(self) -> None:
        # A spent retry budget only hands the error to the chain when the run may switch; a pinned run keeps the abort result.
        results = []
        for fallback in (None, ScriptedFallbackChain(self.backup)):
            runtime = self._runtime(middleware=(ModelRetryMiddleware(max_attempts=1),), fallback=fallback)
            context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
            results.append(await runtime._arun_once("task", handle=self._handle(self.deepseek), context=context, pin_model=True))

        without_chain, pinned = results
        self.assertEqual(pinned.metadata["middleware_abort_reason"], "model_retry_exhausted")
        self.assertEqual((pinned.output, pinned.metadata["stop_reason"]), (without_chain.output, without_chain.metadata["stop_reason"]))
        self.assertEqual(self.backup.calls, [])

    async def test_unpinned_run_still_fails_over(self) -> None:
        # An ordinary run is unaffected: the same outage switches to the backup and reports the switch.
        runtime = self._runtime(fallback=ScriptedFallbackChain(self.backup))
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime._arun_once("task", handle=self._handle(self.deepseek), context=context)

        self.assertEqual(len(self.deepseek.calls), 1)
        self.assertEqual(len(self.backup.calls), 1)
        self.assertEqual(result.metadata["fallback"]["final_model"], "gemini/gemini-3.5-flash")
        self.assertIsNotNone(runtime._fallback_handle)


class ExplicitProviderKeyCheckTests(unittest.TestCase):
    """resolve_active demands a provider's own key only when the agent calls providers directly."""

    PROVIDER_MODELS = {"deepseek": "deepseek-chat", "gemini": "gemini-3.5-flash"}

    def setUp(self) -> None:
        # Hide every provider variable, so only the agent's matched keys can count.
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for env_var in API_KEY_ENV_VARS.values():
            os.environ.pop(env_var, None)

    def test_direct_counts_a_key_matched_into_api_keys(self) -> None:
        keys = ProviderKeys(providers=("deepseek", "gemini"), keys=(_DEEPSEEK_TEST_KEY, _GEMINI_TEST_KEY))
        active = ProviderModelRegistry.resolve_active(self.PROVIDER_MODELS, None, api_keys=keys, model_mode=TextModelMode.DIRECT)
        self.assertEqual(active, self.PROVIDER_MODELS)

    def test_direct_without_a_key_for_a_provider_still_raises(self) -> None:
        # The deepseek key must not stand in for gemini: a key reaches only the provider it was matched to.
        keys = ProviderKeys(providers=("deepseek",), keys=(_DEEPSEEK_TEST_KEY,))
        with self.assertRaises(ConfigurationError) as ctx:
            ProviderModelRegistry.resolve_active(self.PROVIDER_MODELS, None, api_keys=keys, model_mode=TextModelMode.DIRECT)
        self.assertIn("Missing API key for explicitly requested provider 'gemini'", str(ctx.exception))

    def test_gateway_modes_need_no_provider_key(self) -> None:
        for mode in (TextModelMode.AUTO, TextModelMode.VIDBYTE_MANAGED):
            with self.subTest(mode=mode):
                self.assertEqual(ProviderModelRegistry.resolve_active(self.PROVIDER_MODELS, None, model_mode=mode), self.PROVIDER_MODELS)


if __name__ == "__main__":
    unittest.main()

