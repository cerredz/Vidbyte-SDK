"""FILE: vidbyte/harnesses/native/codex/host.py

PURPOSE: CodexHost, one Codex app-server process that many threads and turns share for one async with block: it starts threads and turns, goal runs, forks, reviews and subagent launches, returns a handle as soon as Codex accepts a turn, and answers waits, results, steering, interrupts and per-thread usage from the turns it registered, which forget_codex_turns releases. It also lists, searches, reads, compacts and deletes stored threads, and gets and runs goals and skills. An optional approval_handler answers Codex's approval and user-input requests; without one they are declined.
ROLE IN CODEBASE: The main class of vidbyte/harnesses/native/codex/; the module functions in oneshot.py and the CodexHostTools toolset in vidbyte/tools/ both drive it. It inherits the twenty-five first-class functions from four mixins over CodexHostCore: CodexSettingsMethods, CodexStreamMethods, CodexThreadMethods and CodexGoalMethods (first-class D-1).
ARCHITECTURE NOTE: Importing this module never loads openai-codex: _open imports connection, wire, turns, turn_events, reviews, turn_starts and feature_wire, the modules that do or that only it builds (D-21, hardening INV-41, first-class INV-45). Each public method is one narrated main function over a flat list of leaf helpers; CodexConnection sends every call, answers server requests through its router and keeps background tasks, CodexPreflight runs every check, the translators in wire.py build params and records, CodexTurnRegistry owns every turn, and each CodexLiveTurn sends its own one stop. CodexTurnStarts starts and owns every spending turn, goal run and goal resume, CodexThreadHelpers runs the thread helpers and the fork on those same parts, CodexTurnEvents ends turns from their events, CodexReviews starts reviews, and CodexSkillFunctions runs goals and skills through the host's own public functions, typed by its CodexSkillHost Protocol so it never imports this module.
COMMON MODIFICATION PATTERNS: A new operation is one public method: guard, its input record from vidbyte/lib/dataclasses/codex_host_inputs.py, preflight, the calls through CodexConnection, then a record from CodexResponseTranslator. Its messages go in vidbyte/lib/constants/codex_host.py, never in this module. A new thread helper goes in CodexThreadHelpers and a new run wrapper in CodexSkillFunctions; its host method is the guard, then one delegation. A first-class function goes in the mixin of its family, never on this class, so the pinned method order holds (first-class INV-50). A new way a turn can end goes through CodexTurnRegistry.finish, so the first outcome still wins.
KNOWN EDGE CASES: Close wins over a turn still starting (EC-79); a start whose caller left is still owned and gets one interrupt (INV-11); a goal run registers only after its budget echo matches (INV-25). A user reviewer is refused before any request on a host without an approval_handler, and one that Codex reports stops the operation before the thread spends (D-32, hardening INV-20). A thread's tool handler is registered only once the thread started and was named, and a first turn that fails to start releases it unless that start is still in flight (hardening INV-26). Close cancels a pending approval_handler call before anything else (hardening INV-21). A review is read back after registration, because its first events can be dropped (D-23).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1, 8.5 and 9.2); docs/spec/codex-host-thread-helpers/spec.md (sections 8.5 and 12.3); docs/spec/codex-host-hardening/spec.md (sections 3, 6.1, 8.5 and 9.2); docs/spec/codex-host-first-class/spec.md (sections 8.1 D-1 and D-2, 8.5 and 12.3 row 30)
TESTS: tests/features/codex_host/test_codex_host_lifecycle.py, tests/features/codex_host/test_codex_host_threads.py, tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_review_goals.py, tests/features/codex_host/test_codex_host_failures.py, tests/features/codex_host/test_codex_host_thread_helpers.py, tests/features/codex_host/test_codex_host_goal_skills.py, tests/features/codex_host/test_codex_host_helper_lifecycle.py, tests/features/codex_host/test_codex_host_helper_surface.py, tests/features/codex_host/test_codex_host_approvals.py, tests/features/codex_host/test_codex_host_resilience.py, tests/features/codex_host/test_codex_host_function_rows.py, tests/features/codex_host/test_codex_host_feature_structure.py
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

from vidbyte.agents.codex.tools import CodexToolBridge, CodexToolTranslator
from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.harnesses.native.codex.goal_methods import CodexGoalMethods
from vidbyte.harnesses.native.codex.preflight import CodexPreflight
from vidbyte.harnesses.native.codex.settings_methods import CodexSettingsMethods
from vidbyte.harnesses.native.codex.skill_functions import CodexSkillFunctions
from vidbyte.harnesses.native.codex.stream_methods import CodexStreamMethods
from vidbyte.harnesses.native.codex.thread_helpers import CodexThreadHelpers
from vidbyte.harnesses.native.codex.thread_methods import CodexThreadMethods
from vidbyte.lib.constants.codex import (
    CODEX_ACCOUNT_READ_METHOD,
    CODEX_HOST_BINARY_NAME,
    CODEX_HOST_EXPERIMENTAL_API_TEXT,
    CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT,
    CODEX_OPENAI_DOCS_SKILL_NAME,
    CODEX_RATE_LIMITS_READ_METHOD,
    CODEX_SKILLS_LIST_METHOD,
    CODEX_THREAD_LIST_METHOD,
    CODEX_THREAD_NAME_SET_METHOD,
    CODEX_THREAD_RESUME_METHOD,
    CODEX_THREAD_START_METHOD,
    CODEX_TURN_STEER_METHOD,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_FORK_EXPERIMENTAL_FIELDS,
    CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE,
    CODEX_HOST_LAUNCH_INTERRUPTED_SENTENCE,
    CODEX_HOST_NEVER_RAN_MESSAGE,
    CODEX_HOST_REOPEN_MESSAGE,
    CODEX_HOST_STEER_FINISHED_MESSAGE,
    CODEX_HOST_STEER_STOPPING_MESSAGE,
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
    CodexServerAnswer,
    CodexServerRequest,
    CodexSkillInfo,
    CodexSpawnRequest,
    CodexThreadGoal,
    CodexThreadInfo,
    CodexThreadPage,
    CodexThreadSummary,
    CodexThreadUsage,
    CodexTurnHandle,
    CodexTurnPage,
    CodexTurnSnapshot,
)
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexContinueRequest,
    CodexForkRequest,
    CodexGoalRunRequest,
    CodexHostSetup,
    CodexModelListRequest,
    CodexReviewRequest,
    CodexSkillListRequest,
    CodexSkillRunRequest,
    CodexSubagentLaunchRequest,
    CodexThreadListing,
    CodexThreadListRequest,
    CodexThreadReadRequest,
    CodexThreadRef,
    CodexTurnListRequest,
    CodexTurnRef,
    CodexTurnSteerRequest,
    CodexTurnWaitRequest,
)
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexReviewDelivery,
    CodexSortDirection,
    CodexThreadSortKey,
    CodexThreadSourceKind,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from types import TracebackType

    from vidbyte.harnesses.native.codex.turns import CodexLiveTurn



class CodexHost(CodexSettingsMethods, CodexStreamMethods, CodexThreadMethods, CodexGoalMethods):
    """One Codex app-server process shared by many threads and turns, open for one async with block.

    ``approval_handler`` is an async function that takes a
    CodexServerRequest and returns a CodexServerAnswer. Codex's command,
    file-change and user-input requests go to it, on the host's loop;
    without one they are declined. openai-codex reads every response on
    one thread that waits for the handler, so never call this same host
    from the handler (both sides stall until the 300-second tool-call
    bound, then the request is declined), and keep the handler quick,
    because every other turn on the host pauses while it runs; give
    approval-gated threads their own host.
    """

    def __init__(self, settings: CodexClientSettings | None = None, *, approval_handler: Callable[[CodexServerRequest], Awaitable[CodexServerAnswer]] | None = None) -> None:
        # Nothing starts here; the host opens once, in __aenter__
        # (INV-2). The settings and the handler are checked first, so a
        # bad one starts nothing (hardening INV-19). The connection,
        # translators, registry, preflight, _threads (thread helpers),
        # _events (turn events), _reviews, _skills (goal and skill
        # runs), _starts (turn starts) and the two feature translators
        # exist only once the host opened; CodexHostCore declares them.
        setup = CodexHostSetup(settings=settings, approval_handler=approval_handler)
        self._settings = setup.settings or CodexClientSettings()
        self._approval_handler = setup.approval_handler
        self._loop: asyncio.AbstractEventLoop | None = None
        self._opened = False
        self._connected = False
        self._closing = False
        self._version = ""

    async def __aenter__(self) -> CodexHost:
        # @intent open-once-and-close-what-a-failed-open-started
        # A host opens once, on the loop that enters it. The loop is
        # claimed before the first await, so a second or concurrent
        # entry is refused (INV-2). A failed open closes the client it
        # started (INV-5).
        if self._loop is not None:
            raise ConfigurationError(CODEX_HOST_REOPEN_MESSAGE)
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
        # The SDK modules load only now, so importing CodexHost never
        # needs openai-codex; a missing SDK means the Python extra is
        # missing.
        try:
            from vidbyte.harnesses.native.codex.connection import CodexConnection
            from vidbyte.harnesses.native.codex.feature_wire import (
                CodexFeatureParamsTranslator,
                CodexFeatureResponseTranslator,
            )
            from vidbyte.harnesses.native.codex.reviews import CodexReviews
            from vidbyte.harnesses.native.codex.turn_events import CodexTurnEvents
            from vidbyte.harnesses.native.codex.turn_starts import CodexTurnStarts
            from vidbyte.harnesses.native.codex.turns import CodexTurnRegistry
            from vidbyte.harnesses.native.codex.wire import (
                CodexParamsTranslator,
                CodexResponseTranslator,
            )
        except ImportError:
            raise CodexErrorMapper.missing_sdk() from None
        # Resolve the binary with shutil.which, unless a launch override
        # names the whole command, which is passed through as given
        # (D-4).
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
        handler = self._approval_handler
        self._connection = CodexConnection(self._params.client_config(binary), loop, handler)
        self._connected = True
        self._preflight = CodexPreflight(self._connection, self._params, self._responses, self._registry, approvals_answered=handler is not None, experimental_api=settings.experimental_api)
        # The thread helpers, the turn events, the reviews, the turn
        # starts and the feature translators share the host's parts;
        # the run wrappers go through the host's own public functions.
        self._threads = CodexThreadHelpers(self._connection, self._params, self._responses, self._preflight, self._registry)
        self._events = CodexTurnEvents(self._connection, self._responses, self._registry, self._threads)
        self._reviews = CodexReviews(self._connection, self._params, self._responses, self._preflight, self._registry, self._threads, self._events)
        self._skills = CodexSkillFunctions(self)
        self._starts = CodexTurnStarts(self._connection, self._params, self._responses, self._registry, self._events)
        self._feature_params = CodexFeatureParamsTranslator()
        self._feature_responses = CodexFeatureResponseTranslator(self._responses)
        found, supported = self._responses.version(await self._connection.launch(target))
        if not supported:
            raise CodexErrorMapper.version_unsupported(found)
        self._version = found
        # Watch the process from now on, so a death ends every turn
        # (D-27).
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
        try:
            # Unless the process already died, send each of those turns
            # one interrupt, all at once, each bounded by the close
            # bound.
            if ended and not connection.is_dead():
                stops = [
                    asyncio.ensure_future(connection.interrupt(CodexHostOperation.INTERRUPT_CODEX_TURN, turn.handle, turn.state, cleanup=True, quiet=True))
                    for turn in ended
                ]
                done, _ = await asyncio.wait(stops)
                for stop in done:
                    stop.result()
        finally:
            # Close each goal run's stream in openai-codex's order, then
            # close the client on its own thread and shut the executor
            # down, even when this close was cancelled, so no process
            # leaks.
            for turn in ended:
                turn.close_goal_stream(connection.client)
            await connection.close()

    async def check_codex_ready(self) -> CodexReadiness:
        # Read the account, the usage allowance through the preflight's
        # own read and, on Windows, the sandbox readiness; every problem
        # found is reported, never raised (AC-22, hardening INV-24).
        operation = CodexHostOperation.CHECK_CODEX_READY
        self._guard(operation, talks=True)
        connection = self._connection
        account = await connection.call(operation, CODEX_ACCOUNT_READ_METHOD, connection.client.account_read)
        usage = await self._preflight.usage_problem(operation)
        sandbox = await self._preflight.sandbox_status(operation)
        return self._responses.readiness(self._version, account, usage, sandbox)

    async def get_codex_rate_limits(self) -> CodexRateLimits:
        # One read of the account's usage windows, with the SDK's
        # retries.
        operation = CodexHostOperation.GET_CODEX_RATE_LIMITS
        self._guard(operation, talks=True)
        connection = self._connection
        limits = await connection.call(operation, CODEX_RATE_LIMITS_READ_METHOD, connection.raw(CODEX_RATE_LIMITS_READ_METHOD, None))
        return self._responses.rate_limits(limits)

    async def list_codex_models(self, include_hidden: bool = False) -> tuple[CodexModelInfo, ...]:
        # Every page of the model list, hidden models only on request.
        operation = CodexHostOperation.LIST_CODEX_MODELS
        self._guard(operation, talks=True)
        listing = CodexModelListRequest(include_hidden=include_hidden)
        return await self._preflight.models(operation, listing.include_hidden)

    async def spawn_codex_thread(self, request: CodexSpawnRequest) -> CodexTurnHandle:
        """Start a new thread and its first turn or goal run, and return its handle once Codex accepts it.

        Every spawn runs the preflight first: fresh account and usage
        reads, the Windows sandbox read, and the cached model list, read
        again only when it misses a model or tier the request names.
        """
        # @intent check-everything-before-the-first-spending-call
        # Start a new thread and its first turn or goal run, and return
        # as soon as Codex accepted it.
        operation = CodexHostOperation.SPAWN_CODEX_THREAD
        self._guard(operation, talks=True)
        # The request record checked its own fields when it was built,
        # so only its type is left to check here.
        RecordFieldConverter.require_instance(request, "spawn_codex_thread request", CodexSpawnRequest)
        # Build the input, the tools and the answer schema first, so a
        # bad prompt, tool or schema fails before anything is sent.
        items = [] if request.goal is not None else self._params.input_items(request.prompt)
        bridge = self._tool_bridge(request)
        self._params.reject_unusable_schema(request)
        # Check the account, usage, sandbox and models before spending.
        await self._preflight.run(operation, request)
        # Start the thread with its tools, and stop if its approvals
        # would go to a person nothing here answers.
        thread_id, pricing = await self._open_thread(operation, request, bridge)
        # Start the goal run or the turn, then watch it until it ends. A
        # failed start releases the thread's tools (hardening INV-26).
        try:
            if request.goal is not None:
                turn = await self._starts.start_goal(operation, thread_id, request, request.goal, pricing)
            else:
                turn = await self._starts.start_turn(operation, thread_id, request, items, pricing)
        except BaseException:
            self._starts.release_tools(thread_id)
            raise
        return self._starts.accept(operation, turn)

    async def continue_codex_thread(self, thread_id: str, input: str | CodexRunInput, overrides: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        # @intent continue-only-an-idle-thread-that-exists
        # Start one more turn on an existing thread, by id.
        operation = CodexHostOperation.CONTINUE_CODEX_THREAD
        self._guard(operation, talks=True)
        # Check the thread id, the overrides continue can apply and the
        # input, then the answer schema, so a bad argument sends
        # nothing.
        continued = CodexContinueRequest(thread_id=thread_id, run_input=input, overrides=overrides or CodexSpawnRequest())
        request = continued.overrides
        items = self._params.input_items(continued.run_input)
        self._params.reject_unusable_schema(request)
        # Reserve the thread before the first await, so a second
        # continue on it is refused rather than racing this one
        # (INV-24).
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            # Check the reviewer, account, usage, sandbox and models,
            # then that the thread exists. A thread not loaded here is
            # resumed only when no unfinished goal could continue
            # (hardening INV-27); then check its reviewer.
            await self._preflight.run(operation, request)
            thread = await self._preflight.require_thread(operation, thread_id)
            await self._threads.refuse_unfinished_goal(operation, thread)
            connection = self._connection
            resume = self._params.thread_resume(thread_id, request)
            resumed = await connection.call(operation, CODEX_THREAD_RESUME_METHOD, connection.client.thread_resume, thread_id, resume, thread_id=thread_id)
            self._preflight.reject_routed_reviewer(operation, thread_id, self._responses.routes_to_user(resumed))
            # Start the turn, priced as the model the thread resumed
            # with, or the mode's or turn's own model (first-class
            # INV-13).
            pricing = self._responses.pricing(resumed.model, resumed.model_provider, self._params.turn_model(request))
            turn = await self._starts.start_turn(operation, thread_id, request, items, pricing)
        finally:
            self._registry.release(thread_id)
        return self._starts.accept(operation, turn)

    async def fork_codex_thread(
        self,
        thread_id: str,
        from_turn_id: str = "",
        exclude_turns: bool = False,
        overrides: CodexSpawnRequest | None = None,
        before_turn_id: str = "",
        defer_goal_continuation: bool = False,
    ) -> CodexThreadInfo:
        # @intent fork-only-through-a-completed-turn
        # Copy a thread through one of its completed turns, or up to the
        # turn named in before_turn_id, into a new thread. exclude_turns
        # only leaves the turns out of the answer; the fork still holds
        # them (D-29).
        operation = CodexHostOperation.FORK_CODEX_THREAD
        self._guard(operation, talks=True)
        # Check every argument and the overrides a fork can apply, then
        # the experimental fields this host allows, before anything is
        # sent (hardening INV-28 step 1).
        forking = CodexForkRequest(
            thread_id=thread_id,
            from_turn_id=from_turn_id,
            exclude_turns=exclude_turns,
            overrides=overrides or CodexSpawnRequest(),
            before_turn_id=before_turn_id,
            defer_goal_continuation=defer_goal_continuation,
        )
        self._reject_experimental_fork_fields(forking)
        # The thread helpers run the remaining checks in order, then
        # fork, share the parent's tools and name the fork.
        return await self._threads.fork(operation, forking)

    async def list_codex_threads(
        self,
        cwd: str = "",
        search: str = "",
        archived: bool = False,
        source_kinds: tuple[CodexThreadSourceKind, ...] = (),
        sort: CodexThreadSortKey = CodexThreadSortKey.PROVIDER_DEFAULT,
        sort_direction: CodexSortDirection = CodexSortDirection.PROVIDER_DEFAULT,
        cursor: str = "",
        limit: int | None = None,
    ) -> CodexThreadPage:
        """One page of stored threads, at most limit when given; search matches thread titles only, not their content."""
        # @intent list-one-page-without-empty-filters
        # Empty arguments and a None limit are left out, so Codex
        # applies its own default for each one not given (INV-29).
        operation = CodexHostOperation.LIST_CODEX_THREADS
        self._guard(operation, talks=True)
        listing = CodexThreadListRequest(cwd=cwd, search=search, archived=archived, source_kinds=source_kinds, sort=sort, sort_direction=sort_direction, cursor=cursor, limit=limit)
        connection = self._connection
        params = self._params.thread_list(listing.cwd, listing.search, listing.archived, listing.source_kinds, listing.sort, listing.sort_direction, listing.cursor, listing.limit)
        page = await connection.call(operation, CODEX_THREAD_LIST_METHOD, connection.client.thread_list, params)
        return self._responses.page(page)

    async def read_codex_thread(self, thread_id: str, include_turns: bool = False) -> CodexThreadInfo:
        """One stored thread; include_turns, deprecated in openai-codex 0.163, also reads its turn summaries.

        Prefer list_codex_turns, which pages the stored transcript.
        """
        operation = CodexHostOperation.READ_CODEX_THREAD
        self._guard(operation, talks=True)
        reading = CodexThreadReadRequest(thread_id=thread_id, include_turns=include_turns)
        thread = await self._preflight.require_thread(operation, reading.thread_id, reading.include_turns)
        return self._responses.thread_info(thread)

    async def wait_codex_turn(self, handle: CodexTurnHandle, timeout_seconds: float | None = None) -> CodexTurnSnapshot:
        """Wait for a turn to end, at most timeout_seconds; there is no default timeout.

        Without one the wait still returns once Codex ends the turn, the
        host closes, the process dies, or the host stops a turn whose
        events failed or stopped arriving.
        """
        # @intent waiting-never-cancels-the-turn
        # Wait for a turn this host registered to end, at most
        # timeout_seconds. The wait is shielded, so a timeout or a
        # cancelled waiter never stops the turn; a turn still running
        # comes back as a RUNNING snapshot.
        operation = CodexHostOperation.WAIT_CODEX_TURN
        self._guard(operation, talks=False)
        # A wait takes exactly the timeouts a turn does, so its record
        # checks them with the turn's own seconds rule.
        waiting = CodexTurnWaitRequest(handle=handle, timeout_seconds=timeout_seconds)
        turn = self._owned(operation, handle)
        try:
            return await asyncio.wait_for(asyncio.shield(turn.ended), waiting.timeout_seconds)
        except TimeoutError:
            return turn.snapshot or self._responses.running(handle)

    async def get_codex_turn_result(self, handle: CodexTurnHandle) -> CodexTurnSnapshot:
        """The turn's snapshot now, without waiting; a handle belongs to this host, so read stored turns with list_codex_turns."""
        operation = CodexHostOperation.GET_CODEX_TURN_RESULT
        self._guard(operation, talks=False)
        turn = self._owned(operation, CodexTurnRef(operation=operation, handle=handle).handle)
        return turn.snapshot or self._responses.running(handle)

    async def steer_codex_turn(self, handle: CodexTurnHandle, input: str | CodexRunInput) -> CodexTurnHandle:
        # Add input to a running turn. A goal run is steered on the
        # physical turn running now.
        operation = CodexHostOperation.STEER_CODEX_TURN
        self._guard(operation, talks=True)
        steering = CodexTurnSteerRequest(handle=handle, run_input=input)
        turn = self._owned(operation, handle)
        items = self._params.input_items(steering.run_input)
        if turn.snapshot is not None:
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, CODEX_HOST_STEER_FINISHED_MESSAGE.format(turn_id=handle.turn_id), operation, handle.thread_id)
        # A turn whose stop is in flight is ending, so nothing is sent
        # (hardening INV-6).
        if turn.stop_pending:
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, CODEX_HOST_STEER_STOPPING_MESSAGE.format(turn_id=handle.turn_id), operation, handle.thread_id)
        expected = (turn.state.current_turn() if turn.state is not None else None) or handle.turn_id
        connection = self._connection
        await connection.call(operation, CODEX_TURN_STEER_METHOD, connection.client.turn_steer, handle.thread_id, expected, items, thread_id=handle.thread_id)
        return handle

    async def interrupt_codex_turn(self, handle: CodexTurnHandle) -> None:
        """Send a running turn one interrupt; await wait_codex_turn(handle) to confirm it ended."""
        # @intent the-caller-can-always-retry-a-failed-stop
        # Stop a running turn with one interrupt and no stop reason
        # (AC-16). A finished turn gets nothing (EC-25), and so does a
        # turn whose earlier stop is still being awaited. A stop whose
        # await failed, timed out or was cancelled blocks nothing, so
        # the caller can retry.
        operation = CodexHostOperation.INTERRUPT_CODEX_TURN
        self._guard(operation, talks=True)
        turn = self._owned(operation, CodexTurnRef(operation=operation, handle=handle).handle)
        if turn.snapshot is not None or turn.stop_pending:
            return
        # Mark the stop as sent, so a later timeout or output cap
        # crossing adds no interrupt (D-7), and as pending until this
        # interrupt returns.
        turn.stop_sent = True
        turn.stop_pending = True
        await turn.send_stop(self._connection, operation)

    async def track_codex_thread_usage(self, thread_id: str) -> CodexThreadUsage:
        """The usage of every turn this host saw end on the thread; stored usage and Codex's own subagent spend are not included."""
        operation = CodexHostOperation.TRACK_CODEX_THREAD_USAGE
        self._guard(operation, talks=False)
        ref = CodexThreadRef(operation=operation, thread_id=thread_id)
        usage = self._registry.usage(ref.thread_id)
        if usage is None:
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, CODEX_HOST_NEVER_RAN_MESSAGE, operation, ref.thread_id)
        return usage

    async def forget_codex_turns(self, thread_id: str) -> int:
        """Release the ended turns this host registered on an idle thread, with its usage, and return how many it dropped.

        Nothing is sent to Codex, and it works on a closed host. A busy
        thread is refused. Afterwards their handles and the thread's
        usage are unknown here; the thread's tools stay registered.
        """
        # @intent forget-only-an-idle-thread-s-turns
        # A thread with a running, reserved or starting turn is refused,
        # so only ended turns are dropped (hardening INV-22).
        operation = CodexHostOperation.FORGET_CODEX_TURNS
        self._guard(operation, talks=False)
        ref = CodexThreadRef(operation=operation, thread_id=thread_id)
        self._preflight.require_idle(operation, ref.thread_id)
        return self._registry.forget(ref.thread_id)

    async def launch_codex_subagents(
        self,
        prompts: Sequence[str | CodexRunInput],
        request: CodexSpawnRequest | None = None,
        limit: int | None = None,
    ) -> tuple[CodexTurnHandle, ...]:
        """Start one thread and turn per prompt, one after another, after one preflight.

        Starts are not concurrent and there is no default fan-out cap;
        pass limit to cap how many prompts one call may start.
        """
        # @intent launch-in-order-and-stop-what-a-failure-leaves
        # Start one thread and turn per prompt, in order, after a single
        # preflight. If one fails, or the caller leaves, every turn
        # already started gets one interrupt, and a failure says how
        # many there were (INV-37, INV-11).
        operation = CodexHostOperation.LAUNCH_CODEX_SUBAGENTS
        self._guard(operation, talks=True)
        # Check the prompts, the shared request and the limit, then
        # turn each prompt into its own thread's input.
        launch = CodexSubagentLaunchRequest(prompts=prompts, request=request or CodexSpawnRequest(), limit=limit)
        spawn = launch.request
        batch = [self._params.input_items(prompt) for prompt in launch.prompts]
        bridge = self._tool_bridge(spawn)
        self._params.reject_unusable_schema(spawn)
        await self._preflight.run(operation, spawn)
        started: list[CodexLiveTurn] = []
        try:
            for items in batch:
                thread_id, pricing = await self._open_thread(operation, spawn, bridge)
                try:
                    turn = await self._starts.start_turn(operation, thread_id, spawn, items, pricing)
                except BaseException:
                    self._starts.release_tools(thread_id)
                    raise
                self._starts.accept(operation, turn)
                started.append(turn)
        except BaseException as exc:
            for turn in started:
                turn.stop(self._connection, None)
            if not started or not isinstance(exc, CodexAgentError):
                raise
            # Keep every field of the error; only its message grows.
            raise exc.with_sentence(CODEX_HOST_LAUNCH_INTERRUPTED_SENTENCE.format(count=len(started))) from None
        return tuple(turn.handle for turn in started)

    async def start_codex_review(
        self,
        thread_id: str,
        target: CodexReviewTarget,
        delivery: CodexReviewDelivery = CodexReviewDelivery.INLINE,
        request: CodexSpawnRequest | None = None,
    ) -> CodexTurnHandle:
        # @intent a-review-is-sent-once-and-owned
        # Start a Codex review of a thread's work, capped by Vidbyte's
        # own time and output limits when the request sets them.
        # review/start spends, so it is sent once, and its turn is owned
        # even when its caller left.
        operation = CodexHostOperation.START_CODEX_REVIEW
        self._guard(operation, talks=True)
        # Only a missing request means the uncapped default, so any
        # other value reaches the record and a bad one is refused
        # rather than replaced (hardening INV-30).
        review = CodexReviewRequest(thread_id=thread_id, target=target, delivery=delivery, request=CodexSpawnRequest() if request is None else request)
        return await self._reviews.start(operation, review)

    async def list_recent_codex_threads(self, cwd: str, limit: int = CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT) -> tuple[CodexThreadSummary, ...]:
        """Up to limit threads of every top-level source, newest first.

        The SDK's own threads are included, and no preflight check is
        sent. Nothing here filters by text; search_codex_threads
        matches thread titles only, not their content.
        """
        operation = CodexHostOperation.LIST_RECENT_CODEX_THREADS
        self._guard(operation, talks=True)
        return await self._threads.list_threads(CodexThreadListing(operation=operation, cwd=cwd, limit=limit))

    async def list_codex_threads_since(self, cwd: str, since: int, limit: int = CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT) -> tuple[CodexThreadSummary, ...]:
        """Up to limit threads updated at or after since, newest first.

        since is in Unix seconds, and an empty window is (). Nothing
        here filters by text; search_codex_threads matches thread
        titles only, not their content.
        """
        operation = CodexHostOperation.LIST_CODEX_THREADS_SINCE
        self._guard(operation, talks=True)
        return await self._threads.list_threads(CodexThreadListing(operation=operation, cwd=cwd, limit=limit, since=since))

    async def search_codex_threads(self, cwd: str, query: str, limit: int = CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT) -> tuple[CodexThreadSummary, ...]:
        """Up to limit threads whose title matches query, newest first.

        Codex matches query against titles only, not thread content.
        """
        operation = CodexHostOperation.SEARCH_CODEX_THREADS
        self._guard(operation, talks=True)
        return await self._threads.list_threads(CodexThreadListing(operation=operation, cwd=cwd, limit=limit, query=query))

    async def get_codex_thread_lineage(self, thread_id: str) -> tuple[CodexThreadSummary, ...]:
        # The thread and its fork or spawn parents, child first; the
        # chain is complete when the last has no parent (INV-16).
        operation = CodexHostOperation.GET_CODEX_THREAD_LINEAGE
        self._guard(operation, talks=True)
        return await self._threads.lineage(CodexThreadRef(operation=operation, thread_id=thread_id))

    async def list_codex_turns(self, thread_id: str, cursor: str = "", limit: int | None = None) -> CodexTurnPage:
        # One page of the stored transcript, oldest first, with every
        # item; a None limit means Codex's own page size (INV-17).
        operation = CodexHostOperation.LIST_CODEX_TURNS
        self._guard(operation, talks=True)
        return await self._threads.turns(operation, CodexTurnListRequest(thread_id=thread_id, cursor=cursor, limit=limit))

    async def compact_codex_thread(self, thread_id: str) -> None:
        """Start Codex's compaction of a stored thread's history.

        The compaction runs inside this host's codex app-server process,
        so it finishes only while the host stays open. A thread that is
        not loaded here is loaded first, the way continue_codex_thread
        loads it, and is refused with codex.goal_unfinished while it has
        an unfinished goal. It returns once Codex accepts the request;
        there is no way to wait for or confirm the compaction.
        """
        # Busy and unknown threads are refused before anything is sent
        # (INV-8, INV-18).
        operation = CodexHostOperation.COMPACT_CODEX_THREAD
        self._guard(operation, talks=True)
        await self._threads.compact(CodexThreadRef(operation=operation, thread_id=thread_id))

    async def delete_codex_thread(self, thread_id: str) -> None:
        """Delete a stored thread for good; it cannot be undone.

        This is a plain function and never a tool, so no model can
        reach it. Busy and unknown threads are refused. There is no
        archive alternative, and threads forked from this one are not
        checked: a child's lineage then ends at the missing parent.
        """
        # Busy and unknown threads are refused before anything is sent
        # (INV-8, INV-19).
        operation = CodexHostOperation.DELETE_CODEX_THREAD
        self._guard(operation, talks=True)
        await self._threads.delete(CodexThreadRef(operation=operation, thread_id=thread_id))

    async def get_codex_goal(self, thread_id: str) -> CodexThreadGoal | None:
        # The thread's stored goal, or None, without loading the thread
        # (INV-20, INV-33).
        operation = CodexHostOperation.GET_CODEX_GOAL
        self._guard(operation, talks=True)
        return await self._threads.goal(CodexThreadRef(operation=operation, thread_id=thread_id))

    async def run_codex_goal(self, objective: str, token_budget: int | None = None, request: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        # @intent a-goal-run-is-confirmed-before-its-handle-returns
        # Start a goal run on a new thread with the caller's request,
        # and return its handle only once Codex stored that goal
        # (INV-21, INV-22).
        operation = CodexHostOperation.RUN_CODEX_GOAL
        self._guard(operation, talks=True)
        goal_run = CodexGoalRunRequest(goal=CodexGoal(objective=objective, token_budget=token_budget), request=request or CodexSpawnRequest())
        self._preflight.reject_user_reviewer(operation, goal_run.request)
        return await self._skills.run_goal(operation, goal_run)

    async def list_codex_skills(self, cwd: str = "", force_reload: bool = False) -> tuple[CodexSkillInfo, ...]:
        # The skills Codex lists for one folder, or for the
        # app-server's own when cwd is empty, with no usage check
        # (INV-23); force_reload makes Codex rescan (hardening INV-32).
        operation = CodexHostOperation.LIST_CODEX_SKILLS
        self._guard(operation, talks=True)
        folder = CodexSkillListRequest(cwd=cwd, force_reload=force_reload)
        connection = self._connection
        listing = connection.raw(CODEX_SKILLS_LIST_METHOD, self._params.skills_list(folder.cwd, folder.force_reload))
        return self._responses.skills(await connection.call(operation, CODEX_SKILLS_LIST_METHOD, listing))

    async def run_codex_skill(self, skill: str, prompt: str, request: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        """Run one skill on a new thread with a text prompt; a run takes no images, no mentions and no second skill."""
        # @intent a-skill-run-is-confirmed-before-its-handle-returns
        # Start a new thread whose first turn carries the skill as a
        # first-class input item, and return its handle only once Codex
        # recorded that item (INV-24, INV-25, INV-34).
        operation = CodexHostOperation.RUN_CODEX_SKILL
        self._guard(operation, talks=True)
        skill_run = CodexSkillRunRequest(operation=operation, skill=skill, prompt=prompt, request=request or CodexSpawnRequest())
        self._preflight.reject_user_reviewer(operation, skill_run.request)
        return await self._skills.run_skill(skill_run)

    async def run_codex_openai_docs(self, question: str, request: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        """Ask the openai-docs skill a text question on a new thread; as with run_codex_skill, no images, mentions or second skill."""
        # @intent the-docs-run-is-the-openai-docs-skill-run
        # run_codex_skill for the bundled openai-docs skill, which
        # answers from the official OpenAI documentation (INV-26).
        operation = CodexHostOperation.RUN_CODEX_OPENAI_DOCS
        self._guard(operation, talks=True)
        skill_run = CodexSkillRunRequest(operation=operation, skill=CODEX_OPENAI_DOCS_SKILL_NAME, prompt=question, request=request or CodexSpawnRequest())
        self._preflight.reject_user_reviewer(operation, skill_run.request)
        return await self._skills.run_skill(skill_run)

    def _reject_experimental_fork_fields(self, forking: CodexForkRequest) -> None:
        # @intent experimental-fork-fields-need-the-experimental-api
        # Codex takes beforeTurnId and deferGoalContinuation only from
        # clients that opt in to its experimental API, so without it
        # each is refused here, before any request, as dynamic tools are
        # (hardening INV-28 step 1, EC-56).
        if self._settings.experimental_api:
            return
        for name in CODEX_HOST_FORK_EXPERIMENTAL_FIELDS:
            if getattr(forking, name):
                raise ConfigurationError(CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE.format(field=name), details={"field": name})

    def _tool_bridge(self, request: CodexSpawnRequest) -> CodexToolBridge | None:
        # @intent tools-are-checked-before-any-call
        # Dynamic tools need the experimental API and names Codex
        # accepts; both are checked before anything is sent (INV-29).
        if not request.tools:
            return None
        if not self._settings.experimental_api:
            raise ConfigurationError(CODEX_HOST_EXPERIMENTAL_API_TEXT)
        catalog = Tools(request.tools)
        CodexToolTranslator.validate_names(catalog)
        return CodexToolBridge(catalog, request.tool_permission_policy)

    async def _open_thread(self, operation: CodexHostOperation, request: CodexSpawnRequest, bridge: CodexToolBridge | None) -> tuple[str, CodexAgentSettings]:
        # @intent check-the-reviewer-before-the-thread-spends
        # Start the thread with its dynamic tools. On a host without an
        # approval_handler, a user reviewer Codex reports stops here,
        # naming the thread, before any name, turn or goal is sent
        # (D-32, hardening INV-20). The tool handler is registered
        # last, so a failed step leaves none behind (hardening
        # INV-26). The pricing names the model Codex resolved and its
        # provider (D-19), and the mode's or turn's own model
        # (first-class INV-13).
        connection = self._connection
        dynamic_tools = bridge.dynamic_tools if bridge is not None else ()
        started = await connection.call(operation, CODEX_THREAD_START_METHOD, connection.client.thread_start, self._params.thread_start(request, dynamic_tools))
        thread_id = started.thread.id
        self._preflight.reject_routed_reviewer(operation, thread_id, self._responses.routes_to_user(started))
        if request.name:
            await connection.call(operation, CODEX_THREAD_NAME_SET_METHOD, connection.client.thread_set_name, thread_id, request.name, thread_id=thread_id)
        if bridge is not None:
            connection.router.register(thread_id, bridge.handler(asyncio.get_running_loop(), connection.router.handle))
        return thread_id, self._responses.pricing(started.model, started.model_provider, self._params.turn_model(request))

    def _end_running_turns(self) -> list[CodexLiveTurn]:
        # Stop the approval handler first, so nothing routed reaches it
        # from now on, cancel every running tool call, release each
        # plain turn's route so its watcher ends, and end every running
        # turn as exited (INV-7 steps 1 and 2, hardening INV-21).
        connection = self._connection
        connection.router.cancel_pending()
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
        # Runs on the loop when the liveness monitor sees the process
        # die (D-27): close steps 1 and 2 run at once, so every running
        # turn ends as exited and each goal run's stream closes, and the
        # dead process is reaped on the close thread. Close does this
        # itself.
        if self._closing:
            return
        for turn in self._end_running_turns():
            turn.close_goal_stream(self._connection.client)
        self._connection.reap()


__all__ = ["CodexHost"]
