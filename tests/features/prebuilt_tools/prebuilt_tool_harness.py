"""FILE: tests/features/prebuilt_tools/prebuilt_tool_harness.py

PURPOSE: Shared helpers for the prebuilt tool feature pack: run a tool through FunctionTool.execute the way a model would, compare outputs with hand-computed expectations, build schema-valid argument sets, and count tool constructions.
ROLE IN CODEBASE: Imported by conftest.py and the test modules in tests/features/prebuilt_tools/; it calls the real seam (vidbyte.tools.types.ToolCall into FunctionTool.execute) and never imports the prebuilt package itself.
ARCHITECTURE NOTE: Nothing here mocks FunctionTool, pydantic, or the standard library. Every call runs asyncio.run(tool.execute(ToolCall(...))), exactly as spec §13 prescribes, so validation and the worker thread stay real.
FUNCTION INVENTORY: ok, bad, and invalid build parametrized cases; parse_tool_output parses success text and rejects NaN and Infinity; OutputMatcher lists differences between an expectation and an output; ToolRunner executes calls and checks cases; SchemaArgumentFactory builds deterministic argument sets from a tool's JSON input schema; ConstructionCounter counts FunctionTool and Tools constructions.
COMMON MODIFICATION PATTERNS: Add a sample to a SchemaArgumentFactory pool when a new input format appears; add a matcher marker only when a row states its own tolerance; keep every helper free of knowledge about one particular tool.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte.tools.toolsets or vidbyte.tools.builtins.prebuilt at module level; a missing feature must fail each test at setup, not abort collection. 2. Do not loosen FLOAT_RELATIVE_TOLERANCE or FLOAT_ABSOLUTE_TOLERANCE; spec §9.2 item 5 fixes them.
KNOWN EDGE CASES: JSON integers parse as int, so an expected float accepts an int while an expected int rejects a float and a bool. A validation failure names its parameter as the first segment of each "loc: message" part. ConstructionCounter only sees the thread that enters it.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (§9.2, §13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import FrameType
from typing import Any

import pytest

from vidbyte.tools.types import ToolCall, ToolResult, ToolStatus

FLOAT_RELATIVE_TOLERANCE = 1e-9
FLOAT_ABSOLUTE_TOLERANCE = 1e-12
ALLOWED_ERROR_TYPES = frozenset({"validation", "ToolExecutionError"})
MAX_ECHOED_ARGUMENT_CHARS = 100
ARGUMENT_ERROR_PATTERN = re.compile(
    r"\AInvalid value for '(?P<parameter>[^']+)': (?P<problem>.+)\. Expected (?P<expected>.+)\.\Z",
    re.DOTALL,
)


class AnyValue:
    """Marker for an output value the spec leaves open, such as a version-dependent flag or a seeded draw."""

    def __repr__(self) -> str:
        return "ANY"


ANY = AnyValue()


@dataclass(frozen=True, slots=True)
class Close:
    """Expected float that its row rounds to k places, compared within an absolute tolerance of 10^-k."""

    value: float
    absolute: float


@dataclass(frozen=True, slots=True)
class SuccessCase:
    """One call whose parsed output must equal `expected` under the OutputMatcher rules."""

    tool: str
    arguments: Mapping[str, Any]
    expected: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FailureCase:
    """One call that must fail with `error_type` and name `parameter`; `contains` is an optional message fragment."""

    tool: str
    arguments: Mapping[str, Any]
    parameter: str
    error_type: str
    contains: str | None = None


def ok(tool: str, arguments: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> Any:
    """A success case for pytest.mark.parametrize, with the id `<tool>-<label>`."""
    return pytest.param(SuccessCase(tool, arguments, expected), id=f"{tool}-{label}")


def bad(tool: str, arguments: Mapping[str, Any], parameter: str, label: str, contains: str | None = None) -> Any:
    """A case that must fail with a ToolExecutionError naming `parameter` (Appendix A "error(p)")."""
    return pytest.param(FailureCase(tool, arguments, parameter, "ToolExecutionError", contains), id=f"{tool}-{label}")


def invalid(tool: str, arguments: Mapping[str, Any], parameter: str, label: str, contains: str | None = None) -> Any:
    """A case that schema validation must reject, naming only `parameter`, before the tool body runs."""
    return pytest.param(FailureCase(tool, arguments, parameter, "validation", contains), id=f"{tool}-{label}")


def reject_json_constant(name: str) -> Any:
    """parse_constant hook: NaN, Infinity, and -Infinity in a tool output break INV-11."""
    raise ValueError(f"tool output contains the non-finite JSON constant {name}")


def parse_tool_output(text: str) -> Any:
    """Parse success text the way the model would, refusing non-finite constants."""
    return json.loads(text, parse_constant=reject_json_constant)


def describe_result(result: ToolResult) -> str:
    """One line that explains a result in an assertion message."""
    error_type = result.metadata.get("error_type")
    return f"status={result.status.value} error_type={error_type!r} output={result.output[:600]!r}"


def argument_error_parameter(message: str) -> str | None:
    """The parameter an INV-15 message names, or None when the message does not have the INV-15 form."""
    match = ARGUMENT_ERROR_PATTERN.match(message)
    return match.group("parameter") if match else None


def validation_parameters(message: str) -> set[str]:
    """The parameters named by the first loc segment of each part of a FunctionTool validation message."""
    names = set()
    for part in message.split("; "):
        location = part.split(": ", 1)[0]
        names.add(location.split(".", 1)[0])
    return names


class OutputMatcher:
    """Compares a parsed tool output with a hand-computed expectation and lists every difference."""

    def mismatches(self, expected: Any, actual: Any, path: str = "$") -> list[str]:
        """Return one message per difference; an empty list means the output matches."""
        if isinstance(expected, AnyValue):
            return []
        if isinstance(expected, Close):
            return self._compare_close(expected, actual, path)
        if expected is None or isinstance(expected, (bool, str)):
            return self._compare_exact(expected, actual, path)
        if isinstance(expected, int):
            return self._compare_integer(expected, actual, path)
        if isinstance(expected, float):
            return self._compare_float(expected, actual, path)
        if isinstance(expected, Mapping):
            return self._compare_mapping(expected, actual, path)
        if isinstance(expected, (list, tuple)):
            return self._compare_sequence(expected, actual, path)
        return [f"{path}: the test has an unsupported expectation {expected!r}"]

    def _compare_exact(self, expected: Any, actual: Any, path: str) -> list[str]:
        if type(actual) is type(expected) and actual == expected:
            return []
        return [f"{path}: expected {expected!r}, got {actual!r}"]

    def _compare_integer(self, expected: int, actual: Any, path: str) -> list[str]:
        if type(actual) is int and actual == expected:
            return []
        return [f"{path}: expected the integer {expected!r}, got {actual!r}"]

    def _compare_float(self, expected: float, actual: Any, path: str) -> list[str]:
        is_number = isinstance(actual, (int, float)) and not isinstance(actual, bool)
        if is_number and actual == pytest.approx(expected, rel=FLOAT_RELATIVE_TOLERANCE, abs=FLOAT_ABSOLUTE_TOLERANCE):
            return []
        return [f"{path}: expected about {expected!r} (rel 1e-9, abs 1e-12), got {actual!r}"]

    def _compare_close(self, expected: Close, actual: Any, path: str) -> list[str]:
        is_number = isinstance(actual, (int, float)) and not isinstance(actual, bool)
        if is_number and abs(actual - expected.value) <= expected.absolute * (1 + 1e-9):
            return []
        return [f"{path}: expected {expected.value!r} within {expected.absolute!r}, got {actual!r}"]

    def _compare_mapping(self, expected: Mapping[str, Any], actual: Any, path: str) -> list[str]:
        if not isinstance(actual, dict):
            return [f"{path}: expected an object, got {actual!r}"]
        problems = []
        if set(actual) != set(expected):
            problems.append(f"{path}: keys differ; missing {sorted(set(expected) - set(actual))}, extra {sorted(set(actual) - set(expected))}")
        for key in expected:
            if key in actual:
                problems.extend(self.mismatches(expected[key], actual[key], f"{path}.{key}"))
        return problems

    def _compare_sequence(self, expected: Sequence[Any], actual: Any, path: str) -> list[str]:
        if not isinstance(actual, list):
            return [f"{path}: expected an array, got {actual!r}"]
        if len(actual) != len(expected):
            return [f"{path}: expected {len(expected)} items, got {len(actual)}: {actual!r}"[:800]]
        problems = []
        for index, (want, got) in enumerate(zip(expected, actual, strict=True)):
            problems.extend(self.mismatches(want, got, f"{path}[{index}]"))
        return problems


class ToolRunner:
    """Executes prebuilt tools through FunctionTool.execute and checks results against cases."""

    def __init__(self, catalogue: Iterable[Any]) -> None:
        self._tools = {tool.name: tool for tool in catalogue}

    def tool(self, name: str) -> Any:
        """The tool object with this name; a missing name fails the calling test."""
        assert name in self._tools, f"the prebuilt library has no tool named {name!r}"
        return self._tools[name]

    def result(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        """Run one call exactly as the runtime would, through the tool's own validation and worker thread."""
        return asyncio.run(self.tool(name).execute(ToolCall(name, dict(arguments))))

    def output(self, name: str, arguments: Mapping[str, Any]) -> Any:
        """Run one call that must succeed and return its parsed JSON output."""
        result = self.result(name, arguments)
        assert result.status is ToolStatus.SUCCESS, f"{name}({arguments!r:.300}) failed: {describe_result(result)}"
        return parse_tool_output(result.output)

    def check_success(self, case: SuccessCase) -> Any:
        """Assert that a success case returns exactly its expected object; returns the parsed output."""
        actual = self.output(case.tool, case.arguments)
        problems = OutputMatcher().mismatches(dict(case.expected), actual)
        assert not problems, f"{case.tool} returned {actual!r:.1500}; differences: {problems}"
        return actual

    def check_failure(self, case: FailureCase) -> ToolResult:
        """Assert that a failure case fails with its error type and names its parameter."""
        result = self.result(case.tool, case.arguments)
        assert result.status is ToolStatus.ERROR, f"{case.tool} should fail on {case.parameter!r}: {describe_result(result)}"
        assert result.metadata.get("error_type") == case.error_type, describe_result(result)
        if case.error_type == "ToolExecutionError":
            named = argument_error_parameter(result.output)
            assert named == case.parameter, f"the INV-15 message should name {case.parameter!r}: {describe_result(result)}"
        else:
            named_set = validation_parameters(result.output)
            assert named_set == {case.parameter}, f"validation should name only {case.parameter!r}: {describe_result(result)}"
        if case.contains is not None:
            assert case.contains in result.output, f"message lacks {case.contains!r}: {describe_result(result)}"
        return result


DATE_SAMPLES = ("2024-02-29", "2023-01-31", "1970-01-01", "2024-12-30", "9999-12-31", "0001-01-01")
DATETIME_SAMPLES = (
    "2024-02-29T12:30:00Z",
    "2024-03-10T01:59:59-05:00",
    "1970-01-01T00:00:00",
    "2000-01-01T00:00:00.123456+05:30",
    "9999-12-31T23:59:59+00:00",
    "0001-01-01T00:00:00+00:00",
)
TIME_SAMPLES = ("00:00", "12:30:15", "23:59:59.999999", "09:05")
PATTERN_SAMPLES = (
    "0", "7", "-12", "+5", "000123", "99999999999999999999", "1/3", "-22/7", "0/1", "3.14159", "-0.5", ".5", "1.",
    "+00:00", "Z", "-05:30", "+23:59", "10", "255", "0.(3)", ".(142857)", "1.2(34)", "ff", "Zz9", "-zz", "101",
)
GENERAL_TEXT_SAMPLES = (
    "",
    " ",
    "a",
    "Hello, World! 123",
    "ünïcödé ß İ ﬁ 😀 日本語",
    "line one\r\nline two\rline three\n\nlast",
    "The quick brown fox. Dr. Smith arrived! Did he? Yes…",
    "{}",
    "[1, 2, {\"a\": null}]",
    "[{\"a\": 1, \"b\": \"x\"}, {\"a\": 2}, {\"b\": \"y\", \"a\": 1}]",
    "<a href='x'>t</a>",
    "x = 1\u0000",
    "[" * 150 + "]" * 150,
    "0",
    "-12.50",
    "a" * 300,
    "a,b\n1,2\n3,4\n",
    "<root><a x='1'>t</a><a/></root>",
    "def f(a, b=1, *args, c, **kw):\n    \"\"\"Doc.\"\"\"\n    return a\n\nclass K(object):\n    pass\n",
    "a = 1\n[t]\nb = \"x\"\n",
    "[s]\nk = v\n",
    "https://user:pw@example.com:8080/p/a?x=1&y=2&x=3#f",
    "A=1\nB='x y'\nA=2\n",
    "a.b@example.com",
    "192.168.0.1",
    "10.0.0.0/8",
    "::1",
    "(a)(?P<n>b)?",
    "# Title\n\n| a | b |\n|---|:-:|\n| 1 | 2 |\n\n- [x] done\n- [ ] open\n[l](http://x.y)\n```py\nx\n```\n",
    "<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table><a href='/x'>t</a>",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln",
    "1.2.3-alpha.1+build.5",
    "886313e1-3b8a-5372-9b90-0c9aee199e5d",
    "aGVsbG8=",
    "68656c6c6f",
    "Hello {name}, {{literal}}",
    "2d6+3",
    "rwxr-x---",
    "1h 30m",
    "one hundred twenty-three",
    "1.5 GiB",
    "$1,234.56",
    "40°26'46\"N",
    "next friday",
    "03/04/2025",
    "*.py",
)


RECORDS_SAMPLE = "[{\"a\": 1, \"b\": \"x\"}, {\"a\": 2}, {\"b\": \"y\", \"a\": 1}]"
NAME_HINTS = (
    ("json", ("{}", "[1, 2, {\"a\": null}]", RECORDS_SAMPLE, "{\"a\": {\"b\": [1, 2]}, \"c\": \"x\"}", "[" * 150 + "]" * 150, "nul")),
    ("records", (RECORDS_SAMPLE, "[]", "[{}]", "{\"a\": 1}", "[1, 2]")),
    ("csv", ("a,b\n1,2\n3,4\n", "a;b\r\n1;2\r\n", "x\n", "a,a\n1,2\n", "a,b\n1,2,3\n", "\"q\"\"x\",b\n\"1\n2\",3\n")),
    ("xml", ("<root><a x='1'>t</a><a/></root>", "<a><b>1</b><b>2</b></a>", "<a>", "<?xml version='1.0'?><r xmlns:p='urn:x'><p:i/></r>")),
    ("toml", ("a = 1\n[t]\nb = \"x\"\n", "a = [1, 2]\n", "a = \n", "d = 1979-05-27T07:32:00Z\n")),
    ("ini", ("[s]\nk = v\n", "k = v\n", "[DEFAULT]\na = 1\n[s]\nb = 2\n")),
    ("url", ("https://user:pw@example.com:8080/p/a?x=1&y=2&x=3#f", "/relative/path?q", "http://[::1]:80/", "mailto:a@b.c", "a%20b%ZZ")),
    ("email", ("a.b@example.com", "no-at-sign", "a@@b.com", "x@localhost")),
    ("source", ("def f(a, b=1, *args, c, **kw):\n    \"\"\"Doc.\"\"\"\n    return a\n\nclass K(object):\n    pass\n", "import os, sys\nfrom a.b import c as d\n", "def (:\n")),
    ("literal", ("{'a': (1, 2), 'b': None}", "[1, 2.5, 'x', True]", "set()", "1j")),
    ("markdown", ("# Title\n\n| a | b |\n|---|:-:|\n| 1 | 2 |\n\n- [x] done\n- [ ] open\n[l](http://x.y)\n```py\nx\n```\n",)),
    ("html", ("<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table><a href='/x'>t</a>", "<p>a &amp; b</p>")),
    ("pattern", ("(a)(?P<n>b)?", ".", "[", "a*", "^$", "*.py")),
    ("address", ("192.168.0.1", "::1", "10.0.0.256", "2001:db8::1", "01.2.3.4")),
    ("network", ("10.0.0.0/8", "192.168.0.0/24", "::/0", "10.0.0.1/8")),
    ("token", ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln", "a.b", "e30.e30.")),
    ("version", ("1.2.3-alpha.1+build.5", "1.2.3", "01.2.3", "1.2")),
    ("uuid", ("886313e1-3b8a-5372-9b90-0c9aee199e5d", "not-a-uuid", "{886313E1-3B8A-5372-9B90-0C9AEE199E5D}")),
    ("base64", ("aGVsbG8=", "aGVsbG8", "!!!", "")),
    ("hex", ("68656c6c6f", "6", "zz", "68 65")),
    ("template", ("Hello {name}, {{literal}}", "{a}{b}", "{", "plain")),
    ("notation", ("2d6+3", "d20", "0d6", "3d6-1")),
    ("permission", ("755", "rwxr-x---", "4755", "999")),
    ("duration", ("1h 30m", "PT1H30M", "90 minutes", "1 day 2 hours")),
    ("words", ("one hundred twenty-three", "minus five", "twelve thousand and one")),
    ("command", ("ls -la 'a b' \"c\"", "echo 'unterminated", "")),
)
EDGE_TEXT_SAMPLES = ("", "a", "a" * 300)


class SchemaArgumentFactory:
    """Builds deterministic, schema-valid argument sets for a tool from its JSON input schema."""

    PROFILE_COUNT = 12

    def argument_sets(self, tool_name: str, schema: Mapping[str, Any]) -> list[dict[str, Any]]:
        """A required-only set first, then PROFILE_COUNT sets that rotate every parameter through its pool."""
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        definitions = schema.get("$defs", {})
        pools = {name: self.pool(prop, definitions, name) for name, prop in properties.items()}
        seed = zlib.crc32(tool_name.encode("utf-8"))
        sets = [{name: pools[name][0] for name in properties if name in required}]
        for profile in range(self.PROFILE_COUNT):
            arguments = {}
            for index, (name, pool) in enumerate(pools.items()):
                shift = 0 if index == 0 else (seed >> (3 * index)) % len(pool)
                arguments[name] = pool[(profile + shift) % len(pool)]
            sets.append(arguments)
        return sets

    def pool(self, prop: Mapping[str, Any], definitions: Mapping[str, Any], name: str = "") -> list[Any]:
        """Every candidate value for one parameter schema, edge values first."""
        prop = self._resolve(prop, definitions)
        if "anyOf" in prop:
            values: list[Any] = []
            for branch in prop["anyOf"]:
                values.extend([None] if branch.get("type") == "null" else self.pool(branch, definitions, name))
            return values
        if "enum" in prop:
            return list(prop["enum"])
        kind = prop.get("type")
        if kind == "string":
            return self._string_pool(prop, name)
        if kind == "integer":
            return self._integer_pool(prop)
        if kind == "number":
            return self._number_pool(prop)
        if kind == "boolean":
            return [False, True]
        if kind == "array":
            return self._array_pool(prop, definitions, name)
        if kind == "object":
            return [{}]
        raise AssertionError(f"SchemaArgumentFactory cannot build values for the schema {dict(prop)!r}")

    def _resolve(self, prop: Mapping[str, Any], definitions: Mapping[str, Any]) -> Mapping[str, Any]:
        if "$ref" in prop:
            target = definitions[prop["$ref"].rsplit("/", 1)[-1]]
            return {**target, **{key: value for key, value in prop.items() if key != "$ref"}}
        if "allOf" in prop and len(prop["allOf"]) == 1:
            return {**self._resolve(prop["allOf"][0], definitions), **{key: value for key, value in prop.items() if key != "allOf"}}
        return prop

    def _string_pool(self, prop: Mapping[str, Any], name: str) -> list[Any]:
        formats = {"date": DATE_SAMPLES, "date-time": DATETIME_SAMPLES, "time": TIME_SAMPLES}
        if prop.get("format") in formats:
            return list(formats[prop["format"]])
        hinted = tuple(sample for hint, samples in NAME_HINTS if hint in name for sample in samples)
        if "pattern" in prop:
            candidates = PATTERN_SAMPLES + hinted + GENERAL_TEXT_SAMPLES
        elif hinted:
            candidates = hinted + EDGE_TEXT_SAMPLES
        else:
            candidates = GENERAL_TEXT_SAMPLES + PATTERN_SAMPLES
        pattern = re.compile(prop["pattern"]) if "pattern" in prop else None
        low, high = prop.get("minLength", 0), prop.get("maxLength", sys.maxsize)
        allowed = [text for text in candidates if low <= len(text) <= high and (pattern is None or pattern.search(text))]
        pool = list(dict.fromkeys(allowed))
        assert pool, f"SchemaArgumentFactory has no sample for the string schema {dict(prop)!r}; add one to the pools"
        return pool

    def _integer_pool(self, prop: Mapping[str, Any]) -> list[Any]:
        low = prop["minimum"] if "minimum" in prop else prop["exclusiveMinimum"] + 1 if "exclusiveMinimum" in prop else -1_000_000
        high = prop["maximum"] if "maximum" in prop else prop["exclusiveMaximum"] - 1 if "exclusiveMaximum" in prop else 1_000_000
        candidates = [low, 0, 1, 2, 3, 5, 10, 64, 100, -1, -7] + ([high] if high <= 1000 else [])
        pool = list(dict.fromkeys(value for value in candidates if low <= value <= high))
        return pool or [low]

    def _number_pool(self, prop: Mapping[str, Any]) -> list[Any]:
        candidates = [0.0, 1.5, -2.25, 100.0, 3.0, 0.5, 1e-300, 1e300, -1e300]
        pool = [value for value in candidates if self._number_allowed(value, prop)]
        bounds = [prop[key] for key in ("minimum", "maximum") if key in prop]
        return pool or [float(bounds[0]) if bounds else 0.0]

    def _number_allowed(self, value: float, prop: Mapping[str, Any]) -> bool:
        return (
            value >= prop.get("minimum", -float("inf"))
            and value <= prop.get("maximum", float("inf"))
            and value > prop.get("exclusiveMinimum", -float("inf"))
            and value < prop.get("exclusiveMaximum", float("inf"))
        )

    def _array_pool(self, prop: Mapping[str, Any], definitions: Mapping[str, Any], name: str) -> list[Any]:
        items = self.pool(prop.get("items", {"type": "string"}), definitions, name)
        low, high = prop.get("minItems", 0), prop.get("maxItems", sys.maxsize)
        shapes = [[], items[:1], items[:3], [items[0], items[0]], list(reversed(items[:4])), items[1:6]]
        pool = []
        for shape in shapes:
            padded = (shape + items * low)[: max(len(shape), low)]
            if low <= len(padded) <= high:
                pool.append(padded)
        return pool or [items[:low]]


class ConstructionCounter:
    """Counts FunctionTool.__init__ and Tools.__init__ calls on the current thread while the block runs."""

    def __init__(self) -> None:
        self.function_tools = 0
        self.catalogues = 0
        self._previous: Any = None

    def __enter__(self) -> ConstructionCounter:
        self._previous = sys.getprofile()
        sys.setprofile(self._observe)
        return self

    def __exit__(self, *exc_info: object) -> None:
        sys.setprofile(self._previous)

    def _observe(self, frame: FrameType, event: str, arg: object) -> None:
        if event != "call" or frame.f_code.co_name != "__init__":
            return
        qualified = getattr(frame.f_code, "co_qualname", "")
        filename = frame.f_code.co_filename.replace("\\", "/")
        if qualified == "FunctionTool.__init__" and filename.endswith("vidbyte/tools/function_tool.py"):
            self.function_tools += 1
        elif qualified == "Tools.__init__" and filename.endswith("vidbyte/tools/catalog.py"):
            self.catalogues += 1
