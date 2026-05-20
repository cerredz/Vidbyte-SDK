# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines prompt translations for the Conditional loop agent harness.
# Purpose: Exposes standardized, versioned prompts for agent loops inside harnesses.
# Architecture & Functions:
#   - ConditionalLoopAgentPrompt (subclass of BasePrompt): Renders current goals and feedback turn-by-turn.
# Codebase Relation:
#   - Registerable default translation used by the ConditionalLoopAgentHarness.
# Similar Files:
#   - vidbyte/prompts/translations/harnesses/conditional/stopping_evaluator.py (evaluator prompt)
# ==============================================================================

from __future__ import annotations

from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class ConditionalLoopAgentPrompt(BasePrompt):
    """
    Powers the agent's task iteration inside the conditional harness,
    integrating stopping evaluator feedback.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="harnesses.conditional",
            name="loop_agent"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """Your goal is to accomplish the following task:
{task}

This is iteration number {iteration}.
Below is the evaluation feedback from your previous iteration:
{feedback}

Please revise and improve your solution based on the feedback."""

    def variables(self) -> Dict[str, str]:
        return {
            "task": "The primary goal/task",
            "iteration": "Current iteration number",
            "feedback": "Actionable feedback from the stopping condition evaluator"
        }
