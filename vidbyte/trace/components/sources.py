"""Artifact source semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class SourceTrace:
    """Factory for artifact source trace spans."""

    @staticmethod
    def fetch(**attributes: Any) -> SpanSpec:
        # Describes an artifact source fetch operation.
        return SpanSpec("source.fetch", SpanKind.RETRIEVER, "sources", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def load(**attributes: Any) -> SpanSpec:
        # Describes an artifact source load operation.
        return SpanSpec("source.load", SpanKind.RETRIEVER, "sources", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def cache_hit(**attributes: Any) -> SpanSpec:
        # Describes a source cache hit.
        return SpanSpec("source.cache.hit", SpanKind.CHAIN, "sources", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def cache_miss(**attributes: Any) -> SpanSpec:
        # Describes a source cache miss.
        return SpanSpec("source.cache.miss", SpanKind.CHAIN, "sources", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["SourceTrace"]
