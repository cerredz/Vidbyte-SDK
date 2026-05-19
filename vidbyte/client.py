from __future__ import annotations

from vidbyte.harnesses.client import HarnessClient
from vidbyte.providers.client import ProvidersClient
from vidbyte.tools.client import ToolsClient


class VidbyteSDK:
    """Root client for Vidbyte SDK namespace clients."""

    def __init__(self) -> None:
        self.harnesses = HarnessClient()
        self.tools = ToolsClient()
        self.providers = ProvidersClient()
