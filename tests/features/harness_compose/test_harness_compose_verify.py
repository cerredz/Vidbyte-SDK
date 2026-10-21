"""FILE: tests/features/harness_compose/test_harness_compose_verify.py

PURPOSE: verify_with and the trio aliases (AC-3, AC-8a, AC-8b, INV-9 to INV-12, INV-14 to INV-16, INV-25, EC-18, EC-52, EC-63): the writer runs first, alone, in place; a Grok reader runs in place with its own PLAN mode; an opencode or Muse reader runs in a disposable worktree under the temporary folder that holds the writer's change; every verifier prompt carries the writer's diff and never the writer's answer; the backstop raises READER_CHANGED_WORKSPACE after every verifier finished when a Grok reader writes, and a worktree reader's writes never reach the workspace; a failed writer stops the verifiers but keeps its diff; a failed verifier stops no sibling; agreement follows INV-25.
ROLE IN CODEBASE: Start here when a review runs in the wrong place, sees the wrong change, or lets a reviewer's edit through.
ARCHITECTURE NOTE: Where each step ran is read from the stand-in start records (cwd, --cwd, --dir, --workspace) and what a worktree reader saw from the digests the stand-in logged (observe_files). Ordering comes from the CliRunner spy's enter and exit events. Expected diffs come from the conftest tree oracle.
FUNCTION INVENTORY: first_folder_under names the folder a path occupies directly under the temporary folder; last_git_index finds the last git child running a subcommand; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Give every stand-in in a test its own label, and assert on launches by label.
WHAT NOT TO DO IN THIS FILE: Do not read compose's worktree folder names from anything but the stand-in logs; the folder is gone once the call returns.
KNOWN EDGE CASES: A Muse RUN reader starts only `muse exec`; `muse serve` appears only for its continue turns. The backstop's after-snapshot runs once every reader worktree is removed, so its write-tree is the last git child that starts after the verifiers exit.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-9 to INV-16, INV-25, §6.2 AC-3, AC-8, §6.3 EC-18, EC-52, EC-63
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_verify.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FEATURE = "FEATURE-9c1e\nadded by the writer\n"
WRITER_TEXT = "WRITER-ANSWER-TEXT-55aa: I added feature.txt."


def first_folder_under(path: str, folder: Path) -> str:
    child = Path(os.path.normcase(str(Path(path).resolve())))
    parent = Path(os.path.normcase(str(folder.resolve())))
    return child.relative_to(parent).parts[0]


def last_git_index(runs, word: str) -> int:
    return max(index for index, item in runs.git_calls() if runs.subcommand(item)[:1] == [word])


@pytest.mark.asyncio
async def test_trio_runs_the_writer_alone_then_reviews_its_diff_in_place_and_in_a_worktree(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-3 / INV-9 / INV-10 / INV-12 / INV-25.
    api = compose_api
    sandbox.make_repo()
    before = sandbox.tree_of()
    writer = steps.bind("opencode", label="writer", fake={"final_parts": [WRITER_TEXT], "write_files": {"feature.txt": FEATURE}})
    grok = steps.bind("grok", plan=True, label="grok-reader", fake={"text": pack.verdict_json("approve")})
    muse = steps.bind("muse", label="muse-reader", fake={"text": pack.verdict_json("reject", findings=["Add a test."]), "observe_files": ["feature.txt", "README.md"]})
    result = await api.compose.run_opencode_verify_with_grok_and_muse(pack.PROMPT, writer=writer, grok=grok, muse=muse)
    after = sandbox.tree_of()
    files, diff_text = sandbox.tree_diff(before, after)
    assert files == ("feature.txt",)

    # The writer first, alone, in the workspace.
    (writer_call,) = runs.calls_of("writer")
    reader_calls = runs.calls_of("grok-reader") + runs.calls_of("muse-reader")
    assert len(reader_calls) == 2
    assert all(runs.position("exit", writer_call) < runs.position("enter", reader) for reader in reader_calls)
    writer_launch = sandbox.only_launch("writer")
    assert pack.launch_prompt(writer_launch) == pack.PROMPT
    assert pack.same_path(writer_launch["start"]["cwd"], sandbox.workspace) and pack.same_path(pack.launch_workspace(writer_launch), sandbox.workspace)

    # Grok reviews in place, in its own PLAN mode.
    grok_launch = sandbox.only_launch("grok-reader")
    assert pack.same_path(grok_launch["start"]["cwd"], sandbox.workspace) and pack.same_path(pack.launch_workspace(grok_launch), sandbox.workspace)
    assert "--permission-mode=plan" in grok_launch["start"]["argv"]

    # Muse reviews in a compose worktree under the temporary folder,
    # which holds the writer's file and the committed content.
    muse_launch = sandbox.only_launch("muse-reader")
    folder = pack.launch_workspace(muse_launch)
    assert pack.inside(folder, sandbox.tmp) and not pack.inside(folder, sandbox.workspace)
    assert first_folder_under(folder, sandbox.tmp).startswith(os.path.normcase(pack.WORKTREE_PREFIX))
    assert pack.same_path(muse_launch["start"]["cwd"], folder)
    assert pack.launch_observed(muse_launch) == {"feature.txt": pack.text_digest(FEATURE), "README.md": pack.text_digest(pack.DEFAULT_FILES["README.md"])}
    assert not Path(folder).exists(), "the worktree folder is removed"

    # Each verifier prompt carries the diff and the
    # verdict schema, never the writer's answer.
    for launch in (grok_launch, muse_launch):
        prompt = pack.launch_prompt(launch)
        assert pack.PROMPT in prompt and "feature.txt" in prompt and "+FEATURE-9c1e" in prompt
        assert WRITER_TEXT not in prompt
        assert all(chunk in prompt for chunk in pack.literal_chunks("verdict_schema"))

    # The record: writer with its diff, verdicts in verifier order.
    assert result.writer.ok and result.writer.text == WRITER_TEXT
    assert (result.writer.diff.files, result.writer.diff.text, result.writer.diff.truncated) == (files, diff_text, False)
    assert [answer.value.decision.value for answer in result.verdicts] == ["approve", "reject"]
    assert result.verdicts[1].value.findings == ("Add a test.",)
    assert [len(answer.turns) for answer in result.verdicts] == [1, 1]
    assert result.agreement is False and result.failed_verifiers == ()

    # Afterwards: no worktree, no leftovers, the tree right after the
    # writer.
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1
    assert sandbox.tree_of() == after and sandbox.status() == {"?? feature.txt"}


@pytest.mark.asyncio
async def test_grok_reader_that_writes_raises_reader_changed_after_every_verifier(compose_api, sandbox, steps, runs, pack, check_compose_error) -> None:
    # AC-8a / INV-11 / T-1: the backstop compares the phase snapshots
    # once both verifiers finished; the error names the file and the
    # workspace and carries the record so far.
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("opencode", label="writer", fake={"write_files": {"feature.txt": FEATURE}})
    grok = steps.bind("grok", plan=True, label="grok-writes", fake={"text": pack.verdict_json("approve"), "write_files": {"grok-was-here.txt": "oops\n"}})
    calm = steps.bind("opencode", label="calm", fake={"final_parts": [pack.verdict_json("approve")]})
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(writer, [grok, calm], prompt=pack.PROMPT)
    error = caught.value
    check_compose_error(error, problem="reader_changed_workspace", workspace=sandbox.workspace, observations=[("changed file", ("grok-was-here.txt",))])
    assert error.diff.files == ("grok-was-here.txt",) and "+oops" in error.diff.text
    assert isinstance(error.result, api.records.VerifyResult)
    assert error.result.writer.ok and error.result.writer.diff.files == ("feature.txt",)
    assert [answer.value.decision.value for answer in error.result.verdicts] == ["approve", "approve"]
    assert all(pack.launch_answered(sandbox.only_launch(label)) for label in ("grok-writes", "calm"))
    verifier_exits = [runs.position("exit", index) for label in ("grok-writes", "calm") for index in runs.calls_of(label)]
    assert runs.position("enter", last_git_index(runs, "write-tree")) > max(verifier_exits), "the backstop snapshot follows every verifier"
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_worktree_readers_that_write_leave_the_workspace_untouched(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-8b / INV-9: the writes land only in each reader's worktree,
    # which is removed; the verdicts stand.
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("grok", edits=True, label="writer", fake={"write_files": {"feature.txt": FEATURE}})
    opencode = steps.bind("opencode", label="oc-writes", fake={"final_parts": [pack.verdict_json("approve")], "write_files": {"oc-note.txt": "from opencode\n"}})
    muse = steps.bind("muse", label="muse-writes", fake={"text": pack.verdict_json("approve"), "write_files": {"muse-note.txt": "from muse\n"}})
    result = await api.compose.run_grok_verify_with_opencode_and_muse(pack.PROMPT, writer=writer, opencode=opencode, muse=muse)
    assert [answer.value.decision.value for answer in result.verdicts] == ["approve", "approve"] and result.agreement is True
    for label in ("oc-writes", "muse-writes"):
        launch = sandbox.only_launch(label)
        assert any(record["kind"] == "wrote" for record in launch["records"])
        folder = pack.launch_workspace(launch)
        assert pack.inside(folder, sandbox.tmp) and not Path(folder).exists()
    expected = {**{name: pack.text_digest(text) for name, text in pack.DEFAULT_FILES.items()}, "feature.txt": pack.text_digest(FEATURE)}
    assert sandbox.files() == expected
    assert sandbox.status() == {"?? feature.txt"}
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_failed_writer_runs_no_verifier_but_keeps_its_diff(compose_api, sandbox, steps, runs, pack) -> None:
    # EC-52 / INV-16: the writer's diff is taken even though it failed;
    # no verifier starts; verdicts are empty and agreement is False.
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("opencode", label="writer", fake={"mode": "fail", "vendor_text": "the edit was refused halfway", "write_files": {"half.txt": "half done\n"}})
    verifier = steps.bind("grok", plan=True, label="never")
    result = await api.compose.verify_with(writer, [verifier], prompt=pack.PROMPT)
    assert not result.writer.ok and result.writer.error.failure_code.value == "opencode.run_failed"
    assert result.writer.diff.files == ("half.txt",) and "+half done" in result.writer.diff.text
    assert result.verdicts == () and result.agreement is False and result.failed_verifiers == ()
    assert sandbox.launches(label="never") == [] and runs.calls_of("never") == []
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_failed_verifier_stops_no_sibling_and_one_verdict_can_agree(compose_api, sandbox, steps, runs, pack) -> None:
    # EC-18 / INV-14 / INV-25 / EC-63: a key_rejected verifier is
    # recorded as its verdict's last turn while its sibling finishes;
    # a single parsed verdict is agreement.
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("grok", edits=True, label="writer", fake={"write_files": {"feature.txt": FEATURE}})
    rejected = steps.bind("opencode", label="rejected", fake={"mode": "key_rejected"})
    fine = steps.bind("grok", plan=True, label="fine", fake={"text": pack.verdict_json("approve")})
    result = await api.compose.verify_with(writer, [rejected, fine], prompt=pack.PROMPT)
    assert result.failed_verifiers == (0,) and result.agreement is False
    assert result.verdicts[0].value is None and result.verdicts[0].turns[-1].error.failure_code.value == "opencode.key_rejected"
    assert len(result.verdicts[0].turns) == 1, "a NativeThreadError ends the answer without a repair turn"
    assert result.verdicts[1].ok and result.verdicts[1].value.decision.value == "approve"
    alone = await api.compose.verify_with(writer, [fine], prompt=pack.PROMPT)
    assert alone.agreement is True and alone.failed_verifiers == ()
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1
