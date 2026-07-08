"""Middleware semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class MiddlewareTrace:
    """Factory for middleware decision spans."""

    @staticmethod
    def decision(**attributes: Any) -> SpanSpec:
        # Describes a middleware decision that may change runtime control flow.
        return SpanSpec("middleware.decision", SpanKind.CHAIN, "middleware", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def hook(**attributes: Any) -> SpanSpec:
        # Describes an individual middleware hook in diagnostic mode.
        return SpanSpec("middleware.hook", SpanKind.CHAIN, "middleware", TraceDetail.DIAGNOSTIC, ParentPolicy.CURRENT, attributes)


__all__ = ["MiddlewareTrace"]
