"""FILE: vidbyte/tools/toolsets/codex.py

PURPOSE: Defines CodexHostTools, the catalog of the forty-two agent tools over one CodexHost, one tool per CodexHost function except delete_codex_thread, forget_codex_turns and the nine first-class functions kept from the model, which have no tool, all sharing one CodexToolScope.
ROLE IN CODEBASE: Exported by vidbyte/tools/toolsets/__init__.py. Composes the tools and CodexToolScope from vidbyte/tools/builtins/codex/ over a CodexHost from vidbyte/harnesses/native/codex/; an agent or McpStudioServer takes the catalog like any other Tools.
ARCHITECTURE NOTE: CodexHostTools is a Tools subclass that holds only the forty-two tools, in the order of the CodexHost functions. delete_codex_thread has no tool, so no model can delete a thread, and neither have forget_codex_turns nor the nine first-class functions stream_codex_turn, reset_codex_memories, revert_codex_thread, inject_codex_items, create_codex_worktree, edit_codex_goal, clear_codex_goal, set_codex_thread_memory_mode and clean_codex_background_terminals, which would hand the model an iterator, an irreversible change, a folder or the developer's posture (first-class INV-41, INV-42). CodexHost is imported under TYPE_CHECKING only, so building the catalog never loads openai-codex. The developer owns the host and closes it with their own async with; the catalog never opens or closes it (D-10).
COMMON MODIFICATION PATTERNS: A new CodexHost function adds its tool to vidbyte/tools/builtins/codex/ and one line here, at its place in the function order.
WHAT NOT TO DO IN THIS FILE: 1. Do not share one catalog between two agents: they would share the cap and could act on each other's turns (EC-56). 2. Do not pass a host's own catalog as dynamic tools to a thread on that same host: the tool call would wait on the reader thread that is running it, and fail after 300 seconds (EC-48).
KNOWN EDGE CASES: openai-codex answers a dynamic tool call on its one reader thread, so while such a call runs, every other turn's events and every response on that host wait (EC-68). Tools given to Codex threads should be short, or those threads should get their own CodexHost.
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.5 and 9.2); docs/spec/codex-host-thread-helpers/spec.md (section 9.2 tool table); docs/spec/codex-host-first-class/spec.md (section 9.2 tool table; INV-41, INV-42, INV-49)
TESTS: tests/features/codex_host/test_codex_host_tools.py, tests/features/codex_host/test_codex_host_packaging.py, tests/features/codex_host/test_codex_host_helper_tools.py, tests/features/codex_host/test_codex_host_feature_tools.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
from vidbyte.tools.builtins.codex import (
    ArchiveCodexThreadTool,
    CheckCodexReadyTool,
    CodexToolScope,
    CompactCodexThreadTool,
    ContinueCodexThreadTool,
    ForkCodexThreadTool,
    GetCodexGoalTool,
    GetCodexMemoryStatusTool,
    GetCodexRateLimitsTool,
    GetCodexThreadLineageTool,
    GetCodexTurnResultTool,
    InterruptCodexTurnTool,
    LaunchCodexSubagentsTool,
    ListCodexBackgroundTerminalsTool,
    ListCodexChildThreadsTool,
    ListCodexCollaborationModesTool,
    ListCodexMcpServersTool,
    ListCodexModelsTool,
    ListCodexSkillsTool,
    ListCodexThreadsSinceTool,
    ListCodexThreadsTool,
    ListCodexTurnsTool,
    ListRecentCodexThreadsTool,
    PauseCodexGoalTool,
    ReadCodexThreadTool,
    RenameCodexThreadTool,
    ResumeCodexGoalTool,
    RunCodexGoalTool,
    RunCodexOpenaiDocsTool,
    RunCodexPlanTool,
    RunCodexSkillTool,
    SearchCodexThreadContentTool,
    SearchCodexThreadsTool,
    SpawnCodexThreadTool,
    StartCodexReviewTool,
    StartCodexSideChatTool,
    SteerCodexTurnTool,
    TrackCodexThreadUsageTool,
    UnarchiveCodexThreadTool,
    UpdateCodexThreadSettingsTool,
    UpdateCodexTurnSettingsTool,
    WaitCodexTurnsTool,
    WaitCodexTurnTool,
)
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from vidbyte.harnesses.native.codex import CodexHost


class CodexHostTools(Tools):
    """Catalog of one agent tool per CodexHost function, except delete_codex_thread, forget_codex_turns and the nine first-class functions kept from the model, over one host.

    The developer owns the host and closes it; build one catalog per agent,
    and never pass a host's catalog as dynamic tools to that same host
    (EC-48). A running dynamic tool call blocks every other event and
    response on its host, so tools given to Codex threads should be short,
    or those threads should get their own CodexHost (EC-68).
    """

    def __init__(self, host: CodexHost, *, max_live_turns: int, spawn_defaults: CodexSpawnRequest | None = None) -> None:
        # One scope holds the cap on live tool-started turns, the
        # developer's spawn posture and the handles these tools create;
        # it refuses a bad cap or a posture carrying a prompt or goal.
        scope = CodexToolScope(max_live_turns=max_live_turns, spawn_defaults=spawn_defaults)

        # Give every CodexHost function its tool over the same host and
        # scope, in the order of the functions; delete_codex_thread has
        # none, so no model can delete a thread (INV-2), and neither do
        # forget_codex_turns and the nine first-class functions kept
        # from the model (first-class INV-42).
        tool_classes = (
            CheckCodexReadyTool,
            GetCodexRateLimitsTool,
            ListCodexModelsTool,
            SpawnCodexThreadTool,
            ContinueCodexThreadTool,
            ForkCodexThreadTool,
            ListCodexThreadsTool,
            ReadCodexThreadTool,
            WaitCodexTurnTool,
            GetCodexTurnResultTool,
            SteerCodexTurnTool,
            InterruptCodexTurnTool,
            TrackCodexThreadUsageTool,
            LaunchCodexSubagentsTool,
            StartCodexReviewTool,
            ListRecentCodexThreadsTool,
            ListCodexThreadsSinceTool,
            SearchCodexThreadsTool,
            GetCodexThreadLineageTool,
            ListCodexTurnsTool,
            CompactCodexThreadTool,
            GetCodexGoalTool,
            RunCodexGoalTool,
            ListCodexSkillsTool,
            RunCodexSkillTool,
            RunCodexOpenaiDocsTool,
            UpdateCodexThreadSettingsTool,
            ListCodexCollaborationModesTool,
            RunCodexPlanTool,
            WaitCodexTurnsTool,
            ListCodexMcpServersTool,
            UpdateCodexTurnSettingsTool,
            GetCodexMemoryStatusTool,
            StartCodexSideChatTool,
            PauseCodexGoalTool,
            ResumeCodexGoalTool,
            ArchiveCodexThreadTool,
            UnarchiveCodexThreadTool,
            RenameCodexThreadTool,
            ListCodexBackgroundTerminalsTool,
            SearchCodexThreadContentTool,
            ListCodexChildThreadsTool,
        )

        # Hand the forty-two tools to the catalog: none for
        # delete_codex_thread, forget_codex_turns, stream_codex_turn,
        # reset_codex_memories, revert_codex_thread, inject_codex_items,
        # create_codex_worktree, edit_codex_goal, clear_codex_goal,
        # set_codex_thread_memory_mode or
        # clean_codex_background_terminals.
        super().__init__([tool_class(host, scope) for tool_class in tool_classes])


__all__ = ["CodexHostTools"]
