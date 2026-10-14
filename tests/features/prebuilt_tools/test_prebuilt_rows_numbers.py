"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_numbers.py

PURPOSE: Exact-output and error cases for every Appendix A row of the exact_arithmetic, number_theory, and number_formatting categories (A.1 to A.3, 27 tools), plus round-trip properties between tools that invert each other.
ROLE IN CODEBASE: Calls each tool through FunctionTool.execute via the session ToolRunner from tests/features/prebuilt_tools/conftest.py; the cases and matching rules come from prebuilt_tool_harness.py.
ARCHITECTURE NOTE: Every expected value was computed by hand, taken from a published table (prime counts, the Wikipedia modular-power example, the 13-base Miller-Rabin bound), or computed by a different route (integer division instead of long division, factor products instead of trial division). Nothing here reuses implementation code.
FUNCTION INVENTORY: first_primes and divisors_from_factors build long expected lists by an independent route; test_numbers_rows_return_documented_output checks SUCCESS_CASES; test_numbers_rows_reject_bad_input checks FAILURE_CASES; test_number_words_round_trip, test_fraction_decimal_round_trip, test_gcd_times_lcm_equals_product, and test_modular_inverse_times_value_is_one check algebraic identities across tools.
COMMON MODIFICATION PATTERNS: Add a row case as ok(...), bad(...), or invalid(...) in the table of its category; give it a label that names the edge it covers, and list every output key the row documents.
WHAT NOT TO DO IN THIS FILE: 1. Do not compute an expectation by calling the tool or importing vidbyte.tools.builtins.prebuilt; that would compare the implementation with itself. 2. Do not build expected integers of more than 4,300 digits with str(int); repeat characters instead, as the 4,000-digit cases do.
KNOWN EDGE CASES: Rounding ties (2.675, 0.125, 1/8 at two places, 5e-21) separate half-even from half-up; rounded zeros never carry a minus sign; 318665857834031151167461 is a strong pseudoprime to the first twelve prime bases, so only base 41 rejects it.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.1, A.2, A.3 and §9.2 items 2, 5, and 13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_numbers.py
"""

from __future__ import annotations

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import FailureCase, SuccessCase, ToolRunner, bad, invalid, ok

MAX_PRIMALITY_VALUE = "3317044064679887385961980"
NINES_GROUP = "nine hundred ninety-nine"
SCALE_WORDS = (
    "decillion", "nonillion", "octillion", "septillion", "sextillion", "quintillion",
    "quadrillion", "trillion", "billion", "million", "thousand",
)
NINES_36_WORDS = " ".join(f"{NINES_GROUP} {scale}" for scale in SCALE_WORDS) + f" {NINES_GROUP}"
TEN_TO_THE_3999 = "1" + "0" * 3999
TEN_TO_THE_4000 = "1" + "0" * 4000


def first_primes(count: int) -> list[int]:
    """The first `count` primes by trial division, a different route from any sieve."""
    found: list[int] = []
    candidate = 2
    while len(found) < count:
        if all(candidate % prime for prime in found if prime * prime <= candidate):
            found.append(candidate)
        candidate += 1
    return found


def divisors_from_factors(factors: list[tuple[int, int]]) -> list[int]:
    """Every divisor of the product of p^e, built from the factorization instead of by trial division."""
    divisors = [1]
    for prime, exponent in factors:
        divisors = [divisor * prime**power for divisor in divisors for power in range(exponent + 1)]
    return sorted(divisors)


TERA_DIVISORS = divisors_from_factors([(2, 12), (5, 12)])
HIGHLY_COMPOSITE_DIVISORS = divisors_from_factors([(2, 6), (3, 4), (5, 2), (7, 1), (11, 1), (13, 1), (17, 1), (19, 1), (23, 1)])
ONE_OVER_1019_DIGITS = str(10**1000 // 1019).zfill(1000)

EXACT_ARITHMETIC_SUCCESS = [
    ok("decimal_arithmetic", {"left": "0.1", "right": "0.2", "operation": "add"}, {"result": "0.3", "exact": True}, "add-no-float-error"),
    ok("decimal_arithmetic", {"left": "1.10", "right": "1.1", "operation": "subtract"}, {"result": "0", "exact": True}, "subtract-to-canonical-zero"),
    ok("decimal_arithmetic", {"left": "1.5", "right": "-2.20", "operation": "multiply"}, {"result": "-3.3", "exact": True}, "multiply-drops-trailing-zeros"),
    ok("decimal_arithmetic", {"left": "0.333", "right": "3", "operation": "multiply", "decimal_places": 0}, {"result": "0.999", "exact": True}, "multiply-ignores-places"),
    ok("decimal_arithmetic", {"left": "1", "right": "3", "operation": "divide"}, {"result": "0." + "3" * 28, "exact": False}, "divide-default-28-places"),
    ok("decimal_arithmetic", {"left": "1", "right": "8", "operation": "divide"}, {"result": "0.125", "exact": True}, "divide-terminating-exact"),
    ok("decimal_arithmetic", {"left": "1", "right": "8", "operation": "divide", "decimal_places": 2}, {"result": "0.12", "exact": False}, "divide-tie-half-even"),
    ok("decimal_arithmetic", {"left": "5", "right": "2", "operation": "divide", "decimal_places": 0}, {"result": "2", "exact": False}, "divide-tie-to-even-two"),
    ok("decimal_arithmetic", {"left": "-7", "right": "2", "operation": "divide", "decimal_places": 0}, {"result": "-4", "exact": False}, "divide-negative-tie"),
    ok("decimal_arithmetic", {"left": "-1", "right": "3", "operation": "divide", "decimal_places": 0}, {"result": "0", "exact": False}, "divide-rounded-zero-unsigned"),
    ok("decimal_arithmetic", {"left": "100", "right": "4", "operation": "divide"}, {"result": "25", "exact": True}, "divide-integer-result"),
    ok("decimal_arithmetic", {"left": "9" * 4000, "right": "0", "operation": "add"}, {"result": "9" * 4000, "exact": True}, "just-under-digit-cap"),
    ok("round_decimal", {"value": "2.5"}, {"result": "2"}, "default-half-even-zero-places"),
    ok("round_decimal", {"value": "3.5"}, {"result": "4"}, "half-even-rounds-up-to-even"),
    ok("round_decimal", {"value": "2.675", "decimal_places": 2}, {"result": "2.68"}, "exact-decimal-tie-not-binary-float"),
    ok("round_decimal", {"value": "2.675", "decimal_places": 2, "mode": "half_down"}, {"result": "2.67"}, "half-down-tie"),
    ok("round_decimal", {"value": "2.665", "decimal_places": 2, "mode": "half_up"}, {"result": "2.67"}, "half-up-tie"),
    ok("round_decimal", {"value": "2.665", "decimal_places": 2}, {"result": "2.66"}, "half-even-tie-down"),
    ok("round_decimal", {"value": "0.0125", "decimal_places": 3}, {"result": "0.012"}, "half-even-small-tie"),
    ok("round_decimal", {"value": "0.0125", "decimal_places": 3, "mode": "half_up"}, {"result": "0.013"}, "half-up-small-tie"),
    ok("round_decimal", {"value": "-0.004", "decimal_places": 2}, {"result": "0.00"}, "rounded-zero-has-no-sign"),
    ok("round_decimal", {"value": "1.5", "decimal_places": 3}, {"result": "1.500"}, "keeps-trailing-zeros"),
    ok("round_decimal", {"value": "-2.5", "mode": "up"}, {"result": "-3"}, "up-is-away-from-zero"),
    ok("round_decimal", {"value": "-2.5", "mode": "ceiling"}, {"result": "-2"}, "ceiling-toward-positive"),
    ok("round_decimal", {"value": "-2.5", "mode": "floor"}, {"result": "-3"}, "floor-toward-negative"),
    ok("round_decimal", {"value": "-2.5", "mode": "down"}, {"result": "-2"}, "down-toward-zero"),
    ok("round_decimal", {"value": "-123.456", "decimal_places": 1, "mode": "ceiling"}, {"result": "-123.4"}, "negative-ceiling"),
    ok("round_significant_figures", {"value": "2.5", "significant_figures": 3}, {"result": "2.50"}, "adds-fractional-zeros"),
    ok("round_significant_figures", {"value": "1", "significant_figures": 3}, {"result": "1.00"}, "integer-padded"),
    ok("round_significant_figures", {"value": "123456", "significant_figures": 2}, {"result": "120000"}, "place-holding-zeros"),
    ok("round_significant_figures", {"value": "9.99", "significant_figures": 2}, {"result": "10"}, "carry-new-leading-digit"),
    ok("round_significant_figures", {"value": "99.5", "significant_figures": 2}, {"result": "100"}, "tie-carry-to-hundred"),
    ok("round_significant_figures", {"value": "0.0999", "significant_figures": 2}, {"result": "0.10"}, "carry-keeps-fraction-zero"),
    ok("round_significant_figures", {"value": "0", "significant_figures": 3}, {"result": "0"}, "zero"),
    ok("round_significant_figures", {"value": "-0.0012345", "significant_figures": 3}, {"result": "-0.00123"}, "negative-small"),
    ok("round_significant_figures", {"value": "1250", "significant_figures": 2}, {"result": "1200"}, "half-even-tie"),
    ok("round_significant_figures", {"value": "1250", "significant_figures": 2, "mode": "half_up"}, {"result": "1300"}, "half-up-tie"),
    ok("sum_decimal_list", {"values": ["0.1", "0.2", "0.3"]}, {"sum": "0.6", "count": 3}, "no-float-error"),
    ok("sum_decimal_list", {"values": ["1.50", "-1.5"]}, {"sum": "0", "count": 2}, "cancel-to-zero"),
    ok("sum_decimal_list", {"values": ["+1", ".5", "2."]}, {"sum": "3.5", "count": 3}, "decimal-text-forms"),
    ok("fraction_arithmetic", {"left": "1/3", "right": "1/6", "operation": "add"}, {"result": "1/2", "decimal_approximation": "0.5"}, "add-lowest-terms"),
    ok("fraction_arithmetic", {"left": "1/3", "right": "1/3", "operation": "add"}, {"result": "2/3", "decimal_approximation": "0.66666666666666666667"}, "approximation-20-digits"),
    ok("fraction_arithmetic", {"left": "-3/4", "right": "2/3", "operation": "multiply"}, {"result": "-1/2", "decimal_approximation": "-0.5"}, "negative-product"),
    ok("fraction_arithmetic", {"left": "5", "right": "5/1", "operation": "subtract"}, {"result": "0", "decimal_approximation": "0"}, "zero-result"),
    ok("fraction_arithmetic", {"left": "1/7", "right": "2", "operation": "divide"}, {"result": "1/14", "decimal_approximation": "0.07142857142857142857"}, "divide"),
    ok("fraction_arithmetic", {"left": "1/2", "right": "-1/4", "operation": "divide"}, {"result": "-2", "decimal_approximation": "-2"}, "integer-result-sign-on-p"),
    ok("fraction_arithmetic", {"left": "6/4", "right": "1/4", "operation": "subtract"}, {"result": "5/4", "decimal_approximation": "1.25"}, "reduces-input"),
    ok("fraction_arithmetic", {"left": "1/200000000000000000000", "right": "0", "operation": "add"}, {"result": "1/200000000000000000000", "decimal_approximation": "0"}, "approximation-tie-to-even-zero"),
    ok("fraction_arithmetic", {"left": "3/200000000000000000000", "right": "0", "operation": "add"}, {"result": "3/200000000000000000000", "decimal_approximation": "0.00000000000000000002"}, "approximation-tie-to-even-two"),
    ok("decimal_to_fraction", {"value": "0.75"}, {"fraction": "3/4", "exact": True}, "exact"),
    ok("decimal_to_fraction", {"value": "-2.5"}, {"fraction": "-5/2", "exact": True}, "negative"),
    ok("decimal_to_fraction", {"value": "3"}, {"fraction": "3", "exact": True}, "integer"),
    ok("decimal_to_fraction", {"value": "0.000"}, {"fraction": "0", "exact": True}, "zero"),
    ok("decimal_to_fraction", {"value": "3.14159", "max_denominator": 100}, {"fraction": "311/99", "exact": False}, "bounded-denominator"),
    ok("decimal_to_fraction", {"value": "0.5", "max_denominator": 2}, {"fraction": "1/2", "exact": True}, "bound-still-exact"),
    ok("decimal_to_fraction", {"value": "1.1", "max_denominator": 1}, {"fraction": "1", "exact": False}, "bound-of-one"),
    ok("repeating_decimal_to_fraction", {"value": "0.(9)"}, {"fraction": "1"}, "nines-are-one"),
    ok("repeating_decimal_to_fraction", {"value": ".(3)"}, {"fraction": "1/3"}, "no-integer-part"),
    ok("repeating_decimal_to_fraction", {"value": "-0.1(6)"}, {"fraction": "-1/6"}, "sign-applies-to-whole"),
    ok("repeating_decimal_to_fraction", {"value": "1.2(34)"}, {"fraction": "611/495"}, "non-repeating-prefix"),
    ok("repeating_decimal_to_fraction", {"value": "0.(142857)"}, {"fraction": "1/7"}, "six-digit-block"),
    ok("repeating_decimal_to_fraction", {"value": "+3.(0)"}, {"fraction": "3"}, "zero-block"),
    ok("fraction_to_decimal", {"fraction": "1/6"}, {"decimal": "0.1(6)", "terminates": False, "repeating_digits": "6", "truncated": False}, "late-start-block"),
    ok("fraction_to_decimal", {"fraction": "1/8"}, {"decimal": "0.125", "terminates": True, "repeating_digits": "", "truncated": False}, "terminating"),
    ok("fraction_to_decimal", {"fraction": "6/4"}, {"decimal": "1.5", "terminates": True, "repeating_digits": "", "truncated": False}, "improper"),
    ok("fraction_to_decimal", {"fraction": "22/7"}, {"decimal": "3.(142857)", "terminates": False, "repeating_digits": "142857", "truncated": False}, "integer-part"),
    ok("fraction_to_decimal", {"fraction": "-1/3"}, {"decimal": "-0.(3)", "terminates": False, "repeating_digits": "3", "truncated": False}, "negative-shortest-block"),
    ok("fraction_to_decimal", {"fraction": "1/12"}, {"decimal": "0.08(3)", "terminates": False, "repeating_digits": "3", "truncated": False}, "two-digit-prefix"),
    ok("fraction_to_decimal", {"fraction": "1/11"}, {"decimal": "0.(09)", "terminates": False, "repeating_digits": "09", "truncated": False}, "block-with-leading-zero"),
    ok("fraction_to_decimal", {"fraction": "1/1019"}, {"decimal": "0." + ONE_OVER_1019_DIGITS, "terminates": False, "repeating_digits": "", "truncated": True}, "period-1018-truncated"),
    ok("integer_square_root", {"value": "17"}, {"root": "4", "is_perfect_square": False, "remainder": "1"}, "not-square"),
    ok("integer_square_root", {"value": "0"}, {"root": "0", "is_perfect_square": True, "remainder": "0"}, "zero"),
    ok("integer_square_root", {"value": "+0016"}, {"root": "4", "is_perfect_square": True, "remainder": "0"}, "sign-and-leading-zeros"),
    ok("integer_square_root", {"value": "99999999999999999999"}, {"root": "9999999999", "is_perfect_square": False, "remainder": "19999999998"}, "beyond-float-precision"),
    ok("integer_square_root", {"value": TEN_TO_THE_4000}, {"root": "1" + "0" * 2000, "is_perfect_square": True, "remainder": "0"}, "largest-input"),
    ok("solve_quadratic_equation", {"a": 1, "b": -3, "c": 2}, {"discriminant": 1.0, "root_count": 2, "roots": [{"real": 1.0, "imaginary": 0.0}, {"real": 2.0, "imaginary": 0.0}]}, "two-real-ascending"),
    ok("solve_quadratic_equation", {"a": 2, "b": -4, "c": -6}, {"discriminant": 64.0, "root_count": 2, "roots": [{"real": -1.0, "imaginary": 0.0}, {"real": 3.0, "imaginary": 0.0}]}, "leading-coefficient"),
    ok("solve_quadratic_equation", {"a": 1, "b": 2, "c": 1}, {"discriminant": 0.0, "root_count": 1, "roots": [{"real": -1.0, "imaginary": 0.0}]}, "double-root-once"),
    ok("solve_quadratic_equation", {"a": 1, "b": 0, "c": 1}, {"discriminant": -4.0, "root_count": 2, "roots": [{"real": 0.0, "imaginary": 1.0}, {"real": 0.0, "imaginary": -1.0}]}, "complex-positive-first"),
    ok("solve_quadratic_equation", {"a": 1, "b": 2, "c": 5}, {"discriminant": -16.0, "root_count": 2, "roots": [{"real": -1.0, "imaginary": 2.0}, {"real": -1.0, "imaginary": -2.0}]}, "complex-pair"),
    ok("solve_quadratic_equation", {"a": 0, "b": 2, "c": -4}, {"discriminant": 4.0, "root_count": 1, "roots": [{"real": 2.0, "imaginary": 0.0}]}, "linear"),
    ok("solve_quadratic_equation", {"a": 1, "b": -1e8, "c": 1}, {"discriminant": 9999999999999996.0, "root_count": 2, "roots": [{"real": 1e-8, "imaginary": 0.0}, {"real": 99999999.99999999, "imaginary": 0.0}]}, "stable-formula-small-root"),
]

EXACT_ARITHMETIC_FAILURES = [
    bad("decimal_arithmetic", {"left": "1", "right": "0", "operation": "divide"}, "right", "divide-by-zero"),
    bad("decimal_arithmetic", {"left": "1", "right": "-0.000", "operation": "divide"}, "right", "divide-by-signed-zero-text"),
    bad("decimal_arithmetic", {"left": "9" * 4000, "right": "1", "operation": "add"}, "left", "sum-reaches-ten-to-4000"),
    bad("decimal_arithmetic", {"left": "9" * 4000, "right": "10", "operation": "multiply"}, "left", "product-over-digit-cap"),
    invalid("decimal_arithmetic", {"left": "1e5", "right": "1", "operation": "add"}, "left", "exponent-not-decimal-text"),
    invalid("decimal_arithmetic", {"left": "1", "right": "3", "operation": "divide", "decimal_places": 1001}, "decimal_places", "places-over-bound"),
    invalid("decimal_arithmetic", {"left": "1", "right": "3", "operation": "power"}, "operation", "unknown-operation"),
    invalid("round_decimal", {"value": "abc"}, "value", "not-decimal-text"),
    invalid("round_decimal", {"value": "1.5", "mode": "bankers"}, "mode", "unknown-mode"),
    invalid("round_significant_figures", {"value": "1.5", "significant_figures": 0}, "significant_figures", "zero-figures"),
    invalid("round_significant_figures", {"value": "1.5", "significant_figures": 101}, "significant_figures", "over-figure-bound"),
    bad("sum_decimal_list", {"values": ["9" * 4000, "1"]}, "values", "sum-reaches-ten-to-4000"),
    invalid("sum_decimal_list", {"values": []}, "values", "empty-list"),
    bad("fraction_arithmetic", {"left": "1/0", "right": "1", "operation": "add"}, "left", "zero-denominator-left"),
    bad("fraction_arithmetic", {"left": "1", "right": "3/0", "operation": "add"}, "right", "zero-denominator-right"),
    bad("fraction_arithmetic", {"left": "1", "right": "0/5", "operation": "divide"}, "right", "divide-by-zero"),
    bad("fraction_arithmetic", {"left": TEN_TO_THE_3999, "right": "100", "operation": "multiply"}, "left", "numerator-over-4000-digits"),
    invalid("fraction_arithmetic", {"left": "1/-3", "right": "1", "operation": "add"}, "left", "sign-on-denominator"),
    invalid("decimal_to_fraction", {"value": "0.5", "max_denominator": 0}, "max_denominator", "zero-bound"),
    invalid("decimal_to_fraction", {"value": "0.5", "max_denominator": 1_000_000_000_001}, "max_denominator", "over-bound"),
    invalid("repeating_decimal_to_fraction", {"value": "0.3"}, "value", "no-repeating-block"),
    bad("fraction_to_decimal", {"fraction": "1/0"}, "fraction", "zero-denominator"),
    bad("integer_square_root", {"value": "-4"}, "value", "negative"),
    bad("solve_quadratic_equation", {"a": 0, "b": 0, "c": 1}, "a", "no-equation"),
    bad("solve_quadratic_equation", {"a": 1e300, "b": 1e300, "c": 1}, "a", "non-finite-discriminant"),
    invalid("solve_quadratic_equation", {"a": "x", "b": 1, "c": 1}, "a", "not-a-number"),
]

NUMBER_THEORY_SUCCESS = [
    ok("is_prime", {"value": "2"}, {"is_prime": True}, "two"),
    ok("is_prime", {"value": "1"}, {"is_prime": False}, "one"),
    ok("is_prime", {"value": "0"}, {"is_prime": False}, "zero"),
    ok("is_prime", {"value": "-7"}, {"is_prime": False}, "negative"),
    ok("is_prime", {"value": "0007"}, {"is_prime": True}, "leading-zeros"),
    ok("is_prime", {"value": "561"}, {"is_prime": False}, "carmichael"),
    ok("is_prime", {"value": "2305843009213693951"}, {"is_prime": True}, "mersenne-61"),
    ok("is_prime", {"value": "318665857834031151167461"}, {"is_prime": False}, "pseudoprime-to-twelve-bases"),
    ok("is_prime", {"value": MAX_PRIMALITY_VALUE}, {"is_prime": False}, "bound-accepted"),
    ok("prime_factorize", {"value": 360}, {"factors": [{"prime": 2, "exponent": 3}, {"prime": 3, "exponent": 2}, {"prime": 5, "exponent": 1}], "expression": "2^3 * 3^2 * 5"}, "mixed"),
    ok("prime_factorize", {"value": 1}, {"factors": [], "expression": "1"}, "one"),
    ok("prime_factorize", {"value": 97}, {"factors": [{"prime": 97, "exponent": 1}], "expression": "97"}, "prime"),
    ok("prime_factorize", {"value": 1_000_000_000_000}, {"factors": [{"prime": 2, "exponent": 12}, {"prime": 5, "exponent": 12}], "expression": "2^12 * 5^12"}, "upper-bound"),
    ok("prime_factorize", {"value": 999_999_999_989}, {"factors": [{"prime": 999_999_999_989, "exponent": 1}], "expression": "999999999989"}, "large-prime"),
    ok("list_primes_in_range", {"start": 10, "end": 30}, {"primes": [11, 13, 17, 19, 23, 29], "count": 6, "truncated": False}, "inclusive-range"),
    ok("list_primes_in_range", {"start": 0, "end": 1}, {"primes": [], "count": 0, "truncated": False}, "no-primes"),
    ok("list_primes_in_range", {"start": 2, "end": 2}, {"primes": [2], "count": 1, "truncated": False}, "single-value"),
    ok("list_primes_in_range", {"start": 0, "end": 10_000_000}, {"primes": first_primes(1000), "count": 664579, "truncated": True}, "item-cap-full-count"),
    ok("nth_prime", {"n": 1}, {"prime": 2}, "first"),
    ok("nth_prime", {"n": 6}, {"prime": 13}, "sixth"),
    ok("nth_prime", {"n": 1000}, {"prime": 7919}, "thousandth"),
    ok("nth_prime", {"n": 100000}, {"prime": 1299709}, "upper-bound"),
    ok("next_prime", {"value": "10"}, {"prime": "11"}, "next"),
    ok("next_prime", {"value": "11"}, {"prime": "13"}, "strictly-above"),
    ok("next_prime", {"value": "0"}, {"prime": "2"}, "from-zero"),
    ok("next_prime", {"value": "100", "direction": "previous"}, {"prime": "97"}, "previous"),
    ok("next_prime", {"value": "3", "direction": "previous"}, {"prime": "2"}, "previous-to-two"),
    ok("next_prime", {"value": "2", "direction": "previous"}, {"prime": None}, "nothing-below-two"),
    ok("next_prime", {"value": "1000000000000"}, {"prime": "1000000000039"}, "above-ten-to-twelve"),
    ok("next_prime", {"value": "1000000000000", "direction": "previous"}, {"prime": "999999999989"}, "below-ten-to-twelve"),
    ok("greatest_common_divisor", {"values": ["12", "18"]}, {"gcd": "6"}, "pair"),
    ok("greatest_common_divisor", {"values": ["-12", "18", "30"]}, {"gcd": "6"}, "absolute-values"),
    ok("greatest_common_divisor", {"values": ["0", "0"]}, {"gcd": "0"}, "all-zero"),
    ok("greatest_common_divisor", {"values": ["0", "5"]}, {"gcd": "5"}, "zero-and-value"),
    ok("greatest_common_divisor", {"values": ["17", "5"]}, {"gcd": "1"}, "coprime"),
    ok("least_common_multiple", {"values": ["4", "6"]}, {"lcm": "12"}, "pair"),
    ok("least_common_multiple", {"values": ["-4", "6"]}, {"lcm": "12"}, "absolute-values"),
    ok("least_common_multiple", {"values": ["0", "5"]}, {"lcm": "0"}, "any-zero"),
    ok("least_common_multiple", {"values": ["2", "3", "5", "7"]}, {"lcm": "210"}, "many"),
    ok("least_common_multiple", {"values": [TEN_TO_THE_3999, "3"]}, {"lcm": "3" + "0" * 3999}, "just-under-digit-cap"),
    ok("list_divisors", {"value": 12}, {"divisors": [1, 2, 3, 4, 6, 12], "count": 6, "sum": 28, "truncated": False}, "twelve"),
    ok("list_divisors", {"value": 1}, {"divisors": [1], "count": 1, "sum": 1, "truncated": False}, "one"),
    ok("list_divisors", {"value": 1_000_000_000_000}, {"divisors": TERA_DIVISORS, "count": 169, "sum": 2499694822171, "truncated": False}, "upper-bound"),
    ok("list_divisors", {"value": 963_761_198_400}, {"divisors": HIGHLY_COMPOSITE_DIVISORS[:1000], "count": 6720, "sum": 5531765944320, "truncated": True}, "cap-counts-every-divisor"),
    ok("modular_exponentiation", {"base": "4", "exponent": "13", "modulus": "497"}, {"result": "445"}, "published-example"),
    ok("modular_exponentiation", {"base": "2", "exponent": "10", "modulus": "1000"}, {"result": "24"}, "small"),
    ok("modular_exponentiation", {"base": "3", "exponent": "-1", "modulus": "7"}, {"result": "5"}, "negative-exponent-inverse"),
    ok("modular_exponentiation", {"base": "-2", "exponent": "3", "modulus": "5"}, {"result": "2"}, "negative-base-in-range"),
    ok("modular_exponentiation", {"base": "5", "exponent": "3", "modulus": "1"}, {"result": "0"}, "modulus-one"),
    ok("modular_exponentiation", {"base": "2", "exponent": "1" + "0" * 2000, "modulus": "1000000007"}, {"result": "536875138"}, "huge-exponent-fermat"),
    ok("modular_inverse", {"value": "3", "modulus": "11"}, {"inverse": "4", "exists": True}, "small"),
    ok("modular_inverse", {"value": "10", "modulus": "17"}, {"inverse": "12", "exists": True}, "another"),
    ok("modular_inverse", {"value": "-3", "modulus": "11"}, {"inverse": "7", "exists": True}, "negative-value"),
    ok("modular_inverse", {"value": "6", "modulus": "9"}, {"inverse": None, "exists": False}, "shared-factor"),
    ok("modular_inverse", {"value": "0", "modulus": "7"}, {"inverse": None, "exists": False}, "zero-value"),
]

NUMBER_THEORY_FAILURES = [
    bad("is_prime", {"value": "3317044064679887385961981"}, "value", "above-primality-bound"),
    invalid("is_prime", {"value": "7.0"}, "value", "not-integer-text"),
    invalid("prime_factorize", {"value": 0}, "value", "zero"),
    invalid("prime_factorize", {"value": 1_000_000_000_001}, "value", "over-bound"),
    bad("list_primes_in_range", {"start": 20, "end": 10}, "start", "start-after-end"),
    invalid("list_primes_in_range", {"start": 0, "end": 10_000_001}, "end", "over-sieve-bound"),
    invalid("nth_prime", {"n": 0}, "n", "zero"),
    invalid("nth_prime", {"n": 100001}, "n", "over-bound"),
    bad("next_prime", {"value": MAX_PRIMALITY_VALUE}, "value", "search-passes-bound"),
    bad("next_prime", {"value": "3317044064679887385961981"}, "value", "above-bound"),
    invalid("next_prime", {"value": "10", "direction": "up"}, "direction", "unknown-direction"),
    invalid("greatest_common_divisor", {"values": ["12"]}, "values", "one-value"),
    invalid("least_common_multiple", {"values": ["4"]}, "values", "one-value"),
    bad("least_common_multiple", {"values": [TEN_TO_THE_3999, "11"]}, "values", "running-result-over-cap"),
    invalid("list_divisors", {"value": 0}, "value", "zero"),
    bad("modular_exponentiation", {"base": "2", "exponent": "-1", "modulus": "4"}, "base", "no-inverse"),
    bad("modular_exponentiation", {"base": "2", "exponent": "3", "modulus": "0"}, "modulus", "zero-modulus"),
    bad("modular_exponentiation", {"base": "2", "exponent": "3", "modulus": "-7"}, "modulus", "negative-modulus"),
    invalid("modular_exponentiation", {"base": "1" * 2002, "exponent": "3", "modulus": "7"}, "base", "operand-over-cap"),
    bad("modular_inverse", {"value": "3", "modulus": "1"}, "modulus", "modulus-one"),
    bad("modular_inverse", {"value": "3", "modulus": "0"}, "modulus", "modulus-zero"),
    bad("modular_inverse", {"value": "3", "modulus": "-5"}, "modulus", "negative-modulus"),
]

NUMBER_FORMATTING_SUCCESS = [
    ok("convert_number_base", {"value": "255", "from_base": 10, "to_base": 16}, {"result": "ff"}, "lowercase-output"),
    ok("convert_number_base", {"value": "FF", "from_base": 16, "to_base": 2}, {"result": "11111111"}, "uppercase-input"),
    ok("convert_number_base", {"value": "-zz", "from_base": 36, "to_base": 10}, {"result": "-1295"}, "sign-kept"),
    ok("convert_number_base", {"value": "ZZ", "from_base": 36, "to_base": 36}, {"result": "zz"}, "same-base-normalizes"),
    ok("convert_number_base", {"value": "0", "from_base": 10, "to_base": 2}, {"result": "0"}, "zero"),
    ok("convert_number_base", {"value": "0010", "from_base": 2, "to_base": 10}, {"result": "2"}, "leading-zeros"),
    ok("convert_number_base", {"value": "f" * 3000, "from_base": 16, "to_base": 2}, {"result": "1" * 12000}, "long-output"),
    ok("number_to_english_words", {"value": "0"}, {"words": "zero"}, "zero"),
    ok("number_to_english_words", {"value": "+7"}, {"words": "seven"}, "plus-sign"),
    ok("number_to_english_words", {"value": "21"}, {"words": "twenty-one"}, "hyphenated-tens"),
    ok("number_to_english_words", {"value": "105"}, {"words": "one hundred five"}, "no-and"),
    ok("number_to_english_words", {"value": "-42"}, {"words": "minus forty-two"}, "negative"),
    ok("number_to_english_words", {"value": "1000000"}, {"words": "one million"}, "scale"),
    ok("number_to_english_words", {"value": "1234567"}, {"words": "one million two hundred thirty-four thousand five hundred sixty-seven"}, "several-scales"),
    ok("number_to_english_words", {"value": "9" * 36}, {"words": NINES_36_WORDS}, "largest-decillion"),
    ok("number_to_english_words", {"value": "1", "ordinal": True}, {"words": "first"}, "ordinal-first"),
    ok("number_to_english_words", {"value": "12", "ordinal": True}, {"words": "twelfth"}, "ordinal-twelfth"),
    ok("number_to_english_words", {"value": "21", "ordinal": True}, {"words": "twenty-first"}, "ordinal-last-word-only"),
    ok("number_to_english_words", {"value": "40", "ordinal": True}, {"words": "fortieth"}, "ordinal-tens"),
    ok("number_to_english_words", {"value": "100", "ordinal": True}, {"words": "one hundredth"}, "ordinal-hundred"),
    ok("number_to_english_words", {"value": "1003", "ordinal": True}, {"words": "one thousand third"}, "ordinal-after-scale"),
    ok("english_words_to_number", {"words": "one hundred twenty-three"}, {"value": "123"}, "hundreds"),
    ok("english_words_to_number", {"words": "twenty one hundred"}, {"value": "2100"}, "hundred-multiplies-group"),
    ok("english_words_to_number", {"words": "nineteen hundred eighty four"}, {"value": "1984"}, "teen-hundred"),
    ok("english_words_to_number", {"words": "a thousand"}, {"value": "1000"}, "leading-a"),
    ok("english_words_to_number", {"words": "Minus  Five"}, {"value": "-5"}, "case-and-spaces"),
    ok("english_words_to_number", {"words": "one million, two hundred and five thousand and six"}, {"value": "1205006"}, "commas-and-and"),
    ok("english_words_to_number", {"words": "negative twelve thousand and one"}, {"value": "-12001"}, "negative-word"),
    ok("english_words_to_number", {"words": "zero"}, {"value": "0"}, "zero"),
    ok("english_words_to_number", {"words": "one decillion"}, {"value": "1" + "0" * 33}, "largest-scale"),
    ok("parse_abbreviated_number", {"text": "1.5k"}, {"value": "1500"}, "thousand-suffix"),
    ok("parse_abbreviated_number", {"text": "$2.3M"}, {"value": "2300000"}, "currency-and-uppercase"),
    ok("parse_abbreviated_number", {"text": "-4 bn"}, {"value": "-4000000000"}, "sign-space-billion"),
    ok("parse_abbreviated_number", {"text": "1,250 thousand"}, {"value": "1250000"}, "comma-groups-word"),
    ok("parse_abbreviated_number", {"text": "€0.5 tn"}, {"value": "500000000000"}, "euro-trillion"),
    ok("parse_abbreviated_number", {"text": "12mm"}, {"value": "12000000"}, "mm-is-million"),
    ok("parse_abbreviated_number", {"text": "+5K"}, {"value": "5000"}, "plus-sign"),
    ok("parse_abbreviated_number", {"text": "1.2345k"}, {"value": "1234.5"}, "exact-fraction"),
    ok("parse_abbreviated_number", {"text": "7"}, {"value": "7"}, "bare-number"),
    ok("format_number_with_separators", {"value": "1234567.891"}, {"formatted": "1,234,567.891"}, "default-style"),
    ok("format_number_with_separators", {"value": "1234567.891", "style": "period_comma"}, {"formatted": "1.234.567,891"}, "period-comma"),
    ok("format_number_with_separators", {"value": "-1234.5", "style": "space_comma", "decimal_places": 2}, {"formatted": "-1 234,50"}, "space-comma-padded"),
    ok("format_number_with_separators", {"value": "1234.5678", "style": "apostrophe_period", "decimal_places": 2}, {"formatted": "1'234.57"}, "apostrophe"),
    ok("format_number_with_separators", {"value": "1000000", "style": "underscore_period"}, {"formatted": "1_000_000"}, "underscore"),
    ok("format_number_with_separators", {"value": "1234", "style": "space_period"}, {"formatted": "1 234"}, "space-period"),
    ok("format_number_with_separators", {"value": ".5"}, {"formatted": "0.5"}, "adds-integer-zero"),
    ok("format_number_with_separators", {"value": "1."}, {"formatted": "1"}, "drops-bare-point"),
    ok("format_number_with_separators", {"value": "0001234"}, {"formatted": "1,234"}, "drops-leading-zeros"),
    ok("format_number_with_separators", {"value": "+1000"}, {"formatted": "1,000"}, "drops-plus"),
    ok("format_number_with_separators", {"value": "1.10"}, {"formatted": "1.10"}, "null-places-keeps-zeros"),
    ok("format_number_with_separators", {"value": "2.5", "decimal_places": 0}, {"formatted": "2"}, "half-even-no-point"),
    ok("format_number_with_separators", {"value": "0.125", "decimal_places": 2}, {"formatted": "0.12"}, "half-even-tie"),
    ok("format_number_with_separators", {"value": "-0.004", "decimal_places": 2}, {"formatted": "0.00"}, "zero-has-no-sign"),
    ok("format_number_with_separators", {"value": "-999.995", "decimal_places": 2}, {"formatted": "-1,000.00"}, "carry-adds-group"),
    ok("parse_formatted_number", {"text": "1,234.50"}, {"value": "1234.5", "is_percent": False}, "grouped"),
    ok("parse_formatted_number", {"text": "$1,234.56"}, {"value": "1234.56", "is_percent": False}, "currency"),
    ok("parse_formatted_number", {"text": "(1,234.00)"}, {"value": "-1234", "is_percent": False}, "accounting-negative"),
    ok("parse_formatted_number", {"text": "12.5%"}, {"value": "12.5", "is_percent": True}, "percent-not-divided"),
    ok("parse_formatted_number", {"text": "1.234,5", "style": "period_comma"}, {"value": "1234.5", "is_percent": False}, "period-comma"),
    ok("parse_formatted_number", {"text": "1 234,5", "style": "space_comma"}, {"value": "1234.5", "is_percent": False}, "space-comma"),
    ok("parse_formatted_number", {"text": "  -5  "}, {"value": "-5", "is_percent": False}, "trims"),
    ok("parse_formatted_number", {"text": "1234"}, {"value": "1234", "is_percent": False}, "ungrouped"),
    ok("to_scientific_notation", {"value": "12345"}, {"mantissa": "1.2345", "exponent": 4, "text": "1.2345e4"}, "scientific"),
    ok("to_scientific_notation", {"value": "0.00012"}, {"mantissa": "1.2", "exponent": -4, "text": "1.2e-4"}, "negative-exponent"),
    ok("to_scientific_notation", {"value": "1200"}, {"mantissa": "1.2", "exponent": 3, "text": "1.2e3"}, "canonical-mantissa"),
    ok("to_scientific_notation", {"value": "0"}, {"mantissa": "0", "exponent": 0, "text": "0e0"}, "zero"),
    ok("to_scientific_notation", {"value": "-0.00"}, {"mantissa": "0", "exponent": 0, "text": "0e0"}, "signed-zero"),
    ok("to_scientific_notation", {"value": "-123.45", "significant_figures": 2}, {"mantissa": "-1.2", "exponent": 2, "text": "-1.2e2"}, "rounded-negative"),
    ok("to_scientific_notation", {"value": "9.96", "significant_figures": 2}, {"mantissa": "1", "exponent": 1, "text": "1e1"}, "carry-moves-exponent"),
    ok("to_scientific_notation", {"value": "0.125", "significant_figures": 2}, {"mantissa": "1.2", "exponent": -1, "text": "1.2e-1"}, "half-even-tie"),
    ok("to_scientific_notation", {"value": "12345", "style": "engineering"}, {"mantissa": "12.345", "exponent": 3, "text": "12.345e3"}, "engineering"),
    ok("to_scientific_notation", {"value": "0.00012", "style": "engineering"}, {"mantissa": "120", "exponent": -6, "text": "120e-6"}, "engineering-small"),
    ok("to_scientific_notation", {"value": "999.95", "significant_figures": 4, "style": "engineering"}, {"mantissa": "1", "exponent": 3, "text": "1e3"}, "engineering-carry"),
]

NUMBER_FORMATTING_FAILURES = [
    bad("convert_number_base", {"value": "102", "from_base": 2, "to_base": 10}, "value", "digit-not-in-base"),
    bad("convert_number_base", {"value": TEN_TO_THE_4000, "from_base": 10, "to_base": 16}, "value", "magnitude-over-cap"),
    invalid("convert_number_base", {"value": "10", "from_base": 37, "to_base": 10}, "from_base", "base-over-36"),
    invalid("convert_number_base", {"value": "10", "from_base": 10, "to_base": 1}, "to_base", "base-under-2"),
    invalid("convert_number_base", {"value": "1.5", "from_base": 10, "to_base": 2}, "value", "point-not-allowed"),
    bad("number_to_english_words", {"value": "1" + "0" * 36}, "value", "ten-to-36"),
    bad("number_to_english_words", {"value": "-1", "ordinal": True}, "value", "negative-ordinal"),
    bad("english_words_to_number", {"words": "one thousand million"}, "words", "scale-not-decreasing"),
    bad("english_words_to_number", {"words": "first"}, "words", "ordinal-word-unknown", contains="first"),
    bad("english_words_to_number", {"words": "123"}, "words", "digit-string-unknown"),
    bad("english_words_to_number", {"words": "five four"}, "words", "unit-after-unit"),
    bad("english_words_to_number", {"words": "twenty thirty"}, "words", "tens-after-tens"),
    bad("english_words_to_number", {"words": "and"}, "words", "no-number-word"),
    bad("parse_abbreviated_number", {"text": "3 apples"}, "text", "unknown-suffix"),
    bad("parse_abbreviated_number", {"text": "1.2.3k"}, "text", "two-points"),
    invalid("parse_abbreviated_number", {"text": ""}, "text", "empty"),
    invalid("format_number_with_separators", {"value": "1,234"}, "value", "grouped-input-not-decimal-text"),
    invalid("format_number_with_separators", {"value": "1", "decimal_places": -1}, "decimal_places", "negative-places"),
    bad("parse_formatted_number", {"text": "1,23,456"}, "text", "uneven-groups"),
    bad("parse_formatted_number", {"text": "1,2345"}, "text", "four-digit-group"),
    bad("parse_formatted_number", {"text": "abc"}, "text", "no-digits"),
    invalid("to_scientific_notation", {"value": "1e5"}, "value", "exponent-input"),
    invalid("to_scientific_notation", {"value": "1", "significant_figures": 0}, "significant_figures", "zero-figures"),
]

SUCCESS_CASES = EXACT_ARITHMETIC_SUCCESS + NUMBER_THEORY_SUCCESS + NUMBER_FORMATTING_SUCCESS
FAILURE_CASES = EXACT_ARITHMETIC_FAILURES + NUMBER_THEORY_FAILURES + NUMBER_FORMATTING_FAILURES


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_numbers_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_numbers_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


@pytest.mark.parametrize("value", ["0", "7", "-42", "1205006", "9" * 36, "1" + "0" * 33, "1000001"])
def test_number_words_round_trip(tool_runner: ToolRunner, value: str) -> None:
    words = tool_runner.output("number_to_english_words", {"value": value})["words"]
    assert tool_runner.output("english_words_to_number", {"words": words}) == {"value": value}


@pytest.mark.parametrize("fraction", ["1/7", "22/7", "-1/12", "5/11", "1/6", "-7/3"])
def test_fraction_decimal_round_trip(tool_runner: ToolRunner, fraction: str) -> None:
    decimal = tool_runner.output("fraction_to_decimal", {"fraction": fraction})["decimal"]
    assert tool_runner.output("repeating_decimal_to_fraction", {"value": decimal}) == {"fraction": fraction}


@pytest.mark.parametrize(("left", "right"), [("12", "18"), ("-35", "49"), ("1071", "462"), ("99999999977", "1000000007")])
def test_gcd_times_lcm_equals_product(tool_runner: ToolRunner, left: str, right: str) -> None:
    gcd = int(tool_runner.output("greatest_common_divisor", {"values": [left, right]})["gcd"])
    lcm = int(tool_runner.output("least_common_multiple", {"values": [left, right]})["lcm"])
    assert gcd * lcm == abs(int(left) * int(right))


@pytest.mark.parametrize(("value", "modulus"), [("3", "11"), ("123456789", "1000000007"), ("-17", "3120"), ("65537", "3120")])
def test_modular_inverse_times_value_is_one(tool_runner: ToolRunner, value: str, modulus: str) -> None:
    output = tool_runner.output("modular_inverse", {"value": value, "modulus": modulus})
    inverse = int(output["inverse"])
    assert output["exists"] is True
    assert 0 <= inverse < int(modulus)
    assert (inverse * int(value)) % int(modulus) == 1
