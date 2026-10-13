"""FILE: vidbyte/harnesses/native/hostkit/peers.py

PURPOSE: Defines NativePeer, one JSON-RPC stdio peer process (`grok agent stdio` or `muse serve`) with an inbox of the frames it sends unasked, and NativeChildEnvironment, which builds a vendor child's environment as the caller's environment plus the host's overlay.
ROLE IN CODEBASE: GrokHost and MuseHost start one NativePeer per live turn and one short-lived peer per read; their turn drivers read peer.inbox and answer server requests through peer.answer. NativeChildEnvironment is also used for opencode's owned server and the Muse in-distro reap.
ARCHITECTURE NOTE: NativePeer reuses McpStdioTransport (D-3) with exit_grace_seconds=NATIVE_STOP_GRACE_SECONDS, shutdown_timeout=NATIVE_KILL_WAIT_SECONDS and stop_process_tree=True (D-23), so close is stdin EOF, a grace period, then a whole-tree stop, all bounded. Every write passes the control timeout as its deadline, so it is bounded and a pipe that closed under it fails at once. The timing constants are read when a peer is built, so tests can shrink them through the constants module.
FUNCTION INVENTORY: NativePeer.start launches the process; call sends a request and waits for its answer; send writes a request and returns its future; notify writes a notification; answer replies to a server request; close stops the peer and never raises; stderr_tail returns scrubbed stderr; closed reports whether the pipe has ended; exit_code is the child's exit code once it has exited. NativeChildEnvironment.build merges the overlay over os.environ.
COMMON MODIFICATION PATTERNS: A new peer protocol reuses NativePeer unchanged and maps its own JSON-RPC error codes in its host's wire.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not map JSON-RPC error answers here; they stay McpProtocolError for the host's wire codec (spec §8.5). 2. Do not let close raise; it runs in finally blocks and __aexit__. 3. Do not put a secret on argv; secrets travel in the environment overlay.
KNOWN EDGE CASES: A peer that never started closes without doing anything. The inbox keeps every frame that arrived before a driver began reading, so nothing sent between a turn/start answer and the driver's first read is lost.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Shared host plumbing), D-3, D-18, D-22, D-23, EC-6, EC-10
TESTS: tests/features/grok_host/test_grok_host_shared_contract.py, tests/features/grok_host/test_grok_host_process_bounds.py, tests/features/muse_host/test_muse_host_process_bounds.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.enums.process import ProcessLaunchFailure
from vidbyte.lib.errors import McpProtocolError
from vidbyte.tools.mcp.transport import McpStdioTransport


class NativeChildEnvironment:
    """Builds the environment of a vendor child process."""

    @staticmethod
    def build(overlay: Mapping[str, str]) -> dict[str, str]:
        # @intent native-child-env-inherits-the-callers-environment
        # A vendor CLI is the user's own tool and authenticates through
        # its own environment variables, so it runs as if started in the
        # user's terminal: the caller's environment plus the host's
        # overlay, never editing os.environ itself.
        return {**os.environ, **dict(overlay)}


class NativePeer:
    """One JSON-RPC stdio peer process with an inbox of its server frames."""

    def __init__(self, argv: Sequence[str], *, env: Mapping[str, str], control_timeout_seconds: float, errors: NativeErrorFactory) -> None:
        self.inbox: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue()
        self._errors = errors
        self._control_timeout_seconds = control_timeout_seconds
        self._transport = McpStdioTransport(
            tuple(argv),
            env=dict(env),
            request_timeout=control_timeout_seconds,
            shutdown_timeout=native_host_constants.NATIVE_KILL_WAIT_SECONDS,
            on_message=self.inbox.put_nowait,
            exit_grace_seconds=native_host_constants.NATIVE_STOP_GRACE_SECONDS,
            stop_process_tree=True,
        )

    @property
    def closed(self) -> bool:
        # True once the peer's output ended or close began.
        return self._transport.closed

    async def start(self, *, operation: str) -> None:
        # @intent native-peer-launch-failures-are-typed
        # A missing executable is not_installed and any other
        # launch failure is process_exited, so no raw OSError
        # leaves a host method.
        try:
            await self._transport.start()
        except FileNotFoundError as exc:
            raise self._errors.from_launch_failure(ProcessLaunchFailure.NOT_FOUND, operation=operation) from exc
        except PermissionError as exc:
            raise self._errors.from_launch_failure(ProcessLaunchFailure.PERMISSION_DENIED, operation=operation) from exc
        except (OSError, ValueError) as exc:
            raise self._errors.from_launch_failure(ProcessLaunchFailure.OS_ERROR, operation=operation) from exc
        except McpProtocolError as exc:
            raise self._errors.from_protocol_error(exc, operation=operation) from exc

    async def call(self, method: str, params: Mapping[str, Any], *, operation: str, timeout_seconds: float | None = None) -> Mapping[str, Any]:
        # @intent native-peer-vendor-errors-stay-protocol-errors
        # A JSON-RPC error answer is re-raised unchanged for the host's
        # wire codec to map to its failure; a transport failure
        # (timeout, dead pipe) becomes NativeHostError here.
        # @intent native-peer-writes-name-their-deadline
        # Every write names a deadline, the control timeout unless
        # the caller gave one, because the transport bounds a
        # write and refuses a pipe that closed under it only for a
        # call that names one; a peer that stopped reading must
        # surface as process_exited.
        seconds = self._control_timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            return await self._transport.request(method, params, timeout_seconds=seconds)
        except McpProtocolError as exc:
            if "error" in exc.details:
                raise
            raise self._errors.from_protocol_error(exc, operation=operation) from exc

    async def send(self, method: str, params: Mapping[str, Any], *, operation: str, timeout_seconds: float | None = None) -> asyncio.Future[Mapping[str, Any]]:
        # @intent native-peer-send-returns-before-the-answer
        # A host hands back a turn handle while the turn's prompt
        # request is still pending, so this returns the answer's
        # future as soon as the frame is written. The write has a
        # deadline; the caller bounds the wait and reads vendor
        # errors from the future.
        seconds = self._control_timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            return await self._transport.send_request(method, params, timeout_seconds=seconds)
        except McpProtocolError as exc:
            raise self._errors.from_protocol_error(exc, operation=operation) from exc

    async def notify(self, method: str, params: Mapping[str, Any], *, operation: str) -> None:
        # Writes a notification within the control timeout; a dead or
        # closed pipe becomes process_exited.
        try:
            await self._transport.notify(method, params, timeout_seconds=self._control_timeout_seconds)
        except McpProtocolError as exc:
            raise self._errors.from_protocol_error(exc, operation=operation) from exc

    async def answer(self, request_id: int | str, *, result: Mapping[str, Any] | None = None, error: Mapping[str, Any] | None = None) -> None:
        # Replies to a server request within the control timeout; a
        # failed write stays McpProtocolError for the driver to judge.
        await self._transport.respond(request_id, result=result, error=error, timeout_seconds=self._control_timeout_seconds)

    async def close(self) -> None:
        # @intent native-peer-close-never-raises
        # Stdin EOF, the grace period, then a whole-tree stop with
        # bounded waits. Close runs in finally blocks and __aexit__,
        # so a failure here must never replace the error or
        # cancellation in flight.
        with contextlib.suppress(Exception):
            await self._transport.close()

    @property
    def exit_code(self) -> int | None:
        # The transport's returncode: the child's exit code once it has
        # exited, None while it runs. The Muse host reads it to spot a
        # muse missing inside WSL.
        return self._transport.returncode

    def stderr_tail(self) -> str:
        # @intent native-peer-stderr-is-scrubbed
        # The retained stderr, scrubbed and capped, for error context: a
        # vendor CLI may print an injected key or token there.
        return self._errors.scrub(self._transport.stderr_snapshot())


__all__ = ["NativeChildEnvironment", "NativePeer"]
