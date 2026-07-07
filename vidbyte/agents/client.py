"""
FILE: vidbyte/agents/client.py

PURPOSE:
    Owns client behavior inside the vidbyte/agents layer.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/agents layer, which owns agent construction, runtime dispatch, handoff, fork, and execution state.
    It should be read with `vidbyte/agents/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.agents.base: imported by this file.
    - vidbyte.agents.handoff: imported by this file.
    - vidbyte.context.handoff: imported by this file.

FUNCTION INVENTORY:
    - AgentClient (class): public or navigational symbol owned here.
    - AgentClient (export): public or navigational symbol owned here.

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
    - python -m compileall vidbyte; scripts/test-agent-behavior.py, scripts/test-new-runners.py, and agent-runtime scripts when changing behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.context.handoff import Handoff


class AgentClient:
    """Namespace client for agent constructors."""

    def base(self, **kwargs: Any) -> BaseAgent:
        # Construct a standard base agent from keyword configuration.
        return BaseAgent(**kwargs)

    def handoff(self, handoff: Handoff | None = None, **kwargs: Any) -> HandoffAgent:
        # Construct a handoff agent for a given handoff spec, defaulting to MinimalHandoff.
        return HandoffAgent(handoff, **kwargs)

    def continual_trace(self, schema: Any, **kwargs: Any) -> Any:
        # Construct a continual trace agent that fills the given trace schema.
        from vidbyte.agents.continual_trace import ContinualTraceAgent
        return ContinualTraceAgent(schema, **kwargs)

    def aggregate(self, **kwargs: Any) -> Any:
        # Construct an AggregateAgent that fans out to multiple proposer models and synthesizes one answer.
        from vidbyte.agents.aggregation import AggregateAgent
        return AggregateAgent(**kwargs)


__all__ = [
    "AgentClient",
]
