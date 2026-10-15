"""FILE: tests/features/harness_threads/test_harness_threads_process_bounds.py

PURPOSE: Every run is bounded and leaves nothing behind: a run past config.timeout_seconds raises <harness>.timed_out within the stop bound with its whole process tree gone (AC-9, INV-8, EC-15), the Muse serve exchange is bounded by NATIVE_CONTROL_TIMEOUT_SECONDS, stdout past its cap raises <harness>.output_too_large (EC-17), answer text past NATIVE_RESULT_TEXT_MAX_CHARS is cut and flagged (EC-31), caller cancellation propagates unchanged after the tree is stopped and the Muse temp folder removed (AC-11, INV-9, EC-16), and each failure carries the newest thread id the vendor had printed (AC-21, INV-5, D-27).
ROLE IN CODEBASE: Start here when a call hangs, outlives its timeout, leaks a vendor process, or reports the wrong thread for a failed run.
ARCHITECTURE NOTE: The stand-in holds until a release file appears or its 30-second limit passes, and can start a grandchild that inherits its pipes, so only a whole-tree stop ends it. Liveness is checked on win32 too (OpenProcess/GetExitCodeProcess). NATIVE_KILL_WAIT_SECONDS and NATIVE_CONTROL_TIMEOUT_SECONDS are shrunk through the constants module, as spec §13 allows.
FUNCTION INVENTORY: tree_pids lists the stand-in leader and grandchild pids; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Keep every bound as timeout + a few kill waits + SLACK_SECONDS; never a fixed sleep.
WHAT NOT TO DO IN THIS FILE: Do not raise the stand-in's hold limit; a broken stop should fail the elapsed-time assertion, not hang the suite.
KNOWN EDGE CASES: The cap tests write just past the real caps (4 MiB for Grok, 64 MiB for opencode and Muse), because only the three timing knobs are documented as monkeypatchable.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-5, INV-8, INV-9, §6.2 AC-9, AC-11, AC-21, §6.3 EC-15 to EC-17, EC-31, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_process_bounds.py
"""

from __future__ import annotations

import asyncio
import time

import pytest

HARNESSES = ("grok", "opencode", "muse")
EXEC_ROLES = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}
TIMEOUT = 1.5
FLOOD_EXTRA_BYTES = 65536


def tree_pids(sandbox, role: str) -> list[int]:
    return [record["pid"] for record in sandbox.starts(role)] + [record["grandchild_pid"] for record in sandbox.records("grandchild")]


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "mode", "printed"), [
    ("grok", "hold", False), ("opencode", "hold", False), ("opencode", "session_then_hold", True),
    ("muse", "hold", False), ("muse", "session_then_hold", True),
])
async def test_run_past_its_timeout_is_timed_out_with_its_tree_stopped(api, sandbox, call, check_error, fast_stop, alive, wait_until, harness, mode, printed) -> None:
    # AC-9 / INV-8 / EC-15 / AC-21: timed_out within timeout + stop bound; leader and grandchild gone; the printed thread id is kept.
    started = time.monotonic()
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, fake={"mode": mode, "grandchild": True}, config={"timeout_seconds": TIMEOUT})
    assert time.monotonic() - started < TIMEOUT + 4 * fast_stop.kill_wait + fast_stop.slack
    thread_id = sandbox.records("session")[0]["session"] if printed else None
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.timed_out", workspace=sandbox.workspace, thread_id=thread_id, observations=[("seconds waited", (str(TIMEOUT),))])
    pids = tree_pids(sandbox, EXEC_ROLES[harness])
    assert len(pids) == 2
    assert await wait_until(lambda: not any(alive(pid) for pid in pids), fast_stop.kill_wait + 1.0), "INV-8: the whole tree is stopped"


@pytest.mark.asyncio
async def test_grok_continue_that_times_out_carries_the_callers_thread(api, sandbox, call, check_error, fast_stop) -> None:
    # INV-5 / D-27: Grok prints its id only at exit, so a failed continue carries the caller's id.
    first = await call("grok")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok", "continue", "Again.", thread_id=first.thread_id, fake={"mode": "hold"}, config={"timeout_seconds": TIMEOUT})
    check_error(caught.value, harness="grok", verb="continue", code="grok.timed_out", workspace=sandbox.workspace, thread_id=first.thread_id)


@pytest.mark.asyncio
async def test_muse_fork_that_times_out_in_exec_carries_the_new_thread(api, sandbox, call, check_error, fast_stop) -> None:
    # AC-21 / INV-5: once session/fork answered, a failure carries the fork's new id.
    first = await call("muse")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "fork", "Branch.", thread_id=first.thread_id, fake={"mode": "hold"}, config={"timeout_seconds": TIMEOUT})
    forked = sandbox.records("forked")
    assert len(forked) == 1
    check_error(caught.value, harness="muse", verb="fork", code="muse.timed_out", workspace=sandbox.workspace, thread_id=forked[0]["session"])


@pytest.mark.asyncio
async def test_muse_serve_exchange_is_bounded_by_the_control_timeout(api, sandbox, call, check_error, fast_stop, alive, wait_until, monkeypatch) -> None:
    # INV-8 / INV-6: the serve exchange passing NATIVE_CONTROL_TIMEOUT_SECONDS is muse.timed_out, even with a long run timeout; no exec starts.
    monkeypatch.setattr(api.constants, "NATIVE_CONTROL_TIMEOUT_SECONDS", TIMEOUT)
    started = time.monotonic()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "continue", "Again.", thread_id="0192f0c4-aaaa-7bbb-8ccc-dddddddddddd", fake={"serve_mode": "hold"}, config={"timeout_seconds": 600.0})
    assert time.monotonic() - started < TIMEOUT + 4 * fast_stop.kill_wait + fast_stop.slack
    check_error(caught.value, harness="muse", verb="continue", code="muse.timed_out", workspace=sandbox.workspace, thread_id="0192f0c4-aaaa-7bbb-8ccc-dddddddddddd", observations=[("seconds waited", (str(TIMEOUT),))])
    assert sandbox.starts("muse-exec") == []
    serve_pid = sandbox.only_start("muse-serve")["pid"]
    assert await wait_until(lambda: not alive(serve_pid), fast_stop.kill_wait + 1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "mode", "cap_name", "printed"), [
    ("grok", "flood", "GROK_CLI_MAX_OUTPUT_BYTES", False),
    ("opencode", "session_then_flood", "NATIVE_PROCESS_MAX_OUTPUT_BYTES", True),
    ("muse", "flood", "NATIVE_PROCESS_MAX_OUTPUT_BYTES", True),
])
async def test_stdout_past_its_cap_is_output_too_large(api, sandbox, call, check_error, harness, mode, cap_name, printed) -> None:
    # EC-17 / INV-8 / AC-21: the cut stream is never parsed as an answer; the cap is named; a printed thread id is kept.
    cap = getattr(api.constants, cap_name)
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, fake={"mode": mode, "flood_bytes": cap + FLOOD_EXTRA_BYTES})
    thread_id = sandbox.records("session")[0]["session"] if printed else None
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.output_too_large", workspace=sandbox.workspace, thread_id=thread_id, observations=[("byte cap", (str(cap), f"{cap:,}"))])


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_answer_text_past_the_cap_is_cut_and_flagged(api, call, harness) -> None:
    # EC-31 / INV-8: text cut at NATIVE_RESULT_TEXT_MAX_CHARS with text_truncated True; exactly the cap is not truncated.
    cap = api.constants.NATIVE_RESULT_TEXT_MAX_CHARS
    letter = harness[0]
    over = await call(harness, fake={"mode": "long_text", "text_chars": cap + 5})
    assert over.text == letter * cap and over.text_truncated is True
    exact = await call(harness, fake={"mode": "long_text", "text_chars": cap})
    assert exact.text == letter * cap and exact.text_truncated is False


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_cancellation_propagates_after_the_tree_is_stopped(sandbox, call, fast_stop, alive, wait_until, harness) -> None:
    # AC-11 / INV-9 / EC-16: CancelledError reaches the caller unchanged, no process from the call is left, the Muse temp folder is gone.
    task = asyncio.create_task(call(harness, fake={"mode": "hold", "grandchild": True}))
    assert await wait_until(lambda: bool(sandbox.records("grandchild")), 30.0), "the stand-in never started"
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as caught:
        await task
    assert type(caught.value) is asyncio.CancelledError
    assert time.monotonic() - started < 4 * fast_stop.kill_wait + fast_stop.slack
    pids = tree_pids(sandbox, EXEC_ROLES[harness])
    assert await wait_until(lambda: not any(alive(pid) for pid in pids), fast_stop.kill_wait + 1.0), "INV-9: the tree is stopped before CancelledError propagates"
    assert list(sandbox.tmp.iterdir()) == [], "INV-9: the Muse temp folder is removed"
