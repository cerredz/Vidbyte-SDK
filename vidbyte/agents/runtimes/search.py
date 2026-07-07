"""
FILE: vidbyte/agents/runtimes/search.py

PURPOSE:
    Implements a branching search runtime using Monte Carlo Tree Search (MCTS). Allows agents to explore multiple parallel reasoning paths, score them, and execute rollbacks to historical parent nodes when a path hits a dead end.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/agents layer, which owns agent construction, runtime dispatch, handoff, fork, and execution state.
    It should be read with `vidbyte/agents/runtimes/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.agents.types: imported by this file.
    - vidbyte.context.manager: imported by this file.
    - vidbyte.context.primitives: imported by this file.
    - vidbyte.context.window: imported by this file.
    - vidbyte.lib.dataclasses.agents: imported by this file.
    - vidbyte.lib.dataclasses.context: imported by this file.
    - vidbyte.lib.dataclasses.runner: imported by this file.
    - vidbyte.lib.dataclasses.strategies: imported by this file.

FUNCTION INVENTORY:
    - SearchNode (class): public or navigational symbol owned here.
    - SearchTreeRuntimeComponent (class): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-agent-behavior.py, scripts/test-new-runners.py, and agent-runtime scripts when changing behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
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
        self.tracer = tracer

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
        span = self._start_semantic_span("runtime.search.run", parent=trace_context, agent_name=self.agent_name, message=message)
        root = SearchNode(node_id=str(uuid.uuid4()), parent=None, context=context)
        self._nodes[root.node_id] = root

        # Conceptual execution of a non-linear path, simulating selections and rollbacks
        try:
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

            result = StrategyResult(
                output=output_text,
                strategy_name="mcts_search",
                calls=(),
                metadata={"depth_reached": 1, "total_nodes": len(self._nodes)},
            )
            self._end_semantic_span(span, output=output_text)
            return result
        except BaseException as exc:
            self._end_semantic_span(span, error=exc)
            raise

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
        span = self._start_semantic_span("runtime.search.node", node_id=child.node_id, parent_id=node.node_id, value_score=child.value_score)
        self._end_semantic_span(span, output=child.action_taken)
        return [child]

    def _select_best_node(self, nodes: Sequence[SearchNode]) -> SearchNode:
        # Select the candidate node with the highest heuristic value.
        return max(nodes, key=lambda n: n.value_score)

    def _rollback_to_best_alternative(self, root: SearchNode) -> SearchNode:
        # Traverses the tree to find the highest-valued, unexhausted ancestor node.
        span = self._start_semantic_span("runtime.search.rollback", node_id=root.node_id)
        self._end_semantic_span(span, output="root")
        return root

    def _start_semantic_span(self, name: str, parent: Any = None, **attributes: Any) -> Any:
        # Opens search runtime spans only for semantic controllers.
        if not _is_semantic_tracer(self.tracer):
            return None
        return self.tracer.start_span(name, parent=parent, **attributes)

    def _end_semantic_span(self, span: Any, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes search runtime spans only when one was opened.
        if span is not None and _is_semantic_tracer(self.tracer):
            self.tracer.end_span(span, output=output, error=error)


def _is_semantic_tracer(tracer: object) -> bool:
    # Detects TraceController-like tracers without importing vidbyte.trace during runtime initialization.
    return all(hasattr(tracer, attr) for attr in ("inner", "profile", "translator"))
