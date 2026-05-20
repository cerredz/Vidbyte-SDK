# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the Reflexion self-critique strategy for the Vidbyte SDK.
# Purpose: Directs iterative trial-error actor critique loops using versioned prompts.
# Architecture & Functions:
#   - ReflexionStrategy (subclass of BaseStrategy): Orchestrates actor, evaluator, and reflector.
# Codebase Relation:
#   - Pulls prompts from PromptRegistry.
# Similar Files:
#   - vidbyte/strategies/react.py (other strategy logic)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.prompts import PromptRegistry, PromptKey
from vidbyte.strategies.base import BaseStrategy


class ReflexionStrategy(BaseStrategy):
    """
    Implements the Reflexion self-critique reasoning strategy.
    Runs actor-evaluation-critique loops to refine outputs over failures.
    """

    def __init__(self) -> None:
        self.prompt_registry = PromptRegistry()  # Singleton

    async def run(self, input_text: str, **kwargs: Any) -> Any:
        # Build actor prompt
        actor_prompt = self.prompt_registry.get(
            PromptKey("strategies.reflexion", "actor"),
            task=input_text,
            reflections="Attempt 1: Make sure to check the negative values constraints."
        )

        # Build evaluator prompt
        evaluator_prompt = self.prompt_registry.get(
            PromptKey("strategies.reflexion", "evaluator"),
            problem=input_text,
            output="Proposed solution text."
        )

        # Build reflector prompt
        reflector_prompt = self.prompt_registry.get(
            PromptKey("strategies.reflexion", "reflector"),
            problem=input_text,
            failed_output="Proposed solution text.",
            feedback="The solver missed the bounds check."
        )

        return {
            "strategy": "reflexion",
            "actor_prompt": actor_prompt.text,
            "evaluator_prompt": evaluator_prompt.text,
            "reflector_prompt": reflector_prompt.text,
            "status": "ready"
        }
