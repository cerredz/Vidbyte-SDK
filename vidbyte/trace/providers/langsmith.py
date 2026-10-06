"""LangSmith translator for Vidbyte semantic spans."""

from __future__ import annotations

from vidbyte.trace.providers.base import ProviderSpanPayload
from vidbyte.trace.schema import SpanKind, SpanSpec


class LangSmithProviderTranslator:
    """Maps semantic span kinds into LangSmith run_type values."""

    provider = "langsmith"

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Adds explicit LangSmith run_type while preserving the semantic payload.
        attributes = dict(spec.attributes)
        attributes.setdefault("run_type", self._run_type(spec.kind))
        return ProviderSpanPayload(name=spec.name, attributes=attributes)

    @staticmethod
    def _run_type(kind: SpanKind) -> str:
        # Returns the LangSmith run_type for every supported semantic kind.
        return kind.value


__all__ = ["LangSmithProviderTranslator"]
