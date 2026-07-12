"""FILE: vidbyte/harnesses/dataset.py

PURPOSE:
    Exports selected canonical harness runs as raw, loss-minimizing JSONL rows.
    Each row contains its exact specification, terminal or running run snapshot,
    and ordered event stream so downstream dataset builders can transform it.

ROLE IN CODEBASE:
    Constructed directly or through HarnessClient.export_jsonl(). It queries only
    the HarnessStore protocol and encodes records only through HarnessSerializer.

ARCHITECTURE NOTE:
    This is a raw trajectory export, not a chat, preference, or fine-tuning schema.
    Specialized datasets should be derived downstream without mutating canonical
    run evidence. See the approved harness execution-contract design document.

PUBLIC API INVENTORY:
    HarnessDatasetExporter(store, serializer=None) and async export_jsonl().

COMMON MODIFICATION PATTERNS:
    Add selection filters without changing row meaning. Add specialized exporters
    as separate modules rather than making this raw row format task-specific.

WHAT NOT TO DO IN THIS FILE:
    1. Do not infer messages, rewards, labels, or train/test splits.
    2. Do not mutate specs, runs, events, or backend state during export.
    3. Do not bypass HarnessSerializer or expose backend-native records.
    4. Do not replace the destination until every selected row is valid.

KNOWN EDGE CASES:
    Empty selections atomically create an empty file. Repeated spec IDs are read
    once per export. A source failure leaves any prior destination untouched.

COMMON ERRORS:
    HarnessDatasetExportError identifies status validation, source reads, JSON
    encoding, temporary writes, and destination replacement failures.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline memory/file round-trip and filtered JSONL smoke verification;
    no dedicated test file was added under the approved no-tests workflow.

CONCURRENCY MODEL:
    Source queries follow store semantics. Each row append runs off the event loop;
    one exporter call owns one unique temporary file and final atomic replacement.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vidbyte.harnesses.contracts import HARNESS_SCHEMA_VERSION, HarnessEvent, HarnessRun, HarnessRunStatus, HarnessSpec
from vidbyte.harnesses.errors import HarnessDatasetExportError
from vidbyte.harnesses.serialization import HarnessSerializer
from vidbyte.harnesses.store import HarnessStore


class HarnessDatasetExporter:
    """Atomic raw JSONL exporter over any conforming HarnessStore."""

    def __init__(self, store: HarnessStore, *, serializer: HarnessSerializer | None = None) -> None:
        # Binds a source store and the canonical versioned record codec.
        self._store = store
        self._serializer = serializer or HarnessSerializer()

    async def export_jsonl(self, path: str | Path, *, spec_id: str | None = None, statuses: HarnessRunStatus | str | Iterable[HarnessRunStatus | str] | None = None) -> int:
        # Streams selected canonical rows to a temp file and atomically publishes them.
        target = Path(path).expanduser()
        allowed = self._normalize_statuses(statuses)
        temp_path: Path | None = None
        try:
            temp_path = await asyncio.to_thread(self._prepare_temp, target)
            runs = await self._store.list_runs(spec_id=spec_id)
            specs: dict[str, HarnessSpec] = {}
            count = 0
            for run in runs:
                if allowed is not None and run.status not in allowed:
                    continue
                spec = specs.get(run.spec_id)
                if spec is None:
                    spec = await self._store.get_spec(run.spec_id)
                    specs[run.spec_id] = spec
                events = await self._store.events(run.run_id)
                row = self._row(spec, run, events)
                await asyncio.to_thread(self._append_row, temp_path, row)
                count += 1
            await asyncio.to_thread(self._publish, temp_path, target)
            temp_path = None
            return count
        except asyncio.CancelledError:
            if temp_path is not None:
                await asyncio.to_thread(self._discard, temp_path)
            raise
        except Exception as exc:
            if temp_path is not None:
                await asyncio.to_thread(self._discard, temp_path)
            if isinstance(exc, HarnessDatasetExportError):
                raise
            raise HarnessDatasetExportError("Harness dataset JSONL export failed.", details={"destination": target.name, "error_type": type(exc).__name__}) from exc

    def _normalize_statuses(self, statuses: HarnessRunStatus | str | Iterable[HarnessRunStatus | str] | None) -> frozenset[HarnessRunStatus] | None:
        # Accepts one status or an iterable and rejects unsupported lifecycle names.
        if statuses is None:
            return None
        try:
            values = [statuses] if isinstance(statuses, (str, HarnessRunStatus)) else list(statuses)
            return frozenset(value if isinstance(value, HarnessRunStatus) else HarnessRunStatus(value) for value in values)
        except (TypeError, ValueError) as exc:
            raise HarnessDatasetExportError("Harness dataset status filter is unsupported.", details={"allowed": [item.value for item in HarnessRunStatus]}) from exc

    def _row(self, spec: HarnessSpec, run: HarnessRun, events: list[HarnessEvent]) -> dict[str, Any]:
        # Builds one self-contained raw trajectory row from canonical record bodies.
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "spec": self._serializer.spec_to_dict(spec)["spec"],
            "run": self._serializer.run_to_dict(run)["run"],
            "events": [self._serializer.event_to_dict(event)["event"] for event in events],
        }

    def _prepare_temp(self, target: Path) -> Path:
        # Creates an empty sibling temporary file without touching any prior destination.
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
            os.close(handle)
            return Path(temp_name)
        except OSError as exc:
            raise HarnessDatasetExportError("Harness dataset temporary file could not be created.", details={"destination": target.name}) from exc

    def _append_row(self, temp_path: Path, row: dict[str, Any]) -> None:
        # Encodes and appends one compact JSON object followed by exactly one newline.
        try:
            line = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            with temp_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")
        except (OSError, TypeError, ValueError) as exc:
            raise HarnessDatasetExportError("Harness dataset row could not be encoded or written.", details={"temporary_file": temp_path.name}) from exc

    def _publish(self, temp_path: Path, target: Path) -> None:
        # Atomically replaces the destination only after the complete export succeeds.
        try:
            os.replace(temp_path, target)
        except OSError as exc:
            raise HarnessDatasetExportError("Harness dataset destination could not be replaced atomically.", details={"destination": target.name}) from exc

    def _discard(self, temp_path: Path) -> None:
        # Removes only the exporter-owned temporary file after failure or cancellation.
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            return


__all__ = ["HarnessDatasetExporter"]
