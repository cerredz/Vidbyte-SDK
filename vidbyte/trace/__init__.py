"""Context Protocol Header

Description:
    Exposes the public Trace facade for ergonomic SDK tracing presets.
Purpose:
    Gives agent users simple trace helper methods while preserving the internal
    TracerBase runtime contract.
Architecture:
    - Trace: Tracer client namespace for built-in and provider-backed tracers.
    - DebugTracer: In-memory tracer from vidbyte.trace.debug.
    - ContinualTracer: Continual trace capture preset from vidbyte.trace.continual.
Relations:
    Wraps vidbyte.lib.tracing and vidbyte.providers.tracing for public use.
"""

from __future__ import annotations

from vidbyte.trace.base import Trace
from vidbyte.trace.continual import ContinualTracer
from vidbyte.trace.debug import DebugTracer

__all__ = ["ContinualTracer", "DebugTracer", "Trace"]
