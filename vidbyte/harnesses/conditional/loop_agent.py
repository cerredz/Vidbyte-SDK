# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the ConditionalLoopAgentHarness for the Vidbyte SDK.
# Purpose: Coordinates multi-turn execution loops with stopping evaluations.
# Architecture & Functions:
#   - ConditionalLoopAgentHarness (subclass of BaseHarness): Runs step-by-step agent loops.
# Codebase Relation:
#   - Uses harnesses prompt translations and coordinates evaluator checks.
# Similar Files:
#   - vidbyte/harnesses/conditional/stopping_evaluator.py (halt decision maker)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.harnesses.base import BaseHarness
from vidbyte.prompts import PromptRegistry, PromptKey


class ConditionalLoopAgentHarness(BaseHarness):
    """
    Coordinates multi-turn iterative loops where an agent produces attempts
    and improves them iteratively using evaluator feedback.
    """

    def __init__(self) -> None:
        self.prompt_registry = PromptRegistry()  # Singleton

    async def execute(self, task: str, **kwargs: Any) -> Any:
        iteration = kwargs.get("iteration", 1)

        # Build loop agent instruction prompt
        prompt = self.prompt_registry.get(
            PromptKey("harnesses.conditional", "loop_agent"),
            task=task,
            iteration=str(iteration),
            feedback="The stopping evaluator requested more detail on the security sandbox."
        )

        return {
            "harness": "conditional_loop_agent",
            "prompt": prompt.text,
            "iteration": iteration,
            "status": "ready"
        }
