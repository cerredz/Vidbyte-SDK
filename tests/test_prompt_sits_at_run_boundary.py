"""FILE: tests/test_prompt_sits_at_run_boundary.py

PURPOSE: Regression tests that the task is sent at the boundary between the caller's history and this run's own
    exchange, so a rejected plain-text draft and its feedback never push the task behind the tool results.
ROLE IN CODEBASE: Drives agents end to end through TextModelRunner and the real provider adapters (DeepSeek's
    compatible wire, Anthropic, Gemini) with a scripted fake transport, and reads the captured request bodies.
ARCHITECTURE NOTE: The runtime passes prompt_index (where this run's first own message sits) and the providers
    insert the task there; without it they keep the shape rule tested in tests/test_prompt_opens_tool_exchange.py.
COMMON MODIFICATION PATTERNS: Script one more response per scenario and assert on the request bodies.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: A before_model_call transform that rewrites the head of the list drops prompt_index; Gemini still
    puts the task first when the history opens with a model turn.
RELATED DOCS: vidbyte/lib/util/prompt_placement.py; vidbyte/providers/gemini.py (_prompt_index).
TESTS: Run with python -m pytest -q tests/test_prompt_sits_at_run_boundary.py.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from vidbyte import CodingAgent, tool
from vidbyte.agents import AgentLoopSettings, AgentRuntime
from vidbyte.agents.contracts import MinDistinctTools
from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision, MiddlewareTransform
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from vidbyte.middleware import AgentMiddleware

TASK = "TASK: what is 2 + 2? Search, then fetch the source."
GREETING = {"role": "assistant", "content": "Hi! I'm the research desk."}
QUESTION = {"role": "user", "content": "Can you check sums?"}
ANSWER = {"role": "assistant", "content": "Yes, send one over."}


class SequenceTransport:
    """Fake HTTP transport that answers each request with the next scripted body and keeps every request body."""

    def __init__(self, *bodies: Mapping[str, Any]) -> None:
        self.bodies = list(bodies)
        self.requests: list[dict[str, Any]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, Any] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse:
        self.requests.append(dict(json_body or {}))
        return HttpResponse(status_code=200, body=json.dumps(self.bodies.pop(0)), headers={})


class SpyRunner:
    """Wraps a TextModelRunner and records the prompt_index each call received."""

    def __init__(self, inner: TextModelRunner) -> None:
        self.inner = inner
        self._config = inner._config
        self.prompt_indexes: list[int | None] = []

    async def arun(self, prompt: str, *, system: str | None = None, tools: Any = (), tool_choice: Any = None, messages: Any = (), response_format: Any = None, prompt_index: int | None = None) -> Any:
        self.prompt_indexes.append(prompt_index)
        return await self.inner.arun(prompt, system=system, tools=tools, tool_choice=tool_choice, messages=messages, response_format=response_format, prompt_index=prompt_index)


def chat_text(text: str) -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def chat_call(call_id: str, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    call = {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(dict(arguments))}}
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}


def anthropic_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


def anthropic_call(call_id: str, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "tool_use", "id": call_id, "name": name, "input": dict(arguments)}], "stop_reason": "tool_use"}


def gemini_text(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]}


def gemini_call(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": name, "args": dict(arguments)}}]}}]}


@tool
def search(query: str) -> str:
    """Search the web."""
    return "result: 4"


@tool
def fetch(url: str) -> str:
    """Fetch a page."""
    return "page: 2 + 2 = 4"


def _runner(provider: ModelProvider, model: str, transport: SequenceTransport) -> TextModelRunner:
    return TextModelRunner(TextModelConfig(provider=provider, model=model, api_key="key"), transport=transport)


async def _research(runner: object, provider: str, model: str, *, messages: list | None = None, middleware: tuple = ()) -> None:
    # A research agent that must use two distinct tools, so a plain "4" first is rejected.
    agent = build_test_agent(name="researcher", system_prompt="Research.", runner=runner, tools=[search, fetch], provider=provider, model_name=model, middleware=middleware, agent_loop_settings=AgentLoopSettings(output_contracts=[MinDistinctTools(2)]))
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        if messages is None:
            await agent.arun(TASK)
        else:
            await agent.arun(TASK, messages=messages)


def _roles(turns: list[Mapping[str, Any]]) -> list[str]:
    # Role per turn, with an assistant turn that carries calls marked as such.
    return [f"{turn['role']}+calls" if turn.get("tool_calls") else str(turn["role"]) for turn in turns]


class CompatibleRunBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_plain_draft_then_tool_rounds_keep_the_task_before_the_draft(self) -> None:
        transport = SequenceTransport(chat_text("4"), chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4, confirmed."))
        await _research(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport), "deepseek", "deepseek-v4-pro")
        second, third, fourth = (request["messages"] for request in transport.requests[1:])
        self.assertEqual(_roles(second), ["system", "user", "assistant", "user"])
        self.assertEqual(second[1]["content"], TASK)
        self.assertEqual(_roles(third), ["system", "user", "assistant", "user", "assistant+calls", "tool"])
        self.assertEqual([third[1]["content"], third[2]["content"]], [TASK, "4"])
        self.assertEqual(_roles(fourth)[-4:], ["assistant+calls", "tool", "assistant+calls", "tool"])
        self.assertEqual([turn["content"] for turn in fourth if turn.get("content") == TASK], [TASK])
        self.assertEqual(fourth[1]["content"], TASK)

    async def test_caller_history_stays_in_front_of_the_task_and_the_draft(self) -> None:
        transport = SequenceTransport(chat_text("4"), chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4, confirmed."))
        await _research(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport), "deepseek", "deepseek-v4-pro", messages=[GREETING, QUESTION, ANSWER])
        third = transport.requests[2]["messages"]
        self.assertEqual(third[1:5], [GREETING, QUESTION, ANSWER, {"role": "user", "content": TASK}])
        self.assertEqual(third[5]["content"], "4")
        self.assertEqual(_roles(third)[5:], ["assistant", "user", "assistant+calls", "tool"])

    async def test_caller_greeting_cases_still_follow_the_shape_rule(self) -> None:
        # The first request has no turn of this run's own, so a caller greeting (with or without Q/A) keeps the task last.
        for history in ([GREETING], [GREETING, QUESTION, ANSWER]):
            transport = SequenceTransport(chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4"))
            await _research(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport), "deepseek", "deepseek-v4-pro", messages=history)
            first, second = transport.requests[0]["messages"], transport.requests[1]["messages"]
            self.assertEqual(first[1:], [*history, {"role": "user", "content": TASK}])
            # With a tool round of its own, the task sits after the caller history and in front of that round.
            self.assertEqual(second[1 : len(history) + 2], [*history, {"role": "user", "content": TASK}])
            self.assertEqual(_roles(second)[len(history) + 2 :], ["assistant+calls", "tool"])

    async def test_a_transform_that_rewrites_the_head_falls_back_to_the_shape_rule(self) -> None:
        class Summarize(AgentMiddleware):
            async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
                # Once a tool result exists, replace everything before the newest round, caller history included, with one note.
                messages = list(ctx.provider_messages)
                if not any(message.get("role") == "tool" for message in messages):
                    return MiddlewareDecision.continue_()
                return MiddlewareDecision.continue_(transform=MiddlewareTransform(provider_messages=[{"role": "user", "content": "(summary)"}, *messages[-2:]]))

        transport = SequenceTransport(chat_text("4"), chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4, confirmed."))
        spy = SpyRunner(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport))
        await _research(spy, "deepseek", "deepseek-v4-pro", messages=[GREETING, QUESTION, ANSWER], middleware=(Summarize(),))
        # No own turn yet, then the boundary after the caller's three messages, then none once the head was rewritten.
        self.assertEqual(spy.prompt_indexes[:3], [None, 3, None])
        third = transport.requests[2]["messages"]
        self.assertEqual(third[-1], {"role": "user", "content": TASK})


class CodingAgentRunBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_verify_rejection_then_a_tool_round_keeps_the_task_before_the_claim(self) -> None:
        transport = SequenceTransport(chat_text("I fixed it."), chat_call("c1", "write_text", {"path": "done.txt", "content": "ok"}), chat_text("I fixed it."))
        with tempfile.TemporaryDirectory() as root:
            agent = build_test_agent(name="coder", system_prompt="Work.", root_dir=root, runner=_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport), agent_type=CodingAgent, provider="deepseek", model_name="deepseek-v4-pro", verify_command="test -f done.txt", load_agents=False, load_environment=False, load_map=False, progress_notes=False)
            with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
                await agent.arun(TASK)
        third = transport.requests[2]["messages"]
        self.assertEqual(_roles(third), ["system", "user", "assistant", "user", "assistant+calls", "tool"])
        self.assertEqual([third[1]["content"], third[2]["content"]], [TASK, "I fixed it."])
        self.assertTrue(third[3]["content"].startswith("Not done yet"))


class AnthropicRunBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_plain_draft_then_a_tool_round(self) -> None:
        transport = SequenceTransport(anthropic_text("4"), anthropic_call("t1", "search", {"query": "2+2"}), anthropic_call("t2", "fetch", {"url": "u"}), anthropic_text("4, confirmed."))
        await _research(_runner(ModelProvider.ANTHROPIC, "claude-test", transport), "anthropic", "claude-sonnet-5")
        third = transport.requests[2]["messages"]
        self.assertEqual(third[0], {"role": "user", "content": TASK})
        self.assertEqual(third[1]["content"], "4")
        self.assertEqual(third[3]["content"][0]["type"], "tool_use")
        self.assertEqual(third[-1]["content"][0]["type"], "tool_result")


class GeminiRunBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_plain_draft_then_a_tool_round_opens_with_the_task(self) -> None:
        transport = SequenceTransport(gemini_text("4"), gemini_call("search", {"query": "2+2"}), gemini_call("fetch", {"url": "u"}), gemini_text("4, confirmed."))
        await _research(_runner(ModelProvider.GEMINI, "gemini-test", transport), "gemini", "gemini-2.5-flash")
        contents = transport.requests[2]["contents"]
        self.assertEqual(contents[0], {"role": "user", "parts": [{"text": TASK}]})
        self.assertEqual(contents[1]["parts"], [{"text": "4"}])
        self.assertIn("functionCall", contents[3]["parts"][0])
        self.assertIn("functionResponse", contents[-1]["parts"][0])

    async def test_caller_history_stays_in_front_of_the_task(self) -> None:
        transport = SequenceTransport(gemini_text("4"), gemini_call("search", {"query": "2+2"}), gemini_call("fetch", {"url": "u"}), gemini_text("4, confirmed."))
        await _research(_runner(ModelProvider.GEMINI, "gemini-test", transport), "gemini", "gemini-2.5-flash", messages=[QUESTION, ANSWER])
        contents = transport.requests[2]["contents"]
        self.assertEqual([turn["role"] for turn in contents], ["user", "model", "user", "model", "user", "model", "user"])
        self.assertEqual(contents[2], {"role": "user", "parts": [{"text": TASK}]})
        self.assertIn("functionResponse", contents[-1]["parts"][0])


class PromptIndexValidationTests(unittest.TestCase):
    def test_prompt_index_must_be_a_non_negative_int(self) -> None:
        for bad in (-1, True, 1.0, "1"):
            with self.assertRaises(ConfigurationError):
                TextModelConfig(provider=ModelProvider.DEEPSEEK, model="m", prompt_index=bad)
        self.assertEqual(TextModelConfig(provider=ModelProvider.DEEPSEEK, model="m", prompt_index=0).prompt_index, 0)


if __name__ == "__main__":
    unittest.main()
