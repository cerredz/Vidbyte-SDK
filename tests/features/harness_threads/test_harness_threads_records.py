"""FILE: tests/features/harness_threads/test_harness_threads_records.py

PURPOSE: The validated records of spec §8.5 and §9.1 on their own: the three config records refuse a bad field when they are built (INV-4, FR-9, D-14, NG-9), accept an enum member or its exact value, NativeThreadRequest checks paths as given and then stores them resolved (D-26, R-14) and ties thread_id to the verb, NativeThreadResult and CliOption refuse malformed values (§9.1, R-15).
ROLE IN CODEBASE: Start here when a record accepts a value the spec refuses, or refuses one it allows. These tests need only vidbyte.lib, so they go green with spec phase P2.
ARCHITECTURE NOTE: Config records are built by the caller before any thread function runs, so their refusal is a ConfigurationError raised at construction, not a NativeThreadError. The public-function refusals live in test_harness_threads_arguments.py.
FUNCTION INVENTORY: the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new config field is a spec change first (§8.5), then one bad value in BAD_CONFIG_FIELDS.
WHAT NOT TO DO IN THIS FILE: Do not test framework behaviour (frozen assignment, dataclass equality).
KNOWN EDGE CASES: A relative path that exists relative to the current folder must still be refused, which is why the relative cases chdir into the sandbox first.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §8.5, §9.1, D-26
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_records.py
"""

from __future__ import annotations

import math

import pytest

BAD_CONFIG_FIELDS = [
    ("GrokThreadConfig", "timeout_seconds", 0), ("GrokThreadConfig", "timeout_seconds", -1.0), ("GrokThreadConfig", "timeout_seconds", math.nan),
    ("GrokThreadConfig", "timeout_seconds", 14400.5), ("GrokThreadConfig", "timeout_seconds", True), ("GrokThreadConfig", "timeout_seconds", "60"),
    ("GrokThreadConfig", "reasoning_effort", "turbo"), ("GrokThreadConfig", "reasoning_effort", "ultra"),
    ("GrokThreadConfig", "permission_mode", "bypassPermissions"), ("GrokThreadConfig", "permission_mode", "yolo"),
    ("GrokThreadConfig", "grok_command", ()), ("GrokThreadConfig", "grok_command", ("",)),
    ("OpencodeThreadConfig", "timeout_seconds", 0), ("OpencodeThreadConfig", "agent", "--auto"), ("OpencodeThreadConfig", "agent", "has space"),
    ("OpencodeThreadConfig", "agent", "a" * 65), ("OpencodeThreadConfig", "agent", ""), ("OpencodeThreadConfig", "variant", "-x"),
    ("OpencodeThreadConfig", "variant", "b" * 65), ("OpencodeThreadConfig", "opencode_command", ()),
    ("MuseThreadConfig", "timeout_seconds", math.inf), ("MuseThreadConfig", "reasoning_effort", "max"), ("MuseThreadConfig", "wsl_distro", "-e"),
    ("MuseThreadConfig", "wsl_distro", "bad name"), ("MuseThreadConfig", "wsl_distro", "d" * 65), ("MuseThreadConfig", "wsl_distro", ""),
    ("MuseThreadConfig", "muse_path", "usr/local/bin/muse"), ("MuseThreadConfig", "muse_path", "/usr/bin/muse\nrm"),
    ("MuseThreadConfig", "muse_path", "/usr/bin/mu\x00se"), ("MuseThreadConfig", "muse_command", ()),
]


@pytest.mark.parametrize(("record", "field", "bad"), BAD_CONFIG_FIELDS, ids=[f"{record}.{field}={bad!r}"[:60] for record, field, bad in BAD_CONFIG_FIELDS])
def test_config_record_refuses_a_bad_field_when_built(lib_api, record, field, bad) -> None:
    # §9.1: enums by to_enum, timeout by require_number(max 14400), commands by require_argv, names, distro and path by their patterns.
    with pytest.raises(lib_api.ConfigurationError) as caught:
        getattr(lib_api, record)(**{field: bad})
    assert field in str(caught.value), str(caught.value)


def test_config_records_accept_members_exact_values_and_the_bounds(lib_api) -> None:
    # §9.1 to_enum: a member or its exact value; timeout up to NATIVE_THREAD_MAX_SECONDS; names at 64 characters.
    enums = lib_api.enums
    grok = lib_api.GrokThreadConfig(permission_mode="acceptEdits", reasoning_effort="max", timeout_seconds=14400, grok_command=("grok-bin",))
    assert grok.permission_mode is enums.GrokPermissionMode.ACCEPT_EDITS and grok.reasoning_effort is enums.GrokReasoningEffort.MAX
    assert lib_api.GrokThreadConfig().permission_mode is enums.GrokPermissionMode.DEFAULT, "D-14: the vendor default"
    opencode = lib_api.OpencodeThreadConfig(agent="a" * 64, variant="high.v2_x-y")
    assert (opencode.agent, opencode.variant) == ("a" * 64, "high.v2_x-y")
    muse = lib_api.MuseThreadConfig(reasoning_effort=enums.MuseReasoningEffort.ULTRA, wsl_distro="d" * 64, muse_path="/opt/muse code/bin/muse")
    assert muse.reasoning_effort is enums.MuseReasoningEffort.ULTRA and muse.wsl_distro == "d" * 64


def test_request_checks_paths_as_given_then_stores_them_resolved(lib_api, sandbox, monkeypatch) -> None:
    # D-26 / R-14 / EC-40: the workspace and each skill must be absolute and exist as given; the record stores Path.resolve().
    enums = lib_api.enums
    skill = sandbox.make_skill("style-guide")
    (sandbox.workspace / "sub").mkdir()
    request = lib_api.NativeThreadRequest(harness="grok", verb="run", prompt="Explain.", api_key="vbk-key", workspace=str(sandbox.workspace / "sub" / ".."), skills=[str(skill / ".." / "style-guide")])
    assert request.workspace == sandbox.workspace.resolve() and isinstance(request.workspace, type(sandbox.workspace))
    assert request.skills == (skill.resolve(),)
    assert request.harness is enums.NativeHarness.GROK and request.verb is enums.NativeThreadVerb.RUN
    monkeypatch.chdir(sandbox.root)
    with pytest.raises(lib_api.ConfigurationError) as relative_workspace:
        lib_api.NativeThreadRequest(harness=enums.NativeHarness.GROK, verb=enums.NativeThreadVerb.RUN, prompt="Explain.", api_key="vbk-key", workspace="ws")
    assert "workspace" in str(relative_workspace.value)
    with pytest.raises(lib_api.ConfigurationError) as relative_skill:
        lib_api.NativeThreadRequest(harness=enums.NativeHarness.GROK, verb=enums.NativeThreadVerb.RUN, prompt="Explain.", api_key="vbk-key", workspace=sandbox.workspace, skills=["skill-src/style-guide"])
    assert "skills[0]" in str(relative_skill.value)


def test_request_needs_a_thread_id_exactly_for_continue_and_fork(lib_api, sandbox) -> None:
    # §9.1: thread_id is None iff the verb is RUN.
    enums = lib_api.enums
    fields = {"harness": enums.NativeHarness.MUSE, "prompt": "Explain.", "api_key": "vbk-key", "workspace": sandbox.workspace}
    with pytest.raises(lib_api.ConfigurationError) as with_id:
        lib_api.NativeThreadRequest(verb=enums.NativeThreadVerb.RUN, thread_id="thread-0001", **fields)
    assert "thread_id" in str(with_id.value)
    for verb in (enums.NativeThreadVerb.CONTINUE, enums.NativeThreadVerb.FORK):
        with pytest.raises(lib_api.ConfigurationError) as without_id:
            lib_api.NativeThreadRequest(verb=verb, **fields)
        assert "thread_id" in str(without_id.value)
        assert lib_api.NativeThreadRequest(verb=verb, thread_id="thread-0001", **fields).thread_id == "thread-0001"


def test_result_record_refuses_a_malformed_id_or_flag(lib_api) -> None:
    # §9.1 NativeThreadResult: harness enum, thread_id pattern, text str, text_truncated bool.
    good = lib_api.NativeThreadResult(harness="opencode", thread_id="ses_01abc", text="done", text_truncated=False)
    assert good.harness is lib_api.enums.NativeHarness.OPENCODE
    for field, bad in (("thread_id", "--yolo"), ("thread_id", ""), ("text_truncated", "no"), ("harness", "claude_code"), ("text", None)):
        values = {"harness": "opencode", "thread_id": "ses_01abc", "text": "done", "text_truncated": False, field: bad}
        with pytest.raises(lib_api.ConfigurationError) as caught:
            lib_api.NativeThreadResult(**values)
        assert field in str(caught.value), field


def test_cli_option_takes_a_dash_flag_and_a_nul_free_value(lib_api) -> None:
    # §9.1 / R-15: flag ^-[^\s=]*$ under fullmatch (a leading dash, no whitespace, no "="); value without NUL.
    enums = lib_api.enums
    assert lib_api.CliOption(enums.GrokFlag.MODEL, "grok-code-fast-1").flag == "--model"
    assert lib_api.CliOption("--fork").value is None
    assert lib_api.CliOption(enums.WslFlag.DISTRIBUTION, "Ubuntu").flag == "-d"
    assert lib_api.CliOption(enums.MuseFlag.WORKSPACE, "").value == ""
    for flag in ("model", "--model=x", "--a b", "", " -x"):
        with pytest.raises(lib_api.ConfigurationError):
            lib_api.CliOption(flag, "value")
    with pytest.raises(lib_api.ConfigurationError):
        lib_api.CliOption("--model", "bad\x00value")
