# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines prompt translations for the Reflexion strategy.
# Purpose: Exposes standardized, versioned system prompts for the actor-critic Reflexion strategy.
# Architecture & Functions:
#   - ReflexionActorPrompt (subclass of BasePrompt): Actor generating initial tries with self-critique history.
#   - ReflexionEvaluatorPrompt (subclass of BasePrompt): Evaluator scoring candidate outcomes.
#   - ReflexionReflectorPrompt (subclass of BasePrompt): Critique builder generating hindsight reflection.
# Codebase Relation:
#   - Registerable default translations used by the ReflexionStrategy loop.
# Similar Files:
#   - vidbyte/prompts/translations/strategies/react.py (other strategy prompts)
# ==============================================================================

from __future__ import annotations

from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class ReflexionActorPrompt(BasePrompt):
    """
    Powers the actor generation step of the Reflexion loop.
    Integrates feedback reflections into next iteration generation.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.reflexion",
            name="actor"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """You are an adaptive problem solver. Your goal is to solve the given task.

Task: {task}

You have failed on previous attempts. Here are the reflections from those failures:
{reflections}

Please solve the task again, adjusting your reasoning based on the reflections provided."""

    def variables(self) -> Dict[str, str]:
        return {
            "task": "The original task",
            "reflections": "Historical critiques from prior failures"
        }


class ReflexionEvaluatorPrompt(BasePrompt):
    """
    Powers the evaluator step of the Reflexion loop.
    Decides whether the actor's output is correct.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.reflexion",
            name="evaluator"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """Evaluate whether the following output solves the problem successfully.

Problem: {problem}
Agent Output: {output}

Respond ONLY in the following JSON format:
{{
    "is_correct": true or false,
    "score": 0.0 to 1.0,
    "justification": "Why this output is or is not correct"
}}"""

    def variables(self) -> Dict[str, str]:
        return {
            "problem": "The original problem being solved",
            "output": "The candidate output to grade"
        }


class ReflexionReflectorPrompt(BasePrompt):
    """
    Powers the reflector critique step of the Reflexion loop.
    Generates hindsight critiques explaining why an attempt failed.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.reflexion",
            name="reflector"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """Analyze your previous failed attempt to solve the problem and write a hindsight reflection.

Problem: {problem}
Failed Output: {failed_output}
Evaluator Feedback: {feedback}

Explain what went wrong, why it failed, and what strategy adjustments are needed for the next attempt.
Keep your reflection concise (2-4 sentences)."""

    def variables(self) -> Dict[str, str]:
        return {
            "problem": "The original problem being solved",
            "failed_output": "The incorrect output produced by the actor",
            "feedback": "The evaluator's justification feedback"
        }
