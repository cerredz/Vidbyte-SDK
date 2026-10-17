"""Context Protocol Header

Description:
    Defines internal data contracts for code-search tooling and the records
    of the canonical full-text index.
Purpose:
    Keeps code-search dataclasses in the shared dataclass namespace while
    allowing built-in tools to keep behavior in their package.
Architecture:
    - _CodeChunk: Internal indexed text chunk for semantic-style search.
    - FullTextRow: One line handed to vidbyte.lib.util.fulltext.FullTextIndex.
    - FullTextHit: One ranked match with its snippet.
    - FullTextMatches: The hits of one search and how many rows matched.
Relations:
    Related to vidbyte.tools.builtins.code_search.semantic,
    vidbyte.lib.util.fulltext and
    vidbyte.tools.builtins.code_search.search_memory.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.dataclasses.validation import RecordFieldConverter, RecordFieldValidator


@dataclass(frozen=True, slots=True)
class _CodeChunk:
    """Internal representation of an indexed code chunk."""

    path: str
    start_line: int
    end_line: int
    text: str
    vector: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class FullTextRow:
    """One searchable line: the file it came from, the label a hit shows, and its text."""

    source: str
    label: str
    text: str

    def __post_init__(self) -> None:
        # @intent full-text-rows-name-their-source-and-label
        # A row is replaced and dropped by its source, and a hit is shown
        # by its label, so neither may be blank; the text may be empty.
        RecordFieldValidator.require_text(self.source, "FullTextRow.source")
        RecordFieldValidator.require_text(self.label, "FullTextRow.label")
        RecordFieldValidator.require_text(self.text, "FullTextRow.text", allow_blank=True)


@dataclass(frozen=True, slots=True)
class FullTextHit:
    """One matching row: its label and a short snippet around the match."""

    label: str
    snippet: str

    def __post_init__(self) -> None:
        # Both fields are text; the snippet may be empty.
        RecordFieldValidator.require_text(self.label, "FullTextHit.label", allow_blank=True)
        RecordFieldValidator.require_text(self.snippet, "FullTextHit.snippet", allow_blank=True)


@dataclass(frozen=True, slots=True)
class FullTextMatches:
    """The best hits of one search, best first, and how many rows matched in all."""

    hits: tuple[FullTextHit, ...]
    total: int

    def __post_init__(self) -> None:
        # @intent the-total-counts-every-shown-hit
        # The total is the count of every matching row, so it can never be
        # smaller than the hits shown.
        object.__setattr__(self, "hits", RecordFieldConverter.to_tuple(self.hits, "FullTextMatches.hits", item_type=FullTextHit))
        RecordFieldValidator.require_int(self.total, "FullTextMatches.total", minimum=len(self.hits))


__all__ = [
    "FullTextHit",
    "FullTextMatches",
    "FullTextRow",
]
