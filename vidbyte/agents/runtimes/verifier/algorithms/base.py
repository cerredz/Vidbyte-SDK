"""Context Protocol Header

Description:
    Defines the lifecycle contract shared by verifier runtime algorithms.
Purpose:
    Keeps algorithm-specific control flow outside AgentRuntime while exposing
    only the few lifecycle seams the linear loop must announce.
Architecture note:
    - VerifierRuntimeMode: no-op base behavior for run, iteration,
      finalization, and tool contribution.
Relations:
    Implemented by the four concrete classes in this package and delegated to
    by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
Role in codebase:
    Defines the minimal lifecycle seam between AgentRuntime and mode classes.
Common modification patterns:
    Add a lifecycle hook only when every mode can supply a safe default.
Known edge cases:
    The default mode must remain a no-op outside finalization verification.
Related docs:
    docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by verifier runtime mode delegation tests.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.verifier import (
    GateDecision,
    ResolutionContext,
    VerifierRunRequest,
    VerifierRuntimeModeKind,
    VerifierRuntimeOutcome,
)

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.runtime import AgentVerifierRuntime


RunOnce = Callable[[VerifierRunRequest], Awaitable[Any]]


class VerifierRuntimeMode:
    """Base lifecycle contract for one verifier execution algorithm."""

    kind = VerifierRuntimeModeKind.FINALIZATION_GATE

    # @intent one-attempt-delegation
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
