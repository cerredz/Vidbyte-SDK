"""Context Protocol Header

Description:
    Tests that the two return-level review adapters refuse allow-listed tools
    that would carry the producer's live authority into the reviewer.
Purpose:
    The independent critic and the prosecutor/defender/judge stages run in a
    fresh runtime with context_manager=None, but a context-window tool, a
    reasoning-trace tool, or any tool keeping the producer's ContextManager in
    _manager still writes to and reads that live manager. A customize() view
    over a delegation tool hid it from the critic's owner guard. Both cases
    must be refused before any review call, and the producer's registry must
    stay exactly as it was; ordinary tools must still reach the reviewer.
Architecture:
    - IndependentCriticToolGuardTests: context, trace, and wrapped tools are refused; ordinary tools are reviewed.
    - ProsecutorDefenderJudgeToolGuardTests: context and wrapped context tools fail preflight; ordinary tools are debated.
Relations:
    Regression tests for the @intent review-refuses-live-context-tools sites in
    vidbyte/agents/algorithms/independent_critic.py and
    vidbyte/agents/algorithms/prosecutor_defender_judge.py, which follow the
    _manager convention of BaseTool.rebind_context_manager in vidbyte/tools/base.py.
Similar Files:
    - tests/test_algorithms_honor_middleware_abort.py: the scripted runtime harness used here.
    - tests/test_reflexion_algorithm.py: the fake runner and response shapes reused here.
"""

from __future__ import annotations

import json
import unittest

from vidbyte import ContextManager, ContextWindowAlgorithm, IndependentCriticAlgorithm, ProsecutorDefenderJudgeAlgorithm
from vidbyte.agents import AgentRuntime
from vidbyte.context.algorithms.independent_critic import CriticFailurePolicy
from vidbyte.context.algorithms.prosecutor_defender_judge import DebateStageSettings, ProsecutorDefenderJudgeFailurePolicy
from vidbyte.context.primitives.documents import TextContextItem
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.tools import Tools, tool
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.context_primitives import context_window_tools
from vidbyte.tools.builtins.reasoning import FermiEstimationTraceTool
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec
from tests.agent_test_support import build_test_agent
from tests.test_reflexion_algorithm import FakeResponse, FakeRunner, invoke_runner, runner_output_metadata, runner_output_text

_REVIEW_PASS = json.dumps({"verdict": "pass", "summary": "The answer is supported.", "findings": []})
_NO_ALLEGATIONS = (json.dumps({"summary": "Nothing to allege.", "allegations": []}), json.dumps({"responses": []}), json.dumps({"decisions": []}))
_NOTE = {"primitive_id": "reviewer:note", "content": "REVIEWER-NOTE: written from inside the review."}


@tool
def lookup() -> str:
    """Look up information."""
    return "Paris is the capital of France."


class _PooledLookupTool(BaseTool):
    """A user tool that keeps a non-context resource in _manager and detaches through clone_for_fork."""

    def __init__(self, pool: object) -> None:
        self._manager = pool
        self.clones: list[_PooledLookupTool] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(name="pooled_lookup", description="Look up a value through a connection pool.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(call.tool_name, "pooled value")

    def clone_for_fork(self) -> _PooledLookupTool:
        clone = _PooledLookupTool(self._manager)
        self.clones.append(clone)
        return clone


def _call(name: str, arguments: dict[str, object]) -> FakeResponse:
    # An OpenAI-shaped model turn that calls one tool.
    return FakeResponse("", {"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments)}]})


def _producer_manager() -> ContextManager:
    # The producer's private context: one primitive the reviewer must never read or sit beside.
    manager = ContextManager()
    manager.upsert(TextContextItem(title="Pricing floor", content="INTERNAL-FLOOR: never quote below EUR 41.", primitive_id="floor"))
    return manager


def _context_tool(manager: ContextManager, name: str) -> BaseTool:
    return next(item for item in context_window_tools(manager) if item.name == name)


def _registry_ids(manager: ContextManager) -> list[str]:
    return [primitive_id for primitive_id, _ in manager.registry_items()]


def _desk_tool() -> BaseTool:
    # A subagent delegation tool; the critic refuses it because it carries another agent's live authority.
    desk = build_test_agent(name="desk", system_prompt="You are the pricing desk.", runner=FakeRunner([]), agent_metadata=AgentMetadata(name="desk", description="Pricing desk.", use_cases="Second opinions."))
    return desk.as_tool()  # type: ignore[return-value]


async def _run(runner: FakeRunner, algorithm: ContextWindowAlgorithm, tools: list[object], manager: ContextManager) -> AgentResult:
    # One producer run with the given tools bound to the producer's own context manager.
    runtime = AgentRuntime(agent_name="pricing", system_prompt="You quote prices.", tools=Tools(tools), permission_policy=PermissionPolicy(), algorithm=algorithm, context_manager=manager)
    context = runtime.build_context("Quote 10 seats.", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
    handle = RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata)
    return await runtime.arun("Quote 10 seats.", handle=handle, context=context)


def _critic(*tool_names: str) -> ContextWindowAlgorithm:
    # RETURN_CANDIDATE never raises on a review failure, so a raise proves the refusal is a configuration error.
    critic = IndependentCriticAlgorithm(allowed_tool_names=tool_names, failure_policy=CriticFailurePolicy.RETURN_CANDIDATE)
    return ContextWindowAlgorithm(name="independent_critic", independent_critic=critic)


def _debate(*tool_names: str) -> ContextWindowAlgorithm:
    pdj = ProsecutorDefenderJudgeAlgorithm(prosecutor=DebateStageSettings(tool_names=tool_names), failure_policy=ProsecutorDefenderJudgeFailurePolicy.RAISE)
    return ContextWindowAlgorithm(name="prosecutor_defender_judge", prosecutor_defender_judge=pdj)


class IndependentCriticToolGuardTests(unittest.IsolatedAsyncioTestCase):
    async def assert_refused_before_any_model_call(self, tool_under_test: BaseTool, manager: ContextManager, reviewer_turn: FakeResponse) -> None:
        # Without the guard the reviewer would get the tool, use it, and finish the review on these replies.
        runner = FakeRunner([FakeResponse("We can offer EUR 45 per seat."), reviewer_turn, FakeResponse(_REVIEW_PASS)])
        with self.assertRaises(ConfigurationError) as ctx:
            await _run(runner, _critic(tool_under_test.name), [tool_under_test], manager)
        self.assertIn("context-bound", str(ctx.exception))
        self.assertEqual(runner.calls, [])
        self.assertEqual(_registry_ids(manager), ["floor"])

    async def test_context_window_tools_bound_to_the_producer_manager_are_refused(self) -> None:
        # [Security] context_create_text wrote into the producer's next prompt, context_list listed its private ids, and context_recite added recite:floor.
        cases = {"context_create_text": _call("context_create_text", _NOTE), "context_list": _call("context_list", {}), "context_recite": _call("context_recite", {"primitive_id": "floor"})}
        for name, reviewer_turn in cases.items():
            with self.subTest(tool=name):
                manager = _producer_manager()
                await self.assert_refused_before_any_model_call(_context_tool(manager, name), manager, reviewer_turn)

    async def test_reasoning_trace_tool_bound_to_the_producer_manager_is_refused(self) -> None:
        # [Security] A reasoning trace upserts its record into the manager it holds, which here is the producer's.
        manager = _producer_manager()
        await self.assert_refused_before_any_model_call(FermiEstimationTraceTool(manager), manager, FakeResponse(_REVIEW_PASS))

    async def test_customized_context_tool_is_refused_like_the_plain_tool(self) -> None:
        # [Edge Case] A description-only view executes the same manager-bound tool, so the guard must look through it.
        manager = _producer_manager()
        view = _context_tool(manager, "context_list").customize(description="List the notes you have.")
        await self.assert_refused_before_any_model_call(view, manager, _call("context_list", {}))

    async def test_customized_subagent_tool_is_refused_like_the_plain_agent_tool(self) -> None:
        # [Security] The plain AgentTool was already refused; its customize() view passed because the guard read the view's module.
        for label, make_tool in (("plain", _desk_tool), ("customized", lambda: _desk_tool().customize(description="Ask the pricing desk for a second opinion."))):
            with self.subTest(tool=label):
                runner = FakeRunner([FakeResponse("We can offer EUR 45 per seat."), FakeResponse(_REVIEW_PASS)])
                desk = make_tool()
                with self.assertRaises(ConfigurationError):
                    await _run(runner, _critic(desk.name), [desk], _producer_manager())
                self.assertEqual(runner.calls, [])

    async def test_ordinary_tools_still_reach_the_reviewer(self) -> None:
        # [Control] A plain @tool function, and a user tool whose clone_for_fork detaches a non-context _manager, are reviewed as before.
        pooled = _PooledLookupTool(pool=object())
        runner = FakeRunner([FakeResponse("We can offer EUR 45 per seat."), _call("lookup", {}), FakeResponse(_REVIEW_PASS)])
        manager = _producer_manager()

        result = await _run(runner, _critic("lookup", "pooled_lookup"), [lookup, pooled], manager)

        self.assertEqual(result.metadata["independent_critic"]["status"], "reviewed")
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(len(pooled.clones), 1)
        self.assertEqual(_registry_ids(manager), ["floor"])


class ProsecutorDefenderJudgeToolGuardTests(unittest.IsolatedAsyncioTestCase):
    async def assert_refused_at_preflight(self, tool_under_test: BaseTool, manager: ContextManager) -> None:
        # Without the guard the prosecutor would call the tool, write into the producer's registry, and finish on these replies.
        runner = FakeRunner([FakeResponse("We can offer EUR 45 per seat."), _call("context_create_text", _NOTE), *(FakeResponse(reply) for reply in _NO_ALLEGATIONS)])
        with self.assertRaises(AgentExecutionError) as ctx:
            await _run(runner, _debate(tool_under_test.name), [tool_under_test], manager)
        self.assertIsInstance(ctx.exception.__cause__, ConfigurationError)
        self.assertIn("live context manager", str(ctx.exception.__cause__))
        self.assertEqual((ctx.exception.details["failed_stage"], ctx.exception.details["phase"]), ("prosecutor", "preflight"))
        # Only the producer ran; no debate stage was invoked.
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(_registry_ids(manager), ["floor"])

    async def test_context_create_tool_bound_to_the_producer_manager_is_refused(self) -> None:
        # [Security] context_create_* tools declare SAFE and no binds_to_primitive, so only the _manager check catches them.
        manager = _producer_manager()
        await self.assert_refused_at_preflight(_context_tool(manager, "context_create_text"), manager)

    async def test_customized_context_create_tool_is_refused_like_the_plain_tool(self) -> None:
        # [Edge Case] The view's spec, class, and attributes look harmless; the wrapped tool still holds the producer's manager.
        manager = _producer_manager()
        await self.assert_refused_at_preflight(_context_tool(manager, "context_create_text").customize(description="Write a note."), manager)

    async def test_ordinary_tools_are_still_debated(self) -> None:
        # [Control] A plain @tool function, and a user tool whose clone_for_fork detaches a non-context _manager, reach the prosecutor.
        pooled = _PooledLookupTool(pool=object())
        runner = FakeRunner([FakeResponse("We can offer EUR 45 per seat."), _call("lookup", {}), *(FakeResponse(reply) for reply in _NO_ALLEGATIONS)])
        manager = _producer_manager()

        result = await _run(runner, _debate("lookup", "pooled_lookup"), [lookup, pooled], manager)

        self.assertEqual(result.metadata["prosecutor_defender_judge"]["verdict"], "pass")
        self.assertEqual(len(runner.calls), 5)
        self.assertEqual(len(pooled.clones), 1)
        self.assertEqual(_registry_ids(manager), ["floor"])


if __name__ == "__main__":
    unittest.main()
