"""Context Protocol Header

Description:
    Exports shared SDK tool formatting helpers.
Purpose:
    Provides provider-specific conversion and parsing utilities for tool specs
    without coupling built-in tool execution to any model provider.
Architecture:
    - ToolsFormatter: Converts ToolSpec objects to provider tool declarations
      and parses provider tool calls into ToolCall objects.
Relations:
    Related to vidbyte.tools.types and model provider integrations.
"""

from __future__ import annotations

from vidbyte.lib.tools.formatter import ErrorVerbosity, ToolErrorRenderOptions, ToolsFormatter

__all__ = [
    "ErrorVerbosity",
    "ToolErrorRenderOptions",
    "ToolsFormatter",
]
