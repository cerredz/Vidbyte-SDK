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
Architecture note:
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
Role in codebase:
    Composes the verifier kernel and delegates algorithm-specific lifecycle
    control to the selected VerifierRuntimeMode.
Common modification patterns:
    Add shared checkpoint behavior here; add new timing policy as a mode class.
Known edge cases:
    A runtime is scoped to one agent run and must not retain tool state across
    subsequent runs.
Related docs:
    docs/design/verifier-runtime.md; docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by verifier runtime integration tests.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from vidbyte.agents.runtimes.verifier.algorithms.base import RunOnce
from vidbyte.agents.runtimes.verifier.ledger import VerifierLedgerStatistics
from vidbyte.agents.runtimes.verifier.settings import VerifierRuntimeSettings
from vidbyte.agents.runtimes.verifier.types import GateDecision, RepairContext, RepairOutcome, ResolutionContext, VerificationAttempt, VerifierRuntimeOutcome
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.dataclasses.verifier import VerifierRunRequest


class AgentVerifierRuntime:
    """Orchestrates the eight verifier-runtime pillars for one AgentRuntime run."""

    def __init__(self, settings: VerifierRuntimeSettings, *, run_id: str, context_manager: Any = None) -> None:
        # Builds this run's own ledger, overriding the configured placeholder run_id with the real one.
        self.settings = settings
        self.ledger = VerifierLedgerStatistics(dataclasses.replace(settings.params.ledger_params, run_id=run_id))
        self.mode = settings.mode
        self.context_manager = context_manager
        self._tool_call_count = 0
        self._last_tool_passed = False

    # @intent verifier-finalization-boundary
    async def on_finalization_attempt(self, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Delegates finalization behavior to the selected algorithm mode.
        return await self.mode.on_finalization(self, context)

    # @intent verifier-mode-dispatch
    async def run(self, request: VerifierRunRequest, run_once: RunOnce) -> AgentResult:
        # Delegates one complete agent invocation to the selected outer algorithm mode.
        self._tool_call_count = 0
        self._last_tool_passed = False
        result = await self.mode.run(self, request, run_once)
        return self.with_verifier_metadata(result)

    async def after_iteration(self, context: ResolutionContext) -> VerifierRuntimeOutcome | None:
        # Delegates a completed non-final iteration to modes that schedule checkpoints.
        return await self.mode.after_iteration(self, context)

    # @intent verifier-checkpoint
    async def evaluate_checkpoint(self, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Runs the shared target, collection, verdict, ledger, gate, feedback, and repair pipeline.
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

    # @intent post-run-result
    async def evaluate_result(self, request: VerifierRunRequest, result: AgentResult) -> VerifierRuntimeOutcome:
        # Verifies a completed outer attempt using its result and initial request context.
        output = str(getattr(result, "output", result) or "")
        options = dict(getattr(request, "options", None) or {})
        messages = tuple(options.get("messages", ())) + ({"role": "assistant", "content": output},)
        metadata = getattr(result, "metadata", {})
        context = ResolutionContext(candidate_output=output, messages=messages, workspace_root=None, iteration_count=int(dict(metadata).get("iteration_count", 0)), context_manager=self.context_manager)
        return await self.evaluate_checkpoint(context)

    # @intent verifier-tool-checkpoint
    async def evaluate_tool(self, candidate_output: str) -> VerifierRuntimeOutcome:
        # Verifies the candidate supplied by the model-callable verifier tool.
        context = ResolutionContext(candidate_output=candidate_output, messages=(), workspace_root=None, iteration_count=0, context_manager=self.context_manager)
        outcome = await self.evaluate_checkpoint(context)
        self._last_tool_passed = outcome.decision is GateDecision.ALLOW_FINALIZE
        return outcome

    def allow_tool_call(self) -> bool:
        # Increments the accepted verifier-tool call count when the configured ceiling permits it.
        mode_params = getattr(self.mode, "params", None)
        maximum = getattr(mode_params, "max_calls", None)
        if maximum is not None and self._tool_call_count >= maximum:
            return False
        self._tool_call_count += 1
        return True

    @property
    def last_tool_passed(self) -> bool:
        # Returns whether the most recent accepted verifier-tool call passed.
        return self._last_tool_passed

    def mode_tools(self) -> tuple[Any, ...]:
        # Returns model-callable tools contributed by the selected algorithm mode.
        return self.mode.tools(self)

    def with_verifier_metadata(self, result: Any) -> Any:
        # Returns a result carrying the current verifier ledger report in its metadata.
        if not isinstance(result, AgentResult):
            return result
        metadata = dict(result.metadata)
        metadata["verifier_evaluations"] = self.ledger.report()
        return dataclasses.replace(result, metadata=metadata)

    # @intent verifier-decision-resolution
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

    # @intent verifier-repair-transition
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
