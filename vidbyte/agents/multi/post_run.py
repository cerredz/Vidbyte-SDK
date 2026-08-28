"""Context Protocol Header

Description:
    Finalizes controller outcomes and builds BaseAgent-compatible replies.
Purpose:
    Separates terminal synthesis, result bookkeeping, and facade history updates
    from planning and round execution.
Architecture:
    MultiAgentPostRunner creates finalization context, terminal results, and replies.
Relations:
    Used by MultiAgentRunner and MultiAgent after lifecycle cleanup.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.agents.multi.ledger_controller import MultiAgentOrchestratorLedger
from vidbyte.agents.multi.orchestrator_runtime import MultiAgentOrchestratorRunner
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.multi_agent import (
    FinalizationContext,
    MultiAgentResult,
    MultiAgentRunState,
)
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason
from vidbyte.lib.errors import MultiAgentExecutionError

if TYPE_CHECKING:
    from vidbyte.agents.multi.agent import MultiAgent


class MultiAgentPostRunner:
    """Turn terminal controller state into public result and message contracts."""

    def __init__(self, agent: MultiAgent, validator: MultiAgentValidator, ledger: MultiAgentOrchestratorLedger, orchestrator: MultiAgentOrchestratorRunner) -> None:
        self._agent = agent
        self._validator = validator
        self._ledger = ledger
        self._orchestrator = orchestrator

    async def finalize_result(self, state: MultiAgentRunState, stop_reason: MultiAgentStopReason, completed: bool) -> MultiAgentResult:
        # Every non-timeout outcome receives one schema-free terminal synthesis call.
        finalization = FinalizationContext(orchestration=self._ledger.context(state), stop_reason=stop_reason, completed=completed, candidate_answer=state.candidate_answer, finish_decision=state.finish_decision)
        orchestrator = self._validator.require_orchestrator(state)
        content = await self._orchestrator.call(state, "finalize", orchestrator.finalize(finalization))
        self._validate_final_content(content, stop_reason)
        return self._store_result(state, content, completed, stop_reason)

    def timeout_result(self, state: MultiAgentRunState, *, cause: TimeoutError) -> MultiAgentResult:
        # Timeout returns are allowed only when policy and a non-blank candidate both exist.
        candidate = state.candidate_answer
        if not self._agent.settings.return_partial_on_limit or not isinstance(candidate, str) or not candidate.strip() or state.ledger is None:
            error = MultiAgentExecutionError("Multi-agent run timed out without an allowed candidate answer for partial return.", details={"run_id": state.run_id, "rounds": state.rounds, "replans": state.replans, "candidate_available": bool(candidate and candidate.strip()), "partial_return_enabled": self._agent.settings.return_partial_on_limit})
            raise error from cause
        return self._store_result(state, candidate, False, MultiAgentStopReason.TIMEOUT)

    async def build_reply(self, result: MultiAgentResult, request: str, recipient: str, input_metadata: Mapping[str, Any]) -> AgentMessage:
        # History and queued-prompt mutation occurs only after run-local cleanup completes.
        metadata: dict[str, Any] = {**dict(input_metadata), "strategy": "multi_agent", "multi_agent": {"stop_reason": result.stop_reason.value, "completed": result.completed, "rounds": result.rounds, "replans": result.replans, "ledger_revision": result.ledger.revision, "result": result, "ledger": result.ledger}}
        reply = AgentMessage(sender=self._agent.name, recipient=recipient, content=result.content, metadata=metadata)
        self._agent.history.append(reply)
        self._agent.last_prompt = request
        self._agent.last_reply = reply
        if self._agent._queued_prompts and not self._agent._draining_queued_prompts:
            await self._agent._drain_queued_prompts(metadata)
        return reply

    def _store_result(self, state: MultiAgentRunState, content: str, completed: bool, stop_reason: MultiAgentStopReason) -> MultiAgentResult:
        # Public result and snapshot references always describe the same terminal revision.
        snapshot = self._validator.require_ledger(state).snapshot()
        result = MultiAgentResult(content=content, completed=completed, stop_reason=stop_reason, ledger=snapshot, rounds=state.rounds, replans=state.replans, metadata={"event_callback_error_types": tuple(state.event_error_types)})
        self._agent.last_result = result
        self._agent.last_ledger = snapshot
        return result

    def _validate_final_content(self, content: Any, stop_reason: MultiAgentStopReason) -> None:
        # Finalizers must produce a concrete non-blank user-facing answer.
        if not isinstance(content, str) or not content.strip():
            raise MultiAgentExecutionError("Multi-agent finalizer must return a non-blank string.", details={"stop_reason": stop_reason.value})


__all__ = ["MultiAgentPostRunner"]
