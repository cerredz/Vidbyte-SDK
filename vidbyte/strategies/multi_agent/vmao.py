from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.multi_agent.base import BaseMultiAgentStrategy
from vidbyte.strategies.types import StrategyContext, StrategyResult


@dataclass(frozen=True, slots=True)
class DagNode:
    id: str
    question: str
    depends_on: tuple[str, ...] = ()
    preferred_capability: str | None = None


@dataclass(frozen=True, slots=True)
class Verification:
    approved: bool
    score: float
    gaps: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(slots=True)
class NodeState:
    node: DagNode
    output: str | None = None
    failed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class VerifiedMultiAgentOrchestrationStrategy(BaseMultiAgentStrategy):
    """Plan, execute, verify, and replan over a DAG of sub-questions."""

    name = "multi_agent.vmao"

    def __init__(
        self,
        *,
        planner: BaseAgent,
        workers: Sequence[BaseAgent],
        verifier: BaseAgent,
        synthesizer: BaseAgent | None = None,
        max_rounds: int = 3,
        completeness_threshold: float = 0.85,
        max_parallel_tasks: int = 4,
    ) -> None:
        super().__init__(max_calls=max_rounds * (len(workers) + 4))
        if not workers:
            raise ValueError("At least one worker is required.")
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least 1.")
        if completeness_threshold < 0 or completeness_threshold > 1:
            raise ValueError("completeness_threshold must be between 0 and 1.")
        if max_parallel_tasks < 1:
            raise ValueError("max_parallel_tasks must be at least 1.")
        self.planner = planner
        self.workers = tuple(workers)
        self.verifier = verifier
        self.synthesizer = synthesizer
        self.max_rounds = max_rounds
        self.completeness_threshold = completeness_threshold
        self.max_parallel_tasks = max_parallel_tasks

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult:
        self._reset_calls()
        all_states: list[NodeState] = []
        verifier_history: list[dict[str, Any]] = []
        current_prompt = prompt
        final_output = ""
        for round_index in range(1, self.max_rounds + 1):
            nodes = await self._plan(current_prompt, context=context)
            round_states = await self._execute_dag(nodes, context=context, options=options)
            all_states.extend(round_states)
            final_output = await self._synthesize(prompt, all_states, context=context)
            verification = await self._verify(prompt, final_output, context=context)
            verifier_history.append(
                {
                    "round": round_index,
                    "approved": verification.approved,
                    "score": verification.score,
                    "gaps": list(verification.gaps),
                    "rationale": verification.rationale,
                }
            )
            if verification.approved or verification.score >= self.completeness_threshold:
                break
            current_prompt = self._gap_prompt(prompt, final_output, verification)
        return StrategyResult(
            output=final_output,
            strategy_name=self.name,
            metadata={
                "rounds": len(verifier_history),
                "verification": verifier_history,
                "nodes": [
                    {
                        "id": state.node.id,
                        "question": state.node.question,
                        "depends_on": list(state.node.depends_on),
                        "preferred_capability": state.node.preferred_capability,
                        "output": state.output,
                        "failed": state.failed,
                    }
                    for state in all_states
                ],
            },
        )

    async def _plan(self, prompt: str, *, context: StrategyContext | None) -> tuple[DagNode, ...]:
        planner_prompt = (
            "Decompose the task into a JSON array of DAG nodes. "
            "Each node must include id, question, depends_on, and optional preferred_capability.\n\n"
            f"Task:\n{prompt}"
        )
        reply = await self._run_agent(self.planner, planner_prompt, context=context, recipient="vmao")
        try:
            return _parse_nodes(reply.content)
        except StrategyExecutionError:
            repair_prompt = (
                "Repair this planner output into valid JSON array DAG nodes with id, question, depends_on, "
                f"and optional preferred_capability:\n{reply.content}"
            )
            repair = await self._run_agent(self.planner, repair_prompt, context=context, recipient="vmao")
            return _parse_nodes(repair.content)

    async def _execute_dag(
        self,
        nodes: Sequence[DagNode],
        *,
        context: StrategyContext | None,
        options: dict[str, Any],
    ) -> list[NodeState]:
        _validate_acyclic(nodes)
        states = {node.id: NodeState(node=node) for node in nodes}
        completed: set[str] = set()
        running: set[str] = set()
        while len(completed) < len(nodes):
            ready = [
                state
                for state in states.values()
                if state.node.id not in completed
                and state.node.id not in running
                and all(dep in completed for dep in state.node.depends_on)
            ]
            if not ready:
                raise StrategyExecutionError("DAG execution stalled before all nodes completed.")
            batch = ready[: self.max_parallel_tasks]
            running.update(state.node.id for state in batch)
            results = await asyncio.gather(
                *(self._execute_node(state, states, context=context, options=options) for state in batch),
                return_exceptions=True,
            )
            for state, result in zip(batch, results):
                if isinstance(result, Exception):
                    state.failed = True
                    state.output = f"FAILED: {self._safe_error(result)}"
                else:
                    state.output = result
                completed.add(state.node.id)
                running.discard(state.node.id)
        return list(states.values())

    async def _execute_node(
        self,
        state: NodeState,
        states: dict[str, NodeState],
        *,
        context: StrategyContext | None,
        options: dict[str, Any],
    ) -> str:
        worker = self._select_worker(state.node)
        dependency_context = "\n".join(
            f"{dep}: {states[dep].output}" for dep in state.node.depends_on if states[dep].output is not None
        )
        node_prompt = f"Sub-question:\n{state.node.question}\n\nDependency results:\n{dependency_context}"
        reply = await self._run_agent(worker, node_prompt, context=context, recipient="vmao", **options)
        return reply.content

    async def _synthesize(
        self,
        original_prompt: str,
        states: Sequence[NodeState],
        *,
        context: StrategyContext | None,
    ) -> str:
        evidence = "\n\n".join(f"{state.node.id}: {state.output}" for state in states)
        if self.synthesizer is None:
            return f"Original task:\n{original_prompt}\n\nCollected results:\n{evidence}"
        prompt = f"Synthesize a final answer for the original task.\n\nTask:\n{original_prompt}\n\nEvidence:\n{evidence}"
        reply = await self._run_agent(self.synthesizer, prompt, context=context, recipient="vmao")
        return reply.content

    async def _verify(self, original_prompt: str, output: str, *, context: StrategyContext | None) -> Verification:
        prompt = (
            "Verify the answer against the task. Return JSON with approved, score, gaps, and rationale.\n\n"
            f"Task:\n{original_prompt}\n\nAnswer:\n{output}"
        )
        reply = await self._run_agent(self.verifier, prompt, context=context, recipient="vmao")
        try:
            parsed = json.loads(reply.content)
        except json.JSONDecodeError:
            return Verification(approved=False, score=0.0, gaps=("Verifier returned invalid JSON.",), rationale=reply.content)
        return Verification(
            approved=bool(parsed.get("approved", False)),
            score=float(parsed.get("score", 0.0)),
            gaps=tuple(str(gap) for gap in parsed.get("gaps", ())),
            rationale=str(parsed.get("rationale", "")),
        )

    def _select_worker(self, node: DagNode) -> BaseAgent:
        if node.preferred_capability:
            for worker in self.workers:
                if node.preferred_capability in worker.card().capabilities:
                    return worker
        return self.workers[0]

    def _gap_prompt(self, original_prompt: str, output: str, verification: Verification) -> str:
        gaps = "\n".join(f"- {gap}" for gap in verification.gaps)
        return (
            "Create follow-up DAG nodes only for these missing gaps.\n\n"
            f"Original task:\n{original_prompt}\n\nCurrent answer:\n{output}\n\nGaps:\n{gaps}"
        )


def _parse_nodes(raw: str) -> tuple[DagNode, ...]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StrategyExecutionError("Planner did not return valid JSON DAG nodes.") from exc
    if isinstance(parsed, dict) and "nodes" in parsed:
        parsed = parsed["nodes"]
    if not isinstance(parsed, list):
        raise StrategyExecutionError("Planner JSON must be a list of nodes or an object with a nodes list.")
    nodes: list[DagNode] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise StrategyExecutionError("Each planner node must be an object.")
        node_id = str(item.get("id", "")).strip()
        question = str(item.get("question", "")).strip()
        if not node_id or not question:
            raise StrategyExecutionError("Each planner node requires id and question.")
        depends_on = item.get("depends_on", ())
        if depends_on is None:
            depends_on = ()
        nodes.append(
            DagNode(
                id=node_id,
                question=question,
                depends_on=tuple(str(dep) for dep in depends_on),
                preferred_capability=(
                    str(item["preferred_capability"]) if item.get("preferred_capability") else None
                ),
            )
        )
    return tuple(nodes)


def _validate_acyclic(nodes: Sequence[DagNode]) -> None:
    by_id = {node.id: node for node in nodes}
    if len(by_id) != len(nodes):
        raise StrategyExecutionError("DAG node ids must be unique.")
    for node in nodes:
        missing = [dep for dep in node.depends_on if dep not in by_id]
        if missing:
            raise StrategyExecutionError(f"DAG node '{node.id}' depends on unknown node(s): {missing}.")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise StrategyExecutionError("Planner DAG contains a cycle.")
        visiting.add(node_id)
        for dep in by_id[node_id].depends_on:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node in nodes:
        visit(node.id)
