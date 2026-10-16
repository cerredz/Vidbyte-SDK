"""FILE: tests/features/harness_threads/test_harness_threads_muse_commands.py

PURPOSE: The Muse skill functions against a muse stand-in whose exec run folds `toolCall` items into the thread: the §9.2 prompt after `--` (AC-17, INV-9, INV-25), the evidence read through `session/read {excludeItems: false}` in history modes inline, snapshot and none (AC-17, INV-8, EC-55, EC-56), the export fallback when the history is an anchored snapshot after compaction (AC-34, D-33, EC-79), the goal function's `create_goal` evidence, and an evidence read that fails after the run with the new thread id attached (EC-61).
ROLE IN CODEBASE: Start here when a Muse skill function returns for a run that never loaded the skill, or fails a run that did.
ARCHITECTURE NOTE: The stand-in adds a `read_skill` call whose `args` hold the skill id when the exec prompt says "Use the `<id>` skill" (unless `expand` is false); `exec_items` replaces the calls. `history_mode` chooses how `session/read` returns the items; `anchoredSnapshot` keeps only a compaction item and the later `list_dir` calls, as Muse does after compaction, and `muse export` still writes every item unless `export_drop_tools` drops some.
FUNCTION INVENTORY: skill_prompt builds the §9.2 prompt independently of the constant; new_thread reads the exec run's thread id from the stand-in log; evidence_reads lists the logged `session/read` params; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new named Muse function is one row in NAMED.
WHAT NOT TO DO IN THIS FILE: Do not let a test pass on the exec run alone: each success also checks the evidence read that followed it.
KNOWN EDGE CASES: The goal prompt template has no value in the spec, so its prompt is built from the constant and only its objective is checked literally.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-8, INV-25, §6.2 AC-17, AC-34, §6.3 EC-55, EC-56, EC-61, EC-79, §9.2, D-9, D-33
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_muse_commands.py
"""

from __future__ import annotations

import pytest

TIMEOUT = 1.5
NAMED = [
    ("run_muse_plan", "bundled:plan", "Plan the cache rewrite"),
    ("run_muse_import", "bundled:import", "~/.claude/projects/app/session-01.jsonl"),
    ("run_muse_scaffold", "bundled:greenfield-project-scaffolding", "A FastAPI service with a Postgres store"),
    ("run_muse_browser_app", "bundled:browser-app-delivery", "A to-do app with offline storage"),
]
GOAL_CALL = [["list_dir", "{\"path\": \".\"}"], ["create_goal", "{\"objective\": \"Ship the release\"}"]]


def skill_prompt(skill_id: str, text: str) -> str:
    return f"Use the `{skill_id}` skill.\n\n{text}"


def new_thread(sandbox) -> str:
    return sandbox.records("session", "muse-exec")[-1]["session"]


def evidence_reads(sandbox) -> list[dict]:
    return [record["frame"]["params"] for record in sandbox.records("frame", "muse-serve") if record["frame"].get("method") == "session/read"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "skill_id", "text"), [("run_muse_skill", "team-review", "Review the diff"), ("run_muse_skill", "bundled:plan", "Plan it"), *NAMED], ids=["user-skill", "bundled-by-id", *[row[0] for row in NAMED]])
async def test_skill_functions_send_the_prompt_and_return_after_the_evidence_read(api, sandbox, skill, pack, name, skill_id, text) -> None:
    # AC-17 / INV-8 / INV-25 / D-9: exec gets the template prompt after
    # `--`; the thread's items are read with excludeItems false and hold
    # a read_skill call whose args name the skill.
    positional = (skill_id, text) if name == "run_muse_skill" else (text,)
    result = await skill(name, *positional)
    start = sandbox.only_start("muse-exec")
    assert start["operands"] == [skill_prompt(skill_id, text)] and start["argv"][-2] == "--"
    session = new_thread(sandbox)
    assert (result.harness.value, result.thread_id, result.text, result.text_truncated) == ("muse", session, f"muse answer to: {skill_prompt(skill_id, text)}", False)
    assert evidence_reads(sandbox) == [{"sessionId": session, "excludeItems": False}]
    serve = sandbox.only_start("muse-serve")
    assert all(value is None for value in serve["credentials"].values()), "INV-23: the evidence read carries no key"
    assert start["credentials"]["META_API_KEY"] == pack.key_digest(pack.API_KEY)
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_snapshot_history_counts_as_items(sandbox, skill) -> None:
    # §12.3 row 25: mode snapshot keeps the items under
    # history.snapshot.state.items.
    result = await skill("run_muse_plan", "Plan it", fake={"history_mode": "snapshot"})
    assert result.thread_id == new_thread(sandbox) and sandbox.starts("muse-export") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "fake"), [
    ("run_muse_plan", ("Plan it",), {"expand": False}),
    ("run_muse_plan", ("Plan it",), {"exec_items": [["read_skill", "{\"id\": \"bundled:import\"}"]]}),
    ("run_muse_skill", ("team-review", "Review"), {"exec_items": [["read_file", "{\"path\": \"skills/team-review/SKILL.md\"}"]]}),
    ("run_muse_goal", ("Ship the release",), {}),
], ids=["never-loaded", "other-skill", "skill-read-as-file", "goal-without-create-goal"])
async def test_missing_evidence_is_command_not_run_with_the_new_thread(api, sandbox, skill, check_error, name, positional, fake) -> None:
    # AC-17 / EC-55 / INV-8: the run happened, so its id is attached.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill(name, *positional, fake=fake)
    check_error(caught.value, harness="muse", operation=name, code="muse.command_not_run", workspace=sandbox.workspace, thread_id=new_thread(sandbox))


@pytest.mark.asyncio
async def test_history_mode_none_fails_closed_naming_the_reason(api, sandbox, skill, check_error) -> None:
    # AC-17 / EC-56 / A-16: no items to check is no evidence.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_muse_plan", "Plan it", fake={"history_mode": "none", "none_reason": "projectionUnavailable"})
    check_error(caught.value, harness="muse", operation="run_muse_plan", code="muse.command_not_run", workspace=sandbox.workspace, thread_id=new_thread(sandbox), observations=[("noneReason", ("projectionUnavailable",))])


@pytest.mark.asyncio
async def test_goal_needs_a_create_goal_call(api, sandbox, skill) -> None:
    # §9.2: the goal template prompt; evidence is a create_goal item.
    result = await skill("run_muse_goal", "Ship the release", fake={"exec_items": GOAL_CALL})
    prompt = sandbox.only_start("muse-exec")["operands"][0]
    assert prompt == api.constants.MUSE_GOAL_PROMPT_TEMPLATE.format(prompt="Ship the release") and "Ship the release" in prompt
    assert result.thread_id == new_thread(sandbox)


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "fake"), [
    ("run_muse_plan", ("Plan the cache rewrite",), {}),
    ("run_muse_goal", ("Ship the release",), {"exec_items": GOAL_CALL}),
], ids=["plan", "goal"])
async def test_after_compaction_the_evidence_comes_from_the_export_transcript(api, sandbox, skill, name, positional, fake) -> None:
    # AC-34 / D-33 / EC-79: anchoredSnapshot items start after the early
    # call, so the run's own `muse export` is read instead, through a
    # keyless child, and its temp folder is removed.
    result = await skill(name, *positional, fake={**fake, "history_mode": "anchoredSnapshot"})
    session = new_thread(sandbox)
    assert result.thread_id == session
    export = sandbox.only_start("muse-export")
    assert export["options"]["--session"] == session and all(value is None for value in export["credentials"].values())
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_after_compaction_a_transcript_without_the_call_is_command_not_run_naming_compaction(api, sandbox, skill, check_error) -> None:
    # AC-34 / D-33: the cause names compaction.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_muse_plan", "Plan it", fake={"history_mode": "anchoredSnapshot", "export_drop_tools": ["read_skill"]})
    error = caught.value
    check_error(error, harness="muse", operation="run_muse_plan", code="muse.command_not_run", workspace=sandbox.workspace, thread_id=new_thread(sandbox))
    assert "compact" in error.likely_cause.lower()
    assert len(sandbox.starts("muse-export")) == 1 and list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("fake", "code"), [({"serve_mode": "not_found"}, "muse.thread_not_found"), ({"serve_mode": "hold"}, "muse.timed_out")], ids=["not-found", "hangs"])
async def test_an_evidence_read_that_fails_after_the_run_carries_the_new_thread(api, sandbox, skill, check_error, monkeypatch, fast_stop, fake, code) -> None:
    # EC-61 / INV-16: the evidence read is a control child; its failure
    # keeps the run's id so the caller can read or continue it.
    monkeypatch.setattr(api.constants, "NATIVE_CONTROL_TIMEOUT_SECONDS", TIMEOUT)
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_muse_plan", "Plan it", fake=fake)
    check_error(caught.value, harness="muse", operation="run_muse_plan", code=code, workspace=sandbox.workspace, thread_id=new_thread(sandbox))
    assert len(sandbox.starts("muse-exec")) == 1 and list(sandbox.tmp.iterdir()) == []
