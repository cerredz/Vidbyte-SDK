"""Context Protocol Header

Description:
    Exposes continual tracing presets and helpers.
Purpose:
    Keeps the continual tracing package ready for future trace memory work.
Architecture:
    - ContinualTracer: Validated in-memory continual trace capture preset.
Relations:
    Imported by the public vidbyte.trace tracer client.
"""

from __future__ import annotations

from vidbyte.trace.continual.base import ContinualTracer

__all__ = ["ContinualTracer"]
