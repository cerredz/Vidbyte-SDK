"""FILE: vidbyte/tools/builtins/grok/tools.py

PURPOSE: Defines GrokHostTool, the base of the Grok tools, and the ten tools over the GrokHost methods: CheckGrokReadyTool, ListGrokModelsTool, SpawnGrokSessionTool, RunGrokOnceTool, ContinueGrokSessionTool, ForkGrokSessionTool, ListGrokSessionsTool, SearchGrokSessionsTool, WaitGrokTurnTool and InterruptGrokTurnTool.
ROLE IN CODEBASE: Bundled by GrokTools in vidbyte/tools/toolsets/grok.py; each tool calls one method of a GrokHost (vidbyte/harnesses/native/grok/). Exported by vidbyte/tools/builtins/grok/__init__.py.
ARCHITECTURE NOTE: GrokHostTool is a NativeHostTool over a GrokHost that reports its harness as "grok". Each subclass sets its name, permission, description and parameters and implements _invoke as one argument parse (NativeToolArguments, then the request record) and one host call; the base turns failures into error results (INV-7). Calls that block (run_grok_once, fork_grok_session, wait_grok_turn) are capped at NATIVE_TOOL_WAIT_MAX_SECONDS through NativeToolArguments.seconds (EC-144).
FUNCTION INVENTORY: Each tool's _invoke parses its arguments and calls its host method.
COMMON MODIFICATION PATTERNS: A new public GrokHost method gets one more subclass here, its description in descriptions.py, and its entry in GrokTools (and in GrokTools.read_only when it is READ).
WHAT NOT TO DO IN THIS FILE: 1. Do not add a parameter for the permission mode, allow or deny rules, allowed tool kinds, the working folder or the grok command (AC-19, INV-9); tool-started turns keep the safe defaults. 2. Do not catch errors here; the base turns them into results.
KNOWN EDGE CASES: A blocking time left out defaults to the tool cap for one-shot and fork runs and to NATIVE_WAIT_DEFAULT_SECONDS for waits; a live turn's ceiling left out is the record default. A handle that is not an object of three strings is refused as the handle parameter (EC-145).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 1-10, EC-138 to EC-145
TESTS: tests/features/grok_host/test_grok_host_tools.py, tests/features/grok_host/test_grok_host_errors.py
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.harnesses.native.grok import GrokHost
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.grok import GrokOneShotRequest, GrokTurnRequest
from vidbyte.tools.builtins.grok.descriptions import (
    CHECK_GROK_READY_DESCRIPTION,
    CONTINUE_GROK_SESSION_DESCRIPTION,
    CURSOR_PARAMETER_DESCRIPTION,
    FORK_GROK_SESSION_DESCRIPTION,
    HANDLE_PARAMETER_DESCRIPTION,
    INTERRUPT_GROK_TURN_DESCRIPTION,
    LIMIT_PARAMETER_DESCRIPTION,
    LIST_GROK_MODELS_DESCRIPTION,
    LIST_GROK_SESSIONS_DESCRIPTION,
    MAX_TURNS_PARAMETER_DESCRIPTION,
    MODEL_PARAMETER_DESCRIPTION,
    NEW_SESSION_ID_PARAMETER_DESCRIPTION,
    ONE_SHOT_PROMPT_PARAMETER_DESCRIPTION,
    ONE_SHOT_SECONDS_PARAMETER_DESCRIPTION,
    QUERY_PARAMETER_DESCRIPTION,
    REASONING_EFFORT_PARAMETER_DESCRIPTION,
    RUN_GROK_ONCE_DESCRIPTION,
    SEARCH_GROK_SESSIONS_DESCRIPTION,
    SESSION_ID_PARAMETER_DESCRIPTION,
    SPAWN_GROK_SESSION_DESCRIPTION,
    TIMEOUT_PARAMETER_DESCRIPTION,
    TURN_PROMPT_PARAMETER_DESCRIPTION,
    TURN_SECONDS_PARAMETER_DESCRIPTION,
    WAIT_GROK_TURN_DESCRIPTION,
)
from vidbyte.tools.builtins.native_host_tool import NativeHostTool, NativeToolArguments
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission

_PROMPT = "prompt"
_MODEL = "model"
_REASONING_EFFORT = "reasoning_effort"
_MAX_TURN_SECONDS = "max_turn_seconds"
_MAX_TURNS = "max_turns"
_SESSION_ID = "session_id"
_NEW_SESSION_ID = "new_session_id"
_CURSOR = "cursor"
_QUERY = "query"
_LIMIT = "limit"
_HANDLE = "handle"
_TIMEOUT_SECONDS = "timeout_seconds"
_STRING = "string"
_NUMBER = "number"
_INTEGER = "integer"
_OBJECT = "object"

_TURN_PROMPT = ToolParameter(name=_PROMPT, type=_STRING, description=TURN_PROMPT_PARAMETER_DESCRIPTION, required=True)
_ONE_SHOT_PROMPT = ToolParameter(name=_PROMPT, type=_STRING, description=ONE_SHOT_PROMPT_PARAMETER_DESCRIPTION, required=True)
_MODEL_PARAMETER = ToolParameter(name=_MODEL, type=_STRING, description=MODEL_PARAMETER_DESCRIPTION, required=False)
_EFFORT_PARAMETER = ToolParameter(name=_REASONING_EFFORT, type=_STRING, description=REASONING_EFFORT_PARAMETER_DESCRIPTION, required=False)
_TURN_SECONDS = ToolParameter(name=_MAX_TURN_SECONDS, type=_NUMBER, description=TURN_SECONDS_PARAMETER_DESCRIPTION, required=False)
_ONE_SHOT_SECONDS = ToolParameter(name=_MAX_TURN_SECONDS, type=_NUMBER, description=ONE_SHOT_SECONDS_PARAMETER_DESCRIPTION, required=False)
_MAX_TURNS_PARAMETER = ToolParameter(name=_MAX_TURNS, type=_INTEGER, description=MAX_TURNS_PARAMETER_DESCRIPTION, required=False)
_SESSION_ID_PARAMETER = ToolParameter(name=_SESSION_ID, type=_STRING, description=SESSION_ID_PARAMETER_DESCRIPTION, required=True)
_NEW_SESSION_ID_PARAMETER = ToolParameter(name=_NEW_SESSION_ID, type=_STRING, description=NEW_SESSION_ID_PARAMETER_DESCRIPTION, required=False)
_HANDLE_PARAMETER = ToolParameter(name=_HANDLE, type=_OBJECT, description=HANDLE_PARAMETER_DESCRIPTION, required=True)


class GrokHostTool(NativeHostTool[GrokHost]):
    """A tool over one GrokHost method; it reports its harness as grok."""

    _HARNESS: ClassVar[str] = "grok"


class CheckGrokReadyTool(GrokHostTool):
    """Checks that Grok Build is installed, current and signed in."""

    _TOOL_NAME: ClassVar[str] = "check_grok_ready"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = CHECK_GROK_READY_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: the three-step readiness check.
        return await self._host.check_grok_ready()


class ListGrokModelsTool(GrokHostTool):
    """Lists the models Grok offers and their reasoning efforts."""

    _TOOL_NAME: ClassVar[str] = "list_grok_models"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_GROK_MODELS_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: the live model catalog.
        return await self._host.list_grok_models()


class SpawnGrokSessionTool(GrokHostTool):
    """Starts a new session with one prompt and returns its turn handle."""

    _TOOL_NAME: ClassVar[str] = "spawn_grok_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = SPAWN_GROK_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_TURN_PROMPT, _MODEL_PARAMETER, _EFFORT_PARAMETER, _TURN_SECONDS)

    async def _invoke(self, call: ToolCall) -> object:
        # The turn record checks every value; a ceiling left out is the record's default, and no tool kind is allowed.
        seconds = NativeToolArguments.number(call, _MAX_TURN_SECONDS)
        turn = GrokTurnRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            reasoning_effort=NativeToolArguments.text(call, _REASONING_EFFORT),
            max_turn_seconds=native_host_constants.NATIVE_TURN_DEFAULT_SECONDS if seconds is None else seconds,
        )
        return await self._host.spawn_grok_session(turn)


class RunGrokOnceTool(GrokHostTool):
    """Runs one headless prompt and returns its answer."""

    _TOOL_NAME: ClassVar[str] = "run_grok_once"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = RUN_GROK_ONCE_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_ONE_SHOT_PROMPT, _MODEL_PARAMETER, _EFFORT_PARAMETER, _MAX_TURNS_PARAMETER, _ONE_SHOT_SECONDS)

    async def _invoke(self, call: ToolCall) -> object:
        # The run blocks the tool call, so its time is capped at the tool limit (EC-144); the permission mode stays Grok's default.
        one_shot = GrokOneShotRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            reasoning_effort=NativeToolArguments.text(call, _REASONING_EFFORT),
            max_turns=NativeToolArguments.integer(call, _MAX_TURNS),
            max_turn_seconds=NativeToolArguments.seconds(call, _MAX_TURN_SECONDS, default=native_host_constants.NATIVE_TOOL_WAIT_MAX_SECONDS),
        )
        return await self._host.run_grok_once(one_shot)


class ContinueGrokSessionTool(GrokHostTool):
    """Sends one more prompt to an existing session and returns its turn handle."""

    _TOOL_NAME: ClassVar[str] = "continue_grok_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = CONTINUE_GROK_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_SESSION_ID_PARAMETER, _TURN_PROMPT, _MODEL_PARAMETER, _EFFORT_PARAMETER, _TURN_SECONDS)

    async def _invoke(self, call: ToolCall) -> object:
        # The session id must be text; the host checks its form before anything starts.
        session_id = str(NativeToolArguments.text(call, _SESSION_ID, required=True))
        seconds = NativeToolArguments.number(call, _MAX_TURN_SECONDS)
        turn = GrokTurnRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            reasoning_effort=NativeToolArguments.text(call, _REASONING_EFFORT),
            max_turn_seconds=native_host_constants.NATIVE_TURN_DEFAULT_SECONDS if seconds is None else seconds,
        )
        return await self._host.continue_grok_session(session_id, turn)


class ForkGrokSessionTool(GrokHostTool):
    """Forks an existing session and runs one headless prompt on the copy."""

    _TOOL_NAME: ClassVar[str] = "fork_grok_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = FORK_GROK_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _SESSION_ID_PARAMETER,
        _ONE_SHOT_PROMPT,
        _NEW_SESSION_ID_PARAMETER,
        _MODEL_PARAMETER,
        _EFFORT_PARAMETER,
        _MAX_TURNS_PARAMETER,
        _ONE_SHOT_SECONDS,
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The fork blocks the tool call, so its time is capped at the tool limit (EC-144); the host checks both ids.
        session_id = str(NativeToolArguments.text(call, _SESSION_ID, required=True))
        new_session_id = NativeToolArguments.text(call, _NEW_SESSION_ID)
        one_shot = GrokOneShotRequest(
            prompt=str(NativeToolArguments.text(call, _PROMPT, required=True)),
            model=NativeToolArguments.text(call, _MODEL),
            reasoning_effort=NativeToolArguments.text(call, _REASONING_EFFORT),
            max_turns=NativeToolArguments.integer(call, _MAX_TURNS),
            max_turn_seconds=NativeToolArguments.seconds(call, _MAX_TURN_SECONDS, default=native_host_constants.NATIVE_TOOL_WAIT_MAX_SECONDS),
        )
        return await self._host.fork_grok_session(session_id, one_shot, new_session_id=new_session_id)


class ListGrokSessionsTool(GrokHostTool):
    """Lists one page of this workspace's sessions."""

    _TOOL_NAME: ClassVar[str] = "list_grok_sessions"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_GROK_SESSIONS_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (ToolParameter(name=_CURSOR, type=_STRING, description=CURSOR_PARAMETER_DESCRIPTION, required=False),)

    async def _invoke(self, call: ToolCall) -> object:
        # The cursor is optional text, passed back verbatim.
        return await self._host.list_grok_sessions(cursor=NativeToolArguments.text(call, _CURSOR))


class SearchGrokSessionsTool(GrokHostTool):
    """Finds this workspace's sessions whose title contains a query."""

    _TOOL_NAME: ClassVar[str] = "search_grok_sessions"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = SEARCH_GROK_SESSIONS_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        ToolParameter(name=_QUERY, type=_STRING, description=QUERY_PARAMETER_DESCRIPTION, required=True),
        ToolParameter(name=_LIMIT, type=_INTEGER, description=LIMIT_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The query is required text; a limit left out is the host's default.
        query = str(NativeToolArguments.text(call, _QUERY, required=True))
        limit = NativeToolArguments.integer(call, _LIMIT)
        return await self._host.search_grok_sessions(query, limit=native_host_constants.GROK_SEARCH_DEFAULT_LIMIT if limit is None else limit)


class WaitGrokTurnTool(GrokHostTool):
    """Waits for a live turn's result."""

    _TOOL_NAME: ClassVar[str] = "wait_grok_turn"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = WAIT_GROK_TURN_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        _HANDLE_PARAMETER,
        ToolParameter(name=_TIMEOUT_SECONDS, type=_NUMBER, description=TIMEOUT_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # The wait blocks the tool call, so it is capped at the tool limit (EC-144); cancelling it leaves the turn running.
        handle = NativeToolArguments.handle(call)
        seconds = NativeToolArguments.seconds(call, _TIMEOUT_SECONDS, default=native_host_constants.NATIVE_WAIT_DEFAULT_SECONDS)
        return await self._host.wait_grok_turn(handle, timeout_seconds=seconds)


class InterruptGrokTurnTool(GrokHostTool):
    """Asks a live turn to stop."""

    _TOOL_NAME: ClassVar[str] = "interrupt_grok_turn"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.WRITE
    _DESCRIPTION: ClassVar[str] = INTERRUPT_GROK_TURN_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (_HANDLE_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The handle object the spawn or continue result carried.
        return await self._host.interrupt_grok_turn(NativeToolArguments.handle(call))


__all__ = [
    "CheckGrokReadyTool",
    "ContinueGrokSessionTool",
    "ForkGrokSessionTool",
    "GrokHostTool",
    "InterruptGrokTurnTool",
    "ListGrokModelsTool",
    "ListGrokSessionsTool",
    "RunGrokOnceTool",
    "SearchGrokSessionsTool",
    "SpawnGrokSessionTool",
    "WaitGrokTurnTool",
]
