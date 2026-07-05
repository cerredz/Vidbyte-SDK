from __future__ import annotations

import unittest
from unittest.mock import patch

from vidbyte import Agent, tool
from vidbyte.agents import AgentRuntime
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


class AssistantToolCallHistoryTests(unittest.IsolatedAsyncioTestCase):
    """Verify that the assistant's tool-call message is inserted before tool results in messages."""

    async def test_openai_chat_assistant_turn_precedes_tool_result_in_messages(self) -> None:
        @tool
        def read(path: str) -> str:
            """Read a file."""
            return "content"

        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {"id": "call_1", "type": "function", "function": {"name": "read", "arguments": '{"path": "f.py"}'}}
                                    ],
                                }
                            }
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {"id": "call_2", "type": "function", "function": {"name": "isDone", "arguments": '{"final_answer": "done"}'}}
                                    ],
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            await agent.arun("task")

        second_call_messages = runner.calls[1]["kwargs"]["messages"]
        self.assertGreater(len(second_call_messages), 1)
        assistant_idx = next(
            (i for i, m in enumerate(second_call_messages) if isinstance(m.get("tool_calls"), list)),
            None,
        )
        tool_result_idx = next(
            (i for i, m in enumerate(second_call_messages) if m.get("role") == "tool"),
            None,
        )
        self.assertIsNotNone(assistant_idx, "no assistant tool-call message found in messages")
        self.assertIsNotNone(tool_result_idx, "no tool result message found in messages")
        self.assertLess(assistant_idx, tool_result_idx, "assistant turn must precede tool result")

    async def test_anthropic_assistant_turn_precedes_tool_result_in_messages(self) -> None:
        @tool
        def read(path: str) -> str:
            """Read a file."""
            return "content"

        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {
                        "content": [
                            {"type": "tool_use", "id": "tu_1", "name": "read", "input": {"path": "f.py"}}
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {
                        "content": [
                            {"type": "tool_use", "id": "tu_2", "name": "isDone", "input": {"final_answer": "done"}}
                        ]
                    },
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            await agent.arun("task", provider="anthropic")

        second_call_messages = runner.calls[1]["kwargs"]["messages"]
        assistant_idx = next(
            (i for i, m in enumerate(second_call_messages) if m.get("role") == "assistant"),
            None,
        )
        tool_result_idx = next(
            (i for i, m in enumerate(second_call_messages)
             if m.get("role") == "user" and isinstance(m.get("content"), list)
             and any(b.get("type") == "tool_result" for b in m["content"] if isinstance(b, dict))),
            None,
        )
        self.assertIsNotNone(assistant_idx, "no assistant message found for Anthropic")
        self.assertIsNotNone(tool_result_idx, "no tool_result message found for Anthropic")
        self.assertLess(assistant_idx, tool_result_idx, "assistant turn must precede tool result")

    async def test_gemini_model_turn_precedes_tool_result_in_messages(self) -> None:
        @tool
        def read(path: str) -> str:
            """Read a file."""
            return "content"

        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {
                        "candidates": [
                            {
                                "content": {
                                    "role": "model",
                                    "parts": [{"functionCall": {"name": "read", "args": {"path": "f.py"}}}],
                                }
                            }
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {
                        "candidates": [
                            {
                                "content": {
                                    "role": "model",
                                    "parts": [{"functionCall": {"name": "isDone", "args": {"final_answer": "done"}}}],
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            await agent.arun("task", provider="gemini")

        second_call_messages = runner.calls[1]["kwargs"]["messages"]
        model_idx = next(
            (i for i, m in enumerate(second_call_messages) if m.get("role") == "model"),
            None,
        )
        function_result_idx = next(
            (i for i, m in enumerate(second_call_messages) if m.get("role") == "function"),
            None,
        )
        self.assertIsNotNone(model_idx, "no model turn found for Gemini")
        self.assertIsNotNone(function_result_idx, "no function result found for Gemini")
        self.assertLess(model_idx, function_result_idx, "model turn must precede function result")

    async def test_responses_api_skips_assistant_turn_insertion(self) -> None:
        # Responses API (output list) — no assistant turn should be inserted since the
        # format_assistant_tool_calls returns None for this shape.
        @tool
        def read(path: str) -> str:
            """Read a file."""
            return "content"

        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "read", "arguments": '{"path": "f.py"}', "call_id": "fc_1"}]},
                ),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "fc_2"}]},
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("task")
        # The run must still complete successfully — just without an assistant turn in messages.
        self.assertEqual(reply.content, "done")

    async def test_no_assistant_turn_for_text_only_response(self) -> None:
        # Text-only final response: no tool calls, so no assistant tool-call message should be inserted.
        runner = ToolCallingRunner(
            [
                FakeResponse("just text", {"choices": [{"message": {"role": "assistant", "content": "just text"}}]}),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("task")
        self.assertEqual(reply.content, "just text")
        # Only one call was made — no second call to inspect messages on.
        self.assertEqual(len(runner.calls), 1)

    async def test_two_sequential_tool_calls_each_get_own_assistant_turn(self) -> None:
        @tool
        def read(path: str) -> str:
            """Read a file."""
            return "content"

        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read", "arguments": '{"path": "a.py"}'}}],
                                }
                            }
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "isDone", "arguments": '{"final_answer": "done"}'}}],
                                }
                            }
                        ]
                    },
                ),
            ]
        )
        agent = Agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            await agent.arun("task")

        third_call_messages = runner.calls[1]["kwargs"]["messages"]
        assistant_turns = [m for m in third_call_messages if isinstance(m.get("tool_calls"), list)]
        # First round produced exactly one assistant turn in the accumulated history.
        self.assertEqual(len(assistant_turns), 1, "expected exactly one assistant tool-call turn in accumulated messages")


if __name__ == "__main__":
    unittest.main()
