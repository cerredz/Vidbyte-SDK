"""FILE: tests/features/grok_host/test_grok_host_acceptance.py

PURPOSE: End-to-end acceptance for GrokHost: the spec §4 snippet run as written (AC-1, both outcomes), a spawn that returns while the turn runs (AC-6), a wait that times out and later succeeds (AC-11), a double interrupt of a finished turn (AC-12), and the module-level run_grok_once (FR-17).
ROLE IN CODEBASE: Start here for a caller-visible regression in vidbyte.harnesses.native.grok. Every test drives the real host over real pipes to fake_grok_peer.py.
ARCHITECTURE NOTE: AC-1 runs the snippet in a fresh interpreter with PATH and HOME pointed at temporary folders, so `grok` resolves only to a shim that execs the fake, or to nothing. The other tests use GrokHostSettings.grok_command, the spec §13 seam.
FUNCTION INVENTORY: write_grok_shim writes a `grok` (POSIX) or `grok.cmd` (Windows) launcher for the fake; run_snippet runs the §4 snippet; the test_* functions are one acceptance criterion each.
COMMON MODIFICATION PATTERNS: If spec §4 changes, update SNIPPET verbatim and the expected lines with it.
WHAT NOT TO DO IN THIS FILE: 1. Do not let the snippet's PATH include a folder that may hold the real grok; it would send a live prompt. 2. Do not loosen the exact expected lines; AC-1 says "exactly the shown result".
KNOWN EDGE CASES: On Windows the shim is a .cmd file, which the transport's Windows launcher resolves through PATHEXT; System32 stays on PATH so cmd.exe and taskkill resolve. The snippet subprocess gets PYTHONPATH set to the worktree so it imports this checkout.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §4, §6.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_acceptance.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FAKE_GROK = Path(__file__).with_name("fake_grok_peer.py")
SNIPPET_TIMEOUT_SECONDS = 120
SHORT_WAIT_SECONDS = 0.3
SNIPPET = '''import asyncio
from pathlib import Path

from vidbyte.harnesses.native.grok import GrokHost
from vidbyte.lib.dataclasses.grok import GrokHostSettings, GrokTurnRequest
from vidbyte.lib.errors import NativeHostError


async def main() -> None:
    settings = GrokHostSettings(workspace=Path.cwd())
    try:
        async with GrokHost(settings) as host:
            # Returns as soon as Grok has the prompt; the turn keeps running.
            handle = await host.spawn_grok_session(GrokTurnRequest(prompt="List the top-level folders."))
            result = await host.wait_grok_turn(handle, timeout_seconds=600)
            print(result.status.value, result.text)
    except NativeHostError as error:
        print(error.failure_code.value, "->", error.next_step)


asyncio.run(main())
'''


def write_grok_shim(folder: Path, scenario_path: Path) -> None:
    # A `grok` on PATH that runs the fake with the scenario, passing the host's arguments through.
    if sys.platform == "win32":
        body = f'@echo off\r\n"{sys.executable}" -u "{FAKE_GROK}" "{scenario_path}" %*\r\n'
        (folder / "grok.cmd").write_text(body, encoding="utf-8", newline="")
        return
    shim = folder / "grok"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -u "{FAKE_GROK}" "{scenario_path}" "$@"\n', encoding="utf-8", newline="\n")
    shim.chmod(0o755)


def run_snippet(tmp_path: Path, path_entries: list[str], *, grok_command: tuple[str, ...] | None = None) -> subprocess.CompletedProcess[str]:
    workspace = tmp_path / "snippet-workspace"
    workspace.mkdir()
    home = tmp_path / "snippet-home"
    home.mkdir()
    snippet = tmp_path / "snippet.py"
    # r8 grant (a): on win32 the §4 snippet reaches the fake through GrokHostSettings.grok_command, because EC-157 refuses a .cmd shim.
    body = SNIPPET if grok_command is None else SNIPPET.replace("GrokHostSettings(workspace=Path.cwd())", f"GrokHostSettings(workspace=Path.cwd(), grok_command={tuple(grok_command)!r})")
    snippet.write_text(body, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env.update({"PATH": os.pathsep.join(path_entries), "HOME": str(home), "USERPROFILE": str(home), "PYTHONPATH": str(REPO_ROOT)})
    return subprocess.run([sys.executable, str(snippet)], cwd=workspace, env=env, capture_output=True, text=True, timeout=SNIPPET_TIMEOUT_SECONDS, check=False)


def system_folders() -> list[str]:
    # Windows needs System32 for cmd.exe (the .cmd shim) and taskkill (ProcessStopper); it holds no grok.
    if sys.platform == "win32":
        return [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")]
    return []


def test_snippet_prints_completed_text_when_grok_is_the_fake(tmp_path: Path, grok_fake) -> None:
    # AC-1, first outcome: `grok` resolves to a fake ACP peer that completes the turn with text "alpha-beta".
    scenario_path = tmp_path / "snippet-scenario.json"
    scenario_path.write_text(json.dumps(grok_fake.scenario()), encoding="utf-8")
    if sys.platform == "win32":
        # r8 grant (a) / AC-1: EC-157 refuses a grok.cmd shim, so win32 reaches the fake through the §13 seam; only System32 is on PATH.
        command = (sys.executable, "-u", str(FAKE_GROK), str(scenario_path))
        completed = run_snippet(tmp_path, system_folders(), grok_command=command)
    else:
        shim_folder = tmp_path / "shim"
        shim_folder.mkdir()
        write_grok_shim(shim_folder, scenario_path)
        completed = run_snippet(tmp_path, [str(shim_folder), *system_folders()])
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "completed alpha-beta", completed.stdout + completed.stderr
    assert grok_fake.received("session/prompt"), "the snippet's prompt reached the fake, not a real grok"


def test_snippet_prints_not_installed_line_when_no_grok_exists(tmp_path: Path) -> None:
    # AC-1, second outcome: no grok on PATH and none at ~/.grok/bin.
    empty = tmp_path / "empty-path"
    empty.mkdir()
    completed = run_snippet(tmp_path, [str(empty)])
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "grok.not_installed -> Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command."


@pytest.mark.asyncio
async def test_spawn_returns_a_handle_while_the_turn_is_still_running(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # AC-6 / INV-11: the handle comes back once the prompt is written; wait returns once the peer finishes.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt="List the top-level folders."))
        assert handle.harness is grok_api.NativeHarness.GROK
        assert len(handle.turn_id) == 32 and handle.turn_id == handle.turn_id.lower()
        prompt_ids = [frame["id"] for frame in grok_fake.received("session/prompt")]
        answered = [record["frame"].get("id") for record in grok_fake.records("sent")]
        assert not any(frame_id in answered for frame_id in prompt_ids), "the turn must still be running when spawn returns"
        with pytest.raises(grok_api.NativeHostError) as still_running:
            await host.wait_grok_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS)
        assert still_running.value.failure_code is grok_api.FailureCode.GROK_TURN_TIMED_OUT
        grok_fake.release()
        result = await host.wait_grok_turn(handle, timeout_seconds=30)
    assert result.status is grok_api.NativeTurnStatus.COMPLETED
    assert result.text == "alpha-beta"
    assert result.stop_reason == "end_turn"
    assert result.handle == handle


@pytest.mark.asyncio
async def test_wait_times_out_then_returns_the_result(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # AC-11 / INV-12: a timed-out wait leaves the turn running, and a later wait gets its outcome.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt="List the top-level folders."))
        with pytest.raises(grok_api.NativeHostError) as first:
            await host.wait_grok_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS)
        check_native_error(first.value, code="grok.turn_timed_out", token="wait_grok_turn", operation="wait_grok_turn")
        assert grok_fake.received("session/cancel") == [], "a timed-out wait never touches the turn"
        grok_fake.release()
        result = await host.wait_grok_turn(handle, timeout_seconds=30)
    assert result.status is grok_api.NativeTurnStatus.COMPLETED
    assert result.interrupt_source is None


@pytest.mark.asyncio
async def test_interrupting_a_finished_turn_twice_reports_not_running(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # AC-12 / EC-52: both calls return was_running=False, raise nothing and send nothing.
    async with make_grok_host() as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt="List the top-level folders."))
        await host.wait_grok_turn(handle, timeout_seconds=30)
        first = await host.interrupt_grok_turn(handle)
        second = await host.interrupt_grok_turn(handle)
    assert first.was_running is False and second.was_running is False
    assert first.handle == handle and second.handle == handle
    assert grok_fake.received("session/cancel") == []


@pytest.mark.asyncio
async def test_module_level_run_grok_once_opens_and_closes_its_own_host(grok_api, grok_fake, fast_stop) -> None:
    # FR-17: run_grok_once(request, *, settings) wraps the one-shot method in its own host.
    settings = grok_api.GrokHostSettings(workspace=grok_fake.workspace, grok_command=grok_fake.command())
    result = await grok_api.run_grok_once(grok_api.GrokOneShotRequest(prompt="Summarise the README."), settings=settings)
    assert result.text == "one-shot answer"
    assert result.text_truncated is False
    assert result.stop_reason == "end_turn"
    assert result.request_id == "req-0001"
    assert grok_fake.launches("oneshot"), "the one-shot CLI ran"


@pytest.mark.asyncio
async def test_module_level_run_grok_once_without_grok_raises_not_installed(grok_api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # FR-17 with EC-11 for the module function's own host.
    empty = tmp_path / "empty-path"
    empty.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    with pytest.raises(grok_api.NativeHostError) as caught:
        await grok_api.run_grok_once(grok_api.GrokOneShotRequest(prompt="Summarise the README."), settings=grok_api.GrokHostSettings(workspace=workspace))
    check_native_error(caught.value, code="grok.not_installed", token="GrokHostSettings.grok_command")
