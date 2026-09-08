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

CODEX_ROOT_FORK_DEPTH = 0
CODEX_NEXT_FORK_DEPTH = 1
CODEX_ZERO_DURATION_MS = 0
CODEX_PROVIDER_NAME = "codex"
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


__all__ = [
    "CODEX_UNSUPPORTED_LOOP_FIELDS",
    "CODEX_UNOBSERVABLE_COUNTER_KEYS",
    "CODEX_TOOL_ITEM_TYPES",
    "CODEX_MILLISECONDS_PER_SECOND",
    "CODEX_ITEM_COMPLETED_STATUS",
    "CODEX_CONTRACTS_KEY",
    "CODEX_COMPACTION_ITEM_TYPE",
    "CODEX_COMMAND_SUCCESS_EXIT_CODE",
    "CODEX_NEXT_FORK_DEPTH",
    "CODEX_PROVIDER_NAME",
    "CODEX_RESERVED_SUBAGENT_NAMES",
    "CODEX_ROOT_FORK_DEPTH",
    "CODEX_SDK_EXTRA",
    "CODEX_SUBAGENT_ITEM_TYPES",
    "CODEX_SUPPORTED_ITEM_TYPES",
    "CODEX_USAGE_PROVIDER",
    "CODEX_USAGE_ROLLUP_KEY",
    "CODEX_ZERO_DURATION_MS",
]
