from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from pydantic import BaseModel

from vidbyte import Agent, OutputSchemaViolationError, tool
from tests.test_text_model_runner import FakeTransport
from vidbyte.agents import AgentLoopSettings, AgentRuntime, MinIterations, MinToolCalls, MinToolCallsById, ToolSettings
from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.runners import TextModelRunner
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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[lookup])

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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[])
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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[tool_instance])

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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[lookup], max_tool_rounds=1)

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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            await agent.arun("task", provider="gemini")

        second_call_messages = runner.calls[1]["kwargs"]["messages"]
        model_idx = next(
            (i for i, m in enumerate(second_call_messages) if m.get("role") == "model"),
            None,
        )
        # The tool result rides on a 'user' turn — generateContent has no 'function' role —
        # so identify it by its functionResponse part rather than by role.
        function_result_idx = next(
            (
                i
                for i, m in enumerate(second_call_messages)
                if any("functionResponse" in part for part in m.get("parts", []) if isinstance(part, dict))
            ),
            None,
        )
        self.assertIsNotNone(model_idx, "no model turn found for Gemini")
        self.assertIsNotNone(function_result_idx, "no function result found for Gemini")
        self.assertLess(model_idx, function_result_idx, "model turn must precede function result")

    async def test_responses_api_next_request_pairs_function_calls_with_outputs(self) -> None:
        # Regression: after a Responses function_call turn the next /responses input must echo each
        # function_call (no item id) before its function_call_output, and never send role "tool".
        @tool
        def read(path: str) -> str:
            """Read a file."""
            return "content"

        @tool
        def boom(path: str) -> str:
            """Always fails."""
            raise RuntimeError("disk gone")

        runner = ToolCallingRunner(
            [
                FakeResponse(
                    "",
                    {
                        "output": [
                            {"type": "function_call", "id": "fc_a", "call_id": "call_1", "name": "read", "arguments": '{"path": "f.py"}'},
                            {"type": "function_call", "id": "fc_b", "call_id": "call_2", "name": "boom", "arguments": '{"path": "g.py"}'},
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "call_3"}]},
                ),
            ]
        )
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[read, boom])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("task")
        self.assertEqual(reply.content, "done")

        second = runner.calls[1]
        transport = FakeTransport({"output_text": "ok"})
        openai_runner = TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
        await openai_runner.arun(second["prompt"], messages=second["kwargs"]["messages"])
        wire_input = transport.requests[0]["json_body"]["input"]

        self.assertFalse([item for item in wire_input if item.get("role") == "tool"])
        calls = [item for item in wire_input if item.get("type") == "function_call"]
        self.assertEqual(
            calls,
            [
                {"type": "function_call", "call_id": "call_1", "name": "read", "arguments": '{"path": "f.py"}'},
                {"type": "function_call", "call_id": "call_2", "name": "boom", "arguments": '{"path": "g.py"}'},
            ],
        )
        outputs = {item["call_id"]: index for index, item in enumerate(wire_input) if item.get("type") == "function_call_output"}
        self.assertEqual(set(outputs), {"call_1", "call_2"})
        for call in calls:
            self.assertLess(wire_input.index(call), outputs[call["call_id"]])
        self.assertEqual(wire_input[outputs["call_1"]]["output"], "content")
        self.assertIn("[tool_error", wire_input[outputs["call_2"]]["output"])

    async def test_no_assistant_turn_for_text_only_response(self) -> None:
        # Text-only final response: no tool calls, so no assistant tool-call message should be inserted.
        runner = ToolCallingRunner(
            [
                FakeResponse("just text", {"choices": [{"message": {"role": "assistant", "content": "just text"}}]}),
            ]
        )
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[])
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
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            await agent.arun("task")

        third_call_messages = runner.calls[1]["kwargs"]["messages"]
        assistant_turns = [m for m in third_call_messages if isinstance(m.get("tool_calls"), list)]
        # First round produced exactly one assistant turn in the accumulated history.
        self.assertEqual(len(assistant_turns), 1, "expected exactly one assistant tool-call turn in accumulated messages")



def _chat_tool_turn(*calls: tuple[str, str, str]) -> FakeResponse:
    tool_calls = [{"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}} for call_id, name, arguments in calls]
    return FakeResponse("", {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}]})


class RejectedFinishSiblingCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_after_rejected_is_done_still_get_tool_results(self) -> None:
        searched: list[str] = []

        @tool
        def search(q: str) -> str:
            """Search."""
            searched.append(q)
            return "hit"

        runner = ToolCallingRunner(
            [
                _chat_tool_turn(("call_1", "isDone", '{"final_answer": "early"}'), ("call_2", "search", '{"q": "a"}')),
                _chat_tool_turn(("call_3", "search", '{"q": "b"}'), ("call_4", "search", '{"q": "c"}')),
                _chat_tool_turn(("call_5", "isDone", '{"final_answer": "done"}')),
            ]
        )
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[search], agent_loop_settings=AgentLoopSettings(output_contracts=[MinToolCalls(2)]))
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            result = await agent.arun("task")

        self.assertEqual(result.content, "done")
        self.assertEqual(searched, ["b", "c"], "the call after the rejected isDone must not run")
        following = self._assert_tool_calls_answered(runner.calls[1]["kwargs"]["messages"])
        self.assertIn("not executed", following[1]["content"])

    async def test_continued_finish_answers_is_done_and_skipped_calls_before_continuation(self) -> None:
        searched: list[str] = []

        @tool
        def search(q: str) -> str:
            """Search."""
            searched.append(q)
            return "hit"

        continued: list[bool] = []

        async def continue_once(runtime: AgentRuntime, result: object, state: object, messages: list[dict]) -> bool:
            if continued:
                return False
            continued.append(True)
            messages.append({"role": "user", "content": "Done check failed; keep working."})
            return True

        runner = ToolCallingRunner(
            [
                _chat_tool_turn(("call_1", "isDone", '{"final_answer": "early"}'), ("call_2", "search", '{"q": "a"}')),
                _chat_tool_turn(("call_3", "isDone", '{"final_answer": "done"}')),
            ]
        )
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[search])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}), patch.object(AgentRuntime, "_continue_finish_attempt", continue_once):
            result = await agent.arun("task")

        self.assertEqual(result.content, "done")
        self.assertEqual(searched, [], "the call after the continued isDone must not run")
        second_call_messages = runner.calls[1]["kwargs"]["messages"]
        following = self._assert_tool_calls_answered(second_call_messages)
        self.assertIn("not accepted", following[0]["content"])
        self.assertIn("not executed", following[1]["content"])
        self.assertEqual(second_call_messages[second_call_messages.index(following[-1]) + 1]["role"], "user")

    def _assert_tool_calls_answered(self, messages: list[dict]) -> list[dict]:
        """Assert every assistant tool_call id is answered by the contiguous tool messages that follow it; return them."""
        assistant_indices = [i for i, m in enumerate(messages) if isinstance(m.get("tool_calls"), list)]
        self.assertTrue(assistant_indices, "no assistant tool-call message found in messages")
        following: list[dict] = []
        for idx in assistant_indices:
            expected_ids = [call["id"] for call in messages[idx]["tool_calls"]]
            following = messages[idx + 1 : idx + 1 + len(expected_ids)]
            self.assertEqual([m.get("role") for m in following], ["tool"] * len(expected_ids))
            self.assertEqual([m.get("tool_call_id") for m in following], expected_ids)
        return following

if __name__ == "__main__":
    unittest.main()


class _Report(BaseModel):
    summary: str


def _text_turn(text: str) -> FakeResponse:
    return FakeResponse(text, {"choices": [{"message": {"role": "assistant", "content": text}}]})


class ContractUnsatisfiedStructuredOutputTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, runner: ToolCallingRunner) -> object:
        @tool
        def lookup(q: str) -> str:
            """Look something up."""
            return "hit"

        settings = AgentLoopSettings(output_contracts=(MinToolCalls(2),), max_contract_rejections=1)
        return build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[lookup], output_schema=_Report, agent_loop_settings=settings)

    async def test_schema_valid_answer_with_unmet_floor_keeps_structured(self) -> None:
        runner = ToolCallingRunner([_text_turn('{"summary": "early"}') for _ in range(4)])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await self._agent(runner).arun("task")

        self.assertEqual(reply.metadata["stop_reason"], "contract_unsatisfied")
        self.assertEqual(reply.structured, _Report(summary="early"))

    async def test_schema_valid_is_done_with_unmet_floor_keeps_structured(self) -> None:
        runner = ToolCallingRunner([_chat_tool_turn((f"call_{i}", "isDone", '{"final_answer": "{\\"summary\\": \\"early\\"}"}')) for i in range(4)])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await self._agent(runner).arun("task")

        self.assertEqual(reply.metadata["stop_reason"], "contract_unsatisfied")
        self.assertEqual(reply.structured, _Report(summary="early"))

    async def test_schema_invalid_answer_with_exhausted_budget_still_raises(self) -> None:
        runner = ToolCallingRunner([_text_turn("not json") for _ in range(4)])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            with self.assertRaises(OutputSchemaViolationError) as ctx:
                await self._agent(runner).arun("task")

        self.assertEqual(ctx.exception.stop_reason, "contract_unsatisfied")


class PerToolFloorAtCapTests(unittest.IsolatedAsyncioTestCase):
    async def test_floor_equal_to_per_tool_cap_is_met_even_when_denials_abort(self) -> None:
        # A per-tool cap only denies the call after the cap, so the floor is met without ever reaching the abort path.
        searched: list[str] = []

        @tool
        def web_search(q: str) -> str:
            """Search the web."""
            searched.append(q)
            return "hit"

        runner = ToolCallingRunner([_chat_tool_turn(("call_1", "web_search", '{"q": "a"}')), _chat_tool_turn(("call_2", "web_search", '{"q": "b"}')), _text_turn("answer")])
        settings = AgentLoopSettings(tool_settings=ToolSettings(max_calls_per_tool={"web_search": 2}, on_deny="abort"), output_contracts=(MinToolCallsById("web_search", 2),), max_iterations=6)
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[web_search], agent_loop_settings=settings)
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("task")

        self.assertEqual(reply.metadata["stop_reason"], "final_response")
        self.assertEqual(reply.content, "answer")
        self.assertEqual(searched, ["a", "b"])


class IterationFloorAtMaxIterationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_floor_equal_to_max_iterations_is_met_in_the_last_iteration(self) -> None:
        # The budget is checked before an iteration and the floor after its model call, so iteration 3 of 3 can finish.
        runner = ToolCallingRunner([_text_turn(f"answer {i}") for i in range(1, 4)])
        settings = AgentLoopSettings(max_iterations=3, output_contracts=(MinIterations(3),))
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, agent_loop_settings=settings)
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("task")

        self.assertEqual(reply.metadata["stop_reason"], "final_response")
        self.assertEqual(reply.content, "answer 3")
        self.assertEqual(len(runner.calls), 3)


class IsDoneObjectFinalAnswerTests(unittest.IsolatedAsyncioTestCase):
    # Models often send isDone's final_answer as a JSON object rather than a JSON-encoded string.
    async def test_object_final_answer_parses_against_output_schema_on_first_call(self) -> None:
        runner = ToolCallingRunner([_chat_tool_turn(("call_1", "isDone", '{"final_answer": {"summary": "café"}}'))])
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, output_schema=_Report)
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("task")

        self.assertEqual(reply.metadata["stop_reason"], "is_done")
        self.assertEqual(reply.structured, _Report(summary="café"))
        self.assertEqual(len(runner.calls), 1, "a valid object answer must not be rejected and retried")

    async def test_object_final_answer_without_schema_is_json_content(self) -> None:
        runner = ToolCallingRunner([_chat_tool_turn(("call_1", "isDone", '{"final_answer": {"severity": "high", "owners": ["dba"]}}'))])
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner)
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("task")

        self.assertEqual(json.loads(reply.content), {"severity": "high", "owners": ["dba"]})
