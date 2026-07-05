"""Parser semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class ParserTrace:
    """Factory for parsing and structured-output spans."""

    @staticmethod
    def tool_calls(**attributes: Any) -> SpanSpec:
        # Describes provider tool-call parsing.
        return SpanSpec("parser.tool_calls", SpanKind.PARSER, "parsers", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def structured_output(**attributes: Any) -> SpanSpec:
        # Describes structured-output validation.
        return SpanSpec("parser.structured_output", SpanKind.PARSER, "parsers", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)


__all__ = ["ParserTrace"]
