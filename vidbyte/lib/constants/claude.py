"""FILE: vidbyte/lib/constants/claude.py

PURPOSE: Defines shared operational constants for the Claude harness adapter.
ROLE IN CODEBASE: Supplies stable bounds, counters, provider labels, and block vocabularies.
ARCHITECTURE NOTE: Constants live below agent modules so every collaborator can import them safely.
COMMON MODIFICATION PATTERNS: Add a CLAUDE-prefixed value when adapter behavior needs a shared literal.
KNOWN EDGE CASES: Supported block kinds track the pinned claude-agent-sdk compatibility range.
RELATED DOCS: docs/design/claude-harness-agent.md.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

CLAUDE_ROOT_FORK_DEPTH = 0
CLAUDE_NEXT_FORK_DEPTH = 1
CLAUDE_PROVIDER_NAME = "claude"
CLAUDE_SDK_EXTRA = "vidbyte-sdk[claude]"
CLAUDE_SDK_DISTRIBUTION = "claude-agent-sdk"
CLAUDE_SDK_MODULE = "claude_agent_sdk"
CLAUDE_JSON_SCHEMA_DRAFT = "http://json-schema.org/draft-07/schema#"
CLAUDE_SCHEMA_DRAFT_KEY = "$schema"
CLAUDE_OUTPUT_FORMAT_TYPE = "json_schema"
CLAUDE_CODE_PRESET_NAME = "claude_code"
CLAUDE_PRESET_TYPE = "preset"
CLAUDE_FILE_TYPE = "file"
CLAUDE_ALL_SKILLS = "all"
CLAUDE_DEFAULT_RECIPIENT = "user"
CLAUDE_MIN_THINKING_BUDGET_TOKENS = 1_024

# Sentinels meaning "no Vidbyte-declared bound": the option is omitted before the
# SDK call so the provider applies its own default rather than an explicit zero.
CLAUDE_PROVIDER_DEFAULT_TIMEOUT_MS = 0
CLAUDE_UNBOUNDED_TURNS = 0
CLAUDE_UNBOUNDED_BUDGET_USD = 0.0
CLAUDE_UNSET_THINKING_BUDGET_TOKENS = 0
CLAUDE_MAX_THINKING_BUDGET_TOKENS = 200_000

# Blocks copied into ClaudeItem. Thinking is absent by design, matching the Codex
# adapter's exclusion of private reasoning content at the serialization boundary.
CLAUDE_SUPPORTED_BLOCK_TYPES = frozenset({"text", "tool_use", "tool_result"})
CLAUDE_SUBAGENT_TOOL_NAMES = frozenset({"Task", "Agent"})
CLAUDE_RESERVED_SUBAGENT_NAMES = frozenset({"general-purpose", "Task", "Agent"})

__all__ = [
    "CLAUDE_ALL_SKILLS",
    "CLAUDE_CODE_PRESET_NAME",
    "CLAUDE_DEFAULT_RECIPIENT",
    "CLAUDE_FILE_TYPE",
    "CLAUDE_JSON_SCHEMA_DRAFT",
    "CLAUDE_MAX_THINKING_BUDGET_TOKENS",
    "CLAUDE_MIN_THINKING_BUDGET_TOKENS",
    "CLAUDE_NEXT_FORK_DEPTH",
    "CLAUDE_OUTPUT_FORMAT_TYPE",
    "CLAUDE_PRESET_TYPE",
    "CLAUDE_PROVIDER_DEFAULT_TIMEOUT_MS",
    "CLAUDE_PROVIDER_NAME",
    "CLAUDE_RESERVED_SUBAGENT_NAMES",
    "CLAUDE_ROOT_FORK_DEPTH",
    "CLAUDE_SCHEMA_DRAFT_KEY",
    "CLAUDE_SDK_DISTRIBUTION",
    "CLAUDE_SDK_EXTRA",
    "CLAUDE_SDK_MODULE",
    "CLAUDE_SUBAGENT_TOOL_NAMES",
    "CLAUDE_SUPPORTED_BLOCK_TYPES",
    "CLAUDE_UNBOUNDED_BUDGET_USD",
    "CLAUDE_UNBOUNDED_TURNS",
    "CLAUDE_UNSET_THINKING_BUDGET_TOKENS",
]
