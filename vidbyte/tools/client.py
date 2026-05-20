# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the ToolsClient namespace class for the Vidbyte SDK.
# Purpose: Exposes the primary developer API for interacting with the tool registry
#          and tool executor. Pre-registers all builtin tools automatically.
# Architecture & Functions:
#   - ToolsClient (class): Entry client for tool tasks.
#   - ToolsClient.registry: Property exposing the initialized ToolRegistry.
#   - ToolsClient.executor: Property exposing the initialized ToolExecutor.
# Codebase Relation:
#   - Instantiated as the `sdk.tools` property in `VidbyteSDK`.
# Similar Files:
#   - vidbyte/harnesses/client.py (client for the harness subsystem)
# ==============================================================================

from __future__ import annotations

from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
from vidbyte.tools.builtins.web_search import WebSearchTool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.registry import ToolRegistry


class ToolsClient:
    """
    Namespace client for all tool operations.
    Exposes the central ToolRegistry and unified ToolExecutor.
    """

    def __init__(self) -> None:
        self._registry = ToolRegistry()
        self._executor = ToolExecutor(self._registry)

        # Pre-register standard default built-in tools
        self._registry.register(CalculatorTool())
        self._registry.register(WebSearchTool())
        self._registry.register(CodeExecutionTool())
        self._registry.register(DocumentRetrievalTool())

    @property
    def registry(self) -> ToolRegistry:
        """Access the central ToolRegistry."""
        return self._registry

    @property
    def executor(self) -> ToolExecutor:
        """Access the unified ToolExecutor."""
        return self._executor
