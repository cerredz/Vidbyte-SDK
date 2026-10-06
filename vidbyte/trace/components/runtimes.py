"""Runtime semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class LinearRuntimeTrace:
    """Factory for linear agent runtime spans."""

    @staticmethod
    def iteration(**attributes: Any) -> SpanSpec:
        # Describes one model/tool loop iteration.
        return SpanSpec("runtime.iteration", SpanKind.CHAIN, "runtimes", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def stop(**attributes: Any) -> SpanSpec:
        # Describes a runtime stop condition.
        return SpanSpec("runtime.stop", SpanKind.CHAIN, "runtimes", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


class ActorRuntimeTrace:
    """Factory for actor runtime spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes an actor runtime execution.
        return SpanSpec("runtime.actor.run", SpanKind.CHAIN, "actor", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def spawn(**attributes: Any) -> SpanSpec:
        # Describes dynamic actor creation.
        return SpanSpec("runtime.actor.spawn", SpanKind.CHAIN, "actor", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def message(**attributes: Any) -> SpanSpec:
        # Describes an actor message transfer.
        return SpanSpec("runtime.actor.message", SpanKind.CHAIN, "actor", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def completion(**attributes: Any) -> SpanSpec:
        # Describes actor runtime termination.
        return SpanSpec("runtime.actor.completion", SpanKind.CHAIN, "actor", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


class SearchRuntimeTrace:
    """Factory for search runtime spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes a search runtime execution.
        return SpanSpec("runtime.search.run", SpanKind.CHAIN, "search", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def node(**attributes: Any) -> SpanSpec:
        # Describes one search node selection or expansion.
        return SpanSpec("runtime.search.node", SpanKind.CHAIN, "search", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def rollback(**attributes: Any) -> SpanSpec:
        # Describes a search rollback event.
        return SpanSpec("runtime.search.rollback", SpanKind.CHAIN, "search", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["ActorRuntimeTrace", "LinearRuntimeTrace", "SearchRuntimeTrace"]
