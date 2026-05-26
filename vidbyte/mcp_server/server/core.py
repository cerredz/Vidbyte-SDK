"""Context Protocol Header

Description:
    Implements McpStudioServer - the MCP server that exposes Vidbyte SDK capabilities
    as MCP tools over stdio JSON-RPC transport.
Purpose:
    Allows external MCP-compatible clients (Codex, Claude, OpenAI Agents SDK, etc.)
    to discover and invoke Vidbyte agents, tools, strategies, pipelines, and prompts
    through the standard Model Context Protocol.
Architecture:
    - McpStudioServer: Core class owning tool/prompt registries and the I/O loop.
    - _connect_stdin(): Sets up asyncio StreamReader from sys.stdin.buffer.
    - _read_input(): Reads one line, decodes, parses JSON, validates type.
    - _dispatch(): Dict-based switch over handler instances, one per JSON-RPC method.
    - Each JSON-RPC method handler lives in server/handlers/<method>.py.
Relations:
    Used by external MCP clients via stdio subprocess spawning.
    Uses vidbyte.mcp_server.handlers and vidbyte.mcp_server.schema internally.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.mcp_server.handlers import StudioToolRegistry
from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler
from vidbyte.mcp_server.server.handlers.initialize import InitializeHandler
from vidbyte.mcp_server.server.handlers.prompts_get import PromptsGetHandler
from vidbyte.mcp_server.server.handlers.prompts_list import PromptsListHandler
from vidbyte.mcp_server.server.handlers.tools_call import ToolsCallHandler
from vidbyte.mcp_server.server.handlers.tools_list import ToolsListHandler
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


class _EOF:
    """Sentinel returned by _read_input when stdin is closed — signals loop break."""


class _SKIP:
    """Sentinel returned by _read_input when a line should be skipped — signals continue."""


class McpStudioServer:
    """Minimal, zero-dependency MCP server over stdio.

    Exposes Vidbyte SDK capabilities (agents, tools, strategies, prompts,
    pipelines) as MCP tools discoverable by any MCP-compliant client.
    """

    def __init__(
        self,
        *,
        name: str = "vidbyte-sdk-studio",
        version: str = "0.1.0",
        agents: Mapping[str, BaseAgent] | None = None,
        tools: Sequence[BaseTool] = (),
        strategy_names: Sequence[str] = (),
        pipeline_names: Sequence[str] = (),
        prompt_content: Mapping[str, str] | None = None,
    ) -> None:
        self._name = name
        self._version = version
        self._server_initialized = False
        self._shutdown = False

        prompt_families: dict[str, Sequence[str]] = {}
        prompt_text_by_key: dict[str, str] = {}
        if prompt_content is not None:
            prompt_text_by_key = dict(prompt_content)
        try:
            prompts = Prompts()
            prompt_families["strategy"] = list(prompts._data.keys())
            for key, entry in prompts._data.items():
                try:
                    prompt_text_by_key[key] = entry.get("prompt", "")
                except Exception:
                    prompt_text_by_key[key] = str(entry or "")
        except Exception:
            pass

        self._tool_registry = StudioToolRegistry(
            agents=agents,
            tools=tools,
            strategy_names=strategy_names,
            pipeline_names=pipeline_names,
            prompt_families=prompt_families,
            prompt_content=prompt_text_by_key,
        )
        self._handler_map: dict[str, _BaseHandler] = {
            "initialize":   InitializeHandler(self._name, self._version, self._set_initialized),
            "tools/list":   ToolsListHandler(self._tool_registry),
            "tools/call":   ToolsCallHandler(self._tool_registry),
            "prompts/list": PromptsListHandler(self._tool_registry),
            "prompts/get":  PromptsGetHandler(self._tool_registry),
        }

    def _set_initialized(self) -> None:
        """Callback passed to InitializeHandler to flip the initialized flag."""
        self._server_initialized = True

    async def run(self) -> None:
        """Runs the main read-dispatch-write loop until stdin closes or shutdown is signaled."""
        try:
            reader = await self._connect_stdin()
        except Exception:
            return

        while not self._shutdown:
            result = await self._read_input(reader)
            if isinstance(result, _EOF):
                break
            if isinstance(result, _SKIP):
                continue
            try:
                response = await self._dispatch(result)
            except Exception as exc:
                response = McpSchema.mcp_error_response(
                    result.get("id") if isinstance(result, Mapping) else None,
                    JSONRPC_INTERNAL_ERROR,
                    f"Internal error: {exc}",
                )
            self._write_response(response)

    async def close(self) -> None:
        """Signals the server loop to shut down on the next iteration."""
        self._shutdown = True

    def _write_response(self, response: dict[str, Any]) -> None:
        """Serializes a JSON-RPC response dict and writes it as a single line to stdout."""
        try:
            line = json.dumps(response, default=str)
            sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()
        except Exception:
            pass

    async def _connect_stdin(self) -> asyncio.StreamReader:
        """Creates an asyncio StreamReader connected to sys.stdin.buffer."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(loop=loop)
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        return reader

    async def _read_input(self, reader: asyncio.StreamReader) -> dict[str, Any] | _EOF | _SKIP:
        """Reads one stdin line; returns a parsed request dict, _EOF, or _SKIP."""
        try:
            line = await reader.readline()
        except Exception:
            return _EOF()
        if not line:
            return _EOF()
        line_str = line.decode("utf-8").strip()
        if not line_str:
            return _SKIP()
        try:
            request = json.loads(line_str)
        except json.JSONDecodeError:
            self._write_response(McpSchema.mcp_error_response(None, JSONRPC_PARSE_ERROR, "Parse error"))
            return _SKIP()
        if not isinstance(request, Mapping):
            self._write_response(McpSchema.mcp_error_response(None, JSONRPC_INVALID_REQUEST, "Invalid request"))
            return _SKIP()
        return request

    async def _dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Routes a JSON-RPC request to the matching handler via the handler map."""
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params")

        if not isinstance(method, str):
            return McpSchema.mcp_error_response(request_id, JSONRPC_INVALID_REQUEST, "Missing or invalid method")

        handler = self._handler_map.get(method)
        if handler is None:
            return McpSchema.mcp_error_response(request_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")

        return await handler.handle(request_id, params)
