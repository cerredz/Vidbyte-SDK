"""Context Protocol Header

Description:
    Defines MCP transport interfaces and a hardened stdio JSON-RPC implementation.
Purpose:
    Keeps process communication isolated from MCP tool discovery and native tool
    wrapping logic while making concurrent requests, timeouts, stderr drainage,
    process exit fan-out, and shutdown reliable.
Architecture:
    - McpTransport: Async request protocol.
    - McpStdioTransport: Newline-delimited JSON-RPC over subprocess stdio with
      ID demultiplexing, background stdout/stderr readers, per-request deadlines,
      restricted child environment, and idempotent bounded close.
    - Opt-in peer extension (the defaults keep MCP behaviour): on_message for
      frames that carry "method", send_request, notify, respond, per-call
      timeouts, exit_grace_seconds, and stop_process_tree, plus a read-only
      returncode that outlives close. Only a call with its own
      timeout_seconds bounds its write and refuses a pipe that closed under
      it; without one the write is MCP's plain drain.
Relations:
    Related to vidbyte.tools.mcp.client, vidbyte.tools.mcp.bridge, and
    vidbyte.tools.mcp.attach.
    Design: docs/design/harden-mcp-stdio-transport.md
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from vidbyte.lib.constants.native_hosts import NATIVE_STDIO_MAX_WAIT_SECONDS
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.errors import ConfigurationError, McpProtocolError
from vidbyte.lib.process import ProcessStopper

MessageCallback = Callable[[Mapping[str, Any]], None]

# Process-necessary variables only. Caller credentials arrive via ``env=``.
# PYTHONPATH is intentionally excluded so parent import paths do not leak.
_POSIX_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TERM",
    "TZ",
)

_WINDOWS_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "USERNAME",
    "NUMBER_OF_PROCESSORS",
)

_DEFAULT_STDERR_MAX_BYTES = 64 * 1024
# @intent mcp-stdio-reads-large-lines
# One JSON-RPC response is one stdout line, and image/audio results carry base64 payloads that can run to
# megabytes, so asyncio's 64 KiB default line limit would kill the reader; allow lines up to 64 MiB.
_STDOUT_LINE_LIMIT_BYTES = 64 * 1024 * 1024
_DEFAULT_REQUEST_TIMEOUT = 30.0
_DEFAULT_SHUTDOWN_TIMEOUT = 5.0


def _inherited_env_keys() -> tuple[str, ...]:
    """Return the platform allowlist of parent env keys safe to inherit."""
    if sys.platform == "win32":
        return _WINDOWS_ENV_KEYS
    return _POSIX_ENV_KEYS


def build_child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a minimal child environment from the allowlist plus caller overlays."""
    child: dict[str, str] = {}
    for key in _inherited_env_keys():
        value = os.environ.get(key)
        if value is not None:
            child[key] = value
    if extra:
        child.update(dict(extra))
    return child


class McpTransport(Protocol):
    """Protocol implemented by MCP client transports."""

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Send one JSON-RPC request and return the result object."""


class McpStdioTransport:
    """Newline-delimited JSON-RPC transport backed by a subprocess.

    Concurrent requests are demultiplexed by JSON-RPC response ``id``. A
    background task drains stdout; another drains stderr into a size-bounded
    buffer. Every request has a deadline. Close is idempotent and fails all
    pending waiters before terminating the child.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        request_timeout: float = _DEFAULT_REQUEST_TIMEOUT,
        shutdown_timeout: float = _DEFAULT_SHUTDOWN_TIMEOUT,
        stderr_max_bytes: int = _DEFAULT_STDERR_MAX_BYTES,
        on_message: MessageCallback | None = None,
        exit_grace_seconds: float | None = None,
        stop_process_tree: bool = False,
    ) -> None:
        """Store command, optional env overlays, transport timing bounds, and the opt-in peer options."""
        if not command:
            raise ValueError("MCP stdio command cannot be empty")
        if request_timeout <= 0:
            raise ValueError("request_timeout must be greater than zero")
        if shutdown_timeout <= 0:
            raise ValueError("shutdown_timeout must be greater than zero")
        if stderr_max_bytes <= 0:
            raise ValueError("stderr_max_bytes must be greater than zero")
        self.command = tuple(command)
        self.env = env
        self.request_timeout = request_timeout
        self.shutdown_timeout = shutdown_timeout
        self.stderr_max_bytes = stderr_max_bytes
        self.on_message = on_message
        self.exit_grace_seconds = None if exit_grace_seconds is None else self._seconds_or_invalid_call(exit_grace_seconds, "exit_grace_seconds")
        self.stop_process_tree = self._switch_or_invalid_call(stop_process_tree, "stop_process_tree")
        self._process: asyncio.subprocess.Process | None = None
        self._returncode: int | None = None
        self._next_id = 1
        self._closed = False
        self._pending: dict[int, asyncio.Future[Mapping[str, Any]]] = {}
        self._write_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_buf = bytearray()
        self._close_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def closed(self) -> bool:
        """True after close has begun or completed."""
        return self._closed

    @property
    def returncode(self) -> int | None:
        """The child's exit code once it has exited, else None; kept after close detaches the child."""
        process = self._process
        return self._returncode if process is None else process.returncode

    def is_bound_to_running_loop(self) -> bool:
        """False when the pipes were opened on an event loop that is not the one running now."""
        if self._loop is None:
            return True
        try:
            return self._loop is asyncio.get_running_loop() and not self._loop.is_closed()
        except RuntimeError:
            return False

    def abandon(self) -> None:
        """Mark closed and kill the child without awaiting, for when its event loop is gone."""
        self._closed = True
        process = self._process
        try:
            if process is not None and process.returncode is None:
                process.kill()
        except Exception:
            pass
        self._detach_process_state()

    def stderr_snapshot(self) -> str:
        """Return the retained stderr tail as UTF-8 text (replacement on errors)."""
        return self._stderr_buf.decode("utf-8", errors="replace")

    async def start(self) -> None:
        """Start the subprocess and reader tasks if not already running."""
        if self._closed:
            raise McpProtocolError(
                "MCP transport is closed",
                details={"reason": "closed"},
            )
        if self._process is not None:
            return
        async with self._start_lock:
            if self._closed:
                raise McpProtocolError(
                    "MCP transport is closed",
                    details={"reason": "closed"},
                )
            if self._process is not None:
                return
            child_env = build_child_env(self.env)
            # Subprocess pipes only work on the loop that opens them, so remember which one that is.
            self._loop = asyncio.get_running_loop()
            program, *arguments = self.command
            # @intent windows-launchers-resolve-like-a-shell
            # Windows only appends .exe to a bare program name, but npm launchers such as npx are
            # .cmd files, so look the name up through PATH and PATHEXT first, as a shell would.
            if sys.platform == "win32":
                program = shutil.which(program) or program
            self._process = await asyncio.create_subprocess_exec(
                program,
                *arguments,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
                # A peer whose tree is stopped at close leads its own
                # process group on POSIX.
                start_new_session=self.stop_process_tree and sys.platform != "win32",
                # @intent mcp-stdio-reads-large-lines
                # Raise the stdout line limit so one large result does not close the transport for good.
                limit=_STDOUT_LINE_LIMIT_BYTES,
            )
            self._stdout_task = asyncio.create_task(
                self._stdout_reader(),
                name="mcp-stdio-stdout",
            )
            self._stderr_task = asyncio.create_task(
                self._stderr_reader(),
                name="mcp-stdio-stderr",
            )

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        """Send a JSON-RPC request and return its result object."""
        # @intent mcp-stdio-request-is-send-then-bounded-wait
        # One deadline per call, request_timeout or this call's
        # timeout_seconds, bounds the wait for the answer. Only an
        # explicit timeout_seconds also bounds the write; without
        # one the write is the plain drain MCP callers had before
        # the peer extension.
        # None keeps request_timeout; any other value must
        # pass the shared check.
        timeout = self.request_timeout if timeout_seconds is None else self._seconds_or_invalid_call(timeout_seconds, "timeout_seconds")
        write_seconds = None if timeout_seconds is None else timeout
        request_id, future = await self._send(method, params, write_seconds)
        return await self._answer(method, request_id, future, timeout)

    async def _send(self, method: str, params: Mapping[str, Any] | None, seconds: float | None) -> tuple[int, asyncio.Future[Mapping[str, Any]]]:
        """Register a pending future under a fresh id, then write the request frame, checked within seconds when given."""
        # @intent mcp-stdio-pending-before-write
        # The future is registered before the frame is written,
        # so an answer that arrives at once still finds it; a
        # failed write removes it.
        if self._closed:
            raise McpProtocolError(
                "MCP transport is closed",
                details={"reason": "closed", "method": method},
            )
        await self.start()
        process = self._process
        if process is None or process.stdin is None:
            raise McpProtocolError(
                "MCP process is not available",
                details={
                    "method": method,
                    "stderr_tail": self.stderr_snapshot(),
                },
            )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Mapping[str, Any]] = loop.create_future()
        request_id: int
        async with self._write_lock:
            if self._closed or self._process is None or self._process.stdin is None:
                raise McpProtocolError(
                    "MCP transport is closed",
                    details={"reason": "closed", "method": method},
                )
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = future
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params or {}),
            }
            try:
                self._process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
                # @intent mcp-stdio-checked-write-has-a-deadline
                # Without a deadline this is MCP's plain drain. With
                # one the drain is bounded, and a pipe already closing
                # afterwards raises: on a broken pipe asyncio marks
                # the pipe closing at once but tells drain only a loop
                # turn later, so drain alone can return as if the
                # frame had been written.
                if seconds is None:
                    await self._process.stdin.drain()
                else:
                    await asyncio.wait_for(self._process.stdin.drain(), seconds)
                if seconds is not None and self._process.stdin.is_closing():
                    raise BrokenPipeError("The MCP process stdin closed under the write.")
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                self._pending.pop(request_id, None)
                if not future.done():
                    future.cancel()
                raise McpProtocolError(
                    "MCP process stdin is not writable",
                    details={
                        "method": method,
                        "request_id": request_id,
                        "stderr_tail": self.stderr_snapshot(),
                        "reason": "timeout" if isinstance(exc, TimeoutError) else "stdin_write_failed",
                    },
                ) from exc

        return request_id, future

    async def _answer(self, method: str, request_id: int, future: asyncio.Future[Mapping[str, Any]], seconds: float) -> Mapping[str, Any]:
        """Wait for one request's answer within its deadline."""
        # @intent mcp-stdio-answer-wait-is-bounded
        # On timeout or cancellation the pending entry is
        # removed, so a late answer is dropped instead of
        # resolving a forgotten future.
        try:
            return await asyncio.wait_for(future, timeout=seconds)
        except TimeoutError as exc:
            pending = self._pending.pop(request_id, None)
            if pending is not None and not pending.done():
                pending.cancel()
            raise McpProtocolError(
                "MCP request timed out",
                details={
                    "method": method,
                    "request_id": request_id,
                    "timeout": seconds,
                    "stderr_tail": self.stderr_snapshot(),
                    "reason": "timeout",
                },
            ) from exc
        except asyncio.CancelledError:
            pending = self._pending.pop(request_id, None)
            if pending is not None and not pending.done():
                pending.cancel()
            raise
        finally:
            # Best-effort cleanup if close/exit already removed the entry.
            current = self._pending.get(request_id)
            if current is future and future.done():
                self._pending.pop(request_id, None)

    async def send_request(self, method: str, params: Mapping[str, Any] | None = None, *, timeout_seconds: float | None = None) -> asyncio.Future[Mapping[str, Any]]:
        """Write one JSON-RPC request and return the future its answer resolves; the caller bounds that wait."""
        # @intent mcp-stdio-send-returns-after-drain
        # A host returns a turn handle while a long request (an
        # ACP session/prompt) is still pending, so this returns
        # once the frame is written and drained, within
        # timeout_seconds when given.
        write_seconds = None if timeout_seconds is None else self._seconds_or_invalid_call(timeout_seconds, "timeout_seconds")
        _request_id, future = await self._send(method, params, write_seconds)
        return future

    async def notify(self, method: str, params: Mapping[str, Any] | None = None, *, timeout_seconds: float | None = None) -> None:
        """Write one JSON-RPC notification, which has no id and gets no answer; params is left out when None."""
        write_seconds = None if timeout_seconds is None else self._seconds_or_invalid_call(timeout_seconds, "timeout_seconds")
        frame: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            frame["params"] = dict(params)
        await self._write_frame(frame, method, write_seconds)

    async def respond(self, request_id: int | str, *, result: Mapping[str, Any] | None = None, error: Mapping[str, Any] | None = None, timeout_seconds: float | None = None) -> None:
        """Answer one server request with exactly one of a result or an error."""
        # @intent mcp-stdio-respond-is-checked-before-writing
        # A response with both or neither of result and error is
        # refused as invalid_call before anything is written, so the
        # peer never sees it.
        write_seconds = None if timeout_seconds is None else self._seconds_or_invalid_call(timeout_seconds, "timeout_seconds")
        if (result is None) == (error is None):
            raise McpProtocolError("An MCP response needs exactly one of result and error.", details={"reason": "invalid_call", "request_id": request_id})
        answer = {"result": dict(result)} if result is not None else {"error": dict(error or {})}
        await self._write_frame({"jsonrpc": "2.0", "id": request_id, **answer}, None, write_seconds)

    async def _write_frame(self, frame: Mapping[str, Any], method: str | None, seconds: float | None) -> None:
        """Write one frame that expects no answer, checked within seconds when given."""
        if self._closed:
            raise McpProtocolError("MCP transport is closed", details={"reason": "closed", "method": method})
        await self.start()
        async with self._write_lock:
            process = self._process
            if self._closed or process is None or process.stdin is None:
                raise McpProtocolError("MCP transport is closed", details={"reason": "closed", "method": method})
            try:
                process.stdin.write((json.dumps(frame) + "\n").encode("utf-8"))
                # @intent mcp-stdio-checked-write-has-a-deadline
                # The same write as _send: plain without a deadline,
                # bounded and refused on a closing pipe with one.
                if seconds is None:
                    await process.stdin.drain()
                else:
                    await asyncio.wait_for(process.stdin.drain(), seconds)
                if seconds is not None and process.stdin.is_closing():
                    raise BrokenPipeError("The MCP process stdin closed under the write.")
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                reason = "timeout" if isinstance(exc, TimeoutError) else "stdin_write_failed"
                raise McpProtocolError("MCP process stdin is not writable", details={"method": method, "stderr_tail": self.stderr_snapshot(), "reason": reason}) from exc

    @staticmethod
    def _seconds_or_invalid_call(value: object, name: str) -> float:
        """Check a new seconds value with the shared validator, as an MCP protocol error."""
        # The shared record validator refuses bool, NaN, inf and
        # values <= 0, and a refusal is
        # McpProtocolError(invalid_call), the error type MCP callers
        # already catch; nothing is written for an invalid call.
        try:
            return RecordFieldValidator.require_number(value, name, maximum=NATIVE_STDIO_MAX_WAIT_SECONDS)
        except ConfigurationError as exc:
            raise McpProtocolError(f"{name} must be a finite number of seconds greater than 0 and at most {NATIVE_STDIO_MAX_WAIT_SECONDS}.", details={"reason": "invalid_call", "field": name}) from exc

    @staticmethod
    def _switch_or_invalid_call(value: object, name: str) -> bool:
        """Check a new switch with the shared validator, as an MCP protocol error."""
        try:
            return RecordFieldValidator.require_bool(value, name)
        except ConfigurationError as exc:
            raise McpProtocolError(f"{name} must be True or False.", details={"reason": "invalid_call", "field": name}) from exc

    async def close(self) -> None:
        """Idempotently fail pendings, terminate the child, and detach state."""
        async with self._close_lock:
            already_closed = self._closed
            self._closed = True
            self._fail_all_pending(
                "MCP transport closed",
                reason="closed",
            )
            process = self._process
            if process is not None and process.stdin is not None:
                try:
                    process.stdin.close()
                except Exception:
                    pass
            if process is not None and (self.exit_grace_seconds is not None or self.stop_process_tree):
                await self._stop_peer(process)
            elif process is not None and process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=self.shutdown_timeout)
                except TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    try:
                        await process.wait()
                    except ProcessLookupError:
                        pass
            await self._stop_reader_tasks()
            self._detach_process_state()
            if already_closed and process is None:
                return

    async def _stop_peer(self, process: asyncio.subprocess.Process) -> None:
        """Give the child its exit grace, then stop it or its whole tree, with every wait bounded."""
        # @intent mcp-stdio-bounded-tree-stop
        # A peer gets exit_grace_seconds after stdin EOF to finish by
        # itself. With stop_process_tree its whole group is then stopped
        # whatever returncode says, because a grandchild can outlive the
        # child and hold its pipes. Waits after a kill are bounded by
        # shutdown_timeout and the pipes are closed afterwards, so a
        # surviving grandchild cannot hang close.
        if self.exit_grace_seconds is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=self.exit_grace_seconds)
        if self.stop_process_tree:
            await ProcessStopper.stop_tree(process, grace_seconds=self.shutdown_timeout)
            return
        try:
            for stop in (process.terminate, process.kill):
                if process.returncode is not None:
                    break
                with contextlib.suppress(ProcessLookupError, TimeoutError):
                    stop()
                    await asyncio.wait_for(process.wait(), timeout=self.shutdown_timeout)
        finally:
            # getattr degrades to a pipe leak on a Python without the
            # private attribute instead of raising.
            pipes = getattr(process, "_transport", None)
            if pipes is not None:
                with contextlib.suppress(PermissionError, ProcessLookupError, OSError, RuntimeError):
                    pipes.close()

    def _detach_process_state(self) -> None:
        """Idempotently clear process ownership after wait or known death."""
        if self._process is not None:
            self._returncode = self._process.returncode
        self._process = None
        self._stdout_task = None
        self._stderr_task = None
        self._pending.clear()

    async def _stop_reader_tasks(self) -> None:
        """Cancel background readers and wait briefly for them to finish."""
        tasks = [task for task in (self._stdout_task, self._stderr_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)

    def _fail_all_pending(self, message: str, *, reason: str) -> None:
        """Complete every outstanding future with a protocol error."""
        details = {
            "reason": reason,
            "stderr_tail": self.stderr_snapshot(),
        }
        pending = list(self._pending.items())
        self._pending.clear()
        for request_id, future in pending:
            if future.done():
                continue
            future.set_exception(
                McpProtocolError(
                    message,
                    details={**details, "request_id": request_id},
                )
            )

    async def _stdout_reader(self) -> None:
        """Read NDJSON responses and demultiplex them onto pending futures."""
        process = self._process
        if process is None or process.stdout is None:
            self._fail_all_pending(
                "MCP process is not available",
                reason="process_unavailable",
            )
            return
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    self._fail_all_pending(
                        "MCP server closed stdout",
                        reason="process_exited",
                    )
                    self._closed = True
                    return
                self._dispatch_stdout_line(line)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fail_all_pending(
                f"MCP stdout reader failed: {exc}",
                reason="reader_failed",
            )
            self._closed = True

    def _dispatch_stdout_line(self, line: bytes) -> None:
        """Parse one stdout line and route it to the matching waiter if any."""
        try:
            text = line.decode("utf-8")
            message = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Malformed frames must not be delivered to a random waiter.
            return
        if not isinstance(message, dict):
            return
        if "method" in message:
            # @intent mcp-stdio-callback-cannot-kill-reader
            # A frame that carries "method" is a server request or
            # notification, never an answer, so it must not resolve
            # a pending request even when its id collides with one.
            # The callback is the caller's code: an Exception from
            # it drops this frame only, and the reader keeps serving
            # the other requests.
            if isinstance(message["method"], str) and self.on_message is not None:
                with contextlib.suppress(Exception):
                    self.on_message(message)
            return
        if "id" not in message:
            # Notifications and server pushes have no id; discard safely.
            return
        request_id = message["id"]
        if not isinstance(request_id, int):
            return
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            # Unknown or duplicate response id.
            return
        if "error" in message:
            future.set_exception(
                McpProtocolError(
                    "MCP server returned an error",
                    details={
                        "error": message["error"],
                        "request_id": request_id,
                        "stderr_tail": self.stderr_snapshot(),
                    },
                )
            )
            return
        result = message.get("result")
        if not isinstance(result, Mapping):
            future.set_exception(
                McpProtocolError(
                    "MCP response result must be an object",
                    details={
                        "request_id": request_id,
                        "stderr_tail": self.stderr_snapshot(),
                    },
                )
            )
            return
        future.set_result(result)

    async def _stderr_reader(self) -> None:
        """Continuously drain stderr into a size-bounded buffer."""
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            while True:
                chunk = await process.stderr.read(4096)
                if not chunk:
                    return
                self._append_stderr(chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    def _append_stderr(self, chunk: bytes) -> None:
        """Append stderr bytes and drop oldest data past the size bound."""
        self._stderr_buf.extend(chunk)
        overflow = len(self._stderr_buf) - self.stderr_max_bytes
        if overflow > 0:
            del self._stderr_buf[:overflow]
