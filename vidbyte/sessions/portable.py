"""Context Protocol Header

Description:
    Provides portable zip export/import for a single durable session.
Purpose:
    Lets callers move one session's metadata, checkpoint DAG, and persisted trace
    payloads between store backends without coupling to FileSessionStore internals.
Architecture:
    - SessionBundleExporter serializes public store reads into an in-memory zip.
    - SessionBundleImporter parses a zip and writes records through store.ingest().
Relations:
    Uses SessionSerializer, SESSION_SCHEMA_VERSION, and the SessionStore port.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from vidbyte.sessions.contracts import SESSION_SCHEMA_VERSION, Checkpoint, SessionMeta
from vidbyte.sessions.errors import SessionNotFoundError, SessionSerializationError, SessionStoreError, SessionVersionError
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.store import SessionStore


class SessionBundleExporter:
    """Serializes one session from any SessionStore into a portable zip bundle."""

    def __init__(self, store: SessionStore, serializer: SessionSerializer | None = None) -> None:
        # Bind the source store and serializer used for all bundle records.
        self._store = store
        self._serializer = serializer or SessionSerializer()

    def export(self, session_id: str) -> bytes:
        # Read a session through the public store API and return its zip bytes.
        meta = self._store.get_meta(session_id)
        checkpoints = self._store.history(session_id)
        manifest = self._build_manifest(meta, checkpoints)
        return self._write_bundle(manifest, meta, checkpoints)

    def _build_manifest(self, meta: SessionMeta, checkpoints: Sequence[Checkpoint]) -> dict[str, Any]:
        # Build the human-inspectable bundle manifest for this export.
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": meta.session_id,
            "checkpoint_count": len(checkpoints),
            "exported_at": _now(),
        }

    def _write_bundle(self, manifest: Mapping[str, Any], meta: SessionMeta, checkpoints: Sequence[Checkpoint]) -> bytes:
        # Write manifest, meta, and checkpoint JSON files into an in-memory zip.
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
            self._write_json(bundle, "manifest.json", dict(manifest))
            self._write_json(bundle, "meta.json", self._serializer.meta_to_dict(meta))
            for checkpoint in checkpoints:
                self._write_json(bundle, self._checkpoint_name(checkpoint), self._serializer.checkpoint_to_dict(checkpoint))
        return buffer.getvalue()

    @staticmethod
    def _write_json(bundle: zipfile.ZipFile, name: str, payload: Mapping[str, Any]) -> None:
        # Serialize a payload as formatted UTF-8 JSON inside the bundle.
        bundle.writestr(name, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    @staticmethod
    def _checkpoint_name(checkpoint: Checkpoint) -> str:
        # Return the FileSessionStore-compatible checkpoint archive path.
        return f"checkpoints/{checkpoint.seq:08d}-{checkpoint.id}.json"


class SessionBundleImporter:
    """Parses a portable zip bundle and ingests its records verbatim into a store."""

    def __init__(self, store: SessionStore, serializer: SessionSerializer | None = None) -> None:
        # Bind the target store and serializer used for every imported record.
        self._store = store
        self._serializer = serializer or SessionSerializer()

    def import_bundle(self, bundle: bytes, *, new_id: str | None = None) -> str:
        # Parse, optionally re-id, and ingest the bundle, returning the final session id.
        meta, checkpoints = self._read_bundle(bundle)
        if new_id is not None:
            meta, checkpoints = self._rewrite_session_id(meta, checkpoints, new_id)
        else:
            self._assert_session_absent(meta.session_id)
        self._store.ingest(meta, checkpoints)
        return meta.session_id

    def _read_bundle(self, bundle: bytes) -> tuple[SessionMeta, list[Checkpoint]]:
        # Open the zip archive and deserialize its meta and checkpoint records.
        try:
            with zipfile.ZipFile(io.BytesIO(bundle), mode="r") as archive:
                manifest = self._read_manifest(archive)
                meta = self._read_meta(archive)
                checkpoints = self._read_checkpoints(archive)
        except zipfile.BadZipFile as exc:
            raise SessionSerializationError("Session bundle is not a valid zip archive.", details={}) from exc
        self._assert_manifest_matches_records(manifest, meta, checkpoints)
        return meta, checkpoints

    def _read_manifest(self, archive: zipfile.ZipFile) -> Mapping[str, Any]:
        # Read and validate manifest.json from the bundle.
        manifest = self._read_json(archive, "manifest.json")
        version = self._read_manifest_int(manifest, "schema_version")
        if int(version) != SESSION_SCHEMA_VERSION:
            raise SessionVersionError(f"Unsupported session schema version: {version}.", details={"found": version, "expected": SESSION_SCHEMA_VERSION})
        return manifest

    def _read_meta(self, archive: zipfile.ZipFile) -> SessionMeta:
        # Read and deserialize meta.json from the bundle.
        return self._serializer.meta_from_dict(self._read_json(archive, "meta.json"))

    def _read_checkpoints(self, archive: zipfile.ZipFile) -> list[Checkpoint]:
        # Read all checkpoint JSON files in stable archive-name order.
        names = sorted(name for name in archive.namelist() if name.startswith("checkpoints/") and name.endswith(".json"))
        return [self._serializer.checkpoint_from_dict(self._read_json(archive, name)) for name in names]

    def _read_json(self, archive: zipfile.ZipFile, name: str) -> Mapping[str, Any]:
        # Read one JSON member and wrap missing or malformed data as session errors.
        try:
            with archive.open(name, mode="r") as stream:
                payload = json.loads(stream.read().decode("utf-8"))
        except KeyError as exc:
            raise SessionSerializationError(f"Session bundle missing required file: {name}.", details={"path": name}) from exc
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise SessionSerializationError(f"Session bundle file is not valid JSON: {name}.", details={"path": name}) from exc
        if not isinstance(payload, Mapping):
            raise SessionSerializationError(f"Session bundle file must contain a JSON object: {name}.", details={"path": name})
        return payload

    def _assert_manifest_matches_records(self, manifest: Mapping[str, Any], meta: SessionMeta, checkpoints: Sequence[Checkpoint]) -> None:
        # Check manifest counts and ids against the deserialized bundle records.
        if manifest.get("session_id") != meta.session_id:
            raise SessionSerializationError("Session bundle manifest session_id does not match meta.json.", details={"manifest_session_id": manifest.get("session_id"), "meta_session_id": meta.session_id})
        if self._read_manifest_int(manifest, "checkpoint_count") != len(checkpoints):
            raise SessionSerializationError("Session bundle checkpoint_count does not match checkpoint files.", details={"manifest_count": manifest.get("checkpoint_count"), "actual_count": len(checkpoints)})

    @staticmethod
    def _read_manifest_int(manifest: Mapping[str, Any], field: str) -> int:
        # Read an integer manifest field, raising a typed session error on malformed data.
        value = manifest.get(field)
        if value is None:
            raise SessionSerializationError(f"Session bundle manifest missing {field}.", details={"path": "manifest.json", "field": field})
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise SessionSerializationError(f"Session bundle manifest field must be an integer: {field}.", details={"path": "manifest.json", "field": field}) from exc

    @staticmethod
    def _rewrite_session_id(meta: SessionMeta, checkpoints: Sequence[Checkpoint], new_id: str) -> tuple[SessionMeta, list[Checkpoint]]:
        # Rewrite only the session_id fields, preserving checkpoint ids and links.
        return replace(meta, session_id=new_id), [replace(checkpoint, session_id=new_id) for checkpoint in checkpoints]

    def _assert_session_absent(self, session_id: str) -> None:
        # Raise before same-id import would overwrite an existing session record.
        try:
            self._store.get_meta(session_id)
        except SessionNotFoundError:
            return
        raise SessionStoreError("Session already exists; pass new_id= to import as a copy.", details={"session_id": session_id})


def _now() -> str:
    # Return the current UTC timestamp as an ISO-8601 string.
    return datetime.now(timezone.utc).isoformat()


__all__ = ["SessionBundleExporter", "SessionBundleImporter"]
