"""FILE: vidbyte/harnesses/native/codex/stream_methods.py

PURPOSE: CodexStreamMethods, the CodexHost mixin for reading turns while they run: stream_codex_turn returns an independent subscription to one turn's events, and wait_codex_turns waits on several turns at once and returns one snapshot per turn.
ROLE IN CODEBASE: One of the four feature mixins of vidbyte/harnesses/native/codex/; CodexHost inherits its two public methods (first-class D-1). Neither talks to Codex: the events come from the turn's own CodexTurnEventLog, which CodexTurnEvents fills as notifications arrive, and the snapshots from the turns CodexTurnRegistry holds.
ARCHITECTURE NOTE: Imports no openai-codex module and none of the host's SDK-loading collaborators at module level, so importing this mixin, or CodexHost, still loads no SDK (first-class INV-45). stream_codex_turn is a plain def, so its guard, record and handle check run when it is called and an unknown handle fails at the call, before any iteration (D-10, INV-22). wait_codex_turns waits on the turns' own ended futures with asyncio.wait, which never cancels them (D-13, INV-23).
COMMON MODIFICATION PATTERNS: A new way to read live turns is one public method here: guard with talks=False, its record, _owned for every handle before any wait, then a read of the turn's log or snapshot. A new event kind is a row in CODEX_HOST_STREAM_NOTIFICATION_KINDS, never code here.
KNOWN EDGE CASES: stream_codex_turn needs a running event loop, because _guard looks it up; called from plain synchronous code it raises Python's own RuntimeError (EC-3). Iterating a subscription on another loop is refused at its first step (INV-22). A caller of wait_codex_turns that is cancelled leaves every turn running, and a turn still running when the wait returns gets a RUNNING snapshot (INV-23, EC-22).
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.5, 9.2 and 12.3 row 27, INV-1, INV-21 to INV-23, D-10, D-13, D-37)
TESTS: tests/features/codex_host/test_codex_host_stream_wait.py, tests/features/codex_host/test_codex_host_feature_contract.py, tests/features/codex_host/test_codex_host_feature_structure.py, tests/features/codex_host/test_codex_host_feature_docs.py
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from vidbyte.harnesses.native.codex.host_core import CodexHostCore
from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle, CodexTurnSnapshot
from vidbyte.lib.dataclasses.codex_host_features import CodexTurnEvent
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexTurnRef,
    CodexTurnsWaitRequest,
)
from vidbyte.lib.enums.codex import CodexHostOperation, CodexTurnWaitMode


class CodexStreamMethods(CodexHostCore):
    """The stream and multi-turn wait functions CodexHost inherits; neither sends a request."""

    def stream_codex_turn(self, handle: CodexTurnHandle) -> AsyncIterator[CodexTurnEvent]:
        """Return a new subscription to a turn's events, from the oldest event the host still keeps; the last event is always ENDED.

        Call it on the host's running event loop and iterate it there.
        Each call is independent. Events dropped before a subscription
        reads them are reported as one GAP event. A caller that leaves
        ``async for`` early should close the subscription, for example
        with ``contextlib.aclosing``, so the host releases its window at
        once rather than when the subscription is collected.
        """
        # @intent a-stream-checks-its-handle-when-called
        # The guard, the record and the handle check run now, so an
        # unknown handle fails here, not at the first step; the
        # subscription's start is fixed now too (first-class INV-22).
        operation = CodexHostOperation.STREAM_CODEX_TURN
        self._guard(operation, talks=False)
        turn = self._owned(operation, CodexTurnRef(operation=operation, handle=handle).handle)
        return turn.events.subscribe()

    async def wait_codex_turns(
        self,
        handles: Sequence[CodexTurnHandle],
        return_when: CodexTurnWaitMode = CodexTurnWaitMode.FIRST_COMPLETED,
        timeout_seconds: float | None = None,
    ) -> tuple[CodexTurnSnapshot, ...]:
        """Wait for the first turn, or all of them, to end, at most timeout_seconds, and return one snapshot per handle in the order given.

        Waiting never stops a turn: a turn still running when the wait
        returns comes back as a RUNNING snapshot, and a cancelled wait
        leaves every turn running. Every handle must belong to this host.
        """
        # @intent waiting-on-many-turns-never-touches-them
        # Check every handle before any wait, then wait on the turns'
        # own ended futures, which asyncio.wait never cancels
        # (first-class INV-23, D-13).
        operation = CodexHostOperation.WAIT_CODEX_TURNS
        self._guard(operation, talks=False)
        waiting = CodexTurnsWaitRequest(handles=handles, return_when=return_when, timeout_seconds=timeout_seconds)
        turns = [self._owned(operation, handle) for handle in waiting.handles]
        await asyncio.wait([turn.ended for turn in turns], timeout=waiting.timeout_seconds, return_when=waiting.return_when.value)
        return tuple(turn.snapshot or self._responses.running(turn.handle) for turn in turns)


__all__ = ["CodexStreamMethods"]
