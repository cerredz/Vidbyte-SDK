"""
FILE: vidbyte/middleware/builtins/context_compaction.py

PURPOSE:
    Owns context compaction behavior inside the vidbyte/middleware layer.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.middleware.compaction.context_compaction: imported by this file.

FUNCTION INVENTORY:
    - MessageHistoryCompactionMiddleware (export): public or navigational symbol owned here.
    - SummaryCompactionMiddleware (export): public or navigational symbol owned here.
    - ToolResultCompactionMiddleware (export): public or navigational symbol owned here.
    - TraceReplacementCompactionMiddleware (export): public or navigational symbol owned here.
    - TraceSummaryTailCompactionMiddleware (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-security-middleware.py and compaction-related scripts when changing middleware behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""

from vidbyte.middleware.compaction.context_compaction import (
    MessageHistoryCompactionMiddleware,
    SummaryCompactionMiddleware,
    ToolResultCompactionMiddleware,
    TraceReplacementCompactionMiddleware,
    TraceSummaryTailCompactionMiddleware,
)

__all__ = [
    "MessageHistoryCompactionMiddleware",
    "SummaryCompactionMiddleware",
    "ToolResultCompactionMiddleware",
    "TraceReplacementCompactionMiddleware",
    "TraceSummaryTailCompactionMiddleware",
]
