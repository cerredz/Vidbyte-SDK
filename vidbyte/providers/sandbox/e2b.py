"""Context Protocol Header

Description:
    Lazy E2B sandbox provider scaffold.
Purpose:
    Implements the SandboxProvider protocol but defers the heavy e2b SDK import
    to create() so the base package stays installable without it.
Architecture:
    - E2BSandboxProvider: Raises a clear install/credentials error until wired.
Relations:
    Registered in vidbyte.providers.sandbox as Platform.E2B.
"""

from __future__ import annotations

import os

from vidbyte.lib.dataclasses.sandbox import Sandbox, SandboxConfig
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxProviderError
from vidbyte.providers.sandbox.base import BaseSandboxProvider


class E2BSandboxProvider(BaseSandboxProvider):
    """Creates E2B microVM sandboxes when the e2b SDK and key are present."""

    platform = Platform.E2B

    async def create(self, config: SandboxConfig) -> Sandbox:
        # Lazily require the e2b SDK and API key before constructing a sandbox.
        self._require_sdk()
        self._require_credentials()
        raise SandboxProviderError("E2B provider is not yet wired; concrete integration is a follow-up.", details={"platform": "e2b"})

    def _require_sdk(self) -> None:
        # Raise an actionable install hint when the e2b SDK is missing.
        try:
            import e2b  # noqa: F401
        except ImportError as exc:
            raise SandboxProviderError("E2B SDK not installed. Run: pip install vidbyte-sdk[e2b]", details={"platform": "e2b"}) from exc

    def _require_credentials(self) -> None:
        # Raise a setup hint when the E2B API key is absent from the environment.
        if not os.environ.get("E2B_API_KEY"):
            raise SandboxProviderError("E2B_API_KEY is not set in the environment.", details={"platform": "e2b"})


__all__ = [
    "E2BSandboxProvider",
]
