"""FILE: vidbyte/lib/enums/codex.py

PURPOSE: Defines closed Codex SDK option vocabularies used by validated settings.
ROLE IN CODEBASE: Replaces free-form provider strings with discoverable public enum contracts.
ARCHITECTURE NOTE: Empty PROVIDER_DEFAULT sentinels are omitted before SDK calls.
COMMON MODIFICATION PATTERNS: Add an SDK-supported member when upgrading the pinned compatibility range.
KNOWN EDGE CASES: Enum values must match openai-codex 0.147 wire values exactly.
RELATED DOCS: https://developers.openai.com/codex/sdk; docs/design/codex-harness-agent.md.
TESTS: python scripts/run_ci.py.
"""

from __future__ import annotations

from enum import Enum, StrEnum


class CodexApprovalMode(str, Enum):
    """Stable approval modes accepted by openai-codex 0.147."""

    PROVIDER_DEFAULT = ""
    AUTO_REVIEW = "auto_review"
    DENY_ALL = "deny_all"


class CodexPersonality(str, Enum):
    """Codex response personalities exposed by the installed SDK."""

    PROVIDER_DEFAULT = ""
    NONE = "none"
    FRIENDLY = "friendly"
    PRAGMATIC = "pragmatic"


class CodexReasoningEffort(str, Enum):
    """Reasoning effort values accepted by the installed SDK."""

    PROVIDER_DEFAULT = ""
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class CodexReasoningSummary(str, Enum):
    """Reasoning-summary policies accepted by the installed SDK."""

    PROVIDER_DEFAULT = ""
    NONE = "none"
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"


class CodexSandbox(str, Enum):
    """Stable sandbox modes accepted by openai-codex 0.147."""

    PROVIDER_DEFAULT = ""
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


class CodexThreadSource(str, Enum):
    """Source labels accepted when Codex creates or forks a thread."""

    PROVIDER_DEFAULT = ""
    USER = "user"
    SUBAGENT = "subagent"
    MEMORY_CONSOLIDATION = "memory_consolidation"


class CodexThreadStartSource(str, Enum):
    """Stable thread-start source values accepted by the SDK."""

    PROVIDER_DEFAULT = ""
    STARTUP = "startup"
    CLEAR = "clear"


class CodexInputType(str, Enum):
    """Input variants accepted by a Codex turn."""

    TEXT = "text"
    IMAGE = "image"
    LOCAL_IMAGE = "localImage"
    SKILL = "skill"
    MENTION = "mention"


class CodexContextAnchor(StrEnum):
    """Adapter-owned positions around explicit current-turn input, not native history."""

    BEFORE_IMAGES = "before_images"
    AFTER_IMAGES = "after_images"
    BEFORE_SKILLS = "before_skills"
    AFTER_SKILLS = "after_skills"


__all__ = [
    "CodexApprovalMode",
    "CodexContextAnchor",
    "CodexInputType",
    "CodexPersonality",
    "CodexReasoningEffort",
    "CodexReasoningSummary",
    "CodexSandbox",
    "CodexThreadSource",
    "CodexThreadStartSource",
]
