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

    @staticmethod
    def is_done(**attributes: Any) -> SpanSpec:
        # Describes the is_done tool signal being parsed.
        return SpanSpec("parser.is_done", SpanKind.PARSER, "parsers", TraceDetail.VERBOSE, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def response_format_built(**attributes: Any) -> SpanSpec:
        # Describes a provider response format being constructed from an output schema.
        return SpanSpec("parser.response_format_built", SpanKind.PARSER, "parsers", TraceDetail.DIAGNOSTIC, ParentPolicy.AGENT, attributes)


__all__ = ["ParserTrace"]
