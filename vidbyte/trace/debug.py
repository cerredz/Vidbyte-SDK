"""Context Protocol Header

Description:
    Implements the public in-memory debug tracer for local inspection and tests.
Purpose:
    Keeps debug trace recording separate from the Trace tracer client facade.
Architecture:
    - DebugTracer: TracerBase implementation that records lifecycle events in memory.
Relations:
    Used by vidbyte.trace.Trace.debug and by continual tracing presets.
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.tracing import SpanContext, TracerBase


class DebugTracer(TracerBase):
    """In-memory tracer useful for local debugging and tests."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events = events if events is not None else []
        self._counter = 0

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        context = self._context("trace", name)
        self.events.append(
            {
                "type": "start_trace",
                "name": name,
                "attributes": dict(attributes),
                "context": context,
                "parent": None,
                "output": None,
                "error": None,
            }
        )
        return context

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        self.events.append(
            {
                "type": "end_trace",
                "name": None,
                "attributes": {},
                "context": context,
                "parent": None,
                "output": output,
                "error": self._error_text(error),
            }
        )

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        context = self._context("span", name)
        self.events.append(
            {
                "type": "start_span",
                "name": name,
                "attributes": dict(attributes),
                "context": context,
                "parent": parent,
                "output": None,
                "error": None,
            }
        )
        return context

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        self.events.append(
            {
                "type": "end_span",
                "name": None,
                "attributes": {},
                "context": context,
                "parent": None,
                "output": output,
                "error": self._error_text(error),
            }
        )

    def _context(self, kind: str, name: str) -> SpanContext:
        self._counter += 1
        return SpanContext(metadata={"id": self._counter, "kind": kind, "name": name})

    @staticmethod
    def _error_text(error: BaseException | None) -> str | None:
        return str(error) if error is not None else None


__all__ = ["DebugTracer"]
