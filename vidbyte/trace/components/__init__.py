"""Context Protocol Header

Description:
    Re-exports Vidbyte-owned semantic trace span-spec factories by subsystem.
Purpose:
    Gives controllers and callers a stable entry point for agent, aggregate, multi-agent, runtime, context, tool, parser, and middleware spans.
Architecture:
    Each exported factory creates declarative `SpanSpec` values; provider translation and tracer I/O remain outside this package.
Relations:
    Consumed by trace controllers and feature implementations, including the ledger-driven `MultiAgent` controller.
"""

from __future__ import annotations

from vidbyte.trace.components.agents import AgentTrace, AggregateTrace, MultiAgentTrace
from vidbyte.trace.components.algorithms import AlgorithmTrace
from vidbyte.trace.components.context import ContextTrace
from vidbyte.trace.components.middleware import MiddlewareTrace
from vidbyte.trace.components.parsers import ParserTrace
from vidbyte.trace.components.runtimes import (
    ActorRuntimeTrace,
    LinearRuntimeTrace,
    SearchRuntimeTrace,
)
from vidbyte.trace.components.tools import ToolTrace

__all__ = [
    "ActorRuntimeTrace",
    "AgentTrace",
    "AggregateTrace",
    "AlgorithmTrace",
    "ContextTrace",
    "LinearRuntimeTrace",
    "MiddlewareTrace",
    "MultiAgentTrace",
    "ParserTrace",
    "SearchRuntimeTrace",
    "ToolTrace",
]
