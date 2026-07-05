"""Context Protocol Header

Description:
    Compatibility markdown helper exports for artifact sources.
Purpose:
    Preserves draft helper names while the regex-backed implementations live in
    vidbyte.sources.regex.regex.
Architecture:
    - first_h1_title, parse_link_bullet, and slugify wrappers.
Relations:
    New code should import DocumentRegex, LlmsTxtRegex, or SourcesRegex directly.
"""

from __future__ import annotations

from vidbyte.sources.regex import DocumentRegex, LlmsTxtRegex, SourcesRegex


def first_h1_title(text: str) -> str | None:
    # Compatibility wrapper around DocumentRegex.
    return DocumentRegex.first_h1_title(text)


def parse_link_bullet(line: str) -> tuple[str, str, str | None] | None:
    # Compatibility wrapper around LlmsTxtRegex.
    return LlmsTxtRegex.parse_link_bullet(line)


def slugify(name: str, *, max_len: int = 48) -> str:
    # Compatibility wrapper around SourcesRegex.
    return SourcesRegex.slugify(name, max_len=max_len)


__all__ = [
    "first_h1_title",
    "parse_link_bullet",
    "slugify",
]
