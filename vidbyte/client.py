# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the main root SDK client class for Vidbyte.
# Purpose: Orchestrates all major client namespaces (tools, prompts, strategies, harnesses, providers).
# Architecture & Functions:
#   - VidbyteSDK: The developer-facing entrypoint of the SDK. Exposes harnesses, tools, providers, prompts, and strategies namespaces.
# Codebase Relation:
#   - The main entrypoint that developers import and instantiate.
# Similar Files:
#   - None (this is the single root client entrypoint).
# ==============================================================================

from __future__ import annotations

from vidbyte.harnesses.client import HarnessClient
from vidbyte.providers.client import ProvidersClient
from vidbyte.tools.client import ToolsClient
from vidbyte.prompts.registry import PromptRegistry
from vidbyte.strategies.client import StrategiesClient


class VidbyteSDK:
    """Root client for Vidbyte SDK namespace clients."""

    def __init__(self) -> None:
        self.harnesses = HarnessClient()
        self.tools = ToolsClient()
        self.providers = ProvidersClient()
        self.prompts = PromptRegistry()
        self.strategies = StrategiesClient(self.tools.registry)

