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
Relations:
    Validates MultiProviderAgenticGraderAlgorithm and MultiProviderAgenticGraderRuntimeAlgorithm within the test framework.
Similar Files:
    - tests/test_reflexion_algorithm.py: Parallel verification suite for Reflexion.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from typing import Any

from vidbyte import ContextWindow, ContextWindowAlgorithm, MultiProviderAgenticGraderAlgorithm
from vidbyte.agents.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.config.constants import API_KEY_ENV_VARS
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult


class FakeResponse:
    """Mock model response carrier."""

    def __init__(self, text: str) -> None:
        # Carrier for mock response text content.
        self.text = text


class FakeRunner:
    """Mock model runner."""

    def __init__(self, output: str) -> None:
        # Initializes a fake runner with specified output.
        self.output = output
        self.calls: list[dict[str, Any]] = []

    async def arun(self, prompt: str, **kwargs: Any) -> FakeResponse:
        # Simulates a runner execution and tracks arguments.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return FakeResponse(self.output)


async def _invoke_runner_helper(runner: Any, prompt: str, **kwargs: Any) -> Any:
    # Awaits the fake runner's arun implementation for test execution.
    return await runner.arun(prompt, **kwargs)


class MultiProviderAgenticGraderTests(unittest.IsolatedAsyncioTestCase):
    """Test suite for Multi-Provider Agentic Grader context-window algorithm."""

    def setUp(self) -> None:
        # Setup clean test context before each run.
        self.original_env = dict(os.environ)

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
            runner=FakeRunner("ignored"),
            context=context,
            provider="openai",
            invoke_runner=_invoke_runner_helper,
            runner_output_text=lambda r: getattr(r, "text", str(r)),
            runner_output_metadata=lambda r: {},
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
                runner=FakeRunner("ignored"),
                context=context,
                provider="openai",
                invoke_runner=_invoke_runner_helper,
                runner_output_text=lambda r: getattr(r, "text", str(r)),
                runner_output_metadata=lambda r: {},
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

        with self.assertRaises(ConfigurationError) as ctx:
            await runtime.arun(
                "task",
                runner=FakeRunner("ignored"),
                context=context,
                provider="openai",
                invoke_runner=_invoke_runner_helper,
                runner_output_text=lambda r: getattr(r, "text", str(r)),
                runner_output_metadata=lambda r: {},
            )
        self.assertIn("Missing API key for explicitly requested provider 'openai'", str(ctx.exception))

    @patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner")
    async def test_concurrency_provider_crash(self, mock_create_runner: MagicMock) -> None:
        # [Hidden Failure] Concurrency provider crash: Still works if at least one provider succeeds.
        os.environ["OPENAI_API_KEY"] = "fake-openai-key"
        os.environ["ANTHROPIC_API_KEY"] = "fake-anthropic-key"

        algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"openai": "gpt-4o", "anthropic": "claude-3"})
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
            runner=FakeRunner("ignored"),
            context=context,
            provider="openai",
            invoke_runner=_invoke_runner_helper,
            runner_output_text=lambda r: getattr(r, "text", str(r)),
            runner_output_metadata=lambda r: {},
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
            runner=FakeRunner("ignored"),
            context=context,
            provider="openai",
            invoke_runner=_invoke_runner_helper,
            runner_output_text=lambda r: getattr(r, "text", str(r)),
            runner_output_metadata=lambda r: {},
        )

        self.assertEqual(result.output, "candidate answer")
        self.assertEqual(result.metadata["multi_provider_agentic_grader"]["grader_decision"]["selected_provider"], "openai")

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
                runner=FakeRunner("ignored"),
                context=context,
                provider="openai",
                invoke_runner=_invoke_runner_helper,
                runner_output_text=lambda r: getattr(r, "text", str(r)),
                runner_output_metadata=lambda r: {},
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

    def test_registry_all_default_models_are_valid_text_modality(self) -> None:
        # [Silent Failure] All default provider models are valid text models that map to ModelModality.TEXT.
        from vidbyte.lib.registries.models import ProviderModelRegistry
        from vidbyte.lib.enums import ModelProvider, ModelModality
        from vidbyte.lib.agents.modality_detector import ModalityDetector

        for provider in ModelProvider:
            model_name = ProviderModelRegistry.default_model(provider)
            modality = ModalityDetector.detect_modality(model_name)
            self.assertEqual(
                modality,
                ModelModality.TEXT,
                f"Default model '{model_name}' for provider '{provider.value}' did not resolve to TEXT modality."
            )

    def test_registry_resolve_active_explicit_provider_models(self) -> None:
        # [Hidden Assumption] resolve_active successfully returns explicit provider models, bypassing env checks when credentials supplied.
        from vidbyte.lib.registries.models import ProviderModelRegistry

        explicit_map = {"openai": "gpt-5.5", "anthropic": "claude-sonnet-4-6"}
        os.environ["OPENAI_API_KEY"] = "fake-openai-key"
        os.environ["ANTHROPIC_API_KEY"] = "fake-anthropic-key"

        resolved = ProviderModelRegistry.resolve_active(provider_models=explicit_map, options=None)
        self.assertEqual(resolved, explicit_map)


if __name__ == "__main__":
    unittest.main()

