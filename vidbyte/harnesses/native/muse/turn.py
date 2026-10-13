"""FILE: vidbyte/harnesses/native/muse/turn.py

PURPOSE: Defines MuseTurnDriver, which runs one live Muse turn on its own peer from the turn/start ack to its end: it collects the reply text from the turn's agentMessage items, answers every approval with a denied choice scoped once (each requirement once) and every user-input request with a cancel, enforces the turn ceiling and the stop grace period, and turns the outcome into a NativeTurnResult or the turn's failure row.
ROLE IN CODEBASE: MuseHost (vidbyte/harnesses/native/muse/host.py) builds one driver per spawned or continued turn and runs MuseTurnDriver.run as the task NativeTurnTable owns; wait_muse_turn reads that task, and steer_muse_turn and interrupt_muse_turn use the driver's peer, ids and interrupt. Frames are parsed by MuseWire (vidbyte/harnesses/native/muse/wire.py).
ARCHITECTURE NOTE: run is the narrated main loop. It reads peer.inbox in arrival order with a short bounded wait, so a peer that exits mid-turn is noticed even though no request is pending, and hands each frame to one handler per method. A handler that must stop the turn (EC-121, EC-156) returns the stop source, and run sends turn/interrupt; every stop then gets NATIVE_STOP_GRACE_SECONDS for turn/completed before the peer is closed (D-10, D-23). The driver always closes its peer through the host's closer, which also runs the in-distro reap in WSL mode.
FUNCTION INVENTORY: run drives the turn and closes the peer; interrupt sends turn/interrupt and starts the grace period; close_after_grace starts it without sending; shut_down is __aexit__'s stop; peer, session_id, turn_id and running describe the turn; _next_frame waits for one frame; _on_item, _on_gap, _on_approval, _on_user_input, _on_completed and _on_other handle one method each; _grace_over checks the stop deadline; _outcome builds the result or raises the failure row.
COMMON MODIFICATION PATTERNS: A new MSP notification the turn must read is one more handler in _handlers, parsing its frame through a MuseWire parser first; a new failure kind is one more entry in _FAILURE_PROBLEMS.
WHAT NOT TO DO IN THIS FILE: 1. Do not pick an approving choice or a session or persistent scope; with no denied choice scoped once, record CANCELLED and stop the turn (INV-9, EC-121). 2. Do not match items or completions by commandId; the ack's turnId is the turn's id (EC-109). 3. Do not wait on the inbox without a bound; a dead peer sends nothing more.
KNOWN EDGE CASES: A turn/completed for another turn id, such as a foreign or queued turn, is ignored. A cancelled turn the host did not stop has source CALLER, because another client of the session stopped it. A decide answered -32051 or -32053 lost a benign race and the turn goes on; any other failed decide or cancel stops the turn by policy (EC-156). Decisions past NATIVE_MAX_RECORDED_DECISIONS are counted in decisions_dropped.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.5 (EC-109, EC-115 to EC-121, EC-156), §8.1 D-9, D-10, D-11, D-14, D-23, §8.5 (How MuseTurnDriver builds the result)
TESTS: tests/features/muse_host/test_muse_host_turns.py, tests/features/muse_host/test_muse_host_acceptance.py, tests/features/muse_host/test_muse_host_process_bounds.py
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativePeer
from vidbyte.harnesses.native.muse.wire import MuseWire
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.muse import MuseTurnAck, MuseTurnCompleted
from vidbyte.lib.dataclasses.native_hosts import (
    NativeApprovalDecision,
    NativeTurnHandle,
    NativeTurnResult,
)
from vidbyte.lib.enums.native_hosts import (
    ApprovalOutcome,
    InterruptSource,
    NativeTurnStatus,
)
from vidbyte.lib.errors import McpProtocolError, NativeHostError

_SHUTDOWN_OPERATION = "__aexit__"
_AGENT_MESSAGE_KIND = "agentMessage"
_TEXT_SEPARATOR = "\n\n"
_DENIED_DECISION = "denied"
_ONCE_SCOPE = "once"
_APPROVAL_KIND = "muse.approval"
_USER_INPUT_KIND = "muse.user_input"
_COMPLETED_TERMINAL = "completed"
_DEFAULT_FAILURE_PROBLEM = "api_error"
_NONE_DROPPED = 0
# turn/completed error kinds with a failure of their own; every
# other kind is api_error.
_FAILURE_PROBLEMS: Mapping[str, str] = MappingProxyType({"stepLimit": "budget_exhausted", "environmentError": "sandbox_not_ready"})


class MuseTurnDriver:
    """Runs one Muse turn on its own peer and builds its result."""

    def __init__(self, peer: NativePeer, *, handle: NativeTurnHandle, ack: MuseTurnAck, max_turn_seconds: float, errors: NativeErrorFactory, closer: Callable[[], Awaitable[None]]) -> None:
        self._peer = peer
        self._handle = handle
        self._ack = ack
        self._max_turn_seconds = max_turn_seconds
        self._errors = errors
        self._closer = closer
        self._text = ""
        self._text_truncated = False
        self._decided: set[tuple[str, str, int]] = set()
        self._cancelled_inputs: set[str] = set()
        self._decisions: list[NativeApprovalDecision] = []
        self._completed: MuseTurnCompleted | None = None
        self._stop_source: InterruptSource | None = None
        self._stop_deadline: float | None = None
        self._running = True
        self._handlers: Mapping[str, Callable[[Mapping[str, Any]], Awaitable[InterruptSource | None]]] = MappingProxyType(
            {
                "item/completed": self._on_item,
                "view/gap": self._on_gap,
                "approval/requested": self._on_approval,
                "approval/updated": self._on_approval,
                "userInput/requested": self._on_user_input,
                "turn/completed": self._on_completed,
            }
        )

    @property
    def peer(self) -> NativePeer:
        # The turn's own peer, for turn/steer.
        return self._peer

    @property
    def session_id(self) -> str:
        # The Muse session the turn runs in.
        return self._handle.session_id

    @property
    def turn_id(self) -> str:
        # The turn's MSP id, always the ack's turnId.
        return self._ack.turn_id

    @property
    def running(self) -> bool:
        # False once the driver has left its loop.
        return self._running

    async def run(self) -> NativeTurnResult:
        # @intent muse-turn-driver-owns-its-peer
        # The driver owns the peer from the ack on: it reads the turn's
        # frames until turn/completed, a stop's grace period ends or the
        # peer goes away, and it always closes the peer (and reaps it in
        # WSL mode) on the way out, whatever the outcome.
        loop = asyncio.get_running_loop()
        ceiling = loop.time() + self._max_turn_seconds
        try:
            while self._completed is None and not self._grace_over(loop.time()):
                # Take the next frame in arrival order, waiting only
                # briefly so a gone peer is noticed.
                frame = await self._next_frame()
                # Past the turn ceiling the turn must stop.
                stop = InterruptSource.DEADLINE if loop.time() >= ceiling else None
                if frame is not None:
                    # Hand the frame to its method's handler; a handler
                    # that must stop the turn names who stops it.
                    stop = await self._handlers.get(str(frame.get("method")), self._on_other)(frame) or stop
                elif self._peer.closed and self._peer.inbox.empty():
                    # The peer closed its output and every frame it sent
                    # was read: it is gone.
                    break
                if stop is not None and self._stop_source is None:
                    # Ask Muse to stop the turn; whether or not it
                    # answers, the grace period bounds the wait.
                    with contextlib.suppress(NativeHostError):
                        await self.interrupt(stop, operation=native_host_constants.MUSE_TURN_OPERATION)
                    self.close_after_grace(stop)
            # Turn what happened into the result, or into
            # the turn's failure.
            return self._outcome()
        finally:
            self._running = False
            await self._closer()

    async def interrupt(self, source: InterruptSource, *, operation: str, timeout_seconds: float | None = None) -> None:
        # @intent muse-turn-interrupt-starts-the-grace-period
        # turn/interrupt for the ack's turn id. -32013 and
        # -32014 mean the turn is already stopping, which
        # counts as success. Once Muse has the interrupt, the
        # turn gets NATIVE_STOP_GRACE_SECONDS to finish before
        # the driver closes the peer.
        params = MuseWire.turn_interrupt_params(self._handle.session_id, self._ack.turn_id)
        try:
            await self._peer.call("turn/interrupt", params, operation=operation, timeout_seconds=timeout_seconds)
        except McpProtocolError as exc:
            if not MuseWire.is_already_stopping(exc):
                raise MuseWire.vendor_failure(exc, operation=operation) from exc
        self._stop_source = self._stop_source or source
        if self._stop_deadline is None:
            self._stop_deadline = asyncio.get_running_loop().time() + native_host_constants.NATIVE_STOP_GRACE_SECONDS

    def close_after_grace(self, source: InterruptSource) -> None:
        # Records who stops the turn and closes the peer after the grace
        # period, even when no interrupt reached Muse.
        self._stop_source = self._stop_source or source
        if self._stop_deadline is None:
            self._stop_deadline = asyncio.get_running_loop().time() + native_host_constants.NATIVE_STOP_GRACE_SECONDS

    async def shut_down(self) -> None:
        # The host is closing, so ask Muse to stop the turn within the
        # grace period and let the driver close the peer when it ends;
        # the turn finishes INTERRUPTED with source HOST_CLOSED.
        with contextlib.suppress(NativeHostError):
            await self.interrupt(InterruptSource.HOST_CLOSED, operation=_SHUTDOWN_OPERATION, timeout_seconds=native_host_constants.NATIVE_STOP_GRACE_SECONDS)
        self.close_after_grace(InterruptSource.HOST_CLOSED)

    async def _next_frame(self) -> Mapping[str, Any] | None:
        # One frame from the inbox, or None when none arrives
        # within the poll interval.
        try:
            async with asyncio.timeout(native_host_constants.MUSE_FRAME_POLL_SECONDS):
                return await self._peer.inbox.get()
        except TimeoutError:
            return None

    async def _on_item(self, frame: Mapping[str, Any]) -> InterruptSource | None:
        # Only this turn's agentMessage items carry reply text; they
        # join with a blank line up to NATIVE_RESULT_TEXT_MAX_CHARS.
        item = MuseWire.parse_item_completed(frame.get("params"), operation=native_host_constants.MUSE_TURN_OPERATION)
        if item.kind != _AGENT_MESSAGE_KIND or item.turn_id != self._ack.turn_id:
            return None
        limit = native_host_constants.NATIVE_RESULT_TEXT_MAX_CHARS
        self._text_truncated = self._text_truncated or item.truncated
        if item.text is not None:
            joined = item.text if not self._text else self._text + _TEXT_SEPARATOR + item.text
            self._text_truncated = self._text_truncated or len(joined) > limit
            self._text = joined[:limit]
        return None

    async def _on_gap(self, frame: Mapping[str, Any]) -> InterruptSource | None:
        # A view gap may have dropped a reply item, so the
        # text may be incomplete.
        self._text_truncated = True
        return None

    async def _on_approval(self, frame: Mapping[str, Any]) -> InterruptSource | None:
        # @intent muse-approval-denied-once-per-requirement
        # Each requirement is decided once with the denied choice scoped
        # once. With no such choice nothing is chosen and the turn is
        # stopped by policy; a failed decide stops it too, except for
        # the two benign races.
        request = MuseWire.parse_approval_request(frame.get("params"), operation=native_host_constants.MUSE_TURN_OPERATION)
        key = (request.approval_id, request.requirement_approval_id, request.requirement_source_index)
        if key in self._decided:
            return None
        self._decided.add(key)
        title = self._errors.scrub(request.tool_name or request.approval_id)[: native_host_constants.NATIVE_APPROVAL_TITLE_MAX_CHARS]
        choice = next((item for item in request.choices if item.decision == _DENIED_DECISION and item.scope == _ONCE_SCOPE), None)
        if choice is None:
            self._decisions.append(NativeApprovalDecision(request_kind=_APPROVAL_KIND, title=title, outcome=ApprovalOutcome.CANCELLED))
            return InterruptSource.POLICY
        try:
            await self._peer.call("approval/decide", MuseWire.approval_decide_params(request, choice.choice_id), operation=native_host_constants.MUSE_TURN_OPERATION)
        except McpProtocolError as exc:
            self._decisions.append(NativeApprovalDecision(request_kind=_APPROVAL_KIND, title=title, outcome=ApprovalOutcome.CANCELLED))
            return None if MuseWire.is_benign_race(exc) else InterruptSource.POLICY
        except NativeHostError:
            self._decisions.append(NativeApprovalDecision(request_kind=_APPROVAL_KIND, title=title, outcome=ApprovalOutcome.CANCELLED))
            return InterruptSource.POLICY
        self._decisions.append(NativeApprovalDecision(request_kind=_APPROVAL_KIND, title=title, outcome=ApprovalOutcome.REJECTED))
        return None

    async def _on_user_input(self, frame: Mapping[str, Any]) -> InterruptSource | None:
        # @intent muse-user-input-always-cancelled
        # A question to the user is always cancelled and recorded as
        # CANCELLED; a failed cancel stops the turn by policy.
        request = MuseWire.parse_user_input_request(frame.get("params"), operation=native_host_constants.MUSE_TURN_OPERATION)
        if request.user_input_id in self._cancelled_inputs:
            return None
        self._cancelled_inputs.add(request.user_input_id)
        title = self._errors.scrub(request.tool_name)[: native_host_constants.NATIVE_APPROVAL_TITLE_MAX_CHARS]
        self._decisions.append(NativeApprovalDecision(request_kind=_USER_INPUT_KIND, title=title, outcome=ApprovalOutcome.CANCELLED))
        try:
            await self._peer.call("userInput/cancel", MuseWire.user_input_cancel_params(request), operation=native_host_constants.MUSE_TURN_OPERATION)
        except McpProtocolError as exc:
            return None if MuseWire.is_benign_race(exc) else InterruptSource.POLICY
        except NativeHostError:
            return InterruptSource.POLICY
        return None

    async def _on_completed(self, frame: Mapping[str, Any]) -> InterruptSource | None:
        # Only the completion of the ack's turn ends this turn;
        # others are ignored.
        completed = MuseWire.parse_turn_completed(frame.get("params"), operation=native_host_constants.MUSE_TURN_OPERATION)
        if completed.turn_id == self._ack.turn_id:
            self._completed = completed
        return None

    async def _on_other(self, frame: Mapping[str, Any]) -> InterruptSource | None:
        # @intent muse-unknown-server-request-gets-method-not-found
        # Any other server request is answered -32601; an unknown
        # notification is ignored, because MSP vocabularies are open.
        if "id" in frame:
            with contextlib.suppress(McpProtocolError):
                await self._peer.answer(frame["id"], error=MuseWire.method_not_found_error())
        return None

    def _grace_over(self, now: float) -> bool:
        # True once a stop's grace period has passed
        # without turn/completed.
        return self._stop_deadline is not None and now >= self._stop_deadline

    def _outcome(self) -> NativeTurnResult:
        # A failed turn raises its muse.* failure and a peer that
        # went away unasked raises process_exited. Otherwise the turn
        # is COMPLETED, or INTERRUPTED by whoever stopped it; a
        # cancel the host did not ask for came from another client,
        # so its source is CALLER.
        completed = self._completed
        if completed is not None and completed.terminal == native_host_constants.MUSE_FAILED_TERMINAL:
            kind = str(completed.error_kind)
            context = {"vendor_kind": kind, "retryable": native_host_constants.NATIVE_TRUE_TEXT if completed.error_retryable else native_host_constants.NATIVE_FALSE_TEXT, "vendor_error": str(completed.error_message)}
            raise self._errors.build(self._errors.code(_FAILURE_PROBLEMS.get(kind, _DEFAULT_FAILURE_PROBLEM)), f"The Muse turn failed with {kind}.", operation=native_host_constants.MUSE_TURN_OPERATION, context=context)
        if completed is None and self._stop_source is None:
            raise self._errors.build(self._errors.code("process_exited"), "The Muse Code process stopped before the turn completed.", operation=native_host_constants.MUSE_TURN_OPERATION, context={"reason": "process_exited"})
        finished = completed is not None and completed.terminal == _COMPLETED_TERMINAL
        cap = native_host_constants.NATIVE_MAX_RECORDED_DECISIONS
        return NativeTurnResult(
            handle=self._handle,
            status=NativeTurnStatus.COMPLETED if finished else NativeTurnStatus.INTERRUPTED,
            stop_reason=completed.terminal if completed is not None else None,
            text=self._text,
            text_truncated=self._text_truncated,
            usage=completed.usage if completed is not None else None,
            interrupt_source=None if finished else (self._stop_source or InterruptSource.CALLER),
            decisions=tuple(self._decisions[:cap]),
            decisions_dropped=max(len(self._decisions) - cap, _NONE_DROPPED),
        )


__all__ = ["MuseTurnDriver"]
