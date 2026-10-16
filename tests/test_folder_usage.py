"""FILE: tests/test_folder_usage.py

PURPOSE: Proves FolderUsage counts every file under a folder from disk, skips only the named top-level folders, keys files by POSIX relative path, and projects a write's effect on the file count and token total; and that FolderTotals refuses impossible counts. It also proves LocalFileSystemBackend.write_text(atomic=True), the write FolderUsage's callers pair it with: a whole file is swapped in, and a failed swap leaves the target and no temporary file behind.
ROLE IN CODEBASE: Unit tests for vidbyte/lib/tools/filesystem/usage.py, FolderTotals in vidbyte/lib/dataclasses/filesystem.py, and the atomic option of vidbyte/lib/tools/filesystem/backends/local.py. InfiniteWorkspace's caps are proven through them in tests/features/infinite_memory_agent/test_infinite_memory_workspace.py.
ARCHITECTURE NOTE: Each test builds a small folder in tmp_path and compares exact counts, using TokenEstimate's four-characters-per-token rule. The failed-swap test patches os.replace to raise, so the cleanup path runs without a real disk fault.
COMMON MODIFICATION PATTERNS: A new FolderUsage option adds one folder layout and its expected mapping; a new write_text option adds one test that checks the folder listing after the write, so a leftover temporary file is caught.
KNOWN EDGE CASES: skip names only top-level folders, so a nested folder with a skipped name still counts. Undecodable bytes are counted, not refused. Text the encoding cannot hold fails before any file, temporary or target, is created.
RELATED DOCS: vidbyte/lib/README.md (tools/filesystem/); vidbyte/agents/infinite/README.md (limits).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_folder_usage.py -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vidbyte.lib.dataclasses.filesystem import FolderTotals
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tools.filesystem import FolderUsage
from vidbyte.lib.tools.filesystem.backends.local import LocalFileSystemBackend


def _write(root: Path, relative: str, text: str) -> None:
    # Writes one file under root, creating its folders.
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_every_file_counts_except_the_skipped_top_level_folders(tmp_path: Path) -> None:
    """Nested files count with POSIX keys; a skipped name skips only the top-level folder, not a nested folder of the same name."""
    _write(tmp_path, "a.md", "abcd" * 3)
    _write(tmp_path, "notes/deep/b.txt", "x")
    _write(tmp_path, "runs/journal.jsonl", "ignored" * 50)
    _write(tmp_path, "notes/runs/c.md", "abcde")
    (tmp_path / "empty").mkdir()
    assert FolderUsage.tokens_by_file(tmp_path, skip=("runs",)) == {"a.md": 3, "notes/deep/b.txt": 1, "notes/runs/c.md": 2}
    assert "runs/journal.jsonl" in FolderUsage.tokens_by_file(tmp_path)


def test_undecodable_bytes_are_counted_not_refused(tmp_path: Path) -> None:
    """A file a shell wrote in another encoding still counts toward the caps."""
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\xfd\xfc\xfb")
    assert FolderUsage.tokens_by_file(tmp_path) == {"blob.bin": 2}


def test_totals_project_a_write_over_fresh_counts() -> None:
    """A changed path that exists swaps its old count for the new text's; a new path adds a file."""
    counts = {"a.md": 10, "b.md": 5}
    assert FolderUsage.totals(counts, {}) == FolderTotals(files=2, tokens=15)
    assert FolderUsage.totals(counts, {"a.md": "abcd"}) == FolderTotals(files=2, tokens=6)
    assert FolderUsage.totals(counts, {"c.md": "abcdefgh", "a.md": ""}) == FolderTotals(files=3, tokens=7)


@pytest.mark.parametrize(("files", "tokens"), [(-1, 0), (0, -1), (True, 0), (0, 1.0)])
def test_folder_totals_refuse_impossible_counts(files: object, tokens: object) -> None:
    """Both totals are non-negative integers, never a bool or a float."""
    with pytest.raises(ConfigurationError, match="FolderTotals"):
        FolderTotals(files=files, tokens=tokens)  # type: ignore[arg-type]


def test_an_atomic_write_swaps_in_the_whole_file_and_leaves_no_temporary(tmp_path: Path) -> None:
    """The target holds the new text with the requested newline style, and only the target is left in its folder."""
    target = tmp_path / "notes" / "a.md"
    LocalFileSystemBackend().write_text(target, "old\n", encoding="utf-8", create_parents=True, newline="", atomic=True)
    LocalFileSystemBackend().write_text(target, "line one\nline two\n", encoding="utf-8", create_parents=True, newline="", atomic=True)
    assert target.read_bytes() == b"line one\nline two\n"
    assert os.listdir(target.parent) == ["a.md"]


def test_a_failed_atomic_swap_keeps_the_target_and_removes_the_temporary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the swap fails, a reader still sees the old file, and no temporary file lingers to count toward a cap."""
    target = tmp_path / "a.md"
    target.write_text("old", encoding="utf-8")

    def refuse(source: str, destination: object) -> None:
        raise OSError("the disk refused the swap")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError, match="refused the swap"):
        LocalFileSystemBackend().write_text(target, "new", encoding="utf-8", create_parents=False, atomic=True)
    assert target.read_text(encoding="utf-8") == "old"
    assert os.listdir(tmp_path) == ["a.md"]


def test_text_the_encoding_cannot_hold_fails_before_any_file_is_touched(tmp_path: Path) -> None:
    """The encoding check runs first, so neither the target nor a temporary file is created."""
    with pytest.raises(UnicodeEncodeError):
        LocalFileSystemBackend().write_text(tmp_path / "a.md", "café", encoding="ascii", create_parents=False, atomic=True)
    assert os.listdir(tmp_path) == []
