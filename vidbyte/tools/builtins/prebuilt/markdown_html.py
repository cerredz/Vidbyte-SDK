"""FILE: vidbyte/tools/builtins/prebuilt/markdown_html.py

PURPOSE: Defines MarkdownHtmlToolFunctions, the seven prebuilt tools that read Markdown and HTML documents: Markdown headings, task items, tables, links, and fenced code blocks, plus HTML tables as records and HTML links.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the MARKDOWN_HTML category is chosen. Builds on PrebuiltToolSupport in _support.py for the line rule, the item cap, and the argument error, and on PREBUILT_HTML_BLOCK_TAGS in vidbyte/lib/constants/prebuilt_tools.py.
ARCHITECTURE NOTE: Markdown is read line by line with anchored regular expressions, after one pass that marks the lines of fenced code blocks so the other Markdown tools can skip them. HTML is read with two private html.parser.HTMLParser subclasses that only collect text, cells, and attributes, so malformed markup never fails a call. Both table tools build their records one at a time through one shared helper that keeps a running output size and refuses a result over the output cap.
FUNCTION INVENTORY: extract_markdown_headings, extract_markdown_tasks, parse_markdown_table, extract_markdown_links, extract_fenced_code_blocks, html_table_to_records, and extract_html_links are the tools. _fence_spans and _fenced_lines find fenced code; _heading_entries and _unique_anchors build headings and anchors; _table_spans and _split_table_row read pipe tables; _column_names and _bounded_records build table output under the cap; _link_definitions, _link_matches, and _link_item read Markdown links; _joined_url resolves an HTML link; _TableParser and _LinkParser are the HTML parsers; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new Markdown tool splits lines with PrebuiltToolSupport.split_lines, marks fenced lines with _fence_spans and _fenced_lines, and skips them unless its row says otherwise. A new HTML tool adds its own private HTMLParser subclass that only records what it needs, and adds its row in the spec's Appendix A.28 and its entry in tool_functions.
WHAT NOT TO DO IN THIS FILE: 1. Do not build a whole table output before measuring it; records are measured as they are built so a huge colspan or a wide padded table fails early. 2. Do not let an HTML parser error escape; malformed HTML is read as far as possible. 3. Do not write a regular expression with two adjacent runs that can match the same characters, because a long line would then take quadratic time.
KNOWN EDGE CASES: A Setext heading takes only the line directly above its underline as its text. Python's HTMLParser gives up with an AssertionError on a few malformed marked sections, so parsing stops there and the content read so far is kept. A colspan is read from its leading digits, zero or junk counts as one, and a huge value is clamped to the output cap, which never changes an accepted result. Repeated HTML header names get the same numeric suffixes as repeated Markdown column names, so no record silently loses a cell.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.28, section 9.2 items 6, 12, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_geometry_bits_markdown.py, tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py, and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import contextlib
import itertools
import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from html.parser import HTMLParser
from types import MappingProxyType
from typing import Annotated
from urllib.parse import urljoin, urlsplit

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_HTML_BLOCK_TAGS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import MarkdownLinkKind, TableAlignment
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_FENCE_OPEN = re.compile(r" {0,3}(?P<fence>`{3,}+|~{3,}+)(?P<info>.*)")
_FENCE_CLOSE = re.compile(r" {0,3}(?P<fence>`{3,}+|~{3,}+)[ \t]*+")
_ATX_HEADING = re.compile(r" {0,3}(?P<hashes>#{1,6})(?:[ \t]++(?P<text>.*))?")
# A closing run may start only where a run of spaces starts, so a
# long run of spaces is scanned once rather than once per space.
_ATX_CLOSING = re.compile(r"(?:^|(?<![ \t])[ \t]++)#++[ \t]*+$")
_SETEXT_UNDERLINE = re.compile(r" {0,3}(?:=++|-++)[ \t]*+")
_TASK_ITEM = re.compile(r"\s*+(?:[-*+]|\d++[.)])\s++\[( |x|X)\]\s++(.*)")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_DELIMITER_ROW = re.compile(r"[ \t]*+(?:\|[ \t]*+)?:?-++:?[ \t]*+(?:\|[ \t]*+:?-++:?[ \t]*+)*+(?:\|[ \t]*+)?")
_LINK_DEFINITION = re.compile(r" {0,3}\[(?P<label>[^\[\]]++)\]:[ \t]*+(?:<(?P<angle>[^<>]*+)>|(?P<url>[^\s<>]\S*+))(?:[ \t]++(?P<title>\"[^\"]*+\"|'[^']*+'|\([^()]*+\)))?[ \t]*+")
_MARKDOWN_LINK = re.compile(
    r"(?P<bang>!?)\[(?P<text>(?:[^\[\]]|\[[^\[\]]*+\])*+)\]"
    + r"(?:\((?P<destination><[^<>]*+>|[^\s()<>]*+(?:\([^\s()]*+\)[^\s()]*+)*+)(?:[ \t]++(?P<title>\"[^\"]*+\"|'[^']*+'|\([^()]*+\)))?[ \t]*+\)"
    + r"|\[(?P<label>[^\[\]]*+)\])"
    + r"|<(?P<autolink>[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>]*+)>"
)
_SPAN_DIGITS = re.compile(r"\s*+([0-9]++)")
_MAX_SPAN = PREBUILT_MAX_TEXT_CHARS
_MAX_SPAN_DIGITS = len(str(_MAX_SPAN))
_RAW_TEXT_TAGS = frozenset({"script", "style"})
_TABLE_CELL_TAGS = frozenset({"td", "th"})
_TABLE_STRUCTURE_TAGS = frozenset({"table", "tr", "td", "th"})
_URL_WHITESPACE = " \t\n\r\f"
_ALIGNMENTS: Mapping[tuple[bool, bool], str] = MappingProxyType(
    {(True, False): TableAlignment.LEFT.value, (True, True): TableAlignment.CENTER.value, (False, True): TableAlignment.RIGHT.value}
)
_OUTPUT_CAP_EXPECTED = f"input whose table output stays within {PREBUILT_MAX_TEXT_CHARS} characters"

_MARKDOWN_PARAMETER_DESCRIPTION = "The Markdown document to read, given as plain text. Line breaks may be CRLF, LF, or a lone CR, and line numbers in the result are 1-based. Content inside fenced code blocks is treated as code, not as Markdown. The text may hold at most one million characters."
_HTML_PARAMETER_DESCRIPTION = "The HTML document or fragment to read, given as text. It may be malformed, and no tag or attribute ever causes a parsing failure. Character references are decoded in text and in attribute values, and script and style content is ignored. The text may hold at most one million characters."

_TableRow = list[tuple[bool, str, int]]


class MarkdownHtmlToolFunctions:
    """The markdown_html category: reading structure out of Markdown and HTML documents."""

    @staticmethod
    def extract_markdown_headings(markdown: Annotated[str, Field(description=_MARKDOWN_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """List the headings of a Markdown document in order, with each heading's level, text, 1-based line number, and GitHub-style link anchor. Use it to outline a document, build a table of contents, or find the line where a section starts. It reads ATX headings of one to six hash marks, with any closing hashes removed, and Setext headings underlined with equals signs or hyphens, while lines inside fenced code blocks are ignored. Anchors are lowercase with spaces turned into hyphens and other punctuation dropped, a repeated anchor gets a numeric suffix, and the tool has no failure case beyond the text length cap."""
        # Mark the lines of fenced code so headings inside them are
        # skipped, then find every heading in document order.
        lines = PrebuiltToolSupport.split_lines(markdown)
        fenced = MarkdownHtmlToolFunctions._fenced_lines(MarkdownHtmlToolFunctions._fence_spans(lines), len(lines))
        entries = MarkdownHtmlToolFunctions._heading_entries(lines, fenced)

        # Give every heading its GitHub anchor, numbering repeats.
        anchors = MarkdownHtmlToolFunctions._unique_anchors([text for _, text, _ in entries])
        headings = [{"level": level, "text": text, "line": line, "anchor": anchor} for (level, text, line), anchor in zip(entries, anchors, strict=True)]
        return {"headings": headings, "count": len(headings)}

    @staticmethod
    def extract_markdown_tasks(markdown: Annotated[str, Field(description=_MARKDOWN_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """List the checklist items of a Markdown document with each item's line, whether it is checked, and its text, plus the numbers of done and open items. Use it to track progress in a plan, an issue, or meeting notes written as a task list. A task is a bullet or numbered list item that starts with brackets holding a space, a lowercase x, or an uppercase X, followed by whitespace and its text. Lines inside fenced code blocks are ignored, and the tool has no failure case beyond the text length cap."""
        # Mark the lines of fenced code so tasks inside them are
        # skipped.
        lines = PrebuiltToolSupport.split_lines(markdown)
        fenced = MarkdownHtmlToolFunctions._fenced_lines(MarkdownHtmlToolFunctions._fence_spans(lines), len(lines))

        # Match every other line against the task item pattern.
        tasks: list[dict[str, object]] = []
        for index, line in enumerate(lines):
            match = None if fenced[index] else _TASK_ITEM.fullmatch(line)
            if match is not None:
                tasks.append({"line": index + 1, "checked": match[1] != " ", "text": match[2]})
        done = sum(1 for task in tasks if task["checked"])
        return {"tasks": tasks, "done": done, "open": len(tasks) - done}

    @staticmethod
    def parse_markdown_table(
        markdown: Annotated[str, Field(description=_MARKDOWN_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        table_index: Annotated[int, Field(description="Which table to convert, counting from zero in document order. Tables inside fenced code blocks are not counted. The default is zero, the first table. An index at or past the number of tables fails with an error naming this parameter.", ge=0)] = 0,
    ) -> PrebuiltToolOutput:
        """Convert one Markdown table into records keyed by its header cells, with the column names, the column alignments, and how many tables the document holds. Use it to read data out of a pipe table so it can be filtered, summed, or compared reliably. Cells are trimmed, escaped pipes become plain pipes, short rows are padded with empty text, extra cells are dropped, and a repeated column name gets a numeric suffix. Tables inside fenced code blocks are ignored, and tables are numbered from zero in document order. A document with no table, an index past the last table, or records longer than one million characters in total fail with an error."""
        # Find every table outside fenced code: a header row with pipes
        # followed by a delimiter row of hyphen cells.
        lines = PrebuiltToolSupport.split_lines(markdown)
        fenced = MarkdownHtmlToolFunctions._fenced_lines(MarkdownHtmlToolFunctions._fence_spans(lines), len(lines))
        tables = MarkdownHtmlToolFunctions._table_spans(lines, fenced)
        if not tables:
            raise PrebuiltToolSupport.argument_error("markdown", "the text holds no Markdown table outside fenced code", "a header row with pipes followed by a delimiter row of hyphen cells")
        if table_index >= len(tables):
            raise PrebuiltToolSupport.argument_error("table_index", f"the text holds {len(tables)} tables, so the index is past the last one", f"an index from 0 to {len(tables) - 1}")

        # Name the columns from the header and read the alignment of
        # each column from the colons of the delimiter row.
        start, end = tables[table_index]
        columns = MarkdownHtmlToolFunctions._column_names(MarkdownHtmlToolFunctions._split_table_row(lines[start]), "markdown")
        delimiters = MarkdownHtmlToolFunctions._split_table_row(lines[start + 1])[: len(columns)]
        alignment = [_ALIGNMENTS.get((cell.startswith(":"), cell.endswith(":"))) for cell in delimiters]
        alignment += [None] * (len(columns) - len(alignment))

        # Build the records one row at a time under the output cap.
        rows = (MarkdownHtmlToolFunctions._split_table_row(line) for line in lines[start + 2 : end])
        records = MarkdownHtmlToolFunctions._bounded_records(columns, rows, "markdown")
        return {"columns": columns, "records": records, "table_count": len(tables), "alignment": alignment}

    @staticmethod
    def extract_markdown_links(markdown: Annotated[str, Field(description=_MARKDOWN_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """List the links and images of a Markdown document in document order, with each one's text, URL, title, kind, and line. Use it to audit references, collect URLs, or check which images a document embeds. It reads inline links and images, autolinks in angle brackets, and reference links resolved through link definitions whose labels match without regard to case, while unresolved references and lines inside fenced code blocks are skipped. At most 1,000 links are listed while the count covers every link, and the tool has no failure case beyond the text length cap."""
        # Mark fenced code, then collect the link definitions first,
        # because a reference may come before its definition.
        lines = PrebuiltToolSupport.split_lines(markdown)
        fenced = MarkdownHtmlToolFunctions._fenced_lines(MarkdownHtmlToolFunctions._fence_spans(lines), len(lines))
        definitions = MarkdownHtmlToolFunctions._link_definitions(lines, fenced)

        # Count every link, then list them up to the item cap and the
        # character budget in a second pass.
        count = sum(1 for line_number, match in MarkdownHtmlToolFunctions._link_matches(lines, fenced) if MarkdownHtmlToolFunctions._link_item(line_number, match, definitions) is not None)
        candidates = (MarkdownHtmlToolFunctions._link_item(line_number, match, definitions) for line_number, match in MarkdownHtmlToolFunctions._link_matches(lines, fenced))
        links, truncated = PrebuiltToolSupport.cap_items(link for link in candidates if link is not None)
        return {"links": links, "count": count, "truncated": truncated}

    @staticmethod
    def extract_fenced_code_blocks(
        markdown: Annotated[str, Field(description="The Markdown document whose fenced code blocks are extracted, given as plain text. Line breaks may be CRLF, LF, or a lone CR, and line numbers in the result are 1-based. Indented code blocks without fences are not extracted. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        language: Annotated[str | None, Field(description="The language whose blocks to keep, compared with the first word of each fence's info string without regard to case. When it is null, every block is returned. Blocks without a language never match a filter. It must hold between one and two hundred characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)] = None,
    ) -> PrebuiltToolOutput:
        """Extract the fenced code blocks of a Markdown document, each with its language, its code, and the lines of its opening and closing fences. Use it to pull runnable snippets, configuration files, or commands out of documentation or a model's own answer. Fences are three or more backticks or tildes, the language is the first word after the opening fence or null, and the optional filter compares languages without regard to case. An unclosed block runs to the last line of the document, and the tool has no failure case beyond its caps."""
        # Find every fenced block, keeping only the chosen language.
        lines = PrebuiltToolSupport.split_lines(markdown)
        wanted = None if language is None else language.casefold()
        spans = [span for span in MarkdownHtmlToolFunctions._fence_spans(lines) if wanted is None or (span[2] is not None and span[2].casefold() == wanted)]

        # The code is the lines between the fences; an unclosed block
        # keeps every line to the end of the document.
        blocks = [
            {"language": block_language, "code": "\n".join(lines[start + 1 : end if closed else end + 1]), "start_line": start + 1, "end_line": end + 1}
            for start, end, block_language, closed in spans
        ]
        return {"blocks": blocks, "count": len(blocks)}

    @staticmethod
    def html_table_to_records(
        html_text: Annotated[str, Field(description=_HTML_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        table_index: Annotated[int, Field(description="Which top-level table to convert, counting from zero in document order. Tables nested inside another table's cells are not counted. The default is zero, the first table. An index at or past the number of tables fails with an error naming this parameter.", ge=0)] = 0,
    ) -> PrebuiltToolOutput:
        """Convert one HTML table into records keyed by its header cells, with the column names and the number of top-level tables in the document. Use it to read tabular data out of a web page or an HTML report so it can be filtered or compared reliably. A first row made only of header cells names the columns, otherwise the columns are numbered, colspan repeats a cell, and a nested table's text joins its enclosing cell. Malformed or unclosed tags never cause a failure, and tables are numbered from zero in document order. A document with no table, an index past the last table, or records longer than one million characters in total fail with an error."""
        # Parse the HTML into top-level tables of rows of cells; the
        # parser gives up only on a few broken marked sections, and the
        # tables read before that point are kept.
        parser = MarkdownHtmlToolFunctions._TableParser()
        with contextlib.suppress(AssertionError):
            parser.feed(html_text)
            parser.close()
        tables = parser.finish()
        if not tables:
            raise PrebuiltToolSupport.argument_error("html_text", "the HTML holds no table", "HTML with at least one table element")
        if table_index >= len(tables):
            raise PrebuiltToolSupport.argument_error("table_index", f"the HTML holds {len(tables)} top-level tables, so the index is past the last one", f"an index from 0 to {len(tables) - 1}")

        # A first row of header cells names the columns; otherwise the
        # longest row sets how many numbered columns there are.
        rows = tables[table_index]
        if rows and all(is_header for is_header, _, _ in rows[0]):
            columns = MarkdownHtmlToolFunctions._column_names((text for _, text, span in rows[0] for _ in range(span)), "html_text")
            body = rows[1:]
        else:
            width = max((sum(span for _, _, span in row) for row in rows), default=0)
            columns = MarkdownHtmlToolFunctions._column_names((f"column_{number}" for number in range(1, width + 1)), "html_text")
            body = rows

        # Build the records one row and one colspan copy at a time
        # under the output cap.
        cells = ((text for _, text, span in row for _ in range(span)) for row in body)
        records = MarkdownHtmlToolFunctions._bounded_records(columns, cells, "html_text")
        return {"columns": columns, "records": records, "table_count": len(tables)}

    @staticmethod
    def extract_html_links(
        html_text: Annotated[str, Field(description=_HTML_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        base_url: Annotated[str | None, Field(description="The absolute URL that relative link addresses are resolved against, the way a browser resolves them. When it is null, every address is returned exactly as written in its href attribute. It may hold at most ten thousand characters. A URL that cannot be parsed fails with an error naming this parameter.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)] = None,
    ) -> PrebuiltToolOutput:
        """List the hyperlinks of an HTML document in document order, with each link's URL, its visible text, and its rel attribute. Use it to collect the links of a web page, check where navigation points, or gather the sources cited in an HTML report. With a base URL, every link address is resolved against it the way a browser would, and link text has its whitespace collapsed. Malformed HTML never causes a failure, at most 1,000 links are listed while the count covers every link, and a base URL that cannot be parsed fails with an error naming base_url."""
        # Check the base URL once, so a broken one fails clearly instead
        # of silently leaving every link unresolved.
        if base_url is not None:
            try:
                urlsplit(base_url)
            except ValueError as exc:
                raise PrebuiltToolSupport.argument_error("base_url", "the URL cannot be parsed", "an absolute URL such as a page address") from exc

        # Read the href, text, and rel of every anchor element; the
        # parser gives up only on a few broken marked sections.
        parser = MarkdownHtmlToolFunctions._LinkParser()
        with contextlib.suppress(AssertionError):
            parser.feed(html_text)
            parser.close()
        anchors = parser.finish()

        # List the links up to the item cap and the character budget,
        # resolving each address only when it is listed.
        items = ({"url": MarkdownHtmlToolFunctions._joined_url(base_url, href), "text": text, "rel": rel} for href, text, rel in anchors)
        links, truncated = PrebuiltToolSupport.cap_items(items)
        return {"links": links, "count": len(anchors), "truncated": truncated}

    @staticmethod
    def _fence_spans(lines: Sequence[str]) -> list[tuple[int, int, str | None, bool]]:
        """Find every fenced code block as its opening line index, closing or last line index, language, and whether it was closed."""
        spans: list[tuple[int, int, str | None, bool]] = []
        opening: tuple[int, str, str | None] | None = None
        for index, line in enumerate(lines):
            if opening is None:
                # A backtick fence may not hold a backtick in its info
                # string; the language is the info string's first word.
                match = _FENCE_OPEN.fullmatch(line)
                if match is not None and not (match["fence"].startswith("`") and "`" in match["info"]):
                    words = match["info"].split()
                    opening = (index, match["fence"], words[0] if words else None)
                continue
            # A closing fence uses the same character, at least as many.
            closing = _FENCE_CLOSE.fullmatch(line)
            if closing is not None and closing["fence"][0] == opening[1][0] and len(closing["fence"]) >= len(opening[1]):
                spans.append((opening[0], index, opening[2], True))
                opening = None
        if opening is not None:
            spans.append((opening[0], len(lines) - 1, opening[2], False))
        return spans

    @staticmethod
    def _fenced_lines(spans: Iterable[tuple[int, int, str | None, bool]], line_count: int) -> list[bool]:
        """Mark every line that is a fence or lies inside a fenced code block."""
        fenced = [False] * line_count
        for start, end, _, _ in spans:
            fenced[start : end + 1] = [True] * (end + 1 - start)
        return fenced

    @staticmethod
    def _heading_entries(lines: Sequence[str], fenced: Sequence[bool]) -> list[tuple[int, str, int]]:
        """Find the ATX and Setext headings outside fenced code as level, text, and 1-based line."""
        entries: list[tuple[int, str, int]] = []
        for index, line in enumerate(lines):
            atx = None if fenced[index] else _ATX_HEADING.fullmatch(line)
            if atx is not None:
                text = _ATX_CLOSING.sub("", (atx["text"] or "").strip(), count=1).strip()
                entries.append((len(atx["hashes"]), text, index + 1))
                continue
            # A Setext underline turns the plain line above it into a
            # heading, unless that line is blank, fenced, or a heading.
            above = lines[index - 1] if index > 0 and not fenced[index - 1] else ""
            is_underline = not fenced[index] and _SETEXT_UNDERLINE.fullmatch(line) is not None
            if is_underline and above.strip() and _ATX_HEADING.fullmatch(above) is None and _SETEXT_UNDERLINE.fullmatch(above) is None:
                entries.append((1 if line.strip().startswith("=") else 2, above.strip(), index))
        return entries

    @staticmethod
    def _unique_anchors(texts: Iterable[str]) -> list[str]:
        """Turn heading texts into GitHub anchors, numbering a repeated anchor with -1, -2, and so on."""
        occurrences: dict[str, int] = {}
        anchors: list[str] = []
        for text in texts:
            base = "".join(character for character in text.lower() if character.isalpha() or character.isdecimal() or character in " -_").replace(" ", "-")
            anchor = base
            while anchor in occurrences:
                occurrences[base] += 1
                anchor = f"{base}-{occurrences[base]}"
            occurrences[anchor] = 0
            anchors.append(anchor)
        return anchors

    @staticmethod
    def _table_spans(lines: Sequence[str], fenced: Sequence[bool]) -> list[tuple[int, int]]:
        """Find every pipe table outside fenced code as its header line index and the index just past its last row."""
        spans: list[tuple[int, int]] = []
        index = 0
        while index + 1 < len(lines):
            header, delimiter = lines[index], lines[index + 1]
            unfenced = not fenced[index] and not fenced[index + 1]
            if not (unfenced and _UNESCAPED_PIPE.search(header) and "|" in delimiter and _DELIMITER_ROW.fullmatch(delimiter)):
                index += 1
                continue
            # The body runs while lines are outside fences and hold an
            # unescaped pipe.
            end = index + 2
            while end < len(lines) and not fenced[end] and _UNESCAPED_PIPE.search(lines[end]):
                end += 1
            spans.append((index, end))
            index = end
        return spans

    @staticmethod
    def _split_table_row(line: str) -> list[str]:
        """Split one pipe-table row into trimmed cells, dropping the outer pipes and unescaping escaped pipes."""
        body = line.strip()
        if body.startswith("|"):
            body = body[1:]
        if body.endswith("|") and not body.endswith("\\|"):
            body = body[:-1]
        return [cell.strip().replace("\\|", "|") for cell in _UNESCAPED_PIPE.split(body)]

    @staticmethod
    def _column_names(names: Iterable[str], parameter_name: str) -> list[str]:
        """Make column names unique with _2, _3, and so on, refusing a column list over the output cap."""
        columns: list[str] = []
        taken: set[str] = set()
        suffixes: dict[str, int] = {}
        used = 0
        for name in names:
            candidate = name
            while candidate in taken:
                suffixes[name] = suffixes.get(name, 1) + 1
                candidate = f"{name}_{suffixes[name]}"
            # @intent prebuilt-table-output-cap
            # A colspan or a wide header can name more columns than the
            # output cap holds, so the names are measured as they are
            # made and a list past the cap fails before it is finished.
            used += len(json.dumps(candidate, ensure_ascii=False)) + 1
            if used > PREBUILT_MAX_TEXT_CHARS:
                raise PrebuiltToolSupport.argument_error(parameter_name, f"the column names would pass {PREBUILT_MAX_TEXT_CHARS} characters", _OUTPUT_CAP_EXPECTED)
            taken.add(candidate)
            columns.append(candidate)
        return columns

    @staticmethod
    def _bounded_records(columns: Sequence[str], rows: Iterable[Iterable[str]], parameter_name: str) -> list[dict[str, str]]:
        """Build one record per row, padding or cutting it to the columns, and refuse records whose compact JSON passes the output cap."""
        width = len(columns)
        fixed = 2 + sum(len(json.dumps(name, ensure_ascii=False)) + 1 for name in columns) + max(width - 1, 0)
        records: list[dict[str, str]] = []
        used = 0
        for row in rows:
            cells = list(itertools.islice(row, width))
            cells += [""] * (width - len(cells))
            # @intent prebuilt-table-output-cap
            # Padding and colspan copies let a small input make a huge
            # table, so each record's compact JSON size is added before
            # the record is kept, and passing the cap fails the call.
            used += fixed + sum(len(json.dumps(cell, ensure_ascii=False)) for cell in cells)
            if used > PREBUILT_MAX_TEXT_CHARS:
                raise PrebuiltToolSupport.argument_error(parameter_name, f"the records would pass {PREBUILT_MAX_TEXT_CHARS} characters", _OUTPUT_CAP_EXPECTED)
            records.append(dict(zip(columns, cells, strict=True)))
        return records

    @staticmethod
    def _link_definitions(lines: Sequence[str], fenced: Sequence[bool]) -> dict[str, tuple[str, str | None]]:
        """Collect link reference definitions outside fenced code, keyed by case-folded label; the first definition of a label wins."""
        definitions: dict[str, tuple[str, str | None]] = {}
        for index, line in enumerate(lines):
            match = None if fenced[index] else _LINK_DEFINITION.fullmatch(line)
            label = " ".join(match["label"].split()).casefold() if match is not None else ""
            if match is not None and label:
                url = match["angle"] if match["angle"] is not None else match["url"]
                definitions.setdefault(label, (url, match["title"][1:-1] if match["title"] else None))
        return definitions

    @staticmethod
    def _link_matches(lines: Sequence[str], fenced: Sequence[bool]) -> Iterator[tuple[int, re.Match[str]]]:
        """Yield every link, image, and autolink match outside fenced code and definitions, with its 1-based line, in document order."""
        for index, line in enumerate(lines):
            if fenced[index] or _LINK_DEFINITION.fullmatch(line) is not None:
                continue
            for outer in _MARKDOWN_LINK.finditer(line):
                yield index + 1, outer
                # A link cannot hold another link, but its text can
                # hold images, such as a badge that links somewhere.
                if outer["text"] and not outer["bang"]:
                    yield from ((index + 1, inner) for inner in _MARKDOWN_LINK.finditer(outer["text"]) if inner["bang"])

    @staticmethod
    def _link_item(line_number: int, match: re.Match[str], definitions: Mapping[str, tuple[str, str | None]]) -> dict[str, object] | None:
        """Describe one link match, resolving a reference through the definitions, or return None for an unresolved reference."""
        if match["autolink"] is not None:
            return {"text": match["autolink"], "url": match["autolink"], "title": None, "kind": MarkdownLinkKind.AUTOLINK.value, "line": line_number}
        kind = MarkdownLinkKind.IMAGE if match["bang"] else MarkdownLinkKind.INLINE if match["label"] is None else MarkdownLinkKind.REFERENCE
        if match["label"] is None:
            destination = match["destination"]
            url = destination[1:-1] if destination.startswith("<") else destination
            title = match["title"][1:-1] if match["title"] else None
        else:
            # An empty label, as in a collapsed reference, means the
            # text is the label.
            target = definitions.get(" ".join((match["label"] or match["text"]).split()).casefold())
            if target is None:
                return None
            url, title = target
        return {"text": match["text"], "url": url, "title": title, "kind": kind.value, "line": line_number}

    @staticmethod
    def _joined_url(base_url: str | None, href: str) -> str:
        """Resolve a link address against the base URL, keeping the address as written when there is no base or it cannot be joined."""
        if base_url is None:
            return href
        try:
            return urljoin(base_url, href)
        except ValueError:
            return href

    class _TableParser(HTMLParser):
        """Collects the top-level tables of an HTML document as rows of (is header, text, colspan) cells."""

        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.tables: list[list[_TableRow]] = []
            self.open_tables = 0
            self.row: _TableRow | None = None
            self.cell: list[str] | None = None
            self.cell_is_header = False
            self.cell_span = 1
            self.in_raw_text = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            """Open tables, rows, and cells of the top-level table, and keep other block tags as word breaks."""
            if tag in _RAW_TEXT_TAGS:
                self.in_raw_text = True
                return
            if tag == "table":
                self.open_tables += 1
                if self.open_tables == 1:
                    self.tables.append([])
                    return
            elif self.open_tables == 1 and tag in _TABLE_STRUCTURE_TAGS:
                self._close_cell()
                if tag == "tr":
                    self._close_row()
                    self.row = []
                else:
                    self._open_cell(tag == "th", attrs)
                return
            if self.cell is not None and tag in PREBUILT_HTML_BLOCK_TAGS:
                self.cell.append(" ")

        def handle_endtag(self, tag: str) -> None:
            """Close cells, rows, and the top-level table, and keep other block tags as word breaks."""
            if tag in _RAW_TEXT_TAGS:
                self.in_raw_text = False
                return
            if self.open_tables == 1 and tag in _TABLE_STRUCTURE_TAGS:
                self._close_cell()
                if tag not in _TABLE_CELL_TAGS:
                    self._close_row()
                if tag == "table":
                    self.open_tables = 0
                return
            if tag == "table" and self.open_tables > 1:
                self.open_tables -= 1
            if self.cell is not None and tag in PREBUILT_HTML_BLOCK_TAGS:
                self.cell.append(" ")

        def handle_data(self, data: str) -> None:
            """Add text to the open cell of the top-level table, nested tables included."""
            if self.cell is not None and not self.in_raw_text:
                self.cell.append(data)

        def finish(self) -> list[list[_TableRow]]:
            """Close any cell and row left open by unclosed tags and return the tables."""
            self._close_cell()
            self._close_row()
            return self.tables

        def _open_cell(self, is_header: bool, attrs: list[tuple[str, str | None]]) -> None:
            # A cell outside any row starts one; the colspan comes from
            # its leading digits, and zero or junk counts as one.
            if self.row is None:
                self.row = []
            value = next((value for name, value in attrs if name == "colspan"), None)
            found = _SPAN_DIGITS.match(value or "")
            digits = found[1].lstrip("0") if found is not None else ""
            span = _MAX_SPAN if len(digits) > _MAX_SPAN_DIGITS else min(int(digits or "1"), _MAX_SPAN)
            self.cell, self.cell_is_header, self.cell_span = [], is_header, span

        def _close_cell(self) -> None:
            # The cell's text is kept with its whitespace collapsed.
            if self.cell is not None and self.row is not None:
                self.row.append((self.cell_is_header, " ".join("".join(self.cell).split()), self.cell_span))
            self.cell = None

        def _close_row(self) -> None:
            # A row with no cells is dropped.
            if self.row and self.tables:
                self.tables[-1].append(self.row)
            self.row = None

    class _LinkParser(HTMLParser):
        """Collects the href, collapsed text, and rel of every anchor element in document order."""

        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.anchors: list[tuple[str, str, str | None]] = []
            self.open_anchor: tuple[str, str | None] | None = None
            self.parts: list[str] = []
            self.in_raw_text = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            """Start a link at an anchor with an href, closing any link still open, and keep block tags as word breaks."""
            if tag in _RAW_TEXT_TAGS:
                self.in_raw_text = True
                return
            if tag != "a":
                if self.open_anchor is not None and tag in PREBUILT_HTML_BLOCK_TAGS:
                    self.parts.append(" ")
                return
            self._close_anchor()
            hrefs = [value or "" for name, value in attrs if name == "href"]
            if hrefs:
                rel = next((value for name, value in attrs if name == "rel"), None)
                self.open_anchor, self.parts = (hrefs[0].strip(_URL_WHITESPACE), rel), []

        def handle_endtag(self, tag: str) -> None:
            """Finish the open link at its closing anchor tag."""
            if tag in _RAW_TEXT_TAGS:
                self.in_raw_text = False
            elif tag == "a":
                self._close_anchor()
            elif self.open_anchor is not None and tag in PREBUILT_HTML_BLOCK_TAGS:
                self.parts.append(" ")

        def handle_data(self, data: str) -> None:
            """Add text to the open link."""
            if self.open_anchor is not None and not self.in_raw_text:
                self.parts.append(data)

        def finish(self) -> list[tuple[str, str, str | None]]:
            """Close a link left open by a missing end tag and return every link."""
            self._close_anchor()
            return self.anchors

        def _close_anchor(self) -> None:
            # The link text is kept with its whitespace collapsed.
            if self.open_anchor is not None:
                href, rel = self.open_anchor
                self.anchors.append((href, " ".join("".join(self.parts).split()), rel))
            self.open_anchor, self.parts = None, []

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.extract_markdown_headings,
            cls.extract_markdown_tasks,
            cls.parse_markdown_table,
            cls.extract_markdown_links,
            cls.extract_fenced_code_blocks,
            cls.html_table_to_records,
            cls.extract_html_links,
        )


__all__ = ["MarkdownHtmlToolFunctions"]
