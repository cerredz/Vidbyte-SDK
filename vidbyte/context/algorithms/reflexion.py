"""Context Protocol Header

Description:
    Implements Reflexion admission algorithms for context-window presets.
Purpose:
    Controls how prior-trial data (scratchpads and self-reflections) is
    admitted into model-visible context on subsequent attempts under the
    Noah Shinn Reflexion verbal reinforcement learning algorithm.
Architecture:
    - ReflexionAdmission: Supported admission modes (NONE / LAST_ATTEMPT /
      REFLEXION / LAST_ATTEMPT_AND_REFLEXION).
    - ReflexionConfig: Immutable configuration dataclass.
    - Pure helper functions: format_reflections, format_last_attempt,
      build_reflexion_context.
Relations:
    Used by vidbyte.context.algorithms.tool_results (ContextWindowAlgorithm
    reflexion field) and vidbyte.context.presets.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


REFLECTION_HEADER = (
    "You have attempted to answer the following task before and failed. "
    "The following reflection(s) give a plan to avoid failing the same way. "
    "Use them to improve your strategy.\n"
)

REFLECTION_AFTER_LAST_TRIAL_HEADER = (
    "The following reflection(s) give a plan to avoid failing the same way "
    "you did previously. Use them to improve your strategy.\n"
)

LAST_TRIAL_HEADER = (
    "You have attempted the following task before and failed. "
    "Below is the last trial you attempted.\n"
)


class ReflexionAdmission(str, Enum):
    """How a context-window algorithm admits reflexion data into model context."""

    NONE = "none"
    LAST_ATTEMPT = "last_attempt"
    REFLEXION = "reflexion"
    LAST_ATTEMPT_AND_REFLEXION = "last_attempt_and_reflexion"


@dataclass(frozen=True, slots=True)
class ReflexionConfig:
    """Immutable configuration for the Reflexion context-window algorithm."""

    admission: ReflexionAdmission = ReflexionAdmission.REFLEXION
    max_reflection_chars: int = 1000
    max_scratchpad_chars: int = 6000
    metadata: dict[str, Any] = field(default_factory=dict)


def format_reflections(
    reflections: Sequence[str],
    header: str = REFLECTION_HEADER,
) -> str:
    """Join accumulated self-reflections with a header and bullet points."""
    if not reflections:
        return ""
    return header + "Reflections:\n- " + "\n- ".join(r.strip() for r in reflections)


def format_last_attempt(
    question: str,
    scratchpad: str,
    header: str = LAST_TRIAL_HEADER,
    max_chars: int = 6000,
) -> str:
    """Format the previous trial scratchpad for context injection."""
    truncated = _truncate_scratchpad(scratchpad, max_chars)
    formatted = f"{header}Task: {question}\n{truncated}\n(END PREVIOUS TRIAL)"
    return formatted


def build_reflexion_context(
    config: ReflexionConfig,
    question: str,
    scratchpad: str,
    reflections: Sequence[str],
    context: str | None = None,
) -> str:
    """Build the full reflexion context string based on admission strategy."""
    admission = ReflexionAdmission(config.admission)

    if admission is ReflexionAdmission.NONE:
        return ""

    if admission is ReflexionAdmission.LAST_ATTEMPT:
        return format_last_attempt(question, scratchpad, max_chars=config.max_scratchpad_chars)

    if admission is ReflexionAdmission.REFLEXION:
        return format_reflections(reflections)

    if admission is ReflexionAdmission.LAST_ATTEMPT_AND_REFLEXION:
        parts: list[str] = []
        parts.append(format_last_attempt(question, scratchpad, max_chars=config.max_scratchpad_chars))
        parts.append(format_reflections(reflections, header=REFLECTION_AFTER_LAST_TRIAL_HEADER))
        return "\n".join(p for p in parts if p)

    return ""


def _truncate_scratchpad(scratchpad: str, max_chars: int) -> str:
    """Truncate a scratchpad to max_chars by removing the longest observation lines."""
    if max_chars <= 0 or len(scratchpad) <= max_chars:
        return scratchpad
    lines = scratchpad.split("\n")
    observation_lines = [line for line in lines if line.strip().startswith("Observation")]
    observation_lines.sort(key=len, reverse=True)
    while len("\n".join(lines)) > max_chars and observation_lines:
        longest = observation_lines.pop(0)
        try:
            idx = lines.index(longest)
        except ValueError:
            continue
        prefix = longest.split(":")[0] + ": "
        lines[idx] = prefix + "[truncated]"
    return "\n".join(lines)


__all__ = [
    "LAST_TRIAL_HEADER",
    "REFLECTION_AFTER_LAST_TRIAL_HEADER",
    "REFLECTION_HEADER",
    "ReflexionAdmission",
    "ReflexionConfig",
    "build_reflexion_context",
    "format_last_attempt",
    "format_reflections",
]
