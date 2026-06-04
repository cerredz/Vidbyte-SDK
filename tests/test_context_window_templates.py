"""Context Protocol Header

Description:
    Unit and integration tests for the context window template system.
Purpose:
    Validates SlotEvent, ContextWindowRecorder, NullRecorder, ContextWindowTemplate,
    TemplateViolation, ReflexionContextWindowTemplate, AgentRuntime recorder wiring,
    and ReflexionRuntimeAlgorithm slot instrumentation.
Architecture:
    - Recorder tests: correctness, ordering, isolation, reset.
    - Template tests: validation logic, edge cases, violation structure.
    - ReflexionContextWindowTemplate tests: slot list construction.
    - AgentRuntime integration tests: recorder param accepted and stored.
    - Reflexion instrumentation tests: correct slots emitted in correct order.
Relations:
    Tests code in vidbyte/context/templates/, vidbyte/lib/templates/,
    vidbyte/agents/runtime.py, and vidbyte/agents/algorithms/reflexion.py.
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte.agents.algorithms.reflexion import ReflexionRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.templates import ContextWindowRecorder, NullRecorder, RecorderBase, SlotEvent
from vidbyte.context.window import ContextWindow
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.templates import ContextWindowTemplate, ReflexionContextWindowTemplate, TemplateViolation, TrajectoryCheckpointContextWindowTemplate
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)

    def run(self, prompt: str, **kwargs: Any) -> FakeResponse:
        return self.responses.pop(0)


def _is_done_response(final_answer: str = "done") -> FakeResponse:
    return FakeResponse(
        "",
        {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "{final_answer}"}}'}]},
    )


def _max_iterations_response() -> FakeResponse:
    return FakeResponse("I could not complete the task.", {})


def _reflection_response() -> FakeResponse:
    return FakeResponse("I should have been more methodical.", {})


async def _invoke_runner(runner: FakeRunner, prompt: str, **kwargs: Any) -> FakeResponse:
    return runner.responses.pop(0)


def _output_text(r: object) -> str:
    return str(getattr(r, "text", r))


def _output_metadata(r: object) -> dict:
    return {}


def _make_runtime(*, algorithm: str | None = None, recorder: RecorderBase | None = None) -> AgentRuntime:
    return AgentRuntime(
        agent_name="test-agent",
        system_prompt="Be helpful.",
        tools=Tools(),
        permission_policy=PermissionPolicy(),
        config=AgentRuntimeConfig(max_iterations=3),
        algorithm=algorithm,
        recorder=recorder,
    )


def _base_context() -> BaseAgentContext:
    return BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)


# ---------------------------------------------------------------------------
# SlotEvent tests
# ---------------------------------------------------------------------------

class SlotEventTests(unittest.TestCase):
    def test_slot_event_is_frozen(self) -> None:
        event = SlotEvent(slot_type="test", iteration=0, metadata={})
        with self.assertRaises((AttributeError, TypeError)):
            event.slot_type = "mutated"  # type: ignore[misc]

    def test_slot_event_stores_slot_type_iteration_metadata(self) -> None:
        meta = {"key": "value"}
        event = SlotEvent(slot_type="system_prompt", iteration=2, metadata=meta)
        self.assertEqual(event.slot_type, "system_prompt")
        self.assertEqual(event.iteration, 2)
        self.assertEqual(event.metadata, {"key": "value"})


# ---------------------------------------------------------------------------
# ContextWindowRecorder tests
# ---------------------------------------------------------------------------

class ContextWindowRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = ContextWindowRecorder()

    def test_recorder_starts_empty(self) -> None:
        self.assertEqual(self.recorder.slots(), ())

    def test_recorder_slots_returns_insertion_order(self) -> None:
        self.recorder.append("A")
        self.recorder.append("B")
        self.recorder.append("C")
        self.assertEqual(self.recorder.slots(), ("A", "B", "C"))

    def test_recorder_events_returns_full_slot_events(self) -> None:
        self.recorder.append("reflexion_trial", iteration=0)
        events = self.recorder.events()
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], SlotEvent)

    def test_recorder_append_stores_iteration(self) -> None:
        self.recorder.append("reflexion_trial", iteration=5)
        self.assertEqual(self.recorder.events()[0].iteration, 5)

    def test_recorder_append_stores_extra_metadata(self) -> None:
        self.recorder.append("reflexion_trial", iteration=0, trial_index=2)
        self.assertEqual(self.recorder.events()[0].metadata, {"trial_index": 2})

    def test_recorder_reset_clears_all_events(self) -> None:
        self.recorder.append("system_prompt")
        self.recorder.reset()
        self.assertEqual(self.recorder.slots(), ())

    def test_recorder_does_not_share_metadata_across_events(self) -> None:
        self.recorder.append("A", iteration=0, key=1)
        self.recorder.append("B", iteration=1, key=2)
        events = self.recorder.events()
        self.assertEqual(events[0].metadata["key"], 1)
        self.assertEqual(events[1].metadata["key"], 2)


# ---------------------------------------------------------------------------
# NullRecorder tests
# ---------------------------------------------------------------------------

class NullRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = NullRecorder()

    def test_null_recorder_append_does_not_raise(self) -> None:
        self.recorder.append("system_prompt", iteration=0)

    def test_null_recorder_slots_always_empty(self) -> None:
        for _ in range(10):
            self.recorder.append("some_slot")
        self.assertEqual(self.recorder.slots(), ())


# ---------------------------------------------------------------------------
# ContextWindowTemplate tests
# ---------------------------------------------------------------------------

class ContextWindowTemplateTests(unittest.TestCase):
    def _recorder_with(self, *slots: str) -> ContextWindowRecorder:
        rec = ContextWindowRecorder()
        for slot in slots:
            rec.append(slot)
        return rec

    def test_template_stores_expected_slots(self) -> None:
        template = ContextWindowTemplate(["A", "B", "C"])
        self.assertEqual(template.expected_slots, ("A", "B", "C"))

    def test_validate_returns_empty_for_exact_match(self) -> None:
        template = ContextWindowTemplate(["A", "B"])
        recorder = self._recorder_with("A", "B")
        self.assertEqual(template.validate(recorder), [])

    def test_validate_reports_mismatch_at_correct_position(self) -> None:
        template = ContextWindowTemplate(["A", "B"])
        recorder = self._recorder_with("A", "X")
        violations = template.validate(recorder)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].position, 1)
        self.assertEqual(violations[0].expected, "B")
        self.assertEqual(violations[0].actual, "X")

    def test_validate_reports_trace_ended_early(self) -> None:
        template = ContextWindowTemplate(["A", "B", "C"])
        recorder = self._recorder_with("A")
        violations = template.validate(recorder)
        self.assertEqual(len(violations), 2)
        self.assertIsNone(violations[0].actual)
        self.assertIsNone(violations[1].actual)

    def test_validate_reports_extra_slots_in_trace(self) -> None:
        template = ContextWindowTemplate(["A"])
        recorder = self._recorder_with("A", "B", "C")
        violations = template.validate(recorder)
        self.assertEqual(len(violations), 2)
        self.assertEqual(violations[0].expected, "<end>")
        self.assertEqual(violations[0].actual, "B")

    def test_validate_empty_template_empty_trace(self) -> None:
        template = ContextWindowTemplate([])
        recorder = ContextWindowRecorder()
        self.assertEqual(template.validate(recorder), [])

    def test_validate_empty_template_nonempty_trace(self) -> None:
        template = ContextWindowTemplate([])
        recorder = self._recorder_with("A", "B")
        violations = template.validate(recorder)
        self.assertEqual(len(violations), 2)
        self.assertEqual(violations[0].expected, "<end>")

    def test_validate_nonempty_template_empty_trace(self) -> None:
        template = ContextWindowTemplate(["A", "B"])
        recorder = ContextWindowRecorder()
        violations = template.validate(recorder)
        self.assertEqual(len(violations), 2)
        self.assertIsNone(violations[0].actual)
        self.assertIsNone(violations[1].actual)

    def test_passes_returns_true_on_exact_match(self) -> None:
        template = ContextWindowTemplate(["A", "B"])
        recorder = self._recorder_with("A", "B")
        self.assertTrue(template.passes(recorder))

    def test_passes_returns_false_on_any_violation(self) -> None:
        template = ContextWindowTemplate(["A", "B"])
        recorder = self._recorder_with("A", "X")
        self.assertFalse(template.passes(recorder))


# ---------------------------------------------------------------------------
# TemplateViolation tests
# ---------------------------------------------------------------------------

class TemplateViolationTests(unittest.TestCase):
    def test_violation_is_frozen(self) -> None:
        v = TemplateViolation(position=0, expected="A", actual="B", message="mismatch")
        with self.assertRaises((AttributeError, TypeError)):
            v.position = 99  # type: ignore[misc]

    def test_violation_stores_none_actual(self) -> None:
        v = TemplateViolation(position=2, expected="reflexion_trial", actual=None, message="ended")
        self.assertIsNone(v.actual)


# ---------------------------------------------------------------------------
# ReflexionContextWindowTemplate tests
# ---------------------------------------------------------------------------

class ReflexionContextWindowTemplateTests(unittest.TestCase):
    def test_single_trial_no_failures(self) -> None:
        template = ReflexionContextWindowTemplate(max_trials=1, failing_trials=0)
        self.assertEqual(template.expected_slots, ("system_prompt", "reflexion_trial"))

    def test_two_trials_one_failure(self) -> None:
        template = ReflexionContextWindowTemplate(max_trials=2, failing_trials=1)
        self.assertEqual(
            template.expected_slots,
            ("system_prompt", "reflexion_trial", "reflexion_reflection", "reflexion_trial"),
        )

    def test_three_trials_two_failures_default(self) -> None:
        template = ReflexionContextWindowTemplate(max_trials=3)
        self.assertEqual(
            template.expected_slots,
            (
                "system_prompt",
                "reflexion_trial", "reflexion_reflection",
                "reflexion_trial", "reflexion_reflection",
                "reflexion_trial",
            ),
        )

    def test_failing_trials_defaults_to_max_trials_minus_one(self) -> None:
        default = ReflexionContextWindowTemplate(max_trials=3)
        explicit = ReflexionContextWindowTemplate(max_trials=3, failing_trials=2)
        self.assertEqual(default.expected_slots, explicit.expected_slots)

    def test_zero_failing_trials_produces_system_prompt_plus_one_trial(self) -> None:
        template = ReflexionContextWindowTemplate(max_trials=3, failing_trials=0)
        self.assertEqual(template.expected_slots, ("system_prompt", "reflexion_trial"))


class TrajectoryCheckpointContextWindowTemplateTests(unittest.TestCase):
    def test_trajectory_template_zero_iterations(self) -> None:
        template = TrajectoryCheckpointContextWindowTemplate(iterations=0, interval=2)

        self.assertEqual(template.expected_slots, ("system_prompt",))

    def test_trajectory_template_interval_two(self) -> None:
        template = TrajectoryCheckpointContextWindowTemplate(iterations=4, interval=2)

        self.assertEqual(
            template.expected_slots,
            (
                "system_prompt",
                "trajectory_checkpoint_iteration",
                "trajectory_checkpoint_iteration",
                "trajectory_checkpoint_injection",
                "trajectory_checkpoint_iteration",
                "trajectory_checkpoint_iteration",
                "trajectory_checkpoint_injection",
            ),
        )

    def test_trajectory_template_respects_max_checkpoints(self) -> None:
        template = TrajectoryCheckpointContextWindowTemplate(iterations=4, interval=1, max_checkpoints=2)

        self.assertEqual(
            template.expected_slots,
            (
                "system_prompt",
                "trajectory_checkpoint_iteration",
                "trajectory_checkpoint_injection",
                "trajectory_checkpoint_iteration",
                "trajectory_checkpoint_injection",
                "trajectory_checkpoint_iteration",
                "trajectory_checkpoint_iteration",
            ),
        )


# ---------------------------------------------------------------------------
# AgentRuntime recorder integration tests
# ---------------------------------------------------------------------------

class AgentRuntimeRecorderTests(unittest.TestCase):
    def test_runtime_defaults_to_null_recorder(self) -> None:
        runtime = _make_runtime()
        self.assertIsInstance(runtime.recorder, NullRecorder)

    def test_runtime_accepts_recorder_instance(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = _make_runtime(recorder=recorder)
        self.assertIs(runtime.recorder, recorder)

    def test_existing_construction_without_recorder_kwarg_unchanged(self) -> None:
        runtime = AgentRuntime(
            agent_name="agent",
            system_prompt="sys",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
        )
        self.assertIsInstance(runtime.recorder, NullRecorder)


# ---------------------------------------------------------------------------
# Reflexion instrumentation tests
# ---------------------------------------------------------------------------

class ReflexionInstrumentationTests(unittest.IsolatedAsyncioTestCase):
    def _make_reflexion_runtime(self, recorder: ContextWindowRecorder, max_trials: int = 3) -> AgentRuntime:
        from vidbyte.context.algorithms import ReflexionAlgorithm
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm, ToolResultAdmission
        algorithm = ContextWindowAlgorithm(
            name="reflexion",
            reflexion=ReflexionAlgorithm(max_trials=max_trials),
        )
        return AgentRuntime(
            agent_name="reflexion-agent",
            system_prompt="Work carefully.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=algorithm,
            recorder=recorder,
        )

    async def test_reflexion_emits_system_prompt_once_at_run_start(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = self._make_reflexion_runtime(recorder, max_trials=1)
        runner = FakeRunner([_is_done_response()])
        await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        system_prompt_slots = [s for s in recorder.slots() if s == "system_prompt"]
        self.assertEqual(len(system_prompt_slots), 1)
        self.assertEqual(recorder.slots()[0], "system_prompt")

    async def test_reflexion_emits_reflexion_trial_per_trial(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = self._make_reflexion_runtime(recorder, max_trials=2)
        # Trial 0 hits max_iterations, reflection call runs, trial 1 succeeds.
        runner = FakeRunner([_max_iterations_response(), _reflection_response(), _is_done_response()])
        await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        trial_slots = [s for s in recorder.slots() if s == "reflexion_trial"]
        self.assertEqual(len(trial_slots), 2)

    async def test_reflexion_emits_reflexion_reflection_per_failing_trial(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = self._make_reflexion_runtime(recorder, max_trials=2)
        runner = FakeRunner([_max_iterations_response(), _reflection_response(), _is_done_response()])
        await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        reflection_slots = [s for s in recorder.slots() if s == "reflexion_reflection"]
        self.assertEqual(len(reflection_slots), 1)

    async def test_reflexion_slot_order_matches_template(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = self._make_reflexion_runtime(recorder, max_trials=2)
        runner = FakeRunner([_max_iterations_response(), _reflection_response(), _is_done_response()])
        await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        template = ReflexionContextWindowTemplate(max_trials=2, failing_trials=1)
        self.assertTrue(template.passes(recorder), msg=f"Violations: {template.validate(recorder)}")

    async def test_reflexion_early_success_no_reflection_slot(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = self._make_reflexion_runtime(recorder, max_trials=3)
        runner = FakeRunner([_is_done_response()])
        await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        self.assertNotIn("reflexion_reflection", recorder.slots())

    async def test_reflexion_null_recorder_does_not_crash(self) -> None:
        runtime = self._make_reflexion_runtime(ContextWindowRecorder(), max_trials=1)
        runtime.recorder = NullRecorder()
        runner = FakeRunner([_is_done_response()])
        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        self.assertIsNotNone(result)

    async def test_reflexion_trial_index_stored_in_slot_event(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = self._make_reflexion_runtime(recorder, max_trials=2)
        runner = FakeRunner([_max_iterations_response(), _reflection_response(), _is_done_response()])
        await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        trial_events = [e for e in recorder.events() if e.slot_type == "reflexion_trial"]
        self.assertEqual(trial_events[0].iteration, 0)
        self.assertEqual(trial_events[1].iteration, 1)

    async def test_reflexion_three_trial_two_failure_full_integration(self) -> None:
        recorder = ContextWindowRecorder()
        runtime = self._make_reflexion_runtime(recorder, max_trials=3)
        runner = FakeRunner([
            _max_iterations_response(),   # trial 0 model call
            _reflection_response(),       # reflection after trial 0
            _max_iterations_response(),   # trial 1 model call
            _reflection_response(),       # reflection after trial 1
            _is_done_response(),          # trial 2 model call
        ])
        await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=_base_context(),
        )
        template = ReflexionContextWindowTemplate(max_trials=3, failing_trials=2)
        violations = template.validate(recorder)
        self.assertEqual(violations, [], msg=f"Unexpected violations: {violations}")


if __name__ == "__main__":
    unittest.main()
