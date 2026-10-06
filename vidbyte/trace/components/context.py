"""Context-window semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class ContextTrace:
    """Factory for context-window and context primitive spans."""

    @staticmethod
    def window_build(**attributes: Any) -> SpanSpec:
        # Describes context-window construction for an iteration.
        return SpanSpec("context.window.build", SpanKind.PROMPT, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def primitive_render(**attributes: Any) -> SpanSpec:
        # Describes context primitive rendering.
        return SpanSpec("context.primitive.render", SpanKind.PROMPT, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def compaction(**attributes: Any) -> SpanSpec:
        # Describes context compaction or truncation.
        return SpanSpec("context.compaction", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def update(**attributes: Any) -> SpanSpec:
        # Describes a context object update.
        return SpanSpec("context.update", SpanKind.CHAIN, "context", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["ContextTrace"]
