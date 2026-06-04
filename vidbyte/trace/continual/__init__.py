"""Context Protocol Header

Description:
    Public package for continual-trace runtime scheduling.
Purpose:
    Houses the per-run controller that drives ContinualTraceAgent updates from the
    direct linear AgentRuntime, keeping trace runtime logic out of runtime.py.
Architecture:
    Re-exports ContinualTraceController from the controller module.
Relations:
    Imported by vidbyte.agents.runtime and depends on vidbyte.agents.continual_trace.
"""

from __future__ import annotations

from vidbyte.trace.continual.controller import ContinualTraceController

__all__ = [
    "ContinualTraceController",
]
