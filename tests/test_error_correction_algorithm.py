"""Context Protocol Header

Description:
    Unit and integration tests for the error-correction context algorithm.
Purpose:
    Validates audit cadence, allow-listed removals, single-notice replacement,
    JSON parsing, config validation, dispatcher wiring, slot templates, metadata.
Architecture:
    - FakeRunner & FakeResponse: Mock LLM responses for the agent loop and auditor.
    - ErrorCorrectionAlgorithmTests: Unit-level and AgentRuntime integration tests.
Relations:
    Tests `vidbyte/context/algorithms/error_correction.py` and its execution
    inside `AgentRuntime`.
Similar Files:
    - `tests/test_trajectory_checkpoint_algorithm.py`
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte import ContextWindow, ContextWindowAlgorithm, ErrorCorrectionAlgorithm, ErrorCorrectionContextItem, ReflexionAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ProblemSpaceSearchContextItem
from vidbyte.context.runtime import ContextWindowPlacement, ContextWindowRunContext
from vidbyte.context.templates import NullRecorder
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.templates import ErrorCorrectionContextWindowTemplate
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.tools import Tools, tool
from vidbyte.tools.security import PermissionPolicy

_EC_JSON = '{"corrections": [{"claim": "x is true", "why_wrong": "system prompt says x is false"}], "stale_primitive_ids": [], "summary": "one correction"}'
_EC_EMPTY = '{"corrections": [], "stale_primitive_ids": [], "summary": "context is consistent"}'


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


def lookup_tools() -> Tools:
    # Builds a tool catalog with a simple lookup tool.
    @tool
    def lookup() -> str:
        return "raw output"
    return Tools([lookup])


def algo_runtime(algorithm: ErrorCorrectionAlgorithm) -> AgentRuntime:
    # Builds an AgentRuntime configured with the error-correction algorithm.
    return AgentRuntime(agent_name="worker", system_prompt="Work.", tools=lookup_tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindowAlgorithm(name="error_correction", error_correction=algorithm))


def run_context(manager: ContextManager) -> ContextWindowRunContext:
    # Builds a minimal run context over a manager for unit-level removal tests.
    return ContextWindowRunContext(context_manager=manager, recorder=NullRecorder(), state={})


class ErrorCorrectionAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    # Unit and integration tests for ErrorCorrectionAlgorithm.

    def test_preset_exposes_algorithm(self) -> None:
        # [Edge Case] Preset config resolves to the correct algorithm instance.
        preset = ContextWindow.preset.error_correction
        self.assertEqual(preset.name, "error_correction")
        self.assertIsInstance(preset.error_correction, ErrorCorrectionAlgorithm)

    def test_resolve_algorithm_accepts_string(self) -> None:
        # [Hidden Assumption] Preset string resolution is supported.
        resolved = ContextWindow.resolve_algorithm("error_correction")
        self.assertEqual(resolved.name, "error_correction")
        self.assertIsInstance(resolved.error_correction, ErrorCorrectionAlgorithm)

    def test_config_rejects_zero_interval(self) -> None:
        # [Edge Case] Non-positive intervals are rejected at construction.
        with self.assertRaises(ConfigurationError):
            ErrorCorrectionAlgorithm(interval=0)

    def test_config_rejects_zero_max_passes(self) -> None:
        # [Edge Case] Non-positive max_passes are rejected.
        with self.assertRaises(ConfigurationError):
            ErrorCorrectionAlgorithm(max_passes=0)

    def test_config_rejects_oversized_char_limit(self) -> None:
        # [Edge Case] Char limits beyond the safeguard are rejected.
        with self.assertRaises(ConfigurationError):
            ErrorCorrectionAlgorithm(max_notice_chars=10_000_000)

    def test_config_rejects_empty_title(self) -> None:
        # [Edge Case] Empty notice titles are rejected.
        with self.assertRaises(ConfigurationError):
            ErrorCorrectionAlgorithm(notice_title=" ")

    def test_config_rejects_empty_prompt_override(self) -> None:
        # [Silent Failure] Empty override must not silently fall back to the catalog.
        with self.assertRaises(ConfigurationError):
            ErrorCorrectionAlgorithm(auditor_prompt="   ")

    def test_config_rejects_empty_removable_prefixes(self) -> None:
        # [Hidden Assumption] An empty allow-list is rejected.
        with self.assertRaises(ConfigurationError):
            ErrorCorrectionAlgorithm(removable_prefixes=())

    def test_config_rejects_non_string_metadata_key(self) -> None:
        # [Hidden Assumption] Only string keys are allowed in metadata.
        with self.assertRaises(ConfigurationError):
            ErrorCorrectionAlgorithm(metadata={1: "bad"})  # type: ignore[dict-item]

    def test_config_coerces_placement_string(self) -> None:
        # [Hidden Assumption] Placement strings coerce to the enum.
        algorithm = ErrorCorrectionAlgorithm(placement="end_of_context")  # type: ignore[arg-type]
        self.assertIs(algorithm.placement, ContextWindowPlacement.END_OF_CONTEXT)

    def test_mutual_exclusivity(self) -> None:
        # [Hidden Failure] At most one runtime context algorithm may be configured.
        with self.assertRaises(ValueError):
            ContextWindowAlgorithm(name="bad", reflexion=ReflexionAlgorithm(), error_correction=ErrorCorrectionAlgorithm())

    def test_notice_item_renders_corrections(self) -> None:
        # [Edge Case] The notice renders each correction under an authoritative header.
        item = ErrorCorrectionContextItem(primitive_id="error_correction:notice", iteration=4, pass_index=1, corrections=("a is wrong", "b is wrong"), summary="two issues")
        text = item.to_context_text()
        self.assertIn("authoritative", text.lower())
        self.assertIn("a is wrong", text)
        self.assertIn("b is wrong", text)

    def test_notice_item_bounds_rendered_text(self) -> None:
        # [Silent Failure] Character limits bound the rendered notice string.
        item = ErrorCorrectionContextItem(primitive_id="error_correction:notice", iteration=4, pass_index=1, corrections=("x" * 5000,), summary="s", max_chars=240)
        self.assertLessEqual(len(item.to_context_text()), 240)

    def test_format_corrections_handles_dict_and_caps(self) -> None:
        # [Edge Case] Corrections accept claim/why_wrong dicts and respect the cap.
        algorithm = ErrorCorrectionAlgorithm(max_corrections=2)
        result = algorithm._format_corrections([{"claim": "c1", "why_wrong": "w1"}, {"claim": "c2", "why_wrong": "w2"}, {"claim": "c3", "why_wrong": "w3"}])
        self.assertEqual(len(result), 2)
        self.assertIn("c1", result[0])

    def test_apply_removals_only_removes_allowlisted_ids(self) -> None:
        # [Hidden Assumption] Only allow-listed prefixes may be removed; others are skipped.
        manager = ContextManager()
        manager.upsert(ProblemSpaceSearchContextItem(primitive_id="problem_space_search:1", iteration=1, note_index=1, unconsidered="u", blind_spots="b", next_directions="n"))
        algorithm = ErrorCorrectionAlgorithm()
        ctx = run_context(manager)
        removed, skipped = algorithm.apply_removals(ctx, ["problem_space_search:1", "user_provided:keepme"])
        self.assertEqual(removed, ["problem_space_search:1"])
        self.assertEqual(skipped, ["user_provided:keepme"])
        self.assertIsNone(manager.get_by_id("problem_space_search:1"))

    def test_apply_removals_never_removes_own_notice(self) -> None:
        # [Hidden Failure] The active correction notice id is never self-removed.
        algorithm = ErrorCorrectionAlgorithm()
        ctx = run_context(ContextManager())
        removed, skipped = algorithm.apply_removals(ctx, ["error_correction:notice"])
        self.assertEqual(removed, [])
        self.assertIn("error_correction:notice", skipped)

    def test_apply_removals_missing_id_is_noop(self) -> None:
        # [Edge Case] Removing a non-existent allow-listed id does not raise.
        algorithm = ErrorCorrectionAlgorithm()
        ctx = run_context(ContextManager())
        removed, skipped = algorithm.apply_removals(ctx, ["error_correction:gone"])
        self.assertEqual(removed, ["error_correction:gone"])

    def test_parse_malformed_json_raises(self) -> None:
        # [Silent Failure] Malformed JSON is not silently ignored.
        with self.assertRaises(Exception):
            ErrorCorrectionAlgorithm()._parse_json_response("not json")

    def test_dispatcher_detects_algorithm(self) -> None:
        # [Hidden Failure] The dispatcher detects and returns the inner-loop algorithm.
        runtime = algo_runtime(ErrorCorrectionAlgorithm())
        dispatcher = AgentRuntimeContextAlgorithms(runtime)
        self.assertEqual(dispatcher.detect_algorithm(), "error_correction")
        self.assertIs(dispatcher.inner_loop_algorithm(), runtime.algorithm.error_correction)
        self.assertIsNone(dispatcher.return_algorithm())

    def test_template_builds_expected_slots(self) -> None:
        # [Silent Failure] The slot template encodes the audit cadence.
        slots = ErrorCorrectionContextWindowTemplate(iterations=4, interval=2).expected_slots
        self.assertEqual(slots.count("error_correction_pass"), 2)
        self.assertEqual(slots[0], "system_prompt")

    async def test_runtime_upserts_notice_on_cadence(self) -> None:
        # [Silent Failure] An audit pass upserts a model-visible notice on cadence.
        runner = FakeRunner([tool_response(), FakeResponse(_EC_JSON), is_done_response()])
        runtime = algo_runtime(ErrorCorrectionAlgorithm(interval=1))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["error_correction"]["pass_count"], 1)
        self.assertTrue(any("Correction Notice" in c["kwargs"].get("system", "") for c in runner.calls))

    async def test_runtime_replaces_notice_not_duplicates(self) -> None:
        # [Hidden Failure] Repeated passes replace the single notice rather than accumulating.
        runner = FakeRunner([tool_response(), FakeResponse(_EC_JSON), tool_response(), FakeResponse(_EC_JSON), is_done_response()])
        runtime = algo_runtime(ErrorCorrectionAlgorithm(interval=1))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        final_system = runner.calls[-1]["kwargs"].get("system", "")
        self.assertEqual(result.metadata["error_correction"]["pass_count"], 2)
        self.assertEqual(final_system.count("Correction Notice"), 1)

    async def test_runtime_skips_notice_when_nothing_to_correct(self) -> None:
        # [Edge Case] No notice is upserted when there are zero corrections and zero removals.
        runner = FakeRunner([tool_response(), FakeResponse(_EC_EMPTY), is_done_response()])
        runtime = algo_runtime(ErrorCorrectionAlgorithm(interval=1))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["error_correction"]["pass_count"], 1)
        self.assertFalse(any("Correction Notice" in c["kwargs"].get("system", "") for c in runner.calls))

    async def test_runtime_respects_max_passes(self) -> None:
        # [Edge Case] The pass cap halts audits while iterations continue.
        runner = FakeRunner([tool_response(), FakeResponse(_EC_JSON), tool_response(), tool_response(), is_done_response()])
        runtime = algo_runtime(ErrorCorrectionAlgorithm(interval=1, max_passes=1))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["error_correction"]["pass_count"], 1)

    async def test_runtime_metadata_preserves_normal_fields(self) -> None:
        # [Silent Failure] Algorithm metadata is merged without dropping normal runtime fields.
        runner = FakeRunner([tool_response(), FakeResponse(_EC_JSON), is_done_response()])
        runtime = algo_runtime(ErrorCorrectionAlgorithm(interval=1))
        result = await runtime.arun("task", handle=runner_handle(runner), context=base_context())
        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertIn("middleware", result.metadata)
        self.assertIn("error_correction", result.metadata)


if __name__ == "__main__":
    unittest.main()
