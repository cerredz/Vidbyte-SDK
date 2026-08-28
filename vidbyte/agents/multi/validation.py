"""Context Protocol Header

Description:
    Centralizes validation and guard clauses for the multi-agent facade and runtime.
Purpose:
    Keeps public methods and orchestration flows in a validate-then-execute shape
    with consistent safe error messages at every lifecycle boundary.
Architecture:
    MultiAgentValidator exposes small guards for configuration, input, forks,
    run-local ledgers, orchestrators, and worker isolation.
Relations:
    Used by agent, lifecycle, pre-run, dispatch, ledger, and post-run collaborators.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import fields
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.multi.ledger import TaskLedger
from vidbyte.agents.multi.orchestrator import MultiAgentOrchestrator
from vidbyte.agents.multi.transfer import AgentBinding
from vidbyte.agents.types import AgentInput
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.multi_agent import MultiAgentRunState, MultiAgentSettings
from vidbyte.lib.errors import (
    AgentTransferError,
    ConfigurationError,
    MultiAgentExecutionError,
)


class MultiAgentValidator:
    """Validate multi-agent boundaries before core orchestration logic executes."""

    def normalize_bindings(self, agents: Sequence[BaseAgent | AgentBinding]) -> tuple[AgentBinding, ...]:
        # Normalize shorthand agents once so runtime code handles one binding shape.
        bindings = tuple(item if isinstance(item, AgentBinding) else AgentBinding(item) for item in agents)
        self._validate_bindings_present(bindings)
        self._validate_no_nested_teams(bindings)
        self._validate_worker_names(bindings)
        return bindings

    def validate_configuration(self, orchestrator: Any, settings: Any, callbacks: Mapping[str, Any]) -> None:
        # Validate constructor dependencies before collaborators capture the facade.
        self.validate_orchestrator(orchestrator)
        self.validate_settings(settings)
        self.validate_callbacks(callbacks)

    def validate_generate_options(self, options: Mapping[str, Any]) -> None:
        # Provider options belong on child agents; the facade only accepts trace metadata.
        unsupported = sorted(key for key in options if key != "trace_metadata")
        if unsupported:
            raise ConfigurationError(f"MultiAgent.generate_reply does not support runner option keys: {', '.join(unsupported)}; configure model options on manager or worker agents.")
        trace_metadata = options.get("trace_metadata")
        if trace_metadata is not None and not isinstance(trace_metadata, Mapping):
            raise ConfigurationError("MultiAgent trace_metadata must be a mapping when provided.")

    def normalize_input(self, message: str | AgentInput) -> AgentInput:
        # Preserve typed metadata/context while normalizing the string convenience input.
        if isinstance(message, AgentInput):
            if isinstance(message.prompt, str) and message.prompt.strip():
                return message
            raise MultiAgentExecutionError("MultiAgent AgentInput.prompt must be a non-blank string.")
        if isinstance(message, str) and message.strip():
            return AgentInput(prompt=message)
        raise MultiAgentExecutionError("MultiAgent input must be a non-blank string or AgentInput.")

    def validate_orchestrator(self, orchestrator: Any) -> MultiAgentOrchestrator:
        # Runtime-checkable protocol validation rejects incomplete manager adapters early.
        if not isinstance(orchestrator, MultiAgentOrchestrator):
            raise ConfigurationError("MultiAgent.orchestrator must be BaseAgent or MultiAgentOrchestrator.", details={"actual_type": type(orchestrator).__name__})
        return orchestrator

    def validate_orchestrator_fork(self, orchestrator: Any) -> MultiAgentOrchestrator:
        # Forks must be synchronous and preserve the complete orchestration protocol.
        if inspect.isawaitable(orchestrator):
            if inspect.iscoroutine(orchestrator):
                orchestrator.close()
            raise ConfigurationError("MultiAgentOrchestrator.fork must synchronously return the orchestration protocol.", details={"actual_type": type(orchestrator).__name__})
        return self.validate_orchestrator(orchestrator)

    def validate_settings(self, settings: Any) -> MultiAgentSettings:
        # The immutable settings contract makes every controller loop finite.
        if not isinstance(settings, MultiAgentSettings):
            raise ConfigurationError("MultiAgent.settings must be MultiAgentSettings.", details={"actual_type": type(settings).__name__})
        return settings

    def validate_callbacks(self, callbacks: Mapping[str, Any]) -> None:
        # Extension seams are validated together before any one is stored.
        for label, callback in callbacks.items():
            if callback is not None and not callable(callback):
                raise ConfigurationError(f"MultiAgent.{label} must be callable when provided.", details={"actual_type": type(callback).__name__})

    def validate_ledger(self, state: MultiAgentRunState, ledger: Any, active_ids: set[int]) -> TaskLedger:
        # A run may only own a fresh empty ledger matching its request and id.
        if inspect.isawaitable(ledger):
            if inspect.iscoroutine(ledger):
                ledger.close()
            raise ConfigurationError("ledger_factory must synchronously return a fresh TaskLedger.", details={"actual_type": type(ledger).__name__})
        if not isinstance(ledger, TaskLedger):
            raise ConfigurationError("ledger_factory must return TaskLedger.", details={"actual_type": type(ledger).__name__})
        self._validate_fresh_ledger(state, ledger)
        if id(ledger) in active_ids:
            raise ConfigurationError("ledger_factory returned a TaskLedger already active in another run.")
        return ledger

    def require_ledger(self, state: MultiAgentRunState) -> TaskLedger:
        # Collaborators fail with one lifecycle error when called before initialization.
        if state.ledger is None:
            raise MultiAgentExecutionError("Multi-agent ledger is not initialized.", details={"run_id": state.run_id})
        return state.ledger

    def require_orchestrator(self, state: MultiAgentRunState) -> MultiAgentOrchestrator:
        # Collaborators fail with one lifecycle error when the run manager is unavailable.
        if state.orchestrator is None:
            raise MultiAgentExecutionError("Multi-agent orchestrator is not initialized.", details={"run_id": state.run_id})
        return state.orchestrator

    def validate_distinct_worker(self, owner: str, worker: BaseAgent, workers: Mapping[str, BaseAgent]) -> None:
        # A fork factory cannot assign the same live worker instance to two owners.
        if any(worker is existing for existing_owner, existing in workers.items() if existing_owner != owner):
            raise AgentTransferError("Worker fork factories must return a distinct run-local instance per owner.", details={"owner": owner})

    def resolve_fork_settings(self, settings: AgentForkSettings | None) -> AgentForkSettings:
        # Team forks support only identity, prompt, metadata, and history settings.
        resolved = settings or AgentForkSettings()
        defaults = AgentForkSettings()
        supported = {"name", "system_prompt", "metadata", "include_history", "history"}
        unsupported = sorted(spec.name for spec in fields(resolved) if spec.name not in supported and getattr(resolved, spec.name) != getattr(defaults, spec.name))
        if unsupported:
            raise ConfigurationError(f"MultiAgent.fork does not support override keys: {', '.join(unsupported)}.")
        return resolved

    def fork_binding_template(self, binding: AgentBinding) -> AgentBinding:
        # Convert transfer-layer fork failures into public configuration errors.
        try:
            return binding.fork_template()
        except Exception as exc:
            raise ConfigurationError("MultiAgent.fork could not construct an isolated worker template.", details={"worker": binding.agent.name, "error_type": type(exc).__name__}) from exc

    def normalize_run_error(self, error: BaseException, state: MultiAgentRunState) -> BaseException:
        # Cancellation and existing SDK errors retain identity; unknown exceptions gain safe context.
        if not isinstance(error, Exception):
            return error
        if isinstance(error, (ConfigurationError, MultiAgentExecutionError)):
            return error
        return MultiAgentExecutionError("Multi-agent run failed before a safe terminal result.", details={"run_id": state.run_id, "error_type": type(error).__name__, "rounds": state.rounds, "replans": state.replans})

    def _validate_bindings_present(self, bindings: tuple[AgentBinding, ...]) -> None:
        # A team without workers cannot execute a delegated task.
        if not bindings:
            raise ConfigurationError("MultiAgent requires at least one worker agent.")

    def _validate_no_nested_teams(self, bindings: tuple[AgentBinding, ...]) -> None:
        # Nested teams require an explicit tool boundary in the v1 lifecycle model.
        if any(getattr(binding.agent, "_is_multi_agent_facade", False) for binding in bindings):
            raise ConfigurationError("MultiAgent workers cannot be nested directly in v1; expose a deliberate child team through as_tool() instead.")

    def _validate_worker_names(self, bindings: tuple[AgentBinding, ...]) -> None:
        # Worker names are stable owner ids, so whitespace and duplicates are invalid.
        owners = [binding.agent.name for binding in bindings]
        if any(not isinstance(owner, str) or not owner.strip() or owner != owner.strip() for owner in owners):
            raise ConfigurationError("MultiAgent worker names must be non-empty strings without surrounding whitespace.", details={"worker_count": len(owners)})
        if len(owners) != len(set(owners)):
            raise ConfigurationError("MultiAgent worker names must be non-empty and unique.", details={"worker_count": len(owners), "unique_worker_count": len(set(owners))})

    def _validate_fresh_ledger(self, state: MultiAgentRunState, ledger: TaskLedger) -> None:
        # Freshness prevents state leakage across independent facade invocations.
        initial = ledger.snapshot()
        matches = initial.run_id == state.run_id and initial.goal == state.request.prompt
        empty = initial.revision == 0 and not initial.tasks and not initial.events
        if not matches or not empty:
            raise ConfigurationError("ledger_factory must return a fresh empty TaskLedger for the current run and request.", details={"run_id_matches": initial.run_id == state.run_id, "goal_matches": initial.goal == state.request.prompt, "revision": initial.revision, "task_count": len(initial.tasks), "event_count": len(initial.events)})


__all__ = ["MultiAgentValidator"]
