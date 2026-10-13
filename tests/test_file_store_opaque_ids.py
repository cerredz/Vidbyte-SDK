"""FILE: tests/test_file_store_opaque_ids.py

PURPOSE: Regression tests proving FileSessionStore treats session and checkpoint ids as opaque, exact names.
ROLE IN CODEBASE: Guards against glob injection and path traversal through ids that reach the store from public APIs.
ARCHITECTURE NOTE: Compares FileSessionStore with InMemorySessionStore on the same ids in temporary directories.
COMMON MODIFICATION PATTERNS: Add a case when a new store method takes an id from callers.
KNOWN EDGE CASES: Glob metacharacters, suffix-colliding ids, "..", separators, Windows drive prefixes, and case-aliased ids.
RELATED DOCS: vidbyte/sessions/stores/file.py.
TESTS: python -m pytest -q tests/test_file_store_opaque_ids.py.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidbyte.sessions import FileSessionStore, InMemorySessionStore, Session
from vidbyte.sessions.contracts import SESSION_SCHEMA_VERSION, Checkpoint, RunState, SessionMeta, SessionStatus
from vidbyte.sessions.errors import CheckpointNotFoundError, SessionNotFoundError, SessionStoreError

PATTERN_IDS = ("*", "x*", "ck_9*", "????????*", "[a-z]*", "**")
TRAVERSAL_SESSION_IDS = ("../escape", "..", ".", "", "a/b", "a\\b", "C:", "C:escape")


def _run_state() -> RunState:
    return RunState(
        schema_version=SESSION_SCHEMA_VERSION,
        agent_name="a",
        system_prompt="s",
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
        history=(),
    )


def _checkpoint(session_id: str, cid: str, *, parent: str | None = None) -> Checkpoint:
    return Checkpoint(id=cid, session_id=session_id, parent_id=parent, seq=0, created_at="2026-06-06T00:00:00+00:00", run_state=_run_state())


class FileStoreOpaqueIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._base = Path(tempfile.mkdtemp())
        self.root = self._base / "store"
        self.file_store = FileSessionStore(str(self.root))
        self.memory_store = InMemorySessionStore()
        for store in (self.file_store, self.memory_store):
            store.put(_checkpoint("alice", "ck_9alice"))
            store.put(_checkpoint("bob", "ck_9bob"))
            store.put(_checkpoint("bob", "x-ck_9bob", parent="ck_9bob"))

    def test_pattern_checkpoint_ids_are_not_found_like_memory_store(self) -> None:  # [Silent Failure]
        for checkpoint_id in PATTERN_IDS:
            for name, store in (("file", self.file_store), ("memory", self.memory_store)):
                with self.subTest(store=name, checkpoint_id=checkpoint_id):
                    with self.assertRaises(CheckpointNotFoundError):
                        store.get(checkpoint_id)

    def test_checkpoint_id_must_match_exactly_not_as_suffix(self) -> None:  # [Silent Failure]
        self.assertEqual(self.file_store.get("ck_9bob").id, "ck_9bob")
        self.assertEqual(self.file_store.get("x-ck_9bob").id, "x-ck_9bob")
        self.file_store.put(_checkpoint("dan", "y-ck_dan"))
        with self.assertRaises(CheckpointNotFoundError):
            self.file_store.get("ck_dan")

    def test_pattern_delete_removes_nothing(self) -> None:  # [Hidden Failure]
        self.file_store._delete_checkpoint("*")
        self.assertEqual(len(list(self.root.glob("*/checkpoints/*.json"))), 3)

    def test_traversal_session_ids_read_as_not_found_and_create_nothing(self) -> None:  # [Hidden Failure]
        before = sorted(self._base.rglob("*"))
        for session_id in TRAVERSAL_SESSION_IDS:
            with self.subTest(session_id=session_id):
                self.assertIsNone(self.file_store.head(session_id))
                self.assertEqual(self.file_store.history(session_id), [])
                with self.assertRaises(SessionNotFoundError):
                    self.file_store.get_meta(session_id)
        self.assertFalse((self._base / "escape").exists())
        self.assertEqual(sorted(self._base.rglob("*")), before)

    def test_reads_of_unknown_session_create_no_directory(self) -> None:  # [Hidden Failure]
        self.assertIsNone(self.file_store.head("ghost"))
        self.assertEqual(self.file_store.history("ghost"), [])
        self.assertFalse((self.root / "ghost").exists())

    def test_writes_with_unsafe_ids_raise_store_error(self) -> None:  # [Edge Case]
        for session_id in TRAVERSAL_SESSION_IDS:
            with self.subTest(session_id=session_id), self.assertRaises(SessionStoreError):
                self.file_store.put(_checkpoint(session_id, "ck_ok"))
        with self.assertRaises(SessionStoreError):
            self.file_store.put(_checkpoint("alice", "../../escape"))
        self.assertFalse((self._base / "escape").exists())
        self.assertFalse((self._base / "escape.json").exists())

    def test_normal_operations_still_work(self) -> None:  # [Edge Case]
        store = self.file_store
        for i in range(4):
            store.put(_checkpoint("carol", f"ck_c{i}"))
        self.assertEqual(store.get("ck_c2").session_id, "carol")
        self.assertEqual(store.head("carol").id, "ck_c3")
        self.assertEqual([c.id for c in store.history("carol")], ["ck_c0", "ck_c1", "ck_c2", "ck_c3"])
        store.prune("carol", keep=2)
        remaining = [c.id for c in store.history("carol")]
        self.assertEqual(len(remaining), 2)
        self.assertIn("ck_c3", remaining)
        self.assertEqual(store.get("ck_9alice").session_id, "alice")

    def _alias_acme_directory(self) -> Path:
        # Present "Acme"'s files under the name the store uses for "acme", as a case-insensitive filesystem does.
        self.file_store.put(_checkpoint("Acme", "ck_acme"))
        alias = self.root / "acme"
        if not alias.exists():
            shutil.copytree(self.root / "Acme", alias)
        return alias

    def test_case_aliased_session_id_reads_as_not_found(self) -> None:  # [Silent Failure]
        self._alias_acme_directory()
        with self.assertRaises(SessionNotFoundError):
            self.file_store.get_meta("acme")
        self.assertEqual(self.file_store.history("acme"), [])
        self.assertIsNone(self.file_store.head("acme"))
        with self.assertRaises(SessionNotFoundError):
            Session.resume(self.file_store, "acme")
        self.assertEqual(self.file_store.get_meta("Acme").session_id, "Acme")

    def test_case_aliased_session_id_write_refuses_and_keeps_owner(self) -> None:  # [Silent Failure]
        alias = self._alias_acme_directory()
        before = (alias / "meta.json").read_bytes()
        meta = SessionMeta(session_id="acme", head_id=None, parent_session_id=None, agent_name="a", status=SessionStatus.ACTIVE, created_at="2026-06-06T00:00:00+00:00", updated_at="2026-06-06T00:00:00+00:00", tags=())
        with self.assertRaises(SessionStoreError):
            self.file_store.put_meta(meta)
        with self.assertRaises(SessionStoreError):
            self.file_store.put(_checkpoint("acme", "ck_intruder"))
        self.assertEqual((alias / "meta.json").read_bytes(), before)
        self.assertEqual([c.id for c in self.file_store.history("Acme")], ["ck_acme"])

    def test_case_swapped_checkpoint_id_misses_under_case_insensitive_glob(self) -> None:  # [Silent Failure]
        (real,) = list(self.root.glob("alice/checkpoints/*.json"))
        with mock.patch.object(type(self.root), "glob", lambda _self, _pattern: iter([real])):
            with self.assertRaises(CheckpointNotFoundError):
                self.file_store.get("CK_9ALICE")
            self.file_store._delete_checkpoint("CK_9ALICE")
        self.assertTrue(real.exists())


if __name__ == "__main__":
    unittest.main()
