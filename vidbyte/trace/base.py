"""Context Protocol Header

Description:
    Exposes the public Trace tracer client for ergonomic SDK tracing presets.
Purpose:
    Keeps tracing helpers importable from vidbyte.trace while implementation
    details live in dedicated trace modules.
Architecture:
    - Trace: Tracer client namespace for off, debug, continual, custom, and provider tracers.
    - _TraceFactory: Small validation helper for custom tracer normalization.
Relations:
    Used by BaseAgent through trace= and delegates to debug, continual, and provider tracers.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import NullTracer, TracerBase
from vidbyte.trace.continual import ContinualTracer
from vidbyte.trace.debug import DebugTracer


class Trace:
    """Public tracer client namespace for agent tracing presets."""

    @staticmethod
    def off() -> TracerBase:
        # Returns the existing no-op tracer for disabled tracing.
        return NullTracer()

    @staticmethod
    def debug(events: list[dict[str, Any]] | None = None) -> DebugTracer:
        # Returns an in-memory tracer that records trace and span lifecycle events.
        return DebugTracer(events=events)

    @staticmethod
    def custom(tracer: type[TracerBase] | TracerBase) -> TracerBase:
        # Normalizes a caller-provided tracer class or instance.
        return _TraceFactory.resolve_custom_tracer(tracer)

    @staticmethod
    def continual(remember: Sequence[str], *, max_memory_chars: int = 1200, redact: bool = True) -> ContinualTracer:
        # Returns a validated continual trace capture preset.
        return ContinualTracer(remember, max_memory_chars=max_memory_chars, redact=redact)

    @staticmethod
    def langfuse(public_key: str | None = None, secret_key: str | None = None, host: str | None = None) -> TracerBase:
        # Builds the existing Langfuse provider tracer with forwarded credentials.
        from vidbyte.providers.tracing import LangfuseTracer
        return LangfuseTracer(public_key=public_key, secret_key=secret_key, host=host)

    @staticmethod
    def langsmith(api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False, include_runtime_info: bool = False) -> TracerBase:
        # Builds the existing LangSmith provider tracer with forwarded settings.
        from vidbyte.providers.tracing import LangSmithTracer
        return LangSmithTracer(api_key=api_key, project=project, endpoint=endpoint, strict=strict, include_runtime_info=include_runtime_info)

    @staticmethod
    def phoenix(endpoint: str | None = None) -> TracerBase:
        # Builds the existing Phoenix provider tracer with the forwarded endpoint.
        from vidbyte.providers.tracing import PhoenixTracer
        return PhoenixTracer(endpoint=endpoint)


class _TraceFactory:
    """Validation helpers for the public Trace tracer client."""

    @staticmethod
    def resolve_custom_tracer(tracer: type[TracerBase] | TracerBase) -> TracerBase:
        # Returns a concrete tracer instance or raises for unsupported objects.
        if tracer is None:
            raise ConfigurationError("Trace.custom() requires a TracerBase class or instance.")
        resolved = tracer() if isinstance(tracer, type) else tracer
        if not isinstance(resolved, TracerBase):
            raise ConfigurationError("Trace.custom() requires a TracerBase class or instance.")
        return resolved


__all__ = ["ContinualTracer", "DebugTracer", "Trace"]
