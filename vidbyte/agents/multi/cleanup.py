"""Context Protocol Header

Description:
    Owns run-local worker/orchestrator cleanup and worker resets after replanning.
Purpose:
    Ensures participant lifecycle failures are isolated, aggregated, and observable.
Architecture:
    MultiAgentCleanup supports shielded terminal cleanup and selective worker reset.
Relations:
    Used by lifecycle and ledger-controller collaborators.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.multi.transfer import AgentBinding
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.lib.dataclasses.multi_agent import MultiAgentRunState
from vidbyte.lib.errors import MultiAgentExecutionError

if TYPE_CHECKING:
    from vidbyte.agents.multi.agent import MultiAgent


class MultiAgentCleanup:
    """Close or replace every run-local participant without sharing state."""

    def __init__(self, agent: MultiAgent, validator: MultiAgentValidator) -> None:
        self._agent = agent
        self._validator = validator

    async def shielded_close(self, state: MultiAgentRunState) -> BaseException | None:
        # Cleanup completes under cancellation; the lifecycle re-raises after trace closure.
        task = asyncio.create_task(self.close_run(state))
        try:
            await asyncio.shield(task)
            return None
        except asyncio.CancelledError as cancellation:
            await asyncio.shield(task)
            return cancellation
        except BaseException as error:
            return error

    async def close_run(self, state: MultiAgentRunState) -> None:
        # Collect unique workers first so aliased factories cannot double-close an instance.
        unique_workers = self._unique_workers(state)
        closers: list[Awaitable[None]] = [binding.close(worker) for binding, worker in unique_workers.values()]
        state.workers.clear()
        self._release_ledger(state)
        self._append_orchestrator_closer(state, closers)
        if not closers:
            return
        outcomes = await asyncio.gather(*closers, return_exceptions=True)
        state.cleanup_error_types = tuple(type(outcome).__name__ for outcome in outcomes if isinstance(outcome, BaseException))

    async def reset_workers(self, state: MultiAgentRunState) -> None:
        # Every selected owner is attempted; failures are reported together afterward.
        errors: list[tuple[str, str]] = []
        for owner, binding in self._agent._bindings_by_owner.items():
            if binding.transfer.reset_on_replan:
                error = await self._reset_worker(state, owner, binding)
                if error is not None:
                    errors.append((owner, error))
        if errors:
            raise MultiAgentExecutionError("One or more workers could not be safely reset after replanning.", details={"failures": tuple({"owner": owner, "error_type": error_type} for owner, error_type in errors)})

    async def _reset_worker(self, state: MultiAgentRunState, owner: str, binding: AgentBinding) -> str | None:
        # Close before removing the worker so a failed closer leaves no hidden replacement.
        worker = state.workers[owner]
        try:
            await binding.close(worker)
        except Exception as exc:
            return type(exc).__name__
        state.workers.pop(owner)
        return await self._install_replacement(state, owner, binding)

    async def _install_replacement(self, state: MultiAgentRunState, owner: str, binding: AgentBinding) -> str | None:
        # A replacement must remain isolated from every other live owner.
        try:
            replacement = await binding.fork()
            self._validator.validate_distinct_worker(owner, replacement, state.workers)
            state.workers[owner] = replacement
            return None
        except Exception as exc:
            return type(exc).__name__

    def _unique_workers(self, state: MultiAgentRunState) -> dict[int, tuple[AgentBinding, BaseAgent]]:
        # Identity keys protect custom factories that accidentally return aliased workers.
        unique: dict[int, tuple[AgentBinding, BaseAgent]] = {}
        for owner, worker in tuple(state.workers.items()):
            unique.setdefault(id(worker), (self._agent._bindings_by_owner[owner], worker))
        return unique

    def _release_ledger(self, state: MultiAgentRunState) -> None:
        # Active-id tracking ends only when the run cleanup owns the ledger release.
        if state.ledger is not None:
            self._agent._active_ledger_ids.discard(id(state.ledger))

    def _append_orchestrator_closer(self, state: MultiAgentRunState, closers: list[Awaitable[None]]) -> None:
        # The run-local orchestrator closes after workers and is detached immediately.
        if state.orchestrator is None:
            return
        closers.append(state.orchestrator.aclose())
        state.orchestrator = None


__all__ = ["MultiAgentCleanup"]
