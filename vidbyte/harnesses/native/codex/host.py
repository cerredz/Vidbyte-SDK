"""FILE: vidbyte/harnesses/native/codex/host.py

PURPOSE: CodexHost, one Codex app-server process that many threads and turns share for one async with block: it starts threads and turns, goal runs, forks, reviews and subagent launches, returns a handle as soon as Codex accepts a turn, and answers waits, results, steering, interrupts and per-thread usage from the turns it registered.
ROLE IN CODEBASE: The main class of vidbyte/harnesses/native/codex/; the module functions in oneshot.py and the CodexHostTools toolset in vidbyte/tools/ both drive it.
ARCHITECTURE NOTE: Importing this module never loads openai-codex: __aenter__ imports connection, wire and turns, the modules that do (D-21). Each public method is one narrated main function over a flat list of leaf helpers; CodexConnection sends every call, CodexPreflight runs every check, the translators in wire.py build params and records, and CodexTurnRegistry owns every turn.
COMMON MODIFICATION PATTERNS: A new operation is one public method: guard, field rules, preflight, the calls through CodexConnection, then a record from CodexResponseTranslator. A new way a turn can end goes through CodexTurnRegistry.finish, so the first outcome still wins.
KNOWN EDGE CASES: Close wins over a turn still starting (EC-79); a start whose caller left is still owned and gets one interrupt (INV-11); a goal run registers only after its budget echo matches (INV-25); a user reviewer that Codex reports stops the operation before the thread spends (D-32); a review is read back after registration, because its first events can be dropped (D-23).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1, 8.5 and 9.2)
TESTS: tests/features/codex_host/test_codex_host_lifecycle.py, tests/features/codex_host/test_codex_host_threads.py, tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_review_goals.py, tests/features/codex_host/test_codex_host_failures.py
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Coroutine, Sequence
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, Any, cast

from vidbyte.agents.codex.tools import CodexToolBridge, CodexToolTranslator
from vidbyte.harnesses.native.codex.errors import GOAL_START_CALL, CodexErrorMapper
from vidbyte.harnesses.native.codex.preflight import CodexPreflight
from vidbyte.lib.constants.codex import (
    CODEX_GOAL_SET_METHOD,
    CODEX_HOST_BINARY_NAME,
    CODEX_HOST_EXPERIMENTAL_API_TEXT,
    CODEX_HOST_MIN_LIVE_TURNS,
    CODEX_RATE_LIMITS_READ_METHOD,
    CODEX_REVIEW_START_METHOD,
)
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexRunInput,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexGoal,
    CodexModelInfo,
    CodexRateLimits,
    CodexReadiness,
    CodexReviewTarget,
    CodexSpawnRequest,
    CodexThreadInfo,
    CodexThreadPage,
    CodexThreadUsage,
    CodexTurnHandle,
    CodexTurnSnapshot,
)
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexReviewDelivery,
    CodexSortDirection,
    CodexThreadSortKey,
    CodexThreadSourceKind,
    CodexTurnStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from types import TracebackType

    from openai_codex._goal import _GoalOperationState
    from openai_codex.generated.v2_all import (
        ReviewStartResponse,
        Turn,
        TurnStartResponse,
    )
    from openai_codex.models import Notification

    from vidbyte.harnesses.native.codex.connection import CodexConnection
    from vidbyte.harnesses.native.codex.turns import (
        CodexGoalTurn,
        CodexLiveTurn,
        CodexTurnRegistry,
    )
    from vidbyte.harnesses.native.codex.wire import (
        CodexParamsTranslator,
        CodexResponseTranslator,
    )

NOT_OPEN_MESSAGE = "CodexHost is not open; use it inside 'async with CodexHost(...) as host'."
REOPEN_MESSAGE = "A CodexHost opens once; open a new CodexHost instead."
OTHER_LOOP_MESSAGE = "CodexHost was opened on another event loop; call it from that loop."
UNKNOWN_HANDLE_MESSAGE = "This host registered no turn with that handle."
STEER_FINISHED_MESSAGE = "The turn already ended, so it cannot be steered; continue the thread instead."
NEVER_RAN_MESSAGE = "This host never ran a turn on the thread."
NO_FORK_POINT_MESSAGE = "The thread has no completed turn to fork through at from_turn_id."
BUDGET_ECHO_MESSAGE = "Codex did not keep the goal token budget it was sent."
BAD_TIMEOUT_MESSAGE = "wait_codex_turn timeout_seconds must be None or a finite number above 0."
LAUNCH_PROMPTS_MESSAGE = "launch_codex_subagents needs a non-empty sequence of prompts, not one string."
LAUNCH_LIMIT_MESSAGE = "launch_codex_subagents limit must be None or an int of at least 1."
# The request a review turn is registered with: Vidbyte sets no limits on it.
REVIEW_REQUEST = CodexSpawnRequest()


class CodexHost:
    """One Codex app-server process shared by many threads and turns, open for one async with block."""

    def __init__(self, settings: CodexClientSettings | None = None) -> None:
        # Nothing starts here; the host opens once, in __aenter__ (INV-2).
        # The connection, translators, registry and preflight exist only
        # once the host opened.
        self._settings = settings or CodexClientSettings()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._opened = False
        self._connected = False
        self._closing = False
        self._version = ""
        self._tasks: set[asyncio.Future[Any]] = set()
        self._connection: CodexConnection
        self._params: CodexParamsTranslator
        self._responses: CodexResponseTranslator
        self._registry: CodexTurnRegistry
        self._preflight: CodexPreflight

    async def __aenter__(self) -> CodexHost:
        # @intent open-once-and-close-what-a-failed-open-started
        # A host opens once, on the loop that enters it. The loop is claimed
        # before the first await, so a second or concurrent entry is refused
        # (INV-2). A failed open closes the client it started (INV-5).
        if self._loop is not None:
            raise ConfigurationError(REOPEN_MESSAGE)
        self._loop = asyncio.get_running_loop()
        try:
            await self._open()
        except BaseException:
            self._closing = True
            if self._connected:
                await self._connection.close()
            raise
        self._opened = True
        return self

    async def _open(self) -> None:
        # The SDK modules load only now, so importing CodexHost never needs
        # openai-codex; a missing SDK means the Python extra is missing.
        try:
            from vidbyte.harnesses.native.codex.connection import CodexConnection
            from vidbyte.harnesses.native.codex.turns import CodexTurnRegistry
            from vidbyte.harnesses.native.codex.wire import (
                CodexParamsTranslator,
                CodexResponseTranslator,
            )
        except ImportError:
            raise CodexErrorMapper.missing_sdk() from None
        # Resolve the binary with shutil.which, unless a launch override
        # names the whole command, which is passed through as given (D-4).
        settings = self._settings
        override = settings.launch_args_override
        name = settings.codex_bin or CODEX_HOST_BINARY_NAME
        binary = "" if override else shutil.which(name)
        if binary is None:
            raise CodexErrorMapper.not_installed(name)
        target = next(iter(override)) if override else binary
        # Build the host's parts, start the process and refuse a runtime
        # older than the minimum version (INV-4).
        loop = asyncio.get_running_loop()
        self._params = CodexParamsTranslator(settings)
        self._responses = CodexResponseTranslator()
        self._registry = CodexTurnRegistry(loop)
        self._connection = CodexConnection(self._params.client_config(binary), loop)
        self._connected = True
        self._preflight = CodexPreflight(self._connection, self._params, self._responses, self._registry)
        found, supported = self._responses.version(await self._connection.launch(target))
        if not supported:
            raise CodexErrorMapper.version_unsupported(found)
        self._version = found
        # Watch the process from now on, so a death ends every turn (D-27).
        self._connection.watch_liveness(self._on_death)

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        # @intent close-in-the-order-that-loses-nothing
        # Close runs once, in the INV-7 order. From here on only cleanup
        # calls are sent.
        if not self._connected or self._closing:
            return
        self._closing = True
        connection = self._connection
        connection.begin_close()
        # Cancel the running tool calls, then end every running turn as
        # exited, so nobody waits on a turn that can no longer report.
        ended = self._end_running_turns()
        # Unless the process already died, send each of those turns one
        # interrupt, all at once, each bounded by the close bound.
        if ended and not connection.is_dead():
            stops = [
                asyncio.ensure_future(connection.interrupt(CodexHostOperation.INTERRUPT_CODEX_TURN, turn.handle, turn.state, cleanup=True, quiet=True))
                for turn in ended
            ]
            done, _ = await asyncio.wait(stops)
            for stop in done:
                stop.result()
        # Close each goal run's stream in openai-codex's order, then close
        # the client on its own thread and shut the executor down.
        for turn in ended:
            turn.close_goal_stream(connection.client)
        await connection.close()

    async def check_codex_ready(self) -> CodexReadiness:
        # Read the account and, on Windows, the sandbox readiness; every
        # problem found is reported in the result, never raised (AC-22).
        operation = CodexHostOperation.CHECK_CODEX_READY
        self._guard(operation, talks=True)
        connection = self._connection
        account = await connection.call(operation, "account/read", connection.client.account_read)
        sandbox = await self._preflight.sandbox_status(operation)
        return self._responses.readiness(self._version, account, sandbox)

    async def get_codex_rate_limits(self) -> CodexRateLimits:
        # One read of the account's usage windows, with the SDK's retries.
        operation = CodexHostOperation.GET_CODEX_RATE_LIMITS
        self._guard(operation, talks=True)
        connection = self._connection
        limits = await connection.call(operation, CODEX_RATE_LIMITS_READ_METHOD, connection.raw(CODEX_RATE_LIMITS_READ_METHOD, None))
        return self._responses.rate_limits(limits)

    async def list_codex_models(self, include_hidden: bool = False) -> tuple[CodexModelInfo, ...]:
        # Every page of the model list, hidden models only on request.
        operation = CodexHostOperation.LIST_CODEX_MODELS
        self._guard(operation, talks=True)
        return await self._preflight.models(operation, include_hidden)

    async def spawn_codex_thread(self, request: CodexSpawnRequest) -> CodexTurnHandle:
        # @intent check-everything-before-the-first-spending-call
        # Start a new thread and its first turn or goal run, and return as
        # soon as Codex accepted it.
        operation = CodexHostOperation.SPAWN_CODEX_THREAD
        self._guard(operation, talks=True)
        # Build the input and the tools first, so a bad prompt or tool
        # fails before anything is sent.
        items = [] if request.goal is not None else self._params.input_items(request.prompt)
        bridge = self._tool_bridge(request)
        # Check the account, usage, sandbox and models before spending.
        await self._preflight.run(operation, request)
        # Start the thread with its tools, and stop if its approvals would
        # go to a person nothing here answers.
        thread_id, pricing = await self._open_thread(operation, request, bridge)
        # Start the goal run or the turn, then watch it until it ends.
        if request.goal is not None:
            turn = await self._start_goal(operation, thread_id, request, request.goal, pricing)
        else:
            turn = await self._start_turn(operation, thread_id, request, items, pricing)
        return self._accept(operation, turn)

    async def continue_codex_thread(self, thread_id: str, input: str | CodexRunInput, overrides: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        # @intent continue-only-an-idle-thread-that-exists
        # Start one more turn on an existing thread, by id.
        operation = CodexHostOperation.CONTINUE_CODEX_THREAD
        self._guard(operation, talks=True)
        # Refuse fields continue cannot apply, and a bad input, first.
        request = overrides or CodexSpawnRequest()
        CodexPreflight.reject_unusable_fields(request, operation)
        items = self._params.input_items(input)
        # Reserve the thread before the first await, so a second continue
        # on it is refused rather than racing this one (INV-24).
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            # Check the account, usage, sandbox and models, then that the
            # thread exists, then resume it and check its reviewer.
            await self._preflight.run(operation, request)
            await self._preflight.require_thread(operation, thread_id)
            connection = self._connection
            resume = self._params.thread_resume(thread_id, request)
            resumed = await connection.call(operation, "thread/resume", connection.client.thread_resume, thread_id, resume, thread_id=thread_id)
            if self._responses.routes_to_user(resumed):
                raise CodexErrorMapper.reviewer_refusal(operation, thread_id)
            # Start the turn, priced as the model the thread resumed with.
            pricing = self._responses.pricing(resumed.model, resumed.model_provider, request.turn.model)
            turn = await self._start_turn(operation, thread_id, request, items, pricing)
        finally:
            self._registry.release(thread_id)
        return self._accept(operation, turn)

    async def fork_codex_thread(
        self,
        thread_id: str,
        from_turn_id: str = "",
        exclude_turns: bool = False,
        overrides: CodexSpawnRequest | None = None,
    ) -> CodexThreadInfo:
        # @intent fork-only-through-a-completed-turn
        # Copy a thread through one of its completed turns into a new
        # thread. exclude_turns only leaves the turns out of the answer;
        # the fork still holds them (D-29).
        operation = CodexHostOperation.FORK_CODEX_THREAD
        self._guard(operation, talks=True)
        request = overrides or CodexSpawnRequest()
        CodexPreflight.reject_unusable_fields(request, operation)
        # Read the thread with its turns and pick the fork point locally,
        # so a wrong point stops before thread/fork.
        source = await self._preflight.require_thread(operation, thread_id, include_turns=True)
        point = self._responses.fork_point(source, from_turn_id)
        if not point:
            raise CodexErrorMapper.error(FailureCode.CODEX_FORK_FAILED, NO_FORK_POINT_MESSAGE, operation, thread_id)
        connection = self._connection
        fork = self._params.thread_fork(thread_id, point, exclude_turns, request)
        forked = await connection.call(operation, "thread/fork", connection.client.thread_fork, thread_id, fork, thread_id=thread_id)
        # The fork inherits the parent's tools, so it shares its handler.
        fork_id = forked.thread.id
        handler = connection.router.handler_for(thread_id)
        if handler is not None:
            connection.router.register(fork_id, handler)
        if request.name:
            await connection.call(operation, "thread/name/set", connection.client.thread_set_name, fork_id, request.name, thread_id=fork_id)
        return self._responses.thread_info(forked.thread)

    async def list_codex_threads(
        self,
        cwd: str = "",
        search: str = "",
        archived: bool = False,
        source_kinds: tuple[CodexThreadSourceKind, ...] = (),
        sort: CodexThreadSortKey = CodexThreadSortKey.PROVIDER_DEFAULT,
        sort_direction: CodexSortDirection = CodexSortDirection.PROVIDER_DEFAULT,
        cursor: str = "",
    ) -> CodexThreadPage:
        # One page of stored threads; empty arguments are left out.
        operation = CodexHostOperation.LIST_CODEX_THREADS
        self._guard(operation, talks=True)
        connection = self._connection
        listing = self._params.thread_list(cwd, search, archived, source_kinds, sort, sort_direction, cursor)
        page = await connection.call(operation, "thread/list", connection.client.thread_list, listing)
        return self._responses.page(page)

    async def read_codex_thread(self, thread_id: str, include_turns: bool = False) -> CodexThreadInfo:
        # One stored thread, with its turn summaries only when asked.
        operation = CodexHostOperation.READ_CODEX_THREAD
        self._guard(operation, talks=True)
        thread = await self._preflight.require_thread(operation, thread_id, include_turns)
        return self._responses.thread_info(thread)

    async def wait_codex_turn(self, handle: CodexTurnHandle, timeout_seconds: float | None = None) -> CodexTurnSnapshot:
        # @intent waiting-never-cancels-the-turn
        # Wait for a turn this host registered to end, at most
        # timeout_seconds. The wait is shielded, so a timeout or a
        # cancelled waiter never stops the turn; a turn still running
        # comes back as a RUNNING snapshot.
        operation = CodexHostOperation.WAIT_CODEX_TURN
        self._guard(operation, talks=False)
        # A wait takes exactly the timeouts a turn does, so the spawn
        # request's own seconds rule checks it.
        try:
            CodexSpawnRequest(timeout_seconds=timeout_seconds)
        except ConfigurationError:
            raise ConfigurationError(BAD_TIMEOUT_MESSAGE) from None
        turn = self._owned(operation, handle)
        try:
            return await asyncio.wait_for(asyncio.shield(turn.ended), timeout_seconds)
        except TimeoutError:
            return turn.snapshot or self._responses.running(handle)

    async def get_codex_turn_result(self, handle: CodexTurnHandle) -> CodexTurnSnapshot:
        # The turn's snapshot now, without waiting.
        operation = CodexHostOperation.GET_CODEX_TURN_RESULT
        self._guard(operation, talks=False)
        turn = self._owned(operation, handle)
        return turn.snapshot or self._responses.running(handle)

    async def steer_codex_turn(self, handle: CodexTurnHandle, input: str | CodexRunInput) -> CodexTurnHandle:
        # Add input to a running turn. A goal run is steered on the
        # physical turn running now.
        operation = CodexHostOperation.STEER_CODEX_TURN
        self._guard(operation, talks=True)
        turn = self._owned(operation, handle)
        items = self._params.input_items(input)
        if turn.snapshot is not None:
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, STEER_FINISHED_MESSAGE, operation, handle.thread_id)
        expected = (turn.state.current_turn() if turn.state is not None else None) or handle.turn_id
        connection = self._connection
        await connection.call(operation, "turn/steer", connection.client.turn_steer, handle.thread_id, expected, items, thread_id=handle.thread_id)
        return handle

    async def interrupt_codex_turn(self, handle: CodexTurnHandle) -> None:
        # Stop a running turn with one interrupt and no stop reason (AC-16);
        # a finished turn gets nothing.
        operation = CodexHostOperation.INTERRUPT_CODEX_TURN
        self._guard(operation, talks=True)
        turn = self._owned(operation, handle)
        if turn.snapshot is not None:
            return
        turn.stop_sent = True
        await self._connection.interrupt(operation, handle, turn.state)

    async def track_codex_thread_usage(self, thread_id: str) -> CodexThreadUsage:
        # The usage of every turn this host saw end on the thread.
        operation = CodexHostOperation.TRACK_CODEX_THREAD_USAGE
        self._guard(operation, talks=False)
        usage = self._registry.usage(thread_id)
        if usage is None:
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, NEVER_RAN_MESSAGE, operation, thread_id)
        return usage

    async def launch_codex_subagents(
        self,
        prompts: Sequence[str | CodexRunInput],
        request: CodexSpawnRequest | None = None,
        limit: int | None = None,
    ) -> tuple[CodexTurnHandle, ...]:
        # @intent launch-in-order-and-stop-what-a-failure-leaves
        # Start one thread and turn per prompt, in order, after a single
        # preflight. If one fails, every turn already started gets one
        # interrupt and the error says how many there were (INV-37).
        operation = CodexHostOperation.LAUNCH_CODEX_SUBAGENTS
        self._guard(operation, talks=True)
        spawn = request or CodexSpawnRequest()
        CodexPreflight.reject_unusable_fields(spawn, operation)
        batch = self._launch_items(prompts, limit)
        bridge = self._tool_bridge(spawn)
        await self._preflight.run(operation, spawn)
        started: list[CodexLiveTurn] = []
        try:
            for items in batch:
                thread_id, pricing = await self._open_thread(operation, spawn, bridge)
                turn = await self._start_turn(operation, thread_id, spawn, items, pricing)
                self._accept(operation, turn)
                started.append(turn)
        except CodexAgentError as exc:
            if not started:
                raise
            for turn in started:
                self._stop(turn, None)
            message = f"{exc.message} {len(started)} turns were started before this failure and were interrupted."
            raise CodexAgentError(message, failure_code=exc.failure_code, operation=exc.operation, next_step=exc.next_step) from None
        return tuple(turn.handle for turn in started)

    async def start_codex_review(
        self,
        thread_id: str,
        target: CodexReviewTarget,
        delivery: CodexReviewDelivery = CodexReviewDelivery.INLINE,
    ) -> CodexTurnHandle:
        # @intent a-review-is-sent-once-and-owned
        # Start a Codex review of a thread's work. review/start spends, so
        # it is sent once, and its turn is owned even when its caller left.
        operation = CodexHostOperation.START_CODEX_REVIEW
        self._guard(operation, talks=True)
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            # Check the account, usage and sandbox; a review names no model.
            await self._preflight.run(operation, REVIEW_REQUEST, check_model=False)
            thread = await self._preflight.require_thread(operation, thread_id)
            pricing = self._responses.pricing(thread.model or "", thread.model_provider, "")
            connection = self._connection
            review_call = connection.raw(CODEX_REVIEW_START_METHOD, self._params.review(thread_id, target, delivery))
            adopt = partial(self._adopt_late_review, operation, pricing)
            response = await connection.start(operation, CODEX_REVIEW_START_METHOD, review_call, adopt, thread_id=thread_id)
        finally:
            self._registry.release(thread_id)
        # Register the review turn and read it back before returning.
        return await self._accept_review(operation, response, pricing, late=False)

    def _guard(self, operation: CodexHostOperation, *, talks: bool) -> None:
        # Every method needs an open host and the loop that opened it; a
        # call that talks to Codex also needs a live, open process (INV-6).
        if not self._opened:
            raise ConfigurationError(NOT_OPEN_MESSAGE)
        if asyncio.get_running_loop() is not self._loop:
            raise ConfigurationError(OTHER_LOOP_MESSAGE)
        if talks and (self._closing or self._connection.is_dead()):
            raise CodexErrorMapper.process_exited(operation)

    def _owned(self, operation: CodexHostOperation, handle: CodexTurnHandle) -> CodexLiveTurn:
        # A handle must name a turn this host registered (INV-23, D-33).
        turn = self._registry.get(handle)
        if turn is None:
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, UNKNOWN_HANDLE_MESSAGE, operation)
        return turn

    def _stopped(self) -> bool:
        # Close began or the process died, so nothing new may start.
        return self._closing or self._connection.is_dead()

    def _tool_bridge(self, request: CodexSpawnRequest) -> CodexToolBridge | None:
        # @intent tools-are-checked-before-any-call
        # Dynamic tools need the experimental API and names Codex accepts;
        # both are checked before anything is sent (INV-29).
        if not request.tools:
            return None
        if not self._settings.experimental_api:
            raise ConfigurationError(CODEX_HOST_EXPERIMENTAL_API_TEXT)
        catalog = Tools(request.tools)
        CodexToolTranslator.validate_names(catalog)
        return CodexToolBridge(catalog, request.tool_permission_policy)

    def _launch_items(self, prompts: Sequence[str | CodexRunInput], limit: int | None) -> list[list[dict[str, Any]]]:
        # The prompts are a non-empty sequence within the limit, and each
        # becomes its own thread's input.
        if isinstance(prompts, str) or not prompts:
            raise ConfigurationError(LAUNCH_PROMPTS_MESSAGE)
        if limit is not None and (type(limit) is not int or limit < CODEX_HOST_MIN_LIVE_TURNS):
            raise ConfigurationError(LAUNCH_LIMIT_MESSAGE)
        if limit is not None and len(prompts) > limit:
            raise ConfigurationError(f"launch_codex_subagents got {len(prompts)} prompts, over its limit of {limit}.")
        return [self._params.input_items(prompt) for prompt in prompts]

    async def _open_thread(self, operation: CodexHostOperation, request: CodexSpawnRequest, bridge: CodexToolBridge | None) -> tuple[str, CodexAgentSettings]:
        # @intent check-the-reviewer-before-the-thread-spends
        # Start the thread with its dynamic tools. A user reviewer Codex
        # reports stops here, naming the thread, before any name, turn or
        # goal is sent (D-32). The pricing names the model Codex resolved
        # and its provider (D-19).
        connection = self._connection
        dynamic_tools = bridge.dynamic_tools if bridge is not None else ()
        started = await connection.call(operation, "thread/start", connection.client.thread_start, self._params.thread_start(request, dynamic_tools))
        thread_id = started.thread.id
        if self._responses.routes_to_user(started):
            raise CodexErrorMapper.reviewer_refusal(operation, thread_id)
        if bridge is not None:
            connection.router.register(thread_id, bridge.handler(asyncio.get_running_loop(), connection.router.handle))
        if request.name:
            await connection.call(operation, "thread/name/set", connection.client.thread_set_name, thread_id, request.name, thread_id=thread_id)
        return thread_id, self._responses.pricing(started.model, started.model_provider, request.turn.model)

    async def _start_turn(
        self,
        operation: CodexHostOperation,
        thread_id: str,
        request: CodexSpawnRequest,
        items: list[dict[str, Any]],
        pricing: CodexAgentSettings,
    ) -> CodexLiveTurn:
        # @intent own-the-turn-even-when-its-caller-left
        # turn/start spends, so it is sent once. If its caller leaves first,
        # the turn is still adopted when Codex accepts it (INV-11).
        connection = self._connection
        start = partial(connection.client.turn_start, thread_id, items, self._params.turn_start(thread_id, request))
        adopt = partial(self._adopt_late_turn, thread_id, request, pricing)
        response = await connection.start(operation, "turn/start", start, adopt, thread_id=thread_id)
        return self._registry.track(CodexTurnHandle(thread_id=thread_id, turn_id=response.turn.id), request, pricing)

    async def _start_goal(
        self,
        operation: CodexHostOperation,
        thread_id: str,
        request: CodexSpawnRequest,
        goal: CodexGoal,
        pricing: CodexAgentSettings,
    ) -> CodexLiveTurn:
        # @intent a-goal-run-registers-only-after-its-budget-holds
        # openai-codex starts the goal; its token budget is then set on its
        # own, once, and must come back unchanged. Any failure before the
        # run is registered cancels it and releases its stream (INV-25).
        connection = self._connection
        start = partial(connection.client.start_goal_operation, thread_id, goal.objective)
        adopt = partial(self._adopt_late_goal, thread_id, request, pricing)
        state, turn_id = await connection.start(operation, GOAL_START_CALL, start, adopt, thread_id=thread_id)
        try:
            if goal.token_budget is not None and not self._stopped():
                budget_call = connection.raw(CODEX_GOAL_SET_METHOD, self._params.goal_budget(thread_id, goal.token_budget))
                echoed = await connection.call(operation, CODEX_GOAL_SET_METHOD, budget_call, thread_id=thread_id)
                if echoed.goal.token_budget != goal.token_budget:
                    raise CodexErrorMapper.error(FailureCode.CODEX_PROTOCOL_MISMATCH, BUDGET_ECHO_MESSAGE, operation, thread_id)
        except BaseException:
            with suppress(CodexAgentError):
                await connection.call(operation, "cancel_goal_operation", connection.client.cancel_goal_operation, state, thread_id=thread_id, cleanup=True)
            state.finish()
            connection.client.unregister_goal_operation(state)
            raise
        return self._registry.track_goal(CodexTurnHandle(thread_id=thread_id, turn_id=turn_id), request, pricing, state)

    def _accept(self, operation: CodexHostOperation, turn: CodexLiveTurn) -> CodexTurnHandle:
        # @intent close-wins-over-a-starting-turn
        # A turn accepted after close began or the process died ends as
        # exited, and its caller gets process_exited naming the thread
        # (EC-79). Otherwise one watcher and the turn's timer start.
        client = self._connection.client
        if self._stopped():
            self._registry.finish(turn, self._responses.exited(turn.handle))
            if turn.state is None:
                client.unregister_turn_notifications(turn.handle.turn_id)
            turn.close_goal_stream(client)
            raise CodexErrorMapper.process_exited(operation, turn.handle.thread_id)
        turn.watch(client, self._on_turn_event, self._stop)
        return turn.handle

    def _adopt_late_turn(self, thread_id: str, request: CodexSpawnRequest, pricing: CodexAgentSettings, response: TurnStartResponse) -> None:
        # @intent a-late-turn-is-owned-then-stopped
        # Runs on the loop when turn/start returns after its caller left.
        # The turn is registered, so a get finds it, and stopped with one
        # interrupt that carries no stop reason (D-35); close wins (EC-79).
        turn = self._registry.track(CodexTurnHandle(thread_id=thread_id, turn_id=response.turn.id), request, pricing)
        if self._stopped():
            self._connection.client.unregister_turn_notifications(turn.handle.turn_id)
            self._registry.finish(turn, self._responses.exited(turn.handle))
            return
        turn.watch(self._connection.client, self._on_turn_event, self._stop)
        self._stop(turn, None)

    def _adopt_late_goal(
        self,
        thread_id: str,
        request: CodexSpawnRequest,
        pricing: CodexAgentSettings,
        started: tuple[_GoalOperationState, str],
    ) -> None:
        # @intent a-late-goal-run-is-owned-then-stopped
        # The goal-run twin of _adopt_late_turn: registered, then stopped
        # with one cancel, or ended as exited when close came first.
        state, turn_id = started
        turn = self._registry.track_goal(CodexTurnHandle(thread_id=thread_id, turn_id=turn_id), request, pricing, state)
        if self._stopped():
            self._registry.finish(turn, self._responses.exited(turn.handle))
            turn.close_goal_stream(self._connection.client)
            return
        turn.watch(self._connection.client, self._on_turn_event, self._stop)
        self._stop(turn, None)

    def _adopt_late_review(self, operation: CodexHostOperation, pricing: CodexAgentSettings, response: ReviewStartResponse) -> None:
        # @intent a-late-review-is-owned-then-stopped
        # A review accepted after its caller left is registered and read
        # back like any other, then stopped with one interrupt.
        self._spawn_task(self._accept_review(operation, response, pricing, late=True))

    async def _accept_review(self, operation: CodexHostOperation, response: ReviewStartResponse, pricing: CodexAgentSettings, *, late: bool) -> CodexTurnHandle:
        # @intent register-a-review-then-read-it-back
        # Register the review turn right away, then read its thread back,
        # because openai-codex drops a review turn's events that arrive
        # before registration (D-23).
        connection = self._connection
        client = connection.client
        handle = CodexTurnHandle(thread_id=response.review_thread_id, turn_id=response.turn.id)
        client.register_turn_notifications(handle.turn_id)
        turn = self._registry.track(handle, REVIEW_REQUEST, pricing, review=True)
        stored = None if self._stopped() else await self._read_back(operation, handle)
        # Close wins: the turn ends as exited and nothing more is sent.
        if self._stopped():
            client.unregister_turn_notifications(handle.turn_id)
            self._registry.finish(turn, self._responses.exited(handle))
            if late:
                return handle
            raise CodexErrorMapper.process_exited(operation, handle.thread_id)
        # A review that already ended is built from what was read back.
        if stored is not None and stored.status.value != CodexTurnStatus.RUNNING.value:
            client.unregister_turn_notifications(handle.turn_id)
            self._registry.finish(turn, self._responses.turn_snapshot(turn, stored.items, stored))
            return handle
        # Otherwise watch it; a late review also gets its one interrupt.
        turn.watch(client, self._on_turn_event, self._stop)
        if late:
            self._stop(turn, None)
        return handle

    async def _read_back(self, operation: CodexHostOperation, handle: CodexTurnHandle) -> Turn | None:
        # The review turn as Codex stored it, or None when the read fails
        # or the turn is not stored yet.
        connection = self._connection
        with suppress(CodexAgentError):
            stored = await connection.call(operation, "thread/read", connection.client.thread_read, handle.thread_id, True, thread_id=handle.thread_id)
            return self._responses.stored_turn(stored.thread, handle.turn_id)
        return None

    async def _complete_review(self, turn: CodexLiveTurn) -> None:
        # @intent build-a-review-from-its-stored-items
        # When a review turn completes, its result comes from the review
        # thread read back with its turns, since its last item can be lost;
        # the items seen live are used when the read fails (D-23).
        stored = await self._read_back(CodexHostOperation.START_CODEX_REVIEW, turn.handle)
        items = stored.items if stored is not None else turn.items
        self._registry.finish(turn, self._responses.turn_snapshot(turn, items, turn.completed))

    def _on_turn_event(self, turn: CodexLiveTurn, note: Notification) -> None:
        # @intent the-first-outcome-ends-a-turn
        # Runs on the loop for each notification a watcher posts. A turn
        # that already ended ignores later events (INV-15). Passing the
        # output cap sends one interrupt (D-7).
        if turn.snapshot is not None:
            return
        ended = turn.observe(note)
        if turn.over_cap():
            self._stop(turn, FailureCode.CODEX_BUDGET_EXHAUSTED)
        if not ended:
            return
        # The end builds the snapshot: a review from its read-back, a goal
        # run by the goal table, any other turn from its completion.
        if turn.review:
            self._spawn_task(self._complete_review(turn))
        elif turn.state is not None:
            self._registry.finish(turn, self._responses.goal_snapshot(cast("CodexGoalTurn", turn)))
            turn.close_goal_stream(self._connection.client)
        else:
            self._registry.finish(turn, self._responses.turn_snapshot(turn, turn.items, turn.completed))

    def _stop(self, turn: CodexLiveTurn, reason: FailureCode | None) -> None:
        # @intent the-first-stop-wins-and-is-sent-once
        # Vidbyte's timeout, its output cap and late acceptance each stop a
        # turn with one interrupt. The first stop wins, its reason labels
        # the turn only if Codex reports it interrupted, and a failed
        # interrupt is not retried (D-7, D-35).
        if turn.stop_sent or turn.snapshot is not None or self._closing:
            return
        turn.stop_sent = True
        turn.stop_reason = reason
        self._spawn_task(self._connection.interrupt(CodexHostOperation.INTERRUPT_CODEX_TURN, turn.handle, turn.state, quiet=True))

    def _spawn_task(self, work: Coroutine[Any, Any, Any]) -> None:
        # Background work is kept until it ends, so it is never collected.
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _end_running_turns(self) -> list[CodexLiveTurn]:
        # Cancel every running tool call, release each plain turn's route
        # so its watcher ends, and end every running turn as exited
        # (INV-7 steps 1 and 2).
        connection = self._connection
        for handler in connection.router.remove_all():
            handler.close()
        ended = list(self._registry.running())
        for turn in ended:
            if turn.state is None:
                connection.client.unregister_turn_notifications(turn.handle.turn_id)
            self._registry.finish(turn, self._responses.exited(turn.handle))
        return ended

    def _on_death(self) -> None:
        # @intent a-dead-process-ends-every-running-turn
        # Runs on the loop when the liveness monitor sees the process die
        # (D-27): close steps 1 and 2 run at once, so every running turn
        # ends as exited and each goal run's stream closes, and the dead
        # process is reaped on the close thread. Close does this itself.
        if self._closing:
            return
        for turn in self._end_running_turns():
            turn.close_goal_stream(self._connection.client)
        self._connection.reap()


__all__ = ["CodexHost"]
