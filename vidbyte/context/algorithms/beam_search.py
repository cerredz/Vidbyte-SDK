"""Context Protocol Header

Description:
    Implements the public Beam Search algorithm configuration.
Purpose:
    Defines the frozen, type-safe settings for running beam_width parallel
    agent trials, scoring each output with an LLM scorer, and returning the
    highest-scored result.
Architecture:
    - BeamSearchAlgorithm: Immutable public configuration class.
Relations:
    Used by ContextWindowPresets and AgentRuntimeContextAlgorithms to configure
    the runtime adapter.
Similar Files:
    - vidbyte/context/algorithms/reflexion.py: A similar context-window algorithm
      public configuration.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import ConfigurationError

_MAX_SCORER_CHARS_LIMIT = 1_000_000
_REQUIRED_SCORER_PLACEHOLDERS = {"task", "candidate"}

_DEFAULT_SCORER_SYSTEM_PROMPT = (
    "You are an impartial evaluator. Score the candidate answer on a scale of 0 to 10 "
    "for quality, completeness, and correctness relative to the task. "
    "Respond with a single integer between 0 and 10 and nothing else."
)

_DEFAULT_SCORER_PROMPT = (
    "Task:\n{task}\n\nCandidate answer:\n{candidate}\n\nScore (0-10):"
)


@dataclass(frozen=True, slots=True)
class BeamSearchAlgorithm:
    """Public immutable config for the Beam Search runtime algorithm."""

    beam_width: int = 3
    max_scorer_chars: int = 8000
    scorer_system_prompt: str | None = None
    scorer_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates all configuration fields at construction time.
        _validate_beam_width(self.beam_width)
        _validate_scorer_chars(self.max_scorer_chars)
        _validate_prompt_override(self.scorer_system_prompt, "scorer_system_prompt")
        _validate_scorer_prompt_placeholders(self.scorer_prompt)
        _validate_metadata_keys(self.metadata)

    def scorer_system_prompt_text(self) -> str:
        """Return the system prompt for the scorer stage."""
        return self.scorer_system_prompt or _DEFAULT_SCORER_SYSTEM_PROMPT

    def render_scorer_prompt(self, task: str, candidate: str) -> str:
        """Render the scorer prompt with the task and candidate answer."""
        template = self.scorer_prompt or _DEFAULT_SCORER_PROMPT
        return template.format(task=task, candidate=candidate)

    def truncate_candidate(self, output: str) -> str:
        """Trim candidate output to max_scorer_chars before passing to the scorer."""
        if len(output) <= self.max_scorer_chars:
            return output
        return output[: self.max_scorer_chars].rstrip() + "\n...[candidate truncated]"


def _validate_beam_width(beam_width: int) -> None:
    # Raises ConfigurationError if beam_width is less than one.
    if beam_width < 1:
        raise ConfigurationError("beam_width must be at least 1.")


def _validate_scorer_chars(max_scorer_chars: int) -> None:
    # Raises ConfigurationError if max_scorer_chars is outside the valid positive range.
    if max_scorer_chars <= 0:
        raise ConfigurationError("max_scorer_chars must be greater than zero.")
    if max_scorer_chars > _MAX_SCORER_CHARS_LIMIT:
        raise ConfigurationError(
            f"max_scorer_chars ({max_scorer_chars}) exceeds the safeguard limit of {_MAX_SCORER_CHARS_LIMIT}."
        )


def _validate_prompt_override(value: str | None, field_name: str) -> None:
    # Raises ConfigurationError if an optional prompt override is provided but empty.
    if value is not None and not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")


def _validate_scorer_prompt_placeholders(scorer_prompt: str | None) -> None:
    # Raises ConfigurationError if scorer_prompt is missing {task} or {candidate}.
    if scorer_prompt is None:
        return
    if not scorer_prompt.strip():
        raise ConfigurationError("scorer_prompt must be a non-empty string when provided.")
    found = {name for _, name, _, _ in string.Formatter().parse(scorer_prompt) if name is not None}
    missing = _REQUIRED_SCORER_PLACEHOLDERS - found
    if missing:
        raise ConfigurationError(
            f"scorer_prompt is missing required formatting placeholders: {sorted(missing)}."
        )


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Raises ConfigurationError if any metadata key is not a string.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


__all__ = [
    "BeamSearchAlgorithm",
]
