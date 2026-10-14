"""FILE: tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py

PURPOSE: Resource bounds of the prebuilt tools: enumerating outputs stop at the item cap or the character budget and still count every item (AC-14, INV-17), huge integers fail cleanly (AC-15, INV-18), amplifying tools refuse output over PREBUILT_MAX_TEXT_CHARS without building it (AC-20, INV-20), and deep nesting fails or is skipped without execute raising (AC-21, INV-19).
ROLE IN CODEBASE: Calls the vidbyte.tools.toolsets.PrebuiltTools library through FunctionTool.execute with small inputs that amplify, the way a hostile or careless model call would.
ARCHITECTURE NOTE: No assertion uses the wall clock. "Without first building the oversized result" is checked with tracemalloc's peak for the tools whose whole output would be tens of megabytes, and the infeasible-if-enumerated counts (2^128 subnets, 10^15 integers) can only finish if the tool computes totals arithmetically.
FUNCTION INVENTORY: Case tables INTEGER_LIMIT_CASES, AMPLIFICATION_CASES, NESTING_CASES; peak_allocation runs one call under tracemalloc; tests for regex item cap, regex character budget, divisors, subnets, integer ranges, combinations, the integer digit limit, every INV-20 tool, peak memory of predicted outputs, deep nesting, and the EC-39 scan cap.
COMMON MODIFICATION PATTERNS: Add an INV-20 tool to AMPLIFICATION_CASES with the parameter its row names; add a memory check only when the full output would be at least four times PEAK_ALLOWANCE_BYTES.
WHAT NOT TO DO IN THIS FILE: 1. Do not add timing assertions; AC-15's 1 second and AC-20's 2 seconds are deliberately not asserted (see test-plan.md). 2. Do not shrink the inputs below the cap they are built to cross.
KNOWN EDGE CASES: A tool that enumerates instead of computing a total would hang on the count cases rather than fail; that is the documented price of proving arithmetic counting. Big expected integers are built from digit strings, never with str(int) above 4,300 digits.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (INV-17 to INV-20, AC-14, AC-15, AC-20, AC-21, EC-8, EC-12, EC-13, EC-39, EC-41 to EC-43)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py
"""

from __future__ import annotations

import itertools
import json
import tracemalloc
from math import isqrt
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import FailureCase, ToolRunner, bad, describe_result, parse_tool_output
from vidbyte.tools.types import ToolStatus

MAX_TEXT_CHARS = 1_000_000
PEAK_ALLOWANCE_BYTES = 5_000_000
HIGHLY_DIVISIBLE = 963_761_198_400  # 2^6 * 3^4 * 5^2 * 7 * 11 * 13 * 17 * 19 * 23: 6,720 divisors.
TEN_TO_2000_PLUS_ONE = "1" + "0" * 1999 + "1"
TEN_TO_2000_PLUS_THREE = "1" + "0" * 1999 + "3"


def csv_with_wide_empty_rows(rows: int) -> str:
    """A 500-column header and rows of 500 empty cells; small to send, about ten times larger as records."""
    header = ",".join(f"c{index}" for index in range(500))
    return header + "\n" + ("," * 499 + "\n") * rows


def markdown_table_with_short_rows() -> str:
    """A 300-column Markdown table whose 1,000 one-cell rows are padded to 300 cells each."""
    header = "| " + " | ".join(f"c{index}" for index in range(300)) + " |\n"
    delimiter = "|" + "---|" * 300 + "\n"
    return header + delimiter + "| x |\n" * 1000


INTEGER_LIMIT_CASES = [
    bad("exact_factorial", {"n": 10_000}, "n", "largest-n"),
    bad("count_permutations", {"n": 10_000, "k": 10_000}, "n", "ten-thousand-factorial"),
    bad("count_permutations", {"n": 10, "k": 4000, "with_repetition": True}, "n", "exactly-ten-to-4000"),
    bad("least_common_multiple", {"values": [TEN_TO_2000_PLUS_ONE, TEN_TO_2000_PLUS_THREE]}, "values", "coprime-2001-digit-values"),
]

AMPLIFICATION_CASES = [
    bad("replace_all_occurrences", {"text": "a" * 100_000, "find": "a", "replacement": "b" * 200}, "replacement", "ec13-twenty-million"),
    bad("regex_replace", {"pattern": "a", "replacement": "b" * 200, "text": "a" * 100_000}, "replacement", "twenty-million"),
    bad("fill_text_template", {"template": "{{x}}" * 20_000, "values_json": json.dumps({"x": "y" * 1000})}, "values_json", "twenty-million"),
    bad("regex_match", {"pattern": "(?=(a*))" * 11 + "a*", "text": "a" * 100_000}, "pattern", "eleven-whole-text-groups"),
    bad("format_json", {"json_text": "[" * 50 + ",".join(["0"] * 100_000) + "]" * 50, "indent": 8}, "indent", "ec43-deep-indent"),
    bad(
        "apply_json_patch",
        {"json_text": json.dumps({"a": "x" * 100}), "patch_json": json.dumps([{"op": "copy", "from": "", "path": f"/k{index}"} for index in range(16)])},
        "patch_json",
        "ec41-root-copy-chain",
    ),
    bad("records_to_csv", {"records_json": "[" + ",".join(["{}"] * 10_000) + "]", "columns": [f"c{index}" for index in range(500)]}, "records_json", "wide-empty-rows"),
    bad("csv_to_records", {"csv_text": csv_with_wide_empty_rows(1900), "delimiter": "comma"}, "csv_text", "ec43-header-repeated-per-record"),
    bad("csv_to_markdown_table", {"csv_text": csv_with_wide_empty_rows(1900), "delimiter": "comma"}, "csv_text", "wide-empty-rows"),
    bad(
        "xml_to_json",
        {"xml_text": '<r xmlns="urn:' + "u" * 190 + '">' + "".join(f"<e{index}/>" for index in range(100_000)) + "</r>"},
        "xml_text",
        "ec43-namespace-copied-into-names",
    ),
    bad("parse_markdown_table", {"markdown": markdown_table_with_short_rows()}, "markdown", "padded-rows"),
    bad("html_table_to_records", {"html_text": '<table><tr><td colspan="200000">x</td></tr></table>'}, "html_text", "ec43-huge-colspan"),
    bad("list_python_functions", {"source": "class " + "C" * 5000 + ":\n" + "    def f(self):\n        pass\n" * 2000}, "source", "long-qualified-names"),
    bad("list_python_classes", {"source": "class " + "A" * 5000 + ":\n" + "    class B:\n        pass\n" * 3000}, "source", "long-qualified-names"),
]

NESTING_CASES = [
    bad("xml_to_json", {"xml_text": "<a>" * 101 + "</a>" * 101}, "xml_text", "101-levels"),
    bad("xml_to_json", {"xml_text": "<a>" * 5000 + "</a>" * 5000}, "xml_text", "ec42-5000-levels"),
    bad("toml_to_json", {"toml_text": "a = " + "[" * 101 + "]" * 101}, "toml_text", "101-levels"),
    bad("toml_to_json", {"toml_text": "a = " + "[" * 5000 + "]" * 5000}, "toml_text", "5000-levels"),
    bad("python_literal_to_json", {"literal": "[" * 101 + "]" * 101}, "literal", "101-levels"),
    bad("python_literal_to_json", {"literal": "[" * 5000 + "]" * 5000}, "literal", "5000-levels"),
    bad("format_json", {"json_text": "[" * 100_000 + "]" * 100_000}, "json_text", "ec12-100000-levels"),
    bad("xml_to_json", {"xml_text": '<!DOCTYPE r [<!ENTITY a "aaaaaaaaaa">]><r>&a;&a;</r>'}, "xml_text", "ec11-entity"),
]

# The tools whose whole output would be at least 20 MB, so a peak far below that proves it was never built.
PREDICTED_OUTPUT_CASES = [case for case in AMPLIFICATION_CASES if case.id.split("-", 1)[0] in {"replace_all_occurrences", "regex_replace", "fill_text_template", "format_json"}]


def peak_allocation(tool_runner: ToolRunner, case: FailureCase) -> tuple[Any, int]:
    """Run one call under tracemalloc and return its result and the peak traced allocation during the call."""
    tool_runner.tool(case.tool)
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        baseline = tracemalloc.get_traced_memory()[0]
        result = tool_runner.result(case.tool, case.arguments)
        peak = tracemalloc.get_traced_memory()[1] - baseline
    finally:
        tracemalloc.stop()
    return result, peak


# ---- AC-14 and INV-17: item cap, character budget, and full counts ----


def test_regex_matches_stop_at_the_item_cap_and_count_every_match(tool_runner: ToolRunner) -> None:
    """AC-14: 5,000 matches return the first 1,000 in order, truncated is true, and count is 5,000."""
    output = tool_runner.output("regex_find_all", {"pattern": "a", "text": "a" * 5000})
    assert output["count"] == 5000 and output["truncated"] is True
    assert len(output["matches"]) == 1000
    assert output["matches"][0] == {"match": "a", "start": 0, "end": 1, "groups": [], "named_groups": {}}
    assert output["matches"][999] == {"match": "a", "start": 999, "end": 1000, "groups": [], "named_groups": {}}


def test_regex_matches_stop_at_the_character_budget(tool_runner: ToolRunner) -> None:
    """AC-14 and EC-43: lookahead groups that copy the rest of the text stop at 49 items, the last that fits in 1,000,000 compact characters."""
    output = tool_runner.output("regex_find_all", {"pattern": "(?=(a*))", "text": "a" * 20_000})
    assert output["count"] == 20_001 and output["truncated"] is True
    assert len(output["matches"]) == 49
    assert output["matches"][0] == {"match": "", "start": 0, "end": 0, "groups": ["a" * 20_000], "named_groups": {}}
    assert output["matches"][48]["start"] == 48 and output["matches"][48]["groups"] == ["a" * 19_952]
    kept = sum(len(json.dumps(item, separators=(",", ":"), ensure_ascii=False)) for item in output["matches"])
    assert kept <= MAX_TEXT_CHARS


def test_divisors_past_the_cap_still_count_and_sum(tool_runner: ToolRunner) -> None:
    """AC-14: a number with 6,720 divisors returns the 1,000 smallest, and count and sum cover all of them."""
    small_divisors = [value for value in range(1, isqrt(HIGHLY_DIVISIBLE) + 1) if HIGHLY_DIVISIBLE % value == 0]
    every_divisor = sorted(set(small_divisors) | {HIGHLY_DIVISIBLE // value for value in small_divisors})
    output = tool_runner.output("list_divisors", {"value": HIGHLY_DIVISIBLE})
    assert output == {"divisors": every_divisor[:1000], "count": 6720, "sum": 5_531_765_944_320, "truncated": True}
    assert sum(every_divisor) == 5_531_765_944_320 and len(every_divisor) == 6720


def test_subnet_count_is_arithmetic_for_two_to_the_128(tool_runner: ToolRunner) -> None:
    """AC-14: splitting ::/0 into /128 networks returns 1,000 in address order and counts 2^128 without enumerating."""
    output = tool_runner.output("split_cidr_into_subnets", {"cidr": "::/0", "new_prefix_length": 128})
    assert output["count"] == "340282366920938463463374607431768211456" and output["truncated"] is True
    assert output["subnets"] == ["::/128"] + [f"::{index:x}/128" for index in range(1, 1000)]


def test_integer_range_count_is_arithmetic_for_ten_to_the_15(tool_runner: ToolRunner) -> None:
    """AC-14: "1-1000000000000000" returns the first 10,000 integers and counts 10^15 without expanding them."""
    output = tool_runner.output("expand_integer_ranges", {"text": "1-1000000000000000"})
    assert output == {"values": list(range(1, 10_001)), "count": "1000000000000000", "truncated": True}


def test_combination_count_covers_every_combination(tool_runner: ToolRunner) -> None:
    """AC-14: 20 items taken 20 at a time with repetition return 1,000 combinations and count C(39, 20)."""
    items = [f"item{index:02d}" for index in range(20)]
    output = tool_runner.output("list_combinations", {"items": items, "size": 20, "with_repetition": True})
    expected = [list(combo) for combo in itertools.islice(itertools.combinations_with_replacement(items, 20), 1000)]
    assert output == {"combinations": expected, "count": 68_923_264_410, "truncated": True}


# ---- AC-15, AC-20, AC-21: refusals ----


@pytest.mark.parametrize("case", INTEGER_LIMIT_CASES)
def test_integers_of_4001_digits_fail_as_tool_errors(tool_runner: ToolRunner, case: FailureCase) -> None:
    """AC-15, INV-18, and EC-8: a result of 10^4000 or more is a ToolExecutionError naming the row's parameter, never ValueError."""
    tool_runner.check_failure(case)


@pytest.mark.parametrize("case", AMPLIFICATION_CASES)
def test_amplifying_tools_refuse_output_over_the_text_cap(tool_runner: ToolRunner, case: FailureCase) -> None:
    """AC-20 and INV-20: each INV-20 tool refuses an output over PREBUILT_MAX_TEXT_CHARS, naming the parameter its row names."""
    tool_runner.check_failure(case)


@pytest.mark.parametrize("case", PREDICTED_OUTPUT_CASES)
def test_refused_text_outputs_are_never_built(tool_runner: ToolRunner, case: FailureCase) -> None:
    """AC-20 and EC-13: a refused output of 20 million characters or more never exists in memory, so the call peaks far below it."""
    result, peak = peak_allocation(tool_runner, case)
    assert result.status is ToolStatus.ERROR and result.metadata.get("error_type") == "ToolExecutionError", describe_result(result)
    assert peak < PEAK_ALLOWANCE_BYTES, f"{case.tool} allocated {peak} bytes; the refused output was built first"


@pytest.mark.parametrize("case", NESTING_CASES)
def test_deep_nesting_fails_as_a_tool_error(tool_runner: ToolRunner, case: FailureCase) -> None:
    """AC-21, INV-19, EC-11, EC-12, and EC-42: deep or hostile structure is a ToolExecutionError, and execute never raises."""
    tool_runner.check_failure(case)


def test_json_scan_stops_after_1000_start_positions(tool_runner: ToolRunner) -> None:
    """EC-39 and INV-17: 100,000 "[" characters try at most 1,000 starts, find nothing, and report truncated."""
    result = tool_runner.result("extract_json_from_text", {"text": "[" * 100_000})
    assert result.status is ToolStatus.SUCCESS, describe_result(result)
    assert parse_tool_output(result.output) == {"documents": [], "count": 0, "truncated": True}


def test_too_deep_json_candidate_is_skipped_not_fatal(tool_runner: ToolRunner) -> None:
    """AC-21: a 101-level candidate is skipped, the 100-level document inside it is kept, and the scan goes on."""
    text = "[" * 101 + "]" * 101 + ' {"a": 1}'
    nested: Any = []
    for _ in range(99):
        nested = [nested]
    output = tool_runner.output("extract_json_from_text", {"text": text})
    assert output["count"] == 2 and output["truncated"] is False
    assert output["documents"][0] == {"start": 1, "end": 201, "value": nested}
    assert output["documents"][1] == {"start": 203, "end": 211, "value": {"a": 1}}
