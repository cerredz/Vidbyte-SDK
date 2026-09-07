"""FILE: vidbyte/agents/claude/__init__.py

PURPOSE: Publishes the Claude-owned harness integration for Vidbyte agents.
ROLE IN CODEBASE: The single public import surface for the Claude adapter.
ARCHITECTURE NOTE: Every export is statically bound; the SDK import stays lazy in transport.
COMMON MODIFICATION PATTERNS: Export a new public record here and at the two parent packages.
KNOWN EDGE CASES: Importing this package must succeed without claude-agent-sdk installed.
RELATED DOCS: docs/design/claude-harness-agent.md.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from vidbyte.agents.claude.agent import ClaudeHarnessAgent
from vidbyte.lib.dataclasses.claude import (
    ClaudeAgentDefinition,
    ClaudeAgentSettings,
    ClaudeForkSettings,
    ClaudeHarnessAgentSettings,
    ClaudeItem,
    ClaudeLoopSettings,
    ClaudeMessageData,
    ClaudeModelSettings,
    ClaudePluginConfig,
    ClaudeProcessSettings,
    ClaudeRunInput,
    ClaudeRunResult,
    ClaudeSandboxSettings,
    ClaudeSessionSettings,
    ClaudeSubagentSettings,
    ClaudeSystemPromptSettings,
    ClaudeToolSettings,
    ClaudeUsage,
)
from vidbyte.lib.enums.claude import (
    ClaudeBlockType,
    ClaudeEffortLevel,
    ClaudePermissionMode,
    ClaudeResultSubtype,
    ClaudeSettingSource,
    ClaudeSystemPromptKind,
    ClaudeThinkingDisplay,
    ClaudeThinkingMode,
)

__all__ = [
    "ClaudeAgentDefinition",
    "ClaudeAgentSettings",
    "ClaudeBlockType",
    "ClaudeEffortLevel",
    "ClaudeForkSettings",
    "ClaudeHarnessAgent",
    "ClaudeHarnessAgentSettings",
    "ClaudeItem",
    "ClaudeLoopSettings",
    "ClaudeMessageData",
    "ClaudeModelSettings",
    "ClaudePermissionMode",
    "ClaudePluginConfig",
    "ClaudeProcessSettings",
    "ClaudeResultSubtype",
    "ClaudeRunInput",
    "ClaudeRunResult",
    "ClaudeSandboxSettings",
    "ClaudeSessionSettings",
    "ClaudeSettingSource",
    "ClaudeSubagentSettings",
    "ClaudeSystemPromptKind",
    "ClaudeSystemPromptSettings",
    "ClaudeThinkingDisplay",
    "ClaudeThinkingMode",
    "ClaudeToolSettings",
    "ClaudeUsage",
]
