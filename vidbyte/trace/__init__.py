"""Context Protocol Header

Description:
    Exposes the public Trace facade for ergonomic SDK tracing presets.
Purpose:
    Gives agent users simple trace helper methods while preserving the internal
    TracerBase runtime contract.
Architecture:
    - Trace: Static helper namespace for built-in and provider-backed tracers.
    - DebugTracer: In-memory tracer for local debugging and tests.
    - ContinualTracer: First-step configurable continual trace capture preset.
Relations:
    Wraps vidbyte.lib.tracing and vidbyte.providers.tracing for public use.
"""

from __future__ import annotations

from vidbyte.trace.base import ContinualTracer, DebugTracer, Trace

__all__ = ["ContinualTracer", "DebugTracer", "Trace"]
