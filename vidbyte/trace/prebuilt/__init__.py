"""Context Protocol Header

Description:
    Exposes SDK-provided continual trace schemas.
Purpose:
    Lets callers import reusable schemas for TraceOption.continual(...).
Architecture:
    Re-exports prebuilt TraceSchema constants from focused modules.
Relations:
    Used by README examples, tests, and user-facing skills.
"""

from __future__ import annotations

from vidbyte.trace.prebuilt.action import ActionTrace, ActionTraceModel
from vidbyte.trace.prebuilt.debug import DebugTrace, DebugTraceModel

__all__ = [
    "ActionTrace",
    "ActionTraceModel",
    "DebugTrace",
    "DebugTraceModel",
]
