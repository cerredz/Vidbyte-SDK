"""Context Protocol Header

Description:
    Defines AgentVerifierRuntime, the verifier-runtime orchestrator.
Purpose:
    The one method the linear AgentRuntime calls at each finalization
    boundary: resolve a target, run the collection, aggregate the verdict,
    record it, and turn the result into a concrete continue/stop decision.
Architecture:
    - AgentVerifierRuntime: one instance per AgentRuntime run.
      on_finalization_attempt() is the entire public surface the caller needs.
Relations:
    Constructed by vidbyte.agents.runtime.AgentRuntime from a
    vidbyte.agents.runtimes.verifier.settings.VerifierRuntimeSettings.
Similar Files:
    - vidbyte/agents/contract.py: AgentLoopSettingsOutputContract, the
      nearest existing "one owner consulted at both finalization boundaries"
      shape this orchestrator's call sites mirror.
"""

from __future__ import annotations

import dataclasses
import time

from vidbyte.agents.runtimes.verifier.ledger import VerifierLedger
from vidbyte.agents.runtimes.verifier.settings import VerifierRuntimeSettings
from vidbyte.agents.runtimes.verifier.types import GateDecision, RepairContext, RepairOutcome, ResolutionContext, VerificationAttempt, VerifierRuntimeOutcome


class AgentVerifierRuntime:
    """Orchestrates the eight verifier-runtime pillars for one AgentRuntime run."""

    def __init__(self, settings: VerifierRuntimeSettings, *, run_id: str) -> None:
        # Builds this run's own ledger, overriding the configured placeholder run_id with the real one.
        self.settings = settings
        self.ledger = VerifierLedger(dataclasses.replace(settings.params.ledger_params, run_id=run_id))

    async def on_finalization_attempt(self, context: ResolutionContext) -> VerifierRuntimeOutcome:
        """Runs one full gate check for a finalization attempt and returns the resulting outcome."""
        if not self.settings.params.gate.should_fire(context):
            return VerifierRuntimeOutcome(GateDecision.ALLOW_FINALIZE, None, None)
        attempt = await self._run_attempt(context)
        decision = self.settings.params.gate.decide(attempt.aggregated, attempt.attempt_number, self.settings.params.budget, self.ledger)
        return await self._resolve_decision(decision, attempt, context)

    async def _run_attempt(self, context: ResolutionContext) -> VerificationAttempt:
        # Resolves the target, runs every configured verifier, aggregates the result, and records it.
        started = time.monotonic()
        target = self.settings.params.target_resolver.resolve(context)
        verdicts = await self.settings.params.collection.run(target)
        aggregated = self.settings.params.verdict_policy.aggregate(verdicts)
        attempt = VerificationAttempt(
            attempt_number=len(self.ledger.history()) + 1,
            target=target,
            aggregated=aggregated,
            started_at=started,
            completed_at=time.monotonic(),
            cost_spent_usd=context.cost_spent_usd,
        )
        self.ledger.record(attempt)
        return attempt

    async def _resolve_decision(self, decision: GateDecision, attempt: VerificationAttempt, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Turns a GateDecision into the feedback/repair pairing appropriate for that decision.
        if decision is GateDecision.ALLOW_FINALIZE:
            self._publish_context(context, last_repair=None)
            return VerifierRuntimeOutcome(decision, None, None)
        feedback_text = self.settings.params.feedback.emit(attempt.aggregated)
        if decision is GateDecision.REJECT_AND_TERMINATE:
            self._publish_context(context, last_repair=None)
            return VerifierRuntimeOutcome(decision, feedback_text, None)
        repair = await self._repair(attempt, context, feedback_text)
        self._publish_context(context, last_repair=repair)
        return VerifierRuntimeOutcome(decision, feedback_text, repair)

    async def _repair(self, attempt: VerificationAttempt, context: ResolutionContext, feedback_text: str) -> RepairOutcome:
        # Delegates to the configured RepairStrategy with everything it needs to decide what happens next.
        repair_context = RepairContext(attempt=attempt, ledger=self.ledger, resolution_context=context, feedback_text=feedback_text)
        return await self.settings.params.repair_strategy.repair(repair_context)

    def _publish_context(self, context: ResolutionContext, *, last_repair: RepairOutcome | None) -> None:
        # Upserts (never appends) the ledger's context primitives, so republishing updates the same slots.
        if not self.ledger.params.publish_to_context or context.context_manager is None:
            return
        for item in self.ledger.to_context_items(budget=self.settings.params.budget, last_repair=last_repair):
            context.context_manager.upsert(item)


__all__ = ["AgentVerifierRuntime"]
