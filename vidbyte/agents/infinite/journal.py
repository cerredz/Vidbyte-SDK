"""FILE: vidbyte/agents/infinite/journal.py

PURPOSE: Defines InfiniteRunJournal, the append-only record of one InfiniteMemory run in .runs/<run_id>.jsonl: the task, every pair that started, every pair that finished with its result card, and how the run ended, so an interrupted run can resume without redoing finished pairs.
ROLE IN CODEBASE: Started by InfiniteMemoryRuntime.arun (runtime.py) for a new run, or found by InfiniteMemoryAgent.resume (agent.py) for an interrupted one; written and read by the launch tool (launch.py) for every pair; read by the agent to brief a resumed root and by the launch tool to brief a re-run generator and to cap the number of agents.
ARCHITECTURE NOTE: One JSON object per line, as spec section 9.1 documents. Every record is opened, written, flushed, fsynced, and closed before the step it records counts as done, under one class-level lock, so a crash loses at most the record being written. That record is then a torn final line without its newline, which loading ignores and the next write cuts off. Card serialization and parsing live here, not on the record.
FUNCTION INVENTORY: start writes run_started for a new run id; find validates a run id and loads the newest or the named unfinished journal; pair_started, pair_finished, and finish write one record each; finished, finished_children, interrupted_children, and agents_started read what was loaded or written; _whole_lines reads a journal file without its torn last line; _parse turns its lines into a journal; _append writes one record.
COMMON MODIFICATION PATTERNS: A new record type adds one InfiniteJournalEvent member, one writer method here, and one case in _parse; old journals without it must still load.
WHAT NOT TO DO IN THIS FILE: 1. Do not batch records or skip fsync; resume trusts every record already on disk. 2. Do not rewrite a journal; only the torn final line is ever cut off. 3. Do not follow a run id that fails INFINITE_RUN_ID_PATTERN; it could name a path outside .runs/. 4. Do not write settings or keys into a record.
KNOWN EDGE CASES: A final line without its newline that does not parse is torn and ignored; one that parses is kept, and the next write first ends it with a newline. Any other malformed line refuses the journal with its line number. A pair started twice (re-run after a resume) counts as two pairs toward max_agents. Run ids start with a UTC timestamp, so sorting file names newest first sorts runs newest first.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 6.1 INV-25 to INV-28, and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_resume.py and tests/features/infinite_memory_agent/test_infinite_memory_delegation.py
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from vidbyte.lib.constants.infinite import (
    INFINITE_MIN_AGENTS,
    INFINITE_RUN_ID_PATTERN,
    INFINITE_RUN_ID_TIME_FORMAT,
    INFINITE_RUNS_DIRNAME,
)
from vidbyte.lib.dataclasses.infinite import InfiniteResultCard
from vidbyte.lib.enums.infinite import (
    InfiniteJournalEvent,
    InfiniteResultStatus,
    InfiniteVerdict,
)
from vidbyte.lib.errors import ConfigurationError


class InfiniteRunJournal:
    """The append-only journal of one run: its task, the pairs started and finished, and how it ended."""

    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, path: Path, task: str, *, started: list[str] | None = None, cards: dict[str, InfiniteResultCard] | None = None, stop_reason: str | None = None, repair: tuple[int, str] | None = None) -> None:
        self.path = path
        self.run_id = path.stem
        self.task = task
        self.stop_reason = stop_reason
        self._started = started if started is not None else []
        self._cards = cards if cards is not None else {}
        # Where a torn last line starts, and what to write before the
        # next record, so the next write leaves only whole lines.
        self._repair = repair

    @classmethod
    def start(cls, workspace_root: Path, task: str) -> InfiniteRunJournal:
        """Create the journal of a new run and write its run_started record."""
        # @intent run-ids-sort-by-time
        # A run id is its UTC start time plus a random suffix, so names
        # sort by age and two runs started in one second never collide.
        run_id = f"{datetime.now(timezone.utc).strftime(INFINITE_RUN_ID_TIME_FORMAT)}-{uuid.uuid4().hex[:8]}"
        journal = cls(Path(workspace_root) / INFINITE_RUNS_DIRNAME / f"{run_id}.jsonl", task)
        journal.path.parent.mkdir(parents=True, exist_ok=True)
        journal._append(InfiniteJournalEvent.RUN_STARTED, {"run": run_id, "task": task})
        return journal

    @classmethod
    def find(cls, workspace_root: Path, run_id: str | None) -> InfiniteRunJournal:
        """Return the named unfinished run, or the newest unfinished run when run_id is None; raise ConfigurationError otherwise."""
        # @intent resume-only-a-safe-unfinished-run
        # A run id is checked against its pattern before it becomes a
        # path, so it can never lead outside .runs/. Only an unfinished
        # run resumes, and nothing is written while looking.
        runs = Path(workspace_root) / INFINITE_RUNS_DIRNAME
        if run_id is not None and (not isinstance(run_id, str) or re.fullmatch(INFINITE_RUN_ID_PATTERN, run_id) is None):
            raise ConfigurationError(f"run_id must look like 20261015T024900Z-1a2b3c4d; got {run_id!r}.", details={"field": "run_id"})
        if run_id is None:
            paths = sorted((path for path in runs.glob("*.jsonl") if re.fullmatch(INFINITE_RUN_ID_PATTERN, path.stem)), reverse=True)
            loaded = (cls._parse(path, *cls._whole_lines(path)) for path in paths)
            journal = next((candidate for candidate in loaded if candidate.stop_reason is None), None)
            if journal is None:
                raise ConfigurationError(f"There is no unfinished run in {runs} to resume; start a new one with run().", details={"field": "run_id"})
            return journal
        path = runs / f"{run_id}.jsonl"
        if not path.is_file():
            raise ConfigurationError(f"There is no run {run_id} in {runs}.", details={"field": "run_id"})
        journal = cls._parse(path, *cls._whole_lines(path))
        if journal.stop_reason is not None:
            raise ConfigurationError(f"Run {run_id} already finished, so it cannot be resumed; start a new one with run().", details={"field": "run_id"})
        return journal

    def pair_started(self, key: str) -> None:
        """Record that the pair with this key is about to start."""
        self._append(InfiniteJournalEvent.PAIR_STARTED, {"key": key})
        self._started.append(key)

    def pair_finished(self, key: str, card: InfiniteResultCard) -> None:
        """Record the finished pair's result card; enum values and tuples are written as JSON strings and lists."""
        self._append(InfiniteJournalEvent.PAIR_FINISHED, {"key": key, "card": asdict(card)})
        self._cards[key] = card

    def finish(self, stop_reason: str) -> None:
        """Record that the root's loop returned, which closes the run to resume."""
        self._append(InfiniteJournalEvent.RUN_FINISHED, {"stop_reason": stop_reason})
        self.stop_reason = stop_reason

    def finished(self, key: str) -> InfiniteResultCard | None:
        """Return the recorded card of a finished pair, or None."""
        return self._cards.get(key)

    def finished_children(self, parent_key: str) -> tuple[InfiniteResultCard, ...]:
        """Return the cards of the finished pairs this agent launched, in finishing order."""
        return tuple(card for key, card in self._cards.items() if key.rpartition("/")[0] == parent_key)

    def interrupted_children(self, parent_key: str) -> tuple[str, ...]:
        """Return the names of pairs this agent launched that started but never finished, each once."""
        keys = dict.fromkeys(key for key in self._started if key.rpartition("/")[0] == parent_key and key not in self._cards)
        return tuple(key.rpartition("/")[2] for key in keys)

    @property
    def agents_started(self) -> int:
        """Return how many agents this run has started: two for every pair_started record."""
        return INFINITE_MIN_AGENTS * len(self._started)

    @staticmethod
    def _whole_lines(path: Path) -> tuple[str, tuple[int, str] | None]:
        # @intent a-torn-tail-is-not-a-broken-journal
        # A crash can cut the last record short. A last line without its
        # newline that does not parse is left out here and cut off before
        # the next write; one that parses is kept and gets its newline.
        data = path.read_bytes()
        head, newline, tail = data.rpartition(b"\n")
        if not tail.strip():
            return data.decode("utf-8", errors="replace"), None
        try:
            json.loads(tail)
        except ValueError:
            return (head + newline).decode("utf-8", errors="replace"), (len(head) + len(newline), "")
        return data.decode("utf-8", errors="replace"), (len(data), "\n")

    @classmethod
    def _parse(cls, path: Path, text: str, repair: tuple[int, str] | None) -> InfiniteRunJournal:
        # Every whole line must be a record in the documented shape, so a
        # bad line refuses the journal with its line number.
        task: str | None = None
        started: list[str] = []
        cards: dict[str, InfiniteResultCard] = {}
        stop_reason: str | None = None
        for number, line in enumerate(text.split("\n"), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                match InfiniteJournalEvent(record["event"]):
                    case InfiniteJournalEvent.RUN_STARTED:
                        task = str(record["task"])
                    case InfiniteJournalEvent.PAIR_STARTED:
                        started.append(str(record["key"]))
                    case InfiniteJournalEvent.PAIR_FINISHED:
                        card = record["card"]
                        enums = {"status": InfiniteResultStatus(card["status"]), "verdict": InfiniteVerdict(card["verdict"])}
                        lists = {field: tuple(card[field]) for field in ("entries", "dropped", "files")}
                        cards[str(record["key"])] = InfiniteResultCard(**{**card, **enums, **lists})
                    case InfiniteJournalEvent.RUN_FINISHED:
                        stop_reason = str(record["stop_reason"])
            except (ValueError, KeyError, TypeError, ConfigurationError) as exc:
                raise ConfigurationError(f"The journal {path.name} has a bad record at line {number}; fix or remove that line before resuming.", details={"file": path.name, "line": number}) from exc
        if task is None:
            raise ConfigurationError(f"The journal {path.name} has no run_started record with its task, so it cannot be resumed.", details={"file": path.name})
        return cls(path, task, started=started, cards=cards, stop_reason=stop_reason, repair=repair)

    def _append(self, event: InfiniteJournalEvent, fields: Mapping[str, object]) -> None:
        # @intent every-record-is-durable-before-it-counts
        # Each record is flushed and fsynced before the caller moves on,
        # so resume can trust every whole line on disk. Records are
        # ASCII JSON, so text UTF-8 cannot encode, such as a lone
        # surrogate in a model's reply, is escaped instead of failing.
        record = {"event": event.value, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
        with self._lock:
            prefix = ""
            if self._repair is not None:
                offset, prefix = self._repair
                os.truncate(self.path, offset)
                self._repair = None
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"{prefix}{json.dumps(record)}\n")
                handle.flush()
                os.fsync(handle.fileno())


__all__ = ["InfiniteRunJournal"]
