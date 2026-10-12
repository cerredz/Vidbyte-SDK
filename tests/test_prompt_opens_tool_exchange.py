"""FILE: tests/test_prompt_opens_tool_exchange.py

PURPOSE: Regression tests that the run's prompt is sent in front of the tool exchange it provoked.
ROLE IN CODEBASE: Covers PromptPlacement and the OpenAI-compatible, Anthropic, and Responses request bodies.
ARCHITECTURE NOTE: Sends history through TextModelRunner/StreamingTextModelRunner with fake transports and
    reads the captured wire bodies; the agent test replays the runtime's second request the same way.
COMMON MODIFICATION PATTERNS: Add a case per provider wire shape that carries tool calls.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: Anthropic tool_result turns carry role "user" but do not introduce a call.
RELATED DOCS: vidbyte/providers/gemini.py (_prompt_index) holds the same rule for Gemini.
TESTS: Run with python -m pytest -q tests/test_prompt_opens_tool_exchange.py.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from tests.test_agent_tool_loop import FakeResponse, ToolCallingRunner
from tests.test_streaming_text_runner import FakeStreamingTransport
from tests.test_text_model_runner import FakeTransport
from vidbyte import tool
from vidbyte.agents import AgentRuntime
from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.runners import StreamingTextModelRunner, TextModelRunner

PROMPT = "fix calc.py"
CHAT_CALL = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}
CHAT_RESULT = {"role": "tool", "tool_call_id": "c1", "content": "source"}
ANTHROPIC_CALL = {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "read", "input": {}}]}
ANTHROPIC_RESULT = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "source"}]}


def _chat_wire(messages: list) -> list:
    transport = FakeTransport({"choices": [{"message": {"content": "ok"}}]})
    TextModelRunner(TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_key="key"), transport=transport).run(PROMPT, system="Work.", messages=messages)
    return transport.requests[0]["json_body"]["messages"]


def _anthropic_wire(messages: list) -> list:
    transport = FakeTransport({"content": [{"type": "text", "text": "ok"}]})
    TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key"), transport=transport).run(PROMPT, messages=messages)
    return transport.requests[0]["json_body"]["messages"]


def _responses_wire(messages: list) -> list:
    transport = FakeTransport({"output_text": "ok"})
    TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport).run(PROMPT, messages=messages)
    return transport.requests[0]["json_body"]["input"]


def _is_prompt(turn: dict) -> bool:
    return turn.get("role") == "user" and turn.get("content") == PROMPT


class CompatiblePromptOrderTests(unittest.TestCase):
    def test_prompt_opens_a_tool_round(self) -> None:
        wire = _chat_wire([CHAT_CALL, CHAT_RESULT])
        self.assertEqual([turn["role"] for turn in wire], ["system", "user", "assistant", "tool"])
        self.assertTrue(_is_prompt(wire[1]))

    def test_prompt_follows_a_prior_reply_and_opens_the_round(self) -> None:
        wire = _chat_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}, CHAT_CALL, CHAT_RESULT])
        self.assertTrue(_is_prompt(wire[3]))
        self.assertEqual(wire[2]["content"], "prior reply")
        self.assertIn("tool_calls", wire[4])

    def test_prompt_appends_without_a_tool_round(self) -> None:
        wire = _chat_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}])
        self.assertTrue(_is_prompt(wire[-1]))
        self.assertTrue(_is_prompt(_chat_wire([])[-1]))


class AnthropicPromptOrderTests(unittest.TestCase):
    def test_prompt_opens_a_tool_round(self) -> None:
        wire = _anthropic_wire([ANTHROPIC_CALL, ANTHROPIC_RESULT])
        self.assertTrue(_is_prompt(wire[0]))
        self.assertEqual(wire[1:], [ANTHROPIC_CALL, ANTHROPIC_RESULT])

    def test_prompt_follows_a_prior_reply_and_opens_the_round(self) -> None:
        wire = _anthropic_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}, ANTHROPIC_CALL, ANTHROPIC_RESULT])
        self.assertTrue(_is_prompt(wire[2]))
        self.assertEqual(wire[3], ANTHROPIC_CALL)

    def test_a_tool_result_does_not_introduce_a_call(self) -> None:
        # A tool_result turn carries role "user" but is not the user speaking, so the call still needs the prompt.
        wire = _anthropic_wire([{"role": "user", "content": "earlier"}, ANTHROPIC_RESULT, ANTHROPIC_CALL])
        self.assertTrue(_is_prompt(wire[2]))
        self.assertEqual(wire[3], ANTHROPIC_CALL)

    def test_prompt_appends_without_a_tool_round(self) -> None:
        wire = _anthropic_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}])
        self.assertTrue(_is_prompt(wire[-1]))

    def test_streaming_uses_the_same_order(self) -> None:
        transport = FakeStreamingTransport([])
        runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key"), transport=transport)
        list(runner.stream(PROMPT, messages=[ANTHROPIC_CALL, ANTHROPIC_RESULT]))
        self.assertTrue(_is_prompt(transport.requests[0]["json_body"]["messages"][0]))


class ResponsesPromptOrderTests(unittest.TestCase):
    def test_prompt_opens_a_tool_round(self) -> None:
        wire = _responses_wire([CHAT_CALL, CHAT_RESULT])
        self.assertTrue(_is_prompt(wire[0]))
        self.assertEqual([item.get("type") for item in wire[1:]], ["function_call", "function_call_output"])

    def test_prompt_follows_a_prior_reply_and_opens_the_round(self) -> None:
        wire = _responses_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}, {**CHAT_CALL, "content": "reading"}, CHAT_RESULT])
        # The call's own note stays with its function_call, behind the prompt.
        self.assertTrue(_is_prompt(wire[2]))
        self.assertEqual(wire[3], {"role": "assistant", "content": "reading"})
        self.assertEqual(wire[4]["type"], "function_call")

    def test_prompt_appends_without_a_tool_round(self) -> None:
        wire = _responses_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}])
        self.assertTrue(_is_prompt(wire[-1]))

    def test_streaming_uses_the_same_order(self) -> None:
        transport = FakeStreamingTransport([])
        runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
        list(runner.stream(PROMPT, messages=[CHAT_CALL, CHAT_RESULT]))
        self.assertTrue(_is_prompt(transport.requests[0]["json_body"]["input"][0]))


class AgentRequestOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_request_opens_with_the_task_on_the_wire(self) -> None:
        # The runtime's second request, replayed through a compatible provider, must read
        # system > user(task) > assistant(call) > tool, not end on the task again.
        @tool
        def read(path: str) -> str:
            """Read a file."""
            return "source"

        def call(call_id: str, name: str, arguments: str) -> FakeResponse:
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}]}
            return FakeResponse("", {"choices": [{"message": message}]})

        runner = ToolCallingRunner([call("c1", "read", '{"path": "calc.py"}'), call("c2", "isDone", '{"final_answer": "done"}')])
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, tools=[read])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            await agent.arun(PROMPT)
        second = runner.calls[1]
        transport = FakeTransport({"choices": [{"message": {"content": "ok"}}]})
        await TextModelRunner(TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_key="key"), transport=transport).arun(second["prompt"], system="Work.", messages=second["kwargs"]["messages"])
        wire = transport.requests[0]["json_body"]["messages"]
        self.assertEqual([turn["role"] for turn in wire], ["system", "user", "assistant", "tool"])
        self.assertEqual(wire[1]["content"], second["prompt"])


if __name__ == "__main__":
    unittest.main()
