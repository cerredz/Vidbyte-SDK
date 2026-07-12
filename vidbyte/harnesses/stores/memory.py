"""FILE: vidbyte/harnesses/stores/memory.py

PURPOSE:
    Implements the default ephemeral HarnessStore using process-local mappings.
    It gives every HarnessClient a canonical run ledger without creating files,
    opening databases, or requiring external services.

ROLE IN CODEBASE:
    Constructed by HarnessClient by default and through memory_store(). It
    subclasses BaseHarnessStore, which owns all collision, transition, ordering,
    filtering, and concurrency invariants.

ARCHITECTURE NOTE:
    This is the zero-config reference backend, not a durability guarantee. Data
    disappears with the process and must be exported or stored elsewhere when
    retention matters.

PUBLIC API INVENTORY:
    InMemoryHarnessStore() implementing every HarnessStore operation through the
    inherited public surface.

COMMON MODIFICATION PATTERNS:
    Change raw collection behavior only when the public BaseHarnessStore contract
    changes, then update file.py and the folder README in the same operation.

WHAT NOT TO DO IN THIS FILE:
    1. Do not duplicate shared validation from BaseHarnessStore.
    2. Do not write files or open databases.
    3. Do not return mutable internal event lists directly.

KNOWN EDGE CASES:
    Records are retained for the lifetime of this store instance with no pruning.
    Frozen dataclasses contain mapping values that callers should treat as immutable.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline success/failure/event/query smoke verification; no dedicated
    test file was added under the approved no-tests workflow.

CONCURRENCY MODEL:
    Inherits the per-instance asyncio operation lock from BaseHarnessStore.
"""

from __future__ import annotations

from vidbyte.harnesses.contracts import HarnessEvent, HarnessRun, HarnessSpec
from vidbyte.harnesses.store import BaseHarnessStore


class InMemoryHarnessStore(BaseHarnessStore):
    """Process-local harness store backed by dictionaries and event lists."""

    def __init__(self) -> None:
        # Initializes empty record maps and the inherited atomic operation lock.
        super().__init__()
        self._specs: dict[str, HarnessSpec] = {}
        self._runs: dict[str, HarnessRun] = {}
        self._run_events: dict[str, list[HarnessEvent]] = {}

    async def _write_spec(self, spec: HarnessSpec) -> None:
        # Stores one specification by its deterministic identifier.
        self._specs[spec.spec_id] = spec

    async def _read_spec(self, spec_id: str) -> HarnessSpec | None:
        # Returns one specification or None without applying lookup policy.
        return self._specs.get(spec_id)

    async def _write_run(self, run: HarnessRun) -> None:
        # Stores one running or terminal snapshot by its unique run id.
        self._runs[run.run_id] = run
        self._run_events.setdefault(run.run_id, [])

    async def _read_run(self, run_id: str) -> HarnessRun | None:
        # Returns one run snapshot or None without applying lookup policy.
        return self._runs.get(run_id)

    async def _read_all_runs(self) -> list[HarnessRun]:
        # Returns a detached list of every current run snapshot.
        return list(self._runs.values())

    async def _write_event(self, event: HarnessEvent) -> None:
        # Appends one already-validated event to its run-local list.
        self._run_events.setdefault(event.run_id, []).append(event)

    async def _read_events(self, run_id: str) -> list[HarnessEvent]:
        # Returns a detached list so callers cannot mutate internal event state.
        return list(self._run_events.get(run_id, ()))


__all__ = ["InMemoryHarnessStore"]
