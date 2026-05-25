"""Context Protocol Header

Description:
    Shared config, event, and message types for context-window lifecycle algorithms.
Purpose:
    Keeps config objects, event payloads, and message wrappers in one typed location
    so algorithm renderers and the runtime can share them without circular imports.
Architecture:
    - ReasoningTraceConfig: Controls trace size, prompt, and metadata.
    - PlanThenImplementConfig: Controls planner prompt, artifact name, and bounds.
    - ContextWindowMessage: Role-content wrapper for lifecycle trace messages.
    - ContextWindowIterationEvent: Safe event payload for trace rendering.
Relations:
    Used by vidbyte.context.algorithms.reasoning_trace,
    vidbyte.context.algorithms.plan_then_implement, and AgentRuntime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.tools.types import ToolCallContext


class ReasoningTraceSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass(frozen=True, slots=True)
class ReasoningTraceConfig:
    size: ReasoningTraceSize = ReasoningTraceSize.MEDIUM
    system_prompt: str | None = None
    role: str = "user"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanThenImplementConfig:
    artifact_name: str = "Plan"
    planner_prompt: str | None = None
    max_plan_chars: int = 4000
    fallback_on_empty: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextWindowMessage:
    role: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextWindowIterationEvent:
    request: str
    iteration_count: int
    assistant_output: str | None = None
    tool_contexts: Sequence[ToolCallContext] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = [
    "ContextWindowIterationEvent",
    "ContextWindowMessage",
    "PlanThenImplementConfig",
    "ReasoningTraceConfig",
    "ReasoningTraceSize",
]
