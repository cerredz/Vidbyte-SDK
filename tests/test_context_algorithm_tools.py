from __future__ import annotations

import unittest
from unittest import mock

from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ReflexionContextItem, TrajectoryCheckpointContextItem
from vidbyte.lib.constants.cot_events import DEFAULT_SALVAGE
from vidbyte.tools.builtins.cot_events import BacktrackTool, UncertaintyTool
from vidbyte.tools.builtins.reasoning.deduce import DeduceTool
from vidbyte.tools.builtins.reflexion import ReflexionTool
from vidbyte.tools.builtins.trajectory_checkpoint import TrajectoryCheckpointTool
from vidbyte.tools.types import ToolCall, ToolStatus


# ---------------------------------------------------------------------------
# TrajectoryCheckpointContextItem rendering
# ---------------------------------------------------------------------------


class TrajectoryCheckpointContextItemTests(unittest.TestCase):
    def _make(self, **overrides) -> TrajectoryCheckpointContextItem:
        defaults = dict(
            primitive_id="tc:1",
            iteration=0,
            checkpoint_index=1,
            reasoning_summary="Analyzed the problem.",
            trajectory="step1 → step2",
            output="intermediate result",
            score=0.8,
            feedback="continue refining",
        )
        defaults.update(overrides)
        return TrajectoryCheckpointContextItem(**defaults)

    def test_to_context_text_includes_all_sections(self) -> None:
        item = self._make()
        text = item.to_context_text()
        for section in ("Reasoning Summary", "Trajectory", "Output", "Score", "Feedback"):
            self.assertIn(section, text)

    def test_score_renders_as_na_when_none(self) -> None:
        item = self._make(score=None)
        self.assertIn("N/A", item.to_context_text())

    def test_score_renders_as_float_string(self) -> None:
        item = self._make(score=0.75)
        self.assertIn("0.75", item.to_context_text())

    def test_truncates_to_max_chars(self) -> None:
        long_content = "x" * 5000
        item = self._make(reasoning_summary=long_content, max_chars=100)
        # max_chars=100 plus the 15-char suffix "\n...[truncated]"
        self.assertLessEqual(len(item.to_context_text()), 115)
        self.assertIn("truncated", item.to_context_text())

    def test_does_not_truncate_when_under_limit(self) -> None:
        item = self._make(reasoning_summary="short", max_chars=5000)
        self.assertNotIn("truncated", item.to_context_text())

    def test_zero_max_chars_passes_through_untruncated(self) -> None:
        item = self._make(max_chars=0)
        text = item.to_context_text()
        self.assertNotIn("truncated", text)
        self.assertIn("Reasoning Summary", text)


# ---------------------------------------------------------------------------
# ReflexionContextItem rendering
# ---------------------------------------------------------------------------


class ReflexionContextItemTests(unittest.TestCase):
    def test_to_context_text_includes_critique_and_correction_plan(self) -> None:
        item = ReflexionContextItem(
            primitive_id="r:1",
            critique="Used wrong approach.",
            correction_plan="Switch to binary search.",
        )
        text = item.to_context_text()
        self.assertIn("Critique", text)
        self.assertIn("Correction Plan", text)
        self.assertIn("Used wrong approach", text)
        self.assertIn("Switch to binary search", text)

    def test_failed_attempt_section_absent_when_none(self) -> None:
        item = ReflexionContextItem(
            primitive_id="r:1",
            critique="c",
            correction_plan="p",
            failed_attempt=None,
        )
        self.assertNotIn("Failed Attempt", item.to_context_text())

    def test_failed_attempt_section_present_when_set(self) -> None:
        item = ReflexionContextItem(
            primitive_id="r:1",
            critique="c",
            correction_plan="p",
            failed_attempt="tried linear scan",
        )
        self.assertIn("Failed Attempt", item.to_context_text())
        self.assertIn("tried linear scan", item.to_context_text())

    def test_truncates_to_max_chars(self) -> None:
        item = ReflexionContextItem(
            primitive_id="r:1",
            critique="c" * 2000,
            correction_plan="p" * 2000,
            max_chars=100,
        )
        # max_chars=100 plus the 15-char suffix "\n...[truncated]"
        self.assertLessEqual(len(item.to_context_text()), 115)
        self.assertIn("truncated", item.to_context_text())


# ---------------------------------------------------------------------------
# TrajectoryCheckpointTool execution
# ---------------------------------------------------------------------------


class TrajectoryCheckpointToolTests(unittest.IsolatedAsyncioTestCase):
    def _tool(self) -> tuple[TrajectoryCheckpointTool, ContextManager]:
        manager = ContextManager()
        return TrajectoryCheckpointTool(manager), manager

    def _call(self, **kwargs) -> ToolCall:
        return ToolCall(tool_name="trajectory_checkpoint", arguments=kwargs)

    async def test_execute_with_all_fields_writes_primitive(self) -> None:
        tool, manager = self._tool()
        call = self._call(
            reasoning_summary="analyzed",
            trajectory="tool_a → tool_b",
            output="result",
            score="0.9",
            feedback="keep going",
        )
        result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        stored = manager.get_by_id("trajectory_checkpoint:1")
        self.assertIsNotNone(stored)

    async def test_execute_returns_rendered_context_text(self) -> None:
        tool, _ = self._tool()
        call = self._call(reasoning_summary="r", trajectory="t", output="o")
        result = await tool.execute(call)
        self.assertIn("Reasoning Summary", result.output)

    async def test_execute_missing_reasoning_summary_returns_error(self) -> None:
        tool, _ = self._tool()
        call = self._call(trajectory="t", output="o")
        result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("reasoning_summary", result.output)

    async def test_execute_missing_trajectory_returns_error(self) -> None:
        tool, _ = self._tool()
        call = self._call(reasoning_summary="r", output="o")
        result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("trajectory", result.output)

    async def test_execute_missing_output_returns_error(self) -> None:
        tool, _ = self._tool()
        call = self._call(reasoning_summary="r", trajectory="t")
        result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("output", result.output)

    async def test_invalid_score_string_stores_none(self) -> None:
        tool, manager = self._tool()
        call = self._call(reasoning_summary="r", trajectory="t", output="o", score="abc")
        await tool.execute(call)
        stored = manager.get_by_id("trajectory_checkpoint:1")
        self.assertIsNone(stored.score)

    async def test_valid_score_string_coerces_to_float(self) -> None:
        tool, manager = self._tool()
        call = self._call(reasoning_summary="r", trajectory="t", output="o", score="0.85")
        await tool.execute(call)
        stored = manager.get_by_id("trajectory_checkpoint:1")
        self.assertAlmostEqual(stored.score, 0.85)

    async def test_score_above_one_is_clamped(self) -> None:
        tool, manager = self._tool()
        call = self._call(reasoning_summary="r", trajectory="t", output="o", score="2.5")
        await tool.execute(call)
        stored = manager.get_by_id("trajectory_checkpoint:1")
        self.assertEqual(stored.score, 1.0)

    async def test_two_calls_produce_distinct_primitive_ids(self) -> None:
        tool, manager = self._tool()
        base_call = self._call(reasoning_summary="r", trajectory="t", output="o")
        await tool.execute(base_call)
        await tool.execute(base_call)
        self.assertIsNotNone(manager.get_by_id("trajectory_checkpoint:1"))
        self.assertIsNotNone(manager.get_by_id("trajectory_checkpoint:2"))

    async def test_frozen_note_on_taken_id_is_kept(self) -> None:
        from vidbyte.context.primitives import TrajectoryCheckpointContextItem
        tool, manager = self._tool()
        frozen = TrajectoryCheckpointContextItem(
            primitive_id="trajectory_checkpoint:1",
            iteration=0,
            checkpoint_index=1,
            reasoning_summary="r",
            trajectory="t",
            output="o",
            score=None,
            feedback="",
            primitive_frozen=True,
        )
        manager.upsert(frozen)
        call = self._call(reasoning_summary="new", trajectory="t2", output="o2")
        result = await tool.execute(call)
        # The taken id is skipped, so the frozen note survives and the new note lands beside it.
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIs(manager.get_by_id("trajectory_checkpoint:1"), frozen)
        self.assertEqual(manager.get_by_id("trajectory_checkpoint:2").reasoning_summary, "new")

    async def test_rejected_upsert_returns_error(self) -> None:
        tool, _ = self._tool()
        call = self._call(reasoning_summary="r", trajectory="t", output="o")
        with mock.patch.object(ContextManager, "upsert", side_effect=ValueError("rejected")):
            result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.ERROR)

    def test_spec_name_is_trajectory_checkpoint(self) -> None:
        tool, _ = self._tool()
        self.assertEqual(tool.spec().name, "trajectory_checkpoint")

    def test_validate_call_returns_error_for_missing_required_args(self) -> None:
        tool, _ = self._tool()
        call = ToolCall(tool_name="trajectory_checkpoint", arguments={"output": "o"})
        error = tool.validate_call(call)
        self.assertIsNotNone(error)


# ---------------------------------------------------------------------------
# ReflexionTool execution
# ---------------------------------------------------------------------------


class ReflexionToolTests(unittest.IsolatedAsyncioTestCase):
    def _tool(self) -> tuple[ReflexionTool, ContextManager]:
        manager = ContextManager()
        return ReflexionTool(manager), manager

    def _call(self, **kwargs) -> ToolCall:
        return ToolCall(tool_name="reflexion", arguments=kwargs)

    async def test_execute_with_required_fields_writes_primitive(self) -> None:
        tool, manager = self._tool()
        call = self._call(critique="bad approach", correction_plan="use X instead")
        result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIsNotNone(manager.get_by_id("reflexion:1"))

    async def test_execute_returns_rendered_context_text(self) -> None:
        tool, _ = self._tool()
        call = self._call(critique="c", correction_plan="p")
        result = await tool.execute(call)
        self.assertIn("Critique", result.output)
        self.assertIn("Correction Plan", result.output)

    async def test_execute_missing_critique_returns_error(self) -> None:
        tool, _ = self._tool()
        call = self._call(correction_plan="p")
        result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("critique", result.output)

    async def test_execute_missing_correction_plan_returns_error(self) -> None:
        tool, _ = self._tool()
        call = self._call(critique="c")
        result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("correction_plan", result.output)

    async def test_optional_failed_attempt_included_in_output(self) -> None:
        tool, _ = self._tool()
        call = self._call(critique="c", correction_plan="p", failed_attempt="tried linear scan")
        result = await tool.execute(call)
        self.assertIn("tried linear scan", result.output)

    async def test_optional_failed_attempt_absent_when_not_provided(self) -> None:
        tool, _ = self._tool()
        call = self._call(critique="c", correction_plan="p")
        result = await tool.execute(call)
        self.assertNotIn("Failed Attempt", result.output)

    async def test_null_title_uses_default_title(self) -> None:
        # @intent null-optional-arg-means-default: a null title means the "Reflexion Note" default.
        tool, manager = self._tool()
        result = await tool.execute(self._call(critique="c", correction_plan="p", title=None))
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        self.assertEqual(manager.get_by_id("reflexion:1").title, "Reflexion Note")
        self.assertNotIn("None", result.output)

    async def test_two_calls_produce_distinct_primitive_ids(self) -> None:
        tool, manager = self._tool()
        base_call = self._call(critique="c", correction_plan="p")
        await tool.execute(base_call)
        await tool.execute(base_call)
        self.assertIsNotNone(manager.get_by_id("reflexion:1"))
        self.assertIsNotNone(manager.get_by_id("reflexion:2"))

    async def test_frozen_note_on_taken_id_is_kept(self) -> None:
        from vidbyte.context.primitives import ReflexionContextItem
        tool, manager = self._tool()
        frozen = ReflexionContextItem(
            primitive_id="reflexion:1",
            critique="c",
            correction_plan="p",
            primitive_frozen=True,
        )
        manager.upsert(frozen)
        call = self._call(critique="new critique", correction_plan="new plan")
        result = await tool.execute(call)
        # The taken id is skipped, so the frozen note survives and the new note lands beside it.
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIs(manager.get_by_id("reflexion:1"), frozen)
        self.assertEqual(manager.get_by_id("reflexion:2").critique, "new critique")

    async def test_rejected_upsert_returns_error(self) -> None:
        tool, _ = self._tool()
        call = self._call(critique="c", correction_plan="p")
        with mock.patch.object(ContextManager, "upsert", side_effect=ValueError("rejected")):
            result = await tool.execute(call)
        self.assertEqual(result.status, ToolStatus.ERROR)

    def test_spec_name_is_reflexion(self) -> None:
        tool, _ = self._tool()
        self.assertEqual(tool.spec().name, "reflexion")

    async def test_two_tool_instances_have_independent_counters(self) -> None:
        manager = ContextManager()
        tool_a = ReflexionTool(manager)
        tool_b = ReflexionTool(manager)
        call = self._call(critique="c", correction_plan="p")
        await tool_a.execute(call)
        await tool_b.execute(call)
        self.assertIsNotNone(manager.get_by_id("reflexion:1"))

    async def test_primitives_appear_in_render_primitives_zone(self) -> None:
        tool, manager = self._tool()
        call = self._call(critique="c", correction_plan="p")
        await tool.execute(call)
        rendered = manager.render_primitives_zone()
        self.assertIn("reflexion:1", rendered)
        self.assertIn("Reflexion Note", rendered)


# ---------------------------------------------------------------------------
# Null optional fields on chain-of-thought event tools
# ---------------------------------------------------------------------------


class CotEventNullOptionalTests(unittest.IsolatedAsyncioTestCase):
    """@intent null-optional-arg-means-default: a null optional field behaves like the omitted key."""

    async def _record(self, tool_class, tool_name: str, arguments: dict):
        manager = ContextManager()
        result = await tool_class(manager).execute(ToolCall(tool_name=tool_name, arguments=arguments))
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        return result, manager.get_by_id(f"{tool_name}:1")

    async def test_backtrack_null_salvage_uses_default(self) -> None:
        args = {
            "abandoning": "path",
            "reason": "r",
            "evidence": "e",
            "attempted_result": "a",
            "replacement_plan": "p",
            "loop_guard": "g",
        }
        omitted_result, omitted = await self._record(BacktrackTool, "backtrack", args)
        null_result, nulled = await self._record(BacktrackTool, "backtrack", {**args, "salvage": None})
        self.assertEqual(nulled.salvage, DEFAULT_SALVAGE)
        self.assertEqual(null_result.output, omitted_result.output)
        self.assertNotIn("None", null_result.output)

    async def test_uncertainty_null_optionals_render_like_omitted(self) -> None:
        args = {
            "next_step": 0.7,
            "on_track": 0.6,
            "progress": "progressing",
            "uncertainty_source": "s",
            "next_action": "n",
        }
        nulls = {"trigger": None, "blocker": None, "reassessment_condition": None}
        omitted_result, omitted = await self._record(UncertaintyTool, "uncertainty", args)
        null_result, nulled = await self._record(UncertaintyTool, "uncertainty", {**args, **nulls})
        self.assertEqual((nulled.trigger, nulled.blocker, nulled.reassessment_condition), ("", "", ""))
        self.assertEqual(null_result.output, omitted_result.output)
        self.assertNotIn("None", null_result.output)


# ---------------------------------------------------------------------------
# Note tools sharing one ContextManager
# ---------------------------------------------------------------------------


class SharedManagerNoteIdTests(unittest.IsolatedAsyncioTestCase):
    """Two instances of one note tool on a shared manager must never overwrite each other."""

    async def _run_twice(self, factory, tool_name: str, first: dict, second: dict) -> ContextManager:
        manager = ContextManager()
        first_result = await factory(manager).execute(ToolCall(tool_name=tool_name, arguments=first))
        second_result = await factory(manager).execute(ToolCall(tool_name=tool_name, arguments=second))
        self.assertEqual(first_result.status, ToolStatus.SUCCESS, first_result.output)
        self.assertEqual(second_result.status, ToolStatus.SUCCESS, second_result.output)
        return manager

    async def test_reflexion_keeps_both_notes(self) -> None:
        manager = await self._run_twice(
            ReflexionTool,
            "reflexion",
            {"critique": "first critique", "correction_plan": "p"},
            {"critique": "second critique", "correction_plan": "p"},
        )
        self.assertEqual(manager.get_by_id("reflexion:1").critique, "first critique")
        self.assertEqual(manager.get_by_id("reflexion:2").critique, "second critique")

    async def test_trajectory_checkpoint_keeps_both_notes_and_syncs_index(self) -> None:
        manager = await self._run_twice(
            TrajectoryCheckpointTool,
            "trajectory_checkpoint",
            {"reasoning_summary": "first", "trajectory": "t", "output": "o"},
            {"reasoning_summary": "second", "trajectory": "t", "output": "o"},
        )
        first = manager.get_by_id("trajectory_checkpoint:1")
        second = manager.get_by_id("trajectory_checkpoint:2")
        self.assertEqual((first.reasoning_summary, first.checkpoint_index), ("first", 1))
        self.assertEqual((second.reasoning_summary, second.checkpoint_index), ("second", 2))

    async def test_cot_event_tool_keeps_both_notes(self) -> None:
        args = {
            "reason": "r",
            "evidence": "e",
            "attempted_result": "a",
            "replacement_plan": "p",
            "loop_guard": "g",
        }
        manager = await self._run_twice(
            BacktrackTool,
            "backtrack",
            {**args, "abandoning": "first path"},
            {**args, "abandoning": "second path"},
        )
        self.assertEqual(manager.get_by_id("backtrack:1").abandoning, "first path")
        self.assertEqual(manager.get_by_id("backtrack:2").abandoning, "second path")

    async def test_single_step_reasoning_tool_keeps_both_notes(self) -> None:
        args = {"premises": ["p"], "inference_rule": "modus ponens", "soundness_caveat": "c"}
        manager = await self._run_twice(
            DeduceTool,
            "deduce",
            {**args, "conclusion": "first"},
            {**args, "conclusion": "second"},
        )
        self.assertEqual(manager.get_by_id("deduce:1").conclusion, "first")
        self.assertEqual(manager.get_by_id("deduce:2").conclusion, "second")


if __name__ == "__main__":
    unittest.main()
