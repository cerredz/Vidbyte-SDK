"""FILE: vidbyte/tools/builtins/prebuilt/probability.py

PURPOSE: Defines ProbabilityToolFunctions, the nine prebuilt tools for counting and chance: exact combination, permutation, and factorial counts, binomial and Poisson probabilities over a chosen tail, normal interval probabilities and quantiles, the birthday collision probability, and an enumeration of the combinations of a small list.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the PROBABILITY category is chosen. Builds on PrebuiltToolSupport in _support.py for exact integer text under the 4,000-digit cap, the finite float guard, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Exact counts come from math.comb, math.perm, math.factorial, and integer powers after a logarithmic size estimate, so a count far past the digit cap is refused before it is built. Discrete probabilities add terms computed in log space with math.lgamma through math.fsum, the normal tools use statistics.NormalDist, and every probability is clamped to the range zero to one.
FUNCTION INVENTORY: count_combinations, count_permutations, exact_factorial, binomial_probability, poisson_probability, normal_distribution_probability, normal_quantile, birthday_collision_probability, and list_combinations are the tools; _tail_bounds turns a ProbabilityTail into an inclusive range of counts, _binomial_mass and _poisson_mass add up the probabilities over such a range, _standard_score standardizes a normal bound without overflow, and _unit_interval clamps a probability; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new probability tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.5, and its entry in tool_functions. A new tail adds a ProbabilityTail member and one case in _tail_bounds, and both discrete distributions pick it up from there.
WHAT NOT TO DO IN THIS FILE: 1. Do not multiply raw binomial coefficients and powers in floating point; they overflow long before the parameter caps, so terms stay in log space. 2. Do not take the logarithm of a probability of zero or one; those cases are point masses handled exactly. 3. Do not count combinations by enumerating them; the count comes from math.comb so twenty items taken twenty at a time finish instantly. 4. Do not build a factorial or a power before its logarithmic size estimate has passed.
KNOWN EDGE CASES: An upper Poisson tail whose start lies above the rate is added term by term until the terms stop changing the sum, and one whose start lies at or below the rate is one minus the lower tail. With repetition and no items, only the empty selection exists, so the count is one for size zero and zero otherwise. The factorial of 1,463 has 3,998 digits and is the largest one returned.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.5, section 9.2 items 2, 5, 12, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_statistics.py, tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py, and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterator
from fractions import Fraction
from statistics import NormalDist
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_BIRTHDAY_ITEMS,
    PREBUILT_MAX_BIRTHDAY_VALUES,
    PREBUILT_MAX_COMBINATION_ITEMS,
    PREBUILT_MAX_COMBINATORIC_N,
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_POISSON_OCCURRENCES,
    PREBUILT_MAX_POISSON_RATE,
)
from vidbyte.lib.enums.prebuilt_tools import ProbabilityTail
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_LN_TEN = math.log(10)
_DIGIT_ESTIMATE_MARGIN = 1
_TAIL_RELATIVE_TOLERANCE = 2.0**-60
_LOWEST_COUNT = 0

_ITEM_COUNT_DESCRIPTION = "How many distinct items there are to choose from. It must be between zero and ten thousand. Every item is treated as distinguishable from every other. A count of more than 4,000 digits fails with an error naming this parameter."
_TAIL_DESCRIPTION = "Which outcomes the probability covers relative to the given count. Exactly covers only that count, at_most covers it and every smaller count, and at_least covers it and every larger count. Less_than covers only the smaller counts, and greater_than covers only the larger counts. The default is exactly."
_MEAN_DESCRIPTION = "The mean of the normal distribution, the center of its bell curve. It may be any finite number. The default is zero. Together with the default standard deviation it gives the standard normal distribution."
_STANDARD_DEVIATION_DESCRIPTION = "The standard deviation of the normal distribution, which sets the width of its bell curve. It must be greater than zero. It must be a finite number. The default is one."
_DIGIT_CAP_EXPECTED = f"n and k whose count has at most {PREBUILT_MAX_INTEGER_DIGITS} digits"


class ProbabilityToolFunctions:
    """The probability category: exact counting, discrete and normal probabilities, and combinations."""

    @staticmethod
    def count_combinations(
        n: Annotated[int, Field(description=_ITEM_COUNT_DESCRIPTION, ge=0, le=PREBUILT_MAX_COMBINATORIC_N)],
        k: Annotated[int, Field(description="How many items each selection takes. It must be between zero and ten thousand. Without repetition, a value above n gives a count of zero. With repetition, an item may be taken more than once.", ge=0, le=PREBUILT_MAX_COMBINATORIC_N)],
        with_repetition: Annotated[bool, Field(description="Whether an item may be chosen more than once in the same selection. When false, the count is the number of subsets of size k. When true, it is the number of multisets of size k. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Count the ways to choose k items from n distinct items when order does not matter, exactly, with or without repetition. Use it for lottery odds, committee selections, or any how-many-ways question whose answer is too large to work out by hand. Without repetition the count is the binomial coefficient and is zero when k exceeds n, and with repetition it counts the multisets of size k. A count of more than 4,000 digits fails with an error naming n."""
        if not with_repetition:
            count = math.comb(n, k)
        elif n == 0:
            # With no items to repeat, only the empty selection exists.
            count = 1 if k == 0 else 0
        else:
            count = math.comb(n + k - 1, k)
        return {"count": PrebuiltToolSupport.integer_text(count, "n")}

    @staticmethod
    def count_permutations(
        n: Annotated[int, Field(description=_ITEM_COUNT_DESCRIPTION, ge=0, le=PREBUILT_MAX_COMBINATORIC_N)],
        k: Annotated[int | None, Field(description="How many items each arrangement takes, with null meaning all n of them. It must be between zero and ten thousand. Without repetition, a value above n gives a count of zero. With repetition, each position may reuse any item.", ge=0, le=PREBUILT_MAX_COMBINATORIC_N)] = None,
        with_repetition: Annotated[bool, Field(description="Whether an item may appear in more than one position of the same arrangement. When false, the count is the number of ordered selections without reuse. When true, it is n raised to the power k. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Count the ordered arrangements of k items chosen from n distinct items, exactly, with or without repetition. Use it for seating orders, ranked podiums, codes, or any question where order matters. Without repetition the count is n factorial divided by the factorial of n minus k and is zero when k exceeds n, and with repetition it is n to the power k. The size of the count is estimated with logarithms first, and a count of more than 4,000 digits fails with an error naming n."""
        # A null k arranges every item, and taking more items than
        # exist without reuse is impossible.
        chosen = n if k is None else k
        if not with_repetition and chosen > n:
            return {"count": "0"}

        # Estimate the count's decimal size from logarithms so a huge
        # count is refused before it is built.
        if with_repetition:
            magnitude = chosen * math.log10(n) if n > 1 else 0.0
        else:
            magnitude = (math.lgamma(n + 1) - math.lgamma(n - chosen + 1)) / _LN_TEN
        # @intent prebuilt-integer-digit-cap
        # A count whose logarithm is clearly past the cap is refused
        # without being built; one near the cap is built exactly and
        # integer_text makes the exact decision.
        if magnitude >= PREBUILT_MAX_INTEGER_DIGITS + _DIGIT_ESTIMATE_MARGIN:
            raise PrebuiltToolSupport.argument_error("n", f"the count would have more than {PREBUILT_MAX_INTEGER_DIGITS} digits", _DIGIT_CAP_EXPECTED)

        # Build the exact count.
        count = n**chosen if with_repetition else math.perm(n, chosen)
        return {"count": PrebuiltToolSupport.integer_text(count, "n")}

    @staticmethod
    def exact_factorial(n: Annotated[int, Field(description="The non-negative integer whose factorial is computed. Zero factorial is one. Values up to 1,463 give a result, and larger ones fail with an error. The schema accepts at most ten thousand.", ge=0, le=PREBUILT_MAX_COMBINATORIC_N)]) -> PrebuiltToolOutput:
        """Compute n factorial exactly and report how many decimal digits it has. Use it whenever a factorial is needed in full, because large factorials are far beyond what can be multiplied out by hand. The size is checked with the log-gamma function before the product is built, so the largest accepted n is 1,463, whose factorial has 3,998 digits. A larger n fails with an error naming n, because its factorial would pass 4,000 digits."""
        # @intent prebuilt-integer-digit-cap
        # The base-ten logarithm of n factorial gives its digit count,
        # so a factorial of more than 4,000 digits is refused before
        # the product is built.
        if math.lgamma(n + 1) / _LN_TEN >= PREBUILT_MAX_INTEGER_DIGITS:
            raise PrebuiltToolSupport.argument_error("n", f"the factorial would have more than {PREBUILT_MAX_INTEGER_DIGITS} digits", "an n whose factorial has at most that many digits")
        factorial = PrebuiltToolSupport.integer_text(math.factorial(n), "n")
        return {"factorial": factorial, "digit_count": len(factorial)}

    @staticmethod
    def binomial_probability(
        trials: Annotated[int, Field(description="How many independent trials are run. It must be between zero and ten thousand. Each trial either succeeds or fails. With zero trials, zero successes is certain.", ge=0, le=PREBUILT_MAX_COMBINATORIC_N)],
        successes: Annotated[int, Field(description="The number of successes that the tail is measured against. It must be between zero and ten thousand. It must not be greater than trials. The tail decides whether the probability covers exactly this count or a range around it.", ge=0, le=PREBUILT_MAX_COMBINATORIC_N)],
        probability: Annotated[float, Field(description="The chance that a single trial succeeds, as a number from zero to one. A chance of exactly zero or exactly one is handled without logarithms, so the result is exact. Values outside that range fail validation. It must be a finite number.", ge=0, le=1, allow_inf_nan=False)],
        tail: Annotated[ProbabilityTail, Field(description=_TAIL_DESCRIPTION)] = ProbabilityTail.EXACTLY,
    ) -> PrebuiltToolOutput:
        """Compute the probability of a number of successes in a fixed number of independent trials that each succeed with the same chance. Use it for coin flips, defect rates, survey hits, and any yes-or-no experiment repeated a known number of times. The tail chooses exactly that many, at most, at least, fewer, or more successes, the terms are computed in log space so large trial counts stay accurate, and the result is clamped to the range zero to one. A success count above the number of trials fails with an error naming successes."""
        if successes > trials:
            raise PrebuiltToolSupport.argument_error("successes", "there are more successes than trials", "a success count of at most trials")
        first, last = ProbabilityToolFunctions._tail_bounds(tail, successes)
        mass = ProbabilityToolFunctions._binomial_mass(trials, probability, first, trials if last is None else last)
        return {"probability": ProbabilityToolFunctions._unit_interval(mass)}

    @staticmethod
    def poisson_probability(
        rate: Annotated[float, Field(description="The average number of events in the interval, which is the Poisson mean. It must be above zero. It must be at most one million. It may be fractional.", gt=0, le=PREBUILT_MAX_POISSON_RATE, allow_inf_nan=False)],
        occurrences: Annotated[int, Field(description="The count of events that the tail is measured against. It must be between zero and one hundred thousand. Upper tails add terms beyond this count until they no longer change the sum. The tail decides whether the probability covers exactly this count or a range around it.", ge=0, le=PREBUILT_MAX_POISSON_OCCURRENCES)],
        tail: Annotated[ProbabilityTail, Field(description=_TAIL_DESCRIPTION)] = ProbabilityTail.EXACTLY,
    ) -> PrebuiltToolOutput:
        """Compute a Poisson probability for a count of events when events arrive independently at a known average rate. Use it for arrivals per hour, defects per batch, calls per minute, or other counts of rare independent events. The tail chooses exactly that many, at most, at least, fewer, or more events, the terms are computed in log space, and the result is clamped to the range zero to one. The rate must be above zero and at most one million and the count at most one hundred thousand, and other values fail validation."""
        first, last = ProbabilityToolFunctions._tail_bounds(tail, occurrences)
        mass = ProbabilityToolFunctions._poisson_mass(rate, first, last)
        return {"probability": ProbabilityToolFunctions._unit_interval(mass)}

    @staticmethod
    def normal_distribution_probability(
        lower: Annotated[float | None, Field(description="The lower bound of the interval, or null for no lower bound. It must be a finite number when given. It must not be greater than upper. At least one of lower and upper must be given.", allow_inf_nan=False)] = None,
        upper: Annotated[float | None, Field(description="The upper bound of the interval, or null for no upper bound. It must be a finite number when given. It must not be less than lower. At least one of lower and upper must be given.", allow_inf_nan=False)] = None,
        mean: Annotated[float, Field(description=_MEAN_DESCRIPTION, allow_inf_nan=False)] = 0.0,
        standard_deviation: Annotated[float, Field(description=_STANDARD_DEVIATION_DESCRIPTION, gt=0, allow_inf_nan=False)] = 1.0,
    ) -> PrebuiltToolOutput:
        """Compute the probability that a normally distributed variable falls strictly between a lower and an upper bound. Use it for questions about test scores, measurement errors, heights, or any quantity modeled by a bell curve. A null bound leaves that side open, the calculation uses the normal cumulative distribution function, and equal bounds give zero. Both bounds null fails with an error naming lower, and a lower bound above the upper bound fails with an error naming upper."""
        # Refuse an interval with no bound or with its ends reversed.
        if lower is None and upper is None:
            raise PrebuiltToolSupport.argument_error("lower", "both bounds are null", "a lower bound, an upper bound, or both")
        if lower is not None and upper is not None and lower > upper:
            raise PrebuiltToolSupport.argument_error("upper", "the upper bound is below the lower bound", "an upper bound at least as large as lower")

        # Turn each bound into a standard score, with an open side at
        # infinity, so no step can overflow on huge finite inputs.
        upper_score = math.inf if upper is None else ProbabilityToolFunctions._standard_score(upper, mean, standard_deviation)
        lower_score = -math.inf if lower is None else ProbabilityToolFunctions._standard_score(lower, mean, standard_deviation)

        # The probability is the cumulative share below the upper bound
        # minus the share below the lower bound.
        standard = NormalDist()
        share = standard.cdf(upper_score) - standard.cdf(lower_score)
        return {"probability": ProbabilityToolFunctions._unit_interval(share)}

    @staticmethod
    def normal_quantile(
        probability: Annotated[float, Field(description="The share of the distribution that lies below the returned value. It must be strictly greater than zero. It must be strictly less than one. A share of one half gives the mean.", gt=0, lt=1, allow_inf_nan=False)],
        mean: Annotated[float, Field(description=_MEAN_DESCRIPTION, allow_inf_nan=False)] = 0.0,
        standard_deviation: Annotated[float, Field(description=_STANDARD_DEVIATION_DESCRIPTION, gt=0, allow_inf_nan=False)] = 1.0,
    ) -> PrebuiltToolOutput:
        """Find the value below which a given share of a normal distribution lies, which is the inverse of its cumulative distribution function. Use it for critical values, percentile cutoffs, and confidence bounds of a bell curve. The share must lie strictly between zero and one, and the result is the mean plus the standard normal quantile times the standard deviation. A share of exactly zero or one fails validation, and a result outside the floating-point range fails with an error naming standard_deviation."""
        quantile = NormalDist(mean, standard_deviation).inv_cdf(probability)
        return {"x": PrebuiltToolSupport.float_result(quantile, "standard_deviation")}

    @staticmethod
    def birthday_collision_probability(
        items: Annotated[int, Field(description="How many items are drawn. It must be between zero and one hundred thousand. Zero or one item can never collide. More items than possible values must collide.", ge=0, le=PREBUILT_MAX_BIRTHDAY_ITEMS)],
        possible_values: Annotated[int, Field(description="How many equally likely values each item can take. It must be at least one. It must be at most one quintillion. Every value is assumed to be equally likely for every item.", ge=1, le=PREBUILT_MAX_BIRTHDAY_VALUES)],
    ) -> PrebuiltToolOutput:
        """Compute the chance that at least two of n random items share a value when each is drawn independently and uniformly from a number of equally likely values. Use it for the birthday problem, hash or identifier collisions, and duplicate draws from a pool. The formula adds logarithms with log1p and finishes with expm1, so tiny probabilities stay accurate. One item or none gives zero, more items than values gives one, and the tool fails only through its schema bounds."""
        # Too few items cannot collide, and more items than values must.
        if items <= 1:
            return {"probability": 0.0}
        if items > possible_values:
            return {"probability": 1.0}

        # The chance of no collision is the product of 1 - i/d, added
        # here as logarithms so a tiny collision chance keeps its
        # digits.
        no_collision = math.fsum(math.log1p(-index / possible_values) for index in range(1, items))
        return {"probability": ProbabilityToolFunctions._unit_interval(-math.expm1(no_collision))}

    @staticmethod
    def list_combinations(
        items: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_NAME_CHARS)]], Field(description="The items to combine, as strings in the order that sets the output order. It must hold at least one and at most twenty items. Each item may hold at most two hundred characters. Repeated items are treated as separate positions.", min_length=1, max_length=PREBUILT_MAX_COMBINATION_ITEMS)],
        size: Annotated[int, Field(description="How many items each combination holds. It must be between zero and twenty. Size zero gives one empty combination. Without repetition, a size above the number of items gives no combinations.", ge=0, le=PREBUILT_MAX_COMBINATION_ITEMS)],
        with_repetition: Annotated[bool, Field(description="Whether an item may appear more than once in the same combination. When false, each combination uses distinct positions. When true, a position may repeat any number of times. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """List every combination of a chosen size from a small list of items, in the standard lexicographic order of positions, with the total count. Use it to enumerate team pairings, menu choices, or test-case combinations instead of writing them out by hand. Duplicate items count as distinct positions, and at most 1,000 combinations are listed while the count covers all of them and is computed arithmetically. The list may hold at most twenty items of at most two hundred characters each, and larger input fails validation."""
        # Count every combination arithmetically, never by walking them.
        if with_repetition:
            count = math.comb(len(items) + size - 1, size)
            chosen: Iterator[tuple[str, ...]] = itertools.combinations_with_replacement(items, size)
        else:
            count = math.comb(len(items), size)
            chosen = itertools.combinations(items, size)

        # List the first combinations in itertools order up to the cap.
        listed, truncated = PrebuiltToolSupport.cap_items(list(combination) for combination in chosen)
        return {"combinations": listed, "count": count, "truncated": truncated}

    @staticmethod
    def _tail_bounds(tail: ProbabilityTail, count: int) -> tuple[int, int | None]:
        """Turn a tail around count into an inclusive range of counts, with None as an open upper end."""
        match tail:
            case ProbabilityTail.EXACTLY:
                return count, count
            case ProbabilityTail.AT_MOST:
                return _LOWEST_COUNT, count
            case ProbabilityTail.AT_LEAST:
                return count, None
            case ProbabilityTail.LESS_THAN:
                return _LOWEST_COUNT, count - 1
            case _:
                # The only tail left is greater_than.
                return count + 1, None

    @staticmethod
    def _binomial_mass(trials: int, chance: float, first: int, last: int) -> float:
        """Add the binomial probabilities of first through last successes, in log space unless the chance is zero or one."""
        outcomes = range(first, last + 1)
        # A chance of zero or one puts all the mass on one count, and
        # the logarithm of zero must never be taken.
        if chance in (0.0, 1.0):
            certain = trials if chance == 1.0 else _LOWEST_COUNT
            return 1.0 if certain in outcomes else 0.0
        log_chance = math.log(chance)
        log_miss = math.log1p(-chance)
        log_arrangements = math.lgamma(trials + 1)
        return math.fsum(
            math.exp(log_arrangements - math.lgamma(count + 1) - math.lgamma(trials - count + 1) + count * log_chance + (trials - count) * log_miss) for count in outcomes
        )

    @staticmethod
    def _poisson_mass(rate: float, first: int, last: int | None) -> float:
        """Add the Poisson probabilities of first through last events, where None leaves the range open above."""
        log_rate = math.log(rate)
        if last is not None:
            return math.fsum(math.exp(count * log_rate - rate - math.lgamma(count + 1)) for count in range(first, last + 1))
        # An open range starting at or below the rate holds most of the
        # mass, so it is one minus the short closed range below it.
        if first <= rate:
            return 1.0 - math.fsum(math.exp(count * log_rate - rate - math.lgamma(count + 1)) for count in range(first))
        # Above the rate every term is smaller than the one before, so
        # adding stops once a term no longer changes the sum.
        terms: list[float] = []
        running = 0.0
        count = first
        while True:
            term = math.exp(count * log_rate - rate - math.lgamma(count + 1))
            terms.append(term)
            running += term
            if term <= running * _TAIL_RELATIVE_TOLERANCE:
                return math.fsum(terms)
            count += 1

    @staticmethod
    def _standard_score(bound: float, mean: float, standard_deviation: float) -> float:
        """Return (bound - mean) / standard_deviation rounded once from exact arithmetic, or an infinity past the float range."""
        # Exact fractions keep the difference and the quotient finite
        # even when float arithmetic would overflow on its way there.
        exact = (Fraction(bound) - Fraction(mean)) / Fraction(standard_deviation)
        try:
            return float(exact)
        except OverflowError:
            return math.inf if exact > 0 else -math.inf

    @staticmethod
    def _unit_interval(value: float) -> float:
        """Clamp a computed probability to the range zero to one, which rounding can leave by a hair."""
        return min(max(value, 0.0), 1.0)

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.count_combinations,
            cls.count_permutations,
            cls.exact_factorial,
            cls.binomial_probability,
            cls.poisson_probability,
            cls.normal_distribution_probability,
            cls.normal_quantile,
            cls.birthday_collision_probability,
            cls.list_combinations,
        )


__all__ = ["ProbabilityToolFunctions"]
