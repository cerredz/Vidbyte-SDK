"""Standalone verification script for context-algorithm-as-tools implementation.

Runs every test case from the Testing Plan in docs/design/context-algorithms-as-tools.md.
Prints PASS/FAIL per case and exits non-zero if any fail.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ReflexionContextItem, TrajectoryCheckpointContextItem
from vidbyte.tools.builtins.reflexion import ReflexionTool
from vidbyte.tools.builtins.trajectory_checkpoint import TrajectoryCheckpointTool
from vidbyte.tools.types import ToolCall, ToolStatus

_passed = 0
_failed = 0


def _check(name: str, condition: bool) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}")


def _tc_call(**kwargs) -> ToolCall:
    return ToolCall(tool_name="trajectory_checkpoint", arguments=kwargs)


def _rx_call(**kwargs) -> ToolCall:
    return ToolCall(tool_name="reflexion", arguments=kwargs)


# ---------------------------------------------------------------------------
# TrajectoryCheckpointContextItem
# ---------------------------------------------------------------------------

def test_trajectory_checkpoint_primitive() -> None:
    print("\n[TrajectoryCheckpointContextItem]")

    item = TrajectoryCheckpointContextItem(
        primitive_id="tc:1", iteration=0, checkpoint_index=1,
        reasoning_summary="analyzed", trajectory="step1→step2",
        output="result", score=0.8, feedback="keep going",
    )
    text = item.to_context_text()

    _check("to_context_text includes all 6 sections",
           all(s in text for s in ("Reasoning Summary", "Trajectory", "Output", "Score", "Feedback")))

    item_no_score = TrajectoryCheckpointContextItem(
        primitive_id="tc:2", iteration=0, checkpoint_index=2,
        reasoning_summary="r", trajectory="t", output="o",
        score=None, feedback="",
    )
    _check("score=None renders as N/A", "N/A" in item_no_score.to_context_text())

    item_scored = TrajectoryCheckpointContextItem(
        primitive_id="tc:3", iteration=0, checkpoint_index=3,
        reasoning_summary="r", trajectory="t", output="o",
        score=0.75, feedback="",
    )
    _check("score=0.75 renders as '0.75'", "0.75" in item_scored.to_context_text())

    long_item = TrajectoryCheckpointContextItem(
        primitive_id="tc:4", iteration=0, checkpoint_index=4,
        reasoning_summary="x" * 5000, trajectory="t", output="o",
        score=None, feedback="", max_chars=100,
    )
    _check("truncates to max_chars (&lt;=115)",
           len(long_item.to_context_text()) <= 115 and "truncated" in long_item.to_context_text())

    short_item = TrajectoryCheckpointContextItem(
        primitive_id="tc:5", iteration=0, checkpoint_index=5,
        reasoning_summary="short", trajectory="t", output="o",
        score=None, feedback="", max_chars=5000,
    )
    _check("does not truncate when under limit", "truncated" not in short_item.to_context_text())

    zero_item = TrajectoryCheckpointContextItem(
        primitive_id="tc:6", iteration=0, checkpoint_index=6,
        reasoning_summary="r", trajectory="t", output="o",
        score=None, feedback="", max_chars=0,
    )
    _check("max_chars=0 passes through untruncated",
           "truncated" not in zero_item.to_context_text() and "Reasoning Summary" in zero_item.to_context_text())


# ---------------------------------------------------------------------------
# ReflexionContextItem
# ---------------------------------------------------------------------------

def test_reflexion_primitive() -> None:
    print("\n[ReflexionContextItem]")

    item = ReflexionContextItem(primitive_id="r:1", critique="bad", correction_plan="fix it")
    text = item.to_context_text()
    _check("to_context_text includes critique and correction_plan",
           "Critique" in text and "Correction Plan" in text)

    no_attempt = ReflexionContextItem(primitive_id="r:2", critique="c", correction_plan="p", failed_attempt=None)
    _check("failed_attempt=None omits section", "Failed Attempt" not in no_attempt.to_context_text())

    with_attempt = ReflexionContextItem(
        primitive_id="r:3", critique="c", correction_plan="p", failed_attempt="tried linear"
    )
    _check("failed_attempt present when set",
           "Failed Attempt" in with_attempt.to_context_text() and "tried linear" in with_attempt.to_context_text())

    long_item = ReflexionContextItem(
        primitive_id="r:4", critique="c" * 2000, correction_plan="p" * 2000, max_chars=100
    )
    _check("truncates to max_chars (&lt;=115)",
           len(long_item.to_context_text()) <= 115 and "truncated" in long_item.to_context_text())


# ---------------------------------------------------------------------------
# TrajectoryCheckpointTool
# ---------------------------------------------------------------------------

async def test_trajectory_checkpoint_tool() -> None:
    print("\n[TrajectoryCheckpointTool]")

    manager = ContextManager()
    tool = TrajectoryCheckpointTool(manager)

    result = await tool.execute(_tc_call(reasoning_summary="r", trajectory="t", output="o", score="0.9", feedback="next"))
    _check("all fields: status=SUCCESS", result.status == ToolStatus.SUCCESS)
    _check("all fields: primitive written", manager.get_by_id("trajectory_checkpoint:1") is not None)
    _check("all fields: output is rendered text", "Reasoning Summary" in result.output)

    result2 = await tool.execute(_tc_call(trajectory="t", output="o"))
    _check("missing reasoning_summary → ERROR", result2.status == ToolStatus.ERROR and "reasoning_summary" in result2.output)

    result3 = await tool.execute(_tc_call(reasoning_summary="r", output="o"))
    _check("missing trajectory → ERROR", result3.status == ToolStatus.ERROR and "trajectory" in result3.output)

    result4 = await tool.execute(_tc_call(reasoning_summary="r", trajectory="t"))
    _check("missing output → ERROR", result4.status == ToolStatus.ERROR and "output" in result4.output)

    tool2 = TrajectoryCheckpointTool(ContextManager())
    await tool2.execute(_tc_call(reasoning_summary="r", trajectory="t", output="o", score="abc"))
    stored_bad = tool2._manager.get_by_id("trajectory_checkpoint:1")
    _check("invalid score 'abc' → score=None", stored_bad is not None and stored_bad.score is None)

    tool3 = TrajectoryCheckpointTool(ContextManager())
    await tool3.execute(_tc_call(reasoning_summary="r", trajectory="t", output="o", score="0.85"))
    stored_good = tool3._manager.get_by_id("trajectory_checkpoint:1")
    _check("score='0.85' coerces to float 0.85",
           stored_good is not None and abs(stored_good.score - 0.85) < 0.001)

    tool4 = TrajectoryCheckpointTool(ContextManager())
    await tool4.execute(_tc_call(reasoning_summary="r", trajectory="t", output="o", score="2.5"))
    stored_clamped = tool4._manager.get_by_id("trajectory_checkpoint:1")
    _check("score=2.5 clamped to 1.0",
           stored_clamped is not None and stored_clamped.score == 1.0)

    tool5 = TrajectoryCheckpointTool(ContextManager())
    await tool5.execute(_tc_call(reasoning_summary="r", trajectory="t", output="o"))
    await tool5.execute(_tc_call(reasoning_summary="r2", trajectory="t2", output="o2"))
    _check("two calls produce distinct IDs",
           tool5._manager.get_by_id("trajectory_checkpoint:1") is not None
           and tool5._manager.get_by_id("trajectory_checkpoint:2") is not None)

    manager_frozen = ContextManager()
    frozen = TrajectoryCheckpointContextItem(
        primitive_id="trajectory_checkpoint:1", iteration=0, checkpoint_index=1,
        reasoning_summary="r", trajectory="t", output="o", score=None, feedback="",
        primitive_frozen=True,
    )
    manager_frozen.upsert(frozen)
    tool_frozen = TrajectoryCheckpointTool(manager_frozen)
    result_frozen = await tool_frozen.execute(_tc_call(reasoning_summary="new", trajectory="t", output="o"))
    _check("frozen primitive → ERROR", result_frozen.status == ToolStatus.ERROR)

    _check("spec().name == 'trajectory_checkpoint'", tool.spec().name == "trajectory_checkpoint")

    validate_err = tool.validate_call(ToolCall(tool_name="trajectory_checkpoint", arguments={"output": "o"}))
    _check("validate_call catches missing required args", validate_err is not None)


# ---------------------------------------------------------------------------
# ReflexionTool
# ---------------------------------------------------------------------------

async def test_reflexion_tool() -> None:
    print("\n[ReflexionTool]")

    manager = ContextManager()
    tool = ReflexionTool(manager)

    result = await tool.execute(_rx_call(critique="bad", correction_plan="fix"))
    _check("required fields: status=SUCCESS", result.status == ToolStatus.SUCCESS)
    _check("required fields: primitive written", manager.get_by_id("reflexion:1") is not None)
    _check("required fields: output contains rendered text", "Critique" in result.output and "Correction Plan" in result.output)

    result2 = await tool.execute(_rx_call(correction_plan="p"))
    _check("missing critique → ERROR", result2.status == ToolStatus.ERROR and "critique" in result2.output)

    result3 = await tool.execute(_rx_call(critique="c"))
    _check("missing correction_plan → ERROR", result3.status == ToolStatus.ERROR and "correction_plan" in result3.output)

    result_fa = await tool.execute(_rx_call(critique="c", correction_plan="p", failed_attempt="tried X"))
    _check("failed_attempt present in output", "tried X" in result_fa.output)

    tool2 = ReflexionTool(ContextManager())
    result_no_fa = await tool2.execute(_rx_call(critique="c", correction_plan="p"))
    _check("no failed_attempt → section absent", "Failed Attempt" not in result_no_fa.output)

    tool3 = ReflexionTool(ContextManager())
    await tool3.execute(_rx_call(critique="c", correction_plan="p"))
    await tool3.execute(_rx_call(critique="c2", correction_plan="p2"))
    _check("two calls produce distinct IDs",
           tool3._manager.get_by_id("reflexion:1") is not None
           and tool3._manager.get_by_id("reflexion:2") is not None)

    manager_frozen2 = ContextManager()
    frozen_rx = ReflexionContextItem(
        primitive_id="reflexion:1", critique="c", correction_plan="p", primitive_frozen=True
    )
    manager_frozen2.upsert(frozen_rx)
    tool_frozen2 = ReflexionTool(manager_frozen2)
    result_frozen2 = await tool_frozen2.execute(_rx_call(critique="new", correction_plan="new plan"))
    _check("frozen primitive → ERROR", result_frozen2.status == ToolStatus.ERROR)

    _check("spec().name == 'reflexion'", tool.spec().name == "reflexion")

    tool_a = ReflexionTool(ContextManager())
    tool_b = ReflexionTool(ContextManager())
    await tool_a.execute(_rx_call(critique="c", correction_plan="p"))
    await tool_b.execute(_rx_call(critique="c", correction_plan="p"))
    _check("two instances have independent counters",
           tool_a._counter == 1 and tool_b._counter == 1)

    manager_render = ContextManager()
    tool_render = ReflexionTool(manager_render)
    await tool_render.execute(_rx_call(critique="c", correction_plan="p"))
    rendered = manager_render.render_primitives_zone()
    _check("primitive appears in render_primitives_zone",
           "reflexion:1" in rendered and "Reflexion Note" in rendered)


# ---------------------------------------------------------------------------
# Integration: round-trip
# ---------------------------------------------------------------------------

async def test_integration() -> None:
    print("\n[Integration]")

    manager = ContextManager()
    tc_tool = TrajectoryCheckpointTool(manager)
    rx_tool = ReflexionTool(manager)

    await tc_tool.execute(_tc_call(reasoning_summary="r", trajectory="t", output="o"))
    await rx_tool.execute(_rx_call(critique="c", correction_plan="p"))

    rendered = manager.render_primitives_zone()
    _check("both primitives appear in rendered zone",
           "trajectory_checkpoint:1" in rendered and "reflexion:1" in rendered)

    _check("trajectory item is TrajectoryCheckpointContextItem",
           isinstance(manager.get_by_id("trajectory_checkpoint:1"), TrajectoryCheckpointContextItem))
    _check("reflexion item is ReflexionContextItem",
           isinstance(manager.get_by_id("reflexion:1"), ReflexionContextItem))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    test_trajectory_checkpoint_primitive()
    test_reflexion_primitive()
    await test_trajectory_checkpoint_tool()
    await test_reflexion_tool()
    await test_integration()

    total = _passed + _failed
    print(f"\n{_passed}/{total} tests passed")
    if _failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
