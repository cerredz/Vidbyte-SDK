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

import string
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.models import ProviderModelRegistry
from vidbyte.prompts import Prompts

_MAX_GRADER_CHARS_LIMIT = 1_000_000
_REQUIRED_GRADER_PLACEHOLDERS = {"request", "candidates"}


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
        # Validates all configuration fields at construction time to surface errors early.
        _validate_grader_chars(self.max_grader_chars)
        ProviderModelRegistry.validate_provider(self.grader_provider)
        ProviderModelRegistry.validate_model(self.grader_model)
        if self.provider_models is not None:
            ProviderModelRegistry.validate_provider_models_map(self.provider_models)
        _validate_prompt_override(self.agent_system_prompt, "agent_system_prompt")
        _validate_prompt_override(self.grader_system_prompt, "grader_system_prompt")
        _validate_grader_prompt_placeholders(self.grader_prompt)
        _validate_metadata_keys(self.metadata)

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


def _validate_grader_chars(max_grader_chars: int) -> None:
    # Raises ConfigurationError if max_grader_chars is outside the valid positive range.
    if max_grader_chars <= 0:
        raise ConfigurationError("max_grader_chars must be greater than zero.")
    if max_grader_chars > _MAX_GRADER_CHARS_LIMIT:
        raise ConfigurationError(f"max_grader_chars ({max_grader_chars}) exceeds the safeguard limit of {_MAX_GRADER_CHARS_LIMIT}.")


def _validate_prompt_override(value: str | None, field_name: str) -> None:
    # Raises ConfigurationError if an optional prompt override is provided but empty.
    if value is not None and not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")


def _validate_grader_prompt_placeholders(grader_prompt: str | None) -> None:
    # Raises ConfigurationError if grader_prompt is missing the required {request} or {candidates} placeholders.
    if grader_prompt is None:
        return
    if not grader_prompt.strip():
        raise ConfigurationError("grader_prompt must be a non-empty string when provided.")
    found = {name for _, name, _, _ in string.Formatter().parse(grader_prompt) if name is not None}
    missing = _REQUIRED_GRADER_PLACEHOLDERS - found
    if missing:
        raise ConfigurationError(f"grader_prompt is missing required formatting placeholders: {sorted(missing)}.")


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Raises ConfigurationError if any metadata key is not a string.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


__all__ = [
    "MultiProviderAgenticGraderAlgorithm",
]
