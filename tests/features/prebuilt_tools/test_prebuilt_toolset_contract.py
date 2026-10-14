"""FILE: tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py

PURPOSE: Contract tests for building the prebuilt tool library: PrebuiltTools construction and category validation, catalogue size and order, the 68 enums, each tool's FunctionTool shape, and every tool's parameter schema against Appendix A.
ROLE IN CODEBASE: Exercises vidbyte.tools.toolsets.PrebuiltTools, vidbyte.lib.enums (PrebuiltToolCategory and the §9.2 vocabularies), and the internal vidbyte.tools.builtins.prebuilt category classes through the public toolset (spec §8.5, §9.2).
ARCHITECTURE NOTE: Expected values come from the hand-copied tables in prebuilt_catalogue_data.py and prebuilt_parameter_data.py, never from vidbyte code. Construction is counted with ConstructionCounter (a profile hook), not with mocks.
FUNCTION INVENTORY: Floor and order tests (AC-2, AC-3, AC-12, INV-1, INV-2, INV-3); category validation tests (AC-4, AC-19, INV-4, INV-5); construction identity tests (INV-6, AC-18); FunctionTool shape (INV-8); export lists (INV-22, §8.5); enum tables; per-tool schema contract (INV-16, Appendix A parameters).
COMMON MODIFICATION PATTERNS: When Appendix A changes, update the data modules first and let these tests follow; add a new construction rule as its own test with its spec ID in the name or docstring.
WHAT NOT TO DO IN THIS FILE: 1. Do not import PrebuiltTools or the prebuilt package at module level; collection must survive a missing feature. 2. Do not compare against values read from the implementation's own constants.
KNOWN EDGE CASES: ToolRegistrationError subclasses ToolRegistryError, so category rejection tests also check the message. A bare PrebuiltToolCategory member is a str, so it must be treated as one category, while a bare plain string must be rejected without being iterated. The one list of lists, intersect_lists.lists (list[TextList]), is checked one level down: its minItems, each inner list's maxItems, and the inner strings' maxLength.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (§6.1, §6.2, §8.5, §9.2, Appendix A)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py
"""

from __future__ import annotations

import importlib
import inspect
import re
from enum import Enum
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_catalogue_data import ALL_TOOL_NAMES, CATEGORY_TABLE, CATEGORY_TOOL_NAMES, ENUM_TABLE
from tests.features.prebuilt_tools.prebuilt_parameter_data import REQUIRED, TOOL_PARAMETERS, TextListsShape
from tests.features.prebuilt_tools.prebuilt_tool_harness import ConstructionCounter
from vidbyte.lib.errors import ToolRegistrationError, ToolRegistryError
from vidbyte.tools.catalog import Tools
from vidbyte.tools.function_tool import FunctionTool
from vidbyte.tools.types import ToolPermission

CATEGORY_VALUES = tuple(value for value, _, _ in CATEGORY_TABLE)
UTC_OFFSET_PATTERN = "^(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])$"
TOOL_NAME_PATTERN = re.compile(r"\A[a-z][a-z0-9_]*\Z")
RESERVED_TOOL_NAMES = frozenset({"isDone", "updateTrace", "mcp"})
JSON_TYPES = {"string": ("string", None), "integer": ("integer", None), "number": ("number", None), "boolean": ("boolean", None), "array": ("array", None)}
JSON_TYPES.update({"date": ("string", "date"), "date-time": ("string", "date-time"), "time": ("string", "time"), "utc_offset": ("string", None)})


def category(api: Any, value: str) -> Any:
    return api.categories(value)


def library_tool(library: Any, name: str) -> Any:
    matches = [tool for tool in library if tool.name == name]
    assert len(matches) == 1, f"expected exactly one tool named {name!r}, found {len(matches)}"
    return matches[0]


# ---- AC-2, AC-12, INV-1, INV-2, INV-3: the whole library ----


def test_full_library_meets_the_floor_and_holds_every_appendix_name(prebuilt_library: Any) -> None:
    """AC-2 and AC-12: at least 250 tools, every Appendix A name present, so shrinking the catalogue fails the suite."""
    names = prebuilt_library.names()
    assert len(prebuilt_library) >= 250, f"the library holds only {len(prebuilt_library)} tools"
    missing = [name for name in ALL_TOOL_NAMES if name not in names]
    assert not missing, f"Appendix A tools missing from PrebuiltTools(PrebuiltToolCategory): {missing}"


def test_full_library_is_exactly_appendix_a_in_catalogue_order(prebuilt_library: Any) -> None:
    """INV-1 and INV-2: exactly the 265 Appendix A names, each once, in enum order and then row order."""
    names = prebuilt_library.names()
    assert len(names) == len(set(names)), "a tool name appears twice"
    assert names == ALL_TOOL_NAMES


def test_every_tool_name_is_a_safe_identifier(prebuilt_library: Any) -> None:
    """INV-3: names match ^[a-z][a-z0-9_]*$, are at most 64 characters, and avoid the reserved runtime names."""
    for name in prebuilt_library.names():
        assert TOOL_NAME_PATTERN.match(name) and len(name) <= 64, name
        assert name not in RESERVED_TOOL_NAMES, name


@pytest.mark.parametrize(("value", "class_name", "names"), CATEGORY_TABLE, ids=CATEGORY_VALUES)
def test_single_category_holds_its_appendix_rows_in_order(prebuilt_api: Any, value: str, class_name: str, names: tuple[str, ...]) -> None:
    """AC-3 and INV-2: PrebuiltTools([c]).names() equals c's Appendix A table in row order, 6 to 15 tools."""
    catalogue = prebuilt_api.tools([category(prebuilt_api, value)])
    assert catalogue.names() == names
    assert 6 <= len(catalogue) <= 15


# ---- PrebuiltToolCategory and the §9.2 enums ----


def test_category_enum_declares_the_31_values_in_spec_order(prebuilt_api: Any) -> None:
    """§8.5: PrebuiltToolCategory is a str Enum whose values follow Appendix A, and values() returns them in order."""
    enum_class = prebuilt_api.categories
    assert issubclass(enum_class, str) and issubclass(enum_class, Enum)
    assert tuple(member.value for member in enum_class) == CATEGORY_VALUES
    assert tuple(member.name for member in enum_class) == tuple(value.upper() for value in CATEGORY_VALUES)
    assert enum_class.values() == CATEGORY_VALUES
    assert isinstance(enum_class.values(), tuple)


@pytest.mark.parametrize(("enum_name", "module", "values"), ENUM_TABLE, ids=[row[0] for row in ENUM_TABLE])
def test_enum_vocabulary_matches_spec(enum_name: str, module: str, values: tuple[str, ...]) -> None:
    """§9.2: each enum is a str Enum in vidbyte/lib/enums/<module>.py, exported from vidbyte.lib.enums, with the listed values."""
    enums = importlib.import_module("vidbyte.lib.enums")
    assert enum_name in enums.__all__, f"{enum_name} is not exported from vidbyte.lib.enums"
    enum_class = getattr(enums, enum_name)
    assert issubclass(enum_class, str) and issubclass(enum_class, Enum)
    assert enum_class.__module__ == f"vidbyte.lib.enums.{module}"
    assert tuple(member.value for member in enum_class) == values
    expected_names = values if enum_name == "CompassPoint" else tuple(value.upper() for value in values)
    assert tuple(member.name for member in enum_class) == expected_names


# ---- AC-4, AC-19, INV-4, INV-5: category validation ----


def test_plain_string_equal_to_a_member_value_is_rejected_before_building(prebuilt_api: Any) -> None:
    """AC-4 and INV-5: ["dates"] raises ToolRegistryError, lists every valid value, and builds no FunctionTool."""
    with ConstructionCounter() as counter, pytest.raises(ToolRegistryError) as caught:
        prebuilt_api.tools(["dates"])
    assert counter.function_tools == 0
    for value in CATEGORY_VALUES:
        assert value in str(caught.value), f"the message does not list the valid value {value!r}"


def test_mixed_valid_and_invalid_items_name_every_bad_value(prebuilt_api: Any) -> None:
    """AC-4 and INV-5: every bad item is named, a valid member beside them does not rescue the call, and nothing is built."""
    dates = category(prebuilt_api, "dates")
    with ConstructionCounter() as counter, pytest.raises(ToolRegistryError) as caught:
        prebuilt_api.tools([dates, 7, None, "calendar"])
    message = str(caught.value)
    assert counter.function_tools == 0
    for fragment in ("7", "None", "calendar"):
        assert fragment in message, f"the message does not name the bad value {fragment!r}: {message}"
    assert not isinstance(caught.value, ToolRegistrationError)


def test_bare_plain_string_is_rejected_whole_and_never_iterated(prebuilt_api: Any) -> None:
    """EC-3 and INV-5: a bare "calendar" raises naming 'calendar' itself, not its characters, before any tool is built."""
    with ConstructionCounter() as counter, pytest.raises(ToolRegistryError) as caught:
        prebuilt_api.tools("calendar")
    message = str(caught.value)
    assert counter.function_tools == 0
    assert "calendar" in message
    assert "'c'" not in message and "'l'" not in message, f"the string was iterated character by character: {message}"
    with pytest.raises(ToolRegistryError):
        prebuilt_api.tools("dates")


def test_select_categories_rejects_plain_strings_too(prebuilt_api: Any) -> None:
    """§8.5: the static select_categories applies the same INV-5 rule as the constructor."""
    with pytest.raises(ToolRegistryError):
        prebuilt_api.tools.select_categories(["dates"])
    with pytest.raises(ToolRegistryError):
        prebuilt_api.tools.select_categories("dates")


def test_empty_categories_give_an_empty_catalogue_and_there_is_no_default(prebuilt_api: Any) -> None:
    """AC-19 and INV-4: PrebuiltTools([]) is empty, and calling it with no argument is an error rather than the whole library."""
    empty = prebuilt_api.tools([])
    assert len(empty) == 0
    assert empty.names() == ()
    with pytest.raises(TypeError):
        prebuilt_api.tools()


def test_category_order_and_repeats_do_not_change_the_catalogue(prebuilt_api: Any) -> None:
    """INV-4 and EC-2: the result is the distinct categories in catalogue order, whatever the input order or repeats."""
    dates, text = category(prebuilt_api, "dates"), category(prebuilt_api, "text_counting")
    expected = CATEGORY_TOOL_NAMES["dates"] + CATEGORY_TOOL_NAMES["text_counting"]
    assert prebuilt_api.tools([text, dates, dates, text]).names() == expected
    assert prebuilt_api.tools((member for member in (text, dates))).names() == expected
    assert prebuilt_api.tools((dates, text)).names() == expected


def test_bare_member_is_one_category(prebuilt_api: Any) -> None:
    """EC-3 and INV-4: a member passed without a list is one category, not a string to iterate."""
    assert prebuilt_api.tools(category(prebuilt_api, "dates")).names() == CATEGORY_TOOL_NAMES["dates"]


def test_select_categories_returns_distinct_members_in_enum_order(prebuilt_api: Any) -> None:
    """§8.5: select_categories gives a tuple of distinct members in declaration order; a bare member is one category."""
    enum_class = prebuilt_api.categories
    regex, dates, finance = enum_class("regex"), enum_class("dates"), enum_class("finance")
    assert prebuilt_api.tools.select_categories([regex, dates, regex, finance]) == (finance, dates, regex)
    assert prebuilt_api.tools.select_categories(dates) == (dates,)
    assert prebuilt_api.tools.select_categories([]) == ()


def test_get_tools_builds_fresh_function_tools_in_catalogue_order(prebuilt_api: Any) -> None:
    """§8.5 and INV-6: get_tools returns new FunctionTool objects in catalogue order on every call."""
    enum_class = prebuilt_api.categories
    chosen = (enum_class("finance"), enum_class("dates"))
    first = prebuilt_api.tools.get_tools(chosen)
    second = prebuilt_api.tools.get_tools(chosen)
    assert isinstance(first, tuple)
    assert tuple(tool.name for tool in first) == CATEGORY_TOOL_NAMES["finance"] + CATEGORY_TOOL_NAMES["dates"]
    assert all(isinstance(tool, FunctionTool) for tool in first)
    assert not {id(tool) for tool in first} & {id(tool) for tool in second}


# ---- INV-6, AC-18: construction identity and merging ----


def test_two_constructions_share_no_tool_object(prebuilt_api: Any) -> None:
    """INV-6: there is no module-level cache, so two PrebuiltTools constructions never share a tool."""
    dates = category(prebuilt_api, "dates")
    first, second = prebuilt_api.tools([dates]), prebuilt_api.tools([dates])
    assert not {id(tool) for tool in first} & {id(tool) for tool in second}


def test_construction_builds_exactly_one_function_tool_per_selected_tool(prebuilt_api: Any) -> None:
    """INV-6 and §5: one FunctionTool per tool of the chosen categories, and no hidden prebuilding of the rest."""
    with ConstructionCounter() as counter:
        catalogue = prebuilt_api.tools([category(prebuilt_api, "graphs")])
    assert counter.function_tools == len(CATEGORY_TOOL_NAMES["graphs"]) == len(catalogue)


def test_overlapping_catalogues_cannot_be_merged(prebuilt_api: Any) -> None:
    """AC-18 and EC-4: Tools([a, b]) names the first duplicate tool, and a and b share no object."""
    dates, scheduling = category(prebuilt_api, "dates"), category(prebuilt_api, "scheduling")
    first, second = prebuilt_api.tools([dates, scheduling]), prebuilt_api.tools([dates])
    assert not {id(tool) for tool in first} & {id(tool) for tool in second}
    with pytest.raises(ToolRegistrationError, match="Tool already exists: days_between_dates"):
        Tools([first, second])


def test_subset_returns_a_plain_tools_catalogue_in_catalogue_order(prebuilt_library: Any) -> None:
    """§4 and §8.5: subset is inherited, returns a plain Tools in catalogue order, and shares objects with its source."""
    picked = prebuilt_library.subset(["count_character_occurrences", "days_between_dates"])
    assert type(picked) is Tools
    assert picked.names() == ("days_between_dates", "count_character_occurrences")
    assert picked[0] is library_tool(prebuilt_library, "days_between_dates")


# ---- INV-8, INV-22, §8.5: tool shape and exports ----


def test_toolsets_package_exports_prebuilt_tools_and_keeps_the_rest(prebuilt_api: Any) -> None:
    """INV-22: vidbyte.tools.toolsets.__all__ keeps CodingAgentTools and ParadigmMinimalToolset and adds only PrebuiltTools."""
    toolsets = importlib.import_module("vidbyte.tools.toolsets")
    assert sorted(toolsets.__all__) == ["CodingAgentTools", "ParadigmMinimalToolset", "PrebuiltTools"]
    assert issubclass(prebuilt_api.tools, Tools)
    assert prebuilt_api.tools.__module__ == "vidbyte.tools.toolsets.prebuilt"


@pytest.mark.parametrize(("value", "class_name", "names"), CATEGORY_TABLE, ids=CATEGORY_VALUES)
def test_category_class_lists_its_functions_in_row_order(value: str, class_name: str, names: tuple[str, ...]) -> None:
    """§8.5 and §9.2: the prebuilt package re-exports <Category>ToolFunctions, whose tool_functions() follows Appendix A."""
    package = importlib.import_module("vidbyte.tools.builtins.prebuilt")
    category_class = getattr(package, class_name)
    functions = category_class.tool_functions()
    assert isinstance(functions, tuple)
    assert tuple(function.__name__ for function in functions) == names
    assert all(function.__module__ == f"vidbyte.tools.builtins.prebuilt.{value}" for function in functions)


@pytest.mark.parametrize("name", ALL_TOOL_NAMES)
def test_tool_is_a_safe_function_tool_described_by_its_docstring(prebuilt_library: Any, name: str) -> None:
    """INV-8: a FunctionTool with SAFE permission, named after its function, described by its docstring's first paragraph."""
    tool = library_tool(prebuilt_library, name)
    assert isinstance(tool, FunctionTool)
    spec = tool.spec()
    assert spec.permission is ToolPermission.SAFE
    assert tool.func.__name__ == name == spec.name
    assert tool.func.__qualname__.split(".")[-1] == name and tool.func.__qualname__.endswith(f"ToolFunctions.{name}")
    docstring = inspect.getdoc(tool.func) or ""
    first_paragraph = docstring.split("\n\n")[0].strip()
    assert first_paragraph, f"{name} has no docstring"
    assert spec.description == first_paragraph


# ---- INV-16 and Appendix A parameters: each tool's input schema ----


def resolve_schema(prop: dict[str, Any], definitions: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return the non-null branch of a parameter schema with any $ref inlined, and whether null is accepted."""
    nullable = False
    if "anyOf" in prop:
        branches = [branch for branch in prop["anyOf"] if branch.get("type") != "null"]
        nullable = len(branches) < len(prop["anyOf"])
        assert len(branches) == 1, f"unexpected union schema {prop!r}"
        prop = {**branches[0], **{key: value for key, value in prop.items() if key != "anyOf"}}
    if "allOf" in prop and len(prop["allOf"]) == 1:
        prop = {**prop["allOf"][0], **{key: value for key, value in prop.items() if key != "allOf"}}
    if "$ref" in prop:
        enum_name = prop["$ref"].rsplit("/", 1)[-1]
        prop = {**definitions[enum_name], "ref_name": enum_name, **{key: value for key, value in prop.items() if key != "$ref"}}
    return prop, nullable


def schema_problems(name: str, row: tuple[Any, ...], prop: dict[str, Any], definitions: dict[str, Any], required: bool) -> list[str]:
    """Every way one parameter's live schema differs from its Appendix A row."""
    parameter, type_code, cap, item_cap, default = row
    resolved, _ = resolve_schema(prop, definitions)
    problems = []
    if required != (default == REQUIRED):
        problems.append(f"{parameter}: required is {required}, Appendix A says {default == REQUIRED}")
    if default != REQUIRED and prop.get("default", "<missing>") != default:
        problems.append(f"{parameter}: default {prop.get('default', '<missing>')!r}, Appendix A says {default!r}")
    if type_code.startswith("enum:"):
        enum_name = type_code.split(":", 1)[1]
        expected_values = next(values for enum, _, values in ENUM_TABLE if enum == enum_name)
        if resolved.get("ref_name") != enum_name or tuple(resolved.get("enum", ())) != expected_values:
            problems.append(f"{parameter}: expected enum {enum_name} {expected_values}, schema has {resolved!r}")
    elif (resolved.get("type"), resolved.get("format")) != JSON_TYPES[type_code]:
        problems.append(f"{parameter}: expected {JSON_TYPES[type_code]}, schema has type {resolved.get('type')!r} format {resolved.get('format')!r}")
    cap_key = "maxItems" if resolved.get("type") == "array" else "maxLength"
    if type_code == "utc_offset" and resolved.get("pattern") != UTC_OFFSET_PATTERN:
        problems.append(f"{parameter}: a UtcOffset needs the pattern {UTC_OFFSET_PATTERN!r}, schema has {resolved.get('pattern')!r}")
    if isinstance(cap, int) and resolved.get(cap_key) != cap:
        problems.append(f"{parameter}: {cap_key} is {resolved.get(cap_key)!r}, Appendix A says {cap}")
    if isinstance(item_cap, int):
        items, _ = resolve_schema(resolved.get("items", {}), definitions)
        if items.get("maxLength") != item_cap:
            problems.append(f"{parameter}: item maxLength is {items.get('maxLength')!r}, Appendix A says {item_cap}")
    if isinstance(item_cap, TextListsShape):
        items, _ = resolve_schema(resolved.get("items", {}), definitions)
        strings, _ = resolve_schema(items.get("items", {}), definitions)
        found = (resolved.get("minItems"), items.get("type"), items.get("maxItems"), strings.get("type"), strings.get("maxLength"))
        wanted = (item_cap.min_lists, "array", item_cap.list_items, "string", item_cap.item_chars)
        if found != wanted:
            problems.append(f"{parameter}: (minItems, item type, item maxItems, string type, string maxLength) is {found!r}, Appendix A says {wanted!r}")
    return problems


@pytest.mark.parametrize("name", ALL_TOOL_NAMES)
def test_tool_schema_matches_its_appendix_row(prebuilt_library: Any, name: str) -> None:
    """Appendix A parameters and INV-16: names in signature order, required flags, defaults, JSON types, enums, and caps."""
    schema = dict(library_tool(prebuilt_library, name).spec().input_schema or {})
    properties = schema.get("properties", {})
    definitions = schema.get("$defs", {})
    required = set(schema.get("required", []))
    rows = TOOL_PARAMETERS[name]
    assert tuple(properties) == tuple(row[0] for row in rows), f"{name}: parameter names or order differ"
    problems = []
    for row in rows:
        problems.extend(schema_problems(name, row, properties[row[0]], definitions, row[0] in required))
    assert not problems, f"{name}: {problems}"


@pytest.mark.parametrize("name", ALL_TOOL_NAMES)
def test_every_text_and_list_parameter_is_capped(prebuilt_library: Any, name: str) -> None:
    """INV-16: every str parameter has maxLength (spec r4 gives UtcOffset one too), and every list, and every list inside a list, has maxItems and capped string items."""
    schema = dict(library_tool(prebuilt_library, name).spec().input_schema or {})
    definitions = schema.get("$defs", {})
    for parameter, prop in schema.get("properties", {}).items():
        resolved, _ = resolve_schema(prop, definitions)
        if resolved.get("type") == "array":
            assert "maxItems" in resolved, f"{name}.{parameter} has no maxItems"
            items, _ = resolve_schema(resolved.get("items", {}), definitions)
            if items.get("type") == "array":
                assert "maxItems" in items, f"{name}.{parameter} inner lists have no maxItems"
                items, _ = resolve_schema(items.get("items", {}), definitions)
            plain_string_items = items.get("type") == "string" and "enum" not in items and "format" not in items
            assert not plain_string_items or "maxLength" in items, f"{name}.{parameter} items have no maxLength"
        elif resolved.get("type") == "string" and "enum" not in resolved and "format" not in resolved:
            assert "maxLength" in resolved, f"{name}.{parameter} has no maxLength"
