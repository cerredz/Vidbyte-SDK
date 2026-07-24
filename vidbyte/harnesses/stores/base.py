"""FILE: vidbyte/harnesses/stores/base.py

PURPOSE:
    Defines the TrajectorySink port: the append-only destination that receives a
    redacted, self-contained trajectory record after a harness run. This mirrors
    vidbyte/sessions/store.py, which defines the SessionStore port for the
    operational checkpoint backends in vidbyte/sessions/stores/.

ROLE IN CODEBASE:
    Harness.execute() joins a run into a TrajectoryRecord (via TrajectoryCollector)
    and, only under an explicit consent flag, hands it to the bound sink. The two
    reference backends (memory.py, file.py) implement this protocol; a future
    S3/warehouse sink implements the same protocol with zero harness changes.

ARCHITECTURE NOTE:
    A sink is deliberately NOT a SessionStore. The SessionStore is the operational
    source of truth and is typed to the agent checkpoint domain (RunState has 15
    agent-specific required fields); a sink is a write-only export target for one
    already-redacted TrajectoryRecord per run. Keeping the two ports distinct is
    what keeps the consent/redaction boundary sharp when the buyer is a frontier lab.

PUBLIC API INVENTORY:
    TrajectorySink protocol.

WHAT NOT TO DO IN THIS FILE:
    1. Do not redact here; the collector applies the single redaction pass upstream.
    2. Do not read from a sink during a run; a sink is write-only append storage.
    3. Do not couple a sink to SessionStore internals.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline collect/sink smoke verification; no dedicated test file was
    added under the approved no-tests workflow.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vidbyte.harnesses.contracts import TrajectoryRecord


@runtime_checkable
class TrajectorySink(Protocol):
    """Append-only destination for redacted, self-contained trajectory records."""

    async def write(self, record: TrajectoryRecord) -> None:
        # Durably appends one already-redacted trajectory record.
        ...


__all__ = ["TrajectorySink"]
