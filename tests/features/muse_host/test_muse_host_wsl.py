"""FILE: tests/features/muse_host/test_muse_host_wsl.py

PURPOSE: MuseHost's WSL mode (FR-19, D-19, D-23, AC-10): MusePathTranslator.to_wsl, the launch argv `wsl.exe -d <distro> -e <muse_path> serve|--version`, the peer environment overlay (VIDBYTE_PEER_MARK and the WSLENV entries), the in-distro reap `wsl.exe -d <distro> -e sh -s <mark>` with MUSE_REAP_SCRIPT on stdin and the caller's environment, the reap script itself on Linux, and the WSL rows EC-94 and EC-95.
ROLE IN CODEBASE: Proves the launcher half of vidbyte.harnesses.native.muse.launcher. The translator and the reap script tests run on any OS that has what they need; the host-level tests need win32, where WSL mode exists.
ARCHITECTURE NOTE: On win32 the make_wsl_host fixture puts a fake wsl.exe first on PATH, built from pip's console-script launcher with a zipped __main__ that runs fake_muse_peer.py with `--as-wsl wsl.exe`. The fake plays `-l -q` (UTF-16-LE names), the distro-not-found text, a missing in-distro muse, the version run, the MSP peer and the reap, and logs argv, the overlay variables and the script it read. Every host here names FAKE_DISTRO, never MuseUbuntu1, so a host that ran the real wsl.exe could only reach a distro that does not exist.
FUNCTION INVENTORY: translator imports MusePathTranslator; wsl_form turns a Windows path into its /mnt form for comparison; peer_start returns the one WSL turn peer's start record; the test_* functions check one rule each.
COMMON MODIFICATION PATTERNS: A new WSL behaviour gets a scenario key under "wsl" in conftest.py's default_scenario, a branch in fake_muse_peer.py's wsl_role, and a test here.
WHAT NOT TO DO IN THIS FILE: 1. Never run the real wsl.exe or name the distro MuseUbuntu1 in a test that starts a process. 2. Never put a real key in META_API_KEY; the placeholder only switches the WSLENV entry on, and the fake logs whether the variable is set, not its value.
KNOWN EDGE CASES: AC-10's own settings need an existing C:/w/repo, which a test machine does not have, so AC-10 is proven in two parts: the translator on PureWindowsPath("C:/w/repo"), and the full host path on a temporary workspace through the fake. The caller's WSLENV is set by each test, because a terminal may already hold one. A refusal from to_wsl is accepted as either NativeHostError(configuration.invalid_argument) or ConfigurationError; the spec names the code but not the type.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.5 EC-94/EC-95, §8.1 D-19/D-23, §8.5, §9.3, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_wsl.py
"""

from __future__ import annotations

import importlib
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

FAKE_DISTRO = "VidbyteFakeDistro"
PROMPT = "List the top-level folders."
WAIT_SECONDS = 30.0
CALLER_WSLENV = "WT_SESSION:WT_PROFILE_ID"
PLACEHOLDER_KEY = "placeholder-not-a-key"
MARK_PATTERN = re.compile(r"^[0-9a-f]{32}$")
OVERLAY_KEYS = ["VIDBYTE_PEER_MARK", "WSLENV"]
REAP_WAIT_SECONDS = 5.0
POLL_SECONDS = 0.05
win32_only = pytest.mark.skipif(sys.platform != "win32", reason="MuseHost's WSL mode exists only on win32 (D-19)")
needs_proc = pytest.mark.skipif(not Path("/proc/self/environ").exists() or shutil.which("sh") is None, reason="the reap script needs sh and /proc (spec §13: Linux CI)")


def translator() -> Any:
    return importlib.import_module("vidbyte.harnesses.native.muse.launcher").MusePathTranslator


def wsl_form(path: Path) -> str:
    windows = PureWindowsPath(path)
    return "/mnt/" + windows.drive[0].lower() + "/" + "/".join(windows.parts[1:])


def peer_start(muse_fake: Any) -> dict[str, Any]:
    starts = muse_fake.starts("peer")
    assert len(starts) == 1, f"expected one turn peer, got {[record['argv'] for record in starts]}"
    return starts[0]


@pytest.mark.parametrize(
    ("windows_path", "expected"),
    [
        (r"C:\w\repo", "/mnt/c/w/repo"),
        ("C:/w/repo", "/mnt/c/w/repo"),
        (r"D:\Data\Repo Name", "/mnt/d/Data/Repo Name"),
        ("e:/", "/mnt/e"),
    ],
)
def test_to_wsl_maps_a_drive_path_under_mnt(windows_path: str, expected: str) -> None:
    # §8.5 / AC-10: MusePathTranslator is a pure static class; C:\w\repo becomes /mnt/c/w/repo.
    assert translator().to_wsl(PureWindowsPath(windows_path)) == expected


@pytest.mark.parametrize("windows_path", [r"\\server\share\repo", r"\w\repo", "w/repo"], ids=["unc", "drive-less-rooted", "relative"])
def test_to_wsl_refuses_unc_and_drive_less_paths(windows_path: str, muse_api) -> None:
    # §8.5: UNC and drive-less paths are refused with configuration.invalid_argument.
    with pytest.raises((muse_api.NativeHostError, muse_api.ConfigurationError)) as caught:
        translator().to_wsl(PureWindowsPath(windows_path))
    if isinstance(caught.value, muse_api.NativeHostError):
        assert caught.value.failure_code is muse_api.FailureCode.CONFIGURATION_INVALID_ARGUMENT


def test_reap_constants_match_the_spec(muse_api) -> None:
    # §9.3: the mark variable and pattern, the reap timeout, and an LF-only script that never kills itself.
    constants = muse_api.constants
    assert constants.MUSE_PEER_MARK_VARIABLE == "VIDBYTE_PEER_MARK"
    assert constants.MUSE_PEER_MARK_PATTERN == r"^[0-9a-f]{32}$"
    assert constants.MUSE_REAP_TIMEOUT_SECONDS == 10.0
    script = constants.MUSE_REAP_SCRIPT
    assert isinstance(script, str) and "\r" not in script
    assert 'VIDBYTE_PEER_MARK=$1' in script and "PPid:" in script and "kill -KILL" in script and "$$" in script


@needs_proc
def test_reap_script_kills_marked_processes_and_their_children_only(muse_api, process_running) -> None:
    # D-23 / §13: `sh -s <mark>` with the script on stdin kills the marked process and its unmarked child, not a bystander.
    mark = uuid.uuid4().hex
    clean_env = {key: value for key, value in os.environ.items() if key != "VIDBYTE_PEER_MARK"}
    source = "import os, subprocess, sys, time\nenv = {k: v for k, v in os.environ.items() if k != 'VIDBYTE_PEER_MARK'}\nchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], env=env)\nprint(child.pid, flush=True)\ntime.sleep(60)\n"
    marked = subprocess.Popen([sys.executable, "-c", source], env={**clean_env, "VIDBYTE_PEER_MARK": mark}, stdout=subprocess.PIPE, text=True)
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], env=clean_env)
    child_pid = 0
    try:
        child_pid = int(marked.stdout.readline())
        outcome = subprocess.run(["sh", "-s", mark], input=muse_api.constants.MUSE_REAP_SCRIPT, text=True, env=clean_env, capture_output=True,
                                 timeout=muse_api.constants.MUSE_REAP_TIMEOUT_SECONDS, check=False)
        assert outcome.returncode == 0, outcome.stderr
        assert marked.wait(timeout=REAP_WAIT_SECONDS) == -signal.SIGKILL
        deadline = time.monotonic() + REAP_WAIT_SECONDS
        while process_running(child_pid) and time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
        assert not process_running(child_pid), "the marked process's unmarked child must be killed too"
        assert bystander.poll() is None, "an unmarked process outside the tree must survive"
    finally:
        for process in (marked, bystander):
            if process.poll() is None:
                process.kill()
            process.wait()
        if child_pid and process_running(child_pid):
            os.kill(child_pid, signal.SIGKILL)


@pytest.mark.asyncio
@win32_only
async def test_wsl_turn_peer_launch_workspace_overlay_and_reap(muse_api, muse_fake, make_wsl_host, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-10 / FR-19 / D-23: argv, translated workspaceRoot, the mark and WSLENV entries, then the reap with the caller's environment.
    monkeypatch.setenv("WSLENV", CALLER_WSLENV)
    monkeypatch.setenv("META_API_KEY", PLACEHOLDER_KEY)
    async with make_wsl_host({"env_keys": OVERLAY_KEYS}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    start = peer_start(muse_fake)
    assert start["via_wsl"] is True and start["launcher_name"] == "wsl.exe"
    assert start["argv"] == ["-d", FAKE_DISTRO, "-e", "/usr/local/bin/muse", "serve"]
    assert muse_fake.launches("wsl_list") == [["-l", "-q"]], "the distro list runs once, at __aenter__"
    workspace_root = muse_fake.received("session/start")[0]["params"]["workspaceRoot"]
    assert workspace_root in {wsl_form(muse_fake.workspace), wsl_form(muse_fake.workspace.resolve())}
    mark = start["env"]["VIDBYTE_PEER_MARK"]
    assert mark and MARK_PATTERN.match(mark)
    entries = start["env"]["WSLENV"].split(":")
    assert entries[:2] == ["WT_SESSION", "WT_PROFILE_ID"], "the caller's WSLENV entries are kept first"
    assert "VIDBYTE_PEER_MARK/u" in entries and "META_API_KEY/u" in entries
    assert start["meta_key_set"] is True
    reaps = muse_fake.records("reap")
    assert len(reaps) == 1, "the turn peer's close runs the in-distro reap once"
    assert muse_fake.launches("reap") == [["-d", FAKE_DISTRO, "-e", "sh", "-s", mark]]
    assert reaps[0]["script"] == muse_api.constants.MUSE_REAP_SCRIPT
    assert reaps[0]["has_carriage_return"] is False
    assert reaps[0]["peer_mark"] is None, "the reap runs with the caller's environment, never the peer's overlay"
    assert reaps[0]["wslenv"] == CALLER_WSLENV


@pytest.mark.asyncio
@win32_only
async def test_wslenv_gets_no_key_entry_when_meta_api_key_is_unset(muse_api, muse_fake, make_wsl_host, monkeypatch: pytest.MonkeyPatch) -> None:
    # §9.3 / T-8: META_API_KEY/u is appended only when the variable is set; the mark entry always is.
    monkeypatch.setenv("WSLENV", CALLER_WSLENV)
    monkeypatch.delenv("META_API_KEY", raising=False)
    async with make_wsl_host({"env_keys": OVERLAY_KEYS}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    entries = peer_start(muse_fake)["env"]["WSLENV"].split(":")
    assert "VIDBYTE_PEER_MARK/u" in entries
    assert "META_API_KEY/u" not in entries


@pytest.mark.asyncio
@win32_only
async def test_short_lived_read_peer_skips_the_reap(muse_api, muse_fake, make_wsl_host, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-23: read peers run no tools, so only turn peers get the in-distro reap.
    monkeypatch.setenv("WSLENV", CALLER_WSLENV)
    async with make_wsl_host() as host:
        page = await host.list_muse_sessions()
    assert page.sessions
    assert muse_fake.launches("peer") == [["-d", FAKE_DISTRO, "-e", "/usr/local/bin/muse", "serve"]]
    assert muse_fake.records("reap") == []


@pytest.mark.asyncio
@win32_only
async def test_read_peer_forwards_meta_api_key_through_wslenv(muse_api, muse_fake, make_wsl_host, monkeypatch: pytest.MonkeyPatch) -> None:
    # R-7 / §9.3 / D-18: META_API_KEY/u is keyed to the variable being set, not to being a turn peer, so a read peer forwards it too.
    monkeypatch.setenv("WSLENV", CALLER_WSLENV)
    monkeypatch.setenv("META_API_KEY", PLACEHOLDER_KEY)
    async with make_wsl_host({"env_keys": OVERLAY_KEYS}) as host:
        page = await host.list_muse_sessions()
    assert page.sessions
    entries = peer_start(muse_fake)["env"]["WSLENV"].split(":")
    assert entries[:2] == ["WT_SESSION", "WT_PROFILE_ID"], "the caller's WSLENV entries are kept first"
    assert "META_API_KEY/u" in entries, "R-7: a short-lived read peer forwards META_API_KEY into the distro, like a turn peer"
    assert peer_start(muse_fake)["meta_key_set"] is True


@pytest.mark.asyncio
@win32_only
async def test_check_in_wsl_mode_runs_version_through_the_distro(muse_api, muse_fake, make_wsl_host, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-19: the launcher prefix is `wsl.exe -d <distro> -e <muse_path>`; readiness names the distro.
    monkeypatch.setenv("WSLENV", CALLER_WSLENV)
    async with make_wsl_host() as host:
        readiness = await host.check_muse_ready()
    assert muse_fake.launches("version") == [["-d", FAKE_DISTRO, "-e", "/usr/local/bin/muse", "--version"]]
    assert readiness.wsl_distro == FAKE_DISTRO
    assert Path(readiness.launcher[0]).name.lower() == "wsl.exe"
    assert tuple(readiness.launcher[1:]) == ("-d", FAKE_DISTRO, "-e", "/usr/local/bin/muse")


@pytest.mark.asyncio
@win32_only
async def test_win32_without_a_launcher_or_distro_is_wsl_unavailable(muse_api, muse_fake, check_native_error) -> None:
    # EC-94: on win32 with neither muse_command nor wsl_distro, __aenter__ raises and starts nothing.
    host = muse_api.MuseHost(muse_api.MuseHostSettings(workspace=muse_fake.workspace))
    with pytest.raises(muse_api.NativeHostError) as caught:
        async with host:
            pass
    check_native_error(caught.value, code="muse.wsl_unavailable", token="wsl_distro")
    assert muse_fake.starts() == []


@pytest.mark.asyncio
@win32_only
async def test_missing_wsl_executable_is_wsl_unavailable(muse_api, muse_fake, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # EC-94: shutil.which("wsl.exe") returns None.
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    host = muse_api.MuseHost(muse_api.MuseHostSettings(workspace=muse_fake.workspace, wsl_distro=FAKE_DISTRO))
    with pytest.raises(muse_api.NativeHostError) as caught:
        async with host:
            pass
    check_native_error(caught.value, code="muse.wsl_unavailable", token="wsl_distro")


@pytest.mark.asyncio
@win32_only
async def test_unlisted_distro_is_wsl_unavailable_naming_the_listed_ones(muse_api, muse_fake, make_wsl_host, check_native_error) -> None:
    # EC-94: `wsl.exe -l -q`, decoded as UTF-16-LE at __aenter__, does not list wsl_distro.
    host = make_wsl_host({"wsl": {"distros": ["OtherDistro", "Ubuntu-24.04"]}})
    with pytest.raises(muse_api.NativeHostError) as caught:
        async with host:
            pass
    check_native_error(caught.value, code="muse.wsl_unavailable", token="wsl_distro")
    distros = caught.value.context["distros"]
    assert "OtherDistro" in distros and "Ubuntu-24.04" in distros
    assert muse_fake.launches("wsl_list") == [["-l", "-q"]]
    assert muse_fake.starts("peer") == [] and muse_fake.starts("version") == []


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize("operation", ["spawn_muse_session", "check_muse_ready"])
async def test_distro_not_found_text_from_a_launch_is_wsl_unavailable(operation: str, muse_api, muse_fake, make_wsl_host, fast_stop, check_native_error) -> None:
    # EC-94: a process prints WSL_E_DISTRO_NOT_FOUND (the verified text).
    async with make_wsl_host({"wsl": {"launch_distro_missing": True}}) as host:
        with pytest.raises(muse_api.NativeHostError) as caught:
            if operation == "spawn_muse_session":
                await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
            else:
                await host.check_muse_ready()
    check_native_error(caught.value, code="muse.wsl_unavailable", token="wsl_distro", operation=operation)
    assert muse_fake.received("turn/start") == []


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize(
    ("wsl_overrides", "operation"),
    [
        pytest.param({}, "spawn_muse_session", id="spawn-enoent-text"),
        pytest.param({}, "check_muse_ready", id="check-enoent-text"),
        pytest.param({"missing_muse_stderr": "", "missing_muse_exit": 127}, "spawn_muse_session", id="spawn-exit-127"),
    ],
)
async def test_missing_in_distro_muse_is_not_installed(wsl_overrides: dict[str, Any], operation: str, muse_api, muse_fake, make_wsl_host, fast_stop, check_native_error) -> None:
    # EC-95 in WSL mode: the process exits before answering with 127 or with "No such file or directory".
    async with make_wsl_host({"wsl": wsl_overrides}, muse_path="/opt/missing/muse") as host:
        with pytest.raises(muse_api.NativeHostError) as caught:
            if operation == "spawn_muse_session":
                await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
            else:
                await host.check_muse_ready()
    check_native_error(caught.value, code="muse.not_installed", token="muse_path", operation=operation)
    assert any(argv[3] == "/opt/missing/muse" for argv in muse_fake.launches("wsl_missing_muse"))
