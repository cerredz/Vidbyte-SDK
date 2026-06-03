"""Context Protocol Header

Description:
    Defines BaseNonLinearRuntime, the shared base class for all non-linear agent runtimes.
Purpose:
    Eliminates copy-paste duplication of build_context across Beam Search, DAG Dataflow,
    Market Auction, and Gossip runtimes and fixes the three correctness bugs that appeared
    in each duplicate: wrong field name (strategy_metadata vs run_metadata), missing
    base_context.metadata and input_metadata in the merge, and ignored base_context.system_prompt.
Architecture:
    - BaseNonLinearRuntime: Shared build_context implementation for all non-linear runtimes.
Relations:
    Located in vidbyte/agents/runtimes/base_nonlinear.py. Inherited by BeamSearchAgentRuntime,
    DAGDataflowAgentRuntime, MarketAuctionAgentRuntime, and GossipAgentRuntime.
Similar Files:
    - vidbyte/agents/runtime.py: Linear AgentRuntime (does not share this base).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.enums import ModelModality
from vidbyte.tools.types import ToolCallContext


class BaseNonLinearRuntime:
    """Shared build_context for non-linear runtimes; the linear AgentRuntime does not inherit this."""

    system_prompt: str

    def build_context(
        self,
        message: str,
        *,
        base_context: BaseContext | None,
        history: Sequence[AgentMessage],
        agent_history: Sequence[AgentMessage],
        agent_metadata: Mapping[str, Any],
        existing_tool_calls: Sequence[ToolCallContext],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
        agentic_loop: bool = True,
        context_items: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
        **_: Any,
    ) -> BaseAgentContext:
        # Canonical non-linear build_context: respects base_context overrides and merges all metadata.
        manager = ContextManager()
        if context_manager is not None:
            manager.extend(context_manager.items())
        manager.extend(context_items)
        system_prompt = (
            base_context.system_prompt if base_context and base_context.system_prompt else self.system_prompt
        )
        metadata = {
            **(dict(base_context.metadata) if base_context else {}),
            **dict(agent_metadata),
            **dict(input_metadata or {}),
        }
        return BaseAgentContext.from_manager(
            manager,
            base_context,
            system_prompt=system_prompt,
            history=tuple(history) + tuple(agent_history),
            tools=self.tools.specs(),
            existing_tool_calls=existing_tool_calls,
            metadata=metadata,
        )


__all__ = ["BaseNonLinearRuntime"]
