"""Context Protocol Header

Description:
    Public package of the verifier runtime — verifier-gated finalization for
    the linear AgentRuntime.
Purpose:
    Exposes every pillar (target resolution, verifiers, collection, gate,
    verdict policy, feedback, repair, budget, ledger) and the orchestrator
    that composes them, for developer-facing construction and for wiring
    into vidbyte.agents.settings.loop.AgentLoopSettings.
Architecture note:
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
Role in codebase:
    Stable public import surface for the verifier runtime subsystem.
Common modification patterns:
    Add new public contracts here only after defining them in their owning
    pillar and updating the package-level exports.
Known edge cases:
    Imports must remain lightweight because AgentRuntime imports this surface
    while constructing optional verifier settings.
Related docs:
    docs/design/verifier-runtime.md; docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by verifier runtime imports and the full SDK test suite.
Similar Files:
    - vidbyte/agents/contracts/__init__.py: the nearest existing
      "small package of composable, validated checks" public surface.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.verifier.algorithms import FinalizationGateMode, PeriodicVerificationMode, PostRunVerificationMode, RunOnce, VerifierAsToolMode, VerifierRuntimeMode, VerifierTool
from vidbyte.agents.runtimes.verifier.budget import VerifierRuntimeBudget
from vidbyte.agents.runtimes.verifier.collection import (
    DatabaseQueryVerifier,
    LeanProofVerifier,
    TestSuiteVerifier,
    VerifierCollection,
    VerifierCollectionParams,
)
from vidbyte.agents.runtimes.verifier.feedback import VerifierRuntimeFeedback, VerifierRuntimeFeedbackParams
from vidbyte.agents.runtimes.verifier.gate import VerifierRuntimeGate, VerifierRuntimeGateParams
from vidbyte.agents.runtimes.verifier.ledger import VerifierLedger, VerifierLedgerParams, VerifierLedgerStatistics
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
from vidbyte.lib.dataclasses.verifier import (
    DatabaseQueryVerifierConfig,
    LeanProofVerifierConfig,
    PeriodicVerificationModeParams,
    PostRunVerificationModeParams,
    TestSuiteVerifierConfig,
    VerifierAsToolModeParams,
    VerifierRuntimeBudgetParams,
    VerifierRuntimeModeKind,
    VerifierRetryContextMode,
    VerifierRunRequest,
)

__all__ = [
    "AgentVerifierRuntime",
    "FinalizationGateMode",
    "AggregatedVerdict",
    "BudgetExhaustedAction",
    "CallableVerifier",
    "ContextPrimitiveSelectorParams",
    "DatabaseQueryVerifier",
    "DatabaseQueryVerifierConfig",
    "FeedbackContentMode",
    "FeedbackDelivery",
    "PeriodicVerificationMode",
    "PeriodicVerificationModeParams",
    "PostRunVerificationMode",
    "PostRunVerificationModeParams",
    "GateDecision",
    "GateTrigger",
    "LeanProofVerifier",
    "LeanProofVerifierConfig",
    "RepairContext",
    "RepairMode",
    "RepairOutcome",
    "ResolutionContext",
    "TargetResolutionMode",
    "TestSuiteVerifier",
    "TestSuiteVerifierConfig",
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
    "VerifierLedgerStatistics",
    "VerifierParams",
    "VerifierRepairStrategy",
    "VerifierRepairStrategyParams",
    "VerifierRuntimeBudget",
    "VerifierRuntimeBudgetParams",
    "VerifierAsToolMode",
    "VerifierAsToolModeParams",
    "RunOnce",
    "VerifierRuntimeFeedback",
    "VerifierRuntimeFeedbackParams",
    "VerifierRuntimeGate",
    "VerifierRuntimeGateParams",
    "VerifierRuntimeOutcome",
    "VerifierRuntimeMode",
    "VerifierRuntimeModeKind",
    "VerifierRetryContextMode",
    "VerifierRunRequest",
    "VerifierRuntimeSettings",
    "VerifierRuntimeSettingsParams",
    "VerifierTarget",
    "VerifierTargetResolver",
    "VerifierTargetResolverParams",
    "VerifierTool",
    "VerifierVerdict",
    "VerifierVerdictPolicy",
    "VerifierVerdictPolicyParams",
]
