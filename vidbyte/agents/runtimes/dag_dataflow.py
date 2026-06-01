"""Context Protocol Header

Description:
    Implements the DAG Dataflow non-linear agent execution runtime.
Purpose:
    The agent generates a dependency graph from the task, then the runtime executes
    nodes in topological order using asyncio.gather with bounded parallelism —
    multiple independent branches run concurrently.
Architecture:
    - DAGDataflowAgentRuntime: Plans a DAG, executes nodes level-by-level, synthesizes output.
Relations:
    Located in vidbyte/agents/runtimes/dag_dataflow.py. Registered in RuntimeRegistry.
    Instantiated by BaseAgent._runtime() when runtime_type is DAG_DATAFLOW.
Similar Files:
    - vidbyte/agents/runtimes/beam_search.py: Beam Search non-linear runtime.
    - vidbyte/agents/runtimes/search.py: MCTS non-linear runtime.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, StrategyContext
from vidbyte.lib.dataclasses.strategies import StrategyResult
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.enums import ModelModality
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCallContext
from vidbyte.lib.tracing import NullTracer, TracerBase
from vidbyte.context.window import ContextWindowAlgorithm
from vidbyte.middleware import AgentMiddleware


class DAGDataflowAgentRuntime:
    """Plans a dependency DAG, executes nodes in topological order, and synthesizes a final answer."""

    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        tools: Tools,
        permission_policy: PermissionPolicy,
        config: AgentRuntimeConfig | None = None,
        tracer: TracerBase | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        run_id: str | None = None,
        algorithm: ContextWindowAlgorithm | str | None = None,
        max_parallel: int = 4,
        max_node_output_chars: int = 12000,
        planner_system_prompt: str = "",
        node_system_prompt: str = "",
        synthesizer_system_prompt: str = "",
        **kwargs: Any,
    ) -> None:
        # Store agent config and DAG dataflow parameters; middleware is intentionally ignored.
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self._tracer: TracerBase = tracer or NullTracer()
        self.run_id = run_id
        self.max_parallel = max_parallel
        self.max_node_output_chars = max_node_output_chars
        self.planner_system_prompt = planner_system_prompt
        self.node_system_prompt = node_system_prompt
        self.synthesizer_system_prompt = synthesizer_system_prompt

    def build_context(
        self,
        message: str,
        *,
        base_context: StrategyContext | None,
        history: Sequence[AgentMessage],
        agent_history: Sequence[AgentMessage],
        agent_metadata: Mapping[str, Any],
        existing_tool_calls: Sequence[ToolCallContext],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
        agentic_loop: bool = True,
        context_items: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
    ) -> BaseAgentContext:
        # Build the initial context window for the DAG planner and node executions.
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

    async def arun(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: Any = None,
    ) -> StrategyResult:
        # Plan a DAG, execute nodes in topological order, and synthesize the final result.
        started_at = time.monotonic()
        nodes = await self._plan_dag(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
        )
        node_outputs = await self._execute_dag(
            message,
            nodes,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
        )
        final_output = await self._synthesize(
            message,
            nodes,
            node_outputs,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
        )
        return self._with_metadata(final_output, nodes=nodes, node_outputs=node_outputs, started_at=started_at)

    async def _plan_dag(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> list[dict[str, Any]]:
        # Call the planner to generate a JSON DAG from the task description.
        try:
            raw = await invoke_runner(runner, message, system=self.planner_system_prompt)
            plan_text = runner_output_text(raw)
        except Exception as exc:
            raise AgentExecutionError("DAG planner call failed.", details={"cause": str(exc)}) from exc
        nodes = self._parse_dag(plan_text)
        self._validate_no_cycles(nodes)
        return nodes

    async def _execute_dag(
        self,
        message: str,
        nodes: list[dict[str, Any]],
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        trace_context: Any,
    ) -> dict[str, str]:
        # Execute DAG nodes level-by-level with bounded parallelism per level.
        levels = self._topological_levels(nodes)
        node_outputs: dict[str, str] = {}
        semaphore = asyncio.Semaphore(self.max_parallel)
        for level_nodes in levels:
            await self._execute_level(
                level_nodes,
                node_outputs,
                message,
                semaphore=semaphore,
                runner=runner,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                runner_output_metadata=runner_output_metadata,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )
        return node_outputs

    async def _execute_level(
        self,
        level_nodes: list[dict[str, Any]],
        node_outputs: dict[str, str],
        message: str,
        *,
        semaphore: asyncio.Semaphore,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        trace_context: Any,
    ) -> None:
        # Execute all nodes in one topology level concurrently, bounded by the semaphore.
        async def run_one(node: dict[str, Any]) -> None:
            async with semaphore:
                output = await self._execute_node(
                    node,
                    node_outputs,
                    message,
                    runner=runner,
                    context=context,
                    provider=provider,
                    invoke_runner=invoke_runner,
                    runner_output_text=runner_output_text,
                    runner_output_metadata=runner_output_metadata,
                    metadata=metadata,
                    options=options,
                    trace_context=trace_context,
                )
                node_outputs[node["id"]] = output

        await asyncio.gather(*[run_one(node) for node in level_nodes])

    async def _execute_node(
        self,
        node: dict[str, Any],
        node_outputs: dict[str, str],
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        trace_context: Any,
    ) -> str:
        # Run one DAG node as a full agent trial with dependency inputs injected.
        from vidbyte.agents.runtime import AgentRuntime
        node_task = self._build_node_task(node, node_outputs, message)
        node_context = replace(
            context,
            system_prompt=self.node_system_prompt,
            metadata={**dict(context.metadata), "dag_node_id": node.get("id", "?")},
        )
        inner = AgentRuntime(
            agent_name=self.agent_name,
            system_prompt=self.node_system_prompt,
            tools=self.tools,
            permission_policy=self.permission_policy,
            config=self.config,
            tracer=self._tracer,
            run_id=self.run_id,
        )
        result = await inner._arun_once(
            node_task,
            runner=runner,
            context=node_context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata={**(metadata or {}), "dag_node_id": node.get("id", "?")},
            options=dict(options or {}),
            trace_context=trace_context,
        )
        output = result.output or ""
        return output[:self.max_node_output_chars]

    async def _synthesize(
        self,
        message: str,
        nodes: list[dict[str, Any]],
        node_outputs: dict[str, str],
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> str:
        # Merge all node outputs into a final answer via a lightweight synthesizer call.
        outputs_text = "\n\n".join(
            f"[{node['id']}] {node.get('description', '')}\n{node_outputs.get(node['id'], '(no output)')}"
            for node in nodes
        )
        synthesis_prompt = f"Original task:\n{message}\n\nSubtask outputs:\n{outputs_text}\n\nFinal synthesis:"
        try:
            raw = await invoke_runner(runner, synthesis_prompt, system=self.synthesizer_system_prompt)
            return runner_output_text(raw)
        except Exception:
            return "\n".join(node_outputs.get(node["id"], "") for node in nodes[-1:])

    def _build_node_task(self, node: dict[str, Any], node_outputs: dict[str, str], original_task: str) -> str:
        # Assemble the node's task prompt with parent outputs injected as context.
        deps = node.get("dependencies", [])
        parts = [f"Original task context:\n{original_task}", f"\nYour subtask:\n{node.get('description', '')}"]
        inputs = {dep: node_outputs.get(dep, "(not available)") for dep in deps if dep in node_outputs}
        if inputs:
            parts.append("\nInputs from completed subtasks:\n" + "\n".join(f"[{k}]: {v}" for k, v in inputs.items()))
        return "\n".join(parts)

    def _parse_dag(self, text: str) -> list[dict[str, Any]]:
        # Extract a JSON DAG array from the planner output; fall back to a single-node plan.
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                nodes = json.loads(text[start:end])
                if isinstance(nodes, list) and all(isinstance(n, dict) and "id" in n for n in nodes):
                    return nodes
            except (json.JSONDecodeError, ValueError):
                pass
        return [{"id": "main", "description": text[:200] or "Complete the task.", "dependencies": []}]

    def _topological_levels(self, nodes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        # Group nodes into levels via Kahn's algorithm for topological sort.
        node_map = {n["id"]: n for n in nodes}
        in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
        for node in nodes:
            for dep in node.get("dependencies", []):
                if dep in in_degree:
                    in_degree[node["id"]] += 1
        levels: list[list[dict[str, Any]]] = []
        remaining = set(in_degree)
        while remaining:
            level = [node_map[nid] for nid in remaining if in_degree[nid] == 0]
            if not level:
                break
            levels.append(level)
            for node in level:
                remaining.discard(node["id"])
                for other in nodes:
                    if node["id"] in other.get("dependencies", []) and other["id"] in remaining:
                        in_degree[other["id"]] -= 1
        return levels

    def _validate_no_cycles(self, nodes: list[dict[str, Any]]) -> None:
        # Raise AgentExecutionError if the dependency graph contains a cycle.
        levels = self._topological_levels(nodes)
        executed = {n["id"] for level in levels for n in level}
        cycle_nodes = {n["id"] for n in nodes} - executed
        if cycle_nodes:
            raise AgentExecutionError(
                f"DAG contains a cycle involving nodes: {sorted(cycle_nodes)}",
                details={"cycle_nodes": sorted(cycle_nodes)},
            )

    def _with_metadata(
        self,
        output: str,
        *,
        nodes: list[dict[str, Any]],
        node_outputs: dict[str, str],
        started_at: float,
    ) -> StrategyResult:
        # Build the final StrategyResult with DAG trace metadata.
        levels = self._topological_levels(nodes)
        return StrategyResult(
            output=output,
            strategy_name="direct_runner",
            metadata={
                "stop_reason": "is_done",
                "dag_dataflow": {
                    "node_count": len(nodes),
                    "level_count": len(levels),
                    "elapsed_seconds": max(0.0, time.monotonic() - started_at),
                    "nodes": tuple(
                        {
                            "id": n.get("id", "?"),
                            "description": n.get("description", ""),
                            "dependencies": n.get("dependencies", []),
                            "output_chars": len(node_outputs.get(n.get("id", ""), "")),
                        }
                        for n in nodes
                    ),
                },
            },
        )


__all__ = ["DAGDataflowAgentRuntime"]
