"""FILE: vidbyte/tools/builtins/muse/tools.py

PURPOSE: Defines MuseHostTool, the base of the Muse tools, and the twelve tools over the MuseHost methods: CheckMuseReadyTool, ListMuseModelsTool, SpawnMuseSessionTool, ContinueMuseSessionTool, ForkMuseSessionTool, ListMuseSessionsTool, ReadMuseSessionTool, PageMuseSessionTool, SteerMuseTurnTool, InterruptMuseTurnTool, WaitMuseTurnTool and TrackMuseSessionUsageTool.
ROLE IN CODEBASE: Bundled by MuseTools in vidbyte/tools/toolsets/muse.py; each tool calls one method of a MuseHost (vidbyte/harnesses/native/muse/). Exported by vidbyte/tools/builtins/muse/__init__.py.
ARCHITECTURE NOTE: MuseHostTool is a NativeHostTool over a MuseHost that reports its harness as "muse". Each subclass sets its name, permission, description and parameters and implements _invoke as one argument parse (NativeToolArguments, then the request record) and one host call; the base turns failures into error results. The one blocking call, wait_muse_turn, is capped at NATIVE_TOOL_WAIT_MAX_SECONDS through NativeToolArguments.seconds.
FUNCTION INVENTORY: Each tool's _invoke parses its arguments and calls its host method.
COMMON MODIFICATION PATTERNS: A new public MuseHost method gets one more subclass here, its description in descriptions.py, and its entry in MuseTools (and in MuseTools.read_only when it is READ).
WHAT NOT TO DO IN THIS FILE: 1. Do not add a parameter for an approval mode, the workspace, the launcher, muse_path or the WSL distro; tool-started turns keep the host's safe defaults. 2. Do not catch errors here; the base turns them into results.
KNOWN EDGE CASES: A turn ceiling left out is the record default; a list or page limit left out is NATIVE_LIST_DEFAULT_LIMIT; a direction left out is forward; a wait time left out is NATIVE_WAIT_DEFAULT_SECONDS. Enum arguments must be the exact value strings. A handle that is not an object of three strings is refused as the handle parameter.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 29-40, EC-138 to EC-145
TESTS: tests/features/muse_host/test_muse_host_tools.py, tests/features/muse_host/test_muse_host_errors.py
"""

from __future__ import annotations

import dataclasses
from typing import ClassVar

from vidbyte.harnesses.native.muse import MuseHost
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.muse import MuseTurnRequest
from vidbyte.lib.enums.native_hosts import MuseReasoningEffort, MuseViewDirection
from vidbyte.lib.tools.formatter import ToolsFormatter
from vidbyte.tools.builtins.muse.descriptions import (
    CHECK_MUSE_READY_DESCRIPTION,
    CONTINUE_MUSE_SESSION_DESCRIPTION,
    DIRECTION_PARAMETER_DESCRIPTION,
    FORK_MUSE_SESSION_DESCRIPTION,
    HANDLE_PARAMETER_DESCRIPTION,
    INTERRUPT_MUSE_TURN_DESCRIPTION,
    LAST_TURN_ID_PARAMETER_DESCRIPTION,
    LIST_CURSOR_PARAMETER_DESCRIPTION,
    LIST_LIMIT_PARAMETER_DESCRIPTION,
    LIST_MUSE_MODELS_DESCRIPTION,
    LIST_MUSE_SESSIONS_DESCRIPTION,
    MODEL_PARAMETER_DESCRIPTION,
    PAGE_CURSOR_PARAMETER_DESCRIPTION,
    PAGE_LIMIT_PARAMETER_DESCRIPTION,
    PAGE_MUSE_SESSION_DESCRIPTION,
    PROMPT_PARAMETER_DESCRIPTION,
    READ_MUSE_SESSION_DESCRIPTION,
    REASONING_EFFORT_PARAMETER_DESCRIPTION,
    SESSION_ID_PARAMETER_DESCRIPTION,
    SPAWN_MUSE_SESSION_DESCRIPTION,
    STEER_MUSE_TURN_DESCRIPTION,
    STEER_TEXT_PARAMETER_DESCRIPTION,
    TIMEOUT_PARAMETER_DESCRIPTION,
    TRACK_MUSE_SESSION_USAGE_DESCRIPTION,
    TURN_SECONDS_PARAMETER_DESCRIPTION,
    WAIT_MUSE_TURN_DESCRIPTION,
)
from vidbyte.tools.builtins.native_host_tool import NativeHostTool, NativeToolArguments
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolSpec

_PROMPT = "prompt"
_MODEL = "model"
_REASONING_EFFORT = "reasoning_effort"
_MAX_TURN_SECONDS = "max_turn_seconds"
_SESSION_ID = "session_id"
_LAST_TURN_ID = "last_turn_id"
_CURSOR = "cursor"
_LIMIT = "limit"
_DIRECTION = "direction"
_HANDLE = "handle"
_TEXT = "text"
_TIMEOUT_SECONDS = "timeout_seconds"
_STRING = "string"
_NUMBER = "number"
_INTEGER = "integer"
_OBJECT = "object"

_PROMPT_PARAMETER = ToolParameter(name=_PROMPT, type=_STRING, description=PROMPT_PARAMETER_DESCRIPTION, required=True)
_MODEL_PARAMETER = ToolParameter(name=_MODEL, type=_STRING, description=MODEL_PARAMETER_DESCRIPTION, required=False)
_EFFORT_PARAMETER = ToolParameter(name=_REASONING_EFFORT, type=_STRING, description=REASONING_EFFORT_PARAMETER_DESCRIPTION, required=False)
_TURN_SECONDS_PARAMETER = ToolParameter(name=_MAX_TURN_SECONDS, type=_NUMBER, description=TURN_SECONDS_PARAMETER_DESCRIPTION, required=False)
_SESSION_ID_PARAMETER = ToolParameter(name=_SESSION_ID, type=_STRING, description=SESSION_ID_PARAMETER_DESCRIPTION, required=True)
_HANDLE_PARAMETER = ToolParameter(name=_HANDLE, type=_OBJECT, description=HANDLE_PARAMETER_DESCRIPTION, required=True)


class MuseHostTool(NativeHostTool[MuseHost]):
    """A tool over one MuseHost method; it reports its harness as muse."""

    _HARNESS: ClassVar[str] = "muse"

    def spec(self) -> ToolSpec:
        # @intent muse-effort-schema-lists-its-values
        # reasoning_effort takes only MuseReasoningEffort's values, so
        # the input schema lists them as an enum, as the repo's other
        # categorical tool parameters do; a tool without it keeps the
        # schema its parameters build.
        spec = super().spec()
        schema = ToolsFormatter.input_schema(spec)
        effort = schema["properties"].get(_REASONING_EFFORT)
        if effort is None:
            return spec
        effort["enum"] = [member.value for member in MuseReasoningEffort]
        return dataclasses.replace(spec, input_schema=schema)


class CheckMuseReadyTool(MuseHostTool):
    """Checks that Muse Code is installed, current and speaks MSP 1.0.1."""

    _TOOL_NAME: ClassVar[str] = "check_muse_ready"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = CHECK_MUSE_READY_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: the version check and the handshake.
        return await self._host.check_muse_ready()


class ListMuseModelsTool(MuseHostTool):
    """Lists the models Muse offers."""

    _TOOL_NAME: ClassVar[str] = "list_muse_models"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_MUSE_MODELS_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: the live model catalog.
        return await self._host.list_muse_models()


class SpawnMuseSessionTool(MuseHostTool):
    """Starts a new session with one prompt and returns its turn handle."""

    _TOOL_NAME: ClassVar[str] = "spawn_muse_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = SPAWN_MUSE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_PROMPT_PARAMETER, _MODEL_PARAMETER, _EFFORT_PARAMETER, _TURN_SECONDS_PARAMETER)

    async def _invoke(self, call: ToolCall) -> object:
        # @intent muse-spawn-tool-builds-the-turn-request
        # The turn record checks every value; a ceiling left out is the
        # record's default, and no approval setting can be passed.
        seconds = NativeToolArguments.number(call, _MAX_TURN_SECONDS)
        request = MuseTurnRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            reasoning_effort=NativeToolArguments.choice(call, _REASONING_EFFORT, MuseReasoningEffort),
            max_turn_seconds=native_host_constants.NATIVE_TURN_DEFAULT_SECONDS if seconds is None else seconds,
        )
        return await self._host.spawn_muse_session(request)


class ContinueMuseSessionTool(MuseHostTool):
    """Sends one more prompt to an existing session and returns its turn handle."""

    _TOOL_NAME: ClassVar[str] = "continue_muse_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = CONTINUE_MUSE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_SESSION_ID_PARAMETER, _PROMPT_PARAMETER, _MODEL_PARAMETER, _EFFORT_PARAMETER, _TURN_SECONDS_PARAMETER)

    async def _invoke(self, call: ToolCall) -> object:
        # @intent muse-continue-tool-builds-the-turn-request
        # The session id is checked by the host, the rest by the turn
        # record; no approval setting can be passed.
        session_id = str(NativeToolArguments.text(call, _SESSION_ID, required=True))
        seconds = NativeToolArguments.number(call, _MAX_TURN_SECONDS)
        request = MuseTurnRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            reasoning_effort=NativeToolArguments.choice(call, _REASONING_EFFORT, MuseReasoningEffort),
            max_turn_seconds=native_host_constants.NATIVE_TURN_DEFAULT_SECONDS if seconds is None else seconds,
        )
        return await self._host.continue_muse_session(session_id, request)


class ForkMuseSessionTool(MuseHostTool):
    """Copies a session, whole or up to a turn, into a new session."""

    _TOOL_NAME: ClassVar[str] = "fork_muse_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = FORK_MUSE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _SESSION_ID_PARAMETER,
        ToolParameter(name=_LAST_TURN_ID, type=_STRING, description=LAST_TURN_ID_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # Without a last turn id the whole session is copied.
        session_id = str(NativeToolArguments.text(call, _SESSION_ID, required=True))
        return await self._host.fork_muse_session(session_id, last_turn_id=NativeToolArguments.text(call, _LAST_TURN_ID))


class ListMuseSessionsTool(MuseHostTool):
    """Lists one page of the workspace's sessions."""

    _TOOL_NAME: ClassVar[str] = "list_muse_sessions"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_MUSE_SESSIONS_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        ToolParameter(name=_CURSOR, type=_STRING, description=LIST_CURSOR_PARAMETER_DESCRIPTION, required=False),
        ToolParameter(name=_LIMIT, type=_INTEGER, description=LIST_LIMIT_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # A limit left out is the host's default page size.
        limit = NativeToolArguments.integer(call, _LIMIT)
        page_limit = native_host_constants.NATIVE_LIST_DEFAULT_LIMIT if limit is None else limit
        return await self._host.list_muse_sessions(cursor=NativeToolArguments.text(call, _CURSOR), limit=page_limit)


class ReadMuseSessionTool(MuseHostTool):
    """Reads one session's metadata."""

    _TOOL_NAME: ClassVar[str] = "read_muse_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = READ_MUSE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_SESSION_ID_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The session id is checked by the host.
        return await self._host.read_muse_session(str(NativeToolArguments.text(call, _SESSION_ID, required=True)))


class PageMuseSessionTool(MuseHostTool):
    """Reads one page of a session's event view."""

    _TOOL_NAME: ClassVar[str] = "page_muse_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = PAGE_MUSE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _SESSION_ID_PARAMETER,
        ToolParameter(name=_CURSOR, type=_STRING, description=PAGE_CURSOR_PARAMETER_DESCRIPTION, required=False),
        ToolParameter(name=_LIMIT, type=_INTEGER, description=PAGE_LIMIT_PARAMETER_DESCRIPTION, required=False),
        ToolParameter(name=_DIRECTION, type=_STRING, description=DIRECTION_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The direction is the exact MuseViewDirection value; left out,
        # the page reads forward.
        session_id = str(NativeToolArguments.text(call, _SESSION_ID, required=True))
        limit = NativeToolArguments.integer(call, _LIMIT)
        direction = NativeToolArguments.choice(call, _DIRECTION, MuseViewDirection)
        return await self._host.page_muse_session(
            session_id,
            cursor=NativeToolArguments.text(call, _CURSOR),
            limit=native_host_constants.NATIVE_LIST_DEFAULT_LIMIT if limit is None else limit,
            direction=MuseViewDirection.FORWARD if direction is None else direction,
        )


class SteerMuseTurnTool(MuseHostTool):
    """Adds guidance text to a running turn."""

    _TOOL_NAME: ClassVar[str] = "steer_muse_turn"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = STEER_MUSE_TURN_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _HANDLE_PARAMETER,
        ToolParameter(name=_TEXT, type=_STRING, description=STEER_TEXT_PARAMETER_DESCRIPTION, required=True),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The handle object the spawn or continue result carried; the
        # text is checked by the host.
        handle = NativeToolArguments.handle(call)
        return await self._host.steer_muse_turn(handle, str(NativeToolArguments.text(call, _TEXT, required=True)))


class InterruptMuseTurnTool(MuseHostTool):
    """Asks a running turn to stop."""

    _TOOL_NAME: ClassVar[str] = "interrupt_muse_turn"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = INTERRUPT_MUSE_TURN_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_HANDLE_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The handle object the spawn or continue result carried.
        return await self._host.interrupt_muse_turn(NativeToolArguments.handle(call))


class WaitMuseTurnTool(MuseHostTool):
    """Waits for a turn's result."""

    _TOOL_NAME: ClassVar[str] = "wait_muse_turn"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = WAIT_MUSE_TURN_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _HANDLE_PARAMETER,
        ToolParameter(name=_TIMEOUT_SECONDS, type=_NUMBER, description=TIMEOUT_PARAMETER_DESCRIPTION, required=False, default=native_host_constants.NATIVE_WAIT_DEFAULT_SECONDS),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The wait blocks the tool call, so it is capped at the tool
        # limit; a timed-out wait leaves the turn running.
        handle = NativeToolArguments.handle(call)
        seconds = NativeToolArguments.seconds(call, _TIMEOUT_SECONDS, default=native_host_constants.NATIVE_WAIT_DEFAULT_SECONDS)
        return await self._host.wait_muse_turn(handle, timeout_seconds=seconds)


class TrackMuseSessionUsageTool(MuseHostTool):
    """Reports a session's latest cumulative token usage."""

    _TOOL_NAME: ClassVar[str] = "track_muse_session_usage"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = TRACK_MUSE_SESSION_USAGE_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_SESSION_ID_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The session id is checked by the host.
        return await self._host.track_muse_session_usage(str(NativeToolArguments.text(call, _SESSION_ID, required=True)))


__all__ = [
    "CheckMuseReadyTool",
    "ContinueMuseSessionTool",
    "ForkMuseSessionTool",
    "InterruptMuseTurnTool",
    "ListMuseModelsTool",
    "ListMuseSessionsTool",
    "MuseHostTool",
    "PageMuseSessionTool",
    "ReadMuseSessionTool",
    "SpawnMuseSessionTool",
    "SteerMuseTurnTool",
    "TrackMuseSessionUsageTool",
    "WaitMuseTurnTool",
]
