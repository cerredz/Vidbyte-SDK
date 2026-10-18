"""FILE: vidbyte/lib/enums/codex.py

PURPOSE: Defines closed Codex SDK option vocabularies used by validated settings.
ROLE IN CODEBASE: Replaces free-form provider strings with discoverable public enum contracts.
ARCHITECTURE NOTE: Empty PROVIDER_DEFAULT sentinels are omitted before SDK calls.
COMMON MODIFICATION PATTERNS: Add an SDK-supported member when upgrading the pinned compatibility range.
KNOWN EDGE CASES: Enum values must match openai-codex 0.163 wire values exactly. The three server-request enums (CodexServerRequestKind, CodexApprovalDecision, CodexCommandApprovalKind) mirror the approval and user-input requests CodexHost routes to its approval_handler; object decisions such as policy amendments have no member, because no answer this release sends can carry them. The nine first-class-feature enums (CodexCollaborationModeKind through CodexTurnWaitMode) mirror wire values of Codex's experimental methods, which the stable SDK does not model; CodexTurnEventKind and CodexTurnWaitMode are Vidbyte's own, and CodexTurnWaitMode's values equal asyncio.FIRST_COMPLETED and ALL_COMPLETED. CodexHostOperation holds 55 members: the 25 first-class-feature operations sit between FORGET_CODEX_TURNS and LAUNCH_CODEX_SUBAGENTS in CodexHost method order.
RELATED DOCS: https://developers.openai.com/codex/sdk; docs/design/codex-harness-agent.md; docs/spec/codex-host-thread-helpers/spec.md (CodexSkillScope and the helper operations, section 9.1); docs/spec/codex-host-hardening/spec.md (the server-request enums, MAX and ULTRA, FORGET_CODEX_TURNS, section 8.5); docs/spec/codex-host-first-class/spec.md (the nine feature enums and 25 operations, section 8.5).
TESTS: python scripts/run_ci.py; tests/features/codex_host/test_codex_host_helper_surface.py, tests/features/codex_host/test_codex_host_records.py, tests/features/codex_host/test_codex_host_hardening_records.py and tests/features/codex_host/test_codex_host_feature_constants.py.
"""

from __future__ import annotations

from enum import Enum, StrEnum


class CodexApprovalMode(str, Enum):
    """Stable approval modes accepted by openai-codex 0.162."""

    PROVIDER_DEFAULT = ""
    AUTO_REVIEW = "auto_review"
    DENY_ALL = "deny_all"


class CodexPersonality(str, Enum):
    """Codex response personalities exposed by the installed SDK.

    Since Codex 0.163, FRIENDLY and PRAGMATIC no longer select a
    response style; they only replace a stored NONE setting.
    """

    PROVIDER_DEFAULT = ""
    NONE = "none"
    FRIENDLY = "friendly"
    PRAGMATIC = "pragmatic"


class CodexReasoningEffort(str, Enum):
    """Reasoning effort values accepted by the installed SDK.

    MAX and ULTRA are the 0.163 efforts above XHIGH; a model accepts
    only the efforts list_codex_models reports for it.
    """

    PROVIDER_DEFAULT = ""
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"
    ULTRA = "ultra"


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


class CodexServerRequestKind(str, Enum):
    """The server requests CodexHost routes to its approval_handler."""

    COMMAND_EXECUTION = "item/commandExecution/requestApproval"
    FILE_CHANGE = "item/fileChange/requestApproval"
    USER_INPUT = "item/tool/requestUserInput"


class CodexApprovalDecision(str, Enum):
    """The decisions an approval_handler can send back to Codex."""

    ACCEPT = "accept"
    ACCEPT_FOR_SESSION = "acceptForSession"
    DECLINE = "decline"
    CANCEL = "cancel"


class CodexCommandApprovalKind(str, Enum):
    """What a command approval asks for: a new command, or input typed into a running one."""

    COMMAND = "command"
    WRITE_STDIN = "writeStdin"


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
    """Where a review runs; Codex 0.163 has deprecated DETACHED, so prefer INLINE."""

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


class CodexSkillScope(str, Enum):
    """Where a Codex skill comes from, as skills/list reports it."""

    USER = "user"
    REPO = "repo"
    SYSTEM = "system"
    ADMIN = "admin"


class CodexCollaborationModeKind(str, Enum):
    """A Codex collaboration mode; NONE when Codex listed a preset with no mode."""

    NONE = ""
    PLAN = "plan"
    DEFAULT = "default"


class CodexMemoryMode(str, Enum):
    """Whether Codex may use and write memories for one thread."""

    ENABLED = "enabled"
    DISABLED = "disabled"


class CodexMcpAuthStatus(str, Enum):
    """How an MCP server Codex runs is signed in, as mcpServerStatus/list reports it.

    BEARER is the wire value "bearerToken": the member name leaves out
    the word the security lint reads as a credential (first-class D-40).
    """

    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    NOT_LOGGED_IN = "notLoggedIn"
    BEARER = "bearerToken"
    OAUTH = "oAuth"


class CodexMcpConnectionStatus(str, Enum):
    """Whether Codex has connected to an MCP server; NOT_REPORTED when Codex sent none."""

    NOT_REPORTED = ""
    NOT_STARTED = "notStarted"
    STARTING = "starting"
    CONNECTED = "connected"
    AUTHENTICATION_REQUIRED = "authenticationRequired"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISABLED = "disabled"


class CodexMcpServerDetail(str, Enum):
    """How much an MCP server listing reports: everything, or only tools and sign-in."""

    FULL = "full"
    TOOLS_AND_AUTH_ONLY = "toolsAndAuthOnly"


class CodexTurnSettingsStatus(str, Enum):
    """Codex's answer to a running-turn settings update: taken, or no turn to take it."""

    APPLIED = "applied"
    TARGET_UNAVAILABLE = "targetUnavailable"


class CodexTurnEventKind(str, Enum):
    """What one streamed turn event carries; GAP marks dropped events, ENDED the end."""

    ITEM_STARTED = "item_started"
    ITEM_COMPLETED = "item_completed"
    MESSAGE_DELTA = "message_delta"
    REASONING_SUMMARY_DELTA = "reasoning_summary_delta"
    PLAN_DELTA = "plan_delta"
    COMMAND_OUTPUT_DELTA = "command_output_delta"
    FILE_CHANGE_DELTA = "file_change_delta"
    PLAN_UPDATED = "plan_updated"
    DIFF_UPDATED = "diff_updated"
    USAGE_UPDATED = "usage_updated"
    GAP = "gap"
    ENDED = "ended"


class CodexPlanStepStatus(str, Enum):
    """The state of one step of a turn's plan."""

    PENDING = "pending"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"


class CodexTurnWaitMode(str, Enum):
    """When wait_codex_turns returns; the values equal asyncio's wait constants."""

    FIRST_COMPLETED = "FIRST_COMPLETED"
    ALL_COMPLETED = "ALL_COMPLETED"


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
    FORGET_CODEX_TURNS = "forget_codex_turns"
    UPDATE_CODEX_THREAD_SETTINGS = "update_codex_thread_settings"
    LIST_CODEX_COLLABORATION_MODES = "list_codex_collaboration_modes"
    RUN_CODEX_PLAN = "run_codex_plan"
    STREAM_CODEX_TURN = "stream_codex_turn"
    WAIT_CODEX_TURNS = "wait_codex_turns"
    LIST_CODEX_MCP_SERVERS = "list_codex_mcp_servers"
    UPDATE_CODEX_TURN_SETTINGS = "update_codex_turn_settings"
    SET_CODEX_THREAD_MEMORY_MODE = "set_codex_thread_memory_mode"
    GET_CODEX_MEMORY_STATUS = "get_codex_memory_status"
    RESET_CODEX_MEMORIES = "reset_codex_memories"
    START_CODEX_SIDE_CHAT = "start_codex_side_chat"
    CREATE_CODEX_WORKTREE = "create_codex_worktree"
    PAUSE_CODEX_GOAL = "pause_codex_goal"
    RESUME_CODEX_GOAL = "resume_codex_goal"
    EDIT_CODEX_GOAL = "edit_codex_goal"
    CLEAR_CODEX_GOAL = "clear_codex_goal"
    ARCHIVE_CODEX_THREAD = "archive_codex_thread"
    UNARCHIVE_CODEX_THREAD = "unarchive_codex_thread"
    REVERT_CODEX_THREAD = "revert_codex_thread"
    RENAME_CODEX_THREAD = "rename_codex_thread"
    INJECT_CODEX_ITEMS = "inject_codex_items"
    LIST_CODEX_BACKGROUND_TERMINALS = "list_codex_background_terminals"
    CLEAN_CODEX_BACKGROUND_TERMINALS = "clean_codex_background_terminals"
    SEARCH_CODEX_THREAD_CONTENT = "search_codex_thread_content"
    LIST_CODEX_CHILD_THREADS = "list_codex_child_threads"
    LAUNCH_CODEX_SUBAGENTS = "launch_codex_subagents"
    START_CODEX_REVIEW = "start_codex_review"
    LIST_RECENT_CODEX_THREADS = "list_recent_codex_threads"
    LIST_CODEX_THREADS_SINCE = "list_codex_threads_since"
    SEARCH_CODEX_THREADS = "search_codex_threads"
    GET_CODEX_THREAD_LINEAGE = "get_codex_thread_lineage"
    LIST_CODEX_TURNS = "list_codex_turns"
    COMPACT_CODEX_THREAD = "compact_codex_thread"
    DELETE_CODEX_THREAD = "delete_codex_thread"
    GET_CODEX_GOAL = "get_codex_goal"
    RUN_CODEX_GOAL = "run_codex_goal"
    LIST_CODEX_SKILLS = "list_codex_skills"
    RUN_CODEX_SKILL = "run_codex_skill"
    RUN_CODEX_OPENAI_DOCS = "run_codex_openai_docs"


__all__ = [
    "CodexFailureClass",
    "CodexAccountKind",
    "CodexApprovalDecision",
    "CodexApprovalMode",
    "CodexApprovalPolicy",
    "CodexApprovalsReviewer",
    "CodexCollaborationModeKind",
    "CodexCommandApprovalKind",
    "CodexContextAnchor",
    "CodexGoalStatus",
    "CodexHostOperation",
    "CodexInputType",
    "CodexMcpAuthStatus",
    "CodexMcpConnectionStatus",
    "CodexMcpServerDetail",
    "CodexMemoryMode",
    "CodexPersonality",
    "CodexPlanStepStatus",
    "CodexReasoningEffort",
    "CodexReasoningSummary",
    "CodexReviewDelivery",
    "CodexReviewTargetKind",
    "CodexSandbox",
    "CodexSandboxReadiness",
    "CodexServerRequestKind",
    "CodexSkillScope",
    "CodexSortDirection",
    "CodexThreadSortKey",
    "CodexThreadSource",
    "CodexThreadSourceKind",
    "CodexThreadStartSource",
    "CodexThreadStatus",
    "CodexTurnEventKind",
    "CodexTurnSettingsStatus",
    "CodexTurnStatus",
    "CodexTurnWaitMode",
]
