"""Context Protocol Header

Description:
    Defines the validated typed IR for a parsed llms.txt file.
Purpose:
    Gives the parser an immutable, hashable target and the loader a stable structure to emit
    from, with no I/O or rendering concerns.
Architecture:
    - LlmsTxtLink: One markdown link inside a section.
    - LlmsTxtSection: A named H2 section with zero or more links (optional flag for "## Optional").
    - LlmsTxtDocument: Title, optional summary/details, and ordered sections.
Relations:
    Produced by vidbyte.sources.llms_txt.parser; consumed by vidbyte.sources.llms_txt.loader.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmsTxtLink:
    """A single markdown link inside an llms.txt section."""

    title: str
    url: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class LlmsTxtSection:
    """A named H2 section of an llms.txt file containing zero or more links."""

    name: str
    links: tuple[LlmsTxtLink, ...]
    optional: bool = False


@dataclass(frozen=True, slots=True)
class LlmsTxtDocument:
    """Validated IR of a parsed llms.txt file."""

    title: str
    summary: str | None
    details: str | None
    sections: tuple[LlmsTxtSection, ...]
