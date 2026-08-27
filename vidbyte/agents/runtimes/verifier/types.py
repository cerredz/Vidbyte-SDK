"""Context Protocol Header

Description:
    Shared enums and result dataclasses for the verifier runtime pillars.
Purpose:
    Gives every pillar (target resolution, verifiers, gate, verdict policy,
    feedback, repair, budget, ledger) one common, typed vocabulary instead of
    loose dicts crossing pillar boundaries.
Architecture:
    - Enums defined here: VerifierExecutionMode, GateTrigger, GateDecision —
      each is an eager default value only on VerifierCollectionParams or
      VerifierRuntimeGateParams, the two Params classes
      vidbyte.lib.dataclasses.verifier's move deliberately excludes (owned by
      collection.py and gate.py respectively).
    - Every other enum and dataclass this module used to define —
      VerifierKind, VerifierCostClass, TargetResolutionMode, VerdictStrategy,
      FeedbackContentMode, FeedbackDelivery, RepairMode,
      BudgetExhaustedAction, VerifierTarget, VerifierVerdict,
      AggregatedVerdict, VerificationAttempt, ResolutionContext,
      RepairContext, RepairOutcome, VerifierRuntimeOutcome — now lives in
      vidbyte.lib.dataclasses.verifier per review feedback on PR #349, and is
      re-exported here for every existing import site in this package
      (including vidbyte.agents.runtimes.verifier.gate and .collection,
      neither of which this move touches).
Relations:
    Imported by every module in vidbyte.agents.runtimes.verifier.
Similar Files:
    - vidbyte/lib/dataclasses/agents.py: AgentStopReason, the sibling enum
      family this subsystem's VERIFICATION_FAILED member extends.
"""

from __future__ import annotations

from enum import Enum

from vidbyte.lib.dataclasses.verifier import (
    AggregatedVerdict,
    BudgetExhaustedAction,
    FeedbackContentMode,
    FeedbackDelivery,
    RepairContext,
    RepairMode,
    RepairOutcome,
    ResolutionContext,
    TargetResolutionMode,
    VerdictStrategy,
    VerificationAttempt,
    VerifierCostClass,
    VerifierKind,
    VerifierRuntimeOutcome,
    VerifierTarget,
    VerifierVerdict,
)


class VerifierExecutionMode(str, Enum):
    """How VerifierCollection dispatches verifiers within one tier."""

    SEQUENTIAL = "sequential"
    PARALLEL_WITHIN_TIER = "parallel_within_tier"
    COST_ORDERED = "cost_ordered"


class GateTrigger(str, Enum):
    """When VerifierRuntimeGate.should_fire considers this loop moment a checkpoint."""

    ON_FINALIZATION_ONLY = "on_finalization_only"
    ON_EVERY_ITERATION = "on_every_iteration"
    ON_EXPLICIT_SIGNAL = "on_explicit_signal"
    ON_TIER_BOUNDARY = "on_tier_boundary"


class GateDecision(str, Enum):
    """The three outcomes VerifierRuntimeGate.decide can return."""

    ALLOW_FINALIZE = "allow_finalize"
    REJECT_AND_CONTINUE = "reject_and_continue"
    REJECT_AND_TERMINATE = "reject_and_terminate"


__all__ = [
    "AggregatedVerdict",
    "BudgetExhaustedAction",
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
    "VerifierCostClass",
    "VerifierExecutionMode",
    "VerifierKind",
    "VerifierRuntimeOutcome",
    "VerifierTarget",
    "VerifierVerdict",
]
