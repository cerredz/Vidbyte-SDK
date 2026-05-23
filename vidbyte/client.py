"""Context Protocol Header

Description:
    Defines the root Vidbyte SDK namespace client.
Purpose:
    Owns construction of public namespace clients while keeping feature-specific
    logic inside their packages.
Architecture:
    - VidbyteSDK: Instantiates harnesses, tools, and providers namespace clients.
Relations:
    Related to vidbyte.__init__, vidbyte.tools.client, vidbyte.harnesses.client,
    and vidbyte.providers.client.
"""

from __future__ import annotations

from vidbyte.agents.client import AgentClient
from vidbyte.harnesses.client import HarnessClient
from vidbyte.providers.client import ProvidersClient
from vidbyte.strategies.client import StrategyClient
from vidbyte.tools.client import ToolsClient


class VidbyteSDK:
    """Root client for Vidbyte SDK namespace clients."""

    def __init__(self) -> None:
        self.agents = AgentClient()
        self.harnesses = HarnessClient()
        self.tools = ToolsClient()
        self.providers = ProvidersClient()
        self.strategies = StrategyClient()
