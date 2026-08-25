"""Context Protocol Header

Description:
    Enumerations for the batch-3 deep-family CoT monitoring tools.
Purpose:
    Gives the cot_context, cot_foraging, cot_verification, cot_delegation, and
    cot_meta tool and primitive modules a single typed source of truth for
    every categorical field they validate, instead of ad hoc string tuples
    declared per module. Each enum's original value set is preserved; members
    without that marker were derived afterward to round out the category so
    the field distinguishes more than the minimum the tool shipped with.
Architecture:
    - YesNo: shared binary decision enum reused across strictly two-state
      fields (a third or fourth state would blur, not sharpen, the signal).
    - One enum per categorical field family, shared across tools where the
      same concept recurs (Severity, Recoverability, SurpriseLevel).
Relations:
    Consumed by vidbyte.tools.builtins.cot.{context,delegation,foraging,
    verification,meta}, which derive their CotEventParser.parse_enum allowed
    tuples from these members via `tuple(member.value for member in Enum)`.
Similar Files:
    - vidbyte/lib/enums/context.py
"""

from __future__ import annotations

from enum import Enum


class YesNo(str, Enum):
    """Shared binary decision enum for strictly two-state monitoring fields."""

    YES = "yes"
    NO = "no"


class ContextCrowding(str, Enum):
    """How full and how load-bearing-at-risk the context window currently is."""

    SPACIOUS = "spacious"
    COMFORTABLE = "comfortable"
    TIGHT = "tight"
    OVERFLOWING = "overflowing"
    CRITICAL = "critical"


class FactVisibility(str, Enum):
    """Whether a fact a next step depends on is currently visible in context."""

    YES = "yes"
    PARTIALLY = "partially"
    UNSURE = "unsure"
    CACHED_ONLY = "cached_only"
    NO = "no"


class ContextImbalance(str, Enum):
    """What kind of content dominates the context window, if any."""

    NONE = "none"
    TOOL_HEAVY = "tool_heavy"
    PRIMITIVE_HEAVY = "primitive_heavy"
    CONVERSATION_HEAVY = "conversation_heavy"
    DOCUMENT_HEAVY = "document_heavy"
    MIXED = "mixed"


class Recoverability(str, Enum):
    """Whether dropped or lost information can be recovered later."""

    YES = "yes"
    PENDING = "pending"
    COSTLY = "costly"
    UNKNOWN = "unknown"
    NO = "no"


class ReloadCost(str, Enum):
    """What recovering dropped information would cost if it becomes necessary."""

    NEGLIGIBLE = "negligible"
    CHEAP = "cheap"
    MODERATE = "moderate"
    EXPENSIVE = "expensive"
    IMPOSSIBLE = "impossible"


class RecallMatchOutcome(str, Enum):
    """How a from-memory recall claim compared to its verified source."""

    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    WRONG = "wrong"
    SUPERSEDED = "superseded"
    COULD_NOT_VERIFY = "could_not_verify"


class Criticality(str, Enum):
    """How much a step's correctness hinges on the dependency being checked."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


class SearchUrgency(str, Enum):
    """How urgently a search must resolve before dependent work can proceed."""

    BACKGROUND = "background"
    EXPLORATORY = "exploratory"
    SOON = "soon"
    BLOCKING = "blocking"


class ExpectedSource(str, Enum):
    """Where a missing fact is expected to be found."""

    DOCS = "docs"
    CODE = "code"
    WEB = "web"
    DATA = "data"
    TEAMMATE = "teammate"
    MEMORY = "memory"
    CACHE = "cache"


class SearchExpectedYield(str, Enum):
    """What kind of result one planned query is expected to produce."""

    EXACT_HIT = "exact_hit"
    CONFIRMATORY = "confirmatory"
    PARTIAL = "partial"
    BROAD_SURVEY = "broad_survey"
    EXPLORATORY = "exploratory"


class SearchFoundOutcome(str, Enum):
    """What a completed search round actually yielded against expectations."""

    EXACTLY = "exactly"
    PARTIALLY = "partially"
    FOUND_ALTERNATIVE = "found_alternative"
    NOTHING = "nothing"
    INFORMATION_OVERLOAD = "information_overload"
    CONTRADICTS_EXPECTATION = "contradicts_expectation"


class SearchPivot(str, Enum):
    """The deliberate next move chosen after a search round concludes."""

    CONTINUE = "continue"
    NARROW = "narrow"
    REFINE = "refine"
    BROADEN = "broaden"
    CHANGE_TOOL = "change_tool"
    ABANDON_LINE = "abandon_line"


class SurpriseLevel(str, Enum):
    """How much an observed result diverged from what was expected."""

    EXPECTED = "expected"
    MILD = "mild"
    MODERATE = "moderate"
    SURPRISING = "surprising"
    MAJOR = "major"
    ALARMING = "alarming"


class VerificationMethod(str, Enum):
    """The verification act actually performed to check a claim."""

    RE_DERIVE = "re-derive"
    RE_RUN = "re-run"
    CROSS_CHECK = "cross-check"
    READ_BACK = "read-back"
    STATIC_ANALYSIS = "static-analysis"
    PEER_REVIEW = "peer-review"


class VerificationVerdict(str, Enum):
    """The outcome of one executed verification check."""

    PASSES = "passes"
    PARTIALLY_PASSES = "partially_passes"
    FAILS = "fails"
    CANNOT_VERIFY = "cannot_verify"
    SKIPPED = "skipped"


class Severity(str, Enum):
    """Blast radius or consequence tier shared across verification and delegation fields."""

    COSMETIC = "cosmetic"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    FATAL = "fatal"


class FixedStatus(str, Enum):
    """Whether a failed verification's underlying issue was fixed."""

    YES = "yes"
    DEFERRED = "deferred"
    NO = "no"
    WONT_FIX = "wont_fix"
    NOT_NEEDED = "not_needed"


class TestRanStatus(str, Enum):
    """Whether a named self-test was actually executed before a completion claim."""

    YES = "yes"
    PARTIALLY = "partially"
    DEFERRED = "deferred"
    NO = "no"
    NOT_POSSIBLE = "not_possible"


class TestResult(str, Enum):
    """The pass/fail outcome of an executed self-test."""

    PASSED = "passed"
    FLAKY = "flaky"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    N_A = "n_a"


class TestCoverage(str, Enum):
    """How much of the work under test a self-test actually exercises."""

    SMOKE = "smoke"
    SPOT = "spot"
    TARGETED = "targeted"
    REGRESSION = "regression"
    EXHAUSTIVE = "exhaustive"


class AgreementLevel(str, Enum):
    """Whether two independent derivation paths support the same conclusion."""

    YES = "yes"
    PARTIAL = "partial"
    UNCLEAR = "unclear"
    NO = "no"


class MatchState(str, Enum):
    """How a re-read record compared to what was held in working memory."""

    YES = "yes"
    DRIFTED = "drifted"
    SUPERSEDED = "superseded"
    CONTRADICTS = "contradicts"
    UNVERIFIABLE = "unverifiable"


class Staleness(str, Enum):
    """How long it has been since a record was last re-verified against its source."""

    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"


class ContextAttachLevel(str, Enum):
    """How much supporting context traveled with a delegated task."""

    NONE = "none"
    MINIMAL = "minimal"
    CURATED = "curated"
    MODERATE = "moderate"
    FULL = "full"


class TrustLevel(str, Enum):
    """How much a delegated result was verified before being relied on."""

    VERIFIED = "verified"
    SPOT_CHECKED = "spot_checked"
    ASSUMED = "assumed"
    DELEGATED_TRUST = "delegated_trust"
    DISTRUSTED = "distrusted"


class CriteriaOutcome(str, Enum):
    """A delegated result judged against its brief's success criteria."""

    EXCEEDED = "exceeded"
    MET = "met"
    PARTIALLY_MET = "partially_met"
    MISSED = "missed"
    GAMED = "gamed"
    UNVERIFIABLE = "unverifiable"


class RecheckCost(str, Enum):
    """What fully re-verifying a delegated result would cost right now."""

    FREE = "free"
    CHEAP = "cheap"
    MODERATE = "moderate"
    EXPENSIVE = "expensive"
    IMPOSSIBLE = "impossible"


class HandoffReason(str, Enum):
    """The primary reason a unit of work crossed an agent boundary."""

    SPECIALIZATION = "specialization"
    CAPACITY = "capacity"
    CONTEXT_LIMIT = "context_limit"
    PARALLELISM = "parallelism"
    PERMISSION_BOUNDARY = "permission_boundary"
    COST_OPTIMIZATION = "cost_optimization"


class ReadinessLevel(str, Enum):
    """Whether a receiver had what it needed to start delegated work."""

    YES = "yes"
    PARTIALLY = "partially"
    PENDING = "pending"
    UNCLEAR = "unclear"
    NO = "no"


class HandoffCompletenessGap(str, Enum):
    """What category, if any, a handoff brief was missing for its receiver."""

    NOTHING = "nothing"
    CONTEXT = "context"
    CONSTRAINTS = "constraints"
    FORMAT = "format"
    AUDIENCE = "audience"
    SUCCESS_CRITERIA = "success_criteria"


class ReviewSource(str, Enum):
    """Who audited a handoff brief for completeness."""

    SELF = "self"
    RECEIVER = "receiver"
    THIRD_PARTY = "third_party"


class FailureOwner(str, Enum):
    """The true owner of a subagent failure once attributed honestly."""

    BRIEF = "brief"
    CAPABILITY = "capability"
    CONTEXT = "context"
    ENVIRONMENT = "environment"
    TIMING = "timing"
    LUCK = "luck"


class PatternSeenBefore(str, Enum):
    """Whether this failure attribution matches a pattern seen earlier in the run."""

    YES = "yes"
    UNSURE = "unsure"
    NO = "no"


class BlockedResponse(str, Enum):
    """The chosen response to a currently blocking dependency."""

    WAIT = "wait"
    REPRIORITIZE = "reprioritize"
    NUDGE = "nudge"
    TAKE_BACK = "take_back"
    ESCALATE = "escalate"


class DisputeVerdict(str, Enum):
    """Adjudication of which side of a contradiction between two records is wrong."""

    A = "a"
    B = "b"
    BOTH = "both"
    NEITHER = "neither"
    INCONCLUSIVE = "inconclusive"


class MonitoringHealth(str, Enum):
    """Overall verdict on whether monitoring calls are pulling their weight."""

    SPARSE = "sparse"
    NEGLECTED = "neglected"
    HEALTHY = "healthy"
    HEAVY = "heavy"
    SMOTHERING = "smothering"


class GapSeverity(str, Enum):
    """How much an uncapturable telemetry gap costs a later reader."""

    MINOR = "minor"
    MODERATE = "moderate"
    NOTABLE = "notable"
    CRITICAL = "critical"
    CATASTROPHIC = "catastrophic"


class GapFrequency(str, Enum):
    """How often a telemetry gap or a description-drift mismatch recurs."""

    ONE_OFF = "one_off"
    OCCASIONAL = "occasional"
    RECURRING = "recurring"
    CONSTANT = "constant"


class DirectionChangeLevel(str, Enum):
    """How much a monitoring record actually steered the run's direction."""

    YES = "yes"
    MAJORLY = "majorly"
    SLIGHTLY = "slightly"
    NO = "no"
    REVERSED = "reversed"


class CalibrationTrend(str, Enum):
    """How self-estimated calibration has moved since the previous self-report."""

    IMPROVING = "improving"
    STABLE = "stable"
    WORSENING = "worsening"
    UNKNOWN = "unknown"


class BiasAssessment(str, Enum):
    """Self-diagnosed direction of miscalibration in one's own predictions."""

    OVERCONFIDENT = "overconfident"
    CALIBRATED = "calibrated"
    UNDERCONFIDENT = "underconfident"
    ERRATIC = "erratic"
    UNKNOWN = "unknown"


__all__ = [
    "AgreementLevel",
    "BiasAssessment",
    "BlockedResponse",
    "CalibrationTrend",
    "ContextAttachLevel",
    "ContextCrowding",
    "ContextImbalance",
    "Criticality",
    "CriteriaOutcome",
    "DirectionChangeLevel",
    "DisputeVerdict",
    "ExpectedSource",
    "FactVisibility",
    "FailureOwner",
    "FixedStatus",
    "GapFrequency",
    "GapSeverity",
    "HandoffCompletenessGap",
    "HandoffReason",
    "MatchState",
    "MonitoringHealth",
    "PatternSeenBefore",
    "ReadinessLevel",
    "RecallMatchOutcome",
    "RecheckCost",
    "Recoverability",
    "ReloadCost",
    "ReviewSource",
    "SearchExpectedYield",
    "SearchFoundOutcome",
    "SearchPivot",
    "SearchUrgency",
    "Severity",
    "Staleness",
    "SurpriseLevel",
    "TestCoverage",
    "TestRanStatus",
    "TestResult",
    "TrustLevel",
    "VerificationMethod",
    "VerificationVerdict",
    "YesNo",
]
