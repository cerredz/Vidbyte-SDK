"""Context Protocol Header

Description:
    Exposes continual tracing presets, the trace agent, and the trace middleware.
Purpose:
    Provides the public continual tracing surface: the structured-artifact trace
    agent plus the legacy in-memory capture preset.
Architecture:
    - ContinualTraceAgent: Dedicated agent that fills a typed trace schema.
    - ContinualTraceMiddleware: Injection seam that schedules trace updates.
    - ActionTrace and the seven sibling lenses: Prebuilt continual trace schemas.
    - ContinualTracer: Validated in-memory continual trace capture preset.
Relations:
    Imported by the public vidbyte.trace package and vidbyte.agents wiring.
"""

from __future__ import annotations

from vidbyte.trace.continual.base import ContinualTracer
from vidbyte.trace.continual.agent import ContinualTraceAgent
from vidbyte.trace.continual.middleware import ContinualTraceMiddleware
from vidbyte.trace.continual.prebuilt import (
    ActionTrace,
    ActionTraceModel,
    ArtifactTrace,
    ArtifactTraceModel,
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
]
