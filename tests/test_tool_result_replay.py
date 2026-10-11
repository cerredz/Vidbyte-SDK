"""FILE: tests/test_tool_result_replay.py

PURPOSE:
    Regression tests proving that tool output a model never saw in one run is
    not replayed to the model on a later run of the same agent.
ROLE IN CODEBASE:
    Covers BaseAgent's cross-run tool-call memory together with the runtime's
    model-visible tool result (ToolSettings.result_max_chars truncation and
    middleware model_visible_tool_result redaction).
ARCHITECTURE NOTE:
    Uses an offline scripted runner; the second run's system prompt is where
    BaseAgent renders earlier tool calls.
RELATED DOCS:
    docs/design/replay-model-visible-tool-output.md
TESTS:
    Run with `python -m pytest tests/test_tool_result_replay.py`.
"""

from __future__ import annotations

import unittest

from tests.agent_test_support import build_test_agent
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.lib.dataclasses.middleware import MiddlewareDecision, MiddlewareTransform
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec

SECRET = "ssn=123-45-6789"
RAW_OUTPUT = "customer record: " + "x" * 2400 + " " + SECRET


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class LookupTool(BaseTool):
    """Returns a long customer record that ends with a sensitive value."""

    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup_customer", description="Look up a customer.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success("lookup_customer", RAW_OUTPUT)


class ScriptedRunner:
    """Calls the tool once on the first run, then answers directly; records every system prompt."""

    def __init__(self) -> None:
        self.systems: list[str] = []
        self.responses = [
            FakeResponse("", {"output": [{"type": "function_call", "name": "lookup_customer", "arguments": "{}", "call_id": "call_1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "found ann"}'}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "9 to 5"}'}]}),
        ]

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> FakeResponse:
        self.systems.append(system or "")
        return self.responses.pop(0)


class RedactingMiddleware(AgentMiddleware):
    """Shows the model a redacted copy of every tool result."""

    async def after_tool_call(self, context: object) -> MiddlewareDecision:
        result = context.tool_result
        redacted = ToolResult(tool_name=result.tool_name, status=result.status, output=result.output.replace(SECRET, "[REDACTED]"), metadata=result.metadata)
        return MiddlewareDecision.continue_(transform=MiddlewareTransform(model_visible_tool_result=redacted))


class ToolResultReplayTests(unittest.IsolatedAsyncioTestCase):
    async def _run_twice(self, **agent_options: object) -> tuple[ScriptedRunner, object]:
        # Run once with a tool call, then once more on the same agent, and return the runner and first reply.
        runner = ScriptedRunner()
        agent = build_test_agent(name="support", system_prompt="Help customers.", runner=runner, tools=[LookupTool()], **agent_options)
        first = await agent.generate_reply("look up ann")
        await agent.generate_reply("what are your hours?")
        return runner, first

    async def test_truncated_output_is_not_replayed_uncapped_on_the_next_run(self) -> None:
        runner, _ = await self._run_twice(agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(result_max_chars=200)))

        second_run_system = runner.systems[-1]
        self.assertIn("lookup_customer", second_run_system)
        self.assertIn("tool output truncated by ToolSettings", second_run_system)
        self.assertFalse(SECRET in second_run_system, "raw tool output was replayed to the model on the next run")

    async def test_redacted_output_is_not_replayed_raw_on_the_next_run(self) -> None:
        runner, _ = await self._run_twice(middleware=[RedactingMiddleware()])

        second_run_system = runner.systems[-1]
        self.assertIn("[REDACTED]", second_run_system)
        self.assertFalse(SECRET in second_run_system, "raw tool output was replayed to the model on the next run")

    async def test_raw_result_stays_on_the_reply_metadata(self) -> None:
        _, first = await self._run_twice(middleware=[RedactingMiddleware()], agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(result_max_chars=200)))

        lookup = next(context for context in first.metadata["tool_calls"] if context.tool_name == "lookup_customer")
        self.assertEqual(lookup.result.output, RAW_OUTPUT)
        self.assertEqual(lookup.output, RAW_OUTPUT)


if __name__ == "__main__":
    unittest.main()
