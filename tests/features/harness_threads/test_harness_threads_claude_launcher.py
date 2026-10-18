"""FILE: tests/features/harness_threads/test_harness_threads_claude_launcher.py

PURPOSE: How the Claude Code launcher is found (spec claude-thread-functions INV-7 steps 1-3, INV-15, D-19): PATH first, then the native install `~/.local/bin/claude[.exe]` when PATH has none (AC-17), claude.not_installed naming the program, PATH and the fallback that were searched, before anything is written (AC-17, EC-1), Windows batch launchers refused whether found on PATH or passed as claude_command, and a PATH `claude.cmd` falling through to the native install first (AC-17, EC-2), a `claude` in the current folder never launched, and a private config folder or user home that cannot be prepared reported as claude.launch_failed before anything starts (EC-3).
ROLE IN CODEBASE: Start here when a Claude thread function runs the wrong program, runs npm's claude.cmd through cmd.exe, or reports a launcher problem with the wrong code.
ARCHITECTURE NOTE: The sandbox points PATH at its own empty bin folder and USERPROFILE/HOME at an empty home, so a missing stand-in can never fall through to the real claude (the author's machine has ~/.local/bin/claude.exe). PATH stand-ins are `.exe` launchers on win32 and executable scripts on POSIX; a batch stand-in writes a marker file if anything ever runs it. claude_command=None makes the SDK search; the call fixture otherwise passes the stand-in command.
FUNCTION INVENTORY: no_command builds the config that makes the SDK search; failure_of awaits a call and returns its NativeThreadError, or None; decoy_log moves into the workspace, removes NoDefaultCurrentDirectoryInExePath and gives a current-folder decoy its own log folder; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new launcher source is a spec change first (INV-7 step 1, D-19), then one test here.
WHAT NOT TO DO IN THIS FILE: Never leave PATH or the user home pointing at the developer's machine.
KNOWN EDGE CASES: shutil.which returns PATHEXT suffixes in upper case (`claude.CMD`), so refused paths are compared case-insensitively on win32. Windows drops a trailing dot or space when it opens `claude.bat.`, which is why the batch check ignores them. The agent shell sets NoDefaultCurrentDirectoryInExePath, which would keep the current-folder test from ever failing; decoy_log removes it (as #1036's R-31).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-7, INV-13, INV-15, §6.2 AC-17, §6.3 EC-1 to EC-3, §8.1 D-19, §12.3 rows 19 and 32
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_launcher.py
"""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest

win32_only = pytest.mark.skipif(sys.platform != "win32", reason="batch launchers exist only on win32 (INV-15, EC-2)")
FALLBACK_NAME = "claude.exe" if sys.platform == "win32" else "claude"
NO_CURRENT_FOLDER_SEARCH = "NoDefaultCurrentDirectoryInExePath"
BATCH_NAMES = [("launcher.cmd", ""), ("launcher.bat", ""), ("launcher.CMD", ""), ("launcher.bat", "."), ("launcher.cmd", " ")]


def no_command() -> dict:
    return {"claude_command": None}


def fallback_folder(sandbox) -> Path:
    # D-19: the native installer's location under the user home.
    return sandbox.home / ".local" / "bin"


async def failure_of(pending: Awaitable[Any], kind: type[BaseException]) -> BaseException | None:
    try:
        await pending
    except kind as error:
        return error
    return None


@pytest.fixture
def decoy_log(sandbox, monkeypatch) -> Path:
    # The caller works from a cloned repository (the workspace) that
    # ships a program named claude; any launch of it leaves a file here.
    folder = sandbox.root / "decoy-log"
    folder.mkdir()
    monkeypatch.chdir(sandbox.workspace)
    monkeypatch.delenv(NO_CURRENT_FOLDER_SEARCH, raising=False)
    return folder


@pytest.mark.asyncio
async def test_claude_is_found_on_path(sandbox, call) -> None:
    # INV-7 step 1 / AC-17: with no claude_command the program is looked
    # up on PATH.
    sandbox.stand_in(sandbox.bin, "claude", "claude")
    result = await call("claude", config=no_command())
    assert result.thread_id == sandbox.answers("claude")[0]["session"]


@pytest.mark.asyncio
async def test_claude_falls_back_to_the_native_install(sandbox, call) -> None:
    # AC-17 / D-19: PATH holds no claude, so ~/.local/bin/claude[.exe]
    # is started.
    sandbox.stand_in(fallback_folder(sandbox), "claude", "claude")
    result = await call("claude", config=no_command())
    assert result.thread_id == sandbox.answers("claude")[0]["session"]
    assert len(sandbox.starts("claude")) == 1


@pytest.mark.asyncio
async def test_missing_claude_is_not_installed_naming_what_was_searched(api, sandbox, call, check_error, pack) -> None:
    # AC-17 / EC-1: the program, PATH and the fallback path that were
    # searched; resolution fails before any write (no config folder).
    before = sandbox.snapshot()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", config=no_command())
    observations = [("program", ("claude",)), ("PATH", ("PATH",)), ("fallback path", pack.path_spellings(fallback_folder(sandbox) / FALLBACK_NAME))]
    check_error(caught.value, harness="claude", verb="run", code="claude.not_installed", workspace=sandbox.workspace, thread_id=None, observations=observations)
    assert sandbox.snapshot() == before, "EC-1: resolution fails before any write"


@pytest.mark.asyncio
@win32_only
async def test_batch_launcher_found_on_path_is_refused(api, sandbox, call, check_error, pack) -> None:
    # AC-17 / INV-15 / EC-2: npm's claude.cmd first on PATH and no
    # native install.
    batch, marker = sandbox.batch_file(sandbox.bin, "claude.cmd")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", config=no_command())
    check_error(caught.value, harness="claude", verb="run", code="claude.launcher_refused", workspace=sandbox.workspace, thread_id=None, observations=[("refused path", pack.path_spellings(batch))])
    assert not marker.exists() and sandbox.starts() == []


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize(("name", "suffix"), BATCH_NAMES, ids=["cmd", "bat", "upper-cmd", "bat-trailing-dot", "cmd-trailing-space"])
async def test_batch_file_passed_as_claude_command_is_refused(api, sandbox, call, check_error, pack, name, suffix) -> None:
    # AC-17 / INV-15: .cmd or .bat, any case, ignoring trailing dots and
    # spaces.
    batch, marker = sandbox.batch_file(sandbox.root / "batch", f"claude-{name}")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", command=(str(batch) + suffix,))
    check_error(caught.value, harness="claude", verb="run", code="claude.launcher_refused", workspace=sandbox.workspace, thread_id=None, observations=[("refused path", pack.path_spellings(batch))])
    assert not marker.exists() and sandbox.starts() == []


@pytest.mark.asyncio
@win32_only
async def test_batch_on_path_falls_through_to_the_native_install(sandbox, call) -> None:
    # EC-2 / INV-15: claude.cmd first on PATH is skipped in favour of
    # ~/.local/bin/claude.exe.
    batch, marker = sandbox.batch_file(sandbox.bin, "claude.cmd")
    sandbox.stand_in(fallback_folder(sandbox), "claude", "claude")
    result = await call("claude", config=no_command())
    assert result.thread_id == sandbox.answers("claude")[0]["session"]
    assert not marker.exists()


@pytest.mark.asyncio
async def test_claude_in_the_current_folder_is_never_launched(api, sandbox, call, check_error, decoy_log) -> None:
    # INV-7 step 1: only claude_command, PATH and the native install are
    # searched, never the current folder, so the decoy never runs or
    # sees the key.
    sandbox.stand_in(sandbox.workspace, "claude", "claude", log_dir=str(decoy_log))
    error = await failure_of(call("claude", config=no_command()), api.NativeThreadError)
    assert list(decoy_log.iterdir()) == [], "the claude program in the current folder was launched"
    check_error(error, harness="claude", verb="run", code="claude.not_installed", workspace=sandbox.workspace, thread_id=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocker", [".vidbyte", ".vidbyte/claude-configs"])
async def test_unpreparable_config_folder_is_launch_failed(api, sandbox, call, check_error, pack, blocker) -> None:
    # EC-3 / INV-7 step 3: a file where the config folder's parent must
    # be is claude.launch_failed naming the folder; nothing runs.
    target = sandbox.home / blocker
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("a file, not a folder\n", encoding="utf-8")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude")
    check_error(caught.value, harness="claude", verb="run", code="claude.launch_failed", workspace=sandbox.workspace, thread_id=None, observations=[("private config folder", pack.path_spellings(sandbox.claude_config()))])
    head = api.constants.CLAUDE_CONFIG_FAILURE_DETAIL.split("{home}", 1)[0]
    assert head in str(caught.value), "EC-3: the message uses CLAUDE_CONFIG_FAILURE_DETAIL"
    assert sandbox.starts() == []


@pytest.mark.asyncio
async def test_undeterminable_user_home_is_launch_failed(api, sandbox, call, monkeypatch) -> None:
    # EC-3 / D-19: Path.home() raising RuntimeError (no HOME or
    # USERPROFILE) is claude.launch_failed with the unknown-home detail,
    # not runtime.error, and nothing starts.
    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    command = sandbox.command("claude")
    monkeypatch.setattr(pathlib.Path, "home", classmethod(no_home))
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", command=command)
    assert caught.value.failure_code.value == "claude.launch_failed"
    assert api.constants.CLAUDE_CONFIG_UNKNOWN_DETAIL.format(error_type="RuntimeError") in str(caught.value)
    assert sandbox.starts() == []
