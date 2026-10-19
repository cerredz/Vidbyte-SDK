"""FILE: vidbyte/tools/builtins/codex/controls.py

PURPOSE: The five CodexHost tools over Codex's settings and state: update_codex_thread_settings and update_codex_turn_settings, which change paid Codex work, and list_codex_collaboration_modes, list_codex_mcp_servers and get_codex_memory_status, which only read.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these among the sixteen first-class tools, in the order of the CodexHost functions.
ARCHITECTURE NOTE: Each tool reads its arguments with the _CodexHostTool resolve_ helpers, calls its host function once and answers through _run, so it never raises (INV-10). The model reaches only a model and an effort on either settings tool; a tier, reviewer, sandbox, folder, plugin list or collaboration mode stays the developer's (first-class INV-43, INV-44). The turn-settings tool accepts only handles its own CodexToolScope created and refuses any other before the host is called.
COMMON MODIFICATION PATTERNS: A new model-settable setting is one schema property, one resolve_ call and one field on the record the tool builds; a setting that widens the posture belongs in spawn_defaults, never in a schema.
KNOWN EDGE CASES: The thread-settings tool answers THREAD_SETTINGS_UPDATED_TEXT, because its function returns nothing for _json to write. The turn-settings tool answers TURN_SETTINGS_STATUS_TEXT, and Codex's targetUnavailable is a normal result there, not an error (first-class INV-25). The MCP listing always asks for the full detail. JSON null means omitted, so a null model or effort leaves that setting unchanged.
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (section 9.2 tool table, rows 27, 28, 31, 32 and 33, and the tool rules; INV-41 to INV-44)
TESTS: tests/features/codex_host/test_codex_host_feature_tools.py, tests/features/codex_host/test_codex_host_tools.py, tests/features/codex_host/test_codex_host_tool_hardening.py
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexMcpServerDetail,
    CodexReasoningEffort,
)
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    CURSOR_DESCRIPTION,
    GET_CODEX_MEMORY_STATUS_DESCRIPTION,
    LIST_CODEX_COLLABORATION_MODES_DESCRIPTION,
    LIST_CODEX_MCP_SERVERS_DESCRIPTION,
    MCP_THREAD_ID_DESCRIPTION,
    SERVER_NAME_DESCRIPTION,
    SETTINGS_EFFORT_DESCRIPTION,
    SETTINGS_MODEL_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
    TURN_ID_DESCRIPTION,
    TURN_SETTINGS_EFFORT_DESCRIPTION,
    TURN_SETTINGS_MODEL_DESCRIPTION,
    UPDATE_CODEX_THREAD_SETTINGS_DESCRIPTION,
    UPDATE_CODEX_TURN_SETTINGS_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

THREAD_SETTINGS = CodexHostOperation.UPDATE_CODEX_THREAD_SETTINGS
MODES = CodexHostOperation.LIST_CODEX_COLLABORATION_MODES
MCP_SERVERS = CodexHostOperation.LIST_CODEX_MCP_SERVERS
TURN_SETTINGS = CodexHostOperation.UPDATE_CODEX_TURN_SETTINGS
MEMORY_STATUS = CodexHostOperation.GET_CODEX_MEMORY_STATUS
EFFORTS = [member.value for member in CodexReasoningEffort if member.value]
THREAD_SETTINGS_UPDATED_TEXT = "Codex updated the settings of thread {thread_id}, and its later turns use them."
TURN_SETTINGS_STATUS_TEXT = "Codex answered {status} to the settings update for turn {turn_id} on thread {thread_id}, where applied means the running turn takes the change and targetUnavailable means no turn was running to take it."


class UpdateCodexThreadSettingsTool(_CodexHostTool):
    """Changes the model or reasoning effort a stored Codex thread uses for its later turns."""

    def spec(self) -> ToolSpec:
        # The thread is required; the model and the effort are the only
        # settings the model may change.
        return ToolSpec(
            name=THREAD_SETTINGS.value,
            description=UPDATE_CODEX_THREAD_SETTINGS_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {
                    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
                    "model": {"type": "string", "description": SETTINGS_MODEL_DESCRIPTION},
                    "effort": {"type": "string", "enum": EFFORTS, "description": SETTINGS_EFFORT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the fixed confirmation; the function returns nothing.
        return await self._run(THREAD_SETTINGS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Only the model and the effort reach the update; every other
        # setting stays as Codex has it (first-class INV-43).
        thread_id = self._resolve_text(call, "thread_id", required=True)
        effort = self._resolve_choice(call, "effort", CodexReasoningEffort)
        settings = CodexThreadSettingsUpdate(model=self._resolve_text(call, "model"), effort=effort if effort is not None else CodexReasoningEffort.PROVIDER_DEFAULT)
        await self._host.update_codex_thread_settings(thread_id, settings)
        return THREAD_SETTINGS_UPDATED_TEXT.format(thread_id=thread_id)


class ListCodexCollaborationModesTool(_CodexHostTool):
    """Lists the collaboration mode presets the Codex app-server offers."""

    def spec(self) -> ToolSpec:
        # No arguments.
        return ToolSpec(
            name=MODES.value,
            description=LIST_CODEX_COLLABORATION_MODES_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={"type": "object", "additionalProperties": False, "properties": {}},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the presets as a JSON array.
        return await self._run(MODES.value, self._perform())

    async def _perform(self) -> str:
        # Read the presets.
        return self._json(await self._host.list_codex_collaboration_modes())


class ListCodexMcpServersTool(_CodexHostTool):
    """Lists one page of the MCP servers Codex knows, with their sign-in and connection status."""

    def spec(self) -> ToolSpec:
        # Every argument is optional.
        return ToolSpec(
            name=MCP_SERVERS.value,
            description=LIST_CODEX_MCP_SERVERS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "thread_id": {"type": "string", "description": MCP_THREAD_ID_DESCRIPTION},
                    "server_name": {"type": "string", "description": SERVER_NAME_DESCRIPTION},
                    "cursor": {"type": "string", "description": CURSOR_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the page as JSON.
        return await self._run(MCP_SERVERS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # The listing always asks for the full detail (section 9.2).
        thread_id = self._resolve_text(call, "thread_id")
        server_name = self._resolve_text(call, "server_name")
        cursor = self._resolve_text(call, "cursor")
        return self._json(await self._host.list_codex_mcp_servers(thread_id=thread_id, server_name=server_name, detail=CodexMcpServerDetail.FULL, cursor=cursor))


class UpdateCodexTurnSettingsTool(_CodexHostTool):
    """Changes the model or reasoning effort of a running turn this toolset started."""

    def spec(self) -> ToolSpec:
        # The handle is required; the model and the effort are the only
        # settings the model may change.
        return ToolSpec(
            name=TURN_SETTINGS.value,
            description=UPDATE_CODEX_TURN_SETTINGS_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id", "turn_id"],
                "properties": {
                    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
                    "turn_id": {"type": "string", "description": TURN_ID_DESCRIPTION},
                    "model": {"type": "string", "description": TURN_SETTINGS_MODEL_DESCRIPTION},
                    "effort": {"type": "string", "enum": EFFORTS, "description": TURN_SETTINGS_EFFORT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the status sentence; the function returns an enum.
        return await self._run(TURN_SETTINGS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # @intent the-turn-settings-tool-reaches-only-model-and-effort
        # Only this scope's handles are changed, and only their model
        # and effort; Codex's answer is a status, and targetUnavailable
        # is a normal result (first-class INV-25, INV-43).
        handle = CodexTurnHandle(thread_id=self._resolve_text(call, "thread_id", required=True), turn_id=self._resolve_text(call, "turn_id", required=True))
        model = self._resolve_text(call, "model")
        effort = self._resolve_choice(call, "effort", CodexReasoningEffort)
        self._scope.require_owned(handle, TURN_SETTINGS)
        status = await self._host.update_codex_turn_settings(handle, model=model, effort=effort if effort is not None else CodexReasoningEffort.PROVIDER_DEFAULT)
        return TURN_SETTINGS_STATUS_TEXT.format(status=status.value, turn_id=handle.turn_id, thread_id=handle.thread_id)


class GetCodexMemoryStatusTool(_CodexHostTool):
    """Reports how many threads Codex consolidated into memories and whether they are ready."""

    def spec(self) -> ToolSpec:
        # No arguments.
        return ToolSpec(
            name=MEMORY_STATUS.value,
            description=GET_CODEX_MEMORY_STATUS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={"type": "object", "additionalProperties": False, "properties": {}},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the status as JSON.
        return await self._run(MEMORY_STATUS.value, self._perform())

    async def _perform(self) -> str:
        # The tool never asks for a minimum count (section 9.2).
        return self._json(await self._host.get_codex_memory_status(min_consolidated_threads=None))


__all__ = [
    "GetCodexMemoryStatusTool",
    "ListCodexCollaborationModesTool",
    "ListCodexMcpServersTool",
    "UpdateCodexThreadSettingsTool",
    "UpdateCodexTurnSettingsTool",
]
