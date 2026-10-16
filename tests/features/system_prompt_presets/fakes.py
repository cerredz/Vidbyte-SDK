"""FILE: tests/features/system_prompt_presets/fakes.py

PURPOSE: Offline model stand-ins and a safety net for the system-prompt preset feature pack, plus the pack's own copy of the Working Principles paragraph.
ROLE IN CODEBASE: Imported by test_system_prompt_presets_units.py and test_system_prompt_presets_propagation.py; OfflineModels replaces BaseAgent._runner_for_model, so every agent the SDK builds during a test, including children nobody bound a runner to, talks to a RecordingModel.
ARCHITECTURE NOTE: The tests run under pytest and under scripts/test-working-principles-preset.py (plain unittest), so the safety net is a unittest mixin with setUp patches rather than a pytest fixture. WORKING_PRINCIPLES is typed here independently of the prompt asset, so an edited asset fails the verbatim test instead of being compared with itself.
FUNCTION INVENTORY: model_call builds one Responses-style tool call; RecordingModel replays scripted calls and records every system string; OfflineModels hands one RecordingModel per agent name; OfflineAgentTest installs OfflineModels and refuses non-loopback sockets and SDK HTTP sends for every test.
COMMON MODIFICATION PATTERNS: Script a child's tool calls with OfflineModels.script(name, ...) before the run that starts it; read what it was sent with OfflineModels.systems(name).
KNOWN EDGE CASES: A runner bound through the agent's runner cache wins over OfflineModels, as it does in production. Loopback sockets stay allowed because the Windows event loop builds its self-pipe with a loopback connect.
RELATED DOCS: docs/design/working-principles-preset.md; tests/features/system_prompt_presets/FEATURE.md.
TESTS: python scripts/test-working-principles-preset.py.
"""

from __future__ import annotations

import json
import socket
import unittest
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http.transport import HttpTransport

WORKING_PRINCIPLES = "Before starting any task, identify the outcome it serves and what should happen after it is done, and aim your work at that larger goal, not only the literal request. Approach the task the way the best professional in the relevant field would, starting from the rawest available material and using the methods and tools that field actually relies on rather than rough approximations. Hold the work to a high standard: set specific, demanding targets, and when something looks impossible, search for the path that makes it possible before reducing the goal. Question the assumptions built into the request, test them against evidence, and verify your results with something independent of your own judgment. Describe the task by what it must accomplish rather than by the artifact it produces, and use that description to identify other fields that solve the same underlying problem. Draw on those fields by applying the methods their practitioners actually use, not by imitating their roles, and combine what each contributes into a single coherent result. Complete the task you were given first, then name the larger or deeper move it opens, and take that move when it clearly serves the user's real goal. When you launch a subagent, carry these principles into its prompt in a form suited to its task: the outcome beyond its assignment, the professional methods and source material to use, the fields to draw on, and how its result will be verified."

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def model_call(name: str, arguments: Mapping[str, object], call_id: str) -> SimpleNamespace:
    """Return one model response that asks for a single tool call, with usage so metered agents accept it."""
    output = [{"type": "function_call", "name": name, "arguments": json.dumps(dict(arguments)), "call_id": call_id}]
    return SimpleNamespace(text="", raw={"output": output}, provider=ModelProvider.OPENAI, model="gpt-5.4-mini", usage={"input_tokens": 10, "output_tokens": 2})


class RecordingModel:
    """Offline model for one agent: replays its scripted tool calls, then finishes, and records every system string."""

    def __init__(self, agent_name: str, calls: Sequence[tuple[str, Mapping[str, object]]] = ()) -> None:
        self.agent_name = agent_name
        self.calls = list(calls)
        self.systems: list[str] = []

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> SimpleNamespace:
        """Record the system string the agent sent and return the next scripted call, or isDone."""
        self.systems.append(system or "")
        if self.calls:
            name, arguments = self.calls.pop(0)
            return model_call(name, arguments, f"call_{len(self.systems)}")
        return model_call("isDone", {"final_answer": f"{self.agent_name} done"}, "call_done")


class OfflineModels:
    """One RecordingModel per agent name, handed to every agent that has no runner bound."""

    def __init__(self) -> None:
        self.models: dict[str, RecordingModel] = {}
        self.scripts: dict[str, list[tuple[str, Mapping[str, object]]]] = {}

    def script(self, agent_name: str, *calls: tuple[str, Mapping[str, object]]) -> None:
        """Make the agent named `agent_name` request these tool calls before it finishes."""
        self.scripts[agent_name] = list(calls)

    def runner_for(self, agent: BaseAgent) -> tuple[object, str]:
        """Return the agent's bound runner, or the RecordingModel for its name, in place of a real provider runner."""
        bound = agent._runner_cache.get(RUNNER_TYPE_TEXT)
        if bound is not None:
            return bound, RUNNER_TYPE_TEXT
        if agent.name not in self.models:
            self.models[agent.name] = RecordingModel(agent.name, self.scripts.pop(agent.name, ()))
        return self.models[agent.name], RUNNER_TYPE_TEXT

    def systems(self, agent_name: str) -> list[str]:
        """Return every system string the agent named `agent_name` sent, or [] when it never called a model."""
        model = self.models.get(agent_name)
        return list(model.systems) if model is not None else []


class OfflineAgentTest(unittest.TestCase):
    """Mixin base: every agent gets an offline model, and any real network attempt fails the test."""

    models: OfflineModels

    def setUp(self) -> None:
        # Replace the provider runner seam, the SDK HTTP seam, and outbound sockets for the whole test.
        super().setUp()
        self.models = OfflineModels()
        models = self.models
        self._start(patch.object(BaseAgent, "_runner_for_model", new=lambda agent: models.runner_for(agent)))
        self._start(patch.object(HttpTransport, "_send_once", new=OfflineAgentTest._refuse_http))
        self._start(patch.object(socket, "create_connection", new=OfflineAgentTest._refuse_socket))
        original_connect = socket.socket.connect
        self._start(patch.object(socket.socket, "connect", new=lambda sock, address: OfflineAgentTest._loopback_only(original_connect, sock, address)))

    def _start(self, patcher: Any) -> None:
        # Starts one patch and undoes it when the test ends, even when the test fails.
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _refuse_http(*args: object, **kwargs: object) -> object:
        # The SDK's own HTTP seam: a test that reaches it would have called a paid service.
        raise AssertionError("a test tried to send a real HTTP request")

    @staticmethod
    def _refuse_socket(*args: object, **kwargs: object) -> object:
        # Raised for any outbound connection a provider client might open.
        raise AssertionError("a test tried to open a real socket")

    @staticmethod
    def _loopback_only(original: Any, sock: socket.socket, address: Any) -> object:
        # Lets the event loop's own loopback self-pipe connect and refuses everything else.
        host = address[0] if isinstance(address, tuple) and address else address
        if host not in _LOOPBACK_HOSTS:
            raise AssertionError(f"a test tried to connect to {host!r}")
        return original(sock, address)


class OfflineAsyncAgentTest(OfflineAgentTest, unittest.IsolatedAsyncioTestCase):
    """Async variant of OfflineAgentTest for tests that await agent runs."""


__all__ = ["WORKING_PRINCIPLES", "OfflineAgentTest", "OfflineAsyncAgentTest", "OfflineModels", "RecordingModel", "model_call"]
