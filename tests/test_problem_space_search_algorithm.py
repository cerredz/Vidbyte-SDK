"""Context Protocol Header

Description:
    Unit and integration tests for the problem-space search context algorithm.
Purpose:
    Validates explorer cadence, note injection, JSON parsing, config
    validation, dispatcher wiring, slot templates, and metadata.
Architecture:
    - FakeRunner & FakeResponse: Mock LLM responses for the agent loop and explorer.
    - ProblemSpaceSearchAlgorithmTests: Unit-level and AgentRuntime integration tests.
Relations:
    Tests `vidbyte/context/algorithms/problem_space_search.py` and its execution
    inside `AgentRuntime`.
Similar Files:
    - `tests/test_trajectory_checkpoint_algorithm.py`
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte import ContextWindow, ContextWindowAlgorithm, ProblemSpaceSearchAlgorithm, ProblemSpaceSearchContextItem, ReflexionAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.templates import ProblemSpaceSearchContextWindowTemplate
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.tools import Tools, tool
from vidbyte.tools.security import PermissionPolicy

_JSON_OUTPUT = '{"unconsidered": ["alt approach"], "blind_spots": ["unchecked assumption"], "next_directions": ["verify edge case"]}'


class FakeResponse:
    # A fake response object mimicking LLM output.
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    # A fake runner holding an ordered list of responses to return.
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


def algo_runtime(algorithm: ProblemSpaceSearchAlgorithm, tools: Tools | None = None) -> AgentRuntime:
    # Builds an AgentRuntime configured with the problem-space search algorithm.
    return AgentRuntime(agent_name="worker", system_prompt="Work.", tools=tools or Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="problem_space_search", problem_space_search=algorithm))


class ProblemSpaceSearchAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    # Unit and integration tests for ProblemSpaceSearchAlgorithm.

    def test_preset_exposes_algorithm(self) -> None:
        # [Edge Case] Preset config resolves to the correct algorithm instance.
        preset = ContextWindow.preset.problem_space_search
        self.assertEqual(preset.name, "problem_space_search")
        self.assertIsInstance(preset.problem_space_search, ProblemSpaceSearchAlgorithm)

    def test_resolve_algorithm_accepts_string(self) -> None:
        # [Hidden Assumption] Preset string resolution is supported.
        resolved = ContextWindow.resolve_algorithm("problem_space_search")
        self.assertEqual(resolved.name, "problem_space_search")
        self.assertIsInstance(resolved.problem_space_search, ProblemSpaceSearchAlgorithm)

    def test_resolve_unknown_name_raises(self) -> None:
        # [Silent Failure] Unknown preset names must not fall back to a default.
        with self.assertRaises(ValueError):
            ContextWindow.resolve_algorithm("not_a_real_algorithm")

    def test_config_rejects_zero_interval(self) -> None:
        # [Edge Case] Non-positive intervals are rejected at construction.
        with self.assertRaises(ConfigurationError):
            ProblemSpaceSearchAlgorithm(interval=0)

    def test_config_rejects_zero_max_notes(self) -> None:
        # [Edge Case] Non-positive max_notes are rejected.
        with self.assertRaises(ConfigurationError):
            ProblemSpaceSearchAlgorithm(max_notes=0)

    def test_config_rejects_oversized_char_limit(self) -> None:
        # [Edge Case] Char limits beyond the safeguard are rejected.
        with self.assertRaises(ConfigurationError):
            ProblemSpaceSearchAlgorithm(max_note_chars=10_000_000)

    def test_config_rejects_empty_title(self) -> None:
        # [Edge Case] Empty note titles are rejected.
        with self.assertRaises(ConfigurationError):
            ProblemSpaceSearchAlgorithm(note_title=" ")

    def test_config_rejects_empty_prompt_override(self) -> None:
        # [Silent Failure] Empty override must not silently fall back to the catalog.
        with self.assertRaises(ConfigurationError):
            ProblemSpaceSearchAlgorithm(explorer_prompt="   ")

    def test_config_rejects_non_string_metadata_key(self) -> None:
        # [Hidden Assumption] Only string keys are allowed in metadata.
        with self.assertRaises(ConfigurationError):
            ProblemSpaceSearchAlgorithm(metadata={1: "bad"})  # type: ignore[dict-item]

    def test_config_coerces_placement_string(self) -> None:
        # [Hidden Assumption] Placement strings coerce to the enum.
        algorithm = ProblemSpaceSearchAlgorithm(placement="top_of_context")  # type: ignore[arg-type]
        self.assertIs(algorithm.placement, ContextWindowPlacement.TOP_OF_CONTEXT)

    def test_mutual_exclusivity(self) -> None:
        # [Hidden Failure] At most one runtime context algorithm may be configured.
        with self.assertRaises(ValueError):
            ContextWindowAlgorithm(name="bad", reflexion=ReflexionAlgorithm(), problem_space_search=ProblemSpaceSearchAlgorithm())

    def test_item_outputs_sections_in_order(self) -> None:
        # [Edge Case] The primitive renders required sections in deterministic order.
        item = ProblemSpaceSearchContextItem(primitive_id="problem_space_search:1", iteration=5, note_index=1, unconsidered="u", blind_spots="b", next_directions="n")
        text = item.to_context_text()
        expected = ["### Not Yet Considered", "### Blind Spots", "### Next Directions To Explore"]
        indexes = [text.index(section) for section in expected]
        self.assertEqual(indexes, sorted(indexes))

    def test_item_bounds_rendered_text(self) -> None:
        # [Silent Failure] Character limits bound the rendered context string.
        item = ProblemSpaceSearchContextItem(primitive_id="problem_space_search:1", iteration=5, note_index=1, unconsidered="x" * 5000, blind_spots="b", next_directions="n", max_chars=240)
        self.assertLessEqual(len(item.to_context_text()), 240)

    def test_parse_fenced_and_bare_json(self) -> None:
        # [Edge Case] Both fenced and bare JSON objects parse correctly.
        algorithm = ProblemSpaceSearchAlgorithm()
        fenced = algorithm._parse_json_response("```json\n{\"unconsidered\": \"a\"}\n```")
        bare = algorithm._parse_json_response("noise {\"unconsidered\": \"a\"} trailing")
        self.assertEqual(fenced["unconsidered"], "a")
        self.assertEqual(bare["unconsidered"], "a")

    def test_parse_malformed_json_raises(self) -> None:
        # [Silent Failure] Malformed JSON is not silently ignored.
        with self.assertRaises(Exception):
            ProblemSpaceSearchAlgorithm()._parse_json_response("not json at all")

    def test_format_field_handles_list_and_none(self) -> None:
        # [Edge Case] List fields render as bullets and None renders empty.
        algorithm = ProblemSpaceSearchAlgorithm()
        self.assertIn("- one", algorithm._format_field(["one", "two"]))
        self.assertEqual(algorithm._format_field(None), "")

    def test_dispatcher_detects_algorithm(self) -> None:
        # [Hidden Failure] The dispatcher detects and returns the inner-loop algorithm.
        runtime = algo_runtime(ProblemSpaceSearchAlgorithm())
        dispatcher = AgentRuntimeContextAlgorithms(runtime)
        self.assertEqual(dispatcher.detect_algorithm(), "problem_space_search")
        self.assertIs(dispatcher.inner_loop_algorithm(), runtime.algorithm.problem_space_search)
        self.assertIsNone(dispatcher.return_algorithm())

    def test_template_builds_expected_slots(self) -> None:
        # [Silent Failure] The slot template encodes the cadence, capped by max_notes.
        slots = ProblemSpaceSearchContextWindowTemplate(iterations=4, interval=2, max_notes=1).expected_slots
        self.assertEqual(slots.count("problem_space_search_injection"), 1)
        self.assertEqual(slots[0], "system_prompt")

    async def test_runtime_injects_note_after_interval(self) -> None:
        # [Silent Failure] A note is injected at the interval boundary and made model-visible.
        runner = FakeRunner([tool_response(), tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = algo_runtime(ProblemSpaceSearchAlgorithm(interval=2), tools=_lookup_tools())
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["problem_space_search"]["note_count"], 1)
        self.assertTrue(any("Problem-Space Search" in c["kwargs"].get("system", "") for c in runner.calls))

    async def test_runtime_does_not_inject_before_interval(self) -> None:
        # [Silent Failure] No note is injected before the interval boundary is reached.
        runner = FakeRunner([tool_response(), is_done_response()])
        runtime = algo_runtime(ProblemSpaceSearchAlgorithm(interval=5), tools=_lookup_tools())
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["problem_space_search"]["note_count"], 0)

    async def test_runtime_respects_max_notes(self) -> None:
        # [Edge Case] The note cap halts injection while iterations continue.
        runner = FakeRunner([tool_response(), FakeResponse(_JSON_OUTPUT), tool_response(), tool_response(), is_done_response()])
        runtime = algo_runtime(ProblemSpaceSearchAlgorithm(interval=1, max_notes=1), tools=_lookup_tools())
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["problem_space_search"]["note_count"], 1)

    async def test_runtime_metadata_preserves_normal_fields(self) -> None:
        # [Silent Failure] Algorithm metadata is merged without dropping normal runtime fields.
        runner = FakeRunner([tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = algo_runtime(ProblemSpaceSearchAlgorithm(interval=1), tools=_lookup_tools())
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertIn("middleware", result.metadata)
        self.assertIn("problem_space_search", result.metadata)

    async def test_runtime_omits_raw_tool_output_by_default(self) -> None:
        # [Hidden Assumption] Raw tool output is excluded from the explorer prompt by default.
        runner = FakeRunner([tool_response(), FakeResponse(_JSON_OUTPUT), is_done_response()])
        runtime = algo_runtime(ProblemSpaceSearchAlgorithm(interval=1), tools=_secret_tools())
        await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertFalse(any("very sensitive raw tool output" in c["prompt"] for c in runner.calls))


def _lookup_tools() -> Tools:
    # Builds a tool catalog with a simple lookup tool.
    @tool
    def lookup() -> str:
        return "raw output"
    return Tools([lookup])


def _secret_tools() -> Tools:
    # Builds a tool catalog whose output should not leak into the explorer prompt.
    @tool
    def lookup() -> str:
        return "very sensitive raw tool output"
    return Tools([lookup])


if __name__ == "__main__":
    unittest.main()
