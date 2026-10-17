"""FILE: vidbyte/harnesses/native/codex/connection.py

PURPOSE: Owns one CodexHost's openai-codex client: the host's own call executor, every bounded app-server call and its log record, the overload retries of the idempotent reads, the shielded spending starts and their late acceptance, the liveness monitor, the close thread, and the server-request router that answers approvals, questions and dynamic tool calls.
ROLE IN CODEBASE: The process and transport layer of vidbyte/harnesses/native/codex/; CodexHost and CodexPreflight reach Codex only through CodexConnection, and the developer's approval_handler is reached only through CodexServerRequestRouter.
ARCHITECTURE NOTE: "from openai_codex.client import CodexClient, CodexConfig" and "from openai_codex.retry import retry_on_overload" at module level are test seams (section 13), so only CodexHost.__aenter__ imports this module (D-21). Every call runs on the host's own ThreadPoolExecutor, bounded by asyncio.wait_for, never on the loop or its default executor (D-1); the bounds, including CODEX_TOOL_CALL_TIMEOUT_SECONDS for the approval handler, are read from this module's namespace at call time. The router schedules the handler on the host's loop and waits for it on openai-codex's reader thread, under one lock shared with close (hardening INV-17, INV-21).
COMMON MODIFICATION PATTERNS: A new app-server call goes through call() with a typed CodexClient method, or through raw() when openai-codex has no typed method, with its generated response model's name in CODEX_HOST_RAW_RESPONSE_MODELS (vidbyte/lib/constants/codex_host.py); a raw call that spends usage is added to CODEX_HOST_SPENDING_RAW_METHODS there, so it is sent once (D-2), and a typed idempotent read joins CODEX_HOST_RETRIED_METHODS there to be retried on overload (hardening D-7). A new routed server-request kind is a CodexServerRequestKind member; the router needs no change beyond its fit check (INV-18).
KNOWN EDGE CASES: A spending start that outlives its caller or its bound is owned, never orphaned: a queued start is withdrawn, and a running one posts its outcome to the loop when it returns (INV-11). The router and the done-callback run on openai-codex's threads, so they never raise. Once close began or the process died, only cleanup calls are sent; a call refused for that reason sent nothing, so it writes no log record, and neither does a cancelled call. A host without an approval_handler answers every routed request with its fail-closed default and writes no fallback WARNING, because that default is its designed answer (hardening INV-8, INV-16). The router never holds its lock while it waits for the handler, because close takes that lock on the loop the handler needs. Codex chooses the method and ids of a server request and a caller or Codex the thread id of a call, so each record shows them through LogToken.of, cut at CODEX_HOST_LOG_TOKEN_MAX_CHARS, while routing, answers and errors keep the raw values (hardening INV-10).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-1 to D-3, D-18 and D-27, and 12.4 call list); docs/spec/codex-host-thread-helpers/spec.md (section 9.2 wire calls); docs/spec/codex-host-hardening/spec.md (sections 6.1 INV-3, INV-7, INV-8, INV-10, INV-15 to INV-18 and INV-21, and 8.1 D-3, D-7, D-12)
TESTS: tests/features/codex_host/test_codex_host_lifecycle.py, tests/features/codex_host/test_codex_host_failures.py, tests/features/codex_host/test_codex_host_router.py, tests/features/codex_host/test_codex_host_helper_lifecycle.py, tests/features/codex_host/test_codex_host_approvals.py, tests/features/codex_host/test_codex_host_observability.py, tests/features/codex_host/test_codex_host_resilience.py, tests/features/codex_host/test_codex_host_sdk_contract.py
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar, cast

from openai_codex.client import CodexClient, CodexConfig
from openai_codex.errors import JsonRpcError
from openai_codex.generated import v2_all
from openai_codex.generated.v2_all import WindowsSandboxReadinessResponse
from openai_codex.models import InitializeResponse
from openai_codex.retry import retry_on_overload

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.harnesses.native.codex.wire import CodexParamsTranslator
from vidbyte.lib.constants.codex import (
    CODEX_GOAL_CANCEL_CALL,
    CODEX_HOST_CLOSE_INTERRUPT_SECONDS,
    CODEX_HOST_CLOSE_WAIT_SECONDS,
    CODEX_HOST_REQUEST_TIMEOUT_SECONDS,
    CODEX_HOST_SINGLE_ATTEMPT,
    CODEX_HOST_WORKER_THREADS,
    CODEX_INITIALIZE_METHOD,
    CODEX_MILLISECONDS_PER_SECOND,
    CODEX_SANDBOX_READINESS_METHOD,
    CODEX_TOOL_CALL_METHOD,
    CODEX_TOOL_CALL_TIMEOUT_SECONDS,
    CODEX_TURN_INTERRUPT_METHOD,
    CODEX_UNREGISTERED_TOOL_TEXT,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_LOG_TOKEN_MAX_CHARS,
    CODEX_HOST_PROCESS_START,
    CODEX_HOST_RAW_RESPONSE_MODELS,
    CODEX_HOST_RETRIED_METHODS,
    CODEX_HOST_SPENDING_RAW_METHODS,
)
from vidbyte.lib.dataclasses.codex_host import CodexServerAnswer, CodexServerRequest
from vidbyte.lib.enums.codex import (
    CodexApprovalDecision,
    CodexHostOperation,
    CodexSandboxReadiness,
    CodexServerRequestKind,
)
from vidbyte.lib.errors import CodexAgentError
from vidbyte.lib.util.exception_origin import ExceptionOrigin
from vidbyte.lib.util.text import LogToken

if TYPE_CHECKING:
    from openai_codex._goal import _GoalOperationState

    from vidbyte.agents.codex.tools import CodexToolCallHandler
    from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

ResultT = TypeVar("ResultT")
logger = logging.getLogger(__name__)


class CodexServerRequestRouter:
    """Answers every server request of one host's client: approvals and questions through the developer's handler, tool calls by thread, and the rest with fixed defaults."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        approval_handler: Callable[[CodexServerRequest], Awaitable[CodexServerAnswer]] | None,
    ) -> None:
        # Each thread with Vidbyte tools has its own tool-call handler
        # (D-18). The developer's approval handler runs on the host's
        # loop. One lock guards the handler, the closed flag and the
        # handler calls still pending, because the reader thread and
        # the loop both reach them (hardening INV-17, INV-21). Whether
        # the router was built with a handler never changes, so a
        # host without one never logs a fallback (INV-8).
        self._handlers: dict[str, CodexToolCallHandler] = {}
        self._loop = loop
        self._approval_handler = approval_handler
        self._routes_requests = approval_handler is not None
        self._lock = threading.Lock()
        self._closed = False
        self._pending: set[Future[CodexServerAnswer]] = set()

    def register(self, thread_id: str, handler: CodexToolCallHandler) -> None:
        # A fork registers its parent's handler, as it inherits the
        # tools (D-29).
        self._handlers[thread_id] = handler

    def handler_for(self, thread_id: str) -> CodexToolCallHandler | None:
        # The handler of a thread, or None when it has no Vidbyte tools.
        return self._handlers.get(thread_id)

    def unregister(self, thread_id: str) -> None:
        # A thread whose start failed loses its tool handler. The
        # handler is not closed, because a fork shares its parent's
        # (hardening INV-26, INV-28 step 8).
        self._handlers.pop(thread_id, None)

    def remove_all(self) -> tuple[CodexToolCallHandler, ...]:
        # At close every thread's handler is removed and handed back, so
        # the host can cancel the tool calls still running (INV-7 step
        # 1).
        handlers = tuple(self._handlers.values())
        self._handlers = {}
        return handlers

    def cancel_pending(self) -> None:
        # @intent close-stops-the-approval-handler-first
        # Hardening INV-21: under the lock, the router closes, drops the
        # handler and cancels every handler call still running. It
        # cancels a snapshot, because each cancelled request's own
        # cleanup discards from the live set.
        with self._lock:
            self._closed = True
            self._approval_handler = None
            for future in tuple(self._pending):
                future.cancel()

    def handle(self, method: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
        # @intent answer-every-server-request-without-raising
        # Runs on openai-codex's reader thread, where a raise would stop
        # the host, so one try spans reading the request, scheduling the
        # developer's handler, waiting for it and checking its answer
        # (D-3, hardening INV-15, INV-17).
        thread_id, turn_id, item_id = self._ids(params)
        kind = next((kind for kind in CodexServerRequestKind if kind.value == method), None)
        handled_by = "tool" if method == CODEX_TOOL_CALL_METHOD else "default"
        answer: dict[str, Any] | None = None
        fallback: tuple[str, str, str] | None = None
        request: CodexServerRequest | None = None
        coroutine: Coroutine[Any, Any, CodexServerAnswer] | None = None
        future: Future[CodexServerAnswer] | None = None
        try:
            # A tool call goes to its thread's own tool handler, which
            # answers every call itself (D-18, EC-47).
            tools = self._handlers.get(thread_id) if handled_by == "tool" else None
            answer = None if tools is None else tools.handle(method, params)
            # An approval or a question goes to the developer's handler
            # when the host has one (INV-16). The close check, reading
            # the request into its record and scheduling the handler on
            # the host's loop happen under the lock close takes too, so
            # a closed router never calls the handler (INV-17, INV-21).
            # CodexHostSetup admits only async handlers, so the call
            # returns a coroutine (INV-19).
            if kind is not None and self._routes_requests:
                with self._lock:
                    handler = None if self._closed else self._approval_handler
                    request = None if handler is None else CodexServerRequest.from_params(kind, params)
                    coroutine = None if handler is None or request is None else cast("Coroutine[Any, Any, CodexServerAnswer]", handler(request))
                    future = None if coroutine is None else self._schedule(coroutine)
                fallback = ("closing", "", "") if future is None else None
            # The wait happens outside the lock, bounded by the timeout
            # read now, and only an answer that fits its request is sent
            # (INV-18).
            if future is not None and request is not None:
                reply = future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)
                if self._fits(request, reply):
                    answer, handled_by = CodexParamsTranslator.server_answer(request.kind, reply), "handler"
                else:
                    fallback = ("answer_invalid", type(reply).__name__, "")
        except Exception as exc:
            fallback = (self._reason(exc, request, future), type(exc).__name__, ExceptionOrigin.describe(exc))
        finally:
            # The handler call never outlives its request: it leaves the
            # pending set and is cancelled, or a call never scheduled is
            # closed.
            with self._lock:
                if future is not None:
                    future.cancel()
                    self._pending.discard(future)
            if future is None and asyncio.iscoroutine(coroutine):
                coroutine.close()
        # A misfit is logged by kind and type only, never by its text,
        # and then answered with the fixed default (INV-8, INV-10).
        # Codex chooses the method and the ids, so each is logged as
        # one bounded token; routing used the raw values (S4 R-9).
        limit = CODEX_HOST_LOG_TOKEN_MAX_CHARS
        if fallback is not None:
            reason, error_type, origin = fallback
            logger.warning("codex_host_server_request_fallback method=%s thread_id=%s reason=%s error_type=%s origin=%s", LogToken.of(method, limit), LogToken.of(thread_id, limit), reason, error_type, origin)
        if answer is None:
            answer = self._unregistered() if handled_by == "tool" else CodexParamsTranslator.default_answer(method)
        logger.info("codex_host_server_request method=%s thread_id=%s turn_id=%s item_id=%s handled_by=%s answer=%s", LogToken.of(method, limit), LogToken.of(thread_id, limit), LogToken.of(turn_id, limit), LogToken.of(item_id, limit), handled_by, self._label(answer))
        return answer

    def _schedule(self, coroutine: Coroutine[Any, Any, CodexServerAnswer]) -> Future[CodexServerAnswer]:
        # Runs under the lock: the handler call is scheduled on the
        # host's loop and held as pending, so close can cancel it
        # (hardening INV-17, INV-21). A loop that refuses it raises
        # before the call is held, and handle's finally closes it.
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        self._pending.add(future)
        return future

    @staticmethod
    def _ids(params: Mapping[str, Any] | None) -> tuple[str, str, str]:
        # The request's thread, turn and item ids, each "" when Codex
        # sent none or sent something that is not text.
        values = params if isinstance(params, Mapping) else {}
        thread_id, turn_id, item_id = (values.get(key) for key in ("threadId", "turnId", "itemId"))
        return (
            thread_id if isinstance(thread_id, str) else "",
            turn_id if isinstance(turn_id, str) else "",
            item_id if isinstance(item_id, str) else "",
        )

    @staticmethod
    def _fits(request: CodexServerRequest, reply: object) -> bool:
        # @intent only-a-fitting-answer-is-sent
        # Hardening INV-18: an approval carries no answers, a question
        # takes accept, decline or cancel, a listed decision or a
        # refusal is required when Codex sent a list, and every answer
        # names one of the request's questions.
        if not isinstance(reply, CodexServerAnswer):
            return False
        refusals = (CodexApprovalDecision.DECLINE, CodexApprovalDecision.CANCEL)
        if request.kind is CodexServerRequestKind.USER_INPUT:
            kind_fits = reply.decision in (CodexApprovalDecision.ACCEPT, *refusals)
        else:
            kind_fits = not reply.answers
        offered = request.available_decisions
        listed = offered is None or reply.decision in refusals or reply.decision in offered
        asked = {question.question_id for question in request.questions}
        return kind_fits and listed and all(item.question_id in asked for item in reply.answers)

    def _reason(self, exc: Exception, request: CodexServerRequest | None, future: Future[CodexServerAnswer] | None) -> str:
        # Why a routed request fell back (hardening INV-8): it did not
        # read as a request, the loop was gone, the handler ran past
        # its bound, close cancelled it, or the handler failed.
        if request is None:
            return "parse_failed"
        if future is None:
            return "closing" if self._loop.is_closed() else "handler_failed"
        if isinstance(exc, TimeoutError) and not future.done():
            return "handler_timed_out"
        if isinstance(exc, CancelledError) and self._closed:
            return "closing"
        return "handler_failed"

    @staticmethod
    def _label(answer: Mapping[str, Any]) -> str:
        # A short label of what was sent, never its content (hardening
        # INV-8): a tool result by whether it succeeded, a decision or
        # an action by its value, and every other answer by its kind.
        if "success" in answer:
            return "success" if answer["success"] is True else "failure"
        if "answers" in answer:
            return "answers"
        if "permissions" in answer:
            return "no_permissions"
        if "currentTimeAt" in answer:
            return "current_time"
        value = answer.get("decision", answer.get("action"))
        return value if isinstance(value, str) else "empty"

    @staticmethod
    def _unregistered() -> dict[str, Any]:
        # The failed tool result Codex gets for a thread with no tools
        # here.
        return {"success": False, "contentItems": [{"type": "inputText", "text": CODEX_UNREGISTERED_TOOL_TEXT}]}


class CodexConnection:
    """One host's openai-codex client, its call executor, its liveness monitor and its close thread."""

    def __init__(
        self,
        config: CodexConfig,
        loop: asyncio.AbstractEventLoop,
        approval_handler: Callable[[CodexServerRequest], Awaitable[CodexServerAnswer]] | None = None,
    ) -> None:
        # The router answers the client's server requests, through the
        # developer's approval handler when the host has one (hardening
        # INV-17). The executor is the host's own, sized when it is
        # built, so no call ever uses the loop's default executor
        # (D-1). The monitor sets the death flag before it tells the
        # loop (D-27).
        self.router = CodexServerRequestRouter(loop, approval_handler)
        self.client = CodexClient(config, approval_handler=self.router.handle)
        self._loop = loop
        self._executor = ThreadPoolExecutor(max_workers=CODEX_HOST_WORKER_THREADS, thread_name_prefix="codex-host")
        self._dead = threading.Event()
        self._closing = False
        self._closed: asyncio.Future[None] | None = None
        self._tasks: set[asyncio.Future[Any]] = set()
        self._starting: set[str] = set()

    async def launch(self, target: str) -> InitializeResponse:
        # @intent start-and-initialize-on-host-workers
        # The process starts on a host worker, bounded by the request
        # timeout. A process that cannot start means Codex is not
        # installed at target; a stalled start is an API error (D-3).
        # Initializing the session then reports the runtime version.
        bound = CODEX_HOST_REQUEST_TIMEOUT_SECONDS
        try:
            await asyncio.wait_for(self._loop.run_in_executor(self._executor, self.client.start), bound)
        except Exception as exc:
            missing = isinstance(exc, OSError) and not isinstance(exc, TimeoutError)
            error = CodexErrorMapper.not_installed(target) if missing else CodexErrorMapper.from_exception(exc, CodexHostOperation.OPEN_HOST, CODEX_HOST_PROCESS_START, dead=False, bound_seconds=bound)
            raise error from None
        return await self.call(CodexHostOperation.OPEN_HOST, CODEX_INITIALIZE_METHOD, self.client.initialize)

    async def call(
        self,
        operation: CodexHostOperation,
        method: str,
        function: Callable[..., ResultT],
        *args: object,
        thread_id: str = "",
        cleanup: bool = False,
    ) -> ResultT:
        # @intent every-call-is-bounded-on-host-workers
        # Every app-server call runs on the host's own executor, bounded
        # by the request timeout, or by the close bound for cleanup
        # calls (D-1, D-3). Once close began only cleanup is sent, and
        # after a death nothing is (INV-6).
        if self._dead.is_set() or (self._closing and not cleanup):
            raise CodexErrorMapper.process_exited(operation, thread_id)
        bound = CODEX_HOST_CLOSE_INTERRUPT_SECONDS if cleanup else CODEX_HOST_REQUEST_TIMEOUT_SECONDS
        # The idempotent reads go through openai-codex's own overload
        # retry, inside the same bound; every other call is sent once
        # (hardening INV-3, D-7).
        work = partial(function, *args)
        if method in CODEX_HOST_RETRIED_METHODS:
            work = partial(retry_on_overload, work)
        # A failure is mapped and raised from None, so no openai-codex
        # text travels with it (INV-9), and each call is logged once
        # (hardening INV-7).
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(self._loop.run_in_executor(self._executor, work), bound)
        except Exception as exc:
            error = CodexErrorMapper.from_exception(exc, operation, method, dead=self._dead.is_set(), bound_seconds=bound, thread_id=thread_id)
            self._log_call(operation, method, thread_id, started, exc, error)
            raise error from None
        self._log_call(operation, method, thread_id, started)
        return result

    def raw(self, method: str, params: Mapping[str, Any] | None) -> Callable[[], Any]:
        # @intent raw-calls-that-spend-are-sent-once
        # The raw path, for the calls openai-codex has no typed method
        # for. A call that spends usage gets a single attempt; the
        # others keep the SDK's own overload retries (D-2). The lib
        # table names each response model, and the class is read from
        # openai-codex's generated models here.
        payload = dict(params) if params is not None else None
        model = getattr(v2_all, CODEX_HOST_RAW_RESPONSE_MODELS[method])
        send = partial(self.client.request_with_retry_on_overload, method, payload, response_model=model)
        return partial(send, max_attempts=CODEX_HOST_SINGLE_ATTEMPT) if method in CODEX_HOST_SPENDING_RAW_METHODS else send

    async def sandbox_status(self, operation: CodexHostOperation) -> CodexSandboxReadiness:
        # The Windows sandbox readiness, or NOT_CHECKED when this
        # runtime cannot report it, which is not a failure (D-28).
        return await self.call(operation, CODEX_SANDBOX_READINESS_METHOD, self._sandbox_status_now)

    def _sandbox_status_now(self) -> CodexSandboxReadiness:
        # @intent unknown-sandbox-readiness-is-not-checked
        # Runs on a host worker. A JSON-RPC error means the runtime does
        # not offer the readiness check, so the sandbox is not checked.
        try:
            response = self.client.request_with_retry_on_overload(CODEX_SANDBOX_READINESS_METHOD, None, response_model=WindowsSandboxReadinessResponse)
        except JsonRpcError:
            return CodexSandboxReadiness.NOT_CHECKED
        return CodexSandboxReadiness(response.status.value)

    async def start(
        self,
        operation: CodexHostOperation,
        method: str,
        function: Callable[[], ResultT],
        on_late: Callable[[ResultT], None],
        *,
        thread_id: str,
    ) -> ResultT:
        # @intent own-every-start-codex-accepts
        # A spending start runs on a host worker and is awaited through
        # a shield, bounded by the request timeout read now. If the
        # caller is cancelled or the bound elapses, the start is handed
        # over: one still queued is withdrawn, so nothing was sent, and
        # one already running reports to on_late on the loop when it
        # returns (INV-11).
        if self._dead.is_set() or self._closing:
            raise CodexErrorMapper.process_exited(operation, thread_id)
        bound = CODEX_HOST_REQUEST_TIMEOUT_SECONDS
        started = time.monotonic()
        future = self._executor.submit(function)
        try:
            result = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), bound)
        except asyncio.CancelledError:
            self._hand_over(future, on_late, thread_id)
            raise
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                self._hand_over(future, on_late, thread_id)
            error = CodexErrorMapper.from_exception(exc, operation, method, dead=self._dead.is_set(), bound_seconds=bound, thread_id=thread_id)
            self._log_call(operation, method, thread_id, started, exc, error)
            raise error from None
        # Each start is logged once, as every call is (hardening INV-7).
        self._log_call(operation, method, thread_id, started)
        return result

    @staticmethod
    def _log_call(
        operation: CodexHostOperation,
        method: str,
        thread_id: str,
        started: float,
        exc: Exception | None = None,
        error: CodexAgentError | None = None,
    ) -> None:
        # Hardening INV-7: a success at DEBUG, a failure at WARNING with
        # its code, the type of what was raised and where it was raised,
        # never its text (INV-10). The caller or Codex chose the thread
        # id, so it is logged as one bounded token (S4 R-9).
        duration_ms = int((time.monotonic() - started) * CODEX_MILLISECONDS_PER_SECOND)
        thread_token = LogToken.of(thread_id, CODEX_HOST_LOG_TOKEN_MAX_CHARS)
        if exc is None or error is None:
            logger.debug("codex_host_call operation=%s method=%s thread_id=%s duration_ms=%d", operation.value, method, thread_token, duration_ms)
            return
        logger.warning(
            "codex_host_call_failed operation=%s method=%s thread_id=%s failure_code=%s error_type=%s origin=%s duration_ms=%d",
            operation.value,
            method,
            thread_token,
            error.failure_code,
            type(exc).__name__,
            ExceptionOrigin.describe(exc),
            duration_ms,
        )

    def starting(self, thread_id: str) -> bool:
        # Whether a start on the thread outlived its caller and is still
        # in flight, which keeps the thread busy (INV-24).
        return thread_id in self._starting

    def _hand_over(self, future: Future[ResultT], on_late: Callable[[ResultT], None], thread_id: str) -> None:
        # A start still queued is withdrawn, so it is never sent; one
        # already running keeps its thread busy and posts its outcome
        # when it returns.
        if future.cancel():
            return
        self._starting.add(thread_id)
        future.add_done_callback(partial(self._post_late, on_late, thread_id))

    def _post_late(self, on_late: Callable[[ResultT], None], thread_id: str, future: Future[ResultT]) -> None:
        # Runs on the worker that finished the start, and never raises:
        # a closed loop takes no post.
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._land, on_late, thread_id, future)

    def _land(self, on_late: Callable[[ResultT], None], thread_id: str, future: Future[ResultT]) -> None:
        # Runs on the loop: the thread is free again, and a start Codex
        # accepted is adopted at once; a failed start accepted nothing.
        self._starting.discard(thread_id)
        if not future.cancelled() and future.exception() is None:
            on_late(future.result())

    async def interrupt(
        self,
        operation: CodexHostOperation,
        handle: CodexTurnHandle,
        state: _GoalOperationState | None,
        *,
        cleanup: bool = False,
        quiet: bool = False,
    ) -> None:
        # One interrupt per stop. A goal run is paused and interrupted
        # the way openai-codex cancels its own goal operations; any
        # other turn gets one turn/interrupt. A quiet interrupt ignores
        # its failure, because no caller waits on it, and it is never
        # retried (D-7).
        with suppress(*((CodexAgentError,) if quiet else ())):
            if state is not None:
                await self.call(operation, CODEX_GOAL_CANCEL_CALL, self.client.cancel_goal_operation, state, thread_id=handle.thread_id, cleanup=cleanup)
            else:
                await self.call(operation, CODEX_TURN_INTERRUPT_METHOD, self.client.turn_interrupt, handle.thread_id, handle.turn_id, thread_id=handle.thread_id, cleanup=cleanup)

    def watch_liveness(self, on_death: Callable[[], None]) -> None:
        # One daemon thread reads openai-codex's global notifications
        # until they fail, which is how the host learns the process died
        # (D-27).
        threading.Thread(target=self._monitor, args=(on_death,), name="codex-host-monitor", daemon=True).start()

    def _monitor(self, on_death: Callable[[], None]) -> None:
        # The death flag is set before the loop hears of it, so a call
        # failing at the same moment already maps to process_exited.
        with suppress(Exception):
            while True:
                self.client.next_notification()
        self._dead.set()
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(on_death)

    def is_dead(self) -> bool:
        # Whether the app-server process died while the host was open.
        return self._dead.is_set()

    def begin_close(self) -> None:
        # From now on only cleanup calls are sent (INV-7).
        self._closing = True

    def stopped(self) -> bool:
        # Close began or the process died, so nothing new may start.
        return self._closing or self._dead.is_set()

    def spawn_task(self, work: Coroutine[Any, Any, Any]) -> None:
        # Background work is kept until it ends, so it is never
        # collected.
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def reap(self) -> asyncio.Future[None]:
        # The client closes once, on its own daemon thread, so close
        # never blocks the loop; the future completes when the thread is
        # done.
        if self._closed is None:
            self._closing = True
            self._closed = self._loop.create_future()
            threading.Thread(target=self._close_client, name="codex-host-close", daemon=True).start()
        return self._closed

    def _close_client(self) -> None:
        # Runs on the close thread; a failing close is ignored, because
        # the process is being let go either way.
        with suppress(Exception):
            self.client.close()
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._mark_closed)

    def _mark_closed(self) -> None:
        # Runs on the loop once the close thread finished.
        if self._closed is not None and not self._closed.done():
            self._closed.set_result(None)

    async def close(self) -> None:
        # INV-7 steps 5 and 6: wait for the close thread at most the
        # close bound, then shut the executor down without waiting,
        # dropping anything still queued, so no worker outlives the
        # host, even when the wait is cancelled.
        try:
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(self.reap()), CODEX_HOST_CLOSE_WAIT_SECONDS)
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)


__all__ = ["CodexConnection", "CodexServerRequestRouter"]
