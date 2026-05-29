"""Context Protocol Header

Description:
    Executes the DAG Dataflow context-window algorithm for AgentRuntime.
Purpose:
    Keeps DAG planning, topological execution, node-level agentic trials, and
    synthesis orchestration out of the generic agent runtime loop.
Architecture:
    - DAGDataflowRuntimeAlgorithm: Plans a dependency graph, executes nodes in
      topological order using asyncio for parallelism, and synthesizes a final answer.
Relations:
    Used by AgentRuntimeContextAlgorithms. Consumes DAGDataflowAlgorithm config
    from vidbyte.context.algorithms.dag_dataflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.dag_dataflow import DAGDataflowAlgorithm
from vidbyte.lib.errors import AgentExecutionError  # noqa: F401 — used for DAG cycle/parse errors
from vidbyte.lib.tracing import SpanContext
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class DAGDataflowRuntimeAlgorithm:
    """Runtime adapter for the DAG Dataflow context-window algorithm."""

    name = "dag_dataflow"

    def __init__(self, runtime: AgentRuntime, algorithm: DAGDataflowAlgorithm) -> None:
        """Store the runtime reference and DAG dataflow configuration."""
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> StrategyResult:
        """Plan a DAG, execute nodes in topological order, and synthesize the result."""
        started_at = self.runtime.middleware.clock()
        nodes = await self._plan_dag(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
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
            metadata=metadata,
            trace_context=trace_context,
        )
        return self._with_dag_metadata(final_output, nodes=nodes, node_outputs=node_outputs, started_at=started_at)

    async def _plan_dag(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[dict[str, Any]]:
        """Call the planner stage to generate a JSON DAG from the task."""
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            message,
            {"system": self.algorithm.planner_system_prompt_text()},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=self._stage_metadata(metadata, stage="planner"),
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            raise AgentExecutionError("DAG planner was aborted by middleware before producing a plan.")
        plan_text = runner_output_text(raw_result)
        nodes = self.algorithm.parse_dag_plan(plan_text)
        self._validate_no_cycles(nodes)
        return nodes

    async def _execute_dag(self, message: str, nodes: list[dict[str, Any]], *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> dict[str, str]:
        """Execute nodes level-by-level with bounded parallelism per level."""
        levels = self._topological_levels(nodes)
        node_outputs: dict[str, str] = {}
        semaphore = asyncio.Semaphore(self.algorithm.max_parallel)
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

    async def _execute_level(self, level_nodes: list[dict[str, Any]], node_outputs: dict[str, str], message: str, *, semaphore: asyncio.Semaphore, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> None:
        """Execute all nodes in a topology level concurrently, bounded by semaphore."""
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

    async def _execute_node(self, node: dict[str, Any], node_outputs: dict[str, str], message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> str:
        """Run one DAG node as a full agent trial with inputs from parent nodes."""
        node_task = self._build_node_task(node, node_outputs, message)
        node_context = self._build_node_context(context, node)
        result = await self.runtime._arun_once(
            node_task,
            runner=runner,
            context=node_context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata=self._node_metadata(metadata, node_id=node.get("id", "?")),
            options=dict(options or {}),
            trace_context=trace_context,
        )
        return self.algorithm.truncate_node_output(result.output)

    async def _synthesize(self, message: str, nodes: list[dict[str, Any]], node_outputs: dict[str, str], *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> str:
        """Call the synthesizer to merge all node outputs into a final answer."""
        outputs_summary = "\n\n".join(
            f"[{node['id']}] {node.get('description', '')}\n{node_outputs.get(node['id'], '(no output)')}"
            for node in nodes
        )
        synthesis_prompt = f"Original task:\n{message}\n\nSubtask outputs:\n{outputs_summary}\n\nFinal synthesis:"
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            synthesis_prompt,
            {"system": self.algorithm.synthesizer_system_prompt_text()},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=self._stage_metadata(metadata, stage="synthesizer"),
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            return raw_result.output
        return runner_output_text(raw_result)

    def _build_node_task(self, node: dict[str, Any], node_outputs: dict[str, str], original_task: str) -> str:
        """Assemble the node's task prompt including parent outputs as inputs."""
        deps = node.get("dependencies", [])
        available_inputs = {dep: node_outputs.get(dep, "(not available)") for dep in deps if dep in node_outputs}
        parts = [f"Original task context:\n{original_task}", f"\nYour subtask:\n{node.get('description', '')}"]
        if available_inputs:
            inputs_text = "\n".join(f"[{dep}]: {out}" for dep, out in available_inputs.items())
            parts.append(f"\nInputs from completed subtasks:\n{inputs_text}")
        return "\n".join(parts)

    def _build_node_context(self, context: BaseAgentContext, node: dict[str, Any]) -> BaseAgentContext:
        """Build a node-specific context with the node system prompt injected."""
        return replace(
            context,
            system_prompt=self.algorithm.node_system_prompt_text(),
            metadata={**dict(context.metadata), "dag_node_id": node.get("id", "?")},
        )

    def _topological_levels(self, nodes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group nodes into levels using Kahn's algorithm for topological sort."""
        node_map = {node["id"]: node for node in nodes}
        in_degree: dict[str, int] = {node["id"]: 0 for node in nodes}
        for node in nodes:
            for dep in node.get("dependencies", []):
                if dep in in_degree:
                    in_degree[node["id"]] += 1
        levels: list[list[dict[str, Any]]] = []
        remaining = set(in_degree.keys())
        while remaining:
            current_level = [node_map[nid] for nid in remaining if in_degree[nid] == 0]
            if not current_level:
                break
            levels.append(current_level)
            for node in current_level:
                remaining.discard(node["id"])
                for other in nodes:
                    if node["id"] in other.get("dependencies", []) and other["id"] in remaining:
                        in_degree[other["id"]] -= 1
        return levels

    def _validate_no_cycles(self, nodes: list[dict[str, Any]]) -> None:
        """Raise AgentExecutionError if the dependency graph contains a cycle."""
        levels = self._topological_levels(nodes)
        executed = {node["id"] for level in levels for node in level}
        all_ids = {node["id"] for node in nodes}
        cycle_nodes = all_ids - executed
        if cycle_nodes:
            raise AgentExecutionError(
                f"DAG contains a cycle involving nodes: {sorted(cycle_nodes)}",
                details={"cycle_nodes": sorted(cycle_nodes)},
            )

    def _with_dag_metadata(self, output: str, *, nodes: list[dict[str, Any]], node_outputs: dict[str, str], started_at: float) -> StrategyResult:
        """Build the final StrategyResult with DAG trace metadata."""
        levels = self._topological_levels(nodes)
        return StrategyResult(
            output=output,
            strategy_name="direct_runner",
            metadata={
                "stop_reason": "is_done",
                "dag_dataflow": {
                    "node_count": len(nodes),
                    "level_count": len(levels),
                    "elapsed_seconds": max(0.0, self.runtime.middleware.clock() - started_at),
                    "nodes": tuple(
                        {
                            "id": node.get("id", "?"),
                            "description": node.get("description", ""),
                            "dependencies": node.get("dependencies", []),
                            "output_chars": len(node_outputs.get(node.get("id", ""), "")),
                        }
                        for node in nodes
                    ),
                },
            },
        )

    @staticmethod
    def _stage_metadata(metadata: Mapping[str, Any] | None, *, stage: str) -> dict[str, Any]:
        """Build metadata for a DAG non-agentic stage call."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "dag_dataflow",
            "dag_stage": stage,
        }

    @staticmethod
    def _node_metadata(metadata: Mapping[str, Any] | None, *, node_id: str) -> dict[str, Any]:
        """Build metadata for a DAG node execution trial."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "dag_dataflow",
            "dag_node_id": node_id,
        }


__all__ = [
    "DAGDataflowRuntimeAlgorithm",
]
