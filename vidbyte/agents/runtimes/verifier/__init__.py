"""Context Protocol Header

Description:
    Public package of the verifier runtime — verifier-gated finalization for
    the linear AgentRuntime.
Purpose:
    Exposes every pillar (target resolution, verifiers, collection, gate,
    verdict policy, feedback, repair, budget, ledger) and the orchestrator
    that composes them, for developer-facing construction and for wiring
    into vidbyte.agents.settings.loop.AgentLoopSettings.
Architecture:
    - types: shared enums + result dataclasses.
    - verifier/collection: the checks themselves and how they are run.
    - target: what gets checked.
    - gate/verdict: when verification fires and what a result means.
    - feedback/repair: what happens after a rejection.
    - budget/ledger: how much this is allowed to cost, and the history that
      budget and feedback both read back from.
    - settings/runtime: the composed configuration and its orchestrator.
Relations:
    Re-exported by vidbyte.agents.runtimes and vidbyte.agents.
Similar Files:
    - vidbyte/agents/contracts/__init__.py: the nearest existing
      "small package of composable, validated checks" public surface.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.verifier.budget import VerifierRuntimeBudget, VerifierRuntimeBudgetParams
from vidbyte.agents.runtimes.verifier.collection import VerifierCollection, VerifierCollectionParams
from vidbyte.agents.runtimes.verifier.feedback import VerifierRuntimeFeedback, VerifierRuntimeFeedbackParams
from vidbyte.agents.runtimes.verifier.gate import VerifierRuntimeGate, VerifierRuntimeGateParams
from vidbyte.agents.runtimes.verifier.ledger import VerifierLedger, VerifierLedgerParams
from vidbyte.agents.runtimes.verifier.repair import VerifierRepairStrategy, VerifierRepairStrategyParams
from vidbyte.agents.runtimes.verifier.runtime import AgentVerifierRuntime
from vidbyte.agents.runtimes.verifier.settings import VerifierRuntimeSettings, VerifierRuntimeSettingsParams
from vidbyte.agents.runtimes.verifier.target import ContextPrimitiveSelectorParams, VerifierTargetResolver, VerifierTargetResolverParams
from vidbyte.agents.runtimes.verifier.types import (
    AggregatedVerdict,
    BudgetExhaustedAction,
    FeedbackContentMode,
    FeedbackDelivery,
    GateDecision,
    GateTrigger,
    RepairContext,
    RepairMode,
    RepairOutcome,
    ResolutionContext,
    TargetResolutionMode,
    VerdictStrategy,
    VerificationAttempt,
    VerifierCostClass,
    VerifierExecutionMode,
    VerifierKind,
    VerifierRuntimeOutcome,
    VerifierTarget,
    VerifierVerdict,
)
from vidbyte.agents.runtimes.verifier.verdict import VerifierVerdictPolicy, VerifierVerdictPolicyParams
from vidbyte.agents.runtimes.verifier.verifier import CallableVerifier, Verifier, VerifierParams

__all__ = [
    "AgentVerifierRuntime",
    "AggregatedVerdict",
    "BudgetExhaustedAction",
    "CallableVerifier",
    "ContextPrimitiveSelectorParams",
    "FeedbackContentMode",
    "FeedbackDelivery",
    "GateDecision",
    "GateTrigger",
    "RepairContext",
    "RepairMode",
    "RepairOutcome",
    "ResolutionContext",
    "TargetResolutionMode",
    "VerdictStrategy",
    "VerificationAttempt",
    "Verifier",
    "VerifierCollection",
    "VerifierCollectionParams",
    "VerifierCostClass",
    "VerifierExecutionMode",
    "VerifierKind",
    "VerifierLedger",
    "VerifierLedgerParams",
    "VerifierParams",
    "VerifierRepairStrategy",
    "VerifierRepairStrategyParams",
    "VerifierRuntimeBudget",
    "VerifierRuntimeBudgetParams",
    "VerifierRuntimeFeedback",
    "VerifierRuntimeFeedbackParams",
    "VerifierRuntimeGate",
    "VerifierRuntimeGateParams",
    "VerifierRuntimeOutcome",
    "VerifierRuntimeSettings",
    "VerifierRuntimeSettingsParams",
    "VerifierTarget",
    "VerifierTargetResolver",
    "VerifierTargetResolverParams",
    "VerifierVerdict",
    "VerifierVerdictPolicy",
    "VerifierVerdictPolicyParams",
]
