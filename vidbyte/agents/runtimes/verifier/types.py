"""Context Protocol Header

Description:
    Shared enums and result dataclasses for the verifier runtime pillars.
Purpose:
    Gives every pillar (target resolution, verifiers, gate, verdict policy,
    feedback, repair, budget, ledger) one common, typed vocabulary instead of
    loose dicts crossing pillar boundaries.
Architecture:
    - Enums: VerifierKind, VerifierCostClass, TargetResolutionMode,
      VerifierExecutionMode, GateTrigger, GateDecision, VerdictStrategy,
      FeedbackContentMode, FeedbackDelivery, RepairMode. BudgetExhaustedAction
      is defined in vidbyte.lib.dataclasses.verifier and re-exported here.
    - Dataclasses: VerifierTarget, VerifierVerdict, AggregatedVerdict,
      VerificationAttempt, ResolutionContext, RepairContext, RepairOutcome,
      VerifierRuntimeOutcome.
Relations:
    Imported by every module in vidbyte.agents.runtimes.verifier. Each
    pillar's own Params dataclass lives in that pillar's file, not here,
    except VerifierRuntimeBudgetParams which lives in
    vidbyte.lib.dataclasses.verifier alongside BudgetExhaustedAction.
Similar Files:
    - vidbyte/lib/dataclasses/agents.py: AgentStopReason, the sibling enum
      family this subsystem's VERIFICATION_FAILED member extends.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.verifier import BudgetExhaustedAction

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem


class VerifierKind(str, Enum):
    """The supported verifier kinds — the 'keywords' VerifierCollectionParams validates against."""

    CODE_EXECUTION = "code_execution"
    STATIC_ANALYSIS = "static_analysis"
    SCHEMA_VALIDATION = "schema_validation"
    NUMERIC_TOLERANCE = "numeric_tolerance"
    QUERY_EXECUTION = "query_execution"
    GOLDEN_DIFF = "golden_diff"
    FORMAT_PATTERN = "format_pattern"
    REFERENCE_VALIDITY = "reference_validity"
    SECURITY_SCAN = "security_scan"
    RESOURCE_CEILING = "resource_ceiling"
    IDEMPOTENCY = "idempotency"
    CONTRACT_COMPATIBILITY = "contract_compatibility"
    SANDBOX_EXECUTION = "sandbox_execution"
    RUBRIC_CHECKLIST = "rubric_checklist"
    CUSTOM = "custom"


class VerifierCostClass(str, Enum):
    """What a check costs, independent of what it checks. Feeds tier ordering."""

    LEAN = "lean"
    STANDARD = "standard"
    HEAVY = "heavy"


class TargetResolutionMode(str, Enum):
    """Which source VerifierTargetResolver reads to build the VerifierTarget."""

    FINAL_OUTPUT_TEXT = "final_output_text"
    WORKSPACE_FILES = "workspace_files"
    WORKSPACE_DIFF = "workspace_diff"
    STRUCTURED_SUBMISSION = "structured_submission"
    CUSTOM = "custom"


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


class VerdictStrategy(str, Enum):
    """How VerifierVerdictPolicy combines N verifier verdicts into one decision."""

    ALL_BLOCKING_MUST_PASS = "all_blocking_must_pass"
    WEIGHTED_SCORE_THRESHOLD = "weighted_score_threshold"
    K_OF_N = "k_of_n"
    ANY_BLOCKING_PASSES = "any_blocking_passes"
    UNANIMOUS_ENSEMBLE = "unanimous_ensemble"


class FeedbackContentMode(str, Enum):
    """What content VerifierRuntimeFeedback.emit renders."""

    RAW_VERDICT = "raw_verdict"
    CUSTOM_MESSAGE = "custom_message"
    STRUCTURED_PAYLOAD = "structured_payload"
    RAW_AND_CUSTOM = "raw_and_custom"


class FeedbackDelivery(str, Enum):
    """Where the rendered feedback payload is delivered."""

    USER_MESSAGE = "user_message"
    TOOL_RESULT = "tool_result"
    CONTEXT_ITEM = "context_item"
    SYSTEM_MESSAGE = "system_message"
    MCP_RESOURCE = "mcp_resource"


class RepairMode(str, Enum):
    """What mechanically happens to the next attempt after a rejection."""

    IN_PLACE_CONTINUE = "in_place_continue"
    FRESH_RESTART_WITH_SUMMARY = "fresh_restart_with_summary"
    TARGETED_SCOPE = "targeted_scope"
    PARALLEL_BRANCHING = "parallel_branching"


@dataclass(frozen=True, slots=True)
class VerifierTarget:
    """The resolved object handed to every verifier in one collection run."""

    mode: TargetResolutionMode
    text: str | None = None
    file_paths: tuple[str, ...] = ()
    diff: str | None = None
    submission: Mapping[str, Any] | None = None
    context_primitives: tuple["ContextItem", ...] = ()


@dataclass(frozen=True, slots=True)
class VerifierVerdict:
    """One verifier's result for one target."""

    verifier_name: str
    tier: int
    blocking: bool
    passed: bool
    score: float | None
    diagnostics: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class AggregatedVerdict:
    """The combined pass/fail decision across every verdict gathered this attempt."""

    passed: bool
    verdicts: tuple[VerifierVerdict, ...]
    advisory: tuple[VerifierVerdict, ...] = ()


@dataclass(frozen=True, slots=True)
class VerificationAttempt:
    """One full pass through the gate — what the ledger records."""

    attempt_number: int
    target: VerifierTarget
    aggregated: AggregatedVerdict
    started_at: float
    completed_at: float
    cost_spent_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class ResolutionContext:
    """The loop-local snapshot handed to every pillar at one finalization attempt."""

    candidate_output: str | None
    messages: Sequence[Mapping[str, Any]]
    workspace_root: str | None
    iteration_count: int
    context_manager: "ContextManager | None"
    cost_spent_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class RepairContext:
    """Everything a RepairStrategy needs to decide what happens next."""

    attempt: VerificationAttempt
    ledger: Any
    resolution_context: ResolutionContext
    feedback_text: str = ""


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    """What a RepairStrategy decided should happen to the next attempt."""

    injected_messages: tuple[Mapping[str, Any], ...]
    restart_session: bool = False
    scope_lock: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class VerifierRuntimeOutcome:
    """The full result of one AgentVerifierRuntime.on_finalization_attempt call."""

    decision: GateDecision
    feedback: str | None
    repair: RepairOutcome | None


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
