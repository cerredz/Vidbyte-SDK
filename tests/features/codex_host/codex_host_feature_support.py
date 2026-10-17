"""FILE: tests/features/codex_host/codex_host_feature_support.py

PURPOSE: The first-class-features half of the CodexHost test support: the spec's literal texts, tables and bounds for the twenty-five new host methods, a packet helper that checks a CodexErrorMapper message whose likely cause and next step are the spec's own overrides, and FeatureStubMethods, the sixteen methods StubCodexHost answers for the new agent tools.
ROLE IN CODEBASE: Imported by the slice-2 test modules of tests/features/codex_host/ and by codex_host_support.py, whose StubCodexHost inherits FeatureStubMethods. The literals are written from docs/spec/codex-host-first-class/spec.md sections 8.5, 9.2 and 9.3, never read from the production constants, so a changed text fails a test.
ARCHITECTURE NOTE: This module imports nothing the feature adds, nothing from openai-codex and nothing from codex_host_support at module level, so every module that imports it still collects before the feature exists, on CI, and without an import cycle. FeatureStubMethods reaches the records it returns only inside each method, and it calls StubCodexHost._enter, _handle, _snapshot and _thread_info through self, so a tool error raised by the stub still names codex_host_support.py:_enter as its origin.
FUNCTION INVENTORY: FEATURE_METHODS lists the twenty-five new methods in CodexHostOperation order; NO_TOOL_FUNCTIONS, EXPERIMENTAL_FUNCTIONS, UNMODELED_METHODS, STREAM_KINDS and the other tables mirror sections 6.1 and 9.3; the *_MESSAGE, *_CAUSE and *_NEXT_STEP texts mirror section 9.2; priced_cost prices usage deltas with the repo's own tracker (the pricing oracle); packet_text builds the full CodexErrorMapper message for an override cause and next step, and assert_packet checks an error against it; FeatureStubMethods answers update_codex_thread_settings through list_codex_child_threads from scripted records.
COMMON MODIFICATION PATTERNS: When the spec changes one of these texts or tables, change the literal here. Add a stub method here, with the host's parameter names recorded as keywords, when a new tool calls a new host method.
WHAT NOT TO DO IN THIS FILE: 1. Do not import codex_host_support, vidbyte.harnesses.native, codex_host_features, codex_host_modes, the new enums or openai_codex at module level. 2. Do not copy production logic; the tables are the spec's words. 3. Do not start a process or touch the network.
KNOWN EDGE CASES: Three of the fifteen method-name constants are named by the spec (the first and the last); the others are pinned by value only, because section 9.3 does not name them. StubCodexHost.wait_codex_turns answers each handle with its current stub snapshot, so a test that wants snapshots with items marks the handles finished first.
RELATED DOCS: tests/features/codex_host/FEATURE.md; tests/features/codex_host/codex_host_support.py; docs/spec/codex-host-first-class/spec.md sections 6.1, 8.5, 9.2, 9.3 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host
"""

from __future__ import annotations

import os
import unittest
from typing import Any

# Section 8.5: the twenty-five new CodexHost methods, in the CodexHostOperation order D-29 fixes.
FEATURE_METHODS = (
    "update_codex_thread_settings",
    "list_codex_collaboration_modes",
    "run_codex_plan",
    "stream_codex_turn",
    "wait_codex_turns",
    "list_codex_mcp_servers",
    "update_codex_turn_settings",
    "set_codex_thread_memory_mode",
    "get_codex_memory_status",
    "reset_codex_memories",
    "start_codex_side_chat",
    "create_codex_worktree",
    "pause_codex_goal",
    "resume_codex_goal",
    "edit_codex_goal",
    "clear_codex_goal",
    "archive_codex_thread",
    "unarchive_codex_thread",
    "revert_codex_thread",
    "rename_codex_thread",
    "inject_codex_items",
    "list_codex_background_terminals",
    "clean_codex_background_terminals",
    "search_codex_thread_content",
    "list_codex_child_threads",
)
# INV-42: the nine new functions that never get a tool, plus the two older ones.
NO_TOOL_FUNCTIONS = (
    "stream_codex_turn",
    "reset_codex_memories",
    "revert_codex_thread",
    "inject_codex_items",
    "create_codex_worktree",
    "edit_codex_goal",
    "clear_codex_goal",
    "set_codex_thread_memory_mode",
    "clean_codex_background_terminals",
)
OLDER_NO_TOOL_FUNCTIONS = ("delete_codex_thread", "forget_codex_turns")
# INV-4: the eleven functions that need Codex's experimental API.
EXPERIMENTAL_FUNCTIONS = (
    "update_codex_thread_settings",
    "list_codex_collaboration_modes",
    "run_codex_plan",
    "update_codex_turn_settings",
    "set_codex_thread_memory_mode",
    "get_codex_memory_status",
    "reset_codex_memories",
    "list_codex_background_terminals",
    "clean_codex_background_terminals",
    "search_codex_thread_content",
    "list_codex_child_threads",
)
# Section 9.3: the fifteen new method names; the spec names only the first and the last constant.
FEATURE_METHOD_NAMES = (
    "thread/settings/update",
    "turn/settings/update",
    "collaborationMode/list",
    "mcpServerStatus/list",
    "thread/memoryMode/set",
    "memory/status",
    "memory/reset",
    "thread/inject_items",
    "thread/archive",
    "thread/unarchive",
    "thread/revert",
    "thread/goal/clear",
    "thread/backgroundTerminals/list",
    "thread/backgroundTerminals/clean",
    "thread/search",
)
# Section 9.2 "(raw, unmodeled)" rows, which CODEX_HOST_UNMODELED_RAW_METHODS lists (D-3).
UNMODELED_METHODS = frozenset(
    {
        "thread/settings/update",
        "collaborationMode/list",
        "turn/settings/update",
        "thread/memoryMode/set",
        "memory/status",
        "memory/reset",
        "thread/backgroundTerminals/list",
        "thread/backgroundTerminals/clean",
        "thread/search",
    }
)
# Section 9.3: CODEX_HOST_RAW_RESPONSE_MODELS gains these rows.
NEW_RAW_RESPONSE_MODELS = {
    "mcpServerStatus/list": "ListMcpServerStatusResponse",
    "thread/inject_items": "ThreadInjectItemsResponse",
    "thread/revert": "ThreadRevertResponse",
    "thread/goal/clear": "ThreadGoalClearResponse",
}
# Section 9.3 CODEX_HOST_STREAM_NOTIFICATION_KINDS: notification method -> CodexTurnEventKind value.
STREAM_KINDS = {
    "item/started": "item_started",
    "item/completed": "item_completed",
    "item/agentMessage/delta": "message_delta",
    "item/reasoning/summaryTextDelta": "reasoning_summary_delta",
    "item/plan/delta": "plan_delta",
    "item/commandExecution/outputDelta": "command_output_delta",
    "item/fileChange/outputDelta": "file_change_delta",
    "turn/plan/updated": "plan_updated",
    "turn/diff/updated": "diff_updated",
    "thread/tokenUsage/updated": "usage_updated",
}
GOAL_RESUME_FROM_STATUSES = frozenset({"paused", "blocked", "usageLimited", "budgetLimited"})
LOAD_SAFE_GOAL_STATUSES = frozenset({"paused", "blocked", "usageLimited", "budgetLimited", "complete"})
# Section 9.3 numbers and fixed values.
FEATURE_NUMBERS = {
    "CODEX_HOST_GOAL_RESUME_START_SECONDS": 30.0,
    "CODEX_HOST_GOAL_MUTATION_ORIGIN": "user",
    "CODEX_HOST_STREAM_EVENT_LIMIT": 4096,
    "CODEX_HOST_STREAM_TEXT_LIMIT_CHARS": 2_000_000,
    "CODEX_HOST_STREAM_HOST_EVENT_LIMIT": 65_536,
    "CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS": 32_000_000,
    "CODEX_HOST_WAIT_MAX_HANDLES": 1024,
    "CODEX_HOST_INJECT_MAX_ITEMS": 1024,
    "CODEX_HOST_MEMORY_MIN_CONSOLIDATED_THREADS": 1,
    "CODEX_HOST_MEMORY_MAX_CONSOLIDATED_THREADS": 4096,
    "CODEX_HOST_WORKTREE_ROOT_PARTS": (".vidbyte", "codex-worktrees"),
    "CODEX_HOST_WORKTREE_TIMEOUT_SECONDS": 120.0,
    "CODEX_HOST_WORKTREE_MAX_OUTPUT_BYTES": 65536,
    "CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS": 500,
    "CODEX_HOST_WORKTREE_UNSAFE_NAME_PATTERN": r"[^A-Za-z0-9._-]",
    "CODEX_HOST_WORKTREE_NAME_SEPARATOR": "-",
    "CODEX_GOAL_RESUME_CALL": "resume_goal_operation",
}
# Section 9.3, vidbyte.lib.constants.native_threads.
GIT_VALUES = {
    "GIT_PROGRAM": "git",
    "GIT_WORKTREE_ADD_COMMAND": ("worktree", "add"),
    "GIT_END_OF_OPTIONS": "--",
    "GIT_DEFAULT_BASE_REF": "HEAD",
    "GIT_REF_PATTERN": r"^(?!.*\.\.)(?!.*//)(?!.*\.lock$)[A-Za-z0-9][A-Za-z0-9._/-]*(?<![./])$",
    "GIT_REF_MAX_CHARS": 200,
}
GIT_NO_PROMPT_ENV = {"GIT_TERMINAL_PROMPT": "0"}
# Section 9.3: the new CODEX_HOST_REJECTED_FIELDS rows.
PLAN_REJECTED_FIELDS = ("prompt", "goal", "collaboration_mode")
SIDE_CHAT_REJECTED_FIELDS = ("prompt", "goal", "name", "tools", "thread.ephemeral", "thread.personality", "thread.service_name", "thread.session_start_source")
# Section 9.3 CODEX_HOST_HELPER_SOURCE_KINDS values the search sends (D-35), and every CodexThreadSourceKind value (D-24).
HELPER_SOURCE_KINDS = frozenset({"cli", "vscode", "exec", "appServer", "unknown"})
EVERY_SOURCE_KIND = frozenset({"cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview", "subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"})

# Section 9.2 "Messages", verbatim.
EXPERIMENTAL_FEATURE_MESSAGE = "{operation} needs Codex's experimental API for {feature}, but this CodexHost was opened with experimental_api=False. Open the host with CodexClientSettings(experimental_api=True) to use it."
MODE_KIND_MESSAGE = "collaboration_mode mode must be CodexCollaborationModeKind.PLAN or CodexCollaborationModeKind.DEFAULT."
MODE_CONFLICT_MESSAGE = "{owner} collaboration_mode sets {name} to a different value than {owner} does. Set {name} in one place only, because Codex lets the collaboration mode take precedence."
SETTINGS_MODE_MODEL_MESSAGE = "update_codex_thread_settings collaboration_mode needs a model, so set collaboration_mode.model or model, because Codex requires a model with every collaboration mode."
SETTINGS_EMPTY_MESSAGE = "{operation} was given no setting to change; set at least one field."
TIER_CLEAR_CONFLICT_MESSAGE = "{operation} sets service_tier and clear_service_tier together; set a tier or clear it, not both."
SETTINGS_NETWORK_ACCESS_MESSAGE = "update_codex_thread_settings network_access needs sandbox READ_ONLY or WORKSPACE_WRITE, because only those sandbox policies take it, and it got sandbox {sandbox}."
SETTINGS_WRITABLE_ROOTS_MESSAGE = "update_codex_thread_settings writable_roots must be a tuple of non-empty absolute paths, and it needs sandbox WORKSPACE_WRITE."
WAIT_HANDLES_MESSAGE = "wait_codex_turns handles must hold between 1 and {maximum} distinct CodexTurnHandle values."
INJECT_ITEMS_MESSAGE = "inject_codex_items items must hold between 1 and {maximum} JSON objects, each with a non-empty string type."
GOAL_EDIT_EMPTY_MESSAGE = "edit_codex_goal was given nothing to change; set objective, token_budget or clear_token_budget."
BUDGET_CLEAR_CONFLICT_MESSAGE = "edit_codex_goal sets token_budget and clear_token_budget together; set a budget or clear it, not both."
WORKTREE_REPOSITORY_MESSAGE = "create_codex_worktree repository must be the absolute path of an existing folder."
WORKTREE_REF_MESSAGE = "create_codex_worktree {field} must be a git branch or ref name of 1 to {maximum} characters that starts with a letter or digit and uses only letters, digits, '.', '_', '-' and '/', without '..', '//' or a trailing '.', '/' or '.lock'."
NO_PLAN_MODE_MESSAGE = "Codex listed no collaboration mode preset whose mode is plan, so no plan-mode turn was started."
MODE_MODEL_MISSING_MESSAGE = "Codex reported no model for the thread, and neither the collaboration mode nor the turn names one, so the collaboration mode's required model cannot be sent."
MODE_MODEL_MISSING_CAUSE = "The thread was started without a resolved model, and a collaboration mode must name one."
MODE_MODEL_MISSING_NEXT_STEP = "Set collaboration_mode.model or turn.model, then call again."
TURN_SETTINGS_FINISHED_MESSAGE = "update_codex_turn_settings changes only a running turn this host started, and turn {turn_id} on thread {thread_id} is not running on this host."
NO_GOAL_MESSAGE = "{operation} needs a goal on the thread, and Codex stores none."
NO_GOAL_CAUSE = "The thread exists, but no goal was ever set on it, or the goal was cleared."
NO_GOAL_NEXT_STEP = "Start a goal with run_codex_goal, or check the thread with get_codex_goal."
GOAL_NOT_RESUMABLE_MESSAGE = "resume_codex_goal resumes only a paused, blocked, usage-limited or budget-limited goal, and this goal is {status}."
GOAL_NOT_RESUMABLE_CAUSE = "Codex stores the goal with a status resume cannot continue."
GOAL_NOT_RESUMABLE_NEXT_STEP = "Read the goal with get_codex_goal. A complete goal is finished, so start a new one with run_codex_goal. An active goal that no client is running, for example after a host stopped, continues with pause_codex_goal and then resume_codex_goal."
GOAL_BUDGET_SPENT_MESSAGE = "resume_codex_goal did not resume the goal, because it has used {used} tokens of its {budget}-token budget."
GOAL_BUDGET_SPENT_CAUSE = "The goal stopped at its token budget, and the budget has not been raised since."
GOAL_BUDGET_SPENT_NEXT_STEP = "Raise the budget with edit_codex_goal(token_budget=...) or remove it with edit_codex_goal(clear_token_budget=True), then call resume_codex_goal again."
THREAD_RUNNING_MESSAGE = "Codex reports a running turn on the thread, so {operation} cannot change it until that turn ends."
LOAD_GOAL_UNFINISHED_MESSAGE = "Codex reports an unfinished goal (status {status}) on the thread, and loading the thread for {operation} could let Codex continue that goal."
LOAD_GOAL_UNFINISHED_CAUSE = "The thread is not loaded in this host's app-server, and loading it for {operation} could let Codex continue its active goal as paid turns this host does not track."
LOAD_GOAL_UNFINISHED_NEXT_STEP = "Pause the goal with pause_codex_goal or clear it with clear_codex_goal, then call again."
WORKTREE_EXISTS_MESSAGE = "create_codex_worktree did not run git, because the worktree folder for this repository and branch already exists under the Vidbyte worktree root."
WORKTREE_EXISTS_CAUSE = "A worktree for the same repository folder name and branch was created before."
WORKTREE_EXISTS_NEXT_STEP = "Use the existing worktree, choose another branch name, or remove the old one with git worktree remove."
WORKTREE_GIT_MISSING_MESSAGE = "create_codex_worktree could not start the git program."
WORKTREE_GIT_MISSING_CAUSE = "git is not installed, is not on PATH, or cannot be run by this process."
WORKTREE_GIT_MISSING_NEXT_STEP = "Install git or put it on PATH, then call again."
WORKTREE_TIMED_OUT_MESSAGE = "git worktree add did not finish within {seconds} seconds, so create_codex_worktree stopped it."
WORKTREE_TIMED_OUT_CAUSE = "A git hook, a credential helper or a slow file system kept git waiting."
WORKTREE_TIMED_OUT_NEXT_STEP = "Run git worktree add in the repository by hand to see what it waits for, remove any half-made worktree folder with git worktree remove, then call again."
WORKTREE_FAILED_MESSAGE = "git worktree add exited with code {exit_code}: {detail}"
WORKTREE_FAILED_CAUSE = "The folder is not inside a git work tree, the branch already exists, or the base ref is unknown."
WORKTREE_FAILED_NEXT_STEP = "Fix the repository, branch or base ref that git names, then call again."
# Section 9.3, the side-chat texts, verbatim.
SIDE_CHAT_INSTRUCTIONS = "This thread is a side conversation forked from another thread so the user can ask a quick question without changing the main work. Answer the side question using the inherited history as background only. Do not continue, finish or change the main task, and do not edit files unless the user explicitly asks for that in this side conversation."
SIDE_CHAT_BOUNDARY = "The side conversation starts here. Everything above is history from the main thread, given as background; the messages below belong only to this side conversation."
# Section 9.2 tool rules: the turn-settings tool's text, a module-level constant of the controls tool module.
TURN_SETTINGS_STATUS_TEXT = "Codex answered {status} to the settings update for turn {turn_id} on thread {thread_id}, where applied means the running turn takes the change and targetUnavailable means no turn was running to take it."
# Spec A-14: the boundary item the side chat injects.
SIDE_CHAT_BOUNDARY_ITEM = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": SIDE_CHAT_BOUNDARY}]}

# Privacy canaries of section 13 (NFR-7): finding one in a log record or an error text is a leak.
PROMPT_CANARY = "prompt-canary-3b71"
DELTA_CANARY = "delta-canary-91fe"
PLAN_CANARY = "plan-canary-6c02"
OBJECTIVE_CANARY = "objective-canary-d4a8"
ITEM_CANARY = "item-canary-0e57"
MEMORY_CANARY = "memory-canary-72b9"
PATH_CANARY = "pathcanary5e13"
BRANCH_CANARY = "branchcanary8f20"
GIT_STDERR_CANARY = "gitstderrcanary44c1"
FEATURE_CANARIES = (PROMPT_CANARY, DELTA_CANARY, PLAN_CANARY, OBJECTIVE_CANARY, ITEM_CANARY, MEMORY_CANARY, PATH_CANARY, BRANCH_CANARY, GIT_STDERR_CANARY)


def priced_cost(model: str, deltas: tuple[tuple[int, int], ...]) -> float:
    """What the repo's own pricing charges these per-turn (input, output) deltas on the model (hardening D-19 oracle)."""
    from vidbyte.agents.codex.metrics import CodexMetricsTranslator
    from vidbyte.agents.pricing.tracker import UsageTracker
    from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexRunResult, CodexThreadSettings, CodexUsage, CodexUsageTranslationRequest

    tracker = UsageTracker()
    settings = CodexAgentSettings(thread=CodexThreadSettings(model=model))
    for input_tokens, output_tokens in deltas:
        delta = CodexUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens)
        result = CodexRunResult(thread_id="oracle", turn_id="oracle", status="completed", final_response="", duration_ms=0, usage=delta, items=(), last_usage=delta, usage_available=True)
        CodexMetricsTranslator.record_usage(CodexUsageTranslationRequest(result=result, settings=settings, tracker=tracker))
    return float(tracker.rollup().cost_usd)


def packet_text(operation: str, code: str, message: str, cause: str, next_step: str, thread_id: str = "") -> str:
    """The full CodexErrorMapper message of a packet whose summary, likely cause and next step the spec gives."""
    thread = f" The thread id was {thread_id}." if thread_id else ""
    return f"{operation} failed with {code}. {message}{thread} Likely cause: {cause} Next step: {next_step}"


def assert_packet(case: unittest.TestCase, error: Any, *, operation: str, code: str, message: str, cause: str, next_step: str, thread_id: str = "") -> None:
    """Check a CodexAgentError whose cause and next step are the spec's overrides (D-23), not the code's defaults."""
    case.assertEqual(error.failure_code, code, error.message)
    case.assertEqual(error.operation, operation, error.message)
    case.assertEqual(error.message, packet_text(operation, code, message, cause, next_step, thread_id))
    case.assertEqual(error.next_step, next_step)


class FeatureStubMethods:
    """The sixteen new host methods the agent tools call, answered by StubCodexHost from scripted records."""

    # StubCodexHost, which inherits this mixin, owns these.
    _enter: Any
    _handle: Any
    _snapshot: Any
    _thread_info: Any
    finished: set[tuple[str, str]]

    async def update_codex_thread_settings(self, thread_id: str, settings: Any) -> None:
        await self._enter("update_codex_thread_settings", thread_id=thread_id, settings=settings)

    async def list_codex_collaboration_modes(self) -> Any:
        from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationModePreset
        from vidbyte.lib.enums.codex import CodexCollaborationModeKind

        await self._enter("list_codex_collaboration_modes")
        return (CodexCollaborationModePreset(name="Plan", mode=CodexCollaborationModeKind.PLAN, model="", reasoning_effort="medium"),)

    async def run_codex_plan(self, prompt: Any, request: Any = None) -> Any:
        await self._enter("run_codex_plan", prompt=prompt, request=request)
        return self._handle()

    async def wait_codex_turns(self, handles: Any, return_when: Any = None, timeout_seconds: float | None = None) -> Any:
        await self._enter("wait_codex_turns", handles=tuple(handles), return_when=return_when, timeout_seconds=timeout_seconds)
        return tuple(self._snapshot(handle) for handle in handles)

    async def list_codex_mcp_servers(self, thread_id: str = "", server_name: str = "", detail: Any = None, cursor: str = "", limit: int | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex_host_features import CodexMcpServer, CodexMcpServerPage
        from vidbyte.lib.enums.codex import CodexMcpAuthStatus, CodexMcpConnectionStatus

        await self._enter("list_codex_mcp_servers", thread_id=thread_id, server_name=server_name, detail=detail, cursor=cursor, limit=limit)
        server = CodexMcpServer(name="docs", auth_status=CodexMcpAuthStatus.OAUTH, connection_status=CodexMcpConnectionStatus.CONNECTED, tool_names=("fetch", "search"), resource_count=1, resource_template_count=0)
        return CodexMcpServerPage(servers=(server,), next_cursor="")

    async def update_codex_turn_settings(self, handle: Any, model: str = "", effort: Any = None, summary: Any = None, service_tier: str = "", clear_service_tier: bool = False, approvals_reviewer: Any = None) -> Any:
        from vidbyte.lib.enums.codex import CodexTurnSettingsStatus

        settings = {"model": model, "effort": effort, "summary": summary, "service_tier": service_tier, "clear_service_tier": clear_service_tier, "approvals_reviewer": approvals_reviewer}
        await self._enter("update_codex_turn_settings", handle=handle, **settings)
        return CodexTurnSettingsStatus.APPLIED

    async def get_codex_memory_status(self, min_consolidated_threads: int | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex_host_features import CodexMemoryStatus

        await self._enter("get_codex_memory_status", min_consolidated_threads=min_consolidated_threads)
        return CodexMemoryStatus(consolidated_threads=3, ready=True)

    async def start_codex_side_chat(self, thread_id: str, prompt: Any, request: Any = None) -> Any:
        await self._enter("start_codex_side_chat", thread_id=thread_id, prompt=prompt, request=request)
        # The handle names the fork, never the parent (INV-27).
        return self._handle()

    async def pause_codex_goal(self, thread_id: str) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadGoal
        from vidbyte.lib.enums.codex import CodexGoalStatus

        await self._enter("pause_codex_goal", thread_id=thread_id)
        return CodexThreadGoal(thread_id=thread_id, objective="Ship the fix.", status=CodexGoalStatus.PAUSED, token_budget=500, tokens_used=120, time_used_seconds=30, created_at=1, updated_at=2)

    async def resume_codex_goal(self, thread_id: str, request: Any = None) -> Any:
        await self._enter("resume_codex_goal", thread_id=thread_id, request=request)
        return self._handle(thread_id)

    async def archive_codex_thread(self, thread_id: str) -> None:
        await self._enter("archive_codex_thread", thread_id=thread_id)

    async def unarchive_codex_thread(self, thread_id: str) -> Any:
        await self._enter("unarchive_codex_thread", thread_id=thread_id)
        return self._thread_info(thread_id)

    async def rename_codex_thread(self, thread_id: str, name: str) -> None:
        await self._enter("rename_codex_thread", thread_id=thread_id, name=name)

    async def list_codex_background_terminals(self, thread_id: str, cursor: str = "", limit: int | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex_host_features import CodexBackgroundTerminal, CodexBackgroundTerminalPage

        await self._enter("list_codex_background_terminals", thread_id=thread_id, cursor=cursor, limit=limit)
        terminal = CodexBackgroundTerminal(process_id="proc-stub-1", item_id="item-stub-1", command="npm run dev", cwd=os.path.abspath(os.sep), os_pid=4242)
        return CodexBackgroundTerminalPage(terminals=(terminal,), next_cursor="")

    async def search_codex_thread_content(self, query: str, archived: bool = False, cursor: str = "", limit: int | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSearchHit, CodexThreadSearchPage

        await self._enter("search_codex_thread_content", query=query, archived=archived, cursor=cursor, limit=limit)
        hit = CodexThreadSearchHit(thread=self._thread_info("thr-stub-hit"), snippet="stub snippet")
        return CodexThreadSearchPage(hits=(hit,), next_cursor="", backwards_cursor="")

    async def list_codex_child_threads(self, thread_id: str, descendants: bool = False, cursor: str = "", limit: int | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadPage

        await self._enter("list_codex_child_threads", thread_id=thread_id, descendants=descendants, cursor=cursor, limit=limit)
        return CodexThreadPage(threads=(self._thread_info("thr-stub-child"),), next_cursor="")
