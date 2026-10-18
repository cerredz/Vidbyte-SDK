"""FILE: vidbyte/harnesses/native/codex/turns.py

PURPOSE: Holds the live state of every turn a CodexHost started: what Codex reported so far (items, usage, the completion), how the turn ended, the goal finish rule of goal runs, the daemon thread that reads each turn's notifications and reports a failed read, and the per-host registry with each thread's usage ledger, which forget_codex_turns can release, and the host's running totals of kept stream events. Every live turn owns one CodexTurnEventLog (turn_stream.py) as its events attribute.
ROLE IN CODEBASE: The live-state layer of vidbyte/harnesses/native/codex/; CodexHost creates turns here, its watchers feed them through CodexTurnEvents, each turn sends its own one stop through CodexConnection, and the response translator in wire.py turns them into snapshots.
ARCHITECTURE NOTE: openai-codex's notification models are imported at module level, so only CodexHost.__aenter__ imports this module (D-21). Everything except CodexTurnWatcher runs on the host's event loop; a watcher only reads and posts with call_soon_threadsafe, its events to on_event and a failed read to on_lost, so no state here needs a lock. Turn items and turn ends are logged by id, type, status and code only, and each id and item type goes through LogToken.of, because Codex chose it (hardening INV-9, INV-10).
COMMON MODIFICATION PATTERNS: Collect a new notification kind in CodexLiveTurn.observe, and stream it through CODEX_HOST_STREAM_NOTIFICATION_KINDS, never here; change goal finishing only together with openai-codex's private _GoalStreamCursor.process, which CodexGoalFinishRule mirrors. A new way a turn ends goes through CodexTurnRegistry.finish, which logs the first outcome.
KNOWN EDGE CASES: Usage notifications carry the thread's cumulative totals, so a turn's own tokens are its latest totals minus the totals before its first report; a goal run spans several physical turns, so its items and usage cover all of them. A goal run's watcher always ends with a failed read once its stream closes, so on_lost runs for every goal run and finds it ended (hardening INV-13). forget drops ended turns and the ledger only; the host checks the thread is idle first (hardening INV-22).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-6 to D-8 and D-19, and 9.2 goal finish rule); docs/spec/codex-host-hardening/spec.md (sections 6.1 INV-9, INV-13 and INV-22, and 8.5); docs/spec/codex-host-first-class/spec.md (INV-18, INV-20, INV-21, INV-51, D-39)
TESTS: tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_review_goals.py, tests/features/codex_host/test_codex_host_liveness.py, tests/features/codex_host/test_codex_host_observability.py, tests/features/codex_host/test_codex_host_function_rows.py, tests/features/codex_host/test_codex_host_stream_wait.py
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

from openai_codex.generated.v2_all import (
    ItemCompletedNotification,
    ThreadGoalClearedNotification,
    ThreadGoalUpdatedNotification,
    ThreadItem,
    ThreadTokenUsage,
    ThreadTokenUsageUpdatedNotification,
    Turn,
    TurnCompletedNotification,
    TurnStartedNotification,
)
from openai_codex.models import Notification

from vidbyte.agents.codex.metrics import CodexMetricsTranslator
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.harnesses.native.codex.turn_stream import CodexTurnEventLog
from vidbyte.lib.constants.codex import CODEX_GOAL_TERMINAL_STATUSES
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_LOG_TOKEN_MAX_CHARS,
    CODEX_HOST_USAGE_COUNTERS,
)
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexRunResult,
    CodexUsage,
    CodexUsageTranslationRequest,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexSpawnRequest,
    CodexThreadUsage,
    CodexTurnHandle,
    CodexTurnSnapshot,
    CodexTurnUsage,
)
from vidbyte.lib.enums.codex import (
    CodexGoalStatus,
    CodexHostOperation,
    CodexTurnStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.util.text import LogToken

if TYPE_CHECKING:
    from openai_codex._goal import _GoalOperationState
    from openai_codex.client import CodexClient

    from vidbyte.harnesses.native.codex.connection import CodexConnection

logger = logging.getLogger(__name__)


class CodexLiveTurn:
    """One turn the host started: what Codex reported so far, and the snapshot it ended with."""

    def __init__(self, handle: CodexTurnHandle, request: CodexSpawnRequest, pricing: CodexAgentSettings, loop: asyncio.AbstractEventLoop, *, review: bool = False) -> None:
        # @intent turn-keeps-its-own-limits-and-pricing
        # The request carries the turn's own output cap, time limit and
        # output schema; pricing names the model Codex resolved for it,
        # so its usage is priced as that model (D-19).
        self.handle = handle
        self.request = request
        self.pricing = pricing
        self.review = review
        self.items: list[ThreadItem] = []
        self.first_usage: ThreadTokenUsage | None = None
        self.latest_usage: ThreadTokenUsage | None = None
        self.completed: Turn | None = None
        self.stop_reason: FailureCode | None = None
        self.stop_sent = False
        self.stop_pending = False
        self.timer: asyncio.TimerHandle | None = None
        self.snapshot: CodexTurnSnapshot | None = None
        self.ended: asyncio.Future[CodexTurnSnapshot] = loop.create_future()
        # Only a goal run carries openai-codex's goal state, and its
        # goal stream is closed once, when the run ends or the host
        # closes.
        self.state: _GoalOperationState | None = None
        self.stream_closed = False
        # Every live turn streams its events through its own bounded
        # log from the moment it is tracked (first-class INV-18).
        self.events = CodexTurnEventLog(handle, loop)

    def observe(self, note: Notification) -> bool:
        # Keep every completed item, logged by id and type only, each
        # as one bounded token because Codex chose them, and the latest
        # usage, and say whether this notification ends the turn
        # (hardening INV-9, INV-10).
        payload = note.payload
        if isinstance(payload, ItemCompletedNotification):
            self.items.append(payload.item)
            item = payload.item.root
            limit = CODEX_HOST_LOG_TOKEN_MAX_CHARS
            logger.debug("codex_host_turn_item thread_id=%s turn_id=%s item_id=%s item_type=%s", LogToken.of(self.handle.thread_id, limit), LogToken.of(self.handle.turn_id, limit), LogToken.of(item.id, limit), LogToken.of(item.type, limit))
        if isinstance(payload, ThreadTokenUsageUpdatedNotification):
            self.first_usage = self.first_usage or payload.token_usage
            self.latest_usage = payload.token_usage
        if isinstance(payload, TurnCompletedNotification):
            self.completed = payload.turn
        return self.ends(payload)

    def ends(self, payload: object) -> bool:
        # A plain turn ends when Codex completes it.
        return isinstance(payload, TurnCompletedNotification)

    def usage_delta(self) -> CodexUsage | None:
        # This turn's own tokens: the latest thread totals minus the
        # totals the thread had before this turn's first report
        # (INV-19).
        if self.first_usage is None or self.latest_usage is None:
            return None
        counters = set(CODEX_HOST_USAGE_COUNTERS)
        before = Counter(self.first_usage.total.model_dump(mode="python", include=counters, exclude_none=True))
        before.subtract(self.first_usage.last.model_dump(mode="python", include=counters, exclude_none=True))
        latest = Counter(self.latest_usage.total.model_dump(mode="python", include=counters, exclude_none=True))
        window = self.latest_usage.model_context_window
        return CodexUsage(**(latest - before), **({"model_context_window": window} if window is not None else {}))

    def over_cap(self, delta: CodexUsage | None) -> bool:
        # @intent output-cap-counts-only-this-turn
        # Vidbyte's output cap fires once, when this turn's own output
        # tokens pass max_output_tokens; reaching it exactly is allowed.
        # The caller computes the delta once per notification and
        # shares it with the stream (first-class INV-18).
        cap = self.request.max_output_tokens
        return cap is not None and not self.stop_sent and delta is not None and delta.output_tokens > cap

    def finish(self, snapshot: CodexTurnSnapshot) -> bool:
        # A turn ends exactly once; later outcomes are ignored (INV-15).
        # Its stream then ends with the one ENDED event carrying the
        # same snapshot (first-class INV-21).
        if self.snapshot is not None:
            return False
        self.snapshot = snapshot
        if self.timer is not None:
            self.timer.cancel()
        self.ended.set_result(snapshot)
        self.events.close(snapshot)
        return True

    def watch(
        self,
        connection: CodexConnection,
        on_event: Callable[[CodexLiveTurn, Notification], None],
        on_lost: Callable[[CodexLiveTurn], None],
    ) -> None:
        # @intent one-watcher-and-one-timer-per-turn
        # One daemon thread reads this turn's notifications for its
        # whole life, so no host worker is held by a running turn (D-6).
        # A goal run reads its goal state; any other turn reads its own
        # route and releases it when the watcher ends. A failed read is
        # reported to on_lost (hardening INV-13). Vidbyte's time limit
        # is one timer on the loop, cancelled when the turn ends (D-7).
        loop = self.ended.get_loop()
        client = connection.client
        if self.state is not None:
            read = partial(client.next_goal_notification, self.state)
            cleanup = None
        else:
            read = partial(client.next_turn_notification, self.handle.turn_id)
            cleanup = partial(client.unregister_turn_notifications, self.handle.turn_id)
        CodexTurnWatcher(read, partial(on_event, self), loop, cleanup, until_completed=self.state is None, on_lost=partial(on_lost, self)).start()
        if self.request.timeout_seconds is not None:
            self.timer = loop.call_later(self.request.timeout_seconds, self.stop, connection, FailureCode.CODEX_TURN_TIMED_OUT)

    def stop(self, connection: CodexConnection, reason: FailureCode | None) -> None:
        # @intent the-first-stop-wins-and-is-sent-once
        # Vidbyte's timeout, its output cap and late acceptance each
        # stop a turn with one interrupt. The first stop wins, its
        # reason labels the turn only if Codex reports it interrupted,
        # and a failed interrupt is not retried (D-7, D-35).
        if self.stop_sent or self.snapshot is not None or connection.stopped():
            return
        self.stop_sent = True
        self.stop_reason = reason
        self.stop_pending = True
        connection.spawn_task(self.send_stop(connection, CodexHostOperation.INTERRUPT_CODEX_TURN, quiet=True))

    async def send_stop(self, connection: CodexConnection, operation: CodexHostOperation, *, quiet: bool = False) -> None:
        # @intent a-stop-turns-others-away-only-while-in-flight
        # Send the interrupt the caller marked pending, and clear the
        # mark when this await ends: answered, failed, timed out or
        # cancelled. A timed-out or cancelled await can leave the
        # request on a worker (EC-70), so a retry may send a second
        # interrupt. A stop in flight turns a second interrupt away,
        # but a failed one blocks nothing (AC-16).
        try:
            await connection.interrupt(operation, self.handle, self.state, quiet=quiet)
        finally:
            self.stop_pending = False

    def close_goal_stream(self, client: CodexClient) -> None:
        # A goal run's stream closes once, in openai-codex's own order:
        # finish the state, wake its reader so the watcher exits, then
        # release the thread's goal route (INV-25, INV-7 step 4).
        if self.state is None or self.stream_closed:
            return
        self.stream_closed = True
        self.state.finish()
        self.state.wake_notification_reader()
        client.unregister_goal_operation(self.state)


class CodexGoalTurn(CodexLiveTurn):
    """A goal run: one logical turn over the physical turns Codex starts until the goal ends."""

    def __init__(self, handle: CodexTurnHandle, request: CodexSpawnRequest, pricing: CodexAgentSettings, loop: asyncio.AbstractEventLoop, state: _GoalOperationState) -> None:
        # @intent goal-run-keeps-its-own-limits-and-pricing
        # The goal state is openai-codex's own route for this thread's
        # goal events; the rule decides when the run is over. The
        # request and pricing are kept as for any other turn.
        super().__init__(handle, request, pricing, loop)
        self.state = state
        self.rule = CodexGoalFinishRule()

    def ends(self, payload: object) -> bool:
        # A goal run ends by the goal finish rule, not by one
        # completion.
        return self.rule.process(payload)


class CodexGoalFinishRule:
    """Decides when a goal run is over, as openai-codex's private goal stream cursor does."""

    def __init__(self) -> None:
        # The goal's last reported status (NONE while unknown), whether
        # it was cleared, whether a physical turn is running, the last
        # completion, a remembered failure, and a runtime that never
        # activated goal mode.
        self.status = CodexGoalStatus.NONE
        self.cleared = False
        self.active = False
        self.last_completed: Turn | None = None
        self.failed: Turn | None = None
        self.mismatch = False

    def process(self, payload: object) -> bool:
        # Follow one goal notification and say whether the run is over
        # (section 9.2 goal finish rule).
        if isinstance(payload, TurnStartedNotification):
            self.active = True
            return False
        if isinstance(payload, ThreadGoalUpdatedNotification):
            self.status = CodexGoalStatus(payload.goal.status.value)
            self.cleared = self.cleared and self.status is not CodexGoalStatus.ACTIVE
        if isinstance(payload, ThreadGoalClearedNotification):
            self.cleared = True
        over = self.cleared or self.status in CODEX_GOAL_TERMINAL_STATUSES
        if isinstance(payload, TurnCompletedNotification):
            return self._completed(payload.turn, over)
        # A goal update or clear after the last completion ends an idle
        # run.
        return over and not self.active and self.last_completed is not None

    def _completed(self, turn: Turn, over: bool) -> bool:
        # An interrupted turn ends the run, a failed one is remembered,
        # and a completed one while goal mode never showed a status is a
        # mismatch.
        self.active = False
        self.last_completed = turn
        status = turn.status.value
        if status == CodexTurnStatus.FAILED.value:
            self.failed = turn
        self.mismatch = status == CodexTurnStatus.COMPLETED.value and self.status is CodexGoalStatus.NONE and not self.cleared
        return status == CodexTurnStatus.INTERRUPTED.value or over or self.mismatch


class CodexTurnWatcher(threading.Thread):
    """A daemon thread that reads one live turn's notifications and posts each to the host's loop."""

    def __init__(
        self,
        read: Callable[[], Notification],
        on_event: Callable[[Notification], None],
        loop: asyncio.AbstractEventLoop,
        cleanup: Callable[[], None] | None,
        *,
        until_completed: bool,
        on_lost: Callable[[], None],
    ) -> None:
        # A plain turn's watcher stops at turn/completed; a goal run's
        # watcher reads until its stream is closed or fails.
        super().__init__(name="codex-host-watcher", daemon=True)
        self._read = read
        self._on_event = on_event
        self._loop = loop
        self._cleanup = cleanup
        self._until_completed = until_completed
        self._on_lost = on_lost

    def run(self) -> None:
        # Read and post until the turn ends, its stream closes, the
        # process dies or the loop is gone; then release the turn's
        # route.
        try:
            while self._relay():
                continue
        finally:
            if self._cleanup is not None:
                with suppress(Exception):
                    self._cleanup()

    def _relay(self) -> bool:
        # One read and one post. A failure ends the watcher and posts
        # on_lost, which decides whether the turn lost its events or
        # the host closed or died, as it learns on its own (D-27). A
        # loop already closed takes no post (hardening INV-13).
        try:
            note = self._read()
            self._loop.call_soon_threadsafe(self._on_event, note)
        except Exception:
            with suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._on_lost)
            return False
        return not (self._until_completed and isinstance(note.payload, TurnCompletedNotification))


class CodexTurnRegistry:
    """The turns one host started: by handle, the running turn of each thread, reservations and usage."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        # Each thread the host ran gets a usage tracker and a ledger of
        # its terminal turns, kept until forget_codex_turns releases
        # them or the host is gone (hardening INV-22).
        self._loop = loop
        self._turns: dict[CodexTurnHandle, CodexLiveTurn] = {}
        self._running: dict[str, CodexLiveTurn] = {}
        self._reserved: set[str] = set()
        self._trackers: dict[str, UsageTracker] = {}
        self._ledgers: dict[str, list[CodexTurnUsage]] = {}
        # The characters and events every turn's stream log keeps, so
        # all of one host's logs stay within the host bound (D-39).
        self._stream_chars = 0
        self._stream_events = 0

    def busy(self, thread_id: str) -> bool:
        # A thread with a running or reserved turn takes no second one
        # (INV-24).
        return thread_id in self._running or thread_id in self._reserved

    def reserve(self, thread_id: str) -> None:
        # Reserved synchronously, before the caller awaits anything
        # (EC-16).
        self._reserved.add(thread_id)

    def release(self, thread_id: str) -> None:
        # The reservation ends when the start succeeded or failed.
        self._reserved.discard(thread_id)

    def track(self, handle: CodexTurnHandle, request: CodexSpawnRequest, pricing: CodexAgentSettings, *, review: bool = False) -> CodexLiveTurn:
        # @intent register-before-the-handle-is-returned
        # A plain or review turn is registered, with the request and
        # pricing it runs under, before its handle is returned (INV-14).
        return self._add(CodexLiveTurn(handle, request, pricing, self._loop, review=review))

    def track_goal(self, handle: CodexTurnHandle, request: CodexSpawnRequest, pricing: CodexAgentSettings, state: _GoalOperationState) -> CodexGoalTurn:
        # @intent register-a-goal-run-after-its-budget-check
        # A goal run is registered, with its request and pricing, only
        # once its budget check passed (INV-25).
        turn = CodexGoalTurn(handle, request, pricing, self._loop, state)
        self._add(turn)
        return turn

    def charge_stream(self, chars: int, events: int) -> tuple[int, int]:
        # Add a stream log's charge, or its refund when negative, to the
        # host's kept totals and return both; adding zero reads them
        # (first-class D-39).
        self._stream_chars += chars
        self._stream_events += events
        return self._stream_chars, self._stream_events

    def _add(self, turn: CodexLiveTurn) -> CodexLiveTurn:
        # The turn runs on its thread until it ends, and its stream log
        # counts toward the host's totals before its handle is returned,
        # so plain, review and goal turns are all bounded (D-39).
        turn.events.attach(self.charge_stream)
        thread_id = turn.handle.thread_id
        self._turns[turn.handle] = turn
        self._running[thread_id] = turn
        self._trackers.setdefault(thread_id, UsageTracker())
        self._ledgers.setdefault(thread_id, [])
        return turn

    def get(self, handle: CodexTurnHandle) -> CodexLiveTurn | None:
        # Handles are owned by value, so a rebuilt handle finds its turn
        # (D-33).
        return self._turns.get(handle)

    def running(self) -> tuple[CodexLiveTurn, ...]:
        # Every turn that has not ended yet, in start order.
        return tuple(turn for turn in self._turns.values() if turn.snapshot is None)

    def finish(self, turn: CodexLiveTurn, snapshot: CodexTurnSnapshot) -> bool:
        # End a turn once, log how it ended, with its ids as bounded
        # tokens, then file its usage; a second outcome for the same
        # turn changes nothing (INV-15, INV-36, hardening INV-9,
        # INV-10).
        if not turn.finish(snapshot):
            return False
        code = snapshot.problem.code.value if snapshot.problem is not None else ""
        limit = CODEX_HOST_LOG_TOKEN_MAX_CHARS
        logger.info("codex_host_turn_ended thread_id=%s turn_id=%s status=%s failure_code=%s", LogToken.of(turn.handle.thread_id, limit), LogToken.of(turn.handle.turn_id, limit), snapshot.status.value, code)
        self._record(turn, snapshot)
        return True

    def forget(self, thread_id: str) -> int:
        # @intent forget-releases-a-thread-s-ended-turns
        # Drop every turn registered on the thread, with its usage
        # ledger and tracker, and say how many turns went; an unknown
        # thread drops none. The host refuses a busy thread first, so
        # only ended turns are dropped (hardening INV-22).
        dropped = [handle for handle in self._turns if handle.thread_id == thread_id]
        for handle in dropped:
            del self._turns[handle]
        self._ledgers.pop(thread_id, None)
        self._trackers.pop(thread_id, None)
        return len(dropped)

    def _record(self, turn: CodexLiveTurn, snapshot: CodexTurnSnapshot) -> None:
        # @intent price-each-terminal-turn-once
        # File an ended turn's own token delta once, and price it with
        # the model Codex resolved; a turn with no usage report is
        # listed as unavailable rather than as zero (INV-36, D-19).
        thread_id = turn.handle.thread_id
        if self._running.get(thread_id) is turn:
            del self._running[thread_id]
        delta = turn.usage_delta()
        entry = CodexTurnUsage(turn_id=turn.handle.turn_id, status=snapshot.status, usage=delta or CodexUsage(), usage_available=delta is not None)
        self._ledgers[thread_id].append(entry)
        if delta is not None:
            result = CodexRunResult(
                thread_id=thread_id,
                turn_id=turn.handle.turn_id,
                status=snapshot.status.value,
                final_response=None,
                duration_ms=None,
                usage=delta,
                items=(),
                last_usage=delta,
                usage_available=True,
            )
            CodexMetricsTranslator.record_usage(CodexUsageTranslationRequest(result=result, settings=turn.pricing, tracker=self._trackers[thread_id]))

    def usage(self, thread_id: str) -> CodexThreadUsage | None:
        # The thread's terminal turns, their summed usage and the rollup
        # cost; None for a thread this host never ran a turn on.
        ledger = self._ledgers.get(thread_id)
        if ledger is None:
            return None
        total: Counter[str] = Counter()
        for entry in ledger:
            total.update({name: getattr(entry.usage, name) for name in CODEX_HOST_USAGE_COUNTERS})
        rollup = self._trackers[thread_id].rollup()
        complete = rollup.cost_complete and all(entry.usage_available for entry in ledger)
        return CodexThreadUsage(thread_id=thread_id, total=CodexUsage(**total), turns=tuple(ledger), cost_usd=rollup.cost_usd, cost_complete=complete)


__all__ = ["CodexGoalFinishRule", "CodexGoalTurn", "CodexLiveTurn", "CodexTurnRegistry", "CodexTurnWatcher"]
