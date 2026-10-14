"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_statistics.py

PURPOSE: Exact-output and error cases for every Appendix A row of the descriptive_statistics, probability, and seeded_random categories (AC-11), run the way a model calls a tool.
ROLE IN CODEBASE: Drives FunctionTool.execute through prebuilt_tool_harness.ToolRunner over the session library from conftest.py (PrebuiltTools(PrebuiltToolCategory)); the expected values are hand-computed, published, or computed here by a different route.
ARCHITECTURE NOTE: Two case tables feed two parametrized tests; the seeded tools get extra tests that rebuild the documented random.Random(seed) calls in this interpreter, because EC-24 forbids pinning drawn values across Python versions.
FUNCTION INVENTORY: test_statistics_rows_return_documented_output checks SUCCESS_CASES; test_statistics_rows_reject_bad_input checks FAILURE_CASES; test_seeded_tools_repeat_for_the_same_seed, test_seeded_tools_follow_the_documented_generator_calls, test_seeded_tools_change_with_the_seed, and test_seeded_tools_leave_the_global_random_state_alone cover A.6.
COMMON MODIFICATION PATTERNS: Add an ok(...) or bad(...) entry to the matching table when a row gains edge behavior; compute the new expected value by hand or with exact Fraction or Decimal arithmetic first.
WHAT NOT TO DO IN THIS FILE: 1. Do not paste seeded draws as literals; they change between Python versions (EC-24). 2. Do not compute expectations with the statistics or math helper the row names when an exact route exists; a copy of the implementation cannot catch its mistakes.
KNOWN EDGE CASES: A probability of exactly 0 or 1 must not reach a logarithm; 1464! has 4,001 digits while 1463! has 3,998; 10^4000 is the first power of ten that INV-18 refuses; a value exactly on an outlier fence is not an outlier.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.4, A.5, A.6 and §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_statistics.py
"""

from __future__ import annotations

import math
import random
import re
import uuid
from collections.abc import Iterator
from itertools import islice
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import ANY, FailureCase, SuccessCase, ToolRunner, bad, invalid, ok

UUID4_PATTERN = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


def binomial_by_products(n: int, k: int) -> int:
    """C(n, k) by the multiplicative formula, a different route from math.comb."""
    value = 1
    for step in range(1, k + 1):
        value = value * (n - k + step) // step
    return value


def index_combinations(n: int, size: int, start: int, with_repetition: bool) -> Iterator[tuple[int, ...]]:
    """Lexicographic index tuples built recursively, a different route from itertools."""
    if size == 0:
        yield ()
        return
    for first in range(start, n):
        for rest in index_combinations(n, size - 1, first if with_repetition else first + 1, with_repetition):
            yield (first, *rest)


def first_combinations(items: list[str], size: int, with_repetition: bool, limit: int) -> list[list[str]]:
    """The first `limit` combinations of `items` in itertools order, without using itertools."""
    picked = islice(index_combinations(len(items), size, 0, with_repetition), limit)
    return [[items[index] for index in combo] for combo in picked]


TWENTY_ITEMS = [f"item{index:02d}" for index in range(20)]
ONE_THOUSAND_AND_ONE = [float(value) for value in range(1001)]

SUMMARY_KEYS = ("count", "sum", "mean", "median", "min", "max", "range")

SUCCESS_CASES = [
    # A.4 summarize_numbers: sample statistics divide by n - 1, population statistics by n.
    ok(
        "summarize_numbers",
        {"values": [1, 2, 3, 4]},
        {
            "count": 4, "sum": 10.0, "mean": 2.5, "median": 2.5, "min": 1.0, "max": 4.0, "range": 3.0,
            "sample_variance": 5 / 3, "population_variance": 1.25,
            "sample_stdev": math.sqrt(5 / 3), "population_stdev": math.sqrt(1.25),
        },
        "even-count",
    ),
    ok(
        "summarize_numbers",
        {"values": [5, 1, 3]},
        {
            "count": 3, "sum": 9.0, "mean": 3.0, "median": 3.0, "min": 1.0, "max": 5.0, "range": 4.0,
            "sample_variance": 4.0, "population_variance": 8 / 3, "sample_stdev": 2.0, "population_stdev": math.sqrt(8 / 3),
        },
        "unsorted-odd-count",
    ),
    ok(
        "summarize_numbers",
        {"values": [7.5]},
        {
            "count": 1, "sum": 7.5, "mean": 7.5, "median": 7.5, "min": 7.5, "max": 7.5, "range": 0.0,
            "sample_variance": None, "population_variance": 0.0, "sample_stdev": None, "population_stdev": 0.0,
        },
        "single-value-EC-22",
    ),
    # A.4 compute_mode: every tied value, ascending, compared exactly.
    ok("compute_mode", {"values": [3, 1, 2, 2, 3]}, {"modes": [2.0, 3.0], "frequency": 2, "truncated": False}, "tie-ascending"),
    ok("compute_mode", {"values": [0.30000000000000004, 0.3, 0.3]}, {"modes": [0.3], "frequency": 2, "truncated": False}, "exact-compare"),
    ok(
        "compute_mode",
        {"values": list(reversed(ONE_THOUSAND_AND_ONE))},
        {"modes": ONE_THOUSAND_AND_ONE[:1000], "frequency": 1, "truncated": True},
        "cap-1000-INV-17",
    ),
    # A.4 compute_percentile: h = (n - 1) p / 100 on the sorted list; nearest_rank values match the
    # published worked example for {15, 20, 35, 40, 50}.
    ok("compute_percentile", {"values": [50, 15, 40, 20, 35], "percentile": 40}, {"percentile": 40.0, "value": 29.0}, "linear-default"),
    ok("compute_percentile", {"values": [50, 15, 40, 20, 35], "percentile": 40, "method": "lower"}, {"percentile": 40.0, "value": 20.0}, "lower"),
    ok("compute_percentile", {"values": [50, 15, 40, 20, 35], "percentile": 40, "method": "higher"}, {"percentile": 40.0, "value": 35.0}, "higher"),
    ok("compute_percentile", {"values": [15, 20, 35, 40, 50], "percentile": 30, "method": "nearest_rank"}, {"percentile": 30.0, "value": 20.0}, "nearest-rank-30"),
    ok("compute_percentile", {"values": [15, 20, 35, 40, 50], "percentile": 0, "method": "nearest_rank"}, {"percentile": 0.0, "value": 15.0}, "nearest-rank-0"),
    ok("compute_percentile", {"values": [15, 20, 35, 40, 50], "percentile": 100}, {"percentile": 100.0, "value": 50.0}, "linear-100"),
    # A.4 compute_quartiles: the row's own worked values for 1 through 8.
    ok("compute_quartiles", {"values": [8, 1, 7, 2, 6, 3, 5, 4]}, {"q1": 2.25, "q2": 4.5, "q3": 6.75, "iqr": 4.5}, "exclusive-default"),
    ok("compute_quartiles", {"values": [1, 2, 3, 4, 5, 6, 7, 8], "method": "inclusive"}, {"q1": 2.75, "q2": 4.5, "q3": 6.25, "iqr": 3.5}, "inclusive"),
    # A.4 weighted_mean: (1*3 + 2*2 + 3*1) / 6.
    ok("weighted_mean", {"values": [1, 2, 3], "weights": [3, 2, 1]}, {"weighted_mean": 10 / 6, "total_weight": 6.0}, "basic"),
    ok("weighted_mean", {"values": [10, 20], "weights": [0, 1]}, {"weighted_mean": 20.0, "total_weight": 1.0}, "zero-weight-allowed"),
    # A.4 pearson_correlation: Sxy = 6, Sxx = 10, Syy = 6, so r = 6 / sqrt(60) and r^2 = 0.6.
    ok("pearson_correlation", {"x": [1, 2, 3, 4, 5], "y": [2, 4, 5, 4, 5]}, {"r": 6 / math.sqrt(60), "r_squared": 0.6, "count": 5}, "basic"),
    ok("pearson_correlation", {"x": [1, 2, 3], "y": [3, 2, 1]}, {"r": -1.0, "r_squared": 1.0, "count": 3}, "perfect-negative"),
    # A.4 spearman_rank_correlation: y ranks are 1, 2, 3.5, 5, 3.5, so rho = 8 / sqrt(95).
    ok("spearman_rank_correlation", {"x": [1, 2, 3, 4, 5], "y": [5, 6, 7, 8, 7]}, {"rho": 8 / math.sqrt(95), "count": 5}, "average-rank-ties"),
    ok("spearman_rank_correlation", {"x": [1, 2, 3, 4], "y": [1, 4, 9, 16]}, {"rho": 1.0, "count": 4}, "monotone-nonlinear"),
    # A.4 linear_regression_fit: slope Sxy / Sxx = 0.6, intercept 4 - 0.6 * 3 = 2.2.
    ok("linear_regression_fit", {"x": [1, 2, 3, 4, 5], "y": [2, 4, 5, 4, 5]}, {"slope": 0.6, "intercept": 2.2, "r_squared": 0.6, "count": 5}, "basic"),
    ok("linear_regression_fit", {"x": [1, 2, 3], "y": [7, 7, 7]}, {"slope": 0.0, "intercept": 7.0, "r_squared": 1.0, "count": 3}, "constant-y"),
    # A.4 moving_average: trailing windows, n - window + 1 averages.
    ok("moving_average", {"values": [1, 2, 3, 4, 5], "window": 3}, {"averages": [2.0, 3.0, 4.0]}, "window-3"),
    ok("moving_average", {"values": [1, 2, 3, 4, 5], "window": 5}, {"averages": [3.0]}, "window-equals-length"),
    # A.4 detect_outliers_iqr: exclusive quartiles of sorted [-50, 1..7, 100] are 1.5 and 6.5; outliers in input order.
    ok(
        "detect_outliers_iqr",
        {"values": [100, 1, 2, 3, -50, 4, 5, 6, 7]},
        {
            "q1": 1.5, "q3": 6.5, "iqr": 5.0, "lower_fence": -6.0, "upper_fence": 14.0,
            "outliers": [{"index": 0, "value": 100.0}, {"index": 4, "value": -50.0}], "truncated": False,
        },
        "input-order",
    ),
    ok(
        "detect_outliers_iqr",
        {"values": [0, 10, 20, 30, 40, 50, 60], "multiplier": 0.25},
        {"q1": 10.0, "q3": 50.0, "iqr": 40.0, "lower_fence": 0.0, "upper_fence": 60.0, "outliers": [], "truncated": False},
        "on-fence-is-not-outlier",
    ),
    ok(
        "detect_outliers_iqr",
        {"values": [0, 10, 20, 30, 40, 50, 60], "multiplier": 0.125},
        {
            "q1": 10.0, "q3": 50.0, "iqr": 40.0, "lower_fence": 5.0, "upper_fence": 55.0,
            "outliers": [{"index": 0, "value": 0.0}, {"index": 6, "value": 60.0}], "truncated": False,
        },
        "narrow-fences",
    ),
    # A.4 rank_values: floats for average, integers for every other method.
    ok("rank_values", {"values": [10, 20, 20, 30]}, {"ranks": [1.0, 2.5, 2.5, 4.0]}, "average-default"),
    ok("rank_values", {"values": [10, 20, 20, 30], "method": "min"}, {"ranks": [1, 2, 2, 4]}, "min"),
    ok("rank_values", {"values": [10, 20, 20, 30], "method": "max"}, {"ranks": [1, 3, 3, 4]}, "max"),
    ok("rank_values", {"values": [10, 20, 20, 30], "method": "dense"}, {"ranks": [1, 2, 2, 3]}, "dense"),
    ok("rank_values", {"values": [10, 20, 20, 30], "method": "ordinal", "descending": True}, {"ranks": [4, 2, 3, 1]}, "ordinal-descending"),
    ok("rank_values", {"values": [10, 20, 20, 30], "descending": True}, {"ranks": [4.0, 2.5, 2.5, 1.0]}, "average-descending"),
    # A.5 count_combinations: C(52, 5) is the published count of five-card poker hands.
    ok("count_combinations", {"n": 52, "k": 5}, {"count": "2598960"}, "poker-hands"),
    ok("count_combinations", {"n": 5, "k": 2, "with_repetition": True}, {"count": "15"}, "with-repetition"),
    ok("count_combinations", {"n": 3, "k": 5}, {"count": "0"}, "k-over-n"),
    ok("count_combinations", {"n": 0, "k": 0, "with_repetition": True}, {"count": "1"}, "repetition-zero-zero"),
    ok("count_combinations", {"n": 0, "k": 3, "with_repetition": True}, {"count": "0"}, "repetition-zero-n"),
    ok("count_combinations", {"n": 10000, "k": 5000}, {"count": str(binomial_by_products(10000, 5000))}, "largest-3009-digits"),
    # A.5 count_permutations: null k means n; with repetition the count is n^k.
    ok("count_permutations", {"n": 5, "k": 2}, {"count": "20"}, "basic"),
    ok("count_permutations", {"n": 5, "k": None}, {"count": "120"}, "null-k-is-n"),
    ok("count_permutations", {"n": 5, "k": 2, "with_repetition": True}, {"count": "25"}, "with-repetition"),
    ok("count_permutations", {"n": 3, "k": 4}, {"count": "0"}, "k-over-n"),
    ok("count_permutations", {"n": 10, "k": 3999, "with_repetition": True}, {"count": "1" + "0" * 3999}, "4000-digits-allowed"),
    # A.5 exact_factorial: the product is taken with math.prod, not math.factorial.
    ok("exact_factorial", {"n": 0}, {"factorial": "1", "digit_count": 1}, "zero"),
    ok("exact_factorial", {"n": 20}, {"factorial": "2432902008176640000", "digit_count": 19}, "twenty"),
    ok("exact_factorial", {"n": 1463}, {"factorial": str(math.prod(range(1, 1464))), "digit_count": 3998}, "largest-AC-15"),
    # A.5 binomial_probability: exact sums over C(10, i) / 1024 and exact Fraction sums for p = 0.3.
    ok("binomial_probability", {"trials": 10, "successes": 3, "probability": 0.5}, {"probability": 120 / 1024}, "exactly"),
    ok("binomial_probability", {"trials": 10, "successes": 3, "probability": 0.5, "tail": "at_most"}, {"probability": 176 / 1024}, "at-most"),
    ok("binomial_probability", {"trials": 10, "successes": 3, "probability": 0.5, "tail": "at_least"}, {"probability": 968 / 1024}, "at-least"),
    ok("binomial_probability", {"trials": 10, "successes": 3, "probability": 0.5, "tail": "less_than"}, {"probability": 56 / 1024}, "less-than"),
    ok("binomial_probability", {"trials": 10, "successes": 3, "probability": 0.5, "tail": "greater_than"}, {"probability": 848 / 1024}, "greater-than"),
    ok("binomial_probability", {"trials": 20, "successes": 7, "probability": 0.3}, {"probability": 0.1642619852172365}, "p-0.3"),
    ok("binomial_probability", {"trials": 20, "successes": 7, "probability": 0.3, "tail": "at_most"}, {"probability": 0.7722717974181604}, "p-0.3-at-most"),
    ok("binomial_probability", {"trials": 10000, "successes": 5000, "probability": 0.5}, {"probability": 0.007978646139382154}, "log-space-large"),
    ok(
        "binomial_probability",
        {"trials": 10000, "successes": 5000, "probability": 0.5, "tail": "at_most"},
        {"probability": 0.5039893230696911},
        "log-space-large-tail",
    ),
    ok("binomial_probability", {"trials": 5, "successes": 0, "probability": 0.0}, {"probability": 1.0}, "p-zero-exact"),
    ok("binomial_probability", {"trials": 5, "successes": 1, "probability": 0.0, "tail": "at_least"}, {"probability": 0.0}, "p-zero-tail"),
    ok("binomial_probability", {"trials": 5, "successes": 5, "probability": 1.0}, {"probability": 1.0}, "p-one-exact"),
    ok("binomial_probability", {"trials": 5, "successes": 4, "probability": 1.0, "tail": "at_most"}, {"probability": 0.0}, "p-one-tail"),
    ok("binomial_probability", {"trials": 0, "successes": 0, "probability": 0.25}, {"probability": 1.0}, "no-trials"),
    # A.5 poisson_probability: e^-2 * 2^k / k! summed in 60-digit Decimal arithmetic.
    ok("poisson_probability", {"rate": 2, "occurrences": 3}, {"probability": 0.18044704431548359}, "exactly"),
    ok("poisson_probability", {"rate": 2, "occurrences": 3, "tail": "at_most"}, {"probability": 0.85712346049854705}, "at-most"),
    ok("poisson_probability", {"rate": 2, "occurrences": 3, "tail": "at_least"}, {"probability": 0.32332358381693654}, "at-least"),
    ok("poisson_probability", {"rate": 2, "occurrences": 3, "tail": "less_than"}, {"probability": 0.67667641618306346}, "less-than"),
    ok("poisson_probability", {"rate": 2, "occurrences": 3, "tail": "greater_than"}, {"probability": 0.14287653950145295}, "greater-than"),
    ok("poisson_probability", {"rate": 0.5, "occurrences": 0}, {"probability": 0.60653065971263342}, "zero-occurrences"),
    ok("poisson_probability", {"rate": 1000, "occurrences": 1000}, {"probability": 0.012614611348721500}, "log-space-large"),
    ok("poisson_probability", {"rate": 3, "occurrences": 0, "tail": "at_least"}, {"probability": 1.0}, "at-least-zero"),
    ok("poisson_probability", {"rate": 3, "occurrences": 0, "tail": "less_than"}, {"probability": 0.0}, "less-than-zero"),
    # A.5 normal_distribution_probability: erf series values in 50-digit Decimal arithmetic.
    ok("normal_distribution_probability", {"lower": -1, "upper": 1}, {"probability": 0.68268949213708590}, "one-sigma"),
    ok("normal_distribution_probability", {"lower": -1.96, "upper": 1.96}, {"probability": 0.95000420970355913}, "1.96-sigma"),
    ok("normal_distribution_probability", {"lower": 0.5, "upper": 2}, {"probability": 0.28578740677780769}, "asymmetric"),
    ok("normal_distribution_probability", {"lower": None, "upper": 0}, {"probability": 0.5}, "null-lower-unbounded"),
    ok("normal_distribution_probability", {"lower": 0}, {"probability": 0.5}, "missing-upper-unbounded"),
    ok(
        "normal_distribution_probability",
        {"lower": 85, "upper": 115, "mean": 100, "standard_deviation": 15},
        {"probability": 0.68268949213708590},
        "mean-and-deviation",
    ),
    ok("normal_distribution_probability", {"lower": 1, "upper": 1}, {"probability": 0.0}, "empty-interval"),
    # A.5 normal_quantile: the published z value 1.959963984540054 for 0.975.
    ok("normal_quantile", {"probability": 0.975}, {"x": 1.959963984540054}, "z-975"),
    ok("normal_quantile", {"probability": 0.5}, {"x": 0.0}, "median"),
    ok("normal_quantile", {"probability": 0.025, "mean": 100, "standard_deviation": 15}, {"x": 100 - 15 * 1.959963984540054}, "scaled"),
    # A.5 birthday_collision_probability: exact Fraction products; 23 people give the published 0.5073.
    ok("birthday_collision_probability", {"items": 23, "possible_values": 365}, {"probability": 0.5072972343239854}, "classic-23"),
    ok("birthday_collision_probability", {"items": 50, "possible_values": 365}, {"probability": 0.9703735795779884}, "fifty"),
    ok("birthday_collision_probability", {"items": 2, "possible_values": 2}, {"probability": 0.5}, "two-of-two"),
    ok("birthday_collision_probability", {"items": 1, "possible_values": 365}, {"probability": 0.0}, "one-item"),
    ok("birthday_collision_probability", {"items": 0, "possible_values": 1}, {"probability": 0.0}, "no-items"),
    ok("birthday_collision_probability", {"items": 366, "possible_values": 365}, {"probability": 1.0}, "pigeonhole"),
    ok("birthday_collision_probability", {"items": 100000, "possible_values": 10**18}, {"probability": 4.999949987500417e-09}, "tiny-log1p"),
    # A.5 list_combinations: itertools order, rebuilt here by recursion.
    ok(
        "list_combinations",
        {"items": ["a", "b", "c"], "size": 2},
        {"combinations": [["a", "b"], ["a", "c"], ["b", "c"]], "count": 3, "truncated": False},
        "basic",
    ),
    ok(
        "list_combinations",
        {"items": ["a", "b", "c"], "size": 2, "with_repetition": True},
        {"combinations": [["a", "a"], ["a", "b"], ["a", "c"], ["b", "b"], ["b", "c"], ["c", "c"]], "count": 6, "truncated": False},
        "with-repetition",
    ),
    ok("list_combinations", {"items": ["a", "b"], "size": 0}, {"combinations": [[]], "count": 1, "truncated": False}, "size-zero"),
    ok("list_combinations", {"items": ["a", "b"], "size": 3}, {"combinations": [], "count": 0, "truncated": False}, "size-over-length"),
    ok("list_combinations", {"items": ["x", "x"], "size": 1}, {"combinations": [["x"], ["x"]], "count": 2, "truncated": False}, "duplicates-distinct"),
    ok(
        "list_combinations",
        {"items": TWENTY_ITEMS, "size": 10},
        {"combinations": first_combinations(TWENTY_ITEMS, 10, False, 1000), "count": 184756, "truncated": True},
        "cap-1000-full-count",
    ),
    # A.6 seeded tools: only cases whose output no draw can change are pinned here.
    ok("seeded_random_integers", {"seed": 7, "count": 3, "minimum": 5, "maximum": 5}, {"values": [5, 5, 5]}, "single-value-range"),
    ok("seeded_random_integers", {"seed": 7, "count": 1, "minimum": -4, "maximum": -4, "unique": True}, {"values": [-4]}, "unique-single"),
    ok("seeded_shuffle_list", {"items": [], "seed": 1}, {"items": []}, "empty"),
    ok("seeded_shuffle_list", {"items": ["only"], "seed": 1}, {"items": ["only"]}, "single"),
    ok("seeded_sample_list", {"items": ["a", "b"], "size": 0, "seed": 3}, {"items": [], "indices": []}, "size-zero"),
    ok("seeded_sample_list", {"items": ["only"], "size": 1, "seed": 3}, {"items": ["only"], "indices": [0]}, "single"),
    ok("seeded_weighted_choice", {"items": ["a", "b", "c"], "weights": [0, 1, 0], "seed": 3, "picks": 5}, {"picks": ["b"] * 5}, "one-positive-weight"),
    ok("seeded_weighted_choice", {"items": ["a"], "weights": [2.5], "seed": 9}, {"picks": ["a"]}, "default-one-pick"),
    ok("roll_dice_notation", {"notation": "3d6+2", "seed": 11}, {"rolls": ANY, "modifier": 2, "total": ANY}, "plus-modifier"),
    ok("roll_dice_notation", {"notation": "  d20 - 3 ", "seed": 11}, {"rolls": ANY, "modifier": -3, "total": ANY}, "default-one-die"),
    ok("generate_seeded_uuid4", {"seed": 5}, {"uuids": ANY}, "default-count"),
]

FAILURE_CASES = [
    # A.4
    invalid("summarize_numbers", {"values": []}, "values", "empty"),
    bad("summarize_numbers", {"values": [1e308, 1e308]}, "values", "sum-overflow-EC-21"),
    bad("summarize_numbers", {"values": [1e308, -1e308]}, "values", "spread-overflow"),
    invalid("compute_mode", {"values": []}, "values", "empty"),
    invalid("compute_percentile", {"values": [1, 2], "percentile": 100.5}, "percentile", "over-100"),
    invalid("compute_quartiles", {"values": [1]}, "values", "one-value"),
    bad("weighted_mean", {"values": [1, 2], "weights": [1]}, "weights", "length-mismatch"),
    bad("weighted_mean", {"values": [1, 2], "weights": [1, -1]}, "weights", "negative"),
    bad("weighted_mean", {"values": [1, 2], "weights": [0, 0]}, "weights", "zero-total"),
    bad("pearson_correlation", {"x": [1, 2, 3], "y": [1, 2]}, "y", "length-mismatch"),
    bad("pearson_correlation", {"x": [4, 4, 4], "y": [1, 2, 3]}, "x", "constant-x"),
    bad("pearson_correlation", {"x": [1, 2, 3], "y": [5, 5, 5]}, "y", "constant-y"),
    bad("pearson_correlation", {"x": [4, 4, 4], "y": [5, 5, 5]}, "x", "both-constant-x-first"),
    bad("spearman_rank_correlation", {"x": [1, 2, 3], "y": [9, 9, 9]}, "y", "constant-y-ranks"),
    bad("spearman_rank_correlation", {"x": [1, 2, 3], "y": [1, 2, 3, 4]}, "y", "length-mismatch"),
    bad("linear_regression_fit", {"x": [2, 2, 2], "y": [1, 2, 3]}, "x", "constant-x"),
    bad("linear_regression_fit", {"x": [1, 2], "y": [1, 2, 3]}, "y", "length-mismatch"),
    bad("moving_average", {"values": [1, 2, 3], "window": 4}, "window", "window-over-length"),
    invalid("moving_average", {"values": [1, 2, 3], "window": 0}, "window", "window-zero"),
    invalid("moving_average", {"values": [1, 2, 3], "window": 1001}, "window", "window-over-cap"),
    invalid("detect_outliers_iqr", {"values": [1, 2, 3], "multiplier": 0}, "multiplier", "zero-multiplier"),
    invalid("detect_outliers_iqr", {"values": [1, 2, 3], "multiplier": 10.5}, "multiplier", "multiplier-over-cap"),
    invalid("rank_values", {"values": [1, 2], "method": "random"}, "method", "unknown-method"),
    # A.5
    bad("count_permutations", {"n": 10, "k": 4000, "with_repetition": True}, "n", "ten-to-4000-INV-18"),
    bad("count_permutations", {"n": 10000, "k": 10000}, "n", "huge-AC-15"),
    invalid("count_combinations", {"n": 10001, "k": 1}, "n", "n-over-cap"),
    bad("exact_factorial", {"n": 1464}, "n", "first-too-large-AC-15"),
    bad("exact_factorial", {"n": 10000}, "n", "largest-n-AC-15"),
    invalid("exact_factorial", {"n": -1}, "n", "negative"),
    bad("binomial_probability", {"trials": 3, "successes": 4, "probability": 0.5}, "successes", "successes-over-trials"),
    invalid("binomial_probability", {"trials": 3, "successes": 1, "probability": 1.5}, "probability", "probability-over-one"),
    invalid("poisson_probability", {"rate": 0, "occurrences": 1}, "rate", "rate-zero-exclusive"),
    bad("normal_distribution_probability", {"lower": None, "upper": None}, "lower", "both-bounds-null"),
    bad("normal_distribution_probability", {"lower": 2, "upper": 1}, "upper", "lower-above-upper"),
    invalid("normal_distribution_probability", {"lower": 0, "upper": 1, "standard_deviation": 0}, "standard_deviation", "zero-deviation"),
    invalid("normal_quantile", {"probability": 0}, "probability", "probability-zero"),
    invalid("normal_quantile", {"probability": 1}, "probability", "probability-one"),
    invalid("birthday_collision_probability", {"items": 2, "possible_values": 0}, "possible_values", "no-values"),
    invalid("list_combinations", {"items": TWENTY_ITEMS + ["extra"], "size": 2}, "items", "21-items"),
    invalid("list_combinations", {"items": ["a" * 201], "size": 1}, "items", "item-over-name-cap"),
    # A.6
    bad("seeded_random_integers", {"seed": 1, "count": 5, "minimum": 1, "maximum": 4, "unique": True}, "count", "unique-range-too-small"),
    bad("seeded_random_integers", {"seed": 1, "count": 2, "minimum": 5, "maximum": 4}, "maximum", "minimum-over-maximum"),
    invalid("seeded_random_integers", {"seed": -1, "count": 2, "minimum": 1, "maximum": 4}, "seed", "negative-seed"),
    invalid("seeded_random_integers", {"seed": 1, "count": 1001, "minimum": 1, "maximum": 4}, "count", "count-over-cap"),
    bad("seeded_sample_list", {"items": ["a", "b"], "size": 3, "seed": 1}, "size", "size-over-length"),
    bad("seeded_weighted_choice", {"items": ["a", "b"], "weights": [1], "seed": 1}, "weights", "length-mismatch"),
    bad("seeded_weighted_choice", {"items": ["a", "b"], "weights": [1, -1], "seed": 1}, "weights", "negative"),
    bad("seeded_weighted_choice", {"items": ["a", "b"], "weights": [0, 0], "seed": 1}, "weights", "zero-total"),
    bad("roll_dice_notation", {"notation": "0d6", "seed": 1}, "notation", "zero-dice"),
    bad("roll_dice_notation", {"notation": "1001d6", "seed": 1}, "notation", "too-many-dice"),
    bad("roll_dice_notation", {"notation": "2d1", "seed": 1}, "notation", "one-sided-die"),
    bad("roll_dice_notation", {"notation": "2d1001", "seed": 1}, "notation", "too-many-sides"),
    bad("roll_dice_notation", {"notation": "2d6+1000001", "seed": 1}, "notation", "modifier-over-cap"),
    bad("roll_dice_notation", {"notation": "two dice", "seed": 1}, "notation", "not-notation"),
    invalid("roll_dice_notation", {"notation": "", "seed": 1}, "notation", "empty"),
    invalid("generate_seeded_uuid4", {"seed": 1, "count": 0}, "count", "count-zero"),
]

# One fixed call per seeded tool, large enough that a draw that ignored the seed would show.
SEEDED_CALLS = [
    ("seeded_random_integers", {"seed": 20240229, "count": 40, "minimum": -1000, "maximum": 1000}),
    ("seeded_random_integers", {"seed": 20240229, "count": 40, "minimum": -1000, "maximum": 1000, "unique": True}),
    ("seeded_shuffle_list", {"items": TWENTY_ITEMS, "seed": 20240229}),
    ("seeded_sample_list", {"items": TWENTY_ITEMS, "size": 7, "seed": 20240229}),
    ("seeded_weighted_choice", {"items": ["a", "b", "c"], "weights": [1, 2, 3.5], "seed": 20240229, "picks": 40}),
    ("roll_dice_notation", {"notation": "12d20+4", "seed": 20240229}),
    ("generate_seeded_uuid4", {"seed": 20240229, "count": 4}),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_statistics_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_statistics_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


@pytest.mark.parametrize(("tool", "arguments"), SEEDED_CALLS, ids=[f"{tool}-{index}" for index, (tool, _) in enumerate(SEEDED_CALLS)])
def test_seeded_tools_repeat_for_the_same_seed(tool_runner: ToolRunner, tool: str, arguments: dict[str, Any]) -> None:
    first = tool_runner.result(tool, arguments)
    second = tool_runner.result(tool, arguments)
    assert first.output == second.output
    tool_runner.output(tool, arguments)


def expected_seeded_output(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Replay the generator calls the A.6 row documents, in this interpreter, so no draw is pinned across versions."""
    rng = random.Random(arguments["seed"])
    if tool == "seeded_random_integers" and arguments.get("unique"):
        return {"values": rng.sample(range(arguments["minimum"], arguments["maximum"] + 1), arguments["count"])}
    if tool == "seeded_random_integers":
        return {"values": [rng.randint(arguments["minimum"], arguments["maximum"]) for _ in range(arguments["count"])]}
    if tool == "seeded_shuffle_list":
        items = list(arguments["items"])
        rng.shuffle(items)
        return {"items": items}
    if tool == "seeded_sample_list":
        indices = rng.sample(range(len(arguments["items"])), arguments["size"])
        return {"items": [arguments["items"][index] for index in indices], "indices": indices}
    if tool == "seeded_weighted_choice":
        weights = [float(weight) for weight in arguments["weights"]]
        return {"picks": rng.choices(arguments["items"], weights=weights, k=arguments.get("picks", 1))}
    if tool == "roll_dice_notation":
        rolls = [rng.randint(1, 20) for _ in range(12)]
        return {"rolls": rolls, "modifier": 4, "total": sum(rolls) + 4}
    return {"uuids": [str(uuid.UUID(int=rng.getrandbits(128), version=4)) for _ in range(arguments["count"])]}


@pytest.mark.parametrize(("tool", "arguments"), SEEDED_CALLS, ids=[f"{tool}-{index}" for index, (tool, _) in enumerate(SEEDED_CALLS)])
def test_seeded_tools_follow_the_documented_generator_calls(tool_runner: ToolRunner, tool: str, arguments: dict[str, Any]) -> None:
    output = tool_runner.output(tool, arguments)
    assert output == expected_seeded_output(tool, arguments)
    if tool == "generate_seeded_uuid4":
        assert all(UUID4_PATTERN.match(value) for value in output["uuids"]), output
    if tool == "seeded_random_integers":
        assert all(-1000 <= value <= 1000 for value in output["values"])
        assert len(output["values"]) == 40
    if tool == "seeded_shuffle_list":
        assert sorted(output["items"]) == sorted(TWENTY_ITEMS)


@pytest.mark.parametrize(("tool", "arguments"), SEEDED_CALLS, ids=[f"{tool}-{index}" for index, (tool, _) in enumerate(SEEDED_CALLS)])
def test_seeded_tools_change_with_the_seed(tool_runner: ToolRunner, tool: str, arguments: dict[str, Any]) -> None:
    other = {**arguments, "seed": arguments["seed"] + 1}
    assert tool_runner.output(tool, arguments) != tool_runner.output(tool, other)


def test_seeded_tools_leave_the_global_random_state_alone(tool_runner: ToolRunner) -> None:
    state = random.getstate()
    for tool, arguments in SEEDED_CALLS:
        tool_runner.output(tool, arguments)
    assert random.getstate() == state
