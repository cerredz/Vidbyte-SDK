"""FILE: vidbyte/harnesses/native/codex/turn_stream.py

PURPOSE: Streams one live Codex turn's events: CodexTurnEventLog keeps a bounded, ordered window of a turn's events, ends it with exactly one ENDED event, and hands each subscriber an independent async iterator over it; CodexTurnEventTranslator turns one app-server notification into one CodexTurnEvent.
ROLE IN CODEBASE: The stream layer of vidbyte/harnesses/native/codex/. Every CodexLiveTurn in turns.py owns one CodexTurnEventLog as its events attribute; CodexTurnRegistry._add attaches it to the host's stream totals, CodexTurnEvents.on_event records each notification right after the turn observes it, CodexLiveTurn.finish closes it, and CodexHost's stream_codex_turn returns its subscribe().
ARCHITECTURE NOTE: Everything here runs on the host's event loop, from on_event, finish and the subscribers' own steps, so the log needs no lock (slice-1 INV-12); subscribers wait on one asyncio.Event, set on every change. record never raises and never awaits, so a slow or absent reader never delays the turn (first-class INV-19). A subscription is a private async generator: it counts itself as reading from its first step until its finally, keeps its next sequence as a local, and computes its GAP from the log's kept sequences, so the log holds an integer count and no per-subscriber object, weak reference or cursor class (D-37). The four window bounds are imported by name and read at call time, so section 13's patches here apply. The translator narrows each payload to its openai-codex notification class, so this module loads openai-codex; only turns.py, which also loads it and which only CodexHost._open imports, imports this module, so importing the host never loads either (INV-45).
COMMON MODIFICATION PATTERNS: A new streamed notification adds its method and CodexTurnEventKind to CODEX_HOST_STREAM_NOTIFICATION_KINDS (vidbyte/lib/constants/codex_host.py) and, for a text delta, its notification class to the delta check in CodexTurnEventTranslator.event, or, when its payload has a new shape, one isinstance branch there. A new bound is read in CodexTurnEventLog._fits at call time.
KNOWN EDGE CASES: An event the translator cannot build, such as a delta openai-codex could not parse and so delivers as an UnknownNotification, spends its sequence, is logged once as codex_host_stream_event_dropped by type and origin, and shows up as a GAP. An event that alone passes the character bound is dropped and counted. ENDED is kept outside every bound and is never charged or dropped. Once the turn has ended and no subscription is reading, every kept event is released and refunded to the host's totals; a subscription read later sees one GAP for them, then ENDED. A subscription opened after the turn ended yields only ENDED. Iterating a subscription on another loop than the host's raises ConfigurationError at its first step.
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 6.1 INV-18 to INV-22 and 9.1 "Lifecycle: one live turn's CodexTurnEventLog", D-9 to D-12, D-37, D-39, NFR-3)
TESTS: tests/features/codex_host/test_codex_host_stream_wait.py
"""

from __future__ import annotations

import asyncio
import bisect
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Callable
from operator import attrgetter
from typing import TYPE_CHECKING

from openai_codex.generated.v2_all import (
    AgentMessageDeltaNotification,
    CommandExecutionOutputDeltaNotification,
    FileChangeOutputDeltaNotification,
    ItemCompletedNotification,
    ItemStartedNotification,
    PlanDeltaNotification,
    ReasoningSummaryTextDeltaNotification,
    ThreadTokenUsageUpdatedNotification,
    TurnDiffUpdatedNotification,
    TurnPlanUpdatedNotification,
)

from vidbyte.agents.codex.result import CodexResultSerializer
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_LOG_TOKEN_MAX_CHARS,
    CODEX_HOST_OTHER_LOOP_MESSAGE,
    CODEX_HOST_STREAM_EVENT_LIMIT,
    CODEX_HOST_STREAM_HOST_EVENT_LIMIT,
    CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS,
    CODEX_HOST_STREAM_NOTIFICATION_KINDS,
    CODEX_HOST_STREAM_TEXT_LIMIT_CHARS,
)
from vidbyte.lib.dataclasses.codex_host_features import CodexPlanStep, CodexTurnEvent
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexPlanStepStatus,
    CodexTurnEventKind,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.util.exception_origin import ExceptionOrigin
from vidbyte.lib.util.text import LogToken

if TYPE_CHECKING:
    from openai_codex.models import Notification

    from vidbyte.lib.dataclasses.codex import CodexUsage
    from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle, CodexTurnSnapshot

logger = logging.getLogger(__name__)


class CodexTurnEventTranslator:
    """Turns one app-server notification into one CodexTurnEvent, or None for a method that is not streamed."""

    @staticmethod
    def event(note: Notification, handle: CodexTurnHandle, sequence: int, usage: CodexUsage | None) -> CodexTurnEvent | None:
        # @intent only-the-kinds-table-reaches-a-stream
        # A method outside the kinds table is no event, so raw reasoning
        # text never streams; an item goes through the serializer, which
        # leaves out a reasoning item's content (first-class INV-18,
        # D-12). The usage is the turn's own, computed once by on_event.
        kind = CODEX_HOST_STREAM_NOTIFICATION_KINDS.get(note.method)
        if kind is None:
            return None
        payload = note.payload
        if isinstance(payload, (ItemStartedNotification, ItemCompletedNotification)):
            item = CodexResultSerializer.items((payload.item,))[0]
            return CodexTurnEvent(sequence=sequence, kind=kind, handle=handle, item_id=item.id, item_type=item.type, item=item)
        if isinstance(payload, TurnPlanUpdatedNotification):
            steps = tuple(CodexPlanStep(step=entry.step, status=CodexPlanStepStatus(entry.status.value)) for entry in payload.plan)
            return CodexTurnEvent(sequence=sequence, kind=kind, handle=handle, text=payload.explanation or "", plan_steps=steps)
        if isinstance(payload, TurnDiffUpdatedNotification):
            return CodexTurnEvent(sequence=sequence, kind=kind, handle=handle, text=payload.diff)
        if isinstance(payload, ThreadTokenUsageUpdatedNotification):
            return CodexTurnEvent(sequence=sequence, kind=kind, handle=handle, usage=usage)
        # Every other streamed method is one item's text delta. A delta
        # openai-codex could not parse arrives as an UnknownNotification
        # with nothing to keep, so it is refused here and record counts
        # it as a GAP (EC-20).
        if not isinstance(payload, (AgentMessageDeltaNotification, ReasoningSummaryTextDeltaNotification, PlanDeltaNotification, CommandExecutionOutputDeltaNotification, FileChangeOutputDeltaNotification)):
            raise TypeError(type(payload).__name__)
        return CodexTurnEvent(sequence=sequence, kind=kind, handle=handle, item_id=payload.item_id, text=payload.delta)


class CodexTurnEventLog:
    """One live turn's bounded, ordered event window, ended by exactly one ENDED event, with any number of independent subscriptions."""

    def __init__(self, handle: CodexTurnHandle, loop: asyncio.AbstractEventLoop) -> None:
        # The kept events in sequence order with their sizes, the next
        # sequence number, the ENDED event once the turn ends, how many
        # subscriptions are reading, and the host's totals once
        # attached (first-class INV-20, D-37, D-39).
        self._handle = handle
        self._loop = loop
        self._events: deque[CodexTurnEvent] = deque()
        self._sizes: deque[int] = deque()
        self._chars = 0
        self._next = 1
        self._ended: CodexTurnEvent | None = None
        self._reading = 0
        self._changed = asyncio.Event()
        self._charge: Callable[[int, int], tuple[int, int]] | None = None

    def attach(self, charge: Callable[[int, int], tuple[int, int]]) -> None:
        # The host's running totals of kept characters and events, which
        # this log charges and refunds; CodexTurnRegistry._add calls it
        # once (D-39).
        self._charge = charge

    def record(self, note: Notification, usage: CodexUsage | None) -> None:
        # @intent recording-never-harms-the-turn
        # Turn the notification into the next event and keep it within
        # the bounds. Anything that fails spends the event's sequence,
        # so subscribers see it as a GAP, and is logged once by type and
        # origin; the turn's outcome, usage and timers never change
        # (first-class INV-19).
        if self._ended is not None:
            return
        sequence = self._next
        try:
            event = CodexTurnEventTranslator.event(note, self._handle, sequence, usage)
            if event is None:
                return
            self._next = sequence + 1
            size = self._size(event)
            # Drop this log's own oldest events until the new one fits
            # the turn's and the host's bounds; a new event that still
            # does not fit is dropped and counted (INV-20).
            while self._events and not self._fits(size):
                self._drop_oldest()
            if self._fits(size):
                self._append(event, size)
        except Exception as exc:
            self._next = sequence + 1
            self._log_drop(note, exc)
        # Wake every subscription, which reads what changed.
        self._changed.set()

    def close(self, snapshot: CodexTurnSnapshot) -> None:
        # @intent every-stream-ends-with-exactly-one-ended
        # Add the one ENDED event, carrying the snapshot the turn ended
        # with, wake every subscription, and release the window when no
        # subscription is reading (first-class INV-21).
        if self._ended is not None:
            return
        self._ended = CodexTurnEvent(sequence=self._next, kind=CodexTurnEventKind.ENDED, handle=self._handle, snapshot=snapshot)
        self._next += 1
        self._changed.set()
        self._release_if_done()

    def subscribe(self) -> AsyncIterator[CodexTurnEvent]:
        """Return a new, independent subscription whose start is fixed now.

        The start is the ENDED event once the turn has ended, else the
        oldest kept event, else the next one. A subscription counts as
        reading from its first step until it finishes, so a caller that
        leaves ``async for`` early should close it, for example with
        ``contextlib.aclosing``, to release the window at once rather
        than when it is collected.
        """
        if self._ended is not None:
            start = self._ended.sequence
        else:
            start = self._events[0].sequence if self._events else self._next
        return self._read(start)

    async def _read(self, position: int) -> AsyncIterator[CodexTurnEvent]:
        # @intent a-subscription-reads-only-while-its-generator-runs
        # The loop check comes first, then the subscription counts as
        # reading until its finally, so a subscription never iterated,
        # closed or abandoned holds nothing (INV-21, INV-22, D-37).
        if asyncio.get_running_loop() is not self._loop:
            raise ConfigurationError(CODEX_HOST_OTHER_LOOP_MESSAGE.format(operation=CodexHostOperation.STREAM_CODEX_TURN.value))
        self._reading += 1
        try:
            while True:
                event, position = self._next_for(position)
                if event is None:
                    # Nothing unread yet: wait until the log changes.
                    self._changed.clear()
                    await self._changed.wait()
                    continue
                yield event
                if event.kind is CodexTurnEventKind.ENDED:
                    return
        finally:
            self._reading -= 1
            self._release_if_done()

    def _next_for(self, position: int) -> tuple[CodexTurnEvent | None, int]:
        # The next event for a subscription at this sequence: one GAP
        # counting every event from it that was dropped or released,
        # else the kept event at it, else ENDED, else nothing yet; with
        # the subscription's next sequence (INV-20).
        index = bisect.bisect_left(self._events, position, key=attrgetter("sequence"))
        kept = self._events[index] if index < len(self._events) else None
        ended = self._ended.sequence if self._ended is not None else self._next
        nearest = kept.sequence if kept is not None else ended
        if nearest > position:
            return CodexTurnEvent(sequence=position, kind=CodexTurnEventKind.GAP, handle=self._handle, dropped=nearest - position), nearest
        if kept is not None:
            return kept, position + 1
        if self._ended is not None:
            return self._ended, position + 1
        return None, position

    @staticmethod
    def _size(event: CodexTurnEvent) -> int:
        # What an event costs against the character bounds: its text
        # plus its item serialized as the model would read it (INV-20).
        if event.item is None:
            return len(event.text)
        return len(event.text) + len(json.dumps({"id": event.item.id, "type": event.item.type, "fields": dict(event.item.fields)}, default=str))

    def _fits(self, size: int) -> bool:
        # Whether an event of this size fits the turn's bounds and, once
        # attached, the host's. The bounds are read now, so a patched
        # bound applies; charging nothing reads the host's totals
        # (INV-20, D-39).
        turn_fits = len(self._events) < CODEX_HOST_STREAM_EVENT_LIMIT and self._chars + size <= CODEX_HOST_STREAM_TEXT_LIMIT_CHARS
        if self._charge is None:
            return turn_fits
        host_chars, host_events = self._charge(0, 0)
        return turn_fits and host_events < CODEX_HOST_STREAM_HOST_EVENT_LIMIT and host_chars + size <= CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS

    def _drop_oldest(self) -> None:
        # Drop this log's own oldest event and refund it to the host's
        # totals (INV-20, D-39).
        self._events.popleft()
        dropped = self._sizes.popleft()
        self._chars -= dropped
        if self._charge is not None:
            self._charge(-dropped, -1)

    def _log_drop(self, note: Notification, exc: Exception) -> None:
        # One WARNING per event that could not be recorded, by type and
        # origin, never its text, with the ids as bounded tokens
        # (INV-19, EC-20).
        limit = CODEX_HOST_LOG_TOKEN_MAX_CHARS
        ids = (LogToken.of(self._handle.thread_id, limit), LogToken.of(self._handle.turn_id, limit), LogToken.of(note.method, limit))
        logger.warning("codex_host_stream_event_dropped thread_id=%s turn_id=%s method=%s error_type=%s origin=%s", *ids, type(exc).__name__, ExceptionOrigin.describe(exc))

    def _append(self, event: CodexTurnEvent, size: int) -> None:
        # Keep the event and charge it to the host's totals.
        self._events.append(event)
        self._sizes.append(size)
        self._chars += size
        if self._charge is not None:
            self._charge(size, 1)

    def _release_if_done(self) -> None:
        # Once the turn has ended and no subscription is reading, every
        # kept event is released and refunded; only ENDED stays
        # (INV-21).
        if self._ended is None or self._reading or not self._events:
            return
        if self._charge is not None:
            self._charge(-self._chars, -len(self._events))
        self._events.clear()
        self._sizes.clear()
        self._chars = 0


__all__ = ["CodexTurnEventLog", "CodexTurnEventTranslator"]
