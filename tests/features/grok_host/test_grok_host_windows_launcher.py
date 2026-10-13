"""FILE: tests/features/grok_host/test_grok_host_windows_launcher.py

PURPOSE: EC-157 (added in r8, review R-2): on win32 the Grok launcher is never a batch file. A grok.cmd on PATH with grok_command unset and no ~/.grok/bin/grok.exe, and an explicit grok_command whose program is a .cmd or .bat (any case, trailing dots and spaces dropped), are both refused at __aenter__ with grok.not_installed and that row's own next step, and the batch file never runs.
ROLE IN CODEBASE: Proves the T-2/D-19 Windows launcher rule for vidbyte.harnesses.native.grok.GrokHost. The batch shim is harmless: it only drops a marker file, so a regression that handed the host's argv to cmd.exe would both run the shim and fail the refusal.
ARCHITECTURE NOTE: The shim is a real .cmd that writes a marker into tmp_path and exits non-zero, so it is not an ACP peer. The requests carry the cmd metacharacters "&%^ in the prompt and the model; cmd.exe would re-read them if the host ever started a batch file, so the test asserts the marker is absent rather than depending on a particular injection. These tests are win32-only, because EC-157 applies on win32 only (on POSIX a file named grok.cmd is an ordinary program).
FUNCTION INVENTORY: write_batch_shim writes the harmless marker .cmd; system_folders returns System32 for cmd.exe and taskkill; hostile_turn and hostile_oneshot build requests the records accept whose values hold cmd metacharacters; the test_* functions cover EC-157 on PATH and on an explicit command.
COMMON MODIFICATION PATTERNS: A new refusal case is a new parametrisation of the explicit-command test; keep the shim write-only and non-executing as a peer.
WHAT NOT TO DO IN THIS FILE: 1. Never let the shim exec anything or send a live prompt; it only writes a marker. 2. Do not assert on an injected side effect; assert the marker is absent and __aenter__ refused with EC-157's exact next step.
KNOWN EDGE CASES: __aenter__ starts no process, so under the fix neither the live model check nor the CLI run is reached; under a regression the inner call starts the shim. The trailing-dot and trailing-space variants write a real grok.cmd and pass the path with the extra character, which Windows resolves to the same file.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.3 EC-157, §8.1 D-19, §10 T-2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_windows_launcher.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

win32_only = pytest.mark.skipif(sys.platform != "win32", reason="EC-157 applies on win32 only (D-19); a grok.cmd is an ordinary program on POSIX")
EC157_NEXT_STEP = "On Windows this host does not start a .cmd or .bat launcher; install Grok Build so that ~/.grok/bin/grok.exe exists, or set GrokHostSettings.grok_command to the path of a grok.exe."
HOSTILE_PROMPT = 'List the "&%^ folders.'
HOSTILE_MODEL = 'grok"&%^'
EXPLICIT_CASES = [
    pytest.param("grok.cmd", "", id="cmd"),
    pytest.param("grok.CMD", "", id="cmd-upper"),
    pytest.param("grok.bat", "", id="bat"),
    pytest.param("grok.cmd", ".", id="trailing-dot"),
    pytest.param("grok.cmd", " ", id="trailing-space"),
]


def write_batch_shim(path: Path, marker: Path) -> None:
    # A harmless grok batch launcher: when cmd.exe starts it, it records that it ran and exits without being an ACP peer.
    body = f'@echo off\r\necho ran>"{marker}"\r\nexit /b 1\r\n'
    path.write_text(body, encoding="utf-8", newline="")


def system_folders() -> list[str]:
    # Windows needs System32 for cmd.exe (which would start a .cmd shim) and taskkill (ProcessStopper).
    return [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")]


def hostile_turn(grok_api) -> object:
    return grok_api.GrokTurnRequest(prompt=HOSTILE_PROMPT, model=HOSTILE_MODEL)


def hostile_oneshot(grok_api) -> object:
    return grok_api.GrokOneShotRequest(prompt=HOSTILE_PROMPT, model=HOSTILE_MODEL)


@win32_only
@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["spawn_grok_session", "run_grok_once"])
async def test_grok_cmd_on_path_is_refused_at_aenter_and_never_runs(operation: str, grok_api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fast_stop, check_native_error) -> None:
    # EC-157: grok.cmd on PATH, grok_command unset, no ~/.grok/bin/grok.exe; __aenter__ refuses and the shim never runs.
    marker = tmp_path / "shim-ran.flag"
    path_dir = tmp_path / "pathdir"
    path_dir.mkdir()
    write_batch_shim(path_dir / "grok.cmd", marker)
    home = tmp_path / "empty-home"
    home.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("PATH", os.pathsep.join([str(path_dir), *system_folders()]))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    host = grok_api.GrokHost(grok_api.GrokHostSettings(workspace=workspace))
    with pytest.raises(grok_api.NativeHostError) as caught:
        async with host:
            if operation == "spawn_grok_session":
                await host.spawn_grok_session(hostile_turn(grok_api))
            else:
                await host.run_grok_once(hostile_oneshot(grok_api))
    check_native_error(caught.value, code="grok.not_installed", token="GrokHostSettings.grok_command")
    assert caught.value.next_step == EC157_NEXT_STEP
    assert not marker.exists(), "EC-157: the .cmd launcher must never start"


@win32_only
@pytest.mark.asyncio
@pytest.mark.parametrize(("filename", "trailing"), EXPLICIT_CASES)
async def test_explicit_batch_grok_command_is_refused_at_aenter(filename: str, trailing: str, grok_api, tmp_path: Path, fast_stop, check_native_error) -> None:
    # EC-157: an explicit grok_command whose program is a .cmd or .bat is refused the same way, trailing dots and spaces dropped.
    marker = tmp_path / "shim-ran.flag"
    batch = tmp_path / filename
    write_batch_shim(batch, marker)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    program = str(batch) + trailing
    host = grok_api.GrokHost(grok_api.GrokHostSettings(workspace=workspace, grok_command=(program,)))
    with pytest.raises(grok_api.NativeHostError) as caught:
        async with host:
            await host.run_grok_once(hostile_oneshot(grok_api))
    check_native_error(caught.value, code="grok.not_installed", token="GrokHostSettings.grok_command")
    assert caught.value.next_step == EC157_NEXT_STEP
    assert not marker.exists(), "EC-157: an explicit .cmd launcher must never start"
