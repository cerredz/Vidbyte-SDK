"""
FILE: vidbyte/agents/__init__.py

PURPOSE:
    Exposes agents and orchestration primitives for Vidbyte SDK. Allows easy package-level import of BaseAgent, registries, client schemas, and swappable execution runtimes.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/agents layer, which owns agent construction, runtime dispatch, handoff, fork, and execution state.
    It should be read with `vidbyte/agents/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.agents.aggregation: imported by this file.
    - vidbyte.agents.base: imported by this file.
    - vidbyte.agents.client: imported by this file.
    - vidbyte.agents.context_algorithms: imported by this file.
    - vidbyte.agents.continual_trace: imported by this file.
    - vidbyte.agents.handoff: imported by this file.
    - vidbyte.agents.runtimes: imported by this file.
    - vidbyte.agents.settings: imported by this file.

FUNCTION INVENTORY:
    - Agent (export): public or navigational symbol owned here.
    - AggregateAgent (export): public or navigational symbol owned here.
    - AggregateConfig (export): public or navigational symbol owned here.
    - AggregateResult (export): public or navigational symbol owned here.
    - AgentClient (export): public or navigational symbol owned here.
    - AgentLoopSettings (export): public or navigational symbol owned here.
    - ToolErrorPolicy (export): public or navigational symbol owned here.
    - UnrecoverableAction (export): public or navigational symbol owned here.
    - AgentCard (export): public or navigational symbol owned here.
    - AgentForkSettings (export): public or navigational symbol owned here.
    - AgentInput (export): public or navigational symbol owned here.
    - AgentMessage (export): public or navigational symbol owned here.
    - MultiProviderAggregator (export): public or navigational symbol owned here.
    - ProposerSpec (export): public or navigational symbol owned here.
    - AgentRunnerConfig (export): public or navigational symbol owned here.
    - AgentRuntimeContextAlgorithms (export): public or navigational symbol owned here.
    - AgentRuntimeConfig (export): public or navigational symbol owned here.
    - AgentRuntimeStats (export): public or navigational symbol owned here.
    - AgentRegistry (export): public or navigational symbol owned here.
    - AgentSpec (export): public or navigational symbol owned here.
    - AgentStopReason (export): public or navigational symbol owned here.
    - BaseAgent (export): public or navigational symbol owned here.
    - ConfiguredAgentRunner (export): public or navigational symbol owned here.
    - ContinualTraceAgent (export): public or navigational symbol owned here.
    - HandoffAgent (export): public or navigational symbol owned here.
    - ModelModality (export): public or navigational symbol owned here.
    - AgentRuntime (export): public or navigational symbol owned here.
    - SearchTreeRuntimeComponent (export): public or navigational symbol owned here.
    - PointToPointActorRuntime (export): public or navigational symbol owned here.
    - BroadcastActorRuntime (export): public or navigational symbol owned here.
    - LinearRuntime (export): public or navigational symbol owned here.
    - MctsSearchRuntime (export): public or navigational symbol owned here.
    - ActorRuntime (export): public or navigational symbol owned here.

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

from vidbyte.agents.base import BaseAgent, ConfiguredAgentRunner
from vidbyte.agents.aggregation import AggregateAgent, AggregateResult, MultiProviderAggregator
from vidbyte.agents.client import AgentClient
from vidbyte.agents.continual_trace import ContinualTraceAgent
from vidbyte.agents.settings import AgentLoopSettings, ToolErrorPolicy, UnrecoverableAction
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.lib.dataclasses.multi_agent import AggregateConfig, ProposerSpec
from vidbyte.lib.registries import AgentRegistry
from vidbyte.agents.runtimes import (
    LinearAgentRuntime as AgentRuntime,
    SearchTreeRuntimeComponent,
    PointToPointActorRuntime,
    BroadcastActorRuntime,
    LinearRuntime,
    MctsSearchRuntime,
    ActorRuntime,
)
from vidbyte.lib.dataclasses.agents import (
    AgentRunnerConfig,
    AgentRuntimeConfig,
    AgentRuntimeStats,
    AgentStopReason,
)
from vidbyte.agents.types import AgentCard, AgentForkSettings, AgentInput, AgentMessage, AgentSpec, ModelModality

Agent = BaseAgent

__all__ = [
    "Agent",
    "AggregateAgent",
    "AggregateConfig",
    "AggregateResult",
    "AgentClient",
    "AgentLoopSettings",
    "ToolErrorPolicy",
    "UnrecoverableAction",
    "AgentCard",
    "AgentForkSettings",
    "AgentInput",
    "AgentMessage",
    "MultiProviderAggregator",
    "ProposerSpec",
    "AgentRunnerConfig",
    "AgentRuntimeContextAlgorithms",
    "AgentRuntimeConfig",
    "AgentRuntimeStats",
    "AgentRegistry",
    "AgentSpec",
    "AgentStopReason",
    "BaseAgent",
    "ConfiguredAgentRunner",
    "ContinualTraceAgent",
    "HandoffAgent",
    "ModelModality",
    "AgentRuntime",
    "SearchTreeRuntimeComponent",
    "PointToPointActorRuntime",
    "BroadcastActorRuntime",
    "LinearRuntime",
    "MctsSearchRuntime",
    "ActorRuntime",
]
