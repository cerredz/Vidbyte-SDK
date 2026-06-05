"""Context Protocol Header

Description:
    Exposes continual tracing presets, the trace agent, and the trace middleware.
Purpose:
    Provides the public continual tracing surface: the structured-artifact trace
    agent plus the legacy in-memory capture preset.
Architecture:
    - ContinualTraceAgent: Dedicated agent that fills a typed trace schema.
    - ContinualTraceMiddleware: Injection seam that schedules trace updates.
    - ActionTrace: Prebuilt action-oriented trace schema.
    - ContinualTracer: Validated in-memory continual trace capture preset.
Relations:
    Imported by the public vidbyte.trace package and vidbyte.agents wiring.
"""

from __future__ import annotations

from vidbyte.trace.continual.base import ContinualTracer
from vidbyte.trace.continual.agent import ContinualTraceAgent
from vidbyte.trace.continual.middleware import ContinualTraceMiddleware
from vidbyte.trace.continual.prebuilt import ActionTrace, ActionTraceModel

__all__ = [
    "ActionTrace",
    "ActionTraceModel",
    "ContinualTraceAgent",
    "ContinualTraceMiddleware",
    "ContinualTracer",
]
