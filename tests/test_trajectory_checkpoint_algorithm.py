"""Context Protocol Header

Description:
    Unit and integration tests for the agentic trajectory checkpoint algorithm.
Purpose:
    Validates agentic (model-based) checkpoint creation, interval cadence, error propagation, and metadata parsing.
Architecture:
    - FakeRunner & FakeResponse: Mocks LLM responses for the agent iteration loop and summary generation.
    - TrajectoryCheckpointAlgorithmTests: TestCase running unit-level parsing checks and integration-level AgentRuntime runs.
Key Functions:
    - test_runtime_writes_checkpoint_primitive_after_interval: Verifies summary call occurs at correct iterations.
    - test_agentic_parsing_valid_json: Verifies extraction of JSON fields from LLM response.
    - test_agentic_parsing_invalid_json_raises_error: Verifies malformed JSON is not silently ignored.
Relations:
    Tests the `TrajectoryCheckpointAlgorithm` in `vidbyte/context/algorithms/trajectory_checkpoints.py`
    and its execution inside `AgentRuntime` in `vidbyte/agents/runtime.py`.
Similar Files:
    - `tests/test_reflexion_algorithm.py`
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from vidbyte import ContextWindow, ContextWindowAlgorithm, ContextWindowPlacement, ReflexionAlgorithm, TrajectoryCheckpointAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.manager import ContextManager
from vidbyte.context.runtime import ContextWindowRunContext
from vidbyte.context.primitives import TrajectoryCheckpointContextItem
from vidbyte.context.templates import ContextWindowRecorder
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.templates import TrajectoryCheckpointContextWindowTemplate
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools import ToolCallContext, ToolCallState, ToolResult, Tools, tool
from vidbyte.tools.security import PermissionPolicy

_JSON_OUTPUT = '{"reasoning_summary": "res", "trajectory": "traj", "output": "out", "score": 0.85, "feedback": "feed"}'


class FakeResponse:
    # A fake response object mimicking LLM output.
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    # A fake runner object holding a list of responses to return.
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: Any) -> FakeResponse:
    # Invokes the fake runner and records the call.
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    # Extracts the text content from a fake response.
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    # Extracts metadata from a fake response.
    return {}


def base_context() -> BaseAgentContext:
    # Returns a minimal agent context for testing.
    return BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)


def runner_handle(runner: FakeRunner) -> RunnerHandle:
    # Wraps the fake runner in the current runtime handle contract.
    return RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata)


def is_done_response(final_answer: str = "done") -> FakeResponse:
    # Formulates a fake isDone tool call response.
    return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "{final_answer}"}}'}]})


def tool_response(name: str = "lookup") -> FakeResponse:
    # Formulates a fake generic tool call response.
    return FakeResponse("", {"output": [{"type": "function_call", "name": name, "arguments": "{}"}]})


class ToolRecordingTrajectoryAlgorithm(TrajectoryCheckpointAlgorithm):
    # Test subclass recording metadata without calling deterministic methods.
    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        # Intercepts after_tool_calls to set custom metadata.
        await super().after_tool_calls(ctx)
        if ctx.iteration is not None and ctx.iteration.tool_calls:
            latest = ctx.iteration.tool_calls[-1]
            if latest.result is not None:
                ctx.set_metadata("tool_seen", latest.result.output)


class TrajectoryCheckpointAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    # Unit and integration tests for TrajectoryCheckpointAlgorithm.

    def test_preset_exposes_trajectory_checkpoint_algorithm(self) -> None:
        # Verify the preset config resolves to the correct algorithm instance.
        preset = ContextWindow.preset.trajectory_checkpoints
        self.assertEqual(preset.name, "trajectory_checkpoints")
        self.assertIsInstance(preset.trajectory_checkpoints, TrajectoryCheckpointAlgorithm)

    def test_resolve_algorithm_accepts_trajectory_checkpoints_string(self) -> None:
        # Verify preset string resolution is supported.
        resolved = ContextWindow.resolve_algorithm("trajectory_checkpoints")
        self.assertEqual(resolved.name, "trajectory_checkpoints")
        self.assertIsInstance(resolved.trajectory_checkpoints, TrajectoryCheckpointAlgorithm)

    def test_config_rejects_zero_interval(self) -> None:
        # Verify non-positive intervals are rejected.
        with self.assertRaises(ConfigurationError):
            TrajectoryCheckpointAlgorithm(interval=0)

    def test_config_rejects_empty_checkpoint_title(self) -> None:
        # Verify empty checkpoint titles are rejected.
        with self.assertRaises(ConfigurationError):
            TrajectoryCheckpointAlgorithm(checkpoint_title=" ")

    def test_config_rejects_non_string_metadata_key(self) -> None:
        # Verify only string keys are allowed in metadata.
        with self.assertRaises(ConfigurationError):
            TrajectoryCheckpointAlgorithm(metadata={1: "bad"})  # type: ignore[dict-item]

    def test_context_window_algorithm_rejects_multiple_runtime_algorithms(self) -> None:
        # Verify algorithms are mutually exclusive.
        with self.assertRaises(ValueError):
            ContextWindowAlgorithm(name="bad", reflexion=ReflexionAlgorithm(), trajectory_checkpoints=TrajectoryCheckpointAlgorithm())

    def test_checkpoint_item_outputs_required_sections_in_order(self) -> None:
        # Verify the sections are output in the correct semantic layout.
        item = TrajectoryCheckpointContextItem(
            primitive_id="trajectory_checkpoint:1",
            iteration=3,
            checkpoint_index=1,
            reasoning_summary="reasoning",
            trajectory="trajectory",
            output="output",
            score=0.9,
            feedback="feedback"
        )
        text = item.to_context_text()
        expected = ["### Reasoning Summary", "### Trajectory", "### Output", "### Score", "### Feedback"]
        indexes = [text.index(section) for section in expected]
        self.assertEqual(indexes, sorted(indexes))

    def test_checkpoint_item_bounds_rendered_text(self) -> None:
        # Verify character limits bound the total context string size.
        item = TrajectoryCheckpointContextItem(
            primitive_id="trajectory_checkpoint:1",
            iteration=3,
            checkpoint_index=1,
            reasoning_summary="x" * 1000,
            trajectory="trajectory",
            output="output",
            score=0.9,
            feedback="feedback",
            max_chars=240
        )
        self.assertLessEqual(len(item.to_context_text()), 240)

    def test_dispatcher_detects_inner_loop_algorithm(self) -> None:
        # Verify the dispatcher successfully detects the algorithm preset.
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindow.preset.trajectory_checkpoints)
        dispatcher = AgentRuntimeContextAlgorithms(runtime)
        self.assertEqual(dispatcher.detect_algorithm(), "trajectory_checkpoints")
        self.assertIs(dispatcher.inner_loop_algorithm(), runtime.algorithm.trajectory_checkpoints)
        self.assertIsNone(dispatcher.return_algorithm())

    async def test_runtime_writes_checkpoint_primitive_after_interval(self) -> None:
        # Verify the checkpoint is correctly written on configuration interval cadence.
        @tool
        def lookup() -> str:
            return "raw secret output"
        runner = FakeRunner([FakeResponse("draft"), tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=2)))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        final_system = runner.calls[3]["kwargs"]["system"]
        self.assertIn("## Context Window Primitives", final_system)
        self.assertIn("Runtime Checkpoint", final_system)
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 1)

    async def test_runtime_checkpoint_survives_null_and_list_summary_fields(self) -> None:
        # [Hidden Failure] A summarizer that writes null or a list for a text field still yields a checkpoint instead of failing the run.
        @tool
        def lookup() -> str:
            return "plan=pro"
        summary = json.dumps({"reasoning_summary": "res", "trajectory": ["read file", "ran tests"], "output": None, "score": 0.5, "feedback": "feed"})
        runner = FakeRunner([tool_response(), FakeResponse(summary), is_done_response("final output")])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        final_system = runner.calls[2]["kwargs"]["system"]
        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 1)
        self.assertIn("Runtime Checkpoint", final_system)
        self.assertIn("ran tests", final_system)
        self.assertNotIn("### Output\nNone", final_system)

    async def test_runtime_does_not_write_checkpoint_before_interval(self) -> None:
        # Verify checkpoint is omitted before interval boundary.
        runner = FakeRunner([FakeResponse("draft"), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=2)))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertNotIn("Runtime Checkpoint", runner.calls[1]["kwargs"]["system"])
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 0)

    async def test_runtime_metadata_reports_zero_checkpoints_for_early_finish(self) -> None:
        # Verify zero checkpoints when run finishes before interval boundary.
        runner = FakeRunner([is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindow.preset.trajectory_checkpoints)
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 0)

    async def test_runtime_respects_max_checkpoints(self) -> None:
        # Verify the maximum checkpoints cap is respected.
        runner = FakeRunner([FakeResponse("one"), FakeResponse(_JSON_OUTPUT), FakeResponse("two"), FakeResponse("three"), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, max_checkpoints=1)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 1)

    async def test_runtime_checkpoint_metadata_preserves_normal_metadata(self) -> None:
        # Verify final metadata merges checkpoint values without corrupting other fields.
        runner = FakeRunner([FakeResponse("one"), FakeResponse(_JSON_OUTPUT), FakeResponse("two"), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertIn("middleware", result.metadata)
        self.assertIn("trajectory_checkpoints", result.metadata)

    async def test_runtime_checkpoint_omits_raw_tool_output_by_default(self) -> None:
        # Verify tool call output details are excluded by default from the summarizer context history.
        @tool
        def lookup() -> str:
            return "very sensitive raw tool output"
        runner = FakeRunner([tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)))
        await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertNotIn("very sensitive raw tool output", runner.calls[1]["prompt"])

    async def test_runtime_checkpoint_can_include_bounded_tool_output_when_enabled(self) -> None:
        # Verify tool output detail is appended to the summarizer context history when enabled.
        @tool
        def lookup() -> str:
            return "visible output"
        runner = FakeRunner([tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, include_tool_outputs=True, max_field_chars=300)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertIn("visible output", runner.calls[1]["prompt"])

    async def test_runtime_checkpoint_fills_summarizer_input_slots_before_output_description(self) -> None:
        # Verify the agent system prompt and history fill the summarizer template's slots once, ahead of its output contract.
        @tool
        def lookup() -> str:
            return "visible output"
        runner = FakeRunner([tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, include_tool_outputs=True)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Catalog every river gauge.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        prompt = runner.calls[1]["prompt"]
        self.assertNotIn("{main_system_prompt}", prompt)
        self.assertNotIn("{conversation_history}", prompt)
        output_start = prompt.index("# Output Description")
        for marker in ("Catalog every river gauge.", "visible output"):
            self.assertEqual(prompt.count(marker), 1, marker)
            self.assertLess(prompt.index(marker), output_start, marker)

    async def test_runtime_checkpoint_history_shows_task_at_run_boundary(self) -> None:
        # [Hidden Failure] The summarizer sees the run's task once, after the caller's history and before the run's own tool work, as the main model does.
        @tool
        def lookup() -> str:
            return "TOOL-OUTPUT-3"
        task = "TASKMARK-7Q catalog every river gauge"
        caller = [{"role": "user", "content": "CALLER-QUESTION-1"}, {"role": "assistant", "content": "CALLER-REPLY-2"}]
        runner = FakeRunner([tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, include_tool_outputs=True)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        await runtime.arun(task, handle=runner_handle(runner), context=base_context(), options={"messages": caller})
        prompt = runner.calls[1]["prompt"]
        self.assertEqual(prompt.count(task), 1)
        positions = [prompt.index(marker) for marker in ("CALLER-QUESTION-1", "CALLER-REPLY-2", task, "TOOL-OUTPUT-3")]
        self.assertEqual(positions, sorted(positions))
        # The main model still gets the task once, as the prompt and never inside its history.
        self.assertEqual(runner.calls[2]["prompt"], task)
        self.assertNotIn(task, str(runner.calls[2]["kwargs"]["messages"]))

    async def test_runtime_slots_match_template(self) -> None:
        # Verify recorded slot templates validate successfully.
        recorder = ContextWindowRecorder()
        runner = FakeRunner([FakeResponse("one"), FakeResponse("two"), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=2)), recorder=recorder)
        await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        template = TrajectoryCheckpointContextWindowTemplate(iterations=2, interval=2)
        self.assertEqual(template.validate(recorder), [])

    async def test_runtime_checkpoint_never_overwrites_note_already_in_manager(self) -> None:
        # Verify a checkpoint skips an id already registered in a shared manager instead of replacing that note.
        manager = ContextManager()
        existing = TrajectoryCheckpointContextItem(primitive_id="trajectory_checkpoint:1", iteration=1, checkpoint_index=1, reasoning_summary="model note", trajectory="t", output="o", score=None, feedback="f")
        manager.upsert(existing)
        runner = FakeRunner([FakeResponse("one"), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)), context_manager=manager)
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertIs(manager.get_by_id("trajectory_checkpoint:1"), existing)
        added = manager.get_by_id("trajectory_checkpoint:2")
        self.assertIsInstance(added, TrajectoryCheckpointContextItem)
        self.assertEqual(added.reasoning_summary, "res")
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoints"][0]["primitive_id"], "trajectory_checkpoint:2")

    async def test_inner_context_window_private_manager_created_when_missing(self) -> None:
        # Verify private context manager initialization works when none is specified.
        runner = FakeRunner([FakeResponse("one"), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)))
        await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertIsNotNone(runtime.context_manager)

    async def test_context_window_conversation_top_placement_visible_before_existing_messages(self) -> None:
        # Verify TOP_OF_CONVERSATION renders before loop history.
        runner = FakeRunner([FakeResponse("one"), FakeResponse(_JSON_OUTPUT), is_done_response()])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1, placement=ContextWindowPlacement.TOP_OF_CONVERSATION)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        messages = runner.calls[2]["kwargs"]["messages"]
        self.assertIn("### Reasoning Summary", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "one")

    async def test_after_tool_calls_hook_receives_tool_results(self) -> None:
        # Verify tool executions are observed in subsequent hooks.
        @tool
        def lookup() -> str:
            return "tool output"
        runner = FakeRunner([tool_response(), is_done_response()])
        algorithm = ToolRecordingTrajectoryAlgorithm(interval=99)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["tool_seen"], "tool output")

    def test_agentic_prompt_asset_loads_successfully(self) -> None:
        # Verify prompt asset loads from catalog.
        prompt_text = Prompts().get(Prompt.TRAJECTORY_CHECKPOINTS_AGENTIC_SUMMARIZER)
        self.assertIn("You are a trajectory checkpoints generator", prompt_text)

    def test_agentic_parsing_valid_json(self) -> None:
        # Verify JSON extraction works for markdown and standard JSON.
        algo = TrajectoryCheckpointAlgorithm()
        raw_json = '{"reasoning_summary": "res", "trajectory": "traj", "output": "out", "score": 0.85, "feedback": "feed"}'
        parsed = algo._parse_json_response(raw_json)
        self.assertEqual(parsed["reasoning_summary"], "res")
        self.assertEqual(parsed["score"], 0.85)
        raw_markdown = '```json\n{"reasoning_summary": "res2", "trajectory": "traj2", "output": "out2", "score": 0.9, "feedback": "feed2"}\n```'
        parsed_md = algo._parse_json_response(raw_markdown)
        self.assertEqual(parsed_md["reasoning_summary"], "res2")
        self.assertEqual(parsed_md["score"], 0.9)

    def test_format_history_reads_gemini_and_anthropic_tool_turns(self) -> None:
        # [Hidden Failure] Gemini parts and Anthropic tool_use turns reach the side-call history instead of empty lines.
        gemini = [{"role": "model", "parts": [{"functionCall": {"name": "lookup_population", "args": {"city": "Paris"}}}]}, {"role": "user", "parts": [{"functionResponse": {"name": "lookup_population", "response": {"population": 2100000}}}]}]
        anthropic = [{"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "lookup_population", "input": {"city": "Paris"}}]}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "2100000"}]}]
        for include_tool_outputs in (True, False):
            algorithm = TrajectoryCheckpointAlgorithm(include_tool_outputs=include_tool_outputs)
            for provider, messages in (("gemini", gemini), ("anthropic", anthropic)):
                with self.subTest(provider=provider, include_tool_outputs=include_tool_outputs):
                    history = algorithm._format_history(messages)
                    self.assertIn("lookup_population", history)
                    if include_tool_outputs:
                        self.assertIn("2100000", history)
                    else:
                        self.assertIn("[Tool output omitted]", history)
                        self.assertNotIn("2100000", history)

    def test_agentic_parsing_invalid_json_raises_error(self) -> None:
        # Verify malformed LLM responses raise an error.
        algo = TrajectoryCheckpointAlgorithm()
        snapshot = AgentIterationSnapshot(iteration_count=3, message="task", provider="openai", assistant_output="draft")
        class BadRunner:
            pass
        async def bad_invoke(runner: Any, prompt: str, **kwargs: Any) -> FakeResponse:
            # Returns malformed response to trigger error behavior.
            return FakeResponse("bad json response")
        from vidbyte.context.manager import ContextManager
        from vidbyte.context.templates import NullRecorder
        ctx = ContextWindowRunContext(
            context_manager=ContextManager(),
            recorder=NullRecorder(),
            state={},
            iteration=snapshot,
            runner=BadRunner(),
            provider="openai",
            invoke_runner=bad_invoke,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            messages=[],
            system_prompt="sys"
        )
        import asyncio
        with self.assertRaises(json.JSONDecodeError):
            asyncio.run(algo.build_item(ctx, snapshot, 1))

    async def test_runtime_invokes_model_call_for_checkpoints(self) -> None:
        # Verify LLM summary is invoked on interval.
        runner = FakeRunner([FakeResponse("main response 1"), FakeResponse(_JSON_OUTPUT), is_done_response("final output")])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        system_instructions = runner.calls[2]["kwargs"]["system"]
        self.assertIn("res", system_instructions)
        self.assertIn("feed", system_instructions)
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 1)

    async def test_runtime_handles_model_call_failure(self) -> None:
        # Verify exception propagation on model call failures.
        runner = FakeRunner([FakeResponse("main response 1"), FakeResponse("malformed json response"), is_done_response("final output")])
        algorithm = TrajectoryCheckpointAlgorithm(interval=1)
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=algorithm))
        with self.assertRaises(json.JSONDecodeError):
            await runtime.arun("task", handle=runner_handle(runner), context=base_context())


if __name__ == "__main__":
    unittest.main()

