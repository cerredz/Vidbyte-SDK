"""Context Protocol Header

Description:
    Renders deterministic, model-visible reasoning trace messages from visible
    runtime state after each non-terminal direct agent runtime iteration.
Purpose:
    Gives the model an operational scaffold without exposing hidden chain-of-thought.
    Traces are deterministic given the same request, iteration number, visible
    assistant text, tool names, tool statuses, and config.
Architecture:
    - render_reasoning_trace(): Pure function that produces a ContextWindowMessage.
    - Size presets control the amount of inserted trace content.
Relations:
    Used by AgentRuntime._append_reasoning_trace_if_needed().
    Depends on vidbyte.context.algorithms.types for config and event types.
"""

from __future__ import annotations

from vidbyte.context.algorithms.types import (
    ContextWindowIterationEvent,
    ContextWindowMessage,
    ReasoningTraceConfig,
    ReasoningTraceSize,
)

DEFAULT_REASONING_TRACE_PROMPT = (
    "Maintain a concise operational trace for the next model call. "
    "Do not expose hidden chain-of-thought. Track visible state, constraints, next actions, and finish criteria."
)


def render_reasoning_trace(
    config: ReasoningTraceConfig,
    event: ContextWindowIterationEvent,
) -> ContextWindowMessage:
    """Render a deterministic reasoning trace message from visible runtime state."""
    parts: list[str] = ["Context window reasoning trace"]
    parts.append(f"Iteration: {event.iteration_count}")
    parts.append(f"Request: {_excerpt(event.request, 200)}")

    if event.assistant_output:
        parts.append(f"Last assistant output: {_excerpt(event.assistant_output, 200)}")

    if event.tool_contexts:
        tool_names = [ctx.tool_name for ctx in event.tool_contexts]
        tool_statuses = [ctx.state.value for ctx in event.tool_contexts]
        parts.append(f"Tools called: {', '.join(tool_names)}")
        parts.append(f"Tool statuses: {', '.join(tool_statuses)}")

    size = ReasoningTraceSize(config.size)

    if size is ReasoningTraceSize.SMALL:
        parts.append("Current state: Continue from the visible progress shown above.")
        parts.append("Next action: Determine the most direct remaining step.")
        parts.append("Finish check: Call isDone when the task is complete.")
    elif size is ReasoningTraceSize.MEDIUM:
        parts.append("Current state: Continue from the visible progress shown above.")
        parts.append("Next action: Determine the most direct remaining step.")
        parts.append("Constraints: Respect the original request scope and tool permissions.")
        parts.append("Alternate routes: Consider a different approach if current path stalls.")
        parts.append("Finish check: Call isDone when the task is complete.")
    else:
        parts.append("Current state: Continue from the visible progress shown above.")
        parts.append("Next action: Determine the most direct remaining step.")
        parts.append("Constraints: Respect the original request scope and tool permissions.")
        parts.append("Alternate routes: Consider a different approach if current path stalls.")
        parts.append("Risk check: Verify no critical information is missing before proceeding.")
        parts.append("Validation check: Confirm tool outputs are consistent with the request.")
        parts.append("Route tradeoffs: Prefer simpler routes when multiple paths are available.")
        parts.append("Finish check: Call isDone when the task is complete and verified.")

    content = "\n".join(parts)
    return ContextWindowMessage(role=config.role, content=content, metadata={"size": size.value})


def _excerpt(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


__all__ = [
    "DEFAULT_REASONING_TRACE_PROMPT",
    "render_reasoning_trace",
]
