"""FILE: vidbyte/lib/enums/claude.py

PURPOSE: Defines the closed Claude Code vocabularies that ClaudeHost records, results and tools use.
ROLE IN CODEBASE: Replaces free-form Claude Code option and status strings with discoverable public enum contracts.
ARCHITECTURE NOTE: Each enum mirrors one closed set of the claude-agent-sdk options, CLI flags or stream messages; the host translates members to wire values.
COMMON MODIFICATION PATTERNS: Add an SDK-supported member when upgrading the pinned claude-agent-sdk range, then export new enums from vidbyte.lib.enums.
KNOWN EDGE CASES: Enum values must match claude-agent-sdk 0.2.165 / Claude Code 2.1.296 wire values exactly; empty PROVIDER_DEFAULT sentinels are omitted before SDK calls.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from enum import Enum


class ClaudePermissionMode(str, Enum):
    """Permission modes Claude Code accepts for a session."""

    PROVIDER_DEFAULT = ""
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypassPermissions"
    DONT_ASK = "dontAsk"
    AUTO = "auto"


class ClaudeEffort(str, Enum):
    """Effort levels Claude Code accepts for a session or a subagent."""

    PROVIDER_DEFAULT = ""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class ClaudeThinkingMode(str, Enum):
    """Extended-thinking modes of the SDK thinking option."""

    ADAPTIVE = "adaptive"
    ENABLED = "enabled"
    DISABLED = "disabled"


class ClaudeThinkingDisplay(str, Enum):
    """How Claude Code shows thinking when thinking is enabled."""

    PROVIDER_DEFAULT = ""
    SUMMARIZED = "summarized"
    OMITTED = "omitted"


class ClaudeSystemPromptMode(str, Enum):
    """Whether the request text appends to the preset, replaces it, or names a prompt file."""

    PRESET = "preset"
    REPLACE = "replace"
    FILE = "file"


class ClaudeSettingSource(str, Enum):
    """Claude Code settings files a session may load."""

    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class ClaudePermissionPrompts(str, Enum):
    """Who answers a permission prompt: the host callback, or nobody."""

    HOST = "host"
    NONE = "none"


class ClaudeBeta(str, Enum):
    """API beta headers Claude Code accepts."""

    CONTEXT_1M = "context-1m-2025-08-07"


class ClaudeHookEvent(str, Enum):
    """Hook events a session may register callbacks for."""

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"
    SUBAGENT_STOP = "SubagentStop"
    PRE_COMPACT = "PreCompact"
    NOTIFICATION = "Notification"
    SUBAGENT_START = "SubagentStart"
    PERMISSION_REQUEST = "PermissionRequest"


class ClaudeMemoryScope(str, Enum):
    """Memory scopes a subagent definition may use."""

    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class ClaudeMcpTransport(str, Enum):
    """Transports of an external MCP server passed to Claude Code."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class ClaudeImageMediaType(str, Enum):
    """Image media types a prompt may attach."""

    JPEG = "image/jpeg"
    PNG = "image/png"
    GIF = "image/gif"
    WEBP = "image/webp"


class ClaudeTurnStatus(str, Enum):
    """Lifecycle status of one spawned turn."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ClaudeRateLimitStatus(str, Enum):
    """Status of one rate-limit window reported by Claude Code."""

    ALLOWED = "allowed"
    ALLOWED_WARNING = "allowed_warning"
    REJECTED = "rejected"


class ClaudeRateLimitType(str, Enum):
    """Rate-limit windows Claude Code reports."""

    FIVE_HOUR = "five_hour"
    SEVEN_DAY = "seven_day"
    SEVEN_DAY_OPUS = "seven_day_opus"
    SEVEN_DAY_SONNET = "seven_day_sonnet"
    SEVEN_DAY_OVERAGE_INCLUDED = "seven_day_overage_included"
    OVERAGE = "overage"


class ClaudeMessageKind(str, Enum):
    """Speaker of one stored session message."""

    USER = "user"
    ASSISTANT = "assistant"


class ClaudeCliFlag(str, Enum):
    """Claude Code CLI flags the host passes through the SDK's extra_args."""

    FILE = "file"
    RESTRICTED = "restricted"
    AUTOCOMPACT = "autocompact"
    NAME = "name"
    AGENT = "agent"
    BARE = "bare"
    SAFE_MODE = "safe-mode"
    NO_SESSION_PERSISTENCE = "no-session-persistence"
    WORKTREE = "worktree"
    PLUGIN_URL = "plugin-url"
    PERMISSION_PROMPTS = "permission-prompts"


__all__ = [
    "ClaudeBeta",
    "ClaudeCliFlag",
    "ClaudeEffort",
    "ClaudeHookEvent",
    "ClaudeImageMediaType",
    "ClaudeMcpTransport",
    "ClaudeMemoryScope",
    "ClaudeMessageKind",
    "ClaudePermissionMode",
    "ClaudePermissionPrompts",
    "ClaudeRateLimitStatus",
    "ClaudeRateLimitType",
    "ClaudeSettingSource",
    "ClaudeSystemPromptMode",
    "ClaudeThinkingDisplay",
    "ClaudeThinkingMode",
    "ClaudeTurnStatus",
]
