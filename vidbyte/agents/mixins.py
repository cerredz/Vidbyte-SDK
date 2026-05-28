"""Context Protocol Header

Description:
    Defines mixins that equip agents and harnesses with lifecycle-managed and preset MCP servers.
Purpose:
    Enforces identical APIs and automated cleanup routines for attached subprocesses
    without duplicating logic across agents and harnesses.
Architecture:
    - McpAttachableMixin: Shared base class implementing async and sync builder APIs,
      lazy startup, preset lookup capabilities, and context manager hooks.
Key Functions:
    - attach_preset_mcp_server: Attaches a pre-configured popular MCP server in one line.
    - with_preset_mcp_server: Defer attaching a pre-configured popular MCP server until agent execution.
Relations:
    Inherited by SDK classes that attach MCP servers. Integrates with vidbyte.tools.mcp.presets.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.errors import McpAttachmentError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.mcp.attach import attach_mcp_server
from vidbyte.tools.mcp.presets import McpPresetRegistry
from vidbyte.tools.mcp.types import McpServerConfig, McpServerHandle, McpToolPermission


class McpAttachableMixin:
    """Adds Model Context Protocol (MCP) server attachment and lifecycle management
    to any class that owns a tool list (self.tools).
    """

    _mcp_handles: list[McpServerHandle]
    _pending_mcp_configs: list[McpServerConfig]
    tools: list[BaseTool]

    async def attach_mcp_server(
        self,
        command: Sequence[str],
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> McpAttachableMixin:
        """Start one MCP server subprocess, bridge its discovered tools, and attach them.

        Returns self to support builder pattern.
        """
        config = McpServerConfig(
            command=tuple(command),
            name=name,
            permission=permission,
            env=env,
            timeout=timeout,
        )
        handle = await attach_mcp_server(config)
        self._mcp_handles.append(handle)
        
        self._attach_tools(handle.bridged_tools)
        return self

    async def attach_preset_mcp_server(self, preset_name: str, *, name: str | None = None, permission: McpToolPermission = McpToolPermission.EXECUTE, env: Mapping[str, str] | None = None, timeout: float = 30.0, extra_args: Sequence[str] | None = None) -> McpAttachableMixin:
        """Start one popular preset MCP server subprocess in a single line, discovering tools and attaching them."""
        config = McpPresetRegistry.build_config(
            preset_name,
            env=env,
            permission=permission,
            timeout=timeout,
            extra_args=extra_args,
        )
        if name:
            config = McpServerConfig(
                command=config.command,
                name=name,
                permission=config.permission,
                env=config.env,
                timeout=config.timeout,
            )
        handle = await attach_mcp_server(config)
        self._mcp_handles.append(handle)
        self._attach_tools(handle.bridged_tools)
        return self

    async def attach_mcp_servers(
        self,
        servers: Sequence[McpServerConfig],
    ) -> McpAttachableMixin:
        """Attach multiple MCP servers concurrently.

        If any server fails to start or initialize, all successfully started servers
        in this batch are closed and cleaned up before raising McpAttachmentError.
        """
        if not servers:
            return self

        results = await asyncio.gather(
            *[attach_mcp_server(cfg) for cfg in servers],
            return_exceptions=True,
        )

        handles: list[McpServerHandle] = []
        errors: list[Exception] = []
        for r in results:
            if isinstance(r, Exception):
                errors.append(r)
            else:
                handles.append(r)

        if errors:
            if handles:
                await asyncio.gather(
                    *[h.close() for h in handles],
                    return_exceptions=True,
                )
            raise McpAttachmentError(
                f"{len(errors)} MCP server(s) failed to attach.",
                causes=errors,
            )

        for handle in handles:
            self._mcp_handles.append(handle)
            self._attach_tools(handle.bridged_tools)

        return self

    def with_mcp_server(
        self,
        command: Sequence[str],
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> McpAttachableMixin:
        """Sync builder method that registers an MCP server configuration.

        The subprocess and connection will be deferred and connected lazily
        before the first execution.
        """
        self._pending_mcp_configs.append(
            McpServerConfig(
                command=tuple(command),
                name=name,
                permission=permission,
                env=env,
                timeout=timeout,
            )
        )
        return self

    def with_preset_mcp_server(self, preset_name: str, *, name: str | None = None, permission: McpToolPermission = McpToolPermission.EXECUTE, env: Mapping[str, str] | None = None, timeout: float = 30.0, extra_args: Sequence[str] | None = None) -> McpAttachableMixin:
        """Sync builder method that registers an MCP server preset configuration to connect lazily."""
        config = McpPresetRegistry.build_config(
            preset_name,
            env=env,
            permission=permission,
            timeout=timeout,
            extra_args=extra_args,
        )
        if name:
            config = McpServerConfig(
                command=config.command,
                name=name,
                permission=config.permission,
                env=config.env,
                timeout=config.timeout,
            )
        self._pending_mcp_configs.append(config)
        return self

    async def _ensure_mcp_connected(self) -> None:
        """Called internally by execution entry points (e.g. agent/harness run)
        to trigger connection of deferred sync-registered servers.
        """
        if not self._pending_mcp_configs:
            return
        configs = list(self._pending_mcp_configs)
        self._pending_mcp_configs.clear()
        try:
            await self.attach_mcp_servers(configs)
        except Exception:
            self._pending_mcp_configs.extend(configs)
            raise

    def mcp_servers(self) -> tuple[McpServerHandle, ...]:
        """Returns all live MCP server handles currently attached to this object."""
        return tuple(self._mcp_handles)

    def mcp_tool_names(self) -> tuple[str, ...]:
        """Returns the names of all tools that were sourced from MCP servers."""
        return tuple(
            name
            for handle in self._mcp_handles
            for name in handle.tool_names
        )

    async def close_mcp_servers(self) -> None:
        """Close all attached MCP server subprocesses and clean up bridged tools.

        Safe to call multiple times.
        """
        if not self._mcp_handles:
            return
        handles = list(self._mcp_handles)
        self._mcp_handles.clear()
        await asyncio.gather(
            *[h.close() for h in handles],
            return_exceptions=True,
        )

        bridged_tool_set = set()
        for h in handles:
            bridged_tool_set.update(h.bridged_tools)

        if bridged_tool_set:
            without = getattr(self.tools, "without", None)
            if callable(without):
                self.tools = without(bridged_tool_set)
            else:
                self.tools = [t for t in self.tools if t not in bridged_tool_set]

    def _attach_tools(self, tools: Sequence[BaseTool]) -> None:
        add_tool = getattr(self, "add_tool", None)
        if callable(add_tool):
            for tool in tools:
                add_tool(tool)
            return
        if not isinstance(self.tools, list):
            self.tools = list(self.tools)
        self.tools.extend(tools)

    async def __aenter__(self) -> McpAttachableMixin:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close_mcp_servers()
