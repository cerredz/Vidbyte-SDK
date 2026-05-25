"""Context Protocol Header

Description:
    Exposes context-window algorithm implementations.
Purpose:
    Keeps runtime context algorithms separate from preset registration and
    public context primitives.
Architecture:
    - Tool-result admission algorithms from tool_results.
Relations:
    Used by vidbyte.context.presets and AgentRuntime.
"""

from __future__ import annotations

from vidbyte.context.algorithms.tool_results import (
    ContextWindowAlgorithm,
    ToolResultAdmission,
)

__all__ = [
    "ContextWindowAlgorithm",
    "ToolResultAdmission",
]
