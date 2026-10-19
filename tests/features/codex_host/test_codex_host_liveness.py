"""FILE: tests/features/codex_host/test_codex_host_liveness.py

PURPOSE: Proves a hardened CodexHost never leaves a turn running and a wait never hangs: a plain turn or a goal run whose notification cannot be processed ends FAILED with one stop; a turn whose watcher read fails while the host is open ends FAILED after the grace with one cleanup interrupt and one WARNING, with no second interrupt when its stop was already sent, and with no interrupt and no lost-turn record when a close starts inside the grace; a process death and an ordinary goal-run end take the normal paths and write no lost-turn record; and a review whose completion read-back raises a non-Codex error, or whose read-back finds it ended but whose snapshot cannot be built, inline or late, still ends.
ROLE IN CODEBASE: Liveness layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-7, AC-8, AC-9, INV-11 to INV-14, INV-45, EC-16 to EC-18, EC-53, D-7, D-9, and the S4 review rows R-3 and R-8). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The faults are injected at the seams spec section 13 names: CodexResponseTranslator.turn_snapshot, goal_snapshot or stored_turn raise (the INV-11 path finishes through failed, which is not patched), and the client's notification read raises before the spawn binds it. CODEX_HOST_LOST_TURN_GRACE_SECONDS is patched where turn_events reads it at call time: short for the lost-turn test, long for the goal-run test so a wait that sat out the grace would fail its bound, and TIMED_GRACE_SECONDS for the two R-8 timing rows. The R-3 rows convert what escapes start_codex_review and a wait still pending at its bound into assertion failures, so a regression reads as a broken promise rather than an error.
COMMON MODIFICATION PATTERNS: A new way for a turn to end adds one test that ends it and waits with no timeout under asyncio.wait_for.
KNOWN EDGE CASES: After a death the lost-turn path may still be inside its grace, so the death test joins every watcher thread and waits out the loop's other tasks before it checks that no lost-turn record was written. Every wait without a timeout is bounded from outside, so a regression fails in WAIT_SECONDS instead of hanging the run. The close-inside-the-grace row is a deliberate time-bound negative check: it sleeps until two and a half graces after the read failed, then counts the interrupts sent meanwhile; the grace-gap row keeps a quarter of the grace in hand for the coarse Windows clock.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 6.1 (INV-11 to INV-14) and 13 (fault-injection seams).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_liveness.py
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import unittest
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_support import (
    CLOSE_SECONDS,
    EVENT_FAILED_MESSAGE,
    LOST_EVENTS_MESSAGE,
    TURN_EVENTS_MODULE,
    WAIT_SECONDS,
    HostTestCase,
    assert_no_canary,
    is_review_read_back,
    log_events,
    log_fields,
    requires_sdk,
)
from vidbyte.lib.errors import CodexAgentError

TRANSLATOR = "vidbyte.harnesses.native.codex.wire.CodexResponseTranslator"
WATCHER_NAME = "codex-host-watcher"
EVENT_CANARY = "event-canary-6b2e"
WATCHER_CANARY = "watcher-canary-0c7a"
REVIEW_CANARY = "review-canary-d913"
SNAPSHOT_CANARY = "snapshot-canary-5f04"
# The patched grace of the two S4 R-8 timing rows: long enough that close starts well inside it, short enough to wait out.
TIMED_GRACE_SECONDS = 0.4


def _review_target() -> Any:
    from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
    from vidbyte.lib.enums.codex import CodexReviewTargetKind

    return CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)


def _ended_review(*args: Any) -> Any:
    # The review read-back finds the review already ended, so the review is built from what was read back (D-23, S4 R-3).
    return SimpleNamespace(id=args[-1], status=SimpleNamespace(value="completed"), items=[])


class LivenessTestCase(HostTestCase):
    """HostTestCase plus the grace patch, the goal spawn and the drain these tests share."""

    def patch_grace(self, seconds: float) -> None:
        """Patch the lost-turn grace where turn_events reads it at call time (spec section 13)."""
        patcher = mock.patch(f"{TURN_EVENTS_MODULE}.CODEX_HOST_LOST_TURN_GRACE_SECONDS", seconds)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def spawn_goal(self, host: Any) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest

        request = CodexSpawnRequest(goal=CodexGoal(objective="Ship the release notes."))
        return await asyncio.wait_for(host.spawn_codex_thread(request), WAIT_SECONDS)

    async def wait_unbounded(self, host: Any, handle: Any) -> Any:
        """wait_codex_turn with no timeout, as INV-14 promises it returns; bounded here so a hang fails."""
        return await asyncio.wait_for(host.wait_codex_turn(handle), WAIT_SECONDS)

    async def drain(self) -> None:
        """Let every watcher thread end and every task it posted run to its end, so a late log record is seen."""
        for thread in [thread for thread in threading.enumerate() if thread.name == WATCHER_NAME]:
            await asyncio.to_thread(thread.join, WAIT_SECONDS)
        # A watcher posts with call_soon_threadsafe; one turn of the loop runs what it posted.
        await asyncio.sleep(0)
        others = {task for task in asyncio.all_tasks() if task is not asyncio.current_task()}
        if others:
            await asyncio.wait(others, timeout=WAIT_SECONDS)

    async def start_review_or_fail(self, host: Any, thread_id: str) -> Any:
        """start_codex_review must return the review's handle; anything it raises fails the test (S4 R-3)."""
        try:
            return await asyncio.wait_for(host.start_codex_review(thread_id, _review_target()), WAIT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - the row's claim is that nothing escapes, so what escaped is the failure
            self.fail(f"start_codex_review raised {type(exc).__name__} instead of returning the review's handle")

    async def wait_or_fail(self, host: Any, handle: Any) -> Any:
        """wait_codex_turn with no timeout must return (INV-14); a wait still pending at the bound fails the test."""
        try:
            return await asyncio.wait_for(host.wait_codex_turn(handle), WAIT_SECONDS)
        except TimeoutError:
            self.fail(f"the unbounded wait on turn {handle.turn_id} was still pending after {WAIT_SECONDS} seconds")

    async def assert_next_review_accepted(self, host: Any, thread_id: str) -> None:
        """The thread takes another review once the failed one ended, so nothing of it is left running (S4 R-3)."""
        try:
            handle = await asyncio.wait_for(host.start_codex_review(thread_id, _review_target()), WAIT_SECONDS)
        except CodexAgentError as exc:
            self.fail(f"the next review was refused with {exc.failure_code}")
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Reviewed.")
        self.assert_problem(await self.wait_done(host, handle), "completed", None)

    def goal_cancels(self, thread_id: str) -> int:
        return sum(1 for entry in self.server.kinds("cancel_goal_operation") if entry[1] == thread_id)

    def interrupts(self, thread_id: str) -> int:
        return self.count("turn/interrupt", lambda params: params.get("threadId") == thread_id)

    def assert_event_failed(self, records: list[logging.LogRecord], handle: Any) -> None:
        failed = log_events(records, "codex_host_turn_event_failed")
        self.assertEqual(len(failed), 1, [record.getMessage() for record in failed])
        self.assertEqual(failed[0].levelno, logging.WARNING)
        fields = log_fields(failed[0])
        self.assertEqual((fields["thread_id"], fields["turn_id"], fields["error_type"]), (handle.thread_id, handle.turn_id, "RuntimeError"))
        self.assertTrue(fields["origin"], fields)


@requires_sdk
class CodexEventFailureTests(LivenessTestCase):
    """AC-7, INV-11 and INV-14: a notification that cannot be processed stops and fails the turn."""

    async def test_a_plain_turn_whose_completion_cannot_be_processed_fails_with_one_interrupt(self) -> None:
        records = self.capture_logs()
        host = await self.open_host()
        handle = await self.spawn(host)
        with mock.patch(f"{TRANSLATOR}.turn_snapshot", side_effect=RuntimeError(EVENT_CANARY)):
            self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
            snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "failed", "codex.protocol_mismatch")
        self.assertIn(EVENT_FAILED_MESSAGE, snapshot.problem.message)
        await self.wait_for_request("turn/interrupt", lambda params: params.get("threadId") == handle.thread_id)
        await asyncio.wait_for(host.read_codex_thread(handle.thread_id), WAIT_SECONDS)
        self.assertEqual(self.interrupts(handle.thread_id), 1)
        self.assert_event_failed(records, handle)
        assert_no_canary(self, [record.getMessage() for record in records] + [snapshot.problem.message], (EVENT_CANARY,))

    async def test_a_goal_run_whose_update_cannot_be_processed_fails_with_one_goal_cancel_and_closes_its_stream(self) -> None:
        records = self.capture_logs()
        host = await self.open_host()
        handle = await self.spawn_goal(host)
        with mock.patch(f"{TRANSLATOR}.goal_snapshot", side_effect=RuntimeError(EVENT_CANARY)):
            self.server.emit([self.server.goal_update(handle.thread_id, "complete")])
            self.server.complete_turn(handle.thread_id, handle.turn_id, final="Release notes shipped.")
            snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "failed", "codex.protocol_mismatch")
        self.assertIn(EVENT_FAILED_MESSAGE, snapshot.problem.message)
        await self.wait_until(lambda: self.goal_cancels(handle.thread_id) >= 1, "the goal cancel")
        await self.wait_until(lambda: ("unregister_goal_operation", handle.thread_id) in [entry[:2] for entry in self.server.log], "the goal stream to close")
        await self.drain()
        self.assertEqual(self.goal_cancels(handle.thread_id), 1)
        self.assert_event_failed(records, handle)


@requires_sdk
class CodexLostWatcherTests(LivenessTestCase):
    """AC-8, INV-13, INV-14, INV-45 and D-9: a lost watcher ends its turn; a death and a goal end are not losses."""

    async def test_a_watcher_whose_read_fails_on_a_live_host_ends_the_turn_after_the_grace(self) -> None:
        self.patch_grace(0.05)
        records = self.capture_logs()
        host = await self.open_host()
        with mock.patch.object(self.server.client, "next_turn_notification", side_effect=RuntimeError(WATCHER_CANARY)):
            handle = await self.spawn(host)
            snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "failed", "codex.api_error")
        self.assertIn(LOST_EVENTS_MESSAGE, snapshot.problem.message)
        # Step (c) awaits its one cleanup interrupt before step (d) finishes the turn.
        self.assertEqual(self.interrupts(handle.thread_id), 1)
        lost = log_events(records, "codex_host_turn_lost")
        self.assertEqual([(record.levelno, log_fields(record)) for record in lost], [(logging.WARNING, {"thread_id": handle.thread_id, "turn_id": handle.turn_id})])
        assert_no_canary(self, [record.getMessage() for record in records], (WATCHER_CANARY,))

    async def test_a_lost_turn_whose_cleanup_interrupt_fails_still_ends_failed(self) -> None:
        # EC-18: the cleanup interrupt's failure is ignored, sent once, and the turn still ends as a lost turn.
        self.patch_grace(0.05)
        host = await self.open_host()
        self.server.fail("turn/interrupt", self.fakes.FakeRpcError(-32603, "interrupt store failed"), times=1)
        with mock.patch.object(self.server.client, "next_turn_notification", side_effect=RuntimeError(WATCHER_CANARY)):
            handle = await self.spawn(host)
            snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "failed", "codex.api_error")
        self.assertIn(LOST_EVENTS_MESSAGE, snapshot.problem.message)
        self.assertEqual(self.interrupts(handle.thread_id), 1)

    async def test_a_lost_turn_whose_stop_was_already_sent_gets_no_second_interrupt(self) -> None:
        # INV-13 step (c) and D-7 (S4 R-8, mutant M2): the user stops the turn, then its watcher is lost. The stop was sent,
        # so the lost-turn path sends none of its own, and the turn still ends as a lost turn.
        self.patch_grace(0.05)
        records = self.capture_logs()
        host = await self.open_host()
        gate = threading.Event()
        self.addCleanup(gate.set)

        def blocked_read(*args: Any, **kwargs: Any) -> Any:
            # The watcher's read fails only after the user's stop was sent.
            gate.wait(WAIT_SECONDS)
            raise RuntimeError(WATCHER_CANARY)

        with mock.patch.object(self.server.client, "next_turn_notification", side_effect=blocked_read):
            handle = await self.spawn(host)
            await asyncio.wait_for(host.interrupt_codex_turn(handle), WAIT_SECONDS)
            self.assertEqual(self.interrupts(handle.thread_id), 1)
            gate.set()
            snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "failed", "codex.api_error")
        self.assertIn(LOST_EVENTS_MESSAGE, snapshot.problem.message)
        # Step (c) is awaited before step (d) finishes the turn, so a second interrupt would already have reached the fake.
        self.assertEqual(self.interrupts(handle.thread_id), 1)
        self.assertEqual(len(log_events(records, "codex_host_turn_lost")), 1)

    async def test_the_cleanup_interrupt_of_a_lost_turn_waits_out_the_grace(self) -> None:
        # EC-53 and D-9 (S4 R-8, mutant M20): the cleanup interrupt goes out no earlier than the grace after the read failed,
        # which is the window in which a death or a close wins.
        self.patch_grace(TIMED_GRACE_SECONDS)
        host = await self.open_host()
        failed_at: list[float] = []

        def failing_read(*args: Any, **kwargs: Any) -> Any:
            failed_at.append(time.monotonic())
            raise RuntimeError(WATCHER_CANARY)

        with mock.patch.object(self.server.client, "next_turn_notification", side_effect=failing_read):
            handle = await self.spawn(host)
            await self.wait_for_request("turn/interrupt", lambda params: params.get("threadId") == handle.thread_id)
            arrived_at = time.monotonic()
            snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "failed", "codex.api_error")
        # The arrival is read after the fact, which can only lengthen the gap; a quarter of the grace is kept in hand for
        # the coarse Windows clock, and a grace skipped altogether gives a gap of a few milliseconds.
        self.assertGreaterEqual(arrived_at - failed_at[0], TIMED_GRACE_SECONDS * 0.75)

    async def test_a_close_that_starts_inside_the_grace_wins_and_the_lost_turn_sends_nothing(self) -> None:
        # EC-16, D-9 and INV-13 step (b) (S4 R-8, mutant M21): close starts while the lost-turn path sits in its grace, and
        # close's own interrupt is held. Once the grace is over, the path re-checks, sees the close and stops: exactly one
        # interrupt, and no lost-turn record.
        self.patch_grace(TIMED_GRACE_SECONDS)
        records = self.capture_logs()
        host = await self.open_host()
        failed = threading.Event()
        failed_at: list[float] = []

        def failing_read(*args: Any, **kwargs: Any) -> Any:
            failed_at.append(time.monotonic())
            failed.set()
            raise RuntimeError(WATCHER_CANARY)

        with mock.patch.object(self.server.client, "next_turn_notification", side_effect=failing_read):
            handle = await self.spawn(host)
            self.assertTrue(await asyncio.to_thread(failed.wait, WAIT_SECONDS), "the watcher never read")
            held = self.server.hold("turn/interrupt", lambda params: params.get("threadId") == handle.thread_id)
            closing = asyncio.ensure_future(host.__aexit__(None, None, None))
            try:
                await asyncio.to_thread(held.wait_arrived)
                self.assertLess(time.monotonic() - failed_at[0], TIMED_GRACE_SECONDS, "close's interrupt must arrive inside the grace")
                # A deliberate time-bound negative check: sleep until the grace is long over, then count what was sent.
                await asyncio.sleep(max(0.0, failed_at[0] + TIMED_GRACE_SECONDS * 2.5 - time.monotonic()))
                during = self.interrupts(handle.thread_id)
            finally:
                held.release()
            await asyncio.wait_for(closing, CLOSE_SECONDS)
        self.assertEqual(during, 1)
        await self.drain()
        self.assertEqual(self.interrupts(handle.thread_id), 1)
        self.assertEqual(log_events(records, "codex_host_turn_lost"), [])

    async def test_a_process_death_ends_the_turn_as_exited_and_is_not_logged_as_a_lost_turn(self) -> None:
        records = self.capture_logs()
        host = await self.open_host()
        handle = await self.spawn(host)
        self.server.die("the app-server crashed")
        snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "failed", "codex.process_exited")
        # The real grace runs: every watcher ends and every task it posted finishes before the logs are read.
        await self.drain()
        self.assertEqual(log_events(records, "codex_host_turn_lost"), [])
        self.assertEqual(self.server.kinds("write_after_close"), [])
        # INV-9: the one finish is logged, so the recorder above does see this turn's records.
        ended = [log_fields(record) for record in log_events(records, "codex_host_turn_ended")]
        self.assertEqual(ended, [{"thread_id": handle.thread_id, "turn_id": handle.turn_id, "status": snapshot.status.value, "failure_code": "codex.process_exited"}])

    async def test_a_goal_run_that_ends_normally_sends_no_stop_and_its_wait_does_not_sit_out_the_grace(self) -> None:
        # A goal watcher's read always ends by raising once the stream closes (INV-13 step a); a grace far longer than the
        # wait's bound makes a wait that sat it out fail.
        self.patch_grace(WAIT_SECONDS * 3)
        records = self.capture_logs()
        host = await self.open_host()
        handle = await self.spawn_goal(host)
        self.server.emit([self.server.goal_update(handle.thread_id, "complete")])
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Release notes shipped.")
        snapshot = await self.wait_unbounded(host, handle)
        self.assert_problem(snapshot, "completed", None)
        watchers = {entry[2] for entry in self.server.kinds("next_goal_notification") if entry[1] == handle.thread_id}
        self.assertTrue(watchers)
        for watcher in watchers:
            await asyncio.to_thread(watcher.join, WAIT_SECONDS)
            self.assertFalse(watcher.is_alive(), watcher.name)
        # The read that ended the watcher raised, so the lost-turn path ran and found the snapshot.
        self.assertIn(("next_goal_notification_raised", handle.thread_id), [entry[:2] for entry in self.server.log])
        await asyncio.sleep(0)
        self.assertEqual((self.interrupts(handle.thread_id), self.goal_cancels(handle.thread_id)), (0, 0))
        self.assertEqual(log_events(records, "codex_host_turn_lost"), [])


@requires_sdk
class CodexReviewCompletionFailureTests(LivenessTestCase):
    """AC-9 and INV-12: a review whose completion read-back raises a non-Codex error still ends."""

    async def test_a_review_whose_completion_read_back_raises_ends_failed_and_its_wait_returns(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        records = self.capture_logs()
        host = await self.open_host()
        stored = self.server.seed_thread()
        calls: list[int] = []

        def stored_turn(*args: Any, **kwargs: Any) -> Any:
            # The registration read-back finds nothing yet; the completion read-back raises.
            calls.append(1)
            if len(calls) == 1:
                return None
            raise RuntimeError(REVIEW_CANARY)

        with mock.patch(f"{TRANSLATOR}.stored_turn", side_effect=stored_turn):
            handle = await asyncio.wait_for(host.start_codex_review(stored.thread_id, CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)), WAIT_SECONDS)
            self.server.complete_turn(handle.thread_id, handle.turn_id, final="Reviewed.")
            snapshot = await self.wait_unbounded(host, handle)
        self.assertGreaterEqual(len(calls), 2)
        self.assert_problem(snapshot, "failed", "codex.protocol_mismatch")
        self.assertIn(EVENT_FAILED_MESSAGE, snapshot.problem.message)
        self.assert_event_failed(records, handle)
        assert_no_canary(self, [record.getMessage() for record in records] + [snapshot.problem.message], (REVIEW_CANARY,))

    async def test_a_review_read_back_as_ended_whose_snapshot_cannot_be_built_ends_failed_through_the_failure_path(self) -> None:
        # S4 R-3, INV-12 and INV-14: the registration read-back finds the review already ended, and building its snapshot
        # raises. start still returns the handle, the review ends FAILED with one WARNING, its unbounded wait returns, and
        # the thread takes the next review.
        records = self.capture_logs()
        host = await self.open_host()
        stored = self.server.seed_thread()
        with mock.patch(f"{TRANSLATOR}.stored_turn", side_effect=_ended_review), mock.patch(f"{TRANSLATOR}.turn_snapshot", side_effect=RuntimeError(SNAPSHOT_CANARY)):
            handle = await self.start_review_or_fail(host, stored.thread_id)
            snapshot = await self.wait_or_fail(host, handle)
        self.assert_problem(snapshot, "failed", "codex.protocol_mismatch")
        self.assertIn(EVENT_FAILED_MESSAGE, snapshot.problem.message)
        self.assert_event_failed(records, handle)
        await self.assert_next_review_accepted(host, stored.thread_id)
        # INV-11: the failure path stops the turn with at most one interrupt; the next review sent none.
        self.assertLessEqual(self.interrupts(handle.thread_id), 1)
        assert_no_canary(self, [record.getMessage() for record in records] + [snapshot.problem.message], (SNAPSHOT_CANARY,))

    async def test_a_late_review_read_back_as_ended_whose_snapshot_cannot_be_built_ends_failed(self) -> None:
        # S4 R-3 on the late path: the caller left while review/start was held, so the review is adopted in the background;
        # its read-back finds it ended and the snapshot build raises. The review still ends FAILED and its wait returns.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        records = self.capture_logs()
        host = await self.open_host()
        stored = self.server.seed_thread()
        held = self.server.hold("review/start")
        with mock.patch(f"{TRANSLATOR}.stored_turn", side_effect=_ended_review), mock.patch(f"{TRANSLATOR}.turn_snapshot", side_effect=RuntimeError(SNAPSHOT_CANARY)):
            task = asyncio.ensure_future(host.start_codex_review(stored.thread_id, _review_target()))
            try:
                await asyncio.to_thread(held.wait_arrived)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                held.release()
            # The late review is registered before it is read back, so its read-back request shows the host owns it.
            await self.wait_for_request("thread/turns/list", is_review_read_back)
            handle = CodexTurnHandle(thread_id=stored.thread_id, turn_id=self.server.threads[stored.thread_id].turns[-1].turn_id)
            snapshot = await self.wait_or_fail(host, handle)
        self.assert_problem(snapshot, "failed", "codex.protocol_mismatch")
        self.assertIn(EVENT_FAILED_MESSAGE, snapshot.problem.message)
        self.assert_event_failed(records, handle)
        await self.assert_next_review_accepted(host, stored.thread_id)
        # INV-11: the failure path stops the turn with at most one interrupt; the next review sent none.
        self.assertLessEqual(self.interrupts(handle.thread_id), 1)
        assert_no_canary(self, [record.getMessage() for record in records] + [snapshot.problem.message], (SNAPSHOT_CANARY,))


if __name__ == "__main__":
    unittest.main()
