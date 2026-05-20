# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the StrategiesClient namespace class for the Vidbyte SDK.
# Purpose: Exposes the primary developer API for interacting with reasoning strategies.
# Architecture & Functions:
#   - StrategiesClient (class): Entry client for reasoning strategy tasks, instantiating
#     standard strategies (ReAct, ToT, Reflexion, Self-Consistency, Step-Back).
# Codebase Relation:
#   - Instantiated as the `sdk.strategies` property in `VidbyteSDK`, bridging tools and strategies.
# Similar Files:
#   - vidbyte/tools/client.py (client for the tools subsystem)
#   - vidbyte/harnesses/client.py (client for the harness subsystem)
# ==============================================================================

from __future__ import annotations

from vidbyte.strategies.react import ReActStrategy
from vidbyte.strategies.tree_of_thoughts import TreeOfThoughtsStrategy
from vidbyte.strategies.reflexion import ReflexionStrategy
from vidbyte.strategies.self_consistency import SelfConsistencyStrategy
from vidbyte.strategies.step_back import StepBackStrategy
from vidbyte.tools.registry import ToolRegistry


class StrategiesClient:
    """
    Namespace client for all reasoning strategies.
    Exposes and initializes standard strategies utilizing tool and prompt registries.
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry
        self.react = ReActStrategy(tool_registry)
        self.tree_of_thoughts = TreeOfThoughtsStrategy()
        self.reflexion = ReflexionStrategy()
        self.self_consistency = SelfConsistencyStrategy()
        self.step_back = StepBackStrategy()
