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
Relations:
    Related to vidbyte.tools.mcp.client, vidbyte.tools.mcp.bridge, and
    vidbyte.tools.mcp.attach.
    Design: docs/design/harden-mcp-stdio-transport.md
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from vidbyte.lib.errors import McpProtocolError

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
    ) -> None:
        """Store command, optional env overlays, and transport timing bounds."""
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
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._closed = False
        self._pending: dict[int, asyncio.Future[Mapping[str, Any]]] = {}
        self._write_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_buf = bytearray()
        self._close_lock = asyncio.Lock()

    @property
    def closed(self) -> bool:
        """True after close has begun or completed."""
        return self._closed

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
            self._process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
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
    ) -> Mapping[str, Any]:
        """Send a JSON-RPC request and return its result object."""
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
                await self._process.stdin.drain()
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
                        "reason": "stdin_write_failed",
                    },
                ) from exc

        try:
            return await asyncio.wait_for(future, timeout=self.request_timeout)
        except TimeoutError as exc:
            pending = self._pending.pop(request_id, None)
            if pending is not None and not pending.done():
                pending.cancel()
            raise McpProtocolError(
                "MCP request timed out",
                details={
                    "method": method,
                    "request_id": request_id,
                    "timeout": self.request_timeout,
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
            if process is not None and process.returncode is None:
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

    def _detach_process_state(self) -> None:
        """Idempotently clear process ownership after wait or known death."""
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
