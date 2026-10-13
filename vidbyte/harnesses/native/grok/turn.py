"""FILE: vidbyte/harnesses/native/grok/turn.py

PURPOSE: Defines GrokTurnDriver, which plays one live Grok turn on its own ACP peer: it answers permission and other server requests by policy, collects the agent's message text and cost, applies the turn ceiling and the stop grace, and ends with a NativeTurnResult or the error that failed the turn.
ROLE IN CODEBASE: GrokHost (vidbyte/harnesses/native/grok/host.py) builds one driver per spawn or continue after session/prompt is written, runs driver.run as the turn's task in its NativeTurnTable, and calls interrupt and close from interrupt_grok_turn and __aexit__. wait_grok_turn awaits the task.
ARCHITECTURE NOTE: The driver owns its peer from the moment it is built and closes it whatever way the turn ends (D-2, D-23). Every frame becomes a §9.1 record through GrokWire before the driver reads it. An interrupt sends ACP session/cancel once and returns; the driver closes the peer NATIVE_STOP_GRACE_SECONDS later if the turn has not ended (EC-53, D-10).
FUNCTION INVENTORY: run is the narrated main function; interrupt sends the cancel and arms the stop timer; close stops the peer at once. Helpers: _next_frame waits for one frame or timer, _answer_permission and _refuse answer server requests, _take_update collects text and cost, _record keeps a decision within the cap, _outcome reads the prompt answer.
COMMON MODIFICATION PATTERNS: A new server request the host serves is one more branch in run plus its answering helper; a new update kind is one more branch in _take_update.
WHAT NOT TO DO IN THIS FILE: 1. Do not select an allow_always or reject_always option, and never allow a tool kind the request did not allow (D-11, INV-9). 2. Do not leave a server request unanswered while the turn runs (INV-10). 3. Do not report missing usage as zero (INV-15).
KNOWN EDGE CASES: Grok writes a turn's updates before its prompt answer, so updates still queued when the answer lands are taken before the result is built. A "cancelled" stop reason or a -32800 answer ends the turn INTERRUPTED, attributed to CALLER when this host did not send the cancel. A peer that stops after an interrupt ends the turn INTERRUPTED; one that stops without an interrupt fails it with process_exited (EC-48).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Grok host), D-9, D-10, D-11, D-14, EC-48 to EC-53, INV-10, INV-15, INV-16
TESTS: tests/features/grok_host/test_grok_host_turns.py, tests/features/grok_host/test_grok_host_process_bounds.py
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping
from typing import Any

from vidbyte.harnesses.native.grok.wire import GrokWire
from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativePeer
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.grok import GrokTurnRequest
from vidbyte.lib.dataclasses.native_hosts import (
    NativeApprovalDecision,
    NativeTokenUsage,
    NativeTurnHandle,
    NativeTurnResult,
)
from vidbyte.lib.enums.native_hosts import (
    ApprovalOutcome,
    InterruptSource,
    NativeTurnStatus,
)
from vidbyte.lib.errors import McpProtocolError, NativeHostError

_PERMISSION_KIND_PREFIX = "acp.permission:"
_ALLOW_ONCE = "allow_once"
_REJECT_ONCE = "reject_once"
_USD = "USD"
_DECISION_TITLE_MAX_CHARS = 200


class GrokTurnDriver:
    """Plays one live Grok turn on its own peer and ends it with a NativeTurnResult or the turn's error."""

    def __init__(self, *, peer: NativePeer, wire: GrokWire, errors: NativeErrorFactory, handle: NativeTurnHandle, request: GrokTurnRequest, answer: asyncio.Future[Mapping[str, Any]]) -> None:
        self._peer = peer
        self._wire = wire
        self._errors = errors
        self._handle = handle
        self._allowed = request.allowed_tool_kinds
        self._ceiling = request.max_turn_seconds
        self._answer = answer
        self._text: list[str] = []
        self._text_chars = 0
        self._truncated = False
        self._decisions: list[NativeApprovalDecision] = []
        self._dropped = 0
        self._cost_usage: NativeTokenUsage | None = None
        self._source: InterruptSource | None = None
        self._stop_at: float | None = None
        self._reader: asyncio.Task[Mapping[str, Any]] | None = None

    async def run(self) -> NativeTurnResult:
        # @intent grok-turn-driver-owns-its-peer
        # The driver serves the peer until Grok answers session/prompt, so
        # every server request is answered while the turn runs (INV-10), and
        # it closes the peer and its whole process tree however the turn
        # ends (D-23). A failed turn raises its grok.* error, which every
        # wait_grok_turn re-raises (D-9).
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._ceiling
        try:
            while not self._answer.done():
                # Take the next thing the peer sent, or wake for the ceiling, the stop grace or an interrupt.
                frame = await self._next_frame(deadline) or {}
                method = frame.get("method")
                # Answer permission requests by policy, refuse every other server request, and collect updates.
                if method == GrokWire.REQUEST_PERMISSION and "id" in frame:
                    self._record(await self._answer_permission(frame))
                elif method == GrokWire.SESSION_UPDATE:
                    self._take_update(frame)
                elif isinstance(method, str) and method and "id" in frame:
                    self._record(await self._refuse(frame))
                # At the turn ceiling the host interrupts the turn itself; a dead pipe is closed below anyway (D-10).
                if self._source is None and loop.time() >= deadline:
                    with contextlib.suppress(NativeHostError):
                        await self.interrupt(InterruptSource.DEADLINE, operation=native_host_constants.GROK_TURN_OPERATION)
                # Once the stop grace has passed, close the peer; its pending answer then fails and the loop ends.
                if self._stop_at is not None and loop.time() >= self._stop_at:
                    await self._peer.close()
            # Grok writes a turn's updates before its answer, so take the ones still queued.
            while not self._peer.inbox.empty():
                queued = self._peer.inbox.get_nowait()
                if queued.get("method") == GrokWire.SESSION_UPDATE:
                    self._take_update(queued)
            # Read the answer, then report the turn with its capped text, usage and decisions.
            interrupted, stop_reason, usage = self._outcome()
            return NativeTurnResult(
                handle=self._handle,
                status=NativeTurnStatus.INTERRUPTED if interrupted else NativeTurnStatus.COMPLETED,
                stop_reason=stop_reason,
                text="".join(self._text),
                text_truncated=self._truncated,
                usage=usage,
                interrupt_source=(self._source or InterruptSource.CALLER) if interrupted else None,
                decisions=tuple(self._decisions),
                decisions_dropped=self._dropped,
            )
        finally:
            # The turn is over either way: stop the peer, and mark a failed answer as seen so it is not logged as lost.
            await self._peer.close()
            if self._answer.done() and not self._answer.cancelled():
                self._answer.exception()

    async def interrupt(self, source: InterruptSource, *, operation: str) -> None:
        # @intent grok-interrupt-is-cancel-then-grace
        # EC-53 / D-10: an interrupt sends ACP session/cancel once and
        # returns at once; Grok then ends the turn itself, and if it has not
        # NATIVE_STOP_GRACE_SECONDS later the driver closes the peer. The
        # first source wins, and a cancel that cannot be written raises
        # process_exited (EC-51) while the stop timer still runs.
        if self._source is not None or self._answer.done():
            return
        self._source = source
        self._stop_at = asyncio.get_running_loop().time() + native_host_constants.NATIVE_STOP_GRACE_SECONDS
        if self._reader is not None:
            self._reader.cancel()
        await self._peer.notify(GrokWire.CANCEL, self._wire.cancel_params(self._handle.session_id), operation=operation)

    async def close(self) -> None:
        # Stops the peer now; the pending answer fails and run ends the turn (EC-8).
        await self._peer.close()

    async def _next_frame(self, deadline: float) -> Mapping[str, Any] | None:
        # Waits for one peer frame or the prompt answer until the next timer: the stop grace once interrupted, the ceiling before.
        loop = asyncio.get_running_loop()
        wake_at = self._stop_at if self._stop_at is not None else deadline
        reader = asyncio.create_task(self._peer.inbox.get())
        self._reader = reader
        try:
            await asyncio.wait({self._answer, reader}, timeout=wake_at - loop.time(), return_when=asyncio.FIRST_COMPLETED)
        finally:
            self._reader = None
            reader.cancel()
        if reader.done() and not reader.cancelled():
            return reader.result()
        return None

    async def _answer_permission(self, frame: Mapping[str, Any]) -> NativeApprovalDecision:
        # @intent grok-permission-policy
        # D-11: allow_once for a tool kind in allowed_tool_kinds, otherwise
        # reject_once, or the cancelled outcome when Grok offered no reject
        # option; never an *_always option, and the request is always
        # answered. A failed write means the peer is gone, which the prompt
        # answer reports.
        permission = self._wire.parse_permission_request(frame)
        allowing = permission.tool_kind in self._allowed
        allow = next((option.option_id for option in permission.options if option.kind == _ALLOW_ONCE), None) if allowing else None
        reject = next((option.option_id for option in permission.options if option.kind == _REJECT_ONCE), None)
        chosen, outcome = (allow, ApprovalOutcome.ALLOWED) if allow is not None else (reject, ApprovalOutcome.REJECTED)
        if chosen is None:
            outcome = ApprovalOutcome.CANCELLED
        with contextlib.suppress(McpProtocolError):
            await self._peer.answer(permission.request_id, result=self._wire.permission_answer(chosen))
        kind = _PERMISSION_KIND_PREFIX + permission.tool_kind.value
        return NativeApprovalDecision(request_kind=kind, title=permission.title[:_DECISION_TITLE_MAX_CHARS], outcome=outcome)

    async def _refuse(self, frame: Mapping[str, Any]) -> NativeApprovalDecision:
        # INV-10: any other server request gets JSON-RPC -32601 and is recorded as not supported.
        method = str(frame.get("method"))[: native_host_constants.NATIVE_ID_MAX_CHARS]
        with contextlib.suppress(McpProtocolError):
            await self._peer.answer(frame["id"], error=self._wire.method_not_found())
        return NativeApprovalDecision(request_kind=method, title="", outcome=ApprovalOutcome.NOT_SUPPORTED)

    def _take_update(self, frame: Mapping[str, Any]) -> None:
        # @intent grok-turn-text-and-cost
        # INV-16: message text is kept up to NATIVE_RESULT_TEXT_MAX_CHARS
        # and the rest only flagged; D-14: the latest usage_update's cost is
        # the turn's usage when Grok's answer has none, and only a USD cost
        # counts. Other update kinds change nothing (EC-7).
        update = self._wire.parse_session_update(frame.get("params"))
        if update.kind == GrokWire.USAGE_UPDATE:
            self._cost_usage = NativeTokenUsage(cost_usd=update.cost_amount) if update.cost_currency == _USD and update.cost_amount is not None else None
        room = native_host_constants.NATIVE_RESULT_TEXT_MAX_CHARS - self._text_chars
        kept = update.text[:room]
        self._truncated = self._truncated or len(update.text) > room
        if kept:
            self._text.append(kept)
            self._text_chars += len(kept)

    def _record(self, decision: NativeApprovalDecision) -> None:
        # INV-16: at most NATIVE_MAX_RECORDED_DECISIONS decisions are kept; the rest are counted.
        if len(self._decisions) < native_host_constants.NATIVE_MAX_RECORDED_DECISIONS:
            self._decisions.append(decision)
        else:
            self._dropped += 1

    def _outcome(self) -> tuple[bool, str | None, NativeTokenUsage | None]:
        # @intent grok-turn-outcome
        # EC-50: a "cancelled" stopReason or a -32800 answer ends the turn
        # interrupted, and any other stopReason completes it verbatim. A peer
        # that stopped after an interrupt also ends it interrupted; without
        # one the turn fails with process_exited (EC-48), and any other
        # JSON-RPC error fails it with its own row (EC-45 to EC-47).
        failure = None if self._answer.cancelled() else self._answer.exception()
        if not self._answer.cancelled() and failure is None:
            prompt = self._wire.parse_prompt_result(self._answer.result())
            return prompt.stop_reason == GrokWire.CANCELLED_STOP_REASON, prompt.stop_reason, prompt.usage or self._cost_usage
        if isinstance(failure, McpProtocolError) and self._wire.is_cancel_answer(failure):
            return True, GrokWire.CANCELLED_STOP_REASON, self._cost_usage
        if self._source is not None:
            return True, None, self._cost_usage
        if isinstance(failure, McpProtocolError):
            raise self._wire.vendor_error(failure, operation=native_host_constants.GROK_TURN_OPERATION, method=GrokWire.PROMPT, session_id=self._handle.session_id)
        raise self._errors.build(self._errors.code("process_exited"), "The Grok Build peer stopped before it answered the prompt.", operation=native_host_constants.GROK_TURN_OPERATION, context={"session_id": self._handle.session_id})


__all__ = ["GrokTurnDriver"]
