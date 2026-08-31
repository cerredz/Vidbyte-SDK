"""Provider translation contracts for semantic tracing."""

from __future__ import annotations

from collections.abc import Mapping
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

    def translate_end(self, spec: SpanSpec, attributes: Mapping[str, Any]) -> dict[str, Any]:
        # Converts close-time attributes (response/usage data) into provider-facing fields.
        # Optional: callers must check hasattr(translator, "translate_end") before calling,
        # since a translator written before this method existed will not define it.
        ...


__all__ = ["ProviderSpanPayload", "ProviderTraceTranslator"]
