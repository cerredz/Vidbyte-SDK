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

from vidbyte.context.algorithms import (
    ContextWindowAlgorithm,
    MultiProviderAgenticGraderAlgorithm,
    ReflexionAlgorithm,
    TrajectoryCheckpointAlgorithm,
    ToolResultAdmission,
)


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
    def reflexion(self) -> ContextWindowAlgorithm:
        """Run failed attempts through Reflexion retry and self-reflection."""
        return ContextWindowAlgorithm(
            name="reflexion",
            reflexion=ReflexionAlgorithm(),
        )

    @property
    def multi_provider_agentic_grader(self) -> ContextWindowAlgorithm:
        # Run queries concurrently across providers and select the best response via meta-grader.
        return ContextWindowAlgorithm(
            name="multi_provider_agentic_grader",
            multi_provider_agentic_grader=MultiProviderAgenticGraderAlgorithm(),
        )

    @property
    def trajectory_checkpoints(self) -> ContextWindowAlgorithm:
        """Inject deterministic runtime checkpoints during direct agent loops."""
        return ContextWindowAlgorithm(
            name="trajectory_checkpoints",
            trajectory_checkpoints=TrajectoryCheckpointAlgorithm(),
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


__all__ = [
    "ContextWindowPresets",
    "resolve_context_window_algorithm",
]
