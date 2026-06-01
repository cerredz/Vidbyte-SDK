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
from vidbyte.tools.mcp.bridge import McpToolBridge
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.transport import McpStdioTransport
from vidbyte.tools.mcp.types import McpServerConfig, McpServerHandle, McpToolPermission
from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.tools.types import ToolPermission


async def attach_mcp_server(config: McpServerConfig) -> McpServerHandle:
    """Starts the MCP subprocess, runs the initialize handshake, discovers tools,
    wraps them as McpBridgedTool instances, and returns a live McpServerHandle.

    Raises:
        McpConnectionError: If the subprocess fails to start.
        McpInitializeError: If the MCP handshake fails or times out.
        McpToolDiscoveryError: If tools/list returns an unexpected response.
    """
    try:
        transport = McpStdioTransport(
            list(config.command),
            env=config.env,
        )
    except Exception as e:
        raise McpConnectionError(
            f"Failed to start MCP server subprocess for command {config.command}: {e}"
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
            bridged_tools = await McpToolBridge(registry, client, permission=perm).bridge()
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
    )
