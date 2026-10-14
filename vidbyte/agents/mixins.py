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
    - _run_releasing_mcp: Awaits one synchronous-entry run, then re-queues its MCP servers for the next loop.
    - _ensure_mcp_connected: Connects pending servers and reconnects any stranded on a closed event loop;
      a run that arrives while another run's attach is in flight waits for it instead of skipping its tools.
Relations:
    Inherited by SDK classes that attach MCP servers. Integrates with vidbyte.tools.mcp.presets.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any, TypeVar

from vidbyte.lib.errors import McpAttachmentError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.mcp.attach import attach_mcp_server
from vidbyte.tools.mcp.presets import McpPresetRegistry
from vidbyte.tools.mcp.types import McpServerConfig, McpServerHandle, McpToolPermission

ResultT = TypeVar("ResultT")


class McpAttachableMixin:
    """Adds Model Context Protocol (MCP) server attachment and lifecycle management
    to any class that owns a tool list (self.tools).
    """

    _mcp_handles: list[McpServerHandle]
    _pending_mcp_configs: list[McpServerConfig]
    # Names a fork's drop_tools removed; bridged MCP tools with these names are never attached.
    _fork_dropped_tool_names: frozenset[str] = frozenset()
    # Set only while one run is connecting pending servers; resolved and cleared when that attach ends.
    _mcp_attach_in_flight: asyncio.Future[None] | None = None
    # The batch an in-flight lazy attach is connecting: out of the queue, not yet among the handles.
    _mcp_attaching_configs: tuple[McpServerConfig, ...] = ()
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
        self._reject_bare_string_command(command)
        config = McpServerConfig(
            command=tuple(command),
            name=name,
            permission=permission,
            env=env,
            timeout=timeout,
        )
        handle = await attach_mcp_server(config)
        await self._register_mcp_handles([handle])
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
        await self._register_mcp_handles([handle])
        return self

    async def attach_mcp_servers(
        self,
        servers: Sequence[McpServerConfig],
    ) -> McpAttachableMixin:
        """Attach multiple MCP servers concurrently.

        If any server fails to start or initialize, all successfully started servers
        in this batch are closed and cleaned up before raising McpAttachmentError.
        If the batch is cancelled, the servers that already started are closed too,
        and the cancellation propagates; no server from the batch is attached.
        If registering their tools fails (say, a tool name already taken), the batch is
        undone and closed the same way and that error propagates unchanged.
        """
        if not servers:
            return self

        # Keep each attempt so a cancelled batch can still find the servers it already started.
        attempts = [asyncio.ensure_future(attach_mcp_server(cfg)) for cfg in servers]
        try:
            results = await asyncio.gather(*attempts, return_exceptions=True)
        except asyncio.CancelledError:
            started = [a.result() for a in attempts if a.done() and not a.cancelled() and a.exception() is None]
            # @intent cancelled-mcp-batch-leaves-no-untracked-server
            # None of them was attached yet, so stop the ones that finished starting before the cancel;
            # a close error is dropped so it cannot replace the cancellation already propagating.
            await asyncio.gather(*[h.close() for h in started], return_exceptions=True)
            raise

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

        await self._register_mcp_handles(handles)
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
        self._reject_bare_string_command(command)
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

    @staticmethod
    def _reject_bare_string_command(command: Sequence[str]) -> None:
        # @intent name-lists-reject-bare-strings
        # A bare string is itself a sequence, so tuple() would spawn its first character as the program.
        if isinstance(command, (str, bytes)):
            raise ValueError('MCP server command must be a list of program arguments (e.g. ["my-mcp-server"]), not a single string.')

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
        to trigger connection of deferred sync-registered servers, and to reconnect
        servers whose connection was opened on an event loop that is no longer running.
        """
        # @intent mcp-handles-reconnect-on-a-new-event-loop
        # Sync wrappers (pipelines, evals, workflows) each run in a fresh asyncio.run loop, and MCP pipes die with theirs.
        live, stale = self._split_mcp_handles_by_loop()
        if stale:
            # Forget the dead connections and the tools that could only fail through them.
            self._mcp_handles[:] = live
            self._drop_mcp_tools(stale)
            # Stop the orphaned server processes without waiting on the loop that owned them.
            for handle in stale:
                self._abandon_mcp_handle(handle)
            # Queue them to reconnect first, in their original order, on the loop running now.
            self._pending_mcp_configs[:0] = [handle.config for handle in stale]
        # @intent overlapping-runs-wait-for-in-flight-mcp-attach
        # Another run on this loop may already be connecting the servers; wait for it, then look again,
        # so this run sees their tools (or retries the attach itself if that one failed).
        while (in_flight := self._mcp_attach_in_flight_on_running_loop()) is not None:
            await asyncio.shield(in_flight)
        # Nothing waiting to connect and nothing connecting means every attached server is live on this loop.
        if not self._pending_mcp_configs:
            return
        configs = list(self._pending_mcp_configs)
        self._pending_mcp_configs.clear()
        # Mark the attach as in flight so overlapping runs wait for it instead of running without its tools.
        attach_done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._mcp_attach_in_flight = attach_done
        # Remember the batch while it boots, so a fork taken meanwhile still inherits these servers.
        self._mcp_attaching_configs = tuple(configs)
        try:
            await self.attach_mcp_servers(configs)
        except BaseException:
            # @intent cancelled-lazy-mcp-attach-requeues-its-servers
            # A failed or cancelled attach (say, a timeout around a run while a slow server boots) attaches
            # none of these servers, so queue them to connect again first, in order, for the next run.
            self._pending_mcp_configs[:0] = configs
            raise
        finally:
            # Release the waiting runs; the marker never outlives this loop's attach.
            self._mcp_attach_in_flight = None
            self._mcp_attaching_configs = ()
            attach_done.set_result(None)

    async def _run_releasing_mcp(self, run: Awaitable[ResultT]) -> ResultT:
        """Await one run started by a synchronous entry point, then release its MCP servers.

        The servers are closed and their configs re-queued, so the next synchronous run
        reconnects them lazily on its own event loop.
        """
        # @intent sync-run-does-not-strand-mcp-on-closed-loop
        # asyncio.run closes its loop on return, which kills any MCP pipes opened inside it.
        try:
            return await run
        finally:
            # Remember every live server's config before closing, in attach order.
            configs = [handle.config for handle in self._mcp_handles]
            # Close the servers while their loop is still running and drop their tools.
            await self.close_mcp_servers()
            # Put them back ahead of anything registered later, so order is preserved.
            self._pending_mcp_configs[:0] = configs

    def mcp_servers(self) -> tuple[McpServerHandle, ...]:
        """Returns all live MCP server handles currently attached to this object."""
        return tuple(self._mcp_handles)

    def mcp_tool_names(self) -> tuple[str, ...]:
        """Returns the names of all tools that were sourced from MCP servers."""
        return tuple(
            name
            for handle in self._mcp_handles
            for name in handle.tool_names
            if name not in self._fork_dropped_tool_names
        )

    def _mcp_configs_for_fork(self) -> tuple[McpServerConfig, ...]:
        # Returns replayable MCP server configs for child agents without sharing live handles.
        # @intent forks-inherit-servers-still-connecting
        # A lazy attach takes its batch out of the queue before the servers boot, so a fork taken meanwhile
        # must still see that batch: connected servers first, then the ones connecting, then the queued ones.
        return (
            tuple(handle.config for handle in self._mcp_handles)
            + self._mcp_attaching_configs
            + tuple(self._pending_mcp_configs)
        )

    def _mcp_bridged_tools_for_fork(self) -> tuple[BaseTool, ...]:
        # Returns parent-owned bridged tool objects that must not be copied into forked agents.
        return tuple(tool for handle in self._mcp_handles for tool in handle.bridged_tools)

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
        self._drop_mcp_tools(handles)

    def _mcp_attach_in_flight_on_running_loop(self) -> asyncio.Future[None] | None:
        # Returns the attach another run started on this loop, ignoring a marker left by any other loop.
        in_flight = self._mcp_attach_in_flight
        if in_flight is None or in_flight.done() or in_flight.get_loop() is not asyncio.get_running_loop():
            return None
        return in_flight

    def _split_mcp_handles_by_loop(self) -> tuple[list[McpServerHandle], list[McpServerHandle]]:
        # Separates handles usable on the running loop from ones stranded on another or closed loop.
        live: list[McpServerHandle] = []
        stale: list[McpServerHandle] = []
        for handle in self._mcp_handles:
            is_bound = getattr(handle.transport, "is_bound_to_running_loop", None)
            if callable(is_bound) and not is_bound():
                stale.append(handle)
            else:
                live.append(handle)
        return live, stale

    @staticmethod
    def _abandon_mcp_handle(handle: McpServerHandle) -> None:
        # Best-effort kill of a server whose loop is gone; there is no loop left to await its close on.
        abandon = getattr(handle.transport, "abandon", None)
        if not callable(abandon):
            return
        try:
            abandon()
        except Exception:
            pass

    def _drop_mcp_tools(self, handles: Sequence[McpServerHandle]) -> None:
        # Removes the given servers' bridged tools from this object's tool lists.
        bridged_tool_set = set()
        for h in handles:
            bridged_tool_set.update(h.bridged_tools)

        if bridged_tool_set:
            without = getattr(self.tools, "without", None)
            if callable(without):
                self.tools = without(bridged_tool_set)
            else:
                self.tools = [t for t in self.tools if t not in bridged_tool_set]
            # Agents also keep their own tool list for forks, exports, and sessions, so drop the closed tools there too.
            agent_tool_items = getattr(self, "_agent_tool_items", None)
            if agent_tool_items is not None:
                self._agent_tool_items = tuple(t for t in agent_tool_items if t not in bridged_tool_set)

    async def _register_mcp_handles(self, handles: Sequence[McpServerHandle]) -> None:
        # Records freshly started servers and attaches their tools, all of them or none.
        try:
            for handle in handles:
                self._mcp_handles.append(handle)
                self._attach_tools(handle.bridged_tools)
        except Exception:
            # Undo every tool and record of these servers, keeping the agent's own tools and older servers.
            self._drop_mcp_tools(handles)
            self._mcp_handles[:] = [h for h in self._mcp_handles if all(h is not mine for mine in handles)]
            # @intent mcp-attach-registers-all-tools-or-none
            # A tool that cannot be added (its name is taken) would leave these servers half attached and running,
            # and a lazy retry would start another copy, so stop them too. A close error is dropped so it cannot
            # replace the registration error being re-raised.
            await asyncio.gather(*[h.close() for h in handles], return_exceptions=True)
            raise

    def _attach_tools(self, tools: Sequence[BaseTool]) -> None:
        # @intent fork-drop-tools-covers-inherited-mcp-tools
        # A forked child replays the parent's MCP servers, so a tool its fork dropped would come back on connect.
        tools = [tool for tool in tools if tool.spec().name not in self._fork_dropped_tool_names]
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
