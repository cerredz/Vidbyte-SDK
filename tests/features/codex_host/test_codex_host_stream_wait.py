"""FILE: tests/features/codex_host/test_codex_host_stream_wait.py

PURPOSE: Proves stream_codex_turn and wait_codex_turns over the in-memory app-server: one ordered, numbered event per streamed notification ending in exactly one ENDED whose snapshot is wait_codex_turn's; no raw reasoning text in any event or log; the per-turn and per-host bounds dropping each log's own oldest events and showing a lagging subscriber one GAP; a subscription counted as reading only while its generator runs, so an un-iterated, abandoned or closed one releases the window at the turn's end; the eager handle check at the call; and wait_codex_turns returning one snapshot per handle in order without touching any turn.
ROLE IN CODEBASE: Stream and wait layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-12 to AC-18, AC-43, AC-44, INV-18 to INV-23, D-9 to D-13, D-37, D-39, EC-3, EC-4, EC-17 to EC-22, EC-55, EC-60, EC-62, and section 13's dedicated stream_codex_turn boundary test). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: A subscriber reads its first event with anext right after the first notification is emitted, so it is counted as reading before the rest arrive; the rest are emitted in one block, which the fake writes in order and the host records in order. The bounds are patched in vidbyte.harnesses.native.codex.turn_stream, where section 13 says they are read at call time. The host's kept totals are read with CodexTurnRegistry.charge_stream(0, 0), which adds nothing.
COMMON MODIFICATION PATTERNS: Add a notification row to the AC-12 order test when CODEX_HOST_STREAM_NOTIFICATION_KINDS gains a method. Keep every bound test's arithmetic in its comment, so a changed bound rule shows which count moved.
KNOWN EDGE CASES: An abandoned generator is finalized by asyncio's async-generator hooks, which schedule aclose() on the loop, so that test yields to the loop with asyncio.sleep(0), a scheduler yield and never a timed wait, until the totals reach zero. The AC-17 timeout of 0.2 seconds elapses by design while both turns stay running. The EC-55 handler holds the SDK reader thread, so the test writes the later events and only then releases it, and asserts what arrives, not how long the pause lasts. The malformed delta of EC-20 omits its delta member, so openai-codex delivers it as an UnknownNotification routed by its turnId.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1, 6.2, 6.3, 8.1 and 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_stream_wait.py
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import unittest
from collections.abc import AsyncIterator
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_feature_support import DELTA_CANARY, FEATURE_NUMBERS
from tests.features.codex_host.codex_host_support import FeatureHostCase, WAIT_SECONDS, assert_no_canary, log_events, log_fields, mapped_summary, requires_sdk

STREAM_MODULE = "vidbyte.harnesses.native.codex.turn_stream"
UNKNOWN_HANDLE_TEXT = "This host registered no turn {turn_id} on thread {thread_id}; a turn handle works only on the CodexHost that returned it, while that host stays open."
OTHER_LOOP_TEXT = "{operation} was called from another asyncio event loop than the one that opened this CodexHost. The host's turns, watchers and futures belong to that loop, so call {operation} from it, or open a separate CodexHost on this loop."
COMMAND_APPROVAL = "item/commandExecution/requestApproval"
# How many scheduler yields a finalized generator's aclose() may take to run; each is asyncio.sleep(0), never a timer.
LOOP_YIELDS = 200


def _kinds(events: list[Any]) -> list[str]:
    return [event.kind.value for event in events]


async def _first_event(host: Any, handle: Any) -> Any:
    """Subscribe and read one event on whatever loop runs this coroutine."""
    return await anext(host.stream_codex_turn(handle))


def _call_without_a_loop(host: Any, handle: Any) -> BaseException | None:
    """Call stream_codex_turn from a worker thread that runs no event loop (EC-3)."""
    try:
        host.stream_codex_turn(handle)
    except BaseException as exc:  # the test asserts the exact type
        return exc
    return None


class _StreamCase(FeatureHostCase):
    """Shared steps: patch a stream bound, read one event or the rest, and build item notifications."""

    def patch_stream(self, name: str, value: int) -> None:
        patcher = mock.patch(f"{STREAM_MODULE}.{name}", value)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def first(self, stream: AsyncIterator[Any]) -> Any:
        return await self.call(anext(stream))

    async def drain(self, stream: AsyncIterator[Any]) -> list[Any]:
        """Read a subscription to its end; the bound turns a stream that never ends into a failure."""

        async def collect() -> list[Any]:
            return [event async for event in stream]

        return await self.call(collect())

    def items(self, handle: Any, count: int, *, last_final: bool = False) -> list[Any]:
        """Store count commentary messages on the fake turn and return their item/completed notifications."""
        turn = self.server.threads[handle.thread_id].find_turn(handle.turn_id)
        notes = []
        for index in range(count):
            phase = "final_answer" if last_final and index == count - 1 else "commentary"
            item = self.server.final_item(f"Part {index + 1}.", phase)
            turn.items.append(item)
            notes.append(self.server.item_note(handle.thread_id, handle.turn_id, item))
        return notes

    def started(self, handle: Any, item_id: str = "item-a") -> Any:
        return self.server.started_note(handle.thread_id, handle.turn_id, {"type": "agentMessage", "id": item_id, "text": ""})

    def delta(self, handle: Any, text: str, item_id: str = "item-a") -> Any:
        return self.server.delta_note("item/agentMessage/delta", handle.thread_id, handle.turn_id, item_id, text)

    def end(self, handle: Any, final: str | None = None) -> list[Any]:
        return self.server.completion_notes(handle.thread_id, handle.turn_id, final=final)

    @staticmethod
    def kept(host: Any) -> tuple[int, int]:
        """The host's kept stream totals, (characters, events); adding zero reads them (D-39)."""
        return host._registry.charge_stream(0, 0)

    async def yield_loop(self, times: int) -> None:
        # asyncio.sleep(0) only hands the loop to the tasks already scheduled; it waits for no time.
        for _ in range(times):
            await asyncio.sleep(0)

    async def yield_until(self, condition: Any, what: str) -> None:
        # asyncio.sleep(0) only hands the loop to the tasks already scheduled; it waits for no time.
        for _ in range(LOOP_YIELDS):
            if condition():
                return
            await asyncio.sleep(0)
        self.fail(f"{what} did not happen within {LOOP_YIELDS} loop yields")


@requires_sdk
class CodexTurnStreamHostTests(_StreamCase):
    """AC-12 to AC-15, AC-43, AC-44, INV-18 to INV-22, EC-3, EC-4, EC-17 to EC-20, EC-55, EC-60 and EC-62."""

    async def test_a_streamed_turn_yields_each_event_in_order_then_one_ended(self) -> None:
        # AC-12, INV-18, INV-21: consecutive sequences from 1, and ENDED's snapshot is wait_codex_turn's.
        from vidbyte.lib.dataclasses.codex_host_features import CodexPlanStep
        from vidbyte.lib.enums.codex import CodexPlanStepStatus

        host = await self.opened()
        handle = await self.spawn(host)
        stream = host.stream_codex_turn(handle)
        self.server.emit([self.started(handle)])
        events = [await self.first(stream)]
        message = {"type": "agentMessage", "id": "item-a", "text": "Hello world.", "phase": "final_answer"}
        self.server.threads[handle.thread_id].find_turn(handle.turn_id).items.append(message)
        self.server.emit(
            [
                self.delta(handle, "Hel"),
                self.delta(handle, "lo "),
                self.delta(handle, "world."),
                self.server.delta_note("item/plan/delta", handle.thread_id, handle.turn_id, "plan-1", "1. Move"),
                self.server.plan_update_note(handle.thread_id, handle.turn_id, [{"step": "Move the tables.", "status": "inProgress"}], explanation="Two steps."),
                ("thread/tokenUsage/updated", {"threadId": handle.thread_id, "turnId": handle.turn_id, "tokenUsage": self.fakes.token_usage((100, 20), (100, 20))}),
                self.server.item_note(handle.thread_id, handle.turn_id, message),
                *self.end(handle),
            ]
        )
        events += await self.drain(stream)
        self.assertEqual(_kinds(events), ["item_started", "message_delta", "message_delta", "message_delta", "plan_delta", "plan_updated", "usage_updated", "item_completed", "ended"])
        self.assertEqual([event.sequence for event in events], list(range(1, 10)))
        self.assertTrue(all(event.handle == handle for event in events))
        self.assertEqual([event.text for event in events[1:4]], ["Hel", "lo ", "world."])
        self.assertEqual({event.item_id for event in (*events[0:4], events[7])}, {"item-a"})
        self.assertEqual(events[4].text, "1. Move")
        self.assertEqual(events[5].plan_steps, (CodexPlanStep(step="Move the tables.", status=CodexPlanStepStatus.IN_PROGRESS),))
        self.assertEqual(events[5].text, "Two steps.")
        self.assertEqual((events[6].usage.input_tokens, events[6].usage.output_tokens), (100, 20))
        self.assertEqual((events[0].item.id, events[7].item.id, events[7].item.type), ("item-a", "item-a", "agentMessage"))
        self.assertTrue(all(event.snapshot is None for event in events[:-1]))
        self.assertTrue(all(event.item is None for event in events[1:7]))
        snapshot = await self.call(host.wait_codex_turn(handle))
        self.assertEqual(events[-1].snapshot, snapshot)
        self.assertEqual(snapshot.result.final_response, "Hello world.")

    async def test_raw_reasoning_text_never_reaches_a_stream_or_a_log(self) -> None:
        # AC-13, D-12: textDelta is not in the kinds table, and a reasoning item's content is left out.
        records = self.capture_logs()
        host = await self.opened()
        handle = await self.spawn(host)
        reasoning = self.server.reasoning_item("Checked the tests.", DELTA_CANARY)
        stream = host.stream_codex_turn(handle)
        self.server.emit([self.server.started_note(handle.thread_id, handle.turn_id, {**reasoning, "summary": [], "content": []})])
        events = [await self.first(stream)]
        self.server.threads[handle.thread_id].find_turn(handle.turn_id).items.append(reasoning)
        self.server.emit(
            [
                self.server.delta_note("item/reasoning/textDelta", handle.thread_id, handle.turn_id, reasoning["id"], DELTA_CANARY, contentIndex=0),
                self.server.delta_note("item/reasoning/summaryTextDelta", handle.thread_id, handle.turn_id, reasoning["id"], "Checked", summaryIndex=0),
                self.server.item_note(handle.thread_id, handle.turn_id, reasoning),
                *self.end(handle, final="Done."),
            ]
        )
        events += await self.drain(stream)
        self.assertEqual(_kinds(events), ["item_started", "reasoning_summary_delta", "item_completed", "item_completed", "ended"])
        self.assertEqual(events[1].text, "Checked")
        self.assertEqual(events[2].item.type, "reasoning")
        self.assertNotIn("content", events[2].item.fields)
        assert_no_canary(self, [repr(event) for event in events], (DELTA_CANARY,))
        assert_no_canary(self, [record.getMessage() for record in records], (DELTA_CANARY,))

    async def test_a_slow_approval_handler_holds_an_open_stream_and_every_event_arrives_once_it_answers(self) -> None:
        # EC-55, INV-19: the handler blocks the SDK reader, so the events written meanwhile wait, then all arrive in order.
        from vidbyte.lib.dataclasses.codex_host import CodexServerAnswer
        from vidbyte.lib.enums.codex import CodexApprovalDecision

        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow_handler(request: Any) -> Any:
            entered.set()
            await release.wait()
            return CodexServerAnswer(decision=CodexApprovalDecision.ACCEPT)

        host = await self.opened(approval_handler=slow_handler)
        handle = await self.spawn(host)
        stream = host.stream_codex_turn(handle)
        self.server.emit([self.started(handle)])
        events = [await self.first(stream)]
        answer = self.server.server_request(COMMAND_APPROVAL, {"threadId": handle.thread_id, "turnId": handle.turn_id, "itemId": "item-command"})
        await self.call(entered.wait())
        # Codex keeps writing while the handler thinks; the reader reads none of it until the handler answers.
        self.server.emit([self.delta(handle, "Hel"), self.delta(handle, "lo."), *self.end(handle)])
        release.set()
        self.assertEqual(await self.call(asyncio.wrap_future(answer)), {"decision": "accept"})
        events += await self.drain(stream)
        self.assertEqual(_kinds(events), ["item_started", "message_delta", "message_delta", "ended"])
        self.assertEqual([event.sequence for event in events], [1, 2, 3, 4])
        self.assertEqual([event.text for event in events[1:3]], ["Hel", "lo."])

    async def test_a_stalled_subscriber_gets_one_gap_then_the_kept_window_and_never_delays_the_turn(self) -> None:
        # AC-14, INV-19, INV-20: limit 3; events 1..7, the subscriber read 1, so 5..7 are kept and GAP(2) counts 2, 3 and 4.
        self.patch_stream("CODEX_HOST_STREAM_EVENT_LIMIT", 3)
        host = await self.opened()
        handle = await self.spawn(host)
        stream = host.stream_codex_turn(handle)
        self.server.emit([self.started(handle)])
        await self.first(stream)
        self.server.emit([*self.items(handle, 6, last_final=True), *self.end(handle)])
        snapshot = await self.wait_done(host, handle)
        self.assertEqual((snapshot.status.value, snapshot.result.final_response, len(snapshot.result.items)), ("completed", "Part 6.", 6))
        # The subscription is still reading, so the three kept events stay charged to the host until it finishes.
        self.assertEqual(self.kept(host)[1], 3)
        rest = await self.drain(stream)
        self.assertEqual(_kinds(rest), ["gap", "item_completed", "item_completed", "item_completed", "ended"])
        self.assertEqual((rest[0].sequence, rest[0].dropped), (2, 3))
        self.assertEqual([event.sequence for event in rest[1:4]], [5, 6, 7])
        self.assertEqual(rest[-1].snapshot, snapshot)
        self.assertEqual(self.kept(host), (0, 0))

    async def test_an_ended_turn_streams_only_ended_and_an_unknown_handle_is_refused_at_the_call(self) -> None:
        # AC-15, INV-22: the check is eager, so the unknown handle raises before any iteration and sends nothing.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
        from vidbyte.lib.errors import CodexAgentError

        host = await self.opened()
        handle = await self.spawn(host)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
        snapshot = await self.wait_done(host, handle)
        events = await self.drain(host.stream_codex_turn(handle))
        self.assertEqual(_kinds(events), ["ended"])
        self.assertEqual(events[0].snapshot, snapshot)
        foreign = CodexTurnHandle(thread_id=handle.thread_id, turn_id="turn-elsewhere")
        self.remark()
        with self.assertRaises(CodexAgentError) as caught:
            host.stream_codex_turn(foreign)
        self.assertEqual((caught.exception.failure_code, caught.exception.operation), ("codex.session_not_found", "stream_codex_turn"))
        self.assertEqual(mapped_summary(self, caught.exception), UNKNOWN_HANDLE_TEXT.format(turn_id=foreign.turn_id, thread_id=foreign.thread_id))
        self.assertEqual(self.sent_methods(), [])

    async def test_stream_codex_turn_checks_its_argument_at_the_call(self) -> None:
        # Section 13's dedicated boundary test, INV-1, D-10: a plain def builds CodexTurnRef before returning the iterator.
        from vidbyte.lib.errors import ConfigurationError

        host = await self.opened()
        for bad in ("turn-1", None, ("thr-1", "turn-1")):
            with self.subTest(argument=repr(bad)):
                with self.assertRaises(ConfigurationError):
                    host.stream_codex_turn(bad)
        self.assertEqual(self.sent_methods(), [])

    async def test_streaming_without_a_running_loop_raises_pythons_own_runtime_error(self) -> None:
        # EC-3, INV-2's one exception: _guard's asyncio.get_running_loop() raises, before any record or request.
        host = await self.opened()
        handle = await self.spawn(host)
        self.remark()
        outcome = await asyncio.to_thread(_call_without_a_loop, host, handle)
        self.assertIs(type(outcome), RuntimeError)
        self.assertIn("no running event loop", str(outcome))
        self.assertEqual(self.sent_methods(), [])

    async def test_a_stream_called_or_iterated_on_another_loop_is_refused(self) -> None:
        # EC-2 and INV-22: the call on another loop is refused by _guard; a subscription made here refuses its first step there.
        from vidbyte.lib.errors import ConfigurationError

        host = await self.opened()
        handle = await self.spawn(host)
        called = await self.run_in_other_loop(lambda: _first_event(host, handle))
        self.assertIsInstance(called, ConfigurationError)
        self.assertEqual(str(called), OTHER_LOOP_TEXT.format(operation="stream_codex_turn"))
        stream = host.stream_codex_turn(handle)
        iterated = await self.run_in_other_loop(lambda: anext(stream))
        self.assertIsInstance(iterated, ConfigurationError)
        self.assertEqual(str(iterated), OTHER_LOOP_TEXT.format(operation="stream_codex_turn"))

    async def test_a_subscription_never_iterated_holds_nothing_and_reads_one_gap_then_ended(self) -> None:
        # AC-43, EC-60, D-37: it was never counted as reading, so the turn's end releases every kept event.
        host = await self.opened()
        handle = await self.spawn(host)
        stream = host.stream_codex_turn(handle)
        self.server.emit([*self.items(handle, 3, last_final=True), *self.end(handle)])
        await self.wait_done(host, handle)
        self.assertEqual(self.kept(host), (0, 0))
        events = await self.drain(stream)
        self.assertEqual(_kinds(events), ["gap", "ended"])
        self.assertEqual((events[0].sequence, events[0].dropped), (1, 3))

    async def test_an_abandoned_subscription_releases_the_window_once_asyncio_finalizes_it(self) -> None:
        # EC-60, INV-21: the generator's finally lowers the reading count when asyncio closes it, then the log releases.
        host = await self.opened()
        handle = await self.spawn(host)
        stream = host.stream_codex_turn(handle)
        self.server.emit([self.started(handle)])
        await self.first(stream)
        self.server.emit([*self.items(handle, 2, last_final=True), *self.end(handle)])
        await self.wait_done(host, handle)
        self.assertEqual(self.kept(host)[1], 3)
        del stream
        gc.collect()
        await self.yield_until(lambda: self.kept(host) == (0, 0), "the abandoned subscription's release")

    async def test_a_subscriber_that_leaves_early_through_aclosing_releases_at_once(self) -> None:
        # EC-17: contextlib.aclosing closes the generator at the break, so the turn's end releases at once.
        host = await self.opened()
        handle = await self.spawn(host)
        async with contextlib.aclosing(host.stream_codex_turn(handle)) as stream:
            self.server.emit([self.started(handle)])
            await self.first(stream)
        self.server.emit([*self.items(handle, 2, last_final=True), *self.end(handle)])
        snapshot = await self.wait_done(host, handle)
        self.assertEqual(snapshot.status.value, "completed")
        self.assertEqual(self.kept(host), (0, 0))
        self.assertEqual(_kinds(await self.drain(host.stream_codex_turn(handle))), ["ended"])

    async def test_a_fast_and_a_stalled_subscriber_keep_their_own_positions(self) -> None:
        # EC-18, INV-22: limit 3 and events 1..6; the stalled one read 1, so it sees GAP(2) counting 2 and 3, then 4..6.
        self.patch_stream("CODEX_HOST_STREAM_EVENT_LIMIT", 3)
        host = await self.opened()
        handle = await self.spawn(host)
        fast = host.stream_codex_turn(handle)
        stalled = host.stream_codex_turn(handle)
        self.server.emit([self.started(handle)])
        fast_events = [await self.first(fast)]
        stalled_events = [await self.first(stalled)]
        for note in self.items(handle, 5, last_final=True):
            self.server.emit([note])
            fast_events.append(await self.first(fast))
        self.server.emit(self.end(handle))
        fast_events += await self.drain(fast)
        stalled_events += await self.drain(stalled)
        self.assertEqual(_kinds(fast_events), ["item_started", *["item_completed"] * 5, "ended"])
        self.assertEqual([event.sequence for event in fast_events[:-1]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(_kinds(stalled_events), ["item_started", "gap", "item_completed", "item_completed", "item_completed", "ended"])
        self.assertEqual((stalled_events[1].sequence, stalled_events[1].dropped), (2, 2))
        self.assertEqual([event.sequence for event in stalled_events[2:5]], [4, 5, 6])
        self.assertEqual(fast_events[-1].snapshot, stalled_events[-1].snapshot)

    async def test_an_event_larger_than_the_text_bound_is_dropped_and_counted(self) -> None:
        # EC-19, INV-20: the diff alone passes the bound, so it is dropped and shown as GAP(dropped=1); the snapshot keeps its item.
        self.patch_stream("CODEX_HOST_STREAM_TEXT_LIMIT_CHARS", 300)
        host = await self.opened()
        handle = await self.spawn(host)
        stream = host.stream_codex_turn(handle)
        self.server.emit([self.delta(handle, "Hi")])
        events = [await self.first(stream)]
        self.server.emit([self.server.diff_note(handle.thread_id, handle.turn_id, "+" * 1000), self.delta(handle, " there"), *self.end(handle, final="Hi there")])
        events += await self.drain(stream)
        self.assertEqual(_kinds(events), ["message_delta", "gap", "message_delta", "item_completed", "ended"])
        self.assertEqual((events[1].sequence, events[1].dropped), (2, 1))
        self.assertEqual(events[2].sequence, 3)
        self.assertEqual(events[-1].snapshot.result.final_response, "Hi there")

    async def test_a_notification_that_cannot_be_translated_is_logged_once_and_shown_as_a_gap(self) -> None:
        # EC-20, INV-19: record never raises; the drop is logged once with ids, method and type, and the turn ends normally.
        records = self.capture_logs()
        host = await self.opened()
        handle = await self.spawn(host)
        stream = host.stream_codex_turn(handle)
        self.server.emit([self.delta(handle, "Hi")])
        events = [await self.first(stream)]
        malformed = ("item/agentMessage/delta", {"itemId": "item-a", "threadId": handle.thread_id, "turnId": handle.turn_id})
        self.server.emit([malformed, self.delta(handle, " there"), *self.end(handle, final="Hi there")])
        events += await self.drain(stream)
        self.assertEqual(_kinds(events), ["message_delta", "gap", "message_delta", "item_completed", "ended"])
        self.assertEqual((events[1].sequence, events[1].dropped), (2, 1))
        snapshot = events[-1].snapshot
        self.assertEqual((snapshot.status.value, snapshot.problem), ("completed", None))
        dropped = log_events(records, "codex_host_stream_event_dropped")
        self.assertEqual(len(dropped), 1)
        fields = log_fields(dropped[0])
        self.assertEqual(sorted(fields), ["error_type", "method", "origin", "thread_id", "turn_id"])
        self.assertEqual((fields["method"], fields["thread_id"], fields["turn_id"]), ("item/agentMessage/delta", handle.thread_id, handle.turn_id))
        self.assertEqual(dropped[0].levelname, "WARNING")

    async def test_the_host_bound_drops_each_turns_own_oldest_events_and_refunds_them_on_release(self) -> None:
        # AC-44, EC-62, D-39: a host limit of 3 events across two turns; each log drops only its own oldest.
        self.patch_stream("CODEX_HOST_STREAM_HOST_EVENT_LIMIT", 3)
        host = await self.opened()
        first_turn = await self.spawn(host)
        second_turn = await self.spawn(host)
        streams = {first_turn: host.stream_codex_turn(first_turn), second_turn: host.stream_codex_turn(second_turn)}
        for handle, stream in streams.items():
            self.server.emit([self.started(handle)])
            await self.first(stream)
        self.server.emit([*self.items(first_turn, 4, last_final=True), *self.items(second_turn, 4, last_final=True)])
        self.server.emit([*self.end(first_turn), *self.end(second_turn)])
        snapshots = {handle: await self.wait_done(host, handle) for handle in streams}
        self.assertLessEqual(self.kept(host)[1], 3)
        rests = {handle: await self.drain(stream) for handle, stream in streams.items()}
        middles = {handle: [event for event in rest if event.kind.value not in ("gap", "ended")] for handle, rest in rests.items()}
        self.assertLessEqual(sum(len(middle) for middle in middles.values()), 3)
        for handle, rest in rests.items():
            with self.subTest(turn=handle.turn_id):
                self.assertTrue(all(event.handle == handle for event in rest))
                self.assertEqual(rest[0].kind.value, "gap")
                self.assertEqual((rest[0].sequence, rest[0].dropped), (2, 4 - len(middles[handle])))
                self.assertEqual([event.sequence for event in middles[handle]], list(range(6 - len(middles[handle]), 6)))
                self.assertEqual(_kinds(rest), ["gap", *["item_completed"] * len(middles[handle]), "ended"])
                self.assertEqual(rest[-1].snapshot, snapshots[handle])
                self.assertEqual(rest[-1].snapshot, await self.call(host.wait_codex_turn(handle)))
        self.assertEqual(self.kept(host), (0, 0))

    async def test_goal_runs_and_reviews_end_their_streams_with_ended(self) -> None:
        # INV-18, INV-21: every CodexLiveTurn owns a log, and a goal finishing or a review completing closes it.
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        host = await self.opened()
        goal = await self.call(host.run_codex_goal("Ship the fix."))
        stream = host.stream_codex_turn(goal)
        self.server.emit([self.started(goal)])
        events = [await self.first(stream)]
        self.server.emit([self.server.goal_update(goal.thread_id, "complete"), *self.end(goal, final="Shipped.")])
        events += await self.drain(stream)
        self.assertEqual(_kinds(events)[-2:], ["item_completed", "ended"])
        self.assertEqual(events[-1].snapshot.goal_status.value, "complete")
        self.assertEqual(events[-1].snapshot, await self.call(host.wait_codex_turn(goal)))

        seeded = self.server.seed_thread(completed_turns=1)
        review = await self.call(host.start_codex_review(seeded.thread_id, CodexReviewTarget(kind=CodexReviewTargetKind.COMMIT, sha="0a1b2c3")))
        stream = host.stream_codex_turn(review)
        self.server.emit([self.started(review)])
        events = [await self.first(stream)]
        self.server.emit(self.end(review, final="Looks good to merge."))
        events += await self.drain(stream)
        self.assertEqual(_kinds(events)[-1], "ended")
        self.assertEqual(events[-1].snapshot.result.final_response, "Looks good to merge.")

    async def test_a_dead_app_server_ends_every_stream_with_ended(self) -> None:
        # EC-4, INV-21: process death ends every running turn, and each subscription yields ENDED last.
        host = await self.opened()
        handles = (await self.spawn(host), await self.spawn(host))
        streams = [host.stream_codex_turn(handle) for handle in handles]
        for handle, stream in zip(handles, streams):
            self.server.emit([self.started(handle)])
            await self.first(stream)
        self.server.die("the app-server stopped")
        for handle, stream in zip(handles, streams):
            with self.subTest(turn=handle.turn_id):
                rest = await self.drain(stream)
                self.assertEqual(_kinds(rest)[-1], "ended")
                self.assertEqual(rest[-1].snapshot.problem.code.value, "codex.process_exited")


@requires_sdk
class CodexTurnsWaitHostTests(_StreamCase):
    """AC-16 to AC-18, INV-23, EC-21 and EC-22."""

    async def test_a_first_completed_wait_returns_every_snapshot_in_order_and_touches_no_turn(self) -> None:
        # AC-16, D-13: one snapshot per handle in the order given; the running ones stay running.
        host = await self.opened()
        first, second, third = await self.spawn(host), await self.spawn(host), await self.spawn(host)
        waiting = asyncio.ensure_future(host.wait_codex_turns((first, second, third)))
        self.server.complete_turn(second.thread_id, second.turn_id, final="Second done.")
        snapshots = await self.call(waiting)
        self.assertEqual([snapshot.handle for snapshot in snapshots], [first, second, third])
        self.assertEqual([snapshot.status.value for snapshot in snapshots], ["inProgress", "completed", "inProgress"])
        self.assertEqual(self.count("turn/interrupt"), 0)
        for handle in (first, third):
            self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
            self.assertEqual((await self.wait_done(host, handle)).status.value, "completed")
        # D-13: asyncio's own constant is the same mode.
        again = await self.call(host.wait_codex_turns((first,), return_when=asyncio.FIRST_COMPLETED))
        self.assertEqual([snapshot.status.value for snapshot in again], ["completed"])

    async def test_an_all_completed_wait_returns_running_snapshots_at_its_timeout_and_sends_nothing(self) -> None:
        # AC-17, INV-23: the timeout returns anyway; ALL_COMPLETED returns once both ended.
        from vidbyte.lib.enums.codex import CodexTurnWaitMode

        host = await self.opened()
        first, second = await self.spawn(host), await self.spawn(host)
        self.remark()
        snapshots = await self.call(host.wait_codex_turns((first, second), return_when=CodexTurnWaitMode.ALL_COMPLETED, timeout_seconds=0.2))
        self.assertEqual([snapshot.status.value for snapshot in snapshots], ["inProgress", "inProgress"])
        self.assertEqual(self.sent_methods(), [])
        waiting = asyncio.ensure_future(host.wait_codex_turns((first, second), return_when=CodexTurnWaitMode.ALL_COMPLETED))
        self.server.complete_turn(first.thread_id, first.turn_id, final="One.")
        self.server.complete_turn(second.thread_id, second.turn_id, final="Two.")
        self.assertEqual([snapshot.status.value for snapshot in await self.call(waiting)], ["completed", "completed"])

    async def test_bad_handle_tuples_are_refused_before_any_wait(self) -> None:
        # AC-18, EC-21: the record refuses empty, duplicate and oversized tuples; an unknown handle is refused by _owned.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        host = await self.opened()
        running = await self.spawn(host)
        maximum = FEATURE_NUMBERS["CODEX_HOST_WAIT_MAX_HANDLES"]
        too_many = tuple(CodexTurnHandle(thread_id="thr-many", turn_id=f"turn-{index}") for index in range(maximum + 1))
        self.remark()
        for label, handles in (("empty", ()), ("duplicate", (running, running)), ("too many", too_many)):
            with self.subTest(handles=label):
                await self.refused_locally(host.wait_codex_turns(handles), "handles")
        foreign = CodexTurnHandle(thread_id=running.thread_id, turn_id="turn-from-another-host")
        # The running turn would hold a wait open, so returning at all proves the refusal came first.
        error = await self.codex_error(host.wait_codex_turns((running, foreign)), "codex.session_not_found")
        self.assertEqual(error.operation, "wait_codex_turns")
        self.assertEqual(mapped_summary(self, error), UNKNOWN_HANDLE_TEXT.format(turn_id=foreign.turn_id, thread_id=foreign.thread_id))
        self.assertEqual(self.sent_methods(), [])

    async def test_cancelling_the_waiter_leaves_every_turn_running(self) -> None:
        # EC-22, D-13: asyncio.wait never cancels the futures it waits on.
        from vidbyte.lib.enums.codex import CodexTurnWaitMode

        host = await self.opened()
        first, second = await self.spawn(host), await self.spawn(host)
        waiting = asyncio.ensure_future(host.wait_codex_turns((first, second), return_when=CodexTurnWaitMode.ALL_COMPLETED))
        # Let the waiter run up to its asyncio.wait before it is cancelled.
        await self.yield_loop(3)
        self.assertFalse(waiting.done())
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(waiting, WAIT_SECONDS)
        for handle in (first, second):
            self.assertEqual((await self.call(host.get_codex_turn_result(handle))).status.value, "inProgress")
        self.assertEqual(self.count("turn/interrupt"), 0)
        again = asyncio.ensure_future(host.wait_codex_turns((first, second), return_when=CodexTurnWaitMode.ALL_COMPLETED))
        for handle in (first, second):
            self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
        self.assertEqual([snapshot.status.value for snapshot in await self.call(again)], ["completed", "completed"])

    async def test_a_turn_that_already_ended_returns_a_first_completed_wait_at_once(self) -> None:
        # INV-23: FIRST_COMPLETED returns at once when one handle had already ended, with no timeout given.
        host = await self.opened()
        running, ended = await self.spawn(host), await self.spawn(host)
        self.server.complete_turn(ended.thread_id, ended.turn_id, final="Done.")
        await self.wait_done(host, ended)
        snapshots = await self.call(host.wait_codex_turns((running, ended)))
        self.assertEqual([snapshot.status.value for snapshot in snapshots], ["inProgress", "completed"])


if __name__ == "__main__":
    unittest.main()
