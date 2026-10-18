"""FILE: vidbyte/lib/constants/codex_host.py

PURPOSE: Defines every fixed value CodexHost and its collaborators use: the wire tables, field rules and bounds the host modules read, the summary sentence of each failure they report, and the per-code likely cause, related docs and relevant tests that make each CodexAgentError a full diagnostic packet. The hardening slice adds the fail-closed answer of each server request a host gets without an approval_handler, the typed reads retried on overload and the codes CodexAgentError.retryable reports, the goal-run field rule, the fork fields that need the experimental API, the lost-turn grace, the longest value a log record shows, and the texts of its new refusals. The first-class-features slice adds the fifteen method names of its new calls, the unmodeled raw methods and the goal start calls, the stream notification table and its per-turn and per-host bounds, the goal status sets of resume and of the load guard, the wait, inject and memory bounds, the side-chat texts, the worktree values, and every message, likely cause and next step of its refusals.
ROLE IN CODEBASE: The constants layer under vidbyte/harnesses/native/codex/ and vidbyte/lib/dataclasses/codex_host_inputs.py; those modules define no module-level values of their own and read every one from here or from vidbyte/lib/constants/codex.py.
ARCHITECTURE NOTE: Imports only lib enums and the shared Codex constants, so importing it never loads openai-codex: CODEX_HOST_RAW_RESPONSE_MODELS names each generated response model as text, and CodexConnection resolves the class from openai_codex.generated.v2_all when it sends the call. CODEX_NEXT_STEPS stays in codex.py, where the records and tools already read it; CODEX_HOST_LIKELY_CAUSES has exactly the same keys.
COMMON MODIFICATION PATTERNS: A new CodexHost failure adds its summary sentence here; a new failure code adds one row to CODEX_HOST_LIKELY_CAUSES and one to CODEX_NEXT_STEPS. A new raw app-server call adds its model name to CODEX_HOST_RAW_RESPONSE_MODELS, or its method to CODEX_HOST_UNMODELED_RAW_METHODS when openai-codex has no response model for it, and to CODEX_HOST_SPENDING_RAW_METHODS when it spends usage.
KNOWN EDGE CASES: Templates whose text is appended to another message start with a space. A summary never quotes an exception's own text, stderr, env values or the account email; Codex's JSON-RPC message, a method name, a code and a type name are the only variable parts (codex-host INV-9). The one exception is CODEX_HOST_WORKTREE_FAILED_MESSAGE, which shows git's exit code and first stderr line, cut to CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS, as first-class INV-29 and EC-34 require; the worktree-root message names only the exception's type (EC-63). CODEX_HOST_SERVER_REQUEST_DEFAULT_ANSWERS is shared, so the translator hands out a copy of each answer, never the table's own object. The four stream bounds and CODEX_HOST_GOAL_RESUME_START_SECONDS and CODEX_HOST_WORKTREE_TIMEOUT_SECONDS are imported by name into the host modules that read them, so a test patches them there. The fifteen first-class method names live here, never in vidbyte/lib/constants/codex.py, whose export list is pinned.
RELATED DOCS: vidbyte/harnesses/README.md; docs/spec/codex-host/spec.md (sections 9.2 and 9.3); docs/spec/codex-host-thread-helpers/spec.md (section 9.3); docs/spec/codex-host-hardening/spec.md (sections 9.2 and 9.3); docs/spec/codex-host-first-class/spec.md (sections 9.2 and 9.3)
TESTS: tests/features/codex_host/test_codex_host_error_details.py, tests/features/codex_host/test_codex_host_inputs.py, tests/features/codex_host/test_codex_host_hardening_contract.py, tests/features/codex_host/test_codex_host_feature_constants.py
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from vidbyte.lib.constants.codex import (
    CODEX_ACCOUNT_READ_METHOD,
    CODEX_GOAL_GET_METHOD,
    CODEX_GOAL_SET_METHOD,
    CODEX_HOST_MINIMUM_VERSION,
    CODEX_MODEL_LIST_METHOD,
    CODEX_RATE_LIMITS_READ_METHOD,
    CODEX_REVIEW_START_METHOD,
    CODEX_SANDBOX_READINESS_METHOD,
    CODEX_SKILLS_LIST_METHOD,
    CODEX_THREAD_DELETE_METHOD,
    CODEX_THREAD_LIST_METHOD,
    CODEX_THREAD_NAME_SET_METHOD,
    CODEX_THREAD_READ_METHOD,
    CODEX_THREAD_TURNS_LIST_METHOD,
)
from vidbyte.lib.enums.codex import (
    CodexApprovalDecision,
    CodexGoalStatus,
    CodexHostOperation,
    CodexSandboxReadiness,
    CodexServerRequestKind,
    CodexTurnEventKind,
)
from vidbyte.lib.enums.failure import FailureCode

# The first-class features: the app-server method of each new call,
# named like the shared CODEX_GOAL_SET_METHOD (first-class section 9.3,
# D-28).
CODEX_THREAD_SETTINGS_UPDATE_METHOD = "thread/settings/update"
CODEX_TURN_SETTINGS_UPDATE_METHOD = "turn/settings/update"
CODEX_COLLABORATION_MODE_LIST_METHOD = "collaborationMode/list"
CODEX_MCP_SERVER_STATUS_LIST_METHOD = "mcpServerStatus/list"
CODEX_THREAD_MEMORY_MODE_SET_METHOD = "thread/memoryMode/set"
CODEX_MEMORY_STATUS_METHOD = "memory/status"
CODEX_MEMORY_RESET_METHOD = "memory/reset"
CODEX_THREAD_INJECT_ITEMS_METHOD = "thread/inject_items"
CODEX_THREAD_ARCHIVE_METHOD = "thread/archive"
CODEX_THREAD_UNARCHIVE_METHOD = "thread/unarchive"
CODEX_THREAD_REVERT_METHOD = "thread/revert"
CODEX_GOAL_CLEAR_METHOD = "thread/goal/clear"
CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD = "thread/backgroundTerminals/list"
CODEX_THREAD_BACKGROUND_TERMINALS_CLEAN_METHOD = "thread/backgroundTerminals/clean"
CODEX_THREAD_SEARCH_METHOD = "thread/search"

# The connection: the generated response model of each call sent
# through the raw path, by its class name in openai-codex's
# generated.v2_all module (codex-host section 12.4, thread-helpers
# section 9.2).
CODEX_HOST_RAW_RESPONSE_MODELS: Mapping[str, str] = {
    CODEX_RATE_LIMITS_READ_METHOD: "GetAccountRateLimitsResponse",
    CODEX_SANDBOX_READINESS_METHOD: "WindowsSandboxReadinessResponse",
    CODEX_MODEL_LIST_METHOD: "ModelListResponse",
    CODEX_REVIEW_START_METHOD: "ReviewStartResponse",
    CODEX_GOAL_SET_METHOD: "ThreadGoalSetResponse",
    CODEX_THREAD_DELETE_METHOD: "ThreadDeleteResponse",
    CODEX_GOAL_GET_METHOD: "ThreadGoalGetResponse",
    CODEX_SKILLS_LIST_METHOD: "SkillsListResponse",
    CODEX_THREAD_TURNS_LIST_METHOD: "ThreadTurnsListResponse",
    CODEX_MCP_SERVER_STATUS_LIST_METHOD: "ListMcpServerStatusResponse",
    CODEX_THREAD_INJECT_ITEMS_METHOD: "ThreadInjectItemsResponse",
    CODEX_THREAD_REVERT_METHOD: "ThreadRevertResponse",
    CODEX_GOAL_CLEAR_METHOD: "ThreadGoalClearResponse",
}
# The raw calls openai-codex has no response model for: each answer is
# carried as a read-only mapping and read by the call's own translator,
# inside the call (first-class D-3, INV-6).
CODEX_HOST_UNMODELED_RAW_METHODS = frozenset(
    {
        CODEX_THREAD_SETTINGS_UPDATE_METHOD,
        CODEX_TURN_SETTINGS_UPDATE_METHOD,
        CODEX_COLLABORATION_MODE_LIST_METHOD,
        CODEX_THREAD_MEMORY_MODE_SET_METHOD,
        CODEX_MEMORY_STATUS_METHOD,
        CODEX_MEMORY_RESET_METHOD,
        CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD,
        CODEX_THREAD_BACKGROUND_TERMINALS_CLEAN_METHOD,
        CODEX_THREAD_SEARCH_METHOD,
    }
)
# Raw calls that spend usage, so each is sent once and never retried
# (D-2).
CODEX_HOST_SPENDING_RAW_METHODS = frozenset({CODEX_REVIEW_START_METHOD, CODEX_GOAL_SET_METHOD})
# The typed calls that get openai-codex's overload retries: idempotent
# reads, plus a name set that ends the same however often it lands
# (hardening D-7, A-3). Every other typed call is sent once.
CODEX_HOST_RETRIED_METHODS = frozenset({CODEX_ACCOUNT_READ_METHOD, CODEX_THREAD_READ_METHOD, CODEX_THREAD_LIST_METHOD, CODEX_THREAD_NAME_SET_METHOD})
# The codes whose same call, unchanged, can succeed on the same host
# once the condition clears; CodexAgentError.retryable reads them
# (hardening D-6). fork_failed, process_exited and turn_timed_out stay
# out on purpose.
CODEX_HOST_RETRYABLE_CODES = frozenset(
    {
        FailureCode.CODEX_API_ERROR.value,
        FailureCode.CODEX_SESSION_BUSY.value,
        FailureCode.CODEX_USAGE_LIMITED.value,
        FailureCode.CODEX_THREAD_RESUME_FAILED.value,
        FailureCode.CODEX_RESPONSE_INVALID.value,
    }
)
# The server router: the fixed, fail-closed answer of each server
# request a host answers without its approval_handler. Approvals are
# declined, questions get no answers, permissions grant nothing and
# elicitations are declined; a method not listed gets an empty answer
# (hardening D-3, INV-15).
CODEX_HOST_SERVER_REQUEST_DEFAULT_ANSWERS: Mapping[str, Mapping[str, Any]] = {
    CodexServerRequestKind.COMMAND_EXECUTION.value: {"decision": CodexApprovalDecision.DECLINE.value},
    CodexServerRequestKind.FILE_CHANGE.value: {"decision": CodexApprovalDecision.DECLINE.value},
    CodexServerRequestKind.USER_INPUT.value: {"answers": {}},
    "item/permissions/requestApproval": {"permissions": {}},
    "mcpServer/elicitation/request": {"action": "decline"},
    "applyPatchApproval": {"decision": "denied"},
    "execCommandApproval": {"decision": "denied"},
}
# The server request that asks the client for the current time, which
# is answered in whole Unix seconds (hardening section 9.3).
CODEX_CURRENT_TIME_READ_METHOD = "currentTime/read"
# How a failed process start is named in the messages the mapper builds.
CODEX_HOST_PROCESS_START = "the app-server start"
# openai-codex's goal start call; a plain CodexError from it means its
# start window elapsed (D-13).
CODEX_GOAL_START_CALL = "start_goal_operation"
# The goal resume start's call name; its window maps like the goal
# start's (first-class INV-31, D-17).
CODEX_GOAL_RESUME_CALL = "resume_goal_operation"
# The goal start calls whose elapsed start window, a plain CodexError,
# maps to codex.api_error.
CODEX_HOST_GOAL_START_CALLS = frozenset({CODEX_GOAL_START_CALL, CODEX_GOAL_RESUME_CALL})

# Preflight: the only platform with a sandbox readiness check (D-28).
CODEX_HOST_SANDBOX_PLATFORM = "win32"
# The CodexSpawnRequest fields each operation refuses when they differ
# from a default request, because it would drop them unapplied
# (INV-27).
CODEX_HOST_REJECTED_FIELDS: Mapping[CodexHostOperation, tuple[str, ...]] = {
    CodexHostOperation.CONTINUE_CODEX_THREAD: (
        "prompt",
        "goal",
        "thread.ephemeral",
        "thread.thread_source",
        "thread.service_name",
        "thread.session_start_source",
        "tools",
        "name",
    ),
    CodexHostOperation.FORK_CODEX_THREAD: (
        "prompt",
        "goal",
        "thread.personality",
        "thread.service_name",
        "thread.session_start_source",
        "turn",
        "tools",
        "disabled_plugin_ids",
        "output_schema",
        "max_output_tokens",
        "timeout_seconds",
        "turn_service_tier",
        "network_access",
        "writable_roots",
        "collaboration_mode",
    ),
    CodexHostOperation.LAUNCH_CODEX_SUBAGENTS: ("prompt", "goal"),
    # A review runs Codex's own review turn, so only Vidbyte's two caps
    # apply to it (hardening INV-30).
    CodexHostOperation.START_CODEX_REVIEW: (
        "prompt",
        "thread",
        "turn",
        "subagents",
        "developer_instructions",
        "approval_policy",
        "approvals_reviewer",
        "tools",
        "tool_permission_policy",
        "disabled_plugin_ids",
        "output_schema",
        "goal",
        "name",
        "turn_service_tier",
        "network_access",
        "writable_roots",
        "collaboration_mode",
    ),
    # A plan run takes its prompt as an argument and its mode from
    # Codex's plan preset (first-class INV-16).
    CodexHostOperation.RUN_CODEX_PLAN: ("prompt", "goal", "collaboration_mode"),
    # A side chat is always an ephemeral fork with the parent's tools,
    # so these fields could not apply (first-class INV-27).
    CodexHostOperation.START_CODEX_SIDE_CHAT: (
        "prompt",
        "goal",
        "name",
        "tools",
        "thread.ephemeral",
        "thread.personality",
        "thread.service_name",
        "thread.session_start_source",
    ),
    # A goal resume continues the stored thread, so it refuses what
    # continue_codex_thread refuses (first-class INV-31).
    CodexHostOperation.RESUME_CODEX_GOAL: (
        "prompt",
        "goal",
        "thread.ephemeral",
        "thread.thread_source",
        "thread.service_name",
        "thread.session_start_source",
        "tools",
        "name",
    ),
}
# The spawn-request fields a goal run refuses, because Codex starts goal
# turns itself with the thread's settings and would ignore them; the
# first one set is named (hardening D-15, INV-34).
CODEX_HOST_GOAL_REJECTED_FIELDS = ("turn", "output_schema", "disabled_plugin_ids", "turn_service_tier", "network_access", "writable_roots", "collaboration_mode")
# The fork fields Codex takes only from clients that opt in to its
# experimental API; a host without it refuses the first one set, in
# this order (hardening INV-28 step 1, EC-56).
CODEX_HOST_FORK_EXPERIMENTAL_FIELDS = ("before_turn_id", "defer_goal_continuation")
# The service tier every model accepts, so it is never checked against
# the listed tiers (hardening D-16).
CODEX_DEFAULT_SERVICE_TIER = "default"

# The turn registry: the token counters a usage delta subtracts, named
# as on CodexUsage.
CODEX_HOST_USAGE_COUNTERS = frozenset(
    {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"}
)
# The turn events: how long a turn whose watcher stopped waits before
# its cleanup interrupt, so a process death reaches the liveness
# monitor first (hardening D-9, A-14).
CODEX_HOST_LOST_TURN_GRACE_SECONDS = 0.5
# The logs: the longest id or method a record shows before LogToken.of
# cuts it. A Codex thread id is a 36-character UUID and the longest
# 0.163.0 method has 41 characters, so this leaves room for longer
# turn and item ids while a crafted huge id cannot fill a record
# (hardening INV-10).
CODEX_HOST_LOG_TOKEN_MAX_CHARS = 128

# The thread helpers: the fork scan reads pages of turns without their
# items, and a review read-back reads the one newest turn with every
# item (hardening D-18).
CODEX_TURN_ITEMS_VIEW_NOT_LOADED = "notLoaded"
CODEX_HOST_REVIEW_READ_BACK_LIMIT = 1

# The wire translators: a runtime version is three dot-separated
# numbers, and anything else is unreadable and refused (INV-4, D-5).
CODEX_HOST_VERSION_PATTERN = r"(\d+)\.(\d+)\.(\d+)"
CODEX_HOST_MINIMUM_VERSION_PARTS = tuple(int(part) for part in CODEX_HOST_MINIMUM_VERSION.split("."))
# The two wire approval fields, in the order CODEX_APPROVAL_MODE_WIRE
# lists their values.
CODEX_HOST_APPROVAL_FIELDS = ("approval_policy", "approvals_reviewer")
# The Windows sandbox states that keep turns from running (D-28).
CODEX_HOST_SANDBOX_NOT_READY = frozenset({CodexSandboxReadiness.NOT_CONFIGURED, CodexSandboxReadiness.UPDATE_REQUIRED})

# How every CodexAgentError message is put together, in the order the
# lib error packets use: the operation and code, what happened, the
# thread, the likely cause, then the next step.
CODEX_HOST_MESSAGE_HEAD = "{operation} failed with {code}."
CODEX_HOST_THREAD_SENTENCE = "The thread id was {thread_id}."
CODEX_HOST_LIKELY_CAUSE_SENTENCE = "Likely cause: {likely_cause}"
CODEX_HOST_NEXT_STEP_SENTENCE = "Next step: {next_step}"
CODEX_HOST_SENTENCE_SEPARATOR = " "
# Where a reader of a CodexHost error finds the host's contract, and
# which tests prove the failure.
CODEX_HOST_RELATED_DOCS = (
    "vidbyte/harnesses/README.md",
    "docs/spec/codex-host/spec.md",
    "https://developers.openai.com/codex/app-server",
)
CODEX_HOST_RELEVANT_TESTS = ("tests/features/codex_host",)

# One likely cause per failure code a CodexHost error can carry, written
# for that code; the keys equal CODEX_NEXT_STEPS's.
CODEX_HOST_LIKELY_CAUSES: Mapping[str, str] = {
    FailureCode.CODEX_NOT_INSTALLED.value: "No codex executable was found on PATH under the name CodexHost looked for (codex, or CodexClientSettings.codex_bin), or the file it found could not be started as a process.",
    FailureCode.CODEX_VERSION_UNSUPPORTED.value: "The installed Codex CLI is older than the oldest app-server version CodexHost supports, or it reported a version that is not three dot-separated numbers.",
    FailureCode.CODEX_NOT_SIGNED_IN.value: "The Codex CLI has no signed-in ChatGPT account or API key, and this runtime needs one before it starts any turn.",
    FailureCode.CODEX_USAGE_LIMITED.value: "The account's ordinary usage window is used up, so Codex refuses new paid work until the window resets.",
    FailureCode.CODEX_MODEL_UNKNOWN.value: "The model or service tier named in the thread or turn settings is not in the model list Codex reports for this account, often because of a typo or a model or tier the account cannot use.",
    FailureCode.CODEX_SESSION_NOT_FOUND.value: "The thread id or turn handle names no thread Codex stores and no turn this host is running: it may be mistyped, deleted, from another account or host, or a turn that already ended.",
    FailureCode.CODEX_SESSION_BUSY.value: "A turn is already running, starting or reserved on the thread, on this host or in another Codex client, and a thread runs one turn at a time.",
    FailureCode.CODEX_BUDGET_EXHAUSTED.value: "The turn's own output passed max_output_tokens, or the goal run spent its token_budget, so the work stopped before it finished.",
    FailureCode.CODEX_API_ERROR.value: "Codex or the model service answered with an error, or did not answer within CodexHost's request bound; an overload or a network problem is the usual cause.",
    FailureCode.CODEX_PERMISSION_DENIED.value: "The thread's approval policy, approvals reviewer or sandbox refused an action the turn needed, such as a command or a file change.",
    FailureCode.CODEX_SANDBOX_NOT_READY.value: "The Codex Windows sandbox is not set up or needs an update, so Codex cannot run a sandboxed turn on this machine.",
    FailureCode.CODEX_SCHEMA_VIOLATION.value: "The model's final answer was not JSON that matches the turn's output_schema.",
    FailureCode.CODEX_PROCESS_EXITED.value: "The CodexHost was closed, or the codex app-server process it started exited or crashed, so the call could not reach Codex.",
    FailureCode.CODEX_PROTOCOL_MISMATCH.value: "The installed Codex CLI and the openai-codex Python package speak different versions of the app-server protocol: a method is missing, or an answer did not match its response model.",
    FailureCode.CODEX_TURN_TIMED_OUT.value: "The turn ran longer than its timeout_seconds, so CodexHost interrupted it.",
    FailureCode.CODEX_COMMAND_NOT_RUN.value: "Codex accepted the goal or skill run, but the goal it stored or the input it recorded did not match what was sent, so CodexHost could not confirm that the run took.",
    FailureCode.CODEX_SKILL_NOT_FOUND.value: "No enabled skill with that exact name is listed for the working folder; skill names are case-sensitive, and the skills Codex lists depend on the folder the thread runs in.",
    FailureCode.CODEX_SKILL_DISABLED.value: "A skill with that name is listed for the working folder, but the Codex configuration disables it.",
    FailureCode.CODEX_GOAL_UNFINISHED.value: "The thread is not loaded on this host and still holds an unfinished goal, and loading it to compact or continue could let Codex resume that goal as untracked paid turns.",
    FailureCode.CODEX_FORK_FAILED.value: "The thread has no completed turn at the fork point, or Codex refused the fork point it was sent.",
    FailureCode.CODEX_RESPONSE_INVALID.value: "Codex ended the turn without the final answer or completion event the result needs.",
    FailureCode.CONFIGURATION_INVALID_ARGUMENT.value: "An argument or setting failed its check before anything was sent to Codex.",
    FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION.value: "The thread's approval requests go to a user reviewer, and this CodexHost was built without an approval_handler that could answer them.",
}

# The error mapper: what happened, for each kind of failure it maps.
CODEX_HOST_EXITED_DURING_MESSAGE = "The Codex app-server exited during {method}."
CODEX_HOST_RPC_ERROR_MESSAGE = "Codex answered {method} with JSON-RPC error {code}: '{message}'."
CODEX_HOST_SDK_REFUSED_MESSAGE = "openai-codex could not complete {method}."
CODEX_HOST_MODEL_MISMATCH_MESSAGE = "Codex's answer to {method} did not match the openai-codex response model."
CODEX_HOST_NO_ANSWER_MESSAGE = "Codex did not answer {method} within {seconds:g} seconds."
CODEX_HOST_LOCAL_FAILURE_MESSAGE = "{method} failed with {error_type}."
CODEX_HOST_MISSING_SDK_MESSAGE = "openai-codex is not installed, so CodexHost cannot talk to Codex."
CODEX_HOST_MISSING_SDK_CAUSE = "The openai-codex Python package, which CodexHost imports only when a host opens, is not installed in this Python environment."
CODEX_HOST_MISSING_SDK_NEXT_STEP = 'Install the Python SDK extra: pip install "{extra}".'
CODEX_HOST_NOT_INSTALLED_MESSAGE = "The Codex CLI could not be started from {target}."
CODEX_HOST_VERSION_MESSAGE = "The Codex app-server reports version '{found}', and CodexHost needs {minimum} or newer."
CODEX_HOST_REVIEWER_MESSAGE = "Codex routes this thread's approval requests to a user reviewer, and this CodexHost has no approval_handler to answer them."
CODEX_HOST_PROCESS_EXITED_MESSAGE = "CodexHost is closed or its Codex app-server exited."
CODEX_HOST_GOAL_STOPPED_MESSAGE = "Codex stopped the goal run with status {status}."
CODEX_HOST_TURN_FAILED_MESSAGE = "Codex failed the turn: {message}"
CODEX_HOST_TURN_FAILED_SILENTLY_MESSAGE = "Codex failed the turn without an error."
# The turn events: why the host itself stopped a turn whose events it
# could not process, or stopped receiving (hardening INV-11, INV-13).
CODEX_HOST_EVENT_FAILED_MESSAGE = "CodexHost could not process one of the turn's events, so it stopped the turn."
CODEX_HOST_LOST_EVENTS_MESSAGE = "CodexHost stopped receiving the turn's events before it ended, so it stopped the turn."
# The problem of each stop reason Vidbyte itself sends an interrupt for
# (D-7).
CODEX_HOST_STOP_MESSAGES: Mapping[FailureCode, str] = {
    FailureCode.CODEX_TURN_TIMED_OUT: "Vidbyte interrupted the turn because its timeout_seconds elapsed.",
    FailureCode.CODEX_BUDGET_EXHAUSTED: "Vidbyte interrupted the turn because its output tokens passed max_output_tokens.",
}
# The goal statuses that stop a goal run for a limit, as a failure
# (section 9.2).
CODEX_HOST_GOAL_PROBLEM_CODES: Mapping[CodexGoalStatus, FailureCode] = {
    CodexGoalStatus.BUDGET_LIMITED: FailureCode.CODEX_BUDGET_EXHAUSTED,
    CodexGoalStatus.USAGE_LIMITED: FailureCode.CODEX_USAGE_LIMITED,
}

# The host: refusals of a host that cannot take the call. Each says what
# is wrong, why the host needs it, and what to do instead.
CODEX_HOST_NOT_OPEN_MESSAGE = "{operation} needs an open CodexHost, and this host is not open: it was never entered, or its async with block already ended. A CodexHost runs its codex app-server only inside 'async with CodexHost(...) as host:', so call {operation} inside that block, or open a new CodexHost."
CODEX_HOST_REOPEN_MESSAGE = "This CodexHost was already entered once, and a host opens only once, because closing it stops its codex app-server for good. Create a new CodexHost(...) and enter that one instead."
CODEX_HOST_OTHER_LOOP_MESSAGE = "{operation} was called from another asyncio event loop than the one that opened this CodexHost. The host's turns, watchers and futures belong to that loop, so call {operation} from it, or open a separate CodexHost on this loop."
CODEX_HOST_UNKNOWN_HANDLE_MESSAGE = "This host registered no turn {turn_id} on thread {thread_id}; a turn handle works only on the CodexHost that returned it, while that host stays open."
CODEX_HOST_STEER_FINISHED_MESSAGE = "Turn {turn_id} already ended, so it cannot be steered; new input can only join a turn that is still running."
CODEX_HOST_STEER_STOPPING_MESSAGE = "Turn {turn_id} is being interrupted, so it cannot be steered; wait for it to end with wait_codex_turn, then add the input with continue_codex_thread."
CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE = "fork_codex_thread {field} needs CodexClientSettings(experimental_api=True), because Codex accepts it only from clients that opt in to its experimental API."
CODEX_HOST_NEVER_RAN_MESSAGE = "This host never saw a turn end on the thread, so it has no usage to report; usage covers only the turns this CodexHost started and watched to their end."
CODEX_HOST_NO_FORK_POINT_MESSAGE = "The thread has no completed turn to fork through at {point}."
CODEX_HOST_LATEST_FORK_POINT = "its latest turn"
CODEX_HOST_NAMED_FORK_POINT = "turn {turn_id}"
CODEX_HOST_BUDGET_ECHO_MESSAGE = "Codex did not keep the goal token budget it was sent: it reported {stored} after {sent} was set."
CODEX_HOST_LAUNCH_INTERRUPTED_SENTENCE = " {count} turns were started before this failure and were interrupted."

# Preflight: what each failed check found.
CODEX_HOST_USAGE_LIMITED_MESSAGE = "Codex reports that ordinary usage is not allowed right now."
CODEX_HOST_BUSY_MESSAGE = "The thread already has a running turn on this host."
CODEX_HOST_MODEL_UNKNOWN_MESSAGE = "Codex lists no model named {unknown}. Listed models: {visible}."
CODEX_HOST_UNKNOWN_TIER_MESSAGE = "Codex lists no service tier {tier} for {models}. Listed tiers: {tiers}."
# The {models} of the tier refusal when the request names no model.
CODEX_HOST_ANY_MODEL_TEXT = "any model"
CODEX_HOST_USER_REVIEWER_MESSAGE = "approvals_reviewer=USER sends the thread's approval requests to this process, and this CodexHost was built without an approval_handler to answer them."
CODEX_HOST_LIST_SEPARATOR = ", "

# The thread helpers: what a refused compact or delete found.
CODEX_HOST_RUNNING_THREAD_MESSAGE = "Codex reports a running turn on the thread, so it cannot be compacted or deleted until that turn ends."
CODEX_HOST_GOAL_UNFINISHED_MESSAGE = "Codex reports an unfinished goal (status {status}) on the thread, and loading the thread to compact it could let Codex continue that goal."
CODEX_HOST_CONTINUE_GOAL_UNFINISHED_MESSAGE = "Codex reports an unfinished goal (status {status}) on the thread, and loading the thread to continue it could let Codex continue that goal outside the turn this host tracks."

# The goal and skill runs: why a run could not be confirmed, and how a
# skill refusal names the folder and the enabled skills.
CODEX_HOST_SKILL_NOT_FOUND_MESSAGE = "Codex lists no skill named '{skill}' for {place}. Enabled skills: {names}."
CODEX_HOST_SKILL_DISABLED_MESSAGE = "The Codex skill '{skill}' is disabled for {place}."
CODEX_HOST_NO_GOAL_MESSAGE = "Codex reports no goal on the thread after the goal run started."
CODEX_HOST_OBJECTIVE_DIFFERS_MESSAGE = "Codex reports a goal objective different from the one sent."
CODEX_HOST_BUDGET_DIFFERS_MESSAGE = "Codex reports a goal token budget of {stored}, not the {sent} that was sent."
CODEX_HOST_GOAL_UNCHECKED_SENTENCE = " The goal run on thread {thread_id} was interrupted because its goal could not be checked."
CODEX_HOST_INPUT_NOT_RECORDED_MESSAGE = "Codex recorded no input for the turn of skill '{skill}' within {seconds} seconds, so the skill run could not be confirmed."
CODEX_HOST_SKILL_DROPPED_MESSAGE = "Codex recorded the turn's input without the skill '{skill}', so the run did not use the skill."
CODEX_HOST_SKILL_UNCHECKED_SENTENCE = " The skill run on thread {thread_id} was interrupted because its input could not be checked."
CODEX_HOST_FOLDER_PLACE = "the folder {cwd}"
CODEX_HOST_APP_SERVER_PLACE = "the app-server's working folder"
CODEX_HOST_MORE_NAMES_TEXT = " and {count} more"
CODEX_HOST_NO_NAMES_TEXT = "none"
# The wire item key that holds a recorded user message's input.
CODEX_HOST_CONTENT_FIELD = "content"

# The wire translators: problems found in Codex's answers, and the
# refusal of input the wire cannot carry.
CODEX_HOST_SIGNED_OUT_MESSAGE = "Codex has no signed-in account, and this runtime requires one."
CODEX_HOST_NO_FINAL_ANSWER_MESSAGE = "Codex completed the turn without a final answer."
CODEX_HOST_SCHEMA_MESSAGE = "Codex's final answer is not JSON that matches output_schema."
CODEX_HOST_UNUSABLE_SCHEMA_MESSAGE = "output_schema must be a Pydantic model type or a mapping that serializes to JSON, because Codex is sent the schema as JSON with the turn. Got {error_type} while serializing it; nothing was sent to Codex."
CODEX_HOST_NO_GOAL_MODE_MESSAGE = "The Codex runtime completed a goal turn without activating goal mode."
CODEX_HOST_NO_COMPLETION_MESSAGE = "Codex ended the turn without reporting its completion."
CODEX_HOST_EXITED_MESSAGE = "CodexHost closed, or its Codex app-server exited, while the turn was running."
CODEX_HOST_PROMPT_CONTEXT_MESSAGE = "A Codex prompt must be a str or a CodexRunInput without context_items, a context_manager or context_placements, because only the input items are sent to Codex and context would be dropped silently."

# The input records: refusals that name the function the caller called,
# because one record serves several functions.
CODEX_HOST_UNUSED_FIELD_MESSAGE = "{operation} does not use the CodexSpawnRequest field {name}; leave it at its default, because {operation} would otherwise drop the value without applying it."
CODEX_HOST_LAUNCH_PROMPTS_MESSAGE = "launch_codex_subagents needs a non-empty sequence of prompts, one per new thread, not one string; got {received}."
CODEX_HOST_LAUNCH_OVER_LIMIT_MESSAGE = "launch_codex_subagents got {count} prompts, over its limit of {limit}; pass at most {limit} prompts, or raise limit."
CODEX_HOST_RUN_INPUT_MESSAGE = "{field} must be a str or a CodexRunInput without context_items, a context_manager or context_placements; got a value of type {kind}."
CODEX_HOST_LIMIT_MESSAGE = "{operation} limit must be an integer from {minimum} to {maximum}."
CODEX_HOST_SINCE_MESSAGE = "{operation} since must be a non-negative integer number of Unix seconds."
CODEX_HOST_QUERY_MESSAGE = "{operation} query must be a non-empty string."
CODEX_HOST_UNUSED_ARGUMENT_MESSAGE = "{operation} does not take {field}; it is used only by {owner}."
CODEX_HOST_LISTING_OPERATION_MESSAGE = "CodexThreadListing.operation must be list_recent_codex_threads, list_codex_threads_since or search_codex_threads; got {operation}."
CODEX_HOST_OWN_INPUT_MESSAGE = "{operation} takes its input as arguments; leave request.prompt and request.goal at their defaults."
CODEX_HOST_EPHEMERAL_SKILL_MESSAGE = "{operation} needs a stored thread to confirm the skill run, so request.thread.ephemeral must be False."
CODEX_HOST_SKILL_NAME_MESSAGE = "{operation} skill must be a non-empty string."
CODEX_HOST_SKILL_OPERATION_MESSAGE = "CodexSkillRunRequest.operation must be run_codex_skill or run_codex_openai_docs; got {operation}."
CODEX_HOST_APPROVAL_HANDLER_MESSAGE = "CodexHost approval_handler must be None or an async function that takes a CodexServerRequest and returns a CodexServerAnswer, and it got a value of type {kind}."
CODEX_HOST_FORK_POINTS_MESSAGE = "fork_codex_thread before_turn_id cannot be combined with from_turn_id; pass from_turn_id to fork through a completed turn, or before_turn_id to fork just before a turn."
# The spawn request: refusals of the goal rule and of the turn sandbox
# fields (hardening INV-34, INV-37).
CODEX_HOST_GOAL_FIELD_MESSAGE = "{owner} does not use the field {name}, because Codex starts goal turns itself with the thread's settings; leave {name} at its default, or set the matching thread setting."
CODEX_HOST_NETWORK_ACCESS_MESSAGE = "Codex spawn request network_access needs turn.sandbox READ_ONLY or WORKSPACE_WRITE, because only those sandbox policies take it, and it got turn.sandbox {sandbox}."
CODEX_HOST_WRITABLE_ROOTS_MESSAGE = "Codex spawn request writable_roots must be a tuple of non-empty absolute paths, and it needs turn.sandbox WORKSPACE_WRITE."

# The turn stream: which per-turn notifications become stream events.
# Raw reasoning text is never streamed, only its public summary
# (first-class INV-18, D-12).
CODEX_HOST_STREAM_NOTIFICATION_KINDS: Mapping[str, CodexTurnEventKind] = MappingProxyType(
    {
        "item/started": CodexTurnEventKind.ITEM_STARTED,
        "item/completed": CodexTurnEventKind.ITEM_COMPLETED,
        "item/agentMessage/delta": CodexTurnEventKind.MESSAGE_DELTA,
        "item/reasoning/summaryTextDelta": CodexTurnEventKind.REASONING_SUMMARY_DELTA,
        "item/plan/delta": CodexTurnEventKind.PLAN_DELTA,
        "item/commandExecution/outputDelta": CodexTurnEventKind.COMMAND_OUTPUT_DELTA,
        "item/fileChange/outputDelta": CodexTurnEventKind.FILE_CHANGE_DELTA,
        "turn/plan/updated": CodexTurnEventKind.PLAN_UPDATED,
        "turn/diff/updated": CodexTurnEventKind.DIFF_UPDATED,
        "thread/tokenUsage/updated": CodexTurnEventKind.USAGE_UPDATED,
    }
)
# The stream window: events and characters kept per live turn, and
# across all of one host's turns, 16 full windows (first-class INV-20,
# D-39). The host modules import them by name and read them at call
# time.
CODEX_HOST_STREAM_EVENT_LIMIT = 4096
CODEX_HOST_STREAM_TEXT_LIMIT_CHARS = 2_000_000
CODEX_HOST_STREAM_HOST_EVENT_LIMIT = 65_536
CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS = 32_000_000
# The most handles one wait_codex_turns call and the most items one
# inject_codex_items call take (first-class section 9.3).
CODEX_HOST_WAIT_MAX_HANDLES = 1024
CODEX_HOST_INJECT_MAX_ITEMS = 1024
# The schema's range for memory/status minConsolidatedThreads.
CODEX_HOST_MEMORY_MIN_CONSOLIDATED_THREADS = 1
CODEX_HOST_MEMORY_MAX_CONSOLIDATED_THREADS = 4096

# The goal controls: the goals resume_codex_goal continues, the goal
# statuses with which a not-loaded thread is loaded (an allow-list, so a
# status Codex adds later fails closed), the resume start window, and
# the origin every goal set and clear sends (first-class INV-12, INV-30,
# INV-31, D-14, D-16, D-38).
CODEX_HOST_GOAL_RESUME_FROM_STATUSES = frozenset(
    {CodexGoalStatus.PAUSED, CodexGoalStatus.BLOCKED, CodexGoalStatus.USAGE_LIMITED, CodexGoalStatus.BUDGET_LIMITED}
)
CODEX_HOST_LOAD_SAFE_GOAL_STATUSES = frozenset(
    {
        CodexGoalStatus.PAUSED,
        CodexGoalStatus.BLOCKED,
        CodexGoalStatus.USAGE_LIMITED,
        CodexGoalStatus.BUDGET_LIMITED,
        CodexGoalStatus.COMPLETE,
    }
)
CODEX_HOST_GOAL_RESUME_START_SECONDS = 30.0
CODEX_HOST_GOAL_MUTATION_ORIGIN = "user"

# The side chat: Vidbyte's own developer instructions for the fork and
# the user message injected where the side chat starts (first-class
# D-18).
CODEX_HOST_SIDE_CHAT_INSTRUCTIONS = "This thread is a side conversation forked from another thread so the user can ask a quick question without changing the main work. Answer the side question using the inherited history as background only. Do not continue, finish or change the main task, and do not edit files unless the user explicitly asks for that in this side conversation."
CODEX_HOST_SIDE_CHAT_BOUNDARY = "The side conversation starts here. Everything above is history from the main thread, given as background; the messages below belong only to this side conversation."

# The worktree: the root under Path.home(), git's time and output
# bounds, the longest stderr line a failure shows, and how the folder
# name <repository name>-<branch> is made safe (first-class D-19).
CODEX_HOST_WORKTREE_ROOT_PARTS = (".vidbyte", "codex-worktrees")
CODEX_HOST_WORKTREE_TIMEOUT_SECONDS = 120.0
CODEX_HOST_WORKTREE_MAX_OUTPUT_BYTES = 65536
CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS = 500
CODEX_HOST_WORKTREE_UNSAFE_NAME_PATTERN = r"[^A-Za-z0-9._-]"
CODEX_HOST_WORKTREE_NAME_SEPARATOR = "-"

# The first-class features: local refusals of a setting, mode or input
# the feature cannot send (first-class section 9.2, INV-4, INV-10).
CODEX_HOST_EXPERIMENTAL_FEATURE_MESSAGE = "{operation} needs Codex's experimental API for {feature}, but this CodexHost was opened with experimental_api=False. Open the host with CodexClientSettings(experimental_api=True) to use it."
CODEX_HOST_MODE_KIND_MESSAGE = "collaboration_mode mode must be CodexCollaborationModeKind.PLAN or CodexCollaborationModeKind.DEFAULT."
CODEX_HOST_MODE_CONFLICT_MESSAGE = "{owner} collaboration_mode sets {name} to a different value than {owner} does. Set {name} in one place only, because Codex lets the collaboration mode take precedence."
CODEX_HOST_SETTINGS_MODE_MODEL_MESSAGE = "update_codex_thread_settings collaboration_mode needs a model, so set collaboration_mode.model or model, because Codex requires a model with every collaboration mode."
CODEX_HOST_SETTINGS_EMPTY_MESSAGE = "{operation} was given no setting to change; set at least one field."
CODEX_HOST_TIER_CLEAR_CONFLICT_MESSAGE = "{operation} sets service_tier and clear_service_tier together; set a tier or clear it, not both."
CODEX_HOST_SETTINGS_NETWORK_ACCESS_MESSAGE = "update_codex_thread_settings network_access needs sandbox READ_ONLY or WORKSPACE_WRITE, because only those sandbox policies take it, and it got sandbox {sandbox}."
CODEX_HOST_SETTINGS_WRITABLE_ROOTS_MESSAGE = "update_codex_thread_settings writable_roots must be a tuple of non-empty absolute paths, and it needs sandbox WORKSPACE_WRITE."
CODEX_HOST_WAIT_HANDLES_MESSAGE = "wait_codex_turns handles must hold between 1 and {maximum} distinct CodexTurnHandle values."
CODEX_HOST_INJECT_ITEMS_MESSAGE = "inject_codex_items items must hold between 1 and {maximum} JSON objects, each with a non-empty string type."
CODEX_HOST_GOAL_EDIT_EMPTY_MESSAGE = "edit_codex_goal was given nothing to change; set objective, token_budget or clear_token_budget."
CODEX_HOST_BUDGET_CLEAR_CONFLICT_MESSAGE = "edit_codex_goal sets token_budget and clear_token_budget together; set a budget or clear it, not both."
CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE = "create_codex_worktree repository must be the absolute path of an existing folder."
CODEX_HOST_WORKTREE_REF_MESSAGE = "create_codex_worktree {field} must be a git branch or ref name of 1 to {maximum} characters that starts with a letter or digit and uses only letters, digits, '.', '_', '-' and '/', without '..', '//' or a trailing '.', '/' or '.lock'."
# The first-class features: refusals after a read of Codex's state, each
# with its own likely cause and next step where the code's default would
# mislead (first-class D-23).
CODEX_HOST_NO_PLAN_MODE_MESSAGE = "Codex listed no collaboration mode preset whose mode is plan, so no plan-mode turn was started."
CODEX_HOST_MODE_MODEL_MISSING_MESSAGE = "Codex reported no model for the thread, and neither the collaboration mode nor the turn names one, so the collaboration mode's required model cannot be sent."
CODEX_HOST_MODE_MODEL_MISSING_CAUSE = "The thread was started without a resolved model, and a collaboration mode must name one."
CODEX_HOST_MODE_MODEL_MISSING_NEXT_STEP = "Set collaboration_mode.model or turn.model, then call again."
CODEX_HOST_TURN_SETTINGS_FINISHED_MESSAGE = "update_codex_turn_settings changes only a running turn this host started, and turn {turn_id} on thread {thread_id} is not running on this host."
CODEX_HOST_NO_STORED_GOAL_MESSAGE = "{operation} needs a goal on the thread, and Codex stores none."
CODEX_HOST_NO_GOAL_CAUSE = "The thread exists, but no goal was ever set on it, or the goal was cleared."
CODEX_HOST_NO_GOAL_NEXT_STEP = "Start a goal with run_codex_goal, or check the thread with get_codex_goal."
CODEX_HOST_GOAL_NOT_RESUMABLE_MESSAGE = "resume_codex_goal resumes only a paused, blocked, usage-limited or budget-limited goal, and this goal is {status}."
CODEX_HOST_GOAL_NOT_RESUMABLE_CAUSE = "Codex stores the goal with a status resume cannot continue."
CODEX_HOST_GOAL_NOT_RESUMABLE_NEXT_STEP = "Read the goal with get_codex_goal. A complete goal is finished, so start a new one with run_codex_goal. An active goal that no client is running, for example after a host stopped, continues with pause_codex_goal and then resume_codex_goal."
CODEX_HOST_GOAL_BUDGET_SPENT_MESSAGE = "resume_codex_goal did not resume the goal, because it has used {used} tokens of its {budget}-token budget."
CODEX_HOST_GOAL_BUDGET_SPENT_CAUSE = "The goal stopped at its token budget, and the budget has not been raised since."
CODEX_HOST_GOAL_BUDGET_SPENT_NEXT_STEP = "Raise the budget with edit_codex_goal(token_budget=...) or remove it with edit_codex_goal(clear_token_budget=True), then call resume_codex_goal again."
CODEX_HOST_THREAD_RUNNING_MESSAGE = "Codex reports a running turn on the thread, so {operation} cannot change it until that turn ends."
CODEX_HOST_LOAD_GOAL_UNFINISHED_MESSAGE = "Codex reports an unfinished goal (status {status}) on the thread, and loading the thread for {operation} could let Codex continue that goal."
CODEX_HOST_LOAD_GOAL_UNFINISHED_CAUSE = "The thread is not loaded in this host's app-server, and loading it for {operation} could let Codex continue its active goal as paid turns this host does not track."
CODEX_HOST_LOAD_GOAL_UNFINISHED_NEXT_STEP = "Pause the goal with pause_codex_goal or clear it with clear_codex_goal, then call again."
# The worktree: refusals before git runs, and git failures. The failed
# message shows only git's exit code and its first stderr line, cut to
# CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS (first-class INV-38).
CODEX_HOST_WORKTREE_EXISTS_MESSAGE = "create_codex_worktree did not run git, because the worktree folder for this repository and branch already exists under the Vidbyte worktree root."
CODEX_HOST_WORKTREE_EXISTS_CAUSE = "A worktree for the same repository folder name and branch was created before."
CODEX_HOST_WORKTREE_EXISTS_NEXT_STEP = "Use the existing worktree, choose another branch name, or remove the old one with git worktree remove."
# The root refusal names only the exception's type, never the home
# path or the exception's text (first-class INV-29, EC-63).
CODEX_HOST_WORKTREE_ROOT_MESSAGE = "create_codex_worktree did not run git, because preparing the worktree root ~/.vidbyte/codex-worktrees raised {error_type}."
CODEX_HOST_WORKTREE_ROOT_CAUSE = "The home folder cannot be found, a file stands where ~/.vidbyte or ~/.vidbyte/codex-worktrees should be a folder, or this process may not read or create folders there."
CODEX_HOST_WORKTREE_ROOT_NEXT_STEP = "Make sure the home folder exists and that ~/.vidbyte/codex-worktrees is a folder this process can write to, moving aside any file in its place, then call again."
CODEX_HOST_WORKTREE_GIT_MISSING_MESSAGE = "create_codex_worktree could not start the git program."
CODEX_HOST_WORKTREE_GIT_MISSING_CAUSE = "git is not installed, is not on PATH, or cannot be run by this process."
CODEX_HOST_WORKTREE_GIT_MISSING_NEXT_STEP = "Install git or put it on PATH, then call again."
CODEX_HOST_WORKTREE_TIMED_OUT_MESSAGE = "git worktree add did not finish within {seconds} seconds, so create_codex_worktree stopped it."
CODEX_HOST_WORKTREE_TIMED_OUT_CAUSE = "A git hook, a credential helper or a slow file system kept git waiting."
CODEX_HOST_WORKTREE_TIMED_OUT_NEXT_STEP = "Run git worktree add in the repository by hand to see what it waits for, remove any half-made worktree folder with git worktree remove, then call again."
CODEX_HOST_WORKTREE_FAILED_MESSAGE = "git worktree add exited with code {exit_code}: {detail}"
CODEX_HOST_WORKTREE_FAILED_CAUSE = "The folder is not inside a git work tree, the branch already exists, or the base ref is unknown."
CODEX_HOST_WORKTREE_FAILED_NEXT_STEP = "Fix the repository, branch or base ref that git names, then call again."


__all__ = [
    "CODEX_COLLABORATION_MODE_LIST_METHOD",
    "CODEX_CURRENT_TIME_READ_METHOD",
    "CODEX_DEFAULT_SERVICE_TIER",
    "CODEX_GOAL_CLEAR_METHOD",
    "CODEX_GOAL_RESUME_CALL",
    "CODEX_GOAL_START_CALL",
    "CODEX_HOST_ANY_MODEL_TEXT",
    "CODEX_HOST_APPROVAL_FIELDS",
    "CODEX_HOST_APPROVAL_HANDLER_MESSAGE",
    "CODEX_HOST_APP_SERVER_PLACE",
    "CODEX_HOST_BUDGET_CLEAR_CONFLICT_MESSAGE",
    "CODEX_HOST_BUDGET_DIFFERS_MESSAGE",
    "CODEX_HOST_BUDGET_ECHO_MESSAGE",
    "CODEX_HOST_BUSY_MESSAGE",
    "CODEX_HOST_CONTENT_FIELD",
    "CODEX_HOST_CONTINUE_GOAL_UNFINISHED_MESSAGE",
    "CODEX_HOST_EPHEMERAL_SKILL_MESSAGE",
    "CODEX_HOST_EVENT_FAILED_MESSAGE",
    "CODEX_HOST_EXITED_DURING_MESSAGE",
    "CODEX_HOST_EXITED_MESSAGE",
    "CODEX_HOST_EXPERIMENTAL_FEATURE_MESSAGE",
    "CODEX_HOST_FOLDER_PLACE",
    "CODEX_HOST_FORK_EXPERIMENTAL_FIELDS",
    "CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE",
    "CODEX_HOST_FORK_POINTS_MESSAGE",
    "CODEX_HOST_GOAL_BUDGET_SPENT_CAUSE",
    "CODEX_HOST_GOAL_BUDGET_SPENT_MESSAGE",
    "CODEX_HOST_GOAL_BUDGET_SPENT_NEXT_STEP",
    "CODEX_HOST_GOAL_EDIT_EMPTY_MESSAGE",
    "CODEX_HOST_GOAL_FIELD_MESSAGE",
    "CODEX_HOST_GOAL_MUTATION_ORIGIN",
    "CODEX_HOST_GOAL_NOT_RESUMABLE_CAUSE",
    "CODEX_HOST_GOAL_NOT_RESUMABLE_MESSAGE",
    "CODEX_HOST_GOAL_NOT_RESUMABLE_NEXT_STEP",
    "CODEX_HOST_GOAL_PROBLEM_CODES",
    "CODEX_HOST_GOAL_REJECTED_FIELDS",
    "CODEX_HOST_GOAL_RESUME_FROM_STATUSES",
    "CODEX_HOST_GOAL_RESUME_START_SECONDS",
    "CODEX_HOST_GOAL_START_CALLS",
    "CODEX_HOST_GOAL_STOPPED_MESSAGE",
    "CODEX_HOST_GOAL_UNCHECKED_SENTENCE",
    "CODEX_HOST_GOAL_UNFINISHED_MESSAGE",
    "CODEX_HOST_INJECT_ITEMS_MESSAGE",
    "CODEX_HOST_INJECT_MAX_ITEMS",
    "CODEX_HOST_INPUT_NOT_RECORDED_MESSAGE",
    "CODEX_HOST_LATEST_FORK_POINT",
    "CODEX_HOST_LAUNCH_INTERRUPTED_SENTENCE",
    "CODEX_HOST_LAUNCH_OVER_LIMIT_MESSAGE",
    "CODEX_HOST_LAUNCH_PROMPTS_MESSAGE",
    "CODEX_HOST_LIKELY_CAUSES",
    "CODEX_HOST_LIKELY_CAUSE_SENTENCE",
    "CODEX_HOST_LIMIT_MESSAGE",
    "CODEX_HOST_LISTING_OPERATION_MESSAGE",
    "CODEX_HOST_LIST_SEPARATOR",
    "CODEX_HOST_LOAD_GOAL_UNFINISHED_CAUSE",
    "CODEX_HOST_LOAD_GOAL_UNFINISHED_MESSAGE",
    "CODEX_HOST_LOAD_GOAL_UNFINISHED_NEXT_STEP",
    "CODEX_HOST_LOAD_SAFE_GOAL_STATUSES",
    "CODEX_HOST_LOCAL_FAILURE_MESSAGE",
    "CODEX_HOST_LOG_TOKEN_MAX_CHARS",
    "CODEX_HOST_LOST_EVENTS_MESSAGE",
    "CODEX_HOST_LOST_TURN_GRACE_SECONDS",
    "CODEX_HOST_MEMORY_MAX_CONSOLIDATED_THREADS",
    "CODEX_HOST_MEMORY_MIN_CONSOLIDATED_THREADS",
    "CODEX_HOST_MESSAGE_HEAD",
    "CODEX_HOST_MINIMUM_VERSION_PARTS",
    "CODEX_HOST_MISSING_SDK_CAUSE",
    "CODEX_HOST_MISSING_SDK_MESSAGE",
    "CODEX_HOST_MISSING_SDK_NEXT_STEP",
    "CODEX_HOST_MODEL_MISMATCH_MESSAGE",
    "CODEX_HOST_MODEL_UNKNOWN_MESSAGE",
    "CODEX_HOST_MODE_CONFLICT_MESSAGE",
    "CODEX_HOST_MODE_KIND_MESSAGE",
    "CODEX_HOST_MODE_MODEL_MISSING_CAUSE",
    "CODEX_HOST_MODE_MODEL_MISSING_MESSAGE",
    "CODEX_HOST_MODE_MODEL_MISSING_NEXT_STEP",
    "CODEX_HOST_MORE_NAMES_TEXT",
    "CODEX_HOST_NAMED_FORK_POINT",
    "CODEX_HOST_NETWORK_ACCESS_MESSAGE",
    "CODEX_HOST_NEVER_RAN_MESSAGE",
    "CODEX_HOST_NEXT_STEP_SENTENCE",
    "CODEX_HOST_NOT_INSTALLED_MESSAGE",
    "CODEX_HOST_NOT_OPEN_MESSAGE",
    "CODEX_HOST_NO_ANSWER_MESSAGE",
    "CODEX_HOST_NO_COMPLETION_MESSAGE",
    "CODEX_HOST_NO_FINAL_ANSWER_MESSAGE",
    "CODEX_HOST_NO_FORK_POINT_MESSAGE",
    "CODEX_HOST_NO_GOAL_CAUSE",
    "CODEX_HOST_NO_GOAL_MESSAGE",
    "CODEX_HOST_NO_GOAL_MODE_MESSAGE",
    "CODEX_HOST_NO_GOAL_NEXT_STEP",
    "CODEX_HOST_NO_NAMES_TEXT",
    "CODEX_HOST_NO_PLAN_MODE_MESSAGE",
    "CODEX_HOST_NO_STORED_GOAL_MESSAGE",
    "CODEX_HOST_OBJECTIVE_DIFFERS_MESSAGE",
    "CODEX_HOST_OTHER_LOOP_MESSAGE",
    "CODEX_HOST_OWN_INPUT_MESSAGE",
    "CODEX_HOST_PROCESS_EXITED_MESSAGE",
    "CODEX_HOST_PROCESS_START",
    "CODEX_HOST_PROMPT_CONTEXT_MESSAGE",
    "CODEX_HOST_QUERY_MESSAGE",
    "CODEX_HOST_RAW_RESPONSE_MODELS",
    "CODEX_HOST_REJECTED_FIELDS",
    "CODEX_HOST_RELATED_DOCS",
    "CODEX_HOST_RELEVANT_TESTS",
    "CODEX_HOST_REOPEN_MESSAGE",
    "CODEX_HOST_RETRIED_METHODS",
    "CODEX_HOST_RETRYABLE_CODES",
    "CODEX_HOST_REVIEWER_MESSAGE",
    "CODEX_HOST_REVIEW_READ_BACK_LIMIT",
    "CODEX_HOST_RPC_ERROR_MESSAGE",
    "CODEX_HOST_RUNNING_THREAD_MESSAGE",
    "CODEX_HOST_RUN_INPUT_MESSAGE",
    "CODEX_HOST_SANDBOX_NOT_READY",
    "CODEX_HOST_SANDBOX_PLATFORM",
    "CODEX_HOST_SCHEMA_MESSAGE",
    "CODEX_HOST_SDK_REFUSED_MESSAGE",
    "CODEX_HOST_SENTENCE_SEPARATOR",
    "CODEX_HOST_SERVER_REQUEST_DEFAULT_ANSWERS",
    "CODEX_HOST_SETTINGS_EMPTY_MESSAGE",
    "CODEX_HOST_SETTINGS_MODE_MODEL_MESSAGE",
    "CODEX_HOST_SETTINGS_NETWORK_ACCESS_MESSAGE",
    "CODEX_HOST_SETTINGS_WRITABLE_ROOTS_MESSAGE",
    "CODEX_HOST_SIDE_CHAT_BOUNDARY",
    "CODEX_HOST_SIDE_CHAT_INSTRUCTIONS",
    "CODEX_HOST_SIGNED_OUT_MESSAGE",
    "CODEX_HOST_SINCE_MESSAGE",
    "CODEX_HOST_SKILL_DISABLED_MESSAGE",
    "CODEX_HOST_SKILL_DROPPED_MESSAGE",
    "CODEX_HOST_SKILL_NAME_MESSAGE",
    "CODEX_HOST_SKILL_NOT_FOUND_MESSAGE",
    "CODEX_HOST_SKILL_OPERATION_MESSAGE",
    "CODEX_HOST_SKILL_UNCHECKED_SENTENCE",
    "CODEX_HOST_SPENDING_RAW_METHODS",
    "CODEX_HOST_STEER_FINISHED_MESSAGE",
    "CODEX_HOST_STEER_STOPPING_MESSAGE",
    "CODEX_HOST_STOP_MESSAGES",
    "CODEX_HOST_STREAM_EVENT_LIMIT",
    "CODEX_HOST_STREAM_HOST_EVENT_LIMIT",
    "CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS",
    "CODEX_HOST_STREAM_NOTIFICATION_KINDS",
    "CODEX_HOST_STREAM_TEXT_LIMIT_CHARS",
    "CODEX_HOST_THREAD_RUNNING_MESSAGE",
    "CODEX_HOST_THREAD_SENTENCE",
    "CODEX_HOST_TIER_CLEAR_CONFLICT_MESSAGE",
    "CODEX_HOST_TURN_FAILED_MESSAGE",
    "CODEX_HOST_TURN_FAILED_SILENTLY_MESSAGE",
    "CODEX_HOST_TURN_SETTINGS_FINISHED_MESSAGE",
    "CODEX_HOST_UNKNOWN_HANDLE_MESSAGE",
    "CODEX_HOST_UNKNOWN_TIER_MESSAGE",
    "CODEX_HOST_UNMODELED_RAW_METHODS",
    "CODEX_HOST_UNUSABLE_SCHEMA_MESSAGE",
    "CODEX_HOST_UNUSED_ARGUMENT_MESSAGE",
    "CODEX_HOST_UNUSED_FIELD_MESSAGE",
    "CODEX_HOST_USAGE_COUNTERS",
    "CODEX_HOST_USAGE_LIMITED_MESSAGE",
    "CODEX_HOST_USER_REVIEWER_MESSAGE",
    "CODEX_HOST_VERSION_MESSAGE",
    "CODEX_HOST_VERSION_PATTERN",
    "CODEX_HOST_WAIT_HANDLES_MESSAGE",
    "CODEX_HOST_WAIT_MAX_HANDLES",
    "CODEX_HOST_WORKTREE_DETAIL_MAX_CHARS",
    "CODEX_HOST_WORKTREE_EXISTS_CAUSE",
    "CODEX_HOST_WORKTREE_EXISTS_MESSAGE",
    "CODEX_HOST_WORKTREE_EXISTS_NEXT_STEP",
    "CODEX_HOST_WORKTREE_FAILED_CAUSE",
    "CODEX_HOST_WORKTREE_FAILED_MESSAGE",
    "CODEX_HOST_WORKTREE_FAILED_NEXT_STEP",
    "CODEX_HOST_WORKTREE_GIT_MISSING_CAUSE",
    "CODEX_HOST_WORKTREE_GIT_MISSING_MESSAGE",
    "CODEX_HOST_WORKTREE_GIT_MISSING_NEXT_STEP",
    "CODEX_HOST_WORKTREE_MAX_OUTPUT_BYTES",
    "CODEX_HOST_WORKTREE_NAME_SEPARATOR",
    "CODEX_HOST_WORKTREE_REF_MESSAGE",
    "CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE",
    "CODEX_HOST_WORKTREE_ROOT_CAUSE",
    "CODEX_HOST_WORKTREE_ROOT_MESSAGE",
    "CODEX_HOST_WORKTREE_ROOT_NEXT_STEP",
    "CODEX_HOST_WORKTREE_ROOT_PARTS",
    "CODEX_HOST_WORKTREE_TIMED_OUT_CAUSE",
    "CODEX_HOST_WORKTREE_TIMED_OUT_MESSAGE",
    "CODEX_HOST_WORKTREE_TIMED_OUT_NEXT_STEP",
    "CODEX_HOST_WORKTREE_TIMEOUT_SECONDS",
    "CODEX_HOST_WORKTREE_UNSAFE_NAME_PATTERN",
    "CODEX_HOST_WRITABLE_ROOTS_MESSAGE",
    "CODEX_MCP_SERVER_STATUS_LIST_METHOD",
    "CODEX_MEMORY_RESET_METHOD",
    "CODEX_MEMORY_STATUS_METHOD",
    "CODEX_THREAD_ARCHIVE_METHOD",
    "CODEX_THREAD_BACKGROUND_TERMINALS_CLEAN_METHOD",
    "CODEX_THREAD_BACKGROUND_TERMINALS_LIST_METHOD",
    "CODEX_THREAD_INJECT_ITEMS_METHOD",
    "CODEX_THREAD_MEMORY_MODE_SET_METHOD",
    "CODEX_THREAD_REVERT_METHOD",
    "CODEX_THREAD_SEARCH_METHOD",
    "CODEX_THREAD_SETTINGS_UPDATE_METHOD",
    "CODEX_THREAD_UNARCHIVE_METHOD",
    "CODEX_TURN_ITEMS_VIEW_NOT_LOADED",
    "CODEX_TURN_SETTINGS_UPDATE_METHOD",
]
