"""Context Protocol Header

Description:
    Exposes the SDK-provided prebuilt continual trace schemas.
Purpose:
    Lets callers import reusable typed schemas for TraceOption.continual(...), each a
    distinct lens over an agent run (action, plan, reasoning, history, tools,
    decisions, artifacts, knowledge).
Architecture:
    Re-exports prebuilt TraceSchema constants and their Pydantic models from one
    focused module per schema.
Relations:
    Re-exported by vidbyte.trace.continual, vidbyte.trace, and root vidbyte.
"""

from __future__ import annotations

from vidbyte.trace.continual.prebuilt.action import ActionTrace, ActionTraceModel
from vidbyte.trace.continual.prebuilt.artifact import ArtifactTrace, ArtifactTraceModel
from vidbyte.trace.continual.prebuilt.decision import DecisionTrace, DecisionTraceModel
from vidbyte.trace.continual.prebuilt.history import HistoryTrace, HistoryTraceModel
from vidbyte.trace.continual.prebuilt.knowledge import KnowledgeTrace, KnowledgeTraceModel
from vidbyte.trace.continual.prebuilt.plan import PlanTrace, PlanTraceModel
from vidbyte.trace.continual.prebuilt.reasoning import ReasoningTrace, ReasoningTraceModel
from vidbyte.trace.continual.prebuilt.tool import ToolTrace, ToolTraceModel

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
]
