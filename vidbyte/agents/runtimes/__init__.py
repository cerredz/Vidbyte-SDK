"""
FILE: vidbyte/agents/runtimes/__init__.py

PURPOSE:
    Exposes all swappable agent loop execution runtimes. Allows BaseAgent to dynamically import and dispatch different runtime loop paradigms (linear execution, search trees, and actor mailboxes).
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/agents layer, which owns agent construction, runtime dispatch, handoff, fork, and execution state.
    It should be read with `vidbyte/agents/runtimes/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.agents.runtimes.actor.actor: imported by this file.
    - vidbyte.agents.runtimes.actor.broker: imported by this file.
    - vidbyte.agents.runtimes.configs: imported by this file.
    - vidbyte.agents.runtimes.linear: imported by this file.
    - vidbyte.agents.runtimes.search: imported by this file.

FUNCTION INVENTORY:
    - LinearAgentRuntime (export): public or navigational symbol owned here.
    - SearchTreeRuntimeComponent (export): public or navigational symbol owned here.
    - PointToPointActorRuntime (export): public or navigational symbol owned here.
    - BroadcastActorRuntime (export): public or navigational symbol owned here.
    - LinearRuntime (export): public or navigational symbol owned here.
    - MctsSearchRuntime (export): public or navigational symbol owned here.
    - ActorRuntime (export): public or navigational symbol owned here.
    - PrebuiltActor (export): public or navigational symbol owned here.
    - PlannerActor (export): public or navigational symbol owned here.
    - ReviewerActor (export): public or navigational symbol owned here.
    - GeneratorActor (export): public or navigational symbol owned here.
    - CriticActor (export): public or navigational symbol owned here.
    - ReasonerActor (export): public or navigational symbol owned here.
    - SummarizationActor (export): public or navigational symbol owned here.
    - DecomposerActor (export): public or navigational symbol owned here.
    - ExplorerActor (export): public or navigational symbol owned here.
    - TradeoffActor (export): public or navigational symbol owned here.
    - HypothesisGeneratorActor (export): public or navigational symbol owned here.
    - RefinerActor (export): public or navigational symbol owned here.
    - SafetyActor (export): public or navigational symbol owned here.
    - FinalAnswerActor (export): public or navigational symbol owned here.

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

from vidbyte.agents.runtimes.linear import AgentRuntime as LinearAgentRuntime
from vidbyte.agents.runtimes.search import SearchTreeRuntimeComponent
from vidbyte.agents.runtimes.actor.broker import PointToPointActorRuntime, BroadcastActorRuntime
from vidbyte.agents.runtimes.configs import LinearRuntime, MctsSearchRuntime, ActorRuntime
from vidbyte.agents.runtimes.actor.actor import (
    PrebuiltActor,
    PlannerActor,
    ReviewerActor,
    GeneratorActor,
    CriticActor,
    ReasonerActor,
    SummarizationActor,
    DecomposerActor,
    ExplorerActor,
    TradeoffActor,
    HypothesisGeneratorActor,
    RefinerActor,
    SafetyActor,
    FinalAnswerActor,
)

__all__ = [
    "LinearAgentRuntime",
    "SearchTreeRuntimeComponent",
    "PointToPointActorRuntime",
    "BroadcastActorRuntime",
    "LinearRuntime",
    "MctsSearchRuntime",
    "ActorRuntime",
    "PrebuiltActor",
    "PlannerActor",
    "ReviewerActor",
    "GeneratorActor",
    "CriticActor",
    "ReasonerActor",
    "SummarizationActor",
    "DecomposerActor",
    "ExplorerActor",
    "TradeoffActor",
    "HypothesisGeneratorActor",
    "RefinerActor",
    "SafetyActor",
    "FinalAnswerActor",
]
