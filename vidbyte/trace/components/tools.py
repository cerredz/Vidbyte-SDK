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

    @staticmethod
    def resolve(**attributes: Any) -> SpanSpec:
        # Describes a tool being looked up in the registry.
        return SpanSpec("tool.resolve", SpanKind.TOOL, "tools", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def validate(**attributes: Any) -> SpanSpec:
        # Describes tool call argument validation.
        return SpanSpec("tool.validate", SpanKind.TOOL, "tools", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def deny(**attributes: Any) -> SpanSpec:
        # Describes a tool call being denied by permission policy.
        return SpanSpec("tool.deny", SpanKind.TOOL, "tools", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def error(**attributes: Any) -> SpanSpec:
        # Describes a tool execution raising an exception.
        return SpanSpec("tool.error", SpanKind.TOOL, "tools", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def compact(**attributes: Any) -> SpanSpec:
        # Describes a tool result being compacted by admission policy.
        return SpanSpec("tool.compact", SpanKind.TOOL, "tools", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def parallel_batch(**attributes: Any) -> SpanSpec:
        # Describes a batch of parallel tool calls being dispatched.
        return SpanSpec("tool.parallel_batch", SpanKind.TOOL, "tools", TraceDetail.VERBOSE, ParentPolicy.RUNTIME_ITERATION, attributes)

    @staticmethod
    def mcp_invoke(**attributes: Any) -> SpanSpec:
        # Describes an MCP tool being invoked.
        return SpanSpec("tool.mcp.invoke", SpanKind.TOOL, "tools", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def mcp_attach(**attributes: Any) -> SpanSpec:
        # Describes an MCP server being attached to the tool catalog.
        return SpanSpec("tool.mcp.attach", SpanKind.TOOL, "tools", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)


__all__ = ["ToolTrace"]
