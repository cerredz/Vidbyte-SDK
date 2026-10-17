"""FILE: vidbyte/agents/agent_swarm/events.py

PURPOSE: Defines AgentSwarmEvents, the event record of one swarm run: it numbers every state change as it happens and hands each event, in order and exactly once, to the developer's optional on_event callback.
ROLE IN CODEBASE: Built by AgentSwarmRuntime (runtime.py) for each run; the runtime records an event in the same synchronous block that makes the state change and then awaits flush. Its events tuple and error type names become AgentSwarmResult.events and event_error_types. Exported by vidbyte/agents/agent_swarm/__init__.py and vidbyte/agents/__init__.py.
ARCHITECTURE NOTE: An outbox. record never awaits, so the sequence it assigns is the true order of the state changes, whichever task records. flush delivers every recorded event that is not delivered yet, oldest first, under one asyncio.Semaphore of one (the SDK's mutex, since TID251 bans asyncio.Lock), so two agents flushing at once never hand the callback two events at the same time or out of order. Each event is marked delivered before its callback is awaited, so a flush that is cancelled inside a callback never hands that event over again, and the next flush continues with the event after it.
FUNCTION INVENTORY: record builds, numbers, and keeps one AgentSwarmEvent; flush is the narrated main function that delivers the backlog; _deliver calls the callback for one event and keeps the type name of any Exception it raises; events and error_types read the record.
COMMON MODIFICATION PATTERNS: A new event field adds one keyword to record, passed to AgentSwarmEvent, whose __post_init__ checks it per kind.
WHAT NOT TO DO IN THIS FILE: 1. Do not await inside record; the sequence would stop matching the order of state changes. 2. Do not catch BaseException around the callback; cancellation must pass through. 3. Do not deliver an event before marking it delivered.
KNOWN EDGE CASES: A slow callback holds back every agent that flushes after it, which is the intended back-pressure. When a time limit cancels the task inside a callback, that event's callback is cut short and is not repeated; the semaphore is released by the cancellation, so the run's last flush still delivers every later event. A message's id is its own sequence, so record assigns it for MESSAGE_SENT. elapsed_ms is whole milliseconds on the monotonic clock since this record was built. AgentSwarmRuntime builds one record with the runtime and replaces it with a fresh one when arun starts, before the first event, so elapsed_ms counts from the start of the run, not from when the runtime was built.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 6.1 INV-13 to INV-16, 8.1 D-6 and D-16, and 9.1); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_lifecycle.py
"""

from __future__ import annotations

import asyncio
import inspect
import time

from vidbyte.lib.constants import AGENT_SPEED_MILLISECONDS_PER_SECOND
from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent, AgentSwarmEventCallback
from vidbyte.lib.dataclasses.tools import ToolStatus
from vidbyte.lib.enums.agent_swarm import AgentSwarmEventKind, AgentSwarmStopReason


class AgentSwarmEvents:
    """The numbered event record of one swarm run and its in-order delivery to on_event."""

    def __init__(self, on_event: AgentSwarmEventCallback | None) -> None:
        self._on_event = on_event
        self._events: list[AgentSwarmEvent] = []
        self._delivered = 0
        self._error_types: list[str] = []
        # A semaphore of one is a mutex: one delivery at a time.
        self._delivery = asyncio.Semaphore()
        self._started_at = time.monotonic()

    def record(
        self,
        kind: AgentSwarmEventKind,
        agent: str,
        *,
        peer: str = "",
        message_id: int = 0,
        text: str = "",
        tool_name: str = "",
        tool_status: ToolStatus | None = None,
        stop_reason: AgentSwarmStopReason | None = None,
    ) -> AgentSwarmEvent:
        """Number one state change, keep it for delivery, and return it; never awaits."""
        # The next sequence number and the whole milliseconds since the
        # run started; a sent message's id is its own sequence.
        sequence = len(self._events) + 1
        elapsed_ms = int((time.monotonic() - self._started_at) * AGENT_SPEED_MILLISECONDS_PER_SECOND)
        message_id = sequence if kind is AgentSwarmEventKind.MESSAGE_SENT else message_id
        event = AgentSwarmEvent(sequence=sequence, kind=kind, agent=agent, elapsed_ms=elapsed_ms, peer=peer, message_id=message_id, text=text, tool_name=tool_name, tool_status=tool_status, stop_reason=stop_reason)
        self._events.append(event)
        return event

    async def flush(self) -> None:
        """Hand every recorded, undelivered event to on_event, oldest first, one at a time."""
        # @intent each-event-is-delivered-once-in-order
        # Only one task delivers at a time. It keeps going until nothing
        # is left, including events recorded while it waited on the
        # callback, and marks each event delivered before handing it
        # over, so a cancelled delivery is never repeated.
        async with self._delivery:
            while self._delivered < len(self._events):
                event = self._events[self._delivered]
                self._delivered += 1
                await self._deliver(event)

    async def _deliver(self, event: AgentSwarmEvent) -> None:
        # @intent a-callback-error-never-stops-the-swarm
        # The callback is the developer's code: an Exception it raises
        # is kept by type name and the swarm goes on, while cancellation
        # and other BaseExceptions pass through untouched.
        if self._on_event is None:
            return
        try:
            outcome = self._on_event(event)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception as exc:
            self._error_types.append(type(exc).__name__)

    @property
    def events(self) -> tuple[AgentSwarmEvent, ...]:
        """Return every event recorded so far, in sequence order."""
        return tuple(self._events)

    @property
    def error_types(self) -> tuple[str, ...]:
        """Return the type name of every Exception on_event raised, in order."""
        return tuple(self._error_types)


__all__ = ["AgentSwarmEvents"]
