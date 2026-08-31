from __future__ import annotations

import json
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
        error: BaseException | None = None,
        **attributes: Any,
    ) -> None:
        self._end(context, output=output, error=error, attributes=attributes)

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
            if "openinference.span.kind" not in attributes:
                run_type = str(attributes.get("run_type", ""))
                if name.startswith("llm.") or run_type == "llm":
                    span.set_attribute("openinference.span.kind", "LLM")
                elif name.startswith("tool.") or run_type == "tool":
                    span.set_attribute("openinference.span.kind", "TOOL")
                elif run_type:
                    span.set_attribute("openinference.span.kind", run_type.upper())
            return PhoenixSpanContext(span=span)
        except Exception:
            return PhoenixSpanContext()

    def end_span(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: BaseException | None = None,
        **attributes: Any,
    ) -> None:
        self._end(context, output=output, error=error, attributes=attributes)

    @staticmethod
    def _end(context: SpanContext, *, output: str | None, error: BaseException | None, attributes: Mapping[str, Any] | None = None) -> None:
        # Shared close logic for both start_trace and start_span contexts.
        if not isinstance(context, PhoenixSpanContext) or context.span is None:
            return
        try:
            if attributes:
                for key, value in attributes.items():
                    PhoenixTracer._set_close_attribute(context.span, key, value)
            if output is not None:
                context.span.set_attribute("output.value", output)
            if error is not None:
                context.span.set_attribute("error.message", str(error))
                context.span.record_exception(error)
            context.span.end()
        except Exception:
            pass

    @staticmethod
    def _set_close_attribute(span: Any, key: str, value: Any) -> None:
        # Coerces a close-time value for OTel's wire format: primitives pass through, everything
        # else is JSON-encoded, never a Python repr (structured values like output_messages are
        # tuples of dicts, which str() would otherwise corrupt into an unparseable string).
        if value is None:
            return
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
            return
        try:
            span.set_attribute(key, json.dumps(value, default=str))
        except TypeError:
            span.set_attribute(key, str(value))


__all__ = ["PhoenixSpanContext", "PhoenixTracer"]
