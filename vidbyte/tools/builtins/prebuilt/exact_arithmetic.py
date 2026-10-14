"""FILE: vidbyte/tools/builtins/prebuilt/exact_arithmetic.py

PURPOSE: Defines ExactArithmeticToolFunctions, the ten prebuilt tools that do arithmetic a model cannot do reliably in its head: exact decimal arithmetic, rounding to places or significant figures, exact sums, fraction arithmetic, conversions between decimals, repeating decimals, and fractions, integer square roots, and quadratic equations.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the EXACT_ARITHMETIC category is chosen. Builds on PrebuiltToolSupport in _support.py for exact number text, the float guard, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Decimal work runs in the fresh, fully specified context of PrebuiltToolSupport.decimal_context, wide enough that adding, subtracting, and multiplying never round, and every rounding that a row asks for happens exactly once, either with Decimal.quantize or with integer division of an exact Fraction.
FUNCTION INVENTORY: decimal_arithmetic, round_decimal, round_significant_figures, sum_decimal_list, fraction_arithmetic, decimal_to_fraction, repeating_decimal_to_fraction, fraction_to_decimal, integer_square_root, and solve_quadratic_equation are the tools; _round_half_even rounds an exact Fraction to fixed places; _round_to_figures rounds a Decimal to significant figures; _parse_fraction reads fraction text under the digit cap; _expand_digits runs the long division with cycle detection; _quadratic_roots solves the equation in floats; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new exact tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.1, and its entry in tool_functions. A new rounding mode adds a RoundingMode member and its entry in _ROUNDING_MODES.
WHAT NOT TO DO IN THIS FILE: 1. Do not convert decimal text through float or call round(); every exact result must come from Decimal or Fraction. 2. Do not use or change the thread's default decimal context; open PrebuiltToolSupport.decimal_context with _EXACT_PRECISION instead. 3. Do not turn an integer of more than 4,000 digits into text; check the digit cap first, because Python refuses such conversions.
KNOWN EDGE CASES: Division rounds an exact Fraction with integer arithmetic, so a tie is a true tie and never a double rounding. A carry into a new leading digit is rounded again one place higher, so significant figures never grow. A rounded zero is written without a sign. Long division stops after 1,000 fractional digits, and whether a fraction terminates is decided from its denominator, not from the digits shown.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.1, section 9.2 items 2, 5, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_numbers.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
)
from fractions import Fraction
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_APPROXIMATION_DIGITS,
    PREBUILT_DECIMAL_TEXT_PATTERN,
    PREBUILT_DEFAULT_DIVISION_PLACES,
    PREBUILT_INTEGER_TEXT_PATTERN,
    PREBUILT_MAX_DECIMAL_PLACES,
    PREBUILT_MAX_DECIMAL_TEXT_CHARS,
    PREBUILT_MAX_DENOMINATOR,
    PREBUILT_MAX_EXPRESSION_CHARS,
    PREBUILT_MAX_FRACTION_TEXT_CHARS,
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_INTEGER_TEXT_CHARS,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_SIGNIFICANT_FIGURES,
)
from vidbyte.lib.enums.prebuilt_tools import ArithmeticOperation, RoundingMode
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

# Wide enough that two operands of the largest decimal text can be
# added or multiplied, or rounded to the most places, without rounding.
_EXACT_PRECISION = 4 * PREBUILT_MAX_DECIMAL_TEXT_CHARS
_INTEGER_RESULT_BOUND = 10**PREBUILT_MAX_INTEGER_DIGITS
_DECIMAL_BASE = 10
_FRACTION_TEXT_PATTERN = r"^[+-]?[0-9]+(/[0-9]+)?$"
_REPEATING_DECIMAL_PATTERN = r"^[+-]?[0-9]*\.[0-9]*\([0-9]+\)$"
_FRACTION_TEXT = re.compile(r"([+-]?)([0-9]+)(?:/([0-9]+))?")
_REPEATING_DECIMAL = re.compile(r"([+-]?)([0-9]*)\.([0-9]*)\(([0-9]+)\)")

_ROUNDING_MODES: MappingProxyType[RoundingMode, str] = MappingProxyType(
    {
        RoundingMode.HALF_EVEN: ROUND_HALF_EVEN,
        RoundingMode.HALF_UP: ROUND_HALF_UP,
        RoundingMode.HALF_DOWN: ROUND_HALF_DOWN,
        RoundingMode.UP: ROUND_UP,
        RoundingMode.DOWN: ROUND_DOWN,
        RoundingMode.CEILING: ROUND_CEILING,
        RoundingMode.FLOOR: ROUND_FLOOR,
    }
)
_OPERATIONS: MappingProxyType[ArithmeticOperation, Callable[[Any, Any], Any]] = MappingProxyType(
    {
        ArithmeticOperation.ADD: operator.add,
        ArithmeticOperation.SUBTRACT: operator.sub,
        ArithmeticOperation.MULTIPLY: operator.mul,
        ArithmeticOperation.DIVIDE: operator.truediv,
    }
)

_DECIMAL_OPERAND_DESCRIPTION = "An exact decimal number written as plain digits with an optional leading sign and an optional decimal point. Exponents, digit grouping, spaces, and currency marks are not accepted. The text is read exactly, so no binary floating-point error enters the calculation. It may hold at most 4,002 characters."
_FRACTION_OPERAND_DESCRIPTION = "An exact fraction written as an integer numerator, a slash, and a positive integer denominator, or as a plain integer. Only the numerator may carry a sign, and spaces are not accepted. The numerator and the denominator may each hold at most 4,000 significant digits. A zero denominator fails with an error naming this parameter."
_OPERATION_DESCRIPTION = "The arithmetic operation to apply, with the left operand first. Choose add, subtract, multiply, or divide. Subtract computes left minus right, and divide computes left divided by right. A divisor of zero fails with an error naming right."
_ROUNDING_MODE_DESCRIPTION = "How a value that falls between two candidates is rounded. The half modes take the nearer candidate and differ only on exact ties, where half_even picks the even digit, half_up moves away from zero, and half_down moves toward zero. The directed modes ignore ties: up moves away from zero, down moves toward zero, ceiling moves toward positive infinity, and floor moves toward negative infinity. The default is half_even."
_COEFFICIENT_DESCRIPTION = "One coefficient of the quadratic equation, given as a finite number. The equation is a times x squared, plus b times x, plus c, equal to zero. Infinity and NaN are rejected by validation. Coefficients so large that the discriminant overflows fail with an error naming a."


class ExactArithmeticToolFunctions:
    """The exact_arithmetic category: decimal, fraction, and integer arithmetic without floating-point error."""

    @staticmethod
    def decimal_arithmetic(
        left: Annotated[str, Field(description=_DECIMAL_OPERAND_DESCRIPTION, pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        right: Annotated[str, Field(description=_DECIMAL_OPERAND_DESCRIPTION, pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        operation: Annotated[ArithmeticOperation, Field(description=_OPERATION_DESCRIPTION)],
        decimal_places: Annotated[int, Field(description="How many fractional digits a division keeps before it rounds half to even. Add, subtract, and multiply are always exact and ignore this value. The default is 28 places. The value must be between 0 and 1,000.", ge=0, le=PREBUILT_MAX_DECIMAL_PLACES)] = PREBUILT_DEFAULT_DIVISION_PLACES,
    ) -> PrebuiltToolOutput:
        """Add, subtract, multiply, or divide two exact decimal numbers and return the result as canonical decimal text, with no floating-point error. Use it for money, measurements, and any sum or product where binary floating point would give a wrong last digit. Add, subtract, and multiply are always exact, while divide rounds half to even at decimal_places and reports exact as false when it had to round. Dividing by zero fails naming right, and a result of 10 to the power 4,000 or more in magnitude fails naming left."""
        # Read both operands exactly and refuse a zero divisor.
        left_value = PrebuiltToolSupport.parse_decimal_text(left, "left")
        right_value = PrebuiltToolSupport.parse_decimal_text(right, "right")
        if operation is ArithmeticOperation.DIVIDE and right_value.is_zero():
            raise PrebuiltToolSupport.argument_error("right", "it is zero, so the division has no result", "a divisor other than zero")

        # Divide exactly as fractions and round once; the other three
        # operations fit the wide context and never round.
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            if operation is ArithmeticOperation.DIVIDE:
                quotient = Fraction(left_value) / Fraction(right_value)
                result, exact = ExactArithmeticToolFunctions._round_half_even(quotient, decimal_places)
            else:
                result, exact = _OPERATIONS[operation](left_value, right_value), True

        # @intent prebuilt-integer-digit-cap
        # A result of 10^4000 or more would flood the model's context,
        # so it fails here instead of being written out.
        if not result.is_zero() and result.adjusted() >= PREBUILT_MAX_INTEGER_DIGITS:
            raise PrebuiltToolSupport.argument_error("left", f"the result is 10^{PREBUILT_MAX_INTEGER_DIGITS} or more in magnitude", f"operands whose result is below 10^{PREBUILT_MAX_INTEGER_DIGITS} in magnitude")
        return {"result": PrebuiltToolSupport.decimal_text(result), "exact": exact}

    @staticmethod
    def round_decimal(
        value: Annotated[str, Field(description=_DECIMAL_OPERAND_DESCRIPTION, pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        decimal_places: Annotated[int, Field(description="How many fractional digits the result keeps. The result always shows exactly this many fractional digits, padding with zeros when needed. Zero places gives a whole number with no decimal point. The value must be between 0 and 1,000, and the default is 0.", ge=0, le=PREBUILT_MAX_DECIMAL_PLACES)] = 0,
        mode: Annotated[RoundingMode, Field(description=_ROUNDING_MODE_DESCRIPTION)] = RoundingMode.HALF_EVEN,
    ) -> PrebuiltToolOutput:
        """Round an exact decimal number to a fixed number of decimal places with a chosen rounding mode and return it as text. Use it whenever a value must be rounded correctly, because exact ties are decided on the decimal digits as written rather than on a binary approximation. The result keeps exactly decimal_places fractional digits, trailing zeros included, and has no decimal point when decimal_places is zero. A value that rounds to zero is written without a sign, and the tool has no failure case beyond its schema caps."""
        number = PrebuiltToolSupport.parse_decimal_text(value, "value")
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            rounded = number.quantize(Decimal((0, (1,), -decimal_places)), rounding=_ROUNDING_MODES[mode])
        return {"result": format(rounded.copy_abs() if rounded.is_zero() else rounded, "f")}

    @staticmethod
    def round_significant_figures(
        value: Annotated[str, Field(description=_DECIMAL_OPERAND_DESCRIPTION, pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        significant_figures: Annotated[int, Field(description="How many significant digits the result shows, counted from the first non-zero digit. Zeros are added after the decimal point when the value has too few digits, and zeros that only hold place before the point are written out. The value must be between 1 and 100. There is no default, so it must always be given.", ge=1, le=PREBUILT_MAX_SIGNIFICANT_FIGURES)],
        mode: Annotated[RoundingMode, Field(description=_ROUNDING_MODE_DESCRIPTION)] = RoundingMode.HALF_EVEN,
    ) -> PrebuiltToolOutput:
        """Round an exact decimal number to a number of significant figures and return it in plain notation, never with an exponent. Use it for reporting measurements or estimates to a stated precision. The result shows exactly significant_figures significant digits, adding fractional zeros or writing out place-holding zeros as needed, and a carry into a new leading digit is rounded again one place higher. Zero gives zero, the sign is kept, and the tool has no failure case beyond its schema caps."""
        number = PrebuiltToolSupport.parse_decimal_text(value, "value")
        if number.is_zero():
            return {"result": "0"}
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            rounded = ExactArithmeticToolFunctions._round_to_figures(number, significant_figures, _ROUNDING_MODES[mode])
        return {"result": format(rounded, "f")}

    @staticmethod
    def sum_decimal_list(
        values: Annotated[
            list[Annotated[str, Field(pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)]],
            Field(description="The exact decimal numbers to add, each written as plain digits with an optional leading sign and an optional decimal point. Exponents, digit grouping, and spaces are not accepted in any item. The list must hold between 1 and 10,000 items. Each item may hold at most 4,002 characters.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS),
        ],
    ) -> PrebuiltToolOutput:
        """Add a list of exact decimal numbers and return the sum as canonical decimal text together with how many values were added. Use it to total amounts, scores, or measurements where floating-point addition would drift in the last digits. The sum is exact for any mix of signs and decimal places, and trailing fractional zeros are removed from the result. A sum of 10 to the power 4,000 or more in magnitude fails with an error naming values."""
        numbers = [PrebuiltToolSupport.parse_decimal_text(text, "values") for text in values]
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            total = sum(numbers, Decimal(0))
        # @intent prebuilt-integer-digit-cap
        # A sum of 10^4000 or more would flood the model's context, so
        # it fails here instead of being written out.
        if not total.is_zero() and total.adjusted() >= PREBUILT_MAX_INTEGER_DIGITS:
            raise PrebuiltToolSupport.argument_error("values", f"the sum is 10^{PREBUILT_MAX_INTEGER_DIGITS} or more in magnitude", f"values whose sum is below 10^{PREBUILT_MAX_INTEGER_DIGITS} in magnitude")
        return {"sum": PrebuiltToolSupport.decimal_text(total), "count": len(values)}

    @staticmethod
    def fraction_arithmetic(
        left: Annotated[str, Field(description=_FRACTION_OPERAND_DESCRIPTION, pattern=_FRACTION_TEXT_PATTERN, max_length=PREBUILT_MAX_FRACTION_TEXT_CHARS)],
        right: Annotated[str, Field(description=_FRACTION_OPERAND_DESCRIPTION, pattern=_FRACTION_TEXT_PATTERN, max_length=PREBUILT_MAX_FRACTION_TEXT_CHARS)],
        operation: Annotated[ArithmeticOperation, Field(description=_OPERATION_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Add, subtract, multiply, or divide two exact fractions and return the result in lowest terms with a decimal approximation. Use it for ratios, recipe scaling, probabilities, and any calculation that must stay exact. The result is written as numerator slash denominator with the sign on the numerator, or as a plain integer, and the approximation is rounded half to even at 20 fractional digits. A zero denominator fails naming its input, dividing by zero fails naming right, and a numerator or denominator of more than 4,000 digits fails with an error."""
        # Read both fractions, refusing zero denominators and inputs
        # over the digit cap, then refuse a division by zero.
        left_value = ExactArithmeticToolFunctions._parse_fraction(left, "left")
        right_value = ExactArithmeticToolFunctions._parse_fraction(right, "right")
        if operation is ArithmeticOperation.DIVIDE and right_value == 0:
            raise PrebuiltToolSupport.argument_error("right", "it is zero, so the division has no result", "a divisor other than zero")

        # Combine them exactly; Fraction keeps lowest terms by itself.
        result: Fraction = _OPERATIONS[operation](left_value, right_value)

        # @intent prebuilt-integer-digit-cap
        # A numerator or denominator of more than 4,000 digits cannot be
        # written as text safely and would flood the model's context.
        if abs(result.numerator) >= _INTEGER_RESULT_BOUND or result.denominator >= _INTEGER_RESULT_BOUND:
            raise PrebuiltToolSupport.argument_error("left", f"the result has a numerator or denominator of more than {PREBUILT_MAX_INTEGER_DIGITS} digits", f"operands whose result has at most {PREBUILT_MAX_INTEGER_DIGITS} digits above and below the line")

        # Round the exact result once for the decimal approximation.
        with PrebuiltToolSupport.decimal_context(_EXACT_PRECISION):
            approximation, _ = ExactArithmeticToolFunctions._round_half_even(result, PREBUILT_APPROXIMATION_DIGITS)
        return {"result": PrebuiltToolSupport.fraction_text(result), "decimal_approximation": PrebuiltToolSupport.decimal_text(approximation)}

    @staticmethod
    def decimal_to_fraction(
        value: Annotated[str, Field(description=_DECIMAL_OPERAND_DESCRIPTION, pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        max_denominator: Annotated[int | None, Field(description="The largest denominator the fraction may have, or null for the exact fraction. When set, the result is the closest fraction whose denominator does not exceed this bound. The bound must be between 1 and one trillion. The default is null.", ge=1, le=PREBUILT_MAX_DENOMINATOR)] = None,
    ) -> PrebuiltToolOutput:
        """Convert an exact decimal number to a fraction in lowest terms, optionally the closest fraction whose denominator stays within a bound. Use it to turn a decimal into an exact ratio or to find a simple fraction that approximates a measured value. Without a bound the fraction equals the decimal exactly, and with a bound it is the best approximation with that largest denominator. The exact flag says whether the fraction still equals the decimal, and the tool has no failure case beyond its schema caps."""
        exact_value = Fraction(PrebuiltToolSupport.parse_decimal_text(value, "value"))
        fraction = exact_value if max_denominator is None else exact_value.limit_denominator(max_denominator)
        return {"fraction": PrebuiltToolSupport.fraction_text(fraction), "exact": fraction == exact_value}

    @staticmethod
    def repeating_decimal_to_fraction(
        value: Annotated[str, Field(description="A decimal number whose repeating block of digits is written in parentheses at the end. It has an optional sign, optional digits before the point, a decimal point, optional digits that do not repeat, and then the repeating digits in parentheses. The sign applies to the whole value. It must hold between 1 and 1,000 characters.", min_length=1, max_length=PREBUILT_MAX_EXPRESSION_CHARS, pattern=_REPEATING_DECIMAL_PATTERN)],
    ) -> PrebuiltToolOutput:
        """Convert a decimal number with a repeating block of digits, written in parentheses, into the exact fraction it equals. Use it when a repeating decimal must become an exact ratio, which is error-prone to work out by hand. The result is in lowest terms with the sign on the numerator, or a plain integer, and a block of repeating nines rounds up to the next value. Text without a parenthesized block at the end fails validation."""
        match = _REPEATING_DECIMAL.fullmatch(value)
        if match is None:
            raise PrebuiltToolSupport.argument_error("value", "the text is not a decimal with a repeating block in parentheses", "an optional sign, digits, a decimal point, and repeating digits in parentheses")
        sign, whole, prefix, block = match.groups()
        prefix_scale = _DECIMAL_BASE ** len(prefix)
        magnitude = int(whole or "0") + Fraction(int(prefix or "0"), prefix_scale) + Fraction(int(block), prefix_scale * (_DECIMAL_BASE ** len(block) - 1))
        return {"fraction": PrebuiltToolSupport.fraction_text(-magnitude if sign == "-" else magnitude)}

    @staticmethod
    def fraction_to_decimal(
        fraction: Annotated[str, Field(description=_FRACTION_OPERAND_DESCRIPTION, pattern=_FRACTION_TEXT_PATTERN, max_length=PREBUILT_MAX_FRACTION_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Expand a fraction into its decimal digits by long division, marking the shortest repeating block in parentheses. Use it to see the exact decimal form of a ratio, including where and how its digits repeat. At most 1,000 fractional digits are produced, and an expansion that needs more is cut without rounding, with no parentheses and truncated set to true. A terminating expansion has no parentheses and an empty repeating_digits, and a zero denominator fails with an error naming fraction."""
        # Read the fraction and split off its sign and whole part.
        value = ExactArithmeticToolFunctions._parse_fraction(fraction, "fraction")
        sign = "-" if value < 0 else ""
        whole, remainder = divmod(abs(value.numerator), value.denominator)

        # Long division finds the fractional digits and where they start
        # to repeat; the denominator alone says whether they terminate.
        digits, block_start, truncated = ExactArithmeticToolFunctions._expand_digits(remainder, value.denominator)
        terminates = pow(_DECIMAL_BASE, value.denominator.bit_length(), value.denominator) == 0

        # Write the digits, with the repeating block in parentheses.
        if block_start is None:
            decimal = f"{sign}{whole}.{digits}" if digits else f"{sign}{whole}"
            return {"decimal": decimal, "terminates": terminates, "repeating_digits": "", "truncated": truncated}
        decimal = f"{sign}{whole}.{digits[:block_start]}({digits[block_start:]})"
        return {"decimal": decimal, "terminates": terminates, "repeating_digits": digits[block_start:], "truncated": truncated}

    @staticmethod
    def integer_square_root(
        value: Annotated[str, Field(description="The non-negative integer whose square root is wanted, written as decimal digits with an optional plus sign. Leading zeros are allowed. It may hold at most 4,001 characters. A negative value fails with an error naming value.", pattern=PREBUILT_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Compute the exact integer square root of a non-negative integer, the remainder left over, and whether the integer is a perfect square. Use it for exact square roots of large integers, where a floating-point square root loses digits. The root is the largest integer whose square does not exceed the value, and the remainder is the value minus the square of the root. A negative value fails with an error naming value."""
        number = PrebuiltToolSupport.parse_integer_text(value, "value")
        if number < 0:
            raise PrebuiltToolSupport.argument_error("value", "it is negative, so it has no real square root", "an integer of zero or more")
        root = math.isqrt(number)
        remainder = number - root * root
        return {"root": PrebuiltToolSupport.integer_text(root, "value"), "is_perfect_square": remainder == 0, "remainder": PrebuiltToolSupport.integer_text(remainder, "value")}

    @staticmethod
    def solve_quadratic_equation(
        a: Annotated[float, Field(description=_COEFFICIENT_DESCRIPTION, allow_inf_nan=False)],
        b: Annotated[float, Field(description=_COEFFICIENT_DESCRIPTION, allow_inf_nan=False)],
        c: Annotated[float, Field(description=_COEFFICIENT_DESCRIPTION, allow_inf_nan=False)],
    ) -> PrebuiltToolOutput:
        """Find the real or complex roots of the quadratic equation a times x squared plus b times x plus c equals zero, with its discriminant. Use it to solve a quadratic exactly as written instead of rearranging it by hand. Real roots are listed in ascending order using the numerically stable formula, a double root is listed once, a complex pair lists the positive imaginary part first, and a zero a solves the linear equation instead. When a and b are both zero, or when any intermediate value overflows, the call fails with an error naming a."""
        # Refuse an equation without x, then compute the discriminant.
        if a == 0 and b == 0:
            raise PrebuiltToolSupport.argument_error("a", "a and b are both zero, so there is no equation to solve", "a non-zero a or b")
        discriminant = PrebuiltToolSupport.float_result(b * b - 4.0 * a * c, "a")

        # Solve in floats, refusing any root that overflowed.
        roots = ExactArithmeticToolFunctions._quadratic_roots(a, b, c, discriminant)
        listed = [{"real": PrebuiltToolSupport.float_result(real, "a") + 0.0, "imaginary": PrebuiltToolSupport.float_result(imaginary, "a") + 0.0} for real, imaginary in roots]
        return {"discriminant": discriminant + 0.0, "root_count": len(listed), "roots": listed}

    @staticmethod
    def _round_half_even(value: Fraction, places: int) -> tuple[Decimal, bool]:
        """Round an exact Fraction half to even at a number of fractional places, and say whether it was already exact."""
        scaled = value * _DECIMAL_BASE**places
        whole, remainder = divmod(abs(scaled.numerator), scaled.denominator)
        twice_remainder = 2 * remainder
        if twice_remainder > scaled.denominator or (twice_remainder == scaled.denominator and whole % 2 == 1):
            whole += 1
        return Decimal(-whole if scaled < 0 else whole).scaleb(-places), remainder == 0

    @staticmethod
    def _round_to_figures(number: Decimal, figures: int, rounding: str) -> Decimal:
        """Round a non-zero Decimal to a number of significant figures, rounding again one place higher after a carry."""
        last_place = number.adjusted() - figures + 1
        rounded = number.quantize(Decimal((0, (1,), last_place)), rounding=rounding)
        if rounded.adjusted() > number.adjusted():
            rounded = number.quantize(Decimal((0, (1,), last_place + 1)), rounding=rounding)
        return rounded

    @staticmethod
    def _parse_fraction(text: str, parameter_name: str) -> Fraction:
        """Read fraction text as an exact Fraction, refusing a zero denominator and parts over the digit cap."""
        match = _FRACTION_TEXT.fullmatch(text)
        if match is None:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the text is not a fraction", "an integer, or an integer numerator, a slash, and a positive integer denominator")
        sign, numerator_text, denominator_text = match.groups()
        numerator_digits = numerator_text.lstrip("0")
        denominator_digits = (denominator_text or "1").lstrip("0")
        # @intent prebuilt-integer-digit-cap
        # Python refuses to read more than 4,300 digits as an int, and
        # such a part would flood the model's context, so a part of more
        # than 4,000 significant digits fails before any conversion.
        if max(len(numerator_digits), len(denominator_digits)) > PREBUILT_MAX_INTEGER_DIGITS:
            problem = f"its numerator or denominator has more than {PREBUILT_MAX_INTEGER_DIGITS} significant digits"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, f"a numerator and denominator of at most {PREBUILT_MAX_INTEGER_DIGITS} digits each")
        if not denominator_digits:
            raise PrebuiltToolSupport.argument_error(parameter_name, "its denominator is zero", "a fraction whose denominator is a positive integer")
        numerator = int(numerator_digits or "0")
        return Fraction(-numerator if sign == "-" else numerator, int(denominator_digits))

    @staticmethod
    def _expand_digits(remainder: int, denominator: int) -> tuple[str, int | None, bool]:
        """Long-divide a proper remainder, returning the fractional digits, where the repeating block starts, and whether the digit cap cut it."""
        digits: list[str] = []
        seen: dict[int, int] = {}
        while remainder and remainder not in seen:
            if len(digits) == PREBUILT_MAX_DECIMAL_PLACES:
                return "".join(digits), None, True
            seen[remainder] = len(digits)
            digit, remainder = divmod(remainder * _DECIMAL_BASE, denominator)
            digits.append(str(digit))
        return "".join(digits), seen.get(remainder) if remainder else None, False

    @staticmethod
    def _quadratic_roots(a: float, b: float, c: float, discriminant: float) -> list[tuple[float, float]]:
        """Return the (real, imaginary) roots: one for a linear or double root, two ascending real roots, or a complex pair."""
        try:
            if a == 0:
                return [(-c / b, 0.0)]
            if discriminant == 0:
                return [(-0.5 * b / a, 0.0)]
            if discriminant < 0:
                imaginary = 0.5 * math.sqrt(-discriminant) / abs(a)
                return [(-0.5 * b / a, imaginary), (-0.5 * b / a, -imaginary)]
            # The stable formula never subtracts two nearly equal
            # values, so the smaller root keeps its precision.
            q = -0.5 * (b + math.copysign(math.sqrt(discriminant), b))
            first, second = sorted((q / a, c / q))
        except ZeroDivisionError as exc:
            raise PrebuiltToolSupport.argument_error("a", "the roots could not be computed in floating point", "coefficients whose roots are finite numbers") from exc
        return [(first, 0.0), (second, 0.0)]

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.decimal_arithmetic,
            cls.round_decimal,
            cls.round_significant_figures,
            cls.sum_decimal_list,
            cls.fraction_arithmetic,
            cls.decimal_to_fraction,
            cls.repeating_decimal_to_fraction,
            cls.fraction_to_decimal,
            cls.integer_square_root,
            cls.solve_quadratic_equation,
        )


__all__ = ["ExactArithmeticToolFunctions"]
