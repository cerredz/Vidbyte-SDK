"""Context Protocol Header

Description:
    Exports the context window recording infrastructure for slot-level tracing.
Purpose:
    Provides a single import path for all recorder types used by algorithm
    implementations and test harnesses.
Architecture:
    - Recorder types from recorder module.
Relations:
    Used by AgentRuntime, algorithm runtime adapters, and vidbyte.lib.templates.
"""

from __future__ import annotations

from vidbyte.context.templates.recorder import (
    ContextWindowRecorder,
    NullRecorder,
    RecorderBase,
    SlotEvent,
)

__all__ = [
    "ContextWindowRecorder",
    "NullRecorder",
    "RecorderBase",
    "SlotEvent",
]
