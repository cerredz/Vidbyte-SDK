"""Context Protocol Header

Description:
    Compatibility shim re-exporting the configuration dataclasses from their central home.
Purpose:
    The declarative configuration dataclasses now live in vidbyte.lib.dataclasses so all
    SDK data contracts share one namespace; this module keeps vidbyte.config.types as a
    stable import path for the public configuration feature.
Architecture:
    - Re-exports the polymorphic AgentSettings hierarchy plus the nested ToolDefinition and
      MiddlewareDefinition entries.
Relations:
    Canonical definitions live in vidbyte.lib.dataclasses.config; the loader imports them
    from there. Applications may import from vidbyte.config or vidbyte.config.types.
Non-Goals:
    Adds no behavior; it only forwards the shared dataclasses.
"""

from vidbyte.lib.dataclasses.config import (
    AdversarialAgentSettings,
    AggregateAgentSettings,
    AgentSettings,
    BaseAgentSettings,
    ContinualTraceAgentSettings,
    HandoffAgentSettings,
    MiddlewareDefinition,
    MultiAgentSettings,
    ToolDefinition,
)

__all__ = [
    "AdversarialAgentSettings",
    "AggregateAgentSettings",
    "AgentSettings",
    "BaseAgentSettings",
    "ContinualTraceAgentSettings",
    "HandoffAgentSettings",
    "MiddlewareDefinition",
    "MultiAgentSettings",
    "ToolDefinition",
]
