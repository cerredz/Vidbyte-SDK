"""FILE: vidbyte/harnesses/sinks.py

PURPOSE:
    Defines the TrajectorySink port and its zero-dependency reference sinks. A sink
    is the LICENSED, redacted, sellable export target for finished trajectories. It
    is deliberately separate from the operational vidbyte.sessions SessionStore so
    the consent/redaction boundary stays sharp when the buyer is a frontier lab.

ROLE IN CODEBASE:
    Harness.execute() joins the run into a TrajectoryRecord (via TrajectoryCollector)
    and, only under an explicit consent flag, hands it to the bound sink. A future
    WarehouseTrajectorySink / S3TrajectorySink in providers/ implements this same
    protocol with zero harness changes.

ARCHITECTURE NOTE:
    The operational source of truth is the durable SessionStore (checkpoints + full
    traces per agent turn). The sink receives only the already-redacted derivative.
    Records are never mutated after they are written. See the approved design doc.

PUBLIC API INVENTORY:
    TrajectorySink protocol; InMemoryTrajectorySink; FileTrajectorySink.

WHAT NOT TO DO IN THIS FILE:
    1. Do not redact here; the collector applies the single redaction pass upstream.
    2. Do not read from a sink during a run; a sink is write-only append storage.
    3. Do not couple a sink to SessionStore internals.

KNOWN EDGE CASES:
    FileTrajectorySink appends one JSON object per line under a per-process lock and
    creates its parent directory lazily on first write. Concurrent multi-process
    appends to the same file are not guaranteed and are documented as unsupported.

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
from typing import Protocol, runtime_checkable

from vidbyte.harnesses.contracts import TrajectoryRecord
from vidbyte.harnesses.errors import HarnessSinkError


@runtime_checkable
class TrajectorySink(Protocol):
    """Append-only destination for redacted, self-contained trajectory records."""

    async def write(self, record: TrajectoryRecord) -> None:
        # Durably appends one already-redacted trajectory record.
        ...


class InMemoryTrajectorySink:
    """Process-local sink that retains written records for inspection and testing."""

    def __init__(self) -> None:
        # Holds appended records in emission order behind one async lock.
        self._records: list[TrajectoryRecord] = []
        self._lock = asyncio.Lock()

    async def write(self, record: TrajectoryRecord) -> None:
        # Appends one record atomically with respect to concurrent writers.
        async with self._lock:
            self._records.append(record)

    def records(self) -> tuple[TrajectoryRecord, ...]:
        # Returns an immutable snapshot of written records.
        return tuple(self._records)


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


__all__ = ["FileTrajectorySink", "InMemoryTrajectorySink", "TrajectorySink"]
