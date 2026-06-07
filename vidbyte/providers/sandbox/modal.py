"""Context Protocol Header

Description:
    Lazy Modal sandbox provider scaffold.
Purpose:
    Implements the SandboxProvider protocol but defers the heavy modal SDK import
    to create() so the base package stays installable without it.
Architecture:
    - ModalSandboxProvider: Raises a clear install/credentials error until wired.
Relations:
    Registered in vidbyte.providers.sandbox as Platform.MODAL.
"""

from __future__ import annotations

import os

from vidbyte.lib.dataclasses.sandbox import Sandbox, SandboxConfig
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxProviderError
from vidbyte.providers.sandbox.base import BaseSandboxProvider


class ModalSandboxProvider(BaseSandboxProvider):
    """Creates Modal sandboxes when the modal SDK and token are present."""

    platform = Platform.MODAL

    async def create(self, config: SandboxConfig) -> Sandbox:
        # Lazily require the modal SDK and token before constructing a sandbox.
        self._require_sdk()
        self._require_credentials()
        raise SandboxProviderError("Modal provider is not yet wired; concrete integration is a follow-up.", details={"platform": "modal"})

    def _require_sdk(self) -> None:
        # Raise an actionable install hint when the modal SDK is missing.
        try:
            import modal  # noqa: F401
        except ImportError as exc:
            raise SandboxProviderError("Modal SDK not installed. Run: pip install vidbyte-sdk[modal]", details={"platform": "modal"}) from exc

    def _require_credentials(self) -> None:
        # Raise a setup hint when Modal credentials are absent from the environment.
        if not os.environ.get("MODAL_TOKEN_ID"):
            raise SandboxProviderError("MODAL_TOKEN_ID is not set in the environment.", details={"platform": "modal"})


__all__ = [
    "ModalSandboxProvider",
]
