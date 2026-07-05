"""Handoff lifecycle semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class HandoffTrace:
    """Factory for agent handoff trace spans."""

    @staticmethod
    def generate(**attributes: Any) -> SpanSpec:
        # Describes a handoff document being generated.
        return SpanSpec("handoff.generate", SpanKind.CHAIN, "handoff", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def validate(**attributes: Any) -> SpanSpec:
        # Describes a handoff document being validated.
        return SpanSpec("handoff.validate", SpanKind.CHAIN, "handoff", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def record(**attributes: Any) -> SpanSpec:
        # Describes a handoff being recorded to durable storage.
        return SpanSpec("handoff.record", SpanKind.CHAIN, "handoff", TraceDetail.STANDARD, ParentPolicy.AGENT, attributes)

    @staticmethod
    def sync(**attributes: Any) -> SpanSpec:
        # Describes a handoff being synced across agents.
        return SpanSpec("handoff.sync", SpanKind.CHAIN, "handoff", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)


__all__ = ["HandoffTrace"]
