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
    """Abstract tracing contract all platform adapters must implement."""

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
