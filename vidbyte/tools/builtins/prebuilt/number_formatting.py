"""FILE: vidbyte/tools/builtins/prebuilt/number_formatting.py

PURPOSE: Defines NumberFormattingToolFunctions, the seven prebuilt tools that write and read numbers in human forms: base conversion, English number words in both directions, abbreviated amounts with magnitude suffixes, digit grouping in six separator styles, formatted amounts with currency, percent, and accounting marks, and scientific or engineering notation.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the NUMBER_FORMATTING category is chosen. Builds on PrebuiltToolSupport in _support.py for exact number text and the argument error, and on the number word, suffix, and currency tables in vidbyte/lib/constants/prebuilt_tools.py.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Numbers stay exact throughout: digit text is regrouped as text, rounding uses Decimal.quantize in a private wide decimal context, and English words are read by a small left-to-right state machine over one word table.
FUNCTION INVENTORY: convert_number_base, number_to_english_words, english_words_to_number, parse_abbreviated_number, format_number_with_separators, parse_formatted_number, and to_scientific_notation are the tools; _integer_in_base writes a non-negative integer in a base; _cardinal_words and _ordinal_words spell an integer; _read_number_words runs the word state machine; _decimal_parts splits a decimal into sign, integer digits, and fractional digits; _strip_number_marks removes currency, percent, sign, and accounting marks; _read_grouped_digits checks digit groups in a separator style; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new formatting tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.3, and its entry in tool_functions. A new separator style adds a SeparatorStyle member and its pair in _SEPARATORS; new number words or suffixes change only the constants module.
WHAT NOT TO DO IN THIS FILE: 1. Do not convert number text through float; every value must stay exact. 2. Do not turn an integer of more than 4,000 digits into text or read one from text; check the digit cap first, because Python refuses such conversions outside the power-of-two bases. 3. Do not use or change the thread's default decimal context; open PrebuiltToolSupport.decimal_context with _EXACT_PRECISION instead.
KNOWN EDGE CASES: A value whose digits are all zero is written without a sign in every tool. An ordinal changes only the last word, inside a hyphenated tens word too. Hundred may multiply a group up to ninety-nine, so a teen or tens word before hundred reads as a year-style number. A space separator style means U+0020 only, not a no-break space.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.3, section 9.2 items 2, 5, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_numbers.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_ABBREVIATED_NUMBER_SUFFIXES,
    PREBUILT_CURRENCY_SYMBOLS,
    PREBUILT_DECIMAL_TEXT_PATTERN,
    PREBUILT_INTEGER_TEXT_PATTERN,
    PREBUILT_MAX_DECIMAL_PLACES,
    PREBUILT_MAX_DECIMAL_TEXT_CHARS,
    PREBUILT_MAX_EXPRESSION_CHARS,
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_INTEGER_TEXT_CHARS,
    PREBUILT_MAX_NUMBER_WORD_DIGITS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_SIGNIFICANT_FIGURES,
    PREBUILT_NUMBER_WORDS_ONES,
    PREBUILT_NUMBER_WORDS_SCALES,
    PREBUILT_NUMBER_WORDS_TENS,
    PREBUILT_ORDINAL_WORDS,
)
from vidbyte.lib.enums.prebuilt_tools import NotationStyle, SeparatorStyle
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

# Wide enough that the largest decimal text can be rounded to the most
# places, or scaled to any power of ten, without rounding.
_EXACT_PRECISION = 4 * PREBUILT_MAX_DECIMAL_TEXT_CHARS
_INTEGER_RESULT_BOUND = 10**PREBUILT_MAX_INTEGER_DIGITS
_NUMBER_WORD_BOUND = 10**PREBUILT_MAX_NUMBER_WORD_DIGITS
_MIN_BASE = 2
_MAX_BASE = 36
_DIGIT_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_GROUP_SIZE = 3
_ENGINEERING_STEP = 3
_GROUP_BASE = 1000
_HUNDRED = 100
_TEEN_START = 10
_TENS_START = 20
_DECIMAL_BASE = 10
_REPORTED_WORD_LENGTH = 40
_BASE_TEXT_PATTERN = r"^[+-]?[0-9A-Za-z]+$"
_BASE_TEXT = re.compile(r"([+-]?)([0-9A-Za-z]+)")
_WORD_SEPARATORS = re.compile(r"[\s,-]+")
_ABBREVIATED_NUMBER = re.compile(r"(?P<sign>[+-]?)[$€£¥]?(?P<number>[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]*)?|[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\s*(?P<suffix>[A-Za-z]*)")
_CURRENCY_CLASS = "[" + re.escape("".join(PREBUILT_CURRENCY_SYMBOLS)) + "]"
_MARKED_NUMBER = re.compile(
    r"(?P<lead_percent>%)?\s*(?P<sign>[+-])?\s*(?P<lead_currency>" + _CURRENCY_CLASS + r")?\s*(?P<late_sign>[+-])?\s*"
    + r"(?P<body>.*?)\s*(?P<trail_currency>" + _CURRENCY_CLASS + r")?\s*(?P<trail_percent>%)?",
    re.DOTALL,
)
_DIGIT_RUN = re.compile(r"[0-9]*")
_FIRST_GROUP = re.compile(r"[0-9]{1,3}")
_FULL_GROUP = re.compile(r"[0-9]{3}")

_SEPARATORS: MappingProxyType[SeparatorStyle, tuple[str, str]] = MappingProxyType(
    {
        SeparatorStyle.COMMA_PERIOD: (",", "."),
        SeparatorStyle.PERIOD_COMMA: (".", ","),
        SeparatorStyle.SPACE_PERIOD: (" ", "."),
        SeparatorStyle.SPACE_COMMA: (" ", ","),
        SeparatorStyle.APOSTROPHE_PERIOD: ("'", "."),
        SeparatorStyle.UNDERSCORE_PERIOD: ("_", "."),
    }
)

# Word kinds for english_words_to_number. A word may not follow a word
# whose kind is in its forbidden set; the empty kind is the start of
# the phrase.
_UNIT, _TEEN, _TENS, _HUNDRED_WORD, _SCALE, _ZERO = "unit", "teen", "tens", "hundred", "scale", "zero"
_NUMBER_WORDS: MappingProxyType[str, tuple[str, int]] = MappingProxyType(
    {
        **{word: (_UNIT, value) for value, word in enumerate(PREBUILT_NUMBER_WORDS_ONES) if 0 < value < _TEEN_START},
        **{word: (_TEEN, value) for value, word in enumerate(PREBUILT_NUMBER_WORDS_ONES) if value >= _TEEN_START},
        **{word: (_TENS, _DECIMAL_BASE * index) for index, word in enumerate(PREBUILT_NUMBER_WORDS_TENS) if word},
        "hundred": (_HUNDRED_WORD, _HUNDRED),
        **{word: (_SCALE, _GROUP_BASE**power) for power, word in enumerate(PREBUILT_NUMBER_WORDS_SCALES) if word},
        PREBUILT_NUMBER_WORDS_ONES[0]: (_ZERO, 0),
    }
)
_FORBIDDEN_BEFORE: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        _UNIT: frozenset({_UNIT, _TEEN}),
        _TEEN: frozenset({_UNIT, _TEEN}),
        _TENS: frozenset({_UNIT, _TEEN, _TENS}),
        _HUNDRED_WORD: frozenset(),
        _SCALE: frozenset(),
        _ZERO: frozenset({"", _UNIT, _TEEN, _TENS, _HUNDRED_WORD, _SCALE}),
    }
)
_SIGN_WORDS = frozenset({"minus", "negative"})
_ARTICLE = "a"
_IGNORED_WORD = "and"

_DECIMAL_VALUE_DESCRIPTION = "An exact decimal number written as plain digits with an optional leading sign and an optional decimal point. Exponents, digit grouping, spaces, and currency marks are not accepted. The text is read exactly, so no binary floating-point error enters the result. It may hold at most 4,002 characters."
_INTEGER_VALUE_DESCRIPTION = "The integer to spell out, written as decimal digits with an optional leading sign. Leading zeros are allowed. Its magnitude must be below ten to the power 36, the end of the decillion scale. A larger magnitude fails with an error naming value."
_SEPARATOR_STYLE_DESCRIPTION = "Which characters separate the digit groups and mark the decimal point. The style comma_period uses commas and a period, period_comma uses periods and a comma, space_period and space_comma group with a plain space, apostrophe_period groups with an apostrophe, and underscore_period groups with an underscore. Groups hold three digits counted leftward from the decimal point, and the fraction is never grouped. The default is comma_period."


class NumberFormattingToolFunctions:
    """The number_formatting category: writing and reading numbers in bases, words, abbreviations, grouped text, and notation."""

    @staticmethod
    def convert_number_base(
        value: Annotated[str, Field(description="The integer to convert, written in from_base with an optional leading sign. Letters stand for the digits from ten upward and may be in either case. Leading zeros are allowed, while spaces, prefixes, and points are not. It must hold between 1 and 4,001 characters.", min_length=1, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS, pattern=_BASE_TEXT_PATTERN)],
        from_base: Annotated[int, Field(description="The base the value is written in. Digits run from zero to nine and then from a to z, and only those below the base are valid. The value must be between 2 and 36. A digit too large for this base fails with an error naming value.", ge=_MIN_BASE, le=_MAX_BASE)],
        to_base: Annotated[int, Field(description="The base to write the result in. Digits from ten upward are written as lowercase letters. The value must be between 2 and 36. Choosing the same base as from_base rewrites the value in canonical form.", ge=_MIN_BASE, le=_MAX_BASE)],
    ) -> PrebuiltToolOutput:
        """Convert an integer written in one base from 2 to 36 into another base in that range. Use it for binary, octal, hexadecimal, or base-36 conversions, which are easy to get wrong by hand on long values. Input digits are read without regard to case, output digits are lowercase without leading zeros, and the sign is kept. A digit not valid in from_base, or a magnitude of 10 to the power 4,000 or more, fails with an error naming value."""
        # Read the sign and digits, naming the first digit the base
        # lacks.
        match = _BASE_TEXT.fullmatch(value)
        if match is None:
            raise PrebuiltToolSupport.argument_error("value", "the text is not an integer in a base up to 36", "an optional sign followed by digits and letters")
        sign, digits = match.group(1), match.group(2).lower()
        invalid = next((digit for digit in digits if _DIGIT_ALPHABET.index(digit) >= from_base), None)
        if invalid is not None:
            raise PrebuiltToolSupport.argument_error("value", f"the digit {invalid!r} is not valid in base {from_base}", f"digits below {from_base} only")

        # @intent prebuilt-integer-digit-cap
        # Python refuses to write more than 4,300 decimal digits, and
        # such a result would flood the model's context, so a magnitude
        # of 10^4000 or more fails before it is written out.
        magnitude = int(digits, from_base)
        if magnitude >= _INTEGER_RESULT_BOUND:
            problem = f"its magnitude is 10^{PREBUILT_MAX_INTEGER_DIGITS} or more"
            raise PrebuiltToolSupport.argument_error("value", problem, f"an integer whose magnitude is below 10^{PREBUILT_MAX_INTEGER_DIGITS}")

        # Write the magnitude in the new base and keep a minus sign.
        converted = NumberFormattingToolFunctions._integer_in_base(magnitude, to_base)
        return {"result": f"-{converted}" if sign == "-" and magnitude else converted}

    @staticmethod
    def number_to_english_words(
        value: Annotated[str, Field(description=_INTEGER_VALUE_DESCRIPTION, pattern=PREBUILT_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
        ordinal: Annotated[bool, Field(description="Whether to write the ordinal form instead of the cardinal form. Only the last word changes, so the words before it stay cardinal. The default is false. A negative value with this set to true fails with an error naming value.")] = False,
    ) -> PrebuiltToolOutput:
        """Spell out an integer in English words, as a cardinal number or as an ordinal. Use it to write amounts on cheques, numbers in prose, or ranks such as a position in a list. The words are lowercase, separated by single spaces, with hyphenated tens, no and, no commas, and scale words up to decillion, and a negative number starts with minus. A magnitude of 10 to the power 36 or more, or a negative number with ordinal set, fails with an error naming value."""
        # Read the integer and refuse what has no English spelling.
        number = PrebuiltToolSupport.parse_integer_text(value, "value")
        if abs(number) >= _NUMBER_WORD_BOUND:
            problem = f"its magnitude is 10^{PREBUILT_MAX_NUMBER_WORD_DIGITS} or more, beyond the decillion scale"
            raise PrebuiltToolSupport.argument_error("value", problem, f"an integer whose magnitude is below 10^{PREBUILT_MAX_NUMBER_WORD_DIGITS}")
        if number < 0 and ordinal:
            raise PrebuiltToolSupport.argument_error("value", "a negative number has no ordinal form", "an integer of zero or more when ordinal is true")

        # Spell the magnitude, turn the last word into an ordinal when
        # asked, and put the sign in front.
        words = NumberFormattingToolFunctions._cardinal_words(abs(number))
        if ordinal:
            words = NumberFormattingToolFunctions._ordinal_words(words)
        return {"words": f"minus {words}" if number < 0 else words}

    @staticmethod
    def english_words_to_number(
        words: Annotated[str, Field(description="The English number phrase to read, in any letter case. Hyphens, commas, extra spaces, and the word and are ignored, and a leading minus or negative makes the value negative. Words must follow the usual English order up to the decillion scale, and digit strings and ordinal words are not accepted. It must hold between 1 and 1,000 characters.", min_length=1, max_length=PREBUILT_MAX_EXPRESSION_CHARS)],
    ) -> PrebuiltToolOutput:
        """Read an English number phrase written in words and return the integer it names as decimal text. Use it to turn spelled-out amounts from documents, transcripts, or user messages into exact numbers. Hundred multiplies the group before it, each scale word from thousand to decillion must be smaller than the one before, a leading a means one, and zero is accepted only as the whole phrase. An unknown word fails with an error that names it, and a word out of order or a phrase with no number word fails with an error naming words."""
        # Split into lowercase words, dropping separators and "and".
        pieces = [piece for piece in _WORD_SEPARATORS.split(words.lower()) if piece and piece != _IGNORED_WORD]

        # Read a leading sign word and a leading "a" that means one.
        negative = bool(pieces) and pieces[0] in _SIGN_WORDS
        body = pieces[1:] if negative else pieces
        if body[:1] == [_ARTICLE]:
            body = [PREBUILT_NUMBER_WORDS_ONES[1], *body[1:]]

        # Zero stands alone; anything else goes through the word reader.
        number = 0 if body == [PREBUILT_NUMBER_WORDS_ONES[0]] else NumberFormattingToolFunctions._read_number_words(body)
        return {"value": PrebuiltToolSupport.integer_text(-number if negative else number, "words")}

    @staticmethod
    def parse_abbreviated_number(
        text: Annotated[str, Field(description="The shorthand amount to read: an optional sign, an optional dollar, euro, pound, or yen symbol, digits with optional comma groups and a decimal point, and an optional magnitude suffix. The suffix may be k or thousand, m, mm, mn, or million, b, bn, or billion, or t, tn, or trillion, in any letter case. Spaces may separate the digits from the suffix. It must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Read a shorthand amount with a magnitude suffix, such as thousands, millions, billions, or trillions, and return the exact number it stands for. Use it to turn figures from headlines, reports, and chat messages into exact values before comparing or adding them. The digits are multiplied exactly, a currency symbol is dropped, and a bare number with no suffix is read as written. Any other text, an unknown suffix, or malformed digits fail with an error naming text."""
        # Match the whole amount and look up its suffix.
        match = _ABBREVIATED_NUMBER.fullmatch(text.strip())
        suffix = match.group("suffix").lower() if match else ""
        if match is None or (suffix and suffix not in PREBUILT_ABBREVIATED_NUMBER_SUFFIXES):
            raise PrebuiltToolSupport.argument_error("text", "the text is not a number with an optional magnitude suffix", "an optional sign and currency symbol, digits, and an optional suffix from k, m, mm, mn, b, bn, t, tn, or their words")

        # Multiply exactly, then apply the sign.
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            amount = Decimal(match.group("number").replace(",", "")) * PREBUILT_ABBREVIATED_NUMBER_SUFFIXES.get(suffix, 1)
        return {"value": PrebuiltToolSupport.decimal_text(amount.copy_negate() if match.group("sign") == "-" else amount)}

    @staticmethod
    def format_number_with_separators(
        value: Annotated[str, Field(description=_DECIMAL_VALUE_DESCRIPTION, pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        style: Annotated[SeparatorStyle, Field(description=_SEPARATOR_STYLE_DESCRIPTION)] = SeparatorStyle.COMMA_PERIOD,
        decimal_places: Annotated[int | None, Field(description="How many fractional digits to show after rounding half to even, or null to keep the fractional digits exactly as written. When set, the fraction always has exactly this many digits, padded with zeros. Zero places gives a whole number with no decimal separator. The value must be between 0 and 1,000, and the default is null.", ge=0, le=PREBUILT_MAX_DECIMAL_PLACES)] = None,
    ) -> PrebuiltToolOutput:
        """Format an exact decimal number with digit-group and decimal separators in a chosen regional style. Use it to present amounts for people in the convention they expect, without the rounding drift of floating point. The integer part is grouped in threes and loses its leading zeros, and the fraction keeps its digits as written unless decimal_places rounds it half to even to a fixed length. A plus sign is dropped, a value whose digits are all zero has no sign, and the tool has no failure case beyond its schema caps."""
        # Split the value into sign, integer digits, and fraction
        # digits, rounding first when a number of places is given.
        number = PrebuiltToolSupport.parse_decimal_text(value, "value")
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            negative, integer_digits, fraction_digits = NumberFormattingToolFunctions._decimal_parts(value, number, decimal_places)

        # Group the integer digits in threes from the right.
        group_separator, decimal_separator = _SEPARATORS[style]
        integer_digits = integer_digits.lstrip("0") or "0"
        head = len(integer_digits) % _GROUP_SIZE or _GROUP_SIZE
        groups = [integer_digits[:head], *(integer_digits[start : start + _GROUP_SIZE] for start in range(head, len(integer_digits), _GROUP_SIZE))]

        # Keep a minus sign only when some digit is not zero.
        sign = "-" if negative and (integer_digits + fraction_digits).strip("0") else ""
        fraction = f"{decimal_separator}{fraction_digits}" if fraction_digits else ""
        return {"formatted": f"{sign}{group_separator.join(groups)}{fraction}"}

    @staticmethod
    def parse_formatted_number(
        text: Annotated[str, Field(description="The formatted number to read, with surrounding whitespace ignored. It may carry one currency symbol, a leading or trailing percent sign, a plus or minus sign, and accounting parentheses that make it negative. Digit groups must hold exactly three digits after a first group of one to three digits. It must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        style: Annotated[SeparatorStyle, Field(description=_SEPARATOR_STYLE_DESCRIPTION)] = SeparatorStyle.COMMA_PERIOD,
    ) -> PrebuiltToolOutput:
        """Read a number written with digit grouping, a currency symbol, a percent sign, or accounting parentheses and return its exact value. Use it to turn amounts copied from invoices, spreadsheets, or reports into exact numbers before calculating with them. The separators come from the chosen style, a percent sign sets is_percent without dividing the value by 100, and parentheses make the value negative. Misplaced group separators, text with no digits, or any other character fail with an error naming text."""
        # Remove the marks around the digits, then read the digits in
        # the chosen separator style.
        body, negative, is_percent = NumberFormattingToolFunctions._strip_number_marks(text)
        magnitude = NumberFormattingToolFunctions._read_grouped_digits(body, style)
        return {"value": PrebuiltToolSupport.decimal_text(magnitude.copy_negate() if negative else magnitude), "is_percent": is_percent}

    @staticmethod
    def to_scientific_notation(
        value: Annotated[str, Field(description=_DECIMAL_VALUE_DESCRIPTION, pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        significant_figures: Annotated[int | None, Field(description="How many significant digits the mantissa keeps after rounding half to even, or null to keep every significant digit. A rounding carry moves the exponent instead of adding a digit. Trailing zeros are dropped from the mantissa either way. The value must be between 1 and 100, and the default is null.", ge=1, le=PREBUILT_MAX_SIGNIFICANT_FIGURES)] = None,
        style: Annotated[NotationStyle, Field(description="Whether to use scientific or engineering notation. Scientific notation keeps the absolute mantissa at least one and below ten. Engineering notation uses an exponent that is a multiple of three and keeps the absolute mantissa at least one and below one thousand. The default is scientific.")] = NotationStyle.SCIENTIFIC,
    ) -> PrebuiltToolOutput:
        """Write an exact decimal number in scientific or engineering notation as a mantissa and a power-of-ten exponent, optionally rounded to significant figures. Use it to present very large or very small values compactly, or to compare magnitudes. Rounding is half to even, a carry moves the exponent, and the mantissa is canonical decimal text with trailing zeros removed. The text output joins the mantissa and exponent with a lowercase e, zero gives a zero mantissa and exponent, and the tool has no failure case beyond its schema caps."""
        # Zero has no leading digit, so it has a fixed answer.
        number = PrebuiltToolSupport.parse_decimal_text(value, "value")
        if number.is_zero():
            return {"mantissa": "0", "exponent": 0, "text": "0e0"}

        # Round to the requested figures, then move the decimal point to
        # the exponent the style allows.
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            rounded = number
            if significant_figures is not None:
                rounded = number.quantize(Decimal((0, (1,), number.adjusted() - significant_figures + 1)), rounding=ROUND_HALF_EVEN)
            exponent = rounded.adjusted() if style is NotationStyle.SCIENTIFIC else rounded.adjusted() // _ENGINEERING_STEP * _ENGINEERING_STEP
            mantissa = PrebuiltToolSupport.decimal_text(rounded.scaleb(-exponent))
        return {"mantissa": mantissa, "exponent": exponent, "text": f"{mantissa}e{exponent}"}

    @staticmethod
    def _integer_in_base(magnitude: int, base: int) -> str:
        """Write a non-negative integer in a base from 2 to 36 with lowercase letter digits."""
        if magnitude == 0:
            return "0"
        digits: list[str] = []
        while magnitude:
            magnitude, digit = divmod(magnitude, base)
            digits.append(_DIGIT_ALPHABET[digit])
        return "".join(reversed(digits))

    @staticmethod
    def _cardinal_words(magnitude: int) -> str:
        """Spell a non-negative integer below 10^36 in lowercase cardinal words."""
        if magnitude == 0:
            return PREBUILT_NUMBER_WORDS_ONES[0]
        parts: list[str] = []
        for power in range(len(PREBUILT_NUMBER_WORDS_SCALES) - 1, -1, -1):
            hundreds, rest = divmod(magnitude // _GROUP_BASE**power % _GROUP_BASE, _HUNDRED)
            if hundreds:
                parts.append(f"{PREBUILT_NUMBER_WORDS_ONES[hundreds]} hundred")
            if rest >= _TENS_START:
                tens, units = divmod(rest, _DECIMAL_BASE)
                parts.append(PREBUILT_NUMBER_WORDS_TENS[tens] + (f"-{PREBUILT_NUMBER_WORDS_ONES[units]}" if units else ""))
            elif rest:
                parts.append(PREBUILT_NUMBER_WORDS_ONES[rest])
            if power and (hundreds or rest):
                parts.append(PREBUILT_NUMBER_WORDS_SCALES[power])
        return " ".join(parts)

    @staticmethod
    def _ordinal_words(cardinal: str) -> str:
        """Turn the last word of a cardinal phrase into its ordinal, inside a hyphenated tens word too."""
        head, space, last = cardinal.rpartition(" ")
        stem, hyphen, tail = last.rpartition("-")
        if tail in PREBUILT_ORDINAL_WORDS:
            tail = PREBUILT_ORDINAL_WORDS[tail]
        elif tail.endswith("y"):
            tail = f"{tail[:-1]}ieth"
        else:
            tail = f"{tail}th"
        return f"{head}{space}{stem}{hyphen}{tail}"

    @staticmethod
    def _read_number_words(body: list[str]) -> int:
        """Read number words left to right into a running group and total, refusing unknown and misplaced words."""
        expected_order = "number words in English order, with hundred after a group below one hundred and each scale smaller than the one before"
        total, group, previous, last_scale = 0, 0, "", 0
        for word in body:
            kind, amount = _NUMBER_WORDS.get(word, ("", 0))
            shown = word[:_REPORTED_WORD_LENGTH]
            if not kind:
                raise PrebuiltToolSupport.argument_error("words", f"the word {shown!r} is not an English number word", "number words from zero to decillion, without digits or ordinals")
            misplaced = previous in _FORBIDDEN_BEFORE[kind] or (kind == _HUNDRED_WORD and not 0 < group < _HUNDRED) or (kind == _SCALE and (group == 0 or 0 < last_scale <= amount))
            if misplaced:
                raise PrebuiltToolSupport.argument_error("words", f"the word {shown!r} is out of order", expected_order)
            if kind == _HUNDRED_WORD:
                group *= amount
            elif kind == _SCALE:
                total, group, last_scale = total + group * amount, 0, amount
            else:
                group += amount
            previous = kind
        if not previous:
            raise PrebuiltToolSupport.argument_error("words", "the phrase holds no number word", "a phrase with at least one number word")
        return total + group

    @staticmethod
    def _decimal_parts(value: str, number: Decimal, decimal_places: int | None) -> tuple[bool, str, str]:
        """Split decimal text into its sign, integer digits, and fraction digits, rounding half to even first when places are given."""
        if decimal_places is None:
            integer_digits, _, fraction_digits = value.lstrip("+-").partition(".")
            return number.is_signed(), integer_digits, fraction_digits
        rounded = number.quantize(Decimal((0, (1,), -decimal_places)), rounding=ROUND_HALF_EVEN)
        integer_digits, _, fraction_digits = format(rounded.copy_abs(), "f").partition(".")
        return rounded.is_signed(), integer_digits, fraction_digits

    @staticmethod
    def _strip_number_marks(text: str) -> tuple[str, bool, bool]:
        """Remove accounting parentheses, one percent sign, one sign, and one currency symbol, returning the digits and the two flags."""
        body = text.strip()
        accounting = len(body) > 1 and body.startswith("(") and body.endswith(")")
        if accounting:
            body = body[1:-1].strip()
        match = _MARKED_NUMBER.fullmatch(body)
        doubled = match is None or (match["lead_percent"] and match["trail_percent"]) or (match["lead_currency"] and match["trail_currency"]) or (match["sign"] and match["late_sign"])
        if match is None or doubled:
            raise PrebuiltToolSupport.argument_error("text", "it has more than one percent sign, currency symbol, or sign", "a number with at most one of each mark")
        negative = accounting or "-" in (match["sign"], match["late_sign"])
        return match["body"], negative, bool(match["lead_percent"] or match["trail_percent"])

    @staticmethod
    def _read_grouped_digits(body: str, style: SeparatorStyle) -> Decimal:
        """Read digits with the style's group and decimal separators, requiring groups of three after a first group of one to three."""
        group_separator, decimal_separator = _SEPARATORS[style]
        integer_part, _, fraction_digits = body.partition(decimal_separator)
        groups = integer_part.split(group_separator)
        integer_digits = "".join(groups)
        if not integer_digits + fraction_digits:
            raise PrebuiltToolSupport.argument_error("text", "it holds no digits", "a number with at least one digit")
        grouped = len(groups) == 1 or (_FIRST_GROUP.fullmatch(groups[0]) is not None and all(_FULL_GROUP.fullmatch(group) for group in groups[1:]))
        if not grouped or _DIGIT_RUN.fullmatch(integer_digits + fraction_digits) is None:
            raise PrebuiltToolSupport.argument_error("text", "the digits are not a number written in the chosen separator style", "digits in groups of exactly three after a first group of one to three, with at most one decimal separator")
        return Decimal(f"{integer_digits or '0'}.{fraction_digits or '0'}")

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.convert_number_base,
            cls.number_to_english_words,
            cls.english_words_to_number,
            cls.parse_abbreviated_number,
            cls.format_number_with_separators,
            cls.parse_formatted_number,
            cls.to_scientific_notation,
        )


__all__ = ["NumberFormattingToolFunctions"]
