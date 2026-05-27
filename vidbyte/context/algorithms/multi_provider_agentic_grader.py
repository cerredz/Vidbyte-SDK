"""Context Protocol Header

Description:
    Implements the public Multi-Provider Agentic Grader algorithm configuration.
Purpose:
    Defines the frozen, type-safe settings for executing requests concurrently
    across multiple model providers, running agentic loops, and meta-grading results.
Architecture:
    - MultiProviderAgenticGraderAlgorithm: Immutable public configuration class.
Key Functions:
    - render_grader_prompt: Renders the prompt for the meta-grader with the original request and candidate results.
    - grader_system_prompt_text: Exposes the system instruction for the grader LLM.
    - agent_system_prompt_text: Exposes the system instruction override for individual provider agents.
Relations:
    Used by ContextWindowPresets and AgentRuntimeContextAlgorithms to configure the runtime adapter.
Similar Files:
    - vidbyte/context/algorithms/reflexion.py: A similar context-window algorithm public configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts


@dataclass(frozen=True, slots=True)
class MultiProviderAgenticGraderAlgorithm:
    """Public immutable config for the Multi-Provider Agentic Grader algorithm."""

    provider_models: Mapping[str, str] | None = None
    grader_provider: str = "openai"
    grader_model: str = "gpt-4o"
    agent_system_prompt: str | None = None
    grader_system_prompt: str | None = None
    grader_prompt: str | None = None
    max_grader_chars: int = 15000
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates Multi-Provider Agentic Grader configuration limits.
        if self.max_grader_chars <= 0:
            raise ValueError("max_grader_chars must be greater than zero.")

    def render_grader_prompt(self, request: str, candidates: str) -> str:
        # Render the meta-grader prompt with the original task request and candidate outputs.
        template = self.grader_prompt or Prompts().get(Prompt.MULTI_PROVIDER_AGENTIC_GRADER_GRADER_PROMPT)
        return template.format(request=request, candidates=candidates)

    def grader_system_prompt_text(self) -> str:
        # Return the system prompt for the grader stage.
        return self.grader_system_prompt or Prompts().get(Prompt.MULTI_PROVIDER_AGENTIC_GRADER_GRADER_SYSTEM_PROMPT)

    def agent_system_prompt_text(self, original_prompt: str) -> str:
        # Return the system prompt override for individual provider agents.
        if self.agent_system_prompt is not None:
            return self.agent_system_prompt
        return original_prompt


__all__ = [
    "MultiProviderAgenticGraderAlgorithm",
]
