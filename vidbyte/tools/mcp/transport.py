"""Context Protocol Header

Description:
    Defines MCP transport interfaces and a stdio JSON-RPC implementation.
Purpose:
    Keeps process communication isolated from MCP tool discovery and native tool
    wrapping logic.
Architecture:
    - McpTransport: Async request protocol.
    - McpStdioTransport: Newline-delimited JSON-RPC over subprocess stdio.
Relations:
    Related to vidbyte.tools.mcp.client and vidbyte.tools.mcp.bridge.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from vidbyte.lib.errors import McpProtocolError


class McpTransport(Protocol):
    """Protocol implemented by MCP client transports."""

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Send one JSON-RPC request and return the result object."""


class McpStdioTransport:
    """Newline-delimited JSON-RPC transport backed by a subprocess."""

    def __init__(self, command: Sequence[str], *, env: Mapping[str, str] | None = None) -> None:
        """Store the command used to start the MCP server process."""
        if not command:
            raise ValueError("MCP stdio command cannot be empty")
        self.command = tuple(command)
        self.env = env
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1

    async def start(self) -> None:
        """Start the subprocess if it is not already running."""
        if self._process is not None:
            return
        import os
        sub_env = dict(os.environ)
        if self.env:
            sub_env.update(self.env)
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=sub_env,
        )

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Send a JSON-RPC request and return its result."""
        await self.start()
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise McpProtocolError("MCP process is not available")
        request_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": dict(params or {}),
        }
        self._process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._process.stdin.drain()
        line = await self._process.stdout.readline()
        if not line:
            raise McpProtocolError("MCP server closed stdout")
        try:
            response = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise McpProtocolError("MCP server returned invalid JSON") from exc
        if response.get("id") != request_id:
            raise McpProtocolError("MCP response id did not match request id")
        if "error" in response:
            raise McpProtocolError(
                "MCP server returned an error",
                details={"error": response["error"]},
            )
        result = response.get("result")
        if not isinstance(result, Mapping):
            raise McpProtocolError("MCP response result must be an object")
        return result

    async def close(self) -> None:
        """Terminate the subprocess if it is running."""
        if self._process is None:
            return
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()
        self._process = None
