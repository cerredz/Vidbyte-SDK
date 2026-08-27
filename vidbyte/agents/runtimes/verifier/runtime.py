"""Context Protocol Header

Description:
    Defines AgentVerifierRuntime, the verifier-runtime orchestrator.
Purpose:
    The one method the linear AgentRuntime calls at each finalization
    boundary. Per review feedback on PR #349 ("dont really want a
    on_finalization_attempt in the runtime, the gate should have this
    logic"), resolving the target, running the collection, aggregating the
    verdict, recording it, and deciding now lives in
    VerifierRuntimeGate.evaluate_finalization_attempt(); this class owns only
    what happens *after* a decision — feedback, repair, and context
    publishing — which are not gate concerns.
Architecture:
    - AgentVerifierRuntime: one instance per AgentRuntime run.
      on_finalization_attempt() is the entire public surface the caller needs;
      it delegates the finalization check itself to the configured gate.
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

from vidbyte.agents.runtimes.verifier.ledger import VerifierLedgerStatistics
from vidbyte.agents.runtimes.verifier.settings import VerifierRuntimeSettings
from vidbyte.agents.runtimes.verifier.types import GateDecision, RepairContext, RepairOutcome, ResolutionContext, VerificationAttempt, VerifierRuntimeOutcome


class AgentVerifierRuntime:
    """Orchestrates the eight verifier-runtime pillars for one AgentRuntime run."""

    def __init__(self, settings: VerifierRuntimeSettings, *, run_id: str) -> None:
        # Builds this run's own ledger, overriding the configured placeholder run_id with the real one.
        self.settings = settings
        self.ledger = VerifierLedgerStatistics(dataclasses.replace(settings.params.ledger_params, run_id=run_id))

    async def on_finalization_attempt(self, context: ResolutionContext) -> VerifierRuntimeOutcome:
        """Delegates the finalization check to the gate, then resolves the decision into an outcome."""
        decision, attempt = await self.settings.params.gate.evaluate_finalization_attempt(
            context,
            target_resolver=self.settings.params.target_resolver,
            collection=self.settings.params.collection,
            verdict_policy=self.settings.params.verdict_policy,
            budget=self.settings.params.budget,
            ledger=self.ledger,
        )
        if attempt is None:
            # should_fire was False this iteration — nothing ran, nothing to report back.
            return VerifierRuntimeOutcome(decision, None, None)
        return await self._resolve_decision(decision, attempt, context)

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
