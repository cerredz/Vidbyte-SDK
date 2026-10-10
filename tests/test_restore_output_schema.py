"""FILE: tests/test_restore_output_schema.py

PURPOSE:
    Regression tests proving export_state()/restore() and Session.resume,
    continue_ and fork_from keep a JSON-Schema mapping output_schema instead of
    silently dropping the agent's structured-output guarantee.
ROLE IN CODEBASE:
    Covers BaseAgent._restore_output_schema, its SessionSerializer round trip,
    caller override, and the older-checkpoint and type-marker fallbacks.
ARCHITECTURE NOTE:
    Uses offline scripted runners bound through tests.agent_test_support, so no
    provider network call is made.
COMMON MODIFICATION PATTERNS:
    Add a case here when another output_schema marker kind joins RunState.
KNOWN EDGE CASES:
    A type marker (Pydantic model) cannot be rebuilt and still needs re-supply;
    a missing or None field means an older checkpoint and restores no schema.
RELATED DOCS:
    docs/design/restore-mapping-output-schema.md
TESTS:
    python -m pytest -q tests/test_restore_output_schema.py
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace

from pydantic import BaseModel

from tests.agent_test_support import bind_test_runner, build_test_agent
from vidbyte import Agent
from vidbyte.agents.base import BaseAgent
from vidbyte.sessions import FileSessionStore, InMemorySessionStore, Session
from vidbyte.sessions.contracts import Checkpoint
from vidbyte.sessions.serialization import SessionSerializer

QUEUE_SCHEMA = {
    "type": "object",
    "properties": {"queue": {"type": "string", "enum": ["billing", "tech"]}},
    "required": ["queue"],
}


class _Queue(BaseModel):
    queue: str


class _Resp:
    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


class AnswerQueueRunner:
    """Scripted runner that finishes at once with a schema-valid queue answer."""

    def run(self, prompt: str, **_kwargs: object) -> _Resp:
        return _Resp({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "{\\"queue\\": \\"billing\\"}"}', "call_id": "d1"}]})


def _classifier(**options: object) -> Agent:
    return Agent(name="classify", system_prompt="Classify.", provider="openai", model_name="gpt-4.1", **options)


class RestoreOutputSchemaTests(unittest.IsolatedAsyncioTestCase):
    def test_mapping_schema_survives_export_and_restore(self) -> None:  # [Silent Failure]
        agent = _classifier(output_schema=QUEUE_SCHEMA)

        restored = BaseAgent.restore(agent.export_state())

        self.assertEqual(restored.output_schema, QUEUE_SCHEMA)
        self.assertEqual(Agent.restore(agent.export_state()).output_schema, QUEUE_SCHEMA)

    def test_restored_schema_is_a_copy_of_the_checkpoint(self) -> None:  # [Hidden Assumption]
        state = _classifier(output_schema=QUEUE_SCHEMA).export_state()

        restored = BaseAgent.restore(state)
        restored.output_schema["properties"]["queue"]["enum"].append("sales")

        self.assertEqual(state.output_schema["schema"]["properties"]["queue"]["enum"], ["billing", "tech"])

    def test_caller_supplied_schema_overrides_checkpoint(self) -> None:  # [Hidden Assumption]
        state = _classifier(output_schema=QUEUE_SCHEMA).export_state()
        override = {"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]}

        self.assertEqual(BaseAgent.restore(state, output_schema=override).output_schema, override)
        self.assertIs(BaseAgent.restore(state, output_schema=_Queue).output_schema, _Queue)

    def test_type_marker_still_requires_resupply(self) -> None:  # [Hidden Assumption]
        state = _classifier(output_schema=_Queue).export_state()

        self.assertEqual(state.output_schema, {"kind": "type", "name": "_Queue"})
        self.assertIsNone(BaseAgent.restore(state).output_schema)

    def test_older_checkpoints_restore_without_schema(self) -> None:  # [Hidden Assumption]
        agent = _classifier(output_schema=QUEUE_SCHEMA)
        serializer = SessionSerializer()
        checkpoint = Checkpoint(id="c", session_id="s", parent_id=None, seq=0, created_at="t", run_state=replace(agent.export_state(), output_schema=None))
        payload = serializer.checkpoint_to_dict(checkpoint)
        del payload["checkpoint"]["run_state"]["output_schema"]

        self.assertIsNone(BaseAgent.restore(checkpoint.run_state).output_schema)
        self.assertIsNone(BaseAgent.restore(serializer.checkpoint_from_dict(payload).run_state).output_schema)

    def test_serializer_round_trips_mapping_schema(self) -> None:  # [Silent Failure]
        agent = _classifier(output_schema=QUEUE_SCHEMA)
        checkpoint = Checkpoint(id="c", session_id="s", parent_id=None, seq=0, created_at="t", run_state=agent.export_state())
        serializer = SessionSerializer()

        loaded = serializer.checkpoint_from_dict(serializer.checkpoint_to_dict(checkpoint))

        self.assertEqual(BaseAgent.restore(loaded.run_state).output_schema, QUEUE_SCHEMA)

    def test_session_resume_continue_and_fork_keep_mapping_schema(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        session = _classifier(output_schema=QUEUE_SCHEMA).persist(store=store)
        checkpoint_id = session.checkpoint()

        self.assertEqual(Session.resume(store, session.id).agent.output_schema, QUEUE_SCHEMA)
        self.assertEqual(Session.continue_(store, session.id).agent.output_schema, QUEUE_SCHEMA)
        self.assertEqual(Session.fork_from(store, checkpoint_id).agent.output_schema, QUEUE_SCHEMA)

    async def test_cold_file_store_resume_returns_structured_reply(self) -> None:  # [Silent Failure]
        with tempfile.TemporaryDirectory() as root:
            agent = build_test_agent(name="classify", system_prompt="Classify.", runner=AnswerQueueRunner(), output_schema=QUEUE_SCHEMA)
            session = Session(agent, store=FileSessionStore(root))
            await session.arun("my card was charged twice")
            resumed = Session.resume(FileSessionStore(root), session.id)
            bind_test_runner(resumed.agent, AnswerQueueRunner())

            reply = await resumed.arun("my invoice is wrong")

        self.assertEqual(resumed.agent.output_schema, QUEUE_SCHEMA)
        self.assertEqual(reply.structured, {"queue": "billing"})


if __name__ == "__main__":
    unittest.main()
