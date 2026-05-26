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
    - Reads JSON-RPC requests line-by-line from sys.stdin.buffer.
    - Dispatches requests to MCP handlers (initialize, tools/list, tools/call, etc.).
    - Writes JSON-RPC responses line-by-line to sys.stdout.buffer.
    - No external dependencies - uses only asyncio and json from stdlib.
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
from vidbyte.mcp_server.schema import (
    mcp_error_response,
    mcp_result_response,
    mcp_tool_error_result,
    mcp_tool_success_result,
    tool_result_to_mcp_content,
)
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool


JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


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

    async def run(self) -> None:
        """Start the MCP stdio server loop.

        Reads JSON-RPC 2.0 requests from sys.stdin.buffer line-by-line,
        dispatches to the appropriate handler, and writes responses to
        sys.stdout.buffer. Exits when stdin closes or shutdown is signaled.
        """
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(loop=loop)
        protocol = asyncio.StreamReaderProtocol(reader)
        transport: Any = None
        try:
            await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        except Exception:
            return

        while not self._shutdown:
            try:
                line = await reader.readline()
            except Exception:
                break
            if not line:
                break
            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue
            try:
                request = json.loads(line_str)
            except json.JSONDecodeError:
                response = mcp_error_response(
                    None, JSONRPC_PARSE_ERROR, "Parse error"
                )
                self._write_response(response)
                continue
            if not isinstance(request, Mapping):
                response = mcp_error_response(
                    None, JSONRPC_INVALID_REQUEST, "Invalid request"
                )
                self._write_response(response)
                continue
            try:
                response = await self._dispatch(request)
            except Exception as exc:
                response = mcp_error_response(
                    request.get("id", None),
                    JSONRPC_INTERNAL_ERROR,
                    f"Internal error: {exc}",
                )
            self._write_response(response)

        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass

    async def close(self) -> None:
        """Signal the server loop to shut down."""
        self._shutdown = True

    def _write_response(self, response: dict[str, Any]) -> None:
        """Write a single JSON-RPC response line to stdout."""
        try:
            line = json.dumps(response, default=str)
            sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()
        except Exception:
            pass

    async def _dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Route a JSON-RPC request to the correct handler."""
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params")

        if not isinstance(method, str):
            return mcp_error_response(
                request_id, JSONRPC_INVALID_REQUEST, "Missing or invalid method"
            )

        if method == "initialize":
            return await self._handle_initialize(request_id, params)
        if method == "tools/list":
            return await self._handle_tools_list(request_id)
        if method == "tools/call":
            return await self._handle_tools_call(request_id, params)
        if method == "prompts/list":
            return await self._handle_prompts_list(request_id)
        if method == "prompts/get":
            return await self._handle_prompts_get(request_id, params)

        return mcp_error_response(
            request_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}"
        )

    async def _handle_initialize(
        self, request_id: int | str | None, params: Any
    ) -> dict[str, Any]:
        """Respond to MCP initialize handshake with server capabilities."""
        self._server_initialized = True
        return mcp_result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": self._name, "version": self._version},
            },
        )

    async def _handle_tools_list(self, request_id: int | str | None) -> dict[str, Any]:
        """Respond to MCP tools/list with all registered tool definitions."""
        from vidbyte.mcp_server.schema import tool_spec_to_mcp_tool

        studio_tools = [
            tool_spec_to_mcp_tool(spec)
            for spec in self._tool_registry.tool_specs()
        ]
        return mcp_result_response(request_id, {"tools": studio_tools})

    async def _handle_tools_call(
        self, request_id: int | str | None, params: Any
    ) -> dict[str, Any]:
        """Respond to MCP tools/call by executing the named tool."""
        if not isinstance(params, Mapping):
            return mcp_error_response(
                request_id, JSONRPC_INVALID_PARAMS, "Invalid params"
            )
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments")
        if not isinstance(arguments, Mapping):
            arguments = {}
        if not tool_name:
            return mcp_error_response(
                request_id, JSONRPC_INVALID_PARAMS, "Missing tool name"
            )
        try:
            result = await self._tool_registry.execute(tool_name, dict(arguments))
        except Exception as exc:
            return mcp_tool_error_result(
                request_id, f"Tool execution failed: {exc}"
            )
        content = tool_result_to_mcp_content(result)
        if result.status == "error" or result.output.startswith("Error:"):
            return mcp_tool_error_result(
                request_id, result.output
            )
        return mcp_tool_success_result(request_id, content)

    async def _handle_prompts_list(
        self, request_id: int | str | None
    ) -> dict[str, Any]:
        """Respond to MCP prompts/list with available prompt definitions."""
        prompts_list: list[dict[str, Any]] = []
        for key, content in self._tool_registry._prompt_content.items():
            prompts_list.append({
                "name": key,
                "description": f"Prompt template: {key[:60]}",
            })
        return mcp_result_response(request_id, {"prompts": prompts_list})

    async def _handle_prompts_get(
        self, request_id: int | str | None, params: Any
    ) -> dict[str, Any]:
        """Respond to MCP prompts/get with the requested prompt content."""
        if not isinstance(params, Mapping):
            return mcp_error_response(
                request_id, JSONRPC_INVALID_PARAMS, "Invalid params"
            )
        name = str(params.get("name") or "")
        content = self._tool_registry._prompt_content.get(name, "")
        return mcp_result_response(
            request_id,
            {
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": content},
                    }
                ]
            },
        )
