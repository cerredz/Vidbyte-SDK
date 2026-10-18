"""FILE: vidbyte/harnesses/native/codex/feature_wire.py

PURPOSE: Translates between CodexHost's first-class features and the openai-codex wire: CodexFeatureParamsTranslator builds the params of every new app-server call as a plain dict, and CodexFeatureResponseTranslator turns each new answer into the validated records of vidbyte/lib/dataclasses/codex_host_features.py.
ROLE IN CODEBASE: The wire layer of the first-class features under vidbyte/harnesses/native/codex/. CodexHost._open builds one CodexFeatureResponseTranslator over the host's CodexResponseTranslator, and the four host mixins (settings_methods, stream_methods, thread_methods, goal_methods) build every new params dict here and pass each response method to CodexConnection.raw as its parse step.
ARCHITECTURE NOTE: openai-codex's generated models are imported at module level, so only CodexHost._open, or a module that only _open imports, imports this module (first-class INV-45). Params are plain dicts, never a generated params model, so a JSON null (a cleared service tier, a removed token budget) reaches the wire, and the sandbox policy and collaboration mode come from CodexParamsTranslator, so a turn and a settings update send one shape (INV-5, INV-11). Each response method runs on the host's worker inside its own call: it reads members with .get only and builds lib records, which check themselves, so a missing or wrong-typed member is a ConfigurationError that CodexErrorMapper reports as codex.protocol_mismatch for that call, never a KeyError (INV-6, D-3, D-4).
COMMON MODIFICATION PATTERNS: A new first-class call adds one static params method to CodexFeatureParamsTranslator and, when its answer becomes a record, one parse method to CodexFeatureResponseTranslator that builds the record from .get reads; its method name and response model go in vidbyte/lib/constants/codex_host.py (CODEX_HOST_RAW_RESPONSE_MODELS, or CODEX_HOST_UNMODELED_RAW_METHODS when openai-codex has no model).
KNOWN EDGE CASES: A thread settings update and a turn settings update send serviceTier as JSON null when the tier is cleared, and an empty disabled_plugin_ids tuple sends [] (INV-11). A goal edit sends tokenBudget as JSON null when the budget is removed, and never a status (INV-32). A search sends archived only as true and always every top-level source kind (INV-39, D-35); a child listing always sends every source kind, so sub-agent children are listed (INV-40, D-24). A search hit whose thread is not a JSON object is refused by the hit record, so the failure stays a ConfigurationError. A preset's null mode is CodexCollaborationModeKind.NONE and its null model or effort is "" (INV-15).
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.5, 9.1 and 9.2, INV-5, INV-6, INV-11, INV-15, INV-24 to INV-27, INV-30 to INV-40, D-3, D-16, D-24, D-25, D-35); vidbyte/harnesses/native/codex/wire.py
TESTS: tests/features/codex_host/test_codex_host_settings_modes.py, tests/features/codex_host/test_codex_host_mcp_memory.py, tests/features/codex_host/test_codex_host_thread_admin.py, tests/features/codex_host/test_codex_host_goal_control.py, tests/features/codex_host/test_codex_host_side_chat.py, tests/features/codex_host/test_codex_host_feature_contract.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from openai_codex.generated.v2_all import (
    ListMcpServerStatusResponse,
    McpServerStatus,
    Thread,
    ThreadGoalClearResponse,
    ThreadGoalGetResponse,
    ThreadGoalSetResponse,
    ThreadRevertResponse,
)

from vidbyte.harnesses.native.codex.wire import (
    CodexParamsTranslator,
    CodexResponseTranslator,
)
from vidbyte.lib.constants.codex import CODEX_HOST_HELPER_SOURCE_KINDS
from vidbyte.lib.constants.codex_host import (
    CODEX_COLLABORATION_MODE_LIST_METHOD,
    CODEX_HOST_GOAL_MUTATION_ORIGIN,
    CODEX_HOST_REJECTED_FIELDS,
    CODEX_HOST_SIDE_CHAT_BOUNDARY,
    CODEX_HOST_SIDE_CHAT_INSTRUCTIONS,
    CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD,
    CODEX_THREAD_SEARCH_METHOD,
    CODEX_TURN_SETTINGS_UPDATE_METHOD,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexSpawnRequest,
    CodexThreadGoal,
    CodexThreadInfo,
)
from vidbyte.lib.dataclasses.codex_host_features import (
    CodexBackgroundTerminal,
    CodexBackgroundTerminalPage,
    CodexMcpServer,
    CodexMcpServerPage,
    CodexMemoryStatus,
    CodexThreadSearchHit,
    CodexThreadSearchPage,
    CodexThreadSettingsUpdate,
)
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexChildThreadsRequest,
    CodexMcpServerListRequest,
    CodexMemoryStatusRequest,
    CodexTerminalListRequest,
    CodexThreadSearchRequest,
    CodexTurnSettingsRequest,
)
from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationModePreset
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.codex import (
    CodexCollaborationModeKind,
    CodexGoalStatus,
    CodexHostOperation,
    CodexMcpAuthStatus,
    CodexMcpConnectionStatus,
    CodexMemoryMode,
    CodexReasoningEffort,
    CodexSandbox,
    CodexThreadSourceKind,
    CodexTurnSettingsStatus,
)


class CodexFeatureParamsTranslator:
    """Builds the params of every first-class app-server call as a plain dict, so JSON null reaches the wire."""

    @staticmethod
    def thread_settings(thread_id: str, settings: CodexThreadSettingsUpdate) -> dict[str, Any]:
        # @intent a-settings-update-sends-exactly-what-was-set
        # Each setting goes under its wire name only when set; a cleared
        # tier is JSON null, an empty plugin tuple clears the list, and
        # the sandbox policy and mode take the turn's own shapes
        # (first-class INV-5, INV-11).
        values = {
            "model": settings.model,
            "effort": settings.effort.value,
            "summary": settings.summary.value,
            "serviceTier": settings.service_tier,
            "cwd": settings.cwd,
            "approvalPolicy": settings.approval_policy.value,
            "approvalsReviewer": settings.approvals_reviewer.value,
        }
        params: dict[str, Any] = {"threadId": thread_id, **{key: value for key, value in values.items() if value}}
        if settings.clear_service_tier:
            params["serviceTier"] = None
        if settings.sandbox is not CodexSandbox.PROVIDER_DEFAULT:
            params["sandboxPolicy"] = CodexParamsTranslator.sandbox_policy(settings.sandbox, settings.network_access, settings.writable_roots)
        mode = settings.collaboration_mode
        if mode is not None:
            effort = mode.reasoning_effort if mode.reasoning_effort is not CodexReasoningEffort.PROVIDER_DEFAULT else settings.effort
            params["collaborationMode"] = CodexParamsTranslator.collaboration_mode(mode, mode.model or settings.model, effort)
        if settings.disabled_plugin_ids is not None:
            params["disabledPluginIds"] = list(settings.disabled_plugin_ids)
        return params

    @staticmethod
    def turn_settings(update: CodexTurnSettingsRequest, turn_id: str) -> dict[str, Any]:
        # The running turn's own settings, each only when set; a cleared
        # tier is JSON null (first-class INV-25). The turn id is passed
        # in, because a goal run is targeted through its current
        # physical turn.
        values = {
            "model": update.model,
            "effort": update.effort.value,
            "summary": update.summary.value,
            "serviceTier": update.service_tier,
            "approvalsReviewer": update.approvals_reviewer.value,
        }
        params: dict[str, Any] = {"threadId": update.handle.thread_id, "turnId": turn_id, **{key: value for key, value in values.items() if value}}
        if update.clear_service_tier:
            params["serviceTier"] = None
        return params

    @staticmethod
    def mcp_servers(listing: CodexMcpServerListRequest) -> dict[str, Any]:
        # The detail always, and each filter or page field only when set
        # (first-class INV-24).
        values = {"threadId": listing.thread_id, "serverName": listing.server_name, "cursor": listing.cursor, "limit": listing.limit}
        return {"detail": listing.detail.value, **{key: value for key, value in values.items() if value}}

    @staticmethod
    def memory_mode(thread_id: str, mode: CodexMemoryMode) -> dict[str, Any]:
        # Whether Codex may use memories on the thread (first-class
        # INV-26).
        return {"threadId": thread_id, "mode": mode.value}

    @staticmethod
    def memory_status(request: CodexMemoryStatusRequest) -> dict[str, Any]:
        # The consolidated-thread threshold only when one was given
        # (first-class INV-26).
        if request.min_consolidated_threads is None:
            return {}
        return {"minConsolidatedThreads": request.min_consolidated_threads}

    @staticmethod
    def goal_change(thread_id: str, *, status: CodexGoalStatus | None = None, objective: str = "", token_budget: int | None = None, clear_token_budget: bool = False) -> dict[str, Any]:
        # @intent every-goal-change-is-the-users
        # A pause or resume sends only its status and an edit only its
        # objective or budget, a removed budget as JSON null; every
        # change carries the user origin, because Codex treats missing
        # provenance as no user authorization (first-class INV-30 to
        # INV-32, D-16).
        params: dict[str, Any] = {"threadId": thread_id}
        if status is not None:
            params["status"] = status.value
        if objective:
            params["objective"] = objective
        if token_budget is not None or clear_token_budget:
            params["tokenBudget"] = token_budget
        params["origin"] = CODEX_HOST_GOAL_MUTATION_ORIGIN
        return params

    @staticmethod
    def goal_clear(thread_id: str) -> dict[str, Any]:
        # A clear is the user's too (first-class INV-30, INV-33).
        return {"threadId": thread_id, "origin": CODEX_HOST_GOAL_MUTATION_ORIGIN}

    @staticmethod
    def revert(thread_id: str, before_turn_id: str) -> dict[str, Any]:
        # The history goes back to the start of before_turn_id
        # (first-class INV-36).
        return {"threadId": thread_id, "beforeTurnId": before_turn_id}

    @staticmethod
    def inject(thread_id: str, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        # The items exactly as the record copied them, in order
        # (first-class INV-37).
        return {"threadId": thread_id, "items": [dict(item) for item in items]}

    @staticmethod
    def side_chat_boundary(thread_id: str) -> dict[str, Any]:
        # One user message that marks where the side chat starts, as
        # Codex's own /side flow injects it (first-class INV-27, D-18).
        boundary = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": CODEX_HOST_SIDE_CHAT_BOUNDARY}]}
        return {"threadId": thread_id, "items": [boundary]}

    @staticmethod
    def side_chat_views(request: CodexSpawnRequest) -> tuple[CodexSpawnRequest, CodexSpawnRequest]:
        # @intent a-side-chat-fork-is-ephemeral
        # The fork takes only what a fork can apply: every field of the
        # fork row is reset, the thread is ephemeral, and the side-chat
        # instructions follow the request's own after a blank line. The
        # turn on the fork takes the request as given (first-class
        # INV-27, D-18).
        defaults = CodexSpawnRequest()
        reset = {name: getattr(defaults, name) for name in CODEX_HOST_REJECTED_FIELDS[CodexHostOperation.FORK_CODEX_THREAD] if "." not in name}
        instructions = "\n\n".join(text for text in (request.developer_instructions, CODEX_HOST_SIDE_CHAT_INSTRUCTIONS) if text)
        fork = replace(request, **reset, thread=replace(request.thread, ephemeral=True), developer_instructions=instructions)
        return fork, request

    @staticmethod
    def terminals(listing: CodexTerminalListRequest) -> dict[str, Any]:
        # The thread, and the page fields only when set (first-class
        # INV-38).
        values = {"cursor": listing.cursor, "limit": listing.limit}
        return {"threadId": listing.thread_id, **{key: value for key, value in values.items() if value}}

    @staticmethod
    def search(request: CodexThreadSearchRequest) -> dict[str, Any]:
        # @intent a-search-reaches-every-top-level-thread
        # Without sourceKinds Codex searches interactive threads only,
        # which never include CodexHost's own, so every top-level kind
        # is always sent; archived goes only as true, which the schema
        # reads as false when left out (first-class INV-39, D-35).
        values = {"archived": request.archived, "cursor": request.cursor, "limit": request.limit}
        sources = [kind.value for kind in CODEX_HOST_HELPER_SOURCE_KINDS]
        return {"searchTerm": request.query, "sourceKinds": sources, **{key: value for key, value in values.items() if value}}

    @staticmethod
    def child_threads(params: dict[str, Any], request: CodexChildThreadsRequest) -> dict[str, Any]:
        # @intent a-child-listing-names-every-source-kind
        # The listing's own params plus the parent filter, or the
        # ancestor filter for every depth, and every source kind, so
        # the sub-agent children the default filter hides are listed;
        # openai-codex passes the dict through (first-class INV-5,
        # INV-40, D-24).
        key = "ancestorThreadId" if request.descendants else "parentThreadId"
        return {**params, key: request.thread_id, "sourceKinds": [kind.value for kind in CodexThreadSourceKind]}


class CodexFeatureResponseTranslator:
    """Turns each first-class answer into its lib record; each method is a parse step that runs on the host's worker."""

    def __init__(self, responses: CodexResponseTranslator) -> None:
        # The host's own response translator, so a thread and a goal
        # read here have the shape every other host call returns.
        self._responses = responses

    @staticmethod
    def modes(answer: Mapping[str, Any]) -> tuple[CodexCollaborationModePreset, ...]:
        # @intent presets-come-back-in-codex-order
        # Each preset in Codex's order; a null mode is NONE and a null
        # model or effort is blank, while a missing name or a wrong
        # type makes the record refuse (first-class INV-6, INV-15).
        entries = RecordFieldConverter.to_tuple(answer.get("data"), f"{CODEX_COLLABORATION_MODE_LIST_METHOD} data", item_type=Mapping)
        return tuple(
            CodexCollaborationModePreset(
                name=entry.get("name"),
                mode=RecordFieldConverter.to_enum(entry.get("mode") or "", CodexCollaborationModeKind, f"{CODEX_COLLABORATION_MODE_LIST_METHOD} mode"),
                model=entry.get("model") or "",
                reasoning_effort=entry.get("reasoning_effort") or "",
            )
            for entry in entries
        )

    @staticmethod
    def mcp_page(answer: ListMcpServerStatusResponse) -> CodexMcpServerPage:
        # One page of servers, each mapped by mcp_server; a null cursor
        # is blank (first-class INV-24).
        servers = tuple(CodexFeatureResponseTranslator.mcp_server(server) for server in answer.data)
        return CodexMcpServerPage(servers=servers, next_cursor=answer.next_cursor or "")

    @staticmethod
    def mcp_server(server: McpServerStatus) -> CodexMcpServer:
        # The sorted tool names, the resource counts, and Codex's null
        # texts as blanks; a server Codex reported no runtime status
        # for is NOT_REPORTED (first-class section 9.1).
        status = server.runtime_status.value if server.runtime_status is not None else CodexMcpConnectionStatus.NOT_REPORTED.value
        return CodexMcpServer(
            name=server.name,
            auth_status=CodexMcpAuthStatus(server.auth_status.value),
            connection_status=CodexMcpConnectionStatus(status),
            tool_names=tuple(sorted(server.tools)),
            resource_count=len(server.resources),
            resource_template_count=len(server.resource_templates),
            plugin_id=server.plugin_id or "",
            http_origin=server.http_origin or "",
            tools_error=server.tools_error or "",
            version=(server.server_info.version if server.server_info is not None else "") or "",
        )

    @staticmethod
    def turn_settings_status(answer: Mapping[str, Any]) -> CodexTurnSettingsStatus:
        # Codex's own status, TARGET_UNAVAILABLE included, which is a
        # result, not an error (first-class INV-25).
        return RecordFieldConverter.to_enum(answer.get("status"), CodexTurnSettingsStatus, f"{CODEX_TURN_SETTINGS_UPDATE_METHOD} status")

    @staticmethod
    def memory_status(answer: Mapping[str, Any]) -> CodexMemoryStatus:
        # The consolidated-thread count and readiness of Codex's
        # memories; a member that is missing or of another type is
        # refused here by type and by the record by range (first-class
        # INV-26).
        consolidated = RecordFieldConverter.require_instance(answer.get("v2ConsolidatedThreads"), "Codex memory status consolidated_threads", int)
        ready = RecordFieldConverter.require_instance(answer.get("v2Ready"), "Codex memory status ready", bool)
        return CodexMemoryStatus(consolidated_threads=consolidated, ready=ready)

    @staticmethod
    def terminals(answer: Mapping[str, Any]) -> CodexBackgroundTerminalPage:
        # One page of the thread's background terminals; a null cursor
        # is blank (first-class INV-38).
        entries = RecordFieldConverter.to_tuple(answer.get("data"), f"{CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD} data", item_type=Mapping)
        terminals = tuple(
            CodexBackgroundTerminal(
                process_id=entry.get("processId"),
                item_id=entry.get("itemId"),
                command=entry.get("command"),
                cwd=entry.get("cwd"),
                os_pid=entry.get("osPid"),
                cpu_percent=entry.get("cpuPercent"),
                rss_kb=entry.get("rssKb"),
            )
            for entry in entries
        )
        return CodexBackgroundTerminalPage(terminals=terminals, next_cursor=answer.get("nextCursor") or "")

    def search(self, answer: Mapping[str, Any]) -> CodexThreadSearchPage:
        # @intent a-search-hit-has-read-codex-threads-shape
        # Each hit's thread goes through openai-codex's own Thread model
        # and the host's thread_info, so it equals read_codex_thread's;
        # a thread that is not a JSON object is refused by the hit
        # record (first-class INV-39, D-25).
        entries = RecordFieldConverter.to_tuple(answer.get("data"), f"{CODEX_THREAD_SEARCH_METHOD} data", item_type=Mapping)
        hits = tuple(CodexThreadSearchHit(thread=self.hit_thread(entry.get("thread")), snippet=entry.get("snippet")) for entry in entries)
        return CodexThreadSearchPage(hits=hits, next_cursor=answer.get("nextCursor") or "", backwards_cursor=answer.get("backwardsCursor") or "")

    def hit_thread(self, thread: object) -> CodexThreadInfo:
        # A JSON object becomes the host's thread record; anything else
        # is refused as the hit's thread.
        RecordFieldConverter.require_instance(thread, "Codex thread search hit thread", Mapping)
        return self._responses.thread_info(Thread.model_validate(thread))

    def goal(self, answer: ThreadGoalSetResponse) -> CodexThreadGoal | None:
        # The goal Codex stored after the set, read as a goal read is
        # (first-class INV-30, INV-32).
        return self._responses.goal(ThreadGoalGetResponse(goal=answer.goal))

    @staticmethod
    def cleared(answer: ThreadGoalClearResponse) -> bool:
        # Whether Codex had a goal to clear (first-class INV-33).
        return answer.cleared

    def reverted(self, answer: ThreadRevertResponse) -> CodexThreadInfo:
        # The thread as Codex reports it after the revert (first-class
        # INV-36).
        return self._responses.thread_info(answer.thread)

    @staticmethod
    def empty(answer: object) -> None:
        # A call whose answer carries nothing the host returns.
        return None


__all__ = ["CodexFeatureParamsTranslator", "CodexFeatureResponseTranslator"]
