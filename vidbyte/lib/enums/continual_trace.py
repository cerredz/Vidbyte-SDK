"""FILE: vidbyte/lib/enums/continual_trace.py

PURPOSE: Defines the closed string vocabularies used by the nested performance-focused prebuilt continual trace schemas (HierarchicalTaskTreeTrace, CalibrationTrace, ErrorTaxonomyTrace, SelfConsistencyEnsembleTrace, CounterfactualAlternativesTrace).
ROLE IN CODEBASE: `vidbyte/trace/continual/prebuilt.py` and `vidbyte/trace/continual/prebuilt_events.py` annotate Pydantic submodel fields with these enums; TraceSchema.from_model maps a `str, Enum` annotation to TraceFieldType.STRING with no special-casing, since every member is also a plain string.
ARCHITECTURE NOTE: These enums live in `vidbyte.lib` rather than inline in either prebuilt file because the vocabulary is a shared SDK contract a trace-consuming reader may need to recognize independently of any one schema's source file. Each closed set is kept deliberately non-overlapping with its siblings: the three *ErrorType enums each own a distinct kind of mistake (goal-success intent, in-process conduct, factual content), and ErrorSeverity is factored out as its own axis-independent scale rather than folded into any single ErrorType, so severity can be attached uniformly to a goal-success error, a path-quality error, a correctness error, or a decision-point regret without duplicating members across enums.
COMMON MODIFICATION PATTERNS: Add a new member here first, then update the field description in `prebuilt.py`/`prebuilt_events.py` that names the closed set. Preserve a released member's serialized value, since accumulated trace artifacts may already contain it. When adding a member to one of the three *ErrorType enums, check the other two first so the new member does not duplicate a category that already belongs to a sibling enum.
WHAT NOT TO DO IN THIS FILE: Do not add parsing, validation, or trace-merge logic; those belong to `vidbyte/tools/continual_trace.py`. Do not duplicate a vocabulary that already exists elsewhere in `vidbyte/lib/enums`. Do not add a member to one of the three *ErrorType enums that overlaps a category already owned by a sibling *ErrorType enum — narrow the wording or place it on the correct axis instead.
KNOWN EDGE CASES: Enum members are also strings, but callers should serialize `.value` or use `values()` rather than relying on enum display formatting. CalibratedAxis includes pairwise-tie members (e.g. GOAL_AND_PATH_TIED) in addition to the three single-axis members, because CalibrationTraceModel's best_calibrated_axis/worst_calibrated_axis fields have no other way to represent a genuine tie between two axes without one of them being silently dropped.
RELATED DOCS: docs/design/nested-continual-trace-shapes.md, field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised indirectly by scripts/test-continual-trace.py's nested-schema cases.
"""

from __future__ import annotations

from enum import Enum


class ContinualTraceEnum(str, Enum):
    """Base enum that exposes canonical serialized values for continual-trace vocabularies."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class GoalSuccessVerdict(ContinualTraceEnum):
    """Current read on whether the agent's stated goal is being met."""

    ACHIEVED = "achieved"
    IN_PROGRESS = "in_progress"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"
    REGRESSED = "regressed"
    BLOCKED_EXTERNALLY = "blocked_externally"
    SUPERSEDED = "superseded"


class PathQualityVerdict(ContinualTraceEnum):
    """Current read on the efficiency and safety of the steps taken so far."""

    EFFICIENT = "efficient"
    INEFFICIENT = "inefficient"
    RISKY = "risky"
    BLOCKED = "blocked"
    REDUNDANT = "redundant"
    OVERCAUTIOUS = "overcautious"
    UNVERIFIABLE = "unverifiable"
    RECOVERING = "recovering"


class AnswerCorrectnessVerdict(ContinualTraceEnum):
    """Current read on whether the agent's stated claims hold up against evidence."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    PARTIAL = "partial"
    STALE = "stale"
    UNVERIFIABLE = "unverifiable"
    SELF_CONTRADICTORY = "self_contradictory"
    PENDING_VERIFICATION = "pending_verification"


class GoalSuccessErrorType(ContinualTraceEnum):
    """Category of mistake that prevents the agent's output from satisfying its stated goal."""

    MISUNDERSTOOD_INTENT = "misunderstood_intent"
    IGNORED_CONSTRAINT = "ignored_constraint"
    PREMATURE_TERMINATION = "premature_termination"
    INCOMPLETE_EXECUTION = "incomplete_execution"
    SCOPE_OVERREACH = "scope_overreach"
    GOAL_DRIFT = "goal_drift"
    OVERCLAIMED_COMPLETION = "overclaimed_completion"
    MISSED_IMPLICIT_REQUIREMENT = "missed_implicit_requirement"


class PathQualityErrorType(ContinualTraceEnum):
    """Category of mistake in how the agent went about the task, independent of the outcome."""

    REDUNDANT_REASONING = "redundant_reasoning"
    UNSAFE_TOOL_USE = "unsafe_tool_use"
    POOR_PLANNING = "poor_planning"
    FAILED_RECOVERY = "failed_recovery"
    IGNORED_AVAILABLE_SHORTCUT = "ignored_available_shortcut"
    EXCESSIVE_BACKTRACKING = "excessive_backtracking"
    TOOL_MISUSE = "tool_misuse"
    CONTEXT_MISMANAGEMENT = "context_mismanagement"


class AnswerCorrectnessErrorType(ContinualTraceEnum):
    """Category of mistake in the factual content of the agent's stated claims."""

    HALLUCINATED_FACT = "hallucinated_fact"
    STALE_INFORMATION = "stale_information"
    MISATTRIBUTED_SOURCE = "misattributed_source"
    LOGICAL_INCONSISTENCY = "logical_inconsistency"
    OVERGENERALIZATION = "overgeneralization"
    UNSUPPORTED_INFERENCE = "unsupported_inference"
    CONFLATED_CONCEPTS = "conflated_concepts"
    OUTDATED_ASSUMPTION = "outdated_assumption"


class ErrorSeverity(ContinualTraceEnum):
    """How much a single classified mistake actually matters, independent of which axis or category it belongs to.

    Kept as its own enum rather than folded into GoalSuccessErrorType, PathQualityErrorType, or
    AnswerCorrectnessErrorType so the same ascending severity scale can be attached uniformly to an
    error event on any axis, and to a path-decision regret, without tripling the number of members
    those category enums would otherwise need.
    """

    TRIVIAL = "trivial"
    MINOR = "minor"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"
    MAJOR = "major"
    SEVERE = "severe"
    CRITICAL = "critical"
    CATASTROPHIC = "catastrophic"


class CalibratedAxis(ContinualTraceEnum):
    """Which of the three performance axes a calibration comparison currently refers to, including pairwise-tie states.

    The single-axis members (GOAL, PATH, CORRECTNESS) cover the ordinary case where one axis is
    clearly best- or worst-calibrated. The *_TIED and ALL_AXES_EQUAL members exist because a
    field like CalibrationTraceModel.best_calibrated_axis has no other way to represent a genuine
    tie between two or three axes without arbitrarily picking a winner and silently discarding
    the tie itself as information.
    """

    GOAL = "goal"
    PATH = "path"
    CORRECTNESS = "correctness"
    INSUFFICIENT_DATA = "insufficient_data"
    ALL_AXES_EQUAL = "all_axes_equal"
    GOAL_AND_PATH_TIED = "goal_and_path_tied"
    GOAL_AND_CORRECTNESS_TIED = "goal_and_correctness_tied"
    PATH_AND_CORRECTNESS_TIED = "path_and_correctness_tied"


class CalibrationTrend(ContinualTraceEnum):
    """Direction a self-reported confidence estimate is moving relative to its own past accuracy."""

    IMPROVING = "improving"
    WORSENING = "worsening"
    STABLE = "stable"
    RAPIDLY_IMPROVING = "rapidly_improving"
    RAPIDLY_WORSENING = "rapidly_worsening"
    RECOVERING = "recovering"
    VOLATILE = "volatile"
    INSUFFICIENT_DATA = "insufficient_data"


class JudgmentStability(ContinualTraceEnum):
    """Whether repeated independent judgments of the same axis are converging, diverging, or holding steady."""

    CONVERGING = "converging"
    DIVERGING = "diverging"
    STABLE = "stable"
    UNANIMOUS = "unanimous"
    SPLIT = "split"
    RECONVERGING = "reconverging"
    VOLATILE = "volatile"
    INSUFFICIENT_DATA = "insufficient_data"


class PathRegretAssessment(ContinualTraceEnum):
    """Retrospective read on whether a past decision point, judged after the fact, was the right call."""

    CORRECT_CHOICE = "correct_choice"
    ALTERNATIVE_WOULD_HAVE_BEEN_BETTER = "alternative_would_have_been_better"
    UNCLEAR = "unclear"
    MARGINALLY_WORSE = "marginally_worse"
    SIGNIFICANTLY_WORSE = "significantly_worse"
    EQUALLY_VALID = "equally_valid"
    TOO_EARLY_TO_ASSESS = "too_early_to_assess"
    CONTEXT_DEPENDENT = "context_dependent"


__all__ = [
    "AnswerCorrectnessErrorType",
    "AnswerCorrectnessVerdict",
    "CalibratedAxis",
    "CalibrationTrend",
    "ContinualTraceEnum",
    "ErrorSeverity",
    "GoalSuccessErrorType",
    "GoalSuccessVerdict",
    "JudgmentStability",
    "PathQualityErrorType",
    "PathQualityVerdict",
    "PathRegretAssessment",
]
