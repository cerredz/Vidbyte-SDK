"""FILE: vidbyte/workflows/stages.py
PURPOSE: Adapts Python callbacks and Vidbyte agents to the workflow Stage protocol.
ROLE IN CODEBASE: Built by SDK users, stored by graph.py, and invoked under policy by machine.py.

ARCHITECTURE NOTE:
    A stage performs work and proposes StageResult; it never commits state or
    selects a target. AgentStage forks without history by default so repeated
    visits and concurrent machine runs do not accidentally share conversation
    state. A context-aware factory can bind run-ledger tracking tools per visit.

PUBLIC API INVENTORY:
    CallableStage: Invokes one sync/async StageContext callback.
    AgentStage: Builds agent input and maps AgentMessage to StageResult.

COMMON MODIFICATION PATTERNS:
    Add another execution adapter only when an SDK actor cannot be represented
    as a callback or BaseAgent. Keep retries, timeouts, validation, and routing
    in machine.py so adapters have no hidden control flow.

WHAT NOT TO DO IN THIS FILE:
    1. Do not commit or mutate the machine's authoritative state reference.
    2. Do not map outcomes to stage names; graph.py owns that declaration.
    3. Do not add retries around agent calls; StagePolicy owns retries.
    4. Do not automatically inject full workflow history into prompts.

KNOWN EDGE CASES:
    fresh_fork=False intentionally permits shared agent history and makes
    concurrent safety the caller's responsibility. Factories that return the
    same agent instance carry the same risk.

COMMON ERRORS:
    WorkflowDefinitionError for incompatible fork settings or bad factories.
    Agent/provider failures propagate to machine.py for StagePolicy handling.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Existing agent tests plus inline workflow smoke cover adapter integration.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Generic

from vidbyte.agents import AgentForkSettings, AgentInput, AgentMessage, BaseAgent
from vidbyte.workflows.contracts import StageContext, StageResult, StateT
from vidbyte.workflows.errors import WorkflowDefinitionError


class CallableStage(Generic[StateT]):
    """Adapts one synchronous or asynchronous stage callback."""

    def __init__(self, callback: Callable[[StageContext[StateT]], StageResult[StateT] | Awaitable[StageResult[StateT]]], *, name: str | None = None) -> None:
        # Stores the callback and a stable diagnostic name.
        if not callable(callback):
            raise WorkflowDefinitionError("CallableStage callback must be callable.", details={"actual_type": type(callback).__name__})
        self._callback = callback
        self._name = _resolved_name(name, callback, "callable_stage")

    @property
    def name(self) -> str:
        # Returns the adapter's diagnostic name; graph stage names remain authoritative.
        return self._name

    async def run(self, context: StageContext[StateT]) -> StageResult[StateT]:
        # Invokes the callback and awaits it only when necessary.
        value = self._callback(context)
        return await value if inspect.isawaitable(value) else value


class AgentStage(Generic[StateT]):
    """Adapts a fixed or context-created BaseAgent to a typed workflow stage."""

    def __init__(self, agent: BaseAgent | Callable[[StageContext[StateT]], BaseAgent], prompt_builder: Callable[[StageContext[StateT]], str | AgentInput], result_builder: Callable[[AgentMessage, StageContext[StateT]], StageResult[StateT] | Awaitable[StageResult[StateT]]], *, fresh_fork: bool = True, fork_settings: AgentForkSettings | None = None, name: str | None = None) -> None:
        # Validates isolation settings and stores the agent input/output adapters.
        if not isinstance(agent, BaseAgent) and not callable(agent):
            raise WorkflowDefinitionError("AgentStage agent must be BaseAgent or a callable factory.", details={"actual_type": type(agent).__name__})
        if not callable(prompt_builder) or not callable(result_builder):
            raise WorkflowDefinitionError("AgentStage prompt_builder and result_builder must be callable.", details={"prompt_builder_type": type(prompt_builder).__name__, "result_builder_type": type(result_builder).__name__})
        if not isinstance(fresh_fork, bool):
            raise WorkflowDefinitionError("AgentStage fresh_fork must be a boolean.", details={"actual_type": type(fresh_fork).__name__})
        if fork_settings is not None and not isinstance(fork_settings, AgentForkSettings):
            raise WorkflowDefinitionError("AgentStage fork_settings must be AgentForkSettings when provided.", details={"actual_type": type(fork_settings).__name__})
        if fresh_fork and fork_settings is not None and (fork_settings.include_history or fork_settings.history is not None):
            raise WorkflowDefinitionError("AgentStage fresh forks cannot include parent or explicit history.", details={"adapter": name or "agent_stage", "include_history": fork_settings.include_history, "explicit_history": fork_settings.history is not None})
        self._agent_source = agent
        self._prompt_builder = prompt_builder
        self._result_builder = result_builder
        self._fresh_fork = fresh_fork
        self._fork_settings = fork_settings or AgentForkSettings(include_history=False)
        self._name = _resolved_name(name, agent, "agent_stage")

    @property
    def name(self) -> str:
        # Returns the adapter's diagnostic name; graph stage names remain authoritative.
        return self._name

    async def run(self, context: StageContext[StateT]) -> StageResult[StateT]:
        # Runs one agent invocation and maps its reply to the candidate contract.
        agent = self._resolve_agent(context)
        prompt = self._prompt_builder(context)
        reply = await agent.arun(prompt)
        result = self._result_builder(reply, context)
        return await result if inspect.isawaitable(result) else result

    def _resolve_agent(self, context: StageContext[StateT]) -> BaseAgent:
        # Resolves the fixed agent or per-visit factory and applies default isolation.
        agent = self._agent_source if isinstance(self._agent_source, BaseAgent) else self._agent_source(context)
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"AgentStage agent factory must return BaseAgent, got {type(agent).__name__}.")
        return agent.fork(self._fork_settings) if self._fresh_fork else agent


def _resolved_name(name: str | None, source: object, fallback: str) -> str:
    # Derives one non-empty diagnostic name from explicit or source metadata.
    candidate = name or getattr(source, "name", None) or getattr(source, "__name__", None) or fallback
    resolved = str(candidate).strip()
    if not resolved:
        raise WorkflowDefinitionError("Stage adapter name cannot be empty.", details={"fallback": fallback})
    return resolved


__all__ = ["AgentStage", "CallableStage"]
