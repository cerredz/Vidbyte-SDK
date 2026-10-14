"""FILE: vidbyte/tools/builtins/prebuilt/_support.py

PURPOSE: Holds PrebuiltToolSupport, the shared helpers every prebuilt tool category uses: the one argument-error builder, JSON and record parsing, exact number text, numeric text, nesting level, item capping under the character budget, paired lists, weights, dates and offsets, lines, words, sentences, syllables, CSV tables, and text encoding. Also defines the PrebuiltToolOutput and PrebuiltToolFunction type aliases.
ROLE IN CODEBASE: Imported by the 31 category modules in vidbyte/tools/builtins/prebuilt/ and by vidbyte/tools/toolsets/prebuilt.py (for the PrebuiltToolFunction alias). Builds on vidbyte/lib/constants/prebuilt_tools.py, vidbyte/lib/enums/prebuilt_tools.py, and ToolExecutionError from vidbyte/lib/errors/.
ARCHITECTURE NOTE: A static-method-only class (the class-bound helper pattern of vidbyte/lib/util/math.py). Each helper does one job. Helpers may call argument_error and nesting_level, which call nothing else in the class, and no other helper calls another helper, so a caller composes them: a records tool passes the value parse_json_text returns to records_from_json. Every error a helper raises is a ToolExecutionError whose message names the tool parameter the caller passed in, so FunctionTool turns it into a failure the model can act on.
FUNCTION INVENTORY: argument_error builds the INV-15 error. parse_json_text and json_pointer_tokens read JSON input, and records_from_json checks a parsed value as a list of records. parse_integer_text, parse_decimal_text, integer_text, decimal_text, fraction_text, float_result, and parse_numeric_text convert exact and numeric text. decimal_context opens the fresh, fully specified decimal context of section 9.2 item 18. nesting_level measures container depth without recursion. cap_items applies the item cap and character budget. paired_values and weight_total check parallel lists and weights. as_utc, parse_utc_offset, and parse_date_text read times and dates. split_lines, line_and_column, split_words, split_sentences, and count_syllables implement the line, position, word, sentence, and syllable rules. parse_csv_table reads a CSV table. base64_bytes reads tolerant Base64 in a chosen or detected alphabet. parse_html feeds HTML to a parser and drops markup left open at the end before closing it. encode_text encodes text in a TextEncoding.
COMMON MODIFICATION PATTERNS: Add a helper here only when two or more category modules need the same job; logic for one category stays in its own module. Keep every new helper free of calls to other helpers except argument_error and nesting_level.
WHAT NOT TO DO IN THIS FILE: 1. Do not raise anything but argument_error's ToolExecutionError. 2. Do not put str(exc) or repr(exc) in a message; read structured attributes such as msg, lineno, colno, and pos. 3. Do not touch global state: no decimal.getcontext, csv.field_size_limit, or sys.set_int_max_str_digits. 4. Do not import vidbyte.tools.toolsets or anything above the tools layer.
KNOWN EDGE CASES: Python refuses to turn text of more than 4,300 digits into an int, leading zeros included, so parse_numeric_text reads integers through their float value. A sentence terminator run is only matched at its first character, which keeps sentence splitting linear on long runs of punctuation. JSON nesting is checked after parsing, and json.loads itself raises RecursionError for extreme nesting, which is caught.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (section 9.2 items 3 to 17, section 12.3 row 6); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/ (every category's row file exercises these helpers through the tools)
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import math
import re
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from datetime import date, datetime, timedelta, timezone
from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from fractions import Fraction
from functools import partial
from html.parser import HTMLParser
from typing import NoReturn, TypeVar

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_JSON_NESTING,
    PREBUILT_MAX_RECORDS,
    PREBUILT_MAX_RESULT_ITEMS,
    PREBUILT_MAX_SNIFF_CHARS,
    PREBUILT_MAX_TABLE_COLUMNS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_MONTH_NAMES,
    PREBUILT_SENTENCE_ABBREVIATIONS,
)
from vidbyte.lib.enums.prebuilt_tools import CsvDelimiter, TextEncoding
from vidbyte.lib.errors import ToolExecutionError

T = TypeVar("T")
U = TypeVar("U")

PrebuiltToolOutput = dict[str, object]
PrebuiltToolFunction = Callable[..., PrebuiltToolOutput]

_INTEGER_RESULT_BOUND = 10**PREBUILT_MAX_INTEGER_DIGITS
_FLOAT_EXACT_INTEGER_BOUND = 2**53
_INTEGER_TEXT = re.compile(r"[+-]?[0-9]+")
_DECIMAL_TEXT = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)")
_NUMERIC_TEXT = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?")
_LINE_BREAK = re.compile(r"\r\n|\n|\r")
_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
_SENTENCE_END = re.compile(r"(?<![.!?…])[.!?…]++[\"'”’)\]]*+(?=\s|\Z)")
_WORD_BEFORE_END = re.compile(r"[\"'“‘(\[]*+(\S+)\Z")
_ABBREVIATION_WINDOW = 16
_SYLLABLE_VOWELS = re.compile(r"[aeiouy]+")
_CONSONANT_LE_ENDING = re.compile(r"[^aeiouy]le\Z")
_DELIMITER_CHARACTERS = {CsvDelimiter.COMMA: ",", CsvDelimiter.SEMICOLON: ";", CsvDelimiter.TAB: "\t", CsvDelimiter.PIPE: "|"}
_WEEKDAY_PREFIX = re.compile(r"\A(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues|tue|wed|thurs|thur|thu|fri|sat|sun)\.?,?\s+", re.IGNORECASE)
_ISO_DATE = re.compile(r"(?P<year>\d{4})(?P<separator>[-/.])(?P<month>\d{1,2})(?P=separator)(?P<day>\d{1,2})(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?", re.IGNORECASE)
_COMPACT_DATE = re.compile(r"(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})")
_MONTH_FIRST_DATE = re.compile(r"(?P<month>[a-z]+)\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>\d{4})", re.IGNORECASE)
_DAY_FIRST_DATE = re.compile(r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>[a-z]+)\.?,?\s+(?P<year>\d{4})", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"(?P<first>\d{1,2})(?P<separator>[/.-])(?P<second>\d{1,2})(?P=separator)(?P<year>\d{4})")
_MONTHS_IN_YEAR = 12
_BARE_TAG_OPENERS = frozenset({"<", "</"})
_BASE64_GROUP = 4
_URL_SAFE_ALTCHARS = b"-_"
_STANDARD_BASE64 = re.compile(r"[A-Za-z0-9+/]*")
_URL_SAFE_BASE64 = re.compile(r"[A-Za-z0-9_-]*")
_URL_SAFE_MARKS = re.compile(r"[-_]")
_STANDARD_MARKS = re.compile(r"[+/]")
_BASE64_EXPECTED = "Base64 text in one alphabet, with whitespace ignored and padding optional"


class PrebuiltToolSupport:
    """Static helpers shared by every prebuilt tool category."""

    @staticmethod
    def argument_error(parameter_name: str, problem: str, expected: str) -> ToolExecutionError:
        """Build the error a tool raises for an argument that is well-formed but wrong in meaning."""
        message = f"Invalid value for '{parameter_name}': {problem}. Expected {expected}."
        return ToolExecutionError(message, details={"parameter_name": parameter_name, "expected": expected})

    @staticmethod
    def parse_json_text(text: str, parameter_name: str) -> object:
        """Parse one JSON document, refusing non-finite constants and nesting deeper than the cap."""
        reject_constant = partial(PrebuiltToolSupport._reject_json_constant, parameter_name)
        read_float = partial(PrebuiltToolSupport._read_json_float, parameter_name)
        try:
            value = json.loads(text, parse_float=read_float, parse_constant=reject_constant)
        except json.JSONDecodeError as exc:
            problem = f"parsing stopped at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, "the text of one valid JSON document") from exc
        except RecursionError as exc:
            problem = f"the JSON is nested deeper than {PREBUILT_MAX_JSON_NESTING} levels"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, "JSON nested at most that deep") from exc
        except ValueError as exc:
            # Python refuses to read an integer of over 4,300 digits.
            problem = "it holds an integer with more digits than Python reads from text"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, "JSON whose integers have at most 4,300 digits") from exc
        # @intent prebuilt-json-nesting-cap
        # A document nested past the cap would make the output
        # serializer recurse too deep after the tool returns, where
        # FunctionTool can no longer turn the failure into a result.
        if PrebuiltToolSupport.nesting_level(value) > PREBUILT_MAX_JSON_NESTING:
            problem = f"the JSON is nested deeper than {PREBUILT_MAX_JSON_NESTING} levels"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, "JSON nested at most that deep")
        return value

    @staticmethod
    def _reject_json_constant(parameter_name: str, constant: str) -> NoReturn:
        # json.loads calls this for NaN, Infinity, and -Infinity, which
        # are not JSON and would break the finite-number output rule.
        problem = f"the JSON contains the non-finite constant {constant}"
        raise PrebuiltToolSupport.argument_error(parameter_name, problem, "JSON whose numbers are all finite")

    @staticmethod
    def _read_json_float(parameter_name: str, number_text: str) -> float:
        # json.loads calls this for every number with a fraction or an
        # exponent; one such as 1e400 overflows to infinity, which
        # would break the finite-number output rule.
        value = float(number_text)
        if not math.isfinite(value):
            raise PrebuiltToolSupport.argument_error(parameter_name, "the JSON contains a number too large for a float", "JSON whose numbers are all finite")
        return value

    @staticmethod
    def records_from_json(value: object, parameter_name: str) -> list[dict[str, object]]:
        """Check that a value parse_json_text returned is an array of at most PREBUILT_MAX_RECORDS objects, naming the first element that is not an object."""
        expected = f"a JSON array of at most {PREBUILT_MAX_RECORDS} objects"
        if not isinstance(value, list):
            raise PrebuiltToolSupport.argument_error(parameter_name, "the JSON is not an array", expected)
        if len(value) > PREBUILT_MAX_RECORDS:
            raise PrebuiltToolSupport.argument_error(parameter_name, f"the array holds {len(value)} records", expected)
        records: list[dict[str, object]] = []
        for index, element in enumerate(value):
            if not isinstance(element, dict):
                raise PrebuiltToolSupport.argument_error(parameter_name, f"the element at index {index} is not an object", expected)
            records.append(element)
        return records

    @staticmethod
    def json_pointer_tokens(pointer: str, parameter_name: str) -> list[str]:
        """Split an RFC 6901 JSON Pointer into unescaped reference tokens; the empty pointer is the root."""
        if pointer == "":
            return []
        expected = "an empty pointer or one that starts with a slash and escapes tilde as ~0 and slash as ~1"
        if not pointer.startswith("/"):
            raise PrebuiltToolSupport.argument_error(parameter_name, "the pointer does not start with a slash", expected)
        tokens: list[str] = []
        for escaped_part in pointer[1:].split("/"):
            if re.search(r"~(?![01])", escaped_part):
                raise PrebuiltToolSupport.argument_error(parameter_name, "the pointer has a tilde not followed by 0 or 1", expected)
            tokens.append(escaped_part.replace("~1", "/").replace("~0", "~"))
        return tokens

    @staticmethod
    def parse_integer_text(text: str, parameter_name: str) -> int:
        """Read exact integer text (optional sign, decimal digits, leading zeros allowed) as an int."""
        if _INTEGER_TEXT.fullmatch(text) is None:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the text is not an integer", "decimal digits with an optional sign")
        return int(text)

    @staticmethod
    def parse_decimal_text(text: str, parameter_name: str) -> Decimal:
        """Read exact decimal text with no exponent as a Decimal."""
        if _DECIMAL_TEXT.fullmatch(text) is None:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the text is not a plain decimal number", "digits with an optional sign and decimal point")
        return Decimal(text)

    @staticmethod
    def integer_text(value: int, parameter_name: str) -> str:
        """Write an integer result as canonical text, refusing one of 10^4000 or more in magnitude."""
        # @intent prebuilt-integer-digit-cap
        # Python cannot turn an int of more than 4,300 digits into text,
        # and such a result would also flood the model's context, so a
        # result of more than 4,000 digits fails before any conversion.
        if abs(value) >= _INTEGER_RESULT_BOUND:
            problem = f"the result would have more than {PREBUILT_MAX_INTEGER_DIGITS} digits"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, f"inputs whose result has at most {PREBUILT_MAX_INTEGER_DIGITS} digits")
        return str(value)

    @staticmethod
    def decimal_context(precision: int) -> AbstractContextManager[Context]:
        """Open a fresh decimal context with every field given and half-even rounding, so the host's own context never reaches a result."""
        # @intent prebuilt-fresh-decimal-context
        # FunctionTool runs a tool through asyncio.to_thread, which
        # copies the host's decimal context into the worker, and a
        # Context field left out is copied from DefaultContext, which a
        # host can change too, so every field is given (section 9.2
        # item 18).
        context = Context(prec=precision, rounding=ROUND_HALF_EVEN, Emin=MIN_EMIN, Emax=MAX_EMAX, capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])
        return localcontext(context)

    @staticmethod
    def decimal_text(value: Decimal) -> str:
        """Write a Decimal in canonical plain notation: no exponent, no trailing fractional zeros, and 0 for any zero."""
        # The f format without a precision reads nothing from the
        # decimal context, so the text never depends on the host's.
        if value.is_zero():
            return "0"
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    @staticmethod
    def fraction_text(value: Fraction) -> str:
        """Write a Fraction as p/q in lowest terms with the sign on p, or as p when q is 1."""
        if value.denominator == 1:
            return str(value.numerator)
        return f"{value.numerator}/{value.denominator}"

    @staticmethod
    def float_result(value: float, parameter_name: str) -> float:
        """Return a computed float, refusing infinity and NaN."""
        if not math.isfinite(value):
            raise PrebuiltToolSupport.argument_error(parameter_name, "the result is outside the floating-point range", "inputs whose result is a finite number")
        return value

    @staticmethod
    def parse_numeric_text(text: str) -> int | float | None:
        """Read numeric text under the section 9.2 item 15 rule, or return None when the text is not numeric."""
        stripped = text.strip()
        if _NUMERIC_TEXT.fullmatch(stripped) is None:
            return None
        number = float(stripped)
        if not math.isfinite(number):
            return None
        # Integer text below 2^53 is exact as a float, and reading it
        # through the float avoids Python's limit on long digit strings.
        is_integer_form = "." not in stripped and "e" not in stripped.lower()
        if is_integer_form and abs(number) < _FLOAT_EXACT_INTEGER_BOUND:
            return int(number)
        return number

    @staticmethod
    def nesting_level(value: object) -> int:
        """Measure container nesting with a work stack: 0 for a scalar, 1 for a flat or empty container."""
        deepest = 0
        pending: list[tuple[object, int]] = [(value, 1)]
        while pending:
            item, level = pending.pop()
            if isinstance(item, dict):
                children: Iterable[object] = item.values()
            elif isinstance(item, (list, tuple, set, frozenset)):
                children = item
            else:
                continue
            deepest = max(deepest, level)
            # Only containers can go deeper, so scalars are never
            # queued; this keeps the stack small for long flat arrays.
            pending.extend((child, level + 1) for child in children if isinstance(child, (dict, list, tuple, set, frozenset)))
        return deepest

    @staticmethod
    def cap_items(items: Iterable[T], cap: int = PREBUILT_MAX_RESULT_ITEMS) -> tuple[list[T], bool]:
        """Take items in order until the item cap or the character budget is reached, and say whether any were left."""
        kept: list[T] = []
        used = 0
        for item in items:
            if len(kept) >= cap:
                return kept, True
            # @intent prebuilt-enumeration-character-budget
            # Items can copy large parts of the input, so the kept items
            # must also fit the character budget together; the item that
            # would push the compact JSON total past it is left out.
            size = len(json.dumps(item, separators=(",", ":"), ensure_ascii=False))
            if used + size > PREBUILT_MAX_TEXT_CHARS:
                return kept, True
            kept.append(item)
            used += size
        return kept, False

    @staticmethod
    def paired_values(first: Sequence[T], second: Sequence[U], second_name: str) -> list[tuple[T, U]]:
        """Pair two parallel lists item by item, naming the second list when their lengths differ."""
        if len(first) != len(second):
            problem = f"it has {len(second)} items but the list it pairs with has {len(first)}"
            raise PrebuiltToolSupport.argument_error(second_name, problem, "exactly one item for each item of the paired list")
        return list(zip(first, second, strict=True))

    @staticmethod
    def weight_total(weights: Sequence[float], parameter_name: str) -> Fraction:
        """Sum weights exactly from their shortest text, refusing a negative weight or a zero total."""
        expected = "weights of zero or more with a total above zero"
        total = Fraction(0)
        for index, weight in enumerate(weights):
            if weight < 0:
                raise PrebuiltToolSupport.argument_error(parameter_name, f"the weight at index {index} is negative", expected)
            total += Fraction(repr(weight))
        if total == 0:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the weights add up to zero", expected)
        return total

    @staticmethod
    def as_utc(moment: datetime) -> datetime:
        """Return an aware datetime, reading a naive value as UTC; an aware value keeps its offset."""
        if moment.utcoffset() is None:
            return moment.replace(tzinfo=timezone.utc)
        return moment

    @staticmethod
    def parse_utc_offset(text: str) -> timezone:
        """Turn Z or a +HH:MM / -HH:MM offset, already checked by the schema pattern, into a fixed timezone."""
        if text == "Z":
            return timezone.utc
        sign = -1 if text.startswith("-") else 1
        hours, minutes = text[1:].split(":")
        return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))

    @staticmethod
    def parse_date_text(text: str, day_first: bool) -> tuple[date, bool] | None:
        """Read a date in one of the accepted numeric or English forms, returning it with an ambiguity flag, or None."""
        candidate = _WEEKDAY_PREFIX.sub("", text.strip(), count=1)
        named = _ISO_DATE.fullmatch(candidate) or _COMPACT_DATE.fullmatch(candidate) or _MONTH_FIRST_DATE.fullmatch(candidate) or _DAY_FIRST_DATE.fullmatch(candidate)
        numeric = _NUMERIC_DATE.fullmatch(candidate)
        ambiguous = False
        if named is not None:
            year, month_text, day = int(named["year"]), named["month"], int(named["day"])
            month = int(month_text) if month_text.isdigit() else PREBUILT_MONTH_NAMES.get(month_text.lower(), 0)
        elif numeric is not None:
            # In A/B/YYYY a part over 12 must be the day; when both
            # could be the month, day_first decides and the date is
            # ambiguous.
            first, second, year = int(numeric["first"]), int(numeric["second"]), int(numeric["year"])
            if min(first, second) > _MONTHS_IN_YEAR:
                return None
            reads_day_first = first > _MONTHS_IN_YEAR or (day_first and second <= _MONTHS_IN_YEAR)
            day, month = (first, second) if reads_day_first else (second, first)
            ambiguous = first != second and max(first, second) <= _MONTHS_IN_YEAR
        else:
            return None
        try:
            return date(year, month, day), ambiguous
        except ValueError:
            return None

    @staticmethod
    def split_lines(text: str) -> list[str]:
        """Split text at CRLF, LF, and CR under the section 9.2 item 6 rule; a trailing break starts no line, and empty text has none."""
        if not text:
            return []
        lines = _LINE_BREAK.split(text)
        if text.endswith(("\n", "\r")):
            lines.pop()
        return lines

    @staticmethod
    def line_and_column(text: str, position: int) -> tuple[int, int]:
        """Return the 1-based line and column of a code-point position; a line feed that completes a CRLF pair stays on the line it ends."""
        line, line_start = 1, 0
        for match in _LINE_BREAK.finditer(text, 0, position + 1):
            if match.end() <= position:
                line, line_start = line + 1, match.end()
        return line, position - line_start + 1

    @staticmethod
    def split_words(text: str) -> list[tuple[int, str]]:
        """Return (position, word) for every word under the section 9.2 item 8 rule."""
        return [(match.start(), match.group()) for match in _WORD.finditer(text)]

    @staticmethod
    def split_sentences(text: str) -> list[tuple[int, str]]:
        """Return (position, sentence) for every sentence under the section 9.2 item 9 rule, with whitespace removed."""
        sentences: list[tuple[int, str]] = []
        start = 0
        for match in _SENTENCE_END.finditer(text):
            # A period after an abbreviation or a single capital letter
            # (an initial) does not end the sentence.
            if match.group().rstrip("\"'”’)]") == ".":
                before = _WORD_BEFORE_END.search(text, max(0, match.start() - _ABBREVIATION_WINDOW), match.start())
                word = before.group(1) if before else ""
                if f"{word.lower()}." in PREBUILT_SENTENCE_ABBREVIATIONS or (len(word) == 1 and word.isupper()):
                    continue
            piece = text[start : match.end()]
            if piece.strip():
                sentences.append((start + len(piece) - len(piece.lstrip()), piece.strip()))
            start = match.end()
        tail = text[start:]
        if tail.strip():
            sentences.append((start + len(tail) - len(tail.lstrip()), tail.strip()))
        return sentences

    @staticmethod
    def count_syllables(word: str) -> int:
        """Estimate the syllables of one English word under the section 9.2 item 10 rule."""
        letters = "".join(character for character in word.lower() if "a" <= character <= "z")
        if not letters:
            return 0
        count = len(_SYLLABLE_VOWELS.findall(letters))
        if letters.endswith("e") and count > 1 and _CONSONANT_LE_ENDING.search(letters) is None:
            count -= 1
        return max(count, 1)

    @staticmethod
    def parse_csv_table(text: str, delimiter: CsvDelimiter | None, parameter_name: str) -> tuple[list[str], list[list[str]], CsvDelimiter]:
        """Read CSV text into a header, rows padded to the header's width, and the delimiter used."""
        # Detect the delimiter from the start of the text only, because
        # the sniffer slows down sharply on long input.
        chosen = delimiter
        if chosen is None:
            try:
                sniffed = csv.Sniffer().sniff(text[:PREBUILT_MAX_SNIFF_CHARS], delimiters=",;\t|").delimiter
            except csv.Error:
                sniffed = ","
            chosen = next((member for member, character in _DELIMITER_CHARACTERS.items() if character == sniffed), CsvDelimiter.COMMA)
        # Read every non-blank row, reporting a parse failure by line.
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=_DELIMITER_CHARACTERS[chosen])
        expected = f"CSV text whose first row names up to {PREBUILT_MAX_TABLE_COLUMNS} distinct columns, followed by at most {PREBUILT_MAX_RECORDS} rows no wider than the header"
        try:
            table = [row for row in reader if row]
        except csv.Error as exc:
            raise PrebuiltToolSupport.argument_error(parameter_name, f"the CSV could not be read at line {reader.line_num}", expected) from exc
        # Check the header names and the size of the table.
        if not table:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the CSV has no header row", expected)
        header, rows = table[0], table[1:]
        if len(header) > PREBUILT_MAX_TABLE_COLUMNS or len(rows) > PREBUILT_MAX_RECORDS:
            raise PrebuiltToolSupport.argument_error(parameter_name, f"the CSV has {len(header)} columns and {len(rows)} rows", expected)
        seen: set[str] = set()
        for position, name in enumerate(header, start=1):
            if not name.strip() or name in seen:
                problem = f"header column {position} is empty" if not name.strip() else f"header column {position} repeats an earlier name"
                raise PrebuiltToolSupport.argument_error(parameter_name, problem, expected)
            seen.add(name)
        # Pad short rows with empty cells and refuse rows wider than
        # the header.
        padded: list[list[str]] = []
        for row_number, row in enumerate(rows, start=2):
            if len(row) > len(header):
                raise PrebuiltToolSupport.argument_error(parameter_name, f"row {row_number} has {len(row)} cells but the header has {len(header)}", expected)
            padded.append(row + [""] * (len(header) - len(row)))
        return header, padded, chosen

    @staticmethod
    def base64_bytes(text: str, url_safe: bool | None, parameter_name: str) -> bytes:
        """Decode Base64 with whitespace removed and padding optional, in the chosen alphabet or, when url_safe is None, the one its marks show."""
        compact = "".join(text.split())
        core = compact.rstrip("=")
        detected = _URL_SAFE_MARKS.search(core) is not None
        if detected and _STANDARD_MARKS.search(core) is not None:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the text mixes characters of the standard and the URL-safe Base64 alphabets", _BASE64_EXPECTED)
        chosen = detected if url_safe is None else url_safe
        alphabet_name = "URL-safe" if chosen else "standard"
        if (_URL_SAFE_BASE64 if chosen else _STANDARD_BASE64).fullmatch(core) is None:
            raise PrebuiltToolSupport.argument_error(parameter_name, f"the text holds a character outside the {alphabet_name} Base64 alphabet", _BASE64_EXPECTED)
        missing = -len(core) % _BASE64_GROUP
        if len(core) % _BASE64_GROUP == 1 or len(compact) - len(core) > missing:
            raise PrebuiltToolSupport.argument_error(parameter_name, f"the text has {len(core)} Base64 digits with a padding of {len(compact) - len(core)}, which no Base64 text can have", _BASE64_EXPECTED)
        try:
            return base64.b64decode(core + "=" * missing, altchars=_URL_SAFE_ALTCHARS if chosen else None, validate=True)
        except binascii.Error as exc:
            raise PrebuiltToolSupport.argument_error(parameter_name, f"the text is not valid {alphabet_name} Base64", _BASE64_EXPECTED) from exc

    @staticmethod
    def parse_html(parser: HTMLParser, html_text: str) -> None:
        """Feed HTML to a parser and close it, dropping markup left open at the end of the input first (EC-47)."""
        parser.feed(html_text)
        # @intent prebuilt-html-open-tail
        # Before CPython 3.11.13, close() re-scans markup left open at
        # the end once for every "<" in it (CVE-2025-6069), and fixed
        # releases give these tools nothing from such a tail, so it is
        # dropped to keep the time short and the output the same on
        # every release.
        if parser.rawdata.startswith("<") and parser.rawdata not in _BARE_TAG_OPENERS:
            parser.rawdata = ""
        parser.close()

    @staticmethod
    def encode_text(text: str, encoding: TextEncoding, parameter_name: str) -> bytes:
        """Encode text strictly in the chosen encoding, naming the first character it cannot represent."""
        try:
            return text.encode(encoding.value.replace("_", "-"))
        except UnicodeEncodeError as exc:
            problem = f"the character at position {exc.start} cannot be written in {encoding.value}"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, f"text whose characters all exist in {encoding.value}") from exc


__all__ = ["PrebuiltToolFunction", "PrebuiltToolOutput", "PrebuiltToolSupport"]
