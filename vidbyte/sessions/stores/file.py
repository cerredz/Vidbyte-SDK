"""Context Protocol Header

Description:
    Filesystem implementation of the session store with atomic writes.
Purpose:
    Persists sessions as inspectable JSON: one directory per session containing a
    meta file and per-checkpoint files, written atomically via temp + os.replace.
Architecture:
    - FileSessionStore: BaseSessionStore backed by a directory tree.
Relations:
    Implements vidbyte.sessions.store.BaseSessionStore; uses SessionSerializer.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from vidbyte.lib.dataclasses.sessions import Checkpoint, SessionMeta
from vidbyte.lib.errors import SessionStoreError
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.store import BaseSessionStore


class FileSessionStore(BaseSessionStore):
    """Durable session store writing JSON files under a root directory."""

    def __init__(self, root: str, *, serializer: SessionSerializer | None = None) -> None:
        # Bind the root directory and serializer used for all reads and writes.
        self._root = Path(root)
        self._serializer = serializer or SessionSerializer()

    def _write_checkpoint(self, checkpoint: Checkpoint) -> None:
        # Atomically write a checkpoint file inside its session's checkpoints dir.
        target = self._checkpoint_dir(checkpoint.session_id) / f"{checkpoint.seq:08d}-{checkpoint.id}.json"
        self._atomic_write_json(target, self._serializer.checkpoint_to_dict(checkpoint))

    def _read_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        # Find and parse a checkpoint by id across all sessions.
        for path in self._root.glob(f"*/checkpoints/*-{checkpoint_id}.json"):
            return self._serializer.checkpoint_from_dict(self._read_json(path))
        return None

    def _read_session_checkpoints(self, session_id: str) -> list[Checkpoint]:
        # Parse every checkpoint file for a session.
        directory = self._checkpoint_dir(session_id)
        if not directory.exists():
            return []
        return [self._serializer.checkpoint_from_dict(self._read_json(path)) for path in directory.glob("*.json")]

    def _delete_checkpoint(self, checkpoint_id: str) -> None:
        # Remove a checkpoint file by id if present.
        for path in self._root.glob(f"*/checkpoints/*-{checkpoint_id}.json"):
            path.unlink(missing_ok=True)

    def _write_meta(self, meta: SessionMeta) -> None:
        # Atomically write the session meta file.
        self._atomic_write_json(self._session_dir(meta.session_id) / "meta.json", self._serializer.meta_to_dict(meta))

    def _read_meta(self, session_id: str) -> SessionMeta | None:
        # Parse a session's meta file, or None when absent.
        path = self._session_dir(session_id) / "meta.json"
        if not path.exists():
            return None
        return self._serializer.meta_from_dict(self._read_json(path))

    def _read_all_meta(self) -> list[SessionMeta]:
        # Parse every session meta file under the root.
        if not self._root.exists():
            return []
        return [self._serializer.meta_from_dict(self._read_json(path)) for path in self._root.glob("*/meta.json")]

    def _session_dir(self, session_id: str) -> Path:
        # Return (creating) the directory for a single session.
        directory = self._root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _checkpoint_dir(self, session_id: str) -> Path:
        # Return (creating) the checkpoints directory for a session.
        directory = self._session_dir(session_id) / "checkpoints"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _atomic_write_json(self, target: Path, payload: dict) -> None:
        # Write JSON to a temp file in the same dir, then atomically replace the target.
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(tmp_path, target)
        except Exception as exc:
            Path(tmp_path).unlink(missing_ok=True)
            raise SessionStoreError(f"Failed to write session file: {target.name}.", details={"path": str(target)}) from exc

    @staticmethod
    def _read_json(path: Path) -> dict:
        # Read and parse a JSON file, wrapping corruption in SessionStoreError.
        try:
            with path.open("r", encoding="utf-8") as stream:
                return json.load(stream)
        except (OSError, ValueError) as exc:
            raise SessionStoreError(f"Failed to read session file: {path.name}.", details={"path": str(path)}) from exc


__all__ = ["FileSessionStore"]
