"""FILE: vidbyte/harnesses/native/codex/settings_methods.py

PURPOSE: CodexSettingsMethods, the CodexHost mixin for settings, plan mode, MCP servers and memories: it changes a stored thread's settings and a running turn's, lists Codex's collaboration mode presets and runs a plan-mode turn, lists the MCP servers Codex knows, and sets, reads and resets Codex's memories.
ROLE IN CODEBASE: One of the four feature mixins of vidbyte/harnesses/native/codex/; CodexHost inherits its eight public methods, so a caller reaches them on the host itself (first-class D-1). Each method is a thin narrated main function over the host's own collaborators, which CodexHostCore declares and CodexHost._open builds.
ARCHITECTURE NOTE: Imports no openai-codex module and none of the host's SDK-loading collaborators at module level; their types appear only under TYPE_CHECKING, so importing this mixin, or CodexHost, still loads no SDK (first-class INV-45). Every request goes through CodexConnection.call, so each writes one call record, and every answer is parsed on the worker by CodexFeatureResponseTranslator inside its own call (INV-3, INV-6). Every method runs _guard, then its input record, then the experimental gate where one applies, and only then anything else (INV-1, INV-4).
COMMON MODIFICATION PATTERNS: A new settings function is one public method here: guard, its record from vidbyte/lib/dataclasses/codex_host_inputs.py, CodexPreflight.require_experimental_api when Codex marks the call experimental, then one call whose params come from CodexFeatureParamsTranslator and whose parse step is a CodexFeatureResponseTranslator method. Its messages go in vidbyte/lib/constants/codex_host.py, never here.
KNOWN EDGE CASES: A thread settings update loads a thread that is not loaded here, and refuses one whose stored goal is active, because loading could let Codex continue that goal (INV-12, D-14); it is allowed on a thread with a running turn, which keeps its settings (EC-5). A turn settings update acts only on a running turn this host started, and a goal run between its physical turns returns TARGET_UNAVAILABLE without a request (INV-25, EC-24). Neither update re-prices a turn already running (NG-12). run_codex_plan relabels every error it raises (INV-16).
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.5, 9.2 and 12.3 row 26, INV-1, INV-4, INV-11 to INV-16, INV-24 to INV-26, D-1, D-14, D-16)
TESTS: tests/features/codex_host/test_codex_host_settings_modes.py, tests/features/codex_host/test_codex_host_mcp_memory.py, tests/features/codex_host/test_codex_host_feature_contract.py, tests/features/codex_host/test_codex_host_feature_structure.py, tests/features/codex_host/test_codex_host_feature_docs.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.harnesses.native.codex.host_core import CodexHostCore
from vidbyte.lib.constants.codex_host import (
    CODEX_COLLABORATION_MODE_LIST_METHOD,
    CODEX_HOST_TURN_SETTINGS_FINISHED_MESSAGE,
    CODEX_MCP_SERVER_STATUS_LIST_METHOD,
    CODEX_MEMORY_RESET_METHOD,
    CODEX_MEMORY_STATUS_METHOD,
    CODEX_THREAD_MEMORY_MODE_SET_METHOD,
    CODEX_THREAD_SETTINGS_UPDATE_METHOD,
    CODEX_TURN_SETTINGS_UPDATE_METHOD,
)
from vidbyte.lib.dataclasses.codex import CodexRunInput, CodexTurnSettings
from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest, CodexTurnHandle
from vidbyte.lib.dataclasses.codex_host_features import (
    CodexMcpServerPage,
    CodexMemoryStatus,
    CodexThreadSettingsUpdate,
)
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexMcpServerListRequest,
    CodexMemoryModeRequest,
    CodexMemoryStatusRequest,
    CodexPlanRunRequest,
    CodexThreadSettingsRequest,
    CodexTurnSettingsRequest,
)
from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationModePreset
from vidbyte.lib.enums.codex import (
    CodexApprovalsReviewer,
    CodexHostOperation,
    CodexMcpServerDetail,
    CodexMemoryMode,
    CodexReasoningEffort,
    CodexReasoningSummary,
    CodexTurnSettingsStatus,
)
from vidbyte.lib.enums.failure import FailureCode


class CodexSettingsMethods(CodexHostCore):
    """The settings, plan-mode, MCP-server and memory functions CodexHost inherits."""

    async def update_codex_thread_settings(self, thread_id: str, settings: CodexThreadSettingsUpdate) -> None:
        """Change a stored thread's settings for its later turns; it needs Codex's experimental API.

        Only the fields set on ``settings`` are sent. A turn already
        running keeps its own settings and its price: this host prices
        each turn as the model Codex resolved when it started, so a model
        change re-prices only turns started afterwards. A thread not
        loaded on this host is loaded first, and is refused with
        codex.goal_unfinished while its stored goal is active. Codex's
        notification of the change is not read, so nothing is read back.
        """
        # @intent a-settings-update-checks-then-sends-once
        # Change a stored thread's settings with one request, after
        # the same checks a turn would get (first-class INV-11, INV-12).
        operation = CodexHostOperation.UPDATE_CODEX_THREAD_SETTINGS
        self._guard(operation, talks=True)
        update = CodexThreadSettingsRequest(thread_id=thread_id, settings=settings)
        self._preflight.require_experimental_api(operation, CODEX_THREAD_SETTINGS_UPDATE_METHOD)
        # Check the reviewer, the mode and every model and tier named,
        # through a spawn-shaped view of the update; nothing spends.
        changes = update.settings
        view = CodexSpawnRequest(
            turn=CodexTurnSettings(model=changes.model),
            turn_service_tier=changes.service_tier,
            approvals_reviewer=changes.approvals_reviewer,
            collaboration_mode=changes.collaboration_mode,
        )
        await self._preflight.run(operation, view, spends=False)
        # The thread must exist, and one not loaded here is loaded
        # first, unless its stored goal could restart (D-14).
        status = await self._threads.status(operation, update.thread_id)
        await self._threads.load(operation, update.thread_id, status)
        # Send exactly the settings that were set.
        connection = self._connection
        params = self._feature_params.thread_settings(update.thread_id, changes)
        send = connection.raw(CODEX_THREAD_SETTINGS_UPDATE_METHOD, params, parse=self._feature_responses.empty)
        await connection.call(operation, CODEX_THREAD_SETTINGS_UPDATE_METHOD, send, thread_id=update.thread_id)

    async def list_codex_collaboration_modes(self) -> tuple[CodexCollaborationModePreset, ...]:
        """The collaboration mode presets Codex offers, in its order; it needs Codex's experimental API.

        A preset Codex lists with no mode has CodexCollaborationModeKind.NONE,
        and its model or effort is blank when Codex names none. The effort
        stays open text, so an effort newer than CodexReasoningEffort is
        shown rather than refused.
        """
        # Codex marks the preset list experimental, so a host without
        # its experimental API is refused before anything is sent.
        operation = CodexHostOperation.LIST_CODEX_COLLABORATION_MODES
        self._guard(operation, talks=True)
        self._preflight.require_experimental_api(operation, CODEX_COLLABORATION_MODE_LIST_METHOD)
        # Ask once, and return the presets in Codex's order
        # (first-class INV-15).
        connection = self._connection
        listing = connection.raw(CODEX_COLLABORATION_MODE_LIST_METHOD, None, parse=self._feature_responses.modes)
        return await connection.call(operation, CODEX_COLLABORATION_MODE_LIST_METHOD, listing)

    async def run_codex_plan(self, prompt: str | CodexRunInput, request: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        """Start a new thread whose first turn runs in Codex's own plan preset; it needs Codex's experimental API.

        The turn's model and effort win over the preset's. The plan Codex
        writes is the turn's answer. Plan-mode questions go to the host's
        approval_handler, and are answered with no answers on a host
        without one. A later continue_codex_thread sends no mode, so Codex
        decides whether the thread stays in plan mode; pass
        CodexCollaborationMode(mode=CodexCollaborationModeKind.DEFAULT) to
        leave it. Every error names run_codex_plan.
        """
        # @intent a-plan-run-is-checked-here-and-run-by-the-wrapper
        # Check the request, the experimental API and the reviewer,
        # then let the run wrapper list the presets and spawn the one
        # plan turn (first-class INV-16). Only a missing request means
        # the default, so any other value reaches the record.
        operation = CodexHostOperation.RUN_CODEX_PLAN
        self._guard(operation, talks=True)
        plan_run = CodexPlanRunRequest(prompt=prompt, request=CodexSpawnRequest() if request is None else request)
        self._preflight.require_experimental_api(operation, CODEX_COLLABORATION_MODE_LIST_METHOD)
        self._preflight.reject_user_reviewer(operation, plan_run.request)
        return await self._skills.run_plan(plan_run)

    async def list_codex_mcp_servers(
        self,
        thread_id: str = "",
        server_name: str = "",
        detail: CodexMcpServerDetail = CodexMcpServerDetail.FULL,
        cursor: str = "",
        limit: int | None = None,
    ) -> CodexMcpServerPage:
        """One page of the MCP servers Codex knows, with each one's sign-in and connection status.

        Listing may start a server Codex had not started yet. An unknown
        thread_id is Codex's own refusal, as codex.api_error, because the
        filter is optional and nothing reads the thread first.
        """
        # Check the host and the filter and page arguments. The thread
        # filter is optional, so the thread is not read first, and
        # Codex itself refuses an unknown one.
        operation = CodexHostOperation.LIST_CODEX_MCP_SERVERS
        self._guard(operation, talks=True)
        listing = CodexMcpServerListRequest(thread_id=thread_id, server_name=server_name, detail=detail, cursor=cursor, limit=limit)
        # Ask Codex for one page of servers with their sign-in and
        # connection status; listing may start a server.
        connection = self._connection
        page = connection.raw(CODEX_MCP_SERVER_STATUS_LIST_METHOD, self._feature_params.mcp_servers(listing), parse=self._feature_responses.mcp_page)
        return await connection.call(operation, CODEX_MCP_SERVER_STATUS_LIST_METHOD, page, thread_id=listing.thread_id)

    async def update_codex_turn_settings(
        self,
        handle: CodexTurnHandle,
        model: str = "",
        effort: CodexReasoningEffort = CodexReasoningEffort.PROVIDER_DEFAULT,
        summary: CodexReasoningSummary = CodexReasoningSummary.PROVIDER_DEFAULT,
        service_tier: str = "",
        clear_service_tier: bool = False,
        approvals_reviewer: CodexApprovalsReviewer = CodexApprovalsReviewer.PROVIDER_DEFAULT,
    ) -> CodexTurnSettingsStatus:
        """Change a running turn this host started; it needs Codex's experimental API.

        A goal run is changed through the physical turn running now, and
        TARGET_UNAVAILABLE comes back, without a request, when none is.
        The turn stays priced as the model it started with, so a model
        change does not change its price.
        """
        # @intent a-turn-settings-update-targets-a-running-owned-turn
        # Change only a turn this host registered and that is still
        # running, after the reviewer, model and tier checks
        # (first-class INV-25).
        operation = CodexHostOperation.UPDATE_CODEX_TURN_SETTINGS
        self._guard(operation, talks=True)
        update = CodexTurnSettingsRequest(
            handle=handle,
            model=model,
            effort=effort,
            summary=summary,
            service_tier=service_tier,
            clear_service_tier=clear_service_tier,
            approvals_reviewer=approvals_reviewer,
        )
        self._preflight.require_experimental_api(operation, CODEX_TURN_SETTINGS_UPDATE_METHOD)
        # An unknown or ended turn is refused here, naming its thread.
        turn = self._registry.get(update.handle)
        if turn is None or turn.snapshot is not None:
            message = CODEX_HOST_TURN_SETTINGS_FINISHED_MESSAGE.format(turn_id=update.handle.turn_id, thread_id=update.handle.thread_id)
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, message, operation, update.handle.thread_id)
        view = CodexSpawnRequest(turn=CodexTurnSettings(model=update.model), turn_service_tier=update.service_tier, approvals_reviewer=update.approvals_reviewer)
        await self._preflight.run(operation, view, spends=False)
        # A goal run is targeted through its physical turn, as steer
        # does; between turns there is nothing to change.
        target = turn.state.current_turn() if turn.state is not None else update.handle.turn_id
        if not target:
            return CodexTurnSettingsStatus.TARGET_UNAVAILABLE
        connection = self._connection
        params = self._feature_params.turn_settings(update, target)
        send = connection.raw(CODEX_TURN_SETTINGS_UPDATE_METHOD, params, parse=self._feature_responses.turn_settings_status)
        return await connection.call(operation, CODEX_TURN_SETTINGS_UPDATE_METHOD, send, thread_id=update.handle.thread_id)

    async def set_codex_thread_memory_mode(self, thread_id: str, mode: CodexMemoryMode) -> None:
        """Say whether Codex may use memories on a stored thread; it needs Codex's experimental API.

        A thread not loaded on this host is loaded first, and is refused
        with codex.goal_unfinished while its stored goal is active.
        """
        operation = CodexHostOperation.SET_CODEX_THREAD_MEMORY_MODE
        self._guard(operation, talks=True)
        memory = CodexMemoryModeRequest(thread_id=thread_id, mode=mode)
        self._preflight.require_experimental_api(operation, CODEX_THREAD_MEMORY_MODE_SET_METHOD)
        # The thread must exist and be loaded, behind the load guard
        # (first-class INV-26, INV-12).
        status = await self._threads.status(operation, memory.thread_id)
        await self._threads.load(operation, memory.thread_id, status)
        connection = self._connection
        send = connection.raw(CODEX_THREAD_MEMORY_MODE_SET_METHOD, self._feature_params.memory_mode(memory.thread_id, memory.mode), parse=self._feature_responses.empty)
        await connection.call(operation, CODEX_THREAD_MEMORY_MODE_SET_METHOD, send, thread_id=memory.thread_id)

    async def get_codex_memory_status(self, min_consolidated_threads: int | None = None) -> CodexMemoryStatus:
        """How many threads Codex has consolidated into memories, and whether they are ready; it needs Codex's experimental API."""
        # Check the host and the threshold, then refuse at once on a
        # host without Codex's experimental API (first-class INV-4).
        operation = CodexHostOperation.GET_CODEX_MEMORY_STATUS
        self._guard(operation, talks=True)
        reading = CodexMemoryStatusRequest(min_consolidated_threads=min_consolidated_threads)
        self._preflight.require_experimental_api(operation, CODEX_MEMORY_STATUS_METHOD)
        # Ask Codex once how far its memories are consolidated
        # (INV-26).
        connection = self._connection
        status = connection.raw(CODEX_MEMORY_STATUS_METHOD, self._feature_params.memory_status(reading), parse=self._feature_responses.memory_status)
        return await connection.call(operation, CODEX_MEMORY_STATUS_METHOD, status)

    async def reset_codex_memories(self) -> None:
        """Delete every memory Codex stored for this account; it cannot be undone, and it needs Codex's experimental API.

        It is a plain function and never a tool, so no model can reach it.
        """
        # There is no argument to check, so refuse at once on a host
        # without Codex's experimental API (first-class INV-4).
        operation = CodexHostOperation.RESET_CODEX_MEMORIES
        self._guard(operation, talks=True)
        self._preflight.require_experimental_api(operation, CODEX_MEMORY_RESET_METHOD)
        # Ask Codex once to delete every stored memory; this cannot be
        # undone, so no tool reaches it (INV-26, INV-42).
        connection = self._connection
        reset = connection.raw(CODEX_MEMORY_RESET_METHOD, None, parse=self._feature_responses.empty)
        await connection.call(operation, CODEX_MEMORY_RESET_METHOD, reset)


__all__ = ["CodexSettingsMethods"]
