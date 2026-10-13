"""FILE: vidbyte/harnesses/native/grok/host.py

PURPOSE: Defines GrokHost, the async context manager that drives the user's own Grok Build CLI in one workspace through its ten public methods (check_grok_ready, list_grok_models, spawn_grok_session, run_grok_once, continue_grok_session, fork_grok_session, list_grok_sessions, search_grok_sessions, wait_grok_turn, interrupt_grok_turn), and the module function run_grok_once, which wraps one one-shot run in a host of its own.
ROLE IN CODEBASE: The public Grok entry point, exported by vidbyte/harnesses/native/grok/__init__.py and wrapped one tool per method by vidbyte/tools/builtins/grok/. It composes GrokCli (argv and CLI runs), GrokWire (params, parsing and row mapping), GrokTurnDriver (one per live turn) and the shared hostkit pieces (NativePeer, NativeTurnTable, NativeErrorFactory, NativeChildEnvironment).
ARCHITECTURE NOTE: D-2: every live turn runs on its own `grok agent --no-leader ... stdio` peer owned by its driver, and every read starts a short-lived peer that is closed before the method returns. Each public method checks its arguments before any I/O (EC-1), refuses to run outside the async with block (EC-2), and has one try that lets cancellation and NativeHostError through, maps a refused argument to configuration.invalid_argument and any other exception to runtime.error.
FUNCTION INVENTORY: __aenter__ resolves the launcher and refuses a Windows batch launcher; __aexit__ stops every live turn; the ten public methods are narrated main functions. Helpers: _require_open, _reserve, _new_peer, _initialize, _check_model, _call, _list_pages, _check_fork_listing, _launch and the _forget done-callback. Module function run_grok_once.
COMMON MODIFICATION PATTERNS: A new Grok call is one public method here, its parsing and rows in wire.py, its argv in cli.py and one tool in vidbyte/tools/builtins/grok/tools.py. A new row next step that the catalog does not give is a module constant here or in wire.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not read ~/.grok credentials or set approve-everything flags; Grok authenticates itself and permissions follow GrokPermissionMode and allowed_tool_kinds only (INV-9). 2. Do not await between the busy check and the reservation of a turn (EC-9). 3. Do not leave a short-lived peer running after its method returns, on any path (INV-4).
KNOWN EDGE CASES: A host is single use: a second __aenter__ raises invalid_argument (EC-3). fork_grok_session spends money, so it first finds the source session in the workspace listing, refuses a taken new id and checks the model, all before the CLI run. A turn whose host closed ends INTERRUPTED with source HOST_CLOSED.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Grok host), §6.3.3, D-2, D-9 to D-12, D-19, EC-1 to EC-11, EC-24 to EC-53, FR-17
TESTS: tests/features/grok_host/test_grok_host_acceptance.py, tests/features/grok_host/test_grok_host_errors.py, tests/features/grok_host/test_grok_host_reads.py, tests/features/grok_host/test_grok_host_turns.py, tests/features/grok_host/test_grok_host_process_bounds.py
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
from collections.abc import Mapping
from types import TracebackType
from typing import Any

from vidbyte.harnesses.native.grok.cli import GrokCli
from vidbyte.harnesses.native.grok.turn import GrokTurnDriver
from vidbyte.harnesses.native.grok.wire import GrokWire
from vidbyte.harnesses.native.hostkit import (
    NativeChildEnvironment,
    NativeErrorFactory,
    NativePeer,
    NativeTurnTable,
)
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.grok import (
    GrokHostSettings,
    GrokModelCatalog,
    GrokOneShotRequest,
    GrokOneShotResult,
    GrokReadiness,
    GrokSession,
    GrokSessionPage,
    GrokSessionSearch,
    GrokTurnRequest,
)
from vidbyte.lib.dataclasses.native_hosts import (
    NativeInterruptResult,
    NativeTurnHandle,
    NativeTurnResult,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_hosts import InterruptSource, NativeHarness
from vidbyte.lib.enums.process import ProcessLaunchFailure
from vidbyte.lib.errors import ConfigurationError, McpProtocolError, NativeHostError

_ENTER = "__aenter__"
_EXIT = "__aexit__"
_CONSTRUCT = "GrokHost"
_ONE_PAGE = 1
_READY_CAPABILITY_NEXT_STEP = "Update Grok Build with grok update; this SDK needs ACP session/list and session/resume."
_RESUME_CAPABILITY_NEXT_STEP = "Update Grok Build with grok update; continuing needs ACP session/resume."
_LIST_CAPABILITY_NEXT_STEP = "Update Grok Build with grok update; listing needs ACP session/list."
_BATCH_LAUNCHER_NEXT_STEP = "On Windows this host does not start a .cmd or .bat launcher; install Grok Build so that ~/.grok/bin/grok.exe exists, or set GrokHostSettings.grok_command to the path of a grok.exe."


class GrokHost:
    """Drives the user's Grok Build CLI in one workspace: live turns on their own ACP peers, short-lived peers for reads, and bounded CLI runs."""

    def __init__(self, settings: GrokHostSettings) -> None:
        self._errors = NativeErrorFactory(NativeHarness.GROK)
        try:
            self._settings: GrokHostSettings = RecordFieldConverter.require_instance(settings, "settings", GrokHostSettings)
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=_CONSTRUCT) from exc
        self._wire = GrokWire(self._errors)
        self._cli = GrokCli(settings)
        self._turns = NativeTurnTable(NativeHarness.GROK, max_live_turns=settings.max_live_turns, errors=self._errors)
        self._drivers: dict[str, GrokTurnDriver] = {}
        self._entered = False
        self._closed = False

    async def __aenter__(self) -> GrokHost:
        # @intent grok-host-is-single-use-and-finds-grok-once
        # A host serves exactly one async with block. The launcher is
        # found here, once, so every call starts the same program; with
        # nothing found the block never starts, and on Windows a batch
        # launcher is refused before anything runs.
        try:
            # A host serves one block only, open or already closed.
            if self._entered:
                raise self._errors.invalid_argument("host", "This GrokHost was already entered; a host serves one async with block.", operation=_ENTER, next_step=native_host_constants.NATIVE_REENTER_NEXT_STEP)
            self._entered = True
            # Find grok: the explicit command, then PATH, then the
            # installer's folder.
            if not self._cli.resolve_launcher():
                self._closed = True
                # On Windows only a batch file was found, which cmd.exe
                # would run with the prompt on its command line.
                if self._cli.refused_batch is not None:
                    raise self._errors.build(self._errors.code("not_installed"), f"The Grok launcher {self._cli.refused_batch} is a batch file, which this host does not start on Windows.", operation=_ENTER, next_step=_BATCH_LAUNCHER_NEXT_STEP)
                raise self._errors.from_launch_failure(ProcessLaunchFailure.NOT_FOUND, operation=_ENTER)
            return self
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            self._closed = True
            raise self._errors.from_unexpected(exc, operation=_ENTER) from exc

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        # @intent grok-host-exit-stops-every-turn
        # Refuse every later call, interrupt each live turn as
        # HOST_CLOSED, give the turns NATIVE_STOP_GRACE_SECONDS to
        # end, then close the remaining peers all at once and wait for
        # their drivers. It raises nothing of its own and never
        # suppresses the body's error.
        self._closed = True
        drivers = list(self._drivers.values())
        tasks = self._turns.live_tasks()
        if not drivers or not tasks:
            return
        # Ask every live turn to stop; a peer that can no longer be
        # written to is closed below anyway.
        for driver in drivers:
            with contextlib.suppress(NativeHostError):
                await driver.interrupt(InterruptSource.HOST_CLOSED, operation=_EXIT)
        # Give the turns the grace period to end by themselves.
        await asyncio.wait(tasks, timeout=native_host_constants.NATIVE_STOP_GRACE_SECONDS)
        # Close every peer at once, so many turns cost no more than one,
        # then let the drivers record the ending.
        closers = [asyncio.create_task(driver.close()) for driver in drivers]
        await asyncio.wait(closers)
        await asyncio.wait(tasks)

    async def check_grok_ready(self) -> GrokReadiness:
        """Check the Grok Build version, the ACP handshake and the sign-in, and report what Grok offers."""
        operation = "check_grok_ready"
        try:
            self._require_open(operation)
            # Ask the CLI for its version first; an unreadable or too
            # old release needs no peer.
            version_run = await self._cli.run(self._cli.version_argv(), timeout_seconds=self._settings.control_timeout_seconds)
            self._wire.check_cli(version_run, operation=operation, one_shot=False)
            version = self._wire.parse_version(version_run, operation=operation)
            # Run the ACP handshake on a short-lived peer that is closed
            # before anything else happens.
            peer = self._new_peer(None, None)
            try:
                handshake = await self._initialize(peer, operation)
            finally:
                await peer.close()
            # This host lists and resumes sessions, so
            # Grok must offer both.
            self._wire.require_session_capability(handshake, GrokWire.LIST_CAPABILITY, operation=operation, next_step=_READY_CAPABILITY_NEXT_STEP)
            self._wire.require_session_capability(handshake, GrokWire.RESUME_CAPABILITY, operation=operation, next_step=_READY_CAPABILITY_NEXT_STEP)
            # grok models fails, or prints the signed-out line, when the
            # CLI is not signed in.
            models_run = await self._cli.run(self._cli.models_argv(), timeout_seconds=self._settings.control_timeout_seconds)
            self._wire.check_cli(models_run, operation=operation, one_shot=False)
            return self._wire.parse_readiness(version, handshake, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def list_grok_models(self) -> GrokModelCatalog:
        """List the models Grok offers, with each model's reasoning efforts and the current default."""
        operation = "list_grok_models"
        try:
            self._require_open(operation)
            # The catalog is part of the ACP handshake, so one
            # short-lived peer answers it.
            peer = self._new_peer(None, None)
            try:
                handshake = await self._initialize(peer, operation)
            finally:
                await peer.close()
            return self._wire.parse_model_catalog(handshake, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def spawn_grok_session(self, request: GrokTurnRequest) -> NativeTurnHandle:
        """Start a new session with one prompt and return its turn handle once Grok has the prompt."""
        # @intent grok-spawn-reserves-before-any-io
        # The live-turn slot is reserved before the first await and
        # released on every failure, so concurrent spawns respect
        # max_live_turns and a failed spawn frees its slot. The peer
        # belongs to the turn's driver once the handle exists, and is
        # closed here on any path that ends before that.
        operation = "spawn_grok_session"
        try:
            # Check the request and that the host is open, then reserve
            # a slot before anything starts.
            request = RecordFieldConverter.require_instance(request, "request", GrokTurnRequest)
            self._require_open(operation)
            turn_id = self._reserve(None, operation)
            peer = self._new_peer(request.model, request.reasoning_effort)
            handle: NativeTurnHandle | None = None
            try:
                # Run the handshake and check the model Grok really uses
                # before a session exists.
                handshake = await self._initialize(peer, operation)
                self._check_model(handshake, request.model, request.reasoning_effort, operation)
                # Create the session in the workspace, then send the
                # prompt and hand the turn to its driver.
                created = await self._call(peer, GrokWire.NEW_SESSION, self._wire.new_session_params(self._settings.workspace), operation=operation)
                session_id = self._wire.parse_session_id(created, operation=operation)
                self._turns.bind_session(turn_id, session_id)
                handle = await self._launch(turn_id, session_id, peer, request, operation)
                return handle
            finally:
                if handle is None:
                    self._turns.release(turn_id)
                    await peer.close()
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def run_grok_once(self, request: GrokOneShotRequest) -> GrokOneShotResult:
        """Run one headless Grok prompt to completion and return its answer."""
        # @intent grok-one-shot-checks-before-spending
        # A one-shot run spends money, so a requested model or effort is
        # confirmed on a short-lived peer first; without one no peer
        # starts. The run is bounded by max_turn_seconds and stopped
        # with its whole tree when it passes it.
        operation = "run_grok_once"
        try:
            request = RecordFieldConverter.require_instance(request, "request", GrokOneShotRequest)
            self._require_open(operation)
            # Confirm the model and effort live, only when the
            # request names one.
            if request.model is not None or request.reasoning_effort is not None:
                peer = self._new_peer(request.model, request.reasoning_effort)
                try:
                    handshake = await self._initialize(peer, operation)
                finally:
                    await peer.close()
                self._check_model(handshake, request.model, request.reasoning_effort, operation)
            # Run the prompt headless in the workspace and
            # read its JSON answer.
            outcome = await self._cli.run(self._cli.one_shot_argv(request), timeout_seconds=request.max_turn_seconds)
            self._wire.check_cli(outcome, operation=operation, one_shot=True)
            return self._wire.parse_one_shot(outcome, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def continue_grok_session(self, session_id: str, request: GrokTurnRequest) -> NativeTurnHandle:
        """Send one more prompt to an existing session and return its turn handle once Grok has the prompt."""
        # @intent grok-continue-reserves-the-session
        # The session is reserved before the first await, so two
        # continues on one session cannot both pass and the loser starts
        # no process; the reservation is released on every failure.
        operation = "continue_grok_session"
        try:
            # Check the arguments and that the host is open, then
            # reserve the session before anything starts. A session id
            # is a UUID, so its lower-case form names it in the busy
            # check and on the wire.
            request = RecordFieldConverter.require_instance(request, "request", GrokTurnRequest)
            session_id = RecordFieldValidator.require_uuid(session_id, "session_id").lower()
            self._require_open(operation)
            turn_id = self._reserve(session_id, operation)
            peer = self._new_peer(request.model, request.reasoning_effort)
            handle: NativeTurnHandle | None = None
            try:
                # Run the handshake; Grok must be able to resume
                # sessions, and the model must be the one asked for.
                handshake = await self._initialize(peer, operation)
                self._wire.require_session_capability(handshake, GrokWire.RESUME_CAPABILITY, operation=operation, next_step=_RESUME_CAPABILITY_NEXT_STEP)
                self._check_model(handshake, request.model, request.reasoning_effort, operation)
                # Resume the session in the workspace, then send the
                # prompt and hand the turn to its driver.
                params = self._wire.resume_session_params(session_id, self._settings.workspace)
                await self._call(peer, GrokWire.RESUME_SESSION, params, operation=operation, session_id=session_id)
                handle = await self._launch(turn_id, session_id, peer, request, operation)
                return handle
            finally:
                if handle is None:
                    self._turns.release(turn_id)
                    await peer.close()
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def fork_grok_session(self, session_id: str, request: GrokOneShotRequest, *, new_session_id: str | None = None) -> GrokOneShotResult:
        """Run one headless prompt on a fork of an existing session and return its answer."""
        # @intent grok-fork-checks-before-spending
        # The fork run spends money, so everything that can be checked
        # is checked first: the arguments, a live turn on the source,
        # the source in the workspace listing and the new id not taken,
        # then the model. Only then does the CLI run.
        operation = "fork_grok_session"
        try:
            # Check the arguments, then that the host is open and the
            # source session is not busy here. Session ids are UUIDs, so
            # they are compared and sent in lower case.
            request = RecordFieldConverter.require_instance(request, "request", GrokOneShotRequest)
            session_id = RecordFieldValidator.require_uuid(session_id, "session_id").lower()
            if new_session_id is not None:
                new_session_id = RecordFieldValidator.require_uuid(new_session_id, "new_session_id").lower()
            if new_session_id == session_id:
                raise self._errors.invalid_argument("new_session_id", "new_session_id must differ from session_id.", operation=operation)
            self._require_open(operation)
            if self._turns.is_session_busy(session_id):
                raise self._errors.build(self._errors.code("session_busy"), "The source session has a live turn on this host.", operation=operation, context={"session_id": session_id})
            # On one short-lived peer: list the workspace's
            # sessions, find the source, refuse a taken new id,
            # then check the model.
            peer = self._new_peer(request.model, request.reasoning_effort)
            try:
                handshake = await self._initialize(peer, operation)
                self._wire.require_session_capability(handshake, GrokWire.LIST_CAPABILITY, operation=operation, next_step=_LIST_CAPABILITY_NEXT_STEP)
                listing = await self._list_pages(peer, None, native_host_constants.GROK_LIST_MAX_PAGES, operation)
                self._check_fork_listing(listing, session_id, new_session_id, operation)
                self._check_model(handshake, request.model, request.reasoning_effort, operation)
            finally:
                await peer.close()
            # Run the fork headless, then make sure Grok really forked
            # into a different session.
            outcome = await self._cli.run(self._cli.fork_argv(session_id, request, new_session_id), timeout_seconds=request.max_turn_seconds)
            self._wire.check_cli(outcome, operation=operation, one_shot=True)
            forked = self._wire.parse_one_shot(outcome, operation=operation)
            self._wire.check_fork_result(forked, source=session_id, target=new_session_id, operation=operation)
            return forked
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def list_grok_sessions(self, cursor: str | None = None) -> GrokSessionPage:
        """List one page of this workspace's Grok sessions."""
        operation = "list_grok_sessions"
        try:
            # Check the cursor and that the host is open.
            if cursor is not None:
                RecordFieldValidator.require_text(cursor, "cursor", max_chars=native_host_constants.NATIVE_CURSOR_MAX_CHARS)
            self._require_open(operation)
            # On one short-lived peer: Grok must offer session/list,
            # then read one page from the cursor.
            peer = self._new_peer(None, None)
            try:
                handshake = await self._initialize(peer, operation)
                self._wire.require_session_capability(handshake, GrokWire.LIST_CAPABILITY, operation=operation, next_step=_LIST_CAPABILITY_NEXT_STEP)
                return await self._list_pages(peer, cursor, _ONE_PAGE, operation)
            finally:
                await peer.close()
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def search_grok_sessions(self, query: str, limit: int = native_host_constants.GROK_SEARCH_DEFAULT_LIMIT) -> GrokSessionSearch:
        """Find this workspace's sessions whose title contains the query, ignoring case."""
        operation = "search_grok_sessions"
        try:
            # Check the query and the limit, and that the host is open.
            RecordFieldValidator.require_text(query, "query", max_chars=native_host_constants.GROK_QUERY_MAX_CHARS)
            RecordFieldValidator.require_int(limit, "limit", minimum=native_host_constants.NATIVE_LIST_MIN_LIMIT, maximum=native_host_constants.GROK_SEARCH_MAX_LIMIT)
            self._require_open(operation)
            # On one short-lived peer: read up to GROK_LIST_MAX_PAGES
            # pages of the listing.
            peer = self._new_peer(None, None)
            try:
                handshake = await self._initialize(peer, operation)
                self._wire.require_session_capability(handshake, GrokWire.LIST_CAPABILITY, operation=operation, next_step=_LIST_CAPABILITY_NEXT_STEP)
                listing = await self._list_pages(peer, None, native_host_constants.GROK_LIST_MAX_PAGES, operation)
            finally:
                await peer.close()
            # Keep titles that contain the query when both are
            # casefolded, in listing order; a listing cut at the
            # page cap is flagged.
            needle = query.casefold()
            found = [session for session in listing.sessions if session.title is not None and needle in session.title.casefold()]
            return GrokSessionSearch(query=query, sessions=tuple(found[:limit]), truncated=listing.next_cursor is not None)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def wait_grok_turn(self, handle: NativeTurnHandle, timeout_seconds: float = native_host_constants.NATIVE_WAIT_DEFAULT_SECONDS) -> NativeTurnResult:
        """Wait up to timeout_seconds for a turn's result; a timed-out or cancelled wait leaves the turn running."""
        # @intent grok-wait-never-touches-the-turn
        # The wait is shielded, so its timeout or cancellation
        # never reaches the turn; a FAILED turn raises the same
        # error on every wait.
        operation = native_host_constants.GROK_TURN_OPERATION
        try:
            # Check the handle and the time budget before
            # anything is looked up.
            RecordFieldConverter.require_instance(handle, "handle", NativeTurnHandle)
            seconds = RecordFieldValidator.require_number(timeout_seconds, "timeout_seconds", maximum=native_host_constants.NATIVE_WAIT_MAX_SECONDS)
            self._require_open(operation)
            turn = self._turns.lookup(handle, operation=operation)
            # Wait for the turn without ever cancelling it.
            try:
                return await asyncio.wait_for(asyncio.shield(turn), timeout=seconds)
            except TimeoutError as exc:
                raise self._errors.build(self._errors.code("turn_timed_out"), "The turn is still running after timeout_seconds.", operation=operation, context={"session_id": handle.session_id}) from exc
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def interrupt_grok_turn(self, handle: NativeTurnHandle) -> NativeInterruptResult:
        """Ask a running turn to stop and return at once; a finished turn is left alone."""
        operation = "interrupt_grok_turn"
        try:
            # Check the handle and that the host is open, then find the
            # turn this host issued it for.
            RecordFieldConverter.require_instance(handle, "handle", NativeTurnHandle)
            self._require_open(operation)
            turn = self._turns.lookup(handle, operation=operation)
            driver = self._drivers.get(handle.turn_id)
            # A finished turn is not touched and nothing is sent.
            if turn.done() or driver is None:
                return NativeInterruptResult(handle=handle, was_running=False)
            # Send session/cancel and return; the driver stops the peer
            # if Grok ignores it.
            await driver.interrupt(InterruptSource.CALLER, operation=operation)
            return NativeInterruptResult(handle=handle, was_running=True)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    def _require_open(self, operation: str) -> None:
        # A host serves calls only inside its async with block.
        if self._entered and not self._closed:
            return
        raise self._errors.build(self._errors.code("process_exited"), "This GrokHost is not open.", operation=operation, next_step=native_host_constants.NATIVE_NOT_OPEN_NEXT_STEP)

    def _reserve(self, session_id: str | None, operation: str) -> str:
        # Reserves the slot, and the session when known, with no await;
        # at the cap the error tells the caller to wait for or
        # interrupt a running turn.
        try:
            return self._turns.reserve(session_id, operation=operation)
        except NativeHostError as exc:
            if "live_turns" not in exc.context:
                raise
            raise self._errors.build(exc.failure_code, "This host already runs its maximum number of live turns.", operation=operation, next_step=native_host_constants.NATIVE_AT_CAP_NEXT_STEP.format(tool="interrupt_grok_turn"), context=exc.context) from exc

    def _new_peer(self, model: str | None, reasoning_effort: str | None) -> NativePeer:
        # One ACP peer with the caller's environment; the model flags
        # make Grok report the model it will really use.
        argv = self._cli.peer_argv(model, reasoning_effort)
        return NativePeer(argv, env=NativeChildEnvironment.build({}), control_timeout_seconds=self._settings.control_timeout_seconds, errors=self._errors)

    async def _initialize(self, peer: NativePeer, operation: str) -> Mapping[str, Any]:
        # Starts the peer and runs the ACP handshake; a JSON-RPC error
        # maps to its grok.* failure, and the protocol and agent
        # version must be supported.
        await peer.start(operation=operation)
        try:
            handshake = await peer.call(GrokWire.INITIALIZE, self._wire.initialize_params(), operation=operation)
        except McpProtocolError as exc:
            raise self._wire.vendor_error(exc, operation=operation, method=GrokWire.INITIALIZE) from exc
        self._wire.check_initialize(handshake, operation=operation)
        return handshake

    def _check_model(self, handshake: Mapping[str, Any], model: str | None, reasoning_effort: str | None, operation: str) -> None:
        # Only a request that names a model or an
        # effort needs the catalog.
        if model is None and reasoning_effort is None:
            return
        self._wire.require_model(self._wire.parse_model_catalog(handshake, operation=operation), model, reasoning_effort, operation=operation)

    async def _call(self, peer: NativePeer, method: str, params: Mapping[str, Any], *, operation: str, session_id: str | None = None) -> Mapping[str, Any]:
        # One ACP call on a started peer; a JSON-RPC error answer maps
        # to its grok.* failure.
        try:
            return await peer.call(method, params, operation=operation)
        except McpProtocolError as exc:
            raise self._wire.vendor_error(exc, operation=operation, method=method, session_id=session_id) from exc

    async def _list_pages(self, peer: NativePeer, cursor: str | None, pages: int, operation: str) -> GrokSessionPage:
        # Reads up to pages session/list pages from cursor; the returned
        # cursor is where reading stopped, None once Grok has no more.
        sessions: list[GrokSession] = []
        for _page in range(pages):
            try:
                answer = await peer.call(GrokWire.LIST_SESSIONS, self._wire.list_sessions_params(self._settings.workspace, cursor), operation=operation)
            except McpProtocolError as exc:
                raise self._wire.vendor_error(exc, operation=operation, method=GrokWire.LIST_SESSIONS, cursor=cursor) from exc
            page = self._wire.parse_session_page(answer, operation=operation)
            sessions.extend(page.sessions)
            cursor = page.next_cursor
            if cursor is None:
                break
        return GrokSessionPage(sessions=tuple(sessions), next_cursor=cursor)

    def _check_fork_listing(self, listing: GrokSessionPage, session_id: str, new_session_id: str | None, operation: str) -> None:
        # The source must be in the workspace listing, and a new id must
        # not name an existing session. Both ignore letter case: the ids
        # arrive lower-cased and the listing is lower-cased here.
        known = {session.session_id.lower() for session in listing.sessions}
        if session_id not in known:
            truncated = native_host_constants.NATIVE_TRUE_TEXT if listing.next_cursor is not None else native_host_constants.NATIVE_FALSE_TEXT
            raise self._errors.build(self._errors.code("session_not_found"), "The source session is not in this workspace's session list.", operation=operation, context={"session_id": session_id, "truncated": truncated})
        if new_session_id is not None and new_session_id in known:
            raise self._errors.invalid_argument("new_session_id", "new_session_id already names a session in this workspace.", operation=operation)

    async def _launch(self, turn_id: str, session_id: str, peer: NativePeer, request: GrokTurnRequest, operation: str) -> NativeTurnHandle:
        # @intent grok-spawn-returns-once-the-prompt-is-written
        # The handle comes back once session/prompt is written; from
        # then on the driver task, owned by the turn table, plays the
        # turn and owns the peer. A host that closed meanwhile starts no
        # driver, so no turn outlives __aexit__.
        answer = await peer.send(GrokWire.PROMPT, self._wire.prompt_params(session_id, request.prompt), operation=operation)
        if self._closed:
            raise self._errors.build(self._errors.code("process_exited"), "This GrokHost closed while the turn was starting.", operation=operation, next_step=native_host_constants.NATIVE_NOT_OPEN_NEXT_STEP)
        handle = NativeTurnHandle(harness=NativeHarness.GROK, session_id=session_id, turn_id=turn_id)
        driver = GrokTurnDriver(peer=peer, wire=self._wire, errors=self._errors, handle=handle, request=request, answer=answer)
        task = asyncio.create_task(driver.run(), name="grok-turn-" + turn_id)
        self._drivers[turn_id] = driver
        task.add_done_callback(functools.partial(self._forget, turn_id))
        return self._turns.activate(turn_id, task)

    def _forget(self, turn_id: str, task: asyncio.Task[NativeTurnResult]) -> None:
        # Done-callback: drops the finished driver and marks a failed
        # turn's error as seen; wait still re-raises it.
        self._drivers.pop(turn_id, None)
        if not task.cancelled():
            task.exception()


async def run_grok_once(request: GrokOneShotRequest, *, settings: GrokHostSettings) -> GrokOneShotResult:
    """Run one headless Grok prompt in a GrokHost of its own, opened and closed around the call."""
    # @intent grok-module-one-shot-owns-its-host
    # The module function is the method inside its own async with block,
    # so the launcher is found, the run bounded and every process
    # stopped exactly as with an explicit host.
    async with GrokHost(settings) as host:
        return await host.run_grok_once(request)


__all__ = ["GrokHost", "run_grok_once"]
