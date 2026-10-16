"""FILE: tests/features/harness_threads/test_harness_threads_grok_commands.py

PURPOSE: The Grok command functions against a grok stand-in that streams `--output-format=streaming-json` events and keeps a real-layout store: the exact §9.2 slash line, argv and environment of every function (AC-13, INV-9, INV-24, D-29), the evidence rule with and without evidence, Windows paths and a mismatched or missing `end` (AC-14, INV-8, EC-48), the plan and explore agents read from the new thread's `summary.json` (AC-15, EC-51), a corrupt sibling thread (AC-28), imagine-video and the code-review export (AC-30, D-28, EC-73), the minted id on every failure and the "may not exist" detail (AC-29, INV-29, EC-50, EC-81), the stream cap (INV-16) and `skills=` shadowing (AC-33, D-32).
ROLE IN CODEBASE: Start here when a Grok command function sends the wrong line, accepts an unexpanded command, or loses the thread id of a failed run.
ARCHITECTURE NOTE: The stand-in takes `--session-id` as the new thread's id, emits a `list_dir` call and then the evidence call the bundled skill would make (Windows backslash paths, as Grok prints them), and writes `summary.json` with `agent_name` for `--agent` runs. `update_goal` appears only when the child has `GROK_WORKFLOWS=0`, as in Grok, so a goal run without it fails closed. `expand: false` plays a Grok that did not expand the command; `tools` replaces the calls.
FUNCTION INVENTORY: grok_argv builds the expected argv in the §12.3 row 21 order; minted reads the `--session-id` the child got; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new command is one row in LINE_CASES plus its evidence in fake_harness_helpers.py.
WHAT NOT TO DO IN THIS FILE: Do not take the thread id from the stream: the test reads it from argv, because INV-29 says the SDK mints it.
KNOWN EDGE CASES: The design doc lives in the sandbox workspace, so its path holds no whitespace as long as the temp folder has none. The flood and padding cases write just past the real caps, because only the timing knobs are documented as monkeypatchable.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-8, INV-16, INV-24, INV-29, §6.2 AC-13 to AC-15, AC-28 to AC-30, AC-33, §6.3 EC-41, EC-48 to EC-51, EC-73, EC-74, EC-78, EC-81, §9.2, D-28, D-29, D-32
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_grok_commands.py
"""

from __future__ import annotations

import time

import pytest

TIMEOUT = 1.5
FLOOD_EXTRA_BYTES = 65536
DOC = "<doc>"
LINE_CASES = [
    ("goal", "run_grok_goal", ("Ship the release",), {}, "/goal Ship the release", None),
    ("goal-budget", "run_grok_goal", ("Ship it",), {"budget_tokens": 5000}, "/goal Ship it --budget 5000", None),
    ("implement", "run_grok_implement", ("Fix the login bug",), {}, "/implement Fix the login bug", None),
    ("implement-effort-r19", "run_grok_implement", ("Add a --dry-run flag",), {"effort": 3}, "/implement --effort 3 Add a --dry-run flag", None),
    ("design-r19", "run_grok_design", ("Design --local and --branch modes",), {}, "/design Design --local and --branch modes", None),
    ("execute-plan", "run_grok_execute_plan", (DOC,), {}, f"/execute-plan {DOC}", None),
    ("execute-plan-all", "run_grok_execute_plan", (DOC,), {"effort": 2, "concurrency": 3, "dry_run": True, "auto_pr": True}, f"/execute-plan {DOC} --effort 2 --concurrency 3 --dry-run --auto-pr", None),
    ("review", "run_grok_review", (), {}, "/review", None),
    ("review-local", "run_grok_review", (), {"local": True}, "/review --local", None),
    ("review-branch", "run_grok_review", (), {"branch": "feature/login-fix"}, "/review --branch feature/login-fix", None),
    ("review-pr", "run_grok_review", (), {"pr": 12}, "/review --pr 12", None),
    ("review-pr-url", "run_grok_review", (), {"pr": "https://github.com/acme/app/pull/12"}, "/review --pr https://github.com/acme/app/pull/12", None),
    ("code-review", "run_grok_code_review", (), {}, "/code-review", None),
    ("resume-claude", "run_grok_resume_claude", ("sess-claude-01",), {}, "/resume-claude sess-claude-01", None),
    ("resume-codex", "run_grok_resume_codex", ("sess-codex-01",), {}, "/resume-codex sess-codex-01", None),
    ("resume-cursor", "run_grok_resume_cursor", ("sess-cursor-01",), {}, "/resume-cursor sess-cursor-01", None),
    ("imagine", "run_grok_imagine", ("A red fox in snow",), {}, "/imagine A red fox in snow", None),
    ("imagine-video", "run_grok_imagine_video", ("A red fox running",), {}, "/imagine-video A red fox running", None),
    ("plan", "run_grok_plan", ("Plan the refactor of the store",), {}, "Plan the refactor of the store", "plan"),
    ("explore", "run_grok_explore", ("Where is the retry policy?",), {}, "Where is the retry policy?", "explore"),
]


def grok_argv(session: str, workspace, line: str, agent: str | None = None) -> list[str]:
    argv = ["--output-format=streaming-json", f"--session-id={session}", f"--cwd={workspace}", "--permission-mode=default"]
    return argv + ([f"--agent={agent}"] if agent else []) + [f"--single={line}"]


def minted(sandbox) -> str:
    return sandbox.only_start("grok")["options"]["--session-id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "name", "positional", "keywords", "line", "agent"), LINE_CASES, ids=[case[0] for case in LINE_CASES])
async def test_each_command_function_sends_its_line_with_a_minted_session_id(api, sandbox, skill, shapes, pack, case, name, positional, keywords, line, agent) -> None:
    # AC-13 / INV-24 / INV-29 / D-29: one --single= line per the §9.2
    # table, streaming-json, a fresh UUID4 --session-id that becomes the
    # thread id, GROK_WORKFLOWS=0 for goal only, the key in the
    # environment only, the private home; the text after the last tool
    # call (§9.2 rule 7).
    doc = sandbox.workspace / "plan.md"
    doc.write_text("# Plan\n\n1. Do it.\n", encoding="utf-8")
    positional = tuple(str(doc) if value == DOC else value for value in positional)
    line = line.replace(DOC, str(doc))
    result = await skill(name, *positional, **keywords)
    start = sandbox.only_start("grok")
    session = start["options"]["--session-id"]
    assert shapes.UUID4.fullmatch(session), f"--session-id must be a UUID4, got {session!r}"
    assert start["argv"] == grok_argv(session, sandbox.workspace, line, agent)
    assert (result.harness.value, result.thread_id, result.text, result.text_truncated) == ("grok", session, f"grok answer to: {line}", False)
    assert start["plain"]["GROK_WORKFLOWS"] == ("0" if name == "run_grok_goal" else None)
    assert start["plain"]["GROK_HOME"] == str(sandbox.grok_home())
    assert start["credentials"]["XAI_API_KEY"] == pack.key_digest(pack.API_KEY) == start["credentials"]["GROK_CODE_XAI_API_KEY"]
    assert all(pack.API_KEY not in element for element in start["argv"])


@pytest.mark.asyncio
@pytest.mark.parametrize(("command", "arguments", "line"), [
    ("GOAL", "x --budget 5", "/goal x --budget 5"), ("CODE_REVIEW", "", "/code-review"), ("REVIEW", "--local", "/review --local"), ("IMAGINE", "A cat", "/imagine A cat"),
], ids=["goal-raw-budget", "code-review", "review-raw", "imagine"])
async def test_run_grok_command_sends_the_raw_line(api, sandbox, skill, command, arguments, line) -> None:
    # §9.2 / EC-70: `/<c.value>` or `/<c.value> <a>`; raw arguments are
    # the caller's own and skip the wrapper checks.
    positional = (getattr(api.native.GrokCommand, command),) + ((arguments,) if arguments else ())
    result = await skill("run_grok_command", *positional)
    start = sandbox.only_start("grok")
    assert start["argv"][-1] == f"--single={line}" and result.thread_id == start["options"]["--session-id"]
    assert start["plain"]["GROK_WORKFLOWS"] == ("0" if command == "GOAL" else None)


@pytest.mark.asyncio
async def test_every_run_mints_a_new_id(sandbox, skill) -> None:
    # D-29: one uuid4 per run.
    first = await skill("run_grok_goal", "First goal")
    second = await skill("run_grok_goal", "Second goal")
    assert first.thread_id != second.thread_id
    assert [start["options"]["--session-id"] for start in sandbox.starts("grok")] == [first.thread_id, second.thread_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "tools"), [
    ("run_grok_implement", ("Fix it",), [["read_file", {"path": "C:\\\\Users\\\\dev\\\\.grok\\\\bundled\\\\skills\\\\shared\\\\personas\\\\implementer.md"}]]),
    ("run_grok_implement", ("Fix it",), [["read_file", "/home/dev/.grok/bundled/skills/shared/personas/implementer.md"]]),
    ("run_grok_imagine", ("A cat",), [["image_edit", {"prompt": "A cat"}]]),
], ids=["doubled-backslashes", "posix-string-input", "image-edit"])
async def test_evidence_variants_that_count(sandbox, skill, name, positional, tools) -> None:
    # §9.2 evidence rules: backslash runs fold to `/`; rawInput may be a
    # string; image_edit counts for imagine.
    result = await skill(name, *positional, fake={"tools": tools})
    assert result.thread_id == minted(sandbox)


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "fake"), [
    ("run_grok_goal", ("Ship the release",), {"expand": False}),
    ("run_grok_implement", ("Fix it",), {"tools": [["list_dir", {"path": "."}], ["read_file", {"path": "C:\\Users\\dev\\.grok\\bundled\\skills\\shared\\personas\\reviewer.md"}]]}),
    ("run_grok_review", (), {"tools": [["list_dir", {"path": "."}], ["write_file", {"path": "shared/personas/reviewer.md"}]]}),
    ("run_grok_imagine_video", ("A red fox running",), {"expand": False}),
    ("run_grok_imagine_video", ("A red fox running",), {"tools": [["list_dir", {"path": "."}], ["image_gen", {"prompt": "A red fox"}]]}),
    ("run_grok_resume_codex", ("sess-1",), {"expand": False}),
], ids=["goal-unexpanded", "implement-wrong-persona", "review-wrong-tool", "imagine-video-unexpanded", "imagine-video-still-image", "resume-unexpanded"])
async def test_missing_evidence_is_command_not_run_with_the_minted_id_and_the_tools_seen(api, sandbox, skill, check_error, name, positional, fake) -> None:
    # AC-14 / AC-30 / INV-8 / EC-41 / EC-74: no evidence fails closed;
    # the thread exists, so its id is attached; the detail lists the
    # tools the run called.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill(name, *positional, fake=fake)
    check_error(caught.value, harness="grok", operation=name, code="grok.command_not_run", workspace=sandbox.workspace, thread_id=minted(sandbox), observations=[("tools called", ("list_dir",))])


@pytest.mark.asyncio
@pytest.mark.parametrize(("end_session", "member"), [("other", "sessionId"), ("missing", "sessionId"), ("none", "end")])
async def test_an_end_event_that_is_missing_or_names_another_session_is_protocol_mismatch(api, sandbox, skill, check_error, end_session, member) -> None:
    # AC-14 / EC-48 / D-29: §9.2 reading order steps 5 and 6.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_grok_goal", "Ship the release", fake={"end_session": end_session})
    check_error(caught.value, harness="grok", operation="run_grok_goal", code="grok.protocol_mismatch", workspace=sandbox.workspace, thread_id=minted(sandbox), observations=[("member", (member,))])


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "fake"), [
    ("run_grok_plan", {"summary_fields": {"agent_name": "general"}}),
    ("run_grok_plan", {"summary_fields": {"agent_name": None}}),
    ("run_grok_explore", {"summary_mode": "absent"}),
    ("run_grok_explore", {"summary_fields": {"agent_name": "plan"}}),
], ids=["other-agent", "no-agent-name", "no-summary", "explore-got-plan"])
async def test_agent_runs_need_the_agent_name_in_the_new_threads_summary(api, sandbox, skill, check_error, name, fake) -> None:
    # AC-15 / EC-51: equal agent_name returns (LINE_CASES); a different
    # one, none, or no summary.json is command_not_run.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill(name, "Look around", fake=fake)
    check_error(caught.value, harness="grok", operation=name, code="grok.command_not_run", workspace=sandbox.workspace, thread_id=minted(sandbox))


@pytest.mark.asyncio
@pytest.mark.parametrize("sibling", ["invalid-json", "oversize"])
async def test_agent_evidence_ignores_a_corrupt_sibling_thread(api, sandbox, skill, stores, sibling) -> None:
    # AC-28 / EC-68 / D-27: only the new thread's own summary.json is
    # read.
    raw = b"{\"created_at\": " if sibling == "invalid-json" else b" " * (api.constants.GROK_SUMMARY_MAX_BYTES + 1)
    stores.grok_thread("sibling-b", raw=raw)
    result = await skill("run_grok_plan", "Plan the next step")
    assert result.thread_id == minted(sandbox) and result.text == "grok answer to: Plan the next step"


@pytest.mark.asyncio
async def test_code_review_reads_its_own_export_through_a_keyless_child(api, sandbox, skill, check_error) -> None:
    # AC-30 / D-28: `grok export <minted id>` under the run's private
    # home with no key; the fragment proves the skill ran; without it,
    # command_not_run.
    result = await skill("run_grok_code_review")
    session = minted(sandbox)
    assert result.thread_id == session
    export = sandbox.only_start("grok-export")
    assert export["argv"] == ["export", session] and export["plain"]["GROK_HOME"] == str(sandbox.grok_home())
    assert all(value is None for value in export["credentials"].values()), "INV-2: the export child carries no key"
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_grok_code_review", fake={"expand": False})
    second = sandbox.starts("grok")[-1]["options"]["--session-id"]
    check_error(caught.value, harness="grok", operation="run_grok_code_review", code="grok.command_not_run", workspace=sandbox.workspace, thread_id=second)


@pytest.mark.asyncio
@pytest.mark.parametrize(("fake", "code"), [
    ({"export_mode": "not_found"}, "grok.thread_not_found"),
    ({"export_mode": "fail", "vendor_text": "export: the store is busy"}, "grok.run_failed"),
    ({"export_mode": "hold"}, "grok.timed_out"),
    ({"export_mode": "flood"}, "grok.output_too_large"),
], ids=["not-found", "fails", "hangs", "floods"])
async def test_a_failed_code_review_export_carries_the_minted_id(api, sandbox, skill, check_error, monkeypatch, fast_stop, fake, code) -> None:
    # EC-73 / INV-29: the export child after a paid run.
    monkeypatch.setattr(api.constants, "NATIVE_CONTROL_TIMEOUT_SECONDS", TIMEOUT)
    if fake["export_mode"] == "flood":
        fake = {**fake, "flood_bytes": api.constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES + FLOOD_EXTRA_BYTES}
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_grok_code_review", fake=fake)
    check_error(caught.value, harness="grok", operation="run_grok_code_review", code=code, workspace=sandbox.workspace, thread_id=minted(sandbox))


@pytest.mark.asyncio
async def test_a_run_past_its_timeout_is_timed_out_with_the_minted_id(api, sandbox, skill, check_error, fast_stop) -> None:
    # AC-29 / EC-50 / INV-29: the stand-in streams, then never ends.
    started = time.monotonic()
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_grok_goal", "Ship the release", fake={"mode": "hold"}, config={"timeout_seconds": TIMEOUT})
    assert time.monotonic() - started < TIMEOUT + 4 * fast_stop.kill_wait + fast_stop.slack
    check_error(caught.value, harness="grok", operation="run_grok_goal", code="grok.timed_out", workspace=sandbox.workspace, thread_id=minted(sandbox), observations=[("seconds waited", (str(TIMEOUT),))])


@pytest.mark.asyncio
async def test_a_stream_past_the_output_cap_is_output_too_large_with_the_minted_id(api, sandbox, skill, check_error) -> None:
    # AC-29 / EC-50 / INV-16: the cap is NATIVE_PROCESS_MAX_OUTPUT_BYTES;
    # `end` is lost, the id is still known.
    cap = api.constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_grok_imagine", "A cat", fake={"mode": "flood", "flood_bytes": cap + FLOOD_EXTRA_BYTES})
    check_error(caught.value, harness="grok", operation="run_grok_imagine", code="grok.output_too_large", workspace=sandbox.workspace, thread_id=minted(sandbox), observations=[("byte cap", (str(cap), f"{cap:,}"))])


@pytest.mark.asyncio
async def test_a_stream_larger_than_the_run_cap_of_1036_still_succeeds(api, sandbox, skill) -> None:
    # INV-16: Grok command runs use NATIVE_PROCESS_MAX_OUTPUT_BYTES, not
    # GROK_CLI_MAX_OUTPUT_BYTES, because the stream carries tool calls.
    padding = api.constants.GROK_CLI_MAX_OUTPUT_BYTES + (1 << 20)
    result = await skill("run_grok_implement", "Fix it", fake={"padding_bytes": padding})
    assert result.text == "grok answer to: /implement Fix it"


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "code", "vendor"), [
    ("key_rejected", "grok.key_rejected", None),
    ("not_started", "grok.run_failed", "Couldn't start session"),
])
async def test_a_failure_before_the_session_exists_says_the_thread_may_not_exist(api, sandbox, skill, check_error, mode, code, vendor) -> None:
    # AC-29 / EC-49 / EC-81 / INV-29: the requested id is attached and
    # the detail says the thread may not exist.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_grok_goal", "Ship the release", fake={"mode": mode})
    error = caught.value
    check_error(error, harness="grok", operation="run_grok_goal", code=code, workspace=sandbox.workspace, thread_id=minted(sandbox), vendor=vendor)
    assert "may not exist" in str(error).lower()


@pytest.mark.asyncio
async def test_a_completed_run_never_says_the_thread_may_not_exist(api, sandbox, skill) -> None:
    # INV-29: after `end` or a tool call, the thread is known to exist.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_grok_goal", "Ship the release", fake={"expand": False})
    assert "may not exist" not in str(caught.value).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "folder"), [
    ("run_grok_review", (), "review"), ("run_grok_design", ("A new page",), "design"), ("run_grok_implement", ("Fix it",), "implement"),
])
async def test_a_skills_folder_named_like_the_command_is_refused_before_any_run(api, sandbox, skill, check_error, name, positional, folder) -> None:
    # AC-33 / D-32 / EC-78: the caller's folder would shadow the bundled
    # skill, so the run could read no persona.
    shadow = sandbox.make_skill(folder)
    config = api.GrokThreadConfig(grok_command=sandbox.command("grok"))
    before = sandbox.snapshot(include_fake=True)
    with pytest.raises(api.NativeThreadError) as caught:
        await skill(name, *positional, skills=[shadow], raw_config=config)
    check_error(caught.value, harness="grok", operation=name, code="configuration.invalid_argument", observations=[("argument name", ("skills",))])
    assert sandbox.snapshot(include_fake=True) == before and sandbox.starts() == []


@pytest.mark.asyncio
async def test_a_skills_folder_with_another_name_passes(sandbox, skill) -> None:
    # AC-33: only the command's own name is refused.
    other = sandbox.make_skill("team-review-notes")
    result = await skill("run_grok_review", skills=[other])
    assert result.thread_id == minted(sandbox)
