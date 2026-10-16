"""FILE: tests/features/harness_threads/test_harness_threads_helper_surface.py

PURPOSE: The contract of the 47 thread helpers and skill functions that needs no stand-in: their signatures and named defaults (§8.5, D-15), keyless helpers (INV-2, AC-10), one NativeThreadOperation per function named after it (INV-5, §9.1), the §9.3 tables, the exported records NativeThreadSummary and NativeCommandOutput (§9.1), RecordFieldConverter.to_utc_datetime (D-13, EC-14, EC-15), the new and widened error texts (AC-20, §12.4), and the root export lists left alone (INV-1).
ROLE IN CODEBASE: Start here when a helper or skill function's parameters, a default, a record rule or an error text changes. Nothing here starts a process.
ARCHITECTURE NOTE: Expected signatures are written out from spec §8.5 as (name, kind, default) rows, with the named defaults resolved from vidbyte.lib.constants.native_threads, so a literal default or a reordered keyword fails here. Error texts are checked only for the tokens the spec names verbatim (`timeout_seconds`, the control timeout, `transcript`, both Grok caps, `grok inspect --json`, `collidesWith`, `features.video_gen`, compaction, the scan cap), each accepted as the constant's name or its value.
FUNCTION INVENTORY: tail builds a keyword-only tail; expected_signatures holds the §8.5 table; kind maps an inspect kind to P or K; spellings lists the acceptable renderings of a numeric constant; git and literal_all read the merge base; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new parameter is a spec change first (§8.5), then one row here.
WHAT NOT TO DO IN THIS FILE: Do not import vidbyte at module level; do not compare whole free texts (see test_harness_threads_errors.py for the per-code text tables).
KNOWN EDGE CASES: `skills=()` defaults are compared by value, so a list default would fail as intended (a mutable default). GROK_GOAL_RESERVED_WORDS is compared as a set because the spec fixes its members, not a container type.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-1, INV-2, INV-5, §6.2 AC-10, AC-20, §6.3 EC-14, EC-15, §8.5, §9.1, §9.3, §12.4
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_helper_surface.py
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import subprocess
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIRED = inspect.Parameter.empty
GROK_HELPERS = ["list_grok_threads", "list_recent_grok_threads", "list_grok_threads_since", "get_grok_thread", "read_grok_thread", "get_grok_thread_lineage", "search_grok_threads", "delete_grok_thread"]
OPENCODE_HELPERS = [name.replace("grok", "opencode") for name in GROK_HELPERS]
MUSE_HELPERS = ["list_muse_threads", "list_recent_muse_threads", "list_muse_threads_since", "get_muse_thread", "read_muse_thread", "get_muse_thread_lineage"]
KEYLESS = [*GROK_HELPERS, *OPENCODE_HELPERS, *MUSE_HELPERS, "init_muse_workspace"]
SUMMARY = {"harness": "grok", "thread_id": "thread-0001", "title": "A title", "parent_thread_id": "thread-0000", "model": "grok-build-fast-1"}
PLUS_TWO = timezone(timedelta(hours=2))


def tail(model: object = None) -> list[tuple[str, str, object]]:
    # The keyword-only tail of #1036's run functions (K_GROK, K_MUSE;
    # K_OPENCODE requires model).
    return [("api_key", "K", REQUIRED), ("workspace", "K", REQUIRED), ("model", "K", model), ("skills", "K", ()), ("config", "K", None)]


def expected_signatures(constants, scope) -> dict[str, list[tuple[str, str, object]]]:
    listed, recent = constants.NATIVE_LIST_DEFAULT_LIMIT, constants.NATIVE_RECENT_DEFAULT_LIMIT
    table: dict[str, list[tuple[str, str, object]]] = {}
    for harness in ("grok", "opencode", "muse"):
        last = [("scope", "K", scope)] if harness == "grok" else [("config", "K", None)]
        one = [("thread_id", "P", REQUIRED), ("workspace", "P", REQUIRED)]
        table[f"list_{harness}_threads"] = [("workspace", "P", REQUIRED), ("since", "K", None), ("limit", "K", listed), *last]
        table[f"list_recent_{harness}_threads"] = [("workspace", "P", REQUIRED), ("limit", "K", recent), *last]
        table[f"list_{harness}_threads_since"] = [("workspace", "P", REQUIRED), ("since", "P", REQUIRED), ("limit", "K", listed), *last]
        table[f"get_{harness}_thread"] = [*one, *last]
        table[f"get_{harness}_thread_lineage"] = [*one, *last]
        table[f"read_{harness}_thread"] = [*one, *last, *([("config", "K", None)] if harness == "grok" else [])]
        if harness != "muse":
            table[f"search_{harness}_threads"] = [("workspace", "P", REQUIRED), ("query", "P", REQUIRED), ("limit", "K", listed), *last]
            table[f"delete_{harness}_thread"] = [*one, *last, *([("config", "K", None)] if harness == "grok" else [])]
    grok, opencode, muse = tail(), tail(REQUIRED), tail()
    table["run_grok_command"] = [("command", "P", REQUIRED), ("arguments", "P", ""), *grok]
    table["run_grok_goal"] = [("objective", "P", REQUIRED), *grok[:2], ("budget_tokens", "K", None), *grok[2:]]
    table["run_grok_implement"] = [("task", "P", REQUIRED), *grok[:2], ("effort", "K", None), *grok[2:]]
    table["run_grok_execute_plan"] = [("design_doc", "P", REQUIRED), *grok[:2], ("effort", "K", None), ("concurrency", "K", None), ("dry_run", "K", False), ("auto_pr", "K", False), *grok[2:]]
    table["run_grok_review"] = [*grok[:2], ("local", "K", False), ("branch", "K", None), ("pr", "K", None), *grok[2:]]
    table["run_grok_code_review"] = list(grok)
    for name, text in (("design", "description"), ("resume_claude", "session"), ("resume_codex", "session"), ("resume_cursor", "session"), ("imagine", "description"), ("imagine_video", "description"), ("plan", "task"), ("explore", "question")):
        table[f"run_grok_{name}"] = [(text, "P", REQUIRED), *grok]
    table["run_opencode_command"] = [("command", "P", REQUIRED), ("arguments", "P", ""), *opencode]
    table["run_opencode_review"] = [("target", "P", None), *opencode]
    table["run_opencode_init"] = list(opencode)
    table["run_opencode_plan"] = [("task", "P", REQUIRED), *opencode]
    table["run_muse_skill"] = [("skill", "P", REQUIRED), ("prompt", "P", REQUIRED), *muse]
    for name, text in (("goal", "objective"), ("plan", "task"), ("import", "session_ref"), ("scaffold", "description"), ("browser_app", "description")):
        table[f"run_muse_{name}"] = [(text, "P", REQUIRED), *muse]
    table["init_muse_workspace"] = [("workspace", "P", REQUIRED), ("dry_run", "K", False), ("config", "K", None)]
    return table


def kind(parameter: inspect.Parameter) -> str:
    return "K" if parameter.kind is inspect.Parameter.KEYWORD_ONLY else "P" if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD) else parameter.kind.name


def spellings(name: str, value: float) -> tuple[str, ...]:
    # A numeric constant named in a text: its name, or its value as a
    # number, grouped, in MiB, or in seconds.
    found = [name, str(value), f"{value:,}"]
    if isinstance(value, float) and value.is_integer():
        found += [str(int(value)), f"{int(value)} second"]
    if isinstance(value, int) and value % 1048576 == 0:
        found += [f"{value // 1048576} MiB", f"{value // 1048576} MB"]
    return tuple(found)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, check=False)


def literal_all(source: str) -> list[str]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            return list(ast.literal_eval(node.value))
    raise AssertionError("no literal __all__")


def test_new_functions_are_coroutines_with_the_spec_signatures(api) -> None:
    # §8.5 / D-15: helpers take workspace (and thread_id) positionally,
    # skill functions take api_key and workspace keyword-only, and
    # every default is the named constant or enum member.
    table = expected_signatures(api.constants, api.enums.GrokThreadScope.SDK)
    assert len(table) == 47
    wrong = {}
    for name, expected in table.items():
        function = getattr(api.native, name)
        assert inspect.iscoroutinefunction(function), f"{name} must be an async function"
        actual = [(parameter.name, kind(parameter), parameter.default) for parameter in inspect.signature(function).parameters.values()]
        if actual != expected:
            wrong[name] = actual
    assert wrong == {}, f"§8.5 signatures differ: {wrong}"
    for name in GROK_HELPERS:
        scope = inspect.signature(getattr(api.native, name)).parameters["scope"].default
        assert scope is api.enums.GrokThreadScope.SDK, f"{name}: scope defaults to GrokThreadScope.SDK"


def test_thread_helpers_take_no_api_key_and_no_model(api) -> None:
    # INV-2 / AC-10: helpers read no key and call no model.
    carrying = [name for name in KEYLESS if {"api_key", "model"} & set(inspect.signature(getattr(api.native, name)).parameters)]
    assert carrying == []


def test_each_new_function_has_an_operation_named_after_it(lib_api) -> None:
    # INV-5 / §9.1: the operation value is the function's own name and
    # the member name its upper case.
    table = expected_signatures(lib_api.constants, None)
    members = {member.value: member.name for member in lib_api.enums.NativeThreadOperation}
    missing = [name for name in table if members.get(name) != name.upper()]
    assert missing == []


def test_slash_option_flags_reserved_goal_words_and_text_cap(lib_api) -> None:
    # D-30 / R-19 / D-25: only goal (--budget) and implement (--effort)
    # refuse their own flags in text; the four /goal subcommands are
    # reserved; the text cap leaves NATIVE_COMMAND_RESERVED_CHARS free.
    enums, constants = lib_api.enums, lib_api.constants
    flags = constants.GROK_TEXT_OPTION_FLAGS
    assert isinstance(flags, types.MappingProxyType)
    expected = {enums.GrokCommand.GOAL: (enums.GrokCommandFlag.BUDGET,), enums.GrokCommand.IMPLEMENT: (enums.GrokCommandFlag.EFFORT,)}
    assert {command: tuple(flags.get(command, ())) for command in enums.GrokCommand} == {command: expected.get(command, ()) for command in enums.GrokCommand}
    assert set(constants.GROK_GOAL_RESERVED_WORDS) == {"status", "pause", "resume", "clear"}
    assert constants.NATIVE_COMMAND_TEXT_MAX_CHARS == constants.NATIVE_ARGV_PROMPT_MAX_CHARS - constants.NATIVE_COMMAND_RESERVED_CHARS


def test_thread_summary_record_is_frozen_and_holds_utc_times(api) -> None:
    # §9.1 / D-13 / EC-15: times in any offset become UTC; the record is
    # frozen and slotted; harness goes through to_enum.
    created = datetime(2026, 10, 15, 14, 0, tzinfo=PLUS_TWO)
    summary = api.native.NativeThreadSummary(**SUMMARY, created_at=created, updated_at="2026-10-15T13:30:00Z")
    assert summary.harness is api.enums.NativeHarness.GROK
    assert summary.created_at == datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc) and summary.created_at.utcoffset() == timedelta(0)
    assert summary.updated_at == datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc) and summary.updated_at.utcoffset() == timedelta(0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.title = "changed"
    assert not hasattr(summary, "__dict__"), "slots=True"
    bare = api.native.NativeThreadSummary(harness="muse", thread_id="t" * api.constants.NATIVE_THREAD_ID_MAX_CHARS, title=None, created_at=created, updated_at=created, parent_thread_id=None, model=None)
    assert (bare.title, bare.parent_thread_id, bare.model) == (None, None, None)
    longest = api.native.NativeThreadSummary(**{**SUMMARY, "title": "x" * api.constants.NATIVE_TITLE_MAX_CHARS}, created_at=created, updated_at=created)
    assert len(longest.title) == api.constants.NATIVE_TITLE_MAX_CHARS


@pytest.mark.parametrize(("field", "bad"), [
    ("harness", "claude"), ("thread_id", "../x"), ("thread_id", ""), ("thread_id", "has space"), ("thread_id", "t" * 161), ("title", "   "),
    ("title", "a\x00b"), ("title", "x" * 4097), ("created_at", datetime(2026, 10, 15, 12, 0)), ("created_at", "2026-10-15T12:00:00"),
    ("updated_at", 1760529600), ("updated_at", "yesterday"), ("parent_thread_id", "thread-0001"), ("parent_thread_id", "-flag"),
    ("model", "has space"), ("model", "m" * 161),
], ids=lambda value: repr(value)[:24])
def test_thread_summary_record_refuses_each_bad_field_by_name(api, field, bad) -> None:
    # §9.1: every rule raises ConfigurationError naming the field (a
    # parent equal to the thread id included); readers turn that into
    # protocol_mismatch (INV-6).
    fields = {**SUMMARY, "created_at": datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc), "updated_at": datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc), field: bad}
    with pytest.raises(api.ConfigurationError) as caught:
        api.native.NativeThreadSummary(**fields)
    assert caught.value.details.get("field") == field, str(caught.value)


def test_command_output_record_carries_the_harness_and_text(api) -> None:
    # §9.1: harness through to_enum; text must be a str.
    output = api.native.NativeCommandOutput(harness="muse", text="Created .muse/config.toml\n")
    assert output.harness is api.enums.NativeHarness.MUSE and output.text == "Created .muse/config.toml\n"
    with pytest.raises(api.ConfigurationError) as caught:
        api.native.NativeCommandOutput(harness="muse", text=b"bytes")
    assert caught.value.details.get("field") == "text"
    with pytest.raises(dataclasses.FrozenInstanceError):
        output.text = "changed"


@pytest.mark.parametrize(("value", "expected"), [
    (datetime(2026, 10, 15, 14, 0, tzinfo=PLUS_TWO), datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)),
    ("2026-10-15T12:00:00Z", datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)),
    ("2026-10-15T09:30:00-02:30", datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)),
    ("2026-10-15T12:00:00.123456+00:00", datetime(2026, 10, 15, 12, 0, 0, 123456, tzinfo=timezone.utc)),
], ids=["aware-datetime", "zulu", "negative-offset", "microseconds"])
def test_to_utc_datetime_normalizes_offsets(lib_api, value, expected) -> None:
    # D-13 / EC-15: one canonical helper; the result is UTC-aware.
    from vidbyte.lib.dataclasses.validation import RecordFieldConverter

    converted = RecordFieldConverter.to_utc_datetime(value, "created_at")
    assert converted == expected and converted.utcoffset() == timedelta(0)


@pytest.mark.parametrize("value", [datetime(2026, 10, 15, 12, 0), "2026-10-15T12:00:00", "2026-10-15", "yesterday", "", 1760529600, None, True], ids=lambda value: repr(value)[:24])
def test_to_utc_datetime_refuses_naive_and_non_time_values(lib_api, value) -> None:
    # D-13 / EC-14: a naive value would make comparisons raise
    # TypeError later; it is refused here, naming the field.
    from vidbyte.lib.dataclasses.validation import RecordFieldConverter

    with pytest.raises(lib_api.ConfigurationError) as caught:
        RecordFieldConverter.to_utc_datetime(value, "updatedAt")
    assert caught.value.details.get("field") == "updatedAt"


def test_new_codes_have_their_own_complete_texts(lib_api) -> None:
    # AC-20 / §12.4: each new code has a likely cause and a next step
    # that are sentences ending in ".", unique within its harness.
    codes, constants = lib_api.FailureCode, lib_api.constants
    for value in ("grok.command_not_run", "opencode.command_not_run", "muse.command_not_run", "grok.store_unreadable"):
        code = codes(value)
        harness = value.split(".", 1)[0]
        for table in (constants.NATIVE_THREAD_LIKELY_CAUSES, constants.NATIVE_THREAD_NEXT_STEPS):
            text = table[code]
            assert text.strip().endswith("."), f"{value}: {text!r}"
            others = [table[other] for other in table if other is not code and other.value.startswith(harness + ".")]
            assert text not in others, f"{value} shares its text with another {harness} code"


def test_new_and_widened_texts_name_what_the_spec_requires(lib_api) -> None:
    # AC-20 / §12.4 / EC-74 / EC-78 / D-33 / EC-75: the tokens the spec
    # names verbatim appear in the cause or next step of their code.
    codes, constants = lib_api.FailureCode, lib_api.constants
    causes, steps = constants.NATIVE_THREAD_LIKELY_CAUSES, constants.NATIVE_THREAD_NEXT_STEPS
    grok_cause, grok_step = causes[codes("grok.command_not_run")], steps[codes("grok.command_not_run")]
    assert any(word in grok_cause.casefold() for word in ("same-named", "shadow", "overrid")), f"EC-78: the cause names shadowing: {grok_cause!r}"
    assert "grok inspect --json" in grok_step and "collidesWith" in grok_step, f"EC-78: {grok_step!r}"
    assert "read_grok_thread" in grok_step, f"§12.4: {grok_step!r}"
    assert "features.video_gen" in grok_cause + grok_step, "EC-74"
    muse_cause, muse_step = causes[codes("muse.command_not_run")], steps[codes("muse.command_not_run")]
    assert "compact" in muse_cause.casefold() and "read_muse_thread" in muse_step, f"D-33 / AC-34: {muse_cause!r} {muse_step!r}"
    store_step = steps[codes("grok.store_unreadable")]
    assert "HOME" in store_step or "USERPROFILE" in store_step, f"§12.4: {store_step!r}"
    control = spellings("NATIVE_CONTROL_TIMEOUT_SECONDS", constants.NATIVE_CONTROL_TIMEOUT_SECONDS)
    for harness in ("grok", "opencode", "muse"):
        cause, step = causes[codes(f"{harness}.timed_out")], steps[codes(f"{harness}.timed_out")]
        assert "timeout_seconds" in cause and any(text in cause for text in control), f"R-18: {harness} timeout cause names both bounds: {cause!r}"
        assert "retry" in step.casefold(), f"R-18: a helper's timeout next step says to retry: {step!r}"
        output = causes[codes(f"{harness}.output_too_large")]
        assert "transcript" in output.casefold(), f"R-18: {harness} output cause names the transcript case: {output!r}"
    grok_output = causes[codes("grok.output_too_large")]
    assert any(text in grok_output for text in spellings("GROK_CLI_MAX_OUTPUT_BYTES", constants.GROK_CLI_MAX_OUTPUT_BYTES)), grok_output
    assert any(text in grok_output for text in spellings("NATIVE_PROCESS_MAX_OUTPUT_BYTES", constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES)), grok_output
    mismatch = causes[codes("opencode.protocol_mismatch")] + steps[codes("opencode.protocol_mismatch")]
    assert any(text in mismatch for text in spellings("NATIVE_OPENCODE_SCAN_MAX", constants.NATIVE_OPENCODE_SCAN_MAX)) and "list_opencode_threads_since" in mismatch, mismatch


def test_root_export_lists_are_untouched() -> None:
    # INV-1: no name is added to vidbyte's or vidbyte.harnesses'
    # __all__ (checked against the merge base when one exists).
    found = git("merge-base", "origin/main", "HEAD")
    if found.returncode != 0 or not found.stdout.strip():
        pytest.skip("origin/main is not available in this checkout (a shallow CI clone has no main ref)")
    base = found.stdout.strip()
    for path in ("vidbyte/__init__.py", "vidbyte/harnesses/__init__.py"):
        before = literal_all(git("show", f"{base}:{path}").stdout)
        assert literal_all((REPO_ROOT / path).read_text(encoding="utf-8")) == before, path
