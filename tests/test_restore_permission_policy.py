"""FILE: tests/test_restore_permission_policy.py

PURPOSE:
    Regression tests proving export_state()/restore() and cold Session.resume keep
    the agent's tool PermissionPolicy instead of falling back to the default.
ROLE IN CODEBASE:
    Covers the RunState.permission_policy field, its SessionSerializer round trip,
    and the pre-field checkpoint fallback described in
    docs/design/restore-permission-policy.md.
"""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from dataclasses import replace

from tests.agent_test_support import bind_test_runner, build_test_agent
from vidbyte import Agent
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.sessions import FileSessionStore, Session
from vidbyte.sessions.contracts import Checkpoint
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.tools import tool
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolPermission

SAFE_ONLY = PermissionPolicy(allowed=frozenset({ToolPermission.SAFE}))


class _Resp:
    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


class ReadThenDoneRunner:
    """Scripted runner that calls the READ tool once, then finishes."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, prompt: str, **_kwargs: object) -> _Resp:
        self.calls += 1
        if self.calls == 1:
            return _Resp({"output": [{"type": "function_call", "name": "read_file", "arguments": '{"path": "a"}', "call_id": "r1"}]})
        return _Resp({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "d1"}]})


def _read_tool(executed: list[str]) -> object:
    @tool(permission=ToolPermission.READ)
    def read_file(path: str) -> str:
        """Read a file."""
        executed.append(path)
        return "contents"

    return read_file


class RestorePermissionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_narrow_policy_survives_export_and_restore(self) -> None:  # [Silent Failure]
        executed: list[str] = []
        read_file = _read_tool(executed)
        agent = Agent(name="x", system_prompt="sp", provider="openai", model_name="gpt-4.1", tools=[read_file], permission_policy=SAFE_ONLY)

        state = agent.export_state()
        restored = Agent.restore(state, tools=[read_file])

        self.assertEqual(state.permission_policy, ("safe",))
        self.assertEqual(restored.permission_policy, SAFE_ONLY)
        bind_test_runner(restored, ReadThenDoneRunner())
        with contextlib.suppress(VidbyteSdkError):
            await restored.arun("read a")
        self.assertEqual(executed, [])

    def test_allow_all_survives_export_and_restore(self) -> None:  # [Silent Failure]
        agent = Agent(name="x", system_prompt="sp", provider="openai", model_name="gpt-4.1", permission_policy=PermissionPolicy.allow_all())

        restored = Agent.restore(agent.export_state())

        self.assertEqual(restored.permission_policy, PermissionPolicy.allow_all())

    def test_serializer_round_trips_policy(self) -> None:  # [Hidden Assumption]
        agent = Agent(name="x", system_prompt="sp", provider="openai", model_name="gpt-4.1", permission_policy=PermissionPolicy(allowed=frozenset()))
        checkpoint = Checkpoint(id="c", session_id="s", parent_id=None, seq=0, created_at="t", run_state=agent.export_state())
        serializer = SessionSerializer()

        loaded = serializer.checkpoint_from_dict(serializer.checkpoint_to_dict(checkpoint))

        self.assertEqual(loaded.run_state.permission_policy, ())
        self.assertEqual(Agent.restore(loaded.run_state).permission_policy, PermissionPolicy(allowed=frozenset()))

    def test_cold_file_store_resume_keeps_policy(self) -> None:  # [Silent Failure]
        executed: list[str] = []
        read_file = _read_tool(executed)
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(root)
            agent = build_test_agent(name="worker", system_prompt="Work.", runner=ReadThenDoneRunner(), tools=[read_file], permission_policy=SAFE_ONLY)
            session = Session(agent, store=store)
            session.checkpoint()
            resumed = Session.resume(FileSessionStore(root), session.id, tools=[read_file])

        self.assertEqual(resumed.agent.permission_policy, SAFE_ONLY)

    def test_old_state_without_policy_restores_default(self) -> None:  # [Hidden Assumption]
        agent = Agent(name="x", system_prompt="sp", provider="openai", model_name="gpt-4.1", permission_policy=PermissionPolicy.allow_all())
        agent.history.append(AgentMessage(sender="x", recipient="o", content="hi", metadata={}))
        serializer = SessionSerializer()
        checkpoint = Checkpoint(id="c", session_id="s", parent_id=None, seq=0, created_at="t", run_state=replace(agent.export_state(), permission_policy=None))
        payload = serializer.checkpoint_to_dict(checkpoint)
        del payload["checkpoint"]["run_state"]["permission_policy"]

        loaded = serializer.checkpoint_from_dict(payload)
        restored = Agent.restore(loaded.run_state)

        self.assertIsNone(loaded.run_state.permission_policy)
        self.assertEqual(restored.permission_policy, PermissionPolicy())
        self.assertEqual(restored.history[0].content, "hi")


if __name__ == "__main__":
    unittest.main()
