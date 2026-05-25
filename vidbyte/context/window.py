"""Context Protocol Header

Description:
    Defines named context-window algorithm presets for agent runtime behavior.
Purpose:
    Gives developers a simple agent-level knob for common context-window
    strategies without requiring a custom compiler or renderer abstraction.
Architecture:
    - ContextWindowAlgorithm: Immutable preset describing runtime admission rules.
    - ContextWindow: Namespace for SDK-provided preset algorithms.
Relations:
    Used by BaseAgent and AgentRuntime to decide what tool output is admitted
    back into the model-visible context window.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult


class ToolResultAdmission(str, Enum):
    """How a context-window algorithm admits tool results into model context."""

    RAW = "raw"
    COMPACT = "compact"
    HIDE_RAW = "hide_raw"


@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    """Named context-window behavior that can be attached to an agent."""

    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    metadata: Mapping[str, Any] = field(default_factory=dict)

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


class _ContextWindowPresets:
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


class ContextWindow:
    """Namespace for context-window algorithm presets."""

    preset = _ContextWindowPresets()

    @staticmethod
    def resolve_algorithm(
        algorithm: ContextWindowAlgorithm | str | None,
    ) -> ContextWindowAlgorithm:
        """Normalize a preset object, preset name, or None into an algorithm."""
        if algorithm is None:
            return ContextWindow.preset.default
        if isinstance(algorithm, ContextWindowAlgorithm):
            return algorithm
        try:
            preset = getattr(ContextWindow.preset, algorithm)
        except AttributeError as exc:
            raise ValueError(f"Unknown context window algorithm preset: {algorithm}") from exc
        if not isinstance(preset, ContextWindowAlgorithm):
            raise ValueError(f"Unknown context window algorithm preset: {algorithm}")
        return preset


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
    "ContextWindow",
    "ContextWindowAlgorithm",
    "ToolResultAdmission",
]
