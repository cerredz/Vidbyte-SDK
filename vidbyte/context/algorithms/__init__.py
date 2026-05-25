"""Context Protocol Header

Description:
    Exposes context-window algorithm implementations.
Purpose:
    Keeps runtime context algorithms separate from preset registration and
    public context primitives.
Architecture:
    - Tool-result admission algorithms from tool_results.
    - Config types, event payloads, and message wrappers from types.
    - Reasoning trace rendering from reasoning_trace.
    - Plan-then-implement helpers from plan_then_implement.
Relations:
    Used by vidbyte.context.presets and AgentRuntime.
"""

from __future__ import annotations

from vidbyte.context.algorithms.plan_then_implement import (
    DEFAULT_PLAN_PROMPT,
    build_plan_prompt,
    fallback_plan,
    plan_artifact_from_text,
)
from vidbyte.context.algorithms.reasoning_trace import (
    DEFAULT_REASONING_TRACE_PROMPT,
    render_reasoning_trace,
)
from vidbyte.context.algorithms.tool_results import (
    ContextWindowAlgorithm,
    ToolResultAdmission,
)
from vidbyte.context.algorithms.types import (
    ContextWindowIterationEvent,
    ContextWindowMessage,
    PlanThenImplementConfig,
    ReasoningTraceConfig,
    ReasoningTraceSize,
)

__all__ = [
    "ContextWindowAlgorithm",
    "ContextWindowIterationEvent",
    "ContextWindowMessage",
    "DEFAULT_PLAN_PROMPT",
    "DEFAULT_REASONING_TRACE_PROMPT",
    "PlanThenImplementConfig",
    "ReasoningTraceConfig",
    "ReasoningTraceSize",
    "ToolResultAdmission",
    "build_plan_prompt",
    "fallback_plan",
    "plan_artifact_from_text",
    "render_reasoning_trace",
]
