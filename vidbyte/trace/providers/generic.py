"""Generic semantic trace translator."""

from __future__ import annotations

from vidbyte.trace.providers.base import ProviderSpanPayload
from vidbyte.trace.schema import SpanSpec


class GenericProviderTranslator:
    """Pass-through translator for debug, custom, null, Langfuse, and Phoenix tracers."""

    provider = "generic"

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Preserves semantic names and attributes without provider-specific additions.
        return ProviderSpanPayload(name=spec.name, attributes=dict(spec.attributes))


__all__ = ["GenericProviderTranslator"]
