"""FILE: vidbyte/harnesses/stores/file.py

PURPOSE:
    Implements inspectable local harness persistence using versioned JSON spec/run
    snapshots and append-only JSONL event files. Snapshot writes are atomic and
    filesystem work is moved off the caller's event loop.

ROLE IN CODEBASE:
    Constructed through HarnessClient.file_store() or directly. It subclasses
    BaseHarnessStore for shared invariants and uses HarnessSerializer for the
    backend-independent payload shape consumed by dataset export.

ARCHITECTURE NOTE:
    The layout is specs/<spec_id>.json and runs/<run_id>/{run.json,events.jsonl}.
    This is single-process local durability, not a transactional multi-process
    database. See docs/design/harness-execution-contract.md.

PUBLIC API INVENTORY:
    FileHarnessStore(root, serializer=None), implementing inherited HarnessStore
    operations. No construction-time directory or file write occurs.

COMMON MODIFICATION PATTERNS:
    Change paths or payloads only with serializer/schema/docs updates. Preserve
    atomic snapshot replacement and line-numbered corruption diagnostics.

WHAT NOT TO DO IN THIS FILE:
    1. Do not bypass HarnessSerializer or shared BaseHarnessStore validation.
    2. Do not accept arbitrary path separators in record identifiers.
    3. Do not claim cross-process event append safety.
    4. Do not delete or repair caller data implicitly.

KNOWN EDGE CASES:
    A process crash can leave a valid RUNNING snapshot. A crash during JSONL append
    can leave a corrupt final line, which reads fail closed with the line number.
    Multiple FileHarnessStore instances targeting one root are not coordinated.

COMMON ERRORS:
    HarnessStoreError for unsafe identifiers, filesystem failures, and corrupt
    JSON; HarnessSerializationError/HarnessVersionError from the shared codec.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline atomic round-trip/corruption/dataset smoke verification;
    no dedicated test file was added under the approved no-tests workflow.

CONCURRENCY MODEL:
    BaseHarnessStore serializes async operations per instance. A reentrant thread
    lock additionally protects snapshot replacement and JSONL append worker calls.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any

from vidbyte.harnesses.contracts import HarnessEvent, HarnessRun, HarnessSpec
from vidbyte.harnesses.errors import HarnessStoreError
from vidbyte.harnesses.serialization import HarnessSerializer
from vidbyte.harnesses.store import BaseHarnessStore

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


class FileHarnessStore(BaseHarnessStore):
    """Durable local harness store backed by JSON snapshots and JSONL events."""

    def __init__(self, root: str | Path, *, serializer: HarnessSerializer | None = None) -> None:
        # Binds an explicit root and codec without creating filesystem state.
        super().__init__()
        self._root = Path(root).expanduser()
        self._serializer = serializer or HarnessSerializer()
        self._file_lock = RLock()

    async def _write_spec(self, spec: HarnessSpec) -> None:
        # Atomically writes one versioned specification snapshot off the event loop.
        payload = self._serializer.spec_to_dict(spec)
        await asyncio.to_thread(self._atomic_write_payload, self._spec_path(spec.spec_id), payload)

    async def _read_spec(self, spec_id: str) -> HarnessSpec | None:
        # Reads and decodes one specification snapshot off the event loop.
        payload = await asyncio.to_thread(self._read_payload, self._spec_path(spec_id))
        return None if payload is None else self._serializer.spec_from_dict(payload)

    async def _write_run(self, run: HarnessRun) -> None:
        # Atomically writes one versioned running or terminal run snapshot.
        payload = self._serializer.run_to_dict(run)
        await asyncio.to_thread(self._atomic_write_payload, self._run_path(run.run_id), payload)

    async def _read_run(self, run_id: str) -> HarnessRun | None:
        # Reads and decodes one run snapshot off the event loop.
        payload = await asyncio.to_thread(self._read_payload, self._run_path(run_id))
        return None if payload is None else self._serializer.run_from_dict(payload)

    async def _read_all_runs(self) -> list[HarnessRun]:
        # Reads every run snapshot for shared filtering and deterministic ordering.
        payloads = await asyncio.to_thread(self._read_all_run_payloads)
        return [self._serializer.run_from_dict(payload) for payload in payloads]

    async def _write_event(self, event: HarnessEvent) -> None:
        # Appends one compact versioned JSON event line off the event loop.
        payload = self._serializer.event_to_dict(event)
        await asyncio.to_thread(self._append_event_payload, self._events_path(event.run_id), payload)

    async def _read_events(self, run_id: str) -> list[HarnessEvent]:
        # Reads and decodes every non-empty JSONL event for one run.
        payloads = await asyncio.to_thread(self._read_event_payloads, self._events_path(run_id))
        return [self._serializer.event_from_dict(payload) for payload in payloads]

    def _spec_path(self, spec_id: str) -> Path:
        # Builds the safe specification snapshot path for one identifier.
        return self._root / "specs" / f"{self._safe_identifier(spec_id, 'spec_id')}.json"

    def _run_path(self, run_id: str) -> Path:
        # Builds the safe run snapshot path for one identifier.
        safe = self._safe_identifier(run_id, "run_id")
        return self._root / "runs" / safe / "run.json"

    def _events_path(self, run_id: str) -> Path:
        # Builds the safe append-only event path for one run identifier.
        safe = self._safe_identifier(run_id, "run_id")
        return self._root / "runs" / safe / "events.jsonl"

    def _safe_identifier(self, value: str, field: str) -> str:
        # Rejects identifiers that could escape the caller-selected store root.
        if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
            raise HarnessStoreError("Harness store identifier contains unsafe path characters.", details={"field": field, "value": str(value)[:100]})
        return value

    def _atomic_write_payload(self, target: Path, payload: Mapping[str, Any]) -> None:
        # Writes one JSON snapshot to a sibling temp file and atomically replaces target.
        with self._file_lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
            temp_path = Path(temp_name)
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                os.replace(temp_path, target)
            except (OSError, TypeError, ValueError) as exc:
                temp_path.unlink(missing_ok=True)
                raise HarnessStoreError("Harness snapshot write failed.", details={"file": target.name, "operation": "atomic_replace"}) from exc

    def _read_payload(self, path: Path) -> dict[str, Any] | None:
        # Reads one JSON object or returns None when its snapshot is absent.
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HarnessStoreError("Harness snapshot read failed or contains corrupt JSON.", details={"file": path.name}) from exc
        if not isinstance(payload, dict):
            raise HarnessStoreError("Harness snapshot root must be a JSON object.", details={"file": path.name, "actual_type": type(payload).__name__})
        return payload

    def _append_event_payload(self, path: Path, payload: Mapping[str, Any]) -> None:
        # Appends one compact JSON line under the per-instance filesystem lock.
        try:
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            with self._file_lock:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line + "\n")
        except (OSError, TypeError, ValueError) as exc:
            raise HarnessStoreError("Harness event append failed.", details={"file": path.name, "operation": "append"}) from exc

    def _read_event_payloads(self, path: Path) -> list[dict[str, Any]]:
        # Parses every JSONL object and reports the exact corrupt line number.
        if not path.exists():
            return []
        payloads: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if line.strip():
                        payloads.append(self._parse_event_line(line, path.name, line_number))
        except (OSError, UnicodeError) as exc:
            raise HarnessStoreError("Harness event file could not be read.", details={"file": path.name}) from exc
        return payloads

    def _parse_event_line(self, line: str, filename: str, line_number: int) -> dict[str, Any]:
        # Parses one JSONL line and rejects non-object event envelopes.
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarnessStoreError("Harness event file contains corrupt JSON.", details={"file": filename, "line": line_number}) from exc
        if not isinstance(payload, dict):
            raise HarnessStoreError("Harness event line must be a JSON object.", details={"file": filename, "line": line_number, "actual_type": type(payload).__name__})
        return payload

    def _read_all_run_payloads(self) -> list[dict[str, Any]]:
        # Scans only canonical run snapshot paths and parses each object.
        runs_root = self._root / "runs"
        if not runs_root.exists():
            return []
        payloads: list[dict[str, Any]] = []
        for path in runs_root.glob("*/run.json"):
            payload = self._read_payload(path)
            if payload is not None:
                payloads.append(payload)
        return payloads


__all__ = ["FileHarnessStore"]
