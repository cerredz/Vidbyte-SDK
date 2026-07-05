"""Agent semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class AgentTrace:
    """Factory for single-agent semantic spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes the root agent run.
        return SpanSpec("agent.run", SpanKind.CHAIN, "agents", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def stop(**attributes: Any) -> SpanSpec:
        # Describes a final agent stop event.
        return SpanSpec("agent.stop", SpanKind.CHAIN, "agents", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)


class AggregateTrace:
    """Factory for aggregate-agent semantic spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes the overall aggregate fan-out and synthesis run.
        return SpanSpec("aggregate.run", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def proposer(**attributes: Any) -> SpanSpec:
        # Describes one aggregate proposer phase.
        return SpanSpec("aggregate.proposer", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def synthesis(**attributes: Any) -> SpanSpec:
        # Describes the aggregate synthesis phase.
        return SpanSpec("aggregate.synthesis", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def failure(**attributes: Any) -> SpanSpec:
        # Describes an aggregate failure while preserving normal error propagation.
        return SpanSpec("aggregate.failure", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["AgentTrace", "AggregateTrace"]
