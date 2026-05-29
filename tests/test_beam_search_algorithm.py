"""Context Protocol Header

Description:
    Tests for the Beam Search runtime context-window algorithm.
Purpose:
    Validates preset wiring, config validation, dispatcher detection,
    and runtime behavior using fake runners.
"""

from __future__ import annotations

import unittest

from vidbyte.agents.algorithms import BeamSearchRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.algorithms.beam_search import BeamSearchAlgorithm
from vidbyte.context.window import ContextWindow
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult
from vidbyte.tools import Tools
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


class BeamSearchAlgorithmConfigTests(unittest.TestCase):
    def test_context_window_preset_exposes_beam_search_algorithm(self) -> None:
        # [Hidden Assumption] preset name and type correct.
        algorithm = ContextWindow.preset.beam_search

        self.assertEqual(algorithm.name, "beam_search")
        self.assertIsInstance(algorithm.beam_search, BeamSearchAlgorithm)

    def test_resolve_algorithm_accepts_beam_search_string(self) -> None:
        # [Hidden Assumption] string resolution works.
        algorithm = ContextWindow.resolve_algorithm("beam_search")

        self.assertEqual(algorithm.name, "beam_search")

    def test_beam_search_algorithm_raises_on_zero_beam_width(self) -> None:
        # [Edge Case] beam_width=0 is invalid.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(beam_width=0)

    def test_beam_search_algorithm_raises_on_negative_beam_width(self) -> None:
        # [Edge Case] negative beam_width is invalid.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(beam_width=-1)

    def test_beam_search_algorithm_raises_on_zero_scorer_chars(self) -> None:
        # [Edge Case] max_scorer_chars=0 is invalid.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(max_scorer_chars=0)

    def test_beam_search_algorithm_raises_on_negative_scorer_chars(self) -> None:
        # [Edge Case] negative max_scorer_chars is invalid.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(max_scorer_chars=-1)

    def test_beam_search_algorithm_rejects_empty_scorer_system_prompt(self) -> None:
        # [Edge Case] empty string override should raise.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(scorer_system_prompt="")

    def test_beam_search_algorithm_rejects_whitespace_scorer_system_prompt(self) -> None:
        # [Edge Case] whitespace-only override should raise.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(scorer_system_prompt="   ")

    def test_beam_search_algorithm_rejects_scorer_prompt_missing_task_placeholder(self) -> None:
        # [Hidden Assumption] {task} placeholder is required.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(scorer_prompt="Candidate: {candidate}\nScore:")

    def test_beam_search_algorithm_rejects_scorer_prompt_missing_candidate_placeholder(self) -> None:
        # [Hidden Assumption] {candidate} placeholder is required.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(scorer_prompt="Task: {task}\nScore:")

    def test_beam_search_algorithm_accepts_valid_scorer_prompt_override(self) -> None:
        # [Hidden Assumption] valid override accepted without error.
        algorithm = BeamSearchAlgorithm(scorer_prompt="Task: {task}\nCandidate: {candidate}\nScore:")

        self.assertIsNotNone(algorithm)

    def test_beam_search_algorithm_rejects_non_string_metadata_key(self) -> None:
        # [Hidden Assumption] metadata keys must be strings.
        with self.assertRaises(ConfigurationError):
            BeamSearchAlgorithm(metadata={1: "value"})  # type: ignore[arg-type]

    def test_beam_search_algorithm_truncates_candidate_at_limit(self) -> None:
        # [Silent Failure] truncation must apply suffix and not exceed limit.
        algorithm = BeamSearchAlgorithm(max_scorer_chars=10)
        truncated = algorithm.truncate_candidate("A" * 20)

        self.assertTrue(truncated.startswith("AAAAAAAAAA"))
        self.assertIn("truncated", truncated)

    def test_beam_search_algorithm_does_not_truncate_within_limit(self) -> None:
        # [Silent Failure] short output must pass through unchanged.
        algorithm = BeamSearchAlgorithm(max_scorer_chars=100)
        output = "Short output."

        self.assertEqual(algorithm.truncate_candidate(output), output)

    def test_beam_search_algorithm_render_scorer_prompt_includes_task_and_candidate(self) -> None:
        # [Hidden Assumption] rendered prompt must contain both values.
        algorithm = BeamSearchAlgorithm()
        rendered = algorithm.render_scorer_prompt(task="my task", candidate="my answer")

        self.assertIn("my task", rendered)
        self.assertIn("my answer", rendered)


class BeamSearchDispatcherTests(unittest.TestCase):
    def _make_runtime(self, algorithm: object | None = None) -> AgentRuntime:
        return AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=algorithm,
        )

    def test_dispatcher_detects_beam_search_algorithm(self) -> None:
        # [Hidden Assumption] dispatcher must detect the preset.
        runtime = self._make_runtime(ContextWindow.preset.beam_search)
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "beam_search")
        self.assertTrue(dispatcher.is_algorithm("beam_search"))

    def test_dispatcher_returns_beam_search_runtime_algorithm(self) -> None:
        # [Hidden Failure] return_algorithm must return the correct adapter type.
        runtime = self._make_runtime(ContextWindow.preset.beam_search)
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertIsInstance(dispatcher.return_algorithm(), BeamSearchRuntimeAlgorithm)

    def test_dispatcher_does_not_detect_beam_search_without_preset(self) -> None:
        # [Hidden Assumption] unrelated presets must not trigger beam_search.
        runtime = self._make_runtime(ContextWindow.preset.reflexion)
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertNotEqual(dispatcher.detect_algorithm(), "beam_search")

    def test_dispatcher_returns_none_without_any_algorithm(self) -> None:
        # [Hidden Assumption] no algorithm → dispatcher returns None.
        runtime = self._make_runtime()
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertIsNone(dispatcher.return_algorithm())


class BeamSearchRuntimeBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def _make_runtime(self, beam_width: int = 2) -> AgentRuntime:
        return AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.beam_search if beam_width == 3
            else ContextWindow.resolve_algorithm(
                __import__("vidbyte.context.algorithms.tool_results", fromlist=["ContextWindowAlgorithm"]).ContextWindowAlgorithm(
                    name="beam_search",
                    beam_search=BeamSearchAlgorithm(beam_width=beam_width),
                )
            ),
        )

    def _build_context(self, runtime: AgentRuntime) -> object:
        return runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

    async def test_beam_search_runtime_runs_beam_width_trials(self) -> None:
        # [Hidden Failure] exactly beam_width agent trials + beam_width scorer calls should fire.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(name="beam_search", beam_search=BeamSearchAlgorithm(beam_width=2)),
        )
        runner = FakeRunner([
            # Trial 1: isDone
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "answer A"}', "call_id": "c1"}]}),
            # Trial 2: isDone
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "answer B"}', "call_id": "c2"}]}),
            # Scorer 1
            FakeResponse("7"),
            # Scorer 2
            FakeResponse("9"),
        ])
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertIn("beam_search", result.metadata)
        self.assertEqual(result.metadata["beam_search"]["beam_width"], 2)
        self.assertEqual(len(result.metadata["beam_search"]["candidates"]), 2)

    async def test_beam_search_runtime_returns_highest_scored_candidate(self) -> None:
        # [Silent Failure] winner must be the candidate with the highest score.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(name="beam_search", beam_search=BeamSearchAlgorithm(beam_width=2)),
        )
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "low score answer"}', "call_id": "c1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "high score answer"}', "call_id": "c2"}]}),
            FakeResponse("3"),
            FakeResponse("9"),
        ])
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.output, "high score answer")
        self.assertEqual(result.metadata["beam_search"]["winner_index"], 1)

    async def test_beam_search_runtime_handles_non_numeric_scorer_output(self) -> None:
        # [Hidden Failure] non-numeric scorer output must not crash; first candidate wins on 0.0 tie.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(name="beam_search", beam_search=BeamSearchAlgorithm(beam_width=2)),
        )
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "first"}', "call_id": "c1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "second"}', "call_id": "c2"}]}),
            FakeResponse("not a number"),
            FakeResponse("also not a number"),
        ])
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertIn("beam_search", result.metadata)
        self.assertIsNotNone(result.output)

    async def test_beam_search_runtime_attaches_beam_metadata(self) -> None:
        # [Hidden Assumption] metadata must include beam_width, winner_index, candidates.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(name="beam_search", beam_search=BeamSearchAlgorithm(beam_width=2)),
        )
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "A"}', "call_id": "c1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "B"}', "call_id": "c2"}]}),
            FakeResponse("5"),
            FakeResponse("8"),
        ])
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        beam_meta = result.metadata["beam_search"]
        self.assertEqual(beam_meta["beam_width"], 2)
        self.assertIn("winner_index", beam_meta)
        self.assertIn("winner_score", beam_meta)
        self.assertIn("candidates", beam_meta)
        self.assertEqual(len(beam_meta["candidates"]), 2)


class BeamSearchParseScoreTests(unittest.TestCase):
    def test_parse_score_extracts_integer(self) -> None:
        # [Silent Failure] must parse the first integer from scorer output.
        from vidbyte.agents.algorithms.beam_search import BeamSearchRuntimeAlgorithm
        self.assertEqual(BeamSearchRuntimeAlgorithm._parse_score("Score: 7"), 7.0)

    def test_parse_score_returns_zero_on_failure(self) -> None:
        # [Hidden Failure] non-numeric text must return 0.0 not raise.
        from vidbyte.agents.algorithms.beam_search import BeamSearchRuntimeAlgorithm
        self.assertEqual(BeamSearchRuntimeAlgorithm._parse_score("no numbers here"), 0.0)

    def test_parse_score_picks_first_integer(self) -> None:
        # [Silent Failure] must pick the first integer, not a later one.
        from vidbyte.agents.algorithms.beam_search import BeamSearchRuntimeAlgorithm
        self.assertEqual(BeamSearchRuntimeAlgorithm._parse_score("Quality: 6. Completeness: 9."), 6.0)


if __name__ == "__main__":
    unittest.main()
