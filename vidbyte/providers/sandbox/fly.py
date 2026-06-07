"""Context Protocol Header

Description:
    Lazy Fly Machines sandbox provider scaffold.
Purpose:
    Implements the SandboxProvider protocol but defers Fly Machines API wiring to
    create() so the base package stays installable without it.
Architecture:
    - FlySandboxProvider: Raises a clear install/credentials error until wired.
Relations:
    Registered in vidbyte.providers.sandbox as Platform.FLY.
"""

from __future__ import annotations

import os

from vidbyte.lib.dataclasses.sandbox import Sandbox, SandboxConfig
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxProviderError
from vidbyte.providers.sandbox.base import BaseSandboxProvider


class FlySandboxProvider(BaseSandboxProvider):
    """Creates Fly Machines sandboxes when an API token is present."""

    platform = Platform.FLY

    async def create(self, config: SandboxConfig) -> Sandbox:
        # Lazily require the Fly API token before constructing a sandbox.
        self._require_credentials()
        raise SandboxProviderError("Fly provider is not yet wired; concrete integration is a follow-up.", details={"platform": "fly"})

    def _require_credentials(self) -> None:
        # Raise a setup hint when the Fly API token is absent from the environment.
        if not os.environ.get("FLY_API_TOKEN"):
            raise SandboxProviderError("FLY_API_TOKEN is not set. See https://fly.io/docs for setup.", details={"platform": "fly"})


__all__ = [
    "FlySandboxProvider",
]
