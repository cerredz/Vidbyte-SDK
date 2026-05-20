# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the ConditionalStoppingEvaluator for the Vidbyte SDK.
# Purpose: Judges whether an agent loop should halt based on defined conditions.
# Architecture & Functions:
#   - ConditionalStoppingEvaluator (class): Exposes validation and decision checks.
# Codebase Relation:
#   - Pulls prompts from PromptRegistry.
# Similar Files:
#   - vidbyte/harnesses/conditional/loop_agent.py (runs the agent loop)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.prompts import PromptRegistry, PromptKey


class ConditionalStoppingEvaluator:
    """
    Decides whether an agent loop has met a defined termination condition,
    producing structured stop/continue feedback.
    """

    def __init__(self) -> None:
        self.prompt_registry = PromptRegistry()  # Singleton

    async def evaluate(self, stopping_condition: str, agent_output: str, iteration: int) -> Any:
        """Renders the strict evaluator decision prompt."""
        prompt = self.prompt_registry.get(
            PromptKey("harnesses.conditional", "stopping_evaluator"),
            stopping_condition=stopping_condition,
            agent_output=agent_output,
            iteration=str(iteration)
        )

        return {
            "evaluator": "conditional_stopping_evaluator",
            "prompt": prompt.text,
            "status": "ready"
        }
