"""FILE: vidbyte/providers/tracing/otel.py

PURPOSE: Ships Vidbyte semantic spans over standard OTLP/HTTP to any OTel-compatible collector.
ROLE IN CODEBASE: Destination-agnostic transport paired with a ProviderTraceTranslator shape.
ARCHITECTURE NOTE: Mirrors PhoenixTracer's OTel SDK plumbing but never guesses a semantic shape itself.
COMMON MODIFICATION PATTERNS: Add new resolvable endpoint env vars or resource attributes here, not in a translator.
KNOWN EDGE CASES: Missing opentelemetry-sdk or an unresolvable endpoint raise TracerConfigurationError at construction; every per-call method fails open.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: tests/test_otel_tracer_transport.py
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.lib.tracing.base import SpanContext, TracerBase

_ENDPOINT_ENV_VARS = ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")
_DEFAULT_SERVICE_NAME = "vidbyte-agent"


@dataclass
class OTelSpanContext(SpanContext):
    """Carries a raw OpenTelemetry span for the destination-agnostic OTel tracer."""

    span: Any = field(default=None)
    token: Any = field(default=None)


class OTelTracer(TracerBase):
    """Destination-agnostic OpenTelemetry tracer.

    Ships spans over OTLP/HTTP to any OTel-compatible collector: Phoenix, a Datadog
    Agent, an AWS Distro for OpenTelemetry (ADOT) collector feeding Bedrock AgentCore,
    or a self-hosted OTel Collector. Unlike PhoenixTracer, this adapter never guesses a
    semantic shape (no name-prefix or run_type inspection) — every attribute it receives
    is forwarded exactly as given by whichever ProviderTraceTranslator produced it, so it
    works correctly with any shape translator without adapter changes.

    Requires: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        headers: Mapping[str, str] | None = None,
        service_name: str | None = None,
        exporter: Any = None,
    ) -> None:
        # Resolves the OTel exporter/resource and builds a tracer provider, or raises TracerConfigurationError.
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        except ImportError as exc:
            raise TracerConfigurationError(
                "OpenTelemetry packages are not installed. Install them with: "
                "pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http"
            ) from exc

        resolved_exporter = exporter or self._build_default_exporter(endpoint=endpoint, headers=headers)
        resource = Resource.create({"service.name": service_name or _DEFAULT_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(resolved_exporter))

        self._tracer = trace.get_tracer(__name__, tracer_provider=provider)
        self._trace_module = trace

    @staticmethod
    def _build_default_exporter(*, endpoint: str | None, headers: Mapping[str, str] | None) -> Any:
        # Builds the real OTLP/HTTP exporter, raising loudly when no endpoint can be resolved.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        resolved_endpoint = endpoint or next(
            (os.environ[name] for name in _ENDPOINT_ENV_VARS if os.environ.get(name)), None
        )
        if not resolved_endpoint:
            raise TracerConfigurationError(
                "OTelTracer requires an endpoint. Pass endpoint=... or set "
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT / OTEL_EXPORTER_OTLP_ENDPOINT."
            )
        return OTLPSpanExporter(endpoint=resolved_endpoint, headers=dict(headers) if headers else None)

    def start_trace(self, name: str, **attributes: Any) -> OTelSpanContext:
        # Opens a root OTel span and returns its context, degrading safely on failure.
        try:
            span = self._tracer.start_span(name)
            self._set_attributes(span, attributes)
            token = self._trace_module.use_span(span, end_on_exit=False)
            return OTelSpanContext(span=span, token=token)
        except Exception:
            return OTelSpanContext()

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None:
        # Closes a root OTel span with output, error, and any close-time attributes, never raising.
        self._end(context, output=output, error=error, attributes=attributes)

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> OTelSpanContext:
        # Opens a child OTel span under the given parent, degrading safely on failure.
        try:
            ctx = None
            if isinstance(parent, OTelSpanContext) and parent.span is not None:
                ctx = self._trace_module.set_span_in_context(parent.span)
            span = self._tracer.start_span(name, context=ctx)
            self._set_attributes(span, attributes)
            return OTelSpanContext(span=span)
        except Exception:
            return OTelSpanContext()

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None:
        # Closes a child OTel span with output, error, and any close-time attributes, never raising.
        self._end(context, output=output, error=error, attributes=attributes)

    @staticmethod
    def _end(context: SpanContext, *, output: str | None, error: BaseException | None, attributes: Mapping[str, Any] | None = None) -> None:
        # Shared close logic for both start_trace and start_span contexts.
        if not isinstance(context, OTelSpanContext) or context.span is None:
            return
        try:
            if attributes:
                OTelTracer._set_attributes(context.span, attributes)
            if output is not None:
                context.span.set_attribute("output.value", output)
            if error is not None:
                context.span.set_attribute("error.message", str(error))
                context.span.record_exception(error)
            context.span.end()
        except Exception:
            pass

    @staticmethod
    def _set_attributes(span: Any, attributes: Mapping[str, Any]) -> None:
        # Coerces every attribute into an OTel-safe value: primitives pass through, everything else becomes JSON.
        for key, value in attributes.items():
            if value is None:
                continue
            if isinstance(value, (str, bool, int, float)):
                span.set_attribute(key, value)
                continue
            try:
                span.set_attribute(key, json.dumps(value, default=str))
            except TypeError:
                span.set_attribute(key, str(value))


__all__ = ["OTelSpanContext", "OTelTracer"]
