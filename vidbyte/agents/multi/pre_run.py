"""Context Protocol Header

Description:
    Initializes isolated manager, ledger, and worker resources for one team run.
Purpose:
    Keeps run setup sequential, validated, and separate from round execution.
Architecture:
    MultiAgentPreRunner performs orchestrator fork, ledger creation, then worker forks.
Relations:
    Constructed by MultiAgent and invoked by MultiAgentRunner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.agents.multi.ledger import TaskLedger
from vidbyte.agents.multi.orchestrator import MultiAgentOrchestrator
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.agents.types import AgentInput
from vidbyte.lib.dataclasses.multi_agent import MultiAgentRunState, MultiAgentSettings

if TYPE_CHECKING:
    from vidbyte.agents.multi.agent import MultiAgent


class MultiAgentPreRunner:
    """Create every run-local dependency before planning begins."""

    def __init__(self, agent: MultiAgent, validator: MultiAgentValidator) -> None:
        self._agent = agent
        self._validator = validator

    async def initialize(self, state: MultiAgentRunState) -> None:
        # Initialization is deliberately linear so partial setup is easy to clean up.
        state.orchestrator = self._fork_orchestrator()
        state.ledger = self._create_ledger(state)
        self._agent._active_ledger_ids.add(id(state.ledger))
        self._agent.last_ledger = state.ledger.snapshot()
        await self._fork_workers(state)

    def _fork_orchestrator(self) -> MultiAgentOrchestrator:
        # Every invocation receives a manager lifecycle isolated from the template.
        candidate = self._agent._orchestrator_template.fork()
        return self._validator.validate_orchestrator_fork(candidate)

    def _create_ledger(self, state: MultiAgentRunState) -> TaskLedger:
        # Developer factories must return a fresh ledger synchronously.
        owners = tuple(self._agent._bindings_by_owner)
        candidate = self._agent._ledger_factory(state.run_id, state.request, owners, self._agent.settings)
        return self._validator.validate_ledger(state, candidate, self._agent._active_ledger_ids)

    async def _fork_workers(self, state: MultiAgentRunState) -> None:
        # Serial forks make duplicate-instance detection deterministic across owners.
        for owner, binding in self._agent._bindings_by_owner.items():
            worker = await binding.fork()
            self._validator.validate_distinct_worker(owner, worker, state.workers)
            state.workers[owner] = worker

    @staticmethod
    def default_ledger_factory(run_id: str, request: AgentInput, owners: tuple[str, ...], settings: MultiAgentSettings) -> TaskLedger:
        # The default is run-local in-memory state with no persistence implications.
        return TaskLedger(run_id=run_id, goal=request.prompt, owners=owners, settings=settings, metadata={})


__all__ = ["MultiAgentPreRunner"]
