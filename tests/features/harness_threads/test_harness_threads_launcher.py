"""FILE: tests/features/harness_threads/test_harness_threads_launcher.py

PURPOSE: Launcher resolution for all three harnesses (D-16, FR-16): PATH lookup, the Grok fallback `~/.grok/bin/grok[.exe]`, not_installed naming what was searched (EC-11), Windows batch launchers refused before anything runs whether found on PATH or passed as a command (AC-12, INV-14, EC-12), a PATH batch hit falling through to the Grok fallback first (EC-12), Muse on win32 never searching PATH (EC-29), a program named like the vendor CLI in the current folder never running, whether or not the real one is on PATH (T-6, R-4), and a private Grok home that cannot be prepared (EC-14).
ROLE IN CODEBASE: Start here when a thread function runs the wrong program, runs a batch file through cmd.exe, or reports a launcher problem with the wrong code.
ARCHITECTURE NOTE: The sandbox points PATH at its own empty bin folder and USERPROFILE/HOME at an empty home, so a missing stand-in can never fall through to a real vendor CLI (the author's machine has ~/.grok/bin/grok.exe). PATH stand-ins are `.exe` launchers on win32 and executable scripts on POSIX; a batch stand-in writes a marker file if anything ever runs it.
FUNCTION INVENTORY: no_command builds the config override that removes <harness>_command; failure_of awaits a call and returns its NativeThreadError, or None when it succeeded; decoy_log moves into the workspace and gives current-folder decoys their own log folder; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new launcher source is a spec change first (D-16), then one test here.
WHAT NOT TO DO IN THIS FILE: Never leave PATH or the user home pointing at the developer's machine.
KNOWN EDGE CASES: shutil.which returns PATHEXT suffixes in upper case (`grok.CMD`), so refused paths are compared case-insensitively on win32. A trailing dot is dropped by Windows when it opens `grok.bat.`, which is why the batch check ignores trailing dots and spaces.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-2, INV-14, §6.2 AC-12, §6.3 EC-11, EC-12, EC-14, EC-29, D-16, §10 T-6, R-20; docs/spec/harness-thread-functions/review.md R-4
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_launcher.py
"""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest

win32_only = pytest.mark.skipif(sys.platform != "win32", reason="batch launchers and Muse WSL resolution exist only on win32 (INV-14, EC-29)")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Muse is looked up on PATH only outside win32 (EC-29)")
COMMAND_FIELDS = {"grok": "grok_command", "opencode": "opencode_command", "muse": "muse_command"}
GROK_FALLBACK_NAME = "grok.exe" if sys.platform == "win32" else "grok"
ROLES = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}


def no_command(harness: str) -> dict:
    return {COMMAND_FIELDS[harness]: None}


async def failure_of(pending: Awaitable[Any], kind: type[BaseException]) -> BaseException | None:
    try:
        await pending
    except kind as error:
        return error
    return None


@pytest.fixture
def decoy_log(sandbox, monkeypatch) -> Path:
    # T-6 / R-4: the caller works from a cloned repository (here the
    # workspace) that ships programs named like the vendor CLIs. Each
    # decoy logs to this folder, so any launch of one leaves a file.
    folder = sandbox.root / "decoy-log"
    folder.mkdir()
    monkeypatch.chdir(sandbox.workspace)
    return folder


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_launcher_is_found_on_path(sandbox, call, harness) -> None:
    # D-16: with no <harness>_command the program is looked up on PATH.
    sandbox.stand_in(sandbox.bin, harness, harness)
    result = await call(harness, config=no_command(harness))
    assert result.thread_id == sandbox.answers(harness)[0]["session"]


@pytest.mark.asyncio
async def test_grok_falls_back_to_the_home_install(sandbox, call) -> None:
    # D-16: PATH has no grok, so ~/.grok/bin/grok[.exe] runs.
    sandbox.stand_in(sandbox.home / ".grok" / "bin", "grok", "grok")
    result = await call("grok", config=no_command("grok"))
    assert result.thread_id == sandbox.answers("grok")[0]["session"]


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_missing_program_is_not_installed_naming_what_was_searched(api, sandbox, call, check_error, pack, harness) -> None:
    # EC-11: the program, PATH and (for Grok) the fallback path that
    # were searched; nothing is written first.
    before = sandbox.snapshot()
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, config=no_command(harness))
    observations = [("program", (harness,)), ("PATH", ("PATH",))]
    if harness == "grok":
        observations.append(("fallback path", pack.path_spellings(sandbox.home / ".grok" / "bin" / GROK_FALLBACK_NAME)))
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.not_installed", workspace=sandbox.workspace, thread_id=None, observations=observations)
    assert sandbox.snapshot() == before, "resolution fails before any write (no private Grok home)"


@pytest.mark.asyncio
@posix_only
async def test_muse_is_found_on_path_and_missing_muse_is_not_installed(api, sandbox, call) -> None:
    # D-16 / EC-11: outside win32 Muse is looked up on PATH.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", config=no_command("muse"))
    assert caught.value.failure_code.value == "muse.not_installed"
    sandbox.stand_in(sandbox.bin, "muse", "muse")
    result = await call("muse", config=no_command("muse"))
    assert result.thread_id == sandbox.answers("muse-exec")[0]["session"]


@pytest.mark.asyncio
@win32_only
async def test_muse_on_windows_without_distro_or_command_is_wsl_unavailable(api, sandbox, call, check_error) -> None:
    # EC-29: Muse on win32 never searches PATH; a muse.exe on PATH is
    # not used.
    sandbox.stand_in(sandbox.bin, "muse", "muse")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", config=no_command("muse"))
    check_error(caught.value, harness="muse", verb="run", code="muse.wsl_unavailable", workspace=sandbox.workspace, thread_id=None)
    assert sandbox.starts() == []


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_batch_launcher_found_on_path_is_refused(api, sandbox, call, check_error, pack, harness) -> None:
    # AC-12 / INV-14: grok.cmd or opencode.cmd first on PATH, no Grok
    # fallback in the empty home.
    batch, marker = sandbox.batch_file(sandbox.bin, f"{harness}.cmd")
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, config=no_command(harness))
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.launcher_refused", workspace=sandbox.workspace, thread_id=None, observations=[("refused path", pack.path_spellings(batch))])
    assert not marker.exists() and sandbox.starts() == []


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
@pytest.mark.parametrize(("name", "suffix"), [("launcher.cmd", ""), ("launcher.bat", ""), ("launcher.CMD", ""), ("launcher.bat", "."), ("launcher.cmd", " ")], ids=["cmd", "bat", "upper-cmd", "bat-trailing-dot", "cmd-trailing-space"])
async def test_batch_file_passed_as_the_command_is_refused(api, sandbox, call, check_error, pack, harness, name, suffix) -> None:
    # AC-12 / INV-14 / EC-12: .cmd or .bat, case-insensitive, ignoring
    # trailing dots and spaces, for all three harnesses.
    batch, marker = sandbox.batch_file(sandbox.root / "batch", f"{harness}-{name}")
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, command=(str(batch) + suffix,))
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.launcher_refused", workspace=sandbox.workspace, thread_id=None, observations=[("refused path", pack.path_spellings(batch))])
    assert not marker.exists() and sandbox.starts() == []


@pytest.mark.asyncio
@win32_only
async def test_grok_batch_on_path_falls_through_to_the_home_install(sandbox, call) -> None:
    # EC-12 / D-16: the npm grok.cmd first on PATH is skipped in favour
    # of ~/.grok/bin/grok.exe.
    batch, marker = sandbox.batch_file(sandbox.bin, "grok.cmd")
    sandbox.stand_in(sandbox.home / ".grok" / "bin", "grok", "grok")
    result = await call("grok", config=no_command("grok"))
    assert result.thread_id == sandbox.answers("grok")[0]["session"]
    assert not marker.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_program_in_the_current_folder_is_never_launched(api, sandbox, call, check_error, decoy_log, harness) -> None:
    # T-6 / D-16 / R-4: only PATH and the Grok fallback are searched,
    # never the current folder, so the decoy never runs or sees the key.
    sandbox.stand_in(sandbox.workspace, harness, harness, log_dir=str(decoy_log))
    error = await failure_of(call(harness, config=no_command(harness)), api.NativeThreadError)
    assert list(decoy_log.iterdir()) == [], f"R-4: the {harness} program in the current folder was launched"
    check_error(error, harness=harness, verb="run", code=f"{harness}.not_installed", workspace=sandbox.workspace, thread_id=None)


@pytest.mark.asyncio
@win32_only
async def test_wsl_exe_in_the_current_folder_is_never_launched(api, sandbox, call, check_error, pack, decoy_log, wsl_ready) -> None:
    # T-6 / EC-29 / R-4: wsl.exe is looked up on PATH only; a decoy in
    # the current folder never runs or sees META_API_KEY.
    sandbox.stand_in(sandbox.workspace, "wsl", "muse", as_wsl=True, wsl={"distros": [pack.FAKE_DISTRO]}, log_dir=str(decoy_log))
    error = await failure_of(call("muse", config={"muse_command": None, "wsl_distro": pack.FAKE_DISTRO}), api.NativeThreadError)
    assert list(decoy_log.iterdir()) == [], "R-4: the wsl.exe in the current folder was launched"
    check_error(error, harness="muse", verb="run", code="muse.wsl_unavailable", workspace=sandbox.workspace, thread_id=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "how"), [("grok", "search"), ("opencode", "search"), ("grok", "bare-command"), ("opencode", "bare-command"), ("muse", "bare-command")])
async def test_program_on_path_runs_and_a_current_folder_decoy_never_does(sandbox, call, decoy_log, harness, how) -> None:
    # D-16 / T-6 / R-4: the same name on PATH and in the current folder
    # runs the PATH program, whether the SDK searched for it or the
    # caller named it bare in <harness>_command.
    sandbox.stand_in(sandbox.bin, harness, harness)
    sandbox.stand_in(sandbox.workspace, harness, harness, log_dir=str(decoy_log))
    arguments = {"config": no_command(harness)} if how == "search" else {"command": (harness,)}
    result = await call(harness, **arguments)
    assert list(decoy_log.iterdir()) == [], f"R-4: the {harness} program in the current folder was launched"
    assert result.thread_id == sandbox.answers(ROLES[harness])[0]["session"]


@pytest.mark.asyncio
@win32_only
async def test_wsl_exe_on_path_runs_and_a_current_folder_decoy_never_does(sandbox, call, pack, decoy_log, wsl_ready) -> None:
    # EC-29 / T-6 / R-4: the wsl.exe on PATH starts Muse in the distro.
    distros = {"distros": [pack.FAKE_DISTRO]}
    sandbox.stand_in(sandbox.bin, "wsl", "muse", as_wsl=True, wsl=distros)
    sandbox.stand_in(sandbox.workspace, "wsl", "muse", as_wsl=True, wsl=distros, log_dir=str(decoy_log))
    result = await call("muse", config={"muse_command": None, "wsl_distro": pack.FAKE_DISTRO})
    assert list(decoy_log.iterdir()) == [], "R-4: the wsl.exe in the current folder was launched"
    assert sandbox.only_start("muse-exec")["via_wsl"] is True
    assert result.thread_id == sandbox.answers("muse-exec")[0]["session"]


@pytest.mark.asyncio
@pytest.mark.parametrize("blocker", [".vidbyte", ".vidbyte/grok-homes"])
async def test_unpreparable_private_home_is_launch_failed(api, sandbox, call, check_error, pack, blocker) -> None:
    # EC-14: a file where the private home's parent folder must be is
    # grok.launch_failed naming the home; nothing runs.
    target = sandbox.home / blocker
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("a file, not a folder\n", encoding="utf-8")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok")
    check_error(caught.value, harness="grok", verb="run", code="grok.launch_failed", workspace=sandbox.workspace, thread_id=None, observations=[("private home", pack.path_spellings(sandbox.grok_home()))])
    assert sandbox.starts() == []


@pytest.mark.asyncio
async def test_undeterminable_user_home_is_launch_failed(api, sandbox, call, monkeypatch) -> None:
    # EC-14 / R-20: Path.home() raising RuntimeError (no
    # HOME/USERPROFILE, no passwd entry) is grok.launch_failed, not
    # runtime.error.
    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    command = sandbox.command("grok")
    monkeypatch.setattr(pathlib.Path, "home", classmethod(no_home))
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok", command=command)
    assert caught.value.failure_code.value == "grok.launch_failed"
    assert sandbox.starts() == []
