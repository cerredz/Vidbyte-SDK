"""FILE: vidbyte/lib/constants/codex.py

PURPOSE: Defines shared operational constants for the Codex harness adapter.
ROLE IN CODEBASE: Supplies stable bounds, counters, provider labels, and item vocabularies.
ARCHITECTURE NOTE: Constants live below agent modules so every collaborator can import them safely.
COMMON MODIFICATION PATTERNS: Add a CODEX-prefixed value when adapter behavior needs a shared literal.
KNOWN EDGE CASES: Supported item kinds track the pinned openai-codex compatibility range.
RELATED DOCS: docs/design/codex-harness-agent.md.
TESTS: python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.lib.enums.codex import (
    CodexApprovalMode,
    CodexFailureClass,
    CodexGoalStatus,
)
from vidbyte.lib.enums.failure import (
    FailureCode,
    FailureDisposition,
    FailurePhase,
    FailureSeverity,
)

CODEX_ROOT_FORK_DEPTH = 0
CODEX_NEXT_FORK_DEPTH = 1
CODEX_ZERO_DURATION_MS = 0
CODEX_PROVIDER_NAME = "codex"
# Codex owns its model/tool loop, so these hooks have no point at which Vidbyte
# could refuse an action. Declaring one must fail at construction rather than
# load successfully and never run.
CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS = frozenset(
    {
        "before_iteration",
        "before_model_call",
        "after_model_response",
        "before_tool_call",
        "after_tool_call",
        "after_iteration",
        "review_finish",
    }
)
# MiddlewarePipeline.metadata() already nests events and event_count under this
# one key, so no separate events key is needed.
CODEX_MIDDLEWARE_METADATA_KEY = "middleware"
# Codex executes OpenAI models, so its token usage parses and prices through the
# OpenAI registry. A dedicated member would duplicate that rate table verbatim.
CODEX_USAGE_PROVIDER = "openai"
# Matches the key the direct runtime publishes, so one caller reads both agent kinds.
CODEX_USAGE_ROLLUP_KEY = "usage_rollup"
CODEX_SDK_EXTRA = "vidbyte-sdk[codex]"
CODEX_RESERVED_SUBAGENT_NAMES = frozenset(
    {
        "enabled",
        "interrupt_message",
        "default_subagent_model",
        "default_subagent_reasoning_effort",
        "max_concurrent_threads_per_session",
        "max_threads",
    }
)
CODEX_SUBAGENT_ITEM_TYPES = frozenset({"collabAgentToolCall", "subAgentActivity"})
CODEX_SUPPORTED_ITEM_TYPES = frozenset(
    {
        "agentMessage",
        "collabAgentToolCall",
        "commandExecution",
        "contextCompaction",
        "dynamicToolCall",
        "enteredReviewMode",
        "exitedReviewMode",
        "fileChange",
        "hookPrompt",
        "imageGeneration",
        "imageView",
        "mcpToolCall",
        "plan",
        "reasoning",
        "sleep",
        "subAgentActivity",
        "userMessage",
        "webSearch",
    }
)

# Every codex.* failure code, classified once. Keeping this as data rather than
# branches means a new code is one row, and a missing row is detectable: the
# translator reports TERMINAL/CRITICAL rather than defaulting to retryable and
# silently spending a whole fallback chain on an unrecoverable failure.
CODEX_FAILURE_SOURCE = "codex_harness_agent"
# Chain index 0 is always the primary model, and attempt numbering is 1-based so a
# failure detail reading "attempt 1" means the first try rather than the second.
CODEX_PRIMARY_CHAIN_INDEX = 0
CODEX_FIRST_ATTEMPT = 1
CODEX_MAX_TURN_FAILURES = 32
CODEX_FAILURE_CLASSIFICATION: Mapping[str, tuple[str, str, str, str]] = {
    FailureCode.CODEX_SDK_UNAVAILABLE.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.CRITICAL.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.INPUT.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_CONTENT_TRANSLATION_FAILED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.INPUT.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_THREAD_START_FAILED.value: (
        CodexFailureClass.MODEL_RETRYABLE.value,
        FailurePhase.MODEL.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_TURN_FAILED.value: (
        CodexFailureClass.MODEL_RETRYABLE.value,
        FailurePhase.MODEL.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_THREAD_RESUME_FAILED.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.SESSION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_FORK_FAILED.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.RESOURCE.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_RESPONSE_INVALID.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.OUTPUT.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.ROUTE.value,
    ),
    # Middleware codes are terminal: a fallback model must never be a way around a
    # policy decision, and an action Codex cannot represent fails on every model.
    FailureCode.CODEX_MIDDLEWARE_ABORTED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.RUNTIME.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.STOP.value,
    ),
    FailureCode.CODEX_MIDDLEWARE_UNSUPPORTED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    # A run option Codex cannot honor is the caller's configuration, so every model
    # would refuse it the same way; it is raised before any turn starts.
    FailureCode.CODEX_RUN_OPTION_UNSUPPORTED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    # Terminal until a re-prompt policy exists: the turn already ran and edited
    # files, so retrying on another model is a policy decision, not a recovery.
    FailureCode.CODEX_CONTRACT_UNMET.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.OUTPUT.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    # CodexHost codes. Setup problems are terminal until the developer fixes
    # them; usage windows, overload and a dead process pass with time or a
    # new host; Vidbyte's own stops are warnings that end the turn.
    FailureCode.CODEX_NOT_INSTALLED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.CRITICAL.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_VERSION_UNSUPPORTED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.CRITICAL.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_NOT_SIGNED_IN.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_USAGE_LIMITED.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.RESOURCE.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.STOP.value,
    ),
    FailureCode.CODEX_MODEL_UNKNOWN.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_SESSION_NOT_FOUND.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.SESSION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_SESSION_BUSY.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.SESSION.value,
        FailureSeverity.WARNING.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_BUDGET_EXHAUSTED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.RESOURCE.value,
        FailureSeverity.WARNING.value,
        FailureDisposition.STOP.value,
    ),
    FailureCode.CODEX_API_ERROR.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.MODEL.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_PERMISSION_DENIED.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.ACTION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.STOP.value,
    ),
    FailureCode.CODEX_SANDBOX_NOT_READY.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_SCHEMA_VIOLATION.value: (
        CodexFailureClass.MODEL_RETRYABLE.value,
        FailurePhase.OUTPUT.value,
        FailureSeverity.ERROR.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_PROCESS_EXITED.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.RESOURCE.value,
        FailureSeverity.CRITICAL.value,
        FailureDisposition.ROUTE.value,
    ),
    FailureCode.CODEX_PROTOCOL_MISMATCH.value: (
        CodexFailureClass.TERMINAL.value,
        FailurePhase.CONFIGURATION.value,
        FailureSeverity.CRITICAL.value,
        FailureDisposition.RAISE.value,
    ),
    FailureCode.CODEX_TURN_TIMED_OUT.value: (
        CodexFailureClass.TRANSIENT.value,
        FailurePhase.RESOURCE.value,
        FailureSeverity.WARNING.value,
        FailureDisposition.STOP.value,
    ),
}
# Published apart from one another so a caller can tell "no failures" from
# "one recovered failure", and a first-attempt answer from a fallback answer.
CODEX_FAILURES_KEY = "failures"
CODEX_FALLBACK_ATTEMPTS_KEY = "fallback_attempts"
CODEX_ANSWERING_MODEL_KEY = "answering_model"
# Codex validates dynamic function-tool names against the Responses API identifier
# rules at thread/start; checking them here turns a thread-start failure into a
# construction error that names the offending tool.
CODEX_DYNAMIC_TOOL_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"
CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH = 128
CODEX_RESERVED_DYNAMIC_TOOL_NAME = "mcp"
CODEX_RESERVED_DYNAMIC_TOOL_PREFIX = "mcp__"
# App-server wire names for registering dynamic tools and answering their calls.
CODEX_DYNAMIC_TOOLS_PARAM = "dynamicTools"
CODEX_THREAD_START_METHOD = "thread/start"
CODEX_TOOL_CALL_METHOD = "item/tool/call"
# The SDK answers server requests on its only reader thread, so one hung tool
# would stall the whole turn; a bounded wait returns a failed call instead.
CODEX_TOOL_CALL_TIMEOUT_SECONDS = 300.0
# The three item types that represent a tool actually running. webSearch, fileChange,
# and imageView are native capabilities rather than tool calls; counting them would
# inflate every effort floor by an amount that varies with the prompt.
CODEX_TOOL_ITEM_TYPES = frozenset({"commandExecution", "mcpToolCall", "dynamicToolCall"})
CODEX_COMPACTION_ITEM_TYPE = "contextCompaction"
CODEX_ITEM_COMPLETED_STATUS = "completed"
CODEX_COMMAND_SUCCESS_EXIT_CODE = 0
CODEX_MILLISECONDS_PER_SECOND = 1000
# Counters describing a Vidbyte-owned loop. Codex owns its iterations and reports
# neither, so a contract reading one would evaluate against zero and always fail.
CODEX_UNOBSERVABLE_COUNTER_KEYS = frozenset({"iteration_count", "model_call_count"})
# AgentLoopSettings fields describing an inner loop, a local tool executor, or a
# Vidbyte-managed context window. Accepting one silently would let a caller believe
# a bound exists that nothing enforces.
CODEX_UNSUPPORTED_LOOP_FIELDS = (
    "max_iterations",
    "max_tokens",
    "max_tool_calls",
    "max_parallel_tool_calls",
    "max_retries",
    "timeout_seconds",
    "context_window_budget",
    "compaction_trigger_tokens",
    "compaction_target_tokens",
    "allowed_tools",
    "tool_error_policy",
    "tool_settings",
)
CODEX_CONTRACTS_KEY = "output_contracts"
# One turn at a time per agent instance. A Codex thread is a single conversation,
# so simultaneous turns against it are not a performance opportunity the provider
# offers — and the facade's thread_id, history, and usage ledger would race.
CODEX_MAX_CONCURRENT_TURNS = 1
# CodexHost bounds each app-server call by the tool bridge's bound, so a
# host call never outlives the dynamic-tool call that made it (D-3).
CODEX_HOST_REQUEST_TIMEOUT_SECONDS = CODEX_TOOL_CALL_TIMEOUT_SECONDS
# The wait tool's default and clamp, kept below the bridge bound so a
# wait made from inside a Codex dynamic tool still answers (D-31).
CODEX_HOST_TOOL_MAX_WAIT_SECONDS = 240.0
# Each host's own call executor size: the ceiling of the standard
# library's default pool size. Workers start only when needed (D-1).
CODEX_HOST_WORKER_THREADS = 32
# The bound on each interrupt sent at close and on the goal cancel after
# a failed goal start; a live app-server answers at once (INV-7).
CODEX_HOST_CLOSE_INTERRUPT_SECONDS = 5.0
# How long close waits for the close thread; CodexClient.close() bounds
# itself to about 3 seconds (INV-7).
CODEX_HOST_CLOSE_WAIT_SECONDS = 10.0
# The host's dynamic-tools opt-in message (INV-29).
CODEX_HOST_EXPERIMENTAL_API_TEXT = "Dynamic tools on CodexHost require CodexClientSettings(experimental_api=True)."
# The next step of every configuration.unsupported_combination refusal:
# a USER reviewer at construction (D-16) or reported by Codex (D-32).
CODEX_HOST_USER_REVIEWER_TEXT = "Set approvals_reviewer=AUTO_REVIEW or GUARDIAN_SUBAGENT, and set it whenever approval_policy is set. To continue a thread whose reviewer is user, pass overrides=CodexSpawnRequest(approvals_reviewer=AUTO_REVIEW), or set it in the CodexHostTools spawn_defaults. Answering approval requests in code needs set_codex_approval_handler, which this release does not include."
# The oldest codex runtime the host talks to, the SDK's own floor (D-5).
CODEX_HOST_MINIMUM_VERSION = "0.151.0"
# The executable name the host resolves on PATH (D-4).
CODEX_HOST_BINARY_NAME = "codex"
# max_attempts for raw calls that spend usage, so none is sent twice (D-2).
CODEX_HOST_SINGLE_ATTEMPT = 1
# Lower bounds for max_live_turns, token_budget and max_output_tokens.
CODEX_HOST_MIN_LIVE_TURNS = 1
CODEX_HOST_MIN_TOKEN_LIMIT = 1
# Timeouts must be strictly greater than this.
CODEX_HOST_MIN_EXCLUSIVE_SECONDS = 0.0
# The approval_mode thread/start sends when nothing is set (D-16).
CODEX_HOST_DEFAULT_APPROVAL_MODE = CodexApprovalMode.AUTO_REVIEW
# App-server methods the host calls through the SDK's raw request path.
CODEX_RATE_LIMITS_READ_METHOD = "account/rateLimits/read"
CODEX_SANDBOX_READINESS_METHOD = "windowsSandbox/readiness"
CODEX_REVIEW_START_METHOD = "review/start"
CODEX_GOAL_SET_METHOD = "thread/goal/set"
CODEX_MODEL_LIST_METHOD = "model/list"
# Notification names the turn watchers read.
CODEX_TURN_STARTED_NOTIFICATION = "turn/started"
CODEX_TURN_COMPLETED_NOTIFICATION = "turn/completed"
CODEX_ITEM_COMPLETED_NOTIFICATION = "item/completed"
CODEX_USAGE_UPDATED_NOTIFICATION = "thread/tokenUsage/updated"
CODEX_GOAL_UPDATED_NOTIFICATION = "thread/goal/updated"
CODEX_GOAL_CLEARED_NOTIFICATION = "thread/goal/cleared"
# Maps an approval_mode value to the wire approvalPolicy and
# approvalsReviewer; an empty reviewer is left unsent.
CODEX_APPROVAL_MODE_WIRE: Mapping[str, tuple[str, str]] = {
    "auto_review": ("on-request", "auto_review"),
    "deny_all": ("never", ""),
}
# Maps a CodexSandbox value to the thread sandbox mode and to the turn
# sandboxPolicy type.
CODEX_SANDBOX_THREAD_MODE: Mapping[str, str] = {
    "read-only": "read-only",
    "workspace-write": "workspace-write",
    "full-access": "danger-full-access",
}
CODEX_SANDBOX_TURN_POLICY: Mapping[str, str] = {
    "read-only": "readOnly",
    "workspace-write": "workspaceWrite",
    "full-access": "dangerFullAccess",
}
# Approval requests the host's router accepts, mirroring the SDK's own
# default handler (D-16).
CODEX_ACCEPTED_APPROVAL_METHODS = frozenset(
    {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}
)
CODEX_APPROVAL_ACCEPT_DECISION = "accept"
# Maps a turn error's codexErrorInfo key to a failure code; every other
# key means codex.api_error.
CODEX_ERROR_INFO_CODES: Mapping[str, str] = {
    "usageLimitExceeded": FailureCode.CODEX_USAGE_LIMITED.value,
    "rateLimitExceeded": FailureCode.CODEX_USAGE_LIMITED.value,
    "sessionBudgetExceeded": FailureCode.CODEX_BUDGET_EXHAUSTED.value,
    "contextWindowExceeded": FailureCode.CODEX_BUDGET_EXHAUSTED.value,
    "unauthorized": FailureCode.CODEX_NOT_SIGNED_IN.value,
    "sandboxError": FailureCode.CODEX_SANDBOX_NOT_READY.value,
    "tooManyDenials": FailureCode.CODEX_PERMISSION_DENIED.value,
    "cyberPolicy": FailureCode.CODEX_PERMISSION_DENIED.value,
    "misalignmentPolicyViolation": FailureCode.CODEX_PERMISSION_DENIED.value,
}
# Goal statuses that end a goal run, as openai-codex's goal stream ends.
CODEX_GOAL_TERMINAL_STATUSES = frozenset(
    {
        CodexGoalStatus.PAUSED,
        CodexGoalStatus.BLOCKED,
        CodexGoalStatus.USAGE_LIMITED,
        CodexGoalStatus.BUDGET_LIMITED,
        CodexGoalStatus.COMPLETE,
    }
)
# The next step each CodexHost failure tells its caller to take.
CODEX_NEXT_STEPS: Mapping[str, str] = {
    FailureCode.CODEX_NOT_INSTALLED.value: "Install the Codex CLI (npm install -g @openai/codex) or pass CodexClientSettings(codex_bin=...).",
    FailureCode.CODEX_VERSION_UNSUPPORTED.value: "Run codex update, then open a new CodexHost.",
    FailureCode.CODEX_NOT_SIGNED_IN.value: "Run codex login, then retry.",
    FailureCode.CODEX_USAGE_LIMITED.value: "Wait until the usage window resets, or sign Codex in with an API key.",
    FailureCode.CODEX_MODEL_UNKNOWN.value: "Pick a model from list_codex_models.",
    FailureCode.CODEX_SESSION_NOT_FOUND.value: "Find the thread with list_codex_threads, or use a handle this host returned; continue a finished turn instead of steering it.",
    FailureCode.CODEX_SESSION_BUSY.value: "Steer or wait on the running turn, or fork the thread.",
    FailureCode.CODEX_BUDGET_EXHAUSTED.value: "Raise max_output_tokens or the goal token_budget, or split the work.",
    FailureCode.CODEX_API_ERROR.value: "Retry with backoff, and check the service status if it persists.",
    FailureCode.CODEX_PERMISSION_DENIED.value: "Allow the action (approval_policy, approvals_reviewer or sandbox), or ask for work that does not need it.",
    FailureCode.CODEX_SANDBOX_NOT_READY.value: "Set up the Codex Windows sandbox, or run with sandbox=FULL_ACCESS.",
    FailureCode.CODEX_SCHEMA_VIOLATION.value: "Continue the thread and ask for output that matches the schema; the raw text is in result.final_response.",
    FailureCode.CODEX_PROCESS_EXITED.value: "Open a new CodexHost and continue the thread by id.",
    FailureCode.CODEX_PROTOCOL_MISMATCH.value: "Match the Codex CLI and openai-codex versions (codex update), then open a new CodexHost.",
    FailureCode.CODEX_TURN_TIMED_OUT.value: "Raise timeout_seconds, or continue the thread to finish the work.",
    FailureCode.CODEX_FORK_FAILED.value: "Fork from a completed turn.",
    FailureCode.CODEX_RESPONSE_INVALID.value: "Continue the thread and ask for a final answer.",
    FailureCode.CONFIGURATION_INVALID_ARGUMENT.value: "Fix the argument or setup named in the message, then call again.",
    FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION.value: CODEX_HOST_USER_REVIEWER_TEXT,
}
# The router's answer to a tool call on a thread with no Vidbyte tools.
CODEX_UNREGISTERED_TOOL_TEXT = "No Vidbyte tool is registered for this thread on this host."
# App-server methods the host calls through openai-codex's typed
# client methods, named in its mapped errors (D-13); thread/start is
# CODEX_THREAD_START_METHOD above.
CODEX_INITIALIZE_METHOD = "initialize"
CODEX_ACCOUNT_READ_METHOD = "account/read"
CODEX_THREAD_RESUME_METHOD = "thread/resume"
CODEX_THREAD_FORK_METHOD = "thread/fork"
CODEX_THREAD_NAME_SET_METHOD = "thread/name/set"
CODEX_THREAD_LIST_METHOD = "thread/list"
CODEX_THREAD_READ_METHOD = "thread/read"
CODEX_TURN_START_METHOD = "turn/start"
CODEX_TURN_STEER_METHOD = "turn/steer"
CODEX_TURN_INTERRUPT_METHOD = "turn/interrupt"
# openai-codex's own goal cancel call, named in its mapped errors.
CODEX_GOAL_CANCEL_CALL = "cancel_goal_operation"


__all__ = [
    "CODEX_MAX_CONCURRENT_TURNS",
    "CODEX_PRIMARY_CHAIN_INDEX",
    "CODEX_FIRST_ATTEMPT",
    "CODEX_MAX_TURN_FAILURES",
    "CODEX_FALLBACK_ATTEMPTS_KEY",
    "CODEX_FAILURE_SOURCE",
    "CODEX_FAILURE_CLASSIFICATION",
    "CODEX_FAILURES_KEY",
    "CODEX_ANSWERING_MODEL_KEY",
    "CODEX_UNSUPPORTED_LOOP_FIELDS",
    "CODEX_UNOBSERVABLE_COUNTER_KEYS",
    "CODEX_TOOL_ITEM_TYPES",
    "CODEX_MILLISECONDS_PER_SECOND",
    "CODEX_ITEM_COMPLETED_STATUS",
    "CODEX_CONTRACTS_KEY",
    "CODEX_COMPACTION_ITEM_TYPE",
    "CODEX_COMMAND_SUCCESS_EXIT_CODE",
    "CODEX_NEXT_FORK_DEPTH",
    "CODEX_MIDDLEWARE_METADATA_KEY",
    "CODEX_PROVIDER_NAME",
    "CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS",
    "CODEX_RESERVED_SUBAGENT_NAMES",
    "CODEX_ROOT_FORK_DEPTH",
    "CODEX_SDK_EXTRA",
    "CODEX_SUBAGENT_ITEM_TYPES",
    "CODEX_SUPPORTED_ITEM_TYPES",
    "CODEX_USAGE_PROVIDER",
    "CODEX_USAGE_ROLLUP_KEY",
    "CODEX_ZERO_DURATION_MS",
    "CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH",
    "CODEX_DYNAMIC_TOOL_NAME_PATTERN",
    "CODEX_DYNAMIC_TOOLS_PARAM",
    "CODEX_RESERVED_DYNAMIC_TOOL_NAME",
    "CODEX_RESERVED_DYNAMIC_TOOL_PREFIX",
    "CODEX_THREAD_START_METHOD",
    "CODEX_TOOL_CALL_METHOD",
    "CODEX_TOOL_CALL_TIMEOUT_SECONDS",
    "CODEX_HOST_REQUEST_TIMEOUT_SECONDS",
    "CODEX_HOST_TOOL_MAX_WAIT_SECONDS",
    "CODEX_HOST_WORKER_THREADS",
    "CODEX_HOST_CLOSE_INTERRUPT_SECONDS",
    "CODEX_HOST_CLOSE_WAIT_SECONDS",
    "CODEX_HOST_EXPERIMENTAL_API_TEXT",
    "CODEX_HOST_USER_REVIEWER_TEXT",
    "CODEX_HOST_MINIMUM_VERSION",
    "CODEX_HOST_BINARY_NAME",
    "CODEX_HOST_SINGLE_ATTEMPT",
    "CODEX_HOST_MIN_LIVE_TURNS",
    "CODEX_HOST_MIN_TOKEN_LIMIT",
    "CODEX_HOST_MIN_EXCLUSIVE_SECONDS",
    "CODEX_HOST_DEFAULT_APPROVAL_MODE",
    "CODEX_RATE_LIMITS_READ_METHOD",
    "CODEX_SANDBOX_READINESS_METHOD",
    "CODEX_REVIEW_START_METHOD",
    "CODEX_GOAL_SET_METHOD",
    "CODEX_MODEL_LIST_METHOD",
    "CODEX_TURN_STARTED_NOTIFICATION",
    "CODEX_TURN_COMPLETED_NOTIFICATION",
    "CODEX_ITEM_COMPLETED_NOTIFICATION",
    "CODEX_USAGE_UPDATED_NOTIFICATION",
    "CODEX_GOAL_UPDATED_NOTIFICATION",
    "CODEX_GOAL_CLEARED_NOTIFICATION",
    "CODEX_APPROVAL_MODE_WIRE",
    "CODEX_SANDBOX_THREAD_MODE",
    "CODEX_SANDBOX_TURN_POLICY",
    "CODEX_ACCEPTED_APPROVAL_METHODS",
    "CODEX_APPROVAL_ACCEPT_DECISION",
    "CODEX_ERROR_INFO_CODES",
    "CODEX_GOAL_TERMINAL_STATUSES",
    "CODEX_NEXT_STEPS",
    "CODEX_UNREGISTERED_TOOL_TEXT",
    "CODEX_INITIALIZE_METHOD",
    "CODEX_ACCOUNT_READ_METHOD",
    "CODEX_THREAD_RESUME_METHOD",
    "CODEX_THREAD_FORK_METHOD",
    "CODEX_THREAD_NAME_SET_METHOD",
    "CODEX_THREAD_LIST_METHOD",
    "CODEX_THREAD_READ_METHOD",
    "CODEX_TURN_START_METHOD",
    "CODEX_TURN_STEER_METHOD",
    "CODEX_TURN_INTERRUPT_METHOD",
    "CODEX_GOAL_CANCEL_CALL",
]
