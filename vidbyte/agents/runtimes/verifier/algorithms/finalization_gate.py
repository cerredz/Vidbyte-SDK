"""Context Protocol Header

Description:
    Defines the finalization-gated verifier runtime algorithm.
Purpose:
    Preserves PR #349's existing behavior as a selectable mode: verify only
    when the agent attempts to finish and repair in the same loop.
Architecture:
    - FinalizationGateMode: delegates its one lifecycle hook to the shared
      AgentVerifierRuntime checkpoint evaluator.
Relations:
    Consumed by AgentVerifierRuntime and selected by default when no mode is
    supplied in VerifierRuntimeSettingsParams.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.verifier.algorithms.base import VerifierRuntimeMode
from vidbyte.lib.dataclasses.verifier import ResolutionContext, VerifierRuntimeModeKind, VerifierRuntimeOutcome

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.runtime import AgentVerifierRuntime


class FinalizationGateMode(VerifierRuntimeMode):
    """Verifies candidates only at the agent's finalization boundary."""

    kind = VerifierRuntimeModeKind.FINALIZATION_GATE

    async def on_finalization(self, runtime: AgentVerifierRuntime, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Runs the shared verifier kernel for the final candidate.
        return await runtime.evaluate_checkpoint(context)


__all__ = ["FinalizationGateMode"]
