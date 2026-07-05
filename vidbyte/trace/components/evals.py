"""Evaluation harness semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class EvalTrace:
    """Factory for evaluation harness trace spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes an evaluation harness run.
        return SpanSpec("eval.run", SpanKind.CHAIN, "evals", TraceDetail.STANDARD, ParentPolicy.ROOT, attributes)

    @staticmethod
    def grade(**attributes: Any) -> SpanSpec:
        # Describes one evaluation grading step.
        return SpanSpec("eval.grade", SpanKind.CHAIN, "evals", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def behavior(**attributes: Any) -> SpanSpec:
        # Describes an evaluation behavior check.
        return SpanSpec("eval.behavior", SpanKind.CHAIN, "evals", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["EvalTrace"]
