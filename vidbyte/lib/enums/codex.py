"""FILE: vidbyte/lib/enums/codex.py

PURPOSE: Defines closed Codex SDK option vocabularies used by validated settings.
ROLE IN CODEBASE: Replaces free-form provider strings with discoverable public enum contracts.
ARCHITECTURE NOTE: Empty PROVIDER_DEFAULT sentinels are omitted before SDK calls.
COMMON MODIFICATION PATTERNS: Add an SDK-supported member when upgrading the pinned compatibility range.
KNOWN EDGE CASES: Enum values must match openai-codex 0.162 wire values exactly.
RELATED DOCS: https://developers.openai.com/codex/sdk; docs/design/codex-harness-agent.md.
TESTS: python scripts/run_ci.py.
"""

from __future__ import annotations

from enum import Enum, StrEnum


class CodexApprovalMode(str, Enum):
    """Stable approval modes accepted by openai-codex 0.162."""

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
    """Stable sandbox modes accepted by openai-codex 0.162."""

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


class CodexFailureClass(str, Enum):
    """Whether a Codex failure can be survived, and by what kind of retry."""

    MODEL_RETRYABLE = "model_retryable"
    TRANSIENT = "transient"
    TERMINAL = "terminal"


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


class CodexApprovalPolicy(str, Enum):
    """When Codex asks for approval before running a command or changing a file."""

    PROVIDER_DEFAULT = ""
    UNTRUSTED = "untrusted"
    ON_REQUEST = "on-request"
    NEVER = "never"


class CodexApprovalsReviewer(str, Enum):
    """Who answers Codex's approval requests on a thread."""

    PROVIDER_DEFAULT = ""
    USER = "user"
    AUTO_REVIEW = "auto_review"
    GUARDIAN_SUBAGENT = "guardian_subagent"


class CodexTurnStatus(str, Enum):
    """The state of one Codex turn, as the app-server reports it."""

    RUNNING = "inProgress"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class CodexSandboxReadiness(str, Enum):
    """Whether the Codex Windows sandbox is set up; NOT_CHECKED off Windows."""

    NOT_CHECKED = ""
    READY = "ready"
    NOT_CONFIGURED = "notConfigured"
    UPDATE_REQUIRED = "updateRequired"


class CodexAccountKind(str, Enum):
    """The kind of account Codex is signed in with; NONE when signed out."""

    NONE = ""
    API_KEY = "apiKey"
    CHATGPT = "chatgpt"
    AMAZON_BEDROCK = "amazonBedrock"


class CodexThreadStatus(str, Enum):
    """The runtime status Codex reports for a stored thread."""

    NOT_LOADED = "notLoaded"
    IDLE = "idle"
    SYSTEM_ERROR = "systemError"
    ACTIVE = "active"


class CodexThreadSortKey(str, Enum):
    """The field Codex sorts a thread listing by."""

    PROVIDER_DEFAULT = ""
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    RECENCY_AT = "recency_at"
    SECTION_POSITION = "section_position"


class CodexSortDirection(str, Enum):
    """The direction of a thread listing's sort."""

    PROVIDER_DEFAULT = ""
    ASC = "asc"
    DESC = "desc"


class CodexThreadSourceKind(str, Enum):
    """The client or agent that created a thread, used to filter listings."""

    CLI = "cli"
    VSCODE = "vscode"
    EXEC = "exec"
    APP_SERVER = "appServer"
    SUB_AGENT = "subAgent"
    SUB_AGENT_REVIEW = "subAgentReview"
    SUB_AGENT_COMPACT = "subAgentCompact"
    SUB_AGENT_THREAD_SPAWN = "subAgentThreadSpawn"
    SUB_AGENT_OTHER = "subAgentOther"
    UNKNOWN = "unknown"


class CodexReviewTargetKind(str, Enum):
    """What a Codex code review looks at."""

    UNCOMMITTED_CHANGES = "uncommittedChanges"
    BASE_BRANCH = "baseBranch"
    COMMIT = "commit"
    CUSTOM = "custom"


class CodexReviewDelivery(str, Enum):
    """Where a review runs; Codex has deprecated DETACHED."""

    INLINE = "inline"
    DETACHED = "detached"


class CodexGoalStatus(str, Enum):
    """The state of a Codex thread goal; NONE when the turn has no goal."""

    NONE = ""
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    USAGE_LIMITED = "usageLimited"
    BUDGET_LIMITED = "budgetLimited"
    COMPLETE = "complete"


class CodexHostOperation(str, Enum):
    """The CodexHost step an error came from: open, request checks, or one function."""

    OPEN_HOST = "open_host"
    VALIDATE_SPAWN_REQUEST = "validate_spawn_request"
    CHECK_CODEX_READY = "check_codex_ready"
    GET_CODEX_RATE_LIMITS = "get_codex_rate_limits"
    LIST_CODEX_MODELS = "list_codex_models"
    SPAWN_CODEX_THREAD = "spawn_codex_thread"
    CONTINUE_CODEX_THREAD = "continue_codex_thread"
    FORK_CODEX_THREAD = "fork_codex_thread"
    LIST_CODEX_THREADS = "list_codex_threads"
    READ_CODEX_THREAD = "read_codex_thread"
    WAIT_CODEX_TURN = "wait_codex_turn"
    GET_CODEX_TURN_RESULT = "get_codex_turn_result"
    STEER_CODEX_TURN = "steer_codex_turn"
    INTERRUPT_CODEX_TURN = "interrupt_codex_turn"
    TRACK_CODEX_THREAD_USAGE = "track_codex_thread_usage"
    LAUNCH_CODEX_SUBAGENTS = "launch_codex_subagents"
    START_CODEX_REVIEW = "start_codex_review"


__all__ = [
    "CodexFailureClass",
    "CodexAccountKind",
    "CodexApprovalMode",
    "CodexApprovalPolicy",
    "CodexApprovalsReviewer",
    "CodexContextAnchor",
    "CodexGoalStatus",
    "CodexHostOperation",
    "CodexInputType",
    "CodexPersonality",
    "CodexReasoningEffort",
    "CodexReasoningSummary",
    "CodexReviewDelivery",
    "CodexReviewTargetKind",
    "CodexSandbox",
    "CodexSandboxReadiness",
    "CodexSortDirection",
    "CodexThreadSortKey",
    "CodexThreadSource",
    "CodexThreadSourceKind",
    "CodexThreadStartSource",
    "CodexThreadStatus",
    "CodexTurnStatus",
]
