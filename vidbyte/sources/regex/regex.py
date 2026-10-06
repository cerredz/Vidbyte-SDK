"""Context Protocol Header

Description:
    Central regex registry and regex-backed helpers for artifact sources.
Purpose:
    Keeps source regex patterns in one module and exposes semantic helper classes for each
    document grammar that consumes them.
Architecture:
    - SourcesRegex: Shared source helper regexes such as slugification.
    - DocumentRegex: Markdown document title helper.
    - LlmsTxtRegex: llms.txt heading and link-bullet helpers.
Relations:
    Imported by document loaders and the llms.txt parser.
"""

from __future__ import annotations

import re
from typing import ClassVar


class SourcesRegex:
    """Shared regex helpers used by multiple source loaders."""

    SLUG: ClassVar[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")

    @staticmethod
    def slugify(name: str, *, max_len: int = 48) -> str:
        # Lowercases, replaces non-alphanumeric runs with hyphens, trims, and never returns empty.
        slug = SourcesRegex.SLUG.sub("-", name.strip().lower()).strip("-")
        slug = slug[:max_len].strip("-")
        return slug or "item"


class DocumentRegex:
    """Regex helpers for generic markdown/text documents."""

    H1: ClassVar[re.Pattern[str]] = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)

    @staticmethod
    def first_h1_title(text: str) -> str | None:
        # Returns the first markdown H1 found in text, or None.
        match = DocumentRegex.H1.search(text)
        return match.group("title").strip() if match else None


class LlmsTxtRegex:
    """Regex helpers for the llms.txt grammar."""

    LINK_BULLET: ClassVar[re.Pattern[str]] = re.compile(
        r"^\s*-\s*\[(?P<text>[^\]]+)\]\((?P<url>[^)]*)\)\s*(?::\s*(?P<note>.*))?$"
    )
    LINK_BULLET_PREFIX: ClassVar[re.Pattern[str]] = re.compile(r"^\s*-\s*\[")

    @staticmethod
    def is_h1(line: str) -> bool:
        # True for a top-level "# " heading, but not "## ".
        return line.lstrip().startswith("# ")

    @staticmethod
    def is_h2(line: str) -> bool:
        # True for a section "## " heading.
        return line.lstrip().startswith("## ")

    @staticmethod
    def is_link_bullet(line: str) -> bool:
        # True when the line starts like a markdown link bullet.
        return LlmsTxtRegex.LINK_BULLET_PREFIX.match(line) is not None

    @staticmethod
    def parse_link_bullet(line: str) -> tuple[str, str, str | None] | None:
        # Parses "- [text](url): note" into (text, url, note), or None when not a link bullet.
        match = LlmsTxtRegex.LINK_BULLET.match(line)
        if match is None:
            return None
        note = match.group("note")
        return (match.group("text").strip(), match.group("url").strip(), note.strip() if note else None)


__all__ = [
    "DocumentRegex",
    "LlmsTxtRegex",
    "SourcesRegex",
]
