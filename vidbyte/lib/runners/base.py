from __future__ import annotations

from vidbyte.lib.config import ModelProvider
from vidbyte.lib.errors import UnsupportedProviderError


def require_supported_provider(
    provider: ModelProvider,
    *,
    supported: set[ModelProvider],
    capability: str,
) -> None:
    if provider not in supported:
        raise UnsupportedProviderError(
            f"{provider.value} does not support {capability} in this SDK runner.",
            details={"provider": provider.value, "capability": capability},
        )
