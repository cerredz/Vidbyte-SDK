"""FILE: tests/features/prebuilt_tools/test_prebuilt_model_facing_contract.py

PURPOSE: Model-facing contract of every prebuilt tool: description depth and the no-example rule (AC-8, INV-9), provider schemas for three providers (AC-9, INV-21), and schema caps that reject one-over-cap input before the body runs (AC-7, INV-16).
ROLE IN CODEBASE: Reads tool.spec() and Tools.provider_schemas of the session library built from vidbyte.tools.toolsets.PrebuiltTools, counts sentences with the repository's own lint SentenceCounter, and sends over-cap calls through FunctionTool.execute.
ARCHITECTURE NOTE: The sentence counter is imported from lint/rules/s025_model_facing_description_depth.py so the tests and the S025 lint rule can never disagree about what a sentence is. Caps come from the hand-copied parameter table, never from the live schema; since spec r4 every capped parameter states its value.
FUNCTION INVENTORY: test_tool_description_has_four_or_five_sentences_and_no_example; test_parameter_descriptions_have_four_or_five_sentences_and_no_example; test_provider_schemas_declare_every_tool_once; test_one_over_cap_argument_fails_validation_naming_the_parameter; over_cap_values builds each argument that is exactly one unit over a cap (a list's item cap and its item-count cap separately, and each TextList cap inside a list of lists) while still matching any pattern.
COMMON MODIFICATION PATTERNS: Add an example marker to EXAMPLE_MARKERS only when it is precise enough not to flag ordinary prose (ILLUSTRATIVE_LITERAL follows the r6 INV-9 wording and flags only a literal that illustrates a rule); add a provider to PROVIDERS when the SDK formatter gains one.
WHAT NOT TO DO IN THIS FILE: 1. Do not reimplement sentence counting; import SentenceCounter. 2. Do not loosen the one-over-cap check to "any validation error"; the error must name the capped parameter and its cap.
KNOWN EDGE CASES: Pydantic reports every failing field, so the cap test sends only the capped argument and looks for that argument's own "at most" message among the parts. A capped string with a pattern needs a fill character that matches the pattern, or the error would be about the pattern instead of the length; no fill matches the UtcOffset pattern, which works only because pydantic reports a string's length before its pattern. A list with an item cap is checked twice, once one item too long and once one item too many. The list of lists intersect_lists.lists is checked three times: one list too many, one inner list one item too long (loc lists.0), and one inner string one character too long (loc lists.0.0); the inner cases send min_lists lists so the outer minimum never fails beside them.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (INV-9, INV-16, INV-21, AC-7, AC-8, AC-9); lint/rules/s025_model_facing_description_depth.py
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_model_facing_contract.py
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from lint.rules.s025_model_facing_description_depth import SentenceCounter
from tests.features.prebuilt_tools.prebuilt_catalogue_data import ALL_TOOL_NAMES
from tests.features.prebuilt_tools.prebuilt_parameter_data import TOOL_PARAMETERS, TextListsShape
from tests.features.prebuilt_tools.prebuilt_tool_harness import SchemaArgumentFactory, ToolRunner, describe_result
from vidbyte.tools.types import ToolStatus

# INV-9 (spec r6) also counts a literal value that illustrates a rule as an example: a type word followed by a literal
# ("the number 1") or a literal compared with a literal ("true never equals 1", "1 equals 1.0").
ILLUSTRATIVE_LITERAL = r"\b(?:number|string|integer|float|boolean) (?:-?\d|true\b|false\b|null\b)|\b(?:-?\d+(?:\.\d+)?|true|false|null) (?:never |does not |do not )?(?:equals?|matche?s?) (?:-?\d|true\b|false\b|null\b)"
EXAMPLE_MARKERS = re.compile(r"\bfor example\b|\bfor instance\b|\be\.g\.|\b\d{4}-\d{2}-\d{2}\b|" + ILLUSTRATIVE_LITERAL, re.IGNORECASE)
PROVIDERS = ("openai", "anthropic", "gemini")
FILL_CHARACTERS = ("1", "a", "0")


def sentence_problem(label: str, text: str) -> str | None:
    """Why a description breaks INV-9, or None when it has 4 or 5 sentences and no example marker."""
    count = SentenceCounter().count(text or "")
    if not 4 <= count <= 5:
        return f"{label} has {count} sentences, INV-9 needs 4 or 5: {text!r}"
    marker = EXAMPLE_MARKERS.search(text)
    if marker:
        return f"{label} contains the example marker {marker.group(0)!r}: {text!r}"
    return None


@pytest.mark.parametrize("name", ALL_TOOL_NAMES)
def test_tool_description_has_four_or_five_sentences_and_no_example(tool_runner: ToolRunner, name: str) -> None:
    """AC-8 and INV-9: the model-facing tool description is 4 or 5 sentences by SentenceCounter and holds no example."""
    problem = sentence_problem(f"{name} description", tool_runner.tool(name).spec().description)
    assert problem is None, problem


@pytest.mark.parametrize("name", ALL_TOOL_NAMES)
def test_parameter_descriptions_have_four_or_five_sentences_and_no_example(tool_runner: ToolRunner, name: str) -> None:
    """AC-8 and INV-9: every parameter has a non-empty description of 4 or 5 sentences with no example."""
    parameters = tool_runner.tool(name).spec().parameters
    assert tuple(parameter.name for parameter in parameters) == tuple(row[0] for row in TOOL_PARAMETERS[name])
    problems = []
    for parameter in parameters:
        if not (parameter.description or "").strip():
            problems.append(f"{name}.{parameter.name} has an empty description")
            continue
        problem = sentence_problem(f"{name}.{parameter.name}", parameter.description)
        if problem:
            problems.append(problem)
    assert not problems, problems


def declared_names(provider: str, declarations: tuple[dict[str, Any], ...]) -> list[str]:
    """The tool name inside each provider declaration, in order."""
    if provider == "openai":
        return [declaration["function"]["name"] for declaration in declarations]
    if provider == "anthropic":
        return [declaration["name"] for declaration in declarations]
    return [entry["name"] for declaration in declarations for entry in declaration["function_declarations"]]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_schemas_declare_every_tool_once(prebuilt_library: Any, provider: str) -> None:
    """AC-9 and INV-21: provider_schemas succeeds for each provider with one JSON-serializable declaration per tool."""
    declarations = prebuilt_library.provider_schemas(provider)
    assert len(declarations) == len(prebuilt_library)
    assert declared_names(provider, declarations) == list(prebuilt_library.names())
    json.dumps(declarations)


def resolved_property(schema: dict[str, Any], parameter: str) -> dict[str, Any]:
    """A parameter's schema with an Optional wrapper removed."""
    prop = schema["properties"][parameter]
    if "anyOf" in prop:
        prop = next(branch for branch in prop["anyOf"] if branch.get("type") != "null")
    return prop


def over_cap_string(prop: dict[str, Any], length: int) -> str:
    """A string of the given length that still matches the parameter's pattern when it has one."""
    pattern = prop.get("pattern")
    for fill in FILL_CHARACTERS:
        candidate = fill * length
        if pattern is None or re.search(pattern, candidate):
            return candidate
    return FILL_CHARACTERS[0] * length


def over_cap_values(schema: dict[str, Any], parameter: str, cap: object, item_cap: object) -> list[tuple[Any, str, int]]:
    """Build (value, expected loc, cap) for each argument that is exactly one unit over one of the parameter's caps, inner list caps included."""
    prop = resolved_property(schema, parameter)
    values = []
    if isinstance(item_cap, int):
        items = prop.get("items", {})
        values.append(([over_cap_string(items, item_cap + 1)], f"{parameter}.0", item_cap))
    if isinstance(item_cap, TextListsShape):
        other_lists = [["a"]] * (item_cap.min_lists - 1)
        values.append(([["a"] * (item_cap.list_items + 1), *other_lists], f"{parameter}.0", item_cap.list_items))
        values.append(([["a" * (item_cap.item_chars + 1)], *other_lists], f"{parameter}.0.0", item_cap.item_chars))
    if isinstance(cap, int) and prop.get("type") == "array":
        item = SchemaArgumentFactory().pool(prop.get("items", {"type": "string"}), schema.get("$defs", {}), parameter)[0]
        values.append(([item] * (cap + 1), parameter, cap))
    elif isinstance(cap, int):
        values.append((over_cap_string(prop, cap + 1), parameter, cap))
    return values


def capped_rows(name: str) -> list[tuple[Any, ...]]:
    return [row for row in TOOL_PARAMETERS[name] if isinstance(row[2], int) or isinstance(row[3], (int, TextListsShape))]


@pytest.mark.parametrize("name", [name for name in ALL_TOOL_NAMES if capped_rows(name)])
def test_one_over_cap_argument_fails_validation_naming_the_parameter(tool_runner: ToolRunner, name: str) -> None:
    """AC-7 and INV-16: an argument one unit over its cap fails schema validation, naming that argument and its cap."""
    schema = dict(tool_runner.tool(name).spec().input_schema or {})
    problems = []
    for parameter, _, cap, item_cap, _ in capped_rows(name):
        for value, location, limit in over_cap_values(schema, parameter, cap, item_cap):
            result = tool_runner.result(name, {parameter: value})
            parts = result.output.split("; ")
            own = [part for part in parts if part.split(": ", 1)[0] == location]
            rejected = result.status is ToolStatus.ERROR and result.metadata.get("error_type") == "validation"
            if not (rejected and any("at most" in part and str(limit) in part for part in own)):
                problems.append(f"{location} over its cap {limit}: {describe_result(result)[:300]}")
    assert not problems, problems
