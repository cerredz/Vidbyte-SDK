"""Context Protocol Header

Description:
    Exposes the public Trace facade and the continual trace agent surface.
Purpose:
    Gives agent users simple trace helper methods and the structured continual
    trace artifact agent while preserving the internal TracerBase runtime contract.
Architecture:
    - Trace: Tracer client namespace for built-in and provider-backed tracers.
    - DebugTracer: In-memory tracer from vidbyte.trace.debug.
    - SessionTracer: Session wrapper that groups many agent runs under one root.
    - ContinualTracer: Continual trace capture preset from vidbyte.trace.continual.
    - ContinualTraceAgent / ContinualTraceMiddleware: Structured trace artifact agent.
    - TraceOption / TraceSchema / ActionTrace: Continual trace configuration.
Relations:
    Wraps vidbyte.lib.tracing and vidbyte.providers.tracing for public use; consumes
    vidbyte.lib.dataclasses.trace contracts.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType, TraceMode, TraceOption, TraceSchema
from vidbyte.trace.base import Trace
from vidbyte.trace.continual import ActionTrace, ContinualTraceAgent, ContinualTraceMiddleware, ContinualTracer
from vidbyte.trace.debug import DebugTracer
from vidbyte.trace.session import SessionTracer

__all__ = [
    "ActionTrace",
    "ContinualTraceAgent",
    "ContinualTraceMiddleware",
    "ContinualTracer",
    "DebugTracer",
    "SessionTracer",
    "Trace",
    "TraceField",
    "TraceFieldType",
    "TraceMode",
    "TraceOption",
    "TraceSchema",
]
