"""FILE: tests/test_prompt_opens_tool_exchange.py

PURPOSE: Regression tests that the run's prompt is sent in front of the tool exchange it provoked.
ROLE IN CODEBASE: Covers PromptPlacement and the OpenAI-compatible, Anthropic, and Responses request bodies;
    the Gemini replay case lives in tests/test_gemini_tool_wire_format.py.
ARCHITECTURE NOTE: Sends history through TextModelRunner/StreamingTextModelRunner with fake transports and
    reads the captured wire bodies; the agent test replays the runtime's second request the same way.
COMMON MODIFICATION PATTERNS: Add a case per provider wire shape that carries tool calls.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: A call after a user turn or tool result (replayed or a later round) is skipped.
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
from vidbyte.lib.config import ModelProvider, TextModelConfig, TextModelMode
from vidbyte.lib.runners import StreamingTextModelRunner, TextModelRunner

PROMPT = "fix calc.py"
CHAT_CALL = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}
CHAT_RESULT = {"role": "tool", "tool_call_id": "c1", "content": "source"}
ANTHROPIC_CALL = {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "read", "input": {}}]}
ANTHROPIC_RESULT = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "source"}]}
# A caller-supplied history may open with an assistant greeting; it must stay in front.
GREETING = {"role": "assistant", "content": "Hi! I'm the front desk bot."}


def _chat_wire(messages: list) -> list:
    transport = FakeTransport({"choices": [{"message": {"content": "ok"}}]})
    TextModelRunner(TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_keys=["xai-key"], mode=TextModelMode.DIRECT), transport=transport).run(PROMPT, system="Work.", messages=messages)
    return transport.requests[0]["json_body"]["messages"]


def _anthropic_wire(messages: list) -> list:
    transport = FakeTransport({"content": [{"type": "text", "text": "ok"}]})
    TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_keys=["sk-ant-key"], mode=TextModelMode.DIRECT), transport=transport).run(PROMPT, messages=messages)
    return transport.requests[0]["json_body"]["messages"]


def _responses_wire(messages: list) -> list:
    transport = FakeTransport({"output_text": "ok"})
    TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_keys=["sk-key"], mode=TextModelMode.DIRECT), transport=transport).run(PROMPT, messages=messages)
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

    def test_caller_greeting_stays_in_front_of_the_prompt(self) -> None:
        wire = _chat_wire([GREETING])
        self.assertEqual(wire[1:], [GREETING, {"role": "user", "content": PROMPT}])

    def test_caller_conversation_opening_with_a_greeting_keeps_the_prompt_last(self) -> None:
        history = [GREETING, {"role": "user", "content": "Do you sell gift cards?"}, {"role": "assistant", "content": "Yes, at the counter."}]
        wire = _chat_wire(history)
        self.assertEqual(wire[1:], [*history, {"role": "user", "content": PROMPT}])

    def test_prompt_lands_between_a_caller_greeting_and_the_tool_round(self) -> None:
        wire = _chat_wire([GREETING, CHAT_CALL, CHAT_RESULT])
        self.assertEqual(wire[1:], [GREETING, {"role": "user", "content": PROMPT}, CHAT_CALL, CHAT_RESULT])

    def test_prompt_skips_a_replayed_exchange_and_opens_this_runs_round(self) -> None:
        # The caller replays a transcript that already holds a tool exchange; only this run's round gets the prompt.
        replayed = [{"role": "user", "content": "Hours on Sunday?"}, CHAT_CALL, CHAT_RESULT, {"role": "assistant", "content": "We're closed on Sunday."}]
        wire = _chat_wire([*replayed, CHAT_CALL, CHAT_RESULT])
        self.assertEqual(wire[1:], [*replayed, {"role": "user", "content": PROMPT}, CHAT_CALL, CHAT_RESULT])

    def test_later_rounds_of_this_run_stay_behind_the_first(self) -> None:
        wire = _chat_wire([CHAT_CALL, CHAT_RESULT, CHAT_CALL, CHAT_RESULT])
        self.assertEqual(wire[1:], [{"role": "user", "content": PROMPT}, CHAT_CALL, CHAT_RESULT, CHAT_CALL, CHAT_RESULT])

    def test_rejected_draft_alone_keeps_the_prompt_last(self) -> None:
        draft = {"role": "assistant", "content": "draft"}
        self.assertEqual(_chat_wire([draft])[1:], [draft, {"role": "user", "content": PROMPT}])


class AnthropicPromptOrderTests(unittest.TestCase):
    def test_prompt_opens_a_tool_round(self) -> None:
        wire = _anthropic_wire([ANTHROPIC_CALL, ANTHROPIC_RESULT])
        self.assertTrue(_is_prompt(wire[0]))
        self.assertEqual(wire[1:], [ANTHROPIC_CALL, ANTHROPIC_RESULT])

    def test_prompt_follows_a_prior_reply_and_opens_the_round(self) -> None:
        wire = _anthropic_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}, ANTHROPIC_CALL, ANTHROPIC_RESULT])
        self.assertTrue(_is_prompt(wire[2]))
        self.assertEqual(wire[3], ANTHROPIC_CALL)

    def test_prompt_lands_between_a_caller_greeting_and_the_tool_round(self) -> None:
        wire = _anthropic_wire([GREETING, ANTHROPIC_CALL, ANTHROPIC_RESULT])
        self.assertEqual(wire, [GREETING, {"role": "user", "content": PROMPT}, ANTHROPIC_CALL, ANTHROPIC_RESULT])

    def test_prompt_skips_a_replayed_exchange_and_opens_this_runs_round(self) -> None:
        # The replayed call follows a user turn and the later round follows a tool_result, so both are skipped.
        answer = {"role": "assistant", "content": "We're closed on Sunday."}
        replayed = [{"role": "user", "content": "Hours on Sunday?"}, ANTHROPIC_CALL, ANTHROPIC_RESULT, answer]
        wire = _anthropic_wire([*replayed, ANTHROPIC_CALL, ANTHROPIC_RESULT, ANTHROPIC_CALL, ANTHROPIC_RESULT])
        self.assertEqual(wire[:5], [*replayed, {"role": "user", "content": PROMPT}])
        self.assertEqual(len(wire), 9)

    def test_prompt_appends_without_a_tool_round(self) -> None:
        wire = _anthropic_wire([{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "prior reply"}])
        self.assertTrue(_is_prompt(wire[-1]))

    def test_streaming_uses_the_same_order(self) -> None:
        transport = FakeStreamingTransport([])
        runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_keys=["sk-ant-key"], mode=TextModelMode.DIRECT), transport=transport)
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
        runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_keys=["sk-key"], mode=TextModelMode.DIRECT), transport=transport)
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
        await TextModelRunner(TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_keys=["xai-key"], mode=TextModelMode.DIRECT), transport=transport).arun(second["prompt"], system="Work.", messages=second["kwargs"]["messages"])
        wire = transport.requests[0]["json_body"]["messages"]
        self.assertEqual([turn["role"] for turn in wire], ["system", "user", "assistant", "tool"])
        self.assertEqual(wire[1]["content"], second["prompt"])


if __name__ == "__main__":
    unittest.main()
