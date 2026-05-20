# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines prompt translations for the Stopping Evaluator in the Conditional harness.
# Purpose: Exposes versioned prompts for deciding loop halts and creating feedback critique.
# Architecture & Functions:
#   - ConditionalStoppingEvaluatorPrompt (subclass of BasePrompt): Evaluates goal completion via strict JSON formats.
# Codebase Relation:
#   - Registerable default translation used by the ConditionalStoppingEvaluator.
# Similar Files:
#   - vidbyte/prompts/translations/harnesses/conditional/loop_agent.py (loop agent prompt)
# ==============================================================================

from __future__ import annotations

from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class ConditionalStoppingEvaluatorPrompt(BasePrompt):
    """
    The stopping condition evaluator prompt for the conditional harness.
    Instructs the model to decide whether to halt or continue iterating, returning strict JSON.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="harnesses.conditional",
            name="stopping_evaluator"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """You are a strict stopping condition evaluator.

Your only job is to decide whether an agent's output meets a defined stopping condition or whether the agent should continue iterating.

Stopping condition:
{stopping_condition}

Current agent output:
{agent_output}

Iteration number: {iteration}

Respond ONLY in this exact JSON format:
{{
    "decision": "stop" or "continue",
    "reason": "specific reason for your decision",
    "confidence": 0.0 to 1.0,
    "feedback": "if continuing, the specific instruction the agent should follow on its next iteration"
}}

Be strict. Only return stop if the condition is clearly and fully met. Partial completion is not enough.
If there is any doubt, return continue with actionable feedback."""

    def variables(self) -> Dict[str, str]:
        return {
            "stopping_condition": "Natural language description of the condition",
            "agent_output": "The agent's most recent output",
            "iteration": "Current iteration number"
        }
