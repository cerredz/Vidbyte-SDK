"""FILE: vidbyte/lib/util/jsonl.py

PURPOSE: Defines AppendOnlyJsonl, the canonical durable append-only JSON-lines file: every record is one ASCII JSON line, flushed and fsynced before append returns, and a last line cut short by a crash is never read as a record and is cut off before the next write, so the file only ever holds whole lines.
ROLE IN CODEBASE: Used by InfiniteRunJournal (vidbyte/agents/infinite/journal.py) for each run's .runs/<run_id>.jsonl, which resume trusts line by line. Any feature that must resume from a log after a crash, such as a run journal, a ledger, or an event log, should write it through this class.
ARCHITECTURE NOTE: The class owns the bytes on disk, never the meaning of a record: the caller builds each record and parses the text read returns. Writes run under one class-level lock, so two objects over the same file in one process never interleave a line. Records are written with json.dumps defaults, so non-ASCII text is escaped and text UTF-8 cannot encode, such as a lone surrogate, is written instead of failing. A torn tail is found by read and remembered on the object until the next append.
FUNCTION INVENTORY: read() -> str: the file's whole lines, leaving out a torn last line; append(record) writes one record durably, repairing the tail first.
COMMON MODIFICATION PATTERNS: A new durability guarantee, such as fsyncing the folder after the file is created, goes in append; parsing rules belong to the caller.
WHAT NOT TO DO IN THIS FILE: 1. Do not batch records or skip fsync; a caller trusts every line on disk. 2. Do not rewrite or reorder lines; only a torn last line is ever cut off. 3. Do not import from a layer above vidbyte/lib.
KNOWN EDGE CASES: A last line without its newline that parses as JSON is a whole record whose newline was lost; read keeps it, and the next append first writes the missing newline. One that does not parse is torn: read leaves it out, and the next append truncates the file to where it starts. append without an earlier read assumes the file ends in a newline. Decoding uses errors="replace", so a broken byte reaches the caller as a replacement character, never as an exception here.
RELATED DOCS: vidbyte/agents/infinite/README.md (run journals); vidbyte/lib/README.md
TESTS: tests/test_append_only_jsonl.py; and through InfiniteRunJournal, tests/features/infinite_memory_agent/test_infinite_memory_resume.py
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar


class AppendOnlyJsonl:
    """One append-only JSON-lines file whose records are durable before append returns and whose torn last line is never read."""

    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, path: Path) -> None:
        self.path = path
        # Where a torn or unterminated last line ends the whole lines,
        # and what to write before the next record, so the next append
        # leaves only whole lines; read() sets it.
        self._repair: tuple[int, str] | None = None

    def read(self) -> str:
        """Return the file's whole lines as text, leaving out a torn last line, which the next append cuts off."""
        # @intent a-torn-tail-is-not-a-broken-log
        # A crash can cut the last record short. A last line without its
        # newline that does not parse is left out here and cut off
        # before the next write; one that parses is kept and gets its
        # newline then.
        data = self.path.read_bytes()
        head, newline, tail = data.rpartition(b"\n")
        if not tail.strip():
            self._repair = None
            return data.decode("utf-8", errors="replace")
        try:
            json.loads(tail)
        except ValueError:
            self._repair = (len(head) + len(newline), "")
            return (head + newline).decode("utf-8", errors="replace")
        self._repair = (len(data), "\n")
        return data.decode("utf-8", errors="replace")

    def append(self, record: Mapping[str, object]) -> None:
        """Write one record as one ASCII JSON line, flushed and fsynced before returning, after repairing a torn last line."""
        # @intent every-record-is-durable-before-it-counts
        # Each record is flushed and fsynced before the caller moves on,
        # so a crash loses at most the record being written, which then
        # becomes a torn last line that read leaves out.
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


__all__ = ["AppendOnlyJsonl"]
