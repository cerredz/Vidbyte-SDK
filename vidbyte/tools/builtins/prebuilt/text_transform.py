"""FILE: vidbyte/tools/builtins/prebuilt/text_transform.py

PURPOSE: Defines TextTransformToolFunctions, the ten prebuilt tools that rewrite a text: reversing it, converting identifier case, shortening it, replacing a literal string, removing duplicate lines, sorting lines, stripping HTML tags, splitting it into chunks, extracting a line range, and filling a template.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the TEXT_TRANSFORM category is chosen. Builds on PrebuiltToolSupport in _support.py for the line, word, and numeric text rules, JSON parsing, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Tools that can grow their input, replace_all_occurrences and fill_text_template, first predict the output length from the matches and refuse an output over the text cap before building anything. HTML is read by a private HTMLParser subclass, the only class that needs inheritance here.
FUNCTION INVENTORY: reverse_text, convert_identifier_case, shorten_text, replace_all_occurrences, deduplicate_lines, sort_text_lines, strip_html_tags, split_text_into_chunks, extract_line_range, and fill_text_template are the tools; _rebuilt_text joins lines under the line rule; _identifier_words splits an identifier into words; _cut_characters makes a character cut; _natural_key and _numeric_order serve the natural and numeric sorts; _chunk_end finds a chunk's break point; _template_values, _filled_size, and _filled_text render a template; _HtmlTextCollector gathers the text of HTML; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new transform tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.13, and its entry in tool_functions. A tool whose output can grow past its input predicts the output length and refuses it before building it.
WHAT NOT TO DO IN THIS FILE: 1. Do not split words or lines with a local rule; use PrebuiltToolSupport so every category agrees. 2. Do not pass replacement text to re.sub unescaped, because backslashes and group references would be read as template syntax. 3. Do not build an amplified output before its predicted length has been checked against PREBUILT_MAX_TEXT_CHARS. 4. Do not iterate a set or a hash-ordered container when building an output.
KNOWN EDGE CASES: Rebuilt text joins lines with LF and keeps one trailing LF only when the input ended with a line break. A case-insensitive replacement folds one code point at a time, so a sharp s never matches a double s. Python 3.11's HTMLParser raises AssertionError on a marked section with an unknown keyword, so the collector reads such a section as a bogus comment instead. Markup left open at the end of the input is dropped by PrebuiltToolSupport.parse_html before the parser closes (EC-47), because unpatched CPython re-scans it once for every < (CVE-2025-6069) and the fixed releases give nothing from it. A character cut that lands right before whitespace is already at a word boundary and does not move back.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.13, section 9.2 items 6, 8, 12, and 15); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_text.py, tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py, and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from itertools import islice
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_HTML_BLOCK_TAGS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_REPORTED_NAMES,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_MIN_CHUNK_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    IdentifierCase,
    MissingPlaceholderPolicy,
    SortMode,
    TextUnit,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_LINE_BREAK_ENDINGS = ("\n", "\r")
_LETTER_OR_DIGIT_RUN = re.compile(r"[^\W_]+")
_NATURAL_RUN = re.compile(r"[0-9]+|[^0-9]+")
_ASCII_DIGITS = "0123456789"
_SKIPPED_ELEMENTS = frozenset({"script", "style"})
_SPACE_RUN = re.compile(r"[ \t]+")
_EXTRA_LINE_BREAKS = re.compile(r"\n{3,}")
_TEMPLATE_FIELD = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}")
_REPORTED_NAME_LENGTH = 60
_MISSING = object()
_OVERLAP_DIVISOR = 4
_WINDOW_DIVISOR = 2

# Chunk break points in order of preference; group 1 ends at the break
# point. A line break is CRLF, a lone LF, or a lone CR, so a CRLF pair
# is never split, and the blank-line pattern is a lookahead so that
# overlapping blank lines all count.
_LINE_BREAK = r"(?:\r\n|(?<!\r)\n|\r(?!\n))"
_CHUNK_BREAK_PATTERNS = (
    re.compile(rf"(?={_LINE_BREAK}[ \t]*({_LINE_BREAK}))"),
    re.compile(rf"({_LINE_BREAK})"),
    re.compile(r"[.!?…](\s)"),
    re.compile(r"(\s)"),
)

_TEXT_PARAMETER_DESCRIPTION = "The text to transform, given as plain characters. Lengths and positions count Unicode code points, so an emoji or an accented letter counts once. Line breaks may be CRLF, LF, or a lone CR. The text may hold at most one million characters."
_OUTPUT_CAP_EXPECTED = "inputs whose result holds at most 1,000,000 characters"


class TextTransformToolFunctions:
    """The text_transform category: reversing, recasing, shortening, replacing, sorting, chunking, and templating text."""

    class _HtmlTextCollector(HTMLParser):
        """Collects the text of HTML, dropping scripts, styles, and comments and turning block tags into line breaks."""

        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.pieces: list[str] = []
            self.skipped = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            """Start skipping inside a script or style, or insert a line break for a block tag."""
            if tag in _SKIPPED_ELEMENTS:
                self.skipped += 1
            elif tag in PREBUILT_HTML_BLOCK_TAGS:
                self.pieces.append("\n")

        def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            """Insert one line break for a self-closing block tag; a self-closing script holds nothing to skip."""
            if tag in PREBUILT_HTML_BLOCK_TAGS:
                self.pieces.append("\n")

        def handle_endtag(self, tag: str) -> None:
            """Stop skipping after a script or style, or insert a line break for a block tag."""
            if tag in _SKIPPED_ELEMENTS:
                self.skipped = max(self.skipped - 1, 0)
            elif tag in PREBUILT_HTML_BLOCK_TAGS:
                self.pieces.append("\n")

        def handle_data(self, data: str) -> None:
            """Keep text that is outside every script and style."""
            if not self.skipped:
                self.pieces.append(data)

        def parse_marked_section(self, i: int, report: bool = True) -> int:
            """Read a marked section, treating one with an unknown keyword as a bogus comment instead of failing."""
            # Python 3.11 raises AssertionError for a marked
            # section whose keyword it does not know, which would
            # break the promise that malformed HTML never fails.
            try:
                return super().parse_marked_section(i, report)
            except AssertionError:
                return self.parse_bogus_comment(i, report)

    @staticmethod
    def reverse_text(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        unit: Annotated[TextUnit, Field(description="What to reverse the text by. Characters reverses Unicode code points, so combining marks may move off their base letter. Words reverses the words and joins them with single spaces, dropping the punctuation between them. Lines reverses the line order and joins the lines with LF line breaks, and the default is characters.")] = TextUnit.CHARACTERS,
    ) -> PrebuiltToolOutput:
        """Reverse a text by characters, by words, or by lines. Use it for palindrome checks, for reversing a list written one item per line, or for any reversal that is easy to get wrong by reading. Characters reverse Unicode code points, words are joined with single spaces and lose the punctuation between them, and lines are joined with LF line breaks. The tool has no failure case beyond the text length cap."""
        match unit:
            case TextUnit.WORDS:
                reversed_text = " ".join(word for _, word in reversed(PrebuiltToolSupport.split_words(text)))
            case TextUnit.LINES:
                reversed_text = TextTransformToolFunctions._rebuilt_text(PrebuiltToolSupport.split_lines(text)[::-1], text)
            case _:
                reversed_text = text[::-1]
        return {"text": reversed_text}

    @staticmethod
    def convert_identifier_case(
        text: Annotated[str, Field(description="The identifier or phrase to rewrite, written in any naming style. Words split at characters that are not letters or digits, at changes from lowercase to uppercase, and at the end of an uppercase acronym. Digits stay with the word before them, while an uppercase letter after a digit starts a new word. The text may hold at most ten thousand characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        target: Annotated[IdentifierCase, Field(description="The naming style to produce. Snake joins lowercase words with underscores, screaming_snake does the same in uppercase, kebab joins lowercase words with hyphens, and dot joins them with periods. Camel keeps the first word lowercase and capitalizes the rest, pascal capitalizes every word, and title joins capitalized words with spaces. Capitalizing a word uppercases only its first character.")],
    ) -> PrebuiltToolOutput:
        """Rewrite an identifier or phrase in snake, screaming snake, kebab, camel, Pascal, dot, or title case, and list the lowercase words found. Use it to rename variables, keys, and labels consistently across naming conventions. Words split at characters that are not letters or digits, at lowercase-to-uppercase changes, and at acronym ends, digits stay with the word before them, and an uppercase letter after a digit starts a new word. Text with no letters or digits fails with an error naming text."""
        # Split the text into lowercase words, refusing text with none.
        words = TextTransformToolFunctions._identifier_words(text)
        if not words:
            raise PrebuiltToolSupport.argument_error("text", "the text holds no letters or digits", "an identifier or phrase with at least one letter or digit")

        # Join the words in the target style.
        capitalized = [word[:1].upper() + word[1:] for word in words]
        match target:
            case IdentifierCase.SNAKE:
                joined = "_".join(words)
            case IdentifierCase.SCREAMING_SNAKE:
                joined = "_".join(word.upper() for word in words)
            case IdentifierCase.KEBAB:
                joined = "-".join(words)
            case IdentifierCase.CAMEL:
                joined = words[0] + "".join(capitalized[1:])
            case IdentifierCase.PASCAL:
                joined = "".join(capitalized)
            case IdentifierCase.DOT:
                joined = ".".join(words)
            case _:
                joined = " ".join(capitalized)
        return {"text": joined, "words": words}

    @staticmethod
    def shorten_text(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        max_length: Annotated[int, Field(description="The largest allowed length, counted in the chosen unit. For characters, the result including the ellipsis is at most this long. For words and lines, this many units are kept and the ellipsis is added after them. The value must be between 1 and one million.", ge=1, le=PREBUILT_MAX_TEXT_CHARS)],
        unit: Annotated[TextUnit, Field(description="The unit that max_length counts. Characters counts Unicode code points, words counts runs of letters and digits, and lines counts the lines of the text. The original length in the result is reported in the same unit. The default is characters.")] = TextUnit.CHARACTERS,
        ellipsis: Annotated[str, Field(description="The marker added where the text is cut, which may be empty. For characters it counts toward max_length, so it must be shorter than max_length. For words it follows after a space, and for lines it follows on a new line. The default is a single ellipsis character.", max_length=PREBUILT_MAX_NAME_CHARS)] = "…",
        break_on_word: Annotated[bool, Field(description="Whether a character cut moves back to the last whitespace inside the allowed span, so no word is split. Trailing whitespace before the ellipsis is then removed. When the span holds no whitespace, the cut stays where it is. The setting only affects the characters unit, and the default is true.")] = True,
    ) -> PrebuiltToolOutput:
        """Shorten a text to a maximum length in characters, words, or lines, adding an ellipsis when it cuts. Use it to fit a text into a title, a preview, a message limit, or a context budget. For characters the result including the ellipsis fits max_length and the cut can move back to a word boundary, while for words and lines the first max_length units are kept and the ellipsis follows them. Text within the limit comes back unchanged, and a character ellipsis at least as long as max_length fails with an error naming ellipsis."""
        if unit is TextUnit.CHARACTERS and len(ellipsis) >= max_length:
            raise PrebuiltToolSupport.argument_error("ellipsis", f"the ellipsis has {len(ellipsis)} characters but max_length is {max_length}", "an ellipsis shorter than max_length")

        # Measure the text in the chosen unit; text within the limit
        # comes back unchanged.
        words = PrebuiltToolSupport.split_words(text) if unit is TextUnit.WORDS else []
        lines = PrebuiltToolSupport.split_lines(text) if unit is TextUnit.LINES else []
        original_length = {TextUnit.WORDS: len(words), TextUnit.LINES: len(lines)}.get(unit, len(text))
        if original_length <= max_length:
            return {"text": text, "shortened": False, "original_length": original_length}

        # Keep the first max_length units and add the ellipsis after a
        # space, after a line break, or inside the character limit.
        match unit:
            case TextUnit.WORDS:
                position, word = words[max_length - 1]
                shortened = text[: position + len(word)] + (f" {ellipsis}" if ellipsis else "")
            case TextUnit.LINES:
                shortened = "\n".join(lines[:max_length]) + (f"\n{ellipsis}" if ellipsis else "")
            case _:
                shortened = TextTransformToolFunctions._cut_characters(text, max_length - len(ellipsis), break_on_word) + ellipsis
        return {"text": shortened, "shortened": True, "original_length": original_length}

    @staticmethod
    def replace_all_occurrences(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        find: Annotated[str, Field(description="The literal text to find, which is never read as a pattern. It must hold at least one character and at most ten thousand. Matches are found from left to right without overlapping. Characters that are special in regular expressions only match themselves.", min_length=1, max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        replacement: Annotated[str, Field(description="The literal text that replaces each match, which may be empty. Backslashes and group references have no special meaning here. It may hold at most ten thousand characters. A result longer than one million characters fails with an error naming this parameter.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        case_sensitive: Annotated[bool, Field(description="Whether uppercase and lowercase must match exactly. When false, the match folds case one code point at a time, so a sharp s never matches a double s. The replacement is inserted as given either way. The default is true.")] = True,
        max_replacements: Annotated[int | None, Field(description="The largest number of matches to replace, counting from the start of the text. Matches past this number are left unchanged. Null means that every match is replaced. The value must be at least 1 when given.", ge=1)] = None,
    ) -> PrebuiltToolOutput:
        """Replace every occurrence of a literal string in a text, optionally ignoring case or capping how many are replaced, and report the number of replacements. Use it for exact find-and-replace edits instead of rewriting a text by hand. Matching is literal, left to right, and non-overlapping, and the replacement is inserted exactly as given. A result longer than one million characters is refused before it is built, with an error naming replacement."""
        # Count the matches that will be replaced and the characters
        # they cover, without building any output yet.
        pattern = re.compile(re.escape(find), 0 if case_sensitive else re.IGNORECASE)
        replaced = covered = 0
        for match in islice(pattern.finditer(text), max_replacements):
            replaced += 1
            covered += match.end() - match.start()

        # @intent prebuilt-output-cap
        # Many short matches with a long replacement can multiply the
        # text, so the predicted length is checked before the result
        # exists.
        predicted = len(text) - covered + replaced * len(replacement)
        if predicted > PREBUILT_MAX_TEXT_CHARS:
            raise PrebuiltToolSupport.argument_error("replacement", f"the result would hold {predicted} characters", _OUTPUT_CAP_EXPECTED)

        # Escape backslashes so the replacement is inserted literally.
        result = pattern.sub(replacement.replace("\\", "\\\\"), text, count=replaced) if replaced else text
        return {"text": result, "replacements": replaced}

    @staticmethod
    def deduplicate_lines(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        case_sensitive: Annotated[bool, Field(description="Whether lines that differ only in case count as different lines. When false, lines are compared by their case-folded form. Kept lines are never changed, so the first spelling stays. The default is true.")] = True,
        ignore_surrounding_whitespace: Annotated[bool, Field(description="Whether whitespace at the start and end of a line is ignored when lines are compared. Kept lines still keep their own whitespace. Blank lines are compared like any other line. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Remove repeated lines from a text, keeping the first occurrence of each line in its original position. Use it to clean up lists, logs, or pasted data that hold duplicate entries. Lines may be compared without regard to case or surrounding whitespace, but kept lines are never changed, and the result joins lines with LF line breaks. The tool reports how many lines were kept and removed, and it has no failure case beyond the text length cap."""
        # Compare each line in its folded form and keep the first line
        # with each form.
        lines = PrebuiltToolSupport.split_lines(text)
        seen: set[str] = set()
        kept: list[str] = []
        for line in lines:
            stripped = line.strip() if ignore_surrounding_whitespace else line
            key = stripped if case_sensitive else stripped.casefold()
            if key not in seen:
                seen.add(key)
                kept.append(line)
        return {"text": TextTransformToolFunctions._rebuilt_text(kept, text), "kept": len(kept), "removed": len(lines) - len(kept)}

    @staticmethod
    def sort_text_lines(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        mode: Annotated[SortMode, Field(description="How lines are compared. Text sorts by code point, case_insensitive sorts by case-folded text with ties broken by code point, and length sorts by length and then by code point. Natural compares runs of digits by numeric value and other runs without regard to case, while numeric sorts the lines that hold a number by value and keeps the other lines after them in input order. Every sort is stable, and the default is text.")] = SortMode.TEXT,
        descending: Annotated[bool, Field(description="Whether to sort from the largest key to the smallest. Lines with equal keys keep their input order either way, because the sort stays stable. In numeric mode, lines that are not numbers stay last in input order. The default is false.")] = False,
        unique: Annotated[bool, Field(description="Whether to drop exact duplicate lines after sorting. Only the first copy of each line is kept, and lines are compared exactly. The line count in the result counts the lines that remain. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Sort the lines of a text by code point, without regard to case, in natural order, by numeric value, or by length. Use it to order a list, a set of file names, or numbers written one per line. Every sort is stable, descending keeps lines with equal keys in input order, and unique drops exact duplicates after sorting. The result joins lines with LF line breaks, and the tool has no failure case beyond the text length cap."""
        # Sort with the key of the chosen mode; Python's sort stays
        # stable when it is reversed.
        lines = PrebuiltToolSupport.split_lines(text)
        match mode:
            case SortMode.NUMERIC:
                ordered = TextTransformToolFunctions._numeric_order(lines, descending)
            case SortMode.NATURAL:
                ordered = sorted(lines, key=TextTransformToolFunctions._natural_key, reverse=descending)
            case SortMode.CASE_INSENSITIVE:
                ordered = sorted(lines, key=lambda line: (line.casefold(), line), reverse=descending)
            case SortMode.LENGTH:
                ordered = sorted(lines, key=lambda line: (len(line), line), reverse=descending)
            case _:
                ordered = sorted(lines, reverse=descending)

        # Drop exact duplicates after sorting when asked.
        if unique:
            ordered = list(dict.fromkeys(ordered))
        return {"text": TextTransformToolFunctions._rebuilt_text(ordered, text), "lines": len(ordered)}

    @staticmethod
    def strip_html_tags(
        html_text: Annotated[str, Field(description="The HTML to turn into plain text, given as markup characters. It may be a full document or a fragment, and malformed or unclosed markup is accepted. Scripts, styles, and comments are dropped, and character entities are decoded. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Turn HTML into readable plain text by removing tags, scripts, styles, and comments and decoding character entities. Use it to read the text of a web page or an HTML email without its markup. Block elements such as paragraphs, list items, and table cells become line breaks, runs of spaces collapse, each line is trimmed, and at most one blank line is kept between blocks. Malformed HTML never causes an error, so the tool has no failure case beyond the text length cap."""
        # Collect the text outside scripts and styles, with a line break
        # for each block tag; markup left open at the end gives nothing.
        collector = TextTransformToolFunctions._HtmlTextCollector()
        PrebuiltToolSupport.parse_html(collector, html_text)
        collected = "".join(collector.pieces).replace("\r\n", "\n").replace("\r", "\n")

        # Collapse spaces and tabs, strip each line, keep at most one
        # blank line in a row, and trim the result.
        collapsed = _SPACE_RUN.sub(" ", collected)
        stripped = "\n".join(line.strip(" ") for line in collapsed.split("\n"))
        return {"text": _EXTRA_LINE_BREAKS.sub("\n\n", stripped).strip()}

    @staticmethod
    def split_text_into_chunks(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        chunk_size: Annotated[int, Field(description="The largest chunk length in characters. A chunk ends at the best natural break point in the second half of this span, or at a hard cut when that half has none. The value must be between 100 and one million. Larger chunks give fewer and longer pieces.", ge=PREBUILT_MIN_CHUNK_CHARS, le=PREBUILT_MAX_TEXT_CHARS)],
        overlap: Annotated[int, Field(description="How many characters each chunk shares with the end of the chunk before it. The next chunk starts this many characters before the previous end. It must be at most a quarter of chunk_size, rounded down, or the call fails with an error. The default is 0.", ge=0, le=PREBUILT_MAX_TEXT_CHARS)] = 0,
    ) -> PrebuiltToolOutput:
        """Split a long text into chunks of at most chunk_size characters, preferring blank lines, then line breaks, then sentence ends, and then spaces as break points, with optional overlap. Use it to prepare a document for embedding, summarizing, or processing in pieces. Each chunk is an exact slice of the text with its start and end positions, and at most 1,000 chunks are listed while count covers every chunk. An overlap above a quarter of chunk_size fails with an error naming overlap."""
        if overlap > chunk_size // _OVERLAP_DIVISOR:
            raise PrebuiltToolSupport.argument_error("overlap", f"the overlap is {overlap}, which is more than a quarter of the chunk size", f"an overlap of at most {chunk_size // _OVERLAP_DIVISOR}")

        # Find every chunk's bounds first, so the count covers them all;
        # each step moves at least a quarter of a chunk forward.
        bounds: list[tuple[int, int]] = []
        start = 0
        while start < len(text):
            end = TextTransformToolFunctions._chunk_end(text, start, chunk_size)
            bounds.append((start, end))
            start = len(text) if end == len(text) else end - overlap

        # List the chunks up to the item cap and the character budget.
        chunks, truncated = PrebuiltToolSupport.cap_items({"index": index, "start": first, "end": last, "text": text[first:last]} for index, (first, last) in enumerate(bounds))
        return {"chunks": chunks, "count": len(bounds), "truncated": truncated}

    @staticmethod
    def extract_line_range(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        start_line: Annotated[int, Field(description="The 1-based number of the first line to return. A line ends at CRLF, LF, or CR, and a trailing line break does not start an extra empty line. A start past the last line fails with an error. The value must be at least 1.", ge=1)],
        end_line: Annotated[int | None, Field(description="The 1-based number of the last line to return, counted inclusively. Null means the last line of the text, and a number past the end is clipped to it. An end before the start fails with an error. The value must be at least 1 when given.", ge=1)] = None,
        number_lines: Annotated[bool, Field(description="Whether each returned line starts with its 1-based line number, a colon, and a space. The numbers are the line numbers in the original text. Line content is never changed. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Return a range of lines from a text by 1-based line numbers, optionally prefixed with their line numbers. Use it to quote or inspect part of a file without copying the whole text. An end past the last line is clipped, a missing end means the last line, and the selected lines are joined with LF line breaks. A start past the last line fails with an error naming start_line, and an end before the start fails with an error naming end_line."""
        # Check the range against the line count.
        lines = PrebuiltToolSupport.split_lines(text)
        if start_line > len(lines):
            raise PrebuiltToolSupport.argument_error("start_line", f"the text has {len(lines)} lines", f"a start line from 1 to {len(lines)}" if lines else "text with at least one line")
        if end_line is not None and end_line < start_line:
            raise PrebuiltToolSupport.argument_error("end_line", f"the end line {end_line} is before the start line {start_line}", "an end line at or after the start line")

        # Select the lines, number them when asked, and keep a trailing
        # break only when the range reaches the end of a text that had
        # one.
        last = len(lines) if end_line is None else min(end_line, len(lines))
        selected = [f"{number}: {line}" if number_lines else line for number, line in enumerate(lines[start_line - 1 : last], start=start_line)]
        trailing = "\n" if last == len(lines) and text.endswith(_LINE_BREAK_ENDINGS) else ""
        return {"text": "\n".join(selected) + trailing, "start_line": start_line, "end_line": last, "total_lines": len(lines)}

    @staticmethod
    def fill_text_template(
        template: Annotated[str, Field(description="The template text whose placeholders are filled. A placeholder is a name between double curly braces, optionally padded with spaces inside the braces. A name starts with a letter or an underscore, and dotted parts reach into nested objects. Text outside placeholders is copied unchanged, and the template may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        values_json: Annotated[str, Field(description="A JSON object that maps placeholder names to values. Strings are inserted raw, numbers and booleans as JSON, null as empty text, and objects and arrays as compact JSON. A value that is not a JSON object, or a result over one million characters, fails with an error naming this parameter. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        missing: Annotated[MissingPlaceholderPolicy, Field(description="What to do with a placeholder whose name has no value. Error fails the call and lists up to 20 missing names, keep leaves the placeholder as written, and empty removes it. Either way, the result lists the distinct missing names in order of first appearance. The default is error.")] = MissingPlaceholderPolicy.ERROR,
    ) -> PrebuiltToolOutput:
        """Fill placeholders written as a name between double curly braces in a template from a JSON object of values, with dotted names reaching into nested objects. Use it to render messages, prompts, or documents from structured data. Strings are inserted raw, other values as JSON, and a missing name either fails the call, stays as written, or is removed, depending on missing. Values that are not a JSON object, missing names under the error policy, and results over one million characters fail with an error naming values_json."""
        # Read the values and render each distinct placeholder name
        # once.
        values = PrebuiltToolSupport.parse_json_text(values_json, "values_json")
        if not isinstance(values, dict):
            raise PrebuiltToolSupport.argument_error("values_json", "the JSON is not an object", "a JSON object that maps placeholder names to values")
        rendered = TextTransformToolFunctions._template_values(template, values)
        missing_names = [name for name, value in rendered.items() if value is None]

        # Refuse missing names under the error policy, naming at most
        # PREBUILT_MAX_REPORTED_NAMES of them, each shortened.
        if missing_names and missing is MissingPlaceholderPolicy.ERROR:
            listed = ", ".join(name if len(name) <= _REPORTED_NAME_LENGTH else name[:_REPORTED_NAME_LENGTH] + "…" for name in missing_names[:PREBUILT_MAX_REPORTED_NAMES])
            problem = f"the values have no entry for {len(missing_names)} placeholder names: {listed}"
            raise PrebuiltToolSupport.argument_error("values_json", problem, "a value for every placeholder name, or the keep or empty policy")

        # @intent prebuilt-output-cap
        # A short template can repeat a long value many times, so the
        # predicted length is checked before the result exists.
        keep = missing is MissingPlaceholderPolicy.KEEP
        filled, predicted = TextTransformToolFunctions._filled_size(template, rendered, keep)
        if predicted > PREBUILT_MAX_TEXT_CHARS:
            raise PrebuiltToolSupport.argument_error("values_json", f"the filled template would hold {predicted} characters", _OUTPUT_CAP_EXPECTED)
        return {"text": TextTransformToolFunctions._filled_text(template, rendered, keep), "filled": filled, "missing": missing_names}

    @staticmethod
    def _rebuilt_text(lines: list[str], source: str) -> str:
        """Join lines with LF, adding one trailing LF when the source ended with a line break and lines remain."""
        return "\n".join(lines) + ("\n" if lines and source.endswith(_LINE_BREAK_ENDINGS) else "")

    @staticmethod
    def _identifier_words(text: str) -> list[str]:
        """Split runs of letters and digits at lowercase-to-uppercase changes, at uppercase after a digit, and at acronym ends."""
        words: list[str] = []
        for run in _LETTER_OR_DIGIT_RUN.findall(text):
            start = 0
            for index in range(1, len(run)):
                previous, current, following = run[index - 1], run[index], run[index + 1 : index + 2]
                if current.isupper() and (previous.islower() or not previous.isalpha() or (previous.isupper() and following.islower())):
                    words.append(run[start:index].lower())
                    start = index
            words.append(run[start:].lower())
        return words

    @staticmethod
    def _cut_characters(text: str, allowed: int, break_on_word: bool) -> str:
        """Cut text to at most allowed characters, moving back to the last whitespace when break_on_word asks for it."""
        if not break_on_word:
            return text[:allowed]
        # A whitespace character right after the span means the cut
        # already sits at a word boundary, so it is searched as well.
        boundary = next((index for index in range(allowed, -1, -1) if text[index].isspace()), allowed)
        return text[:boundary].rstrip()

    @staticmethod
    def _natural_key(line: str) -> tuple[tuple[int, int, str], ...]:
        """Key a line by its runs: a digit run by its value without leading zeros, any other run by its case fold, digits first."""
        return tuple((0, len(run.lstrip("0")), run.lstrip("0")) if run[0] in _ASCII_DIGITS else (1, 0, run.casefold()) for run in _NATURAL_RUN.findall(line))

    @staticmethod
    def _numeric_order(lines: list[str], descending: bool) -> list[str]:
        """Sort the numeric lines by value, stably, and keep the other lines after them in input order."""
        valued: list[tuple[int | float, str]] = []
        others: list[str] = []
        for line in lines:
            value = PrebuiltToolSupport.parse_numeric_text(line)
            if value is None:
                others.append(line)
            else:
                valued.append((value, line))
        valued.sort(key=lambda pair: pair[0], reverse=descending)
        return [line for _, line in valued] + others

    @staticmethod
    def _chunk_end(text: str, start: int, chunk_size: int) -> int:
        """Return where the chunk starting at start ends: the text end, the best break point, or a hard cut."""
        if len(text) - start <= chunk_size:
            return len(text)
        # Look one character past the window so a CRLF pair at its edge
        # is seen whole, and keep only break points inside the window.
        low, high = start + chunk_size // _WINDOW_DIVISOR, start + chunk_size
        for pattern in _CHUNK_BREAK_PATTERNS:
            best = max((match.end(1) for match in pattern.finditer(text, start, high + 1) if low < match.end(1) <= high), default=0)
            if best:
                return best
        return high

    @staticmethod
    def _template_values(template: str, values: dict[str, object]) -> dict[str, str | None]:
        """Render the value of each distinct placeholder name in order of first appearance, or None when it is missing."""
        rendered: dict[str, str | None] = {}
        for name in (match.group(1) for match in _TEMPLATE_FIELD.finditer(template)):
            if name in rendered:
                continue
            # Walk the dotted parts through nested objects, then
            # write the value as raw text, empty text, or compact JSON.
            current: object = values
            for part in name.split("."):
                current = current.get(part, _MISSING) if isinstance(current, dict) else _MISSING
            if current is _MISSING:
                rendered[name] = None
            elif isinstance(current, str):
                rendered[name] = current
            elif current is None:
                rendered[name] = ""
            else:
                rendered[name] = json.dumps(current, separators=(",", ":"), ensure_ascii=False)
        return rendered

    @staticmethod
    def _filled_size(template: str, rendered: dict[str, str | None], keep: bool) -> tuple[int, int]:
        """Count the placeholders filled with a value and predict the length of the filled template."""
        filled = 0
        size = len(template)
        for match in _TEMPLATE_FIELD.finditer(template):
            value = rendered[match.group(1)]
            if value is not None:
                filled += 1
                size += len(value) - len(match.group(0))
            elif not keep:
                size -= len(match.group(0))
        return filled, size

    @staticmethod
    def _filled_text(template: str, rendered: dict[str, str | None], keep: bool) -> str:
        """Build the filled template, keeping or removing placeholders whose names have no value."""
        pieces: list[str] = []
        position = 0
        for match in _TEMPLATE_FIELD.finditer(template):
            value = rendered[match.group(1)]
            pieces.append(template[position : match.start()])
            pieces.append(match.group(0) if value is None and keep else value or "")
            position = match.end()
        pieces.append(template[position:])
        return "".join(pieces)

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.reverse_text,
            cls.convert_identifier_case,
            cls.shorten_text,
            cls.replace_all_occurrences,
            cls.deduplicate_lines,
            cls.sort_text_lines,
            cls.strip_html_tags,
            cls.split_text_into_chunks,
            cls.extract_line_range,
            cls.fill_text_template,
        )


__all__ = ["TextTransformToolFunctions"]
