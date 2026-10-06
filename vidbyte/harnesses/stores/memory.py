"""FILE: vidbyte/harnesses/stores/memory.py

PURPOSE:
    Process-local reference TrajectorySink that retains written records for
    inspection and testing. Mirrors vidbyte/sessions/stores/memory.py, which
    provides the in-memory backend for the SessionStore port.

ROLE IN CODEBASE:
    The default zero-config export target for tests and ephemeral collection. Bound
    to a Harness via sink=; receives one redacted TrajectoryRecord per run.

ARCHITECTURE NOTE:
    Implements the TrajectorySink protocol in stores/base.py. Holds records in
    emission order behind one async lock; never redacts (the collector does that
    upstream) and never mutates a written record.

PUBLIC API INVENTORY:
    InMemoryTrajectorySink; write(record); records().

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline collect/sink smoke verification; no dedicated test file was
    added under the approved no-tests workflow.
"""

from __future__ import annotations

import asyncio

from vidbyte.harnesses.contracts import TrajectoryRecord


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


__all__ = ["InMemoryTrajectorySink"]
