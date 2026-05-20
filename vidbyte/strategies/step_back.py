# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the Step-Back reasoning strategy for the Vidbyte SDK.
# Purpose: Directs double-stage conceptual abstraction and specific answer synthesis.
# Architecture & Functions:
#   - StepBackStrategy (subclass of BaseStrategy): Solves queries via step back logic.
# Codebase Relation:
#   - Pulls prompts from PromptRegistry.
# Similar Files:
#   - vidbyte/strategies/react.py (other strategy logic)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.prompts import PromptRegistry, PromptKey
from vidbyte.strategies.base import BaseStrategy


class StepBackStrategy(BaseStrategy):
    """
    Implements the Step-Back prompting reasoning strategy.
    Performs conceptual abstraction followed by deduction based on the general principles.
    """

    def __init__(self) -> None:
        self.prompt_registry = PromptRegistry()  # Singleton

    async def run(self, input_text: str, **kwargs: Any) -> Any:
        # Build abstraction prompt
        abstraction_prompt = self.prompt_registry.get(
            PromptKey("strategies.step_back", "abstraction"),
            query=input_text
        )

        # Build reasoning prompt
        reasoning_prompt = self.prompt_registry.get(
            PromptKey("strategies.step_back", "reasoning"),
            query=input_text,
            principles="1. Newton's laws are invariant in all inertial reference frames."
        )

        return {
            "strategy": "step_back",
            "abstraction_prompt": abstraction_prompt.text,
            "reasoning_prompt": reasoning_prompt.text,
            "status": "ready"
        }
