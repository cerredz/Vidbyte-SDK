"""FILE: tests/test_append_only_jsonl.py

PURPOSE: Proves AppendOnlyJsonl writes one ASCII JSON line per record, reads back only whole lines, leaves out a torn last line that does not parse and cuts it off before the next append, keeps an unterminated last line that does parse and ends it first, and keeps concurrent appends whole.
ROLE IN CODEBASE: Unit tests for vidbyte/lib/util/jsonl.py. InfiniteRunJournal's crash recovery is proven through it in tests/features/infinite_memory_agent/test_infinite_memory_resume.py.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_append_only_jsonl.py -q
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from vidbyte.lib.util import AppendOnlyJsonl

WRITERS = 8
RECORDS_PER_WRITER = 25


def _lines(path: Path) -> list[dict[str, object]]:
    # Parses every line of the file, failing on any line that is not whole JSON.
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_append_creates_the_file_and_writes_one_ascii_line_per_record(tmp_path: Path) -> None:
    """Records land in order, one per line, with non-ASCII text escaped."""
    log = AppendOnlyJsonl(tmp_path / "journal.jsonl")
    log.append({"event": "run_started"})
    log.append({"event": "note", "text": "café"})
    data = log.path.read_bytes()
    assert data.isascii() and data.endswith(b"\n") and data.count(b"\n") == 2
    assert _lines(log.path) == [{"event": "run_started"}, {"event": "note", "text": "café"}]
    assert log.read() == data.decode("utf-8")


def test_a_torn_last_line_is_left_out_and_cut_off_by_the_next_append(tmp_path: Path) -> None:
    """A crash mid-write leaves a partial record; read ignores it and the next append replaces it with a whole line."""
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b'{"event": "run_started"}\n{"event": "pair_sta')
    log = AppendOnlyJsonl(path)
    assert log.read() == '{"event": "run_started"}\n'
    log.append({"event": "run_finished"})
    assert _lines(path) == [{"event": "run_started"}, {"event": "run_finished"}]


def test_an_unterminated_last_line_that_parses_is_kept_and_ended_first(tmp_path: Path) -> None:
    """A whole record missing only its newline is real data; the next append adds the newline before its own line."""
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b'{"event": "run_started"}\n{"event": "pair_started"}')
    log = AppendOnlyJsonl(path)
    assert log.read().endswith('{"event": "pair_started"}')
    log.append({"event": "pair_finished"})
    assert _lines(path) == [{"event": "run_started"}, {"event": "pair_started"}, {"event": "pair_finished"}]


def test_a_clean_file_reads_whole_and_appends_without_repair(tmp_path: Path) -> None:
    """With no torn tail, nothing is cut and nothing is prefixed."""
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b'{"event": "run_started"}\n')
    log = AppendOnlyJsonl(path)
    assert log.read() == '{"event": "run_started"}\n'
    log.append({"event": "run_finished"})
    assert path.read_bytes() == b'{"event": "run_started"}\n{"event": "run_finished"}\n'


def test_concurrent_appends_stay_whole_lines(tmp_path: Path) -> None:
    """Writers on several threads, each with its own handle on the same file, never interleave a record."""
    path = tmp_path / "journal.jsonl"

    def write(writer: int) -> None:
        log = AppendOnlyJsonl(path)
        for index in range(RECORDS_PER_WRITER):
            log.append({"writer": writer, "index": index, "pad": "x" * 200})

    threads = [threading.Thread(target=write, args=(writer,)) for writer in range(WRITERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    records = _lines(path)
    assert len(records) == WRITERS * RECORDS_PER_WRITER
    for writer in range(WRITERS):
        assert [record["index"] for record in records if record["writer"] == writer] == list(range(RECORDS_PER_WRITER))
