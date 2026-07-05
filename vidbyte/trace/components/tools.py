"""Tool semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class ToolTrace:
    """Factory for tool call spans."""

    @staticmethod
    def call(**attributes: Any) -> SpanSpec:
        # Describes one tool invocation.
        return SpanSpec("tool.call", SpanKind.TOOL, "tools", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def permission(**attributes: Any) -> SpanSpec:
        # Describes tool permission evaluation.
        return SpanSpec("tool.permission", SpanKind.TOOL, "tools", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)


__all__ = ["ToolTrace"]
