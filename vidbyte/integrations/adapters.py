"""FILE: vidbyte/integrations/adapters.py

PURPOSE: Defines the ProviderAdapter protocol every context integration implements, and the registry that resolves a provider name to one.
ROLE IN CODEBASE: The single seam between the provider-neutral Sources layer and any concrete GitHub, Slack, or Drive implementation added later.
ARCHITECTURE NOTE: This module intentionally ships no concrete adapter; the registry starts empty so a provider is a pure addition.
COMMON MODIFICATION PATTERNS: Add a capability by extending ProviderOperation and describe_operation together; never widen the protocol without a registry test.
KNOWN EDGE CASES: An unknown provider raises at resolve time rather than run time, and a duplicate registration is rejected instead of silently replacing.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.lib.dataclasses.integrations import Credentials, LoadRequest, ResourceScope
from vidbyte.lib.enums.integrations import AccessState, ProviderOperation
from vidbyte.lib.errors import ConfigurationError, SourceAccessError
from vidbyte.tools.types import ToolSpec


@runtime_checkable
class ProviderAdapter(Protocol):
    """Contract a context integration implements to supply content and scoped operations."""

    @property
    def provider(self) -> str:
        """Return the stable provider name selections address this adapter by."""
        ...

    def capabilities(self) -> frozenset[ProviderOperation]:
        """Return every read operation this adapter can expose as a scoped agent tool."""
        ...

    def describe_operation(self, operation: ProviderOperation) -> ToolSpec:
        """Return the model-facing declaration for one supported operation."""
        ...

    async def load(self, request: LoadRequest) -> tuple[DocumentContextItem, ...]:
        """Fetch the selected resource and emit it as ready-to-admit context items."""
        ...

    async def invoke(self, operation: ProviderOperation, scope: ResourceScope, credentials: Credentials, arguments: Mapping[str, Any]) -> str:
        """Run one scoped read operation against the bound resource and return its text."""
        ...


class AdapterRegistry:
    """Maps a provider name to the adapter that resolves selections for it."""

    def __init__(self) -> None:
        # Starts empty; no provider ships with the access layer itself.
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> "AdapterRegistry":
        """Register one adapter under its own provider name and return this registry."""
        # @intent provider
        # Registration is refused rather than overwritten so two libraries cannot
        # silently claim the same provider name and change which one a run uses.
        name = self._require_provider_name(adapter)
        if name in self._adapters:
            raise ConfigurationError(f"An adapter is already registered for provider '{name}'.")
        self._adapters[name] = adapter
        return self

    def get(self, provider: str) -> ProviderAdapter:
        """Return the adapter for a provider, raising a typed error when none is registered."""
        adapter = self._adapters.get(provider)
        if adapter is None:
            raise SourceAccessError(
                provider,
                "*",
                AccessState.RESOURCE_UNAVAILABLE.value,
                f"Registered providers: {', '.join(self.providers()) or 'none'}.",
            )
        return adapter

    def has(self, provider: str) -> bool:
        """Return whether a provider name resolves to a registered adapter."""
        return provider in self._adapters

    def providers(self) -> tuple[str, ...]:
        """Return every registered provider name in sorted order."""
        return tuple(sorted(self._adapters))

    def clear(self) -> None:
        """Remove every registration, primarily so tests start from a known state."""
        self._adapters.clear()

    @staticmethod
    def _require_provider_name(adapter: ProviderAdapter) -> str:
        """Return the adapter's provider name, rejecting a blank or missing one."""
        name = str(getattr(adapter, "provider", "") or "").strip()
        if not name:
            raise ConfigurationError("A ProviderAdapter must expose a non-empty provider name.")
        return name


DEFAULT_ADAPTERS = AdapterRegistry()

__all__ = [
    "DEFAULT_ADAPTERS",
    "AdapterRegistry",
    "ProviderAdapter",
]
