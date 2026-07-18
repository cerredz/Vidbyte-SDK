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
    def critique_adjudicate_revise(**attributes: Any) -> SpanSpec:
        # Describes the outer critique-adjudicate-revise orchestration span.
        return AlgorithmTrace.named("critique_adjudicate_revise", **attributes)

    @staticmethod
    def critique_adjudicate_revise_producer(**attributes: Any) -> SpanSpec:
        # Describes the single producer pass before critique fan-out.
        return AlgorithmTrace.named("critique_adjudicate_revise.producer", **attributes)

    @staticmethod
    def critique_adjudicate_revise_critic(**attributes: Any) -> SpanSpec:
        # Describes one isolated critic branch in the first-round barrier.
        return AlgorithmTrace.named("critique_adjudicate_revise.critic", **attributes)

    @staticmethod
    def critique_adjudicate_revise_adjudicator(**attributes: Any) -> SpanSpec:
        # Describes the reference-only adjudication stage.
        return AlgorithmTrace.named("critique_adjudicate_revise.adjudicator", **attributes)

    @staticmethod
    def critique_adjudicate_revise_revision(**attributes: Any) -> SpanSpec:
        # Describes the accepted-findings-only revision stage.
        return AlgorithmTrace.named("critique_adjudicate_revise.revision", **attributes)


__all__ = ["AlgorithmTrace"]
