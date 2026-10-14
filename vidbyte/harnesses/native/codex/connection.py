"""FILE: vidbyte/harnesses/native/codex/connection.py

PURPOSE: Owns one CodexHost's openai-codex client: the host's own call executor, every bounded app-server call, the shielded spending starts and their late acceptance, the liveness monitor, the close thread, and the server-request router that answers approvals and dynamic tool calls.
ROLE IN CODEBASE: The process and transport layer of vidbyte/harnesses/native/codex/; CodexHost and CodexPreflight reach Codex only through CodexConnection.
ARCHITECTURE NOTE: "from openai_codex.client import CodexClient, CodexConfig" at module level is the test seam (section 13), so only CodexHost.__aenter__ imports this module (D-21). Every call runs on the host's own ThreadPoolExecutor, bounded by asyncio.wait_for, never on the loop or its default executor (D-1); the bounds are read from this module's namespace at call time.
COMMON MODIFICATION PATTERNS: A new app-server call goes through call() with a typed CodexClient method, or through raw() with its generated response model when openai-codex has no typed method; a raw call that spends usage is added to SPENDING_RAW_METHODS, so it is sent once (D-2).
KNOWN EDGE CASES: A spending start that outlives its caller or its bound is owned, never orphaned: a queued start is withdrawn, and a running one posts its outcome to the loop when it returns (INV-11). The router and the done-callback run on openai-codex's threads, so they never raise. Once close began or the process died, only cleanup calls are sent.
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-1 to D-3, D-18 and D-27, and 12.4 call list)
TESTS: tests/features/codex_host/test_codex_host_lifecycle.py, tests/features/codex_host/test_codex_host_failures.py, tests/features/codex_host/test_codex_host_router.py
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar

from openai_codex.client import CodexClient, CodexConfig
from openai_codex.errors import JsonRpcError
from openai_codex.generated.v2_all import (
    GetAccountRateLimitsResponse,
    ModelListResponse,
    ReviewStartResponse,
    ThreadGoalSetResponse,
    WindowsSandboxReadinessResponse,
)
from openai_codex.models import InitializeResponse
from pydantic import BaseModel

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex import (
    CODEX_ACCEPTED_APPROVAL_METHODS,
    CODEX_APPROVAL_ACCEPT_DECISION,
    CODEX_GOAL_SET_METHOD,
    CODEX_HOST_CLOSE_INTERRUPT_SECONDS,
    CODEX_HOST_CLOSE_WAIT_SECONDS,
    CODEX_HOST_REQUEST_TIMEOUT_SECONDS,
    CODEX_HOST_SINGLE_ATTEMPT,
    CODEX_HOST_WORKER_THREADS,
    CODEX_MODEL_LIST_METHOD,
    CODEX_RATE_LIMITS_READ_METHOD,
    CODEX_REVIEW_START_METHOD,
    CODEX_SANDBOX_READINESS_METHOD,
    CODEX_TOOL_CALL_METHOD,
    CODEX_UNREGISTERED_TOOL_TEXT,
)
from vidbyte.lib.enums.codex import CodexHostOperation
from vidbyte.lib.errors import CodexAgentError

if TYPE_CHECKING:
    from openai_codex._goal import _GoalOperationState

    from vidbyte.agents.codex.tools import CodexToolCallHandler
    from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

ResultT = TypeVar("ResultT")

# The generated response model of each call made through the raw path,
# which openai-codex offers no typed method for (section 12.4).
RAW_RESPONSES: Mapping[str, type[BaseModel]] = {
    CODEX_RATE_LIMITS_READ_METHOD: GetAccountRateLimitsResponse,
    CODEX_SANDBOX_READINESS_METHOD: WindowsSandboxReadinessResponse,
    CODEX_MODEL_LIST_METHOD: ModelListResponse,
    CODEX_REVIEW_START_METHOD: ReviewStartResponse,
    CODEX_GOAL_SET_METHOD: ThreadGoalSetResponse,
}
# Raw calls that spend usage, so each is sent once and never retried (D-2).
SPENDING_RAW_METHODS = frozenset({CODEX_REVIEW_START_METHOD, CODEX_GOAL_SET_METHOD})
# How a failed process start is named in the messages the mapper builds.
PROCESS_START = "the app-server start"


class CodexServerRequestRouter:
    """Answers every server request of one host's client: approvals, and tool calls by thread."""

    def __init__(self) -> None:
        # Each thread with Vidbyte tools has its own tool-call handler (D-18).
        self._handlers: dict[str, CodexToolCallHandler] = {}

    def register(self, thread_id: str, handler: CodexToolCallHandler) -> None:
        # A fork registers its parent's handler, as it inherits the tools (D-29).
        self._handlers[thread_id] = handler

    def handler_for(self, thread_id: str) -> CodexToolCallHandler | None:
        # The handler of a thread, or None when it has no Vidbyte tools.
        return self._handlers.get(thread_id)

    def remove_all(self) -> tuple[CodexToolCallHandler, ...]:
        # At close every thread's handler is removed and handed back, so
        # the host can cancel the tool calls still running (INV-7 step 1).
        handlers = tuple(self._handlers.values())
        self._handlers = {}
        return handlers

    def handle(self, method: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
        # @intent answer-every-server-request-without-raising
        # Runs on openai-codex's reader thread, so one try spans it all
        # and nothing escapes: approvals are accepted as the SDK's own
        # default handler does, a tool call goes to its thread's handler,
        # and every other request gets an empty answer (D-16, D-18).
        try:
            if method in CODEX_ACCEPTED_APPROVAL_METHODS:
                return {"decision": CODEX_APPROVAL_ACCEPT_DECISION}
            if method != CODEX_TOOL_CALL_METHOD:
                return {}
            thread_id = (params or {}).get("threadId")
            handler = self._handlers.get(thread_id) if isinstance(thread_id, str) else None
            if handler is not None:
                return handler.handle(method, params)
        except Exception:
            return self._unregistered()
        return self._unregistered()

    @staticmethod
    def _unregistered() -> dict[str, Any]:
        # The failed tool result Codex gets for a thread with no tools here.
        return {"success": False, "contentItems": [{"type": "inputText", "text": CODEX_UNREGISTERED_TOOL_TEXT}]}


class CodexConnection:
    """One host's openai-codex client, its call executor, its liveness monitor and its close thread."""

    def __init__(self, config: CodexConfig, loop: asyncio.AbstractEventLoop) -> None:
        # The router answers the client's server requests. The executor is
        # the host's own, sized when it is built, so no call ever uses the
        # loop's default executor (D-1). The monitor sets the death flag
        # before it tells the loop (D-27).
        self.router = CodexServerRequestRouter()
        self.client = CodexClient(config, approval_handler=self.router.handle)
        self._loop = loop
        self._executor = ThreadPoolExecutor(max_workers=CODEX_HOST_WORKER_THREADS, thread_name_prefix="codex-host")
        self._dead = threading.Event()
        self._closing = False
        self._closed: asyncio.Future[None] | None = None

    async def launch(self, target: str) -> InitializeResponse:
        # @intent start-and-initialize-on-host-workers
        # The process starts on a host worker, bounded by the request
        # timeout. A process that cannot start means Codex is not installed
        # at target; a stalled start is an API error (D-3). Initializing
        # the session then reports the runtime version.
        bound = CODEX_HOST_REQUEST_TIMEOUT_SECONDS
        try:
            await asyncio.wait_for(self._loop.run_in_executor(self._executor, self.client.start), bound)
        except Exception as exc:
            missing = isinstance(exc, OSError) and not isinstance(exc, TimeoutError)
            error = CodexErrorMapper.not_installed(target) if missing else CodexErrorMapper.from_exception(exc, CodexHostOperation.OPEN_HOST, PROCESS_START, dead=False, bound_seconds=bound)
            raise error from None
        return await self.call(CodexHostOperation.OPEN_HOST, "initialize", self.client.initialize)

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
        # Every app-server call runs on the host's own executor, bounded by
        # the request timeout, or by the close bound for cleanup calls
        # (D-1, D-3). Once close began only cleanup is sent, and after a
        # death nothing is (INV-6). A failure is mapped and raised from
        # None, so no openai-codex text travels with it (INV-9).
        if self._dead.is_set() or (self._closing and not cleanup):
            raise CodexErrorMapper.process_exited(operation, thread_id)
        bound = CODEX_HOST_CLOSE_INTERRUPT_SECONDS if cleanup else CODEX_HOST_REQUEST_TIMEOUT_SECONDS
        try:
            return await asyncio.wait_for(self._loop.run_in_executor(self._executor, partial(function, *args)), bound)
        except Exception as exc:
            raise CodexErrorMapper.from_exception(exc, operation, method, dead=self._dead.is_set(), bound_seconds=bound, thread_id=thread_id) from None

    def raw(self, method: str, params: Mapping[str, Any] | None) -> Callable[[], Any]:
        # @intent raw-calls-that-spend-are-sent-once
        # The raw path, for the calls openai-codex has no typed method for.
        # A call that spends usage gets a single attempt; the others keep
        # the SDK's own overload retries (D-2).
        payload = dict(params) if params is not None else None
        send = partial(self.client.request_with_retry_on_overload, method, payload, response_model=RAW_RESPONSES[method])
        return partial(send, max_attempts=CODEX_HOST_SINGLE_ATTEMPT) if method in SPENDING_RAW_METHODS else send

    async def sandbox_status(self, operation: CodexHostOperation) -> str:
        # The Windows sandbox readiness, or "" when this runtime cannot
        # report it, which is not a failure (D-28).
        return await self.call(operation, CODEX_SANDBOX_READINESS_METHOD, self._sandbox_status_now)

    def _sandbox_status_now(self) -> str:
        # @intent unknown-sandbox-readiness-is-not-checked
        # Runs on a host worker. A JSON-RPC error means the runtime does
        # not offer the readiness check, so the sandbox is not checked.
        try:
            response = self.client.request_with_retry_on_overload(CODEX_SANDBOX_READINESS_METHOD, None, response_model=WindowsSandboxReadinessResponse)
        except JsonRpcError:
            return ""
        return response.status.value

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
        # A spending start runs on a host worker and is awaited through a
        # shield, bounded by the request timeout read now. If the caller
        # is cancelled or the bound elapses, the start is handed over: one
        # still queued is withdrawn, so nothing was sent, and one already
        # running reports to on_late on the loop when it returns (INV-11).
        if self._dead.is_set() or self._closing:
            raise CodexErrorMapper.process_exited(operation, thread_id)
        bound = CODEX_HOST_REQUEST_TIMEOUT_SECONDS
        future = self._executor.submit(function)
        try:
            return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), bound)
        except asyncio.CancelledError:
            self._hand_over(future, on_late)
            raise
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                self._hand_over(future, on_late)
            raise CodexErrorMapper.from_exception(exc, operation, method, dead=self._dead.is_set(), bound_seconds=bound, thread_id=thread_id) from None

    def _hand_over(self, future: Future[ResultT], on_late: Callable[[ResultT], None]) -> None:
        # A start still queued is withdrawn, so it is never sent; one
        # already running posts its outcome when it returns.
        if future.cancel():
            return
        future.add_done_callback(partial(self._post_late, on_late))

    def _post_late(self, on_late: Callable[[ResultT], None], future: Future[ResultT]) -> None:
        # Runs on the worker that finished the start, and never raises: a
        # failed start accepted nothing, and a closed loop takes no post.
        if future.cancelled() or future.exception() is not None:
            return
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(on_late, future.result())

    async def interrupt(
        self,
        operation: CodexHostOperation,
        handle: CodexTurnHandle,
        state: _GoalOperationState | None,
        *,
        cleanup: bool = False,
        quiet: bool = False,
    ) -> None:
        # One interrupt per stop. A goal run is paused and interrupted the
        # way openai-codex cancels its own goal operations; any other turn
        # gets one turn/interrupt. A quiet interrupt ignores its failure,
        # because no caller waits on it, and it is never retried (D-7).
        with suppress(*((CodexAgentError,) if quiet else ())):
            if state is not None:
                await self.call(operation, "cancel_goal_operation", self.client.cancel_goal_operation, state, thread_id=handle.thread_id, cleanup=cleanup)
            else:
                await self.call(operation, "turn/interrupt", self.client.turn_interrupt, handle.thread_id, handle.turn_id, thread_id=handle.thread_id, cleanup=cleanup)

    def watch_liveness(self, on_death: Callable[[], None]) -> None:
        # One daemon thread reads openai-codex's global notifications until
        # they fail, which is how the host learns the process died (D-27).
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

    def reap(self) -> asyncio.Future[None]:
        # The client closes once, on its own daemon thread, so close never
        # blocks the loop; the future completes when the thread is done.
        if self._closed is None:
            self._closing = True
            self._closed = self._loop.create_future()
            threading.Thread(target=self._close_client, name="codex-host-close", daemon=True).start()
        return self._closed

    def _close_client(self) -> None:
        # Runs on the close thread; a failing close is ignored, because the
        # process is being let go either way.
        with suppress(Exception):
            self.client.close()
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._mark_closed)

    def _mark_closed(self) -> None:
        # Runs on the loop once the close thread finished.
        if self._closed is not None and not self._closed.done():
            self._closed.set_result(None)

    async def close(self) -> None:
        # INV-7 steps 5 and 6: wait for the close thread at most the close
        # bound, then shut the executor down without waiting, dropping
        # anything still queued, so no worker outlives the host.
        with suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(self.reap()), CODEX_HOST_CLOSE_WAIT_SECONDS)
        self._executor.shutdown(wait=False, cancel_futures=True)


__all__ = ["CodexConnection", "CodexServerRequestRouter"]
