"""FILE: tests/test_anthropic_cache_breakpoints.py

PURPOSE: Proves item 9 of spec infinite-memory-context-economy on AnthropicProvider: a request whose tools and system this adapter has not sent before is byte-identical to main, a repeat carries at most three block-level {"type": "ephemeral"} marks (system, last message, the message before the newest assistant turn), caller-supplied cache_control stops all marking, the caller's messages are never mutated, the digest memory is bounded, and every repeat body passes the gateway's cache rule and the SDK's emitted-key list, direct, streamed, through the gateway, and from a real agent loop.
ROLE IN CODEBASE: Root-level test of vidbyte/providers/anthropic.py (spec section 13: provider HTTP is faked at the transport, or _create_payload is called directly).
ARCHITECTURE NOTE: The main body for the shared request is a literal JSON string captured from main at base 0f2aeb48, so INV-9.2 cannot pass by changing the oracle. _require_short_cache mirrors the gateway rule the spec cites (backend provider/generative_models/client.py:260-278: object or null, ttl absent or "5m"). Transports deep-copy each body, so a mark the adapter adds later to a shared object would show up as a difference.
FUNCTION INVENTORY: _config / _provider / _payload build one request; _marks lists every cache_control path in a body; _require_short_cache is the gateway oracle; RecordingTransport, StreamingTransport fake HTTP. FirstSendTests (INV-9.2 per adapter); RepeatMarkTests (AC-9.1, INV-9.2, INV-9.3, EC-9.1, EC-9.2, EC-9.8); CallerMarkTests (AC-9.3, INV-9.4, EC-9.5); NoMutationTests (AC-9.5, INV-9.5, EC-9.6); GatewayRuleTests (AC-9.4, INV-9.1, INV-9.7, EC-9.9); SeenPrefixLimitTests (INV-9.6); AgentLoopTests (AC-9.2, EC-9.4, NFR-9.1, FR-9.1 run_text and stream_text).
COMMON MODIFICATION PATTERNS: A new history shape is one more config plus the expected list of mark paths from _marks.
WHAT NOT TO DO IN THIS FILE: 1. Do not call a real endpoint. 2. Do not compare a repeat body with another adapter's output; the expected marks are written out. 3. Do not reuse one AnthropicProvider across tests; the seen-digest memory is per instance.
KNOWN EDGE CASES: The task prompt sits inside the payload's messages at prompt_index, so "the message before the newest assistant turn" is counted on the payload's messages, prompt included.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-9.x), 6.2 (AC-9.x), 7 (EC-9.x), 8.5, 12.3 row 15.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_anthropic_cache_breakpoints.py -q
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import unittest
from collections.abc import Iterator, Mapping
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from tests.features.sdk_managed_text.managed_text_fixtures import GATEWAY_URL, VIDBYTE_KEY, ScriptedGateway, provider_answer
from tests.features.sdk_managed_text.test_managed_text_wire_contract import EMITTED_KEYS
from vidbyte import tool
from vidbyte.agents import AgentLoopSettings, AgentRuntime
from vidbyte.lib.config import ModelProvider, TextModelConfig, TextModelMode
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from vidbyte.providers.anthropic import AnthropicProvider

MODEL = "claude-sonnet-4-5"
SYSTEM = "You answer from memory."
PROMPT = "Compare the prices."
EPHEMERAL = {"type": "ephemeral"}
TOOLS = ({"name": "lookup", "description": "Find a fact.", "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}},)
HISTORY = (
    {"role": "user", "content": "Find the Acme price."},
    {"role": "assistant", "content": [{"type": "text", "text": "Looking it up."}, {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": "acme"}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "Acme is 49 USD."}]},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "lookup", "input": {"q": "globex"}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "Globex is 59 USD."}]},
)
# main's body for TOOLS, SYSTEM, HISTORY and PROMPT at prompt_index 1, captured at base 0f2aeb48.
MAIN_BODY_JSON = '{"model": "claude-sonnet-4-5", "max_tokens": 1024, "messages": [{"role": "user", "content": "Find the Acme price."}, {"role": "user", "content": "Compare the prices."}, {"role": "assistant", "content": [{"type": "text", "text": "Looking it up."}, {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": "acme"}}]}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "Acme is 49 USD."}]}, {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "lookup", "input": {"q": "globex"}}]}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "Globex is 59 USD."}]}], "system": "You answer from memory.", "tools": [{"name": "lookup", "description": "Find a fact.", "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}]}'


def _config(**fields: Any) -> TextModelConfig:
    options: dict[str, Any] = {"tools": TOOLS, "messages": HISTORY, "prompt_index": 1}
    options.update(fields)
    return TextModelConfig(provider=ModelProvider.ANTHROPIC, model=MODEL, api_keys=["sk-ant-k"], mode=TextModelMode.DIRECT, **options)


def _provider() -> AnthropicProvider:
    return AnthropicProvider(model=MODEL, api_keys=["sk-ant-k"], mode=TextModelMode.DIRECT)


def _payload(provider: AnthropicProvider, config: TextModelConfig, system: str | None = SYSTEM, prompt: str = PROMPT) -> dict[str, Any]:
    # A deep copy, so a later call that changed a shared object would show up as a difference.
    return copy.deepcopy(provider._create_payload(config, prompt, system, None))


def _marks(node: Any, path: str = "") -> list[tuple[str, Any]]:
    # Every cache_control in a body, as (path, value), in document order.
    found: list[tuple[str, Any]] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "cache_control":
                found.append((path or "<top>", value))
            else:
                found.extend(_marks(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_marks(value, f"{path}[{index}]"))
    return found


def _marked(block: Mapping[str, Any]) -> dict[str, Any]:
    return {**block, "cache_control": EPHEMERAL}


def _require_short_cache(body: Mapping[str, Any]) -> None:
    # The gateway's rule (backend provider/generative_models/client.py:260-278): no top-level cache_control; each one an object or null, ttl absent or "5m".
    if "cache_control" in body:
        raise AssertionError("top-level cache_control is refused by the gateway")
    for path, value in _marks(body):
        if value is not None and not isinstance(value, Mapping):
            raise AssertionError(f"{path}: cache_control must be an object or null, got {value!r}")
        if isinstance(value, Mapping) and value.get("ttl", "5m") != "5m":
            raise AssertionError(f"{path}: ttl {value['ttl']!r} is refused")


def _expected_repeat() -> dict[str, Any]:
    # INV-9.3 on the shared request: the system as one marked text block, the last block of the last message, and the last
    # block of the message before the newest assistant turn (payload messages 5 and 3).
    body = json.loads(MAIN_BODY_JSON)
    body["system"] = [{"type": "text", "text": SYSTEM, "cache_control": EPHEMERAL}]
    body["messages"][5]["content"][-1] = _marked(body["messages"][5]["content"][-1])
    body["messages"][3]["content"][-1] = _marked(body["messages"][3]["content"][-1])
    return body


class FirstSendTests(unittest.TestCase):
    def test_the_seen_memory_is_per_adapter_instance(self) -> None:
        # INV-9.2 / D-13: a second adapter has seen nothing, so its first body is main's even after another adapter repeated.
        repeated = _provider()
        _payload(repeated, _config())
        self.assertEqual(_payload(repeated, _config()), _expected_repeat())
        self.assertEqual(json.dumps(_provider()._create_payload(_config(), PROMPT, SYSTEM, None)), MAIN_BODY_JSON)


class LoneSurrogateTests(unittest.TestCase):
    def test_a_lone_surrogate_in_the_system_or_a_tool_sends_mains_body_first_and_marks_the_repeat(self) -> None:
        # INV-9.2, INV-0.2 (review R-6, R-11). A workspace file name
        # puts a lone surrogate in the root's system through the map,
        # and a tool description can hold one too. The first body is
        # main's with that text, unmarked, and main's transport
        # serializes it with json.dumps; the repeat carries the three
        # marks.
        system = f"{SYSTEM} Notes: notes/caf\ud800.md"
        tools = ({**TOOLS[0], "description": "Find a fact in notes/caf\ud800.md."},)
        for label, config, sent_system in (("system", _config(), system), ("tool", _config(tools=tools), SYSTEM)):
            with self.subTest(surrogate_in=label):
                provider = _provider()
                first = provider._create_payload(config, PROMPT, sent_system, None)
                main_first = json.loads(MAIN_BODY_JSON)
                main_first["system"] = sent_system
                main_first["tools"] = [dict(tool) for tool in config.tools]
                self.assertEqual(first, main_first)
                self.assertEqual(json.dumps(first), json.dumps(main_first))
                self.assertEqual(_marks(first), [])
                second = _payload(provider, config, system=sent_system)
                repeat = _expected_repeat()
                repeat["system"][0]["text"] = sent_system
                repeat["tools"] = [dict(tool) for tool in config.tools]
                self.assertEqual(second, repeat)


class RepeatMarkTests(unittest.TestCase):
    def test_a_repeat_marks_the_system_the_last_message_and_the_message_before_the_newest_assistant(self) -> None:
        # AC-9.1, INV-9.3: exactly three marks, each exactly {"type": "ephemeral"}.
        provider = _provider()
        first = _payload(provider, _config())
        second = _payload(provider, _config())
        # INV-9.2, EC-9.1, AC-9.1 first half: the first body is main's byte for byte, the system a string, no cache_control anywhere.
        self.assertEqual(json.dumps(first), MAIN_BODY_JSON)
        self.assertEqual(_marks(first), [])
        self.assertEqual(second, _expected_repeat())
        self.assertEqual([value for _, value in _marks(second)], [EPHEMERAL] * 3)

    def test_a_different_history_with_the_same_tools_and_system_is_still_a_repeat(self) -> None:
        # INV-9.3 / D-13: the digest covers tools and system only, so a grown history is marked on its own newest turns.
        provider = _provider()
        _payload(provider, _config(messages=HISTORY[:3]))
        second = _payload(provider, _config(messages=HISTORY[:3], prompt_index=None))
        # Payload messages: user, assistant(text, tool_use t1), user(tool_result t1), then the prompt appended last as a string.
        self.assertEqual(second["messages"][3], {"role": "user", "content": [{"type": "text", "text": PROMPT, "cache_control": EPHEMERAL}]})
        self.assertEqual(second["messages"][0], {"role": "user", "content": [{"type": "text", "text": "Find the Acme price.", "cache_control": EPHEMERAL}]})
        self.assertEqual(sorted(path for path, _ in _marks(second)), ["messages[0].content[0]", "messages[3].content[0]", "system[0]"])

    def test_a_stable_system_with_no_history_marks_the_system_only(self) -> None:
        # EC-9.2: repeated one-shot calls with one stable system and no history.
        provider = _provider()
        config = _config(messages=(), prompt_index=None)
        first = _payload(provider, config)
        second = _payload(provider, config)
        self.assertEqual(_marks(first), [])
        self.assertEqual(second["system"], [{"type": "text", "text": SYSTEM, "cache_control": EPHEMERAL}])
        self.assertEqual([path for path, _ in _marks(second)], ["system[0]"])
        self.assertEqual(second["messages"], [{"role": "user", "content": PROMPT}])

    def test_a_thinking_block_or_an_empty_text_block_is_never_marked(self) -> None:
        # EC-9.8, INV-9.3: the mark goes on the last markable block before them.
        thinking = {"type": "thinking", "thinking": "Weigh both prices.", "signature": "sig-1"}
        history = ({"role": "user", "content": "Which is cheaper?"}, {"role": "assistant", "content": [{"type": "text", "text": "Acme is cheaper."}, {"type": "text", "text": ""}, thinking]})
        provider = _provider()
        config = _config(messages=history, prompt_index=0)
        _payload(provider, config)
        second = _payload(provider, config)
        # Payload messages: the prompt first, the user question, then the assistant turn (the newest assistant message).
        self.assertEqual(second["messages"][2]["content"], [{"type": "text", "text": "Acme is cheaper.", "cache_control": EPHEMERAL}, {"type": "text", "text": ""}, thinking])
        self.assertEqual(second["messages"][1], {"role": "user", "content": [{"type": "text", "text": "Which is cheaper?", "cache_control": EPHEMERAL}]})
        self.assertEqual(len(_marks(second)), 3)

    def test_an_empty_system_is_not_marked(self) -> None:
        # INV-9.3: the system mark needs a non-empty system; the message marks still apply.
        provider = _provider()
        _payload(provider, _config(), system=None)
        second = _payload(provider, _config(), system=None)
        self.assertNotIn("system", second)
        self.assertEqual(sorted(path for path, _ in _marks(second)), ["messages[3].content[0]", "messages[5].content[0]"])


class CallerMarkTests(unittest.TestCase):
    def test_caller_supplied_cache_control_anywhere_stops_all_marking(self) -> None:
        # AC-9.3, INV-9.4, EC-9.5: extra_body top level, a message block, or a tool already carries cache_control.
        marked_history = (*HISTORY[:4], {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "Globex is 59 USD.", "cache_control": EPHEMERAL}]})
        marked_tools = ({**TOOLS[0], "cache_control": EPHEMERAL},)
        for label, caller_config in (
            ("extra_body", _config(extra_body={"cache_control": EPHEMERAL})),
            ("messages", _config(messages=marked_history)),
            ("tools", _config(tools=marked_tools)),
        ):
            with self.subTest(caller_mark=label):
                provider = _provider()
                first = _payload(provider, caller_config)
                second = _payload(provider, caller_config)
                self.assertEqual(second, first)
                self.assertEqual(len(_marks(second)), 1, "only the caller's own mark")
                # Positive control on the same adapter: the clean request is marked on its repeat.
                _payload(provider, _config())
                self.assertEqual(_payload(provider, _config()), _expected_repeat())


class NoMutationTests(unittest.TestCase):
    def test_the_callers_messages_are_never_marked_and_marks_never_pile_up(self) -> None:
        # AC-9.5, INV-9.5, EC-9.6: four payloads from one config; the caller's dicts and lists stay as they were.
        messages = copy.deepcopy(list(HISTORY))
        before = copy.deepcopy(messages)
        config = _config(messages=messages)
        provider = _provider()
        bodies = [provider._create_payload(config, PROMPT, SYSTEM, None) for _ in range(4)]
        self.assertEqual(_marks(bodies[0]), [])
        for body in bodies[1:]:
            self.assertEqual(len(_marks(body)), 3)
        self.assertEqual(json.loads(json.dumps(bodies[3])), _expected_repeat())
        self.assertEqual(list(config.messages), before)
        self.assertEqual(_marks(list(config.messages)), [])
        self.assertEqual(messages, before)
        for sent, original in ((bodies[3]["messages"][5], config.messages[4]), (bodies[3]["messages"][3], config.messages[2])):
            self.assertIsNot(sent["content"], original["content"], "a marked message must carry a new content list")


class GatewayRuleTests(unittest.TestCase):
    def test_a_repeat_body_passes_the_gateway_rule_and_adds_no_top_level_key(self) -> None:
        # AC-9.4, INV-9.1, INV-9.7: every mark is exactly ephemeral with no ttl; the top-level keys stay inside EMITTED_KEYS.
        provider = _provider()
        full = _config(temperature=0.3, top_p=0.9, stop_sequences=("END",), tool_choice={"type": "auto"}, thinking_config={"type": "enabled", "budget_tokens": 1024}, metadata={"team": "sdk"})
        first = _payload(provider, full)
        second = _payload(provider, full)
        self.assertEqual(len(_marks(second)), 3)
        for path, value in _marks(second):
            self.assertEqual(value, EPHEMERAL, path)
        _require_short_cache(second)
        self.assertEqual(set(second), set(first))
        self.assertLessEqual(set(second), EMITTED_KEYS[ModelProvider.ANTHROPIC])
        self.assertNotIn("cache_control", second)

    def test_a_gateway_run_forwards_the_marked_repeat_body(self) -> None:
        # EC-9.9, AC-9.4: in AUTO mode the runner keeps one adapter, so the second gateway envelope carries the marks.
        transport = ScriptedGateway(provider_answer(ModelProvider.ANTHROPIC, "Acme is cheaper."))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC.value, model="claude-sonnet-5"), transport=transport)
            for _ in range(2):
                runner.run(PROMPT, system=SYSTEM, tools=TOOLS, messages=HISTORY, prompt_index=1)
        self.assertEqual([request["url"] for request in transport.requests], [GATEWAY_URL, GATEWAY_URL])
        first, second = (request["json_body"]["body"] for request in transport.requests)
        self.assertEqual(_marks(first), [])
        self.assertEqual(sorted(path for path, _ in _marks(second)), ["messages[3].content[0]", "messages[5].content[0]", "system[0]"])
        _require_short_cache(second)
        self.assertLessEqual(set(second), EMITTED_KEYS[ModelProvider.ANTHROPIC])


class SeenPrefixLimitTests(unittest.TestCase):
    def test_the_adapter_remembers_at_most_the_limit_and_clears_when_full(self) -> None:
        # INV-9.6: fill the memory with ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT systems, repeat one, then overflow it.
        from vidbyte.providers.anthropic import ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT

        self.assertEqual(ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT, 256)
        provider = _provider()
        config = _config()
        systems = [f"System number {n}." for n in range(ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT)]
        for system in systems:
            self.assertEqual(_marks(_payload(provider, config, system=system)), [], system)
        self.assertEqual(len(_marks(_payload(provider, config, system=systems[0]))), 3, "a remembered system is a repeat")
        overflow = "System number overflow."
        self.assertEqual(_marks(_payload(provider, config, system=overflow)), [], "a new system when full is a first send")
        self.assertEqual(_marks(_payload(provider, config, system=systems[1])), [], "the full memory was cleared")
        self.assertEqual(len(_marks(_payload(provider, config, system=overflow))), 3, "the system added after the clear is remembered")


class RecordingTransport:
    """Fake HTTP transport: answers each request with the next scripted body and keeps a deep copy of every request body."""

    def __init__(self, *bodies: Mapping[str, Any]) -> None:
        self.bodies = list(bodies)
        self.requests: list[dict[str, Any]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, Any] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse:
        self.requests.append(copy.deepcopy(dict(json_body or {})))
        return HttpResponse(status_code=200, body=json.dumps(self.bodies.pop(0)), headers={})


class StreamingTransport:
    """Fake sync streaming transport: records a deep copy of each body and streams one text delta."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def stream_request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, Any] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> Iterator[str]:
        self.requests.append(copy.deepcopy(dict(json_body or {})))
        yield '{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}}'


def _tool_turn(call_id: str, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "tool_use", "id": call_id, "name": name, "input": dict(arguments)}], "stop_reason": "tool_use"}


def _text_turn(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


@tool
def search(query: str) -> str:
    """Search the notes."""
    return "result: 4"


@tool
def fetch(url: str) -> str:
    """Fetch a page."""
    return "page: 2 + 2 = 4"


def _agent_requests(loop: AgentLoopSettings) -> list[dict[str, Any]]:
    # Three Anthropic calls from one agent through the real runtime and adapter: two tool turns, then an answer.
    transport = RecordingTransport(_tool_turn("c1", "search", {"query": "a"}), _tool_turn("c2", "fetch", {"url": "u"}), _text_turn("done"))
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model=MODEL, api_keys=["sk-ant-key"], mode=TextModelMode.DIRECT), transport=transport)
    agent = build_test_agent(name="desk", system_prompt="Research.", runner=runner, tools=[search, fetch], provider="anthropic", model_name=MODEL, agent_loop_settings=loop)
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        asyncio.run(agent.arun("TASK"))
    return transport.requests


class AgentLoopTests(unittest.TestCase):
    def test_an_agent_whose_system_changes_every_call_sends_no_marks(self) -> None:
        # AC-9.2, EC-9.4, NFR-9.1: a loop limit puts the per-call counter in the system, so no digest repeats.
        varying = _agent_requests(AgentLoopSettings(max_iterations=5))
        self.assertEqual(len(varying), 3)
        self.assertEqual(len({json.dumps(request["system"]) for request in varying}), 3, "precondition: the system differs on every call")
        for index, request in enumerate(varying):
            self.assertEqual(_marks(request), [], f"call {index}")
        # Positive control: the same agent with no loop limit keeps one system, so calls two and three are marked.
        stable = _agent_requests(AgentLoopSettings())
        self.assertEqual(_marks(stable[0]), [])
        for index in (1, 2):
            paths = sorted(path for path, _ in _marks(stable[index]))
            last = len(stable[index]["messages"]) - 1
            self.assertEqual(len(paths), 3, f"call {index}: {paths}")
            self.assertIn("system[0]", paths)
            self.assertIn(f"messages[{last}].content[0]", paths)
            _require_short_cache(stable[index])

    def test_adapter_level_a_system_that_changes_every_call_is_never_marked(self) -> None:
        # AC-9.2 at the adapter: five calls with the same tools and a new system each time; then one repeat is marked.
        provider = _provider()
        for n in range(5):
            self.assertEqual(_marks(_payload(provider, _config(), system=f"{SYSTEM} Call {n}.")), [])
        self.assertEqual(len(_marks(_payload(provider, _config(), system=f"{SYSTEM} Call 4."))), 3)

    def test_stream_text_marks_a_repeat_like_run_text(self) -> None:
        # FR-9.1: stream_text builds the same payload, so its second body is marked and still carries stream.
        provider = _provider()
        transport = StreamingTransport()
        for _ in range(2):
            self.assertEqual("".join(provider.stream_text(prompt=PROMPT, system=SYSTEM, metadata=None, transport=transport, config=_config())), "ok")
        first, second = transport.requests
        self.assertEqual(_marks(first), [])
        self.assertIs(second.pop("stream"), True)
        self.assertEqual(second, _expected_repeat())


if __name__ == "__main__":
    unittest.main()
