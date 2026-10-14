"""FILE: tests/test_refused_finish_adopts_catalog.py

PURPOSE:
    Proves a tool the agent adds to itself mid-run reaches the next model call even when the same turn's isDone
    is refused, by an output contract or by a review_finish that asks to continue.
ROLE IN CODEBASE:
    Regression test for @intent refused-finish-still-adopts-added-tools in AgentRuntime's linear loop, beside
    @intent a-tool-the-agent-adds-mid-run-reaches-the-next-iteration.
ARCHITECTURE NOTE:
    AddThenUseRunner is a scripted offline runner that records the tool names offered per request: turn 1 calls
    unlock_catalog (which calls agent.add_tool) optionally beside isDone, turn 2 calls the added tool, turn 3
    finishes. RefuseFirstFinish continues the run once from review_finish, then accepts.
COMMON MODIFICATION PATTERNS:
    Add another refusal shape as a new test that builds the agent with _agent and asserts with
    _assert_added_tool_offered_next.
KNOWN EDGE CASES:
    The plain tool turn (no isDone) is the control case and must keep offering the added tool on request 2.
RELATED DOCS:
    vidbyte/agents/README.md
TESTS:
    python -m pytest tests/test_refused_finish_adopts_catalog.py -q
"""

from __future__ import annotations

import unittest

from tests.agent_test_support import build_test_agent
from vidbyte import AgentMiddleware, BaseAgent, tool
from vidbyte.agents import AgentLoopSettings, MinToolCalls
from vidbyte.lib.dataclasses.agents import FinishReview


class AddThenUseRunner:
    """Runner that adds lookup_isbn in turn 1, calls it in turn 2, then finishes."""

    def __init__(self, *, finish_in_first_turn: bool) -> None:
        self.finish_in_first_turn = finish_in_first_turn
        self.offered: list[tuple[str, ...]] = []

    async def arun(self, prompt: str, **kwargs: object) -> object:
        self.offered.append(tuple(spec["function"]["name"] for spec in kwargs.get("tools") or ()))
        turn = len(self.offered)
        if turn == 1:
            calls = [("unlock_catalog", "{}")]
            if self.finish_in_first_turn:
                calls.append(("isDone", '{"final_answer": "done early"}'))
        elif turn == 2:
            calls = [("lookup_isbn", '{"title": "Dune"}')]
        else:
            calls = [("isDone", '{"final_answer": "ISBN 978-0 found."}')]
        items = [{"type": "function_call", "name": name, "arguments": arguments, "call_id": f"call_{turn}_{index}"} for index, (name, arguments) in enumerate(calls)]
        return type("_Resp", (), {"text": "", "raw": {"output": items}})()


class RefuseFirstFinish(AgentMiddleware):
    """Asks the model to continue on its first finish attempt, then accepts."""

    def __init__(self) -> None:
        self.refused = 0

    async def review_finish(self, context: object) -> FinishReview:
        if self.refused == 0:
            self.refused += 1
            return FinishReview.continue_with("Not verified yet: look the ISBN up first.")
        return FinishReview.accept()


class RefusedFinishAdoptsCatalogTests(unittest.IsolatedAsyncioTestCase):
    """A tool added in a turn whose isDone is refused must be offered on the very next request."""

    def _agent(self, runner: AddThenUseRunner, **options: object) -> BaseAgent:
        holder: dict[str, BaseAgent] = {}

        @tool
        def lookup_isbn(title: str) -> str:
            """Look up a book's ISBN by title."""
            return f"{title}: ISBN 978-0"

        @tool
        def unlock_catalog() -> str:
            """Unlock the catalog tools for this assistant."""
            holder["agent"].add_tool(lookup_isbn)
            return "catalog unlocked"

        holder["agent"] = build_test_agent(name="librarian", system_prompt="Help with books.", runner=runner, tools=[unlock_catalog], **options)
        return holder["agent"]

    async def _assert_added_tool_offered_next(self, runner: AddThenUseRunner, agent: BaseAgent) -> None:
        result = await agent.arun("What is the ISBN of Dune?")

        # The request after the add offers the new tool, and the model's call to it succeeds the first time.
        self.assertNotIn("lookup_isbn", runner.offered[0])
        self.assertIn("lookup_isbn", runner.offered[1])
        lookups = [context for context in result.metadata["tool_calls"] if context.tool_name == "lookup_isbn"]
        self.assertEqual([context.state.value for context in lookups], ["succeeded"])
        self.assertEqual(result.content, "ISBN 978-0 found.")

    async def test_contract_rejected_finish_still_offers_added_tool_next(self) -> None:
        # @intent refused-finish-still-adopts-added-tools
        runner = AddThenUseRunner(finish_in_first_turn=True)
        settings = AgentLoopSettings(max_iterations=6, output_contracts=(MinToolCalls(2),))
        await self._assert_added_tool_offered_next(runner, self._agent(runner, agent_loop_settings=settings))

    async def test_review_continued_finish_still_offers_added_tool_next(self) -> None:
        # @intent refused-finish-still-adopts-added-tools
        runner = AddThenUseRunner(finish_in_first_turn=True)
        agent = self._agent(runner, middleware=[RefuseFirstFinish()], agent_loop_settings=AgentLoopSettings(max_iterations=6))
        await self._assert_added_tool_offered_next(runner, agent)

    async def test_plain_tool_turn_offers_added_tool_next(self) -> None:
        runner = AddThenUseRunner(finish_in_first_turn=False)
        await self._assert_added_tool_offered_next(runner, self._agent(runner, agent_loop_settings=AgentLoopSettings(max_iterations=6)))


if __name__ == "__main__":
    unittest.main()
