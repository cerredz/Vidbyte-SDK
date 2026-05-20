# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the ReAct reasoning strategy for the Vidbyte SDK.
# Purpose: Orchestrates Thought-Action-Observation iterative agent loops.
# Architecture & Functions:
#   - ReActStrategy (subclass of BaseStrategy): Solves tasks using tools and PromptRegistry.
#   - ReActStrategy._build_system_prompt(): Fetches and renders system prompt with registered tools.
#   - ReActStrategy._build_iteration_prompt(): Fetches and renders current loop state.
# Codebase Relation:
#   - Integrates ToolRegistry and PromptRegistry to drive multi-turn agent logic.
# Similar Files:
#   - vidbyte/strategies/tree_of_thoughts.py (other strategy logic)
# ==============================================================================

from __future__ import annotations

from typing import Any

from vidbyte.prompts import PromptRegistry, PromptKey
from vidbyte.strategies.base import BaseStrategy
from vidbyte.tools import ToolRegistry


class ReActStrategy(BaseStrategy):
    """
    Implements the Reasoning and Acting (ReAct) strategy.
    Decouples reasoning prompts and tool availability using centralized registries.
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry
        self.prompt_registry = PromptRegistry()  # Singleton

    async def _build_system_prompt(self) -> str:
        """Retrieves and renders the ReAct system prompt with active tool specifications."""
        rendered = self.prompt_registry.get(
            PromptKey("strategies.react", "system"),
            tools=self.tool_registry.specs_as_prompt_str()
        )
        return rendered.text

    async def _build_iteration_prompt(self, task: str, history: str) -> str:
        """Retrieves and renders the ReAct turn-level prompt."""
        rendered = self.prompt_registry.get(
            PromptKey("strategies.react", "iteration"),
            task=task,
            history=history
        )
        return rendered.text

    async def run(self, input_text: str, **kwargs: Any) -> Any:
        """
        Executes a mock representation of the ReAct multi-turn loop.
        In a full implementation, this drives the ModelRunner and ToolExecutor loop.
        """
        system_prompt = await self._build_system_prompt()
        iteration_prompt = await self._build_iteration_prompt(input_text, history="(No history yet)")

        # Returns a structure indicating successful prompt compilation and mock execution planning
        return {
            "strategy": "react",
            "system_prompt": system_prompt,
            "iteration_prompt": iteration_prompt,
            "status": "ready",
            "tools_loaded": [t.name for t in self.tool_registry.all()],
        }
