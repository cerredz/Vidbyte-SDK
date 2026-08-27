"""Context Protocol Header

Description:
    Defines periodic verifier checkpointing for the linear agent loop.
Purpose:
    Runs the shared verifier kernel after every configured number of completed
    iterations while retaining a finalization check at the end.
Architecture:
    - PeriodicVerificationMode: cadence-based after-iteration hook plus final
      verification.
Relations:
    Consumed by AgentVerifierRuntime and AgentRuntime's iteration seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.agents.runtimes.verifier.algorithms.base import VerifierRuntimeMode
from vidbyte.lib.dataclasses.verifier import PeriodicVerificationModeParams, ResolutionContext, VerifierRuntimeModeKind, VerifierRuntimeOutcome

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.runtime import AgentVerifierRuntime


class PeriodicVerificationMode(VerifierRuntimeMode):
    """Verifies the current state at a fixed iteration cadence and on finalization."""

    kind = VerifierRuntimeModeKind.PERIODIC

    def __init__(self, params: PeriodicVerificationModeParams | None = None) -> None:
        # Stores validated cadence settings for this mode.
        self.params = params or PeriodicVerificationModeParams()

    async def after_iteration(self, runtime: AgentVerifierRuntime, context: ResolutionContext) -> VerifierRuntimeOutcome | None:
        # Runs a checkpoint only on iterations that land on the configured cadence.
        if context.iteration_count % self.params.every_n_iterations != 0:
            return None
        return await runtime.evaluate_checkpoint(context)

    async def on_finalization(self, runtime: AgentVerifierRuntime, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Rechecks the final target because later iterations may change a passing checkpoint.
        return await runtime.evaluate_checkpoint(context)


__all__ = ["PeriodicVerificationMode"]
