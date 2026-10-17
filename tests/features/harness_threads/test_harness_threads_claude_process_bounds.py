"""FILE: tests/features/harness_threads/test_harness_threads_claude_process_bounds.py

PURPOSE: Every Claude Code run is bounded and leaves nothing behind (spec claude-thread-functions INV-9, INV-10): a run past ClaudeThreadConfig.timeout_seconds raises claude.timed_out within the stop bound with its whole process tree gone, naming the seconds waited and Claude's stderr without the key (AC-15, EC-14), a run timed out before printing reports no thread while a timed-out continue or fork reports the caller's id (EC-14, D-9), a run or fork that printed a valid answer and then hung reports the printed id and a continue the caller's (r4 INV-6, S4 R-3), stdout past NATIVE_PROCESS_MAX_OUTPUT_BYTES raises claude.output_too_large naming the cap and carrying Claude's stderr (AC-15, EC-15, r4 S4 R-1), answer text past NATIVE_RESULT_TEXT_MAX_CHARS is cut and flagged (INV-9), and caller cancellation propagates unchanged after the tree is stopped (AC-16, EC-33).
ROLE IN CODEBASE: Start here when a Claude call hangs, outlives its timeout, leaks a claude process, or reports the wrong thread for a run it stopped.
ARCHITECTURE NOTE: The stand-in holds until a release file appears or its 30-second limit passes, and can start a grandchild that inherits its pipes, so only a whole-tree stop ends it. NATIVE_KILL_WAIT_SECONDS is shrunk through the constants module (fast_stop), as spec §13 allows. Liveness is checked on win32 too (OpenProcess/GetExitCodeProcess).
FUNCTION INVENTORY: tree_pids lists the stand-in leader and grandchild pids; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Keep every bound as timeout + a few kill waits + SLACK_SECONDS; never a fixed sleep.
WHAT NOT TO DO IN THIS FILE: Do not raise the stand-in's hold limit; a broken stop should fail the elapsed-time assertion, not hang the suite.
KNOWN EDGE CASES: The cap test writes just past the real 64 MiB cap, because only the timing knobs are documented as monkeypatchable. The cancellation test reads liveness once, right as CancelledError arrives, with no grace (as #1036's R-24). A task left holding an unretrieved exception is finalised by the garbage collector, and on Python 3.11.0 its log traceback re-enters ast.parse while pytest is already parsing a source for a report (SystemError: AST constructor recursion depth mismatch), so the cancellation test awaits a call that ended early.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-6, INV-9, INV-10, §6.2 AC-15, AC-16, §6.3 EC-14, EC-15, EC-33, §8.1 D-9, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_process_bounds.py
"""

from __future__ import annotations

import asyncio
import time

import pytest

TIMEOUT = 1.5
# S4 R-3: long enough for the stand-in to start and print its answer
# on a loaded machine before the SDK stops it; a stand-in stopped
# before printing fails on its own assertion, not on the thread id.
PRINTED_TIMEOUT = 3.0
BACKGROUND_NOTICE = "Claude Code is still finishing background work"
FLOOD_NOTICE = "Claude Code: output limit notice"
FLOOD_EXTRA_BYTES = 65536
DEVICE_NOTICE = "Waiting for the API to answer the first request"


def tree_pids(sandbox) -> list[int]:
    return [record["pid"] for record in sandbox.starts("claude")] + [record["grandchild_pid"] for record in sandbox.records("grandchild")]


@pytest.mark.asyncio
async def test_run_past_its_timeout_is_timed_out_with_its_tree_stopped(api, sandbox, call, check_error, fast_stop, alive, wait_until, pack) -> None:
    # AC-15 / INV-9 / EC-14: claude.timed_out within timeout + stop
    # bound; leader and grandchild gone; no thread id (no JSON was
    # printed); Claude's stderr kept, without the key.
    started = time.monotonic()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "hold", "grandchild": True, "stderr_text": f"{DEVICE_NOTICE} (key {pack.API_KEY})"}, config={"timeout_seconds": TIMEOUT})
    assert time.monotonic() - started < TIMEOUT + 4 * fast_stop.kill_wait + fast_stop.slack
    error = caught.value
    check_error(error, harness="claude", verb="run", code="claude.timed_out", workspace=sandbox.workspace, thread_id=None, observations=[("seconds waited", (str(TIMEOUT),))], vendor=DEVICE_NOTICE)
    for text in (str(error), repr(error), error.vendor_message or ""):
        assert pack.API_KEY not in text, "INV-3: the key is scrubbed from the vendor text"
    pids = tree_pids(sandbox)
    assert len(pids) == 2
    assert await wait_until(lambda: not any(alive(pid) for pid in pids), fast_stop.kill_wait + 1.0), "INV-9: the whole tree is stopped"


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["continue", "fork"])
async def test_continue_or_fork_that_times_out_carries_the_callers_thread(api, sandbox, call, check_error, fast_stop, verb) -> None:
    # EC-14 / D-9 / INV-6: Claude Code prints its id only at exit and
    # the SDK mints none, so a stopped continue or fork reports the id
    # it was given.
    first = await call("claude")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", verb, "Again.", thread_id=first.thread_id, fake={"mode": "hold"}, config={"timeout_seconds": TIMEOUT})
    check_error(caught.value, harness="claude", verb=verb, code="claude.timed_out", workspace=sandbox.workspace, thread_id=first.thread_id)


@pytest.mark.asyncio
async def test_stdout_past_the_cap_is_output_too_large_naming_it(api, sandbox, call, check_error) -> None:
    # AC-15 / EC-15 / INV-9: the cut stream is never parsed as an
    # answer; the 64 MiB cap is named.
    cap = api.constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "flood", "flood_bytes": cap + FLOOD_EXTRA_BYTES})
    check_error(caught.value, harness="claude", verb="run", code="claude.output_too_large", workspace=sandbox.workspace, thread_id=None, observations=[("byte cap", (str(cap), f"{cap:,}"))])


@pytest.mark.asyncio
async def test_stdout_past_the_cap_carries_claudes_stderr_as_the_vendor_text(api, sandbox, call, check_error) -> None:
    # S4 R-1 / INV-6 / INV-7 item 5 / EC-15 (r4): output_too_large
    # carries stderr as its vendor text, as Grok, opencode and Muse do
    # (G-4); nothing valid was printed, so a run has no thread id.
    cap = api.constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "flood", "flood_bytes": cap + FLOOD_EXTRA_BYTES, "stderr_text": FLOOD_NOTICE})
    check_error(caught.value, harness="claude", verb="run", code="claude.output_too_large", workspace=sandbox.workspace, thread_id=None, observations=[("byte cap", (str(cap), f"{cap:,}"))], vendor=FLOOD_NOTICE)


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["run", "continue", "fork"])
async def test_answer_printed_before_the_timeout_gives_the_newest_thread_id(api, sandbox, call, check_error, fast_stop, verb) -> None:
    # S4 R-3 / INV-6 / INV-7 item 4 / EC-14 / D-9 (r4): Claude Code
    # printed a valid answer and then did not exit. timed_out carries
    # the printed session_id for run and fork, the caller's id for
    # continue, and Claude's stderr as the vendor text.
    source = (await call("claude")).thread_id if verb != "run" else None
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", verb, "Again.", thread_id=source, fake={"mode": "answer_then_hold", "stderr_text": BACKGROUND_NOTICE}, config={"timeout_seconds": PRINTED_TIMEOUT})
    printed = sandbox.records("printed", "claude")
    assert len(printed) == 1, "the stand-in was stopped before it printed its answer; the machine is slower than PRINTED_TIMEOUT allows"
    session = printed[0]["session"]
    if verb == "fork":
        assert session != source, "the stand-in's fork printed a new id"
    expected = source if verb == "continue" else session
    check_error(caught.value, harness="claude", verb=verb, code="claude.timed_out", workspace=sandbox.workspace, thread_id=expected, observations=[("seconds waited", (str(PRINTED_TIMEOUT),))], vendor=BACKGROUND_NOTICE)


@pytest.mark.asyncio
async def test_answer_text_past_the_cap_is_cut_and_flagged(api, call) -> None:
    # INV-9: text cut at NATIVE_RESULT_TEXT_MAX_CHARS with
    # text_truncated True; exactly the cap is not truncated.
    cap = api.constants.NATIVE_RESULT_TEXT_MAX_CHARS
    over = await call("claude", fake={"mode": "long_text", "text_chars": cap + 5})
    assert over.text == "c" * cap and over.text_truncated is True
    exact = await call("claude", fake={"mode": "long_text", "text_chars": cap})
    assert exact.text == "c" * cap and exact.text_truncated is False


@pytest.mark.asyncio
async def test_cancellation_propagates_after_the_tree_is_stopped(sandbox, call, fast_stop, alive, wait_until) -> None:
    # AC-16 / INV-10 / EC-33: CancelledError reaches the caller
    # unchanged, never as a NativeThreadError, and no process from the
    # call is left.
    task = asyncio.create_task(call("claude", fake={"mode": "hold", "grandchild": True}))
    assert await wait_until(lambda: task.done() or bool(sandbox.records("grandchild")), 30.0), "the stand-in never started"
    if task.done():
        # The call ended before the stand-in held: report its own outcome.
        await task
        pytest.fail("the call returned before claude was cancelled")
    pids = tree_pids(sandbox)
    assert len(pids) == 2
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as caught:
        await task
    survivors = [pid for pid in pids if alive(pid)]
    assert survivors == [], "INV-10: the tree is stopped before CancelledError propagates"
    assert type(caught.value) is asyncio.CancelledError
    assert time.monotonic() - started < 4 * fast_stop.kill_wait + fast_stop.slack
