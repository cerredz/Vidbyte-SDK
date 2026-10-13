"""FILE: tests/features/grok_host/test_grok_host_process_bounds.py

PURPOSE: Time bounds, cancellation and reaping for GrokHost on real processes: an unresponsive peer fails within its timeout plus the stop bound (AC-3, NFR-2), cancellation propagates and reaps (AC-4, EC-4, INV-2), a cancelled wait leaves the turn alone (INV-12), __aexit__ stops live turns and never swallows (EC-8), and the whole process tree is stopped (EC-10, INV-4).
ROLE IN CODEBASE: Start here for a hang or a leftover grok process. Covers NativePeer.close, ProcessStopper and the host's __aexit__ through GrokHost's public surface.
ARCHITECTURE NOTE: Stubborn fakes (ignore_eof, and ignore_term on POSIX) force the host past stdin EOF to the tree stop, so a missing kill shows up as a timeout or a live pid. Timings are shrunk through fast_stop except in the one test that checks the NFR-2 default bound.
FUNCTION INVENTORY: STUBBORN is the scenario that refuses to exit by itself; peer_bound computes G + 2K plus slack; the test_* functions each pin one bound.
COMMON MODIFICATION PATTERNS: Assert upper bounds with SLACK_SECONDS; keep liveness checks behind posix_only, the prior art in tests/features/coding_agent/test_bash_tool_process_bounds.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not replace the bounded polls with fixed sleeps. 2. Do not assert a lower bound on a stop; only the upper bound is specified.
KNOWN EDGE CASES: On Windows, taskkill /T cannot reach a grandchild of a peer that already exited (Q-19), so grandchild checks are POSIX-only. The NFR-2 default-timing test takes about seven seconds by design.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md INV-2 to INV-4, EC-4, EC-8, EC-10, NFR-2, AC-3, AC-4
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_process_bounds.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import pytest

KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
PROMPT = "List the top-level folders."
CONTROL_SECONDS = 0.5
STARTED_WITHIN_SECONDS = 20.0
STUBBORN = {"ignore_eof": True, "ignore_term": True}
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


@pytest.mark.asyncio
async def test_unresponsive_peer_raises_server_unreachable_within_the_bound(grok_api, make_grok_host, fast_stop, check_native_error) -> None:
    # AC-3: control timeout plus the NFR-2 stop bound for what the call started.
    scenario = merged(STUBBORN, {"acp": {"initialize": {"mode": "silent"}}})
    async with make_grok_host(scenario, control_timeout_seconds=CONTROL_SECONDS) as host:
        started = time.monotonic()
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.list_grok_models()
        elapsed = time.monotonic() - started
    check_native_error(caught.value, code="grok.server_unreachable", token="control_timeout_seconds", operation="list_grok_models")
    assert elapsed < CONTROL_SECONDS + peer_bound(fast_stop)


@pytest.mark.asyncio
async def test_unresponsive_peer_bound_holds_with_default_timings(grok_api, make_grok_host) -> None:
    # NFR-2 with the defaults: 9 s for a call's peer (5 s grace + 1 s + 1 s + 2 s slack), plus the control timeout.
    assert grok_api.constants.NATIVE_STOP_GRACE_SECONDS == 5.0
    assert grok_api.constants.NATIVE_KILL_WAIT_SECONDS == 1.0
    scenario = merged(STUBBORN, {"acp": {"initialize": {"mode": "silent"}}})
    async with make_grok_host(scenario, control_timeout_seconds=CONTROL_SECONDS) as host:
        started = time.monotonic()
        with pytest.raises(grok_api.NativeHostError):
            await host.list_grok_models()
        elapsed = time.monotonic() - started
    assert elapsed < CONTROL_SECONDS + 9.0


@pytest.mark.asyncio
@posix_only
async def test_unresponsive_peer_is_reaped_before_the_error_is_raised(grok_api, grok_fake, make_grok_host, fast_stop, process_running) -> None:
    # AC-3 / INV-4: every process the call started has exited and been reaped.
    scenario = merged(STUBBORN, {"acp": {"initialize": {"mode": "silent"}}})
    async with make_grok_host(scenario, control_timeout_seconds=CONTROL_SECONDS) as host:
        with pytest.raises(grok_api.NativeHostError):
            await host.list_grok_models()
        pids = grok_fake.pids("peer")
        assert pids and not any(process_running(pid) for pid in pids)


@pytest.mark.asyncio
@posix_only
async def test_short_lived_peer_is_reaped_before_the_read_returns(grok_api, grok_fake, make_grok_host, fast_stop, process_running) -> None:
    # INV-4: a short-lived peer is closed before the method that started it returns, even when it ignores EOF.
    async with make_grok_host(STUBBORN) as host:
        catalog = await host.list_grok_models()
        pids = grok_fake.pids("peer")
        assert pids and not any(process_running(pid) for pid in pids)
    assert catalog.current_model_id == "grok-code-fast-1"


CANCEL_CASES = {
    "spawn_grok_session": ({"acp": {"session_new": {"mode": "silent"}}}, "session/new"),
    "continue_grok_session": ({"acp": {"session_resume": {"mode": "silent"}}}, "session/resume"),
    "list_grok_sessions": ({"acp": {"session_list": {"mode": "silent"}}}, "session/list"),
    "check_grok_ready": ({"version": {"hold": True}}, None),
}


def start_call(host: Any, api: Any, operation: str) -> Any:
    calls = {
        "spawn_grok_session": lambda: host.spawn_grok_session(api.GrokTurnRequest(prompt=PROMPT)),
        "continue_grok_session": lambda: host.continue_grok_session(KNOWN_SESSION, api.GrokTurnRequest(prompt=PROMPT)),
        "list_grok_sessions": lambda: host.list_grok_sessions(),
        "check_grok_ready": lambda: host.check_grok_ready(),
    }
    return asyncio.create_task(calls[operation]())


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(CANCEL_CASES))
async def test_cancelling_a_call_propagates_and_stops_what_it_started(operation: str, grok_api, grok_fake, make_grok_host, fast_stop, wait_until, process_running) -> None:
    # AC-4 / EC-4 / INV-2: CancelledError propagates, and every process the call started is stopped.
    scenario, waiting_on = CANCEL_CASES[operation]
    async with make_grok_host(merged(STUBBORN, scenario), control_timeout_seconds=60.0) as host:
        task = start_call(host, grok_api, operation)
        if waiting_on is None:
            reached = await wait_until(lambda: bool(grok_fake.launches("version")), STARTED_WITHIN_SECONDS)
        else:
            reached = await wait_until(lambda: bool(grok_fake.received(waiting_on)), STARTED_WITHIN_SECONDS)
        assert reached, "the call reached the fake before it was cancelled"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        if sys.platform != "win32":
            pids = grok_fake.pids()
            stopped = await wait_until(lambda: not any(process_running(pid) for pid in pids), peer_bound(fast_stop))
            assert stopped, f"processes left running after cancelling {operation}"


@pytest.mark.asyncio
async def test_cancelling_a_wait_leaves_the_turn_running(grok_api, grok_fake, make_grok_host, fast_stop, wait_until) -> None:
    # AC-4 for wait_* / INV-12: the turn keeps running and a later wait returns its result.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        waiter = asyncio.create_task(host.wait_grok_turn(handle, timeout_seconds=60))
        assert await wait_until(lambda: bool(grok_fake.received("session/prompt")), STARTED_WITHIN_SECONDS)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        with pytest.raises(grok_api.NativeHostError) as still_running:
            await host.wait_grok_turn(handle, timeout_seconds=0.3)
        assert still_running.value.failure_code is grok_api.FailureCode.GROK_TURN_TIMED_OUT
        assert grok_fake.received("session/cancel") == []
        grok_fake.release()
        result = await host.wait_grok_turn(handle, timeout_seconds=30)
    assert result.status is grok_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_aexit_interrupts_live_turns_as_host_closed_within_the_bound(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # EC-8: interrupt each live turn, wait at most G, close every peer concurrently; turns end INTERRUPTED/HOST_CLOSED.
    host = make_grok_host(merged(STUBBORN, {"acp": {"session_prompt": {"mode": "hold", "on_cancel": "ignore"}}}))
    async with host:
        handles = [await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT)) for _ in range(2)]
        waiters = [asyncio.create_task(host.wait_grok_turn(handle, timeout_seconds=60)) for handle in handles]
        await asyncio.sleep(0)
        started = time.monotonic()
    elapsed = time.monotonic() - started
    results = await asyncio.gather(*waiters)
    assert [result.status for result in results] == [grok_api.NativeTurnStatus.INTERRUPTED] * 2
    assert [result.interrupt_source for result in results] == [grok_api.InterruptSource.HOST_CLOSED] * 2
    assert len(grok_fake.received("session/cancel")) == 2
    assert elapsed < fast_stop.grace + peer_bound(fast_stop), "peers close concurrently, so two cost no more than one"


@pytest.mark.asyncio
@posix_only
async def test_aexit_leaves_no_process_running(grok_api, grok_fake, make_grok_host, fast_stop, process_running) -> None:
    # NFR-2: when __aexit__ returns, no process the host started is alive.
    host = make_grok_host(merged(STUBBORN, {"acp": {"session_prompt": {"mode": "hold", "on_cancel": "ignore"}}}))
    async with host:
        await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
    pids = grok_fake.pids()
    assert pids and not any(process_running(pid) for pid in pids)


@pytest.mark.asyncio
async def test_aexit_never_suppresses_the_body_exception(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # EC-8: __aexit__ raises nothing of its own and never swallows the exception it was given.
    with pytest.raises(LookupError, match="body failure"):
        async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}) as host:
            await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
            raise LookupError("body failure")
    assert grok_fake.received("session/cancel"), "the live turn was interrupted on the error path too"


@pytest.mark.asyncio
async def test_aexit_on_cancellation_still_stops_the_turn(grok_api, grok_fake, make_grok_host, fast_stop, wait_until, process_running) -> None:
    # EC-8 / INV-4: __aexit__ runs its stop sequence even when it runs because of cancellation.
    spawned = asyncio.Event()

    async def body() -> None:
        async with make_grok_host(merged(STUBBORN, {"acp": {"session_prompt": {"mode": "hold", "on_cancel": "ignore"}}})) as host:
            await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
            spawned.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(body())
    await asyncio.wait_for(spawned.wait(), timeout=STARTED_WITHIN_SECONDS)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert grok_fake.received("session/cancel")
    if sys.platform != "win32":
        pids = grok_fake.pids()
        assert await wait_until(lambda: not any(process_running(pid) for pid in pids), peer_bound(fast_stop))


@pytest.mark.asyncio
@posix_only
async def test_turn_end_stops_a_grandchild_of_the_peer(grok_api, grok_fake, make_grok_host, fast_stop, wait_until, process_running) -> None:
    # EC-10 / D-23: the peer's whole tree is stopped when its turn ends, even after the peer itself exited.
    async with make_grok_host({"grandchild_roles": ["peer"]}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        result = await host.wait_grok_turn(handle, timeout_seconds=30)
        grandchildren = [record["grandchild_pid"] for record in grok_fake.records("grandchild")]
        assert grandchildren
        assert await wait_until(lambda: not any(process_running(pid) for pid in grandchildren), peer_bound(fast_stop))
    assert result.status is grok_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
@posix_only
async def test_one_shot_timeout_stops_the_cli_tree(grok_api, grok_fake, make_grok_host, fast_stop, wait_until, process_running) -> None:
    # EC-38: at max_turn_seconds ProcessStopper stops and reaps the CLI run's whole tree.
    async with make_grok_host({"oneshot": {"hold": True}, "grandchild_roles": ["oneshot"]}) as host:
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.run_grok_once(grok_api.GrokOneShotRequest(prompt=PROMPT, max_turn_seconds=1.0))
        pids = grok_fake.pids("oneshot") + [record["grandchild_pid"] for record in grok_fake.records("grandchild")]
        assert len(pids) == 2
        assert await wait_until(lambda: not any(process_running(pid) for pid in pids), 2 * fast_stop.kill_wait + fast_stop.slack)
    assert caught.value.failure_code is grok_api.FailureCode.GROK_TURN_TIMED_OUT
