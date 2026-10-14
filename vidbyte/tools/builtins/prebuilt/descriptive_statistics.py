"""FILE: vidbyte/tools/builtins/prebuilt/descriptive_statistics.py

PURPOSE: Defines DescriptiveStatisticsToolFunctions, the eleven prebuilt tools that describe lists of numbers: a full summary, modes, percentiles, quartiles, weighted means, Pearson and Spearman correlation, a least-squares line, moving averages, interquartile-range outliers, and ranks.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the DESCRIPTIVE_STATISTICS category is chosen. Builds on PrebuiltToolSupport in _support.py for paired lists, weights, finite results, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Variances, correlations, the regression line, and moving averages are computed on exact integers (each float scaled by a common power of two) and rounded once by Python's correctly rounded integer division, so no intermediate sum can overflow or lose precision.
FUNCTION INVENTORY: summarize_numbers, compute_mode, compute_percentile, compute_quartiles, weighted_mean, pearson_correlation, spearman_rank_correlation, linear_regression_fit, moving_average, detect_outliers_iqr, and rank_values are the tools; _scaled_integers turns floats into exact integers, _centered_moments builds the exact spread and co-spread sums, _correlation turns them into a coefficient, _median_of_sorted, _interpolate, and _quartiles pick values from sorted data, _tie_groups, _rank_for, and _doubled_ranks implement ranking; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new statistics tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.4, and its entry in tool_functions. A new rank or percentile method adds an enum member and one case in _rank_for or compute_percentile.
WHAT NOT TO DO IN THIS FILE: 1. Do not use statistics.correlation or statistics.linear_regression; their ranked and proportional modes differ between Python versions, so correlation is computed by hand. 2. Do not sum floats with a plain running total; use math.fsum or the exact scaled integers so a long list cannot drift or overflow midway. 3. Do not return a float without knowing it is finite; guard any formula that can overflow with PrebuiltToolSupport.float_result or an explicit check.
KNOWN EDGE CASES: The sum of numbers near the floating-point maximum overflows even when their mean would not, so summarize_numbers fails on it as EC-21 requires. The exclusive quartile method extrapolates for short lists, so two numbers give quartiles outside the data. Positive and negative zero compare equal, so they share one mode, one rank, and one tie group.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.4, section 9.2 items 5, 12, and 13, EC-21, EC-22); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_statistics.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import itertools
import math
import statistics
from collections import Counter
from collections.abc import Sequence
from fractions import Fraction
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_MOVING_AVERAGE_WINDOW,
    PREBUILT_MAX_OUTLIER_MULTIPLIER,
)
from vidbyte.lib.enums.prebuilt_tools import (
    PercentileMethod,
    QuartileMethod,
    RankMethod,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_FULL_PERCENT = 100
_QUARTILE_GROUPS = 4
_DEFAULT_OUTLIER_MULTIPLIER = 1.5

_VALUES_DESCRIPTION = "The numbers to analyze, given as a JSON array of finite numbers. Integers and decimals are both accepted and are read as floating-point values. The list must hold at least one number and at most ten thousand. Infinity and NaN are not accepted and fail validation."
_TWO_OR_MORE_VALUES_DESCRIPTION = "The numbers to analyze, given as a JSON array of finite numbers. Integers and decimals are both accepted and are read as floating-point values. The list must hold at least two numbers and at most ten thousand. Infinity and NaN are not accepted and fail validation."
_PAIRED_X_DESCRIPTION = "The first list of paired numbers, given as a JSON array of finite numbers. Each number pairs with the number at the same index in y. The list must hold at least two numbers and at most ten thousand. A list whose numbers are all equal fails with an error naming x."
_PAIRED_Y_DESCRIPTION = "The second list of paired numbers, given as a JSON array of finite numbers. It must hold exactly as many numbers as x, and a different length fails with an error naming y. The list must hold at least two numbers and at most ten thousand. A list whose numbers are all equal fails with an error naming y."


class DescriptiveStatisticsToolFunctions:
    """The descriptive_statistics category: summaries, percentiles, correlation, regression, smoothing, outliers, and ranks."""

    @staticmethod
    def summarize_numbers(values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_VALUES_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)]) -> PrebuiltToolOutput:
        """Compute the count, sum, mean, median, minimum, maximum, range, variance, and standard deviation of a list of numbers in one call. Use it whenever exact descriptive statistics are needed, because adding up many numbers by reading them is error-prone. The sum is rounded only once, the median of an even count averages the two middle numbers, sample statistics divide by one less than the count, and population statistics divide by the count. A single number gives null sample statistics and zero population statistics, and a result outside the floating-point range fails with an error naming values."""
        # Add the numbers with math.fsum, which raises only when the
        # total leaves the floating-point range.
        count = len(values)
        try:
            total = math.fsum(values)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("values", "the sum exceeds the floating-point range", "numbers whose sum is a finite number") from exc

        # Find the median and the extremes from the sorted numbers.
        ordered = sorted(values)
        median = DescriptiveStatisticsToolFunctions._median_of_sorted(ordered)
        spread_range = PrebuiltToolSupport.float_result(ordered[-1] - ordered[0], "values")

        # Measure the spread exactly on scaled integers, so each
        # variance is rounded once and an overflow is caught here.
        scaled, scale = DescriptiveStatisticsToolFunctions._scaled_integers(values)
        spread = count * sum(item * item for item in scaled) - sum(scaled) ** 2
        try:
            population_variance = spread / (count * count * scale * scale)
            sample_variance = spread / (count * (count - 1) * scale * scale) if count > 1 else None
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("values", "the variance exceeds the floating-point range", "numbers whose variance is a finite number") from exc
        return {
            "count": count,
            "sum": total,
            "mean": total / count,
            "median": median,
            "min": ordered[0],
            "max": ordered[-1],
            "range": spread_range,
            "sample_stdev": None if sample_variance is None else math.sqrt(sample_variance),
            "population_stdev": math.sqrt(population_variance),
            "sample_variance": sample_variance,
            "population_variance": population_variance,
        }

    @staticmethod
    def compute_mode(values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_VALUES_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)]) -> PrebuiltToolOutput:
        """Find the most frequent number or numbers in a list and how many times they occur. Use it to answer which value appears most often, including lists where several values tie. Numbers are compared exactly, every number tied for the highest frequency is listed in ascending order, and at most 1,000 modes are listed with truncated set when more exist. The list must hold at least one number, and the tool has no other failure case."""
        tallies = Counter(values)
        frequency = max(tallies.values())
        modes, truncated = PrebuiltToolSupport.cap_items(iter(sorted(value for value, count in tallies.items() if count == frequency)))
        return {"modes": modes, "frequency": frequency, "truncated": truncated}

    @staticmethod
    def compute_percentile(
        values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_VALUES_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        percentile: Annotated[float, Field(description="The percentile to compute, as a number from 0 to 100. Zero gives the smallest number and 100 gives the largest under every method. Fractional percentiles are allowed. A value outside that range fails validation.", ge=0, le=_FULL_PERCENT, allow_inf_nan=False)],
        method: Annotated[PercentileMethod, Field(description="How to pick a value when the percentile falls between two sorted numbers. Linear interpolates between the two neighbors, lower takes the one below, and higher takes the one above. Nearest_rank takes the number at the ceiling of the percentile times the count over 100, counting from one. The default is linear.")] = PercentileMethod.LINEAR,
    ) -> PrebuiltToolOutput:
        """Compute a percentile of a list of numbers using linear interpolation or the lower, higher, or nearest-rank method. Use it for percentile, median, or threshold questions where the exact convention matters. The numbers are sorted and the target position is the count minus one, times the percentile, over 100; linear interpolates between the numbers around that position, lower and higher take the one below or above, and nearest_rank instead takes the number at the ceiling of the percentile times the count over 100. The percentile must be between 0 and 100, and a value outside that range fails validation."""
        # Locate the percentile exactly among the sorted numbers, so a
        # position that lands on a whole index never rounds past it.
        ordered = sorted(values)
        share = Fraction(repr(percentile)) / _FULL_PERCENT
        position = (len(ordered) - 1) * share
        below, above = math.floor(position), math.ceil(position)

        # Pick or interpolate the value the chosen method asks for.
        match method:
            case PercentileMethod.LOWER:
                value = ordered[below]
            case PercentileMethod.HIGHER:
                value = ordered[above]
            case PercentileMethod.NEAREST_RANK:
                value = ordered[max(1, math.ceil(share * len(ordered))) - 1]
            case _:
                value = DescriptiveStatisticsToolFunctions._interpolate(ordered[below], ordered[above], float(position - below))
        return {"percentile": percentile, "value": value}

    @staticmethod
    def compute_quartiles(
        values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_TWO_OR_MORE_VALUES_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
        method: Annotated[QuartileMethod, Field(description="Which quartile convention to use, passed to the quantiles function of the Python statistics module. Exclusive treats the numbers as a sample and may extrapolate beyond the smallest or largest number. Inclusive treats the numbers as the whole population and always stays within them. The default is exclusive.")] = QuartileMethod.EXCLUSIVE,
    ) -> PrebuiltToolOutput:
        """Compute the first, second, and third quartiles of a list of numbers and the interquartile range between the first and third. Use it to describe the spread of data or to prepare an outlier check. The quartiles are exactly what the quantiles function of the Python statistics module gives with the chosen method, so the exclusive method may place a quartile outside the data for short lists. The list must hold at least two numbers, and a result outside the floating-point range fails with an error naming values."""
        first, second, third = DescriptiveStatisticsToolFunctions._quartiles(values, method)
        return {"q1": first, "q2": second, "q3": third, "iqr": PrebuiltToolSupport.float_result(third - first, "values")}

    @staticmethod
    def weighted_mean(
        values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description="The numbers to average, given as a JSON array of finite numbers. Each number pairs with the weight at the same index. The list must hold at least one number and at most ten thousand. Infinity and NaN are not accepted and fail validation.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        weights: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description="The weight of each number, given as a JSON array of finite numbers in the same order as values. It must hold exactly one weight per number. Weights must be zero or more, and at least one must be above zero. Any other weights fail with an error naming weights.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Compute the weighted average of a list of numbers, where each number counts in proportion to its weight. Use it for graded averages, portfolio returns, or any mean where items matter unequally. The result is the sum of each number times its weight divided by the total weight, computed exactly from the numbers as written and rounded once. A weights list of a different length, a negative weight, a zero total weight, or a total weight beyond the floating-point range fails with an error naming weights."""
        # Pair each number with its weight and total the weights, which
        # refuses a length mismatch, a negative weight, or a zero total.
        pairs = PrebuiltToolSupport.paired_values(values, weights, "weights")
        total = PrebuiltToolSupport.weight_total(weights, "weights")

        # Add the weighted numbers exactly and divide once at the end.
        weighted = sum((Fraction(repr(value)) * Fraction(repr(weight)) for value, weight in pairs), Fraction(0))
        try:
            total_weight = float(total)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("weights", "the total weight exceeds the floating-point range", "weights whose total is a finite number") from exc
        return {"weighted_mean": float(weighted / total), "total_weight": total_weight}

    @staticmethod
    def pearson_correlation(
        x: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_PAIRED_X_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
        y: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_PAIRED_Y_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Measure the Pearson correlation coefficient between two paired lists of numbers, with its square and the number of pairs. Use it to judge how closely two quantities follow a straight-line relationship. The coefficient runs from minus one for a perfect falling line to one for a perfect rising line and is computed from exact sums before one final rounding. Lists of different lengths fail naming y, and a list whose numbers are all equal fails naming that list, checking x first."""
        # Pair the lists, then build exact spread sums on scaled
        # integers and turn them into the coefficient.
        PrebuiltToolSupport.paired_values(x, y, "y")
        x_scaled, _ = DescriptiveStatisticsToolFunctions._scaled_integers(x)
        y_scaled, _ = DescriptiveStatisticsToolFunctions._scaled_integers(y)
        x_spread, y_spread, co_spread = DescriptiveStatisticsToolFunctions._centered_moments(x_scaled, y_scaled)
        coefficient, squared = DescriptiveStatisticsToolFunctions._correlation(x_spread, y_spread, co_spread)
        return {"r": coefficient, "r_squared": squared, "count": len(x)}

    @staticmethod
    def spearman_rank_correlation(
        x: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_PAIRED_X_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
        y: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_PAIRED_Y_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Measure the Spearman rank correlation between two paired lists of numbers, with the number of pairs. Use it to judge whether two quantities rise and fall together even when the relationship is not a straight line. Each list is replaced by its ranks, tied numbers share the average of their positions, and the result is the Pearson correlation of those ranks computed from exact sums. Lists of different lengths fail naming y, and a list whose numbers are all equal fails naming that list, checking x first."""
        # Pair the lists, then rank each one with average ranks for
        # ties, doubled so every rank is a whole number.
        PrebuiltToolSupport.paired_values(x, y, "y")
        x_ranks = DescriptiveStatisticsToolFunctions._doubled_ranks(DescriptiveStatisticsToolFunctions._tie_groups(x, False), len(x))
        y_ranks = DescriptiveStatisticsToolFunctions._doubled_ranks(DescriptiveStatisticsToolFunctions._tie_groups(y, False), len(y))

        # Correlate the ranks exactly; doubling does not change it.
        x_spread, y_spread, co_spread = DescriptiveStatisticsToolFunctions._centered_moments(x_ranks, y_ranks)
        coefficient, _ = DescriptiveStatisticsToolFunctions._correlation(x_spread, y_spread, co_spread)
        return {"rho": coefficient, "count": len(x)}

    @staticmethod
    def linear_regression_fit(
        x: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description="The x coordinates of the points, given as a JSON array of finite numbers. Each coordinate pairs with the y coordinate at the same index. The list must hold at least two numbers and at most ten thousand. A list whose numbers are all equal has no single best line and fails with an error naming x.", min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
        y: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description="The y coordinates of the points, given as a JSON array of finite numbers. It must hold exactly as many numbers as x, and a different length fails with an error naming y. The list must hold at least two numbers and at most ten thousand. Equal y coordinates are allowed and give a flat line.", min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Fit the least-squares straight line through paired points and return its slope, intercept, coefficient of determination, and the number of points. Use it to estimate a linear trend or to predict y from x. The fit minimizes the squared vertical distances and is computed from exact sums before one final rounding, and equal y coordinates give a slope of zero with a coefficient of determination of one. Lists of different lengths fail naming y, x coordinates that are all equal fail naming x, and a slope or intercept beyond the floating-point range fails naming y."""
        # Pair the lists and build exact spread sums on scaled integers.
        PrebuiltToolSupport.paired_values(x, y, "y")
        x_scaled, x_scale = DescriptiveStatisticsToolFunctions._scaled_integers(x)
        y_scaled, y_scale = DescriptiveStatisticsToolFunctions._scaled_integers(y)
        x_spread, y_spread, co_spread = DescriptiveStatisticsToolFunctions._centered_moments(x_scaled, y_scaled)
        if x_spread == 0:
            raise PrebuiltToolSupport.argument_error("x", "all of its numbers are equal, so no single line fits", "x coordinates that are not all equal")

        # Divide the exact sums once each; Python rounds an integer
        # quotient correctly and raises when it is too large.
        count = len(x)
        try:
            slope = co_spread * x_scale / (x_spread * y_scale)
            intercept = (sum(y_scaled) * x_spread - co_spread * sum(x_scaled)) / (count * y_scale * x_spread)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("y", "the fitted slope or intercept exceeds the floating-point range", "points whose fitted line has a finite slope and intercept") from exc
        r_squared = 1.0 if y_spread == 0 else co_spread * co_spread / (x_spread * y_spread)
        return {"slope": slope, "intercept": intercept, "r_squared": r_squared, "count": count}

    @staticmethod
    def moving_average(
        values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_VALUES_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        window: Annotated[int, Field(description="How many consecutive numbers each average covers. The value must be between 1 and 1,000. A window of one returns the numbers themselves. A window longer than the list fails with an error naming window.", ge=1, le=PREBUILT_MAX_MOVING_AVERAGE_WINDOW)],
    ) -> PrebuiltToolOutput:
        """Compute the trailing simple moving average of a list of numbers over a fixed window. Use it to smooth a noisy series or to see a running trend. The result holds one average per full window, so a list of n numbers gives n minus window plus one averages, and the first covers the first window numbers. A window longer than the list fails with an error naming window."""
        # Refuse a window that no stretch of the list can fill.
        if window > len(values):
            raise PrebuiltToolSupport.argument_error("window", f"it is longer than the {len(values)} numbers in the list", "a window no longer than the list")

        # Take exact running totals on scaled integers, so each window
        # sum is one subtraction and each average is rounded once.
        scaled, scale = DescriptiveStatisticsToolFunctions._scaled_integers(values)
        running = list(itertools.accumulate(scaled, initial=0))
        divisor = window * scale
        return {"averages": [(running[end] - running[end - window]) / divisor for end in range(window, len(values) + 1)]}

    @staticmethod
    def detect_outliers_iqr(
        values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_TWO_OR_MORE_VALUES_DESCRIPTION, min_length=2, max_length=PREBUILT_MAX_LIST_ITEMS)],
        multiplier: Annotated[float, Field(description="How many interquartile ranges the fences sit beyond the first and third quartiles. Larger values flag fewer and more extreme outliers. The value must be above zero and at most ten. The default is the conventional one and a half.", gt=0, le=PREBUILT_MAX_OUTLIER_MULTIPLIER, allow_inf_nan=False)] = _DEFAULT_OUTLIER_MULTIPLIER,
    ) -> PrebuiltToolOutput:
        """Find the numbers in a list that lie outside the interquartile-range fences, with the quartiles and fences used. Use it to flag unusually high or low values before averaging or reporting. The quartiles use the exclusive method, the fences sit the multiplier times the interquartile range below the first quartile and above the third, and only numbers strictly beyond a fence count. Outliers are listed in input order with their 0-based index, at most 1,000 are listed with truncated set when more exist, and a result outside the floating-point range fails naming values."""
        # Compute the exclusive quartiles and the two fences.
        first, _, third = DescriptiveStatisticsToolFunctions._quartiles(values, QuartileMethod.EXCLUSIVE)
        spread = PrebuiltToolSupport.float_result(third - first, "values")
        lower_fence = PrebuiltToolSupport.float_result(first - multiplier * spread, "values")
        upper_fence = PrebuiltToolSupport.float_result(third + multiplier * spread, "values")

        # List the numbers strictly outside a fence, in input order.
        outliers, truncated = PrebuiltToolSupport.cap_items(
            {"index": index, "value": value} for index, value in enumerate(values) if value < lower_fence or value > upper_fence
        )
        return {"q1": first, "q3": third, "iqr": spread, "lower_fence": lower_fence, "upper_fence": upper_fence, "outliers": outliers, "truncated": truncated}

    @staticmethod
    def rank_values(
        values: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description=_VALUES_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        method: Annotated[RankMethod, Field(description="How tied numbers are ranked. Average gives each tied number the mean of the positions they share, and min and max give the lowest or highest of those positions. Dense ranks distinct numbers consecutively with no gaps, and ordinal gives tied numbers consecutive ranks in input order. The default is average, the only method whose ranks are decimals.")] = RankMethod.AVERAGE,
        descending: Annotated[bool, Field(description="Whether the largest number gets the first rank. When false, the smallest number gets the first rank. Ties are handled the same way in both directions. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Assign a rank to each number in a list, listed in input order, with a chosen way of handling ties. Use it for leaderboards, standings, or as input to rank-based statistics. Ranks start at one, average gives tied numbers the mean of their positions as decimals, min and max give the lowest or highest of those positions, dense leaves no gaps, and ordinal breaks ties by input order. Descending ranks the largest number first, and the tool has no failure case beyond the list caps."""
        # Group the positions of equal numbers in rank order, then give
        # every member of each group the rank the method asks for.
        groups = DescriptiveStatisticsToolFunctions._tie_groups(values, descending)
        ranks: list[float | int] = [0] * len(values)
        start = 0
        for dense_rank, group in enumerate(groups, start=1):
            for offset, index in enumerate(group):
                ranks[index] = DescriptiveStatisticsToolFunctions._rank_for(method, start, len(group), offset, dense_rank)
            start += len(group)
        return {"ranks": ranks}

    @staticmethod
    def _scaled_integers(values: Sequence[float]) -> tuple[list[int], int]:
        """Return each number times a common power of two as an exact integer, with that power of two."""
        ratios = [value.as_integer_ratio() for value in values]
        scale = max(denominator for _, denominator in ratios)
        return [numerator * (scale // denominator) for numerator, denominator in ratios], scale

    @staticmethod
    def _centered_moments(first: Sequence[int], second: Sequence[int]) -> tuple[int, int, int]:
        """Return n times the sums of squared deviations of each list and of their cross products, all exact."""
        count = len(first)
        first_total, second_total = sum(first), sum(second)
        first_spread = count * sum(item * item for item in first) - first_total * first_total
        second_spread = count * sum(item * item for item in second) - second_total * second_total
        co_spread = count * sum(left * right for left, right in zip(first, second, strict=True)) - first_total * second_total
        return first_spread, second_spread, co_spread

    @staticmethod
    def _correlation(x_spread: int, y_spread: int, co_spread: int) -> tuple[float, float]:
        """Turn exact spread sums into a correlation coefficient and its square, refusing a list of equal numbers."""
        expected = "a list whose numbers are not all equal"
        if x_spread == 0:
            raise PrebuiltToolSupport.argument_error("x", "all of its numbers are equal, so the correlation is undefined", expected)
        if y_spread == 0:
            raise PrebuiltToolSupport.argument_error("y", "all of its numbers are equal, so the correlation is undefined", expected)
        squared = co_spread * co_spread / (x_spread * y_spread)
        magnitude = math.sqrt(squared)
        coefficient = magnitude if co_spread >= 0 else -magnitude
        return max(-1.0, min(1.0, coefficient)), squared

    @staticmethod
    def _median_of_sorted(ordered: Sequence[float]) -> float:
        """Return the middle number, or the mean of the two middle numbers without overflowing their sum."""
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        lower, upper = ordered[middle - 1], ordered[middle]
        pair_sum = lower + upper
        return pair_sum / 2 if math.isfinite(pair_sum) else lower / 2 + upper / 2

    @staticmethod
    def _interpolate(lower: float, upper: float, weight: float) -> float:
        """Move the given share of the way from lower to upper, without overflowing when the gap is huge."""
        gap = upper - lower
        if math.isfinite(gap):
            return lower + weight * gap
        return lower * (1 - weight) + upper * weight

    @staticmethod
    def _quartiles(values: Sequence[float], method: QuartileMethod) -> tuple[float, float, float]:
        """Return the three quartiles statistics.quantiles gives, refusing a result outside the floating-point range."""
        try:
            first, second, third = statistics.quantiles(values, n=_QUARTILE_GROUPS, method=method.value)
        except statistics.StatisticsError as exc:
            raise PrebuiltToolSupport.argument_error("values", "the quartiles could not be computed", "at least two finite numbers") from exc
        return (
            PrebuiltToolSupport.float_result(first, "values"),
            PrebuiltToolSupport.float_result(second, "values"),
            PrebuiltToolSupport.float_result(third, "values"),
        )

    @staticmethod
    def _tie_groups(values: Sequence[float], descending: bool) -> list[list[int]]:
        """Return the input positions in rank order, grouped by equal number, keeping input order inside each group."""
        order = sorted(range(len(values)), key=values.__getitem__, reverse=descending)
        return [list(group) for _, group in itertools.groupby(order, key=values.__getitem__)]

    @staticmethod
    def _rank_for(method: RankMethod, start: int, size: int, offset: int, dense_rank: int) -> float | int:
        """Return the rank of one member of a tie group that starts after `start` earlier numbers."""
        match method:
            case RankMethod.MIN:
                return start + 1
            case RankMethod.MAX:
                return start + size
            case RankMethod.DENSE:
                return dense_rank
            case RankMethod.ORDINAL:
                return start + offset + 1
            case _:
                return start + (size + 1) / 2

    @staticmethod
    def _doubled_ranks(groups: Sequence[Sequence[int]], count: int) -> list[int]:
        """Return twice the average rank of every input position, which is always a whole number."""
        ranks = [0] * count
        start = 0
        for group in groups:
            for index in group:
                ranks[index] = 2 * start + len(group) + 1
            start += len(group)
        return ranks

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.summarize_numbers,
            cls.compute_mode,
            cls.compute_percentile,
            cls.compute_quartiles,
            cls.weighted_mean,
            cls.pearson_correlation,
            cls.spearman_rank_correlation,
            cls.linear_regression_fit,
            cls.moving_average,
            cls.detect_outliers_iqr,
            cls.rank_values,
        )


__all__ = ["DescriptiveStatisticsToolFunctions"]
