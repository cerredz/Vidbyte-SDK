"""FILE: vidbyte/lib/enums/claude.py

PURPOSE: Defines closed Claude Agent SDK option vocabularies used by validated settings.
ROLE IN CODEBASE: Replaces free-form provider strings with discoverable public enum contracts.
ARCHITECTURE NOTE: Empty PROVIDER_DEFAULT sentinels are omitted before SDK calls.
COMMON MODIFICATION PATTERNS: Add an SDK-supported member when upgrading the pinned compatibility range.
KNOWN EDGE CASES: Enum values must match claude-agent-sdk 0.2.152 wire values exactly.
RELATED DOCS: https://code.claude.com/docs/en/agent-sdk/python; docs/design/claude-harness-agent.md.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from enum import Enum


class ClaudePermissionMode(str, Enum):
    """Tool permission modes accepted by claude-agent-sdk 0.2.152."""

    PROVIDER_DEFAULT = ""
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    DONT_ASK = "dontAsk"
    BYPASS_PERMISSIONS = "bypassPermissions"
    AUTO = "auto"


class ClaudeEffortLevel(str, Enum):
    """Reasoning effort levels accepted by the installed SDK."""

    PROVIDER_DEFAULT = ""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class ClaudeSettingSource(str, Enum):
    """Filesystem configuration sources the provider may load."""

    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class ClaudeThinkingMode(str, Enum):
    """Extended-thinking configuration variants exposed by the SDK."""

    PROVIDER_DEFAULT = ""
    ADAPTIVE = "adaptive"
    ENABLED = "enabled"
    DISABLED = "disabled"


class ClaudeThinkingDisplay(str, Enum):
    """How the provider surfaces thinking blocks it produced."""

    PROVIDER_DEFAULT = ""
    SUMMARIZED = "summarized"
    OMITTED = "omitted"


class ClaudeSystemPromptKind(str, Enum):
    """How a Vidbyte system prompt resolves to the SDK's system_prompt union."""

    TEXT = "text"
    PRESET = "preset"
    FILE = "file"


class ClaudeResultSubtype(str, Enum):
    """Terminal subtypes the provider reports on its result message."""

    SUCCESS = "success"
    ERROR = "error"
    ERROR_MAX_TURNS = "error_max_turns"
    ERROR_MAX_BUDGET_USD = "error_max_budget_usd"
    ERROR_MAX_STRUCTURED_OUTPUT_RETRIES = "error_max_structured_output_retries"


class ClaudeBlockType(str, Enum):
    """Assistant content block kinds; THINKING is named so it can be excluded."""

    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"


__all__ = [
    "ClaudeBlockType",
    "ClaudeEffortLevel",
    "ClaudePermissionMode",
    "ClaudeResultSubtype",
    "ClaudeSettingSource",
    "ClaudeSystemPromptKind",
    "ClaudeThinkingDisplay",
    "ClaudeThinkingMode",
]
