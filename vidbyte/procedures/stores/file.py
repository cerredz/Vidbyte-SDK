"""Context Protocol Header

Path: vidbyte/procedures/stores/file.py
Purpose: Persist inspectable procedure chains and outcomes as atomic JSON files.
Architecture: FileProcedureStore maps allowlisted segments below one resolved root,
holds an in-process RLock, claims a single writer process, and uses fsync/os.replace.
Exports: FileProcedureStore.
Invariants: Resolved paths never escape root; record versions are append-only and CAS
checked; outcome files are immutable and idempotent by canonical JSON.
Do not: Claim distributed transactions, multi-writer safety, or tamper resistance.
Related: vidbyte/procedures/README.md and docs/design/long-running-paradigm.md.
Tests: Existing verification and inline smoke checks only under no-tests approval.
Concurrency: One writer process per root; concurrent readers may inspect completed files.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from vidbyte.procedures.contracts import ProcedureOutcome, ProcedureRecord, ProcedureRef
from vidbyte.procedures.errors import ProcedureNotFoundError, ProcedureStoreConflictError, ProcedureStoreError, ProcedureValidationError, ProcedureVersionError
from vidbyte.procedures.serialization import ProcedureCodec, ProcedureIdentity


class FileProcedureStore:
    """Single-writer-process atomic JSON procedure store."""

    def __init__(self, root: str | Path) -> None:
        # Resolve the caller root, create store folders, and fail closed on another writer.
        self.root = Path(root).resolve()
        self._procedures_root = self.root / "procedures"
        self._outcomes_root = self.root / "outcomes"
        self._lock = RLock()
        self._writer_lock_path = self.root / ".writer.lock"
        try:
            self._procedures_root.mkdir(parents=True, exist_ok=True)
            self._outcomes_root.mkdir(parents=True, exist_ok=True)
            self._claim_writer()
        except OSError as exc:
            raise ProcedureStoreError("File procedure store could not initialize its root.", details={"root_name": self.root.name}) from exc
        atexit.register(self.close)

    def close(self) -> None:
        # Release only a lock owned by this process; stale/foreign locks remain fail-closed.
        with self._lock:
            try:
                if self._writer_lock_path.exists() and self._writer_lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                    self._writer_lock_path.unlink()
            except OSError:
                return

    def put(self, record: ProcedureRecord, *, expected_latest_version: int | None) -> None:
        # Compare the durable chain head and atomically append the next version file.
        with self._lock:
            self._assert_writer()
            chain = self.versions(record.namespace, record.procedure_id)
            actual_latest = chain[-1].version if chain else None
            if actual_latest != expected_latest_version:
                raise ProcedureStoreConflictError(
                    "Procedure chain changed before the file append could commit.",
                    details={"namespace": record.namespace, "procedure_id": record.procedure_id, "expected_latest_version": expected_latest_version, "actual_latest_version": actual_latest},
                )
            expected_version = 1 if actual_latest is None else actual_latest + 1
            if record.version != expected_version:
                raise ProcedureStoreConflictError(
                    "Procedure version is not the next immutable file version.",
                    details={"procedure_id": record.procedure_id, "expected_version": expected_version, "actual_version": record.version},
                )
            path = self._record_path(record.namespace, record.procedure_id, record.version)
            if path.exists():
                raise ProcedureStoreConflictError("Procedure version file already exists.", details={"procedure_id": record.procedure_id, "version": record.version})
            self._atomic_write_json(path, ProcedureCodec.record_to_dict(record))

    def get(self, namespace: str, procedure_id: str, version: int) -> ProcedureRecord:
        # Load exactly one audit record and wrap parse/I/O failures with safe context.
        path = self._record_path(namespace, procedure_id, version)
        if not path.is_file():
            raise ProcedureNotFoundError("Procedure audit version was not found.", details={"namespace": namespace, "procedure_id": procedure_id, "version": version})
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ProcedureVersionError("Procedure record JSON root must be an object.")
            return ProcedureCodec.record_from_dict(raw)
        except ProcedureVersionError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise ProcedureStoreError("Procedure record could not be read as valid JSON.", details={"procedure_id": procedure_id, "version": version}) from exc

    def latest(self, namespace: str, procedure_id: str) -> ProcedureRecord:
        # Return the numerically latest audit record, not the active verified record.
        chain = self.versions(namespace, procedure_id)
        if not chain:
            raise ProcedureNotFoundError("Procedure identity was not found.", details={"namespace": namespace, "procedure_id": procedure_id})
        return chain[-1]

    def versions(self, namespace: str, procedure_id: str) -> tuple[ProcedureRecord, ...]:
        # Enumerate only numeric JSON version files beneath an allowlisted identity path.
        directory = self._identity_path(namespace, procedure_id)
        if not directory.is_dir():
            return ()
        versions: list[int] = []
        for path in directory.glob("*.json"):
            if path.stem.isdigit():
                versions.append(int(path.stem))
        return tuple(self.get(namespace, procedure_id, version) for version in sorted(versions))

    def list_ids(self, namespace: str) -> tuple[str, ...]:
        # Return only allowlisted directory names under the requested namespace.
        directory = self._namespace_path(namespace)
        if not directory.is_dir():
            return ()
        ids = [path.name for path in directory.iterdir() if path.is_dir()]
        return tuple(sorted(ProcedureIdentity.validate_id(item, field_name="procedure_id") for item in ids))

    def list_latest(self, namespace: str) -> tuple[ProcedureRecord, ...]:
        # Return one latest audit record per durable identity.
        return tuple(self.latest(namespace, procedure_id) for procedure_id in self.list_ids(namespace))

    def find_by_operation(self, namespace: str, learning_operation_id: str) -> tuple[ProcedureRecord, ...]:
        # Scan inspectable chains for deterministic idempotency reconciliation.
        ProcedureIdentity.validate_id(learning_operation_id, field_name="learning_operation_id")
        matches = [record for procedure_id in self.list_ids(namespace) for record in self.versions(namespace, procedure_id) if record.learning_operation_id == learning_operation_id]
        return tuple(sorted(matches, key=lambda record: (record.procedure_id, record.version)))

    def append_outcome(self, outcome: ProcedureOutcome) -> bool:
        # Atomically create one exact-ref outcome or accept an identical replay.
        with self._lock:
            self._assert_writer()
            path = self._outcome_path(outcome)
            encoded = ProcedureCodec.outcome_to_dict(outcome)
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ProcedureStoreError("Existing procedure outcome is unreadable.", details={"outcome_id": outcome.outcome_id}) from exc
                if existing == encoded:
                    return False
                raise ProcedureStoreConflictError("Procedure outcome id was reused for different content.", details={"outcome_id": outcome.outcome_id})
            self._atomic_write_json(path, encoded)
            return True

    def outcomes(self, procedure: ProcedureRef) -> tuple[ProcedureOutcome, ...]:
        # Load outcome files only from the exact ref/fingerprint directory.
        directory = self._outcome_directory(procedure)
        if not directory.is_dir():
            return ()
        outcomes: list[ProcedureOutcome] = []
        for path in sorted(directory.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ProcedureVersionError("Procedure outcome JSON root must be an object.")
                outcomes.append(ProcedureCodec.outcome_from_dict(raw))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProcedureStoreError("Procedure outcome could not be read as valid JSON.", details={"outcome_file": path.name}) from exc
        return tuple(sorted(outcomes, key=lambda outcome: (outcome.created_at, outcome.outcome_id)))

    def store_identity(self) -> Mapping[str, Any]:
        # Fingerprint the resolved root without exposing its private absolute path.
        return {"type": "file", "schema_version": ProcedureIdentity.SCHEMA_VERSION, "root_hash": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest()}

    def _claim_writer(self) -> None:
        # @intent single-writer-procedure-files
        # Atomic record files do not make multi-record learning transactions safe across
        # processes. Claim the root for this process so CAS/version allocation cannot be
        # interleaved by an unrelated writer that only sees part of the operation.
        try:
            descriptor = os.open(self._writer_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            owner = self._writer_lock_path.read_text(encoding="utf-8").strip()
            if owner == str(os.getpid()):
                return
            raise ProcedureStoreError("File procedure store root is already claimed by another writer process.", details={"root_name": self.root.name})
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
            handle.flush()
            os.fsync(handle.fileno())

    def _assert_writer(self) -> None:
        # Detect a removed or replaced writer claim before any durable mutation.
        try:
            owner = self._writer_lock_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ProcedureStoreError("File procedure store writer claim is unavailable.", details={"root_name": self.root.name}) from exc
        if owner != str(os.getpid()):
            raise ProcedureStoreError("File procedure store writer claim changed unexpectedly.", details={"root_name": self.root.name})

    def _record_path(self, namespace: str, procedure_id: str, version: int) -> Path:
        # Resolve one numeric version path below the validated identity directory.
        if version < 1:
            raise ProcedureValidationError("Procedure version must be positive.", details={"version": version})
        return self._contained(self._identity_path(namespace, procedure_id) / f"{version}.json")

    def _namespace_path(self, namespace: str) -> Path:
        # Map an allowlisted namespace to its durable procedures directory.
        safe = ProcedureIdentity.validate_id(namespace, field_name="namespace")
        return self._contained(self._procedures_root / safe)

    def _identity_path(self, namespace: str, procedure_id: str) -> Path:
        # Map allowlisted namespace/id segments to one version-chain directory.
        safe_id = ProcedureIdentity.validate_id(procedure_id, field_name="procedure_id")
        return self._contained(self._namespace_path(namespace) / safe_id)

    def _outcome_directory(self, procedure: ProcedureRef) -> Path:
        # Separate exact versions and fingerprints so replacement outcomes never mix.
        namespace = ProcedureIdentity.validate_id(procedure.namespace, field_name="namespace")
        procedure_id = ProcedureIdentity.validate_id(procedure.procedure_id, field_name="procedure_id")
        fingerprint = ProcedureIdentity.validate_id(procedure.content_fingerprint, field_name="content_fingerprint")
        return self._contained(self._outcomes_root / namespace / procedure_id / str(procedure.version) / fingerprint)

    def _outcome_path(self, outcome: ProcedureOutcome) -> Path:
        # Resolve one immutable outcome file beneath its exact procedure directory.
        outcome_id = ProcedureIdentity.validate_id(outcome.outcome_id, field_name="outcome_id")
        return self._contained(self._outcome_directory(outcome.procedure) / f"{outcome_id}.json")

    def _contained(self, path: Path) -> Path:
        # Reject path construction that escapes the configured root before I/O.
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ProcedureStoreError("Procedure store path escaped its configured root.", details={"root_name": self.root.name}) from exc
        return resolved

    def _atomic_write_json(self, path: Path, payload: dict[str, object]) -> None:
        # Write, flush, and replace so readers see either the old head or the full new file.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ProcedureStoreError("Procedure JSON file could not commit atomically.", details={"file_name": path.name}) from exc


# Imported late only to keep the public error list visually focused above.


__all__ = ["FileProcedureStore"]
