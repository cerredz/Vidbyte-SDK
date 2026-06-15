"""Verification script for issue #143: loop detection repeated output detection.

Runs every test case from the design doc Section 10 and exits non-zero on failure.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

from vidbyte.lib.dataclasses.middleware import MiddlewareAction, MiddlewareContext, MiddlewareHook
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult
from vidbyte.middleware.builtins import LoopDetectionMiddleware


_passed = 0
_failed = 0


def _report(name: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"{status}: {name}{suffix}")
    if ok:
        _passed += 1
    else:
        _failed += 1


def _ctx(**kwargs: Any) -> MiddlewareContext:
    defaults = dict(hook=MiddlewareHook.BEFORE_ITERATION, agent_name="test-agent")
    defaults.update(kwargs)
    return MiddlewareContext(**defaults)


def _tool_ctx(run_state: dict, name: str, args: dict | None = None, internal: bool = False) -> MiddlewareContext:
    return _ctx(
        hook=MiddlewareHook.BEFORE_TOOL_CALL,
        tool_call=ToolCall(tool_name=name, arguments=args or {}),
        tool_is_internal=internal,
        run_state=run_state,
    )


def _result_ctx(run_state: dict, tool_name: str, output: str, internal: bool = False) -> MiddlewareContext:
    return _ctx(
        hook=MiddlewareHook.AFTER_TOOL_CALL,
        tool_result=ToolResult.success(tool_name, output),
        tool_is_internal=internal,
        run_state=run_state,
    )


def _run_ctx(run_state: dict) -> MiddlewareContext:
    return _ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state)


async def test_aborts_on_threshold() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=3)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "content"))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "content"))
    d = await mw.after_tool_call(_result_ctx(rs, "read_file", "content"))
    _report("aborts when identical output seen max_repeated_outputs times",
            d.action == MiddlewareAction.ABORT_RUN and d.reason == "tool_output_loop_detected")


async def test_disabled_by_default() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware()
    await mw.before_run(_run_ctx(rs))
    d = MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="a")
    for _ in range(50):
        d = await mw.after_tool_call(_result_ctx(rs, "read_file", "same"))
    _report("default middleware does not abort on repeated output",
            d.action == MiddlewareAction.CONTINUE)


async def test_continues_below_threshold() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=4)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "content"))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "content"))
    d = await mw.after_tool_call(_result_ctx(rs, "read_file", "content"))
    _report("continues below threshold", d.action == MiddlewareAction.CONTINUE)


async def test_tools_counted_independently() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=2)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "x"))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "x"))
    d = await mw.after_tool_call(_result_ctx(rs, "glob", "x"))
    _report("tool A hitting threshold does not abort tool B",
            d.action == MiddlewareAction.CONTINUE)


async def test_non_consecutive_counted() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=3)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "no change"))
    await mw.after_tool_call(_result_ctx(rs, "glob", "[]"))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "no change"))
    await mw.after_tool_call(_result_ctx(rs, "glob", "[]"))
    d = await mw.after_tool_call(_result_ctx(rs, "read_file", "no change"))
    _report("non-consecutive identical outputs counted (A-B-A-B pattern)",
            d.action == MiddlewareAction.ABORT_RUN)


async def test_skips_internal_tools() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=2, skip_internal_tools=True)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "isDone", "done", internal=True))
    d = await mw.after_tool_call(_result_ctx(rs, "isDone", "done", internal=True))
    _report("internal tools skipped when skip_internal_tools=True",
            d.action == MiddlewareAction.CONTINUE)


async def test_tracks_internal_tools_when_enabled() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=2, skip_internal_tools=False)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "isDone", "done", internal=True))
    d = await mw.after_tool_call(_result_ctx(rs, "isDone", "done", internal=True))
    _report("internal tools tracked when skip_internal_tools=False",
            d.action == MiddlewareAction.ABORT_RUN)


async def test_skips_none_result() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=2)
    await mw.before_run(_run_ctx(rs))
    d = await mw.after_tool_call(_ctx(
        hook=MiddlewareHook.AFTER_TOOL_CALL, tool_result=None, run_state=rs
    ))
    _report("None tool_result does not raise or count",
            d.action == MiddlewareAction.CONTINUE)


async def test_empty_string_counted() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=2)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "grep", ""))
    d = await mw.after_tool_call(_result_ctx(rs, "grep", ""))
    _report("empty string output is counted",
            d.action == MiddlewareAction.ABORT_RUN)


async def test_metadata_complete() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=2)
    await mw.before_run(_run_ctx(rs))
    await mw.after_tool_call(_result_ctx(rs, "read_file", "same"))
    d = await mw.after_tool_call(_result_ctx(rs, "read_file", "same"))
    ok = (
        d.metadata.get("tool_name") == "read_file"
        and "output_hash" in d.metadata
        and d.metadata.get("repeated_count") == 2
        and "max_repeated_outputs" in d.metadata
    )
    _report("abort metadata contains tool_name, output_hash, repeated_count, max_repeated_outputs", ok)


def test_raises_on_max_repeated_outputs_one() -> None:
    raised = False
    try:
        LoopDetectionMiddleware(max_repeated_outputs=1)
    except ValueError:
        raised = True
    _report("ValueError raised when max_repeated_outputs=1", raised)


async def test_output_resets_on_new_run() -> None:
    rs_a: dict = {}
    rs_b: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_outputs=2)
    await mw.before_run(_run_ctx(rs_a))
    await mw.after_tool_call(_ctx(
        hook=MiddlewareHook.AFTER_TOOL_CALL,
        tool_result=ToolResult.success("read_file", "content"),
        run_state=rs_a,
    ))
    await mw.before_run(_run_ctx(rs_b))
    d = await mw.after_tool_call(_ctx(
        hook=MiddlewareHook.AFTER_TOOL_CALL,
        tool_result=ToolResult.success("read_file", "content"),
        run_state=rs_b,
    ))
    _report("output counts reset on new run (separate run_state)",
            d.action == MiddlewareAction.CONTINUE)


async def test_input_and_output_coexist() -> None:
    rs: dict = {}
    mw = LoopDetectionMiddleware(max_repeated_calls=2, max_repeated_outputs=5)
    await mw.before_run(_run_ctx(rs))
    await mw.before_tool_call(_tool_ctx(rs, "search", {"q": "x"}))
    d = await mw.before_tool_call(_tool_ctx(rs, "search", {"q": "x"}))
    _report("input loop abort fires correctly when both thresholds active",
            d.reason == "tool_loop_detected")


async def main() -> None:
    await test_aborts_on_threshold()
    await test_disabled_by_default()
    await test_continues_below_threshold()
    await test_tools_counted_independently()
    await test_non_consecutive_counted()
    await test_skips_internal_tools()
    await test_tracks_internal_tools_when_enabled()
    await test_skips_none_result()
    await test_empty_string_counted()
    await test_metadata_complete()
    test_raises_on_max_repeated_outputs_one()
    await test_output_resets_on_new_run()
    await test_input_and_output_coexist()

    total = _passed + _failed
    print(f"\n{_passed}/{total} tests passed")
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
