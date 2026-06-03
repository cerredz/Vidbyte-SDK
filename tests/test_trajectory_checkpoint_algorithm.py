from __future__ import annotations

import unittest
from typing import Any

from vidbyte import ContextWindow, ContextWindowAlgorithm, ContextWindowPlacement, ReflexionAlgorithm, TrajectoryCheckpointAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.templates import ContextWindowRecorder
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.templates import TrajectoryCheckpointContextWindowTemplate
from vidbyte.tools import ToolCallContext, ToolCallState, ToolResult, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: Any) -> FakeResponse:
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    return {}


def base_context() -> BaseAgentContext:
    return BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)


def is_done_response(final_answer: str = "done") -> FakeResponse:
    return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "{final_answer}"}}'}]})


def tool_response(name: str = "lookup") -> FakeResponse:
    return FakeResponse("", {"output": [{"type": "function_call", "name": name, "arguments": "{}"}]})


class ToolRecordingTrajectoryAlgorithm(TrajectoryCheckpointAlgorithm):
    def after_tool_calls(self, ctx) -> None:
        # Records the latest observed tool result output from the iteration snapshot.
        super().after_tool_calls(ctx)
        if ctx.iteration is not None and ctx.iteration.tool_calls:
            latest = ctx.iteration.tool_calls[-1]
            if latest.result is not None:
                ctx.set_metadata("tool_seen", latest.result.output)


class TrajectoryCheckpointAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    def test_preset_exposes_trajectory_checkpoint_algorithm(self) -> None:
        preset = ContextWindow.preset.trajectory_checkpoints

        self.assertEqual(preset.name, "trajectory_checkpoints")
        self.assertIsInstance(preset.trajectory_checkpoints, TrajectoryCheckpointAlgorithm)

    def test_resolve_algorithm_accepts_trajectory_checkpoints_string(self) -> None:
        resolved = ContextWindow.resolve_algorithm("trajectory_checkpoints")

        self.assertEqual(resolved.name, "trajectory_checkpoints")
        self.assertIsInstance(resolved.trajectory_checkpoints, TrajectoryCheckpointAlgorithm)

    def test_config_rejects_zero_interval(self) -> None:
        with self.assertRaises(ConfigurationError):
            TrajectoryCheckpointAlgorithm(interval=0)

    def test_config_rejects_empty_checkpoint_title(self) -> None:
        with self.assertRaises(ConfigurationError):
            TrajectoryCheckpointAlgorithm(checkpoint_title=" ")

    def test_config_rejects_non_string_metadata_key(self) -> None:
        with self.assertRaises(ConfigurationError):
            TrajectoryCheckpointAlgorithm(metadata={1: "bad"})  # type: ignore[dict-item]

    def test_context_window_algorithm_rejects_multiple_runtime_algorithms(self) -> None:
        with self.assertRaises(ValueError):
            ContextWindowAlgorithm(name="bad", reflexion=ReflexionAlgorithm(), trajectory_checkpoints=TrajectoryCheckpointAlgorithm())

    def test_checkpoint_item_outputs_required_sections_in_order(self) -> None:
        algorithm = TrajectoryCheckpointAlgorithm()
        item = algorithm.build_item(AgentIterationSnapshot(iteration_count=3, message="task", provider="openai", assistant_output="draft"), checkpoint_index=1)
        text = item.to_context_text()
        expected = ["### Reasoning Summary", "### Trajectory", "### Output", "### Score", "### Feedback"]
        indexes = [text.index(section) for section in expected]

        self.assertEqual(indexes, sorted(indexes))

    def test_checkpoint_item_bounds_rendered_text(self) -> None:
        algorithm = TrajectoryCheckpointAlgorithm(max_checkpoint_chars=240, max_field_chars=80)
        item = algorithm.build_item(AgentIterationSnapshot(iteration_count=3, message="task", provider="openai", assistant_output="x" * 1000), checkpoint_index=1)

        self.assertLessEqual(len(item.to_context_text()), 240)

    def test_score_disabled_renders_na(self) -> None:
        algorithm = TrajectoryCheckpointAlgorithm(score_enabled=False)
        item = algorithm.build_item(AgentIterationSnapshot(iteration_count=3, message="task", provider="openai", assistant_output="draft"), checkpoint_index=1)

        self.assertIn("### Score\nN/A", item.to_context_text())

    def test_score_heuristic_penalizes_failed_tool_calls(self) -> None:
        algorithm = TrajectoryCheckpointAlgorithm()
        success = ToolCallContext(tool_name="ok", state=ToolCallState.SUCCEEDED, result=ToolResult.success("ok", "done"))
        failure = ToolCallContext(tool_name="bad", state=ToolCallState.FAILED, result=ToolResult.error("bad", "failed"))
        good = algorithm.build_item(AgentIterationSnapshot(iteration_count=1, message="t", provider="openai", tool_calls=(success,)), checkpoint_index=1)
        bad = algorithm.build_item(AgentIterationSnapshot(iteration_count=1, message="t", provider="openai", tool_calls=(failure,)), checkpoint_index=1)

        self.assertGreater(good.score or 0, bad.score or 0)

    def test_dispatcher_detects_inner_loop_algorithm(self) -> None:
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindow.preset.trajectory_checkpoints)
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "trajectory_checkpoints")
        self.assertIs(dispatcher.inner_loop_algorithm(), runtime.algorithm.trajectory_checkpoints)
        self.assertIsNone(dispatcher.return_algorithm())

    async def test_runtime_writes_checkpoint_primitive_after_interval(self) -> None:
        @tool
        def lookup() -> str:
            return "raw secret output"

        runner = FakeRunner([FakeResponse("draft"), tool_response(), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=2)))
        result = await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
        final_system = runner.calls[2]["kwargs"]["system"]

        self.assertIn("## Context Window Primitives", final_system)
        self.assertIn("Runtime Checkpoint", final_system)
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 1)

    async def test_runtime_does_not_write_checkpoint_before_interval(self) -> None:
        runner = FakeRunner([FakeResponse("draft"), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=2)))
        result = await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertNotIn("Runtime Checkpoint", runner.calls[1]["kwargs"]["system"])
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 0)

    async def test_runtime_metadata_reports_zero_checkpoints_for_early_finish(self) -> None:
        runner = FakeRunner([is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindow.preset.trajectory_checkpoints)
        result = await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 0)

    async def test_runtime_respects_max_checkpoints(self) -> None:
        runner = FakeRunner([FakeResponse("one"), FakeResponse("two"), FakeResponse("three"), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, max_checkpoints=1)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        result = await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 1)

    async def test_runtime_checkpoint_metadata_preserves_normal_metadata(self) -> None:
        runner = FakeRunner([FakeResponse("one"), FakeResponse("two"), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)))
        result = await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertIn("middleware", result.metadata)
        self.assertIn("trajectory_checkpoints", result.metadata)

    async def test_runtime_checkpoint_omits_raw_tool_output_by_default(self) -> None:
        @tool
        def lookup() -> str:
            return "very sensitive raw tool output"

        runner = FakeRunner([tool_response(), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)))
        await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertNotIn("very sensitive raw tool output", runner.calls[1]["kwargs"]["system"])

    async def test_runtime_checkpoint_can_include_bounded_tool_output_when_enabled(self) -> None:
        @tool
        def lookup() -> str:
            return "visible output"

        runner = FakeRunner([tool_response(), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, include_tool_outputs=True, max_field_chars=300)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertIn("visible output", runner.calls[1]["kwargs"]["system"])

    async def test_runtime_slots_match_template(self) -> None:
        recorder = ContextWindowRecorder()
        runner = FakeRunner([FakeResponse("one"), FakeResponse("two"), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=2)), recorder=recorder)
        await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
        template = TrajectoryCheckpointContextWindowTemplate(iterations=2, interval=2)

        self.assertEqual(template.validate(recorder), [])

    async def test_inner_context_window_private_manager_created_when_missing(self) -> None:
        runner = FakeRunner([FakeResponse("one"), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)))
        await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertIsNotNone(runtime.context_manager)

    async def test_context_window_conversation_top_placement_visible_before_existing_messages(self) -> None:
        runner = FakeRunner([FakeResponse("one"), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, placement=ContextWindowPlacement.TOP_OF_CONVERSATION)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
        messages = runner.calls[1]["kwargs"]["messages"]

        self.assertIn("### Reasoning Summary", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "one")

    async def test_after_tool_calls_hook_receives_tool_results(self) -> None:
        @tool
        def lookup() -> str:
            return "tool output"

        runner = FakeRunner([tool_response(), is_done_response()])
        algorithm = ToolRecordingTrajectoryAlgorithm(interval=99)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        result = await runtime.arun("task", runner=runner, context=base_context(), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertEqual(result.metadata["tool_seen"], "tool output")


if __name__ == "__main__":
    unittest.main()
