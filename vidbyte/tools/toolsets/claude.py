"""FILE: vidbyte/tools/toolsets/claude.py

PURPOSE: Defines ClaudeTools, the catalog of the fifteen Claude Code tools over one ClaudeHost and one base request.
ROLE IN CODEBASE: Built by developers and given to an agent as its tools, or served over MCP by McpStudioServer; exported by vidbyte/tools/toolsets/__init__.py. Composes the tools in vidbyte/tools/builtins/claude/, which call the ClaudeHost in vidbyte/harnesses/native/claude/host.py.
ARCHITECTURE NOTE: ClaudeTools is a Tools subclass that holds only the fifteen tools, in the section 9.2 order. Every tool shares the one host and the one base request, and the base request fixes every spawn setting except the prompt (D-13). ClaudeHost is imported only for type checking, so importing this module never loads the harness or claude_agent_sdk (INV-1).
COMMON MODIFICATION PATTERNS: A new Claude tool joins get_tools at its place in the order and is exported by vidbyte/tools/builtins/claude/__init__.py.
KNOWN EDGE CASES: The history tools can read the transcripts of every project on this machine, not only the base request's folder (T-2). Served through McpStudioServer, which applies no PermissionPolicy, the WRITE tools run without a permission gate (T-4). Custom tools in the base request run under PermissionPolicy.allow_all() once Claude Code approves a call to them (D-12). With setting_sources left unset, spawned sessions load the user's own Claude Code settings and permission rules.
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.claude import (
    CheckClaudeReadyTool,
    ContinueClaudeSessionTool,
    ForkClaudeSessionTool,
    GetClaudeRateLimitsTool,
    GetClaudeSessionInfoTool,
    GetClaudeSessionMessagesTool,
    GetClaudeTurnResultTool,
    InterruptClaudeTurnTool,
    LaunchClaudeSubagentsTool,
    ListClaudeModelsTool,
    ListClaudeSessionsTool,
    SpawnClaudeSessionTool,
    SteerClaudeSessionTool,
    TrackClaudeSessionUsageTool,
    WaitClaudeTurnTool,
)
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from vidbyte.harnesses.native.claude.host import ClaudeHost


class ClaudeTools(Tools):
    """Catalog of the fifteen Claude Code tools, all over one host and one base request."""

    def __init__(self, host: ClaudeHost, request: ClaudeSpawnRequest | None = None) -> None:
        # @intent the-base-request-defaults-to-an-empty-request
        # Without a base request the tools spawn with
        # ClaudeSpawnRequest's own defaults; either way the model adds
        # only prompts and ids to it, never a setting of its own (D-13).
        #
        # Use the developer's base request, or the record's defaults
        # when none is given.
        base = ClaudeSpawnRequest() if request is None else request
        # Build the fifteen tools over the one host and base request, in
        # the order the model sees them.
        super().__init__(self.get_tools(host, base))

    @staticmethod
    def get_tools(host: ClaudeHost, request: ClaudeSpawnRequest) -> tuple[BaseTool, ...]:
        """Return the fifteen Claude tools over one host and base request, in the section 9.2 order."""
        # @intent every-tool-shares-one-host
        # All fifteen tools get the same host and base request, so a
        # handle one tool returns is known to every other tool, and no
        # tool reaches another host's turns (D-14).
        return (
            CheckClaudeReadyTool(host, request),
            ListClaudeModelsTool(host, request),
            GetClaudeRateLimitsTool(host, request),
            SpawnClaudeSessionTool(host, request),
            ContinueClaudeSessionTool(host, request),
            ForkClaudeSessionTool(host, request),
            LaunchClaudeSubagentsTool(host, request),
            ListClaudeSessionsTool(host, request),
            GetClaudeSessionInfoTool(host, request),
            GetClaudeSessionMessagesTool(host, request),
            WaitClaudeTurnTool(host, request),
            GetClaudeTurnResultTool(host, request),
            SteerClaudeSessionTool(host, request),
            InterruptClaudeTurnTool(host, request),
            TrackClaudeSessionUsageTool(host, request),
        )


__all__ = ["ClaudeTools"]
