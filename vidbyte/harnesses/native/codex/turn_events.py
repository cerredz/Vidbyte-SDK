"""FILE: vidbyte/harnesses/native/codex/turn_events.py

PURPOSE: CodexTurnEvents, the CodexHost collaborator that ends each live turn from its events: it folds every notification a watcher posts into its turn and finishes the turn from Codex's completion, the goal finish rule or a review's one-page read-back. A turn whose events cannot be processed, or whose watcher can no longer read them, is stopped and ended FAILED, so no turn is left running and no wait hangs.
ROLE IN CODEBASE: A host collaborator of vidbyte/harnesses/native/codex/; CodexHost builds it in _open() after CodexThreadHelpers and hands on_event and on_lost to every CodexLiveTurn.watch, and CodexReviews watches review turns the same way.
ARCHITECTURE NOTE: Everything here runs on the host's event loop. It imports no openai-codex module at module level, and the connection, translators, turns and thread helpers only under TYPE_CHECKING, so importing CodexHost still loads no SDK module (codex-host D-21, hardening INV-41). CODEX_HOST_LOST_TURN_GRACE_SECONDS is bound by name and read at call time, so the tests can patch it here (section 13).
FUNCTION INVENTORY: on_event(turn, note) folds one notification into its turn and ends the turn when the notification ends it, failing the turn if that raises (INV-11); on_lost(turn) starts _end_lost_turn when a watcher read failed (INV-13); complete_review(turn) ends a completed review from its read-back, failing it if that raises anything but a CodexAgentError (INV-12); _end_lost_turn(turn) ends a turn whose watcher stopped while the host stays open; fail(turn, exc) logs, stops and fails a turn whose events failed, and CodexReviews calls it for a review read back as ended whose snapshot cannot be built (INV-12).
COMMON MODIFICATION PATTERNS: A new way a turn ends from its events is one branch in on_event, finished through CodexTurnRegistry.finish so the first outcome still wins; its failure needs nothing extra, because on_event already guards it.
WHAT NOT TO DO: Do not log an exception's text or pass exc_info; log its type name and ExceptionOrigin only (hardening INV-10). Do not close a goal run's stream before its turn is finished: _end_lost_turn relies on the snapshot to tell a normal goal end from a lost one (INV-13). Do not catch BaseException, so cancellation propagates.
KNOWN EDGE CASES: A goal run's watcher always ends with a failed read once its stream closes, so on_lost runs for every goal run and returns at once, because the run already ended. A process death can reach a watcher before the liveness monitor, so _end_lost_turn waits the grace and checks again, and a close or death that lands before its last step wins as process_exited. The cleanup interrupt of a lost turn is quiet and sent once; its failure does not keep the turn running (EC-18).
RELATED DOCS: docs/spec/codex-host-hardening/spec.md (sections 6.1 INV-9 to INV-14, 8.1 D-9 and D-14, and 8.5); docs/spec/codex-host/spec.md (sections 8.1 D-7 and D-23)
TESTS: tests/features/codex_host/test_codex_host_liveness.py, tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_review_goals.py, tests/features/codex_host/test_codex_host_observability.py
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_EVENT_FAILED_MESSAGE,
    CODEX_HOST_LOST_EVENTS_MESSAGE,
    CODEX_HOST_LOST_TURN_GRACE_SECONDS,
)
from vidbyte.lib.enums.codex import CodexHostOperation
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError
from vidbyte.lib.util.exception_origin import ExceptionOrigin

if TYPE_CHECKING:
    from openai_codex.models import Notification

    from vidbyte.harnesses.native.codex.connection import CodexConnection
    from vidbyte.harnesses.native.codex.thread_helpers import CodexThreadHelpers
    from vidbyte.harnesses.native.codex.turns import (
        CodexGoalTurn,
        CodexLiveTurn,
        CodexTurnRegistry,
    )
    from vidbyte.harnesses.native.codex.wire import CodexResponseTranslator

logger = logging.getLogger(__name__)


class CodexTurnEvents:
    """Ends each live turn of one CodexHost from its events, and ends a turn whose events fail or stop arriving."""

    def __init__(
        self,
        connection: CodexConnection,
        responses: CodexResponseTranslator,
        registry: CodexTurnRegistry,
        threads: CodexThreadHelpers,
    ) -> None:
        # The host's own parts, built once the host opened.
        self._connection = connection
        self._responses = responses
        self._registry = registry
        self._threads = threads

    def on_event(self, turn: CodexLiveTurn, note: Notification) -> None:
        # @intent the-first-outcome-ends-a-turn
        # Runs on the loop for each notification a watcher posts. A turn
        # that already ended ignores later events (INV-15), and passing
        # the output cap sends one interrupt (D-7). If handling the
        # notification raises, the turn is stopped and failed instead,
        # so a wait on it still returns (hardening INV-11).
        try:
            if turn.snapshot is not None:
                return
            ended = turn.observe(note)
            if turn.over_cap():
                turn.stop(self._connection, FailureCode.CODEX_BUDGET_EXHAUSTED)
            if not ended:
                return
            # The end builds the snapshot: a review from its read-back,
            # a goal run by the goal table, any other turn from its
            # completion. A goal run is finished before its stream
            # closes (INV-13).
            if turn.review:
                self._connection.spawn_task(self.complete_review(turn))
            elif turn.state is not None:
                self._registry.finish(turn, self._responses.goal_snapshot(cast("CodexGoalTurn", turn)))
                turn.close_goal_stream(self._connection.client)
            else:
                self._registry.finish(turn, self._responses.turn_snapshot(turn, turn.items, turn.completed))
        except Exception as exc:
            self.fail(turn, exc)

    def on_lost(self, turn: CodexLiveTurn) -> None:
        # Runs on the loop when the turn's watcher could not read; the
        # checks run as a task, because one of them waits (INV-13).
        self._connection.spawn_task(self._end_lost_turn(turn))

    async def complete_review(self, turn: CodexLiveTurn) -> None:
        # @intent build-a-review-from-its-stored-items
        # When a review turn completes, its result comes from the review
        # turn read back from one page, since its last item can be lost;
        # the items seen live are used when the read fails (D-23,
        # hardening INV-38). Anything else that raises ends the review
        # FAILED, and a cancellation propagates (hardening INV-12).
        handle = turn.handle
        stored = None
        try:
            with suppress(CodexAgentError):
                stored = await self._threads.review_turn(CodexHostOperation.START_CODEX_REVIEW, handle.thread_id, handle.turn_id)
            items = stored.items if stored is not None else turn.items
            self._registry.finish(turn, self._responses.turn_snapshot(turn, items, turn.completed))
        except Exception as exc:
            self.fail(turn, exc)

    async def _end_lost_turn(self, turn: CodexLiveTurn) -> None:
        # @intent a-lost-watcher-never-leaves-a-turn-running
        # (a) A turn that already ended, or a host that is closing or
        #     dead, needs nothing; this is how every goal run's watcher
        #     ends, so it is checked first, with no wait.
        connection = self._connection
        if turn.snapshot is not None or connection.stopped():
            return
        # (b) Wait the grace, so a process death has time to reach the
        #     liveness monitor, then check again.
        await asyncio.sleep(CODEX_HOST_LOST_TURN_GRACE_SECONDS)
        if turn.snapshot is not None or connection.stopped():
            return
        # (c) Unless a stop was already sent, send one quiet cleanup
        #     interrupt, whose failure is ignored (EC-18).
        if not turn.stop_sent:
            turn.stop_sent = True
            await connection.interrupt(CodexHostOperation.INTERRUPT_CODEX_TURN, turn.handle, turn.state, cleanup=True, quiet=True)
        # (d) Still running on an open host: the turn lost its events,
        #     so it ends FAILED, then a goal run's stream closes. A
        #     close or death that came first already ended it as exited.
        if turn.snapshot is None and not connection.stopped():
            logger.warning("codex_host_turn_lost thread_id=%s turn_id=%s", turn.handle.thread_id, turn.handle.turn_id)
            self._registry.finish(turn, self._responses.failed(turn.handle, FailureCode.CODEX_API_ERROR, CODEX_HOST_LOST_EVENTS_MESSAGE))
            turn.close_goal_stream(connection.client)

    def fail(self, turn: CodexLiveTurn, exc: Exception) -> None:
        # @intent a-turn-whose-events-fail-is-stopped-then-failed
        # In this order: log the failure by type and origin only, send
        # the turn at most one quiet stop, end it FAILED, then close a
        # goal run's stream (hardening INV-11, INV-12).
        handle = turn.handle
        logger.warning("codex_host_turn_event_failed thread_id=%s turn_id=%s error_type=%s origin=%s", handle.thread_id, handle.turn_id, type(exc).__name__, ExceptionOrigin.describe(exc))
        connection = self._connection
        turn.stop(connection, None)
        self._registry.finish(turn, self._responses.failed(handle, FailureCode.CODEX_PROTOCOL_MISMATCH, CODEX_HOST_EVENT_FAILED_MESSAGE))
        turn.close_goal_stream(connection.client)


__all__ = ["CodexTurnEvents"]
