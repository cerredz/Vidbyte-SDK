"""Context Protocol Header

Description:
    Defines VerifierRuntimeGateParams and VerifierRuntimeGate.
Purpose:
    Decides when verification fires and what an aggregated verdict means for
    loop control flow — the only place a verdict and the remaining budget
    meet to produce a concrete continue/stop decision.
Architecture:
    - VerifierRuntimeGateParams: which GateTrigger to use.
    - VerifierRuntimeGate: should_fire() / decide().
Relations:
    Consumed by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
    decide() reads vidbyte.agents.runtimes.verifier.budget.VerifierRuntimeBudget
    and vidbyte.agents.runtimes.verifier.ledger.VerifierLedger by type only.
Similar Files:
    - vidbyte/agents/contract.py: exhausted()/unmet() is the nearest existing
      "verdict + budget -> continue or stop" decision in this repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vidbyte.agents.runtimes.verifier.types import AggregatedVerdict, BudgetExhaustedAction, GateDecision, GateTrigger, ResolutionContext
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.budget import VerifierRuntimeBudget
    from vidbyte.agents.runtimes.verifier.ledger import VerifierLedger


@dataclass(frozen=True, slots=True)
class VerifierRuntimeGateParams:
    """Validated configuration for one VerifierRuntimeGate."""

    trigger: GateTrigger = GateTrigger.ON_FINALIZATION_ONLY
    explicit_signal_tool_name: str | None = None

    def __post_init__(self) -> None:
        # ON_EXPLICIT_SIGNAL has nothing to scan the transcript for without a tool name.
        if self.trigger is GateTrigger.ON_EXPLICIT_SIGNAL and not self.explicit_signal_tool_name:
            raise ConfigurationError("VerifierRuntimeGateParams: trigger=ON_EXPLICIT_SIGNAL requires explicit_signal_tool_name.")


class VerifierRuntimeGate:
    """Decides when verification fires and what a verdict means for loop control flow."""

    def __init__(self, params: VerifierRuntimeGateParams) -> None:
        # Stores the already-validated configuration for this gate instance.
        self.params = params

    def should_fire(self, context: ResolutionContext) -> bool:
        """Returns whether this loop moment is a verification checkpoint under the configured trigger."""
        if self.params.trigger is GateTrigger.ON_EXPLICIT_SIGNAL:
            return self._explicit_signal_present(context)
        return True

    def decide(
        self,
        verdict: AggregatedVerdict,
        attempt_number: int,
        budget: "VerifierRuntimeBudget",
        ledger: "VerifierLedger",
    ) -> GateDecision:
        """Combines an aggregated verdict with the remaining budget into one concrete loop decision."""
        del attempt_number
        if verdict.passed:
            return GateDecision.ALLOW_FINALIZE
        if not budget.exhausted(ledger):
            return GateDecision.REJECT_AND_CONTINUE
        return self._decide_on_exhaustion(budget)

    def describe_trigger(self) -> str:
        """Returns a short human-readable description of the configured trigger."""
        return self.params.trigger.value

    def _decide_on_exhaustion(self, budget: "VerifierRuntimeBudget") -> GateDecision:
        # DOWNGRADE_TO_ADVISORY lets the run finish anyway; FAIL and ESCALATE_TO_HUMAN both stop the run here,
        # the distinction between them is surfaced by AgentVerifierRuntime via the stop reason and ledger report.
        if budget.params.on_exhausted is BudgetExhaustedAction.DOWNGRADE_TO_ADVISORY:
            return GateDecision.ALLOW_FINALIZE
        return GateDecision.REJECT_AND_TERMINATE

    def _explicit_signal_present(self, context: ResolutionContext) -> bool:
        # Scans the transcript backward for a call to the configured checkpoint tool this iteration.
        for message in reversed(list(context.messages)):
            name = message.get("name") or message.get("tool_name")
            if message.get("role") == "tool" and name == self.params.explicit_signal_tool_name:
                return True
        return False


__all__ = ["VerifierRuntimeGate", "VerifierRuntimeGateParams"]
