"""Context Protocol Header

Description:
    Tests for the Reflexion runtime context-window algorithm.
Purpose:
    Validates automatic retry/reflection behavior, prompt overrides, and
    public context-window preset wiring.
"""

from __future__ import annotations

import unittest

from vidbyte import ContextWindow, ReflexionAlgorithm
from vidbyte.agents.algorithms import ReflexionRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.strategies import StrategyResult
from vidbyte.tools import ToolCallContext, ToolCallState, ToolResult, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    return dict(getattr(response, "metadata", {}))


class ReflexionAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    def test_context_window_preset_exposes_single_reflexion_algorithm(self) -> None:
        algorithm = ContextWindow.preset.reflexion

        self.assertEqual(algorithm.name, "reflexion")
        self.assertIsInstance(algorithm.reflexion, ReflexionAlgorithm)
        self.assertFalse(hasattr(ContextWindow.preset, "reflexion_last_attempt"))

    def test_agent_runtime_context_algorithm_dispatcher_detects_reflexion(self) -> None:
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.reflexion,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "reflexion")
        self.assertTrue(dispatcher.is_algorithm("reflexion"))
        self.assertIsInstance(dispatcher.return_algorithm(), ReflexionRuntimeAlgorithm)

    def test_reflexion_algorithm_allows_stage_prompt_overrides(self) -> None:
        algorithm = ReflexionAlgorithm(
            agent_system_prompt="AGENT {system_prompt} {reflections} {previous_attempt}",
            reflect_system_prompt="REFLECT SYSTEM",
            reflect_prompt="REFLECT {task} {failed_attempt} {reflections}",
        )

        self.assertEqual(algorithm.reflection_system_prompt(), "REFLECT SYSTEM")
        self.assertIn("REFLECT task", algorithm.render_reflection_prompt(
            task="task",
            failed_attempt="failed",
            reflections=("memory",),
        ))

    async def test_runtime_reflects_after_failed_trial_and_retries_with_memory(self) -> None:
        @tool
        def lookup() -> str:
            """Look up information."""
            return "not enough"

        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse("Use the lookup result before finishing."),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "fixed"}'}]}),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.reflexion,
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
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.output, "fixed")
        self.assertEqual(len(runner.calls), 3)
        self.assertIn("Failed attempt:", runner.calls[1]["prompt"])
        self.assertIn("Use the lookup result before finishing.", runner.calls[2]["kwargs"]["system"])
        self.assertEqual(result.metadata["reflexion"]["trial_count"], 2)
        self.assertEqual(result.metadata["reflexion"]["reflection_count"], 1)

    def test_format_failed_attempt_includes_tool_context(self) -> None:
        algorithm = ReflexionAlgorithm()
        context_record = ToolCallContext(
            tool_name="lookup",
            state=ToolCallState.FAILED,
            result=ToolResult.error("lookup", "raw result"),
        )

        summary = algorithm.format_failed_attempt(
            StrategyResult(
                output="failed",
                strategy_name="direct_runner",
                metadata={
                    "stop_reason": "max_iterations",
                    "tool_calls": (context_record,),
                },
            )
        )

        self.assertIn("Stop reason: max_iterations", summary)
        self.assertIn("lookup", summary)


if __name__ == "__main__":
    unittest.main()
