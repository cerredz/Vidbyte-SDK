"""FILE: tests/test_jev_done_criteria.py

PURPOSE: Verifies Jev minimum-duration criteria, early-finish continuation, and result metadata without live model calls.
ROLE IN CODEBASE: Exercises the public settings/preset boundary and its integration with the shared agent runtime loop.
ARCHITECTURE NOTE: Scripted runners and a fake monotonic clock replace only provider/time boundaries.
FUNCTION INVENTORY: Tests cover unit normalization, validation, final-response and isDone gating, metadata, and exports.
COMMON MODIFICATION PATTERNS: Add each criterion's boundary and finish-path cases here and mirror test names in the feature script.
WHAT NOT TO DO: Do not use real sleeps, credentials, or network-backed runners in this test module.
KNOWN EDGE CASES: Python bool is an int subclass; all completion paths must be checked because they are distinct runtime branches.
RELATED DOCS: docs/design/jev-done-criteria.md and tests/features/jev_minimum_duration/FEATURE.md.
TESTS: Run with python scripts/test-jev-done-criteria.py or python -m pytest tests/test_jev_done_criteria.py.
"""

from __future__ import annotations

import unittest
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Awaitable, Callable
from unittest.mock import patch

from vidbyte import JevDoneCriteria as RootJevDoneCriteria
from vidbyte import JevDoneCriterion as RootJevDoneCriterion
from vidbyte import JevPreset as RootJevPreset
from vidbyte import MinimumTime as RootMinimumTime
from vidbyte import tool
from vidbyte.agents import JevDoneCriteria, JevDoneCriterion, JevPreset, MinimumTime
from vidbyte.agents.jev import JevAgent, JevAgentSettings
from vidbyte.agents.jev.done_criteria import JevDoneCriterionResult
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.agents.contracts import MinIterations
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.middleware import AgentMiddleware, MiddlewarePipeline
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision


@tool
def continue_work() -> str:
    # Provides one harmless tool action so a run can reach a time budget without asking to finish.
    return "work continued"


class RawResponse:
    """OpenAI Responses-shaped result used for internal isDone calls."""

    def __init__(self, raw: dict[str, object]) -> None:
        # Exposes the raw function-call payload consumed by the runtime parser.
        self.text = ""
        self.raw = raw


class ScriptedRunner:
    """Synchronous fake runner that records options and returns fixed model outputs."""

    def __init__(self, *responses: object) -> None:
        # Stores one response per expected provider invocation.
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def run(self, prompt: str, **kwargs: object) -> object:
        # Records provider-visible input and returns the next scripted response.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.responses.pop(0)


def _settings(**overrides: object) -> JevAgentSettings:
    # Produces valid Jev settings for runtime tests with selected overrides.
    values: dict[str, object] = {"name": "jev", "system_prompt": "Work carefully.", "provider": "openai", "model_name": "gpt-4.1-mini"}
    values.update(overrides)
    return JevAgentSettings(**values)


def bind_test_runner(agent: JevAgent, runner: object) -> JevAgent:
    # Binds a scripted provider runner directly to the configured Jev agent.
    agent._runner_cache[RUNNER_TYPE_TEXT] = runner
    return agent


@contextmanager
def _runtime_clock(clock: FakeClock) -> Iterator[None]:
    # Injects fake time only into runtime middleware, leaving asyncio's event-loop clock real.
    class ClockedMiddlewarePipeline(MiddlewarePipeline):
        def __init__(self, middleware: Sequence[AgentMiddleware] = (), *, sleeper: Callable[[float], Awaitable[None]] | None = None, clock: Callable[[], float] | None = None) -> None:
            # Preserves the real pipeline behavior while replacing only its monotonic clock source.
            super().__init__(middleware, sleeper=sleeper, clock=clock or clock_source)

    clock_source = clock
    with patch("vidbyte.agents.runtime.MiddlewarePipeline", ClockedMiddlewarePipeline):
        yield


class FakeClock:
    """Mutable callable clock used by the runtime tests."""

    def __init__(self, value: float = 0.0) -> None:
        # Starts at a stable monotonic value that tests can advance explicitly.
        self.value = value

    def __call__(self) -> float:
        # Returns current fake monotonic time without advancing it implicitly.
        return self.value

    def advance(self, seconds: float) -> None:
        # Advances time only when a test runner explicitly requests it.
        self.value += seconds


class ClockAdvancingRunner(ScriptedRunner):
    """Scripted generative runner that can advance fake time before each response."""

    def __init__(self, clock: FakeClock, responses: tuple[object, ...], advances: tuple[float, ...]) -> None:
        # Associates one optional deterministic clock advance with each scripted response.
        super().__init__(*responses)
        self.clock = clock
        self.advances = advances

    def run(self, prompt: str, **kwargs: object) -> object:
        # Advances the fake clock and records the call using the inherited runner behavior.
        call_index = len(self.calls)
        self.clock.advance(self.advances[call_index])
        return super().run(prompt, **kwargs)


class AlternateCriterion(JevDoneCriterion):
    """Simple second criterion used to verify composite AND semantics."""

    def evaluate(self, *, elapsed_seconds: float) -> JevDoneCriterionResult:
        # Requires at least two seconds so tests can distinguish individual and combined policy.
        met = elapsed_seconds >= 2.0
        return JevDoneCriterionResult(met, "second criterion is unmet" if not met else "", {"second_met": met})


class AfterIterationRecorder(AgentMiddleware):
    """Counts normal after-iteration dispatches without changing the runtime decision."""

    def __init__(self) -> None:
        # Keeps a run-local observable for lifecycle assertions.
        self.iterations = 0

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Records the existing hook invocation and allows the runtime loop to proceed.
        del ctx
        self.iterations += 1
        return MiddlewareDecision.continue_()


class JevDoneCriteriaUnitTests(unittest.TestCase):
    """Pins duration validation and deterministic criterion evaluation."""

    def test_each_duration_unit_normalizes_to_seconds(self) -> None:
        # [Edge Case] every supported public unit maps to its canonical threshold.
        criteria = (
            (JevPreset.MinimumTime(seconds=1), 1.0),
            (JevPreset.MinimumTime(minutes=1), 60.0),
            (JevPreset.MinimumTime(hours=1), 3_600.0),
            (JevPreset.MinimumTime(days=1), 86_400.0),
        )
        for criterion, expected in criteria:
            with self.subTest(expected=expected):
                self.assertEqual(criterion.duration_seconds, expected)

    def test_minimum_time_rejects_invalid_values_and_unit_combinations(self) -> None:
        # [Edge Case] invalid values and ambiguous unit choices fail before runtime setup.
        invalid_calls = (
            {},
            {"seconds": 0},
            {"minutes": -1},
            {"hours": True},
            {"days": float("inf")},
            {"seconds": float("nan")},
            {"seconds": "5"},
            {"seconds": 1, "minutes": 1},
        )
        for values in invalid_calls:
            with self.subTest(values=values), self.assertRaises(ConfigurationError):
                JevPreset.MinimumTime(**values)

    def test_large_finite_duration_that_overflows_conversion_is_rejected(self) -> None:
        # [Hidden Failure] finite day input must not become an infinite stored threshold after conversion.
        with self.assertRaisesRegex(ConfigurationError, "normalize to a finite"):
            JevPreset.MinimumTime(days=1e308)
        with self.assertRaisesRegex(ConfigurationError, "representable as a finite"):
            JevPreset.MinimumTime(seconds=10**1000)

    def test_composite_requires_every_criterion(self) -> None:
        # [Silent Failure] satisfying the duration floor cannot hide another unmet criterion.
        combined = JevDoneCriteria((JevPreset.MinimumTime(seconds=1), AlternateCriterion()))
        early = combined.evaluate(elapsed_seconds=1.5)
        passed = combined.evaluate(elapsed_seconds=2.0)
        self.assertFalse(early.is_met)
        self.assertIn("second criterion is unmet", early.continuation_prompt or "")
        self.assertTrue(passed.is_met)
        self.assertEqual(passed.metadata["minimum_duration_met"], True)

    def test_minimum_time_uses_an_inclusive_exact_threshold(self) -> None:
        # [Edge Case] only elapsed time below the threshold rejects; equality is already met.
        criterion = JevPreset.MinimumTime(seconds=5)
        self.assertFalse(criterion.evaluate(elapsed_seconds=4.999).is_met)
        self.assertTrue(criterion.evaluate(elapsed_seconds=5.0).is_met)
        self.assertTrue(criterion.evaluate(elapsed_seconds=5.001).is_met)

    def test_settings_snapshots_valid_criteria_and_rejects_wrong_shapes(self) -> None:
        # [Hidden Assumption] callers cannot inject strings or mutable post-construction policy changes.
        criteria = [JevPreset.MinimumTime(seconds=5)]
        settings = _settings(done_criteria=criteria)
        criteria.clear()
        self.assertEqual(len(settings.done_criteria), 1)
        for invalid in ("criteria", b"criteria", (object(),)):
            with self.subTest(invalid=invalid), self.assertRaises(ConfigurationError):
                _settings(done_criteria=invalid)

    def test_public_import_paths_share_the_same_types(self) -> None:
        # [Hidden Failure] root and agents namespace imports must not expose compatibility copies.
        self.assertIs(RootJevDoneCriteria, JevDoneCriteria)
        self.assertIs(RootJevDoneCriterion, JevDoneCriterion)
        self.assertIs(RootJevPreset, JevPreset)
        self.assertIs(RootMinimumTime, MinimumTime)


class JevDoneCriteriaRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Pins same-loop continuation across both normal model finish paths."""

    async def test_early_plain_response_is_added_to_history_then_continued(self) -> None:
        # [Silent Failure] plain text finalization must not bypass the duration gate or lose its candidate answer.
        clock = FakeClock()
        runner = ClockAdvancingRunner(clock, (TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="early draft", raw={}), TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="finished work", raw={})), (0.0, 5.0))
        agent = bind_test_runner(JevAgent(_settings(done_criteria=(JevPreset.MinimumTime(seconds=5),))), runner)
        with _runtime_clock(clock):
            reply = await agent.arun("complete the task")
        self.assertEqual(reply.content, "finished work")
        self.assertTrue(reply.metadata["minimum_duration_met"])
        self.assertEqual(len(runner.calls), 2)
        messages = runner.calls[1]["kwargs"]["messages"]
        self.assertTrue(any(message.get("content") == "early draft" for message in messages))
        self.assertTrue(any("minimum run duration has not elapsed" in message.get("content", "") for message in messages))

    async def test_early_is_done_attempt_is_rejected_until_model_tries_again(self) -> None:
        # [Hidden Failure] the internal completion tool must use the same duration gate as final text.
        clock = FakeClock()
        runner = ClockAdvancingRunner(clock, (RawResponse({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "too soon"}', "call_id": "done-early"}]}), TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="now complete", raw={})), (0.0, 5.0))
        agent = bind_test_runner(JevAgent(_settings(done_criteria=(JevPreset.MinimumTime(seconds=5),))), runner)
        with _runtime_clock(clock):
            reply = await agent.arun("complete the task")
        self.assertEqual(reply.content, "now complete")
        self.assertEqual(len(runner.calls), 2)
        self.assertTrue(any("minimum run duration has not elapsed" in message.get("content", "") for message in runner.calls[1]["kwargs"]["messages"]))

    async def test_passing_time_without_a_finish_attempt_does_not_finish_run(self) -> None:
        # [Hidden Assumption] threshold passage is eligibility only, not an autonomous completion signal.
        clock = FakeClock()
        tool_call = RawResponse({"output": [{"type": "function_call", "name": "continue_work", "arguments": "{}", "call_id": "work-1"}]})
        runner = ClockAdvancingRunner(clock, (tool_call,), (5.0,))
        settings = _settings(done_criteria=(JevPreset.MinimumTime(seconds=5),), tools=(continue_work,), loop=AgentLoopSettings(max_iterations=1))
        agent = bind_test_runner(JevAgent(settings), runner)
        with _runtime_clock(clock):
            reply = await agent.arun("continue working")
        self.assertIn("max_iterations", str(reply.metadata))
        self.assertEqual(len(runner.calls), 1)
        self.assertTrue(reply.metadata["minimum_duration_met"])

    async def test_unmet_duration_is_recorded_on_budget_stop(self) -> None:
        # [Silent Failure] a non-completion terminal result still reports the configured duration state.
        clock = FakeClock()
        runner = ClockAdvancingRunner(clock, (TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="continue", raw={}),), (0.0,))
        agent = bind_test_runner(JevAgent(_settings(done_criteria=(JevPreset.MinimumTime(seconds=5),), loop=AgentLoopSettings(max_iterations=1))), runner)
        with _runtime_clock(clock):
            reply = await agent.arun("continue")
        self.assertFalse(reply.metadata["minimum_duration_met"])

    async def test_gate_preserves_generic_contracts_and_after_iteration_hooks(self) -> None:
        # [Hidden Failure] Jev rejection must not skip generic floor evaluation or middleware lifecycle.
        clock = FakeClock()
        done_call = RawResponse({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "early"}', "call_id": "done-early"}]})
        runner = ClockAdvancingRunner(clock, (done_call, TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="finished", raw={})), (0.0, 5.0))
        settings = _settings(done_criteria=(JevPreset.MinimumTime(seconds=5),), loop=AgentLoopSettings(output_contracts=(MinIterations(1),)))
        agent = bind_test_runner(JevAgent(settings), runner)
        middleware = AfterIterationRecorder()
        agent.middleware = (middleware,)
        with _runtime_clock(clock):
            reply = await agent.arun("complete the task")
        self.assertEqual(reply.content, "finished")
        self.assertTrue(reply.metadata["minimum_duration_met"])
        self.assertIn("contract_evaluations", reply.metadata)
        self.assertEqual(middleware.iterations, 2)

    async def test_no_criteria_preserves_ordinary_result_without_new_metadata(self) -> None:
        # [Hidden Assumption] no configured criterion has no new prompt or result field.
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="ordinary result", raw={}))
        agent = bind_test_runner(JevAgent(_settings()), runner)
        reply = await agent.arun("question")
        self.assertEqual(reply.content, "ordinary result")
        self.assertNotIn("minimum_duration_met", reply.metadata)
        self.assertEqual(len(runner.calls), 1)

    async def test_concurrent_attempts_use_run_local_start_times(self) -> None:
        # [Hidden Failure] concurrent run states calculate elapsed duration from their own start markers.
        from vidbyte.agents.jev.runtime import JevRuntime
        from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
        from vidbyte.lib.dataclasses.context import BaseAgentContext
        from vidbyte.tools.catalog import Tools
        from vidbyte.tools.security import PermissionPolicy

        clock = FakeClock(20.0)
        runtime = JevRuntime(jev_settings=_settings(done_criteria=(JevPreset.MinimumTime(seconds=5),)), agent_name="jev", system_prompt="work", tools=Tools(), permission_policy=PermissionPolicy())
        runtime.middleware.clock = clock
        older = BaseAgentRuntimeLoopState(message="a", context=BaseAgentContext(system_prompt="work"), provider="openai", metadata={}, started_at=10.0)
        newer = BaseAgentRuntimeLoopState(message="b", context=BaseAgentContext(system_prompt="work"), provider="openai", metadata={}, started_at=18.0)
        self.assertEqual(runtime._elapsed_seconds(older), 10.0)
        self.assertEqual(runtime._elapsed_seconds(newer), 2.0)


if __name__ == "__main__":
    unittest.main()
