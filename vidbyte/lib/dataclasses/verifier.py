"""Context Protocol Header

Description:
    Every enum and dataclass for the verifier runtime, except
    VerifierCollectionParams (owned by
    vidbyte.agents.runtimes.verifier.collection) and
    VerifierRuntimeGateParams (owned by
    vidbyte.agents.runtimes.verifier.gate) — those two files are not
    modified by this move.
Purpose:
    Per review feedback on PR #349 ("all dataclasses in this PR should be in
    vidbyte/lib/dataclasses"), keeps every validated data contract for the
    verifier runtime in one lib-level home, separate from the behavior
    classes (Verifier, VerifierTargetResolver, VerifierVerdictPolicy,
    VerifierRuntimeFeedback, VerifierRepairStrategy, VerifierRuntimeBudget,
    VerifierLedger, VerifierRuntimeSettings, AgentVerifierRuntime) that
    consume them.
Architecture:
    - Enums: BudgetExhaustedAction, FeedbackContentMode, FeedbackDelivery,
      RepairMode, VerdictStrategy, TargetResolutionMode, VerifierKind,
      VerifierCostClass. (VerifierExecutionMode, GateTrigger, and
      GateDecision stay in vidbyte.agents.runtimes.verifier.types — each is
      an eager default only on VerifierCollectionParams or
      VerifierRuntimeGateParams, the two Params classes this move excludes.)
    - Shared result/context dataclasses: VerifierTarget, VerifierVerdict,
      AggregatedVerdict, VerificationAttempt, ResolutionContext,
      RepairContext, RepairOutcome, VerifierRuntimeOutcome.
    - Per-pillar Params dataclasses: VerifierParams,
      ContextPrimitiveSelectorParams, VerifierTargetResolverParams,
      VerifierVerdictPolicyParams, VerifierRuntimeFeedbackParams,
      VerifierRepairStrategyParams, VerifierRuntimeBudgetParams,
      VerifierLedgerParams, VerifierRuntimeSettingsParams.
Relations:
    Re-exported by vidbyte.agents.runtimes.verifier.types and imported
    directly by every pillar file that used to define one of these classes
    locally, so every existing import site — including
    vidbyte.agents.runtimes.verifier.gate and .collection, neither of which
    this move touches — keeps working unchanged.
Similar Files:
    - vidbyte/lib/dataclasses/agents.py: the sibling "shared data contracts,
      no behavior" file for the base agent subsystem.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.budget import VerifierRuntimeBudget
    from vidbyte.agents.runtimes.verifier.collection import VerifierCollection
    from vidbyte.agents.runtimes.verifier.feedback import VerifierRuntimeFeedback
    from vidbyte.agents.runtimes.verifier.gate import VerifierRuntimeGate
    from vidbyte.agents.runtimes.verifier.repair import VerifierRepairStrategy
    from vidbyte.agents.runtimes.verifier.target import VerifierTargetResolver
    from vidbyte.agents.runtimes.verifier.types import GateDecision
    from vidbyte.agents.runtimes.verifier.verdict import VerifierVerdictPolicy
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BudgetExhaustedAction(str, Enum):
    """What happens once VerifierRuntimeBudget.exhausted is true."""

    FAIL = "fail"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    DOWNGRADE_TO_ADVISORY = "downgrade_to_advisory"


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


class VerdictStrategy(str, Enum):
    """How VerifierVerdictPolicy combines N verifier verdicts into one decision."""

    ALL_BLOCKING_MUST_PASS = "all_blocking_must_pass"
    WEIGHTED_SCORE_THRESHOLD = "weighted_score_threshold"
    K_OF_N = "k_of_n"
    ANY_BLOCKING_PASSES = "any_blocking_passes"
    UNANIMOUS_ENSEMBLE = "unanimous_ensemble"


class TargetResolutionMode(str, Enum):
    """Which source VerifierTargetResolver reads to build the VerifierTarget."""

    FINAL_OUTPUT_TEXT = "final_output_text"
    WORKSPACE_FILES = "workspace_files"
    WORKSPACE_DIFF = "workspace_diff"
    STRUCTURED_SUBMISSION = "structured_submission"
    CUSTOM = "custom"


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


# ---------------------------------------------------------------------------
# Shared result/context dataclasses
# ---------------------------------------------------------------------------


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

    decision: "GateDecision"
    feedback: str | None
    repair: RepairOutcome | None


# ---------------------------------------------------------------------------
# Per-pillar Params dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifierParams:
    """Validated configuration for one Verifier instance."""

    name: str
    kind: VerifierKind
    cost_class: VerifierCostClass = VerifierCostClass.STANDARD
    tier: int = 0
    blocking: bool = True
    depends_on: tuple[str, ...] = ()
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        # Rejects a blank name, a kind that is not a real VerifierKind member, and a non-positive timeout.
        self._validate_name()
        self._validate_kind()
        self._validate_timeout()

    def _validate_name(self) -> None:
        # A verifier without a name cannot be addressed by depends_on or reported in feedback.
        if not self.name.strip():
            raise ConfigurationError("VerifierParams.name must be a non-empty string.")

    def _validate_kind(self) -> None:
        # Every verifier must declare one of the SDK's supported kinds.
        if not isinstance(self.kind, VerifierKind):
            raise ConfigurationError(f"VerifierParams.kind must be a VerifierKind member, got {self.kind!r}.")

    def _validate_timeout(self) -> None:
        # A zero or negative timeout would never let the check run.
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ConfigurationError("VerifierParams.timeout_seconds must be greater than zero when provided.")


@dataclass(frozen=True, slots=True)
class ContextPrimitiveSelectorParams:
    """Which of the agent's accumulated context-window primitives to pull into the target."""

    include_all: bool = False
    include_kinds: tuple[str, ...] = ()
    include_managed_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # include_all already selects everything, so a redundant filter is a configuration mistake, not a no-op.
        if self.include_all and (self.include_kinds or self.include_managed_ids):
            raise ConfigurationError(
                "ContextPrimitiveSelectorParams.include_all=True already selects every primitive; "
                "include_kinds/include_managed_ids would be redundant and must be left empty."
            )


@dataclass(frozen=True, slots=True)
class VerifierTargetResolverParams:
    """Validated configuration for one VerifierTargetResolver."""

    mode: TargetResolutionMode
    include_patterns: tuple[str, ...] = ()
    submission_tool_name: str | None = None
    custom_resolver: Callable[[ResolutionContext], VerifierTarget] | None = None
    context_primitives: ContextPrimitiveSelectorParams | None = None

    def __post_init__(self) -> None:
        # CUSTOM and STRUCTURED_SUBMISSION each require the one extra field their mode depends on.
        self._validate_custom_mode()
        self._validate_structured_submission_mode()

    def _validate_custom_mode(self) -> None:
        # A CUSTOM resolver with no custom_resolver has nothing to dispatch to.
        if self.mode is TargetResolutionMode.CUSTOM and self.custom_resolver is None:
            raise ConfigurationError("VerifierTargetResolverParams: mode=CUSTOM requires custom_resolver.")

    def _validate_structured_submission_mode(self) -> None:
        # Without a tool name there is nothing to scan the transcript for.
        if self.mode is TargetResolutionMode.STRUCTURED_SUBMISSION and not self.submission_tool_name:
            raise ConfigurationError("VerifierTargetResolverParams: mode=STRUCTURED_SUBMISSION requires submission_tool_name.")


@dataclass(frozen=True, slots=True)
class VerifierVerdictPolicyParams:
    """Validated configuration for one VerifierVerdictPolicy."""

    strategy: VerdictStrategy = VerdictStrategy.ALL_BLOCKING_MUST_PASS
    score_threshold: float | None = None
    weights: Mapping[str, float] | None = None
    minimum_passing: int | None = None

    def __post_init__(self) -> None:
        # Each strategy that needs a companion field must have it, and thresholds must be sane fractions.
        self._validate_weighted_threshold()
        self._validate_k_of_n()
        self._validate_threshold_range()

    def _validate_weighted_threshold(self) -> None:
        # WEIGHTED_SCORE_THRESHOLD cannot decide pass/fail without a threshold to compare against.
        if self.strategy is VerdictStrategy.WEIGHTED_SCORE_THRESHOLD and self.score_threshold is None:
            raise ConfigurationError("VerifierVerdictPolicyParams: strategy=WEIGHTED_SCORE_THRESHOLD requires score_threshold.")

    def _validate_k_of_n(self) -> None:
        # K_OF_N cannot decide pass/fail without knowing how many verdicts must pass.
        if self.strategy is VerdictStrategy.K_OF_N and self.minimum_passing is None:
            raise ConfigurationError("VerifierVerdictPolicyParams: strategy=K_OF_N requires minimum_passing.")

    def _validate_threshold_range(self) -> None:
        # A threshold outside [0, 1] can never be met or can always be met — either way it is a mistake.
        if self.score_threshold is not None and not (0.0 <= self.score_threshold <= 1.0):
            raise ConfigurationError("VerifierVerdictPolicyParams.score_threshold must be within [0.0, 1.0].")


_FEEDBACK_MODES_REQUIRING_TEMPLATE = (FeedbackContentMode.CUSTOM_MESSAGE, FeedbackContentMode.RAW_AND_CUSTOM)


@dataclass(frozen=True, slots=True)
class VerifierRuntimeFeedbackParams:
    """Validated configuration for one VerifierRuntimeFeedback."""

    content_mode: FeedbackContentMode = FeedbackContentMode.RAW_VERDICT
    delivery: FeedbackDelivery = FeedbackDelivery.USER_MESSAGE
    message_template: str | None = None
    structured_fields: tuple[str, ...] = ()
    max_diagnostics_chars: int | None = None

    def __post_init__(self) -> None:
        # Each content mode that needs a companion field must have it.
        self._validate_template_modes()
        self._validate_structured_mode()
        self._validate_max_chars()
        self._validate_delivery_supported()

    def _validate_delivery_supported(self) -> None:
        # SYSTEM_MESSAGE and MCP_RESOURCE have no wired delivery path in the linear runtime yet;
        # reject-at-construction, matching how RepairMode.PARALLEL_BRANCHING is handled.
        if self.delivery in (FeedbackDelivery.SYSTEM_MESSAGE, FeedbackDelivery.MCP_RESOURCE):
            raise ConfigurationError(
                f"VerifierRuntimeFeedbackParams: delivery={self.delivery.value} has no wired delivery path in the "
                "linear runtime today. Use USER_MESSAGE, TOOL_RESULT, or CONTEXT_ITEM."
            )

    def _validate_template_modes(self) -> None:
        # CUSTOM_MESSAGE and RAW_AND_CUSTOM both need something to render.
        if self.content_mode in _FEEDBACK_MODES_REQUIRING_TEMPLATE and not self.message_template:
            raise ConfigurationError(f"VerifierRuntimeFeedbackParams: content_mode={self.content_mode.value} requires message_template.")

    def _validate_structured_mode(self) -> None:
        # Without named fields, STRUCTURED_PAYLOAD has nothing to render.
        if self.content_mode is FeedbackContentMode.STRUCTURED_PAYLOAD and not self.structured_fields:
            raise ConfigurationError("VerifierRuntimeFeedbackParams: content_mode=STRUCTURED_PAYLOAD requires structured_fields.")

    def _validate_max_chars(self) -> None:
        # A zero or negative cap would truncate every message to nothing.
        if self.max_diagnostics_chars is not None and self.max_diagnostics_chars <= 0:
            raise ConfigurationError("VerifierRuntimeFeedbackParams.max_diagnostics_chars must be greater than zero when provided.")


@dataclass(frozen=True, slots=True)
class VerifierRepairStrategyParams:
    """Validated configuration for one VerifierRepairStrategy."""

    mode: RepairMode = RepairMode.IN_PLACE_CONTINUE
    scope_lock: bool = False
    branch_width: int | None = None

    def __post_init__(self) -> None:
        # PARALLEL_BRANCHING cannot fork attempts without knowing how many to fork.
        self._validate_branch_width_required()
        self._validate_branch_width_range()

    def _validate_branch_width_required(self) -> None:
        # Without a width, PARALLEL_BRANCHING has no concurrency degree to fork with.
        if self.mode is RepairMode.PARALLEL_BRANCHING and not self.branch_width:
            raise ConfigurationError("VerifierRepairStrategyParams: mode=PARALLEL_BRANCHING requires branch_width.")

    def _validate_branch_width_range(self) -> None:
        # A width of one is not actually branching, it is IN_PLACE_CONTINUE with extra steps.
        if self.branch_width is not None and self.branch_width < 2:
            raise ConfigurationError("VerifierRepairStrategyParams.branch_width must be at least 2 when provided.")


@dataclass(frozen=True, slots=True)
class VerifierRuntimeBudgetParams:
    """Validated configuration for one VerifierRuntimeBudget.

    Deliberately verifier-specific: cost ceilings are a general agent/loop
    concern (CostBudgetMiddleware) and are not duplicated here.
    """

    max_attempts: int
    max_total_seconds: float | None = None
    plateau_patience: int | None = None
    max_flaky_flips: int | None = None
    min_score_floor: float | None = None
    max_consecutive_failures: int | None = None
    on_exhausted: BudgetExhaustedAction = BudgetExhaustedAction.FAIL

    def __post_init__(self) -> None:
        # Every numeric ceiling must be strictly positive when provided.
        self._validate_max_attempts()
        self._validate_positive_if_present("max_total_seconds", self.max_total_seconds)
        self._validate_positive_if_present("plateau_patience", self.plateau_patience)
        self._validate_positive_if_present("max_flaky_flips", self.max_flaky_flips)
        self._validate_positive_if_present("max_consecutive_failures", self.max_consecutive_failures)
        self._validate_score_floor_range()

    def _validate_max_attempts(self) -> None:
        # A budget of zero or fewer attempts could never let the loop run once.
        if self.max_attempts <= 0:
            raise ConfigurationError("VerifierRuntimeBudgetParams.max_attempts must be greater than zero.")

    def _validate_score_floor_range(self) -> None:
        # A score floor outside [0, 1] can never be crossed or is always crossed — either way it is a mistake.
        if self.min_score_floor is not None and not (0.0 <= self.min_score_floor <= 1.0):
            raise ConfigurationError("VerifierRuntimeBudgetParams.min_score_floor must be within [0.0, 1.0] when provided.")

    @staticmethod
    def _validate_positive_if_present(name: str, value: float | int | None) -> None:
        # Mirrors ToolErrorPolicy's own "positive when provided" validation shape.
        if value is not None and value <= 0:
            raise ConfigurationError(f"VerifierRuntimeBudgetParams.{name} must be greater than zero when provided.")


@dataclass(frozen=True, slots=True)
class VerifierLedgerParams:
    """Validated configuration for one VerifierLedger."""

    run_id: str
    publish_to_context: bool = False

    def __post_init__(self) -> None:
        # A ledger with no run identity cannot be distinguished across concurrent runs in logs or metadata.
        if not self.run_id.strip():
            raise ConfigurationError("VerifierLedgerParams.run_id must be a non-empty string.")


@dataclass(frozen=True, slots=True)
class VerifierRuntimeSettingsParams:
    """Composes every verifier-runtime pillar into one configuration object.

    No __post_init__ of its own — every field's own class already validated
    itself at construction, so there is nothing left to check here.
    """

    target_resolver: "VerifierTargetResolver"
    collection: "VerifierCollection"
    gate: "VerifierRuntimeGate"
    verdict_policy: "VerifierVerdictPolicy"
    feedback: "VerifierRuntimeFeedback"
    repair_strategy: "VerifierRepairStrategy"
    budget: "VerifierRuntimeBudget"
    ledger_params: VerifierLedgerParams


__all__ = [
    "AggregatedVerdict",
    "BudgetExhaustedAction",
    "ContextPrimitiveSelectorParams",
    "FeedbackContentMode",
    "FeedbackDelivery",
    "RepairContext",
    "RepairMode",
    "RepairOutcome",
    "ResolutionContext",
    "TargetResolutionMode",
    "VerdictStrategy",
    "VerificationAttempt",
    "VerifierCostClass",
    "VerifierKind",
    "VerifierLedgerParams",
    "VerifierParams",
    "VerifierRepairStrategyParams",
    "VerifierRuntimeBudgetParams",
    "VerifierRuntimeFeedbackParams",
    "VerifierRuntimeOutcome",
    "VerifierRuntimeSettingsParams",
    "VerifierTarget",
    "VerifierTargetResolverParams",
    "VerifierVerdict",
    "VerifierVerdictPolicyParams",
]
