"""FILE: tests/features/harness_compose/test_harness_compose_git.py

PURPOSE: Git as a closed, hygienic dependency (AC-13, INV-6, INV-7, INV-26, T-6, EC-1 to EC-5, EC-10, EC-58, EC-59, EC-73): outside a repository every git-needing call raises NOT_A_GIT_REPOSITORY and with no git, or a git the OS will not start, GIT_UNAVAILABLE, before any vendor launch; every git child has the §9.2 argv, working folder and environment, holds no caller or model text and no caret, never sees the caller's repository-location variables, and leaves the real index, HEAD, refs and a decoy repository untouched; a hostile diff.external or textconv driver never runs; a nested repository with no commit fails the snapshot as GIT_FAILED naming add, with the two add texts; an unborn repository allows Grok readers and refuses worktree readers before any step.
ROLE IN CODEBASE: Start here when compose runs git in the wrong place, with the wrong arguments or environment, or turns a git failure into anything but ThreadComposeError.
ARCHITECTURE NOTE: Every git child is read from the CliRunner spy exactly as CliRunner received it. Expected tree ids come from the conftest oracle (a temporary index outside the repository), so the read-tree and diff arguments are checked against trees compose never computed. The hostile-driver test first proves with the test's own git that the planted drivers do run, and skips when this git will not run them.
FUNCTION INVENTORY: classify names the §9.2 command one git argv is; git_needing_call makes one of the five git-needing calls; enter_capture and enter_worktree enter the two context managers; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new git command is a §9.2 row first, then one classify branch and its expected working folder.
WHAT NOT TO DO IN THIS FILE: Do not run compose's git commands yourself to build expectations; use the oracle helpers in conftest.
KNOWN EDGE CASES: The caller's GIT_DIR and friends are set only after the test's repositories exist; the sandbox's own git helper strips them. git prints paths with forward slashes on win32, so paths are compared after resolve and normcase.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-6, INV-7, INV-26, §6.2 AC-13, §6.3 EC-1 to EC-5, EC-10, EC-58, EC-59, EC-73, §9.2 git commands, §9.3, §10 T-6, T-8
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_git.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

CALLS = ("verify_with", "run_ensemble", "chain_threads", "capture_diff", "in_worktree")
SNAPSHOT_KINDS = ("snapshot-read", "snapshot-add", "snapshot-write")
ROOT_KINDS = SNAPSHOT_KINDS + ("diff-names", "diff-text", "worktree-add", "worktree-remove")
WORKSPACE_KINDS = ("toplevel", "has-commit")
WORKTREE_KINDS = ("worktree-fill", "worktree-index")
DECOY_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")


def classify(words: list[str], tree) -> str | None:
    # The §9.2 command this subcommand is, or None.
    if words == ["rev-parse", "--show-toplevel"]:
        return "toplevel"
    if words == ["rev-parse", "--verify", "--quiet", "HEAD"]:
        return "has-commit"
    if words == ["read-tree", "HEAD"]:
        return "snapshot-read"
    if words == ["add", "-A"]:
        return "snapshot-add"
    if words == ["write-tree"]:
        return "snapshot-write"
    if len(words) == 6 and words[:4] == ["diff", "--name-only", "-z", "--no-renames"] and all(tree.match(word) for word in words[4:]):
        return "diff-names"
    if len(words) == 7 and words[:5] == ["diff", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames"] and all(tree.match(word) for word in words[5:]):
        return "diff-text"
    if len(words) == 6 and words[:4] == ["worktree", "add", "--detach", "--no-checkout"] and words[5] == "HEAD":
        return "worktree-add"
    if len(words) == 4 and words[:3] == ["read-tree", "-u", "--reset"] and tree.match(words[3]):
        return "worktree-fill"
    if len(words) == 2 and words[0] == "read-tree" and tree.match(words[1]):
        return "worktree-index"
    if len(words) == 4 and words[:3] == ["worktree", "remove", "--force"]:
        return "worktree-remove"
    return None


async def enter_capture(api, workspace) -> None:
    async with api.compose.capture_diff(workspace):
        raise AssertionError("the capture block must not run")


async def enter_worktree(api, workspace) -> None:
    async with api.compose.in_worktree(workspace):
        raise AssertionError("the worktree block must not run")


def git_needing_call(api, steps, pack, sandbox, which: str):
    if which == "verify_with":
        return api.compose.verify_with(steps.bind("grok", edits=True, label="writer"), [steps.bind("grok", plan=True, label="reader")], prompt=pack.PROMPT)
    if which == "run_ensemble":
        roster = api.ensemble.EnsembleRoster(planner=steps.bind("grok", plan=True, label="planner"), proposers=[steps.bind("grok", plan=True, label="proposer")], selector=steps.bind("grok", plan=True, label="selector"), implementer=steps.bind("grok", edits=True, label="implementer"))
        return api.compose.run_ensemble(pack.TASK, roster)
    if which == "chain_threads":
        return api.compose.chain_threads([steps.bind("opencode", label="first"), steps.bind("grok", label="second")], prompt=pack.PROMPT)
    if which == "capture_diff":
        return enter_capture(api, sandbox.workspace)
    return enter_worktree(api, sandbox.workspace)


@pytest.mark.asyncio
@pytest.mark.parametrize("which", CALLS)
async def test_folder_outside_any_repository_is_not_a_git_repository(compose_api, sandbox, steps, runs, pack, check_compose_error, which) -> None:
    # AC-13a / EC-1: rev-parse fails with 128 before any vendor launch;
    # the error names the workspace and quotes git.
    api = compose_api
    with pytest.raises(api.ThreadComposeError) as caught:
        await git_needing_call(api, steps, pack, sandbox, which)
    check_compose_error(caught.value, problem="not_a_git_repository", workspace=sandbox.workspace, observations=[("subcommand", ("rev-parse",)), ("exit status", ("128",))], git_text="not a git repository")
    assert runs.vendor_calls() == [] and sandbox.launches() == []
    assert sandbox.leftovers() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("which", CALLS)
async def test_no_git_on_path_is_git_unavailable_before_any_launch(compose_api, sandbox, steps, runs, pack, check_compose_error, monkeypatch, which) -> None:
    # AC-13b / EC-2: find_program finds nothing, nothing starts.
    api = compose_api
    sandbox.make_repo()
    monkeypatch.setenv("PATH", str(sandbox.bin))
    with pytest.raises(api.ThreadComposeError) as caught:
        await git_needing_call(api, steps, pack, sandbox, which)
    check_compose_error(caught.value, problem="git_unavailable", workspace=sandbox.workspace)
    assert runs.invocations == [] or all(runs.is_git(item) for item in runs.invocations)
    assert sandbox.launches() == [] and sandbox.leftovers() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["verify_with", "capture_diff"])
async def test_git_the_os_will_not_start_is_git_unavailable(compose_api, sandbox, steps, runs, pack, check_compose_error, monkeypatch, which) -> None:
    # EC-3: a broken git file is found but refused by the OS.
    api = compose_api
    sandbox.make_repo()
    broken = sandbox.root / "brokengit"
    broken.mkdir()
    target = broken / ("git.exe" if sys.platform == "win32" else "git")
    target.write_bytes(b"\x00\x01 this is not a program \x02\x03" * 64)
    target.chmod(0o755)
    monkeypatch.setenv("PATH", str(broken))
    with pytest.raises(api.ThreadComposeError) as caught:
        await git_needing_call(api, steps, pack, sandbox, which)
    check_compose_error(caught.value, problem="git_unavailable", workspace=sandbox.workspace)
    assert all(runs.is_git(item) for item in runs.invocations)
    assert sandbox.launches() == [] and sandbox.leftovers() == []


@pytest.mark.asyncio
async def test_every_git_child_is_the_spec_command_in_the_spec_place_with_a_clean_environment(compose_api, sandbox, steps, runs, pack, monkeypatch) -> None:
    # INV-26 / INV-7 / INV-9 / EC-10 / EC-58 / T-8: a workspace in a
    # subfolder, a decoy repository named by the caller's location
    # variables; every git child is checked against §9.2 and the oracle.
    api = compose_api
    sandbox.make_repo(files={**pack.DEFAULT_FILES, "pkg/__init__.py": "VERSION = 1\n"})
    workspace = sandbox.workspace / "pkg"
    decoy = sandbox.make_repo(sandbox.root / "decoy", {"decoy.txt": "decoy\n"})
    before_tree = sandbox.tree_of()
    real = (sandbox.index_bytes(), sandbox.refs())
    decoy_state = (sandbox.index_bytes(decoy), sandbox.refs(decoy), sandbox.status(decoy))
    for name, value in zip(DECOY_VARIABLES, (decoy / ".git", decoy, decoy / ".git" / "index", decoy / ".git", decoy / ".git" / "objects"), strict=True):
        monkeypatch.setenv(name, str(value))
    secret = pack.fresh_key("hygiene")
    writer = steps.bind("opencode", label="writer", key=secret, workspace=workspace, fake={"final_parts": ["WRITER-SAYS-hello"], "write_files": {"new.py": "print('new')\n"}})
    reader = steps.bind("opencode", label="oc-reader", key=secret, workspace=workspace, fake={"final_parts": [pack.verdict_json("approve")]})
    grok = steps.bind("grok", plan=True, label="grok-reader", key=secret, workspace=workspace, fake={"text": pack.verdict_json("approve")})
    result = await api.compose.verify_with(writer, [reader, grok], prompt=pack.PROMPT)
    after_tree = sandbox.tree_of()
    assert result.writer.diff.files == ("pkg/new.py",) and result.agreement is True

    constants = api.constants
    kinds: dict[str, list] = {}
    worktree_folder = None
    for _index, item in runs.git_calls():
        argv = list(item.argv)
        assert os.path.isabs(argv[0]) and tuple(argv[1 : 1 + len(pack.GIT_GLOBAL_OPTIONS)]) == pack.GIT_GLOBAL_OPTIONS, argv
        words = runs.subcommand(item)
        kind = classify(words, pack.TREE_ID)
        assert kind is not None, f"a git command §9.2 does not list: {words}"
        kinds.setdefault(kind, []).append(item)
        assert not any("^" in word for word in argv), "INV-26 / EC-65: no caret"
        for text in (pack.PROMPT, secret, "WRITER-SAYS-hello", os.path.normcase(str(workspace)), os.path.normcase(str(sandbox.workspace))):
            assert all(os.path.normcase(text) not in os.path.normcase(word) for word in argv[1:]), f"argv holds a caller value or model text: {words}"
        assert set(pack.GIT_LOCATION_VARIABLES) <= set(item.env_remove), "all 15 location variables are removed"
        assert set(item.env_overlay) <= {"GIT_INDEX_FILE"} and secret not in repr(dict(item.env_overlay))
        assert item.stdin_text is None
        assert item.timeout_seconds == constants.COMPOSE_GIT_TIMEOUT_SECONDS and item.max_output_bytes == constants.COMPOSE_GIT_MAX_OUTPUT_BYTES
        if kind in SNAPSHOT_KINDS:
            index = Path(item.env_overlay["GIT_INDEX_FILE"])
            assert index.name == "index" and index.parent.name.startswith(pack.INDEX_PREFIX) and pack.same_path(index.parent.parent, sandbox.tmp)
        else:
            assert "GIT_INDEX_FILE" not in item.env_overlay
        if kind == "worktree-add":
            worktree_folder = Path(words[4])
            assert pack.same_path(worktree_folder.parent, sandbox.tmp) and worktree_folder.name.startswith(pack.WORKTREE_PREFIX)
    assert set(kinds) == set(ROOT_KINDS + WORKSPACE_KINDS + WORKTREE_KINDS), f"missing commands: {set(ROOT_KINDS + WORKSPACE_KINDS + WORKTREE_KINDS) - set(kinds)}"
    for kind, items in kinds.items():
        for item in items:
            if kind in WORKSPACE_KINDS:
                assert pack.same_path(item.cwd, workspace), f"{kind} runs in the workspace"
            elif kind in ROOT_KINDS:
                assert pack.same_path(item.cwd, sandbox.workspace), f"{kind} runs at the repository root"
            else:
                assert pack.same_path(item.cwd, worktree_folder), f"{kind} runs in the worktree folder"
    assert all(pack.same_path(runs.subcommand(item)[3], worktree_folder) for item in kinds["worktree-remove"])
    assert [runs.subcommand(item)[3] for item in kinds["worktree-fill"]] == [after_tree], "the worktree is filled from the after-writer snapshot"
    assert [runs.subcommand(item)[1] for item in kinds["worktree-index"]] == [before_tree], "the verifier worktree's index is the before-writer snapshot"
    pairs = {tuple(runs.subcommand(item)[-2:]) for item in kinds["diff-names"] + kinds["diff-text"]}
    assert (before_tree, after_tree) in pairs and pairs <= {(before_tree, after_tree), (after_tree, after_tree)}, "diffs compare the oracle's snapshots"
    oc_launch = sandbox.only_launch("oc-reader")
    assert pack.same_path(pack.launch_workspace(oc_launch), worktree_folder / "pkg"), "the reader gets the matching subfolder"
    assert (sandbox.index_bytes(), sandbox.refs()) == real
    assert (sandbox.index_bytes(decoy), sandbox.refs(decoy), sandbox.status(decoy)) == decoy_state
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_hostile_diff_drivers_never_run_under_compose(compose_api, sandbox, runs, pack) -> None:
    # T-6 / EC-59: diff.external and a textconv driver planted in the
    # repository run under a plain git diff (the control) and never
    # under compose's snapshots and diffs.
    api = compose_api
    sandbox.make_repo(files={**pack.DEFAULT_FILES, "notes.txt": "one\n", ".gitattributes": "*.txt diff=evil\n"})
    tools = sandbox.root / "tools"
    external_marker, textconv_marker = sandbox.root / "external.marker", sandbox.root / "textconv.marker"
    external = sandbox.stand_in(tools, "external-diff", "marker", marker_file=str(external_marker))
    textconv = sandbox.stand_in(tools, "textconv", "marker", marker_file=str(textconv_marker))
    sandbox.git("config", "diff.external", external.as_posix())
    sandbox.git("config", "diff.evil.textconv", textconv.as_posix())
    (sandbox.workspace / "notes.txt").write_bytes(b"two\n")
    sandbox.git("diff", "HEAD", check=False)
    sandbox.git("diff", "--no-ext-diff", "HEAD", check=False)
    if not (external_marker.exists() and textconv_marker.exists()):
        pytest.skip("this git did not run the planted drivers in the control, so their absence would prove nothing")
    external_marker.unlink()
    textconv_marker.unlink()
    (sandbox.workspace / "notes.txt").write_bytes(b"one\n")
    async with api.compose.capture_diff(sandbox.workspace) as capture:
        (sandbox.workspace / "notes.txt").write_bytes(b"three\n")
    assert not external_marker.exists(), "diff.external ran under compose"
    assert not textconv_marker.exists(), "a textconv driver ran under compose"
    assert capture.diff.files == ("notes.txt",) and "+three" in capture.diff.text and "-one" in capture.diff.text


@pytest.mark.asyncio
async def test_nested_repository_without_a_commit_fails_the_snapshot_naming_add(compose_api, sandbox, steps, runs, pack, check_compose_error) -> None:
    # EC-73 / EC-4 / INV-6 / INV-7: the writer leaves an untracked
    # repository with no commit; the after-writer add exits 128; the
    # error carries the add texts and the record so far; no verifier
    # starts; the temporary index folder is gone.
    api = compose_api
    sandbox.make_repo()
    nested = {"nested/.git/HEAD": "ref: refs/heads/main\n", "nested/.git/objects/.keep": "", "nested/.git/refs/heads/.keep": "", "nested/inner.txt": "inner\n"}
    writer = steps.bind("grok", edits=True, label="writer", fake={"write_files": nested})
    verifier = steps.bind("grok", plan=True, label="never")
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(writer, [verifier], prompt=pack.PROMPT)
    error = caught.value
    check_compose_error(error, problem="git_failed", workspace=sandbox.workspace, observations=[("subcommand", ("add",)), ("exit status", ("128",))], git_text="does not have a commit checked out", add_texts=True)
    assert len(error.git_message) <= api.constants.COMPOSE_GIT_MESSAGE_MAX_CHARS
    assert isinstance(error.result, api.records.VerifyResult) and error.result.writer.ok and error.result.verdicts == ()
    assert sandbox.launches(label="never") == []
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_unborn_repository_allows_grok_readers_and_refuses_worktree_readers(compose_api, sandbox, steps, runs, pack, check_compose_error) -> None:
    # EC-5 / INV-6 / INV-7: snapshots skip read-tree HEAD and still give
    # the writer's diff; a worktree reader is WORKTREE_FAILED before any
    # step runs.
    api = compose_api
    sandbox.make_repo(commit=False)
    writer = steps.bind("grok", edits=True, label="writer", fake={"write_files": {"feature.txt": "feature\n"}})
    grok = steps.bind("grok", plan=True, label="grok-reader", fake={"text": pack.verdict_json("approve")})
    result = await api.compose.verify_with(writer, [grok], prompt=pack.PROMPT)
    assert result.writer.diff.files == ("feature.txt",) and result.agreement is True
    assert not any(runs.subcommand(item) == ["read-tree", "HEAD"] for _index, item in runs.git_calls())
    launched, calls = len(sandbox.launches()), len(runs.invocations)
    opencode = steps.bind("opencode", label="oc-reader")
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(writer, [opencode], prompt=pack.PROMPT)
    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace)
    assert len(sandbox.launches()) == launched, "refused before any step runs"
    assert all(runs.is_git(item) for item in runs.invocations[calls:])
    assert sandbox.leftovers() == []
