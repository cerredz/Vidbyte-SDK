"""Context Protocol Header

Description:
    Defines public trace preset helpers and in-memory tracing implementations.
Purpose:
    Keeps tracing ergonomic for agent users while reusing the existing
    TracerBase runtime interface.
Architecture:
    - Trace: Factory namespace for off, debug, continual, custom, and provider tracers.
    - DebugTracer: Records trace/span lifecycle events into a caller-visible list.
    - ContinualTracer: Stores continual trace capture settings for future context feedback.
Relations:
    Used by BaseAgent through trace= and by provider helper methods.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase

_SUPPORTED_CONTINUAL_MEMORY = frozenset(("model_calls", "tool_calls", "failures", "outputs", "decisions"))


class DebugTracer(TracerBase):
    """In-memory tracer useful for local debugging and tests."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        # Stores lifecycle events in caller-provided storage or an owned list.
        self.events = events if events is not None else []
        self._counter = 0

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Opens a root trace context and records its start event.
        context = self._context("trace", name)
        self.events.append({"type": "start_trace", "name": name, "attributes": dict(attributes), "context": context, "parent": None, "output": None, "error": None})
        return context

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Records root trace completion without raising on error metadata.
        self.events.append({"type": "end_trace", "name": None, "attributes": {}, "context": context, "parent": None, "output": output, "error": self._error_text(error)})

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Opens a child span context and records its parent linkage.
        context = self._context("span", name)
        self.events.append({"type": "start_span", "name": name, "attributes": dict(attributes), "context": context, "parent": parent, "output": None, "error": None})
        return context

    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Records child span completion without raising on error metadata.
        self.events.append({"type": "end_span", "name": None, "attributes": {}, "context": context, "parent": None, "output": output, "error": self._error_text(error)})

    def _context(self, kind: str, name: str) -> SpanContext:
        # Creates a trace/span context with stable debug metadata.
        self._counter += 1
        return SpanContext(metadata={"id": self._counter, "kind": kind, "name": name})

    @staticmethod
    def _error_text(error: Exception | None) -> str | None:
        # Converts exceptions into event-safe text while preserving None.
        return str(error) if error is not None else None


class ContinualTracer(DebugTracer):
    """Configurable in-memory tracer for future continual context feedback."""

    def __init__(self, remember: Sequence[str], *, max_memory_chars: int = 1200, redact: bool = True, events: list[dict[str, Any]] | None = None) -> None:
        # Validates continual capture settings and initializes debug event capture.
        self.remember = _TraceFactory.validate_remember(remember)
        self.max_memory_chars = _TraceFactory.validate_max_memory_chars(max_memory_chars)
        self.redact = bool(redact)
        super().__init__(events=events)


class Trace:
    """Public factory namespace for agent tracing presets."""

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
    def langsmith(api_key: str | None = None, project: str | None = None) -> TracerBase:
        # Builds the existing LangSmith provider tracer with forwarded settings.
        from vidbyte.providers.tracing import LangSmithTracer
        return LangSmithTracer(api_key=api_key, project=project)

    @staticmethod
    def phoenix(endpoint: str | None = None) -> TracerBase:
        # Builds the existing Phoenix provider tracer with the forwarded endpoint.
        from vidbyte.providers.tracing import PhoenixTracer
        return PhoenixTracer(endpoint=endpoint)


class _TraceFactory:
    """Validation helpers for the public Trace factory namespace."""

    @staticmethod
    def resolve_custom_tracer(tracer: type[TracerBase] | TracerBase) -> TracerBase:
        # Returns a concrete tracer instance or raises for unsupported objects.
        if tracer is None:
            raise ConfigurationError("Trace.custom() requires a TracerBase class or instance.")
        resolved = tracer() if isinstance(tracer, type) else tracer
        if not isinstance(resolved, TracerBase):
            raise ConfigurationError("Trace.custom() requires a TracerBase class or instance.")
        return resolved

    @staticmethod
    def validate_remember(remember: Sequence[str]) -> tuple[str, ...]:
        # Validates and normalizes continual memory categories.
        if isinstance(remember, str) or not remember:
            raise ConfigurationError("Trace.continual() requires a non-empty remember sequence.")
        normalized: list[str] = []
        for item in remember:
            if item not in _SUPPORTED_CONTINUAL_MEMORY:
                raise ConfigurationError(f"Unsupported continual trace memory category: {item}.")
            if item not in normalized:
                normalized.append(item)
        return tuple(normalized)

    @staticmethod
    def validate_max_memory_chars(max_memory_chars: int) -> int:
        # Validates the bounded memory character budget for future summaries.
        if isinstance(max_memory_chars, bool) or not isinstance(max_memory_chars, int):
            raise ConfigurationError("Trace.continual() max_memory_chars must be an integer.")
        if max_memory_chars <= 0:
            raise ConfigurationError("Trace.continual() max_memory_chars must be greater than zero.")
        return max_memory_chars


__all__ = ["ContinualTracer", "DebugTracer", "Trace"]
