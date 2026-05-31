"""Context Protocol Header

Description:
    Implements public configuration for the adversarial reflection algorithm.
Purpose:
    Defines validated settings, prompt rendering, critique scheduling, and
    bounded critique capture for scheduled adversarial context injection.
Architecture:
    - AdversarialReflectionAlgorithm: Immutable public config object.
Relations:
    Used by ContextWindow presets and the runtime adversarial reflection adapter.
"""

from __future__ import annotations

import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts import Prompts
from vidbyte.tools.adversarial_agent_tool import AdversarialAgentTool

_MAX_CRITIQUE_CHARS_LIMIT = 1_000_000
_REQUIRED_ADVERSARIAL_PLACEHOLDERS = {"task", "trajectory", "iteration_count", "critique_count"}


@dataclass(frozen=True, slots=True)
class AdversarialReflectionAlgorithm:
    """Public immutable config for scheduled adversarial critique."""

    interval_iterations: int = 3
    max_critiques: int | None = 3
    max_critique_chars: int = 2000
    adversarial_tool: AdversarialAgentTool | None = None
    adversarial_system_prompt: str | None = None
    adversarial_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate all configuration fields at construction time.
        _validate_interval_iterations(self.interval_iterations)
        _validate_max_critiques(self.max_critiques)
        _validate_max_critique_chars(self.max_critique_chars)
        _validate_prompt_override(self.adversarial_system_prompt, "adversarial_system_prompt")
        _validate_adversarial_prompt(self.adversarial_prompt)
        _validate_metadata_keys(self.metadata)

    def render_adversarial_prompt(self, *, task: str, trajectory: str, iteration_count: int, critique_count: int) -> str:
        # Render the adversarial user prompt with task and trajectory sections.
        template = self.adversarial_prompt or Prompts().get(Prompt.ADVERSARIAL_REFLECTION_ADVERSARIAL_PROMPT)
        return template.format(task=task, trajectory=trajectory or "No trajectory has been recorded.", iteration_count=iteration_count, critique_count=critique_count)

    def adversarial_system_prompt_text(self) -> str:
        # Return the adversarial system prompt from override or catalog.
        return self.adversarial_system_prompt or Prompts().get(Prompt.ADVERSARIAL_REFLECTION_ADVERSARIAL_SYSTEM_PROMPT)

    def capture_critique(self, output: str) -> str:
        # Normalize and bound critique text before injecting it into context.
        critique = output.strip()
        if not critique:
            return "The adversarial critique produced no actionable feedback."
        return _truncate_with_suffix(critique, self.max_critique_chars, "\n...[adversarial critique truncated]")

    def should_run_critique(self, *, iteration_count: int, critique_count: int, terminal: bool) -> bool:
        # Return whether a scheduled critique should run after this iteration.
        if terminal or self.max_critiques == 0:
            return False
        if self.max_critiques is not None and critique_count >= self.max_critiques:
            return False
        return iteration_count > 0 and iteration_count % self.interval_iterations == 0

    @staticmethod
    def format_trajectory(*, task: str, output: str, call_contexts: Sequence[Any], max_chars: int) -> str:
        # Render a bounded trajectory summary for the adversarial critique prompt.
        lines = [f"Task: {task}", f"Latest output: {output or 'N/A'}"]
        if call_contexts:
            lines.append("Tool observations:")
            for context in call_contexts:
                name = str(getattr(context, "tool_name", getattr(context, "name", "unknown")))
                state = str(getattr(getattr(context, "state", None), "value", getattr(context, "state", "unknown")))
                result = getattr(context, "result", None)
                result_output = str(getattr(result, "output", getattr(context, "output", "")))
                lines.append(f"- {name} ({state}): {result_output}")
        return _truncate_with_suffix("\n".join(lines), max_chars, "\n...[trajectory truncated]")


def _validate_interval_iterations(interval_iterations: int) -> None:
    # Require a positive scheduling interval.
    if interval_iterations <= 0:
        raise ConfigurationError("interval_iterations must be greater than zero.")


def _validate_max_critiques(max_critiques: int | None) -> None:
    # Allow None for unbounded critique count and zero for disabled scheduling.
    if max_critiques is not None and max_critiques < 0:
        raise ConfigurationError("max_critiques must be greater than or equal to zero when provided.")


def _validate_max_critique_chars(max_critique_chars: int) -> None:
    # Bound critique text to protect the context window.
    if max_critique_chars <= 0:
        raise ConfigurationError("max_critique_chars must be greater than zero.")
    if max_critique_chars > _MAX_CRITIQUE_CHARS_LIMIT:
        raise ConfigurationError(f"max_critique_chars exceeds limit of {_MAX_CRITIQUE_CHARS_LIMIT}.")


def _validate_prompt_override(value: str | None, field_name: str) -> None:
    # Reject empty prompt overrides because they otherwise silently fall back.
    if value is not None and not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")


def _validate_adversarial_prompt(adversarial_prompt: str | None) -> None:
    # Validate custom adversarial prompt placeholders.
    if adversarial_prompt is None:
        return
    if not adversarial_prompt.strip():
        raise ConfigurationError("adversarial_prompt must be a non-empty string when provided.")
    found = {name for _, name, _, _ in string.Formatter().parse(adversarial_prompt) if name is not None}
    missing = _REQUIRED_ADVERSARIAL_PLACEHOLDERS - found
    if missing:
        raise ConfigurationError(f"adversarial_prompt is missing required formatting placeholders: {sorted(missing)}.")


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Reject non-string metadata keys for stable JSON-like metadata.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


def _truncate_with_suffix(value: str, max_chars: int, suffix: str) -> str:
    # Truncate text while keeping the final string within max_chars.
    if len(value) <= max_chars:
        return value
    if max_chars <= len(suffix):
        return suffix[-max_chars:]
    return value[: max_chars - len(suffix)].rstrip() + suffix


__all__ = [
    "AdversarialReflectionAlgorithm",
]

