"""Context Protocol Header

Description:
    Parses raw llms.txt bytes into a validated LlmsTxtDocument.
Purpose:
    Implements the small llms.txt grammar with fail-closed UTF-8 and link validation while
    keeping regex concerns in vidbyte.sources.regex.
Architecture:
    - LlmsTxtParser: Stateful parser with small semantic parsing methods.
    - parse_llms_txt: Compatibility wrapper for function-style callers.
Relations:
    Uses vidbyte.sources.regex.LlmsTxtRegex and vidbyte.lib.dataclasses.sources.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sources import LlmsTxtDocument, LlmsTxtLink, LlmsTxtSection
from vidbyte.lib.errors import SourceParseError
from vidbyte.sources.regex import LlmsTxtRegex


class LlmsTxtParser:
    """Parser for the llms.txt markdown convention."""

    def __init__(self, raw: bytes, *, url: str) -> None:
        # Stores input bytes and parse position; parse() owns decoding and validation.
        self._raw = raw
        self._url = url
        self._lines: list[str] = []
        self._index = 0

    def parse(self) -> LlmsTxtDocument:
        # Parses bytes into a validated llms.txt IR.
        self._lines = self._normalize_lines(self._decode())
        self._index = self._skip_blank_lines(0)
        title = self._parse_title()
        self._index = self._skip_blank_lines(self._index)
        summary = self._parse_summary()
        details = self._parse_details()
        sections = self._parse_sections()
        return LlmsTxtDocument(title=title, summary=summary, details=details, sections=sections)

    def _decode(self) -> str:
        # Decodes UTF-8 and removes a leading byte-order mark when present.
        try:
            text = self._raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("llms.txt is not valid UTF-8.", details={"url": self._url}) from exc
        if text and text[0] == chr(0xFEFF):
            return text[1:]
        return text

    def _normalize_lines(self, text: str) -> list[str]:
        # Normalizes line endings before structural parsing.
        return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    def _skip_blank_lines(self, index: int) -> int:
        # Advances index past blank lines.
        while index < len(self._lines) and self._lines[index].strip() == "":
            index += 1
        return index

    def _parse_title(self) -> str:
        # Parses the required first H1 title.
        if self._index >= len(self._lines) or not LlmsTxtRegex.is_h1(self._lines[self._index]):
            raise SourceParseError("llms.txt must begin with a single H1 title.", details={"url": self._url})
        title = self._lines[self._index].strip()[1:].strip()
        self._index += 1
        return title

    def _parse_summary(self) -> str | None:
        # Parses an optional consecutive blockquote summary block.
        parts: list[str] = []
        while self._index < len(self._lines) and self._lines[self._index].lstrip().startswith(">"):
            parts.append(self._lines[self._index].lstrip()[1:].strip())
            self._index += 1
        return "\n".join(parts).strip() or None

    def _parse_details(self) -> str | None:
        # Parses free prose between summary and the first H2 section.
        parts: list[str] = []
        while self._index < len(self._lines) and not LlmsTxtRegex.is_h2(self._lines[self._index]):
            parts.append(self._lines[self._index])
            self._index += 1
        return "\n".join(parts).strip() or None

    def _parse_sections(self) -> tuple[LlmsTxtSection, ...]:
        # Parses all H2 sections and preserves document order, including duplicate names.
        sections: list[LlmsTxtSection] = []
        while self._index < len(self._lines):
            if not LlmsTxtRegex.is_h2(self._lines[self._index]):
                self._index += 1
                continue
            sections.append(self._parse_section())
        return tuple(sections)

    def _parse_section(self) -> LlmsTxtSection:
        # Parses one H2 section and its link bullets.
        name = self._lines[self._index].strip()[2:].strip()
        self._index += 1
        links = self._parse_section_links(name)
        return LlmsTxtSection(name=name, links=links, optional=name.strip().lower() == "optional")

    def _parse_section_links(self, section_name: str) -> tuple[LlmsTxtLink, ...]:
        # Parses link bullets until the next H2 section.
        links: list[LlmsTxtLink] = []
        while self._index < len(self._lines) and not LlmsTxtRegex.is_h2(self._lines[self._index]):
            line = self._lines[self._index]
            if LlmsTxtRegex.is_link_bullet(line):
                parsed = LlmsTxtRegex.parse_link_bullet(line)
                if parsed is None or not parsed[1]:
                    raise SourceParseError(
                        "Malformed or empty link in llms.txt section.",
                        details={"url": self._url, "section": section_name, "line": line.strip()},
                    )
                links.append(LlmsTxtLink(title=parsed[0], url=parsed[1], note=parsed[2]))
            self._index += 1
        return tuple(links)


def parse_llms_txt(raw: bytes, *, url: str) -> LlmsTxtDocument:
    # Compatibility wrapper for callers that use the function-style parser.
    return LlmsTxtParser(raw, url=url).parse()


__all__ = [
    "LlmsTxtParser",
    "parse_llms_txt",
]
