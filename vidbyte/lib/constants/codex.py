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
    "CODEX_PROVIDER_NAME",
    "CODEX_RESERVED_SUBAGENT_NAMES",
    "CODEX_ROOT_FORK_DEPTH",
    "CODEX_SDK_EXTRA",
    "CODEX_SUBAGENT_ITEM_TYPES",
    "CODEX_SUPPORTED_ITEM_TYPES",
    "CODEX_ZERO_DURATION_MS",
]
