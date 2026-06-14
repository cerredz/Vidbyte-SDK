from __future__ import annotations

import unittest

from vidbyte import Agent, tool
from vidbyte.tools import BaseTool, ToolCall, ToolPermission, ToolResult, ToolSpec


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class ToolCallingRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.responses.pop(0)


class WriteTool(BaseTool):
    def __init__(self) -> None:
        self.executed = False

    def spec(self) -> ToolSpec:
        return ToolSpec(name="write", description="Write.", permission=ToolPermission.WRITE)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed = True
        return ToolResult.success("write", "done")


class AgentToolLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_executes_openai_response_tool_call_then_final_answer(self) -> None:
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return f"found:{topic}"

        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "lookup",
                                "arguments": '{"topic": "sdk"}',
                                "call_id": "call_1",
                            }
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "isDone",
                                "arguments": '{"final_answer": "final answer"}',
                                "call_id": "call_2",
                            }
                        ]
                    },
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[lookup])

        reply = await agent.arun("task")

        self.assertEqual(reply.content, "final answer")
        self.assertEqual(reply.metadata["tool_call_count"], 2)
        self.assertEqual(reply.metadata["tool_call_states"], ("succeeded", "succeeded"))
        self.assertEqual(reply.metadata["stop_reason"], "is_done")
        self.assertEqual(reply.metadata["iteration_count"], 2)
        self.assertIn("tools", runner.calls[0]["kwargs"])
        self.assertIn("messages", runner.calls[1]["kwargs"])

    async def test_agent_records_unknown_tool_failure_context(self) -> None:
        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "missing", "arguments": "{}"}]},
                ),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "handled"}'}]},
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[])
        agent.add_tool(lambda: "unused")

        reply = await agent.arun("task")

        self.assertEqual(reply.content, "handled")
        self.assertEqual(reply.metadata["tool_call_states"], ("failed", "succeeded"))

    async def test_agent_denies_write_tool_by_default(self) -> None:
        tool_instance = WriteTool()
        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "write", "arguments": "{}"}]},
                ),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "denied handled"}'}]},
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[tool_instance])

        reply = await agent.arun("task")

        self.assertEqual(reply.metadata["tool_call_states"], ("denied", "succeeded"))
        self.assertFalse(tool_instance.executed)

    async def test_agent_stops_at_max_tool_rounds(self) -> None:
        @tool
        def lookup() -> str:
            return "again"

        runner = ToolCallingRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[lookup], max_tool_rounds=1)

        reply = await agent.arun("task")

        self.assertEqual(reply.content, "Agent runtime stopped after reaching max_iterations.")
        self.assertEqual(reply.metadata["stop_reason"], "max_iterations")
        self.assertEqual(reply.metadata["iteration_count"], 1)

    async def test_tool_call_arguments_echoed_into_next_turn_context(self) -> None:
        # [Silent Failure] the agent must re-read the arguments of the tool it called, not just the result.
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return f"found:{topic}"

        runner = ToolCallingRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "sdk"}', "call_id": "call_1"}]}),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[lookup])

        await agent.arun("task")

        sent_messages = runner.calls[1]["kwargs"]["messages"]
        assistant_calls = [m for m in sent_messages if m.get("role") == "assistant" and m.get("tool_calls")]
        self.assertEqual(len(assistant_calls), 1)
        self.assertIn("sdk", assistant_calls[0]["tool_calls"][0]["function"]["arguments"])

    async def test_isdone_only_turn_appends_no_assistant_tool_call_message(self) -> None:
        # [Hidden Assumption] a turn that only signals completion must not echo a dangling tool_use.
        runner = ToolCallingRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "x"}', "call_id": "c1"}]}),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]}),
            ]
        )

        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return f"found:{topic}"

        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[lookup])
        await agent.arun("task")

        # The second runner call carries history from the lookup turn but not from a (terminal) isDone echo.
        assistant_calls = [m for m in runner.calls[1]["kwargs"]["messages"] if m.get("role") == "assistant" and m.get("tool_calls")]
        echoed_names = [tc["function"]["name"] for m in assistant_calls for tc in m["tool_calls"]]
        self.assertNotIn("isDone", echoed_names)
        self.assertEqual(echoed_names, ["lookup"])


if __name__ == "__main__":
    unittest.main()
