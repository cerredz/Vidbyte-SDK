# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the Self-Consistency sampling strategy for the Vidbyte SDK.
# Purpose: Samples multiple distinct reasoning paths and aggregates output voting.
# Architecture & Functions:
#   - SelfConsistencyStrategy (subclass of BaseStrategy): Coordinates sample paths.
# Codebase Relation:
#   - Pulls prompts from PromptRegistry.
# Similar Files:
#   - vidbyte/strategies/react.py (other strategy logic)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.prompts import PromptRegistry, PromptKey
from vidbyte.strategies.base import BaseStrategy


class SelfConsistencyStrategy(BaseStrategy):
    """
    Implements the Self-Consistency sampling strategy.
    Samples multiple reasoning generation branches to run majority voting.
    """

    def __init__(self) -> None:
        self.prompt_registry = PromptRegistry()  # Singleton

    async def run(self, input_text: str, **kwargs: Any) -> Any:
        # Build reasoning prompt
        system_prompt = self.prompt_registry.get(
            PromptKey("strategies.self_consistency", "system"),
            problem=input_text
        )

        return {
            "strategy": "self_consistency",
            "system_prompt": system_prompt.text,
            "status": "ready"
        }
