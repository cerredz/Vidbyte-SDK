"""Session semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class SessionTrace:
    """Factory for session-level trace spans."""

    @staticmethod
    def start(**attributes: Any) -> SpanSpec:
        # Describes a session being started.
        return SpanSpec("session.start", SpanKind.CHAIN, "sessions", TraceDetail.STANDARD, ParentPolicy.ROOT, attributes)

    @staticmethod
    def end(**attributes: Any) -> SpanSpec:
        # Describes a session being ended.
        return SpanSpec("session.end", SpanKind.CHAIN, "sessions", TraceDetail.STANDARD, ParentPolicy.ROOT, attributes)

    @staticmethod
    def case(**attributes: Any) -> SpanSpec:
        # Describes one session case invocation.
        return SpanSpec("session.case", SpanKind.CHAIN, "sessions", TraceDetail.VERBOSE, ParentPolicy.SESSION, attributes)


__all__ = ["SessionTrace"]
