"""FILE: tests/test_run_state_snapshot_owns_data.py

PURPOSE:
    Regression tests proving BaseAgent.export_state() hands back a RunState that
    owns its nested metadata and mapping output_schema, and BaseAgent.restore()
    hands a restored agent its own copy, so editing either live agent in place
    cannot rewrite a checkpoint that was already written.
ROLE IN CODEBASE:
    Covers BaseAgent.export_state, BaseAgent._export_output_schema and
    BaseAgent.restore, plus the InMemorySessionStore path that keeps the
    exported RunState object as written.
ARCHITECTURE NOTE:
    Builds agents offline with the shared test runner fixture and never runs a
    model turn, so no provider network call is made.
COMMON MODIFICATION PATTERNS:
    Add a case here when another mutable agent field joins the RunState snapshot.
KNOWN EDGE CASES:
    Only nested values leak without a deep copy; top-level metadata keys were
    already protected by the shallow dict() copy. FileSessionStore serializes on
    write, so only the in-memory backend exposed the shared objects.
RELATED DOCS:
    vidbyte/sessions/store.py (the interchangeable-backend contract)
TESTS:
    python -m pytest -q tests/test_run_state_snapshot_owns_data.py
"""

from __future__ import annotations

import unittest

from tests.agent_test_support import build_test_agent
from vidbyte.agents.base import BaseAgent
from vidbyte.sessions import InMemorySessionStore, Session
from vidbyte.sessions.contracts import CheckpointPolicy


class _IdleRunner:
    """Runner stand-in that fails loudly if a test ever reaches the model."""

    def run(self, prompt: str, **_kwargs: object) -> object:
        raise AssertionError("these tests never run a model turn")


def _ticket_schema() -> dict:
    return {
        "type": "object",
        "properties": {"title": {"type": "string"}, "priority": {"type": "string"}},
        "required": ["title", "priority"],
    }


def _support_agent() -> BaseAgent:
    return build_test_agent(
        name="support",
        system_prompt="Triage tickets.",
        runner=_IdleRunner(),
        metadata={"team": "support", "tags": ["tier1"]},
        output_schema=_ticket_schema(),
    )


def _edit_live_agent(agent: BaseAgent) -> None:
    # Ordinary between-turn updates an application makes to the agent it keeps using.
    agent.metadata["tags"].append("vip")
    agent.output_schema["properties"]["sla_hours"] = {"type": "integer"}
    agent.output_schema["required"].append("sla_hours")


class RunStateSnapshotOwnsDataTests(unittest.TestCase):
    def test_export_state_does_not_share_nested_metadata_or_schema(self) -> None:  # [Silent Failure]
        agent = _support_agent()
        state = agent.export_state()

        _edit_live_agent(agent)

        self.assertEqual(state.metadata, {"team": "support", "tags": ["tier1"]})
        self.assertEqual(state.output_schema, {"kind": "mapping", "schema": _ticket_schema()})

    def test_in_memory_checkpoint_survives_live_agent_edits(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        agent = _support_agent()
        session = Session(agent, store=store, policy=CheckpointPolicy.MANUAL)
        checkpoint_id = session.checkpoint(label="before-edit")

        _edit_live_agent(agent)

        stored = store.get(checkpoint_id).run_state
        self.assertEqual(stored.metadata["tags"], ["tier1"])
        self.assertEqual(stored.output_schema["schema"], _ticket_schema())

        restored = BaseAgent.restore(stored)
        self.assertEqual(restored.metadata, {"team": "support", "tags": ["tier1"]})
        self.assertEqual(restored.output_schema, _ticket_schema())

        forked = Session.fork_from(store, checkpoint_id).agent
        self.assertEqual(forked.metadata["tags"], ["tier1"])
        self.assertEqual(forked.output_schema["required"], ["title", "priority"])

    def test_editing_a_restored_agent_leaves_its_checkpoint_intact(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        session = Session(_support_agent(), store=store, policy=CheckpointPolicy.MANUAL)
        checkpoint_id = session.checkpoint(label="original")

        restored = BaseAgent.restore(store.get(checkpoint_id).run_state)
        _edit_live_agent(restored)
        resumed = Session.resume(store, session.id, checkpoint_id=checkpoint_id).agent
        resumed.metadata["tags"].append("escalated")

        stored = store.get(checkpoint_id).run_state
        self.assertEqual(stored.metadata, {"team": "support", "tags": ["tier1"]})
        self.assertEqual(stored.output_schema["schema"], _ticket_schema())


if __name__ == "__main__":
    unittest.main()
