"""FILE: tests/features/harness_threads/test_harness_threads_browser_contract.py

PURPOSE: The browser functions' contract as importable names (docs/spec/harness-browser-tools/spec.md §8.5, §9.1, §9.2, §12.3): the nine exports and their signatures (AC-3, INV-2, FR-1, FR-2), the records and their checks (FR-3, §9.1), the enums and constants, the four browser.* codes mapped for every harness (FR-16, D-13), the result-record table and `expected` text (D-15, INV-16), the widened texts (D-19, D-22), the lib and hostkit exports, and the one-way imports inside each harness subpackage (D-27).
ROLE IN CODEBASE: Start here when a browser name, signature, record field, enum member, constant, code or import edge changes. Nothing here starts a stand-in.
ARCHITECTURE NOTE: Every vidbyte import goes through the browser_lib and browser_api fixtures or happens inside a test, so a missing module fails each test, not collection. Source edges are read with `ast` from the files on disk; the partial-initialisation check imports each new module first thing in a fresh interpreter, because an import cycle only shows when a module other than the package is imported first.
FUNCTION INVENTORY: annotation_text normalises an annotation to compare string and evaluated forms; parameters_of reads a function's parameters; field_names reads a dataclass's fields; module_edges resolves every import of one source file, including imports inside functions; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A spec change to a name or member updates the matching constant at the top of this file in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte at module level. 2. Do not compare annotation objects directly; a module with `from __future__ import annotations` holds strings.
KNOWN EDGE CASES: The order of the nine new NativeThreadOperation members is not spelled out by the spec (§12.3 row 3 says "for all 9"); this file assumes the plain members' order, harness then verb. The Playwright per-capability tool names are a registry pin in test_harness_threads_browser_registry.py, not here.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §8.1 D-13, D-15, D-19, D-22, D-27, §8.5, §9.1, §9.2, §9.3, §12.3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_browser_contract.py
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import importlib
import inspect
import os
import re
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
NATIVE = REPO_ROOT / "vidbyte" / "harnesses" / "native"
HARNESSES = ("grok", "opencode", "muse")
VERBS = ("run", "continue", "fork")
BROWSER_FUNCTIONS = tuple(f"{verb}_{harness}_with_browser" for harness in HARNESSES for verb in VERBS)
BROWSER_ENUMS = {
    "BrowserTool": ["playwright", "chromedevtools", "firecrawl", "exa", "tavily", "brave", "perplexity", "brightdata", "apify", "linkup", "browserbase", "jina", "parallel"],
    "BrowserToolExclusion": [
        "browserstack", "searxng", "wdio", "fetch", "duckduckgo", "agentbrowser", "playwrightcli", "midscene", "devbrowser", "crawl4ai", "browseruse",
        "scrapling", "kernel", "cloudflare", "puppeteer", "hyperbrowser", "steel", "browserless",
    ],
    "BrowserCapability": ["all", "core", "devtools", "storage", "network", "pdf", "vision", "search", "scrape", "map", "crawl", "interact", "fetch", "extract", "research", "browser"],
    "BrowserToolTransport": ["stdio", "remote"],
    "BrowserKeyRequirement": ["required", "optional", "none"],
    "BrowserToolCallStatus": ["completed", "failed"],
}
TOOL_VARIABLES = {
    "FIRECRAWL": "FIRECRAWL_API_KEY", "EXA": "EXA_API_KEY", "TAVILY": "TAVILY_API_KEY", "BRAVE": "BRAVE_API_KEY", "PERPLEXITY": "PERPLEXITY_API_KEY",
    "BRIGHTDATA": "API_TOKEN", "APIFY": "APIFY_TOKEN", "LINKUP": "LINKUP_API_KEY", "CHROME_DEVTOOLS_UPDATE_CHECKS": "CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS",
}
CREDENTIAL_WORDS = ("PASSWORD", "PASS", "PWD", "TOKEN", "SECRET", "KEY")
RECORD_FIELDS = {
    "BrowserCapabilityDefinition": ["name", "tools", "server_value"],
    "BrowserToolDefinition": [
        "tool", "transport", "package", "version", "entry", "url", "key_rule", "key_variable", "arguments", "environment", "profile_option",
        "output_option", "caps_option", "needs_chrome", "capabilities", "default_capabilities",
    ],
    "BrowserToolRequest": ["tools", "tool_keys"],
    "BrowserToolSelection": ["definition", "capabilities", "allowed", "denied", "server_capabilities", "key"],
    "BrowserServer": ["selection", "command"],
    "BrowserMount": ["servers", "folder", "artifacts"],
    "BrowserToolCall": ["tool", "name", "status"],
    "BrowserToolCalls": ["calls", "truncated"],
    "BrowserThreadResult": ["harness", "thread_id", "text", "text_truncated", "tool_calls", "tool_calls_truncated", "artifacts", "artifacts_truncated"],
}
HIDDEN_FIELDS = {"BrowserToolRequest": "tool_keys", "BrowserToolSelection": "key"}
BROWSER_PROBLEMS = {"mount_unsupported": "browser.mount_unsupported", "runtime_missing": "browser.runtime_missing", "tool_install_failed": "browser.tool_install_failed", "tools_unavailable": "browser.tools_unavailable"}
BROWSER_CONSTANTS = {
    "BROWSER_TOOLS_MAX_PER_CALL": 8, "BROWSER_TOOL_STRING_MAX_CHARS": 128, "BROWSER_TOOL_STRING_PATTERN": r"(?i)[a-z0-9-]+(:[a-z0-9-]+(,[a-z0-9-]+)*)?(@[a-z0-9-]+)?",
    "BROWSER_SUGGESTION_CUTOFF": 0.6, "BROWSER_TOOL_CALLS_MAX_ITEMS": 1000, "BROWSER_ARTIFACTS_MAX_ITEMS": 1000, "BROWSER_TOOL_CACHE_PARTS": (".vidbyte", "tools"),
    "BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS": 600.0, "BROWSER_REAP_TIMEOUT_SECONDS": 10.0, "BROWSER_NODE_MIN_VERSION": (22, 12, 0),
    "GROK_BROWSER_RULES_MAX_UNITS": 1800, "BROWSER_OPENCODE_SERVER_PREFIX": "vidbyte-", "MUSE_SETTINGS_SCHEMA_VERSION": 1, "BROWSER_FILE_ENCODING": "utf-8",
}
NATIVE_CONSTANTS = {"NATIVE_PS_PATHS": ("/bin/ps", "/usr/bin/ps"), "NATIVE_DISABLED_SWITCH": "0", "GROK_STREAMING_JSON_OUTPUT_FORMAT": "streaming-json"}
D22_CODES = ("GROK_THREAD_NOT_FOUND", "OPENCODE_THREAD_NOT_FOUND", "OPENCODE_OUTPUT_TOO_LARGE", "MUSE_THREAD_NOT_FOUND", "MUSE_OUTPUT_TOO_LARGE")
PLAIN_NAME = re.compile(r"\b(run|continue|fork)_(grok|opencode|muse)_thread\b")
HOSTKIT_NAMES = ("BrowserRuntimes", "BrowserToolCache", "NativeBrowserHarness", "NativeBrowserRun", "NativeBrowserTools")
NEW_MODULES = [
    "vidbyte.harnesses.native.hostkit.browser", *(f"vidbyte.harnesses.native.{harness}.{module}" for harness in HARNESSES for module in ("mounts", "browser")),
]
LIB_MODULES = ("vidbyte/lib/enums/browser_tools.py", "vidbyte/lib/dataclasses/browser_tools.py", "vidbyte/lib/constants/browser_tools.py", "vidbyte/lib/registries/browser_tools.py", "vidbyte/lib/process/reaper.py")
# Inside a harness subpackage, a module may import only these siblings
# (D-27: browser -> threads -> wire -> mounts; Muse's launcher sits
# below threads and browser, as on main).
# The sibling modules each module of a harness subpackage may import.
# The thread helpers' modules (PR #1147) sit beside the browser chain:
# commands runs a thread, helpers reads the store or a child, and store
# and children sit just above wire and launcher. No entry names browser.
ALLOWED_SIBLINGS = {
    "mounts": set(),
    "launcher": set(),
    "wire": {"mounts"},
    "store": {"wire"},
    "children": {"launcher"},
    "helpers": {"wire", "store", "children", "launcher"},
    "threads": {"wire", "mounts", "launcher", "store", "children"},
    "commands": {"threads", "helpers", "store", "wire"},
    "browser": {"threads", "wire", "mounts", "launcher"},
}
TOOL_KEYS_ANNOTATIONS = {"Mapping[str,str]|None", "None|Mapping[str,str]", "Optional[Mapping[str,str]]"}
IMPORT_SECONDS = 180


def annotation_text(annotation: Any) -> str:
    # "collections.abc.Sequence[str]" and the string "Sequence[str]"
    # compare equal once module qualifiers and spaces are dropped.
    text = annotation if isinstance(annotation, str) else inspect.formatannotation(annotation)
    return re.sub(r"\b(?:[A-Za-z_]\w*\.)+(?=[A-Za-z_])", "", text).replace(" ", "")


def parameters_of(function: Any) -> list[inspect.Parameter]:
    return list(inspect.signature(function).parameters.values())


def field_names(cls: type) -> list[str]:
    return [field.name for field in dataclasses.fields(cls)]


def module_edges(path: Path) -> list[tuple[str, bool]]:
    # (absolute module, nested inside a function or class) for every
    # import; `from package import name` also yields package.name.
    package = list(path.relative_to(REPO_ROOT).with_suffix("").parts[:-1])
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nested_ids = {id(node) for owner in ast.walk(tree) if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in ast.walk(owner) if node is not owner}
    edges: list[tuple[str, bool]] = []
    for node in ast.walk(tree):
        nested = id(node) in nested_ids
        if isinstance(node, ast.Import):
            edges.extend((alias.name, nested) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join([*package[: len(package) - (node.level - 1)], *([node.module] if node.module else [])])
            edges.append((base, nested))
            edges.extend((f"{base}.{alias.name}", nested) for alias in node.names)
    return edges


def test_native_and_subpackages_export_the_browser_functions(browser_api) -> None:
    # AC-3 / FR-1 / §9.2: the nine functions and the two records at the
    # native level; each subpackage binds its three, the same objects.
    native = browser_api.native
    for name in (*BROWSER_FUNCTIONS, "BrowserThreadResult", "BrowserToolCall"):
        assert name in native.__all__, name
    assert native.BrowserThreadResult is browser_api.BrowserThreadResult and native.BrowserToolCall is browser_api.BrowserToolCall
    for harness in HARNESSES:
        subpackage = importlib.import_module(f"vidbyte.harnesses.native.{harness}")
        for verb in VERBS:
            name = f"{verb}_{harness}_with_browser"
            assert name in subpackage.__all__ and getattr(subpackage, name) is getattr(native, name), name
    # §9.2 also kept these names out of the root, but #1179's contract
    # re-exports every native name from `vidbyte` (pinned in
    # tests/features/root_native_thread_exports/), so only
    # vidbyte.harnesses stays untouched.
    harnesses = importlib.import_module("vidbyte.harnesses")
    assert not set(getattr(harnesses, "__all__", ())) & {*BROWSER_FUNCTIONS, "BrowserThreadResult", "BrowserToolCall"}, "§9.2: nothing is added to vidbyte.harnesses"


def test_browser_functions_take_the_plain_parameters_with_tools_after_model(browser_api) -> None:
    # INV-2 / FR-2 / AC-3: same names, kinds, defaults and types as the
    # plain sibling, with keyword-only tools (required) and tool_keys
    # (None) inserted directly after model.
    for (harness, verb), function in browser_api.functions.items():
        name = f"{verb}_{harness}_with_browser"
        assert inspect.iscoroutinefunction(function), name
        plain = parameters_of(browser_api.plain[(harness, verb)])
        browser = parameters_of(function)
        at = [parameter.name for parameter in plain].index("model") + 1
        assert [parameter.name for parameter in browser] == [*(p.name for p in plain[:at]), "tools", "tool_keys", *(p.name for p in plain[at:])], name
        shared = [parameter for parameter in browser if parameter.name not in ("tools", "tool_keys")]
        for mine, theirs in zip(shared, plain):
            assert (mine.kind, mine.default) == (theirs.kind, theirs.default), f"{name}.{mine.name}"
            assert annotation_text(mine.annotation) == annotation_text(theirs.annotation), f"{name}.{mine.name}"
        tools, tool_keys = browser[at], browser[at + 1]
        assert tools.kind is inspect.Parameter.KEYWORD_ONLY and tools.default is inspect.Parameter.empty, name
        assert tool_keys.kind is inspect.Parameter.KEYWORD_ONLY and tool_keys.default is None, name
        assert annotation_text(tools.annotation) == "Sequence[str]", name
        assert annotation_text(tool_keys.annotation) in TOOL_KEYS_ANNOTATIONS, name
        assert annotation_text(inspect.signature(function).return_annotation) == "BrowserThreadResult", name


def test_browser_records_are_frozen_slotted_dataclasses_with_the_spec_fields(browser_lib) -> None:
    # §8.5 / §9.1 / FR-3: the nine records, field order included; the
    # key fields are hidden from repr.
    for name, fields in RECORD_FIELDS.items():
        cls = getattr(browser_lib.browser_records, name)
        assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen, name
        assert "__slots__" in vars(cls), f"{name} must be slotted"
        assert field_names(cls) == fields, name
        assert name in browser_lib.browser_records.__all__, name
    for name, hidden in HIDDEN_FIELDS.items():
        field = next(field for field in dataclasses.fields(getattr(browser_lib.browser_records, name)) if field.name == hidden)
        assert field.repr is False, f"{name}.{hidden} must be repr=False"
    run = browser_lib.records.NativeThreadRun
    assert dataclasses.is_dataclass(run) and run.__dataclass_params__.frozen and field_names(run) == ["result", "outcome"]
    assert "NativeThreadRun" in browser_lib.records.__all__


def test_tool_call_and_result_records_refuse_bad_values(browser_lib, tmp_path) -> None:
    # §9.1: a call name follows NATIVE_NAME_PATTERN within 64; a result
    # has a pattern thread id, capped tuples and absolute artifacts.
    lib = browser_lib
    call = lib.BrowserToolCall(tool=lib.BrowserTool.PLAYWRIGHT, name="browser_navigate", status=lib.BrowserToolCallStatus.COMPLETED)
    for bad_name in ("browser navigate", "_leading", "n" * 65, ""):
        with pytest.raises(lib.ConfigurationError):
            lib.BrowserToolCall(tool=lib.BrowserTool.PLAYWRIGHT, name=bad_name, status=lib.BrowserToolCallStatus.COMPLETED)
    good = {"harness": lib.enums.NativeHarness.OPENCODE, "thread_id": "ses_0001", "text": "done", "text_truncated": False, "tool_calls": (call,), "tool_calls_truncated": False, "artifacts": (tmp_path / "page.png",), "artifacts_truncated": False}
    assert lib.BrowserThreadResult(**good).tool_calls == (call,)
    cap = lib.browser_constants.BROWSER_TOOL_CALLS_MAX_ITEMS
    for change in ({"thread_id": "has space"}, {"artifacts": (Path("relative.png"),)}, {"tool_calls": (call,) * (cap + 1)}):
        with pytest.raises(lib.ConfigurationError):
            lib.BrowserThreadResult(**{**good, **change})
    with pytest.raises(lib.ConfigurationError):
        lib.browser_records.BrowserToolCalls(calls=(call,) * (cap + 1), truncated=True)
    outcome = lib.CliOutcome(exit_code=0, stdout="", stderr="", stdout_truncated=False, stderr_truncated=False, timed_out=False)
    with pytest.raises(lib.ConfigurationError):
        lib.records.NativeThreadRun(result="not a result", outcome=outcome)


def test_browser_enums_are_exported_str_enums_with_the_spec_members(browser_lib) -> None:
    # §9.1 / §12.3 rows 1-3: members in order; exported from
    # vidbyte.lib.enums; no member name ends in a credential word
    # (S054).
    package = browser_lib.enums_package
    for name, values in BROWSER_ENUMS.items():
        cls = getattr(browser_lib.browser_enums, name)
        assert issubclass(cls, enum.StrEnum) and [member.value for member in cls] == values, name
        assert getattr(package, name) is cls and name in package.__all__, name
    variable = browser_lib.browser_enums.BrowserToolVariable
    assert issubclass(variable, enum.StrEnum) and {member.name: member.value for member in variable} == TOOL_VARIABLES
    assert package.BrowserToolVariable is variable and "BrowserToolVariable" in package.__all__
    assert not [member.name for member in variable if member.name.endswith(CREDENTIAL_WORDS)]
    record = browser_lib.enums.NativeThreadResultRecord
    # The browser record follows the plain one; the thread helpers'
    # records (PR #1147) come after both.
    assert issubclass(record, enum.StrEnum) and list({member.name: member.value for member in record}.items())[:2] == [("NATIVE_THREAD_RESULT", "NativeThreadResult"), ("BROWSER_THREAD_RESULT", "BrowserThreadResult")]
    assert package.NativeThreadResultRecord is record and "NativeThreadResultRecord" in browser_lib.enums.__all__


def test_browser_codes_follow_main_and_map_for_every_harness(browser_lib) -> None:
    # FR-16 / D-13 / §12.3 rows 4 and 8: four codes right after
    # MUSE_WSL_UNAVAILABLE (the thread helpers' codes follow them), one
    # pair per harness and problem, each with its own likely cause and
    # next step.
    lib = browser_lib
    members = list(lib.FailureCode)
    names = [member.name for member in members]
    start = names.index("MUSE_WSL_UNAVAILABLE") + 1
    assert [member.value for member in members[start : start + len(BROWSER_PROBLEMS)]] == list(BROWSER_PROBLEMS.values())
    table = lib.constants.NATIVE_THREAD_FAILURE_CODES
    for problem, code in BROWSER_PROBLEMS.items():
        for harness in lib.enums.NativeHarness:
            assert table[(harness, lib.enums.NativeThreadProblem(problem))] is lib.FailureCode(code), (harness, problem)
    causes, steps = lib.constants.NATIVE_THREAD_LIKELY_CAUSES, lib.constants.NATIVE_THREAD_NEXT_STEPS
    browser_codes = [lib.FailureCode(code) for code in BROWSER_PROBLEMS.values()]
    assert len({causes[code] for code in browser_codes}) == 4 and len({steps[code] for code in browser_codes}) == 4


def test_result_record_table_covers_every_operation(browser_api) -> None:
    # D-15 / §9.2: one entry per operation, naming what the function
    # of that name is annotated to return, so an error's `expected`
    # text never disagrees with the signature (browser ones name
    # BrowserThreadResult, plain ones NativeThreadResult, and the
    # thread helpers their summaries, command output or None).
    lib = browser_api
    table = lib.constants.NATIVE_THREAD_RESULT_RECORDS
    record = lib.enums.NativeThreadResultRecord
    assert isinstance(table, types.MappingProxyType) and set(table) == set(lib.enums.NativeThreadOperation)
    annotated = {
        "NativeThreadResult": record.NATIVE_THREAD_RESULT,
        "BrowserThreadResult": record.BROWSER_THREAD_RESULT,
        "NativeThreadSummary": record.NATIVE_THREAD_SUMMARY,
        "tuple[NativeThreadSummary, ...]": record.NATIVE_THREAD_SUMMARIES,
        "NativeCommandOutput": record.NATIVE_COMMAND_OUTPUT,
        "None": record.NO_RESULT,
    }
    for operation, value in table.items():
        returns = inspect.signature(getattr(lib.native, operation.value)).return_annotation
        assert value is annotated[returns], (operation, returns)
    assert all(table[lib.enums.NativeThreadOperation(name)] is record.BROWSER_THREAD_RESULT for name in BROWSER_FUNCTIONS)


def test_native_thread_error_expected_names_the_result_record(browser_lib) -> None:
    # D-15 / INV-16: result_record=None keeps today's text byte for
    # byte; the browser record names BrowserThreadResult.
    lib = browser_lib
    operation = lib.enums.NativeThreadOperation("run_opencode_with_browser")
    common = {"failure_code": lib.FailureCode.BROWSER_TOOLS_UNAVAILABLE, "harness": lib.enums.NativeHarness.OPENCODE, "operation": operation, "next_step": "Do this.", "likely_cause": "That happened."}
    default = lib.NativeThreadError("Message.", **common)
    assert lib.NativeThreadError("Message.", result_record=None, **common).expected == default.expected == "run_opencode_with_browser returning a NativeThreadResult"
    browser = lib.NativeThreadError("Message.", result_record=lib.enums.NativeThreadResultRecord.BROWSER_THREAD_RESULT, **common)
    assert browser.expected == "run_opencode_with_browser returning a BrowserThreadResult" and browser.details["expected"] == browser.expected


def test_widened_texts_name_both_grok_caps_and_the_browser_siblings(browser_lib) -> None:
    # D-19: the grok.output_too_large cause names both caps. D-22 /
    # EC-31: each of the five next steps that names a plain function
    # also names its _with_browser sibling.
    lib = browser_lib
    cause = lib.constants.NATIVE_THREAD_LIKELY_CAUSES[lib.FailureCode.GROK_OUTPUT_TOO_LARGE]
    assert "GROK_CLI_MAX_OUTPUT_BYTES" in cause and "NATIVE_PROCESS_MAX_OUTPUT_BYTES" in cause
    for name in D22_CODES:
        text = lib.constants.NATIVE_THREAD_NEXT_STEPS[lib.FailureCode[name]]
        plain = sorted({match.group(0) for match in PLAIN_NAME.finditer(text)})
        assert plain, f"{name}: the next step still names a plain function"
        missing = [function.replace("_thread", "_with_browser") for function in plain if function.replace("_thread", "_with_browser") not in text]
        assert missing == [], f"{name}: the next step names {plain} but not {missing}"


def test_browser_constants_hold_the_spec_values(browser_lib) -> None:
    # §9.1 / §9.3 / §12.3 rows 7-8: the bounds, names and switches; one
    # non-empty reason per exclusion; Chrome's searched locations are a
    # tuple of path strings read at call time (the spec names no
    # constant for them; see this file's header).
    lib = browser_lib
    for name, value in BROWSER_CONSTANTS.items():
        assert getattr(lib.browser_constants, name) == value, name
    for name, value in NATIVE_CONSTANTS.items():
        assert getattr(lib.constants, name) == value, name
    reasons = lib.browser_constants.BROWSER_TOOL_EXCLUSION_REASONS
    assert set(reasons) == set(lib.browser_enums.BrowserToolExclusion)
    assert all(isinstance(text, str) and text.strip() for text in reasons.values())
    chrome = lib.browser_constants.BROWSER_CHROME_PATHS
    assert isinstance(chrome, tuple) and chrome and all(isinstance(path, str) and path for path in chrome)


def test_lib_and_hostkit_export_the_new_helpers(browser_lib) -> None:
    # §9.2 / §12.3 rows 11, 14, 17.
    registries = importlib.import_module("vidbyte.lib.registries")
    assert registries.BrowserToolRegistry is browser_lib.BrowserToolRegistry and "BrowserToolRegistry" in registries.__all__
    assert "ProcessReaper" in browser_lib.process.__all__
    reaper = browser_lib.process.ProcessReaper
    assert inspect.iscoroutinefunction(reaper.reap)
    assert [parameter.name for parameter in parameters_of(reaper.reap)] == ["marker", "timeout_seconds"]
    assert parameters_of(reaper.reap)[1].kind is inspect.Parameter.KEYWORD_ONLY
    hostkit = importlib.import_module("vidbyte.harnesses.native.hostkit")
    assert set(HOSTKIT_NAMES) <= set(hostkit.__all__)
    registry = browser_lib.BrowserToolRegistry
    assert isinstance(inspect.getattr_static(registry, "select"), classmethod) and isinstance(inspect.getattr_static(registry, "definition"), classmethod)


@pytest.mark.parametrize("harness", HARNESSES)
def test_harness_subpackage_imports_run_one_way(harness) -> None:
    # D-27 / §12.4: browser -> threads -> wire -> mounts, with the
    # helpers' modules layered beside them (ALLOWED_SIBLINGS); mounts
    # imports nothing from its subpackage; nothing but __init__ imports
    # browser; no import hides inside a function.
    folder = NATIVE / harness
    for module in ("mounts", "browser"):
        assert (folder / f"{module}.py").is_file(), f"§12.3 adds {harness}/{module}.py"
    prefix = f"vidbyte.harnesses.native.{harness}."
    siblings = {path.stem for path in folder.glob("*.py") if path.stem != "__init__"}
    for path in sorted(folder.glob("*.py")):
        if path.stem == "__init__":
            continue
        edges = module_edges(path)
        reached = {target[len(prefix) :].split(".", 1)[0] for target, _ in edges if target.startswith(prefix)} & siblings
        if path.stem in ALLOWED_SIBLINGS:
            assert reached <= ALLOWED_SIBLINGS[path.stem], f"{harness}/{path.name} imports {sorted(reached - ALLOWED_SIBLINGS[path.stem])}"
        else:
            assert not reached & {"browser", "threads", "wire", "mounts"}, f"{harness}/{path.name} imports {sorted(reached)}"
        assert f"vidbyte.harnesses.native.{harness}" not in {target for target, _ in edges}, f"{harness}/{path.name} imports its own package"
        if path.stem in ("mounts", "browser"):
            assert [target for target, nested in edges if nested] == [], f"{harness}/{path.name} hides an import inside a function or class"
        others = [target for target, _ in edges for other in HARNESSES if other != harness and target.startswith(f"vidbyte.harnesses.native.{other}")]
        assert others == [], f"{harness}/{path.name} reaches another harness: {others}"


def test_hostkit_browser_and_lib_modules_import_only_downward() -> None:
    # D-27 / AGENTS.md principle 3: hostkit/browser.py imports concrete
    # hostkit modules, never the facade or a harness; the new lib
    # modules import nothing above vidbyte.lib.
    path = NATIVE / "hostkit" / "browser.py"
    assert path.is_file(), "§12.3 row 16 adds hostkit/browser.py"
    edges = module_edges(path)
    targets = {target for target, _ in edges}
    assert "vidbyte.harnesses.native.hostkit" not in targets, "hostkit/browser.py imports the hostkit facade that imports it"
    assert not [target for target in targets for harness in HARNESSES if target.startswith(f"vidbyte.harnesses.native.{harness}")]
    assert [target for target, nested in edges if nested] == []
    for relative in LIB_MODULES:
        source = REPO_ROOT / relative
        assert source.is_file(), f"§12.3 adds {relative}"
        upward = [target for target, _ in module_edges(source) if target.startswith("vidbyte.") and not target.startswith("vidbyte.lib")]
        assert upward == [], f"{relative} imports above vidbyte.lib: {upward}"


@pytest.mark.parametrize("module", NEW_MODULES)
def test_each_new_module_imports_first_in_a_fresh_interpreter(module) -> None:
    # D-27: a cycle shows only when a module other than the package is
    # imported first; every entry point must load, and the nine plain
    # functions must stay importable.
    probe = f"import {module}\nfrom vidbyte.harnesses.native import run_grok_thread, run_opencode_with_browser\nprint('ok')\n"
    finished = subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT, env={**os.environ, "PYTHONPATH": str(REPO_ROOT)}, capture_output=True, text=True, timeout=IMPORT_SECONDS, stdin=subprocess.DEVNULL, check=False)
    assert finished.returncode == 0 and finished.stdout.strip().endswith("ok"), finished.stderr[-2000:]
