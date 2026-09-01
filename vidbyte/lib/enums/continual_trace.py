"""FILE: vidbyte/lib/enums/continual_trace.py

PURPOSE: Defines the closed string vocabularies used by the nested performance-focused prebuilt continual trace schemas (HierarchicalTaskTreeTrace, CalibrationTrace, ErrorTaxonomyTrace, SelfConsistencyEnsembleTrace, CounterfactualAlternativesTrace).
ROLE IN CODEBASE: `vidbyte/trace/continual/prebuilt.py` annotates Pydantic submodel fields with these enums; TraceSchema.from_model maps a `str, Enum` annotation to TraceFieldType.STRING with no special-casing, since every member is also a plain string.
ARCHITECTURE NOTE: These enums live in `vidbyte.lib` rather than inline in `prebuilt.py` because the vocabulary is a shared SDK contract a trace-consuming reader may need to recognize independently of any one schema's source file.
COMMON MODIFICATION PATTERNS: Add a new member here first, then update the field description in `prebuilt.py` that names the closed set. Preserve a released member's serialized value, since accumulated trace artifacts may already contain it.
WHAT NOT TO DO IN THIS FILE: Do not add parsing, validation, or trace-merge logic; those belong to `vidbyte/tools/continual_trace.py`. Do not duplicate a vocabulary that already exists elsewhere in `vidbyte/lib/enums`.
KNOWN EDGE CASES: Enum members are also strings, but callers should serialize `.value` or use `values()` rather than relying on enum display formatting.
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


class PathQualityVerdict(ContinualTraceEnum):
    """Current read on the efficiency and safety of the steps taken so far."""

    EFFICIENT = "efficient"
    INEFFICIENT = "inefficient"
    RISKY = "risky"
    BLOCKED = "blocked"


class AnswerCorrectnessVerdict(ContinualTraceEnum):
    """Current read on whether the agent's stated claims hold up against evidence."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    PARTIAL = "partial"


class GoalSuccessErrorType(ContinualTraceEnum):
    """Category of mistake that prevents the agent's output from satisfying its stated goal."""

    MISUNDERSTOOD_INTENT = "misunderstood_intent"
    IGNORED_CONSTRAINT = "ignored_constraint"
    PREMATURE_TERMINATION = "premature_termination"
    INCOMPLETE_EXECUTION = "incomplete_execution"
    SCOPE_OVERREACH = "scope_overreach"


class PathQualityErrorType(ContinualTraceEnum):
    """Category of mistake in how the agent went about the task, independent of the outcome."""

    REDUNDANT_REASONING = "redundant_reasoning"
    UNSAFE_TOOL_USE = "unsafe_tool_use"
    POOR_PLANNING = "poor_planning"
    FAILED_RECOVERY = "failed_recovery"
    IGNORED_AVAILABLE_SHORTCUT = "ignored_available_shortcut"


class AnswerCorrectnessErrorType(ContinualTraceEnum):
    """Category of mistake in the factual content of the agent's stated claims."""

    HALLUCINATED_FACT = "hallucinated_fact"
    STALE_INFORMATION = "stale_information"
    MISATTRIBUTED_SOURCE = "misattributed_source"
    LOGICAL_INCONSISTENCY = "logical_inconsistency"
    OVERGENERALIZATION = "overgeneralization"


class CalibratedAxis(ContinualTraceEnum):
    """Which of the three performance axes a calibration comparison currently refers to."""

    GOAL = "goal"
    PATH = "path"
    CORRECTNESS = "correctness"
    INSUFFICIENT_DATA = "insufficient_data"


class CalibrationTrend(ContinualTraceEnum):
    """Direction a self-reported confidence estimate is moving relative to its own past accuracy."""

    IMPROVING = "improving"
    WORSENING = "worsening"
    STABLE = "stable"


class JudgmentStability(ContinualTraceEnum):
    """Whether repeated independent judgments of the same axis are converging, diverging, or holding steady."""

    CONVERGING = "converging"
    DIVERGING = "diverging"
    STABLE = "stable"


class PathRegretAssessment(ContinualTraceEnum):
    """Retrospective read on whether a past decision point, judged after the fact, was the right call."""

    CORRECT_CHOICE = "correct_choice"
    ALTERNATIVE_WOULD_HAVE_BEEN_BETTER = "alternative_would_have_been_better"
    UNCLEAR = "unclear"


__all__ = [
    "AnswerCorrectnessErrorType",
    "AnswerCorrectnessVerdict",
    "CalibratedAxis",
    "CalibrationTrend",
    "ContinualTraceEnum",
    "GoalSuccessErrorType",
    "GoalSuccessVerdict",
    "JudgmentStability",
    "PathQualityErrorType",
    "PathQualityVerdict",
    "PathRegretAssessment",
]
