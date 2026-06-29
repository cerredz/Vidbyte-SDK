"""Context Protocol Header

Description:
    Parses raw llms.txt bytes into a validated LlmsTxtDocument, failing closed on malformed input.
Purpose:
    Implements the small, well-defined llms.txt grammar (H1 title, optional blockquote summary,
    free-prose details, then H2 sections of link bullets) without a markdown dependency.
Architecture:
    - parse_llms_txt: Pure function over bytes -> LlmsTxtDocument; raises SourceParseError.
Relations:
    Uses vidbyte.sources._markdown.parse_link_bullet; produces vidbyte.sources.llms_txt.types.
"""

from __future__ import annotations

import re

from vidbyte.lib.errors import SourceParseError
from vidbyte.sources._markdown import parse_link_bullet
from vidbyte.sources.llms_txt.types import LlmsTxtDocument, LlmsTxtLink, LlmsTxtSection

_LINK_BULLET_PREFIX = re.compile(r"^\s*-\s*\[")


def _is_h1(line: str) -> bool:
    # True for a top-level "# " heading (but not "## ").
    return line.lstrip().startswith("# ")


def _is_h2(line: str) -> bool:
    # True for a section "## " heading.
    return line.lstrip().startswith("## ")


def parse_llms_txt(raw: bytes, *, url: str) -> LlmsTxtDocument:
    # Decodes and parses llms.txt structure into a validated IR; raises SourceParseError on malformed input.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceParseError("llms.txt is not valid UTF-8.", details={"url": url}) from exc
    if text and text[0] == chr(0xFEFF):
        text = text[1:]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    index = 0
    total = len(lines)
    while index < total and lines[index].strip() == "":
        index += 1
    if index >= total or not _is_h1(lines[index]):
        raise SourceParseError("llms.txt must begin with a single H1 title.", details={"url": url})
    title = lines[index].strip()[1:].strip()
    index += 1

    # Skip blank lines between the title and an optional blockquote summary.
    while index < total and lines[index].strip() == "":
        index += 1

    summary_parts: list[str] = []
    while index < total and lines[index].lstrip().startswith(">"):
        summary_parts.append(lines[index].lstrip()[1:].strip())
        index += 1
    summary = "\n".join(summary_parts).strip() or None

    detail_parts: list[str] = []
    while index < total and not _is_h2(lines[index]):
        detail_parts.append(lines[index])
        index += 1
    details = "\n".join(detail_parts).strip() or None

    sections: list[LlmsTxtSection] = []
    while index < total:
        if not _is_h2(lines[index]):
            index += 1
            continue
        name = lines[index].strip()[2:].strip()
        index += 1
        links: list[LlmsTxtLink] = []
        while index < total and not _is_h2(lines[index]):
            line = lines[index]
            if _LINK_BULLET_PREFIX.match(line):
                parsed = parse_link_bullet(line)
                if parsed is None or not parsed[1]:
                    raise SourceParseError(
                        "Malformed or empty link in llms.txt section.",
                        details={"url": url, "section": name, "line": line.strip()},
                    )
                links.append(LlmsTxtLink(title=parsed[0], url=parsed[1], note=parsed[2]))
            index += 1
        sections.append(LlmsTxtSection(name=name, links=tuple(links), optional=name.strip().lower() == "optional"))

    return LlmsTxtDocument(title=title, summary=summary, details=details, sections=tuple(sections))
