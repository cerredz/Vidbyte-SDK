"""FILE: vidbyte/trace/providers/__init__.py

PURPOSE: Exports legacy semantic translators and direct in-memory trace-shape providers.
ROLE IN CODEBASE: Defines the stable import surface for generic/LangSmith translators and OTel/OpenInference shape builders.
ARCHITECTURE NOTE: Translator contracts support existing exporters; direct shape providers return caller-owned plain records without transport.
COMMON MODIFICATION PATTERNS: Update imports and __all__ together when adding or removing a public tracing provider.
KNOWN EDGE CASES: Legacy provider imports and direct shape providers intentionally have different contracts and must not be conflated.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/trace/providers/README.md
TESTS: tests/test_trace_facade.py, tests/test_otel_genai_trace_shape.py, tests/test_openinference_trace_shape.py
"""

from __future__ import annotations

from vidbyte.trace.providers.base import ProviderSpanPayload, ProviderTraceTranslator
from vidbyte.trace.providers.generic import GenericProviderTranslator
from vidbyte.trace.providers.langsmith import LangSmithProviderTranslator
from vidbyte.trace.providers.openinference import OpenInferenceTrace
from vidbyte.trace.providers.otel_genai import OTelGenAITrace

__all__ = [
    "GenericProviderTranslator",
    "LangSmithProviderTranslator",
    "OTelGenAITrace",
    "OpenInferenceTrace",
    "ProviderSpanPayload",
    "ProviderTraceTranslator",
]
