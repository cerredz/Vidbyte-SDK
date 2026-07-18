"""Context Protocol Header

Description:
    Defines RolloutRecorder, the append-only JSONL sink and loader for
    RolloutRecords.
Purpose:
    Persists every verified rollout as one independently parseable JSON line so
    accumulated data stays crash-safe, re-gradable, and export-friendly.
Architecture:
    - RolloutRecorder: Append-only writer plus strict line-by-line loader.
Relations:
    Consumed by vidbyte.environments.runner; parses via RolloutRecord.to_dict
    and RolloutRecord.from_dict.
Similar Files:
    - vidbyte/evals/registry.py: Equivalent local persistence for eval results.
"""

from __future__ import annotations

import json
from pathlib import Path

from vidbyte.environments.types import RolloutRecord
from vidbyte.lib.errors import ConfigurationError


class RolloutRecorder:
    """Append-only JSONL sink and loader for rollout records."""

    def __init__(self, path: Path | str) -> None:
        # Stores the target JSONL path without touching the filesystem yet.
        self._path = Path(path)

    @property
    def path(self) -> Path:
        # Returns the JSONL file path this recorder writes to.
        return self._path

    def append(self, record: RolloutRecord) -> None:
        """Serialize one record and append it as a single JSON line."""
        # Append mode per call keeps writes crash-safe at line granularity.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def load(self) -> tuple[RolloutRecord, ...]:
        """Parse every line back into RolloutRecords, failing loud on corruption."""
        if not self._path.exists():
            return ()
        records: list[RolloutRecord] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    records.append(RolloutRecord.from_dict(json.loads(stripped)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise ConfigurationError(
                        f"Corrupt rollout record at {self._path}:{line_number}: {exc}"
                    ) from exc
        return tuple(records)

    def __len__(self) -> int:
        # Returns the number of parseable records currently stored.
        return len(self.load())


__all__ = [
    "RolloutRecorder",
]
