# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines package exports for Vidbyte SDK Strategies.
# Purpose: Groups and exposes all standard reasoning strategy classes for developer access.
# Architecture & Functions:
#   - Exports BaseStrategy, ReActStrategy, TreeOfThoughtsStrategy, ReflexionStrategy,
#     SelfConsistencyStrategy, StepBackStrategy, StrategiesClient.
# Codebase Relation:
#   - Exposes strategies directly under the `vidbyte.strategies` package namespace.
# Similar Files:
#   - vidbyte/harnesses/__init__.py (harness exports)
# ==============================================================================

from __future__ import annotations

from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.client import StrategiesClient
from vidbyte.strategies.react import ReActStrategy
from vidbyte.strategies.reflexion import ReflexionStrategy
from vidbyte.strategies.self_consistency import SelfConsistencyStrategy
from vidbyte.strategies.step_back import StepBackStrategy
from vidbyte.strategies.tree_of_thoughts import TreeOfThoughtsStrategy

__all__ = [
    "BaseStrategy",
    "ReActStrategy",
    "TreeOfThoughtsStrategy",
    "ReflexionStrategy",
    "SelfConsistencyStrategy",
    "StepBackStrategy",
    "StrategiesClient",
]
