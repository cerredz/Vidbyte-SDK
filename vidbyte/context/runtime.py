"""Context Protocol Header

Description:
    Defines inner-loop context-window contracts for direct agent runtime runs.
Purpose:
    Gives context-window algorithms a single, standard way to update the active
    ContextManager after the tool calls of a completed direct-runtime iteration.
Architecture:
    - ContextWindowPlacement: Rendering placement for managed primitives.
    - InnerContextWindowAlgorithm: No-op base class with one lifecycle hook.
    - ContextWindowRunContext: Slim per-run view over the active ContextManager.
Relations:
    Used by AgentRuntime, ContextManager, and context-window algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.context.primitives import ContextItem
    from vidbyte.context.templates import RecorderBase
    from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot


class ContextWindowPlacement(str, Enum):
    """Placement targets for managed context-window primitives."""

    TOP_OF_CONTEXT = "top_of_context"
    END_OF_CONTEXT = "end_of_context"
    TOP_OF_CONVERSATION = "top_of_conversation"
    END_OF_CONVERSATION = "end_of_conversation"


class InnerContextWindowAlgorithm:
    """No-op base class for algorithms that update context during a direct run.

    Inner-loop algorithms expose a single hook. The runtime invokes it once at
    run start (with ``ctx.iteration is None``) so the algorithm can initialize,
    and again after the tool calls of each completed non-final iteration.
    """

    def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        # Runs after the tool calls of a completed non-final iteration finish.
        del ctx


@dataclass(slots=True)
class ContextWindowRunContext:
    """Slim write surface over the active ContextManager for inner-loop algorithms.

    It carries only the observable iteration snapshot (read), the active
    ContextManager (write surface, via its semantic placement methods), the
    recorder, and a per-run ``state`` dict for cadence tracking and published
    metadata. All primitive placement logic lives on ``ContextManager``.
    """

    context_manager: ContextManager
    recorder: RecorderBase
    state: dict[str, Any]
    iteration: AgentIterationSnapshot | None = None

    def place_after_system_prompt(self, item: ContextItem) -> str:
        # Places a primitive at the top of the context zone (just after the system prompt).
        return self.context_manager.place_after_system_prompt(item)

    def place_after_tools(self, item: ContextItem) -> str:
        # Places a primitive at the end of the context zone (after tool-bound primitives).
        return self.context_manager.place_after_tools(item)

    def remove(self, primitive_id: str) -> None:
        # Removes a managed primitive from the active context manager.
        self.context_manager.remove_by_id(primitive_id)

    def record(self, slot: str, **metadata: Any) -> None:
        # Records a context-window template slot through the active recorder.
        self.recorder.append(slot, **metadata)

    def set_metadata(self, key: str, value: Any) -> None:
        # Stores a final metadata value for the active context-window algorithm.
        self.state[key] = value


__all__ = [
    "ContextWindowPlacement",
    "ContextWindowRunContext",
    "InnerContextWindowAlgorithm",
]
