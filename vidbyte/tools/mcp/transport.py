"""Context Protocol Header

Description:
    Defines MCP transport interfaces, a hardened stdio JSON-RPC implementation, and a
    Streamable HTTP implementation for remote MCP servers.
Purpose:
    Keeps process communication isolated from MCP tool discovery and native tool
    wrapping logic while making concurrent requests, timeouts, stderr drainage,
    process exit fan-out, and shutdown reliable.
Architecture:
    - McpTransport: Async request protocol.
    - McpStdioTransport: Newline-delimited JSON-RPC over subprocess stdio with
      ID demultiplexing, background stdout/stderr readers, per-request deadlines,
      restricted child environment, and idempotent bounded close.
    - McpNotifyingTransport: Optional protocol for transports that can send
      JSON-RPC notifications (used for notifications/initialized).
    - McpStreamableHttpTransport: JSON-RPC over HTTP POST per the MCP Streamable
      HTTP transport: JSON or SSE replies, Mcp-Session-Id and MCP-Protocol-Version
      headers, byte-bounded bodies, and a best-effort session DELETE on close.
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
from typing import Any, Protocol, runtime_checkable

from vidbyte.lib.errors import (
    ConfigurationError,
    McpProtocolError,
    ProviderRequestError,
)
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

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
_DEFAULT_HTTP_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_HTTP_STATUS_OK_FLOOR = 200
_HTTP_STATUS_OK_CEILING = 300
_HTTP_STATUS_NOT_FOUND = 404
_JSONRPC_VERSION = "2.0"
_SESSION_HEADER = "mcp-session-id"
_PROTOCOL_HEADER = "MCP-Protocol-Version"
_EVENT_STREAM = "text/event-stream"
_MIN_POSITIVE = 0


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

    async def close(self) -> None:
        """Release the connection: end the subprocess or the remote session."""


@runtime_checkable
class McpNotifyingTransport(Protocol):
    """Protocol implemented by MCP transports that can send JSON-RPC notifications."""

    async def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        """Send one JSON-RPC notification, which has no id and expects no result."""


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


class McpStreamableHttpTransport:
    """JSON-RPC over the MCP Streamable HTTP transport for one remote server.

    Every message is one HTTP POST to the server's MCP endpoint. A reply is
    either a JSON body or a text/event-stream body whose events carry the
    JSON-RPC response; both are read under a byte ceiling. The server's
    Mcp-Session-Id is echoed on later requests, the negotiated protocol version
    is sent as MCP-Protocol-Version after initialize, and close() sends a
    best-effort DELETE to end the session.
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        request_timeout: float = _DEFAULT_REQUEST_TIMEOUT,
        max_response_bytes: int = _DEFAULT_HTTP_MAX_RESPONSE_BYTES,
        http: HttpTransport | None = None,
    ) -> None:
        """Store the endpoint, the fixed headers (usually carrying a credential), and the transport bounds."""
        # @intent http-transport-validates-bounds-up-front
        # A zero timeout or byte ceiling would disable the protection against untrusted servers, so both are refused here.
        if not url:
            raise ConfigurationError("MCP HTTP url cannot be empty.")
        if request_timeout <= _MIN_POSITIVE:
            raise ConfigurationError("request_timeout must be greater than zero.")
        if max_response_bytes <= _MIN_POSITIVE:
            raise ConfigurationError("max_response_bytes must be greater than zero.")
        self.url = url
        self._headers = dict(headers or {})
        self.request_timeout = request_timeout
        self.max_response_bytes = max_response_bytes
        self._http = http or HttpTransport()
        self._next_id = 1
        self._session_id: str | None = None
        self._protocol_version: str | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        """True after close() has run."""
        return self._closed

    async def request(self, method: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        """Send one JSON-RPC request and return its result object."""
        # @intent mcp-http-request-is-bounded-and-typed
        # Remote servers are untrusted: every reply is read under a byte ceiling, and every failure surfaces as
        # McpProtocolError so callers see one error type whether the server is local (stdio) or remote.
        self._require_open(method)
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": _JSONRPC_VERSION, "id": request_id, "method": method, "params": dict(params or {})}
        response = await self._post(method, payload)
        self._remember_session(response)
        result = self._result(method, request_id, response)
        if method == "initialize":
            version = result.get("protocolVersion")
            self._protocol_version = version if isinstance(version, str) and version else None
        return result

    async def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        """Send one JSON-RPC notification; the server answers 202 Accepted with no body."""
        self._require_open(method)
        payload: dict[str, Any] = {"jsonrpc": _JSONRPC_VERSION, "method": method}
        if params:
            payload["params"] = dict(params)
        response = await self._post(method, payload)
        self._remember_session(response)
        self._require_success(method, response)

    async def close(self) -> None:
        """Mark the transport closed and ask the server to end the session, ignoring servers that refuse."""
        # @intent session-delete-is-best-effort
        # Closing must always succeed locally; a server that rejects DELETE only keeps its own session until expiry.
        if self._closed:
            return
        self._closed = True
        if self._session_id is None:
            return
        try:
            await self._http.request(
                method="DELETE",
                url=self.url,
                headers=self._request_headers(),
                timeout_seconds=self.request_timeout,
                max_response_bytes=self.max_response_bytes,
            )
        except ProviderRequestError:
            # Ending a session is a courtesy; the server expires abandoned sessions on its own.
            return

    async def _post(self, method: str, payload: Mapping[str, Any]) -> HttpResponse:
        # Sends one JSON-RPC message and translates transport failures into McpProtocolError.
        # @intent every-post-is-bounded
        # The response ceiling and timeout apply to every POST, and POSTs are never retried, since a retried
        # tools/call could repeat a side effect.
        try:
            return await self._http.request(
                method="POST",
                url=self.url,
                headers=self._request_headers(),
                json_body=payload,
                timeout_seconds=self.request_timeout,
                max_response_bytes=self.max_response_bytes,
            )
        except ProviderRequestError as exc:
            raise McpProtocolError(
                "MCP HTTP request failed",
                details={"method": method, "reason": "http_error", "cause": exc.message},
            ) from exc

    def _request_headers(self) -> dict[str, str]:
        # Combines the fixed headers with the negotiated session and protocol version.
        # @intent session-and-version-headers-follow-negotiation
        # The session id and protocol version are echoed only after the server assigns them, as the transport spec requires.
        # Lowercase names match the header HttpTransport adds for JSON bodies; a mixed-case duplicate would be sent
        # as a second Content-Type value, which servers reject with 415.
        headers = {
            "content-type": "application/json",
            "accept": f"application/json, {_EVENT_STREAM}",
            **self._headers,
        }
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        if self._protocol_version is not None:
            headers[_PROTOCOL_HEADER] = self._protocol_version
        return headers

    def _remember_session(self, response: HttpResponse) -> None:
        # Keeps the session id the server assigns on initialize; header names are compared case-insensitively.
        session = _header(response.headers, _SESSION_HEADER)
        if session:
            self._session_id = session

    def _require_open(self, method: str) -> None:
        # Refuses to send after close().
        if self._closed:
            raise McpProtocolError("MCP transport is closed", details={"reason": "closed", "method": method})

    def _require_success(self, method: str, response: HttpResponse) -> None:
        # Maps non-2xx statuses to a protocol error, naming an expired session separately.
        if _HTTP_STATUS_OK_FLOOR <= response.status_code < _HTTP_STATUS_OK_CEILING:
            return
        reason = "session_expired" if response.status_code == _HTTP_STATUS_NOT_FOUND and self._session_id else "http_status"
        raise McpProtocolError(
            "MCP HTTP server returned an error status",
            details={"method": method, "reason": reason, "status_code": response.status_code},
        )

    def _result(self, method: str, request_id: int, response: HttpResponse) -> Mapping[str, Any]:
        # Finds the JSON-RPC response for this request id in a JSON or SSE body and returns its result.
        # @intent match-response-by-request-id
        # Server notifications and requests can share a reply stream, so only the message with this request's id counts.
        self._require_success(method, response)
        content_type = _header(response.headers, "content-type") or ""
        messages = _sse_messages(response.body) if _EVENT_STREAM in content_type else _json_messages(response.body)
        for message in messages:
            if message.get("id") != request_id:
                continue
            error = message.get("error")
            if isinstance(error, Mapping):
                raise McpProtocolError(
                    "MCP server returned a JSON-RPC error",
                    details={"method": method, "reason": "rpc_error", "code": error.get("code"), "message": str(error.get("message", ""))[:500]},
                )
            result = message.get("result")
            return result if isinstance(result, Mapping) else {}
        raise McpProtocolError(
            "MCP HTTP reply did not contain a response for the request",
            details={"method": method, "reason": "missing_response", "request_id": request_id},
        )


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Return one response header by case-insensitive name."""
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def _json_messages(body: str) -> list[Mapping[str, Any]]:
    """Decode a JSON reply, which is one JSON-RPC message or a batch array of them."""
    try:
        decoded = json.loads(body) if body.strip() else []
    except json.JSONDecodeError as exc:
        raise McpProtocolError("MCP HTTP reply is not JSON", details={"reason": "invalid_json"}) from exc
    candidates = decoded if isinstance(decoded, list) else [decoded]
    return [message for message in candidates if isinstance(message, Mapping)]


def _sse_messages(body: str) -> list[Mapping[str, Any]]:
    """Decode every event's data lines from a text/event-stream reply, skipping events that are not JSON."""
    messages: list[Mapping[str, Any]] = []
    for event in body.replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[len("data:"):].lstrip() for line in event.split("\n") if line.startswith("data:"))
        if not data:
            continue
        try:
            decoded = json.loads(data)
        except json.JSONDecodeError:
            continue
        candidates = decoded if isinstance(decoded, list) else [decoded]
        messages.extend(message for message in candidates if isinstance(message, Mapping))
    return messages
