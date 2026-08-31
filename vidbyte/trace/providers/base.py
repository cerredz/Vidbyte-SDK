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
    """Protocol implemented by provider-specific semantic translators.

    A translator may also define an optional translate_end(spec, attributes) -> dict[str, Any]
    method to shape close-time data (response text, usage) the way translate_start shapes
    open-time data. It is deliberately not part of this Protocol's required interface — mypy
    would then require every structural implementer to define it, defeating the point of it
    being optional — so callers detect it with getattr(translator, "translate_end", None)
    (see TraceController._translate_end), never a static attribute access or isinstance check.
    """

    provider: str

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Converts a semantic span spec into provider-facing start payload.
        ...


__all__ = ["ProviderSpanPayload", "ProviderTraceTranslator"]
