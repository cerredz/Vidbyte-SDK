"""FILE: tests/features/harness_threads/test_harness_threads_process_bounds.py

PURPOSE: Every run is bounded and leaves nothing behind: a run past config.timeout_seconds raises <harness>.timed_out within the stop bound with its whole process tree gone (AC-9, INV-8, EC-15), the Muse serve exchange is bounded by NATIVE_CONTROL_TIMEOUT_SECONDS, stdout past its cap raises <harness>.output_too_large (EC-17), answer text past NATIVE_RESULT_TEXT_MAX_CHARS is cut and flagged (EC-31), caller cancellation propagates unchanged after the tree is stopped and the Muse temp folder removed (AC-11, INV-9, EC-16), even when it lands while Muse is still copying skills into that folder (review R-10), also when a second cancel follows (review R-30), a timeout or output cap still reports what the vendor printed on stderr, without the key (INV-5 element 6, review R-6), a vendor that exits with its answer while a grandchild holds its pipes still returns that answer at once (AC-2, review R-11), and each failure carries the newest thread id the vendor had printed (AC-21, INV-5, D-27).
ROLE IN CODEBASE: Start here when a call hangs, outlives its timeout, leaks a vendor process, or reports the wrong thread for a failed run.
ARCHITECTURE NOTE: The stand-in holds until a release file appears or its 30-second limit passes, and can start a grandchild that inherits its pipes, so only a whole-tree stop ends it. Liveness is checked on win32 too (OpenProcess/GetExitCodeProcess). NATIVE_KILL_WAIT_SECONDS and NATIVE_CONTROL_TIMEOUT_SECONDS are shrunk through the constants module, as spec §13 allows.
FUNCTION INVENTORY: tree_pids lists the stand-in leader and grandchild pids; stop_grandchildren ends any grandchild that outlived its leader; held_copy holds the Muse skill copy at os.makedirs until the test opens its gate; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Keep every bound as timeout + a few kill waits + SLACK_SECONDS; never a fixed sleep.
WHAT NOT TO DO IN THIS FILE: Do not raise the stand-in's hold limit; a broken stop should fail the elapsed-time assertion, not hang the suite.
KNOWN EDGE CASES: The cap tests write just past the real caps (4 MiB for Grok, 64 MiB for opencode and Muse), because only the three timing knobs are documented as monkeypatchable. The cancellation test reads liveness once, right as CancelledError arrives, with no grace (review R-24). The cancel-during-preparation test holds the skill copy at os.makedirs, the standard-library call copytree makes for each copied folder, and opens that gate right after cancelling, so a fix that waits for the copy cannot deadlock. On win32 a grandchild that outlives its leader cannot be reached by a tree stop, so the R-11 test ends it itself. The double-cancel test polls for the folder to go, because CancelledError may reach the caller before the removal ends (review R-30).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-5, INV-8, INV-9, §6.2 AC-2, AC-9, AC-11, AC-21, §6.3 EC-15 to EC-17, EC-31, §13; docs/spec/harness-thread-functions/review.md R-6, R-10, R-11, R-24, R-30
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_process_bounds.py
"""

from __future__ import annotations

import asyncio
import os
import signal
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

HARNESSES = ("grok", "opencode", "muse")
EXEC_ROLES = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}
CAP_NAMES = {"grok": "GROK_CLI_MAX_OUTPUT_BYTES", "opencode": "NATIVE_PROCESS_MAX_OUTPUT_BYTES", "muse": "NATIVE_PROCESS_MAX_OUTPUT_BYTES"}
TIMEOUT = 1.5
HELD_PIPE_TIMEOUT = 12.0
GATE_SECONDS = 30.0
HELD_SKILL = "slow-skill"
CANCEL_SPACING_SECONDS = 0.1
REMOVAL_SECONDS = 5.0
FLOOD_EXTRA_BYTES = 65536
DEVICE_LOGIN = "Waiting for the device login at https://accounts.example/device"


def tree_pids(sandbox, role: str) -> list[int]:
    return [record["pid"] for record in sandbox.starts(role)] + [record["grandchild_pid"] for record in sandbox.records("grandchild")]


@pytest.fixture
def held_copy(monkeypatch) -> Iterator[SimpleNamespace]:
    # R-10 / R-30: copytree makes each copied folder through
    # os.makedirs, looked up when it runs, so the copy of HELD_SKILL
    # waits for the gate. The gate is always opened at teardown.
    hold = SimpleNamespace(entered=threading.Event(), gate=threading.Event())
    real_makedirs = os.makedirs

    def held_makedirs(name, *args, **kwargs):
        if Path(name).name == HELD_SKILL:
            hold.entered.set()
            hold.gate.wait(GATE_SECONDS)
        return real_makedirs(name, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", held_makedirs)
    yield hold
    hold.gate.set()


def stop_grandchildren(sandbox, alive) -> None:
    # A grandchild that outlived its leader is ended here, so a run
    # that leaves one behind cannot hold the suite's pipes or tmp.
    for record in sandbox.records("grandchild"):
        if alive(record["grandchild_pid"]):
            os.kill(record["grandchild_pid"], signal.SIGTERM)


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "mode", "printed"), [
    ("grok", "hold", False), ("opencode", "hold", False), ("opencode", "session_then_hold", True),
    ("muse", "hold", False), ("muse", "session_then_hold", True),
])
async def test_run_past_its_timeout_is_timed_out_with_its_tree_stopped(api, sandbox, call, check_error, fast_stop, alive, wait_until, harness, mode, printed) -> None:
    # AC-9 / INV-8 / EC-15 / AC-21: timed_out within timeout + stop
    # bound; leader and grandchild gone; the printed thread id is kept.
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
    # INV-5 / D-27: Grok prints its id only at exit, so a failed
    # continue carries the caller's id.
    first = await call("grok")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok", "continue", "Again.", thread_id=first.thread_id, fake={"mode": "hold"}, config={"timeout_seconds": TIMEOUT})
    check_error(caught.value, harness="grok", verb="continue", code="grok.timed_out", workspace=sandbox.workspace, thread_id=first.thread_id)


@pytest.mark.asyncio
async def test_muse_fork_that_times_out_in_exec_carries_the_new_thread(api, sandbox, call, check_error, fast_stop) -> None:
    # AC-21 / INV-5: once session/fork answered, a failure carries the
    # fork's new id.
    first = await call("muse")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "fork", "Branch.", thread_id=first.thread_id, fake={"mode": "hold"}, config={"timeout_seconds": TIMEOUT})
    forked = sandbox.records("forked")
    assert len(forked) == 1
    check_error(caught.value, harness="muse", verb="fork", code="muse.timed_out", workspace=sandbox.workspace, thread_id=forked[0]["session"])


@pytest.mark.asyncio
async def test_muse_serve_exchange_is_bounded_by_the_control_timeout(api, sandbox, call, check_error, fast_stop, alive, wait_until, monkeypatch) -> None:
    # INV-8 / INV-6: the serve exchange passing
    # NATIVE_CONTROL_TIMEOUT_SECONDS is muse.timed_out, even with a long
    # run timeout; no exec starts.
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
    # EC-17 / INV-8 / AC-21: the cut stream is never parsed as an
    # answer; the cap is named; a printed thread id is kept.
    cap = getattr(api.constants, cap_name)
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, fake={"mode": mode, "flood_bytes": cap + FLOOD_EXTRA_BYTES})
    thread_id = sandbox.records("session")[0]["session"] if printed else None
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.output_too_large", workspace=sandbox.workspace, thread_id=thread_id, observations=[("byte cap", (str(cap), f"{cap:,}"))])


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_answer_text_past_the_cap_is_cut_and_flagged(api, call, harness) -> None:
    # EC-31 / INV-8: text cut at NATIVE_RESULT_TEXT_MAX_CHARS with
    # text_truncated True; exactly the cap is not truncated.
    cap = api.constants.NATIVE_RESULT_TEXT_MAX_CHARS
    letter = harness[0]
    over = await call(harness, fake={"mode": "long_text", "text_chars": cap + 5})
    assert over.text == letter * cap and over.text_truncated is True
    exact = await call(harness, fake={"mode": "long_text", "text_chars": cap})
    assert exact.text == letter * cap and exact.text_truncated is False


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_cancellation_propagates_after_the_tree_is_stopped(sandbox, call, fast_stop, alive, wait_until, harness) -> None:
    # AC-11 / INV-9 / EC-16: CancelledError reaches the caller
    # unchanged, no process from the call is left, the Muse temp folder
    # is gone.
    task = asyncio.create_task(call(harness, fake={"mode": "hold", "grandchild": True}))
    assert await wait_until(lambda: bool(sandbox.records("grandchild")), 30.0), "the stand-in never started"
    pids = tree_pids(sandbox, EXEC_ROLES[harness])
    assert len(pids) == 2
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as caught:
        await task
    # R-24: liveness is read once, the moment CancelledError arrives,
    # so a stop that finishes only after it propagates fails here.
    survivors = [pid for pid in pids if alive(pid)]
    assert survivors == [], "INV-9: the tree is stopped before CancelledError propagates"
    assert type(caught.value) is asyncio.CancelledError
    assert time.monotonic() - started < 4 * fast_stop.kill_wait + fast_stop.slack
    assert list(sandbox.tmp.iterdir()) == [], "INV-9: the Muse temp folder is removed"


@pytest.mark.asyncio
async def test_muse_cancelled_while_preparing_its_config_folder_leaves_no_temp_folder(sandbox, call, held_copy, wait_until) -> None:
    # AC-11 / INV-9 / R-10: a cancel that lands while the skills are
    # copied into the temp config folder still removes that folder
    # before CancelledError reaches the caller, and nothing starts.
    skill = sandbox.make_skill(HELD_SKILL)
    task = asyncio.create_task(call("muse", skills=[skill]))
    try:
        assert await wait_until(held_copy.entered.is_set, 30.0), "the skill copy never started"
        task.cancel()
    finally:
        held_copy.gate.set()
    with pytest.raises(asyncio.CancelledError) as caught:
        await task
    left = sorted(path.relative_to(sandbox.tmp).as_posix() for path in sandbox.tmp.rglob("*"))
    assert left == [], "INV-9 / R-10: the temp config folder outlived the cancelled call"
    assert type(caught.value) is asyncio.CancelledError
    assert sandbox.starts() == []


@pytest.mark.asyncio
async def test_muse_cancelled_twice_while_preparing_its_config_folder_leaves_no_temp_folder(sandbox, call, held_copy, wait_until) -> None:
    # AC-11 / INV-9 / R-30: a second cancel, landing while the first
    # waits for the skill copy, must not stop the folder's removal.
    # CancelledError may arrive before the removal ends, so the test
    # polls for the folder to go instead of reading it at that moment.
    skill = sandbox.make_skill(HELD_SKILL)
    task = asyncio.create_task(call("muse", skills=[skill]))
    try:
        assert await wait_until(held_copy.entered.is_set, 30.0), "the skill copy never started"
        for _ in range(2):
            task.cancel()
            # The held copy keeps the window open, so this pause only
            # lets each cancel reach the call before the next one.
            await asyncio.sleep(CANCEL_SPACING_SECONDS)
    finally:
        held_copy.gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    removed = await wait_until(lambda: not any(sandbox.tmp.iterdir()), REMOVAL_SECONDS)
    left = sorted(path.relative_to(sandbox.tmp).as_posix() for path in sandbox.tmp.rglob("*"))
    assert removed, f"INV-9 / R-30: the temp config folder outlived a twice-cancelled call: {left}"
    assert sandbox.starts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize("mode", ["hold", "flood"])
async def test_timeout_and_output_cap_report_the_vendors_stderr_without_the_key(api, sandbox, call, check_error, fast_stop, pack, harness, mode) -> None:
    # INV-5 element 6 / R-6: a hang or a flood still reports what the
    # vendor printed on stderr, with the caller's key scrubbed out.
    fake = {"mode": mode, "stderr_text": f"{DEVICE_LOGIN} (key {pack.API_KEY})"}
    config = {"timeout_seconds": TIMEOUT}
    code = f"{harness}.timed_out"
    if mode == "flood":
        fake["flood_bytes"] = getattr(api.constants, CAP_NAMES[harness]) + FLOOD_EXTRA_BYTES
        config, code = {}, f"{harness}.output_too_large"
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, fake=fake, config=config)
    error = caught.value
    assert error.failure_code.value == code
    assert error.vendor_message and DEVICE_LOGIN in error.vendor_message, f"INV-5 / R-6: {code} left out the vendor's stderr"
    check_error(error, harness=harness, verb="run", code=code, workspace=sandbox.workspace, vendor=DEVICE_LOGIN)
    for text in (str(error), repr(error), error.vendor_message):
        assert pack.API_KEY not in text, "INV-2: the key is scrubbed from the vendor text"


@pytest.mark.asyncio
async def test_answer_returns_when_the_vendor_exits_while_a_grandchild_holds_its_pipes(sandbox, call, fast_stop, alive, pack) -> None:
    # AC-2 / INV-8 / R-11: the run ends when the vendor exits, not when
    # every copy of its pipes closes, so its answer is kept.
    started = time.monotonic()
    try:
        result = await call("grok", fake={"grandchild": True}, config={"timeout_seconds": HELD_PIPE_TIMEOUT})
    finally:
        elapsed = time.monotonic() - started
        stop_grandchildren(sandbox, alive)
    assert elapsed < 4 * fast_stop.kill_wait + fast_stop.slack
    assert result.thread_id == sandbox.answers("grok")[0]["session"]
    assert result.text == f"grok answer to: {pack.PROMPT}"
