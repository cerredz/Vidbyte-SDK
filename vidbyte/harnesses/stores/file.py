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
    multi-process appends to the same file are not guaranteed and are unsupported.

PUBLIC API INVENTORY:
    FileTrajectorySink; path; write(record).

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline collect/sink smoke verification; no dedicated test file was
    added under the approved no-tests workflow.
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import asdict
from pathlib import Path

from vidbyte.harnesses.contracts import TrajectoryRecord
from vidbyte.harnesses.errors import HarnessSinkError


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
        try:
            line = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise HarnessSinkError("Trajectory record could not be encoded as JSON.", details={"run_id": record.run_id, "error_type": type(exc).__name__}) from exc
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line + "\n")
        except OSError as exc:
            raise HarnessSinkError("Trajectory record could not be written to its destination.", details={"destination": self._path.name, "error_type": type(exc).__name__}) from exc


__all__ = ["FileTrajectorySink"]
