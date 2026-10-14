"""FILE: tests/features/prebuilt_tools/test_prebuilt_error_contract.py

PURPOSE: Library-wide result contract: for schema-valid arguments every tool returns a JSON object with exactly its Appendix A keys and only finite numbers, or fails with an allowed error type whose message has the INV-15 form (AC-6, INV-10, INV-11, INV-14, INV-15).
ROLE IN CODEBASE: Drives all 265 tools of the vidbyte.tools.toolsets.PrebuiltTools library through FunctionTool.execute with deterministic argument sets that SchemaArgumentFactory derives from each tool's own input schema.
ARCHITECTURE NOTE: This is a property-style sweep, not an oracle: it cannot know the right answer for a generated input, so it checks only what must hold for every input. The argument sets lean on edge values (empty text, year 1 and 9999, 1e300, 150-deep brackets) because those are where an unexpected exception escapes.
FUNCTION INVENTORY: call_problems lists every contract breach of one call; echoed_argument lists argument text repeated in an error message; test_any_schema_valid_call_keeps_the_result_contract sweeps every tool; test_hmac_key_never_appears_in_output_or_error covers the T-3 secret rule.
COMMON MODIFICATION PATTERNS: Add an edge value to the factory pools in prebuilt_tool_harness.py rather than special-casing a tool here.
WHAT NOT TO DO IN THIS FILE: 1. Do not skip a tool because it fails here; a non-ToolExecutionError escape is exactly the bug INV-14 forbids. 2. Do not catch and ignore validation results as failures; they are allowed by AC-6.
KNOWN EDGE CASES: A validation failure is allowed but proves nothing about the body, so the factory keeps most sets schema-valid. Messages are checked for 101-character windows of each long argument, which is how "more than 100 characters" is measured.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (INV-10, INV-11, INV-14, INV-15, AC-6, T-3)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_error_contract.py
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_catalogue_data import ALL_TOOL_NAMES, RETURN_KEYS
from tests.features.prebuilt_tools.prebuilt_tool_harness import (
    ALLOWED_ERROR_TYPES,
    MAX_ECHOED_ARGUMENT_CHARS,
    SchemaArgumentFactory,
    ToolRunner,
    argument_error_parameter,
    describe_result,
    parse_tool_output,
)
from vidbyte.tools.types import ToolStatus

HMAC_SECRET = "zz-SECRET-hmac-key-material-zz"


def argument_texts(arguments: Mapping[str, Any]) -> Iterator[str]:
    """Every string argument value, including the strings inside list arguments."""
    for value in arguments.values():
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            yield from (item for item in value if isinstance(item, str))


def echoed_argument(message: str, arguments: Mapping[str, Any]) -> list[str]:
    """Argument text of more than MAX_ECHOED_ARGUMENT_CHARS characters that reappears in an error message."""
    window = MAX_ECHOED_ARGUMENT_CHARS + 1
    echoed = []
    for text in argument_texts(arguments):
        for start in range(0, max(len(text) - window + 1, 0)):
            if text[start : start + window] in message:
                echoed.append(text[start : start + window])
                break
    return echoed


def success_problems(name: str, text: str) -> list[str]:
    """INV-10 and INV-11: one JSON object, exactly the row's keys, no NaN or Infinity."""
    try:
        output = parse_tool_output(text)
    except ValueError as error:
        return [f"output is not finite JSON ({error}): {text[:200]!r}"]
    if not isinstance(output, dict):
        return [f"output is not a JSON object: {text[:200]!r}"]
    if set(output) != set(RETURN_KEYS[name]):
        return [f"keys {sorted(output)} differ from Appendix A {sorted(RETURN_KEYS[name])}"]
    return []


def failure_problems(name: str, message: str, error_type: object, arguments: Mapping[str, Any], parameters: set[str]) -> list[str]:
    """INV-14 and INV-15: an allowed error type, and for domain errors the exact message form with no echo."""
    if error_type not in ALLOWED_ERROR_TYPES:
        return [f"error_type {error_type!r} escaped (INV-14): {message[:300]!r}"]
    if error_type != "ToolExecutionError":
        return []
    problems = []
    named = argument_error_parameter(message)
    if named not in parameters:
        problems.append(f"message does not have the INV-15 form naming one of {sorted(parameters)}: {message[:300]!r}")
    if "Traceback" in message:
        problems.append(f"message contains a traceback: {message[:300]!r}")
    echoed = echoed_argument(message, arguments)
    if echoed:
        problems.append(f"message repeats more than {MAX_ECHOED_ARGUMENT_CHARS} characters of an argument: {echoed[0][:40]!r}...")
    return problems


def call_problems(tool_runner: ToolRunner, name: str, arguments: Mapping[str, Any], parameters: set[str]) -> list[str]:
    """Every contract breach of one call, labelled with its arguments."""
    label = f"{name}({dict(arguments)!r:.200})"
    try:
        result = tool_runner.result(name, arguments)
    except Exception as error:
        return [f"{label}: execute itself raised {type(error).__name__} (AC-21, INV-19)"]
    if result.status is ToolStatus.SUCCESS:
        found = success_problems(name, result.output)
    else:
        found = failure_problems(name, result.output, result.metadata.get("error_type"), arguments, parameters)
    return [f"{label}: {problem}" for problem in found]


@pytest.mark.parametrize("name", ALL_TOOL_NAMES)
def test_any_schema_valid_call_keeps_the_result_contract(tool_runner: ToolRunner, name: str) -> None:
    """AC-6 with INV-10, INV-11, INV-14, and INV-15 over thirteen deterministic argument sets per tool."""
    schema = dict(tool_runner.tool(name).spec().input_schema or {})
    parameters = set(schema.get("properties", {}))
    problems = []
    for arguments in SchemaArgumentFactory().argument_sets(name, schema):
        problems.extend(call_problems(tool_runner, name, arguments, parameters))
    assert not problems, problems[:8]


@pytest.mark.parametrize(
    ("key_format", "key"),
    [("hex", HMAC_SECRET), ("base64", f"%%{HMAC_SECRET}%%")],
    ids=["hex", "base64"],
)
def test_hmac_key_never_appears_in_an_error(tool_runner: ToolRunner, key_format: str, key: str) -> None:
    """INV-15 and T-3: a key that is not valid for its format fails naming 'key' without repeating any of the key."""
    result = tool_runner.result("compute_hmac", {"message": "payload", "key": key, "key_format": key_format})
    assert result.status is ToolStatus.ERROR, describe_result(result)
    assert result.metadata.get("error_type") == "ToolExecutionError", describe_result(result)
    assert argument_error_parameter(result.output) == "key", describe_result(result)
    assert "SECRET" not in result.output and HMAC_SECRET not in result.output


def test_hmac_key_never_appears_in_a_success_output(tool_runner: ToolRunner) -> None:
    """T-3: a successful compute_hmac result carries the digest and algorithm only, never the key."""
    result = tool_runner.result("compute_hmac", {"message": "payload", "key": HMAC_SECRET})
    assert result.status is ToolStatus.SUCCESS, describe_result(result)
    assert HMAC_SECRET not in result.output and "SECRET" not in result.output
    assert set(parse_tool_output(result.output)) == {"digest", "algorithm"}
