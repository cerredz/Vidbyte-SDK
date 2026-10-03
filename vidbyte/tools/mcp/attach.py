"""Context Protocol Header

Description:
    Implements free functions to bootstrap and attach remote MCP server processes.
Purpose:
    Handles subprocess instantiation, the JSON-RPC initialization handshake, and
    error recovery to prevent orphan standard streams.
Architecture:
    - attach_mcp_server: Async free function orchestrating the full connection pipeline.
Functions:
    - attach_mcp_server(config: McpServerConfig) -> McpServerHandle
Relations:
    Uses vidbyte.tools.mcp.types, vidbyte.tools.mcp.transport, and vidbyte.tools.mcp.client.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import (
    McpConnectionError,
    McpInitializeError,
    McpToolDiscoveryError,
)
from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.tools.mcp.bridge import McpToolBridge
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.transport import McpStdioTransport, McpStreamableHttpTransport
from vidbyte.tools.mcp.types import McpServerConfig, McpServerHandle, McpToolPermission
from vidbyte.tools.types import ToolPermission


async def attach_mcp_server(config: McpServerConfig) -> McpServerHandle:
    """Connects to the MCP server (a stdio subprocess or a Streamable HTTP url), runs the
    initialize handshake, discovers tools, wraps the allowlisted ones as McpBridgedTool
    instances under the configured prefix, and returns a live McpServerHandle.

    Raises:
        McpConnectionError: If the subprocess fails to start.
        McpInitializeError: If the MCP handshake fails or times out.
        McpToolDiscoveryError: If tools/list returns an unexpected response.
    """
    try:
        transport = _build_transport(config)
    except Exception as e:
        raise McpConnectionError(
            f"Failed to start MCP server transport for {config.target}: {e}"
        ) from e

    try:
        client = McpClient(transport)
        try:
            async with asyncio.timeout(config.timeout):
                await client.initialize()
        except asyncio.TimeoutError as e:
            raise McpInitializeError(
                f"MCP server initialization timed out after {config.timeout} seconds."
            ) from e
        except Exception as e:
            raise McpInitializeError(f"MCP server handshake failed: {e}") from e

        # Map McpToolPermission to native ToolPermission
        perm = ToolPermission.EXECUTE
        if config.permission == McpToolPermission.READONLY:
            perm = ToolPermission.READ
        elif config.permission == McpToolPermission.DISABLED:
            perm = ToolPermission.SAFE

        registry = ToolRegistry()
        try:
            definitions = await client.list_tools()
            bridged_tools = McpToolBridge(registry, client, permission=perm).bridge_definitions(
                definitions,
                allowlist=config.tool_allowlist,
                prefix=config.tool_prefix,
            )
        except Exception as e:
            raise McpToolDiscoveryError(
                f"Failed to discover remote tools from MCP server: {e}"
            ) from e

    except Exception:
        await transport.close()
        raise

    return McpServerHandle(
        config=config,
        client=client,
        transport=transport,
        bridged_tools=tuple(bridged_tools),
        definitions=tuple(definitions),
    )


def _build_transport(config: McpServerConfig) -> McpStdioTransport | McpStreamableHttpTransport:
    """Return the transport the config names: Streamable HTTP for a url, stdio for a command."""
    # @intent one-config-one-transport
    # McpServerConfig guarantees exactly one of url or command, so the choice here is never ambiguous.
    if config.url:
        return McpStreamableHttpTransport(config.url, headers=config.headers, request_timeout=config.timeout)
    return McpStdioTransport(list(config.command), env=config.env, request_timeout=config.timeout)
