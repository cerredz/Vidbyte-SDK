"""FILE: tests/features/grok_host/test_grok_host_process_bounds.py

PURPOSE: Time bounds, cancellation and reaping for GrokHost on real processes: an unresponsive peer fails within its timeout plus the stop bound (AC-3, NFR-2), cancellation propagates and reaps (AC-4, EC-4, INV-2), also when it lands just as a bounded write drain finishes, CPython 3.11's swallowed-cancel window (gh-86296), at the request and the notification site, a cancelled wait leaves the turn alone (INV-12), __aexit__ stops live turns and never swallows (EC-8), and the whole process tree is stopped (EC-10, INV-4).
ROLE IN CODEBASE: Start here for a hang or a leftover grok process. Covers NativePeer.close, ProcessStopper and the host's __aexit__ through GrokHost's public surface.
ARCHITECTURE NOTE: Stubborn fakes (ignore_eof, and ignore_term on POSIX) force the host past stdin EOF to the tree stop, so a missing kill shows up as a timeout or a live pid. Timings are shrunk through fast_stop except in the one test that checks the NFR-2 default bound.
FUNCTION INVENTORY: STUBBORN is the scenario that refuses to exit by itself; peer_bound computes G + 2K plus slack; DrainWindowGate and the drain_window_gate fixture cancel the call under test as its bounded drain of one named frame finishes; describe_outcome names how a call ended; cancel_in_the_drain_window runs one call through the gate in its own frame; the test_* functions each pin one bound.
COMMON MODIFICATION PATTERNS: Assert upper bounds with SLACK_SECONDS; keep liveness checks behind posix_only, the prior art in tests/features/coding_agent/test_bash_tool_process_bounds.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not replace the bounded polls with fixed sleeps. 2. Do not assert a lower bound on a stop; only the upper bound is specified.
KNOWN EDGE CASES: On Windows, taskkill /T cannot reach a grandchild of a peer that already exited (Q-19), so grandchild checks are POSIX-only. The NFR-2 default-timing test takes about seven seconds by design. No frame order through the fake can force the gh-86296 window, because it sits between the end of wait_for's inner drain task and the caller's resume, so drain_window_gate wraps NativePeer.call, send and notify and asyncio.wait_for, always calling the real ones. On 3.11 it cancels the caller from the finishing inner task; on 3.12+ wait_for runs the drain in the caller's own task, so a loop callback cancels it inside the drain instead (a self-cancel there would leave a second cancel pending for the host's cleanup). The 3.11 window is gone on 3.12+, so there the CancelledError check passes before the transport fix, while the never-retrieved check still needs the cancelled write to drop its pending future. The never-retrieved check reads asyncio's log record, which appears only when the future is collected, so the test collects and clears caplog first and runs the call inside a helper coroutine.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md INV-2 to INV-4, EC-4, EC-8, EC-10, NFR-2, AC-3, AC-4
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_process_bounds.py
"""

from __future__ import annotations

import asyncio
import gc
import importlib
import logging
import sys
import time
from collections.abc import Callable
from typing import Any

import pytest

KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
PROMPT = "List the top-level folders."
CONTROL_SECONDS = 0.5
STARTED_WITHIN_SECONDS = 20.0
STUBBORN = {"ignore_eof": True, "ignore_term": True}
HELD_PROMPT = {"acp": {"session_prompt": {"mode": "hold"}}}
# Long enough that a stop under fast_stop (at most 1.3 s) is clearly sooner; short enough that a red run takes seconds.
SWALLOW_CONTROL_SECONDS = 5.0
DRAIN_QUALNAME = "StreamWriter.drain"
CANCELLED = "raised CancelledError"
NEVER_RETRIEVED = "exception was never retrieved"
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
# The calls that write a JSON-RPC request with a deadline; check_grok_ready runs the CLI and writes none.
SWALLOW_CASES = ("continue_grok_session", "list_grok_sessions", "spawn_grok_session")


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


class DrainWindowGate:
    """Cancels the call under test at the moment its bounded write drain finishes: CPython 3.11's swallowed-cancel window (gh-86296)."""

    def __init__(self) -> None:
        self.caller: asyncio.Task[Any] | None = None
        self.method: str | None = None
        self.armed = False
        self.engaged = False
        self.cancel_sent_at: float | None = None

    def aim(self, caller: asyncio.Task[Any] | None, method: str | None) -> None:
        self.caller = caller
        self.method = method

    def note_write(self, method: str) -> None:
        # NativePeer is about to write this frame from the caller's own task, so that task's next bounded drain is this frame's.
        if self.caller is not None and not self.engaged and method == self.method and asyncio.current_task() is self.caller:
            self.armed = True

    def takes(self, awaitable: Any, timeout: Any) -> bool:
        if not self.armed or self.engaged or timeout is None or asyncio.current_task() is not self.caller:
            return False
        self.engaged = getattr(awaitable, "__qualname__", "") == DRAIN_QUALNAME
        return self.engaged

    async def cancel_as_the_drain_finishes(self, drain: Any) -> Any:
        caller = self.caller
        result = await drain
        loop = asyncio.get_running_loop()
        self.cancel_sent_at = loop.time()
        if asyncio.current_task() is caller:
            # 3.12+: wait_for runs the drain in the caller's own task, so the cancel comes from the loop, as from any other task, and lands at this await.
            loop.call_soon(caller.cancel)
            await asyncio.sleep(0)
        else:
            # 3.11: wait_for ran the drain in an inner task that ends with this step, while the caller waits to resume. That is the gh-86296 window.
            caller.cancel()
        return result


@pytest.fixture
def drain_window_gate(monkeypatch: pytest.MonkeyPatch) -> DrainWindowGate:
    # A delegating seam, like cancel_drain_gate in test_grok_host_turns.py: the real NativePeer methods, drain and wait_for all run; the gate only picks the moment of one cancel.
    peer_class = importlib.import_module("vidbyte.harnesses.native.hostkit").NativePeer
    real_call, real_send, real_notify = peer_class.call, peer_class.send, peer_class.notify
    real_wait_for = asyncio.wait_for
    gate = DrainWindowGate()

    async def call(self: Any, method: str, params: Any, **kwargs: Any) -> Any:
        gate.note_write(method)
        return await real_call(self, method, params, **kwargs)

    async def send(self: Any, method: str, params: Any, **kwargs: Any) -> Any:
        gate.note_write(method)
        return await real_send(self, method, params, **kwargs)

    async def notify(self: Any, method: str, params: Any, **kwargs: Any) -> Any:
        gate.note_write(method)
        return await real_notify(self, method, params, **kwargs)

    async def wait_for(awaitable: Any, timeout: Any, *args: Any, **kwargs: Any) -> Any:
        if gate.takes(awaitable, timeout):
            awaitable = gate.cancel_as_the_drain_finishes(awaitable)
        return await real_wait_for(awaitable, timeout, *args, **kwargs)

    monkeypatch.setattr(peer_class, "call", call)
    monkeypatch.setattr(peer_class, "send", send)
    monkeypatch.setattr(peer_class, "notify", notify)
    monkeypatch.setattr(asyncio, "wait_for", wait_for)
    return gate


def describe_outcome(task: asyncio.Task[Any]) -> str:
    if task.cancelled():
        return CANCELLED
    error = task.exception()
    if error is None:
        return f"returned {type(task.result()).__name__}"
    code = getattr(getattr(error, "failure_code", None), "value", None)
    return f"raised {type(error).__name__} {code}: {error}"


async def cancel_in_the_drain_window(gate: DrainWindowGate, launch: Callable[[], asyncio.Task[Any]], method: str, bound: float) -> tuple[str, float | None]:
    # Runs in its own frame, so the call's task, its error and the transport frames that error holds are garbage once this returns (the never-retrieved check needs that).
    task = launch()
    gate.aim(task, method)
    try:
        done, _ = await asyncio.wait({task}, timeout=bound)
        if not done:
            task.cancel()
            await asyncio.wait({task}, timeout=bound)
            return f"was still running {bound:.1f} s after the cancel", None
        after_cancel = None if gate.cancel_sent_at is None else asyncio.get_running_loop().time() - gate.cancel_sent_at
        return describe_outcome(task), after_cancel
    finally:
        gate.aim(None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(SWALLOW_CASES))
async def test_cancel_landing_as_the_request_drain_finishes_still_propagates(operation: str, grok_api, grok_fake, make_grok_host, fast_stop, wait_until, process_running, drain_window_gate, caplog: pytest.LogCaptureFixture) -> None:
    # AC-4 / INV-2 / EC-4 at the request site: on CPython 3.11, wait_for returns a finished drain's result and drops a cancel that landed before the caller resumed (gh-86296), so the call waited out the control timeout on the silent fake.
    scenario, silent_method = CANCEL_CASES[operation]
    bound = SWALLOW_CONTROL_SECONDS + peer_bound(fast_stop)
    gc.collect()
    caplog.set_level(logging.ERROR, logger="asyncio")
    # Collect earlier tests' garbage first and drop what it logged, so only this test's records count.
    caplog.clear()
    async with make_grok_host(merged(STUBBORN, scenario), control_timeout_seconds=SWALLOW_CONTROL_SECONDS) as host:
        outcome, after_cancel = await cancel_in_the_drain_window(drain_window_gate, lambda: start_call(host, grok_api, operation), silent_method, bound)
    # Let the loop drop its last reference to the call's final step, then collect its pending request now rather than in a later test.
    await asyncio.sleep(0)
    gc.collect()
    assert drain_window_gate.engaged, f"seam: no bounded StreamWriter.drain followed the {silent_method} write in the calling task, so the window was not forced"
    assert outcome == CANCELLED, f"AC-4 / INV-2: {operation} was cancelled as its {silent_method} drain finished and {outcome}; the transport must raise CancelledError when wait_for swallowed it (CPython 3.11, gh-86296)"
    assert after_cancel is not None and after_cancel < SWALLOW_CONTROL_SECONDS, f"AC-4: the cancel took {after_cancel} s to propagate; it must not wait out the {SWALLOW_CONTROL_SECONDS} s control timeout"
    if sys.platform != "win32":
        pids = grok_fake.pids()
        stopped = await wait_until(lambda: not any(process_running(pid) for pid in pids), peer_bound(fast_stop))
        assert stopped, f"EC-4: processes left running after cancelling {operation}"
    unretrieved = [record.getMessage().splitlines()[0] for record in caplog.records if record.name == "asyncio" and NEVER_RETRIEVED in record.getMessage()]
    assert unretrieved == [], f"INV-2: cancelling {operation} during its {silent_method} write logged {unretrieved}; the cancelled write must drop its pending answer future, or the peer close fails it unseen"


@pytest.mark.asyncio
async def test_cancel_landing_as_the_session_cancel_drain_finishes_still_propagates(grok_api, grok_fake, make_grok_host, fast_stop, drain_window_gate) -> None:
    # INV-2 / FR-7 at the notification site: the same CPython 3.11 window in the session/cancel write let interrupt_grok_turn return a result to a caller that had been cancelled.
    async with make_grok_host(HELD_PROMPT) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        outcome, _ = await cancel_in_the_drain_window(drain_window_gate, lambda: asyncio.create_task(host.interrupt_grok_turn(handle)), "session/cancel", SWALLOW_CONTROL_SECONDS + peer_bound(fast_stop))
    assert drain_window_gate.engaged, "seam: no bounded StreamWriter.drain followed the session/cancel write in the interrupting task, so the window was not forced"
    assert outcome == CANCELLED, f"INV-2: interrupt_grok_turn was cancelled as its session/cancel drain finished and {outcome}; the transport must raise CancelledError when wait_for swallowed it (CPython 3.11, gh-86296)"
    assert len(grok_fake.received("session/cancel")) >= 1, "precondition: session/cancel never reached the fake, so the cancel did not land after the write"


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
