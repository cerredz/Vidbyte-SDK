"""Context Protocol Header

Description:
    Implements the Reflexion runtime context-window algorithm.
Purpose:
    Gives agents an attached retry/reflection loop when configured with
    ContextWindow.preset.reflexion.
Architecture:
    - ReflexionAlgorithm: Runtime policy for failed attempts, reflection
      prompt rendering, and retry context injection.
Relations:
    Used by ContextWindowAlgorithm and AgentRuntime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from vidbyte.lib.dataclasses.agents import AgentStopReason
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult


@dataclass(frozen=True, slots=True)
class ReflexionAlgorithm:
    """Runtime Reflexion policy attached to a context-window algorithm."""

    max_trials: int = 3
    max_reflection_chars: int = 1200
    max_attempt_chars: int = 6000
    agent_system_prompt: str | None = None
    reflect_system_prompt: str | None = None
    reflect_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate Reflexion limits."""
        if self.max_trials <= 0:
            raise ValueError("max_trials must be greater than zero.")
        if self.max_reflection_chars <= 0:
            raise ValueError("max_reflection_chars must be greater than zero.")
        if self.max_attempt_chars <= 0:
            raise ValueError("max_attempt_chars must be greater than zero.")

    def context_for_trial(
        self,
        context: BaseAgentContext,
        *,
        task: str,
        reflections: Sequence[str],
        failed_attempts: Sequence[str],
    ) -> BaseAgentContext:
        """Return a context with Reflexion memory injected for retry trials."""
        if not reflections:
            return context
        template = self.agent_system_prompt or Prompts().get(Prompt.REFLEXION_AGENT_SYSTEM_PROMPT)
        system_prompt = template.format(
            system_prompt=context.system_prompt or "",
            task=task,
            reflections=self.format_reflections(reflections),
            previous_attempt=self._latest(failed_attempts),
        )
        return replace(
            context,
            system_prompt=system_prompt,
            metadata={
                **dict(context.metadata),
                "context_window_algorithm": "reflexion",
                "reflexion_reflection_count": len(tuple(reflections)),
            },
        )

    def should_reflect(self, result: AgentResult, *, trial_index: int) -> bool:
        """Return whether the failed attempt should produce reflection and retry."""
        if trial_index >= self.max_trials - 1:
            return False
        return self.stop_reason(result) is not AgentStopReason.IS_DONE

    def render_reflection_prompt(
        self,
        *,
        task: str,
        failed_attempt: str,
        reflections: Sequence[str],
    ) -> str:
        """Render the reflection-stage user prompt from prompt assets or overrides."""
        template = self.reflect_prompt or Prompts().get(Prompt.REFLEXION_REFLECT_PROMPT)
        return template.format(
            task=task,
            failed_attempt=failed_attempt,
            reflections=self.format_reflections(reflections) or "No prior reflections.",
        )

    def reflection_system_prompt(self) -> str:
        """Return the reflection-stage system prompt."""
        return self.reflect_system_prompt or Prompts().get(Prompt.REFLEXION_REFLECT_SYSTEM_PROMPT)

    def capture_reflection(self, output: str) -> str:
        """Normalize and bound model reflection text before storing it."""
        reflection = output.strip()
        if len(reflection) <= self.max_reflection_chars:
            return reflection
        return reflection[: self.max_reflection_chars].rstrip() + "\n...[reflection truncated]"

    def format_failed_attempt(self, result: AgentResult) -> str:
        """Render the failed trial state as a compact scratchpad for reflection."""
        lines = [
            f"Stop reason: {self.stop_reason(result).value}",
            f"Output: {result.output}",
        ]
        tool_calls = tuple(dict(result.metadata).get("tool_calls", ()))
        if tool_calls:
            lines.append("Tool calls:")
            for call in tool_calls:
                name = str(getattr(call, "tool_name", "unknown"))
                state = getattr(getattr(call, "state", None), "value", getattr(call, "state", "unknown"))
                output = str(getattr(getattr(call, "result", None), "output", ""))
                lines.append(f"- {name} ({state}): {output}")
        return self._truncate("\n".join(lines), self.max_attempt_chars, "attempt")

    @staticmethod
    def stop_reason(result: AgentResult) -> AgentStopReason:
        """Read a AgentResult stop reason with a conservative fallback."""
        raw = dict(result.metadata).get("stop_reason", AgentStopReason.FINAL_RESPONSE.value)
        try:
            return AgentStopReason(str(raw))
        except ValueError:
            return AgentStopReason.ERROR

    @staticmethod
    def format_reflections(reflections: Sequence[str]) -> str:
        """Render accumulated verbal reinforcement memory."""
        cleaned = tuple(reflection.strip() for reflection in reflections if reflection.strip())
        if not cleaned:
            return ""
        return "Reflections:\n" + "\n".join(f"- {reflection}" for reflection in cleaned)

    @staticmethod
    def _latest(items: Sequence[str]) -> str:
        return tuple(items)[-1] if items else "No failed attempt has been recorded yet."

    @staticmethod
    def _truncate(value: str, max_chars: int, label: str) -> str:
        if len(value) <= max_chars:
            return value
        return value[:max_chars].rstrip() + f"\n...[{label} truncated]"


__all__ = [
    "ReflexionAlgorithm",
]


