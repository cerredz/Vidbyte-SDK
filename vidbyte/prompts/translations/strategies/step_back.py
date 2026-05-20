# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines prompt translations for the Step-Back prompting strategy.
# Purpose: Exposes standardized, versioned prompts for abstracting concepts and
#          reasoning with those abstractions.
# Architecture & Functions:
#   - StepBackAbstractionPrompt (subclass of BasePrompt): Abstracts specific query into high-level principle.
#   - StepBackReasoningPrompt (subclass of BasePrompt): Solves original query utilizing abstract principles.
# Codebase Relation:
#   - Registerable default translations used by the StepBackStrategy loop.
# Similar Files:
#   - vidbyte/prompts/translations/strategies/react.py (other strategy prompts)
# ==============================================================================

from __future__ import annotations

from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class StepBackAbstractionPrompt(BasePrompt):
    """
    Powers the abstraction step of Step-Back prompting.
    Turns specific queries into general/high-level questions.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.step_back",
            name="abstraction"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """You are an expert at abstracting specific problems into broad, conceptual questions.
Given a specific query, identify the core underlying physics, math, logic, or domain concepts and formulate a high-level conceptual question.

Specific Query: {query}

High-Level Conceptual Question:"""

    def variables(self) -> Dict[str, str]:
        return {
            "query": "The specific detailed user query"
        }


class StepBackReasoningPrompt(BasePrompt):
    """
    Powers the final reasoning step of Step-Back prompting.
    Combines the original query and the high-level concepts to arrive at an answer.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.step_back",
            name="reasoning"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """Solve the user's specific query using the high-level conceptual principles provided.

Specific Query: {query}
Conceptual Principles / Background:
{principles}

Provide a detailed step-by-step response utilizing these principles to solve the query."""

    def variables(self) -> Dict[str, str]:
        return {
            "query": "The original detailed user query",
            "principles": "The resolved conceptual background or answers to the abstracted question"
        }
