"""FILE: vidbyte/tools/toolsets/muse.py

PURPOSE: Defines MuseTools, the catalog of the twelve tools over one MuseHost (check_muse_ready, list_muse_models, spawn_muse_session, continue_muse_session, fork_muse_session, list_muse_sessions, read_muse_session, page_muse_session, steer_muse_turn, interrupt_muse_turn, wait_muse_turn, track_muse_session_usage), and its read_only variant.
ROLE IN CODEBASE: Exported by vidbyte/tools/toolsets/__init__.py; composes the tool classes in vidbyte/tools/builtins/muse/. Hand it to an agent or to ToolExecutor like any other Tools catalog, with the MuseHost open while the tools run.
ARCHITECTURE NOTE: A Tools subclass that holds only the twelve tools over the host it is given. The five WRITE tools are denied by the default PermissionPolicy (EC-142); read_only returns the seven READ tools, which is what MCP exposure gets (T-5).
FUNCTION INVENTORY: MuseTools.__init__ is the narrated main function and builds the twelve tools in spec order; read_only builds the seven READ tools.
COMMON MODIFICATION PATTERNS: A new Muse tool is one more entry in the tuple, in §9.2 order, and in read_only when it is READ.
WHAT NOT TO DO IN THIS FILE: 1. Do not open or close the host here; the caller owns its async with block. 2. Do not add a WRITE tool to read_only.
KNOWN EDGE CASES: Building the catalog starts no process; a tool run on a host that is not open returns muse.process_exited (EC-2).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Toolsets), §9.2 rows 29-40, T-5; vidbyte/tools/README.md
TESTS: tests/features/muse_host/test_muse_host_tools.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.muse import MuseHost
from vidbyte.tools.builtins.muse import (
    CheckMuseReadyTool,
    ContinueMuseSessionTool,
    ForkMuseSessionTool,
    InterruptMuseTurnTool,
    ListMuseModelsTool,
    ListMuseSessionsTool,
    PageMuseSessionTool,
    ReadMuseSessionTool,
    SpawnMuseSessionTool,
    SteerMuseTurnTool,
    TrackMuseSessionUsageTool,
    WaitMuseTurnTool,
)
from vidbyte.tools.catalog import Tools


class MuseTools(Tools):
    """Catalog of the twelve tools over one MuseHost."""

    def __init__(self, host: MuseHost) -> None:
        # The readiness and model checks first, then the three ways to
        # start or copy work, then the session reads, the turn
        # controls and usage.
        super().__init__(
            (
                CheckMuseReadyTool(host),
                ListMuseModelsTool(host),
                SpawnMuseSessionTool(host),
                ContinueMuseSessionTool(host),
                ForkMuseSessionTool(host),
                ListMuseSessionsTool(host),
                ReadMuseSessionTool(host),
                PageMuseSessionTool(host),
                SteerMuseTurnTool(host),
                InterruptMuseTurnTool(host),
                WaitMuseTurnTool(host),
                TrackMuseSessionUsageTool(host),
            )
        )

    @staticmethod
    def read_only(host: MuseHost) -> Tools:
        # Only the seven READ tools, so nothing in the catalog can
        # start, copy, steer or stop a turn.
        return Tools(
            (
                CheckMuseReadyTool(host),
                ListMuseModelsTool(host),
                ListMuseSessionsTool(host),
                ReadMuseSessionTool(host),
                PageMuseSessionTool(host),
                WaitMuseTurnTool(host),
                TrackMuseSessionUsageTool(host),
            )
        )


__all__ = ["MuseTools"]
