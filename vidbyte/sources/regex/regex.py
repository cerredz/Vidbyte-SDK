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
    H1_LINE: ClassVar[re.Pattern[str]] = re.compile(r"#[ \t]+(?P<title>.*?\S)[ \t]*")
    FENCE: ClassVar[re.Pattern[str]] = re.compile(r" {0,3}(?P<fence>```|~~~)")

    @staticmethod
    def first_h1_title(text: str) -> str | None:
        # Returns the first markdown H1 outside fenced code blocks, or None.
        # @intent h1-title-skips-fenced-code
        # A "# ..." line inside a fenced code block is code (often a shell comment), not a heading, so it must not title the document.
        fence: str | None = None
        for line in text.splitlines():
            marker = DocumentRegex.FENCE.match(line)
            if marker is not None and fence in (None, marker.group("fence")[0]):
                fence = marker.group("fence")[0] if fence is None else None
                continue
            match = None if fence is not None else DocumentRegex.H1_LINE.fullmatch(line)
            if match is not None:
                return match.group("title").strip()
        return None


class LlmsTxtRegex:
    """Regex helpers for the llms.txt grammar."""

    # @intent llms-txt-url-keeps-balanced-parens
    # CommonMark link destinations may contain a balanced pair of parentheses (e.g. Microsoft Learn "(v=vs.85)"
    # and Wikipedia "_(computing)" URLs), so the url must not stop at the first ')'.
    LINK_BULLET: ClassVar[re.Pattern[str]] = re.compile(
        r"^\s*-\s*\[(?P<text>[^\]]+)\]\((?P<url>(?:[^()]|\([^()]*\))*)\)\s*(?:[:\-\u2013\u2014]\s*(?P<note>.*))?$"
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
        # Parses "- [text](url): note" (or a -, en-dash, or em-dash separator) into (text, url, note).
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
