"""Context Protocol Header

Description:
    Implements tool-result admission algorithms for context-window presets.
Purpose:
    Controls how raw tool output is represented in model-visible provider
    messages while preserving full tool results in runtime metadata.
Architecture:
    - ToolResultAdmission: Supported admission modes.
    - ContextWindowAlgorithm: Immutable, mutually exclusive runtime algorithm object,
      including optional Independent Critic and critique-adjudicate-revise policies.
Relations:
    Used by vidbyte.context.presets and AgentRuntime.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.context.compaction import CompactionMode, ContextCompactionEngine
from vidbyte.context.algorithms.reflexion import ReflexionAlgorithm
from vidbyte.context.algorithms.independent_critic import IndependentCriticAlgorithm
from vidbyte.context.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderAlgorithm
from vidbyte.context.algorithms.trajectory_checkpoints import TrajectoryCheckpointAlgorithm
from vidbyte.context.algorithms.problem_space_search import ProblemSpaceSearchAlgorithm
from vidbyte.context.algorithms.error_correction import ErrorCorrectionAlgorithm
from vidbyte.context.algorithms.critique_adjudicate_revise import CritiqueAdjudicateReviseAlgorithm
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult


class ToolResultAdmission(str, Enum):
    """How a context-window algorithm admits tool results into model context."""

    RAW = "raw"
    COMPACT = "compact"
    HIDE_RAW = "hide_raw"


@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    """Named runtime behavior that controls context-window admission."""

    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    reflexion: ReflexionAlgorithm | None = None
    multi_provider_agentic_grader: MultiProviderAgenticGraderAlgorithm | None = None
    independent_critic: IndependentCriticAlgorithm | None = None
    trajectory_checkpoints: TrajectoryCheckpointAlgorithm | None = None
    problem_space_search: ProblemSpaceSearchAlgorithm | None = None
    error_correction: ErrorCorrectionAlgorithm | None = None
    critique_adjudicate_revise: CritiqueAdjudicateReviseAlgorithm | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Verifies that at most one runtime context algorithm is configured.
        active = [x for x in (self.reflexion, self.multi_provider_agentic_grader, self.independent_critic, self.trajectory_checkpoints, self.problem_space_search, self.error_correction, self.critique_adjudicate_revise) if x is not None]
        if len(active) > 1:
            raise ValueError("At most one runtime context-window algorithm can be configured.")

    def model_visible_tool_result(self, call: ToolCall, result: ToolResult) -> ToolResult:

        """Return the compatibility model-visible tool result for direct callers."""
        admission = ToolResultAdmission(self.tool_result_admission)
        if admission is ToolResultAdmission.RAW:
            return result
        engine = ContextCompactionEngine()
        if admission is ToolResultAdmission.COMPACT:
            visible, _ = engine.compact_tool_result(call, result, mode=CompactionMode.TRUNCATE_TOOL_RESULTS, options={"max_chars": self.max_tool_result_chars, "truncation_indicator": "\n...[tool output compacted]"})
            return visible
        visible, _ = engine.compact_tool_result(call, result, mode=CompactionMode.HIDE_TOOL_RESULTS)
        return visible


__all__ = [
    "ContextWindowAlgorithm",
    "CritiqueAdjudicateReviseAlgorithm",
    "ErrorCorrectionAlgorithm",
    "IndependentCriticAlgorithm",
    "MultiProviderAgenticGraderAlgorithm",
    "ProblemSpaceSearchAlgorithm",
    "ReflexionAlgorithm",
    "TrajectoryCheckpointAlgorithm",
    "ToolResultAdmission",
]

