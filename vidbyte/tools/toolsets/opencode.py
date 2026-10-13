"""FILE: vidbyte/tools/toolsets/opencode.py

PURPOSE: Defines OpencodeTools, the catalog of the 18 tools over one OpencodeHost (readiness, models, providers and auth methods, session spawn, continue, fork, revert and unrevert, session and message reads, diffs, turn wait and interrupt, usage, and MCP server registration), and its read_only variant.
ROLE IN CODEBASE: Exported by vidbyte/tools/toolsets/__init__.py; composes the tool classes in vidbyte/tools/builtins/opencode/. Hand it to an agent or to ToolExecutor like any other Tools catalog, with the OpencodeHost open while the tools run.
ARCHITECTURE NOTE: A Tools subclass that holds only the 18 tools over the host it is given, in §9.2 order. The seven WRITE tools are denied by the default PermissionPolicy (EC-142); read_only returns the eleven READ tools, which is what MCP exposure gets (T-5).
FUNCTION INVENTORY: OpencodeTools.__init__ is the narrated main function and builds the 18 tools in spec order; read_only builds the eleven READ tools.
COMMON MODIFICATION PATTERNS: A new opencode tool is one more entry in the tuple, in §9.2 order, and in read_only when it is READ.
WHAT NOT TO DO IN THIS FILE: 1. Do not open or close the host here; the caller owns its async with block. 2. Do not add a WRITE tool to read_only.
KNOWN EDGE CASES: Building the catalog sends no request; a tool run on a host that is not open returns opencode.process_exited (EC-2).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Toolsets), §9.2 rows 11-28, T-5; vidbyte/tools/README.md
TESTS: tests/features/opencode_host/test_opencode_host_tools.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.opencode import OpencodeHost
from vidbyte.tools.builtins.opencode import (
    AddOpencodeMcpServerTool,
    CheckOpencodeReadyTool,
    ContinueOpencodeSessionTool,
    ForkOpencodeSessionTool,
    GetOpencodeMessageTool,
    GetOpencodeProviderAuthTool,
    GetOpencodeSessionDiffTool,
    GetOpencodeSessionMessagesTool,
    GetOpencodeSessionTool,
    InterruptOpencodeTurnTool,
    ListOpencodeModelsTool,
    ListOpencodeProvidersTool,
    ListOpencodeSessionsTool,
    RevertOpencodeSessionTool,
    SpawnOpencodeSessionTool,
    TrackOpencodeSessionUsageTool,
    UnrevertOpencodeSessionTool,
    WaitOpencodeTurnTool,
)
from vidbyte.tools.catalog import Tools


class OpencodeTools(Tools):
    """Catalog of the 18 tools over one OpencodeHost."""

    def __init__(self, host: OpencodeHost) -> None:
        # The readiness, model and provider checks first, then the ways to start or change work,
        # then the session reads, the turn controls, the usage report and the MCP registration.
        super().__init__(
            (
                CheckOpencodeReadyTool(host),
                ListOpencodeModelsTool(host),
                ListOpencodeProvidersTool(host),
                GetOpencodeProviderAuthTool(host),
                SpawnOpencodeSessionTool(host),
                ContinueOpencodeSessionTool(host),
                ForkOpencodeSessionTool(host),
                RevertOpencodeSessionTool(host),
                UnrevertOpencodeSessionTool(host),
                ListOpencodeSessionsTool(host),
                GetOpencodeSessionTool(host),
                GetOpencodeSessionMessagesTool(host),
                GetOpencodeMessageTool(host),
                GetOpencodeSessionDiffTool(host),
                WaitOpencodeTurnTool(host),
                InterruptOpencodeTurnTool(host),
                TrackOpencodeSessionUsageTool(host),
                AddOpencodeMcpServerTool(host),
            )
        )

    @staticmethod
    def read_only(host: OpencodeHost) -> Tools:
        # Only the eleven READ tools, so nothing in the catalog can start, change or stop work (T-5).
        return Tools(
            (
                CheckOpencodeReadyTool(host),
                ListOpencodeModelsTool(host),
                ListOpencodeProvidersTool(host),
                GetOpencodeProviderAuthTool(host),
                ListOpencodeSessionsTool(host),
                GetOpencodeSessionTool(host),
                GetOpencodeSessionMessagesTool(host),
                GetOpencodeMessageTool(host),
                GetOpencodeSessionDiffTool(host),
                WaitOpencodeTurnTool(host),
                TrackOpencodeSessionUsageTool(host),
            )
        )


__all__ = ["OpencodeTools"]
