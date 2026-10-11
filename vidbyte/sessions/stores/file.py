"""Context Protocol Header

Description:
    Filesystem implementation of the session store with atomic writes.
Purpose:
    Persists sessions as inspectable JSON: one directory per session containing a
    meta file and per-checkpoint files, written atomically via temp + os.replace.
Architecture:
    - FileSessionStore: BaseSessionStore backed by a directory tree. Session and
      checkpoint ids are opaque, exact-match names confined to one path segment
      under the root; reads never create directories.
Relations:
    Implements vidbyte.sessions.store.BaseSessionStore; uses SessionSerializer.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile
from pathlib import Path, PureWindowsPath

from vidbyte.sessions.contracts import Checkpoint, SessionMeta
from vidbyte.sessions.errors import SessionStoreError
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.store import BaseSessionStore


class FileSessionStore(BaseSessionStore):
    """Durable session store writing JSON files under a root directory."""

    def __init__(self, root: str, *, serializer: SessionSerializer | None = None) -> None:
        # Bind the root directory and serializer used for all reads and writes.
        self._root = Path(root)
        self._serializer = serializer or SessionSerializer()

    def _write_checkpoint(self, checkpoint: Checkpoint) -> None:
        # @intent file-store-ids-are-opaque-and-rooted
        # A checkpoint id becomes part of a file name, so reject one that is not a plain name before writing.
        directory = self._checkpoint_dir(checkpoint.session_id)
        if directory is None or not _is_plain_segment(checkpoint.id):
            raise SessionStoreError(
                f"Invalid session or checkpoint id for file store: {checkpoint.session_id!r} / {checkpoint.id!r}.",
                details={"session_id": checkpoint.session_id, "checkpoint_id": checkpoint.id},
            )
        target = directory / f"{checkpoint.seq:08d}-{checkpoint.id}.json"
        self._atomic_write_json(target, self._serializer.checkpoint_to_dict(checkpoint))

    def _read_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        # @intent file-store-ids-are-opaque-and-rooted
        # Ids often come from client requests; a pattern-like id must miss, not match another session's checkpoint.
        for path in self._checkpoint_paths(checkpoint_id):
            return self._serializer.checkpoint_from_dict(self._read_json(path))
        return None

    def _read_session_checkpoints(self, session_id: str) -> list[Checkpoint]:
        # Parse every checkpoint file for a session.
        directory = self._checkpoint_dir(session_id)
        if directory is None or not directory.exists():
            return []
        return [self._serializer.checkpoint_from_dict(self._read_json(path)) for path in directory.glob("*.json")]

    def _delete_checkpoint(self, checkpoint_id: str) -> None:
        # @intent file-store-ids-are-opaque-and-rooted
        # Delete only the file whose id matches exactly; a pattern-like id must never delete other checkpoints.
        for path in self._checkpoint_paths(checkpoint_id):
            path.unlink(missing_ok=True)

    def _checkpoint_paths(self, checkpoint_id: str) -> list[Path]:
        # @intent file-store-ids-are-opaque-and-rooted
        # Escape the id for glob, then keep only files named exactly <seq>-<checkpoint_id>.json, so an id
        # that is a suffix of another id ("b" vs "a-b") does not match it.
        if not _is_plain_segment(checkpoint_id):
            return []
        suffix = f"-{checkpoint_id}.json"
        matches = self._root.glob(f"*/checkpoints/*{glob.escape(suffix)}")
        return [path for path in matches if path.name[: -len(suffix)].lstrip("-").isdigit()]

    def _write_meta(self, meta: SessionMeta) -> None:
        # Atomically write the session meta file.
        directory = self._session_dir(meta.session_id)
        if directory is None:
            raise SessionStoreError(f"Invalid session id for file store: {meta.session_id!r}.", details={"session_id": meta.session_id})
        self._atomic_write_json(directory / "meta.json", self._serializer.meta_to_dict(meta))

    def _read_meta(self, session_id: str) -> SessionMeta | None:
        # Parse a session's meta file, or None when absent or the id is not a valid session name.
        directory = self._session_dir(session_id)
        if directory is None or not (directory / "meta.json").exists():
            return None
        return self._serializer.meta_from_dict(self._read_json(directory / "meta.json"))

    def _read_all_meta(self) -> list[SessionMeta]:
        # Parse every session meta file under the root.
        if not self._root.exists():
            return []
        return [self._serializer.meta_from_dict(self._read_json(path)) for path in self._root.glob("*/meta.json")]

    def _session_dir(self, session_id: str) -> Path | None:
        # @intent file-store-ids-are-opaque-and-rooted
        # Map a session id to its directory without creating it, or None when the id would leave the root.
        return self._root / session_id if _is_plain_segment(session_id) else None

    def _checkpoint_dir(self, session_id: str) -> Path | None:
        # Map a session id to its checkpoints directory without creating it, or None for an invalid id.
        return self._root / session_id / "checkpoints" if _is_plain_segment(session_id) else None

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


def _is_plain_segment(value: object) -> bool:
    # True when value is one plain file name: no separators, drive, NUL, "." or "..", so root / value stays under root.
    if not isinstance(value, str) or value in ("", ".", "..") or any(char in value for char in ("/", "\\", "\x00")):
        return False
    return not PureWindowsPath(value).drive


__all__ = ["FileSessionStore"]
