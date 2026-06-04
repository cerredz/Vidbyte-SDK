"""Context Protocol Header

Description:
    Exposes user-facing trace artifact configuration helpers.
Purpose:
    Keeps continual tracing imports short while separating them from observability
    tracers under vidbyte.lib.tracing.
Architecture:
    Thin public package re-exporting trace dataclasses.
Relations:
    Used by BaseAgent trace configuration and prebuilt trace schemas.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType, TraceMode, TraceOption, TraceSchema

__all__ = [
    "TraceField",
    "TraceFieldType",
    "TraceMode",
    "TraceOption",
    "TraceSchema",
]
