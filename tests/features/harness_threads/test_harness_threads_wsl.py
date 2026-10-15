"""FILE: tests/features/harness_threads/test_harness_threads_wsl.py

PURPOSE: Muse WSL mode on win32 (§9.2, D-16, row 42): the launcher is `wsl.exe -d <distro> -e <muse_path>`, the workspace and temp config folder reach Muse in their /mnt form, the overlay names (and only those) are forwarded through WSLENV after the caller's own value, every call carries a fresh peer mark, a timeout or cancellation reaps the marked in-distro processes (AC-9, INV-8, INV-9), and WSL launch problems map to muse.wsl_unavailable or muse.not_installed (EC-29, EC-30).
ROLE IN CODEBASE: Start here when Muse on Windows runs in the wrong distro, cannot see its key or skills, leaves processes inside WSL, or reports a WSL problem with the wrong code.
ARCHITECTURE NOTE: The wsl.exe stand-in is an `.exe` in the sandbox's PATH folder that runs fake_harness.py with `--as-wsl`. It plays `wsl.exe -l -q` (UTF-16-LE names), refuses unknown distros with WSL's own text, refuses a muse_path it does not know with WSL's execvpe text, runs the reap (`-e sh -s <mark>`, script on stdin), and otherwise plays Muse seeing only the variables WSLENV names, with /mnt paths mapped back so the stand-in can look at the folders.
FUNCTION INVENTORY: wsl_config builds the config fields for WSL mode; wsl_stand_in puts wsl.exe on PATH; wslenv_entries splits a WSLENV value; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new WSL failure text is one stand-in branch plus one case here.
WHAT NOT TO DO IN THIS FILE: Never name the real distro (MuseUbuntu1) or let the real wsl.exe run; PATH holds only the sandbox's bin folder.
KNOWN EDGE CASES: The order of the five forwarded names is not fixed by the spec (§9.2 and row 44 list them differently), so they are compared as a set after the caller's own entry. A UNC workspace refusal is not tested (no UNC path a non-admin test can create; see test-plan.md).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-2, INV-8, INV-9, §6.2 AC-9, AC-11, §6.3 EC-29, EC-30, §9.2, §9.3, §12.3 rows 42, 44
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_wsl.py
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Muse WSL mode exists only on win32 (spec §9.2, EC-29)")

DEFAULT_MUSE_PATH = "/usr/local/bin/muse"
FORWARDED = {"META_API_KEY/u", "MUSE_NO_AUTO_UPDATE/u", "XDG_CONFIG_HOME/u", "MUSE_AUTH_PATH/u", "VIDBYTE_PEER_MARK/u"}
MARK_PATTERN = re.compile(r"^[0-9a-f]{32}$")
CALLER_WSLENV = "USERPROFILE/p"
TIMEOUT = 1.5


def wsl_config(distro: str, **fields: Any) -> dict[str, Any]:
    return {"muse_command": None, "wsl_distro": distro, **fields}


def wsl_stand_in(sandbox, pack, *, muse_path: str = DEFAULT_MUSE_PATH, **fields: Any) -> Path:
    return sandbox.stand_in(sandbox.bin, "wsl", "muse", as_wsl=True, wsl={"distros": [pack.FAKE_DISTRO, pack.OTHER_DISTRO], "muse_path": muse_path}, **fields)


def wslenv_entries(value: str | None) -> list[str]:
    return [entry for entry in (value or "").split(":") if entry]


@pytest.mark.asyncio
async def test_wsl_run_launches_muse_in_the_distro_with_translated_paths_and_forwarded_names(sandbox, call, pack, wsl_ready, monkeypatch) -> None:
    # §9.2 / D-16 / INV-2 / INV-18: wsl.exe -d <distro> -e <muse_path>; /mnt paths; the key only through WSLENV; the caller's WSLENV kept first.
    monkeypatch.setenv("WSLENV", CALLER_WSLENV)
    wsl_stand_in(sandbox, pack)
    skill = sandbox.make_skill("alpha-skill")
    result = await call("muse", config=wsl_config(pack.FAKE_DISTRO), skills=[skill])
    start = sandbox.only_start("muse-exec")
    assert start["via_wsl"] is True
    assert start["launcher_args"][:4] == ["-d", pack.FAKE_DISTRO, "-e", DEFAULT_MUSE_PATH]
    assert start["argv"] == ["exec", "--json", "--provider", "meta", "--workspace", pack.wsl_form(sandbox.workspace), "--user-input-auto-resolve", "--", pack.PROMPT]
    assert start["credentials"]["META_API_KEY"] == pack.key_digest(pack.API_KEY)
    plain = start["plain"]
    assert plain["MUSE_NO_AUTO_UPDATE"] == "1"
    assert plain["XDG_CONFIG_HOME"].startswith(pack.wsl_form(sandbox.tmp) + "/"), "the temp config folder is translated to its /mnt form"
    assert plain["MUSE_AUTH_PATH"] == plain["XDG_CONFIG_HOME"] + "/muse/auth.json"
    assert start["xdg_config_exists"] is True and start["muse_auth_file_exists"] is False
    assert start["skills"] is not None and set(start["skills"]) == {"alpha-skill"}
    assert MARK_PATTERN.fullmatch(plain["VIDBYTE_PEER_MARK"] or "")
    entries = wslenv_entries(start["raw_wslenv"])
    assert entries[0] == CALLER_WSLENV, "the caller's own WSLENV entries come first"
    assert set(entries[1:]) == FORWARDED and len(entries) == len(FORWARDED) + 1
    assert result.thread_id == sandbox.answers("muse-exec")[0]["session"]
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_wsl_custom_muse_path_is_the_program_inside_the_distro(sandbox, call, pack, wsl_ready) -> None:
    # FR-9: MuseThreadConfig.muse_path is what `-e` runs.
    wsl_stand_in(sandbox, pack, muse_path="/opt/muse/bin/muse")
    await call("muse", config=wsl_config(pack.FAKE_DISTRO, muse_path="/opt/muse/bin/muse"))
    assert sandbox.only_start("muse-exec")["launcher_args"][:4] == ["-d", pack.FAKE_DISTRO, "-e", "/opt/muse/bin/muse"]


@pytest.mark.asyncio
async def test_wsl_serve_check_never_forwards_a_key_and_each_call_gets_a_fresh_mark(sandbox, call, pack, wsl_ready, monkeypatch) -> None:
    # §9.2 Muse serve / row 42: forwarded names come from the overlay, not os.environ, so a caller's own META_API_KEY never reaches serve.
    monkeypatch.setenv("META_API_KEY", "caller-own-meta-key-value")
    wsl_stand_in(sandbox, pack)
    first = await call("muse", config=wsl_config(pack.FAKE_DISTRO))
    second = await call("muse", "continue", "Again.", thread_id=first.thread_id, config=wsl_config(pack.FAKE_DISTRO))
    assert second.thread_id == first.thread_id
    serve = sandbox.only_start("muse-serve")
    assert serve["via_wsl"] is True and serve["argv"] == ["serve"]
    assert serve["launcher_args"][:4] == ["-d", pack.FAKE_DISTRO, "-e", DEFAULT_MUSE_PATH]
    assert serve["credentials"]["META_API_KEY"] is None, "serve needs no credential, and the caller's own key is never forwarded"
    assert "META_API_KEY/u" not in wslenv_entries(serve["raw_wslenv"])
    execs = sandbox.starts("muse-exec")
    assert [record["credentials"]["META_API_KEY"] for record in execs] == [pack.key_digest(pack.API_KEY)] * 2
    marks = [record["plain"]["VIDBYTE_PEER_MARK"] for record in execs]
    assert all(MARK_PATTERN.fullmatch(mark or "") for mark in marks) and marks[0] != marks[1], "a fresh mark per call"


@pytest.mark.asyncio
async def test_wsl_run_past_its_timeout_is_reaped_with_the_calls_mark(api, sandbox, call, check_error, pack, wsl_ready, fast_stop, alive, wait_until) -> None:
    # AC-9 / INV-8 / EC-15: timed_out within the bound, and the reap ran with the exec's mark (script on stdin, no carriage return).
    wsl_stand_in(sandbox, pack, mode="hold", grandchild=True)
    started = time.monotonic()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", config=wsl_config(pack.FAKE_DISTRO, timeout_seconds=TIMEOUT))
    assert time.monotonic() - started < TIMEOUT + 4 * fast_stop.kill_wait + api.constants.MUSE_REAP_TIMEOUT_SECONDS + fast_stop.slack
    check_error(caught.value, harness="muse", verb="run", code="muse.timed_out", workspace=sandbox.workspace, thread_id=None)
    mark = sandbox.only_start("muse-exec")["plain"]["VIDBYTE_PEER_MARK"]
    reap = sandbox.only_start("wsl-reap")
    assert reap["mark"] == mark and reap["argv"] == ["-s", mark]
    assert reap["script_chars"] > 0 and reap["script_has_carriage_return"] is False and reap["stdin_kind"] == "pipe"
    pids = [sandbox.only_start("muse-exec")["pid"]] + [record["grandchild_pid"] for record in sandbox.records("grandchild")]
    assert await wait_until(lambda: not any(alive(pid) for pid in pids), fast_stop.kill_wait + 1.0)


@pytest.mark.asyncio
async def test_wsl_serve_past_the_control_timeout_is_reaped(api, sandbox, call, check_error, pack, wsl_ready, fast_stop, monkeypatch) -> None:
    # INV-8 / row 44 step 7: a timed-out serve exchange is reaped too ("timed_out (any process)").
    monkeypatch.setattr(api.constants, "NATIVE_CONTROL_TIMEOUT_SECONDS", TIMEOUT)
    wsl_stand_in(sandbox, pack, serve_mode="hold")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "continue", "Again.", thread_id="0192f0c4-aaaa-7bbb-8ccc-dddddddddddd", config=wsl_config(pack.FAKE_DISTRO))
    check_error(caught.value, harness="muse", verb="continue", code="muse.timed_out", workspace=sandbox.workspace, thread_id="0192f0c4-aaaa-7bbb-8ccc-dddddddddddd")
    mark = sandbox.only_start("muse-serve")["plain"]["VIDBYTE_PEER_MARK"]
    assert MARK_PATTERN.fullmatch(mark or "")
    assert [record["mark"] for record in sandbox.starts("wsl-reap")] == [mark]
    assert sandbox.starts("muse-exec") == []


@pytest.mark.asyncio
async def test_wsl_cancellation_reaps_before_it_propagates(sandbox, call, pack, wsl_ready, fast_stop, wait_until) -> None:
    # AC-11 / INV-9: CancelledError reaches the caller only after the reap ran with the call's mark and the temp folder is gone.
    wsl_stand_in(sandbox, pack, mode="hold")
    task = asyncio.create_task(call("muse", config=wsl_config(pack.FAKE_DISTRO)))
    assert await wait_until(lambda: bool(sandbox.starts("muse-exec")), 30.0), "the stand-in never started"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    mark = sandbox.only_start("muse-exec")["plain"]["VIDBYTE_PEER_MARK"]
    assert [record["mark"] for record in sandbox.starts("wsl-reap")] == [mark], "INV-9: reaped before CancelledError propagates"
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_unknown_distro_is_wsl_unavailable_listing_the_distros(api, sandbox, call, check_error, pack, wsl_ready) -> None:
    # EC-29: WSL_E_DISTRO_NOT_FOUND -> muse.wsl_unavailable listing what `wsl.exe -l -q` reports.
    wsl_stand_in(sandbox, pack)
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", config=wsl_config("VidbyteMissingDistro"))
    check_error(caught.value, harness="muse", verb="run", code="muse.wsl_unavailable", workspace=sandbox.workspace, thread_id=None, observations=[("listed distro", (pack.FAKE_DISTRO,)), ("listed distro", (pack.OTHER_DISTRO,))])
    assert [record["argv"] for record in sandbox.starts("wsl-list")] == [["-l", "-q"]]
    assert sandbox.starts("muse-exec") == []


@pytest.mark.asyncio
async def test_missing_muse_inside_the_distro_is_not_installed_naming_distro_and_path(api, sandbox, call, check_error, pack, wsl_ready) -> None:
    # EC-30: the distro exists but muse_path does not -> muse.not_installed naming both.
    wsl_stand_in(sandbox, pack, muse_path="/opt/elsewhere/muse")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", config=wsl_config(pack.FAKE_DISTRO))
    check_error(caught.value, harness="muse", verb="run", code="muse.not_installed", workspace=sandbox.workspace, thread_id=None)
    message = str(caught.value)
    assert pack.FAKE_DISTRO in message and DEFAULT_MUSE_PATH in message


@pytest.mark.asyncio
async def test_missing_wsl_exe_is_wsl_unavailable(api, sandbox, call, check_error, pack) -> None:
    # EC-29: wsl_distro set but no wsl.exe on PATH; nothing starts and nothing is written.
    before = sandbox.snapshot()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", config=wsl_config(pack.FAKE_DISTRO))
    check_error(caught.value, harness="muse", verb="run", code="muse.wsl_unavailable", workspace=sandbox.workspace, thread_id=None)
    assert sandbox.starts() == []
    assert sandbox.snapshot() == before
