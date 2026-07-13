"""Context Protocol Header

Description:
    Wraps one multi-agent run with tracing, error normalization, and cleanup.
Purpose:
    Provides one top-level exception boundary for the complete controller lifecycle.
Architecture:
    MultiAgentLifecycle starts tracing, executes the runner, normalizes failures,
    closes participants, and finishes tracing in one try/except/finally block.
Relations:
    Called directly by the MultiAgent facade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vidbyte.agents.multi.cleanup import MultiAgentCleanup
from vidbyte.agents.multi.tracing import MultiAgentTracer
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.lib.dataclasses.multi_agent import MultiAgentResult, MultiAgentRunState

if TYPE_CHECKING:
    from vidbyte.agents.multi.agent import MultiAgent


class MultiAgentLifecycle:
    """Own the single top-level try/except/finally boundary for one run."""

    def __init__(self, agent: MultiAgent, validator: MultiAgentValidator, cleanup: MultiAgentCleanup, tracer: MultiAgentTracer) -> None:
        self._agent = agent
        self._validator = validator
        self._cleanup = cleanup
        self._tracer = tracer

    async def execute(self, state: MultiAgentRunState, operation: Any) -> MultiAgentResult:
        # One boundary guarantees cleanup and trace closure for success, failure, and cancellation.
        handles: tuple[Any, Any] = (None, None)
        result: MultiAgentResult | None = None
        error: BaseException | None = None
        try:
            handles = self._tracer.start_run(state)
            result = await operation(state)
        except BaseException as caught:
            error = self._validator.normalize_run_error(caught, state)
            if error is caught:
                raise
            raise error from caught
        finally:
            cleanup_error = await self._cleanup.shielded_close(state)
            self._agent._active_prompt = ""
            self._tracer.finish_run(handles, state, result, error or cleanup_error)
            if error is None and cleanup_error is not None:
                raise cleanup_error
        assert result is not None
        return result


__all__ = ["MultiAgentLifecycle"]
