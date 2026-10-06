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

from vidbyte.lib.enums.codex import CodexFailureClass
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


__all__ = [
    "CODEX_PRIMARY_CHAIN_INDEX",
    "CODEX_FIRST_ATTEMPT",
    "CODEX_MAX_TURN_FAILURES",
    "CODEX_FALLBACK_ATTEMPTS_KEY",
    "CODEX_FAILURE_SOURCE",
    "CODEX_FAILURE_CLASSIFICATION",
    "CODEX_FAILURES_KEY",
    "CODEX_ANSWERING_MODEL_KEY",
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
]
