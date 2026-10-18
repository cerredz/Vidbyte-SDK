"""FILE: tests/test_prompt_sits_at_run_boundary.py

PURPOSE: Regression tests that the task is sent at the boundary between the caller's history and this run's own
    exchange, so a rejected plain-text draft and its feedback never push the task behind the tool results.
ROLE IN CODEBASE: Drives agents end to end through TextModelRunner and the real provider adapters (DeepSeek's
    compatible wire, Anthropic, Gemini) with a scripted fake transport, and reads the captured request bodies.
ARCHITECTURE NOTE: The runtime passes prompt_index (where this run's first own message sits) and the providers
    insert the task there; without it they keep the shape rule tested in tests/test_prompt_opens_tool_exchange.py.
COMMON MODIFICATION PATTERNS: Script one more response per scenario and assert on the request bodies.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: A before_model_call transform that rewrites the head of the list moves prompt_index to the first
    turn of this run it kept, or drops it when it kept none; Gemini still puts the task first when the history opens
    with a model turn.
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
from vidbyte.context import ContextManager, ContextWindowPlacement
from vidbyte.context.primitives import TextContextItem
from vidbyte.lib.config import ModelProvider, TextModelConfig, TextModelMode
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision, MiddlewareTransform
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from vidbyte.middleware import AgentMiddleware, MessageHistoryCompactionMiddleware, TraceReplacementCompactionMiddleware

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
    provider_key = {ModelProvider.DEEPSEEK: "key", ModelProvider.ANTHROPIC: "sk-ant-key", ModelProvider.GEMINI: "AQ" + "." + "x" * 40}[provider]
    return TextModelRunner(TextModelConfig(provider=provider, model=model, api_keys=[provider_key], mode=TextModelMode.DIRECT), transport=transport)


async def _research(runner: object, provider: str, model: str, *, messages: list | None = None, middleware: tuple = (), **options: object) -> None:
    # A research agent that must use two distinct tools, so a plain "4" first is rejected.
    agent = build_test_agent(name="researcher", system_prompt="Research.", runner=runner, tools=[search, fetch], provider=provider, model_name=model, middleware=middleware, agent_loop_settings=AgentLoopSettings(output_contracts=[MinDistinctTools(2)]), **options)
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        if messages is None:
            await agent.arun(TASK)
        else:
            await agent.arun(TASK, messages=messages)


def _roles(turns: list[Mapping[str, Any]]) -> list[str]:
    # Role per turn, with an assistant turn that carries calls marked as such.
    return [f"{turn['role']}+calls" if turn.get("tool_calls") else str(turn["role"]) for turn in turns]


def _task_and_first_call(request: Mapping[str, Any]) -> tuple[list[int], int | None]:
    # Where the task turn sits and where the first call turn sits, on the chat, Anthropic or Gemini wire.
    turns = request.get("messages") or request.get("contents") or []
    tasks = [index for index, turn in enumerate(turns) if turn.get("content") == TASK or turn.get("parts") == [{"text": TASK}]]
    blocks = [(turn["content"] if isinstance(turn.get("content"), list) else []) + list(turn.get("parts") or []) for turn in turns]
    calls = [index for index, turn in enumerate(turns) if turn.get("tool_calls") or any(block.get("type") == "tool_use" or "functionCall" in block for block in blocks[index])]
    return tasks, (calls[0] if calls else None)


class ProviderMessagesSpy(AgentMiddleware):
    """Records the provider messages each before_model_call sees, before later middleware rewrite them."""

    def __init__(self) -> None:
        self.seen: list[list[dict[str, Any]]] = []

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.seen.append([dict(message) for message in ctx.provider_messages])
        return MiddlewareDecision.continue_()


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

    async def test_a_transform_that_rewrites_the_head_moves_the_boundary_to_the_first_kept_own_turn(self) -> None:
        class Summarize(AgentMiddleware):
            async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
                # Once a tool result exists, replace everything before the newest round, caller history included, with one user-role note.
                messages = list(ctx.provider_messages)
                if not any(message.get("role") == "tool" for message in messages):
                    return MiddlewareDecision.continue_()
                return MiddlewareDecision.continue_(transform=MiddlewareTransform(provider_messages=[{"role": "user", "content": "(summary)"}, *messages[-2:]]))

        transport = SequenceTransport(chat_text("4"), chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4, confirmed."))
        spy = SpyRunner(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport))
        await _research(spy, "deepseek", "deepseek-v4-pro", messages=[GREETING, QUESTION, ANSWER], middleware=(Summarize(),))
        # No own turn yet, then the boundary after the caller's three messages, then the kept round once the head was rewritten.
        self.assertEqual(spy.prompt_indexes[:3], [None, 3, 1])
        third = transport.requests[2]["messages"]
        self.assertEqual(_roles(third), ["system", "user", "user", "assistant+calls", "tool"])
        self.assertEqual([third[1]["content"], third[2]["content"]], ["(summary)", TASK])

    async def test_a_transform_that_keeps_none_of_the_run_falls_back_to_the_shape_rule(self) -> None:
        class Collapse(AgentMiddleware):
            async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
                # Once a tool result exists, replace the whole list with one note, so no turn of this run is left to anchor the task.
                if not any(message.get("role") == "tool" for message in ctx.provider_messages):
                    return MiddlewareDecision.continue_()
                return MiddlewareDecision.continue_(transform=MiddlewareTransform(provider_messages=[{"role": "user", "content": "(summary)"}]))

        transport = SequenceTransport(chat_text("4"), chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4, confirmed."))
        spy = SpyRunner(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport))
        await _research(spy, "deepseek", "deepseek-v4-pro", messages=[GREETING, QUESTION, ANSWER], middleware=(Collapse(),))
        self.assertEqual(spy.prompt_indexes[:3], [None, 3, None])
        self.assertEqual(transport.requests[2]["messages"][-1], {"role": "user", "content": TASK})

    async def test_deleting_the_callers_answer_keeps_the_task_in_front_of_the_run(self) -> None:
        # The history preset drops the caller's ANSWER (index 2 of what middleware sees) and leaves QUESTION right in front of the run's first call.
        transport = SequenceTransport(chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4"))
        spy, seen = SpyRunner(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport)), ProviderMessagesSpy()
        await _research(spy, "deepseek", "deepseek-v4-pro", messages=[GREETING, QUESTION, ANSWER], middleware=(seen, MessageHistoryCompactionMiddleware.delete_messages(start=2, end=2)))
        self.assertEqual(seen.seen[1][:3], [GREETING, QUESTION, ANSWER])
        self.assertEqual(spy.prompt_indexes, [None, 2, 2])
        for request in transport.requests[1:]:
            self.assertEqual(request["messages"][1:4], [GREETING, QUESTION, {"role": "user", "content": TASK}])
            self.assertEqual(_roles(request["messages"])[4], "assistant+calls")

    async def test_a_caller_turn_equal_to_a_run_turn_never_anchors_the_task(self) -> None:
        # A continued chat replays an earlier run whose call and result equal this run's own, so those turns cannot tell
        # the run apart; the task must not jump in front of the caller's earlier exchange and its answer.
        first = SequenceTransport(chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4"))
        await _research(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", first), "deepseek", "deepseek-v4-pro")
        earlier = [GREETING, QUESTION, *first.requests[1]["messages"][-2:], ANSWER]
        transport = SequenceTransport(chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_text("4"))
        await _research(_runner(ModelProvider.DEEPSEEK, "deepseek-v4-pro", transport), "deepseek", "deepseek-v4-pro", messages=earlier, middleware=(MessageHistoryCompactionMiddleware.delete_messages(start=0, end=0),))
        second = transport.requests[1]["messages"]
        self.assertEqual(second[1:5], earlier[1:])
        self.assertEqual(second[5], {"role": "user", "content": TASK})
        self.assertEqual(second[6:], earlier[2:4])


class CompactedRunBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire(self) -> None:
        # A pinned top note puts the run boundary past 0; keeping only the newest round replaces that note with a user-role trace.
        wires = (
            (ModelProvider.DEEPSEEK, "deepseek-v4-pro", "deepseek", (chat_call("c1", "search", {"query": "2+2"}), chat_call("c2", "fetch", {"url": "u"}), chat_call("c3", "search", {"query": "4"}), chat_text("4"))),
            (ModelProvider.ANTHROPIC, "claude-sonnet-5", "anthropic", (anthropic_call("t1", "search", {"query": "2+2"}), anthropic_call("t2", "fetch", {"url": "u"}), anthropic_call("t3", "search", {"query": "4"}), anthropic_text("4"))),
            (ModelProvider.GEMINI, "gemini-2.5-flash", "gemini", (gemini_call("search", {"query": "2+2"}), gemini_call("fetch", {"url": "u"}), gemini_call("search", {"query": "4"}), gemini_text("4"))),
        )
        for provider, model, name, bodies in wires:
            with self.subTest(provider=name):
                manager = ContextManager()
                manager.upsert(TextContextItem(primitive_id="runbook", title="Runbook", content="Check the disk first."), placement=ContextWindowPlacement.TOP_OF_CONVERSATION)
                compaction = TraceReplacementCompactionMiddleware.keep_recent_tail(1, placement="synthetic_user", artifact={"goal": "add two numbers", "steps": ["searched", "fetched"]})
                transport = SequenceTransport(*bodies)
                await _research(_runner(provider, model, transport), name, model, middleware=(compaction,), context_manager=manager)
                self.assertEqual(len(transport.requests), 4)
                self.assertIn("Continual trace", json.dumps(transport.requests[-1]))
                for request in transport.requests[1:]:
                    tasks, first_call = _task_and_first_call(request)
                    self.assertEqual(len(tasks), 1)
                    self.assertLess(tasks[0], first_call)


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
