# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines prompt translations for the ReAct strategy.
# Purpose: Exposes standardized, versioned system and iteration prompts for ReAct loops.
# Architecture & Functions:
#   - ReActSystemPrompt (subclass of BasePrompt): Renders ReAct formatting instructions and tool specs.
#   - ReActIterationPrompt (subclass of BasePrompt): Renders historical turn status and current task.
# Codebase Relation:
#   - Registerable default translations used by the ReActStrategy loop.
# Similar Files:
#   - vidbyte/prompts/translations/strategies/tree_of_thoughts.py (other strategy prompts)
# ==============================================================================

from __future__ import annotations

from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class ReActSystemPrompt(BasePrompt):
    """
    The system prompt powering the ReAct strategy.
    Instructs models to adhere to Thought -> Action -> Observation execution steps.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.react",
            name="system"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """You are an agent that solves problems by reasoning and acting.
You have access to the following tools:

{tools}

You must follow this exact format on every iteration:

Thought: think about what to do next
Action: the name of the tool to call
Action Input: {{"param": "value"}} in valid JSON
Observation: (this will be filled in with the tool result)

Continue this loop until you have enough information to answer.
When you have a final answer, output:

Thought: I now have enough information to answer
Final Answer: your complete answer here

Never skip the Thought step.
Never call a tool that is not in the tools list above.
Never fabricate an Observation - wait for the real result."""

    def variables(self) -> Dict[str, str]:
        return {
            "tools": "Rendered tool specs from the ToolRegistry"
        }


class ReActIterationPrompt(BasePrompt):
    """
    Carries turn iteration context and problem status through the ReAct loop.
    """

    def key(self) -> PromptKey:
        return PromptKey(
            namespace="strategies.react",
            name="iteration"
        )

    def version(self) -> str:
        return "1.0.0"

    def template(self) -> str:
        return """Task: {task}

{history}

Thought:"""

    def variables(self) -> Dict[str, str]:
        return {
            "task": "The original task or question",
            "history": "All previous Thought/Action/Observation turns"
        }
