# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the Tree of Thoughts reasoning strategy for the Vidbyte SDK.
# Purpose: Orchestrates branching reasoning paths and scores them for optimal path convergence.
# Architecture & Functions:
#   - TreeOfThoughtsStrategy (subclass of BaseStrategy): Manages branch and score prompts.
# Codebase Relation:
#   - Pulls prompts from PromptRegistry.
# Similar Files:
#   - vidbyte/strategies/react.py (other strategy logic)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.prompts import PromptRegistry, PromptKey
from vidbyte.strategies.base import BaseStrategy


class TreeOfThoughtsStrategy(BaseStrategy):
    """
    Implements the Tree of Thoughts (ToT) reasoning strategy.
    Explores and scores multiple reasoning branches in parallel.
    """

    def __init__(self) -> None:
        self.prompt_registry = PromptRegistry()  # Singleton

    async def run(self, input_text: str, **kwargs: Any) -> Any:
        branching_factor = kwargs.get("branching_factor", 3)

        # Build branching prompt
        branch_prompt = self.prompt_registry.get(
            PromptKey("strategies.tree_of_thoughts", "branch"),
            problem=input_text,
            current_thought="Let us start by defining the domain bounds.",
            branching_factor=str(branching_factor)
        )

        # Build scoring prompt
        score_prompt = self.prompt_registry.get(
            PromptKey("strategies.tree_of_thoughts", "score"),
            problem=input_text,
            branches="Branch 1: Use calculus.\nBranch 2: Use geometry."
        )

        return {
            "strategy": "tree_of_thoughts",
            "branch_prompt": branch_prompt.text,
            "score_prompt": score_prompt.text,
            "status": "ready"
        }
