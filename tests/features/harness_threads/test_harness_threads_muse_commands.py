"""FILE: tests/features/harness_threads/test_harness_threads_muse_commands.py

PURPOSE: The Muse skill functions against a muse stand-in whose exec run folds `toolCall` items into the thread: the §9.2 prompt after `--` (AC-17, INV-9, INV-25), the evidence read through `session/read {excludeItems: false}` in history modes inline, snapshot, anchoredSnapshot and none (AC-17, AC-34, INV-8, EC-55, EC-56, EC-79), a `read_skill` call that counts only when its parsed `id` equals the skill id (AC-17, EC-82), text that never counts (EC-83), a call missing from the served fold (EC-84), the goal function's `create_goal` evidence, and an evidence read or evidence folder that fails after the run with the new thread id attached (EC-61, AC-35, EC-85).
ROLE IN CODEBASE: Start here when a Muse skill function returns for a run that never loaded the skill, or fails a run that did.
ARCHITECTURE NOTE: The stand-in adds a `read_skill` call whose `args` hold the skill id when the exec prompt says "Use the `<id>` skill" (unless `expand` is false); `exec_items` replaces the calls and `text` the answer. `history_mode` chooses how `session/read` returns the items; `anchoredSnapshot` is MSP's full folded state (spec §13, r5): `history.items` is null and `history.snapshot.state.items` holds every item plus a compaction item, unless `anchored_drop_tools` removes calls (A-28 false). No evidence test may start `muse export`, whose real document has no `items` (D-33). The evidence-folder failures patch `tempfile.mkdtemp`, the call spec §13 and INV-12 name for Muse's private folders, and fail it only once the exec run has logged its answer.
FUNCTION INVENTORY: skill_prompt builds the §9.2 prompt independently of the constant; new_thread reads the exec run's thread id from the stand-in log; evidence_reads lists the logged `session/read` params; skill_call builds a `read_skill` call under MUSE_READ_SKILL_ID_MEMBER; read_skill_args builds the not-evidence argument shapes; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new named Muse function is one row in NAMED.
WHAT NOT TO DO IN THIS FILE: Do not let a test pass on the exec run alone: each success also checks the evidence read that followed it.
KNOWN EDGE CASES: The goal prompt template has no value in the spec, so its prompt is built from the constant and only its objective is checked literally. EC-83 needs the trap to be real, so each text case also checks that the prompt or the answer does name the tool or the skill id.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-8, INV-25, §6.2 AC-17, AC-34, AC-35, §6.3 EC-55, EC-56, EC-61, EC-79, EC-82 to EC-85, §9.2, §13, A-28, D-9, D-33, D-34
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_muse_commands.py
"""

from __future__ import annotations

import errno
import json
import tempfile

import pytest

TIMEOUT = 1.5
NAMED = [
    ("run_muse_plan", "bundled:plan", "Plan the cache rewrite"),
    ("run_muse_import", "bundled:import", "~/.claude/projects/app/session-01.jsonl"),
    ("run_muse_scaffold", "bundled:greenfield-project-scaffolding", "A FastAPI service with a Postgres store"),
    ("run_muse_browser_app", "bundled:browser-app-delivery", "A to-do app with offline storage"),
]
GOAL_CALL = [["list_dir", "{\"path\": \".\"}"], ["create_goal", "{\"objective\": \"Ship the release\"}"]]
LIST_CALL = [["list_dir", "{\"path\": \".\"}"]]
ANCHORED = {"history_mode": "anchoredSnapshot"}
GRILL = "bundled:grill"
NOT_EVIDENCE = ["longer-id", "id-in-a-list", "json-string", "not-json", "nested-id", "id-not-a-string"]


def skill_prompt(skill_id: str, text: str) -> str:
    return f"Use the `{skill_id}` skill.\n\n{text}"


def new_thread(sandbox) -> str:
    return sandbox.records("session", "muse-exec")[-1]["session"]


def evidence_reads(sandbox) -> list[dict]:
    return [record["frame"]["params"] for record in sandbox.records("frame", "muse-serve") if record["frame"].get("method") == "session/read"]


def skill_call(api, skill_id: str) -> list[str]:
    # A read_skill call whose args name the skill under the member the
    # spec fixes (MUSE_READ_SKILL_ID_MEMBER, A-17).
    return ["read_skill", json.dumps({api.constants.MUSE_READ_SKILL_ID_MEMBER: skill_id})]


def read_skill_args(api, shape: str) -> str:
    # Arguments that hold GRILL as text but are not an object whose id
    # member equals it (EC-82, AC-17).
    member = api.constants.MUSE_READ_SKILL_ID_MEMBER
    shapes = {
        "longer-id": json.dumps({member: GRILL + "-and-record"}),
        "id-in-a-list": json.dumps([member, GRILL]),
        "json-string": json.dumps(GRILL),
        "not-json": f"{member}={GRILL}",
        "nested-id": json.dumps({"skill": {member: GRILL}}),
        "id-not-a-string": json.dumps({member: [GRILL]}),
    }
    return shapes[shape]


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
@pytest.mark.parametrize("shape", NOT_EVIDENCE)
async def test_a_read_skill_call_counts_only_when_its_parsed_id_is_the_skill(api, sandbox, skill, check_error, shape) -> None:
    # AC-17 / EC-82 / D-33 (r4, S4 R-23): the args, parsed as JSON,
    # must be an object whose id member equals the skill id; a longer
    # id, a list, a string, non-JSON or a nested id is no evidence.
    args = read_skill_args(api, shape)
    assert GRILL in args, "test premise: the args hold the skill id as text"
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_muse_skill", GRILL, "Grill the plan", fake={"exec_items": [["read_skill", args]]})
    check_error(caught.value, harness="muse", operation="run_muse_skill", code="muse.command_not_run", workspace=sandbox.workspace, thread_id=new_thread(sandbox))


@pytest.mark.asyncio
async def test_a_read_skill_call_with_more_arguments_still_counts(api, sandbox, skill) -> None:
    # AC-17 / D-33: other members beside the id do not matter.
    member = api.constants.MUSE_READ_SKILL_ID_MEMBER
    args = json.dumps({member: GRILL, "reason": "the user asked for it"})
    result = await skill("run_muse_skill", GRILL, "Grill the plan", fake={"exec_items": [["read_skill", args]]})
    assert result.thread_id == new_thread(sandbox)


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "goal"), [
    ("run_muse_plan", ("Plan the cache rewrite",), False),
    ("run_muse_goal", ("Ship the release",), True),
], ids=["plan", "goal"])
async def test_after_compaction_the_evidence_is_the_anchored_snapshots_tool_call(api, sandbox, skill, name, positional, goal) -> None:
    # AC-34 / D-33 / EC-79 (r5): MSP's anchored snapshot holds every
    # item, so the early call is read from state.items like a snapshot;
    # the log shows the exec and one serve, and no `muse export`.
    fake = {**ANCHORED, "exec_items": GOAL_CALL} if goal else dict(ANCHORED)
    result = await skill(name, *positional, fake=fake)
    session = new_thread(sandbox)
    assert result.thread_id == session
    assert evidence_reads(sandbox) == [{"sessionId": session, "excludeItems": False}]
    assert sandbox.starts("muse-export") == [], "D-33: no export runs for evidence"
    assert len(sandbox.starts("muse-exec")) == 1 and len(sandbox.starts("muse-serve")) == 1
    assert list(sandbox.tmp.iterdir()) == []


COMPACTED_WITHOUT_EVIDENCE = [
    ("run_muse_goal", ("Ship the release",), lambda api: {}, "create_goal"),
    ("run_muse_plan", ("Plan the cache rewrite",), lambda api: {"exec_items": [skill_call(api, "bundled:import")]}, "bundled:plan"),
    ("run_muse_plan", ("Plan the cache rewrite",), lambda api: {"exec_items": LIST_CALL, "text": "I called read_skill on bundled:plan first."}, "read_skill"),
    ("run_muse_plan", ("Plan the cache rewrite",), lambda api: {"anchored_drop_tools": ["read_skill"]}, None),
    ("run_muse_goal", ("Ship the release",), lambda api: {"exec_items": GOAL_CALL, "anchored_drop_tools": ["create_goal"]}, None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "build", "trap"), COMPACTED_WITHOUT_EVIDENCE, ids=["goal-named-only-in-its-prompt", "plan-reads-another-skill", "answer-names-read-skill", "call-missing-from-the-fold", "goal-call-missing-from-the-fold"])
async def test_after_compaction_text_or_a_call_outside_the_fold_is_command_not_run(api, sandbox, skill, check_error, name, positional, build, trap) -> None:
    # AC-34 / EC-83 / EC-84 / D-33: only a toolCall item in the served
    # state.items counts; the prompt, the answer, another skill's read
    # and a call the fold lacks (A-28 false) do not. The cause names
    # compaction, and no export is read.
    fake = {**ANCHORED, **build(api)}
    with pytest.raises(api.NativeThreadError) as caught:
        await skill(name, *positional, fake=fake)
    error = caught.value
    check_error(error, harness="muse", operation=name, code="muse.command_not_run", workspace=sandbox.workspace, thread_id=new_thread(sandbox))
    assert "compact" in error.likely_cause.casefold()
    assert sandbox.starts("muse-export") == [], "D-33: no export runs for evidence"
    if trap is not None:
        told = sandbox.only_start("muse-exec")["operands"][0] + fake.get("text", "")
        assert trap in told, f"test premise: the thread's text names {trap!r}"


@pytest.mark.asyncio
async def test_an_unknown_history_mode_is_protocol_mismatch_naming_items(api, sandbox, skill, check_error) -> None:
    # D-33 / INV-6: a mode MSP does not define is not read as an empty
    # history; it is protocol_mismatch naming `items`.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_muse_plan", "Plan it", fake={"history_mode": "pagedView"})
    check_error(caught.value, harness="muse", operation="run_muse_plan", code="muse.protocol_mismatch", workspace=sandbox.workspace, thread_id=new_thread(sandbox), observations=[("member", ("items",))])
    assert sandbox.starts("muse-export") == []


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


@pytest.mark.asyncio
@pytest.mark.parametrize(("raised", "code", "observations"), [
    (OSError(errno.ENOSPC, "No space left on device"), "muse.launch_failed", []),
    (KeyError("internal-detail-that-must-not-leak"), "runtime.error", [("exception class", ("KeyError",))]),
], ids=["no-space", "unexpected"])
async def test_an_evidence_folder_failure_after_the_run_carries_the_new_thread(api, sandbox, skill, check_error, monkeypatch, raised, code, observations) -> None:
    # AC-35 / EC-85 / D-34 (r4, S4 R-5): once muse exec returned its
    # thread, the evidence read's private folder fails; the error keeps
    # the new id, whatever its code. Before the run, mkdtemp works.
    real = tempfile.mkdtemp

    def failing_after_the_run(*args, **kwargs):
        if sandbox.answers("muse-exec"):
            raise raised
        return real(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkdtemp", failing_after_the_run)
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_muse_plan", "Plan it")
    check_error(caught.value, harness="muse", operation="run_muse_plan", code=code, workspace=sandbox.workspace, thread_id=new_thread(sandbox), observations=observations)
    assert len(sandbox.starts("muse-exec")) == 1 and sandbox.starts("muse-serve") == []
