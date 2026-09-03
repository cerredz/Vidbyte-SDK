"""FILE: vidbyte/trace/base.py

PURPOSE: Public Trace facade exposing built-in, provider-backed, and profiled tracing presets.
ROLE IN CODEBASE: The single discoverable entry point users call instead of the lower-level TracerBase/TraceController/translator types directly.
ARCHITECTURE NOTE: Legacy exporter presets return TracerBase-compatible adapters; OTel GenAI and OpenInference are direct in-memory shape constructors that do not resolve endpoints or transport.
COMMON MODIFICATION PATTERNS: Add a direct shape provider with a raw Trace.<name>(events=None) constructor and provider mapping; add an exporter preset only when destination transport is intentionally supported.
KNOWN EDGE CASES: Legacy adapter construction errors (missing package, credentials, or endpoint) propagate unchanged; direct shape constructors only allocate or reuse the caller's event list.
RELATED DOCS: docs/design/trace-facade.md, docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: tests/test_trace_facade.py, tests/test_otel_genai_trace_shape.py, tests/test_openinference_trace_shape.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import NullTracer, TracerBase
from vidbyte.trace.controller import TraceController
from vidbyte.trace.continual import ContinualTracer
from vidbyte.trace.debug import DebugTracer
from vidbyte.trace.profiles import TraceProfile
from vidbyte.trace.providers import (
    GenericProviderTranslator,
    LangSmithProviderTranslator,
    OpenInferenceTrace,
    OTelGenAITrace,
    ProviderTraceTranslator,
)
from vidbyte.trace.session import SessionTraceController, SessionTracer


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
    def profile(inner: TracerBase, profile: TraceProfile | None = None, provider: str | ProviderTraceTranslator | None = None) -> TraceController:
        # Wraps a low-level tracer in the semantic trace controller.
        if inner is None:
            raise ConfigurationError("Trace.profile() requires an inner tracer.")
        return TraceController(inner=inner, profile=profile, translator=_TraceFactory.resolve_translator(provider))

    @staticmethod
    def session(
        inner: type[TracerBase] | TracerBase,
        name: str | None = None,
        profile: TraceProfile | None = None,
        provider: str | ProviderTraceTranslator | None = None,
        *,
        default_name: str | None = None,
        default_attributes: Mapping[str, Any] | None = None,
    ) -> SessionTraceController | SessionTracer:
        # Supports the legacy SessionTracer path and the semantic session controller path.
        if inner is None:
            raise ConfigurationError("Trace.session() requires an inner tracer.")
        if default_name is not None or default_attributes is not None:
            if name is not None or profile is not None or provider is not None:
                raise ConfigurationError("Trace.session() cannot mix default_name/default_attributes with semantic session options.")
            return SessionTracer(inner, default_name=default_name or "session.run", default_attributes=default_attributes)
        resolved_inner = _TraceFactory.resolve_custom_tracer(inner)
        return SessionTraceController(inner=resolved_inner, profile=profile, translator=_TraceFactory.resolve_translator(provider), name=name)

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
    def langsmith_default(api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False, include_runtime_info: bool = False) -> TraceController:
        # Builds a LangSmith tracer wrapped in the default semantic profile.
        return Trace.profile(
            Trace.langsmith(api_key=api_key, project=project, endpoint=endpoint, strict=strict, include_runtime_info=include_runtime_info),
            profile=TraceProfile.default(),
            provider="langsmith",
        )

    @staticmethod
    def langsmith_verbose(api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False, include_runtime_info: bool = False) -> TraceController:
        # Builds a LangSmith tracer wrapped in the verbose semantic profile.
        return Trace.profile(
            Trace.langsmith(api_key=api_key, project=project, endpoint=endpoint, strict=strict, include_runtime_info=include_runtime_info),
            profile=TraceProfile.verbose(),
            provider="langsmith",
        )

    @staticmethod
    def langsmith_session(
        api_key: str | None = None,
        project: str | None = None,
        endpoint: str | None = None,
        strict: bool = False,
        include_runtime_info: bool = False,
        name: str | None = None,
        profile: TraceProfile | None = None,
        *,
        default_name: str | None = None,
        default_attributes: Mapping[str, Any] | None = None,
    ) -> SessionTraceController | SessionTracer:
        # Builds a LangSmith tracer wrapped in a session-capable trace root.
        inner = Trace.langsmith(api_key=api_key, project=project, endpoint=endpoint, strict=strict, include_runtime_info=include_runtime_info)
        if default_name is not None or default_attributes is not None:
            return SessionTracer(inner, default_name=default_name or "session.run", default_attributes=default_attributes)
        return Trace.session(inner, name=name, profile=profile or TraceProfile.default(), provider="langsmith")

    @staticmethod
    def phoenix(endpoint: str | None = None) -> TracerBase:
        # Builds the existing Phoenix provider tracer with the forwarded endpoint.
        from vidbyte.providers.tracing import PhoenixTracer
        return PhoenixTracer(endpoint=endpoint)

    @staticmethod
    def otel_genai(events: list[dict[str, Any]] | None = None) -> OTelGenAITrace:
        # Builds the direct in-memory OTel GenAI shape provider.
        return OTelGenAITrace(events=events)

    @staticmethod
    def openinference(events: list[dict[str, Any]] | None = None) -> OpenInferenceTrace:
        # Builds the direct in-memory OpenInference shape provider.
        return OpenInferenceTrace(events=events)


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

    @staticmethod
    def resolve_translator(provider: str | ProviderTraceTranslator | None) -> ProviderTraceTranslator:
        # Converts a provider name or translator instance into a concrete translator.
        if provider is None or provider == "generic":
            return GenericProviderTranslator()
        if provider == "langsmith":
            return LangSmithProviderTranslator()
        if hasattr(provider, "translate_start"):
            return provider
        raise ConfigurationError(f"Unknown trace provider translator: {provider}.")


__all__ = [
    "ContinualTracer",
    "DebugTracer",
    "SessionTraceController",
    "SessionTracer",
    "Trace",
    "TraceController",
    "TraceProfile",
]
