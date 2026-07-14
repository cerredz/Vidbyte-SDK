"""Context Protocol Header

Description:
    Invokes run-local orchestrator phases under timeout and tracing policy.
Purpose:
    Gives planning, decisions, replanning, and finalization one sequential boundary.
Architecture:
    MultiAgentOrchestratorRunner validates initialized state, awaits one phase,
    and closes its span with safe control metadata.
Relations:
    Used by ledger, runner, and post-run collaborators.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vidbyte.agents.multi.tracing import MultiAgentTracer
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.lib.dataclasses.multi_agent import MultiAgentRunState, MultiAgentSettings
from vidbyte.lib.errors import MultiAgentExecutionError


class MultiAgentOrchestratorRunner:
    """Execute one manager phase with a finite, observable boundary."""

    def __init__(self, settings: MultiAgentSettings, validator: MultiAgentValidator, tracer: MultiAgentTracer) -> None:
        self._settings = settings
        self._validator = validator
        self._tracer = tracer

    async def call(self, state: MultiAgentRunState, phase: str, awaitable: Any) -> Any:
        # Every manager phase records the exact counters and ledger revision it observed.
        ledger = self._validator.require_ledger(state)
        span = self._tracer.start_span("multi_agent.orchestrator", run_id=state.run_id, phase=phase, round=state.rounds, replans=state.replans, stalls=state.stalls, revision=ledger.revision)
        try:
            result = await self.await_phase(awaitable)
            self._tracer.end_span(span, output=self._tracer.output(phase=phase, status="completed"))
            return result
        except TimeoutError as exc:
            error = MultiAgentExecutionError("Multi-agent orchestrator phase exceeded its configured timeout.", details={"phase": phase, "round": state.rounds, "timeout_seconds": self._settings.orchestrator_timeout_seconds})
            self._tracer.end_span(span, error=error)
            raise error from exc
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def await_phase(self, awaitable: Any) -> Any:
        # The optional manager timeout applies independently to every orchestration phase.
        timeout = self._settings.orchestrator_timeout_seconds
        return await awaitable if timeout is None else await asyncio.wait_for(awaitable, timeout=timeout)


__all__ = ["MultiAgentOrchestratorRunner"]
