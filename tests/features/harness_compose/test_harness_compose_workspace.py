"""FILE: tests/features/harness_compose/test_harness_compose_workspace.py

PURPOSE: The two workspace plumbing context managers (AC-17, AC-18, INV-7 to INV-9, D-6, EC-5 to EC-7, EC-74, A-9): capture_diff gives exactly the change made inside its block, from git's object store, so earlier uncommitted edits and untracked files never show and core.autocrlf adds no carriage returns, with the text and file list cut at their caps and flagged; in_worktree yields a folder outside the repository holding the committed, edited and untracked content but not ignored files, isolates writes, creates an empty workspace folder no snapshot holds, and removes the worktree after a normal exit and after a raising block whose exception propagates unchanged; neither touches the real index, HEAD, refs or stash; with no commit, in_worktree is WORKTREE_FAILED while capture_diff works.
ROLE IN CODEBASE: Start here when a diff shows changes that came before the block, a worktree misses uncommitted work, or a worktree outlives its block.
ARCHITECTURE NOTE: Expected diffs come from the conftest tree oracle taken just before and just after each block. The writer in AC-17 is a real Grok step called directly inside the block, so the capture is exercised around a real child process.
FUNCTION INVENTORY: the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new plumbing behaviour gets its own repository state built with sandbox.make_repo and sandbox.write.
WHAT NOT TO DO IN THIS FILE: Do not write files with text mode; line endings are part of what is tested, so every write here is bytes.
KNOWN EDGE CASES: COMPOSE_DIFF_MAX_CHARS and COMPOSE_DIFF_MAX_FILES are read by compose at call time, so the tests lower them on vidbyte.lib.constants.native_compose. The local core.autocrlf=true stands in for the Windows default on every platform (A-9).
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-7 to INV-9, §6.2 AC-17, AC-18, §6.3 EC-5 to EC-7, EC-74, §9.2 capture_diff, in_worktree
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_workspace.py
"""

from __future__ import annotations

import pytest

COMMITTED = {"README.md": "# Demo\nline two\n", "cli.py": "def main():\n    return 0\n", ".gitignore": "*.log\n"}


@pytest.mark.asyncio
async def test_capture_diff_shows_only_the_blocks_change_without_line_ending_noise(compose_api, sandbox, steps, runs, pack, monkeypatch) -> None:
    # AC-17 / INV-7 / INV-8 / EC-6 / EC-7 / A-9: earlier CRLF edits and
    # an earlier untracked file stay out; the writer's edit to the
    # already-edited file and its new file are in, exactly as the
    # oracle sees them.
    api = compose_api
    sandbox.make_repo(files=COMMITTED)
    sandbox.git("config", "core.autocrlf", "true")
    (sandbox.workspace / "README.md").write_bytes(b"# Demo\r\nline two\r\nEARLIER-EDIT\r\n")
    (sandbox.workspace / "old.txt").write_bytes(b"old untracked\n")
    writer = steps.bind("grok", edits=True, label="writer", fake={"write_files": {"README.md": "# Demo\r\nline two\r\nEARLIER-EDIT\r\nWRITER-LINE\r\n", "new.txt": "brand new\n"}})
    real = (sandbox.index_bytes(), sandbox.refs())
    before = sandbox.tree_of()
    async with api.compose.capture_diff(sandbox.workspace) as capture:
        assert capture.diff is None
        await writer("Edit README.md and add new.txt.")
    files, text = sandbox.tree_diff(before, sandbox.tree_of())
    assert files == ("README.md", "new.txt")
    assert capture.diff.files == files and capture.diff.text == text and capture.diff.truncated is False
    assert "\r" not in capture.diff.text
    assert "+WRITER-LINE" in text and "+brand new" in text
    assert "+EARLIER-EDIT" not in capture.diff.text and "old.txt" not in capture.diff.text and "old untracked" not in capture.diff.text

    monkeypatch.setattr(api.constants, "COMPOSE_DIFF_MAX_CHARS", 40)
    before = sandbox.tree_of()
    async with api.compose.capture_diff(sandbox.workspace) as cut:
        sandbox.write(sandbox.workspace, {"second.txt": "second change\n" * 5})
    files, text = sandbox.tree_diff(before, sandbox.tree_of())
    assert len(text) > 40
    assert cut.diff.text == text[:40] and cut.diff.truncated is True and cut.diff.files == files

    monkeypatch.setattr(api.constants, "COMPOSE_DIFF_MAX_CHARS", api.threads_constants.NATIVE_RESULT_TEXT_MAX_CHARS)
    monkeypatch.setattr(api.constants, "COMPOSE_DIFF_MAX_FILES", 1)
    before = sandbox.tree_of()
    async with api.compose.capture_diff(sandbox.workspace) as listed:
        sandbox.write(sandbox.workspace, {"a-third.txt": "third\n", "b-fourth.txt": "fourth\n"})
    files, _text = sandbox.tree_diff(before, sandbox.tree_of())
    assert files == ("a-third.txt", "b-fourth.txt")
    assert listed.diff.files == files[:1] and listed.diff.truncated is True
    assert (sandbox.index_bytes(), sandbox.refs()) == real and sandbox.leftovers() == []


@pytest.mark.asyncio
async def test_capture_diff_is_none_after_a_raising_block_whose_error_propagates(compose_api, sandbox, runs, pack) -> None:
    # §9.2 capture_diff / AC-18: an exception skips the diff, leaves
    # .diff None and propagates as the same object.
    api = compose_api
    sandbox.make_repo(files=COMMITTED)
    boom = KeyError("raised inside the block")
    with pytest.raises(KeyError) as caught:
        async with api.compose.capture_diff(sandbox.workspace) as capture:
            sandbox.write(sandbox.workspace, {"partial.txt": "partial\n"})
            raise boom
    assert caught.value is boom and capture.diff is None
    assert sandbox.leftovers() == []


@pytest.mark.asyncio
async def test_in_worktree_holds_the_working_content_isolates_writes_and_always_goes_away(compose_api, sandbox, runs, pack) -> None:
    # AC-18 / INV-9: committed, edited and untracked content, no ignored
    # file, outside the repository; a write stays inside; removal after
    # a normal exit and after a raise; the real index, refs and stash
    # stay as they were.
    api = compose_api
    sandbox.make_repo(files=COMMITTED)
    sandbox.write(sandbox.workspace, {"cli.py": "def main():\n    return 1  # EDITED\n", "untracked.txt": "untracked\n", "debug.log": "ignored\n"})
    real = (sandbox.index_bytes(), sandbox.refs())
    workspace_files = sandbox.files()
    async with api.compose.in_worktree(sandbox.workspace) as folder:
        assert pack.inside(folder, sandbox.tmp) and not pack.inside(folder, sandbox.workspace)
        assert (folder / "README.md").read_bytes() == COMMITTED["README.md"].encode()
        assert (folder / "cli.py").read_bytes() == b"def main():\n    return 1  # EDITED\n"
        assert (folder / "untracked.txt").read_bytes() == b"untracked\n"
        assert not (folder / "debug.log").exists(), "ignored files are not in the snapshot"
        (folder / "made-in-worktree.txt").write_bytes(b"stays here\n")
        (folder / "cli.py").write_bytes(b"changed in the worktree\n")
    assert not folder.exists() and sandbox.worktrees() == 1
    assert sandbox.files() == workspace_files and not (sandbox.workspace / "made-in-worktree.txt").exists()

    boom = RuntimeError("the block failed")
    with pytest.raises(RuntimeError) as caught:
        async with api.compose.in_worktree(sandbox.workspace) as raised_in:
            raise boom
    assert caught.value is boom
    assert not raised_in.exists() and sandbox.worktrees() == 1
    assert (sandbox.index_bytes(), sandbox.refs()) == real and sandbox.leftovers() == []


@pytest.mark.asyncio
async def test_in_worktree_creates_an_empty_workspace_folder_no_snapshot_holds(compose_api, sandbox, runs, pack) -> None:
    # EC-74 / INV-9 / EC-10: the workspace is an empty subfolder, so the
    # yielded folder is created at the same path inside the worktree.
    api = compose_api
    sandbox.make_repo(files=COMMITTED)
    empty = sandbox.workspace / "pkg" / "empty"
    empty.mkdir(parents=True)
    async with api.compose.in_worktree(empty) as folder:
        assert folder.is_dir() and list(folder.iterdir()) == []
        assert folder.name == "empty" and folder.parent.name == "pkg"
        assert (folder.parent.parent / "README.md").is_file(), "the folder sits at the workspace's path inside the worktree"
    assert not folder.exists() and sandbox.worktrees() == 1 and sandbox.leftovers() == []


@pytest.mark.asyncio
async def test_repository_with_no_commit_refuses_in_worktree_but_captures_diffs(compose_api, sandbox, runs, pack, check_compose_error) -> None:
    # AC-18 / EC-5: worktree add needs HEAD, so in_worktree is
    # WORKTREE_FAILED; snapshots skip read-tree, so capture_diff works.
    api = compose_api
    unborn = sandbox.make_repo(sandbox.root / "unborn", commit=False)
    with pytest.raises(api.ThreadComposeError) as caught:
        async with api.compose.in_worktree(unborn):
            raise AssertionError("the block must not run without a commit")
    check_compose_error(caught.value, problem="worktree_failed", workspace=unborn)
    async with api.compose.capture_diff(unborn) as capture:
        sandbox.write(unborn, {"fresh.txt": "fresh\n"})
    assert capture.diff.files == ("fresh.txt",) and "+fresh" in capture.diff.text
    assert sandbox.leftovers() == []
