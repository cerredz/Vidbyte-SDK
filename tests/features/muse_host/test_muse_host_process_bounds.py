"""FILE: tests/features/muse_host/test_muse_host_process_bounds.py

PURPOSE: Time and process bounds for MuseHost: an unresponsive peer fails within control timeout plus the NFR-2 stop bound for every function that talks to one (AC-3), cancellation propagates and stops what the call started (AC-4, EC-4), a cancelled wait leaves the turn running, __aexit__ interrupts live turns as HOST_CLOSED within its bound and never suppresses (EC-8), and a peer's grandchild is stopped with its tree (EC-10).
ROLE IN CODEBASE: Proves INV-2, INV-3, INV-4 and NFR-2 for vidbyte.harnesses.native.muse over the real NativePeer and McpStdioTransport, with fake_muse_peer.py as the child.
ARCHITECTURE NOTE: fast_stop shrinks NATIVE_STOP_GRACE_SECONDS and NATIVE_KILL_WAIT_SECONDS through the constants module, the seam spec §13 names; one test keeps the defaults to bind the 9 s figure. A stubborn fake ignores stdin EOF and, on POSIX, SIGTERM, so the whole stop sequence runs.
FUNCTION INVENTORY: peer_bound sums the NFR-2 peer stop bound; merged combines scenario parts; start_call starts one host call as a task; the test_* functions are one bound each.
COMMON MODIFICATION PATTERNS: A new function that starts a peer gets an entry in SILENT_CASES, and one in CANCEL_CASES when it can block.
WHAT NOT TO DO IN THIS FILE: 1. Do not check liveness on Windows; spec §13 says there is no portable equivalent, so those checks are POSIX-only. 2. Do not use fixed sleeps; poll with wait_until under a deadline.
KNOWN EDGE CASES: Upper bounds carry SLACK_SECONDS (2 s, NFR-2). A short-lived read peer runs no tools, so it has no in-distro reap; the WSL reap bound is covered in test_muse_host_wsl.py.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.1 INV-2 to INV-4, §6.3.2, §7 NFR-2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_process_bounds.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import pytest

KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
PROMPT = "List the top-level folders."
CONTROL_SECONDS = 0.5
STARTED_WITHIN_SECONDS = 20.0
WAIT_SECONDS = 30.0
DEFAULT_PEER_BOUND_SECONDS = 9.0
STUBBORN = {"ignore_eof": True, "ignore_term": True}
HELD_STUBBORN = {"ignore_eof": True, "ignore_term": True, "turn": {"mode": "hold", "on_interrupt": "ignore"}}
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="liveness checks are POSIX-only by spec §13; Windows has no portable equivalent")


def peer_bound(fast_stop: Any) -> float:
    # NFR-2: a peer stop takes at most G (after stdin EOF) + K (after TERM) + K (after KILL); tests add slack.
    return fast_stop.grace + 2 * fast_stop.kill_wait + fast_stop.slack


def merged(*parts: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for part in parts:
        for key, value in part.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value
    return result


def start_call(host: Any, api: Any, operation: str) -> Any:
    calls = {
        "check_muse_ready": lambda: host.check_muse_ready(),
        "list_muse_models": lambda: host.list_muse_models(),
        "spawn_muse_session": lambda: host.spawn_muse_session(api.MuseTurnRequest(prompt=PROMPT)),
        "continue_muse_session": lambda: host.continue_muse_session(KNOWN_SESSION, api.MuseTurnRequest(prompt=PROMPT)),
        "fork_muse_session": lambda: host.fork_muse_session(KNOWN_SESSION),
        "list_muse_sessions": lambda: host.list_muse_sessions(),
        "read_muse_session": lambda: host.read_muse_session(KNOWN_SESSION),
        "page_muse_session": lambda: host.page_muse_session(KNOWN_SESSION),
        "track_muse_session_usage": lambda: host.track_muse_session_usage(KNOWN_SESSION),
    }
    return asyncio.create_task(calls[operation]())


SILENT_CASES = {
    "check_muse_ready": "initialize",
    "list_muse_models": "model/list",
    "spawn_muse_session": "session/start",
    "continue_muse_session": "session/resume",
    "fork_muse_session": "session/fork",
    "list_muse_sessions": "session/list",
    "read_muse_session": "session/read",
    "page_muse_session": "view/page",
    "track_muse_session_usage": "view/page",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(SILENT_CASES))
async def test_unresponsive_peer_raises_server_unreachable_within_the_bound(operation: str, muse_api, muse_fake, make_muse_host, fast_stop, check_native_error, process_running) -> None:
    # AC-3 / EC-97: control timeout plus the NFR-2 stop bound for what the call started; on POSIX, nothing is left running.
    scenario = merged(STUBBORN, {"msp": {SILENT_CASES[operation]: {"mode": "silent"}}})
    async with make_muse_host(scenario, control_timeout_seconds=CONTROL_SECONDS) as host:
        started = time.monotonic()
        with pytest.raises(muse_api.NativeHostError) as caught:
            await start_call(host, muse_api, operation)
        elapsed = time.monotonic() - started
        pids = muse_fake.pids("peer")
        if sys.platform != "win32":
            assert pids and not any(process_running(pid) for pid in pids), "AC-3: every process the call started has exited"
    check_native_error(caught.value, code="muse.server_unreachable", token="control_timeout_seconds", operation=operation)
    assert elapsed < CONTROL_SECONDS + peer_bound(fast_stop)


@pytest.mark.asyncio
async def test_unresponsive_peer_bound_holds_with_default_timings(muse_api, make_muse_host) -> None:
    # NFR-2 with the defaults: 9 s for a call's peer (5 s grace + 1 s + 1 s + 2 s slack), plus the control timeout.
    assert muse_api.constants.NATIVE_STOP_GRACE_SECONDS == 5.0
    assert muse_api.constants.NATIVE_KILL_WAIT_SECONDS == 1.0
    scenario = merged(STUBBORN, {"msp": {"initialize": {"mode": "silent"}}})
    async with make_muse_host(scenario, control_timeout_seconds=CONTROL_SECONDS) as host:
        started = time.monotonic()
        with pytest.raises(muse_api.NativeHostError):
            await host.list_muse_models()
        elapsed = time.monotonic() - started
    assert elapsed < CONTROL_SECONDS + DEFAULT_PEER_BOUND_SECONDS


@pytest.mark.asyncio
@posix_only
async def test_short_lived_peer_is_reaped_before_the_read_returns(muse_api, muse_fake, make_muse_host, fast_stop, process_running) -> None:
    # INV-4: a short-lived peer is closed before the method that started it returns, even when it ignores EOF.
    async with make_muse_host(STUBBORN) as host:
        catalog = await host.list_muse_models()
        pids = muse_fake.pids("peer")
        assert pids and not any(process_running(pid) for pid in pids)
    assert [model.model_id for model in catalog.models] == ["muse-large", "muse-fast"]


CANCEL_CASES = {
    "spawn_muse_session": ({"msp": {"session/start": {"mode": "silent"}}}, "session/start"),
    "continue_muse_session": ({"msp": {"session/resume": {"mode": "silent"}}}, "session/resume"),
    "list_muse_sessions": ({"msp": {"session/list": {"mode": "silent"}}}, "session/list"),
    "check_muse_ready": ({"version": {"hold": True}}, None),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(CANCEL_CASES))
async def test_cancelling_a_call_propagates_and_stops_what_it_started(operation: str, muse_api, muse_fake, make_muse_host, fast_stop, wait_until, process_running) -> None:
    # AC-4 / EC-4 / INV-2: CancelledError propagates, and every process the call started is stopped.
    scenario, waiting_on = CANCEL_CASES[operation]
    async with make_muse_host(merged(STUBBORN, scenario), control_timeout_seconds=60.0) as host:
        task = start_call(host, muse_api, operation)
        if waiting_on is None:
            reached = await wait_until(lambda: bool(muse_fake.launches("version")), STARTED_WITHIN_SECONDS)
        else:
            reached = await wait_until(lambda: bool(muse_fake.received(waiting_on)), STARTED_WITHIN_SECONDS)
        assert reached, "the call reached the fake before it was cancelled"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert muse_fake.received("turn/start") == [], "a cancelled call starts no turn"
        if sys.platform != "win32":
            pids = muse_fake.pids()
            stopped = await wait_until(lambda: not any(process_running(pid) for pid in pids), peer_bound(fast_stop))
            assert stopped, f"processes left running after cancelling {operation}"


@pytest.mark.asyncio
async def test_cancelling_a_wait_leaves_the_turn_running(muse_api, muse_fake, make_muse_host, fast_stop, wait_until) -> None:
    # AC-4 for wait_* / INV-12: the turn keeps running and a later wait returns its result.
    async with make_muse_host({"turn": {"mode": "hold"}}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        waiter = asyncio.create_task(host.wait_muse_turn(handle, timeout_seconds=60))
        assert await wait_until(lambda: bool(muse_fake.received("turn/start")), STARTED_WITHIN_SECONDS)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        with pytest.raises(muse_api.NativeHostError) as still_running:
            await host.wait_muse_turn(handle, timeout_seconds=0.3)
        assert still_running.value.failure_code is muse_api.FailureCode.MUSE_TURN_TIMED_OUT
        assert muse_fake.received("turn/interrupt") == []
        muse_fake.release()
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_aexit_interrupts_live_turns_as_host_closed_within_the_bound(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-8: interrupt each live turn, wait at most G, close every peer concurrently; turns end INTERRUPTED/HOST_CLOSED.
    host = make_muse_host(HELD_STUBBORN)
    async with host:
        handles = [await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT)) for _ in range(2)]
        waiters = [asyncio.create_task(host.wait_muse_turn(handle, timeout_seconds=60)) for handle in handles]
        await asyncio.sleep(0)
        started = time.monotonic()
    elapsed = time.monotonic() - started
    results = await asyncio.gather(*waiters)
    assert [result.status for result in results] == [muse_api.NativeTurnStatus.INTERRUPTED] * 2
    assert [result.interrupt_source for result in results] == [muse_api.InterruptSource.HOST_CLOSED] * 2
    assert len(muse_fake.received("turn/interrupt")) == 2
    assert elapsed < fast_stop.grace + peer_bound(fast_stop), "peers close concurrently, so two cost no more than one"


@pytest.mark.asyncio
@posix_only
async def test_aexit_leaves_no_process_running(muse_api, muse_fake, make_muse_host, fast_stop, process_running) -> None:
    # NFR-2: when __aexit__ returns, no process the host started is alive.
    async with make_muse_host(HELD_STUBBORN) as host:
        await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
    pids = muse_fake.pids()
    assert pids and not any(process_running(pid) for pid in pids)


@pytest.mark.asyncio
async def test_aexit_never_suppresses_the_body_exception(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-8: __aexit__ raises nothing of its own and never swallows the exception it was given.
    with pytest.raises(LookupError, match="body failure"):
        async with make_muse_host({"turn": {"mode": "hold"}}) as host:
            await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
            raise LookupError("body failure")
    assert muse_fake.received("turn/interrupt"), "the live turn was interrupted on the error path too"


@pytest.mark.asyncio
async def test_aexit_on_cancellation_still_stops_the_turn(muse_api, muse_fake, make_muse_host, fast_stop, wait_until, process_running) -> None:
    # EC-8 / INV-4: __aexit__ runs its stop sequence even when it runs because of cancellation.
    spawned = asyncio.Event()
    host = make_muse_host(HELD_STUBBORN)

    async def body() -> None:
        async with host:
            await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
            spawned.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(body())
    await asyncio.wait_for(spawned.wait(), timeout=STARTED_WITHIN_SECONDS)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert muse_fake.received("turn/interrupt")
    if sys.platform != "win32":
        pids = muse_fake.pids()
        assert await wait_until(lambda: not any(process_running(pid) for pid in pids), peer_bound(fast_stop))


@pytest.mark.asyncio
@posix_only
async def test_turn_end_stops_a_grandchild_of_the_peer(muse_api, muse_fake, make_muse_host, fast_stop, wait_until, process_running) -> None:
    # EC-10 / D-23: the peer's whole tree is stopped when its turn ends, even after the peer itself exited.
    async with make_muse_host({"grandchild_roles": ["peer"]}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
        grandchildren = [record["grandchild_pid"] for record in muse_fake.records("grandchild")]
        assert grandchildren
        assert await wait_until(lambda: not any(process_running(pid) for pid in grandchildren), peer_bound(fast_stop))
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
