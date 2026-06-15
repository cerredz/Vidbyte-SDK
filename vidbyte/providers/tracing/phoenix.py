from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.lib.tracing.base import SpanContext, TracerBase

_DEFAULT_ENDPOINT = "http://localhost:6006/v1/traces"


@dataclass
class PhoenixSpanContext(SpanContext):
    """Carries an OpenTelemetry span for Arize Phoenix."""

    span: Any = field(default=None)
    token: Any = field(default=None)


class PhoenixTracer(TracerBase):
    """Tracing adapter for Arize Phoenix via OpenTelemetry.

    The endpoint is read from the constructor kwarg first, then from the
    environment variable PHOENIX_COLLECTOR_ENDPOINT (default: http://localhost:6006/v1/traces).

    Requires: pip install arize-phoenix opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
    """

    def __init__(self, *, endpoint: str | None = None) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        except ImportError as exc:
            raise TracerConfigurationError(
                "OpenTelemetry packages are not installed. Install them with: "
                "pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http"
            ) from exc

        resolved_endpoint = endpoint or os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", _DEFAULT_ENDPOINT)
        exporter = OTLPSpanExporter(endpoint=resolved_endpoint)
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        self._tracer = trace.get_tracer(__name__, tracer_provider=provider)
        self._trace_module = trace

    def start_trace(self, name: str, **attributes: Any) -> PhoenixSpanContext:
        try:
            span = self._tracer.start_span(name)
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
            token = self._trace_module.use_span(span, end_on_exit=False)
            return PhoenixSpanContext(span=span, token=token)
        except Exception:
            return PhoenixSpanContext()

    def end_trace(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
    ) -> None:
        if not isinstance(context, PhoenixSpanContext) or context.span is None:
            return
        try:
            if output is not None:
                context.span.set_attribute("output.value", output)
            if error is not None:
                context.span.set_attribute("error.message", str(error))
                context.span.record_exception(error)
            context.span.end()
        except Exception:
            pass

    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        **attributes: Any,
    ) -> PhoenixSpanContext:
        try:
            ctx = None
            if isinstance(parent, PhoenixSpanContext) and parent.span is not None:
                ctx = self._trace_module.set_span_in_context(parent.span)
            span = self._tracer.start_span(name, context=ctx)
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
            if name.startswith("llm."):
                span.set_attribute("openinference.span.kind", "LLM")
            elif name.startswith("tool."):
                span.set_attribute("openinference.span.kind", "TOOL")
            return PhoenixSpanContext(span=span)
        except Exception:
            return PhoenixSpanContext()

    def end_span(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        # Closes a Phoenix span with output/error plus optional structured metadata as attributes.
        if not isinstance(context, PhoenixSpanContext) or context.span is None:
            return
        try:
            if output is not None:
                context.span.set_attribute("output.value", output)
            for key, value in dict(metadata or {}).items():
                context.span.set_attribute(f"tool.{key}", value)
            if error is not None:
                context.span.set_attribute("error.message", str(error))
                context.span.record_exception(error)
            context.span.end()
        except Exception:
            pass


__all__ = ["PhoenixSpanContext", "PhoenixTracer"]
