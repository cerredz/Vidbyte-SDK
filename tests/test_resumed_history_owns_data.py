"""FILE: tests/test_resumed_history_owns_data.py

PURPOSE:
    Regression tests proving that a message rebuilt from a stored checkpoint owns
    its data, so editing a resumed or rewound history entry cannot rewrite a
    checkpoint that was already written.
ROLE IN CODEBASE:
    Covers SessionSerializer.message_from_dict and the Session rewind path on
    InMemorySessionStore, which hands out its stored checkpoint objects as-is.
ARCHITECTURE NOTE:
    Uses an offline fake agent shaped like the one in test_durable_sessions.py;
    no runner, provider, or network is involved.
COMMON MODIFICATION PATTERNS:
    Add a case here when a new path rebuilds agent history from a checkpoint.
KNOWN EDGE CASES:
    FileSessionStore re-parses JSON on every read, so only the in-memory store
    could show the aliasing; the tests therefore use InMemorySessionStore.
RELATED DOCS:
    vidbyte/sessions/store.py (the SessionStore contract all backends share).
TESTS:
    Run with `python -m pytest tests/test_resumed_history_owns_data.py`.
"""

from __future__ import annotations

import unittest

from vidbyte.agents.types import AgentMessage
from vidbyte.sessions import InMemorySessionStore, Session, SessionSerializer
from vidbyte.sessions.contracts import SESSION_SCHEMA_VERSION, RunState


class StructuredReplyAgent:
    """Minimal offline stand-in for the agent surface Session uses; replies carry structured data and tool calls."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.history: list[AgentMessage] = []
        self.last_reply: AgentMessage | None = None
        self._trace_option = None
        self.last_trace = None
        self._tracer = None

    async def arun(self, message, **_options):
        reply = AgentMessage(
            sender=self.name,
            recipient="orchestrator",
            content=f"reply:{message}",
            metadata={"tool_calls": [{"name": "triage"}]},
            structured={"priority": "low"},
        )
        self.history.append(reply)
        self.last_reply = reply
        return reply

    def export_state(self) -> RunState:
        serializer = SessionSerializer()
        return RunState(
            schema_version=SESSION_SCHEMA_VERSION,
            agent_name=self.name,
            system_prompt="system",
            description="d",
            capabilities=(),
            provider="openai",
            model_name="gpt-4.1",
            temperature=None,
            runtime_type="linear",
            runtime_config={},
            algorithm="default",
            metadata={},
            agent_metadata={},
            tool_names=(),
            history=tuple(serializer.message_to_dict(m) for m in self.history),
        )


class MessageFromDictOwnsDataTests(unittest.TestCase):
    def test_editing_rebuilt_message_leaves_source_dict_unchanged(self) -> None:  # [Silent Failure]
        serializer = SessionSerializer()
        message = AgentMessage(sender="a", recipient="u", content="x", metadata={"tool_calls": [{"name": "t"}]}, structured={"priority": "low"})
        data = serializer.message_to_dict(message)
        rebuilt = serializer.message_from_dict(data)
        rebuilt.structured["priority"] = "LOW"
        rebuilt.metadata["tool_calls"].append({"name": "extra"})
        self.assertEqual(data["structured"], {"priority": "low"})
        self.assertEqual(data["metadata"]["tool_calls"], [{"name": "t"}])


class RewoundHistoryOwnsDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_editing_rewound_entry_does_not_rewrite_in_memory_checkpoint(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        agent = StructuredReplyAgent()
        session = Session(agent, store=store)
        await session.arun("one")
        first = session.head
        await session.arun("two")
        # Rewind, then edit the rebuilt entry in place the way application code would.
        session.rewind(to=first)
        entry = agent.history[-1]
        entry.structured["priority"] = "LOW"
        entry.metadata["tool_calls"].append({"name": "extra"})
        stored = store.get(first).run_state.history[-1]
        self.assertEqual(stored["structured"], {"priority": "low"})
        self.assertEqual(stored["metadata"]["tool_calls"], [{"name": "triage"}])
        # A second rewind to the same checkpoint must return what it recorded.
        session.rewind(to=first)
        self.assertEqual(agent.history[-1].structured, {"priority": "low"})
        self.assertEqual(agent.history[-1].metadata["tool_calls"], [{"name": "triage"}])


if __name__ == "__main__":
    unittest.main()
