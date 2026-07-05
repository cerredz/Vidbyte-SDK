"""Pipeline orchestration semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class PipelineTrace:
    """Factory for pipeline orchestration trace spans."""

    @staticmethod
    def sequential_run(**attributes: Any) -> SpanSpec:
        # Describes a sequential pipeline run.
        return SpanSpec("pipeline.sequential.run", SpanKind.CHAIN, "pipelines", TraceDetail.STANDARD, ParentPolicy.ROOT, attributes)

    @staticmethod
    def parallel_run(**attributes: Any) -> SpanSpec:
        # Describes a parallel pipeline run.
        return SpanSpec("pipeline.parallel.run", SpanKind.CHAIN, "pipelines", TraceDetail.STANDARD, ParentPolicy.ROOT, attributes)

    @staticmethod
    def conditional_run(**attributes: Any) -> SpanSpec:
        # Describes a conditional pipeline run.
        return SpanSpec("pipeline.conditional.run", SpanKind.CHAIN, "pipelines", TraceDetail.STANDARD, ParentPolicy.ROOT, attributes)

    @staticmethod
    def map_reduce_run(**attributes: Any) -> SpanSpec:
        # Describes a map-reduce pipeline run.
        return SpanSpec("pipeline.map_reduce.run", SpanKind.CHAIN, "pipelines", TraceDetail.STANDARD, ParentPolicy.ROOT, attributes)

    @staticmethod
    def stage_invoke(**attributes: Any) -> SpanSpec:
        # Describes one pipeline stage being invoked.
        return SpanSpec("pipeline.stage.invoke", SpanKind.CHAIN, "pipelines", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["PipelineTrace"]
