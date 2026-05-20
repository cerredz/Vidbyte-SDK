# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines prompt translations for the Self-Consistency strategy.
# Purpose: Exposes standardized, versioned system prompts for generating multiple
#          independent reasoning paths.
# Architecture & Functions:
#   - SelfConsistencyPrompt (subclass of BasePrompt): Generates distinct reasoning steps.
# Codebase Relation:
#   - Registerable default translation used by the SelfConsistencyStrategy loop.
# Similar Files:
#   - vidbyte/prompts/translations/strategies/react.py (other strategy prompts)
# ==============================================================================

from __future__ import annotations

from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class SelfConsistencyPrompt(BasePrompt):
    """
    Powers the Self-Consistency reasoning generation step.
    Instructs models to lay out step-by-step thinking for voting.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.self_consistency",
            name="system"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """Solve the following problem by showing your step-by-step reasoning.
Make sure to explain each deduction clearly and conclude with your final answer formatted explicitly as:
'Final Answer: <your single concise answer>'

Problem: {problem}"""

    def variables(self) -> Dict[str, str]:
        return {
            "problem": "The original task or problem to solve"
        }
