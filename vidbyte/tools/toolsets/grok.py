"""FILE: vidbyte/tools/toolsets/grok.py

PURPOSE: Defines GrokTools, the catalog of the ten tools over one GrokHost (check_grok_ready, list_grok_models, spawn_grok_session, run_grok_once, continue_grok_session, fork_grok_session, list_grok_sessions, search_grok_sessions, wait_grok_turn, interrupt_grok_turn), and its read_only variant.
ROLE IN CODEBASE: Exported by vidbyte/tools/toolsets/__init__.py; composes the tool classes in vidbyte/tools/builtins/grok/. Hand it to an agent or to ToolExecutor like any other Tools catalog, with the GrokHost open while the tools run.
ARCHITECTURE NOTE: A Tools subclass that holds only the ten tools over the host it is given. The five WRITE tools are denied by the default PermissionPolicy (EC-142); read_only returns the five READ tools, which is what MCP exposure gets (T-5).
FUNCTION INVENTORY: GrokTools.__init__ is the narrated main function and builds the ten tools in spec order; read_only builds the five READ tools.
COMMON MODIFICATION PATTERNS: A new Grok tool is one more entry in the tuple, in §9.2 order, and in read_only when it is READ.
WHAT NOT TO DO IN THIS FILE: 1. Do not open or close the host here; the caller owns its async with block. 2. Do not add a WRITE tool to read_only.
KNOWN EDGE CASES: Building the catalog starts no process; a tool run on a host that is not open returns grok.process_exited (EC-2).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Toolsets), §9.2 rows 1-10, T-5; vidbyte/tools/README.md
TESTS: tests/features/grok_host/test_grok_host_tools.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.grok import GrokHost
from vidbyte.tools.builtins.grok import (
    CheckGrokReadyTool,
    ContinueGrokSessionTool,
    ForkGrokSessionTool,
    InterruptGrokTurnTool,
    ListGrokModelsTool,
    ListGrokSessionsTool,
    RunGrokOnceTool,
    SearchGrokSessionsTool,
    SpawnGrokSessionTool,
    WaitGrokTurnTool,
)
from vidbyte.tools.catalog import Tools


class GrokTools(Tools):
    """Catalog of the ten tools over one GrokHost."""

    def __init__(self, host: GrokHost) -> None:
        # The readiness and model checks first, then the four ways to
        # start work, then the session reads and the turn controls.
        super().__init__(
            (
                CheckGrokReadyTool(host),
                ListGrokModelsTool(host),
                SpawnGrokSessionTool(host),
                RunGrokOnceTool(host),
                ContinueGrokSessionTool(host),
                ForkGrokSessionTool(host),
                ListGrokSessionsTool(host),
                SearchGrokSessionsTool(host),
                WaitGrokTurnTool(host),
                InterruptGrokTurnTool(host),
            )
        )

    @staticmethod
    def read_only(host: GrokHost) -> Tools:
        # Only the five READ tools, so nothing in the catalog can
        # start or stop a turn.
        return Tools((CheckGrokReadyTool(host), ListGrokModelsTool(host), ListGrokSessionsTool(host), SearchGrokSessionsTool(host), WaitGrokTurnTool(host)))


__all__ = ["GrokTools"]
