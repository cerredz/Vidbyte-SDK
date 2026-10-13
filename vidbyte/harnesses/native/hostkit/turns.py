"""FILE: vidbyte/harnesses/native/hostkit/turns.py

PURPOSE: Defines NativeTurnTable, which tracks one host's turns: synchronous reservations of a session and a live-turn slot, the live driver tasks, and a first-in-first-out table of the last NATIVE_FINISHED_TURN_LIMIT finished turns, so a handle can be waited on after its turn ended.
ROLE IN CODEBASE: One table per host (GrokHost, OpencodeHost, MuseHost). spawn_* and continue_* reserve before their first await, bind the vendor session once it is known, and activate the driver task; wait_* and interrupt_* look a handle up here.
ARCHITECTURE NOTE: Every method is synchronous, so a reservation can never interleave with another task's busy check. The table owns every driver task (lint S006): a done-callback moves a finished driver to the finished table and frees its session.
FUNCTION INVENTORY: reserve takes a session and a slot; bind_session records the session spawn learned; activate turns a reservation into a live handle; release frees a reservation that never started; lookup finds a handle's task; is_session_busy and live_tasks report state; _finish is the driver done-callback; _session_key gives a session id's busy-table key; _busy and _not_found build the two errors.
COMMON MODIFICATION PATTERNS: A new turn state belongs in the driver's NativeTurnResult, not here; this table only knows reserved, live and finished.
WHAT NOT TO DO IN THIS FILE: 1. Do not await anywhere in this class; reservation must stay atomic. 2. Do not drop a live task from the table before it finishes; the host's __aexit__ needs it to interrupt the turn.
KNOWN EDGE CASES: The live-turn cap counts reservations too, so concurrent spawns cannot overshoot it. A handle whose harness, session or turn id differs from the stored handle is not found, so handles are scoped to the host that issued them. A Grok or Muse vendor may return a session id in upper case; the busy table keys it in lower case, so a continue or fork by either spelling finds the live turn, while the handle keeps the vendor's spelling.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Shared host plumbing), EC-9, EC-24, EC-149, INV-14 to INV-17
TESTS: tests/features/grok_host/test_grok_host_shared_contract.py
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections import OrderedDict

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.native_hosts import NativeTurnHandle, NativeTurnResult
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import NativeHarness
from vidbyte.lib.errors import NativeHostError


class NativeTurnTable:
    """Reserved, live and recently finished turns of one host."""

    def __init__(self, harness: NativeHarness, *, max_live_turns: int, errors: NativeErrorFactory) -> None:
        self._harness = harness
        self._max_live_turns = max_live_turns
        self._errors = errors
        self._reserved: dict[str, str | None] = {}
        self._busy_sessions: dict[str, str] = {}
        self._live: dict[str, tuple[NativeTurnHandle, asyncio.Task[NativeTurnResult]]] = {}
        self._finished: OrderedDict[str, tuple[NativeTurnHandle, asyncio.Task[NativeTurnResult]]] = OrderedDict()

    def reserve(self, session_id: str | None, *, operation: str) -> str:
        # @intent native-turn-reservation-is-synchronous
        # The busy check and the reservation happen with no await
        # between them, so two concurrent calls on one session cannot
        # both pass, and the live-turn cap counts reservations as
        # well as live turns.
        key = None if session_id is None else self._session_key(session_id)
        if session_id is not None and key in self._busy_sessions:
            raise self._busy(f"Session {session_id} already has a live turn on this host.", operation, {"session_id": session_id})
        live = len(self._reserved) + len(self._live)
        if live >= self._max_live_turns:
            raise self._busy(f"This host already runs {live} live turns, its limit.", operation, {"live_turns": str(live)})
        turn_id = uuid.uuid4().hex
        self._reserved[turn_id] = session_id
        if key is not None:
            self._busy_sessions[key] = turn_id
        return turn_id

    def bind_session(self, turn_id: str, session_id: str) -> None:
        # Spawn learns its session id only after the vendor
        # created the session.
        self._reserved[turn_id] = session_id
        self._busy_sessions[self._session_key(session_id)] = turn_id

    def activate(self, turn_id: str, driver: asyncio.Task[NativeTurnResult]) -> NativeTurnHandle:
        # Turns a bound reservation into a live turn and gives the table
        # ownership of the driver task.
        session_id = self._reserved.pop(turn_id, None)
        if session_id is None:
            raise self._errors.build(FailureCode.RUNTIME_ERROR, "A turn was activated before its session was bound; this is a defect in the host.", operation="activate")
        handle = NativeTurnHandle(harness=self._harness, session_id=session_id, turn_id=turn_id)
        self._live[turn_id] = (handle, driver)
        driver.add_done_callback(functools.partial(self._finish, turn_id))
        return handle

    def release(self, turn_id: str) -> None:
        # Frees a reservation whose turn never started, so its session
        # and slot are usable again.
        session_id = self._reserved.pop(turn_id, None)
        key = None if session_id is None else self._session_key(session_id)
        if key is not None and self._busy_sessions.get(key) == turn_id:
            del self._busy_sessions[key]

    def lookup(self, handle: NativeTurnHandle, *, operation: str) -> asyncio.Task[NativeTurnResult]:
        # A handle is found only when it equals the handle this table
        # issued, live or finished.
        entry = self._live.get(handle.turn_id) or self._finished.get(handle.turn_id)
        if entry is None or entry[0] != handle:
            raise self._not_found(operation)
        return entry[1]

    def is_session_busy(self, session_id: str) -> bool:
        # True while a reservation or a live turn holds the session.
        return self._session_key(session_id) in self._busy_sessions

    def live_tasks(self) -> tuple[asyncio.Task[NativeTurnResult], ...]:
        # The drivers of every live turn, for
        # interrupting them at __aexit__.
        return tuple(task for _handle, task in self._live.values())

    def _finish(self, turn_id: str, _driver: asyncio.Task[NativeTurnResult]) -> None:
        # Moves a finished driver to the bounded first-in-first-out
        # table and frees its session.
        entry = self._live.pop(turn_id, None)
        if entry is None:
            return
        key = self._session_key(entry[0].session_id)
        if self._busy_sessions.get(key) == turn_id:
            del self._busy_sessions[key]
        self._finished[turn_id] = entry
        while len(self._finished) > native_host_constants.NATIVE_FINISHED_TURN_LIMIT:
            self._finished.popitem(last=False)

    def _session_key(self, session_id: str) -> str:
        # @intent native-uuid-session-ids-ignore-case
        # Grok and Muse session ids are UUIDs, so an id and its
        # upper-cased form name one session, whichever spelling the
        # vendor or the caller chose; the busy key is lower case.
        # opencode ids are case-sensitive vendor ids, kept exact.
        if self._harness in (NativeHarness.GROK, NativeHarness.MUSE):
            return session_id.lower()
        return session_id

    def _busy(self, message: str, operation: str, context: dict[str, str]) -> NativeHostError:
        # session_busy with the host's default next step.
        return self._errors.build(FailureCode(f"{self._harness.value}.session_busy"), message, operation=operation, context=context)

    def _not_found(self, operation: str) -> NativeHostError:
        # turn_not_found with the host's default next step.
        return self._errors.build(FailureCode(f"{self._harness.value}.turn_not_found"), "This host has no turn with that handle; it was never issued here or was dropped from the finished-turn table.", operation=operation)


__all__ = ["NativeTurnTable"]
