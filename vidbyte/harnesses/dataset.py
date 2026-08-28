"""FILE: vidbyte/harnesses/dataset.py

PURPOSE:
    Joins the three streams that make up one harness run into a single, redacted,
    self-contained TrajectoryRecord: the resolved specification, the original task
    and final output, and every tagged agent Session's durable checkpoints (model
    I/O + tool calls/results + reasoning trace). This is aggregation over data the
    Session primitives already captured — not a second capture system.

ROLE IN CODEBASE:
    Constructed by Harness.execute() at the run boundary. It reads only the
    vidbyte.sessions SessionStore (by the run's fan-in tag) and applies the single
    redaction pass before the record is handed to a TrajectorySink under consent.

ARCHITECTURE NOTE:
    The SessionStore is the operational source of truth; this collector produces a
    derived export unit and never mutates checkpoints. The run_id tag is the fan-in
    that reconstructs a whole multi-agent run from N per-agent sessions. See the
    approved harness execution-contract design document.

PUBLIC API INVENTORY:
    TrajectoryCollector(store, redactor=None) and collect(...).

WHAT NOT TO DO IN THIS FILE:
    1. Do not infer messages, rewards, labels, or train/test splits.
    2. Do not mutate sessions, checkpoints, or backend state during collection.
    3. Do not skip redaction; task/output/history all carry free-text secrets.

KNOWN EDGE CASES:
    A run with no tagged sessions yields a record with an empty agents tuple. A
    store read failure surfaces to the caller; Harness.execute() calls this inside
    a fail-open block so collection never fails the run itself.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline multi-agent collect smoke verification; no dedicated test
    file was added under the approved no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from vidbyte.harnesses.contracts import (
    HARNESS_SCHEMA_VERSION,
    HarnessSpec,
    TrajectoryRecord,
)
from vidbyte.harnesses.serialization import HarnessRedactor
from vidbyte.sessions.store import SessionStore


def _utc_now() -> str:
    # Produces a timezone-aware portable timestamp for the export record.
    return datetime.now(timezone.utc).isoformat()


class TrajectoryCollector:
    """Joins a run's tagged Session checkpoints into one redacted TrajectoryRecord."""

    def __init__(self, store: SessionStore, *, redactor: Callable[[Any], Any] | None = None) -> None:
        # Binds the operational session store and the single redaction pass.
        self._store = store
        self._redact = redactor if redactor is not None else HarnessRedactor().redact

    def collect(self, run_id: str, spec: HarnessSpec, task: Any, output: Any, status: str, *, reward: float | None = None) -> TrajectoryRecord:
        # Fans in every session tagged with run_id and inlines the full resolved spec.
        sessions = self._store.list_sessions(tag=run_id)
        agents = tuple(self._redact(self._collect_agent(meta)) for meta in sessions)
        return TrajectoryRecord(
            schema_version=HARNESS_SCHEMA_VERSION,
            run_id=run_id,
            task=self._redact(task),
            spec=self._redact(dict(spec.resolved_config)),
            agents=agents,
            output=self._redact(output),
            status=status,
            reward=reward,
            created_at=_utc_now(),
        )

    def _collect_agent(self, meta: Any) -> dict[str, Any]:
        # Renders one agent session as its ordered turns of history + reasoning trace.
        turns = [
            {
                "history": list(checkpoint.run_state.history),
                "trace_artifact": checkpoint.trace_artifact,
                "trace_events": list(checkpoint.trace_events) if checkpoint.trace_events else [],
            }
            for checkpoint in self._store.history(meta.session_id)
        ]
        return {"session_id": meta.session_id, "agent_name": meta.agent_name, "turns": turns}


__all__ = ["TrajectoryCollector"]
