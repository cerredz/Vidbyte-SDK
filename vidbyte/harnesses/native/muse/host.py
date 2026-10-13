"""FILE: vidbyte/harnesses/native/muse/host.py

PURPOSE: Defines MuseHost, the async context manager that drives the user's own Muse Code (`muse serve`, MSP 1.0.1) in one workspace through its twelve public methods: check_muse_ready, list_muse_models, spawn_muse_session, continue_muse_session, fork_muse_session, list_muse_sessions, read_muse_session, page_muse_session, steer_muse_turn, interrupt_muse_turn, wait_muse_turn and track_muse_session_usage.
ROLE IN CODEBASE: The public Muse entry point, exported by vidbyte/harnesses/native/muse/__init__.py and wrapped one tool per method by vidbyte/tools/builtins/muse/. It composes MuseLauncher (how muse starts, WSL distros and the reap), MuseWire (params, parsing and row mapping), MuseTurnDriver (one per live turn) and the shared hostkit pieces (NativePeer, NativeTurnTable, NativeErrorFactory).
ARCHITECTURE NOTE: D-9: every live turn runs on its own `muse serve` peer owned by its driver, and every read starts a short-lived peer that is closed before the method returns (INV-4). Each public method checks its arguments before any I/O (EC-1), refuses to run outside the async with block (EC-2), and has one try that lets cancellation and NativeHostError through, maps a refused argument to configuration.invalid_argument and any other exception to runtime.error. A turn peer is closed and, in WSL mode, reaped in the distro on every path that does not hand it to a driver (D-23).
FUNCTION INVENTORY: __aenter__ resolves the launcher once; __aexit__ stops every live turn; the twelve public methods are narrated main functions. Helpers: _require_open, _reserve, _turn_task, _new_peer, _handshake, _check_model, _resume, _start_turn, _launch, _list_page, _steer, _latest_usage, _discard and the _forget_driver done-callback.
COMMON MODIFICATION PATTERNS: A new MSP call is one public method here, its params and result reader in wire.py and one tool in vidbyte/tools/builtins/muse/tools.py. A row next step the catalog does not give is a module constant here or in wire.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not read Muse credentials or send an approve-everything value; sessions start with approvalMode denyUnmatched and the driver denies every approval (INV-9, D-11). 2. Do not await between the busy check and the reservation of a turn (EC-9). 3. Do not leave a peer running after its method returns, on any path (INV-4).
KNOWN EDGE CASES: A host is single use: a second __aenter__ raises invalid_argument (EC-3). On win32 a host needs muse_command or wsl_distro (EC-94). A WSL peer that exits before answering is classified from its stderr; an in-distro muse missing with exit code 127 and no text cannot be told apart from another early exit, because NativePeer does not expose the exit code. A turn whose host closed ends INTERRUPTED with source HOST_CLOSED.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (MuseHost), §6.3.5 (EC-94 to EC-121, EC-156), D-9 to D-14, D-18, D-19, D-23, FR-19
TESTS: tests/features/muse_host/test_muse_host_acceptance.py, tests/features/muse_host/test_muse_host_errors.py, tests/features/muse_host/test_muse_host_reads.py, tests/features/muse_host/test_muse_host_turns.py, tests/features/muse_host/test_muse_host_process_bounds.py, tests/features/muse_host/test_muse_host_wsl.py
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
from collections.abc import Mapping
from types import MappingProxyType, TracebackType

from vidbyte.harnesses.native.hostkit import (
    NativeErrorFactory,
    NativePeer,
    NativeTurnTable,
)
from vidbyte.harnesses.native.muse.launcher import MuseLauncher
from vidbyte.harnesses.native.muse.turn import MuseTurnDriver
from vidbyte.harnesses.native.muse.wire import MuseWire
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.muse import (
    MuseHostSettings,
    MuseModelCatalog,
    MusePage,
    MuseReadiness,
    MuseSession,
    MuseSessionPage,
    MuseTurnAck,
    MuseTurnRequest,
)
from vidbyte.lib.dataclasses.native_hosts import (
    NativeInterruptResult,
    NativeSessionUsage,
    NativeSteerResult,
    NativeTokenUsage,
    NativeTurnHandle,
    NativeTurnResult,
)
from vidbyte.lib.dataclasses.process import CliInvocation
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import (
    InterruptSource,
    MuseViewDirection,
    NativeHarness,
)
from vidbyte.lib.errors import ConfigurationError, McpProtocolError, NativeHostError
from vidbyte.lib.process import CliRunner

_ENTER = "__aenter__"
_CONSTRUCT = "MuseHost"
_SERVE = "serve"
_VERSION_FLAG = "--version"
_MIN_LIMIT = 1
_RUNNING_STATUS = "running"
_NOT_OPEN_NEXT_STEP = "Open the host with `async with` and call it inside the block."
_REENTER_NEXT_STEP = "Create a new host object for each `async with` block."
_AT_CAP_NEXT_STEP = "This host already runs its maximum number of live turns; wait for or interrupt one with interrupt_muse_turn, then retry."
_TURN_NOT_FOUND_NEXT_STEP = "The turn is not running; use continue_muse_session to send a new prompt."
_STALE_CURSOR_NEXT_STEP = "Call list_muse_sessions without a cursor to start again."
# The failure rows MuseLauncher.resolve can name at __aenter__ (EC-94, EC-95), with their messages.
_LAUNCHER_MESSAGES: Mapping[str, str] = MappingProxyType(
    {
        "wsl_unavailable": "Muse Code needs WSL on Windows: set MuseHostSettings.wsl_distro or muse_command, and make sure wsl.exe is installed.",
        "not_installed": "The muse executable was not found on PATH.",
    }
)


class MuseHost:
    """Drives the user's Muse Code in one workspace: live turns on their own MSP peers and short-lived peers for reads."""

    def __init__(self, settings: MuseHostSettings) -> None:
        self._errors = NativeErrorFactory(NativeHarness.MUSE)
        try:
            self._settings: MuseHostSettings = RecordFieldConverter.require_instance(settings, "settings", MuseHostSettings)
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=_CONSTRUCT) from exc
        self._launcher = MuseLauncher(settings)
        self._runner = CliRunner()
        self._turns = NativeTurnTable(NativeHarness.MUSE, max_live_turns=settings.max_live_turns, errors=self._errors)
        self._drivers: dict[str, MuseTurnDriver] = {}
        self._workspace_root = ""
        self._entered = False
        self._open = False

    async def __aenter__(self) -> MuseHost:
        # @intent muse-host-is-single-use-and-finds-muse-once
        # EC-3: a host serves exactly one async with block. D-19: the
        # launcher is found here, once, and in WSL mode the distro must be
        # listed by `wsl.exe -l -q` (EC-94); no muse process starts here.
        operation = _ENTER
        try:
            # A host serves one block only, open or already closed.
            if self._entered:
                raise self._errors.invalid_argument("host", "This MuseHost was already entered; a host serves one async with block.", operation=operation, next_step=_REENTER_NEXT_STEP)
            self._entered = True
            # Find how muse starts: an explicit command, wsl.exe with a distro, or muse on PATH.
            problem = self._launcher.resolve()
            if problem is not None:
                raise self._errors.build(self._errors.code(problem), _LAUNCHER_MESSAGES[problem], operation=operation)
            # In WSL mode the named distro must exist; the error lists the ones that do.
            if self._launcher.wsl_mode:
                distros = await self._launcher.list_distros()
                if self._settings.wsl_distro not in distros:
                    raise self._errors.build(self._errors.code("wsl_unavailable"), "wsl.exe does not list the configured distro.", operation=operation, context={"distros": self._errors.listing(distros)})
            # The workspace as muse sees it, translated to /mnt inside WSL.
            self._workspace_root = self._launcher.workspace_root()
            self._open = True
            return self
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        # @intent muse-host-exit-stops-every-turn
        # EC-8: refuse every later call, ask each live turn to stop as
        # HOST_CLOSED, then wait for the drivers, which close (and reap)
        # their peers within the grace period. It raises nothing of its own
        # and never suppresses the body's error.
        self._open = False
        drivers = list(self._drivers.values())
        tasks = self._turns.live_tasks()
        if not tasks:
            return None
        # Interrupt every live turn at once, so many turns cost no more than one.
        with contextlib.suppress(Exception):
            await asyncio.gather(*(driver.shut_down() for driver in drivers))
        # Each driver ends within the grace period and closes its own peer on the way out.
        await asyncio.wait(tasks)
        return None

    async def check_muse_ready(self) -> MuseReadiness:
        """Check the Muse Code version and the MSP handshake, and report how muse is launched."""
        operation = "check_muse_ready"
        try:
            self._require_open(operation)
            # Ask the launcher for its version first; an unreadable or too old release needs no peer (EC-103, EC-104).
            invocation = CliInvocation(
                argv=self._launcher.argv(_VERSION_FLAG),
                env=self._launcher.peer_environment(None),
                timeout_seconds=self._settings.control_timeout_seconds,
                max_output_bytes=native_host_constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            )
            outcome = await self._runner.run(invocation)
            # In WSL mode a failed run may name a missing distro or a missing in-distro muse (EC-94, EC-95).
            failure = self._launcher.launch_failure(outcome.stderr, outcome.exit_code, errors=self._errors, operation=operation)
            if failure is not None:
                raise failure
            version = MuseWire.read_cli_version(outcome, operation=operation)
            # Run the MSP handshake on a short-lived peer that is closed before the answer is built.
            peer = self._new_peer(None)
            try:
                await self._handshake(peer, operation)
            finally:
                await peer.close()
            # MSP 1.0.1 has no sign-in probe, so signed_in stays unknown (EC-105).
            return MuseReadiness(version=version, schema_version=native_host_constants.MUSE_SCHEMA_VERSION, signed_in=None, launcher=self._launcher.prefix, wsl_distro=self._settings.wsl_distro)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def list_muse_models(self) -> MuseModelCatalog:
        """List the models Muse Code offers; an empty list is not an error."""
        operation = "list_muse_models"
        try:
            self._require_open(operation)
            # A short-lived peer answers model/list and is closed before the catalog is returned.
            peer = self._new_peer(None)
            try:
                await self._handshake(peer, operation)
                result = await MuseWire.exchange(peer, "model/list", {}, operation=operation)
                return MuseWire.read_model_catalog(result, operation=operation)
            finally:
                await peer.close()
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def spawn_muse_session(self, request: MuseTurnRequest) -> NativeTurnHandle:
        """Start a new Muse session with one prompt and return the turn handle while the turn runs."""
        # @intent muse-spawn-returns-while-the-turn-runs
        # INV-11: the handle comes back once turn/start is accepted; the
        # turn's peer is closed and reaped on every path that does not reach
        # its driver, and the reservation is released with it.
        operation = "spawn_muse_session"
        try:
            # Refuse a bad request and a closed host before any I/O.
            self._require_open(operation)
            RecordFieldConverter.require_instance(request, "request", MuseTurnRequest)
            # Take a live-turn slot before the first await, so the cap holds under concurrency (EC-107).
            turn_id = self._reserve(None, operation)
            # The turn gets its own peer, marked in WSL mode so its in-distro tree can be reaped.
            mark = self._launcher.new_mark()
            peer = self._new_peer(mark)
            try:
                await self._handshake(peer, operation)
                # A named model must be one Muse offers, checked before any session exists (EC-108).
                await self._check_model(peer, request.model, operation)
                # Create the session; every approval it raises outside the user's own rules is denied (D-11).
                started = await MuseWire.exchange(peer, "session/start", MuseWire.session_start_params(self._workspace_root, request.model), operation=operation)
                session = MuseWire.read_session_result(started, operation=operation)
                self._turns.bind_session(turn_id, session.session_id)
                # Send the prompt; the ack's turnId names the turn from now on (EC-109).
                ack = await self._start_turn(peer, session.session_id, request, operation)
                # Hand the peer to a driver that runs the turn after this call returns.
                return self._launch(peer, mark, turn_id, session.session_id, ack, request, operation)
            except BaseException:
                self._turns.release(turn_id)
                await self._discard(peer, mark)
                raise
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def continue_muse_session(self, session_id: str, request: MuseTurnRequest) -> NativeTurnHandle:
        """Send one more prompt to an existing Muse session and return the turn handle while the turn runs."""
        # @intent muse-continue-reserves-the-session-first
        # EC-9: the session is reserved before the first await, so of two
        # concurrent continues on it exactly one reaches turn/start; the
        # other raises session_busy and starts no process.
        operation = "continue_muse_session"
        try:
            # Refuse bad arguments and a closed host before any I/O.
            self._require_open(operation)
            RecordFieldValidator.require_uuid(session_id, "session_id")
            RecordFieldConverter.require_instance(request, "request", MuseTurnRequest)
            # Reserve the session before the first await, so two calls on it cannot both pass (EC-9, EC-112).
            turn_id = self._reserve(session_id, operation)
            mark = self._launcher.new_mark()
            peer = self._new_peer(mark)
            try:
                await self._handshake(peer, operation)
                await self._check_model(peer, request.model, operation)
                # Load the session; one that is running a turn elsewhere is busy (EC-111, EC-112).
                await self._resume(peer, session_id, operation)
                ack = await self._start_turn(peer, session_id, request, operation)
                return self._launch(peer, mark, turn_id, session_id, ack, request, operation)
            except BaseException:
                self._turns.release(turn_id)
                await self._discard(peer, mark)
                raise
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def fork_muse_session(self, session_id: str, *, last_turn_id: str | None = None) -> MuseSession:
        """Copy a Muse session, whole or up to last_turn_id, into a new session and return the copy."""
        operation = "fork_muse_session"
        try:
            # Refuse bad arguments and a closed host before any I/O.
            self._require_open(operation)
            RecordFieldValidator.require_uuid(session_id, "session_id")
            if last_turn_id is not None:
                RecordFieldValidator.require_text(last_turn_id, "last_turn_id", max_chars=native_host_constants.NATIVE_ID_MAX_CHARS)
            # A session with a live turn on this host is not forked mid-turn (EC-112).
            if self._turns.is_session_busy(session_id):
                raise self._errors.build(self._errors.code("session_busy"), "The source session has a live turn on this host.", operation=operation, context={"session_id": session_id})
            # A short-lived peer forks the session, resuming it once if Muse has not loaded it (EC-114).
            peer = self._new_peer(None)
            try:
                await self._handshake(peer, operation)
                params = functools.partial(MuseWire.session_fork_params, session_id, last_turn_id)
                result = await MuseWire.exchange_loaded(peer, "session/fork", params, session_id, operation=operation)
                return MuseWire.read_session_result(result, operation=operation)
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

    async def list_muse_sessions(self, *, cursor: str | None = None, limit: int = native_host_constants.NATIVE_LIST_DEFAULT_LIMIT) -> MuseSessionPage:
        """List one page of this workspace's Muse sessions, with Muse's cursor for the next page."""
        operation = "list_muse_sessions"
        try:
            # Refuse bad arguments and a closed host before any I/O.
            self._require_open(operation)
            if cursor is not None:
                RecordFieldValidator.require_text(cursor, "cursor", max_chars=native_host_constants.NATIVE_CURSOR_MAX_CHARS)
            RecordFieldValidator.require_int(limit, "limit", minimum=_MIN_LIMIT, maximum=native_host_constants.NATIVE_LIST_MAX_LIMIT)
            # A short-lived peer reads the page; a cursor Muse no longer knows is refused as an argument.
            peer = self._new_peer(None)
            try:
                await self._handshake(peer, operation)
                return await self._list_page(peer, cursor, limit, operation)
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

    async def read_muse_session(self, session_id: str) -> MuseSession:
        """Read one Muse session's metadata without its items."""
        operation = "read_muse_session"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_uuid(session_id, "session_id")
            # A short-lived peer reads the session, resuming it once if Muse has not loaded it (EC-114).
            peer = self._new_peer(None)
            try:
                await self._handshake(peer, operation)
                params = functools.partial(MuseWire.session_read_params, session_id)
                result = await MuseWire.exchange_loaded(peer, "session/read", params, session_id, operation=operation)
                return MuseWire.read_session_result(result, operation=operation)
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

    async def page_muse_session(
        self,
        session_id: str,
        *,
        cursor: str | None = None,
        limit: int = native_host_constants.NATIVE_LIST_DEFAULT_LIMIT,
        direction: MuseViewDirection = MuseViewDirection.FORWARD,
    ) -> MusePage:
        """Read one page of a Muse session's view events as compact JSON."""
        operation = "page_muse_session"
        try:
            # Refuse bad arguments and a closed host before any I/O.
            self._require_open(operation)
            RecordFieldValidator.require_uuid(session_id, "session_id")
            if cursor is not None:
                RecordFieldValidator.require_text(cursor, "cursor", max_chars=native_host_constants.NATIVE_CURSOR_MAX_CHARS)
            RecordFieldValidator.require_int(limit, "limit", minimum=_MIN_LIMIT, maximum=native_host_constants.MUSE_PAGE_MAX_LIMIT)
            RecordFieldConverter.require_instance(direction, "direction", MuseViewDirection)
            # A short-lived peer reads the page, resuming the session once if Muse has not loaded it (EC-114).
            peer = self._new_peer(None)
            try:
                await self._handshake(peer, operation)
                params = functools.partial(MuseWire.view_page_params, session_id, cursor, limit, direction)
                result = await MuseWire.exchange_loaded(peer, "view/page", params, session_id, operation=operation)
                return MuseWire.read_view_page(session_id, result, operation=operation)
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

    async def steer_muse_turn(self, handle: NativeTurnHandle, text: str) -> NativeSteerResult:
        """Add text to a running Muse turn and return Muse's acceptance status."""
        operation = "steer_muse_turn"
        try:
            # Refuse bad arguments before looking the handle up (EC-1, EC-110).
            self._require_open(operation)
            RecordFieldValidator.require_text(text, "text", max_chars=native_host_constants.NATIVE_PROMPT_MAX_CHARS)
            RecordFieldConverter.require_instance(handle, "handle", NativeTurnHandle)
            task = self._turn_task(handle, operation)
            # Only a running turn can be steered; a finished one needs a new prompt (EC-115).
            driver = self._drivers.get(handle.turn_id)
            if task.done() or driver is None or not driver.running:
                raise self._errors.build(self._errors.code("turn_not_found"), "The turn has finished, so it cannot be steered.", operation=operation, next_step=_TURN_NOT_FOUND_NEXT_STEP)
            # Steer on the turn's own peer, naming the ack's turn id.
            ack = await self._steer(driver, text, operation)
            return NativeSteerResult(handle=handle, status=ack.status)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def interrupt_muse_turn(self, handle: NativeTurnHandle) -> NativeInterruptResult:
        """Ask a running Muse turn to stop and report whether it was still running."""
        operation = "interrupt_muse_turn"
        try:
            self._require_open(operation)
            RecordFieldConverter.require_instance(handle, "handle", NativeTurnHandle)
            task = self._turn_task(handle, operation)
            # A finished turn is left alone and nothing is sent (INV-13).
            driver = self._drivers.get(handle.turn_id)
            if task.done() or driver is None or not driver.running:
                return NativeInterruptResult(handle=handle, was_running=False)
            # turn/interrupt on the turn's own peer; the driver closes the peer after the grace period.
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

    async def wait_muse_turn(self, handle: NativeTurnHandle, *, timeout_seconds: float = native_host_constants.NATIVE_WAIT_DEFAULT_SECONDS) -> NativeTurnResult:
        """Wait up to timeout_seconds for a Muse turn's result; a timed-out wait leaves the turn running."""
        operation = "wait_muse_turn"
        try:
            self._require_open(operation)
            seconds = RecordFieldValidator.require_number(timeout_seconds, "timeout_seconds", maximum=native_host_constants.NATIVE_WAIT_MAX_SECONDS)
            RecordFieldConverter.require_instance(handle, "handle", NativeTurnHandle)
            task = self._turn_task(handle, operation)
            # Wait without cancelling the driver, so a timed-out or cancelled wait never stops the turn (INV-12).
            done, _pending = await asyncio.wait({task}, timeout=seconds)
            if not done:
                raise self._errors.build(self._errors.code("turn_timed_out"), "The turn is still running after timeout_seconds.", operation=operation, context={"session_id": handle.session_id})
            # A driver that was cancelled recorded no outcome; report its peer as gone rather than cancelling the caller.
            if task.cancelled():
                raise self._errors.build(self._errors.code("process_exited"), "The turn's driver stopped before the turn completed.", operation=operation, context={"reason": "cancelled"})
            # The recorded result, or the turn's failure row, the same on every wait (EC-148).
            return task.result()
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def track_muse_session_usage(self, session_id: str) -> NativeSessionUsage:
        """Report a Muse session's latest cumulative token usage, read from its view backward (D-14)."""
        operation = "track_muse_session_usage"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_uuid(session_id, "session_id")
            # A short-lived peer pages the view backward until it finds a usage event or reaches the page limit.
            peer = self._new_peer(None)
            try:
                await self._handshake(peer, operation)
                totals, truncated = await self._latest_usage(peer, session_id, operation)
            finally:
                await peer.close()
            # Muse reports no cost, so cost_usd stays None (NG-14).
            return NativeSessionUsage(harness=NativeHarness.MUSE, session_id=session_id, totals=totals, truncated=truncated)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    def _require_open(self, operation: str) -> None:
        # EC-2: calls are served only inside the async with block.
        if not self._open:
            raise self._errors.build(self._errors.code("process_exited"), "This MuseHost is not open.", operation=operation, next_step=_NOT_OPEN_NEXT_STEP)

    def _reserve(self, session_id: str | None, operation: str) -> str:
        # The turn table's reservation; at the live-turn cap the error names the EC-107 next step.
        try:
            return self._turns.reserve(session_id, operation=operation)
        except NativeHostError as exc:
            if "live_turns" not in exc.context:
                raise
            raise self._errors.build(exc.failure_code, exc.message, operation=operation, next_step=_AT_CAP_NEXT_STEP, context=exc.context) from exc

    def _turn_task(self, handle: NativeTurnHandle, operation: str) -> asyncio.Task[NativeTurnResult]:
        # The driver task of a handle this host issued; any other handle is EC-115 with its own next step.
        try:
            return self._turns.lookup(handle, operation=operation)
        except NativeHostError as exc:
            raise self._errors.build(exc.failure_code, exc.message, operation=operation, next_step=_TURN_NOT_FOUND_NEXT_STEP) from exc

    def _new_peer(self, mark: str | None) -> NativePeer:
        # `<launcher> serve` with the caller's environment plus, for a WSL turn peer, its mark (D-18, D-23).
        return NativePeer(self._launcher.argv(_SERVE), env=self._launcher.peer_environment(mark), control_timeout_seconds=self._settings.control_timeout_seconds, errors=self._errors)

    async def _handshake(self, peer: NativePeer, operation: str) -> None:
        # @intent muse-peer-handshake-before-any-request
        # Start the peer, send initialize with clientInfo, check the schema
        # and server version (EC-98, EC-99), then send `initialized` before
        # any other request. A WSL peer that exits before answering may say
        # why on stderr: a missing distro or a missing muse (EC-94, EC-95).
        try:
            await peer.start(operation=operation)
            result = await MuseWire.exchange(peer, "initialize", MuseWire.initialize_params(), operation=operation)
            MuseWire.read_server_version(result, operation=operation)
            await peer.notify("initialized", {}, operation=operation)
        except NativeHostError as exc:
            if exc.failure_code is not FailureCode.MUSE_PROCESS_EXITED:
                raise
            await peer.close()
            failure = self._launcher.launch_failure(peer.stderr_tail(), None, errors=self._errors, operation=operation)
            if failure is None:
                raise
            raise failure from exc

    async def _check_model(self, peer: NativePeer, model: str | None, operation: str) -> None:
        # EC-108: a named model must be in model/list; an empty list cannot
        # refuse anything, so the id passes through to Muse (A-12).
        if model is None:
            return
        result = await MuseWire.exchange(peer, "model/list", {}, operation=operation)
        offered = [entry.model_id for entry in MuseWire.read_model_catalog(result, operation=operation).models]
        if offered and model not in offered:
            raise self._errors.build(self._errors.code("model_unknown"), "Muse Code does not offer the requested model.", operation=operation, context={"available_models": self._errors.listing(offered)})

    async def _resume(self, peer: NativePeer, session_id: str, operation: str) -> None:
        # session/resume loads the session; one that is running a turn for another client is busy (EC-112).
        result = await MuseWire.exchange(peer, "session/resume", MuseWire.session_resume_params(session_id), operation=operation)
        session = MuseWire.read_session_result(result, operation=operation)
        if session.status == _RUNNING_STATUS or session.active_turn_id is not None:
            raise self._errors.build(self._errors.code("session_busy"), "The Muse session is running a turn for another client.", operation=operation, context={"session_id": session_id, "status": session.status})

    async def _start_turn(self, peer: NativePeer, session_id: str, request: MuseTurnRequest, operation: str) -> MuseTurnAck:
        # turn/start with one text part; a prompt Muse finds too large is refused as the prompt argument (EC-101).
        result = await MuseWire.exchange(peer, "turn/start", MuseWire.turn_start_params(session_id, request.prompt, request.reasoning_effort), operation=operation)
        return MuseWire.parse_turn_start_result(result, operation=operation)

    def _launch(self, peer: NativePeer, mark: str | None, turn_id: str, session_id: str, ack: MuseTurnAck, request: MuseTurnRequest, operation: str) -> NativeTurnHandle:
        # @intent muse-host-hands-the-peer-to-a-driver
        # The driver owns the peer from here: it runs the turn as a task the
        # turn table owns and closes (and reaps) the peer when the turn ends.
        # A host that closed while the turn was starting runs no driver.
        if not self._open:
            raise self._errors.build(self._errors.code("process_exited"), "This MuseHost closed while the turn was starting.", operation=operation, next_step=_NOT_OPEN_NEXT_STEP)
        handle = NativeTurnHandle(harness=NativeHarness.MUSE, session_id=session_id, turn_id=turn_id)
        closer = functools.partial(self._discard, peer, mark)
        driver = MuseTurnDriver(peer, handle=handle, ack=ack, max_turn_seconds=request.max_turn_seconds, errors=self._errors, closer=closer)
        task = asyncio.create_task(driver.run(), name=f"muse-turn-{turn_id}")
        self._drivers[turn_id] = driver
        task.add_done_callback(functools.partial(self._forget_driver, turn_id))
        return self._turns.activate(turn_id, task)

    async def _list_page(self, peer: NativePeer, cursor: str | None, limit: int, operation: str) -> MuseSessionPage:
        # session/list; -32602 for a call that sent a cursor means the cursor went stale.
        try:
            result = await peer.call("session/list", MuseWire.session_list_params(self._workspace_root, cursor, limit), operation=operation)
        except McpProtocolError as exc:
            if cursor is not None and MuseWire.is_stale_cursor(exc):
                raise self._errors.invalid_argument("cursor", "cursor is no longer valid for this session list.", operation=operation, next_step=_STALE_CURSOR_NEXT_STEP) from exc
            raise MuseWire.vendor_failure(exc, operation=operation) from exc
        return MuseWire.read_session_page(result, operation=operation)

    async def _steer(self, driver: MuseTurnDriver, text: str, operation: str) -> MuseTurnAck:
        # turn/steer naming the ack's turn. A -32030 refusal is turn_not_found
        # only when the turn has finished here too (EC-115); while the turn
        # still runs locally it is a vendor error like any other (EC-102).
        try:
            result = await driver.peer.call("turn/steer", MuseWire.turn_steer_params(driver.session_id, driver.turn_id, text), operation=operation)
        except McpProtocolError as exc:
            if MuseWire.is_command_rejected(exc) and not driver.running:
                raise self._errors.build(self._errors.code("turn_not_found"), "Muse refused the steer because the turn is no longer running.", operation=operation, next_step=_TURN_NOT_FOUND_NEXT_STEP) from exc
            raise MuseWire.vendor_failure(exc, operation=operation) from exc
        return MuseWire.parse_turn_steer_result(result, operation=operation)

    async def _latest_usage(self, peer: NativePeer, session_id: str, operation: str) -> tuple[NativeTokenUsage | None, bool]:
        # D-14: page the view backward, MUSE_PAGE_MAX_LIMIT events at a time,
        # until a page holds a session/tokenUsage event or the history ends.
        # Returns the usage and whether MUSE_USAGE_MAX_PAGES stopped the search.
        cursor: str | None = None
        for _page in range(native_host_constants.MUSE_USAGE_MAX_PAGES):
            params = functools.partial(MuseWire.view_page_params, session_id, cursor, native_host_constants.MUSE_PAGE_MAX_LIMIT, MuseViewDirection.BACKWARD)
            result = await MuseWire.exchange_loaded(peer, "view/page", params, session_id, operation=operation)
            usage = MuseWire.read_latest_usage(result, operation=operation)
            cursor = MuseWire.read_view_page(session_id, result, operation=operation).next_cursor
            if usage is not None or cursor is None:
                return usage, False
        return None, True

    async def _discard(self, peer: NativePeer, mark: str | None) -> None:
        # @intent muse-turn-peer-close-and-reap
        # D-23: close a turn peer, then, in WSL mode, kill whatever its mark
        # left running inside the distro. Closing runs on error and cancel
        # paths, so a failed reap is never raised.
        await peer.close()
        if mark is not None:
            with contextlib.suppress(Exception):
                await self._launcher.reap(mark)

    def _forget_driver(self, turn_id: str, _task: asyncio.Task[NativeTurnResult]) -> None:
        # A finished driver is dropped; its task stays in the turn table for later waits.
        self._drivers.pop(turn_id, None)


__all__ = ["MuseHost"]
