"""Context Protocol Header

Description:
    Defines SDK-provided context-window algorithm presets.
Purpose:
    Gives developers a small named preset surface while keeping algorithm
    implementations in vidbyte.context.algorithms.
Architecture:
    - ContextWindowPresets: Registry for preset algorithms.
    - resolve_context_window_algorithm: Normalizes objects and preset names.
Relations:
    Used by vidbyte.context.window and BaseAgent.
"""

from __future__ import annotations

from vidbyte.context.algorithms import ContextWindowAlgorithm, ToolResultAdmission
from vidbyte.context.algorithms.types import (
    PlanThenImplementConfig,
    ReasoningTraceConfig,
    ReasoningTraceSize,
)

_REASONING_TRACE_SIZE_MAP = {
    "small": ReasoningTraceSize.SMALL,
    "medium": ReasoningTraceSize.MEDIUM,
    "large": ReasoningTraceSize.LARGE,
}


class ContextWindowPresets:
    """Registry of SDK-provided context-window algorithms."""

    @property
    def default(self) -> ContextWindowAlgorithm:
        """Preserve current behavior by admitting raw tool results."""
        return ContextWindowAlgorithm(name="default")

    @property
    def raw_tool_outputs(self) -> ContextWindowAlgorithm:
        """Alias for the default raw tool-output behavior."""
        return self.default

    @property
    def compact_tool_outputs(self) -> ContextWindowAlgorithm:
        """Admit bounded tool-result text instead of unbounded raw output."""
        return ContextWindowAlgorithm(
            name="compact_tool_outputs",
            tool_result_admission=ToolResultAdmission.COMPACT,
        )

    @property
    def hide_tool_outputs(self) -> ContextWindowAlgorithm:
        """Keep raw tool output in runtime metadata while hiding it from the model."""
        return ContextWindowAlgorithm(
            name="hide_tool_outputs",
            tool_result_admission=ToolResultAdmission.HIDE_RAW,
        )

    @property
    def no_raw_tool_outputs(self) -> ContextWindowAlgorithm:
        """Alias for hiding raw tool output from the model context window."""
        return self.hide_tool_outputs

    @property
    def reasoning_trace_small(self) -> ContextWindowAlgorithm:
        """Insert a small deterministic reasoning trace after each iteration."""
        return ContextWindowAlgorithm(
            name="reasoning_trace_small",
            reasoning_trace=ReasoningTraceConfig(size=ReasoningTraceSize.SMALL),
        )

    @property
    def reasoning_trace_medium(self) -> ContextWindowAlgorithm:
        """Insert a medium deterministic reasoning trace after each iteration."""
        return ContextWindowAlgorithm(
            name="reasoning_trace_medium",
            reasoning_trace=ReasoningTraceConfig(size=ReasoningTraceSize.MEDIUM),
        )

    @property
    def reasoning_trace_large(self) -> ContextWindowAlgorithm:
        """Insert a large deterministic reasoning trace after each iteration."""
        return ContextWindowAlgorithm(
            name="reasoning_trace_large",
            reasoning_trace=ReasoningTraceConfig(size=ReasoningTraceSize.LARGE),
        )

    def reasoning_trace(
        self,
        *,
        size: ReasoningTraceSize | str = ReasoningTraceSize.MEDIUM,
        system_prompt: str | None = None,
    ) -> ContextWindowAlgorithm:
        """Create a reasoning trace algorithm with a custom size and trace prompt."""
        resolved_size = _resolve_reasoning_trace_size(size)
        return ContextWindowAlgorithm(
            name="reasoning_trace",
            reasoning_trace=ReasoningTraceConfig(
                size=resolved_size,
                system_prompt=system_prompt,
            ),
        )

    @property
    def plan_then_implement(self) -> ContextWindowAlgorithm:
        """Create a plan artifact before normal execution."""
        return ContextWindowAlgorithm(
            name="plan_then_implement",
            plan_then_implement=PlanThenImplementConfig(),
        )

    def plan_then_implement_with(
        self,
        *,
        planner_prompt: str | None = None,
        artifact_name: str = "Plan",
        max_plan_chars: int = 4000,
    ) -> ContextWindowAlgorithm:
        """Create a plan-then-implement algorithm with custom plan settings."""
        return ContextWindowAlgorithm(
            name="plan_then_implement",
            plan_then_implement=PlanThenImplementConfig(
                planner_prompt=planner_prompt,
                artifact_name=artifact_name,
                max_plan_chars=max_plan_chars,
            ),
        )


def resolve_context_window_algorithm(
    algorithm: ContextWindowAlgorithm | str | None,
    *,
    presets: ContextWindowPresets | None = None,
) -> ContextWindowAlgorithm:
    """Normalize a preset object, preset name, or None into an algorithm."""
    preset_registry = presets or ContextWindowPresets()
    if algorithm is None:
        return preset_registry.default
    if isinstance(algorithm, ContextWindowAlgorithm):
        return algorithm
    try:
        preset = getattr(preset_registry, algorithm)
    except AttributeError as exc:
        raise ValueError(f"Unknown context window algorithm preset: {algorithm}") from exc
    if not isinstance(preset, ContextWindowAlgorithm):
        raise ValueError(f"Unknown context window algorithm preset: {algorithm}")
    return preset


def _resolve_reasoning_trace_size(size: ReasoningTraceSize | str) -> ReasoningTraceSize:
    if isinstance(size, ReasoningTraceSize):
        return size
    if isinstance(size, str):
        member = _REASONING_TRACE_SIZE_MAP.get(size)
        if member is not None:
            return member
        raise ValueError(
            f"Invalid reasoning trace size: {size}. "
            f"Choose from: {', '.join(_REASONING_TRACE_SIZE_MAP)}"
        )
    raise ValueError(f"Invalid reasoning trace size type: {type(size).__name__}")


__all__ = [
    "ContextWindowPresets",
    "resolve_context_window_algorithm",
]
