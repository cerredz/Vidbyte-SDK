"""Context Protocol Header

Description:
    Tests for the Adversarial Reflection context-window algorithm.
Purpose:
    Validates public API wiring, scheduling cadence, context injection, and
    runtime metadata for scheduled adversarial critique.
"""

from __future__ import annotations

import unittest

from vidbyte import AdversarialAgentTool, AdversarialReflectionAlgorithm, ContextWindow, ContextWindowAlgorithm
from vidbyte.agents.algorithms import AdversarialReflectionRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools import BaseTool, ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec, Tools
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        # Store fake provider text and raw payload for tool parsing.
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        # Store queued responses and every invocation for assertions.
        self.responses = list(responses)
        self.calls: list[dict] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    # Simulate provider invocation and record prompt options.
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    # Extract fake response text the same way provider adapters do.
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    # Return fake provider metadata for runtime result assembly.
    return dict(getattr(response, "metadata", {}))


class AdversarialReflectionAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    def test_preset_exposes_adversarial_reflection_algorithm(self) -> None:
        # Verifies preset and string resolution expose the public algorithm config.
        preset = ContextWindow.preset.adversarial_reflection

        self.assertEqual(preset.name, "adversarial_reflection")
        self.assertIsInstance(preset.adversarial_reflection, AdversarialReflectionAlgorithm)
        self.assertEqual(ContextWindow.resolve_algorithm("adversarial_reflection").name, "adversarial_reflection")

    def test_context_window_algorithm_rejects_multiple_runtime_algorithms(self) -> None:
        # Verifies runtime algorithms remain mutually exclusive.
        with self.assertRaises(ValueError):
            ContextWindowAlgorithm(
                name="bad",
                reflexion=ContextWindow.preset.reflexion.reflexion,
                adversarial_reflection=AdversarialReflectionAlgorithm(),
            )

    def test_algorithm_validation_edges(self) -> None:
        # Verifies numeric and metadata validation edge cases.
        with self.assertRaises(ConfigurationError):
            AdversarialReflectionAlgorithm(interval_iterations=0)
        with self.assertRaises(ConfigurationError):
            AdversarialReflectionAlgorithm(max_critiques=-1)
        with self.assertRaises(ConfigurationError):
            AdversarialReflectionAlgorithm(max_critique_chars=0)
        with self.assertRaises(ConfigurationError):
            AdversarialReflectionAlgorithm(metadata={1: "bad"})  # type: ignore[dict-item]

        self.assertFalse(AdversarialReflectionAlgorithm(max_critiques=0).should_run_critique(iteration_count=1, critique_count=0, terminal=False))

    def test_algorithm_prompt_and_truncation_silent_failures(self) -> None:
        # Verifies prompt placeholders and truncation bounds avoid silent wrong output.
        with self.assertRaises(ConfigurationError):
            AdversarialReflectionAlgorithm(adversarial_prompt="{task} only")

        algorithm = AdversarialReflectionAlgorithm(interval_iterations=3, max_critique_chars=25)
        self.assertFalse(algorithm.should_run_critique(iteration_count=2, critique_count=0, terminal=False))
        self.assertTrue(algorithm.should_run_critique(iteration_count=3, critique_count=0, terminal=False))
        self.assertFalse(algorithm.should_run_critique(iteration_count=3, critique_count=0, terminal=True))
        self.assertLessEqual(len(algorithm.capture_critique("x" * 100)), 25)

    def test_dispatcher_detects_and_returns_adversarial_runtime(self) -> None:
        # Verifies dispatcher links the public preset to the runtime adapter.
        runtime = _runtime(ContextWindow.preset.adversarial_reflection, max_iterations=1)
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "adversarial_reflection")
        self.assertTrue(dispatcher.is_algorithm("adversarial_reflection"))
        self.assertIsInstance(dispatcher.return_algorithm(), AdversarialReflectionRuntimeAlgorithm)

    async def test_runtime_injects_scheduled_critique_into_later_context(self) -> None:
        # Verifies scheduled critique appears in later model-visible context.
        tool = AdversarialAgentTool(critique=lambda args: "The worker is not checking assumptions.")
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=2, max_critiques=1, adversarial_tool=tool))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("draft 2"), FakeResponse("draft 3")])
        runtime = _runtime(algorithm, max_iterations=3)
        context = _context(runtime)

        result = await runtime.arun("task", runner=runner, context=context, provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertIn("adversarial_critique", runner.calls[2]["kwargs"]["system"])
        self.assertIn("not checking assumptions", runner.calls[2]["kwargs"]["system"])
        self.assertNotIn("role': 'tool'", str(runner.calls[2]["kwargs"].get("messages", ())))
        self.assertEqual(result.metadata["adversarial_reflection"]["critique_count"], 1)
        self.assertEqual(result.metadata["context_window_algorithm"], "adversarial_reflection")
        self.assertEqual(result.metadata["stop_reason"], "max_iterations")
        self.assertIn("Work carefully.", runner.calls[2]["kwargs"]["system"])

    async def test_runtime_with_max_critiques_zero_never_calls_tool(self) -> None:
        # Verifies critique scheduling can be disabled without changing normal runtime behavior.
        calls: list[object] = []
        tool = AdversarialAgentTool(critique=lambda args: calls.append(args) or "critique")
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=0, adversarial_tool=tool))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("draft 2")])
        runtime = _runtime(algorithm, max_iterations=2)

        result = await runtime.arun("task", runner=runner, context=_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(calls, [])
        self.assertEqual(result.metadata["adversarial_reflection"]["critique_count"], 0)

    async def test_runtime_with_interval_one_runs_after_first_nonterminal_iteration(self) -> None:
        # Verifies the smallest valid interval schedules immediately after one iteration.
        calls: list[object] = []
        tool = AdversarialAgentTool(critique=lambda args: calls.append(args) or "critique after first")
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1, adversarial_tool=tool))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("draft 2")])
        runtime = _runtime(algorithm, max_iterations=2)

        await runtime.arun("task", runner=runner, context=_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(len(calls), 1)
        self.assertIn("critique after first", runner.calls[1]["kwargs"]["system"])

    async def test_runtime_records_failed_adversarial_tool_and_continues(self) -> None:
        # Verifies failed scheduled critique is auditable and does not crash the main loop.
        def fail(_: object) -> str:
            raise RuntimeError("critic failed")

        tool = AdversarialAgentTool(critique=fail)
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1, adversarial_tool=tool))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("draft 2")])
        runtime = _runtime(algorithm, max_iterations=2)

        result = await runtime.arun("task", runner=runner, context=_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertIn("critic failed", runner.calls[1]["kwargs"]["system"])
        self.assertEqual(result.metadata["adversarial_reflection"]["checkpoints"][0]["status"], "error")

    async def test_scheduled_tool_permission_denial_records_denied_context(self) -> None:
        # Verifies scheduled custom tool still goes through permission policy.
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1, adversarial_tool=WriteCritiqueTool()))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("draft 2")])
        runtime = _runtime(algorithm, max_iterations=2)

        result = await runtime.arun("task", runner=runner, context=_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(result.metadata["tool_calls"][0].state.value, "denied")
        self.assertIn("Permission denied", runner.calls[1]["kwargs"]["system"])

    async def test_runtime_does_not_mutate_original_context(self) -> None:
        # Verifies scheduled injection replaces context instead of mutating the caller's context.
        tool = AdversarialAgentTool(critique=lambda args: "critique")
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1, adversarial_tool=tool))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("draft 2")])
        runtime = _runtime(algorithm, max_iterations=2)
        context = _context(runtime)

        await runtime.arun("task", runner=runner, context=context, provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(context.tool_calls, ())

    async def test_runtime_uses_fresh_options_per_iteration(self) -> None:
        # Verifies runtime copies caller options and does not mutate supplied message options.
        tool = AdversarialAgentTool(critique=lambda args: "critique")
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1, adversarial_tool=tool))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("draft 2")])
        runtime = _runtime(algorithm, max_iterations=2)
        options = {"messages": ({"role": "user", "content": "existing"},)}

        await runtime.arun("task", runner=runner, context=_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata, options=options)

        self.assertIn("messages", options)
        self.assertEqual(options["messages"][0]["content"], "existing")

    async def test_runtime_skips_critique_after_is_done(self) -> None:
        # Verifies terminal isDone responses do not schedule trailing critique.
        calls: list[object] = []
        tool = AdversarialAgentTool(critique=lambda args: calls.append(args) or "critique")
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1, adversarial_tool=tool))
        runner = FakeRunner([FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]})])
        runtime = _runtime(algorithm, max_iterations=5)

        result = await runtime.arun("task", runner=runner, context=_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(result.output, "done")
        self.assertEqual(calls, [])

    async def test_default_internal_tool_uses_adversarial_prompt_assets(self) -> None:
        # Verifies default scheduled critique uses prompt assets and injects its output.
        algorithm = ContextWindowAlgorithm(name="adversarial_reflection", adversarial_reflection=AdversarialReflectionAlgorithm(interval_iterations=1, max_critiques=1))
        runner = FakeRunner([FakeResponse("draft 1"), FakeResponse("asset critique"), FakeResponse("draft 2")])
        runtime = _runtime(algorithm, max_iterations=2)

        await runtime.arun("task", runner=runner, context=_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertIn("Original task:", runner.calls[1]["prompt"])
        self.assertIn("Adversarial Critic", runner.calls[1]["kwargs"]["system"])
        self.assertIn("asset critique", runner.calls[2]["kwargs"]["system"])


class WriteCritiqueTool(BaseTool):
    def spec(self) -> ToolSpec:
        # Return a WRITE permission spec to trigger default permission denial.
        return ToolSpec(
            name="adversarial_critique",
            description="Requires write permission.",
            parameters=(
                ToolParameter("task", "str", "Task."),
                ToolParameter("trajectory", "str", "Trajectory."),
                ToolParameter("iteration_count", "int", "Iteration."),
                ToolParameter("critique_count", "int", "Critique count."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return a result that should never execute under default permissions.
        return ToolResult.success(call.tool_name, "should not execute")


def _runtime(algorithm: ContextWindowAlgorithm, *, max_iterations: int) -> AgentRuntime:
    # Build a minimal runtime for direct-loop adversarial tests.
    return AgentRuntime(agent_name="worker", system_prompt="Work carefully.", tools=Tools(), permission_policy=PermissionPolicy(), config=AgentRuntimeConfig(max_iterations=max_iterations), algorithm=algorithm)


def _context(runtime: AgentRuntime):
    # Build the direct runner context used by runtime tests.
    return runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())


if __name__ == "__main__":
    unittest.main()
