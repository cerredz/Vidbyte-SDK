"""FILE: vidbyte/tools/builtins/opencode/session_tools.py

PURPOSE: Defines the eight opencode tools that start, change or wait on work: SpawnOpencodeSessionTool, ContinueOpencodeSessionTool, ForkOpencodeSessionTool, RevertOpencodeSessionTool, UnrevertOpencodeSessionTool, WaitOpencodeTurnTool, InterruptOpencodeTurnTool and AddOpencodeMcpServerTool.
ROLE IN CODEBASE: Bundled by OpencodeTools in vidbyte/tools/toolsets/opencode.py; WaitOpencodeTurnTool, the only READ tool here, is also in OpencodeTools.read_only. Built on OpencodeHostTool and the shared parameters of vidbyte/tools/builtins/opencode/read_tools.py. Exported by vidbyte/tools/builtins/opencode/__init__.py.
ARCHITECTURE NOTE: Each tool parses its arguments with NativeToolArguments, builds the host's request record where the host takes one (the record checks every value and names the field), and makes one host call; the base turns failures into error results. The spawn tool never passes permission rules, the wait is capped at NATIVE_TOOL_WAIT_MAX_SECONDS, and the add tool takes only the name of a server the developer registered.
FUNCTION INVENTORY: Each tool's _invoke parses its arguments and calls its host method; AddOpencodeMcpServerTool._invoke first looks the name up in the host's registered servers.
COMMON MODIFICATION PATTERNS: A new OpencodeHost method that starts or changes work gets one more subclass here, its description in descriptions.py, and its entry in OpencodeTools.
WHAT NOT TO DO IN THIS FILE: 1. Do not add a parameter for permission rules, a folder, or an MCP command, URL, environment or header. 2. Do not let a wait run past NATIVE_TOOL_WAIT_MAX_SECONDS; always read it through NativeToolArguments.seconds. 3. Do not build an MCP config from the model's arguments; only a registered config is ever sent.
KNOWN EDGE CASES: A turn ceiling left out is the record's default. An unregistered MCP name is refused before anything is sent, with its own next step. A malformed handle is refused as the handle parameter, whichever part is wrong.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 15-19, 25, 26 and 28, EC-138, EC-144 to EC-146
TESTS: tests/features/opencode_host/test_opencode_host_tools.py, tests/features/opencode_host/test_opencode_host_errors.py, tests/features/opencode_host/test_opencode_host_watcher.py
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.opencode import OpencodePromptRequest, OpencodeSpawnRequest
from vidbyte.lib.enums.native_hosts import NativeHarness
from vidbyte.tools.builtins.native_host_tool import NativeToolArguments
from vidbyte.tools.builtins.opencode.descriptions import (
    ADD_OPENCODE_MCP_SERVER_DESCRIPTION,
    AGENT_PARAMETER_DESCRIPTION,
    CONTINUE_OPENCODE_SESSION_DESCRIPTION,
    FORK_MESSAGE_ID_PARAMETER_DESCRIPTION,
    FORK_OPENCODE_SESSION_DESCRIPTION,
    HANDLE_PARAMETER_DESCRIPTION,
    INTERRUPT_OPENCODE_TURN_DESCRIPTION,
    MAX_TURN_SECONDS_PARAMETER_DESCRIPTION,
    MCP_NAME_PARAMETER_DESCRIPTION,
    MODEL_PARAMETER_DESCRIPTION,
    PART_ID_PARAMETER_DESCRIPTION,
    PROMPT_PARAMETER_DESCRIPTION,
    REVERT_MESSAGE_ID_PARAMETER_DESCRIPTION,
    REVERT_OPENCODE_SESSION_DESCRIPTION,
    SPAWN_OPENCODE_SESSION_DESCRIPTION,
    TIMEOUT_SECONDS_PARAMETER_DESCRIPTION,
    TITLE_PARAMETER_DESCRIPTION,
    UNREVERT_OPENCODE_SESSION_DESCRIPTION,
    WAIT_OPENCODE_TURN_DESCRIPTION,
)
from vidbyte.tools.builtins.opencode.read_tools import (
    MESSAGE_ID,
    NUMBER,
    OBJECT,
    SESSION_ID,
    SESSION_ID_PARAMETER,
    STRING,
    OpencodeHostTool,
)
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission

_PROMPT = "prompt"
_MODEL = "model"
_AGENT = "agent"
_TITLE = "title"
_MAX_TURN_SECONDS = "max_turn_seconds"
_PART_ID = "part_id"
_HANDLE = "handle"
_TIMEOUT_SECONDS = "timeout_seconds"
_NAME = "name"
_UNREGISTERED_MCP_STEP = "Register the MCP server in OpencodeHostSettings.mcp_servers; the tool only adds registered servers."

_PROMPT_PARAMETER = ToolParameter(name=_PROMPT, type=STRING, description=PROMPT_PARAMETER_DESCRIPTION, required=True)
_MODEL_PARAMETER = ToolParameter(name=_MODEL, type=STRING, description=MODEL_PARAMETER_DESCRIPTION, required=False)
_AGENT_PARAMETER = ToolParameter(name=_AGENT, type=STRING, description=AGENT_PARAMETER_DESCRIPTION, required=False)
_TURN_SECONDS_PARAMETER = ToolParameter(name=_MAX_TURN_SECONDS, type=NUMBER, description=MAX_TURN_SECONDS_PARAMETER_DESCRIPTION, required=False)
_HANDLE_PARAMETER = ToolParameter(name=_HANDLE, type=OBJECT, description=HANDLE_PARAMETER_DESCRIPTION, required=True)


class SpawnOpencodeSessionTool(OpencodeHostTool):
    """Creates a session, starts its first turn and returns the turn handle."""

    _TOOL_NAME: ClassVar[str] = "spawn_opencode_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = SPAWN_OPENCODE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _PROMPT_PARAMETER,
        _MODEL_PARAMETER,
        _AGENT_PARAMETER,
        ToolParameter(name=_TITLE, type=STRING, description=TITLE_PARAMETER_DESCRIPTION, required=False),
        _TURN_SECONDS_PARAMETER,
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The records check every value; a ceiling left out is the
        # record's default, and no permission rules are ever passed.
        seconds = NativeToolArguments.number(call, _MAX_TURN_SECONDS)
        turn = OpencodePromptRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            agent=NativeToolArguments.text(call, _AGENT),
            max_turn_seconds=native_host_constants.NATIVE_TURN_DEFAULT_SECONDS if seconds is None else seconds,
        )
        return await self._host.spawn_opencode_session(OpencodeSpawnRequest(turn=turn, title=NativeToolArguments.text(call, _TITLE)))


class ContinueOpencodeSessionTool(OpencodeHostTool):
    """Starts a new turn in an existing session and returns the turn handle."""

    _TOOL_NAME: ClassVar[str] = "continue_opencode_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = CONTINUE_OPENCODE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (SESSION_ID_PARAMETER, _PROMPT_PARAMETER, _MODEL_PARAMETER, _AGENT_PARAMETER, _TURN_SECONDS_PARAMETER)

    async def _invoke(self, call: ToolCall) -> object:
        # The host checks the session id; the record checks the turn's
        # values, with the record's default ceiling.
        session_id = str(NativeToolArguments.text(call, SESSION_ID, required=True))
        seconds = NativeToolArguments.number(call, _MAX_TURN_SECONDS)
        turn = OpencodePromptRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            agent=NativeToolArguments.text(call, _AGENT),
            max_turn_seconds=native_host_constants.NATIVE_TURN_DEFAULT_SECONDS if seconds is None else seconds,
        )
        return await self._host.continue_opencode_session(session_id, turn)


class ForkOpencodeSessionTool(OpencodeHostTool):
    """Copies a session, whole or up to one message, into a new session."""

    _TOOL_NAME: ClassVar[str] = "fork_opencode_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = FORK_OPENCODE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        SESSION_ID_PARAMETER,
        ToolParameter(name=MESSAGE_ID, type=STRING, description=FORK_MESSAGE_ID_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # An optional fork point; the host checks both ids
        # before it sends anything.
        session_id = str(NativeToolArguments.text(call, SESSION_ID, required=True))
        return await self._host.fork_opencode_session(session_id, NativeToolArguments.text(call, MESSAGE_ID))


class RevertOpencodeSessionTool(OpencodeHostTool):
    """Sets a session's revert point to one of its messages or parts."""

    _TOOL_NAME: ClassVar[str] = "revert_opencode_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = REVERT_OPENCODE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        SESSION_ID_PARAMETER,
        ToolParameter(name=MESSAGE_ID, type=STRING, description=REVERT_MESSAGE_ID_PARAMETER_DESCRIPTION, required=True),
        ToolParameter(name=_PART_ID, type=STRING, description=PART_ID_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The revert message is required and the part optional; the host
        # checks all three ids.
        session_id = str(NativeToolArguments.text(call, SESSION_ID, required=True))
        message_id = str(NativeToolArguments.text(call, MESSAGE_ID, required=True))
        return await self._host.revert_opencode_session(session_id, message_id, NativeToolArguments.text(call, _PART_ID))


class UnrevertOpencodeSessionTool(OpencodeHostTool):
    """Removes a session's revert point."""

    _TOOL_NAME: ClassVar[str] = "unrevert_opencode_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = UNREVERT_OPENCODE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (SESSION_ID_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The session id the host checks before it sends anything.
        return await self._host.unrevert_opencode_session(str(NativeToolArguments.text(call, SESSION_ID, required=True)))


class WaitOpencodeTurnTool(OpencodeHostTool):
    """Waits for a turn's outcome."""

    _TOOL_NAME: ClassVar[str] = "wait_opencode_turn"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = WAIT_OPENCODE_TURN_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _HANDLE_PARAMETER,
        ToolParameter(name=_TIMEOUT_SECONDS, type=NUMBER, description=TIMEOUT_SECONDS_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The wait blocks the tool call, so it is capped at the tool
        # limit; a timed-out wait leaves the turn running.
        handle = NativeToolArguments.handle(call)
        seconds = NativeToolArguments.seconds(call, _TIMEOUT_SECONDS, default=native_host_constants.NATIVE_WAIT_DEFAULT_SECONDS)
        return await self._host.wait_opencode_turn(handle, seconds)


class InterruptOpencodeTurnTool(OpencodeHostTool):
    """Aborts a running turn."""

    _TOOL_NAME: ClassVar[str] = "interrupt_opencode_turn"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = INTERRUPT_OPENCODE_TURN_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_HANDLE_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The handle object the spawn or continue result carried.
        return await self._host.interrupt_opencode_turn(NativeToolArguments.handle(call))


class AddOpencodeMcpServerTool(OpencodeHostTool):
    """Adds one MCP server the developer registered on the host."""

    _TOOL_NAME: ClassVar[str] = "add_opencode_mcp_server"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = ADD_OPENCODE_MCP_SERVER_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (ToolParameter(name=_NAME, type=STRING, description=MCP_NAME_PARAMETER_DESCRIPTION, required=True),)

    async def _invoke(self, call: ToolCall) -> object:
        # @intent opencode-mcp-tool-registered-only
        # The model names a server; its command, URL, environment and
        # headers come only from the developer's registration, so an
        # unregistered name is refused before anything is sent.
        name = str(NativeToolArguments.text(call, _NAME, required=True))
        config = self._host.mcp_servers.get(name)
        if config is None:
            raise NativeErrorFactory(NativeHarness.OPENCODE).invalid_argument(_NAME, "No MCP server with that name is registered on this host.", operation=self._TOOL_NAME, next_step=_UNREGISTERED_MCP_STEP)
        return await self._host.add_opencode_mcp_server(config)


__all__ = [
    "AddOpencodeMcpServerTool",
    "ContinueOpencodeSessionTool",
    "ForkOpencodeSessionTool",
    "InterruptOpencodeTurnTool",
    "RevertOpencodeSessionTool",
    "SpawnOpencodeSessionTool",
    "UnrevertOpencodeSessionTool",
    "WaitOpencodeTurnTool",
]
