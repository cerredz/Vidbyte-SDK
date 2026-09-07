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

__all__ = [
    "CODEX_NEXT_FORK_DEPTH",
    "CODEX_MIDDLEWARE_METADATA_KEY",
    "CODEX_PROVIDER_NAME",
    "CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS",
    "CODEX_RESERVED_SUBAGENT_NAMES",
    "CODEX_ROOT_FORK_DEPTH",
    "CODEX_SDK_EXTRA",
    "CODEX_SUBAGENT_ITEM_TYPES",
    "CODEX_SUPPORTED_ITEM_TYPES",
    "CODEX_ZERO_DURATION_MS",
]
