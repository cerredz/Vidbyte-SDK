"""Context Protocol Header

Description:
    Defines inner-loop context-window lifecycle contracts.
Purpose:
    Gives context-window algorithms a small, standard way to update the active
    ContextManager during direct agent runtime execution.
Architecture:
    - ContextWindowLifecycleEvent: Named direct-runtime lifecycle points.
    - ContextWindowPlacement: Rendering placement for managed primitives.
    - InnerContextWindowAlgorithm: No-op base class for lifecycle algorithms.
    - ContextWindowRunContext: Mutable per-run view and write surface.
Relations:
    Used by AgentRuntime, ContextManager, and context-window algorithms.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem
    from vidbyte.context.templates import RecorderBase
    from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
    from vidbyte.tools.types import ToolCall, ToolResult


class ContextWindowLifecycleEvent(str, Enum):
    """Lifecycle points exposed to inner-loop context-window algorithms."""

    RUN_START = "run_start"
    BEFORE_MODEL_CALL = "before_model_call"
    AFTER_MODEL_RESPONSE = "after_model_response"
    AFTER_TOOL_CALL = "after_tool_call"
    AFTER_ITERATION = "after_iteration"
    RUN_END = "run_end"


class ContextWindowPlacement(str, Enum):
    """Placement targets for managed context-window primitives."""

    TOP_OF_CONTEXT = "top_of_context"
    END_OF_CONTEXT = "end_of_context"
    TOP_OF_CONVERSATION = "top_of_conversation"
    END_OF_CONVERSATION = "end_of_conversation"


class InnerContextWindowAlgorithm:
    """No-op base class for algorithms that update context during a direct run."""

    def on_run_start(self, ctx: ContextWindowRunContext) -> None:
        # Runs once before the direct runtime loop starts.
        del ctx

    def before_model_call(self, ctx: ContextWindowRunContext) -> None:
        # Runs before each model call is assembled and invoked.
        del ctx

    def after_model_response(self, ctx: ContextWindowRunContext) -> None:
        # Runs after a successful model response is accepted by middleware.
        del ctx

    def after_tool_call(self, ctx: ContextWindowRunContext) -> None:
        # Runs after a tool call has executed or been denied.
        del ctx

    def after_iteration(self, ctx: ContextWindowRunContext) -> None:
        # Runs after a completed non-final runtime iteration.
        del ctx

    def on_run_end(self, ctx: ContextWindowRunContext) -> None:
        # Runs before the final AgentResult is returned.
        del ctx


@dataclass(slots=True)
class ContextWindowRunContext:
    """Small write surface for inner-loop context-window algorithms."""

    event: ContextWindowLifecycleEvent
    context_manager: ContextManager
    recorder: RecorderBase
    metadata: dict[str, Any]
    message: str
    provider: str
    iteration: AgentIterationSnapshot | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    model_response: object | None = None
    is_final: bool = False

    def upsert(self, item: ContextItem, *, placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT) -> None:
        # Writes or replaces a managed primitive in the active context manager.
        self.context_manager.upsert(item, placement=placement)

    def append(self, item: ContextItem, *, placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT) -> str:
        # Writes a primitive, creating a stable per-run primitive id when needed.
        primitive_id = str(getattr(item, "primitive_id", "") or "").strip()
        if not primitive_id:
            primitive_id = self._next_append_id(item)
            item = self._with_primitive_id(item, primitive_id)
        self.upsert(item, placement=placement)
        return primitive_id

    def remove(self, primitive_id: str) -> None:
        # Removes a managed primitive from the active context manager.
        self.context_manager.remove_by_id(primitive_id)

    def record(self, slot: str, **metadata: Any) -> None:
        # Records a context-window template slot through the active recorder.
        self.recorder.append(slot, **metadata)

    def set_metadata(self, key: str, value: Any) -> None:
        # Stores a final metadata value for the active context-window algorithm.
        self.metadata[key] = value

    def every(self, *, iterations: int) -> bool:
        # Returns whether the current completed iteration is a positive multiple.
        if iterations <= 0:
            raise ValueError("iterations must be greater than zero.")
        if self.iteration is None:
            return False
        count = self.iteration.iteration_count
        return count > 0 and count % iterations == 0

    def _next_append_id(self, item: ContextItem) -> str:
        # Builds a deterministic id scoped to this run context and item kind.
        counters = self.metadata.setdefault("_append_counters", {})
        kind = str(getattr(item, "kind", "context"))
        next_value = int(counters.get(kind, 0)) + 1
        counters[kind] = next_value
        return f"{kind}:{next_value}"

    @staticmethod
    def _with_primitive_id(item: ContextItem, primitive_id: str) -> ContextItem:
        # Returns a copy of a dataclass primitive with a primitive id attached.
        if not dataclasses.is_dataclass(item):
            raise ValueError("append() requires a dataclass context item when primitive_id is missing.")
        return dataclasses.replace(item, primitive_id=primitive_id)


__all__ = [
    "ContextWindowLifecycleEvent",
    "ContextWindowPlacement",
    "ContextWindowRunContext",
    "InnerContextWindowAlgorithm",
]
