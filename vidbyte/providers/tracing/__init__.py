"""FILE: vidbyte/providers/tracing/__init__.py

PURPOSE: Exports the SDK's existing tracing adapter classes.
ROLE IN CODEBASE: Keeps Langfuse, LangSmith, and Phoenix exporters available from one package namespace.
ARCHITECTURE NOTE: These adapters are legacy exporters; in-memory OTel/OpenInference shape builders live under vidbyte.trace.providers.
COMMON MODIFICATION PATTERNS: Add an adapter import and __all__ entry only when a destination exporter is intentionally supported.
KNOWN EDGE CASES: Importing an adapter may require its optional provider dependency at construction time.
RELATED DOCS: docs/design/trace-facade.md
TESTS: tests/test_trace_facade.py, tests/test_semantic_tracing.py
"""

from vidbyte.providers.tracing.langfuse import LangfuseTracer
from vidbyte.providers.tracing.langsmith import LangSmithTracer
from vidbyte.providers.tracing.phoenix import PhoenixTracer

__all__ = ["LangfuseTracer", "LangSmithTracer", "PhoenixTracer"]
