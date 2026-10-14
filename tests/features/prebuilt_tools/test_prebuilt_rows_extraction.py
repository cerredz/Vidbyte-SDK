"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_extraction.py

PURPOSE: Exact-output and error-behavior cases for every Appendix A row of the text_extraction category (A.29), run through FunctionTool.execute the way a model calls them.
ROLE IN CODEBASE: One of the AC-11 row files in tests/features/prebuilt_tools/; it uses the tool_runner fixture from conftest.py and the ok and invalid case builders from prebuilt_tool_harness.py.
ARCHITECTURE NOTE: Every expected value is hand-derived from the row text and §9.2, with positions recomputed by str.find on the same text rather than read back from the implementation.
FUNCTION INVENTORY: test_extraction_rows_return_documented_output checks SUCCESS_CASES; test_extraction_rows_reject_bad_input checks FAILURE_CASES; counting_numbers builds the long extract_numbers expectation by arithmetic; number_entry builds one extract_numbers entry.
COMMON MODIFICATION PATTERNS: Add an ok(...) entry beside the tool's existing cases and recompute its positions with str.find before pinning them.
WHAT NOT TO DO IN THIS FILE: 1. Do not pin an output detail a row leaves open; use ANY instead (spec r4 fixed the last one here: a percent match's text includes the % sign). 2. Do not add character-budget or quadratic-scan inputs here; test_prebuilt_resource_bounds.py owns them.
KNOWN EDGE CASES: count keys beside unique-value lists count distinct values, not occurrences; a sign belongs to a number only after whitespace or an opening mark; "999.1.1.1" must not yield its tail "99.1.1.1". Spec r6 (S4 R-2) splits a malformed comma chain at its commas: "1,2,3" gives 1, 2, and 3, and "1,000,0000" gives 1, 000, and 0000; the cap-sized chains live in test_prebuilt_hostile_inputs.py.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.29 and §9.2 items 6, 9, 12, 15
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_extraction.py
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import FailureCase, SuccessCase, ToolRunner, invalid, ok


def counting_numbers(total: int) -> tuple[str, list[dict[str, Any]]]:
    """The text "0 1 2 ..." with `total` numbers, and the extract_numbers entry of each one."""
    words = [str(index) for index in range(total)]
    entries = []
    position = 0
    for word in words:
        entries.append({"text": word, "value": word, "position": position, "is_percent": False})
        position += len(word) + 1
    return " ".join(words), entries


def number_entry(text: str, value: str, position: int) -> dict[str, Any]:
    """One extract_numbers entry for a number written without a percent sign."""
    return {"text": text, "value": value, "position": position, "is_percent": False}


COUNTING_TEXT, COUNTING_ENTRIES = counting_numbers(1001)

URL_TEXT = "See https://example.com/a?b=1, and www.Test.org. (http://x.y/z) then https://example.com/a?b=1!"
SENTENCE_TEXT = "Dr. Smith arrived. Then J. Doe left... It works (really!) Next one. Wait\u2026 Done"
KEY_VALUE_TEXT = "name: Alice\r\nage = 30\n\nurl: http://x.y\nbad line\nx#y: 1\n: empty\nk.e/y-1 : v : w\na=b: c"

SUCCESS_CASES = [
    ok(
        "extract_urls",
        {"text": URL_TEXT},
        {
            "urls": [
                {"url": "https://example.com/a?b=1", "occurrences": 2, "first_position": 4},
                {"url": "www.Test.org", "occurrences": 1, "first_position": 35},
                {"url": "http://x.y/z", "occurrences": 1, "first_position": 50},
            ],
            "count": 3,
            "truncated": False,
        },
        "trailing-punctuation-and-repeats",
    ),
    ok(
        "extract_urls",
        {"text": "Wiki (http://en.wikipedia.org/wiki/Foo_(bar)) and HTTP://EXAMPLE.COM/\u00fc end"},
        {
            "urls": [
                {"url": "http://en.wikipedia.org/wiki/Foo_(bar)", "occurrences": 1, "first_position": 6},
                {"url": "HTTP://EXAMPLE.COM/", "occurrences": 1, "first_position": 50},
            ],
            "count": 2,
            "truncated": False,
        },
        "balanced-brackets-and-non-ascii-stop",
    ),
    ok("extract_urls", {"text": "broken http:// link"}, {"urls": [], "count": 0, "truncated": False}, "prefix-only-skipped"),
    ok(
        "extract_email_addresses",
        {"text": "Mail Alice@Example.com or bob.smith@mail.example.org and again alice@example.com today"},
        {
            "emails": [
                {"email": "Alice@Example.com", "occurrences": 2, "first_position": 5},
                {"email": "bob.smith@mail.example.org", "occurrences": 1, "first_position": 26},
            ],
            "count": 2,
            "truncated": False,
        },
        "casefold-unique-first-spelling",
    ),
    ok("extract_email_addresses", {"text": "no addresses here"}, {"emails": [], "count": 0, "truncated": False}, "none"),
    ok(
        "extract_numbers",
        {"text": "Paid 1,234.50 then -7 and x-3 or 2.5e-3 end"},
        {
            "numbers": [
                {"text": "1,234.50", "value": "1234.5", "position": 5, "is_percent": False},
                {"text": "-7", "value": "-7", "position": 19, "is_percent": False},
                {"text": "3", "value": "3", "position": 28, "is_percent": False},
                {"text": "2.5e-3", "value": "0.0025", "position": 33, "is_percent": False},
            ],
            "count": 4,
            "truncated": False,
        },
        "groups-signs-and-exponent",
    ),
    ok(
        "extract_numbers",
        {"text": "Done 45% so far"},
        {"numbers": [{"text": "45%", "value": "45", "position": 5, "is_percent": True}], "count": 1, "truncated": False},
        "percent-not-divided",
    ),
    ok(
        "extract_numbers",
        {"text": COUNTING_TEXT},
        {"numbers": COUNTING_ENTRIES[:1000], "count": 1001, "truncated": True},
        "item-cap-1000",
    ),
    # S4 R-2 (spec r6 A.29 preamble): a malformed comma chain splits at its commas, and list items stay separate.
    ok(
        "extract_numbers",
        {"text": "1,2,3"},
        {"numbers": [number_entry("1", "1", 0), number_entry("2", "2", 2), number_entry("3", "3", 4)], "count": 3, "truncated": False},
        "comma-list-keeps-every-item",
    ),
    ok(
        "extract_numbers",
        {"text": "1,000,0000"},
        {"numbers": [number_entry("1", "1", 0), number_entry("000", "0", 2), number_entry("0000", "0", 6)], "count": 3, "truncated": False},
        "group-followed-by-digit-splits",
    ),
    ok(
        "extract_dates",
        {"text": "Due 2024-03-15, moved to March 20, 2024 or 03/04/2025; not 2024-02-30, ref 20240315."},
        {
            "dates": [
                {"text": "2024-03-15", "date": "2024-03-15", "position": 4, "ambiguous": False},
                {"text": "March 20, 2024", "date": "2024-03-20", "position": 25, "ambiguous": False},
                {"text": "03/04/2025", "date": "2025-03-04", "position": 43, "ambiguous": True},
            ],
            "count": 3,
            "truncated": False,
        },
        "forms-impossible-and-compact-skipped",
    ),
    ok(
        "extract_dates",
        {"text": "On 03/04/2025 and 13/04/2025", "day_first": True},
        {
            "dates": [
                {"text": "03/04/2025", "date": "2025-04-03", "position": 3, "ambiguous": True},
                {"text": "13/04/2025", "date": "2025-04-13", "position": 18, "ambiguous": False},
            ],
            "count": 2,
            "truncated": False,
        },
        "day-first",
    ),
    ok(
        "extract_ip_addresses",
        {"text": "Hosts 192.168.1.1, 10.0.0.1 and 192.168.1.1 again; bad 999.1.1.1; v6 2001:DB8:0:0:0:0:0:1 and ::1 end"},
        {
            "addresses": [
                {"address": "192.168.1.1", "version": 4, "occurrences": 2, "first_position": 6},
                {"address": "10.0.0.1", "version": 4, "occurrences": 1, "first_position": 19},
                {"address": "2001:db8::1", "version": 6, "occurrences": 1, "first_position": 69},
                {"address": "::1", "version": 6, "occurrences": 1, "first_position": 94},
            ],
            "count": 4,
            "truncated": False,
        },
        "unique-compressed-and-invalid-skipped",
    ),
    ok(
        "extract_money_amounts",
        {"text": "Pay $1,234.56 or \u20ac5 today"},
        {
            "amounts": [
                {"text": "$1,234.56", "currency": "$", "value": "1234.56", "position": 4},
                {"text": "\u20ac5", "currency": "\u20ac", "value": "5", "position": 17},
            ],
            "count": 2,
            "truncated": False,
        },
        "symbols",
    ),
    ok(
        "extract_money_amounts",
        {"text": "Send 20 EUR and USD 3.5k now"},
        {
            "amounts": [
                {"text": "20 EUR", "currency": "EUR", "value": "20", "position": 5},
                {"text": "USD 3.5k", "currency": "USD", "value": "3500", "position": 16},
            ],
            "count": 2,
            "truncated": False,
        },
        "codes-and-suffix",
    ),
    ok(
        "extract_key_value_pairs",
        {"text": KEY_VALUE_TEXT},
        {
            "pairs": [
                {"key": "name", "value": "Alice", "line": 1},
                {"key": "age", "value": "30", "line": 2},
                {"key": "url", "value": "http://x.y", "line": 4},
                {"key": "k.e/y-1", "value": "v : w", "line": 8},
                {"key": "a", "value": "b: c", "line": 9},
            ],
            "count": 5,
            "truncated": False,
        },
        "auto-first-separator",
    ),
    ok(
        "extract_key_value_pairs",
        {"text": KEY_VALUE_TEXT, "separator": "colon"},
        {
            "pairs": [
                {"key": "name", "value": "Alice", "line": 1},
                {"key": "url", "value": "http://x.y", "line": 4},
                {"key": "k.e/y-1", "value": "v : w", "line": 8},
            ],
            "count": 3,
            "truncated": False,
        },
        "colon-only",
    ),
    ok(
        "extract_key_value_pairs",
        {"text": KEY_VALUE_TEXT, "separator": "equals"},
        {"pairs": [{"key": "age", "value": "30", "line": 2}, {"key": "a", "value": "b: c", "line": 9}], "count": 2, "truncated": False},
        "equals-only",
    ),
    ok(
        "extract_sentences",
        {"text": SENTENCE_TEXT},
        {
            "sentences": [
                {"index": 0, "text": "Dr. Smith arrived.", "start": 0},
                {"index": 1, "text": "Then J. Doe left...", "start": 19},
                {"index": 2, "text": "It works (really!)", "start": 39},
                {"index": 3, "text": "Next one.", "start": 58},
                {"index": 4, "text": "Wait\u2026", "start": 68},
                {"index": 5, "text": "Done", "start": 74},
            ],
            "count": 6,
            "truncated": False,
        },
        "abbreviations-initials-brackets",
    ),
    ok(
        "extract_sentences",
        {"text": SENTENCE_TEXT, "contains": "WORKS"},
        {"sentences": [{"index": 2, "text": "It works (really!)", "start": 39}], "count": 1, "truncated": False},
        "case-insensitive-filter",
    ),
]

FAILURE_CASES = [
    invalid("extract_key_value_pairs", {"text": "a: b", "separator": "dash"}, "separator", "unknown-separator"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_extraction_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_extraction_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)
