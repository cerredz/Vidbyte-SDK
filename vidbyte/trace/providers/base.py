"""Provider translation contracts for semantic tracing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from vidbyte.trace.schema import SpanSpec


@dataclass(frozen=True, slots=True)
class ProviderSpanPayload:
    """Provider-facing name and attributes derived from a semantic span."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


class ProviderTraceTranslator(Protocol):
    """Protocol implemented by provider-specific semantic translators."""

    provider: str

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Converts a semantic span spec into provider-facing start payload.
        ...


__all__ = ["ProviderSpanPayload", "ProviderTraceTranslator"]
