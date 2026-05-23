# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the Tree of Thoughts reasoning strategy for the Vidbyte SDK.
# Purpose: Orchestrates branching reasoning paths and scores them for optimal path convergence.
# Architecture & Functions:
#   - TreeOfThoughtsStrategy (subclass of BaseStrategy): Manages branch and score prompts.
# Codebase Relation:
#   - Pulls prompt text from Prompts.
# Similar Files:
#   - vidbyte/strategies/react.py (other strategy logic)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts
from vidbyte.strategies.base import BaseStrategy


class TreeOfThoughtsStrategy(BaseStrategy):
    """
    Implements the Tree of Thoughts (ToT) reasoning strategy.
    Explores and scores multiple reasoning branches in parallel.
    """

    def __init__(self) -> None:
        self.prompts = Prompts()

    async def run(self, input_text: str, **kwargs: Any) -> Any:
        branching_factor = kwargs.get("branching_factor", 3)

        # Build branching prompt
        branch_prompt = self.prompts.get(Prompt.TREE_OF_THOUGHTS_BRANCH_PROMPT).format(branches=branching_factor)

        # Build scoring prompt
        score_prompt = self.prompts.get(Prompt.TREE_OF_THOUGHTS_EVALUATE_PROMPT)

        return {
            "strategy": "tree_of_thoughts",
            "branch_prompt": branch_prompt,
            "score_prompt": score_prompt,
            "status": "ready"
        }
