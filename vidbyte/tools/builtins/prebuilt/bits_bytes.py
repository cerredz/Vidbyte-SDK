"""FILE: vidbyte/tools/builtins/prebuilt/bits_bytes.py

PURPOSE: Defines BitsBytesToolFunctions, the six prebuilt tools for bits and bytes: reading a data size with units, writing a byte count in human units, bitwise operations on exact integers, two's complement in both directions, and Unix permission conversion.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the BITS_BYTES category is chosen. Builds on PrebuiltToolSupport in _support.py for exact integer text, the integer digit cap, and the argument error, and on PREBUILT_DATA_SIZE_SUFFIXES, PREBUILT_SIZE_UNIT_LABELS, PREBUILT_MAX_BIT_WIDTH, and PREBUILT_MAX_DECIMAL_TEXT_CHARS in vidbyte/lib/constants/prebuilt_tools.py.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Sizes are computed exactly in Fraction and converted to float once, bit patterns use Python's unbounded integers masked to the requested width, and permissions go through one table of symbolic letters read in both directions.
FUNCTION INVENTORY: parse_data_size, format_bytes_human, bitwise_operation, integer_to_twos_complement, twos_complement_to_integer, and convert_unix_permissions are the tools; _second_operand reads what an operation needs besides left, _apply_bitwise runs one operation, _bit_texts writes binary and hexadecimal text, _symbolic_mode reads symbolic permissions, and _symbolic_text writes them; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new bits tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.27, and its entry in tool_functions. A new size unit goes into PREBUILT_DATA_SIZE_SUFFIXES or PREBUILT_SIZE_UNIT_LABELS, never into this file.
WHAT NOT TO DO IN THIS FILE: 1. Do not compute a data size in float before the final conversion; the row requires the exact value rounded once. 2. Do not build a Fraction from number text before bounding its exponent; a tiny exponent would build an enormous power of ten. Do not build a Decimal from the whole number text before comparing its exponent with PREBUILT_MAX_DECIMAL_TEXT_CHARS; past about 10^18 Decimal signals InvalidOperation, and a host context that traps nothing turns it into NaN. 3. Do not format an integer result as decimal text without PrebuiltToolSupport.integer_text, which enforces the digit cap. 4. Do not round byte sizes with float arithmetic; ties must go to the even digit.
KNOWN EDGE CASES: Mb means megabyte, not megabit, because units are matched without regard to case. A right shift without width keeps the sign, while with width it shifts the unsigned pattern in zeros, and a shift amount is never reduced to the width. A bit pattern with leading zeros counts them toward its width, so a width smaller than the written pattern fails even when the value would fit. A data size exponent may have any number of digits: past PREBUILT_MAX_DECIMAL_TEXT_CHARS a value other than zero with a positive exponent is refused, zero or a tiny positive value is zero bytes, and a tiny negative value such as -1e-99999999999999999999 is refused as negative although its float is -0.0.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.27, section 9.2 items 2, 5, 13, 15, and 18); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_geometry_bits_markdown.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from fractions import Fraction
from functools import reduce
from operator import or_
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_DATA_SIZE_SUFFIXES,
    PREBUILT_INTEGER_TEXT_PATTERN,
    PREBUILT_MAX_BIT_WIDTH,
    PREBUILT_MAX_DATA_SIZE_BYTES,
    PREBUILT_MAX_DECIMAL_TEXT_CHARS,
    PREBUILT_MAX_INTEGER_TEXT_CHARS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_SIZE_DECIMAL_PLACES,
    PREBUILT_SIZE_UNIT_LABELS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    BitStringFormat,
    BitwiseOperation,
    SizeStandard,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_NUMBER_PREFIX = re.compile(r"(?P<mantissa>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))(?:[eE](?P<exponent>[+-]?[0-9]+))?")
_SMALLEST_SIZE_EXPONENT = -400
_BITS_PER_BYTE = 8
_DECIMAL_BASE = 10
_SIZE_BASES = MappingProxyType({SizeStandard.SI: 1000, SizeStandard.IEC: 1024})
_SHIFT_OPERATIONS = frozenset({BitwiseOperation.SHIFT_LEFT, BitwiseOperation.SHIFT_RIGHT})
_BITS_PER_HEX_DIGIT = 4
_BIT_STRING_IGNORED = re.compile(r"[\s_]+")
_BIT_STRING_PREFIXES = MappingProxyType({BitStringFormat.BINARY: re.compile(r"\A0[bB]"), BitStringFormat.HEX: re.compile(r"\A0[xX]")})
_BIT_STRING_DIGITS = MappingProxyType({BitStringFormat.BINARY: re.compile(r"[01]+"), BitStringFormat.HEX: re.compile(r"[0-9A-Fa-f]+")})
_BIT_STRING_DIGIT_WIDTHS = MappingProxyType({BitStringFormat.BINARY: 1, BitStringFormat.HEX: 4})
_BIT_STRING_BASES = MappingProxyType({BitStringFormat.BINARY: 2, BitStringFormat.HEX: 16})
_OCTAL_PERMISSIONS = re.compile(r"[0-7]{3,4}")
_OCTAL_BASE = 8
_SYMBOLIC_LENGTH = 9
# Each position of a symbolic string maps its letters to mode bits; s
# and t add the special bit to execute, and S and T set it alone.
_SYMBOLIC_BITS = (
    MappingProxyType({"r": 0o400, "-": 0}),
    MappingProxyType({"w": 0o200, "-": 0}),
    MappingProxyType({"x": 0o100, "s": 0o4100, "S": 0o4000, "-": 0}),
    MappingProxyType({"r": 0o40, "-": 0}),
    MappingProxyType({"w": 0o20, "-": 0}),
    MappingProxyType({"x": 0o10, "s": 0o2010, "S": 0o2000, "-": 0}),
    MappingProxyType({"r": 0o4, "-": 0}),
    MappingProxyType({"w": 0o2, "-": 0}),
    MappingProxyType({"x": 0o1, "t": 0o1001, "T": 0o1000, "-": 0}),
)
_SYMBOLIC_MASKS = tuple(reduce(or_, options.values()) for options in _SYMBOLIC_BITS)
_SETUID_BIT = 0o4000
_SETGID_BIT = 0o2000
_STICKY_BIT = 0o1000

_INTEGER_OPERAND_DESCRIPTION = "decimal digits with an optional sign, and leading zeros are allowed. The text may hold at most 4,001 characters."
_WIDTH_BOUND_DESCRIPTION = "The value must be between 1 and 4,096."


class BitsBytesToolFunctions:
    """The bits_bytes category: data sizes, bitwise operations, two's complement, and Unix permissions."""

    @staticmethod
    def parse_data_size(text: Annotated[str, Field(description="The size to read: a number, optional whitespace, and an optional unit. The number may have a sign, a decimal point, and an exponent, but no thousands separators. Surrounding whitespace is ignored. The text must hold at least one character and at most two hundred.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)]) -> PrebuiltToolOutput:
        """Read a data size written as a number and an optional unit, and return it in bytes and in bits. Use it to compare sizes written in different units, or to turn a quota or a bandwidth figure into a plain number. Units are matched without regard to case: the k, m, g, t, and p prefixes with or without a trailing b mean powers of 1000, the kib to pib units mean powers of 1024, bit units are one eighth of a byte, Mb means megabyte, and no unit means bytes. An unknown unit, a negative number, thousands separators, or any other form fails with an error naming text."""
        # Split the text into its longest leading number and the unit
        # written after it.
        stripped = text.strip()
        expected = "a non-negative number with no thousands separators, optionally followed by a known unit of bytes or bits"
        number_match = _NUMBER_PREFIX.match(stripped)
        if number_match is None:
            raise PrebuiltToolSupport.argument_error("text", "the text does not start with a number", expected)
        unit_text = stripped[number_match.end() :].lstrip()
        known_unit = PREBUILT_DATA_SIZE_SUFFIXES.get(unit_text.lower()) if unit_text.isascii() else None
        factor = known_unit if unit_text else "1"
        if factor is None:
            raise PrebuiltToolSupport.argument_error("text", "the unit after the number is not a known data size unit", expected)

        # @intent prebuilt-data-size-far-exponent
        # Decimal cannot be built from an exponent past about 10^18,
        # and the host's decimal context would decide what happens
        # instead, so a far exponent keeps only the mantissa. Its sign
        # still decides whether the size is negative.
        far = abs(int(number_match["exponent"] or 0)) > PREBUILT_MAX_DECIMAL_TEXT_CHARS
        number = Decimal(number_match["mantissa"] if far else number_match.group())

        # The number must be finite as a float and not negative. A far
        # positive exponent on a value other than zero is infinite.
        if not math.isfinite(float(number_match.group())) or number < 0:
            raise PrebuiltToolSupport.argument_error("text", "the number is negative or outside the floating-point range", expected)

        # @intent prebuilt-data-size-exponent-bound
        # An exact fraction of a tiny exponent would build an enormous
        # power of ten, and any size that small, a far exponent left
        # here included, is zero bytes as a float.
        tiny = far or number.is_zero() or number.adjusted() < _SMALLEST_SIZE_EXPONENT
        exact = Fraction(0) if tiny else Fraction(number) * Fraction(factor)

        # Convert the exact size to float once for bytes and once for
        # bits, refusing a size beyond the floating-point range.
        try:
            return {"size_bytes": float(exact), "size_bits": float(exact * _BITS_PER_BYTE)}
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("text", "the size in bits is outside the floating-point range", expected) from exc

    @staticmethod
    def format_bytes_human(
        size_bytes: Annotated[int, Field(description="The number of bytes to format, as a whole number. It must be between zero and 10^24. Values below the unit base are written as whole bytes. The largest unit is the exabyte or the exbibyte, so larger sizes show a value of a thousand or more.", ge=0, le=PREBUILT_MAX_DATA_SIZE_BYTES)],
        standard: Annotated[SizeStandard, Field(description="Which unit system to use. The value iec uses powers of 1024 with the labels KiB, MiB, GiB, TiB, PiB, and EiB, and si uses powers of 1000 with the labels kB, MB, GB, TB, PB, and EB. Sizes below the base are shown in bytes either way. The default is iec.")] = SizeStandard.IEC,
        decimal_places: Annotated[int, Field(description="How many digits to keep after the decimal point when a unit above bytes is used. Trailing zeros are kept, so the text always shows exactly this many digits. Rounding is half to even. The value must be between 0 and 6, and the default is 1.", ge=0, le=PREBUILT_MAX_SIZE_DECIMAL_PLACES)] = 1,
    ) -> PrebuiltToolOutput:
        """Write a byte count in human-readable form with binary or decimal units, and return the text, the rounded value, and the unit. Use it to show file sizes, memory use, or transfer totals to a person. The tool picks the largest unit not above the size, divides exactly, rounds half to even at decimal_places, and moves up one unit when rounding reaches the next one. Sizes below one unit step are shown as a whole number of bytes, and the tool has no failure case beyond the parameter bounds."""
        # Sizes below the base are whole bytes with no fraction.
        base = _SIZE_BASES[standard]
        labels = PREBUILT_SIZE_UNIT_LABELS[standard]
        if size_bytes < base:
            return {"text": f"{size_bytes} {labels[0]}", "value": float(size_bytes), "unit": labels[0]}

        # Find the largest unit not above the size.
        power = 1
        while power + 1 < len(labels) and base ** (power + 1) <= size_bytes:
            power += 1

        # Round the exact quotient half to even; when that reaches the
        # next unit and one exists, move up and round again.
        scale = _DECIMAL_BASE**decimal_places
        scaled = round(Fraction(size_bytes, base**power) * scale)
        if scaled >= base * scale and power + 1 < len(labels):
            power += 1
            scaled = round(Fraction(size_bytes, base**power) * scale)

        # Write exactly decimal_places digits after the point.
        whole, fraction = divmod(scaled, scale)
        number_text = f"{whole}.{fraction:0{decimal_places}d}" if decimal_places else str(whole)
        return {"text": f"{number_text} {labels[power]}", "value": scaled / scale, "unit": labels[power]}

    @staticmethod
    def bitwise_operation(
        left: Annotated[str, Field(description="The first operand, written as " + _INTEGER_OPERAND_DESCRIPTION + " With width it is reduced to that many bits first, so a negative value becomes its two's complement pattern. Without width it keeps its sign.", pattern=PREBUILT_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
        operation: Annotated[BitwiseOperation, Field(description="The operation to apply. The values and, or, and xor combine left and right bit by bit, not inverts left and needs width, and shift_left and shift_right move left by right bits. A right shift without width keeps the sign, while with width it shifts in zeros. This parameter is required.")],
        right: Annotated[str | None, Field(description="The second operand for and, or, and xor, or the shift amount from 0 to 4,096 for the two shifts, written as " + _INTEGER_OPERAND_DESCRIPTION + " It is ignored by not and required by every other operation. A shift amount is never reduced to the width.", pattern=PREBUILT_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)] = None,
        width: Annotated[int | None, Field(description="The bit width to work at, or null for unlimited signed integers. With a width the operands and the result are reduced modulo two to that power and treated as unsigned, and the binary and hexadecimal outputs are zero-padded to it. The not operation needs a width. " + _WIDTH_BOUND_DESCRIPTION, ge=1, le=PREBUILT_MAX_BIT_WIDTH)] = None,
    ) -> PrebuiltToolOutput:
        """Apply a bitwise AND, OR, XOR, NOT, left shift, or right shift to exact integers, optionally at a fixed bit width, and return the result in decimal, binary, and hexadecimal. Use it for flag masks, register values, and protocol fields, where bit arithmetic done by hand goes wrong. With width the operands and the result are reduced to that many bits and treated as unsigned, and without it a negative result keeps a minus sign and a right shift keeps the sign. A missing right operand or a shift amount outside 0 to 4,096 fails naming right, not without width fails naming width, and a result of 10^4000 or more fails naming right."""
        # Read the operands, checking that the operation has what it
        # needs.
        first = PrebuiltToolSupport.parse_integer_text(left, "left")
        second = BitsBytesToolFunctions._second_operand(operation, right, width)

        # Reduce the operands to the width when one is given; a shift
        # amount is a count, not an operand, so it stays as it is.
        if width is not None:
            first &= (1 << width) - 1
            second = second if operation in _SHIFT_OPERATIONS else second & ((1 << width) - 1)

        # Apply the operation, check the size of the result, and write
        # it in decimal, binary, and hexadecimal.
        result = BitsBytesToolFunctions._apply_bitwise(operation, first, second, width)
        result_text = PrebuiltToolSupport.integer_text(result, "right")
        binary, hexadecimal = BitsBytesToolFunctions._bit_texts(result, width)
        return {"result": result_text, "binary": binary, "hex": hexadecimal}

    @staticmethod
    def integer_to_twos_complement(
        value: Annotated[str, Field(description="The signed integer to write, as " + _INTEGER_OPERAND_DESCRIPTION + " It must fit the signed range of the width, from minus two to the power width minus one up to that power minus one. A negative value is written as its two's complement pattern.", pattern=PREBUILT_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
        width: Annotated[int, Field(description="The number of bits in the pattern. It sets both the signed range of the value and the number of output digits. The hexadecimal output has one digit for every four bits, rounded up. " + _WIDTH_BOUND_DESCRIPTION, ge=1, le=PREBUILT_MAX_BIT_WIDTH)],
    ) -> PrebuiltToolOutput:
        """Write a signed integer as a two's complement bit pattern of a given width, in binary and hexadecimal, with the unsigned value of that pattern. Use it to see how a negative number is stored in a register, a file format, or a network field. The binary text has exactly width digits and the hexadecimal text has width divided by four digits, rounded up, both without a prefix. A value outside the signed range of the width fails with an error naming value."""
        # Check that the value fits the signed range of the width.
        number = PrebuiltToolSupport.parse_integer_text(value, "value")
        half = 1 << (width - 1)
        if not -half <= number < half:
            raise PrebuiltToolSupport.argument_error("value", f"the value does not fit in {width} signed bits", f"an integer from -2^{width - 1} to 2^{width - 1} - 1")

        # Masking with the width gives the two's complement pattern.
        unsigned = number & ((1 << width) - 1)
        binary, hexadecimal = BitsBytesToolFunctions._bit_texts(unsigned, width)
        return {"binary": binary, "hex": hexadecimal, "unsigned_value": PrebuiltToolSupport.integer_text(unsigned, "value")}

    @staticmethod
    def twos_complement_to_integer(
        bits: Annotated[str, Field(description="The bit pattern, written in binary or in hexadecimal according to bit_format. Underscores, spaces, and one 0b or 0x prefix matching that format are ignored. Leading zeros count toward the pattern length. The text must hold at least one character and at most ten thousand.", min_length=1, max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        bit_format: Annotated[BitStringFormat, Field(description="How the pattern is written. The value binary reads one bit per digit, and hex reads four bits per digit in either case. The format also decides whether a 0b or a 0x prefix is ignored. The default is binary.")] = BitStringFormat.BINARY,
        width: Annotated[int | None, Field(description="The width of the pattern in bits, or null for the digit count times one for binary or four for hexadecimal. A larger width adds zeros at the front, so the value is non-negative. A width smaller than the pattern fails with an error. " + _WIDTH_BOUND_DESCRIPTION, ge=1, le=PREBUILT_MAX_BIT_WIDTH)] = None,
    ) -> PrebuiltToolOutput:
        """Read a two's complement bit pattern in binary or hexadecimal and return its signed and unsigned values with the width used. Use it to decode a register dump, a raw field, or a hexadecimal constant as a signed number. Underscores, spaces, and one 0b or 0x prefix matching bit_format are ignored, the width defaults to the length of the pattern, and a larger width zero-extends the pattern. An invalid digit or a pattern of more than 4,096 bits fails naming bits, and a width smaller than the pattern fails naming width."""
        # Remove separators and the prefix that matches the format.
        digits = _BIT_STRING_PREFIXES[bit_format].sub("", _BIT_STRING_IGNORED.sub("", bits), count=1)
        expected = f"{bit_format.value} digits for at most {PREBUILT_MAX_BIT_WIDTH} bits, with underscores, spaces, and one prefix ignored"
        if _BIT_STRING_DIGITS[bit_format].fullmatch(digits) is None:
            raise PrebuiltToolSupport.argument_error("bits", f"the pattern is empty or holds a character that is not a {bit_format.value} digit", expected)

        # Measure the pattern and settle the width it is read at.
        pattern_width = len(digits) * _BIT_STRING_DIGIT_WIDTHS[bit_format]
        if pattern_width > PREBUILT_MAX_BIT_WIDTH:
            raise PrebuiltToolSupport.argument_error("bits", f"the pattern has {pattern_width} bits", expected)
        used_width = pattern_width if width is None else width
        if used_width < pattern_width:
            raise PrebuiltToolSupport.argument_error("width", f"the width is smaller than the {pattern_width} bits of the pattern", f"a width of at least {pattern_width}")

        # A set top bit makes the signed value negative.
        unsigned = int(digits, _BIT_STRING_BASES[bit_format])
        signed = unsigned - (1 << used_width) if unsigned >> (used_width - 1) else unsigned
        return {"signed_value": PrebuiltToolSupport.integer_text(signed, "bits"), "unsigned_value": PrebuiltToolSupport.integer_text(unsigned, "bits"), "width": used_width}

    @staticmethod
    def convert_unix_permissions(permissions: Annotated[str, Field(description="The permissions to convert, as 3 or 4 octal digits or as a symbolic string of 9 or 10 characters. A string of 10 characters starts with a file-type character, which is ignored. Surrounding whitespace is ignored. The text must hold at least one character and at most two hundred.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)]) -> PrebuiltToolOutput:
        """Convert Unix file permissions between octal and symbolic forms and explain the owner, group, and others parts and the special bits. Use it to read or write a chmod mode, or to check what a directory listing allows. It accepts 3 or 4 octal digits, or 9 or 10 symbolic characters with an ignored leading file-type character, and it understands the s, S, t, and T special-bit letters. The octal output always has 4 digits, the symbolic output has 9 characters, and any other input fails with an error naming permissions."""
        # Read the mode from octal digits or from symbolic letters.
        compact = permissions.strip()
        if _OCTAL_PERMISSIONS.fullmatch(compact):
            mode: int | None = int(compact, _OCTAL_BASE)
        else:
            mode = BitsBytesToolFunctions._symbolic_mode(compact)
        if mode is None:
            raise PrebuiltToolSupport.argument_error("permissions", "the text is neither octal permission digits nor a symbolic permission string", "3 or 4 octal digits, or 9 symbolic characters optionally preceded by a file-type character")

        # Write the mode both ways and split out its parts.
        symbolic = BitsBytesToolFunctions._symbolic_text(mode)
        return {
            "octal": f"{mode:04o}",
            "symbolic": symbolic,
            "owner": symbolic[0:3],
            "group": symbolic[3:6],
            "others": symbolic[6:9],
            "setuid": bool(mode & _SETUID_BIT),
            "setgid": bool(mode & _SETGID_BIT),
            "sticky": bool(mode & _STICKY_BIT),
        }

    @staticmethod
    def _second_operand(operation: BitwiseOperation, right: str | None, width: int | None) -> int:
        """Return the right operand or shift amount an operation needs, refusing a missing or out-of-range one."""
        match operation:
            case BitwiseOperation.NOT:
                if width is None:
                    raise PrebuiltToolSupport.argument_error("width", "the not operation needs a bit width", f"a width from 1 to {PREBUILT_MAX_BIT_WIDTH}")
                return 0
            case BitwiseOperation.SHIFT_LEFT | BitwiseOperation.SHIFT_RIGHT:
                expected = f"a shift amount from 0 to {PREBUILT_MAX_BIT_WIDTH}"
                if right is None:
                    raise PrebuiltToolSupport.argument_error("right", "a shift needs a shift amount", expected)
                amount = PrebuiltToolSupport.parse_integer_text(right, "right")
                if not 0 <= amount <= PREBUILT_MAX_BIT_WIDTH:
                    raise PrebuiltToolSupport.argument_error("right", "the shift amount is outside the allowed range", expected)
                return amount
            case _:
                if right is None:
                    raise PrebuiltToolSupport.argument_error("right", f"the {operation.value} operation needs a right operand", "an integer right operand")
                return PrebuiltToolSupport.parse_integer_text(right, "right")

    @staticmethod
    def _apply_bitwise(operation: BitwiseOperation, first: int, second: int, width: int | None) -> int:
        """Apply one bitwise operation and reduce the result to the width when one is given."""
        match operation:
            case BitwiseOperation.AND:
                result = first & second
            case BitwiseOperation.OR:
                result = first | second
            case BitwiseOperation.XOR:
                result = first ^ second
            case BitwiseOperation.NOT:
                result = ~first
            case BitwiseOperation.SHIFT_LEFT:
                result = first << second
            case _:
                result = first >> second
        return result if width is None else result & ((1 << width) - 1)

    @staticmethod
    def _bit_texts(number: int, width: int | None) -> tuple[str, str]:
        """Write an integer in binary and lowercase hexadecimal, zero-padded to the width when one is given."""
        if width is None:
            return format(number, "b"), format(number, "x")
        hex_digits = -(-width // _BITS_PER_HEX_DIGIT)
        return format(number, f"0{width}b"), format(number, f"0{hex_digits}x")

    @staticmethod
    def _symbolic_mode(text: str) -> int | None:
        """Read nine symbolic permission letters, after an optional file-type character, as mode bits, or return None."""
        letters = text[1:] if len(text) == _SYMBOLIC_LENGTH + 1 else text
        if len(letters) != _SYMBOLIC_LENGTH:
            return None
        mode = 0
        for options, letter in zip(_SYMBOLIC_BITS, letters, strict=True):
            if letter not in options:
                return None
            mode |= options[letter]
        return mode

    @staticmethod
    def _symbolic_text(mode: int) -> str:
        """Write mode bits as nine symbolic permission letters."""
        return "".join(next(letter for letter, bits in options.items() if bits == mode & mask) for options, mask in zip(_SYMBOLIC_BITS, _SYMBOLIC_MASKS, strict=True))

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.parse_data_size,
            cls.format_bytes_human,
            cls.bitwise_operation,
            cls.integer_to_twos_complement,
            cls.twos_complement_to_integer,
            cls.convert_unix_permissions,
        )


__all__ = ["BitsBytesToolFunctions"]
