"""Context-window algorithm semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class AlgorithmTrace:
    """Factory for context-window algorithm spans."""

    @staticmethod
    def named(name: str, **attributes: Any) -> SpanSpec:
        # Describes one named algorithm phase.
        safe_name = str(name).replace("_", "-")
        return SpanSpec(f"algorithm.{safe_name}", SpanKind.CHAIN, "algorithms", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def reflexion_trial(**attributes: Any) -> SpanSpec:
        # Describes a reflexion trial phase.
        return AlgorithmTrace.named("reflexion.trial", **attributes)

    @staticmethod
    def reflexion_reflection(**attributes: Any) -> SpanSpec:
        # Describes a reflexion reflection phase.
        return AlgorithmTrace.named("reflexion.reflection", **attributes)

    @staticmethod
    def multi_provider_grader(**attributes: Any) -> SpanSpec:
        # Describes multi-provider agentic grading.
        return AlgorithmTrace.named("multi_provider_agentic_grader", **attributes)

    @staticmethod
    def trajectory_checkpoint(**attributes: Any) -> SpanSpec:
        # Describes trajectory checkpoint analysis.
        return AlgorithmTrace.named("trajectory_checkpoints", **attributes)

    @staticmethod
    def problem_space_search(**attributes: Any) -> SpanSpec:
        # Describes problem-space search context generation.
        return AlgorithmTrace.named("problem_space_search", **attributes)

    @staticmethod
    def error_correction(**attributes: Any) -> SpanSpec:
        # Describes error-correction context generation.
        return AlgorithmTrace.named("error_correction", **attributes)

    @staticmethod
    def parallel_panel(**attributes: Any) -> SpanSpec:
        # Describes the outer parallel-panel coordinator span.
        return AlgorithmTrace.named("parallel_panel", **attributes)

    @staticmethod
    def parallel_panel_producer(**attributes: Any) -> SpanSpec:
        # Describes the single producer pass that yields the shared candidate.
        return AlgorithmTrace.named("parallel_panel.producer", **attributes)

    @staticmethod
    def parallel_panel_review(**attributes: Any) -> SpanSpec:
        # Describes one isolated first-round reviewer branch.
        return AlgorithmTrace.named("parallel_panel.review", **attributes)

    @staticmethod
    def parallel_panel_barrier(**attributes: Any) -> SpanSpec:
        # Describes the first-round collection barrier after all reviewers settle.
        return AlgorithmTrace.named("parallel_panel.barrier", **attributes)

    @staticmethod
    def parallel_panel_collection(**attributes: Any) -> SpanSpec:
        # Describes ordered assembly of successful reviews and failure records.
        return AlgorithmTrace.named("parallel_panel.collection", **attributes)

    @staticmethod
    def prosecutor_defender_judge_producer(**attributes: Any) -> SpanSpec:
        # Describes the single producer pass of the prosecutor/defender/judge debate.
        return AlgorithmTrace.named("prosecutor_defender_judge.producer", **attributes)

    @staticmethod
    def prosecutor_defender_judge_prosecutor(**attributes: Any) -> SpanSpec:
        # Describes the isolated prosecutor allegation phase.
        return AlgorithmTrace.named("prosecutor_defender_judge.prosecutor", **attributes)

    @staticmethod
    def prosecutor_defender_judge_defender(**attributes: Any) -> SpanSpec:
        # Describes the isolated defender response phase.
        return AlgorithmTrace.named("prosecutor_defender_judge.defender", **attributes)

    @staticmethod
    def prosecutor_defender_judge_judge(**attributes: Any) -> SpanSpec:
        # Describes the isolated judge adjudication phase.
        return AlgorithmTrace.named("prosecutor_defender_judge.judge", **attributes)


__all__ = ["AlgorithmTrace"]
