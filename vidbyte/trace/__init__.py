"""Context Protocol Header

Description:
    Exposes the public Trace facade and the continual trace agent surface.
Purpose:
    Gives agent users simple trace helper methods and the structured continual
    trace artifact agent while preserving the internal TracerBase runtime contract.
Architecture:
    - Trace: Tracer client namespace for built-in and provider-backed tracers.
    - DebugTracer: In-memory tracer from vidbyte.trace.debug.
    - ContinualTracer: Continual trace capture preset from vidbyte.trace.continual.
    - ContinualTraceAgent / ContinualTraceMiddleware: Structured trace artifact agent.
    - TraceOption / TraceSchema / prebuilt schemas: Continual trace configuration.
Relations:
    Wraps vidbyte.lib.tracing and vidbyte.providers.tracing for public use; consumes
    vidbyte.lib.dataclasses.trace contracts.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType, TraceMode, TraceOption, TraceSchema
from vidbyte.trace.base import Trace
from vidbyte.trace.continual import (
    ActionTrace,
    ActionTraceModel,
    ArtifactTrace,
    ArtifactTraceModel,
    ContinualTraceAgent,
    ContinualTraceMiddleware,
    ContinualTracer,
    DecisionTrace,
    DecisionTraceModel,
    HistoryTrace,
    HistoryTraceModel,
    KnowledgeTrace,
    KnowledgeTraceModel,
    PlanTrace,
    PlanTraceModel,
    ReasoningTrace,
    ReasoningTraceModel,
    ToolTrace,
    ToolTraceModel,
)
from vidbyte.trace.debug import DebugTracer

__all__ = [
    "ActionTrace",
    "ActionTraceModel",
    "ArtifactTrace",
    "ArtifactTraceModel",
    "DecisionTrace",
    "DecisionTraceModel",
    "HistoryTrace",
    "HistoryTraceModel",
    "KnowledgeTrace",
    "KnowledgeTraceModel",
    "PlanTrace",
    "PlanTraceModel",
    "ReasoningTrace",
    "ReasoningTraceModel",
    "ToolTrace",
    "ToolTraceModel",
    "ContinualTraceAgent",
    "ContinualTraceMiddleware",
    "ContinualTracer",
    "DebugTracer",
    "Trace",
    "TraceField",
    "TraceFieldType",
    "TraceMode",
    "TraceOption",
    "TraceSchema",
]
