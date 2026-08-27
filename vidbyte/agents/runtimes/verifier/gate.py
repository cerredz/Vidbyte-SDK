"""Context Protocol Header

Description:
    Defines VerifierRuntimeGateParams and VerifierRuntimeGate.
Purpose:
    Decides when verification fires and what an aggregated verdict means for
    loop control flow — the only place a verdict and the remaining budget
    meet to produce a concrete continue/stop decision. Per review feedback
    on PR #349 ("dont really want a on_finalization_attempt in the runtime,
    the gate should have this logic"), this file also owns the finalization
    orchestration itself, not just the fire/decide judgment calls.
Architecture note:
    - VerifierRuntimeGateParams: which GateTrigger to use.
    - VerifierRuntimeGate: should_fire() / decide() / describe_trigger(), plus
      evaluate_finalization_attempt() — the orchestration entry point
      AgentVerifierRuntime.on_finalization_attempt delegates to: resolve the
      target, run the collection, aggregate the verdict, record it, then
      call decide().
Relations:
    Consumed by vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime,
    which still owns what happens *after* a decision (feedback + repair +
    context publishing) — those are not gate concerns.
    evaluate_finalization_attempt() reads
    vidbyte.agents.runtimes.verifier.target.VerifierTargetResolver,
    .collection.VerifierCollection, .verdict.VerifierVerdictPolicy,
    .budget.VerifierRuntimeBudget, and .ledger.VerifierLedger by type only,
    to avoid a module-level import cycle.
Similar Files:
    - vidbyte/agents/contract.py: exhausted()/unmet() is the nearest existing
      "verdict + budget -> continue or stop" decision in this repo.
Role in codebase:
    Owns checkpoint orchestration and the verdict-to-loop decision.
Common modification patterns:
    Change fire/decision policy through VerifierRuntimeGateParams and its
    collaborators; keep runtime lifecycle delegation thin.
Known edge cases:
    Finalization evaluation records an attempt before applying budget policy.
Related docs:
    docs/design/verifier-runtime.md; docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by gate, budget, and runtime integration tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from vidbyte.agents.runtimes.verifier.types import (
    AggregatedVerdict,
    BudgetExhaustedAction,
    GateDecision,
    GateTrigger,
    ResolutionContext,
    VerificationAttempt,
)
from vidbyte.lib.errors import ConfigurationError

NEXT_ATTEMPT_OFFSET = 1

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.budget import VerifierRuntimeBudget
    from vidbyte.agents.runtimes.verifier.collection import VerifierCollection
    from vidbyte.agents.runtimes.verifier.ledger import VerifierLedger
    from vidbyte.agents.runtimes.verifier.target import VerifierTargetResolver
    from vidbyte.agents.runtimes.verifier.verdict import VerifierVerdictPolicy


@dataclass(frozen=True, slots=True)
class VerifierRuntimeGateParams:
    """Validated configuration for one VerifierRuntimeGate."""

    trigger: GateTrigger = GateTrigger.ON_FINALIZATION_ONLY
    explicit_signal_tool_name: str | None = None

    def __post_init__(self) -> None:
        # ON_EXPLICIT_SIGNAL has nothing to scan the transcript for without a tool name.
        if self.trigger is GateTrigger.ON_EXPLICIT_SIGNAL and not self.explicit_signal_tool_name:
            raise ConfigurationError("VerifierRuntimeGateParams: trigger=ON_EXPLICIT_SIGNAL requires explicit_signal_tool_name.")
        self._validate_trigger_supported()

    def _validate_trigger_supported(self) -> None:
        # The linear runtime only calls on_finalization_attempt at its two finalization boundaries today, so
        # ON_EVERY_ITERATION/ON_TIER_BOUNDARY would silently behave like ON_FINALIZATION_ONLY if allowed through.
        if self.trigger in (GateTrigger.ON_EVERY_ITERATION, GateTrigger.ON_TIER_BOUNDARY):
            raise ConfigurationError(
                f"VerifierRuntimeGateParams: trigger={self.trigger.value} has no wired call site in the linear "
                "runtime today — only ON_FINALIZATION_ONLY and ON_EXPLICIT_SIGNAL fire. Wiring a per-iteration or "
                "per-tier call site is a separate, larger change to runtime.py's loop."
            )


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

    # @intent finalization-orchestration
    async def evaluate_finalization_attempt(
        self,
        context: ResolutionContext,
        *,
        target_resolver: "VerifierTargetResolver",
        collection: "VerifierCollection",
        verdict_policy: "VerifierVerdictPolicy",
        budget: "VerifierRuntimeBudget",
        ledger: "VerifierLedger",
    ) -> tuple[GateDecision, VerificationAttempt | None]:
        """Runs one full gate check for a finalization attempt: resolves the target, runs the
        collection, aggregates the verdict, records it, and returns the resulting decision.

        Returns (ALLOW_FINALIZE, None) without running anything when should_fire is False —
        there is no attempt to report back in that case.
        """
        if not self.should_fire(context):
            return GateDecision.ALLOW_FINALIZE, None
        attempt = await self._run_attempt(context, target_resolver, collection, verdict_policy, ledger)
        decision = self.decide(attempt.aggregated, attempt.attempt_number, budget, ledger)
        return decision, attempt

    # @intent verifier-attempt
    async def _run_attempt(
        self,
        context: ResolutionContext,
        target_resolver: "VerifierTargetResolver",
        collection: "VerifierCollection",
        verdict_policy: "VerifierVerdictPolicy",
        ledger: "VerifierLedger",
    ) -> VerificationAttempt:
        # Resolves the target, runs every configured verifier, aggregates the result, and records it.
        started = time.monotonic()
        target = target_resolver.resolve(context)
        verdicts = await collection.run(target)
        aggregated = verdict_policy.aggregate(verdicts)
        attempt = VerificationAttempt(
            attempt_number=len(ledger.history()) + NEXT_ATTEMPT_OFFSET,
            target=target,
            aggregated=aggregated,
            started_at=started,
            completed_at=time.monotonic(),
            cost_spent_usd=context.cost_spent_usd,
        )
        ledger.record(attempt)
        return attempt

    # @intent verdict-loop-decision
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
