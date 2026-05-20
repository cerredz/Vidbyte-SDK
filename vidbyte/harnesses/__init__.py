# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines package exports for the Vidbyte SDK Harnesses package.
# Purpose: Bundles all public elements of the harness subsystem for clean developer imports.
# Architecture & Functions:
#   - Exports HarnessClient, BaseHarness, and conditional harnesses.
# Codebase Relation:
#   - Exposes these items directly from the `vidbyte.harnesses` import namespace.
# Similar Files:
#   - vidbyte/tools/__init__.py (tools counterpart)
# ==============================================================================

from __future__ import annotations

from vidbyte.harnesses.base import BaseHarness
from vidbyte.harnesses.client import HarnessClient
from vidbyte.harnesses.conditional import ConditionalLoopAgentHarness, ConditionalStoppingEvaluator

__all__ = [
    "BaseHarness",
    "HarnessClient",
    "ConditionalLoopAgentHarness",
    "ConditionalStoppingEvaluator",
]
