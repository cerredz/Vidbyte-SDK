from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest import mock

from vidbyte import Agent
from vidbyte.agents.types import AgentMessage
from vidbyte.sessions.contracts import (
    SESSION_SCHEMA_VERSION,
    Checkpoint,
    CheckpointPolicy,
    RunState,
    SessionMeta,
    SessionStatus,
    TraceCapture,
)
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.sessions.errors import (
    CheckpointNotFoundError,
    SessionError,
    SessionNotFoundError,
    SessionStoreError,
    SessionVersionError,
)
from vidbyte.sessions import (
    FileSessionStore,
    InMemorySessionStore,
    Session,
    SessionClient,
    SessionScope,
    SessionSerializer,
    TraceRecorder,
    export_session,
    import_session,
)
from vidbyte.tools.builtins.sessions import SessionTool
from vidbyte.tools.types import ToolCall


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class FakeAgent:
    """Minimal stand-in implementing the surface Session uses."""

    def __init__(self, name: str = "fake", trace: dict | None = None) -> None:
        self.name = name
        self.history: list[AgentMessage] = []
        self.last_reply: AgentMessage | None = None
        self._trace_option = None
        self.last_trace = None
        self._tracer = None
        self._turn = 0
        self._trace = trace

    async def arun(self, message, **_options):
        self._turn += 1
        metadata = {"trace": self._trace, "trace_metadata": {"update_count": self._turn}} if self._trace is not None else {}
        reply = AgentMessage(sender=self.name, recipient="orchestrator", content=f"reply-{self._turn}:{message}", metadata=metadata)
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
            modality="text",
            temperature=None,
            runner_options={},
            runtime_type="linear",
            runtime_config={},
            algorithm="default",
            metadata={},
            agent_metadata={},
            tool_names=(),
            history=tuple(serializer.message_to_dict(m) for m in self.history),
        )


def _fc(name: str, arguments: str, call_id: str) -> dict:
    return {"output": [{"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}]}


class _Resp:
    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


class EchoRunner:
    """Scripted runner that finishes each run with an incrementing final answer."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, prompt: str, **_kwargs: object) -> _Resp:
        self.calls += 1
        return _Resp(_fc("isDone", '{"final_answer": "answer-%d"}' % self.calls, "c%d" % self.calls))


def _run_state(name: str = "a", history: tuple = ()) -> RunState:
    return RunState(
        schema_version=SESSION_SCHEMA_VERSION,
        agent_name=name,
        system_prompt="s",
        description="d",
        capabilities=(),
        provider="openai",
        model_name="gpt-4.1",
        modality="text",
        temperature=None,
        runner_options={},
        runtime_type="linear",
        runtime_config={},
        algorithm="default",
        metadata={},
        agent_metadata={},
        tool_names=(),
        history=history,
    )


def _checkpoint(session_id: str, cid: str, *, parent: str | None = None, seq: int = 0) -> Checkpoint:
    return Checkpoint(id=cid, session_id=session_id, parent_id=parent, seq=seq, created_at="2026-06-06T00:00:00+00:00", run_state=_run_state())


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
class SerializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s = SessionSerializer()

    def test_round_trips_empty_history(self) -> None:  # [Edge Case]
        cp = _checkpoint("se1", "ck1")
        back = self.s.checkpoint_from_dict(self.s.checkpoint_to_dict(cp))
        self.assertEqual(back.id, "ck1")
        self.assertEqual(back.run_state.history, ())

    def test_round_trips_one_and_many_messages(self) -> None:  # [Edge Case]
        for count in (1, 4):
            messages = tuple({"sender": "a", "recipient": "o", "content": str(i), "message_type": "response", "metadata": {}} for i in range(count))
            cp = Checkpoint(id="ck", session_id="se1", parent_id=None, seq=count, created_at="t", run_state=_run_state(history=messages))
            back = self.s.checkpoint_from_dict(self.s.checkpoint_to_dict(cp))
            self.assertEqual(len(back.run_state.history), count)

    def test_strips_api_key_from_runner_options(self) -> None:  # [Hidden Assumption]
        state = RunState(
            schema_version=1, agent_name="a", system_prompt="s", description="d", capabilities=(), provider="openai",
            model_name="m", modality="text", temperature=None, runner_options={"api_key": "secret", "keep": 1},
            runtime_type="linear", runtime_config={}, algorithm="default", metadata={}, agent_metadata={}, tool_names=(), history=())
        cp = Checkpoint(id="ck", session_id="se", parent_id=None, seq=0, created_at="t", run_state=state)
        text = json.dumps(self.s.checkpoint_to_dict(cp))
        self.assertNotIn("api_key", text)
        self.assertIn("keep", text)

    def test_drops_credential_metadata_keys(self) -> None:  # [Silent Failure]
        message = AgentMessage(sender="a", recipient="o", content="c", metadata={"auth_token": "x", "ok": 1})
        out = self.s.message_to_dict(message)
        self.assertNotIn("auth_token", out["metadata"])
        self.assertEqual(out["metadata"]["ok"], 1)

    def test_marks_non_json_metadata_without_raising(self) -> None:  # [Hidden Failure]
        message = AgentMessage(sender="a", recipient="o", content="c", metadata={"obj": object()})
        out = self.s.message_to_dict(message)
        self.assertIn("__dropped__", out["metadata"]["obj"])

    def test_whitelists_trace_keys(self) -> None:  # [Silent Failure]
        message = AgentMessage(sender="a", recipient="o", content="c", metadata={"trace": {"k": 1}, "trace_metadata": {"n": 2}})
        out = self.s.message_to_dict(message)
        self.assertEqual(out["metadata"]["trace"], {"k": 1})
        self.assertEqual(out["metadata"]["trace_metadata"], {"n": 2})

    def test_raises_on_unknown_schema_version(self) -> None:  # [Hidden Assumption]
        cp = self.s.checkpoint_to_dict(_checkpoint("se", "ck"))
        cp["schema_version"] = 999
        with self.assertRaises(SessionVersionError):
            self.s.checkpoint_from_dict(cp)

    def test_raises_on_missing_required_field(self) -> None:  # [Hidden Failure]
        from vidbyte.sessions.errors import SessionSerializationError
        with self.assertRaises(SessionSerializationError):
            self.s.checkpoint_from_dict({"schema_version": SESSION_SCHEMA_VERSION})


# ---------------------------------------------------------------------------
# Agent state seam
# ---------------------------------------------------------------------------
class AgentStateSeamTests(unittest.TestCase):
    def test_export_captures_config_and_omits_secret(self) -> None:  # [Hidden Assumption]
        agent = Agent(name="x", system_prompt="sp", provider="openai", model_name="gpt-4.1", api_key="supersecret")
        state = agent.export_state()
        self.assertEqual(state.provider, "openai")
        self.assertEqual(state.model_name, "gpt-4.1")
        cp = Checkpoint(id="c", session_id="s", parent_id=None, seq=0, created_at="t", run_state=state)
        self.assertNotIn("supersecret", json.dumps(SessionSerializer().checkpoint_to_dict(cp)))

    def test_restore_reproduces_prompt_runtime_history(self) -> None:  # [Silent Failure]
        agent = Agent(name="x", system_prompt="sp", provider="openai", model_name="gpt-4.1")
        agent.history.append(AgentMessage(sender="x", recipient="o", content="hello", metadata={}))
        restored = Agent.restore(agent.export_state())
        self.assertEqual(restored.system_prompt, "sp")
        self.assertEqual(restored.runtime_type.value, "linear")
        self.assertEqual(restored.history[0].content, "hello")

    def test_restore_records_tool_mismatch(self) -> None:  # [Hidden Assumption]
        state = RunState(
            schema_version=1, agent_name="x", system_prompt="s", description="d", capabilities=(), provider="openai",
            model_name="m", modality="text", temperature=None, runner_options={}, runtime_type="linear", runtime_config={},
            algorithm="default", metadata={}, agent_metadata={}, tool_names=("grep",), history=())
        restored = Agent.restore(state)
        self.assertIn("__resume_tool_mismatch__", restored.metadata)


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------
class InMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemorySessionStore()

    def test_get_unknown_checkpoint_raises(self) -> None:  # [Edge Case]
        with self.assertRaises(CheckpointNotFoundError):
            self.store.get("nope")

    def test_head_returns_latest_by_seq(self) -> None:  # [Silent Failure]
        self.store.put(_checkpoint("se", "c1"))
        self.store.put(_checkpoint("se", "c2"))
        self.assertEqual(self.store.head("se").seq, 1)

    def test_list_sessions_filters(self) -> None:  # [Silent Failure]
        self.store.put(_checkpoint("se", "c1"))
        self.assertEqual(len(self.store.list_sessions(agent_name="a")), 1)
        self.assertEqual(len(self.store.list_sessions(agent_name="missing")), 0)

    def test_seq_is_monotonic(self) -> None:  # [Hidden Failure]
        for i in range(5):
            self.store.put(_checkpoint("se", f"c{i}"))
        self.assertEqual([c.seq for c in self.store.history("se")], [0, 1, 2, 3, 4])


class FileStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp()
        self.store = FileSessionStore(self._dir)

    def test_put_get_round_trip(self) -> None:  # [Edge Case]
        stored = self.store.put(_checkpoint("se", "c1"))
        self.assertEqual(self.store.get(stored.id).id, "c1")

    def test_corrupt_file_raises_session_store_error(self) -> None:  # [Hidden Failure]
        self.store.put(_checkpoint("se", "c1"))
        (Path(self._dir) / "se" / "meta.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(SessionStoreError):
            self.store.get_meta("se")

    def test_atomic_write_leaves_no_tmp_and_no_target_on_failure(self) -> None:  # [Hidden Failure]
        with mock.patch("vidbyte.sessions.stores.file.json.dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(SessionStoreError):
                self.store.put(_checkpoint("se", "c1"))
        leftovers = list(Path(self._dir).glob("se/checkpoints/*"))
        self.assertEqual(leftovers, [])

    def test_get_meta_missing_raises(self) -> None:  # [Edge Case]
        with self.assertRaises(SessionNotFoundError):
            self.store.get_meta("ghost")

    def test_prune_keeps_recent_and_head(self) -> None:  # [Silent Failure]
        for i in range(5):
            self.store.put(_checkpoint("se", f"c{i}"))
        head_id = self.store.head("se").id
        self.store.prune("se", keep=2)
        remaining = {c.id for c in self.store.history("se")}
        self.assertIn(head_id, remaining)
        self.assertLessEqual(len(remaining), 2)


# ---------------------------------------------------------------------------
# Portable bundles
# ---------------------------------------------------------------------------
class PortableBundleTests(unittest.IsolatedAsyncioTestCase):
    async def test_exports_manifest_meta_checkpoints_and_trace_payloads(self) -> None:  # [Silent Failure]
        # Verify the bundle shape mirrors FileSessionStore and includes trace data.
        store = InMemorySessionStore()
        session = Session(FakeAgent(trace={"goal": "g"}), store=store)
        await session.arun("one")

        bundle = export_session(store, session.id)

        with zipfile.ZipFile(BytesIO(bundle), mode="r") as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            meta = json.loads(archive.read("meta.json").decode("utf-8"))
            checkpoint_names = [name for name in archive.namelist() if name.startswith("checkpoints/")]
            checkpoint = json.loads(archive.read(checkpoint_names[0]).decode("utf-8"))
        self.assertEqual(manifest["schema_version"], SESSION_SCHEMA_VERSION)
        self.assertEqual(manifest["session_id"], session.id)
        self.assertEqual(manifest["checkpoint_count"], 1)
        self.assertEqual(meta["session_id"], session.id)
        self.assertEqual(checkpoint["checkpoint"]["trace_artifact"], {"goal": "g"})

    async def test_imports_memory_bundle_into_file_store_with_new_id_and_resumes(self) -> None:  # [Hidden Failure]
        # Verify memory-to-file import preserves DAG fields and creates a resumable session.
        source = InMemorySessionStore()
        session = Session(FakeAgent(trace={"goal": "g"}), store=source)
        await session.arun("one")
        await session.arun("two")
        original = source.history(session.id)

        with tempfile.TemporaryDirectory() as root:
            target = FileSessionStore(root)
            imported_id = import_session(target, export_session(source, session.id), new_id="se_imported")
            resumed = Session.resume(target, imported_id)
            imported = target.history(imported_id)

        self.assertEqual(imported_id, "se_imported")
        self.assertEqual(resumed.id, "se_imported")
        self.assertEqual([c.id for c in imported], [c.id for c in original])
        self.assertEqual([c.seq for c in imported], [c.seq for c in original])
        self.assertEqual(imported[-1].parent_id, original[-1].parent_id)
        self.assertEqual(imported[-1].trace_artifact, {"goal": "g"})

    async def test_imports_file_bundle_into_memory_store_with_same_id_when_absent(self) -> None:  # [Hidden Failure]
        # Verify file-to-memory import preserves the original id when no collision exists.
        with tempfile.TemporaryDirectory() as root:
            source = FileSessionStore(root)
            session = Session(FakeAgent(), store=source)
            await session.arun("one")
            imported_id = import_session(InMemorySessionStore(), export_session(source, session.id))
        self.assertEqual(imported_id, session.id)

    async def test_session_export_and_client_import_are_thin_public_surfaces(self) -> None:  # [Edge Case]
        # Verify Session and SessionClient delegate to the module-level helpers.
        source = InMemorySessionStore()
        client = SessionClient()
        session = Session(FakeAgent(), store=source)
        await session.arun("one")
        target = InMemorySessionStore()

        imported_id = client.import_(target, session.export(), new_id="se_client")

        self.assertEqual(imported_id, "se_client")
        self.assertEqual(client.export(target, imported_id), export_session(target, imported_id))

    def test_import_without_new_id_rejects_existing_session(self) -> None:  # [Hidden Assumption]
        # Verify same-id imports fail loudly rather than clobbering existing metadata.
        source = InMemorySessionStore()
        source.put(_checkpoint("se", "c1"))
        bundle = export_session(source, "se")

        with self.assertRaisesRegex(SessionStoreError, "pass new_id"):
            import_session(source, bundle)

    def test_import_uses_ingest_not_put(self) -> None:  # [Hidden Failure]
        # Verify bundle import does not call the seq-reassigning put path.
        class PutFailingStore(InMemorySessionStore):
            def put(self, checkpoint):
                # Raise if import accidentally routes through put().
                raise AssertionError("put should not be called")

        source = InMemorySessionStore()
        source.put(_checkpoint("se", "c1", seq=99))
        target = PutFailingStore()

        import_session(target, export_session(source, "se"), new_id="copy")

        self.assertEqual(target.history("copy")[0].seq, 0)

    def test_ingest_preserves_supplied_seq_parent_and_head_verbatim(self) -> None:  # [Silent Failure]
        # Verify ingest writes the exact supplied DAG fields without seq/head mutation.
        store = InMemorySessionStore()
        c1 = _checkpoint("se", "c1", seq=7)
        c2 = _checkpoint("se", "c2", parent="c1", seq=12)
        meta = SessionMeta(
            session_id="se",
            head_id="c2",
            parent_session_id="parent",
            agent_name="a",
            status=SessionStatus.ACTIVE,
            created_at="2026-06-06T00:00:00+00:00",
            updated_at="2026-06-06T00:00:00+00:00",
        )

        store.ingest(meta, [c2, c1])

        self.assertEqual([c.seq for c in store.history("se")], [7, 12])
        self.assertEqual(store.head("se").id, "c2")
        self.assertEqual(store.get("c2").parent_id, "c1")


# ---------------------------------------------------------------------------
# TraceRecorder
# ---------------------------------------------------------------------------
class TraceRecorderTests(unittest.TestCase):
    def _reply(self, trace: dict | None) -> AgentMessage:
        metadata = {"trace": trace, "trace_metadata": {"n": 1}} if trace is not None else {}
        return AgentMessage(sender="a", recipient="o", content="c", metadata=metadata)

    def test_auto_captures_when_artifact_present(self) -> None:  # [Edge Case]
        captured = TraceRecorder(TraceCapture.AUTO).capture(FakeAgent(), self._reply({"k": 1}))
        self.assertEqual(captured.artifact, {"k": 1})

    def test_auto_captures_nothing_without_trace(self) -> None:  # [Edge Case]
        captured = TraceRecorder(TraceCapture.AUTO).capture(FakeAgent(), self._reply(None))
        self.assertIsNone(captured.artifact)

    def test_off_never_captures(self) -> None:  # [Hidden Assumption]
        captured = TraceRecorder(TraceCapture.OFF).capture(FakeAgent(), self._reply({"k": 1}))
        self.assertIsNone(captured.artifact)

    def test_artifact_policy_leaves_events_none(self) -> None:  # [Silent Failure]
        captured = TraceRecorder(TraceCapture.ARTIFACT).capture(FakeAgent(), self._reply({"k": 1}))
        self.assertIsNone(captured.events)


# ---------------------------------------------------------------------------
# Session facade
# ---------------------------------------------------------------------------
class SessionFacadeTests(unittest.IsolatedAsyncioTestCase):
    def test_attach_one_line_mints_id_and_meta(self) -> None:  # [Edge Case]
        store = InMemorySessionStore()
        session = Session(FakeAgent(), store=store)
        self.assertTrue(session.id)
        self.assertEqual(store.get_meta(session.id).status, SessionStatus.ACTIVE)

    async def test_arun_writes_checkpoint_with_parent_chain(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        session = Session(FakeAgent(), store=store)
        await session.arun("one")
        first = session.head
        await session.arun("two")
        head = store.get(session.head)
        self.assertEqual(head.parent_id, first)
        self.assertEqual(head.seq, 1)

    async def test_manual_policy_defers_persistence(self) -> None:  # [Hidden Assumption]
        store = InMemorySessionStore()
        session = Session(FakeAgent(), store=store, policy=CheckpointPolicy.MANUAL)
        await session.arun("one")
        self.assertIsNone(session.head)
        cid = session.checkpoint(label="manual")
        self.assertEqual(session.head, cid)

    async def test_fork_sets_lineage_and_isolates_parent(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        session = Session(FakeAgent(), store=store)
        await session.arun("one")
        await session.arun("two")
        parent_len = len(store.history(session.id))
        branch = session.fork()
        branch_agent_reply = AgentMessage(sender="fake", recipient="o", content="branch", metadata={})
        branch._agent.history.append(branch_agent_reply)
        branch.checkpoint(label="extra")
        self.assertEqual(store.get_meta(branch.id).parent_session_id, session.id)
        self.assertEqual(len(store.history(session.id)), parent_len)
        self.assertNotEqual(branch.id, session.id)

    async def test_trace_artifact_persisted_on_checkpoint(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        session = Session(FakeAgent(trace={"goal": "g"}), store=store)
        reply = await session.arun("task")
        self.assertEqual(store.get(session.head).trace_artifact, reply.metadata["trace"])

    async def test_rewind_moves_head_and_branches(self) -> None:  # [Edge Case]
        store = InMemorySessionStore()
        session = Session(FakeAgent(), store=store)
        await session.arun("one")
        first = session.head
        await session.arun("two")
        session.rewind(to=first)
        self.assertEqual(session.head, first)
        await session.arun("three")
        self.assertEqual(store.get(session.head).parent_id, first)

    def test_rewind_to_foreign_checkpoint_raises(self) -> None:  # [Hidden Assumption]
        store = InMemorySessionStore()
        store.put(_checkpoint("other", "foreign"))
        session = Session(FakeAgent(), store=store)
        with self.assertRaises(SessionError):
            session.rewind(to="foreign")

    async def test_edit_transforms_history_into_new_checkpoint(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        session = Session(FakeAgent(), store=store)
        await session.arun("one")
        await session.arun("two")
        session.edit(lambda history: history[:-1], label="trim")
        self.assertEqual(len(store.get(session.head).run_state.history), 1)

    def test_resume_unknown_session_raises(self) -> None:  # [Edge Case]
        with self.assertRaises(SessionNotFoundError):
            Session.resume(InMemorySessionStore(), "ghost")

    async def test_persistence_failure_is_fail_open(self) -> None:  # [Hidden Failure]
        class FailingStore(InMemorySessionStore):
            def put(self, checkpoint):
                raise SessionStoreError("disk full")

        session = Session(FakeAgent(), store=FailingStore())
        reply = await session.arun("one")
        self.assertEqual(reply.content, "reply-1:one")
        self.assertIn("__session_error__", reply.metadata)


# ---------------------------------------------------------------------------
# Integration: real agent + scripted runner over a real store
# ---------------------------------------------------------------------------
class SessionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_continues_history_cold(self) -> None:  # [Hidden Failure]
        store = InMemorySessionStore()
        agent = Agent(name="worker", system_prompt="Work.", runner=EchoRunner())
        session = Session(agent, store=store)
        await session.arun("first")
        await session.arun("second")
        session_id = session.id

        resumed = Session.resume(store, session_id, runner=EchoRunner())
        self.assertEqual(len(resumed.agent.history), 2)
        reply = await resumed.arun("third")
        self.assertEqual(reply.content, "answer-1")
        self.assertEqual(len(resumed.agent.history), 3)

    async def test_file_store_parity_round_trip(self) -> None:  # [Silent Failure]
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(root)
            agent = Agent(name="worker", system_prompt="Work.", runner=EchoRunner())
            session = Session(agent, store=store)
            await session.arun("first")
            session_id = session.id
            resumed = Session.resume(store, session_id, runner=EchoRunner())
            self.assertEqual(len(resumed.agent.history), 1)


# ---------------------------------------------------------------------------
# SessionTool
# ---------------------------------------------------------------------------
class SessionToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_run_out_of_scope_is_denied_not_raised(self) -> None:  # [Hidden Assumption]
        store = InMemorySessionStore()
        store.put(_checkpoint("secret-session", "c1"))
        tool = SessionTool(store, scope=SessionScope.own_runs())
        result = await tool.execute(ToolCall(tool_name="session", arguments={"operation": "read_run", "session_id": "secret-session"}))
        self.assertEqual(result.status.value, "error")
        self.assertIn("denied", result.output.lower())

    async def test_read_run_returns_trace_artifact(self) -> None:  # [Silent Failure]
        store = InMemorySessionStore()
        cp = Checkpoint(id="c1", session_id="se", parent_id=None, seq=0, created_at="t", run_state=_run_state(), trace_artifact={"goal": "g"})
        store.put(cp)
        tool = SessionTool(store, scope=SessionScope.sessions(["se"]))
        result = await tool.execute(ToolCall(tool_name="session", arguments={"operation": "read_run", "session_id": "se"}))
        self.assertEqual(json.loads(result.output), {"goal": "g"})

    async def test_unknown_operation_is_error(self) -> None:  # [Edge Case]
        tool = SessionTool(InMemorySessionStore())
        result = await tool.execute(ToolCall(tool_name="session", arguments={"operation": "explode"}))
        self.assertEqual(result.status.value, "error")


# ---------------------------------------------------------------------------
# Provider import-safety
# ---------------------------------------------------------------------------
class ProviderImportSafetyTests(unittest.TestCase):
    def test_importing_vidbyte_does_not_pull_db_drivers(self) -> None:  # [Hidden Assumption]
        import vidbyte  # noqa: F401
        for driver in ("pymongo", "psycopg", "supabase"):
            self.assertNotIn(driver, sys.modules, f"{driver} should not be imported by the SDK core")

    def test_constructing_provider_without_driver_raises(self) -> None:  # [Hidden Failure]
        from vidbyte.lib.providers import PostgresSessionStore
        with self.assertRaises(VidbyteSdkError):
            PostgresSessionStore(dsn="postgresql://invalid:5432/none")


if __name__ == "__main__":
    unittest.main()
