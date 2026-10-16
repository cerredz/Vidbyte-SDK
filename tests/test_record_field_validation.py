"""FILE: tests/test_record_field_validation.py

PURPOSE: Proves the RecordFieldValidator and RecordFieldConverter options added for InfiniteMemory: text without a length cap, one-line text, tuples of text items checked item by item, integers without a maximum, folders resolved once and never files, and lists of existing files with distinct names. Every refusal names the field, or the item as field[index].
ROLE IN CODEBASE: Unit tests for vidbyte/lib/dataclasses/validation.py. The options that predate InfiniteMemory are proven through the harness-thread records in tests/features/harness_threads/test_harness_threads_records.py.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_record_field_validation.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.errors import ConfigurationError

LONG_TEXT_CHARS = 100_000


def _field(raised: pytest.ExceptionInfo[ConfigurationError]) -> object:
    # The field a refusal names in its details.
    return raised.value.details["field"]


# ---------------------------------------------------------------- text


def test_text_without_a_cap_accepts_any_length_but_never_blank() -> None:
    """max_chars is optional; blank text is still refused unless allow_blank."""
    long = "a" * LONG_TEXT_CHARS
    assert RecordFieldValidator.require_text(long, "Card.summary") == long
    with pytest.raises(ConfigurationError, match=r"Card.summary must be non-empty text; got '   '") as raised:
        RecordFieldValidator.require_text("   ", "Card.summary")
    assert _field(raised) == "Card.summary"
    assert RecordFieldValidator.require_text("", "Card.summary", allow_blank=True) == ""


@pytest.mark.parametrize("text", ["two\nlines", "carriage\rreturn", "line separator", "next\x85line"])
def test_one_line_refuses_every_kind_of_line_break(text: str) -> None:
    """One line means no break str.splitlines would see, so Unicode separators are refused too."""
    with pytest.raises(ConfigurationError, match="must be one line of non-empty text"):
        RecordFieldValidator.require_text(text, "Card.name", one_line=True)
    assert RecordFieldValidator.require_text(text, "Card.name") == text


def test_optional_text_takes_none_and_the_same_options() -> None:
    """None passes; anything else must pass require_text's rule with the same options."""
    assert RecordFieldValidator.require_optional_text(None, "Card.note", one_line=True) is None
    assert RecordFieldValidator.require_optional_text("a" * LONG_TEXT_CHARS, "Card.note") is not None
    with pytest.raises(ConfigurationError, match="Card.note must be one line"):
        RecordFieldValidator.require_optional_text("a\nb", "Card.note", one_line=True)


def test_the_cap_and_the_pattern_still_apply_when_given() -> None:
    """The message names the cap or the pattern that failed."""
    with pytest.raises(ConfigurationError, match="of at most 3 characters"):
        RecordFieldValidator.require_text("abcd", "Card.tag", max_chars=3)
    with pytest.raises(ConfigurationError, match=r"must match \[a-z\]\+"):
        RecordFieldValidator.require_text("ABC", "Card.tag", pattern="[a-z]+")


# ---------------------------------------------------------------- text items


def test_text_items_must_be_a_tuple_within_the_item_cap() -> None:
    """A list is refused so a frozen record cannot be changed through its field; the cap is optional."""
    assert RecordFieldValidator.require_text_items(("a", "b"), "Card.tags", max_items=2) == ("a", "b")
    assert RecordFieldValidator.require_text_items((), "Card.tags") == ()
    with pytest.raises(ConfigurationError, match="Card.tags must be a tuple of text items"):
        RecordFieldValidator.require_text_items(["a"], "Card.tags")
    with pytest.raises(ConfigurationError, match="must be a tuple of at most 2 text items"):
        RecordFieldValidator.require_text_items(("a", "b", "c"), "Card.tags", max_items=2)


@pytest.mark.parametrize(
    ("items", "bad_index"),
    [
        pytest.param(("ok", "   "), 1, id="blank-item"),
        pytest.param(("ok", 7), 1, id="non-text-item"),
        pytest.param(("Bad Tag", "ok"), 0, id="pattern-miss"),
        pytest.param(("ok", "line\nbreak"), 1, id="two-line-item"),
    ],
)
def test_a_bad_item_is_named_by_its_index(items: tuple[object, ...], bad_index: int) -> None:
    """The refusal points at the one item to fix, in the message and in the details."""
    with pytest.raises(ConfigurationError, match=rf"Card.tags\[{bad_index}\] must") as raised:
        RecordFieldValidator.require_text_items(items, "Card.tags", max_chars=20, pattern=r"[a-z\n ]+", one_line=True)
    assert _field(raised) == f"Card.tags[{bad_index}]"


# ---------------------------------------------------------------- integers


def test_an_integer_without_a_maximum_says_of_at_least() -> None:
    """maximum is optional; the message states only the bound that applies, and a bool is never an integer."""
    assert RecordFieldValidator.require_int(2_000_000, "Settings.max_tokens", minimum=1) == 2_000_000
    with pytest.raises(ConfigurationError, match="Settings.max_tokens must be an integer of at least 1; got 0"):
        RecordFieldValidator.require_int(0, "Settings.max_tokens", minimum=1)
    with pytest.raises(ConfigurationError, match="must be an integer from 1 to 5; got True"):
        RecordFieldValidator.require_int(True, "Settings.depth", minimum=1, maximum=5)


# ---------------------------------------------------------------- folders and files


def test_a_folder_is_resolved_once_against_the_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative folder is stored absolute, so a later change of the working directory never moves it; a missing one passes by default."""
    monkeypatch.chdir(tmp_path)
    folder = RecordFieldConverter.to_folder("work/space", "Settings.root")
    assert folder == (tmp_path / "work" / "space").resolve() and folder.is_absolute()
    monkeypatch.chdir(tmp_path.parent)
    assert folder == (tmp_path / "work" / "space").resolve()


def test_a_folder_expands_the_home_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """~ means the user's home, on every platform."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert RecordFieldConverter.to_folder("~/space", "Settings.root") == (tmp_path / "space").resolve()


def test_a_folder_is_never_a_file_and_must_exist_only_when_asked(tmp_path: Path) -> None:
    """An existing file is refused; a missing folder is refused only with must_exist; blank and non-path values are refused."""
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Settings.root must be a folder, but .* is a file"):
        RecordFieldConverter.to_folder(tmp_path / "a.md", "Settings.root")
    with pytest.raises(ConfigurationError, match="must be an existing folder"):
        RecordFieldConverter.to_folder(tmp_path / "missing", "Settings.root", must_exist=True)
    assert RecordFieldConverter.to_folder(tmp_path, "Settings.root", must_exist=True) == tmp_path.resolve()
    for value in ("   ", 7, None):
        with pytest.raises(ConfigurationError, match="Settings.root must be a folder path"):
            RecordFieldConverter.to_folder(value, "Settings.root")


def test_files_are_existing_resolved_paths_returned_as_a_tuple(tmp_path: Path) -> None:
    """A list or tuple of str or Path items becomes a tuple of resolved paths, in order."""
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    assert RecordFieldConverter.to_files([str(tmp_path / "a.md"), tmp_path / "b.md"], "Settings.seed") == ((tmp_path / "a.md").resolve(), (tmp_path / "b.md").resolve())
    assert RecordFieldConverter.to_files((), "Settings.seed") == ()


def test_a_bare_path_a_missing_file_and_a_folder_are_refused(tmp_path: Path) -> None:
    """A str is one path, not a list; a listed item must be an existing file and is named by its index."""
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Settings.seed must be a tuple or list of file paths"):
        RecordFieldConverter.to_files(str(tmp_path / "a.md"), "Settings.seed")
    for bad in (tmp_path / "missing.md", tmp_path, "  "):
        with pytest.raises(ConfigurationError, match=r"Settings.seed\[1\] must name an existing file") as raised:
            RecordFieldConverter.to_files([tmp_path / "a.md", bad], "Settings.seed")
        assert _field(raised) == "Settings.seed[1]"


def test_distinct_names_refuses_two_files_with_the_same_name(tmp_path: Path) -> None:
    """A caller that copies files into one folder by name cannot take two files that would overwrite each other."""
    for folder in ("one", "two"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "notes.md").write_text(folder, encoding="utf-8")
    pair = [tmp_path / "one" / "notes.md", tmp_path / "two" / "notes.md"]
    assert len(RecordFieldConverter.to_files(pair, "Settings.seed")) == 2
    with pytest.raises(ConfigurationError, match="must have distinct file names, but .* are both named notes.md") as raised:
        RecordFieldConverter.to_files(pair, "Settings.seed", distinct_names=True)
    assert _field(raised) == "Settings.seed[1]"
