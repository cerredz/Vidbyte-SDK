"""FILE: tests/features/prebuilt_tools/test_prebuilt_determinism.py

PURPOSE: Prove that prebuilt tool outputs are byte-identical across interpreters with different PYTHONHASHSEED values, working directories, time zones, and locales, and across repeated calls (AC-10, INV-12).
ROLE IN CODEBASE: Runs one battery of calls against vidbyte.tools.toolsets.PrebuiltTools in two child interpreters and in the pytest process, then compares every status, error type, and output text.
ARCHITECTURE NOTE: The battery leans on inputs where set or dict iteration order would leak into output: dozens of distinct strings with tied counts, many graph nodes, records with many keys, and many imports. Strings hash differently under different seeds, so an order that comes from a set shows up as a difference.
FUNCTION INVENTORY: soup_arguments rewrites one tool's arguments to use many distinct strings; battery builds the full call list; run_children runs it in a child interpreter; test_outputs_match_across_hash_seeds_and_environments covers AC-10; test_repeated_calls_in_one_process_are_identical covers the "earlier calls" clause of INV-12.
COMMON MODIFICATION PATTERNS: Add a targeted call to TARGETED_CALLS when a new tool reports grouped, counted, or deduplicated output.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare across Python versions; EC-24, EC-25, EC-26, and EC-38 allow those to differ. 2. Do not set the same PYTHONHASHSEED in both children; the point is that it differs.
KNOWN EDGE CASES: Child output travels as ASCII-escaped JSON, so non-ASCII text cannot be damaged by a console code page. The children run in separate empty directories so the working directory differs too. Windows ignores TZ for most purposes, which only makes that part of the check weaker there, never wrong.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (INV-12, AC-10, §9.2 item 14)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_determinism.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from tests.features.prebuilt_tools.prebuilt_catalogue_data import ALL_TOOL_NAMES
from tests.features.prebuilt_tools.prebuilt_tool_harness import SchemaArgumentFactory, ToolRunner

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CHILD_TIMEOUT_SECONDS = 600
SOUP_WORDS = [f"w{(index * 17) % 40:02d}" for index in range(40)] + [f"w{(index * 7) % 40:02d}" for index in range(0, 40, 3)]
SOUP_TEXT = " ".join(SOUP_WORDS) + ". " + " ".join(reversed(SOUP_WORDS)) + "! Zebra apple Mango kiwi."
SOUP_RECORDS = json.dumps([{"group": f"g{index % 7}", f"k{(index * 11) % 40}": index, "name": f"n{(index * 13) % 40}"} for index in range(40)])
SOUP_CSV = "group,name,value\n" + "".join(f"g{index % 7},n{(index * 13) % 40},{index % 5}\n" for index in range(40))
SOUP_SOURCE = "".join(f"import mod{(index * 7) % 30}\n" for index in range(30)) + "".join(f"from pkg{index % 5} import name{index}\n" for index in range(20))
NODE_SOURCES = [f"n{(index * 13) % 50:02d}" for index in range(45)]
NODE_TARGETS = [f"n{(index * 13 + 7) % 50:02d}" if index % 4 else f"m{index:02d}" for index in range(45)]
TARGETED_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("count_item_frequencies", {"items": SOUP_WORDS}),
    ("word_frequencies", {"text": SOUP_TEXT}),
    ("connected_components", {"sources": NODE_SOURCES, "targets": NODE_TARGETS}),
    ("topological_sort", {"sources": [f"t{index:02d}" for index in range(30)], "targets": [f"u{(index * 7) % 30:02d}" for index in range(30)]}),
    ("group_records_by_field", {"records_json": SOUP_RECORDS, "field": "group"}),
    ("detect_scripts_in_text", {"text": "Hello мир κόσμος 世界 שלום مرحبا नमस्ते Straße"}),
    ("list_python_imports", {"source": SOUP_SOURCE}),
]

CHILD_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import json
    import sys

    from vidbyte.lib.enums import PrebuiltToolCategory
    from vidbyte.tools.toolsets import PrebuiltTools
    from vidbyte.tools.types import ToolCall

    library = {tool.name: tool for tool in PrebuiltTools(PrebuiltToolCategory)}
    calls = json.loads(sys.stdin.read())

    async def run_all():
        results = []
        for name, arguments in calls:
            result = await library[name].execute(ToolCall(name, arguments))
            results.append([result.status.value, result.metadata.get("error_type"), result.output])
        return results

    sys.stdout.write(json.dumps(asyncio.run(run_all()), ensure_ascii=True))
    """
)


def plain_string(prop: dict[str, Any]) -> bool:
    return prop.get("type") == "string" and not {"enum", "format", "pattern"} & set(prop)


def soup_value(parameter: str, prop: dict[str, Any]) -> Any:
    """A many-distinct-strings value for one parameter, or None when the schema cannot take one."""
    if "anyOf" in prop:
        prop = next(branch for branch in prop["anyOf"] if branch.get("type") != "null")
    if prop.get("type") == "array" and plain_string(prop.get("items", {})):
        items = prop["items"]
        words = [word for word in SOUP_WORDS if items.get("minLength", 0) <= len(word) <= items.get("maxLength", 10_000)]
        return words[: prop.get("maxItems", len(words))] if len(words) >= prop.get("minItems", 0) else None
    if not plain_string(prop):
        return None
    if "json" in parameter or "records" in parameter:
        text = SOUP_RECORDS
    elif "csv" in parameter:
        text = SOUP_CSV
    elif "source" in parameter:
        text = SOUP_SOURCE
    else:
        text = SOUP_TEXT
    return text if prop.get("minLength", 0) <= len(text) <= prop.get("maxLength", sys.maxsize) else None


def soup_arguments(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """The tool's first full argument set with every text and string-list argument replaced by many distinct strings."""
    arguments = SchemaArgumentFactory().argument_sets(name, schema)[1]
    for parameter, prop in schema.get("properties", {}).items():
        value = soup_value(parameter, prop)
        if value is not None:
            arguments[parameter] = value
    return arguments


def battery(tool_runner: ToolRunner) -> list[tuple[str, dict[str, Any]]]:
    """Targeted order-sensitive calls, then three argument sets for every tool in the library."""
    calls = list(TARGETED_CALLS)
    for name in ALL_TOOL_NAMES:
        schema = dict(tool_runner.tool(name).spec().input_schema or {})
        argument_sets = SchemaArgumentFactory().argument_sets(name, schema)
        calls.extend((name, arguments) for arguments in (soup_arguments(name, schema), argument_sets[0], argument_sets[2]))
    return calls


def child_environment(hash_seed: str, time_zone: str, locale_name: str) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.upper().endswith("_API_KEY")}
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join([str(REPOSITORY_ROOT), existing] if existing else [str(REPOSITORY_ROOT)])
    environment.update({"PYTHONHASHSEED": hash_seed, "TZ": time_zone, "LC_ALL": locale_name, "LANG": locale_name, "PYTHONIOENCODING": "utf-8"})
    return environment


def run_children(calls: list[tuple[str, dict[str, Any]]], working_directory: Path, environment: dict[str, str]) -> list[list[Any]]:
    """Run the battery in a fresh interpreter and return [status, error_type, output] per call."""
    working_directory.mkdir()
    completed = subprocess.run(
        [sys.executable, "-c", CHILD_SCRIPT],
        input=json.dumps(calls),
        cwd=working_directory,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=CHILD_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    return json.loads(completed.stdout)


def first_difference(calls: list[tuple[str, dict[str, Any]]], left: list[list[Any]], right: list[list[Any]]) -> str | None:
    for (name, arguments), one, other in zip(calls, left, right, strict=True):
        if one != other:
            return f"{name}({json.dumps(arguments)[:200]}): {json.dumps(one)[:400]} != {json.dumps(other)[:400]}"
    return None


def test_outputs_match_across_hash_seeds_and_environments(tool_runner: ToolRunner, tmp_path: Path) -> None:
    """AC-10 and INV-12: two interpreters with different hash seeds, directories, time zones, and locales give identical bytes."""
    calls = battery(tool_runner)
    first = run_children(calls, tmp_path / "first", child_environment("0", "UTC", "C"))
    second = run_children(calls, tmp_path / "second", child_environment("4242", "America/New_York", "de_DE.UTF-8"))
    local = [[result.status.value, result.metadata.get("error_type"), result.output] for result in (tool_runner.result(name, arguments) for name, arguments in calls)]
    assert len(first) == len(second) == len(local) == len(calls)
    assert first_difference(calls, first, second) is None, first_difference(calls, first, second)
    assert first_difference(calls, first, local) is None, first_difference(calls, first, local)


def test_repeated_calls_in_one_process_are_identical(tool_runner: ToolRunner) -> None:
    """INV-12: a call's output does not depend on earlier calls, so the targeted battery gives the same bytes twice."""
    outputs = [tool_runner.result(name, arguments).output for name, arguments in TARGETED_CALLS]
    again = [tool_runner.result(name, arguments).output for name, arguments in TARGETED_CALLS]
    assert outputs == again
