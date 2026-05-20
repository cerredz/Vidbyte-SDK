# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines prompt translations for the Tree of Thoughts strategy.
# Purpose: Exposes standardized, versioned system prompts for generating and scoring thoughts.
# Architecture & Functions:
#   - TreeOfThoughtsBranchPrompt (subclass of BasePrompt): Renders instructions for generating reasoning branches.
#   - TreeOfThoughtsScoringPrompt (subclass of BasePrompt): Renders instructions for scoring reasoning branches.
# Codebase Relation:
#   - Registerable default translations used by the TreeOfThoughtsStrategy loop.
# Similar Files:
#   - vidbyte/prompts/translations/strategies/react.py (ReAct strategy prompts)
# ==============================================================================

from __future__ import annotations

from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class TreeOfThoughtsBranchPrompt(BasePrompt):
    """
    Generates alternative branching directions for the Tree of Thoughts strategy.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.tree_of_thoughts",
            name="branch"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """You are exploring multiple reasoning paths to solve a problem.

Problem: {problem}

Current reasoning so far:
{current_thought}

Generate exactly {branching_factor} distinct continuations of this reasoning. Each continuation must explore a meaningfully different approach or direction.

Format your response as:
Branch 1: ...
Branch 2: ...
Branch 3: ...

Do not repeat ideas across branches.
Each branch should be 2-4 sentences."""

    def variables(self) -> Dict[str, str]:
        return {
            "problem": "The original problem being solved",
            "current_thought": "The reasoning path so far",
            "branching_factor": "Number of branches to generate"
        }


class TreeOfThoughtsScoringPrompt(BasePrompt):
    """
    Evaluates and scores a generated reasoning branch for convergence.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.tree_of_thoughts",
            name="score"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """Score each of the following reasoning branches on their likelihood of leading to a correct solution.

Problem: {problem}

Branches:
{branches}

For each branch return a score from 0.0 to 1.0 and a one sentence justification.

Format:
Branch 1: score=0.8, reason=...
Branch 2: score=0.3, reason=..."""

    def variables(self) -> Dict[str, str]:
        return {
            "problem": "The original problem",
            "branches": "The rendered branch texts to score"
        }
