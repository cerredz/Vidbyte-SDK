"""FILE: vidbyte/tools/builtins/prebuilt/number_theory.py

PURPOSE: Defines NumberTheoryToolFunctions, the ten prebuilt tools for primes and divisibility: a deterministic primality test, prime factorization, the primes in a range, the n-th prime, the nearest prime above or below a value, the greatest common divisor, the least common multiple, the divisors of a value, modular powers, and modular inverses.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the NUMBER_THEORY category is chosen. Builds on PrebuiltToolSupport in _support.py for exact integer text, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Three private helpers hold the shared arithmetic: a deterministic Miller-Rabin test over the 13 prime bases 2 through 41, trial-division factorization over a 6k plus or minus 1 wheel, and a bytearray sieve of Eratosthenes that counts primes in C.
FUNCTION INVENTORY: is_prime, prime_factorize, list_primes_in_range, nth_prime, next_prime, greatest_common_divisor, least_common_multiple, list_divisors, modular_exponentiation, and modular_inverse are the tools; _passes_miller_rabin tests primality, _factor_pairs factors a value into primes and exponents, and _prime_sieve marks the primes up to a bound; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new number theory tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.2, and its entry in tool_functions. A change to the primality bound changes PREBUILT_MAX_PRIMALITY_VALUE and the witness bases together, because the bases are exact only below the first strong pseudoprime to all of them.
WHAT NOT TO DO IN THIS FILE: 1. Do not use a random or probabilistic primality test; the 13 fixed bases make every answer exact up to PREBUILT_MAX_PRIMALITY_VALUE. 2. Do not compute a modular power with ** and %; three-argument pow never builds the full power. 3. Do not write an integer result as text without PrebuiltToolSupport.integer_text, which enforces the 4,000-digit cap. 4. Do not iterate a set when building an output; divisors and primes are listed in ascending order.
KNOWN EDGE CASES: Integer text may carry leading zeros and a sign, so a negative value is simply not prime. Any zero makes the least common multiple zero before the running digit check, so a zero beside huge values still gives zero. A modulus of one makes every modular power zero, and a negative exponent needs the base's modular inverse.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.2, section 9.2 items 2, 5, 12, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_numbers.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import itertools
import math
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_FACTORIZE_VALUE,
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_INTEGER_TEXT_CHARS,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_MODULAR_TEXT_CHARS,
    PREBUILT_MAX_NTH_PRIME,
    PREBUILT_MAX_PRIMALITY_VALUE,
    PREBUILT_MAX_SIEVE_VALUE,
)
from vidbyte.lib.enums.prebuilt_tools import SearchDirection
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_INTEGER_TEXT_PATTERN = r"^[+-]?[0-9]+$"
_INTEGER_RESULT_BOUND = 10**PREBUILT_MAX_INTEGER_DIGITS
_MILLER_RABIN_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41)
_SMALLEST_PRIME = 2
_FIRST_WHEEL_PRIMES = (2, 3)
_WHEEL_START = 6
_WHEEL_STEP = 6
_ROSSER_MIN_POSITION = 6
_SMALL_POSITION_SIEVE_BOUND = 12

_INTEGER_LIST_DESCRIPTION = "The integers to combine, each written as decimal digits with an optional sign. Signs are ignored, because the absolute values are used. Leading zeros are allowed and do not change a value. The list must hold between two and ten thousand values, each of at most 4,001 characters."
_FACTORIZE_VALUE_DESCRIPTION = "The positive integer to examine, given as a JSON integer. It must be at least one and at most one trillion. Larger values fail validation, because trial division would take too long on them. Zero and negative values also fail validation."


class NumberTheoryToolFunctions:
    """The number_theory category: primes, divisibility, and modular arithmetic on exact integers."""

    @staticmethod
    def is_prime(
        value: Annotated[str, Field(description="The integer to test, written as decimal digits with an optional sign. Leading zeros are allowed and do not change the value. Values of one or less are reported as not prime. A value above 3,317,044,064,679,887,385,961,980 fails with an error.", pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Tell whether an integer is prime, using a deterministic Miller-Rabin test with the thirteen prime bases from 2 through 41. Use it whenever primality matters, because checking divisibility by reading is unreliable for large numbers. The answer is exact for every value up to 3,317,044,064,679,887,385,961,980, and zero, one, and negative values are never prime. A value above that bound fails with an error naming value."""
        number = PrebuiltToolSupport.parse_integer_text(value, "value")
        if number > PREBUILT_MAX_PRIMALITY_VALUE:
            raise PrebuiltToolSupport.argument_error("value", "the value is above the largest value the exact primality test covers", f"an integer of at most {PREBUILT_MAX_PRIMALITY_VALUE}")
        return {"is_prime": NumberTheoryToolFunctions._passes_miller_rabin(number)}

    @staticmethod
    def prime_factorize(value: Annotated[int, Field(description=_FACTORIZE_VALUE_DESCRIPTION, ge=1, le=PREBUILT_MAX_FACTORIZE_VALUE)]) -> PrebuiltToolOutput:
        """Break a positive integer into its prime factors with their exponents, in ascending order, plus a readable product expression. Use it for factorization, for simplifying fractions by hand, or for finding the building blocks of a number. The expression joins the factors with an asterisk and writes an exponent only when it is above one, and the value one has no factors. The value must be between one and one trillion, and anything outside that range fails validation."""
        pairs = NumberTheoryToolFunctions._factor_pairs(value)
        expression = " * ".join(f"{prime}^{exponent}" if exponent > 1 else str(prime) for prime, exponent in pairs)
        return {"factors": [{"prime": prime, "exponent": exponent} for prime, exponent in pairs], "expression": expression or "1"}

    @staticmethod
    def list_primes_in_range(
        start: Annotated[int, Field(description="The smallest integer of the range, which is included when it is prime. It must be between zero and ten million. It must not be greater than end. Values below two hold no primes.", ge=0, le=PREBUILT_MAX_SIEVE_VALUE)],
        end: Annotated[int, Field(description="The largest integer of the range, which is included when it is prime. It must be between zero and ten million. It must not be less than start. Every number up to end is sieved, so a larger end takes longer.", ge=0, le=PREBUILT_MAX_SIEVE_VALUE)],
    ) -> PrebuiltToolOutput:
        """List every prime number in an inclusive range of non-negative integers, in ascending order, with the total count. Use it to enumerate primes for puzzles, tests, or number tables instead of recalling them. Both ends are included and must lie between zero and ten million, and at most 1,000 primes are listed while the count covers the whole range. A start above the end fails with an error naming start."""
        if start > end:
            raise PrebuiltToolSupport.argument_error("start", "the start of the range is above its end", "a start that is at most end")

        # Sieve up to the end once, count the marks in the range, and
        # list the first primes in it up to the item cap.
        sieve = NumberTheoryToolFunctions._prime_sieve(end)
        count = sieve.count(1, start, end + 1)
        primes, truncated = PrebuiltToolSupport.cap_items(itertools.compress(range(start, end + 1), memoryview(sieve)[start : end + 1]))
        return {"primes": primes, "count": count, "truncated": truncated}

    @staticmethod
    def nth_prime(n: Annotated[int, Field(description="The 1-based position of the prime to return. Position one is the prime 2, and each later position is the next larger prime. It must be at least one. It must be at most one hundred thousand.", ge=1, le=PREBUILT_MAX_NTH_PRIME)]) -> PrebuiltToolOutput:
        """Return the n-th prime number, counting 2 as the first prime. Use it to answer questions about a prime's position in the sequence of primes without counting by hand. The answer comes from a sieve of Eratosthenes sized by Rosser's bound to cover the requested position. The position must be between one and one hundred thousand, and anything else fails validation."""
        # Rosser's theorem bounds the n-th prime from the sixth on; the
        # first five all lie below a small fixed bound.
        bound = _SMALL_POSITION_SIEVE_BOUND
        if n >= _ROSSER_MIN_POSITION:
            bound = math.ceil(n * (math.log(n) + math.log(math.log(n))))

        # Walk the sieve's marks and take the n-th one.
        sieve = NumberTheoryToolFunctions._prime_sieve(bound)
        prime = next(itertools.islice(itertools.compress(itertools.count(), sieve), n - 1, None))
        return {"prime": prime}

    @staticmethod
    def next_prime(
        value: Annotated[str, Field(description="The integer to start from, written as decimal digits with an optional sign. The value itself is never returned, even when it is prime. Leading zeros are allowed and do not change the value. It must not be above 3,317,044,064,679,887,385,961,980.", pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
        direction: Annotated[SearchDirection, Field(description="Which way to search from value. Next looks for the smallest prime above value, and previous looks for the largest prime below it. The default is next. A previous search from 2 or less finds nothing and gives null.")] = SearchDirection.NEXT,
    ) -> PrebuiltToolOutput:
        """Find the nearest prime strictly above or strictly below an integer. Use it to round a value to a prime, size a hash table, or step through the primes one at a time. The search uses the same exact Miller-Rabin test as is_prime, and searching downward from 2 or less gives null. A value above 3,317,044,064,679,887,385,961,980, or an upward search that would pass that bound, fails with an error naming value."""
        # Refuse a start outside the range the exact test covers.
        number = PrebuiltToolSupport.parse_integer_text(value, "value")
        expected = f"an integer whose search stays at or below {PREBUILT_MAX_PRIMALITY_VALUE}"
        if number > PREBUILT_MAX_PRIMALITY_VALUE:
            raise PrebuiltToolSupport.argument_error("value", "the value is above the largest value the exact primality test covers", expected)

        # Nothing lies below 2, so a downward search from 2 is empty.
        if direction is SearchDirection.PREVIOUS and number <= _SMALLEST_PRIME:
            return {"prime": None}

        # Step one integer at a time until a prime turns up; a downward
        # search always stops at 2, and an upward one may pass the
        # bound.
        step = 1 if direction is SearchDirection.NEXT else -1
        candidate = max(number + 1, _SMALLEST_PRIME) if direction is SearchDirection.NEXT else number - 1
        while candidate <= PREBUILT_MAX_PRIMALITY_VALUE and not NumberTheoryToolFunctions._passes_miller_rabin(candidate):
            candidate += step
        if candidate > PREBUILT_MAX_PRIMALITY_VALUE:
            raise PrebuiltToolSupport.argument_error("value", "the next prime lies above the largest value the exact primality test covers", expected)
        return {"prime": PrebuiltToolSupport.integer_text(candidate, "value")}

    @staticmethod
    def greatest_common_divisor(
        values: Annotated[list[Annotated[str, Field(pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)]], Field(description=_INTEGER_LIST_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Compute the greatest common divisor of two or more integers. Use it to simplify ratios, find a shared step size, or check whether numbers are coprime. Signs are ignored, the result is never negative, and a list of only zeros gives zero. A result of more than 4,000 digits fails with an error naming values."""
        numbers = [PrebuiltToolSupport.parse_integer_text(text, "values") for text in values]
        return {"gcd": PrebuiltToolSupport.integer_text(math.gcd(*numbers), "values")}

    @staticmethod
    def least_common_multiple(
        values: Annotated[list[Annotated[str, Field(pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)]], Field(description=_INTEGER_LIST_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Compute the least common multiple of two or more integers. Use it to find a common denominator, a shared period, or the first time several cycles line up. Signs are ignored, the result is never negative, and any zero in the list gives zero. A running result of more than 4,000 digits fails with an error naming values, checked after each value is folded in."""
        # Any zero makes the whole result zero, so it wins before the
        # running result can grow.
        numbers = [PrebuiltToolSupport.parse_integer_text(text, "values") for text in values]
        if 0 in numbers:
            return {"lcm": "0"}

        # Fold the values in one at a time and stop as soon as the
        # running result passes the digit cap.
        running = 1
        for position, number in enumerate(numbers):
            running = math.lcm(running, number)
            # @intent prebuilt-integer-digit-cap
            # A running multiple of huge coprime values grows with every
            # step, so it is refused as soon as it passes 4,000 digits
            # instead of after the whole list has been multiplied in.
            if running >= _INTEGER_RESULT_BOUND:
                problem = f"the running result passes {PREBUILT_MAX_INTEGER_DIGITS} digits at the value at index {position}"
                raise PrebuiltToolSupport.argument_error("values", problem, f"values whose least common multiple has at most {PREBUILT_MAX_INTEGER_DIGITS} digits")
        return {"lcm": PrebuiltToolSupport.integer_text(running, "values")}

    @staticmethod
    def list_divisors(value: Annotated[int, Field(description=_FACTORIZE_VALUE_DESCRIPTION, ge=1, le=PREBUILT_MAX_FACTORIZE_VALUE)]) -> PrebuiltToolOutput:
        """List every positive divisor of a positive integer in ascending order, with how many there are and their sum. Use it for divisor questions, perfect and abundant number checks, or finding every way to split a quantity evenly. The divisors are built from the prime factorization, and at most 1,000 are listed while the count and the sum cover every divisor. The value must be between one and one trillion, and anything else fails validation."""
        # Build every divisor as a product of prime powers; no value in
        # range has more than a few thousand divisors.
        divisors = [1]
        for prime, exponent in NumberTheoryToolFunctions._factor_pairs(value):
            divisors = [divisor * prime**power for divisor in divisors for power in range(exponent + 1)]
        divisors.sort()

        # List the smallest ones up to the item cap; the count and the
        # sum cover them all.
        listed, truncated = PrebuiltToolSupport.cap_items(iter(divisors))
        return {"divisors": listed, "count": len(divisors), "sum": sum(divisors), "truncated": truncated}

    @staticmethod
    def modular_exponentiation(
        base: Annotated[str, Field(description="The integer to raise to a power, written as decimal digits with an optional sign. A negative base is reduced into the range of the modulus first. Leading zeros are allowed and do not change the value. It may have at most 2,001 characters.", pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_MODULAR_TEXT_CHARS)],
        exponent: Annotated[str, Field(description="The power to raise base to, written as decimal digits with an optional sign. A negative exponent raises the modular inverse of base instead, which needs base and modulus to share no factor. Leading zeros are allowed and do not change the value. It may have at most 2,001 characters.", pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_MODULAR_TEXT_CHARS)],
        modulus: Annotated[str, Field(description="The modulus to reduce by, written as decimal digits with an optional sign. It must be at least one, and a modulus of one always gives zero. Leading zeros are allowed and do not change the value. It may have at most 2,001 characters.", pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_MODULAR_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Compute base raised to exponent and reduced modulo modulus, without ever building the full power. Use it for modular arithmetic, cryptography exercises, and checking large congruences. The result lies between zero and one less than the modulus, and a negative exponent uses the modular inverse of base. A modulus below one fails with an error naming modulus, and a negative exponent with a base that has no inverse fails with an error naming base."""
        # Read the three operands and refuse a modulus below one.
        number = PrebuiltToolSupport.parse_integer_text(base, "base")
        power = PrebuiltToolSupport.parse_integer_text(exponent, "exponent")
        divisor = PrebuiltToolSupport.parse_integer_text(modulus, "modulus")
        if divisor < 1:
            raise PrebuiltToolSupport.argument_error("modulus", "the modulus is below one", "a modulus of at least one")

        # Three-argument pow squares and reduces at every step, and for
        # a negative exponent it inverts the base first.
        try:
            result = pow(number, power, divisor)
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("base", "the base has no inverse modulo the modulus, which a negative exponent needs", "a base that shares no factor with the modulus when the exponent is negative") from exc
        return {"result": PrebuiltToolSupport.integer_text(result, "modulus")}

    @staticmethod
    def modular_inverse(
        value: Annotated[str, Field(description="The integer to invert, written as decimal digits with an optional sign. A negative value is reduced into the range of the modulus first. Leading zeros are allowed and do not change the value. It may have at most 4,001 characters.", pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
        modulus: Annotated[str, Field(description="The modulus to work in, written as decimal digits with an optional sign. It must be at least two, and smaller values fail with an error. Leading zeros are allowed and do not change the value. It may have at most 4,001 characters.", pattern=_INTEGER_TEXT_PATTERN, max_length=PREBUILT_MAX_INTEGER_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Find the inverse of an integer modulo a modulus, the number that times the integer leaves a remainder of one. Use it to divide in modular arithmetic, solve linear congruences, or work through key-generation exercises. The inverse lies between zero and one less than the modulus, and when the integer shares a factor with the modulus no inverse exists, so inverse is null and exists is false. A modulus below two fails with an error naming modulus."""
        # Read both integers and refuse a modulus below two.
        number = PrebuiltToolSupport.parse_integer_text(value, "value")
        divisor = PrebuiltToolSupport.parse_integer_text(modulus, "modulus")
        if divisor < _SMALLEST_PRIME:
            raise PrebuiltToolSupport.argument_error("modulus", "the modulus is below two", "a modulus of at least two")

        # An inverse exists exactly when the two share no factor.
        if math.gcd(number, divisor) != 1:
            return {"inverse": None, "exists": False}
        return {"inverse": PrebuiltToolSupport.integer_text(pow(number, -1, divisor), "modulus"), "exists": True}

    @staticmethod
    def _passes_miller_rabin(number: int) -> bool:
        """Test primality exactly for values up to PREBUILT_MAX_PRIMALITY_VALUE with the 13 prime bases 2 through 41."""
        if number < _SMALLEST_PRIME:
            return False
        for base in _MILLER_RABIN_BASES:
            if number % base == 0:
                return number == base
        # Write number - 1 as odd * 2^shifts, then look for a witness
        # among the fixed bases.
        shifts = ((number - 1) & (1 - number)).bit_length() - 1
        odd = (number - 1) >> shifts
        for base in _MILLER_RABIN_BASES:
            witness = pow(base, odd, number)
            if witness in (1, number - 1):
                continue
            for _ in range(shifts - 1):
                witness = witness * witness % number
                if witness == number - 1:
                    break
            else:
                return False
        return True

    @staticmethod
    def _factor_pairs(value: int) -> list[tuple[int, int]]:
        """Factor a positive integer by trial division over 2, 3, and the numbers 6k - 1 and 6k + 1, as ascending (prime, exponent) pairs."""
        pairs: list[tuple[int, int]] = []
        remaining = value
        wheel = itertools.chain.from_iterable((center - 1, center + 1) for center in itertools.count(_WHEEL_START, _WHEEL_STEP))
        for divisor in itertools.chain(_FIRST_WHEEL_PRIMES, wheel):
            if divisor * divisor > remaining:
                break
            exponent = 0
            while remaining % divisor == 0:
                remaining //= divisor
                exponent += 1
            if exponent:
                pairs.append((divisor, exponent))
        # Whatever is left above one has no divisor up to its square
        # root, so it is itself prime.
        if remaining > 1:
            pairs.append((remaining, 1))
        return pairs

    @staticmethod
    def _prime_sieve(bound: int) -> bytearray:
        """Mark the primes up to bound with a sieve of Eratosthenes: index i holds 1 when i is prime and 0 otherwise."""
        sieve = bytearray(_SMALLEST_PRIME) + bytearray(b"\x01") * max(bound - 1, 0)
        for number in range(_SMALLEST_PRIME, math.isqrt(bound) + 1):
            if sieve[number]:
                sieve[number * number :: number] = bytes(len(range(number * number, bound + 1, number)))
        return sieve

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.is_prime,
            cls.prime_factorize,
            cls.list_primes_in_range,
            cls.nth_prime,
            cls.next_prime,
            cls.greatest_common_divisor,
            cls.least_common_multiple,
            cls.list_divisors,
            cls.modular_exponentiation,
            cls.modular_inverse,
        )


__all__ = ["NumberTheoryToolFunctions"]
