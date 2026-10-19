"""FILE: vidbyte/lib/constants/codex_host.py

PURPOSE: Defines every fixed value CodexHost and its collaborators use: the wire tables, field rules and bounds the host modules read, the summary sentence of each failure they report, and the per-code likely cause, related docs and relevant tests that make each CodexAgentError a full diagnostic packet.
ROLE IN CODEBASE: The constants layer under vidbyte/harnesses/native/codex/ and vidbyte/lib/dataclasses/codex_host_inputs.py; those modules define no module-level values of their own and read every one from here or from vidbyte/lib/constants/codex.py.
ARCHITECTURE NOTE: Imports only lib enums and the shared Codex constants, so importing it never loads openai-codex: CODEX_HOST_RAW_RESPONSE_MODELS names each generated response model as text, and CodexConnection resolves the class from openai_codex.generated.v2_all when it sends the call. CODEX_NEXT_STEPS stays in codex.py, where the records and tools already read it; CODEX_HOST_LIKELY_CAUSES has exactly the same keys.
COMMON MODIFICATION PATTERNS: A new CodexHost failure adds its summary sentence here; a new failure code adds one row to CODEX_HOST_LIKELY_CAUSES and one to CODEX_NEXT_STEPS. A new raw app-server call adds its model name to CODEX_HOST_RAW_RESPONSE_MODELS, and to CODEX_HOST_SPENDING_RAW_METHODS when it spends usage.
KNOWN EDGE CASES: Templates whose text is appended to another message start with a space. A summary never quotes an exception's own text, stderr, env values or the account email; Codex's JSON-RPC message, a method name, a code and a type name are the only variable parts (codex-host INV-9).
RELATED DOCS: vidbyte/harnesses/README.md; docs/spec/codex-host/spec.md (sections 9.2 and 9.3); docs/spec/codex-host-thread-helpers/spec.md (section 9.3)
TESTS: tests/features/codex_host/test_codex_host_error_details.py, tests/features/codex_host/test_codex_host_inputs.py
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.lib.constants.codex import (
    CODEX_GOAL_GET_METHOD,
    CODEX_GOAL_SET_METHOD,
    CODEX_HOST_MINIMUM_VERSION,
    CODEX_MODEL_LIST_METHOD,
    CODEX_RATE_LIMITS_READ_METHOD,
    CODEX_REVIEW_START_METHOD,
    CODEX_SANDBOX_READINESS_METHOD,
    CODEX_SKILLS_LIST_METHOD,
    CODEX_THREAD_DELETE_METHOD,
    CODEX_THREAD_TURNS_LIST_METHOD,
)
from vidbyte.lib.enums.codex import (
    CodexGoalStatus,
    CodexHostOperation,
    CodexSandboxReadiness,
)
from vidbyte.lib.enums.failure import FailureCode

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
}
# Raw calls that spend usage, so each is sent once and never retried
# (D-2).
CODEX_HOST_SPENDING_RAW_METHODS = frozenset({CODEX_REVIEW_START_METHOD, CODEX_GOAL_SET_METHOD})
# How a failed process start is named in the messages the mapper builds.
CODEX_HOST_PROCESS_START = "the app-server start"
# openai-codex's goal start call; a plain CodexError from it means its
# start window elapsed (D-13).
CODEX_GOAL_START_CALL = "start_goal_operation"

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
    ),
    CodexHostOperation.LAUNCH_CODEX_SUBAGENTS: ("prompt", "goal"),
}

# The turn registry: the token counters a usage delta subtracts, named
# as on CodexUsage.
CODEX_HOST_USAGE_COUNTERS = frozenset(
    {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"}
)

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
    FailureCode.CODEX_MODEL_UNKNOWN.value: "The model named in the thread or turn settings is not in the model list Codex reports for this account, often because of a typo or a model the account cannot use.",
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
    FailureCode.CODEX_GOAL_UNFINISHED.value: "The thread is not loaded on this host and still holds an unfinished goal, and loading it to compact could let Codex resume that goal as untracked paid turns.",
    FailureCode.CODEX_FORK_FAILED.value: "The thread has no completed turn at the fork point, or Codex refused the fork point it was sent.",
    FailureCode.CODEX_RESPONSE_INVALID.value: "Codex ended the turn without the final answer or completion event the result needs.",
    FailureCode.CONFIGURATION_INVALID_ARGUMENT.value: "An argument or setting failed its check before anything was sent to Codex.",
    FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION.value: "Codex reports that this thread's approval requests go to a user reviewer, and nothing on a CodexHost can answer them.",
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
CODEX_HOST_REVIEWER_MESSAGE = "Codex routes this thread's approval requests to a user reviewer, and CodexHost cannot answer them."
CODEX_HOST_PROCESS_EXITED_MESSAGE = "CodexHost is closed or its Codex app-server exited."
CODEX_HOST_GOAL_STOPPED_MESSAGE = "Codex stopped the goal run with status {status}."
CODEX_HOST_TURN_FAILED_MESSAGE = "Codex failed the turn: {message}"
CODEX_HOST_TURN_FAILED_SILENTLY_MESSAGE = "Codex failed the turn without an error."
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
CODEX_HOST_LIST_SEPARATOR = ", "

# The thread helpers: what a refused compact or delete found.
CODEX_HOST_RUNNING_THREAD_MESSAGE = "Codex reports a running turn on the thread, so it cannot be compacted or deleted until that turn ends."
CODEX_HOST_GOAL_UNFINISHED_MESSAGE = "Codex reports an unfinished goal (status {status}) on the thread, and loading the thread to compact it could let Codex continue that goal."

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


__all__ = [
    "CODEX_GOAL_START_CALL",
    "CODEX_HOST_APPROVAL_FIELDS",
    "CODEX_HOST_APP_SERVER_PLACE",
    "CODEX_HOST_BUDGET_DIFFERS_MESSAGE",
    "CODEX_HOST_BUDGET_ECHO_MESSAGE",
    "CODEX_HOST_BUSY_MESSAGE",
    "CODEX_HOST_CONTENT_FIELD",
    "CODEX_HOST_EPHEMERAL_SKILL_MESSAGE",
    "CODEX_HOST_EXITED_DURING_MESSAGE",
    "CODEX_HOST_EXITED_MESSAGE",
    "CODEX_HOST_FOLDER_PLACE",
    "CODEX_HOST_GOAL_PROBLEM_CODES",
    "CODEX_HOST_GOAL_STOPPED_MESSAGE",
    "CODEX_HOST_GOAL_UNCHECKED_SENTENCE",
    "CODEX_HOST_GOAL_UNFINISHED_MESSAGE",
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
    "CODEX_HOST_LOCAL_FAILURE_MESSAGE",
    "CODEX_HOST_MESSAGE_HEAD",
    "CODEX_HOST_MINIMUM_VERSION_PARTS",
    "CODEX_HOST_MISSING_SDK_CAUSE",
    "CODEX_HOST_MISSING_SDK_MESSAGE",
    "CODEX_HOST_MISSING_SDK_NEXT_STEP",
    "CODEX_HOST_MODEL_MISMATCH_MESSAGE",
    "CODEX_HOST_MODEL_UNKNOWN_MESSAGE",
    "CODEX_HOST_MORE_NAMES_TEXT",
    "CODEX_HOST_NAMED_FORK_POINT",
    "CODEX_HOST_NEVER_RAN_MESSAGE",
    "CODEX_HOST_NEXT_STEP_SENTENCE",
    "CODEX_HOST_NOT_INSTALLED_MESSAGE",
    "CODEX_HOST_NOT_OPEN_MESSAGE",
    "CODEX_HOST_NO_ANSWER_MESSAGE",
    "CODEX_HOST_NO_COMPLETION_MESSAGE",
    "CODEX_HOST_NO_FINAL_ANSWER_MESSAGE",
    "CODEX_HOST_NO_FORK_POINT_MESSAGE",
    "CODEX_HOST_NO_GOAL_MESSAGE",
    "CODEX_HOST_NO_GOAL_MODE_MESSAGE",
    "CODEX_HOST_NO_NAMES_TEXT",
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
    "CODEX_HOST_REVIEWER_MESSAGE",
    "CODEX_HOST_RPC_ERROR_MESSAGE",
    "CODEX_HOST_RUNNING_THREAD_MESSAGE",
    "CODEX_HOST_RUN_INPUT_MESSAGE",
    "CODEX_HOST_SANDBOX_NOT_READY",
    "CODEX_HOST_SANDBOX_PLATFORM",
    "CODEX_HOST_SCHEMA_MESSAGE",
    "CODEX_HOST_SDK_REFUSED_MESSAGE",
    "CODEX_HOST_SENTENCE_SEPARATOR",
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
    "CODEX_HOST_STOP_MESSAGES",
    "CODEX_HOST_THREAD_SENTENCE",
    "CODEX_HOST_TURN_FAILED_MESSAGE",
    "CODEX_HOST_TURN_FAILED_SILENTLY_MESSAGE",
    "CODEX_HOST_UNKNOWN_HANDLE_MESSAGE",
    "CODEX_HOST_UNUSABLE_SCHEMA_MESSAGE",
    "CODEX_HOST_UNUSED_ARGUMENT_MESSAGE",
    "CODEX_HOST_UNUSED_FIELD_MESSAGE",
    "CODEX_HOST_USAGE_COUNTERS",
    "CODEX_HOST_USAGE_LIMITED_MESSAGE",
    "CODEX_HOST_VERSION_MESSAGE",
    "CODEX_HOST_VERSION_PATTERN",
]
