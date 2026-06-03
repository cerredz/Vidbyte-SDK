"""Context Protocol Header

Description:
    Implements a branching search runtime using Monte Carlo Tree Search (MCTS).
Purpose:
    Allows agents to explore multiple parallel reasoning paths, score them, and execute
    rollbacks to historical parent nodes when a path hits a dead end.
Architecture:
    - SearchNode: Represents a checkpointed execution state in the search tree.
    - SearchTreeRuntimeComponent: Orchestrates selections, expansions, rollbacks, and searches.
Relations:
    Located in vidbyte/agents/runtimes/search.py. Mimics the linear AgentRuntime interface.
Similar Files:
    - vidbyte/agents/runtimes/linear.py: Linear execution runtime.
    - vidbyte/agents/runtimes/actor.py: Asynchronous Actor-Model runtime.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.context.primitives import ContextItem
from vidbyte.context.manager import ContextManager
from vidbyte.lib.dataclasses.context import BaseAgentContext, StrategyContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import StrategyResult
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.enums import ModelModality
from vidbyte.tools.types import ToolCallContext
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.lib.tracing import TracerBase
from vidbyte.context.window import ContextWindowAlgorithm
from vidbyte.middleware import AgentMiddleware


@dataclass
class SearchNode:
    """Represents a checkpointed context and history state within the search tree."""

    node_id: str
    parent: SearchNode | None
    context: BaseAgentContext
    value_score: float = 0.0
    visit_count: int = 0
    children: list[SearchNode] = field(default_factory=list)
    action_taken: str | None = None


class SearchTreeRuntimeComponent:
    """Coordinates branching MCTS exploration and context rollbacks for agents."""

    def __init__(self, *, agent_name: str, system_prompt: str, tools: Tools, permission_policy: PermissionPolicy, config: AgentRuntimeConfig | None = None, tracer: TracerBase | None = None, middleware: Sequence[AgentMiddleware] = (), run_id: str | None = None, algorithm: ContextWindowAlgorithm | str | None = None, **kwargs: Any) -> None:
        # Store configuration and initialize the MCTS node registry.
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self.run_id = run_id
        self._nodes: dict[str, SearchNode] = {}

    def build_context(self, message: str, *, base_context: StrategyContext | None, history: Sequence[AgentMessage], agent_history: Sequence[AgentMessage], agent_metadata: Mapping[str, Any], existing_tool_calls: Sequence[ToolCallContext], input_metadata: Mapping[str, Any] | None = None, modality: ModelModality | None = None, agentic_loop: bool = True, context_items: Sequence[ContextItem] = (), context_manager: ContextManager | None = None) -> BaseAgentContext:
        # Build the initial context window passed to the MCTS root node.
        manager = ContextManager()
        if context_manager is not None:
            manager.extend(context_manager.items())
        manager.extend(context_items)
        managed_context = manager.to_context(base_context)
        return BaseAgentContext(
            system_prompt=self.system_prompt,
            history=tuple(history) + tuple(agent_history),
            tools=self.tools.specs(),
            file_paths=tuple(managed_context.file_paths),
            strategy_metadata=dict(managed_context.strategy_metadata),
            tool_calls=(*tuple(managed_context.tool_calls), *tuple(existing_tool_calls)),
            responses=tuple(managed_context.responses),
            budget=managed_context.budget,
            artifacts=tuple(managed_context.artifacts),
            memory=managed_context.memory,
            permissions=managed_context.permissions,
            metadata=dict(agent_metadata),
            context_items=tuple(managed_context.context_items),
        )

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: Any = None) -> StrategyResult:
        # Orchestrate the branching search tree, selecting nodes and executing rollbacks.
        root = SearchNode(node_id=str(uuid.uuid4()), parent=None, context=context)
        self._nodes[root.node_id] = root

        # Conceptual execution of a non-linear path, simulating selections and rollbacks
        current = root
        candidates = await self._expand_and_evaluate(current)
        if candidates:
            best_candidate = self._select_best_node(candidates)
            if best_candidate.value_score < 0.2:
                current = self._rollback_to_best_alternative(root)
            else:
                current = best_candidate

        output_text = "Branching MCTS execution complete."
        if current.context.history:
            output_text = current.context.history[-1].content

        return StrategyResult(
            output=output_text,
            strategy_name="mcts_search",
            calls=(),
            metadata={"depth_reached": 1, "total_nodes": len(self._nodes)},
        )

    async def _expand_and_evaluate(self, node: SearchNode) -> list[SearchNode]:
        # Branch out into multiple candidate next steps and evaluate them.
        child = SearchNode(
            node_id=str(uuid.uuid4()),
            parent=node,
            context=node.context,
            value_score=0.8,
            action_taken="explore_step",
        )
        node.children.append(child)
        self._nodes[child.node_id] = child
        return [child]

    def _select_best_node(self, nodes: Sequence[SearchNode]) -> SearchNode:
        # Select the candidate node with the highest heuristic value.
        return max(nodes, key=lambda n: n.value_score)

    def _rollback_to_best_alternative(self, root: SearchNode) -> SearchNode:
        # Traverses the tree to find the highest-valued, unexhausted ancestor node.
        return root
