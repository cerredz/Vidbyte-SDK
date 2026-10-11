"""FILE: tests/features/coding_agent/conftest.py

PURPOSE: Shared offline fixtures for the coding-agent feature pack: the two feature imports, a scripted tool-calling model, and a fake provider HTTP send.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/coding_agent/; builds on tests/agent_test_support.py (bind_test_runner) and on the HttpTransport._send_once seam used by tests/test_web_operation_client_retry.py.
ARCHITECTURE NOTE: The feature imports happen inside fixtures, so a missing CodingAgent or BashTool fails each test at setup instead of aborting collection of the whole suite.
FUNCTION INVENTORY: coding_agent_cls returns vidbyte.CodingAgent; bash_module returns vidbyte.tools.builtins.bash; script_model returns ScriptedToolRunner, which replays one tool call per model turn and then isDone; fake_provider_http installs a recording fake for the single-attempt HTTP send.
COMMON MODIFICATION PATTERNS: Add a fixture here only when two or more modules in this pack need it; keep subprocess and process-liveness helpers in the module that uses them.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub CodingAgent or BashTool; a missing feature must stay red. 2. Do not open sockets or call providers; the runner replays scripted turns and the HTTP fake answers in-process.
KNOWN EDGE CASES: The scripted turns use the OpenAI chat-completions shape, so agents must keep provider "openai"; tool results come back as role "tool" messages. The HTTP fake does not patch asyncio.sleep, so responders must use statuses the transport never retries (200, 401).
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/spec/coding-agent/spec.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Mapping, Sequence
from types import ModuleType
from typing import Any

import pytest

from vidbyte.lib.http.transport import HttpResponse, HttpTransport

ProviderResponder = Callable[[Mapping[str, Any]], tuple[int, Mapping[str, Any]]]


class ScriptedTurn:
    """One canned model response carrying a chat-completions tool call."""

    def __init__(self, call_id: str, tool_name: str, arguments: Mapping[str, object]) -> None:
        tool_call = {"id": call_id, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(dict(arguments))}}
        self.text = ""
        self.raw = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [tool_call]}}]}


class ScriptedToolRunner:
    """Offline model stand-in: each turn requests one scripted tool call, and the last turn finishes with isDone."""

    def __init__(self, calls: Sequence[tuple[str, Mapping[str, object]]], final_answer: str) -> None:
        self._turns = [ScriptedTurn(f"call_{index}", name, arguments) for index, (name, arguments) in enumerate(calls, start=1)]
        self._turns.append(ScriptedTurn("call_done", "isDone", {"final_answer": final_answer}))
        self.requests: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> ScriptedTurn:
        self.requests.append(dict(kwargs))
        return self._turns.pop(0)

    def tool_messages(self) -> list[tuple[str, str]]:
        # The (tool name, content) pairs the model was shown in its final request, in call order.
        messages = self.requests[-1].get("messages", [])
        return [(message["name"], message["content"]) for message in messages if message.get("role") == "tool"]


@pytest.fixture
def coding_agent_cls() -> type:
    # Red until vidbyte exports CodingAgent at the root (spec §4).
    from vidbyte import CodingAgent

    return CodingAgent


@pytest.fixture
def bash_module() -> ModuleType:
    # Red until vidbyte/tools/builtins/bash.py exists (spec §8.5); tests patch its BASH_* constants.
    return importlib.import_module("vidbyte.tools.builtins.bash")


@pytest.fixture
def script_model() -> type[ScriptedToolRunner]:
    return ScriptedToolRunner


@pytest.fixture
def fake_provider_http(monkeypatch: pytest.MonkeyPatch) -> Callable[[ProviderResponder], list[dict[str, Any]]]:
    # Replaces the single-attempt HTTP send, so every provider client an agent builds from a key stays offline.
    def install(responder: ProviderResponder) -> list[dict[str, Any]]:
        sends: list[dict[str, Any]] = []

        async def fake_send(self: HttpTransport, client: object, **kwargs: Any) -> HttpResponse:
            sends.append(kwargs)
            status, body = responder(kwargs)
            return HttpResponse(status_code=status, body=json.dumps(dict(body)), headers={})

        monkeypatch.setattr(HttpTransport, "_send_once", fake_send)
        return sends

    return install
