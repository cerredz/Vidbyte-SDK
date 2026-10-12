"""FILE: tests/test_workflow_agent_forks.py

PURPOSE: Proves workflow agent adapters close the MCP servers of the forks they create.
ROLE IN CODEBASE: Regression coverage for AgentStage and AgentValidator fork cleanup.
ARCHITECTURE NOTE: Runs each adapter in a one-stage compiled StateGraph with an offline BaseAgent whose fork returns a spy child; no subprocesses start.
COMMON MODIFICATION PATTERNS: Add a case when another workflow adapter starts forking agents.
KNOWN EDGE CASES: With fresh_fork=False the adapter runs the caller's own agent, which it must not close.
RELATED DOCS: vidbyte/workflows/README.md
TESTS: python -m pytest tests/test_workflow_agent_forks.py
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from tests.agent_test_support import bind_test_runner
from vidbyte.agents import AgentForkSettings, AgentInput, BaseAgent
from vidbyte.workflows.contracts import MachineStatus, StageResult, ValidationResult
from vidbyte.workflows.errors import StageExecutionError
from vidbyte.workflows.graph import StateGraph
from vidbyte.workflows.stages import AgentStage, CallableStage
from vidbyte.workflows.validation import AgentValidator


class Verdict(BaseModel):
    """Minimal structured verdict for the verifier tests."""

    ok: bool


class ForkSpyAgent(BaseAgent):
    """Offline agent whose forks are spy children that record runs and MCP closes."""

    def __init__(self, *, behavior: str = "reply") -> None:
        # Builds an offline agent; behavior is "reply", "fail", or "hang" for every run.
        super().__init__(name="spy", system_prompt="Test.", provider="openai", model_name="gpt-4.1-mini")
        bind_test_runner(self, object())
        self.mode = behavior
        self.children: list[ForkSpyAgent] = []
        self.closed = 0
        self.closed_after_run = False
        self.ran = False

    def fork(self, settings: AgentForkSettings | None = None) -> ForkSpyAgent:
        # Hands out a fresh spy child so the test can see which object was closed.
        child = ForkSpyAgent(behavior=self.mode)
        self.children.append(child)
        return child

    async def arun(self, message: str | AgentInput, **options: Any) -> Any:
        # Replies with a structured verdict, raises, or hangs depending on the configured behavior.
        self.ran = True
        if self.mode == "fail":
            raise RuntimeError("agent run failed")
        if self.mode == "hang":
            await asyncio.sleep(60)
        return SimpleNamespace(content="done", metadata={"structured": {"ok": True}})

    async def close_mcp_servers(self) -> None:
        # Records the close and whether the run had already happened.
        self.closed += 1
        self.closed_after_run = self.ran


def keep_state(context: Any) -> StageResult[str]:
    # Proposes the unchanged state so only the validator under test decides anything.
    return StageResult(context.state)


async def run_one_stage(stage: Any, validators: tuple[Any, ...] = ()) -> Any:
    # Runs a single stage, plus any validators, to a terminal through the real state machine.
    graph: StateGraph[str] = StateGraph(str, name="fork_cleanup")
    graph.add_stage("work", stage, validators=validators)
    graph.add_terminal("done")
    graph.add_terminal("rejected", status=MachineStatus.FAILED)
    graph.set_entry("work")
    graph.add_transition("work", "done")
    graph.add_transition("work", "rejected", on="agent_validator_error")
    return await graph.compile().arun("s")


def validator(agent: ForkSpyAgent, **options: Any) -> AgentValidator[str, Verdict]:
    # Builds a verifier that passes whenever the structured verdict parses.
    return AgentValidator(agent, lambda ctx: "check", Verdict, lambda verdict, ctx: ValidationResult.passed(), **options)


class WorkflowAgentForkTests(unittest.IsolatedAsyncioTestCase):
    """Workflow adapters close only the forks they create, after the fork's run."""

    async def test_agent_stage_closes_its_fork_after_the_run(self) -> None:
        # @intent internal-forks-close-their-mcp-servers
        parent = ForkSpyAgent()
        stage: AgentStage[str] = AgentStage(parent, lambda ctx: "go", lambda reply, ctx: StageResult(ctx.state))
        await run_one_stage(stage)
        self.assertEqual(len(parent.children), 1)
        self.assertEqual(parent.children[0].closed, 1)
        self.assertTrue(parent.children[0].closed_after_run)
        self.assertEqual(parent.closed, 0)

    async def test_agent_stage_closes_its_fork_when_the_run_raises(self) -> None:
        parent = ForkSpyAgent(behavior="fail")
        stage: AgentStage[str] = AgentStage(parent, lambda ctx: "go", lambda reply, ctx: StageResult(ctx.state))
        with self.assertRaises(StageExecutionError):
            await run_one_stage(stage)
        self.assertEqual(parent.children[0].closed, 1)

    async def test_agent_stage_without_fresh_fork_leaves_caller_agent_open(self) -> None:
        agent = ForkSpyAgent()
        stage: AgentStage[str] = AgentStage(agent, lambda ctx: "go", lambda reply, ctx: StageResult(ctx.state), fresh_fork=False)
        await run_one_stage(stage)
        self.assertTrue(agent.ran)
        self.assertEqual(agent.closed, 0)
        self.assertEqual(agent.children, [])

    async def test_agent_validator_closes_its_fork_after_the_run(self) -> None:
        # @intent internal-forks-close-their-mcp-servers
        parent = ForkSpyAgent()
        result = await run_one_stage(CallableStage(keep_state), (validator(parent),))
        self.assertIs(result.status, MachineStatus.SUCCEEDED)
        self.assertEqual(parent.children[0].closed, 1)
        self.assertTrue(parent.children[0].closed_after_run)
        self.assertEqual(parent.closed, 0)

    async def test_agent_validator_closes_its_fork_when_the_run_raises_or_times_out(self) -> None:
        for behavior, options in (("fail", {}), ("hang", {"timeout_seconds": 0.01})):
            parent = ForkSpyAgent(behavior=behavior)
            result = await run_one_stage(CallableStage(keep_state), (validator(parent, **options),))
            self.assertIs(result.status, MachineStatus.FAILED, behavior)
            self.assertEqual(parent.children[0].closed, 1, behavior)

    async def test_agent_validator_without_fresh_fork_leaves_caller_agent_open(self) -> None:
        agent = ForkSpyAgent()
        await run_one_stage(CallableStage(keep_state), (validator(agent, fresh_fork=False),))
        self.assertTrue(agent.ran)
        self.assertEqual(agent.closed, 0)


if __name__ == "__main__":
    unittest.main()
