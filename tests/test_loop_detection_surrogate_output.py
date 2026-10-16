"""FILE: tests/test_loop_detection_surrogate_output.py

PURPOSE: Regression tests for LoopDetectionMiddleware counting tool output that holds a lone surrogate.
ROLE IN CODEBASE: Keeps repeated-output detection from aborting a run when a tool returns any Python str.
ARCHITECTURE NOTE: Drives the after_tool_call hook directly with ToolResult objects, then runs one offline
    agent through a scripted runner so the whole middleware pipeline sees the same output.
FUNCTION INVENTORY: LoopDetectionSurrogateHookTests checks the hook continues, still counts repeats up to
    the soft notice, and keeps a lone surrogate apart from its backslash-escaped text;
    LoopDetectionSurrogateAgentTests checks an agent run finishes instead of stopping with middleware_error.
COMMON MODIFICATION PATTERNS: Add an output shape a real tool can return (file names, decoded API text).
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: os.listdir yields 'report_\\udcff.txt' for a non-UTF-8 POSIX name (surrogateescape), and
    json.loads turns a half-escaped emoji "\\ud83d" into a lone surrogate; strict UTF-8 cannot encode either.
RELATED DOCS: None.
TESTS: Run with python -m pytest -q tests/test_loop_detection_surrogate_output.py.
"""

from __future__ import annotations

import json
import unittest

from tests.agent_test_support import build_test_agent
from vidbyte.lib.dataclasses.middleware import MiddlewareAction, MiddlewareContext, MiddlewareHook
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult
from vidbyte.middleware.builtins import LoopDetectionMiddleware
from vidbyte.middleware.builtins.loop_detection import REPEATED_OUTPUT_LOOP_NOTICE
from vidbyte.tools import tool

# A directory listing holding a POSIX file name that is not valid UTF-8, as os.listdir returns it.
LISTING_WITH_SURROGATE = "report_2024.txt\nreport_\udcff.txt\nsummary.md"


@tool
def list_files(folder: str) -> str:
    """List the files in a folder."""
    return LISTING_WITH_SURROGATE


class ScriptedToolRunner:
    """Offline runner that replays one scripted list of tool calls per model turn."""

    def __init__(self, turns: list[list[tuple[str, dict[str, object]]]]) -> None:
        self.turns = list(turns)

    async def arun(self, prompt: str, **_: object) -> object:
        calls = self.turns.pop(0)

        class _Resp:
            text = ""
            raw = {"output": [{"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": f"fc_{index}"} for index, (name, args) in enumerate(calls)]}
        return _Resp()


class LoopDetectionSurrogateHookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._run_state: dict = {}

    def _result_ctx(self, tool_name: str, output: str) -> MiddlewareContext:
        return MiddlewareContext(
            hook=MiddlewareHook.AFTER_TOOL_CALL,
            agent_name="test-agent",
            tool_call=ToolCall(tool_name=tool_name, arguments={}),
            tool_result=ToolResult.success(tool_name, output),
            run_state=self._run_state,
        )

    async def _started(self, **settings: int) -> LoopDetectionMiddleware:
        mw = LoopDetectionMiddleware(**settings)
        await mw.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="test-agent", run_state=self._run_state))
        return mw

    async def test_lone_surrogate_output_continues(self) -> None:
        # @intent output-hash-accepts-any-text
        # A tool result holding a lone surrogate must be counted, not raise and abort the run.
        mw = await self._started(soft_max_repeated_outputs=2)
        decision = await mw.after_tool_call(self._result_ctx("list_files", LISTING_WITH_SURROGATE))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)
        self.assertIsNone(decision.transform)

    async def test_repeated_surrogate_output_reaches_soft_notice(self) -> None:
        # Repeats of the same surrogate output still count toward the soft threshold.
        mw = await self._started(soft_max_repeated_outputs=2)
        status = json.loads('"all systems up \\ud83d"')
        await mw.after_tool_call(self._result_ctx("fetch_status", status))
        decision = await mw.after_tool_call(self._result_ctx("fetch_status", status))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)
        self.assertIsNotNone(decision.transform)
        visible = decision.transform.model_visible_tool_result
        self.assertIn(REPEATED_OUTPUT_LOOP_NOTICE, visible.output)
        self.assertEqual(decision.metadata["repeated_count"], 2)

    async def test_surrogate_and_its_escaped_text_are_counted_apart(self) -> None:
        # A lone "\udcff" and the six characters "\\udcff" are different outputs and must not share a count.
        mw = await self._started(soft_max_repeated_outputs=2)
        await mw.after_tool_call(self._result_ctx("list_files", "report_\udcff.txt"))
        decision = await mw.after_tool_call(self._result_ctx("list_files", "report_\\udcff.txt"))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)
        self.assertIsNone(decision.transform)


class LoopDetectionSurrogateAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_run_with_surrogate_tool_output_finishes(self) -> None:
        # The run reaches the model's answer instead of stopping with middleware_error.
        runner = ScriptedToolRunner([
            [("list_files", {"folder": "/data/reports"})],
            [("isDone", {"final_answer": "Done: I looked it up."})],
        ])
        agent = build_test_agent(
            name="files",
            system_prompt="Help with files.",
            runner=runner,
            tools=[list_files],
            middleware=[LoopDetectionMiddleware(soft_max_repeated_outputs=3)],
        )
        result = await agent.arun("What is in /data/reports?")
        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertEqual(runner.turns, [])


if __name__ == "__main__":
    unittest.main()
