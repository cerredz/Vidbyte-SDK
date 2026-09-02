"""FILE: vidbyte/harnesses/stores/file.py

PURPOSE:
    Durable append-only JSONL TrajectorySink writing one redacted record per line.
    Mirrors vidbyte/sessions/stores/file.py, which provides the filesystem backend
    for the SessionStore port.

ROLE IN CODEBASE:
    The inspectable, dependency-free export target for finished trajectories. Bound
    to a Harness via sink=; receives one redacted TrajectoryRecord per run.

ARCHITECTURE NOTE:
    Implements the TrajectorySink protocol in stores/base.py. Serializes off the
    event loop and appends one compact JSON object per line under a per-process
    lock, creating the parent directory lazily on first write. Concurrent
    multi-process appends to the same file are not guaranteed and are unsupported
    — see vidbyte/harnesses/stores/{s3,gcs,azure_blob}.py for cloud backends that
    sidestep this by giving every run its own object instead of one shared file.
    Encoding is shared with those backends via _sink_support.SinkEncoding so a
    serialization failure raises the same HarnessSinkPayloadError everywhere.

PUBLIC API INVENTORY:
    FileTrajectorySink; path; write(record).

COMMON MODIFICATION PATTERNS:
    Change the wire encoding or size guard in
    vidbyte/harnesses/stores/_sink_support.SinkEncoding, shared with every
    cloud sink, rather than editing the json.dumps(...) call here directly.

KNOWN EDGE CASES:
    Concurrent multi-process appends to the same file are not guaranteed and
    are unsupported — see s3.py/gcs.py/azure_blob.py for cloud backends that
    sidestep this by giving every run its own object instead of one shared,
    growing file.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md

TESTS:
    Exercised by inline collect/sink smoke verification; regression-covered by
    tests/test_cloud_trajectory_sinks.py for the shared encoding path only.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from vidbyte.harnesses.contracts import TrajectoryRecord
from vidbyte.harnesses.errors import HarnessSinkError
from vidbyte.harnesses.stores._sink_support import SinkEncoding


class FileTrajectorySink:
    """Append-only JSONL sink writing one redacted record per line off the event loop."""

    def __init__(self, path: str | Path) -> None:
        # Binds an explicit destination without writing until the first record.
        self._path = Path(path).expanduser()
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        # Returns the bound JSONL destination.
        return self._path

    async def write(self, record: TrajectoryRecord) -> None:
        # Serializes the record and appends one line without blocking the event loop.
        await asyncio.to_thread(self._append, record)

    def _append(self, record: TrajectoryRecord) -> None:
        # Encodes one compact JSON object followed by exactly one newline under a lock.
        payload = SinkEncoding.prepare_payload(record)
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(payload.decode("utf-8") + "\n")
        except OSError as exc:
            raise HarnessSinkError("Trajectory record could not be written to its destination.", details={"destination": self._path.name, "error_type": type(exc).__name__}) from exc


__all__ = ["FileTrajectorySink"]
