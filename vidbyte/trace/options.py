"""Context Protocol Header

Description:
    Compatibility module for importing trace option dataclasses.
Purpose:
    Provides a stable vidbyte.trace.options import path for SDK users.
Architecture:
    Re-exports the canonical trace dataclasses from vidbyte.lib.dataclasses.
Relations:
    Related to vidbyte.trace.__init__ and BaseAgent trace configuration.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.trace import TraceMode, TraceOption, TraceSchema

__all__ = [
    "TraceMode",
    "TraceOption",
    "TraceSchema",
]
