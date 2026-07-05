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

    @staticmethod
    def model_call(**attributes: Any) -> SpanSpec:
        # Describes a model call within a linear runtime iteration.
        return SpanSpec("runtime.linear.model_call", SpanKind.LLM, "runtimes", TraceDetail.STANDARD, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def tool_batch(**attributes: Any) -> SpanSpec:
        # Describes a batch of tool calls within a linear runtime iteration.
        return SpanSpec("runtime.linear.tool_batch", SpanKind.TOOL, "runtimes", TraceDetail.VERBOSE, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def stop_condition(**attributes: Any) -> SpanSpec:
        # Describes a specific AgentStopReason that terminated the loop.
        return SpanSpec("runtime.linear.stop_condition", SpanKind.CHAIN, "runtimes", TraceDetail.STANDARD, ParentPolicy.AGENT, attributes)


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

    @staticmethod
    def quiescence(**attributes: Any) -> SpanSpec:
        # Describes an actor runtime quiescence check.
        return SpanSpec("runtime.actor.quiescence", SpanKind.CHAIN, "actor", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def compile_prompt(**attributes: Any) -> SpanSpec:
        # Describes an actor prompt being compiled from a message.
        return SpanSpec("runtime.actor.compile_prompt", SpanKind.CHAIN, "actor", TraceDetail.DIAGNOSTIC, ParentPolicy.CURRENT, attributes)


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

    @staticmethod
    def expand(**attributes: Any) -> SpanSpec:
        # Describes a search node expansion step.
        return SpanSpec("runtime.search.expand", SpanKind.CHAIN, "search", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def evaluate(**attributes: Any) -> SpanSpec:
        # Describes a search node evaluation step.
        return SpanSpec("runtime.search.evaluate", SpanKind.CHAIN, "search", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def select(**attributes: Any) -> SpanSpec:
        # Describes a best-node selection step.
        return SpanSpec("runtime.search.select", SpanKind.CHAIN, "search", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["ActorRuntimeTrace", "LinearRuntimeTrace", "SearchRuntimeTrace"]
