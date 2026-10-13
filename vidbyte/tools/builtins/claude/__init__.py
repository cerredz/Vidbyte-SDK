"""FILE: vidbyte/tools/builtins/claude/__init__.py

PURPOSE: Exports the fifteen model-facing Claude Code tools, one per ClaudeHost function: readiness, models, rate limits, spawn, continue, fork, launch, the three session-history reads, and wait, result, steer, interrupt and usage for a turn.
ROLE IN CODEBASE: Imported by vidbyte/tools/builtins/__init__.py and by ClaudeTools (vidbyte/tools/toolsets/claude.py), which builds all fifteen over one host. The tools call the ClaudeHost in vidbyte/harnesses/native/claude/host.py.
ARCHITECTURE NOTE: Every tool subclasses _ClaudeBuiltinTool (_base.py), takes its text from descriptions.py, and imports ClaudeHost only for type checking, so importing this package never loads vidbyte.harnesses or claude_agent_sdk (INV-1).
COMMON MODIFICATION PATTERNS: A new Claude tool goes in the module of its group, is imported here and added to __all__ in sorted order, and joins ClaudeTools.get_tools.
KNOWN EDGE CASES: The history tools can read the transcripts of every project on this machine, not only the folder of the developer's base request (T-2). The WRITE tools run without any permission gate when the tools are served through McpStudioServer, which applies no PermissionPolicy (T-4).
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from vidbyte.tools.builtins.claude.history import (
    GetClaudeSessionInfoTool,
    GetClaudeSessionMessagesTool,
    ListClaudeSessionsTool,
)
from vidbyte.tools.builtins.claude.readiness import (
    CheckClaudeReadyTool,
    GetClaudeRateLimitsTool,
    ListClaudeModelsTool,
)
from vidbyte.tools.builtins.claude.sessions import (
    ContinueClaudeSessionTool,
    ForkClaudeSessionTool,
    LaunchClaudeSubagentsTool,
    SpawnClaudeSessionTool,
)
from vidbyte.tools.builtins.claude.turns import (
    GetClaudeTurnResultTool,
    InterruptClaudeTurnTool,
    SteerClaudeSessionTool,
    TrackClaudeSessionUsageTool,
    WaitClaudeTurnTool,
)

__all__ = [
    "CheckClaudeReadyTool",
    "ContinueClaudeSessionTool",
    "ForkClaudeSessionTool",
    "GetClaudeRateLimitsTool",
    "GetClaudeSessionInfoTool",
    "GetClaudeSessionMessagesTool",
    "GetClaudeTurnResultTool",
    "InterruptClaudeTurnTool",
    "LaunchClaudeSubagentsTool",
    "ListClaudeModelsTool",
    "ListClaudeSessionsTool",
    "SpawnClaudeSessionTool",
    "SteerClaudeSessionTool",
    "TrackClaudeSessionUsageTool",
    "WaitClaudeTurnTool",
]
