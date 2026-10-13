"""FILE: vidbyte/harnesses/native/opencode/host.py

PURPOSE: Defines OpencodeHost, the async context manager that drives opencode through its HTTP server: readiness, models, providers and auth methods, session spawn, continue, fork, revert and unrevert, session and message reads, diffs, turn wait and interrupt, usage, and MCP server registration (the 18 functions of §8.5).
ROLE IN CODEBASE: Exported by vidbyte/harnesses/native/opencode/__init__.py and wrapped one tool per function by vidbyte/tools/builtins/opencode/. Composes OpencodeServer (the owned or attached server), OpencodeClient (every HTTP call), OpencodeWire (bodies and records) and OpencodeTurnWatcher (one per turn), with NativeErrorFactory and NativeTurnTable from hostkit.
ARCHITECTURE NOTE: Each public method is a narrated main function with one try: CancelledError and NativeHostError pass through, a ConfigurationError from a primitive argument check becomes configuration.invalid_argument, and anything else becomes runtime.error naming only the class (INV-1, INV-2). Every argument is checked before any I/O (EC-1); spawn and continue reserve their session and live-turn slot before their first await and release them on any failure (EC-9). A host is used once (EC-2, EC-3).
FUNCTION INVENTORY: __aenter__ starts or attaches the server and checks its health; __aexit__ interrupts live turns and stops the owned server; the 18 public methods; mcp_servers exposes the registered MCP configs to the add tool. Helpers: _require_open, _check_health, _reserve, _require_idle, _check_model, _newest_message_id, _watcher, _drive, _forget, _abandon and _close_turn.
COMMON MODIFICATION PATTERNS: A new function is one more public method with the same try shape, a new route in OpencodeClient call sites, its record parser in OpencodeWire and its tool in vidbyte/tools/builtins/opencode/.
WHAT NOT TO DO IN THIS FILE: 1. Do not send a request before the method's argument checks pass; opencode answers 500 for malformed ids. 2. Do not await between a busy check and the reservation it guards. 3. Do not answer a permission with anything but reject, or send an allow-everything rule (INV-9). 4. Do not restart a dead owned server (EC-153).
KNOWN EDGE CASES: POST …/abort answers 200 for a missing session and GET …/diff answers 200 [] for one, so both are preceded by GET /session/{id}. A cancelled spawn or continue that may already have sent its prompt aborts that turn before propagating (EC-4). A wait that times out or is cancelled never touches the turn (INV-12).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.2, §6.3.4, §8.5 (OpencodeHost), FR-2, INV-1 to INV-17
TESTS: tests/features/opencode_host/
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
from collections.abc import Mapping
from types import TracebackType

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeTurnTable
from vidbyte.harnesses.native.opencode.client import OpencodeClient
from vidbyte.harnesses.native.opencode.server import OpencodeServer
from vidbyte.harnesses.native.opencode.turn import OpencodeTurnWatcher
from vidbyte.harnesses.native.opencode.wire import OpencodeWire
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.native_hosts import (
    NativeInterruptResult,
    NativeMessageUsage,
    NativeSessionUsage,
    NativeTurnHandle,
    NativeTurnResult,
)
from vidbyte.lib.dataclasses.opencode import (
    OpencodeFileDiff,
    OpencodeHostSettings,
    OpencodeMcpServerConfig,
    OpencodeMcpStatus,
    OpencodeMessage,
    OpencodeMessagePage,
    OpencodeModel,
    OpencodePromptRequest,
    OpencodeProvider,
    OpencodeProviderAuth,
    OpencodeReadiness,
    OpencodeSession,
    OpencodeSpawnRequest,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import InterruptSource, NativeHarness
from vidbyte.lib.errors import ConfigurationError, NativeHostError

_OPEN_STEP = "Open the host with async with and call it inside the block."
_NEW_HOST_STEP = "Create a new host object for each async with block."
_LIVE_TURN_CAP_STEP = "This host already runs its maximum number of live turns; wait for or interrupt one with interrupt_opencode_turn, then retry."
_NO_PROVIDER_STEP = "Connect a provider with opencode auth login."
_PROVIDER_PICK_STEP = "Pick a provider id returned by list_opencode_providers."
_LIVE_TURNS_KEY = "live_turns"
_PROVIDER_ID_MAX_CHARS = 64
_PROVIDER_ID_PATTERN = r"^[^/]+$"
_MIN_LIST_LIMIT = 1
_TRUNCATION_PROBE = 1
_NEWEST_ONE = "1"
_OLDEST_INDEX = 0
_MODEL_ID_SPLITS = 1
_BUSY_STATES = frozenset({"busy", "retry"})
_FAILED_MCP_STATES = frozenset({"failed", "needs_auth", "needs_client_registration", "disabled"})
_ASSISTANT_ROLE = "assistant"
_WAIT_OPERATION = "wait_opencode_turn"
_EXIT_OPERATION = "__aexit__"


class OpencodeHost:
    """Drives opencode through its HTTP server: sessions, turns, reads, usage and MCP servers, inside one async with block."""

    def __init__(self, settings: OpencodeHostSettings) -> None:
        # @intent opencode-host-registers-injected-secrets
        # Building a host starts nothing and sends nothing (EC-1). Every value
        # the host may inject (MCP environment and header values, the attached
        # server password) is registered before any call, so vendor text that
        # echoes one is scrubbed to <redacted> on every path (INV-6, AC-2).
        RecordFieldConverter.require_instance(settings, "settings", OpencodeHostSettings)
        self._settings = settings
        self._errors = NativeErrorFactory(NativeHarness.OPENCODE)
        self._wire = OpencodeWire(self._errors)
        self._server = OpencodeServer(settings, self._errors)
        self._client = OpencodeClient(server=self._server, workspace=settings.workspace, request_timeout_seconds=settings.request_timeout_seconds, errors=self._errors)
        self._turns = NativeTurnTable(NativeHarness.OPENCODE, max_live_turns=settings.max_live_turns, errors=self._errors)
        self._watchers: dict[str, OpencodeTurnWatcher] = {}
        self._server_url = ""
        self._entered = False
        self._open = False
        # Every value the host may inject is scrubbed from vendor text (INV-6).
        for config in settings.mcp_servers.values():
            for value in (*config.environment.values(), *config.headers.values()):
                self._errors.register_secret(value)
        if settings.server_password is not None:
            self._errors.register_secret(settings.server_password)

    @property
    def mcp_servers(self) -> Mapping[str, OpencodeMcpServerConfig]:
        # @intent opencode-mcp-registry-is-developer-owned
        # The MCP servers the developer registered, read-only; the add tool
        # looks a model-given name up here and never builds a config from
        # model text, so no command, URL or header comes from a model (T-2).
        return self._settings.mcp_servers

    async def __aenter__(self) -> OpencodeHost:
        operation = "__aenter__"
        # A host is used once, whether it is open or already closed (EC-3).
        if self._entered:
            raise self._errors.build(FailureCode.CONFIGURATION_INVALID_ARGUMENT, "This OpencodeHost was already entered; a host is used for one async with block.", operation=operation, next_step=_NEW_HOST_STEP)
        self._entered = True
        try:
            # Start the owned server, or take the attached address, and remember the credentials for every call.
            base_url, credentials = await self._server.start(operation=operation)
            self._client.connect(base_url, credentials)
            self._server_url = base_url

            # The server must be healthy and new enough before the host opens (EC-55, EC-60).
            await self._check_health(operation=operation)
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
        finally:
            # A failed or cancelled enter stops and reaps what it started; the host stays closed (EC-2).
            if not self._open:
                await self._server.stop()

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        # @intent opencode-host-exit-interrupts-and-stops
        # Later calls see a closed host (EC-2). Every live turn is aborted as
        # HOST_CLOSED and given NATIVE_STOP_GRACE_SECONDS to settle, stragglers
        # are cancelled, and the owned server is stopped and reaped on every
        # path. Nothing but cancellation is raised and the body's exception
        # is never suppressed (EC-8).
        self._open = False
        try:
            # Abort every live turn at once, and let the turns settle within the grace.
            closers = [asyncio.create_task(self._close_turn(watcher)) for watcher in list(self._watchers.values())]
            pending = {*closers, *self._turns.live_tasks()}
            if pending:
                _settled, late = await asyncio.wait(pending, timeout=native_host_constants.NATIVE_STOP_GRACE_SECONDS)
                for task in late:
                    task.cancel()
                if late:
                    await asyncio.wait(late, timeout=native_host_constants.NATIVE_KILL_WAIT_SECONDS)
        finally:
            # Stop and reap the owned server; an attached server is left running.
            await self._server.stop()

    async def check_opencode_ready(self) -> OpencodeReadiness:
        # @intent opencode-ready-needs-a-connected-provider
        # Readiness means a healthy, supported server with at least one
        # connected provider; with none, no turn can run, so it is reported
        # as not signed in with the login step rather than as ready (EC-63).
        operation = "check_opencode_ready"
        try:
            self._require_open(operation)

            # The server must be healthy and new enough (EC-55, EC-60).
            version = await self._check_health(operation=operation)

            # With no connected provider no turn can run (EC-63).
            body = await self._client.call("GET", ("provider",), operation=operation)
            readiness = self._wire.parse_readiness(body, version=version, server_url=self._server_url, operation=operation)
            if not readiness.connected_providers:
                raise self._errors.build(FailureCode.OPENCODE_NOT_SIGNED_IN, "The opencode server has no connected model provider.", operation=operation, next_step=_NO_PROVIDER_STEP)
            return readiness
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def list_opencode_models(self, provider_id: str | None = None) -> tuple[OpencodeModel, ...]:
        # @intent opencode-models-come-from-connected-providers
        # Only connected providers can serve a turn, so models come from
        # GET /config/providers; an unknown provider id is model_unknown with
        # the offered ids, never an empty list that looks like success (EC-65).
        operation = "list_opencode_models"
        try:
            self._require_open(operation)
            # A provider id is one path-free name (EC-64).
            if provider_id is not None:
                RecordFieldValidator.require_text(provider_id, "provider_id", max_chars=_PROVIDER_ID_MAX_CHARS, pattern=_PROVIDER_ID_PATTERN)

            # GET /config/providers lists only the connected providers and their models.
            catalog = self._wire.parse_config_providers(await self._client.call("GET", ("config", "providers"), operation=operation), operation=operation)
            if provider_id is None:
                return tuple(model for models in catalog.values() for model in models)

            # A provider the server does not offer is model_unknown with the offered ids (EC-65).
            if provider_id not in catalog:
                raise self._errors.build(FailureCode.OPENCODE_MODEL_UNKNOWN, "The opencode server has no connected provider with that id.", operation=operation, next_step=_PROVIDER_PICK_STEP, context={"available_providers": self._errors.listing(catalog)})
            return catalog[provider_id]
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def list_opencode_providers(self) -> tuple[OpencodeProvider, ...]:
        operation = "list_opencode_providers"
        try:
            self._require_open(operation)
            # GET /provider lists every known provider; keys and options are never read (INV-6).
            body = await self._client.call("GET", ("provider",), operation=operation)
            return self._wire.parse_providers(body, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def get_opencode_provider_auth(self) -> tuple[OpencodeProviderAuth, ...]:
        # @intent opencode-provider-auth-is-read-only
        # Only the catalogue of auth methods is read; nothing is connected
        # or stored, and the open set of method types is copied verbatim.
        operation = "get_opencode_provider_auth"
        try:
            self._require_open(operation)
            # GET /provider/auth maps each provider to its auth methods, copied verbatim.
            body = await self._client.call("GET", ("provider", "auth"), operation=operation)
            return self._wire.parse_provider_auth(body, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def spawn_opencode_session(self, request: OpencodeSpawnRequest) -> NativeTurnHandle:
        # @intent opencode-spawn-reserves-before-any-io
        # The live-turn slot is taken before the first await and released on
        # every path that does not start the turn (EC-9); the session carries
        # only the caller's rules (D-11); a cancel after the prompt may have
        # been sent aborts that turn, since no caller could reach it (EC-4).
        operation = "spawn_opencode_session"
        turn_id: str | None = None
        session_id: str | None = None
        prompt_sent = False
        activated = False
        try:
            self._require_open(operation)
            RecordFieldConverter.require_instance(request, "request", OpencodeSpawnRequest)

            # Take a live-turn slot before the first await, so concurrent spawns cannot pass the cap (EC-9, EC-67).
            turn_id = self._reserve(None, operation=operation)

            # Check the model against the connected providers before anything is created (EC-68).
            await self._check_model(request.turn.model, operation=operation)

            # Create the session with its title and the caller's permission rules only (D-11, EC-69).
            created = await self._client.call("POST", ("session",), operation=operation, body=OpencodeWire.session_body(request))
            session_id = self._wire.parse_session(created, operation=operation).session_id
            self._turns.bind_session(turn_id, session_id)

            # Send the prompt; a new session has no earlier messages to skip (EC-70, EC-72).
            watcher = self._watcher(turn_id, session_id, request.turn, snapshot_id=None)
            prompt_sent = True
            await self._client.call("POST", ("session", session_id, "prompt_async"), operation=operation, body=OpencodeWire.prompt_body(request.turn), not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND, context={"session_id": session_id})

            # Hand the watcher to the turn table and return the handle while the turn runs (INV-11).
            driver = asyncio.create_task(self._drive(watcher), name="opencode-turn")
            handle = self._turns.activate(turn_id, driver)
            activated = True
            self._watchers[turn_id] = watcher
            driver.add_done_callback(functools.partial(self._forget, turn_id))
            return handle
        except asyncio.CancelledError:
            # The caller can never reach a turn whose prompt may already be on the server, so abort it (EC-4).
            if prompt_sent and not activated and session_id is not None:
                await self._abandon(session_id, operation=operation)
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc
        finally:
            # A spawn that did not start its turn frees the slot it took (EC-9).
            if turn_id is not None and not activated:
                self._turns.release(turn_id)

    async def continue_opencode_session(self, session_id: str, request: OpencodePromptRequest) -> NativeTurnHandle:
        # @intent opencode-continue-reserves-the-session
        # The session and a slot are reserved before the first await, so two
        # continues on one session cannot both pass (EC-9, EC-73); the newest
        # message id is taken before the prompt so an earlier turn's reply is
        # never read as this turn's; a cancel after sending aborts it (EC-4).
        operation = "continue_opencode_session"
        turn_id: str | None = None
        prompt_sent = False
        activated = False
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)
            RecordFieldConverter.require_instance(request, "request", OpencodePromptRequest)

            # Reserve the session and a slot before the first await, so two continues cannot both pass (EC-9, EC-73).
            turn_id = self._reserve(session_id, operation=operation)

            # The session must exist (EC-72), must not be busy on the server (EC-73), and the model must be offered (EC-68).
            await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            await self._require_idle(session_id, operation=operation, include_local=False)
            await self._check_model(request.model, operation=operation)

            # Remember the newest message, so a reply to an earlier turn is never taken for this one (§8.5 step 1).
            snapshot_id = await self._newest_message_id(session_id, operation=operation)

            # Send the prompt; a 404 now means the session was deleted after the check (EC-70, EC-72).
            watcher = self._watcher(turn_id, session_id, request, snapshot_id=snapshot_id)
            prompt_sent = True
            await self._client.call("POST", ("session", session_id, "prompt_async"), operation=operation, body=OpencodeWire.prompt_body(request), not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND, context={"session_id": session_id})

            # Hand the watcher to the turn table and return the handle while the turn runs (INV-11).
            driver = asyncio.create_task(self._drive(watcher), name="opencode-turn")
            handle = self._turns.activate(turn_id, driver)
            activated = True
            self._watchers[turn_id] = watcher
            driver.add_done_callback(functools.partial(self._forget, turn_id))
            return handle
        except asyncio.CancelledError:
            # The caller can never reach a turn whose prompt may already be on the server, so abort it (EC-4).
            if prompt_sent and not activated:
                await self._abandon(session_id, operation=operation)
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc
        finally:
            # A continue that did not start its turn frees its session and slot (EC-9).
            if turn_id is not None and not activated:
                self._turns.release(turn_id)

    async def fork_opencode_session(self, session_id: str, message_id: str | None = None) -> OpencodeSession:
        operation = "fork_opencode_session"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)
            RecordFieldValidator.require_optional_text(message_id, "message_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_MESSAGE_ID_PATTERN)

            # The session must exist (EC-72) and have no running turn here or on the server (EC-73).
            await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            await self._require_idle(session_id, operation=operation, include_local=True)

            # A fork point must be a message of this session (EC-75).
            if message_id is not None:
                await self._client.call("GET", ("session", session_id, "message", message_id), operation=operation, not_found=FailureCode.OPENCODE_MESSAGE_NOT_FOUND)

            # Fork; a 404 here means the session was deleted after the check (EC-76).
            body: dict[str, object] = {} if message_id is None else {"messageID": message_id}
            forked = await self._client.call("POST", ("session", session_id, "fork"), operation=operation, body=body, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            return self._wire.parse_session(forked, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def revert_opencode_session(self, session_id: str, message_id: str, part_id: str | None = None) -> OpencodeSession:
        operation = "revert_opencode_session"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)
            RecordFieldValidator.require_text(message_id, "message_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_MESSAGE_ID_PATTERN)
            RecordFieldValidator.require_optional_text(part_id, "part_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_PART_ID_PATTERN)

            # The session must exist (EC-72), be idle here and on the server (EC-78), and hold the message (EC-75).
            await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            await self._require_idle(session_id, operation=operation, include_local=True)
            await self._client.call("GET", ("session", session_id, "message", message_id), operation=operation, not_found=FailureCode.OPENCODE_MESSAGE_NOT_FOUND)

            # Revert; a 409 SessionBusyError is session_busy (EC-78) and the vendor's revert block comes back (EC-79).
            body: dict[str, object] = {"messageID": message_id} if part_id is None else {"messageID": message_id, "partID": part_id}
            reverted = await self._client.call("POST", ("session", session_id, "revert"), operation=operation, body=body, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND, conflict=FailureCode.OPENCODE_SESSION_BUSY)
            return self._wire.parse_session(reverted, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def unrevert_opencode_session(self, session_id: str) -> OpencodeSession:
        operation = "unrevert_opencode_session"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)

            # The session must exist (EC-72) and be idle here and on the server (EC-78).
            await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            await self._require_idle(session_id, operation=operation, include_local=True)

            # Unrevert; with nothing to restore the session comes back unchanged (A-7).
            restored = await self._client.call("POST", ("session", session_id, "unrevert"), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND, conflict=FailureCode.OPENCODE_SESSION_BUSY)
            return self._wire.parse_session(restored, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def list_opencode_sessions(self, limit: int = native_host_constants.NATIVE_LIST_DEFAULT_LIMIT) -> tuple[OpencodeSession, ...]:
        operation = "list_opencode_sessions"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_int(limit, "limit", minimum=_MIN_LIST_LIMIT, maximum=native_host_constants.NATIVE_LIST_MAX_LIMIT)

            # The server returns at most `limit` sessions, so a long history stays under the body cap.
            body = await self._client.call("GET", ("session",), operation=operation, query={"limit": str(limit)})

            # Sort by last update, newest first, whatever order the server used.
            sessions = self._wire.parse_sessions(body, operation=operation)
            return tuple(sorted(sessions, key=lambda session: session.updated_ms, reverse=True))
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def get_opencode_session(self, session_id: str) -> OpencodeSession:
        operation = "get_opencode_session"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)

            # One Session object; a 404 means the session is not on this server (EC-72).
            body = await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            return self._wire.parse_session(body, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def get_opencode_session_messages(self, session_id: str, limit: int = native_host_constants.NATIVE_LIST_DEFAULT_LIMIT, before: str | None = None) -> OpencodeMessagePage:
        operation = "get_opencode_session_messages"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)
            RecordFieldValidator.require_int(limit, "limit", minimum=_MIN_LIST_LIMIT, maximum=native_host_constants.NATIVE_LIST_MAX_LIMIT)
            RecordFieldValidator.require_optional_text(before, "before", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_MESSAGE_ID_PATTERN)

            # Read one page back from `before`; a 404 means the session is not on this server (EC-72).
            query = {"limit": str(limit)} if before is None else {"limit": str(limit), "before": before}
            body = await self._client.call("GET", ("session", session_id, "message"), operation=operation, query=query, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            messages = self._wire.parse_messages(body, operation=operation)

            # A full page offers its oldest id to page further back.
            next_before = messages[_OLDEST_INDEX].message_id if messages and len(messages) >= limit else None
            return OpencodeMessagePage(session_id=session_id, messages=messages, next_before=next_before)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def get_opencode_message(self, session_id: str, message_id: str) -> OpencodeMessage:
        operation = "get_opencode_message"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)
            RecordFieldValidator.require_text(message_id, "message_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_MESSAGE_ID_PATTERN)

            # The session first, because a missing session and a missing message both answer 404 (EC-72, EC-75).
            await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            body = await self._client.call("GET", ("session", session_id, "message", message_id), operation=operation, not_found=FailureCode.OPENCODE_MESSAGE_NOT_FOUND)
            return self._wire.parse_message(body, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def get_opencode_session_diff(self, session_id: str, message_id: str | None = None) -> tuple[OpencodeFileDiff, ...]:
        operation = "get_opencode_session_diff"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)
            RecordFieldValidator.require_optional_text(message_id, "message_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_MESSAGE_ID_PATTERN)

            # The diff route answers 200 [] for a missing session or message, so both are checked first (EC-72, EC-75).
            await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
            if message_id is not None:
                await self._client.call("GET", ("session", session_id, "message", message_id), operation=operation, not_found=FailureCode.OPENCODE_MESSAGE_NOT_FOUND)

            # Read the diff; long patches are cut at OPENCODE_PATCH_MAX_CHARS.
            query = {} if message_id is None else {"messageID": message_id}
            body = await self._client.call("GET", ("session", session_id, "diff"), operation=operation, query=query)
            return self._wire.parse_diffs(body, operation=operation)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def wait_opencode_turn(self, handle: NativeTurnHandle, timeout_seconds: float = native_host_constants.NATIVE_WAIT_DEFAULT_SECONDS) -> NativeTurnResult:
        operation = _WAIT_OPERATION
        try:
            self._require_open(operation)
            RecordFieldConverter.require_instance(handle, "handle", NativeTurnHandle)
            RecordFieldValidator.require_number(timeout_seconds, "timeout_seconds", maximum=native_host_constants.NATIVE_WAIT_MAX_SECONDS)

            # Only a handle this host issued is found, live or recently finished (EC-80).
            driver = self._turns.lookup(handle, operation=operation)

            # Wait without ever touching the turn: a timeout or a cancelled wait leaves it running (EC-81, INV-12).
            done, _running = await asyncio.wait({driver}, timeout=timeout_seconds)
            if not done:
                raise self._errors.build(FailureCode.OPENCODE_TURN_TIMED_OUT, "The turn is still running at the end of the wait.", operation=operation)

            # A turn cut off while the host closed has no outcome of its own.
            if driver.cancelled():
                raise self._errors.build(FailureCode.OPENCODE_PROCESS_EXITED, "The host closed before this turn reported its end.", operation=operation, next_step=_OPEN_STEP)

            # The result, or the turn's recorded failure, the same on every wait (EC-148).
            return driver.result()
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def interrupt_opencode_turn(self, handle: NativeTurnHandle) -> NativeInterruptResult:
        operation = "interrupt_opencode_turn"
        try:
            self._require_open(operation)
            RecordFieldConverter.require_instance(handle, "handle", NativeTurnHandle)

            # Only a handle this host issued is found (EC-80); a finished turn was not running (INV-13).
            driver = self._turns.lookup(handle, operation=operation)
            watcher = self._watchers.get(handle.turn_id)
            if driver.done() or watcher is None:
                return NativeInterruptResult(handle=handle, was_running=False)

            # Abort answers 200 even for a missing session, so check the session first (EC-90).
            if not await self._client.probe(("session", handle.session_id), operation=operation):
                watcher.fail(self._errors.build(FailureCode.OPENCODE_SESSION_NOT_FOUND, "The turn's session was deleted while the turn ran.", operation=_WAIT_OPERATION))
                raise self._errors.build(FailureCode.OPENCODE_SESSION_NOT_FOUND, "The turn's session no longer exists on this server.", operation=operation)

            # Send the abort with the CALLER source; the watcher ends the turn INTERRUPTED (EC-88).
            await watcher.interrupt(InterruptSource.CALLER, operation=operation)
            return NativeInterruptResult(handle=handle, was_running=True)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def track_opencode_session_usage(self, session_id: str) -> NativeSessionUsage:
        operation = "track_opencode_session_usage"
        try:
            self._require_open(operation)
            RecordFieldValidator.require_text(session_id, "session_id", max_chars=native_host_constants.NATIVE_SESSION_ID_MAX_CHARS, pattern=native_host_constants.OPENCODE_SESSION_ID_PATTERN)

            # The totals come from the Session object itself (D-14, EC-72).
            session = self._wire.parse_session(await self._client.call("GET", ("session", session_id), operation=operation, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND), operation=operation)

            # Read one message past the limit, so a longer history is reported as truncated.
            limit = native_host_constants.OPENCODE_TURN_MESSAGE_LIMIT
            query = {"limit": str(limit + _TRUNCATION_PROBE)}
            messages = self._wire.parse_messages(await self._client.call("GET", ("session", session_id, "message"), operation=operation, query=query, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND), operation=operation)

            # Each assistant message that reported usage, newest OPENCODE_TURN_MESSAGE_LIMIT messages only.
            per_message = tuple(NativeMessageUsage(message_id=message.message_id, usage=message.usage) for message in messages[-limit:] if message.role == _ASSISTANT_ROLE and message.usage is not None)
            return NativeSessionUsage(harness=NativeHarness.OPENCODE, session_id=session.session_id, totals=session.usage, per_message=per_message, truncated=len(messages) > limit)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    async def add_opencode_mcp_server(self, config: OpencodeMcpServerConfig) -> OpencodeMcpStatus:
        # @intent opencode-mcp-add-reports-only-connected
        # The config's environment and header values are secrets registered
        # before the request, so an echo is scrubbed (INV-6); only a reported
        # connected state is success, and a missing, failed, auth-needing or
        # disabled server is mcp_server_failed, never a silent success (EC-92).
        operation = "add_opencode_mcp_server"
        try:
            self._require_open(operation)
            RecordFieldConverter.require_instance(config, "config", OpencodeMcpServerConfig)

            # The config's environment and header values are injected secrets, scrubbed from any answer (INV-6).
            for value in (*config.environment.values(), *config.headers.values()):
                self._errors.register_secret(value)

            # Register the server; a non-2xx answer is an API error (EC-93).
            answer = await self._client.call("POST", ("mcp",), operation=operation, body=OpencodeWire.mcp_body(config))
            status, vendor_error = self._wire.parse_mcp_status(answer, config.name, operation=operation)

            # A missing name, or a failed, auth-needing or disabled server, did not connect (EC-92).
            if status is None:
                raise self._errors.build(FailureCode.OPENCODE_MCP_SERVER_FAILED, "The opencode server did not report a status for the MCP server.", operation=operation)
            if status in _FAILED_MCP_STATES:
                context = {"status": status} if vendor_error is None else {"status": status, "vendor_error": vendor_error}
                raise self._errors.build(FailureCode.OPENCODE_MCP_SERVER_FAILED, f"The MCP server did not connect; opencode reports it as {status}.", operation=operation, context=context)
            return OpencodeMcpStatus(name=config.name, status=status)
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except ConfigurationError as exc:
            raise self._errors.from_configuration_error(exc, operation=operation) from exc
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=operation) from exc

    def _require_open(self, operation: str) -> None:
        # A host that was never entered, has exited, or failed to open starts nothing (EC-2).
        if not self._open:
            raise self._errors.build(FailureCode.OPENCODE_PROCESS_EXITED, "This OpencodeHost is not open: it was never entered, has exited, or failed to open.", operation=operation, next_step=_OPEN_STEP)

    async def _check_health(self, *, operation: str) -> str:
        # GET /global/health: unhealthy is unreachable (EC-55); older than OPENCODE_MIN_VERSION is unsupported (EC-60).
        body = await self._client.call("GET", ("global", "health"), operation=operation)
        healthy, version, numbers = self._wire.parse_health(body, operation=operation)
        if not healthy:
            raise self._errors.build(FailureCode.OPENCODE_SERVER_UNREACHABLE, "The opencode server reports itself as unhealthy.", operation=operation)
        if numbers < native_host_constants.OPENCODE_MIN_VERSION:
            raise self._errors.build(FailureCode.OPENCODE_VERSION_UNSUPPORTED, "The opencode server is older than the oldest version this SDK supports.", operation=operation, context={"version": version})
        return version

    def _reserve(self, session_id: str | None, *, operation: str) -> str:
        # Reserves synchronously; at the live-turn cap the error carries the EC-67 next step.
        try:
            return self._turns.reserve(session_id, operation=operation)
        except NativeHostError as exc:
            if _LIVE_TURNS_KEY not in exc.context:
                raise
            raise self._errors.build(exc.failure_code, exc.message, operation=operation, next_step=_LIVE_TURN_CAP_STEP, context=dict(exc.context)) from exc

    async def _require_idle(self, session_id: str, *, operation: str, include_local: bool) -> None:
        # A session with a live turn on this host, or busy or retrying on the server, is busy (EC-73, EC-78).
        local = include_local and self._turns.is_session_busy(session_id)
        statuses = () if local else self._wire.parse_session_statuses(await self._client.call("GET", ("session", "status"), operation=operation), operation=operation)
        if local or any(status.session_id == session_id and status.state in _BUSY_STATES for status in statuses):
            raise self._errors.build(FailureCode.OPENCODE_SESSION_BUSY, "The session already has a running turn.", operation=operation, context={"session_id": session_id})

    async def _check_model(self, model: str | None, *, operation: str) -> None:
        # @intent opencode-model-checked-before-spending
        # A requested provider/model must be offered by a connected provider
        # before a session is created or a prompt sent, so a typo never
        # spends money or leaves an empty session (EC-68); the context lists
        # the offered ids, capped by the error factory.
        if model is None:
            return
        provider_id, model_id = model.split("/", _MODEL_ID_SPLITS)
        catalog = self._wire.parse_config_providers(await self._client.call("GET", ("config", "providers"), operation=operation), operation=operation)
        offered = catalog.get(provider_id)
        if offered is not None and any(entry.model_id == model_id for entry in offered):
            return
        choices = offered if offered is not None else tuple(entry for models in catalog.values() for entry in models)
        available = self._errors.listing(f"{entry.provider_id}/{entry.model_id}" for entry in choices)
        raise self._errors.build(FailureCode.OPENCODE_MODEL_UNKNOWN, "The requested model is not offered by a connected provider.", operation=operation, context={"available_models": available})

    async def _newest_message_id(self, session_id: str, *, operation: str) -> str | None:
        # The session's newest message id before the prompt, or None for an empty session.
        body = await self._client.call("GET", ("session", session_id, "message"), operation=operation, query={"limit": _NEWEST_ONE}, not_found=FailureCode.OPENCODE_SESSION_NOT_FOUND)
        messages = self._wire.parse_messages(body, operation=operation)
        return messages[-1].message_id if messages else None

    def _watcher(self, turn_id: str, session_id: str, request: OpencodePromptRequest, *, snapshot_id: str | None) -> OpencodeTurnWatcher:
        # One watcher per turn, sharing this host's client, codec and error factory.
        handle = NativeTurnHandle(harness=NativeHarness.OPENCODE, session_id=session_id, turn_id=turn_id)
        return OpencodeTurnWatcher(handle=handle, request=request, snapshot_id=snapshot_id, client=self._client, wire=self._wire, errors=self._errors, request_timeout_seconds=self._settings.request_timeout_seconds)

    async def _drive(self, watcher: OpencodeTurnWatcher) -> NativeTurnResult:
        # @intent opencode-turn-driver-names-defects
        # The driver task's outcome is what wait_opencode_turn returns or
        # raises, so a defect inside the watcher becomes runtime.error naming
        # only its class, under the wait operation (EC-5, S2-6).
        try:
            return await watcher.run()
        except asyncio.CancelledError:
            raise
        except NativeHostError:
            raise
        except Exception as exc:
            raise self._errors.from_unexpected(exc, operation=_WAIT_OPERATION) from exc

    def _forget(self, turn_id: str, driver: asyncio.Task[NativeTurnResult]) -> None:
        # A finished turn's watcher is dropped; its outcome stays with the turn table for later waits.
        self._watchers.pop(turn_id, None)
        if not driver.cancelled():
            driver.exception()

    async def _abandon(self, session_id: str, *, operation: str) -> None:
        # @intent opencode-cancelled-prompt-is-aborted
        # A cancelled spawn or continue may already have delivered its prompt;
        # the turn is aborted, best effort and bounded by the request
        # deadline, because no caller can ever reach it (EC-4).
        with contextlib.suppress(NativeHostError):
            await self._client.call("POST", ("session", session_id, "abort"), operation=operation)

    async def _close_turn(self, watcher: OpencodeTurnWatcher) -> None:
        # Aborts one live turn as HOST_CLOSED; closing never raises a vendor failure (EC-8).
        with contextlib.suppress(NativeHostError):
            await watcher.interrupt(InterruptSource.HOST_CLOSED, operation=_EXIT_OPERATION)


__all__ = ["OpencodeHost"]
