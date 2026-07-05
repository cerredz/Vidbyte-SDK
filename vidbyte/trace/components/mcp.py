"""MCP server semantic trace span specs."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class McpTrace:
    """Factory for MCP server trace spans."""

    @staticmethod
    def attach(**attributes: Any) -> SpanSpec:
        # Describes an MCP server being attached to an agent.
        return SpanSpec("mcp.attach", SpanKind.CHAIN, "mcp", TraceDetail.STANDARD, ParentPolicy.AGENT, attributes)

    @staticmethod
    def search(**attributes: Any) -> SpanSpec:
        # Describes an MCP server tool or resource search.
        return SpanSpec("mcp.search", SpanKind.CHAIN, "mcp", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def transport(**attributes: Any) -> SpanSpec:
        # Describes an MCP transport-level operation.
        return SpanSpec("mcp.transport", SpanKind.CHAIN, "mcp", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


__all__ = ["McpTrace"]
