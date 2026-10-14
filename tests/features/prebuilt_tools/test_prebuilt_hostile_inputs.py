"""FILE: tests/features/prebuilt_tools/test_prebuilt_hostile_inputs.py

PURPOSE: Regression cases for the review findings that only hostile input or a hostile host exposes: cap-sized inputs on which a tool ran for minutes or hours (S4 R-1, R-2, R-6 to R-9, closing R-14; re-review R-15 and R-17, the TOML dotted-key scan), and a host decimal context that leaked into tool arithmetic or a far exponent (S4 R-12; re-review R-16).
ROLE IN CODEBASE: Runs each cap-sized call through FunctionTool.execute in a child interpreter under a liveness watchdog, and runs the decimal-context cases in this process through the ToolRunner fixture of tests/features/prebuilt_tools/conftest.py.
ARCHITECTURE NOTE: The watchdog is the orchestrator's one exception to the pack's no-wall-clock rule, granted for these hostile cases only. It asserts no speed: a call gets WATCHDOG_SECONDS (about 15 times NFR-7's 2 s), and a child that outlives it is killed, so a hang becomes a red test and leaves no work running. Every case still asserts the exact output or error its spec r6 or r7 row defines.
FUNCTION INVENTORY: WatchdogToolRunner runs one call in a child interpreter and turns the reply into a ToolResult; child_environment builds the child's environment; comma_chain_entries and nested_keys build two long expectations; HOSTILE_SUCCESS_CASES and HOSTILE_FAILURE_CASES hold the cap-sized inputs checked by test_hostile_input_returns_documented_output and test_hostile_input_fails_with_documented_error; DECIMAL_CONTEXT_CASES are checked by test_hostile_host_decimal_context_cannot_change_a_result; host_decimal_context sets one host context per test for FAR_EXPONENT_SUCCESS_CASES and FAR_EXPONENT_FAILURE_CASES, checked by test_far_exponent_data_size_is_zero_under_any_host_context and test_far_exponent_data_size_refusal_holds_under_any_host_context.
COMMON MODIFICATION PATTERNS: Size a new hostile input so the fixed tool finishes far under one second and a regressed one runs far past the watchdog, keep its expected value exact, and start its label with the review ID.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert a duration or lower WATCHDOG_SECONDS; the watchdog only turns a hang into a failure. 2. Do not run a cap-sized hostile call in the test process, where a regression would hang the whole run.
KNOWN EDGE CASES: The child reads its request from stdin, because a 1,000,000-character argument does not fit on a Windows command line. FunctionTool runs a tool through asyncio.to_thread, which copies the caller's context variables, so the hostile decimal context is set in the test's own thread before asyncio.run and restored in finally. PREBUILT_MAX_XML_PATH_VISITS counts ElementPath reads, whose number depends on stdlib internals, so the XML inputs sit far past or far under its 2,000,000. R-15's slow input repeats the pair (backslash + quote) * k; a backslash followed by k quotes scans in linear time and proves nothing.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/review.md (R-1 to R-17); docs/spec/prebuilt-agent-tools/spec.md (§9.2 item 18, EC-47 to EC-51, D-19, §13); docs/spec/prebuilt-agent-tools/test-plan.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_hostile_inputs.py
"""

from __future__ import annotations

import decimal
import json
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_catalogue_data import CATEGORY_TABLE
from tests.features.prebuilt_tools.prebuilt_tool_harness import FailureCase, SuccessCase, ToolRunner, bad, ok
from tests.features.prebuilt_tools.test_prebuilt_rows_formats_encoding import JWT_SAMPLE, JWT_SAMPLE_OUTPUT, TOML_INVALID_MESSAGE, TOML_NESTING_MESSAGE
from tests.features.prebuilt_tools.test_prebuilt_rows_geometry_bits_markdown import FAR_EXPONENT_REFUSED_SIZES, FAR_EXPONENT_ZERO_SIZES, ZERO_DATA_SIZE
from vidbyte.tools.types import ToolResult, ToolStatus

WATCHDOG_SECONDS = 30
WORKTREE = Path(__file__).resolve().parents[3]
TOOL_CATEGORIES = {name: value for value, _, names in CATEGORY_TABLE for name in names}

# The child builds only the tool's own category and prints one JSON reply, so the parent can rebuild the ToolResult.
CHILD_PROGRAM = """
import asyncio
import json
import sys

from vidbyte.lib.enums import PrebuiltToolCategory
from vidbyte.tools.toolsets import PrebuiltTools
from vidbyte.tools.types import ToolCall

request = json.loads(sys.stdin.read())
tool = next(tool for tool in PrebuiltTools([PrebuiltToolCategory(request["category"])]) if tool.name == request["tool"])
result = asyncio.run(tool.execute(ToolCall(request["tool"], request["arguments"])))
sys.stdout.write(json.dumps({"status": result.status.value, "output": result.output, "error_type": result.metadata.get("error_type")}))
"""


def child_environment() -> dict[str, str]:
    """This environment with the worktree first on PYTHONPATH and UTF-8 pipes."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(part for part in (str(WORKTREE), environment.get("PYTHONPATH", "")) if part)
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


class WatchdogToolRunner(ToolRunner):
    """A ToolRunner whose calls run in a child interpreter that is killed when it outlives the liveness watchdog."""

    def __init__(self) -> None:
        super().__init__(())

    def result(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        """Run one call in a fresh interpreter; a call still running after WATCHDOG_SECONDS fails the test as hung."""
        request = json.dumps({"category": TOOL_CATEGORIES[name], "tool": name, "arguments": dict(arguments)})
        try:
            completed = subprocess.run(
                [sys.executable, "-c", CHILD_PROGRAM],
                input=request,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=child_environment(),
                timeout=WATCHDOG_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(f"{name} gave no result within the {WATCHDOG_SECONDS} s liveness watchdog, so it is treated as hung (S4 R-14); the child was stopped")
        assert completed.returncode == 0, f"the child running {name} failed: {completed.stderr[-2000:]}"
        reply = json.loads(completed.stdout)
        metadata = {"error_type": reply["error_type"]} if reply["error_type"] is not None else {}
        return ToolResult(name, ToolStatus(reply["status"]), reply["output"], metadata)


WATCHDOG_RUNNER = WatchdogToolRunner()

HEADING_SPACES = 450_000
COMMA_GROUPS = 249_999
DOTTED_SEGMENTS = 499_998
CHAIN_OF_60 = "<a>" * 60 + "</a>" * 60
SIBLINGS = "<r>" + "<b/>" * 249_998 + "</r>"
PATCH_DOCUMENT = '{"a":[' + ",".join(["0"] * 100_000) + "]}"
ESCAPED_QUOTE = chr(92) + '"'
DOTTED_RUN = "a." * 499_990 + "a"
INLINE_TABLE_KEY = "a." * 499_900 + "a = 1"
PATCH_COPY_AND_REMOVE = json.dumps([{"op": "copy", "from": "/a", "path": "/b"}, {"op": "remove", "path": "/b"}] * 500)


def comma_chain_entries() -> list[dict[str, Any]]:
    """The first 1,000 extract_numbers entries of "1" followed by ",000" groups: 1, then 000 at every fourth index."""
    first = {"text": "1", "value": "1", "position": 0, "is_percent": False}
    return [first] + [{"text": "000", "value": "0", "position": 2 + 4 * index, "is_percent": False} for index in range(999)]


def nested_keys(levels: int) -> Any:
    """The JSON value of a TOML key with `levels` dotted segments named a, holding the integer 1."""
    value: Any = 1
    for _ in range(levels):
        value = {"a": value}
    return value


HOSTILE_SUCCESS_CASES = [
    # R-1 (A.28): a long run of spaces before "#x" made the closing-hash pattern quadratic; the heading keeps them.
    ok(
        "extract_markdown_headings",
        {"markdown": "# a" + " " * HEADING_SPACES + "#x"},
        {"headings": [{"level": 1, "text": "a" + " " * HEADING_SPACES + "#x", "line": 1, "anchor": "a" + "-" * HEADING_SPACES + "x"}], "count": 1},
        "r1-space-run-before-hash-text",
    ),
    # R-2 (A.29 preamble): a comma chain that fails at its end restarted at every comma.
    ok(
        "extract_numbers",
        {"text": "1" + ",000" * COMMA_GROUPS + "0"},
        {"numbers": comma_chain_entries(), "count": COMMA_GROUPS + 1, "truncated": True},
        "r2-comma-chain-ending-in-a-digit",
    ),
    ok("extract_money_amounts", {"text": "1" + ",000" * COMMA_GROUPS}, {"amounts": [], "count": 0, "truncated": False}, "r2-comma-chain-without-currency"),
    # R-6 (A.20): the dotted-key scan must not refuse a key of exactly 100 segments.
    ok("toml_to_json", {"toml_text": "a" + ".a" * 99 + "=1"}, {"value": nested_keys(100)}, "r6-exactly-100-segments-still-accepted"),
    # R-7 (A.20, EC-48): 249,998 sibling matches stay far under the visit cap and are counted in full.
    ok(
        "xml_find_elements",
        {"xml_text": SIBLINGS, "path": ".//b"},
        {"elements": [{"tag": "b", "attributes": {}, "text": None}] * 1000, "count": 249_998, "truncated": True},
        "r7-many-siblings-counted-in-full",
    ),
    # R-8 (A.13, A.28, EC-47): markup left open to the end of a cap-sized input made close() re-scan it for every "<".
    ok("strip_html_tags", {"html_text": "x" + "<a " * 333_333}, {"text": "x"}, "r8-open-tags-to-the-cap"),
    ok(
        "extract_html_links",
        {"html_text": '<a href="u">t</a>' + "<a " * 333_327},
        {"links": [{"url": "u", "text": "t", "rel": None}], "count": 1, "truncated": False},
        "r8-open-tags-to-the-cap",
    ),
    ok(
        "html_table_to_records",
        {"html_text": "<table><tr><td>a</td></tr></table>" + "<a " * 333_321},
        {"columns": ["column_1"], "records": [{"column_1": "a"}], "table_count": 1},
        "r8-open-tags-to-the-cap",
    ),
    # S5 R-15 (A.20, EC-51): a one-line quoted segment left open ends at its line end, so a comment of escaped quotes is read once.
    ok("toml_to_json", {"toml_text": "# " + '"' + ESCAPED_QUOTE * 499_995 + "\na = 1"}, {"value": {"a": 1}}, "r15-escaped-quotes-in-comment"),
    # S5 R-17 (A.20, D-19): comments and multi-line strings are skipped whole, so a cap-sized run inside one is parsed.
    ok("toml_to_json", {"toml_text": "# " + DOTTED_RUN + "\nb = 1"}, {"value": {"b": 1}}, "r17-dotted-run-in-comment"),
    ok("toml_to_json", {"toml_text": 's = """' + DOTTED_RUN + '"""'}, {"value": {"s": DOTTED_RUN}}, "r17-dotted-run-in-multi-line-string"),
]

HOSTILE_FAILURE_CASES = [
    # R-6 (A.20): tomllib is quadratic in the segments of one dotted key, in all three key forms.
    bad("toml_to_json", {"toml_text": "a" + ".a" * DOTTED_SEGMENTS + "=1"}, "toml_text", "r6-dotted-bare-key"),
    bad("toml_to_json", {"toml_text": "[a" + ".a" * DOTTED_SEGMENTS + "]"}, "toml_text", "r6-dotted-table-header"),
    bad("toml_to_json", {"toml_text": "x={a" + ".a" * (DOTTED_SEGMENTS - 2) + "=1}"}, "toml_text", "r6-dotted-inline-table-key"),
    # R-7 (A.20, EC-48): the descendant step repeats elements, and a positional predicate compares every sibling.
    bad("xml_find_elements", {"xml_text": CHAIN_OF_60, "path": "." + "//a" * 6}, "path", "r7-six-descendant-steps"),
    bad("xml_find_elements", {"xml_text": CHAIN_OF_60, "path": "." + "//a" * 5 + "//zzz"}, "path", "r7-five-steps-matching-nothing"),
    bad("xml_find_elements", {"xml_text": SIBLINGS, "path": "b[1]"}, "path", "r7-positional-predicate-over-siblings"),
    # R-9 (A.17, EC-49): each operation reads 200,001 characters, so the work total passes 10,000,000 at index 49.
    bad("apply_json_patch", {"json_text": PATCH_DOCUMENT, "patch_json": PATCH_COPY_AND_REMOVE}, "patch_json", "r9-work-total-at-operation-49", contains="operation 49"),
    # S5 R-15 (A.20, EC-51): an open basic string of escaped quotes is invalid TOML, and runs of multi-line openers are read once.
    bad("toml_to_json", {"toml_text": "x = " + '"' + ESCAPED_QUOTE * 499_990}, "toml_text", "r15-open-string-of-escaped-quotes", contains=TOML_INVALID_MESSAGE),
    bad("toml_to_json", {"toml_text": '"""' * 333_333}, "toml_text", "r15-multi-line-basic-openers", contains=TOML_INVALID_MESSAGE),
    bad("toml_to_json", {"toml_text": "'''" * 333_333}, "toml_text", "r15-multi-line-literal-openers", contains=TOML_INVALID_MESSAGE),
    # S5 R-17 (A.20, EC-51): a multi-line string holding an odd number of quotes must not hide the long inline-table key after it.
    bad(
        "toml_to_json",
        {"toml_text": "t = { s = '''it's''', " + INLINE_TABLE_KEY + ", u = 'v' }"},
        "toml_text",
        "r17-key-after-literal-string-and-quote",
        contains=TOML_NESTING_MESSAGE,
    ),
    bad("toml_to_json", {"toml_text": "t = { s = '''it's''', " + INLINE_TABLE_KEY + " }"}, "toml_text", "r17-key-after-literal-string", contains=TOML_NESTING_MESSAGE),
    bad(
        "toml_to_json",
        {"toml_text": 't = { s = """a"b""", ' + INLINE_TABLE_KEY + ', u = "v" }'},
        "toml_text",
        "r17-key-after-basic-string-and-quote",
        contains=TOML_NESTING_MESSAGE,
    ),
]


@pytest.mark.parametrize("case", HOSTILE_SUCCESS_CASES)
def test_hostile_input_returns_documented_output(case: SuccessCase) -> None:
    """R-1, R-2, R-6, R-7, R-8, R-15, R-17 (closing R-14): a cap-sized hostile input returns its exact r6 or r7 output within the watchdog."""
    WATCHDOG_RUNNER.check_success(case)


@pytest.mark.parametrize("case", HOSTILE_FAILURE_CASES)
def test_hostile_input_fails_with_documented_error(case: FailureCase) -> None:
    """R-6, R-7, R-9, R-15, R-17 (closing R-14): a cap-sized hostile input fails with its r6 or r7 error, naming its parameter, within the watchdog."""
    WATCHDOG_RUNNER.check_failure(case)


# A host that traps Inexact and Rounded and lowers Emax; spec §9.2 item 18 says no tool result may depend on it.
HOSTILE_HOST_CONTEXT = decimal.Context(Emax=5, traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow, decimal.Inexact, decimal.Rounded])

DECIMAL_CONTEXT_CASES = [
    ok("compound_interest_future_value", {"principal": 1000, "annual_rate_percent": 5, "years": 10}, {"future_value": "1647.01", "interest_earned": "647.01"}, "r12-growth"),
    ok(
        "decimal_degrees_to_dms",
        {"decimal_degrees": 0.000875, "axis": "latitude", "seconds_decimal_places": 1},
        {"dms": "0°0′3.2″N", "degrees": 0, "minutes": 0, "seconds": 3.2, "hemisphere": "N"},
        "r12-arc-seconds",
    ),
    ok(
        "unix_timestamp_to_datetime",
        {"timestamp": 1.5},
        {"datetime": "1970-01-01T00:00:01.500000+00:00", "date": "1970-01-01", "time": "00:00:01.500000", "weekday": "thursday"},
        "r12-scaled-microseconds",
    ),
    ok("parse_duration_text", {"text": "1h 30m"}, {"total_seconds": 5400.0, "iso8601": "PT1H30M"}, "r12-unit-phrase"),
    ok("parse_duration_text", {"text": "P1DT0.5S"}, {"total_seconds": 86400.5, "iso8601": "P1DT0.5S"}, "r12-iso-fraction"),
    ok("parse_duration_text", {"text": "1:02:03.5"}, {"total_seconds": 3723.5, "iso8601": "PT1H2M3.5S"}, "r12-clock-fraction"),
    ok("decode_jwt_payload", {"jwt_text": JWT_SAMPLE}, JWT_SAMPLE_OUTPUT, "r12-claim-times"),
    ok(
        "extract_money_amounts",
        {"text": "$1.5 million"},
        {"amounts": [{"text": "$1.5 million", "currency": "$", "value": "1500000", "position": 0}], "count": 1, "truncated": False},
        "r12-magnitude-suffix",
    ),
]


@pytest.mark.parametrize("case", DECIMAL_CONTEXT_CASES)
def test_hostile_host_decimal_context_cannot_change_a_result(tool_runner: ToolRunner, case: SuccessCase) -> None:
    """R-12 and §9.2 item 18: with the host's decimal context trapping Inexact and Rounded at Emax 5, results are unchanged."""
    # The worker thread copies this thread's context variables, so the hostile context set here reaches the tool.
    host_context = decimal.getcontext()
    decimal.setcontext(HOSTILE_HOST_CONTEXT.copy())
    try:
        tool_runner.check_success(case)
    finally:
        decimal.setcontext(host_context)


# S5 R-16 (A.27, §9.2 item 18): an exponent past decimal.MAX_EMAX gives the same result whatever the host's decimal context traps.
FAR_EXPONENT_SUCCESS_CASES = [ok("parse_data_size", {"text": text}, ZERO_DATA_SIZE, f"r16-{label}") for text, label in FAR_EXPONENT_ZERO_SIZES]
FAR_EXPONENT_FAILURE_CASES = [bad("parse_data_size", {"text": text}, "text", f"r16-{label}") for text, label in FAR_EXPONENT_REFUSED_SIZES]


@pytest.fixture(params=[decimal.Context(traps=[]), HOSTILE_HOST_CONTEXT], ids=["host-traps-nothing", "host-hostile"])
def host_decimal_context(request: pytest.FixtureRequest) -> Iterator[None]:
    """Give the test's thread one host decimal context for the whole test, then restore the caller's context."""
    caller_context = decimal.getcontext()
    decimal.setcontext(request.param.copy())
    try:
        yield
    finally:
        decimal.setcontext(caller_context)


@pytest.mark.usefixtures("host_decimal_context")
@pytest.mark.parametrize("case", FAR_EXPONENT_SUCCESS_CASES)
def test_far_exponent_data_size_is_zero_under_any_host_context(tool_runner: ToolRunner, case: SuccessCase) -> None:
    """R-16: a tiny positive or zero size with a far exponent is 0 bytes whether the host traps nothing or everything R-12 traps."""
    tool_runner.check_success(case)


@pytest.mark.usefixtures("host_decimal_context")
@pytest.mark.parametrize("case", FAR_EXPONENT_FAILURE_CASES)
def test_far_exponent_data_size_refusal_holds_under_any_host_context(tool_runner: ToolRunner, case: FailureCase) -> None:
    """R-16: a huge or negative size with a far exponent is error(text) under either host context, never InvalidOperation or ValueError."""
    tool_runner.check_failure(case)
