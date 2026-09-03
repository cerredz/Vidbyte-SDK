"""FILE: vidbyte/lib/tracing/base.py

PURPOSE: Defines the minimal tracer lifecycle contract shared by SDK tracing implementations.
ROLE IN CODEBASE: Gives agents a stable start/end interface and an optional response-attribute update hook.
ARCHITECTURE NOTE: update_span is a compatibility-preserving no-op; direct shape providers override it to map post-response usage and finish data.
COMMON MODIFICATION PATTERNS: Extend the default hook without making new lifecycle methods abstract so external tracer implementations remain compatible.
KNOWN EDGE CASES: Existing exporters may ignore post-response attributes; direct in-memory providers retain only fields they can map safely.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: tests/test_otel_genai_trace_shape.py, tests/test_openinference_trace_shape.py, tests/test_trace_facade.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpanContext:
    """Opaque handle to an open span. Subclassed by each adapter to carry
    platform-specific state (Langfuse trace object, LangSmith run ID, OTel span)."""

    metadata: dict[str, Any] = field(default_factory=dict)


class TracerBase(ABC):
    """Abstract tracing contract all platform and semantic adapters must implement."""

    @abstractmethod
    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        """Open a root trace for one agent.generate_reply call."""

    @abstractmethod
    def end_trace(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Close the root trace, recording final output or error."""

    @abstractmethod
    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        **attributes: Any,
    ) -> SpanContext:
        """Open a child span (LLM call, tool call) under the given parent."""

    @abstractmethod
    def end_span(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Close a child span."""

    def update_span(self, context: SpanContext, **attributes: Any) -> None:
        """Add response-derived attributes to an open span when supported."""
        del context, attributes


class NullTracer(TracerBase):
    """Zero-overhead no-op tracer used when no platform is configured."""

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        return SpanContext()

    def end_trace(self, context: SpanContext, **_: Any) -> None:
        pass

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        return SpanContext()

    def end_span(self, context: SpanContext, **_: Any) -> None:
        pass


__all__ = ["NullTracer", "SpanContext", "TracerBase"]
