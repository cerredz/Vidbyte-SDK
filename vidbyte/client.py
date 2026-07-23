"""Context Protocol Header

Description:
    Defines the root Vidbyte SDK namespace client.
Purpose:
    Owns construction of public namespace clients while keeping feature-specific
    logic inside their packages.
Architecture:
    - VidbyteSDK: Instantiates agents, configuration, harnesses, paradigms, tools,
      providers, and evals namespace clients.
Relations:
    Related to vidbyte.__init__, vidbyte.tools.client, vidbyte.harnesses.client,
    vidbyte.paradigms.client, and vidbyte.providers.client.
"""

from __future__ import annotations

from vidbyte.agents.client import AgentClient
from vidbyte.config import YamlLoader
from vidbyte.paradigms.client import ParadigmClient
from vidbyte.harnesses.client import HarnessClient
from vidbyte.providers.client import ProvidersClient
from vidbyte.evals.client import EvalClient
from vidbyte.tools.client import ToolsClient


class VidbyteSDK:
    """Root client for Vidbyte SDK namespace clients."""

    def __init__(self) -> None:
        # Instantiates each public namespace client exposed by the root SDK.
        self.agents = AgentClient()
        self.config = YamlLoader()
        self.harnesses = HarnessClient()
        self.paradigms = ParadigmClient()
        self.tools = ToolsClient()
        self.providers = ProvidersClient()
        self.evals = EvalClient()
