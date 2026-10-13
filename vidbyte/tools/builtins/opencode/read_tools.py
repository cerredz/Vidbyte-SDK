"""FILE: vidbyte/tools/builtins/opencode/read_tools.py

PURPOSE: Defines OpencodeHostTool, the base of the opencode tools, the parameters several opencode tools share, and the ten READ tools that only read from the server: CheckOpencodeReadyTool, ListOpencodeModelsTool, ListOpencodeProvidersTool, GetOpencodeProviderAuthTool, ListOpencodeSessionsTool, GetOpencodeSessionTool, GetOpencodeSessionMessagesTool, GetOpencodeMessageTool, GetOpencodeSessionDiffTool and TrackOpencodeSessionUsageTool (§9.2 rows 11-14, 20-24 and 27).
ROLE IN CODEBASE: Bundled by OpencodeTools in vidbyte/tools/toolsets/opencode.py, and by OpencodeTools.read_only together with WaitOpencodeTurnTool; vidbyte/tools/builtins/opencode/session_tools.py builds its tools on OpencodeHostTool and the shared parameters here. Exported by vidbyte/tools/builtins/opencode/__init__.py.
ARCHITECTURE NOTE: OpencodeHostTool is a NativeHostTool over an OpencodeHost that reports its harness as "opencode". Each subclass sets its name, permission, description and parameters and implements _invoke as one argument parse (NativeToolArguments) and one host call; the base turns failures into error results (INV-7). A host call that returns a tuple is wrapped in an object under one plural key, so every tool answers a JSON object.
FUNCTION INVENTORY: Each tool's _invoke parses its arguments and calls its host method.
COMMON MODIFICATION PATTERNS: A new read-only OpencodeHost method gets one more subclass here, its description in descriptions.py, and its entry in OpencodeTools and OpencodeTools.read_only.
WHAT NOT TO DO IN THIS FILE: 1. Do not give a tool a parameter for permission rules, a folder, or an MCP command, URL, environment or header (AC-19, INV-9, T-2). 2. Do not check an argument's range or pattern here; the host's checks are the single source and name the parameter. 3. Do not add a WRITE tool here; those live in session_tools.py.
KNOWN EDGE CASES: A limit left out is the host's default page size, read when the call runs. A required parameter missing from a direct execute() call is refused as configuration.invalid_argument naming it (EC-138).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 11-14, 20-24 and 27, EC-138
TESTS: tests/features/opencode_host/test_opencode_host_tools.py, tests/features/opencode_host/test_opencode_host_errors.py, tests/features/opencode_host/test_opencode_host_security.py
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.harnesses.native.opencode import OpencodeHost
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.tools.builtins.native_host_tool import NativeHostTool, NativeToolArguments
from vidbyte.tools.builtins.opencode.descriptions import (
    BEFORE_PARAMETER_DESCRIPTION,
    CHECK_OPENCODE_READY_DESCRIPTION,
    DIFF_MESSAGE_ID_PARAMETER_DESCRIPTION,
    GET_OPENCODE_MESSAGE_DESCRIPTION,
    GET_OPENCODE_PROVIDER_AUTH_DESCRIPTION,
    GET_OPENCODE_SESSION_DESCRIPTION,
    GET_OPENCODE_SESSION_DIFF_DESCRIPTION,
    GET_OPENCODE_SESSION_MESSAGES_DESCRIPTION,
    LIST_OPENCODE_MODELS_DESCRIPTION,
    LIST_OPENCODE_PROVIDERS_DESCRIPTION,
    LIST_OPENCODE_SESSIONS_DESCRIPTION,
    MESSAGE_ID_PARAMETER_DESCRIPTION,
    MESSAGES_LIMIT_PARAMETER_DESCRIPTION,
    PROVIDER_ID_PARAMETER_DESCRIPTION,
    SESSION_ID_PARAMETER_DESCRIPTION,
    SESSIONS_LIMIT_PARAMETER_DESCRIPTION,
    TRACK_OPENCODE_SESSION_USAGE_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission

SESSION_ID = "session_id"
MESSAGE_ID = "message_id"
STRING = "string"
NUMBER = "number"
INTEGER = "integer"
OBJECT = "object"
_PROVIDER_ID = "provider_id"
_LIMIT = "limit"
_BEFORE = "before"

SESSION_ID_PARAMETER = ToolParameter(name=SESSION_ID, type=STRING, description=SESSION_ID_PARAMETER_DESCRIPTION, required=True)
_DIFF_MESSAGE_ID_PARAMETER = ToolParameter(name=MESSAGE_ID, type=STRING, description=DIFF_MESSAGE_ID_PARAMETER_DESCRIPTION, required=False)


class OpencodeHostTool(NativeHostTool[OpencodeHost]):
    """A tool over one OpencodeHost method; it reports its harness as opencode."""

    _HARNESS: ClassVar[str] = "opencode"


class CheckOpencodeReadyTool(OpencodeHostTool):
    """Checks that the opencode server is healthy, current and has a connected provider."""

    _TOOL_NAME: ClassVar[str] = "check_opencode_ready"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = CHECK_OPENCODE_READY_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: the health, version and provider check.
        return await self._host.check_opencode_ready()


class ListOpencodeModelsTool(OpencodeHostTool):
    """Lists the models of the connected providers."""

    _TOOL_NAME: ClassVar[str] = "list_opencode_models"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_OPENCODE_MODELS_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (ToolParameter(name=_PROVIDER_ID, type=STRING, description=PROVIDER_ID_PARAMETER_DESCRIPTION, required=False),)

    async def _invoke(self, call: ToolCall) -> object:
        # @intent opencode-models-tool-provider-filter
        # The provider id is only a filter the host checks before any request;
        # the models come back under one key, so the result is a JSON object.
        return {"models": await self._host.list_opencode_models(NativeToolArguments.text(call, _PROVIDER_ID))}


class ListOpencodeProvidersTool(OpencodeHostTool):
    """Lists every provider the server knows, connected or not."""

    _TOOL_NAME: ClassVar[str] = "list_opencode_providers"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_OPENCODE_PROVIDERS_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: the providers come back under one key, without keys or options.
        return {"providers": await self._host.list_opencode_providers()}


class GetOpencodeProviderAuthTool(OpencodeHostTool):
    """Lists the ways each provider can be connected."""

    _TOOL_NAME: ClassVar[str] = "get_opencode_provider_auth"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = GET_OPENCODE_PROVIDER_AUTH_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # @intent opencode-provider-auth-tool-reads-only
        # No arguments and nothing connected: each provider's auth methods
        # come back under one key, so the result is a JSON object.
        return {"providers": await self._host.get_opencode_provider_auth()}


class ListOpencodeSessionsTool(OpencodeHostTool):
    """Lists the server's sessions, most recently updated first."""

    _TOOL_NAME: ClassVar[str] = "list_opencode_sessions"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_OPENCODE_SESSIONS_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (ToolParameter(name=_LIMIT, type=INTEGER, description=SESSIONS_LIMIT_PARAMETER_DESCRIPTION, required=False),)

    async def _invoke(self, call: ToolCall) -> object:
        # A limit left out is the host's default page size; the sessions come back under one key.
        limit = NativeToolArguments.integer(call, _LIMIT)
        sessions = await self._host.list_opencode_sessions(native_host_constants.NATIVE_LIST_DEFAULT_LIMIT if limit is None else limit)
        return {"sessions": sessions}


class GetOpencodeSessionTool(OpencodeHostTool):
    """Reads one session."""

    _TOOL_NAME: ClassVar[str] = "get_opencode_session"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = GET_OPENCODE_SESSION_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (SESSION_ID_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The session id the host checks before it sends anything.
        return await self._host.get_opencode_session(str(NativeToolArguments.text(call, SESSION_ID, required=True)))


class GetOpencodeSessionMessagesTool(OpencodeHostTool):
    """Reads one page of a session's messages."""

    _TOOL_NAME: ClassVar[str] = "get_opencode_session_messages"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = GET_OPENCODE_SESSION_MESSAGES_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        SESSION_ID_PARAMETER,
        ToolParameter(name=_LIMIT, type=INTEGER, description=MESSAGES_LIMIT_PARAMETER_DESCRIPTION, required=False),
        ToolParameter(name=_BEFORE, type=STRING, description=BEFORE_PARAMETER_DESCRIPTION, required=False),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # A limit left out is the host's default page size; before pages back from a message id.
        session_id = str(NativeToolArguments.text(call, SESSION_ID, required=True))
        limit = NativeToolArguments.integer(call, _LIMIT)
        before = NativeToolArguments.text(call, _BEFORE)
        return await self._host.get_opencode_session_messages(session_id, native_host_constants.NATIVE_LIST_DEFAULT_LIMIT if limit is None else limit, before)


class GetOpencodeMessageTool(OpencodeHostTool):
    """Reads one message of a session."""

    _TOOL_NAME: ClassVar[str] = "get_opencode_message"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = GET_OPENCODE_MESSAGE_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (
        SESSION_ID_PARAMETER,
        ToolParameter(name=MESSAGE_ID, type=STRING, description=MESSAGE_ID_PARAMETER_DESCRIPTION, required=True),
    )

    async def _invoke(self, call: ToolCall) -> object:
        # Both ids are required; the host checks the session before the message.
        session_id = str(NativeToolArguments.text(call, SESSION_ID, required=True))
        message_id = str(NativeToolArguments.text(call, MESSAGE_ID, required=True))
        return await self._host.get_opencode_message(session_id, message_id)


class GetOpencodeSessionDiffTool(OpencodeHostTool):
    """Lists the files a session, or one of its messages, changed."""

    _TOOL_NAME: ClassVar[str] = "get_opencode_session_diff"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = GET_OPENCODE_SESSION_DIFF_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (SESSION_ID_PARAMETER, _DIFF_MESSAGE_ID_PARAMETER)

    async def _invoke(self, call: ToolCall) -> object:
        # An optional message id narrows the diff; the changed files come back under one key.
        session_id = str(NativeToolArguments.text(call, SESSION_ID, required=True))
        return {"files": await self._host.get_opencode_session_diff(session_id, NativeToolArguments.text(call, MESSAGE_ID))}


class TrackOpencodeSessionUsageTool(OpencodeHostTool):
    """Reports a session's usage totals and per-message breakdown."""

    _TOOL_NAME: ClassVar[str] = "track_opencode_session_usage"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = TRACK_OPENCODE_SESSION_USAGE_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (SESSION_ID_PARAMETER,)

    async def _invoke(self, call: ToolCall) -> object:
        # The session id the host checks before it sends anything.
        return await self._host.track_opencode_session_usage(str(NativeToolArguments.text(call, SESSION_ID, required=True)))


__all__ = [
    "INTEGER",
    "MESSAGE_ID",
    "NUMBER",
    "OBJECT",
    "SESSION_ID",
    "SESSION_ID_PARAMETER",
    "STRING",
    "CheckOpencodeReadyTool",
    "GetOpencodeMessageTool",
    "GetOpencodeProviderAuthTool",
    "GetOpencodeSessionDiffTool",
    "GetOpencodeSessionMessagesTool",
    "GetOpencodeSessionTool",
    "ListOpencodeModelsTool",
    "ListOpencodeProvidersTool",
    "ListOpencodeSessionsTool",
    "OpencodeHostTool",
    "TrackOpencodeSessionUsageTool",
]
