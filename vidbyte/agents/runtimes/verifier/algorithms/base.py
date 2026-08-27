"""Context Protocol Header

Description:
    Defines the lifecycle contract shared by verifier runtime algorithms.
Purpose:
    Keeps algorithm-specific control flow outside AgentRuntime while exposing
    only the few lifecycle seams the linear loop must announce.
Architecture:
    - VerifierRuntimeMode: no-op base behavior for run, iteration,
      finalization, and tool contribution.
Relations:
    Implemented by the four concrete classes in this package and delegated to
    by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.verifier import (
    ResolutionContext,
    VerifierRunRequest,
    VerifierRuntimeModeKind,
    VerifierRuntimeOutcome,
)
from vidbyte.agents.runtimes.verifier.types import GateDecision

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.runtime import AgentVerifierRuntime


RunOnce = Callable[[VerifierRunRequest], Awaitable[Any]]


class VerifierRuntimeMode:
    """Base lifecycle contract for one verifier execution algorithm."""

    kind = VerifierRuntimeModeKind.FINALIZATION_GATE

    async def run(self, runtime: AgentVerifierRuntime, request: VerifierRunRequest, run_once: RunOnce) -> Any:
        # Runs one normal agent attempt; outer modes override this wrapper.
        del runtime
        return await run_once(request)

    async def after_iteration(self, runtime: AgentVerifierRuntime, context: ResolutionContext) -> VerifierRuntimeOutcome | None:
        # Does nothing after an ordinary iteration unless a mode schedules a checkpoint.
        del runtime, context
        return None

    async def on_finalization(self, runtime: AgentVerifierRuntime, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Allows finalization for modes that verify outside the inner loop.
        del runtime, context
        return VerifierRuntimeOutcome(GateDecision.ALLOW_FINALIZE, None, None)

    def tools(self, runtime: AgentVerifierRuntime) -> tuple[Any, ...]:
        # Contributes no model-callable tools by default.
        del runtime
        return ()


__all__ = ["RunOnce", "VerifierRuntimeMode"]
