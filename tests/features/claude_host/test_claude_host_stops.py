"""FILE: tests/features/claude_host/test_claude_host_stops.py

PURPOSE: Proves every way a turn is stopped or redirected: steer means interrupt then resend with one pending message, interrupt returns at once and ends the turn INTERRUPTED, aclose ends every live turn and locks the host, the one close task is never cancelled and finishes before the turn ends, the time budget fails the turn with budget_exhausted, and every acknowledged interrupt is bounded by the grace period.
ROLE IN CODEBASE: Stop layer of tests/features/claude_host/ (spec AC-9, AC-10, AC-21, AC-25, AC-31, AC-37, AC-40, INV-7, INV-8, INV-11, INV-15, INV-18, D-4, D-26, EC-19 to EC-23, EC-26, EC-27, EC-53, EC-59, EC-60). Exercises vidbyte/harnesses/native/claude/{host,session}.py.
ARCHITECTURE NOTE: The fake client's gates stand in for a slow CLI: interrupt_gate holds interrupt(), connect_gate holds connect() and disconnect_gate holds disconnect() until the test opens them, and interrupt_answer decides whether the fake ends the open prompt when interrupted. The grace constant is patched in the session module, where the spec says it is read at call time.
COMMON MODIFICATION PATTERNS: A new stop path gets a test that holds the disconnect gate, checks the turn is still live while the close runs, then opens the gate and checks the terminal status, one disconnect and no cancellation. Add a new star function to star_calls in claude_host_fixtures.py so the lock tests cover it.
WHAT NOT TO DO IN THIS FILE: 1. Do not sleep for a fixed time; wait on recorded fake calls with eventually(). 2. Do not leave the real 30-second grace in a test whose fake never answers an interrupt; patch GRACE_TARGET. 3. Do not call aclose on a host without adding it to closed_hosts, because a second aclose is unspecified.
KNOWN EDGE CASES: In AC-37 (c) the steer call itself may return normally or raise action.precondition_failed, depending on whether the grace expires before the caller resumes; the spec fixes only the turn's outcome there. AC-37 (d) patches the grace to zero so a wrongly armed grace fires within settle().
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.1, 6.2, 8.1 (D-4, D-26) and 9.2 (steer and interrupt rows).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_stops.py
"""

from __future__ import annotations

import asyncio
import contextlib
import unittest
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from unittest import mock

from tests.features.claude_host.claude_host_fixtures import (
    ANSWER_BEFORE_GATE,
    ANSWER_NEVER,
    CLAUDE_NEXT_STEPS,
    DEFAULT_PROMPT,
    ERROR_MARKER,
    FAKE_CLI_PATH,
    GRACE_TARGET,
    HANG_GUARD_SECONDS,
    LIVE_CAP_NEXT_STEP,
    PRECONDITION_FAILED,
    PRECONDITION_NEXT_STEP,
    SHORT_TIMEOUT_SECONDS,
    SMALL_GRACE_SECONDS,
    WORK_DIR,
    ClaudeHostCase,
    CLIConnectionError,
    answer_for,
    eventually,
    init_message,
    result_message,
    settle,
    star_calls,
)

STEER_MESSAGE = "focus on tests"
LAUNCH_PROMPTS = ("Review src/ for bugs.", "Review tests/ for gaps.")


def codes_from_another_loop(calls: list[tuple[str, Callable[[], Awaitable[Any]]]], error_type: type[BaseException]) -> dict[str, Any]:
    """Run each call on a fresh event loop in this worker thread and return the failure code each one raised."""
    codes: dict[str, Any] = {}
    for name, call in calls:
        try:
            asyncio.run(call())
        except error_type as error:
            codes[name] = getattr(error, "failure_code", None)
        else:
            codes[name] = "returned without raising"
    return codes


class StopCase(ClaudeHostCase):
    """Adds helpers for a held turn and for the one-close checks every stop path shares."""

    async def running_turn(self, host: Any, **fields: Any) -> tuple[Any, Any]:
        """Spawn a held turn and return its handle and client once the prompt has been sent."""
        self.fake.hold(DEFAULT_PROMPT)
        handle = await self.spawn(host, **fields)
        client = await self.client_for(handle)
        await eventually(lambda: len(client.queries) == 1, "the prompt was sent")
        return handle, client

    def assert_closed_once(self, client: Any) -> None:
        self.assertEqual(client.disconnect_calls, 1)
        self.assertTrue(client.disconnect_finished, "the disconnect never finished")
        self.assertFalse(client.disconnect_cancelled, "the disconnect was cancelled")

    async def launch_one_running_one_queued(self, host: Any) -> tuple[Any, Any]:
        """Launch two held prompts with limit 1 and return (running handle, queued handle)."""
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        self.fake.hold(*LAUNCH_PROMPTS)
        handles = await asyncio.wait_for(host.launch_claude_subagents(LAUNCH_PROMPTS, ClaudeSpawnRequest(cwd=WORK_DIR), 1), HANG_GUARD_SECONDS)
        self.assertEqual(len(handles), 2)
        await eventually(lambda: len(self.fake.turn_clients()) == 1, "one launched turn is running")
        running = [handle for handle in handles if self.fake.client_for_session(handle.session_id) is not None]
        queued = [handle for handle in handles if self.fake.client_for_session(handle.session_id) is None]
        self.assertEqual((len(running), len(queued)), (1, 1))
        self.assertEqual((await self.snapshot(host, queued[0])).status.value, "queued")
        return running[0], queued[0]


class SteerTests(StopCase):
    """AC-9, EC-19, EC-20, EC-21 and INV-18: one pending steer, delivered once as the next turn."""

    async def test_steer_interrupts_then_sends_the_message_as_the_next_turn(self) -> None:
        self.fake.reply(STEER_MESSAGE, init_message(), result_message(result="The failing tests are fixed."))
        self.fake.interrupt_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        steer = asyncio.create_task(host.steer_claude_session(handle, STEER_MESSAGE))
        await eventually(lambda: client.interrupt_calls == 1, "the steer sent interrupt()")
        # A second steer while the first is still pending is refused at once.
        second = await self.raises(host.steer_claude_session(handle, "also check the docs"), PRECONDITION_FAILED)
        self.assertIn("pending", second.reason.lower())
        self.assertEqual(second.next_step, PRECONDITION_NEXT_STEP)
        self.fake.interrupt_gate.set()
        self.assertIsNone(await asyncio.wait_for(steer, HANG_GUARD_SECONDS))
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "The failing tests are fixed."))
        self.assertIsNone(result.failure)
        # The message ran exactly once, after the interrupt, and the second steer was never sent.
        self.assertEqual(client.queries, [DEFAULT_PROMPT, STEER_MESSAGE])
        query_positions = [index for index, call in enumerate(client.calls) if call == "query"]
        self.assertLess(client.calls.index("interrupt"), query_positions[1])
        self.assertEqual(client.interrupt_calls, 1)
        self.assertEqual(client.disconnect_calls, 1)
        # A steer on the terminal turn is refused, and its reason names the status.
        late = await self.raises(host.steer_claude_session(handle, "one more thing"), PRECONDITION_FAILED)
        self.assertIn("completed", late.reason.lower())
        self.assertEqual(late.next_step, PRECONDITION_NEXT_STEP)

    async def test_a_result_arriving_with_a_steer_pending_does_not_end_the_handle(self) -> None:
        # EC-19: the prompt's own success result reaches the pump after the steer was stored.
        self.fake.interrupt_reply = lambda: result_message(result="The parser bug is fixed.")
        self.fake.reply(STEER_MESSAGE, init_message(), result_message(result="A regression test is added."))
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        self.assertIsNone(await asyncio.wait_for(host.steer_claude_session(handle, STEER_MESSAGE), HANG_GUARD_SECONDS))
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "A regression test is added."))
        self.assertEqual(client.queries, [DEFAULT_PROMPT, STEER_MESSAGE])

    async def test_a_steer_on_a_queued_turn_is_refused(self) -> None:
        self.fake.connect_gate = asyncio.Event()
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: "connect" in client.calls, "connect is in flight")
        error = await self.raises(host.steer_claude_session(handle, STEER_MESSAGE), PRECONDITION_FAILED)
        self.assertIn("queued", error.reason.lower())
        self.assertEqual(error.next_step, PRECONDITION_NEXT_STEP)
        self.fake.connect_gate.set()
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(client.queries, [DEFAULT_PROMPT])

    async def test_a_steer_on_a_stopping_turn_is_refused(self) -> None:
        self.fake.interrupt_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        await host.interrupt_claude_turn(handle)
        error = await self.raises(host.steer_claude_session(handle, STEER_MESSAGE), PRECONDITION_FAILED)
        self.assertEqual(error.next_step, PRECONDITION_NEXT_STEP)
        self.fake.interrupt_gate.set()
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "interrupted")
        self.assertEqual(client.queries, [DEFAULT_PROMPT])


class PendingSteerDiscardTests(StopCase):
    """INV-18: an explicit interrupt, the time budget or the turn ending discards a pending steer, and the steer call raises."""

    async def test_an_explicit_interrupt_discards_a_pending_steer(self) -> None:
        self.fake.interrupt_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        steer = asyncio.create_task(host.steer_claude_session(handle, STEER_MESSAGE))
        await eventually(lambda: client.interrupt_calls == 1, "the steer sent interrupt()")
        snapshot = await host.interrupt_claude_turn(handle)
        self.assertEqual(snapshot.status.value, "running")
        self.fake.interrupt_gate.set()
        await self.raises(steer, PRECONDITION_FAILED)
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "interrupted")
        self.assertIsNone(result.failure)
        self.assertEqual(client.queries, [DEFAULT_PROMPT])
        self.assertEqual(client.disconnect_calls, 1)

    async def test_the_time_budget_discards_a_pending_steer(self) -> None:
        self.fake.interrupt_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host, timeout_seconds=0.2)
        steer = asyncio.create_task(host.steer_claude_session(handle, STEER_MESSAGE))
        # Wait for the watchdog's own interrupt(); if the watchdog fired first, the steer was refused outright.
        await eventually(lambda: steer.done() or client.interrupt_calls == 2, "the watchdog fired")
        self.fake.interrupt_gate.set()
        await self.raises(steer, PRECONDITION_FAILED)
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.failure.code.value, "claude.budget_exhausted")
        self.assertEqual(client.queries, [DEFAULT_PROMPT])
        self.assertEqual(client.disconnect_calls, 1)

    async def test_a_turn_that_ends_before_the_interrupt_is_answered_discards_the_steer(self) -> None:
        self.fake.interrupt_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        steer = asyncio.create_task(host.steer_claude_session(handle, STEER_MESSAGE))
        await eventually(lambda: client.interrupt_calls == 1, "the steer sent interrupt()")
        client.end_stream()
        await self.raises(steer, PRECONDITION_FAILED)
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.failure.code.value, "claude.process_exited")
        self.assertEqual(result.failure.next_step, CLAUDE_NEXT_STEPS["claude.process_exited"])
        self.assertEqual(client.queries, [DEFAULT_PROMPT])
        self.assertEqual(client.disconnect_calls, 1)


class InterruptTests(StopCase):
    """AC-10, D-26, EC-22 and EC-23: interrupt returns the snapshot at once and ends a live turn INTERRUPTED."""

    async def test_interrupting_a_running_turn(self) -> None:
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        snapshot = await host.interrupt_claude_turn(handle)
        # D-26: the snapshot is taken right after the request, before the CLI answers.
        self.assertEqual((snapshot.handle_id, snapshot.status.value), (handle.handle_id, "running"))
        # A further interrupt on a stopping turn sends nothing.
        self.assertIn((await host.interrupt_claude_turn(handle)).status.value, ("running", "interrupted"))
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "interrupted")
        self.assertIsNone(result.failure)
        self.assertEqual(client.interrupt_calls, 1)
        self.assertEqual(client.disconnect_calls, 1)
        # EC-23: on a terminal turn the call returns the same snapshot and sends nothing.
        self.assertEqual(await host.interrupt_claude_turn(handle), result)
        self.assertEqual(client.interrupt_calls, 1)

    async def test_interrupting_a_completed_turn_returns_it_unchanged(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host)
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(await host.interrupt_claude_turn(handle), result)
        client = await self.client_for(handle)
        self.assertEqual(client.interrupt_calls, 0)

    async def test_interrupting_a_queued_launch_handle_ends_it_at_once_without_a_prompt(self) -> None:
        host = await self.open_host()
        running, queued = await self.launch_one_running_one_queued(host)
        snapshot = await host.interrupt_claude_turn(queued)
        self.assertEqual(snapshot.status.value, "interrupted")
        self.assertIsNone(snapshot.failure)
        # No client exists for it, so it is terminal at once and its done signal has fired.
        self.assertEqual(await self.finished(host, queued), snapshot)
        self.assertEqual((await self.snapshot(host, running)).status.value, "running")
        running_client = await self.client_for(running)
        running_client.finish("Reviewed src/.")
        self.assertEqual((await self.finished(host, running)).status.value, "completed")
        await settle()
        # The queued turn never connected, even after the slot it waited for was freed.
        self.assertIsNone(self.fake.client_for_session(queued.session_id))
        self.assertEqual(len(self.fake.clients), 1)
        self.assertEqual(self.fake.all_queries(), running_client.queries)
        self.assertEqual(await host.interrupt_claude_turn(queued), snapshot)

    async def test_interrupting_a_queued_turn_with_a_connect_in_flight(self) -> None:
        # EC-22 and INV-11: the connect completes, the client is closed, and only then is the turn terminal.
        self.fake.connect_gate = asyncio.Event()
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: "connect" in client.calls, "connect is in flight")
        snapshot = await host.interrupt_claude_turn(handle)
        self.assertEqual(snapshot.status.value, "queued")
        early = await host.wait_claude_turn(handle, timeout_seconds=SHORT_TIMEOUT_SECONDS)
        self.assertEqual(early.status.value, "queued")
        self.fake.connect_gate.set()
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "interrupted")
        self.assertIsNone(result.failure)
        self.assertEqual(client.queries, [])
        self.assertEqual(client.disconnect_calls, 1)


class CloseTests(StopCase):
    """AC-21, AC-25, EC-26, EC-27, EC-60, INV-8, INV-11 and INV-15: the host closes every turn once and then refuses every call."""

    async def test_aclose_interrupts_running_and_queued_handles_and_disconnects_each_client_once(self) -> None:
        host = await self.open_host()
        running, queued = await self.launch_one_running_one_queued(host)
        waits = [asyncio.create_task(host.wait_claude_turn(handle, timeout_seconds=HANG_GUARD_SECONDS)) for handle in (running, queued)]
        await settle()
        self.closed_hosts.append(host)
        await asyncio.wait_for(host.aclose(), HANG_GUARD_SECONDS)
        finals = await asyncio.wait_for(asyncio.gather(*waits), HANG_GUARD_SECONDS)
        self.assertEqual([final.status.value for final in finals], ["interrupted", "interrupted"])
        self.assertEqual([final.failure for final in finals], [None, None])
        # EC-27: the queued handle finished without ever connecting.
        self.assertEqual(len(self.fake.clients), 1)
        self.assert_closed_once(self.fake.clients[0])
        self.assertEqual(self.fake.connected_now, 0)
        # Every later star call and get_handle raise action.precondition_failed.
        for name, call in star_calls(host, running):
            with self.subTest(function=name):
                error = await self.raises(call(), PRECONDITION_FAILED)
                self.assertEqual(error.next_step, PRECONDITION_NEXT_STEP)
        self.assert_get_handle_refused(host, running.handle_id)
        self.assertEqual(len(self.fake.clients), 1)
        # A host is never reopened.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(host.__aenter__(), HANG_GUARD_SECONDS)
        await self.raises(host.get_claude_rate_limits(), PRECONDITION_FAILED)

    async def test_calls_before_entry_are_refused(self) -> None:
        from vidbyte.harnesses.native.claude import ClaudeHost
        from vidbyte.lib.dataclasses.claude_host import ClaudeSessionHandle

        host = ClaudeHost(cli_path=FAKE_CLI_PATH)
        handle = ClaudeSessionHandle(handle_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()))
        for name, call in star_calls(host, handle):
            with self.subTest(function=name):
                error = await self.raises(call(), PRECONDITION_FAILED)
                self.assertEqual(error.next_step, PRECONDITION_NEXT_STEP)
        self.assert_get_handle_refused(host, handle.handle_id)
        self.assertEqual(self.fake.clients, [])

    async def test_a_call_from_another_event_loop_is_refused(self) -> None:
        from vidbyte.lib.errors import ClaudeOperationError

        host = await self.open_host()
        handle = await self.spawn(host)
        await self.finished(host, handle)
        clients_before = len(self.fake.clients)

        async def get_handle_call() -> Any:
            return host.get_handle(handle.handle_id)

        calls = [*star_calls(host, handle), ("get_handle", get_handle_call)]
        codes = await asyncio.wait_for(asyncio.to_thread(codes_from_another_loop, calls, ClaudeOperationError), HANG_GUARD_SECONDS * 3)
        self.assertEqual(codes, {name: PRECONDITION_FAILED for name, _ in calls})
        self.assertEqual(len(self.fake.clients), clients_before)
        # The host still serves the loop that entered it.
        self.assertEqual(await host.get_claude_rate_limits(), ())
        self.assertEqual(host.get_handle(handle.handle_id), handle)

    async def test_aclose_during_connect_sends_no_prompt(self) -> None:
        self.fake.connect_gate = asyncio.Event()
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: "connect" in client.calls, "connect is in flight")
        wait = asyncio.create_task(host.wait_claude_turn(handle, timeout_seconds=HANG_GUARD_SECONDS))
        self.closed_hosts.append(host)
        closing = asyncio.create_task(host.aclose())
        await settle()
        self.assertFalse(closing.done(), "aclose returned before the turn's close completed")
        self.fake.connect_gate.set()
        await asyncio.wait_for(closing, HANG_GUARD_SECONDS)
        final = await asyncio.wait_for(wait, HANG_GUARD_SECONDS)
        self.assertEqual(final.status.value, "interrupted")
        self.assertEqual(client.queries, [])
        self.assertEqual(client.disconnect_calls, 1)

    async def test_the_turn_ends_only_after_its_one_disconnect_finishes(self) -> None:
        # AC-25 and EC-60: the stream ends first, then the close runs; the turn stays live until the close completes.
        self.fake.disconnect_gate = asyncio.Event()
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: client.disconnect_calls == 1, "the close started after the result was read")
        await settle()
        self.assertEqual((await self.snapshot(host, handle)).status.value, "running")
        self.assertEqual((await host.wait_claude_turn(handle, timeout_seconds=SHORT_TIMEOUT_SECONDS)).status.value, "running")
        # The session id is still busy, so a spawn that chooses it is refused and starts nothing.
        clients_before = len(self.fake.clients)
        await self.raises(self.spawn(host, "Reuse that session.", session_id=handle.session_id), "claude.session_busy")
        self.assertEqual(len(self.fake.clients), clients_before)
        # The pump has stopped reading, so an interrupt sends nothing and cancels nothing.
        self.assertEqual((await host.interrupt_claude_turn(handle)).status.value, "running")
        await settle()
        self.assertEqual(client.interrupt_calls, 0)
        self.assertFalse(client.disconnect_cancelled)
        self.fake.disconnect_gate.set()
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", answer_for(DEFAULT_PROMPT)))
        self.assert_closed_once(client)
        self.assertEqual(self.fake.connected_now, 0)

    def assert_get_handle_refused(self, host: Any, handle_id: str) -> None:
        from vidbyte.lib.errors import ClaudeOperationError

        with self.assertRaises(ClaudeOperationError) as caught:
            host.get_handle(handle_id)
        self.assertEqual(caught.exception.failure_code, PRECONDITION_FAILED)
        self.assertEqual(caught.exception.next_step, PRECONDITION_NEXT_STEP)


class TimeBudgetTests(StopCase):
    """AC-31 and EC-14: the watchdog interrupts, the turn fails with budget_exhausted, and the one close finishes before done."""

    async def run_budget_case(self) -> tuple[Any, Any]:
        self.fake.disconnect_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host, timeout_seconds=SHORT_TIMEOUT_SECONDS)
        await eventually(lambda: client.interrupt_calls == 1, "the watchdog sent interrupt()")
        await eventually(lambda: client.disconnect_calls == 1, "the close started")
        early = await host.wait_claude_turn(handle, timeout_seconds=SHORT_TIMEOUT_SECONDS)
        self.assertEqual(early.status.value, "running")
        self.fake.disconnect_gate.set()
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.failure.code.value, "claude.budget_exhausted")
        self.assertEqual(result.failure.next_step, CLAUDE_NEXT_STEPS["claude.budget_exhausted"])
        self.assert_closed_once(client)
        return result, client

    async def test_the_time_budget_fails_the_turn_after_its_interrupt_is_answered(self) -> None:
        _, client = await self.run_budget_case()
        self.assertEqual(client.queries, [DEFAULT_PROMPT])

    async def test_the_time_budget_closes_the_client_when_interrupt_raises(self) -> None:
        self.fake.interrupt_error = lambda: CLIConnectionError(f"control channel closed {ERROR_MARKER}")
        result, _ = await self.run_budget_case()
        self.assertNotIn(ERROR_MARKER, result.failure.reason)


class InterruptGraceTests(StopCase):
    """AC-37, AC-40, EC-53 and EC-59: an interrupt the CLI never answers ends the turn after the grace period."""

    async def run_grace_case(self, start: Callable[[Any, Any], Awaitable[Any]] | None, **fields: Any) -> tuple[Any, Any, Any, Any]:
        """Run one of AC-37 (a) to (c): a held turn whose interrupt is acknowledged but never answered, with the close held."""
        self.enterContext(mock.patch(GRACE_TARGET, SMALL_GRACE_SECONDS))
        self.fake.interrupt_answer = ANSWER_NEVER
        self.fake.disconnect_gate = asyncio.Event()
        host = await self.open_host(max_live_sessions=1)
        handle, client = await self.running_turn(host, **fields)
        caller = asyncio.create_task(start(host, handle)) if start is not None else None
        await eventually(lambda: client.interrupt_calls == 1, "interrupt() was sent")
        await eventually(lambda: client.disconnect_calls == 1, "the grace expiry started the close")
        # While the close runs, the turn is still live: RUNNING, its session id busy and its slot taken.
        self.assertEqual((await host.wait_claude_turn(handle, timeout_seconds=SHORT_TIMEOUT_SECONDS)).status.value, "running")
        self.fake.history.add_session(handle.session_id, cwd=WORK_DIR)
        await self.raises(host.continue_claude_session(handle.session_id, "next"), "claude.session_busy")
        cap = await self.raises(self.spawn(host, "Start another task."), "claude.session_busy")
        self.assertEqual(cap.next_step, LIVE_CAP_NEXT_STEP)
        self.assertEqual(len(self.fake.clients), 1)
        self.fake.disconnect_gate.set()
        result = await self.finished(host, handle)
        self.assert_closed_once(client)
        self.assertEqual(client.queries, [DEFAULT_PROMPT])
        # Once done has fired, the session id and the only slot are free: a continue on it is admitted.
        follow = await asyncio.wait_for(host.continue_claude_session(handle.session_id, "next"), HANG_GUARD_SECONDS)
        self.assertEqual((await self.finished(host, follow)).status.value, "completed")
        return result, client, caller, host

    async def test_a_the_time_budget_with_an_unanswered_interrupt(self) -> None:
        result, _, _, _ = await self.run_grace_case(None, timeout_seconds=SHORT_TIMEOUT_SECONDS)
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.failure.code.value, "claude.budget_exhausted")

    async def test_b_an_explicit_interrupt_that_is_never_answered(self) -> None:
        result, _, caller, _ = await self.run_grace_case(lambda host, handle: host.interrupt_claude_turn(handle))
        self.assertEqual(result.status.value, "interrupted")
        self.assertIsNone(result.failure)
        self.assertEqual((await caller).status.value, "running")

    async def test_c_a_steer_whose_interrupt_is_never_answered(self) -> None:
        from vidbyte.lib.errors import ClaudeOperationError

        result, client, caller, _ = await self.run_grace_case(lambda host, handle: host.steer_claude_session(handle, STEER_MESSAGE))
        self.assertEqual(result.status.value, "interrupted")
        self.assertIsNone(result.failure)
        self.assertNotIn(STEER_MESSAGE, client.queries)
        # The steer call either returned before the grace expired or was told its message was discarded.
        outcome = (await asyncio.gather(caller, return_exceptions=True))[0]
        if isinstance(outcome, ClaudeOperationError):
            self.assertEqual(outcome.failure_code, PRECONDITION_FAILED)
        else:
            self.assertIsNone(outcome)

    async def test_d_no_grace_is_armed_for_a_result_read_before_the_interrupt_returned(self) -> None:
        # A zero grace makes a wrongly armed timer fire within settle().
        self.enterContext(mock.patch(GRACE_TARGET, 0.0))
        self.fake.hold(DEFAULT_PROMPT, STEER_MESSAGE)
        self.fake.interrupt_answer = ANSWER_BEFORE_GATE
        self.fake.interrupt_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        steer = asyncio.create_task(host.steer_claude_session(handle, STEER_MESSAGE))
        await eventually(lambda: len(client.queries) == 2, "the steered prompt was sent")
        self.fake.interrupt_gate.set()
        self.assertIsNone(await asyncio.wait_for(steer, HANG_GUARD_SECONDS))
        await settle()
        self.assertEqual(client.disconnect_calls, 0)
        self.assertEqual((await self.snapshot(host, handle)).status.value, "running")
        client.finish("The steered prompt finished.")
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "The steered prompt finished."))
        self.assertEqual(client.queries, [DEFAULT_PROMPT, STEER_MESSAGE])
        self.assertEqual(client.disconnect_calls, 1)

    async def test_a_steer_whose_caller_timed_out_still_ends_through_the_grace(self) -> None:
        # AC-40 and EC-59: the caller's timeout cancels only its wait; the session's own task still arms the grace.
        self.enterContext(mock.patch(GRACE_TARGET, SMALL_GRACE_SECONDS))
        self.fake.interrupt_answer = ANSWER_NEVER
        self.fake.interrupt_gate = asyncio.Event()
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(host.steer_claude_session(handle, STEER_MESSAGE), SHORT_TIMEOUT_SECONDS)
        await eventually(lambda: client.interrupt_calls == 1, "the steer sent interrupt()")
        self.assertEqual((await self.snapshot(host, handle)).status.value, "running")
        self.fake.interrupt_gate.set()
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "interrupted")
        self.assertIsNone(result.failure)
        self.assertEqual(client.queries, [DEFAULT_PROMPT])
        self.assertEqual(client.disconnect_calls, 1)


if __name__ == "__main__":
    unittest.main()
