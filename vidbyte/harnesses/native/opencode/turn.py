"""FILE: vidbyte/harnesses/native/opencode/turn.py

PURPOSE: Defines OpencodeTurnWatcher, which polls one opencode turn to its end: it finds the turn's user message after the pre-prompt snapshot, collects every reply whose parentID is that message, confirms completion over several idle polls, rejects the permission and question requests of the turn's session tree, aborts a turn past its ceiling, its tree limit or its retry limit, and returns the NativeTurnResult or raises the turn's failure.
ROLE IN CODEBASE: Built by OpencodeHost for each spawn or continue; its run coroutine is the turn's driver task, owned by NativeTurnTable and awaited by wait_opencode_turn. interrupt is called by interrupt_opencode_turn and __aexit__; fail records a failure the host found (EC-90); the host's driver calls abort_before_failing when run raises (EC-158).
ARCHITECTURE NOTE: Every poll reads GET /session/status, GET /permission, GET /question and the newest OPENCODE_WATCH_MESSAGE_LIMIT messages in that order (§8.5 steps 1 to 6), and every body becomes a §9.1 inbound record through OpencodeWire first (D-13). The loop is bounded by the turn ceiling plus the stop grace, and the poll interval is read from the constants module on each pass so tests can shrink it. Only server_unreachable and process_exited polls count toward OPENCODE_POLL_FAILURE_LIMIT; any other poll failure ends the turn at once (EC-87).
FUNCTION INVENTORY: run is the narrated main function; interrupt records a source and sends POST …/abort; fail records a host-found failure; abort_before_failing sends EC-158's best-effort abort for a turn the host fails; _read_statuses, _read_requests and _read_messages read one poll; _track_messages updates the user message and the reply set; _refresh_tree walks the session tree; _reject answers the tree's requests; _count_failure applies EC-87; _retry_failure applies EC-155's limit; _settled applies the idle confirmations; _result builds the outcome.
COMMON MODIFICATION PATTERNS: A new end condition is one more check in run with its own small helper; a new reply error mapping belongs in OpencodeWire.reply_failure.
WHAT NOT TO DO IN THIS FILE: 1. Do not answer a request from a session outside the turn's tree; on an attached server it may be the user's. 2. Do not answer anything but reject (D-11, INV-9). 3. Do not decide the outcome from an earlier step's reply; only the newest reply counts (EC-85). 4. Do not sleep in a loop without the turn's deadline.
KNOWN EDGE CASES: A reply still being written (no time.completed) never completes the turn. An outside session id causes one tree walk and is then remembered for the turn. An abort the server never confirms still ends the turn after NATIVE_STOP_GRACE_SECONDS. An abort the host did not send reads as CALLER.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (OpencodeTurnWatcher), D-9, D-10, D-11, D-14, EC-80 to EC-89, EC-154, EC-155, INV-10, INV-12, INV-13, INV-15
TESTS: tests/features/opencode_host/test_opencode_host_watcher.py, tests/features/opencode_host/test_opencode_host_errors.py
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.harnesses.native.opencode.client import OpencodeClient
from vidbyte.harnesses.native.opencode.wire import OpencodeWire
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.native_hosts import (
    NativeApprovalDecision,
    NativeTokenUsage,
    NativeTurnHandle,
    NativeTurnResult,
)
from vidbyte.lib.dataclasses.opencode import (
    OpencodeMessage,
    OpencodePermissionRequest,
    OpencodePromptRequest,
    OpencodeQuestionRequest,
    OpencodeSessionStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import (
    ApprovalOutcome,
    InterruptSource,
    NativeTurnStatus,
)
from vidbyte.lib.errors import NativeHostError

_USER_ROLE = "user"
_ABORTED_ERROR = "MessageAbortedError"
_OUTPUT_LENGTH_ERROR = "MessageOutputLengthError"
_OUTPUT_LENGTH_STOP = "output_length"
_QUESTION_KIND = "opencode.question"
_PERMISSION_KIND = "opencode.permission:{permission}"
_REJECT_BODY = {"reply": "reject"}
_COUNTED_FAILURES = frozenset({FailureCode.OPENCODE_SERVER_UNREACHABLE, FailureCode.OPENCODE_PROCESS_EXITED})
_USAGE_FIELDS = ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens", "cache_write_tokens", "total_tokens", "cost_usd")
_PATTERN_SEPARATOR = ", "
_NO_FAILED_POLLS = 0
_TREE_ROOT_INDEX = 0
_TREE_STEP = 1


class OpencodeTurnWatcher:
    """Polls one opencode turn to its end and rejects the requests of its session tree."""

    def __init__(self, *, handle: NativeTurnHandle, request: OpencodePromptRequest, snapshot_id: str | None, client: OpencodeClient, wire: OpencodeWire, errors: NativeErrorFactory, request_timeout_seconds: float) -> None:
        # @intent opencode-watcher-owns-one-turn
        # A watcher holds the state of exactly one turn: the snapshot that
        # separates its reply from earlier ones, the first interrupt source,
        # the recorded failure that every later wait repeats (EC-148),
        # whether opencode itself ended the turn, and the request timeout
        # that bounds how long its prompt may go unseen.
        self._handle = handle
        self._session_id = handle.session_id
        self._request = request
        self._snapshot_id = snapshot_id
        self._client = client
        self._wire = wire
        self._errors = errors
        self._request_timeout_seconds = request_timeout_seconds
        self._source: InterruptSource | None = None
        self._abort_deadline: float | None = None
        self._failure: NativeHostError | None = None
        self._server_ended = False
        self._user_message_id: str | None = None
        self._active = False
        self._replies: dict[str, OpencodeMessage] = {}
        self._idle_polls = 0
        self._failed_polls = _NO_FAILED_POLLS
        self._tree: set[str] = {handle.session_id}
        self._outside: set[str] = set()
        self._answered: set[str] = set()
        self._decisions: list[NativeApprovalDecision] = []
        self._dropped = 0

    async def run(self) -> NativeTurnResult:
        # @intent opencode-watcher-bounded-poll-loop
        # The loop polls until the turn settles, fails, or passes its ceiling
        # plus the stop grace; the ceiling sends one abort first (D-10), so
        # the loop always has an overall deadline (S052, S064).
        loop = asyncio.get_running_loop()
        started = loop.time()
        ceiling = started + self._request.max_turn_seconds
        prompt_deadline = started + self._request_timeout_seconds
        hard_stop = ceiling + native_host_constants.NATIVE_STOP_GRACE_SECONDS
        while loop.time() < hard_stop:
            # A failure the host found for this turn ends it at once (EC-90).
            if self._failure is not None:
                raise self._failure

            # An abort the server has not confirmed within the grace still ends the turn.
            if self._abort_deadline is not None and loop.time() >= self._abort_deadline:
                return self._result(abort_overdue=True)
            try:
                # Past the ceiling, abort the turn once with the DEADLINE source.
                if loop.time() >= ceiling and self._source is None:
                    await self.interrupt(InterruptSource.DEADLINE, operation=native_host_constants.OPENCODE_TURN_OPERATION)

                # Read the statuses, the pending requests and the newest messages, in that order.
                statuses = await self._read_statuses()
                permissions, questions = await self._read_requests()
                messages = await self._read_messages()

                # Walk the session tree when a request names an unknown session; past the limit, abort by policy (EC-154).
                if await self._refresh_tree(permissions, questions) and self._source is None:
                    await self.interrupt(InterruptSource.POLICY, operation=native_host_constants.OPENCODE_TURN_OPERATION)

                # Reject every request from the tree and record the answers (D-11).
                await self._reject(permissions, questions)
            except NativeHostError as exc:
                # Only unreachable or exited polls are retried, up to the limit (EC-87).
                self._count_failure(exc)
            else:
                self._failed_polls = _NO_FAILED_POLLS
                status = statuses.get(self._session_id)

                # A retry loop at the attempt limit fails the turn; the driver aborts it first (EC-155, EC-158).
                failure = self._retry_failure(status)
                if failure is not None:
                    raise failure

                # Fold this poll's messages into the turn, then end it once idle is confirmed.
                self._track_messages(messages)
                if self._settled(status, prompt_overdue=loop.time() >= prompt_deadline):
                    return self._result(abort_overdue=False)
            await asyncio.sleep(native_host_constants.OPENCODE_POLL_INTERVAL_SECONDS)

        # The ceiling and its grace have passed without the server confirming the abort.
        return self._result(abort_overdue=True)

    async def interrupt(self, source: InterruptSource, *, operation: str) -> None:
        # @intent opencode-watcher-records-abort-source
        # The first recorded source wins and is set before POST …/abort, so a
        # poll that sees the abort reply already knows who sent it (EC-88);
        # a failed abort leaves no source behind. A turn already recorded as
        # failed has nothing left to abort.
        if self._failure is not None:
            return
        first = self._source is None
        if first:
            self._source = source
        sent = False
        try:
            await self._client.call("POST", ("session", self._session_id, "abort"), operation=operation)
            sent = True
        finally:
            if first and not sent:
                self._source = None
        if first:
            self._abort_deadline = asyncio.get_running_loop().time() + native_host_constants.NATIVE_STOP_GRACE_SECONDS

    def fail(self, error: NativeHostError) -> None:
        # Records a failure the host found outside the poll loop; the next pass raises it.
        self._failure = error

    async def abort_before_failing(self, error: Exception) -> None:
        # @intent opencode-watcher-aborts-a-turn-the-host-fails
        # EC-158: a turn the host fails on its own would keep running and
        # spending at the server, so one best-effort POST …/abort is sent
        # before the failure is recorded, bounded by the request deadline,
        # and its own failure is dropped so the turn's error stays as it is.
        # Nothing is sent when opencode itself ended the turn (a reply
        # error, no reply, a deleted session) or already answered an abort
        # the host sent for this turn.
        if self._server_ended or self._abort_deadline is not None or error is self._failure:
            return
        if isinstance(error, NativeHostError) and error.failure_code is FailureCode.OPENCODE_SESSION_NOT_FOUND:
            return
        with contextlib.suppress(NativeHostError):
            await self._client.call("POST", ("session", self._session_id, "abort"), operation=native_host_constants.OPENCODE_TURN_OPERATION)

    async def _read_statuses(self) -> Mapping[str, OpencodeSessionStatus]:
        # GET /session/status as a map of session id to status; an absent session is idle.
        body = await self._client.call("GET", ("session", "status"), operation=native_host_constants.OPENCODE_TURN_OPERATION)
        return {status.session_id: status for status in self._wire.parse_session_statuses(body, operation=native_host_constants.OPENCODE_TURN_OPERATION)}

    async def _read_requests(self) -> tuple[tuple[OpencodePermissionRequest, ...], tuple[OpencodeQuestionRequest, ...]]:
        # @intent opencode-watcher-reads-every-pending-request
        # Every pending permission and question request on the server is
        # read on each poll, so none from the turn's tree can wait unanswered
        # and stall the turn; which ones belong to the tree is decided later.
        permissions = self._wire.parse_permission_requests(await self._client.call("GET", ("permission",), operation=native_host_constants.OPENCODE_TURN_OPERATION), operation=native_host_constants.OPENCODE_TURN_OPERATION)
        questions = self._wire.parse_question_requests(await self._client.call("GET", ("question",), operation=native_host_constants.OPENCODE_TURN_OPERATION), operation=native_host_constants.OPENCODE_TURN_OPERATION)
        return permissions, questions

    async def _read_messages(self) -> tuple[OpencodeMessage, ...]:
        # The newest OPENCODE_WATCH_MESSAGE_LIMIT messages; a 404 means the session was deleted mid-turn (EC-86).
        query = {"limit": str(native_host_constants.OPENCODE_WATCH_MESSAGE_LIMIT)}
        body = await self._client.call("GET", ("session", self._session_id, "message"), operation=native_host_constants.OPENCODE_TURN_OPERATION, query=query, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
        return self._wire.parse_messages(body, operation=native_host_constants.OPENCODE_TURN_OPERATION)

    def _track_messages(self, messages: tuple[OpencodeMessage, ...]) -> None:
        # The turn's user message is the first user message newer than the
        # snapshot; its replies are kept by id across polls, latest version
        # each, so a reply that left the window still counts (§8.5 step 3).
        if self._user_message_id is None:
            newer = (message for message in messages if message.role == _USER_ROLE and (self._snapshot_id is None or message.message_id > self._snapshot_id))
            self._user_message_id = next((message.message_id for message in newer), None)
        if self._user_message_id is None:
            return
        for message in messages:
            if message.role == native_host_constants.OPENCODE_ASSISTANT_ROLE and message.parent_id == self._user_message_id:
                self._replies[message.message_id] = message

    async def _refresh_tree(self, permissions: tuple[OpencodePermissionRequest, ...], questions: tuple[OpencodeQuestionRequest, ...]) -> bool:
        # @intent opencode-watcher-session-tree
        # The tree is the turn's session and its descendants, walked
        # breadth-first only when a request names a session neither in the
        # tree nor known to be outside it; ids still outside are remembered
        # for the turn. Returns True when the tree passes the size limit.
        named = {request.session_id for request in permissions} | {question.session_id for question in questions}
        unknown = named - self._tree - self._outside
        if not unknown:
            return False
        limit = native_host_constants.OPENCODE_MAX_SESSION_TREE
        order = [self._session_id]
        index = _TREE_ROOT_INDEX
        while index < len(order) and len(order) <= limit:
            body = await self._client.call("GET", ("session", order[index], "children"), operation=native_host_constants.OPENCODE_TURN_OPERATION, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            order.extend(child.session_id for child in self._wire.parse_sessions(body, operation=native_host_constants.OPENCODE_TURN_OPERATION) if child.session_id not in order)
            index += _TREE_STEP
        self._tree = set(order)
        self._outside |= unknown - self._tree
        return len(order) > limit

    async def _reject(self, permissions: tuple[OpencodePermissionRequest, ...], questions: tuple[OpencodeQuestionRequest, ...]) -> None:
        # @intent opencode-watcher-rejects-tree-requests
        # Each request from the tree is answered once with reject, never
        # once or always, and recorded; past NATIVE_MAX_RECORDED_DECISIONS
        # the answers are only counted (D-11, INV-10).
        cap = native_host_constants.NATIVE_ID_MAX_CHARS
        pending: list[tuple[str, tuple[str, ...], Mapping[str, str] | None, NativeApprovalDecision]] = [
            (
                permission.request_id,
                ("permission", permission.request_id, "reply"),
                _REJECT_BODY,
                NativeApprovalDecision(request_kind=_PERMISSION_KIND.format(permission=permission.permission)[:cap], title=self._errors.scrub(_PATTERN_SEPARATOR.join(permission.patterns))[:cap], outcome=ApprovalOutcome.REJECTED),
            )
            for permission in permissions
            if permission.session_id in self._tree and permission.request_id not in self._answered
        ]
        pending.extend(
            (question.request_id, ("question", question.request_id, "reject"), None, NativeApprovalDecision(request_kind=_QUESTION_KIND, title="", outcome=ApprovalOutcome.REJECTED))
            for question in questions
            if question.session_id in self._tree and question.request_id not in self._answered
        )
        for request_id, route, body, decision in pending:
            await self._client.call("POST", route, operation=native_host_constants.OPENCODE_TURN_OPERATION, body=body)
            self._answered.add(request_id)
            if len(self._decisions) < native_host_constants.NATIVE_MAX_RECORDED_DECISIONS:
                self._decisions.append(decision)
            else:
                self._dropped += 1

    def _count_failure(self, error: NativeHostError) -> None:
        # Re-raises any failure that is not an unreachable or exited server, and the one that reaches the limit.
        if error.failure_code not in _COUNTED_FAILURES:
            raise error
        self._failed_polls += 1
        if self._failed_polls >= native_host_constants.OPENCODE_POLL_FAILURE_LIMIT:
            raise error

    def _retry_failure(self, status: OpencodeSessionStatus | None) -> NativeHostError | None:
        # @intent opencode-watcher-retry-limit
        # A retry status at OPENCODE_RETRY_ATTEMPT_LIMIT or later fails the
        # turn: usage_limited when the message or reason carries a
        # rate-limit marker (A-17), else api_error, with the attempt, the
        # reason and the scrubbed message in the context (EC-155). The
        # abort that stops the retry loop is EC-158's, sent by the driver.
        if status is None or status.retry_attempt is None or status.retry_attempt < native_host_constants.OPENCODE_RETRY_ATTEMPT_LIMIT:
            return None
        evidence = f"{status.retry_message or ''} {status.retry_reason or ''}".casefold()
        limited = any(marker in evidence for marker in native_host_constants.OPENCODE_RATE_LIMIT_MARKERS)
        context = {"retry_attempt": str(status.retry_attempt)}
        if status.retry_reason is not None:
            context["reason"] = status.retry_reason
        if status.retry_message is not None:
            context["vendor_error"] = status.retry_message
        code = FailureCode.OPENCODE_USAGE_LIMITED if limited else FailureCode.OPENCODE_API_ERROR
        return self._errors.build(code, f"opencode kept retrying the model call ({status.retry_attempt} attempts), so the turn was aborted.", operation=native_host_constants.OPENCODE_TURN_OPERATION, context=context)

    def _settled(self, status: OpencodeSessionStatus | None, *, prompt_overdue: bool) -> bool:
        # @intent opencode-watcher-idle-confirmations
        # Idle polls count only after the user message or a busy or retry
        # status was seen, and only while no reply exists or the newest one
        # has time.completed; OPENCODE_IDLE_CONFIRMATIONS in a row end the
        # turn. Nothing seen within the request deadline is prompt_not_seen.
        busy = status is not None and status.state in native_host_constants.OPENCODE_BUSY_STATES
        self._active = self._active or busy or self._user_message_id is not None
        if not self._active:
            if prompt_overdue:
                raise self._errors.build(FailureCode.OPENCODE_API_ERROR, "opencode never showed the prompt as received.", operation=native_host_constants.OPENCODE_TURN_OPERATION, context={"reason": "prompt_not_seen", "vendor_error": "prompt_not_seen"})
            return False
        newest = max(self._replies.values(), key=lambda message: (message.created_ms, message.message_id), default=None)
        counts = not busy and (newest is None or newest.completed_ms is not None)
        self._idle_polls = self._idle_polls + 1 if counts else 0
        return self._idle_polls >= native_host_constants.OPENCODE_IDLE_CONFIRMATIONS

    def _result(self, *, abort_overdue: bool) -> NativeTurnResult:
        # @intent opencode-watcher-outcome
        # The newest reply decides: an abort error, or an abort the server
        # never confirmed, is INTERRUPTED with the recorded source (CALLER
        # when none was recorded); an output-length error is COMPLETED; any
        # other error fails the turn; no reply at all is no_reply. Usage is
        # summed field by field over every reply (D-14, INV-15). From here
        # the outcome is opencode's own, so a failure needs no abort.
        self._server_ended = True
        newest = max(self._replies.values(), key=lambda message: (message.created_ms, message.message_id), default=None)
        error = None if newest is None else newest.error
        reports = [reply.usage for reply in self._replies.values() if reply.usage is not None]
        values = {name: [getattr(usage, name) for usage in reports if getattr(usage, name) is not None] for name in _USAGE_FIELDS}
        usage = NativeTokenUsage(**{name: sum(items[1:], items[0]) if items else None for name, items in values.items()}) if reports else None
        decisions = tuple(self._decisions)
        aborted = abort_overdue or (error is not None and error.name == _ABORTED_ERROR) or (newest is None and self._source is not None)
        text = "" if newest is None else newest.text
        truncated = newest is not None and newest.text_truncated
        if aborted:
            source = self._source or (InterruptSource.DEADLINE if abort_overdue else InterruptSource.CALLER)
            return NativeTurnResult(handle=self._handle, status=NativeTurnStatus.INTERRUPTED, text=text, text_truncated=truncated, usage=usage, interrupt_source=source, decisions=decisions, decisions_dropped=self._dropped)
        if newest is None:
            raise self._errors.build(FailureCode.OPENCODE_API_ERROR, "opencode went idle without replying to the turn's prompt.", operation=native_host_constants.OPENCODE_TURN_OPERATION, context={"reason": "no_reply", "vendor_error": "no_reply"})
        if error is not None and error.name != _OUTPUT_LENGTH_ERROR:
            raise self._wire.reply_failure(error, operation=native_host_constants.OPENCODE_TURN_OPERATION)
        stop_reason = _OUTPUT_LENGTH_STOP if error is not None else newest.finish
        if stop_reason is not None:
            stop_reason = stop_reason[: native_host_constants.NATIVE_ID_MAX_CHARS]
        return NativeTurnResult(handle=self._handle, status=NativeTurnStatus.COMPLETED, stop_reason=stop_reason, text=text, text_truncated=truncated, usage=usage, decisions=decisions, decisions_dropped=self._dropped)


__all__ = ["OpencodeTurnWatcher"]
