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

from collections.abc import Mapping
from typing import Any

from vidbyte.context.algorithms import (
    ContextWindowAlgorithm,
    ErrorCorrectionAlgorithm,
    IndependentCriticAlgorithm,
    MultiProviderAgenticGraderAlgorithm,
    ParallelPanelAlgorithm,
    ProblemSpaceSearchAlgorithm,
    ProsecutorDefenderJudgeAlgorithm,
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

    def parallel_panel(self, reviewer_count: int = 3, min_successful_reviews: int = 2, max_concurrency: int | None = None, per_reviewer_timeout_seconds: float | None = None, panel_timeout_seconds: float | None = None, max_candidate_chars: int = 50_000, max_review_chars: int = 6_000, artifact_names: tuple[str, ...] = (), max_artifact_chars: int = 4_000, max_total_artifact_chars: int = 16_000, reviewer_system_prompt: str | None = None, reviewer_prompt: str | None = None, metadata: Mapping[str, Any] | None = None) -> ContextWindowAlgorithm:
        # Builds a validated parallel-panel wrapper with caller-selected review limits.
        config = ParallelPanelAlgorithm(
            reviewer_count=reviewer_count,
            min_successful_reviews=min_successful_reviews,
            max_concurrency=max_concurrency,
            per_reviewer_timeout_seconds=per_reviewer_timeout_seconds,
            panel_timeout_seconds=panel_timeout_seconds,
            max_candidate_chars=max_candidate_chars,
            max_review_chars=max_review_chars,
            artifact_names=artifact_names,
            max_artifact_chars=max_artifact_chars,
            max_total_artifact_chars=max_total_artifact_chars,
            reviewer_system_prompt=reviewer_system_prompt,
            reviewer_prompt=reviewer_prompt,
            metadata=dict(metadata or {}),
        )
        return ContextWindowAlgorithm(name="parallel_panel", parallel_panel=config)

    @property
    def prosecutor_defender_judge(self) -> ContextWindowAlgorithm:
        # Runs one producer followed by isolated prosecutor, defender, and judge roles.
        return ContextWindowAlgorithm(name="prosecutor_defender_judge", prosecutor_defender_judge=ProsecutorDefenderJudgeAlgorithm())

    @property
    def independent_critic(self) -> ContextWindowAlgorithm:
        # Review one producer candidate inside a fresh critic-only runtime.
        return ContextWindowAlgorithm(name="independent_critic", independent_critic=IndependentCriticAlgorithm())

    @property
    def trajectory_checkpoints(self) -> ContextWindowAlgorithm:
        # Write deterministic trajectory checkpoints through ContextManager primitives.
        return ContextWindowAlgorithm(
            name="trajectory_checkpoints",
            trajectory_checkpoints=TrajectoryCheckpointAlgorithm(),
        )

    @property
    def problem_space_search(self) -> ContextWindowAlgorithm:
        # Every N iterations, surface unconsidered angles into the context window.
        return ContextWindowAlgorithm(
            name="problem_space_search",
            problem_space_search=ProblemSpaceSearchAlgorithm(),
        )

    @property
    def error_correction(self) -> ContextWindowAlgorithm:
        # Every N iterations, audit and clean the context window against the system prompt.
        return ContextWindowAlgorithm(
            name="error_correction",
            error_correction=ErrorCorrectionAlgorithm(),
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
    if callable(preset):
        preset = preset()
    if not isinstance(preset, ContextWindowAlgorithm):
        raise ValueError(f"Unknown context window algorithm preset: {algorithm}")
    return preset


__all__ = [
    "ContextWindowPresets",
    "resolve_context_window_algorithm",
]
