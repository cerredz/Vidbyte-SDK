"""Context Protocol Header

Description:
    Lazy Daytona sandbox provider scaffold.
Purpose:
    Implements the SandboxProvider protocol but defers the heavy daytona SDK
    import to create() so the base package stays installable without it.
Architecture:
    - DaytonaSandboxProvider: Raises a clear install/credentials error until wired.
Relations:
    Registered in vidbyte.providers.sandbox as Platform.DAYTONA.
"""

from __future__ import annotations

import os

from vidbyte.lib.dataclasses.sandbox import Sandbox, SandboxConfig
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxProviderError
from vidbyte.providers.sandbox.base import BaseSandboxProvider


class DaytonaSandboxProvider(BaseSandboxProvider):
    """Creates Daytona sandboxes when the daytona SDK and key are present."""

    platform = Platform.DAYTONA

    async def create(self, config: SandboxConfig) -> Sandbox:
        # Lazily require the daytona SDK and key before constructing a sandbox.
        self._require_sdk()
        self._require_credentials()
        raise SandboxProviderError("Daytona provider is not yet wired; concrete integration is a follow-up.", details={"platform": "daytona"})

    def _require_sdk(self) -> None:
        # Raise an actionable install hint when the daytona SDK is missing.
        try:
            import daytona_sdk  # noqa: F401
        except ImportError as exc:
            raise SandboxProviderError("Daytona SDK not installed. Run: pip install vidbyte-sdk[daytona]", details={"platform": "daytona"}) from exc

    def _require_credentials(self) -> None:
        # Raise a setup hint when the Daytona API key is absent from the environment.
        if not os.environ.get("DAYTONA_API_KEY"):
            raise SandboxProviderError("DAYTONA_API_KEY is not set in the environment.", details={"platform": "daytona"})


__all__ = [
    "DaytonaSandboxProvider",
]
