# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the Reflexion self-critique strategy for the Vidbyte SDK.
# Purpose: Directs iterative trial-error actor critique loops using versioned prompts.
# Architecture & Functions:
#   - ReflexionStrategy (subclass of BaseStrategy): Orchestrates actor, evaluator, and reflector.
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


class ReflexionStrategy(BaseStrategy):
    """
    Implements the Reflexion self-critique reasoning strategy.
    Runs actor-evaluation-critique loops to refine outputs over failures.
    """

    def __init__(self) -> None:
        self.prompts = Prompts()

    async def run(self, input_text: str, **kwargs: Any) -> Any:
        # Build actor prompt
        actor_prompt = self.prompts.get(Prompt.MULTI_AGENT_REFLEXION_DRAFT_PROMPT)

        # Build evaluator prompt
        evaluator_prompt = self.prompts.get(Prompt.MULTI_AGENT_REFLEXION_CRITIC_PROMPT).format(critic_role="evaluator")

        # Build reflector prompt
        reflector_prompt = self.prompts.get(Prompt.MULTI_AGENT_REFLEXION_FINAL_PROMPT)

        return {
            "strategy": "reflexion",
            "actor_prompt": actor_prompt,
            "evaluator_prompt": evaluator_prompt,
            "reflector_prompt": reflector_prompt,
            "status": "ready"
        }
