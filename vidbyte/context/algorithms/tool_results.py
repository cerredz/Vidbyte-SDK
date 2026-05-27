"""Context Protocol Header

Description:
    Implements tool-result admission algorithms for context-window presets.
Purpose:
    Controls how raw tool output is represented in model-visible provider
    messages while preserving full tool results in runtime metadata.
Architecture:
    - ToolResultAdmission: Supported admission modes.
    - ContextWindowAlgorithm: Immutable runtime algorithm object.
Relations:
    Used by vidbyte.context.presets and AgentRuntime.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.context.algorithms.reflexion import ReflexionAlgorithm
from vidbyte.context.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderAlgorithm
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
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Verifies that at most one runtime context algorithm is configured.
        active = [x for x in (self.reflexion, self.multi_provider_agentic_grader) if x is not None]
        if len(active) > 1:
            raise ValueError("At most one runtime context-window algorithm can be configured.")

    def model_visible_tool_result(self, call: ToolCall, result: ToolResult) -> ToolResult:

        """Return the tool result that should be appended to provider messages."""
        admission = ToolResultAdmission(self.tool_result_admission)
        if admission is ToolResultAdmission.RAW:
            return result
        if admission is ToolResultAdmission.COMPACT:
            output = _compact_output(result.output, self.max_tool_result_chars)
            return _replace_tool_result(
                result,
                output,
                {
                    "context_window_algorithm": self.name,
                    "raw_output_compacted": output != result.output,
                    "raw_output_chars": len(result.output),
                },
            )
        return _replace_tool_result(
            result,
            (
                f"Tool '{call.tool_name}' completed with status '{result.status.value}'. "
                "Raw tool output was withheld from the model context window."
            ),
            {
                "context_window_algorithm": self.name,
                "raw_output_hidden": True,
                "raw_output_chars": len(result.output),
            },
        )


def _replace_tool_result(
    result: ToolResult,
    output: str,
    metadata: Mapping[str, Any],
) -> ToolResult:
    result_metadata = {**dict(result.metadata), **dict(metadata)}
    return ToolResult(
        tool_name=result.tool_name,
        status=result.status,
        output=output,
        metadata=result_metadata,
    )


def _compact_output(output: str, max_chars: int) -> str:
    if max_chars <= 0 or len(output) <= max_chars:
        return output
    return output[:max_chars].rstrip() + "\n...[tool output compacted]"


__all__ = [
    "ContextWindowAlgorithm",
    "MultiProviderAgenticGraderAlgorithm",
    "ReflexionAlgorithm",
    "ToolResultAdmission",
]

