"""FILE: tests/features/harness_threads/test_harness_threads_helper_bounds.py

PURPOSE: Launch, bound and stop rules for the new functions' children: a missing program, a Windows batch launcher, a hung child (stopped after NATIVE_CONTROL_TIMEOUT_SECONDS whatever config.timeout_seconds says), an output flood and a non-zero exit, per harness, with #1036's message order (AC-25, INV-16, D-14, EC-33, EC-37); Muse on Windows without a distro or command (EC-34); Muse helpers in WSL mode with translated paths (§9.2); and cancellation mid-child that stops the child, reaps it in WSL, removes every temp folder and re-raises (AC-23, INV-14).
ROLE IN CODEBASE: Start here when a helper hangs past its control timeout, leaks a child or a temp folder, or reports a launch problem under the wrong code.
ARCHITECTURE NOTE: The stand-in's helper children hold, flood or fail by the scenario field of their role (`export_mode`, `delete_mode`, `mode`, `serve_mode`). NATIVE_CONTROL_TIMEOUT_SECONDS and NATIVE_KILL_WAIT_SECONDS are shrunk through the constants module, which the harness modules read at call time (spec §13). The WSL cases use the `wsl.exe` stand-in of test_harness_threads_wsl.py.
FUNCTION INVENTORY: seed builds the thread each helper needs; wsl_stand_in places wsl.exe on PATH; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Keep every bound as timeout + a few kill waits + SLACK_SECONDS; never a fixed sleep.
WHAT NOT TO DO IN THIS FILE: Do not raise the stand-in's hold limit; a missing stop should fail the elapsed-time assertion.
KNOWN EDGE CASES: The flood cases write just past the real 64 MiB cap. Grok list, get, lineage and search start no child, so the Grok rows use read and delete. Batch launchers and WSL exist only on win32; on POSIX, Muse is looked up on PATH.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-14, INV-16, §6.2 AC-23, AC-25, §6.3 EC-33, EC-34, EC-37, §9.2, D-14
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_helper_bounds.py
"""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

TIMEOUT = 1.5
FLOOD_EXTRA_BYTES = 65536
GROK_ID = "f0000000-0000-4000-8000-0000000000c3"
DEFAULT_MUSE_PATH = "/usr/local/bin/muse"
win32_only = pytest.mark.skipif(sys.platform != "win32", reason="batch launchers and Muse WSL mode exist only on win32 (INV-14 of #1036, EC-29, EC-34)")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Muse is looked up on PATH only outside win32 (EC-29)")
# (helper, positional builder key, role, scenario field that drives the role)
HELPERS = {
    "grok-read": ("read_grok_thread", "grok", "grok-export", "export_mode"),
    "grok-delete": ("delete_grok_thread", "grok", "grok-delete", "delete_mode"),
    "opencode-list": ("list_opencode_threads", "none", "opencode-list", "mode"),
    "opencode-get": ("get_opencode_thread", "opencode", "opencode-db", "mode"),
    "muse-list": ("list_muse_threads", "none", "muse-serve", "serve_mode"),
    "muse-read": ("read_muse_thread", "muse", "muse-export", "export_mode"),
    "muse-init": ("init_muse_workspace", "none", "muse-init", "mode"),
}


def seed(sandbox, stores, key: str) -> tuple:
    if key == "grok":
        stores.grok_thread(GROK_ID)
        return (GROK_ID, sandbox.workspace)
    if key == "opencode":
        stores.opencode_session("ses_bound")
        return ("ses_bound", sandbox.workspace)
    if key == "muse":
        stores.muse_session("muse-bound")
        return ("muse-bound", sandbox.workspace)
    return (sandbox.workspace,)


def wsl_stand_in(sandbox, pack, **fields):
    return sandbox.stand_in(sandbox.bin, "wsl", "muse", as_wsl=True, wsl={"distros": [pack.FAKE_DISTRO, pack.OTHER_DISTRO], "muse_path": DEFAULT_MUSE_PATH}, **fields)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["grok-read", "grok-delete", "opencode-list", "opencode-get"])
async def test_a_missing_program_is_not_installed(api, sandbox, helper, stores, check_error, pack, case) -> None:
    # AC-25 / EC-33: PATH holds only the sandbox's empty folder and the
    # Grok fallback does not exist.
    name, key, _, _ = HELPERS[case]
    harness = name.split("_")[1]
    positional = seed(sandbox, stores, key)
    with pytest.raises(api.NativeThreadError) as caught:
        await helper(name, *positional, config={pack.COMMAND_FIELDS[harness]: None})
    check_error(caught.value, harness=harness, operation=name, code=f"{harness}.not_installed", workspace=sandbox.workspace, observations=[("program", (harness,))])
    assert sandbox.starts() == []


@pytest.mark.asyncio
@posix_only
async def test_muse_helpers_outside_windows_look_muse_up_on_path(api, sandbox, helper, check_error) -> None:
    # AC-25 / EC-29: no muse on PATH is not_installed.
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_muse_threads", sandbox.workspace, raw_config=None)
    check_error(caught.value, harness="muse", operation="list_muse_threads", code="muse.not_installed", workspace=sandbox.workspace)


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize("config", ["default", "no-command"])
async def test_muse_helpers_on_windows_without_a_distro_or_command_are_wsl_unavailable(api, sandbox, helper, check_error, pack, config) -> None:
    # EC-34: MuseLauncher.resolve refuses; a muse.exe on PATH is not used.
    sandbox.stand_in(sandbox.bin, "muse", "muse")
    keywords = {"raw_config": None} if config == "default" else {"config": {"muse_command": None}}
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_muse_threads", sandbox.workspace, **keywords)
    check_error(caught.value, harness="muse", operation="list_muse_threads", code="muse.wsl_unavailable", workspace=sandbox.workspace)
    assert sandbox.starts() == []


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize("case", ["grok-read", "opencode-list", "muse-init"])
async def test_a_batch_launcher_is_refused_and_never_runs(api, sandbox, helper, stores, check_error, pack, case) -> None:
    # AC-25 / EC-33: found on PATH (Grok, opencode) or passed as the
    # command (Muse).
    name, key, _, _ = HELPERS[case]
    harness = name.split("_")[1]
    positional = seed(sandbox, stores, key)
    if harness == "muse":
        batch, marker = sandbox.batch_file(sandbox.root / "batch", "muse-launcher.cmd")
        config = {"muse_command": (str(batch),)}
    else:
        batch, marker = sandbox.batch_file(sandbox.bin, f"{harness}.cmd")
        config = {pack.COMMAND_FIELDS[harness]: None}
    with pytest.raises(api.NativeThreadError) as caught:
        await helper(name, *positional, config=config)
    check_error(caught.value, harness=harness, operation=name, code=f"{harness}.launcher_refused", workspace=sandbox.workspace, observations=[("refused path", pack.path_spellings(batch))])
    assert not marker.exists() and sandbox.starts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", list(HELPERS))
async def test_a_hung_helper_child_is_timed_out_after_the_control_timeout(api, sandbox, helper, stores, check_error, fast_stop, alive, wait_until, monkeypatch, case) -> None:
    # AC-25 / INV-16 / D-14 / EC-37: config.timeout_seconds is ignored;
    # the child is stopped; no temp folder remains.
    monkeypatch.setattr(api.constants, "NATIVE_CONTROL_TIMEOUT_SECONDS", TIMEOUT)
    name, key, role, field = HELPERS[case]
    harness = name.split("_")[1]
    positional = seed(sandbox, stores, key)
    started = time.monotonic()
    with pytest.raises(api.NativeThreadError) as caught:
        await helper(name, *positional, fake={field: "hold"}, config={"timeout_seconds": 600.0})
    assert time.monotonic() - started < TIMEOUT + 4 * fast_stop.kill_wait + fast_stop.slack
    check_error(caught.value, harness=harness, operation=name, code=f"{harness}.timed_out", workspace=sandbox.workspace, observations=[("seconds waited", (str(TIMEOUT),))])
    pid = sandbox.starts(role)[-1]["pid"]
    assert await wait_until(lambda: not alive(pid), fast_stop.kill_wait + 1.0)
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["grok-read", "opencode-list", "muse-read"])
async def test_a_helper_child_past_the_output_cap_is_output_too_large(api, sandbox, helper, stores, check_error, case) -> None:
    # AC-25 / INV-16 / EC-22: NATIVE_PROCESS_MAX_OUTPUT_BYTES; never a
    # cut document.
    cap = api.constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES
    name, key, _, field = HELPERS[case]
    harness = name.split("_")[1]
    positional = seed(sandbox, stores, key)
    with pytest.raises(api.NativeThreadError) as caught:
        await helper(name, *positional, fake={field: "flood", "flood_bytes": cap + FLOOD_EXTRA_BYTES})
    check_error(caught.value, harness=harness, operation=name, code=f"{harness}.output_too_large", workspace=sandbox.workspace, observations=[("byte cap", (str(cap), f"{cap:,}"))])
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["grok-delete", "opencode-get", "muse-init"])
async def test_a_failing_helper_child_is_run_failed_with_the_vendor_text(api, sandbox, helper, stores, check_error, case) -> None:
    # AC-25: a non-zero exit keeps the vendor's own words.
    name, key, _, field = HELPERS[case]
    harness = name.split("_")[1]
    positional = seed(sandbox, stores, key)
    vendor = f"{harness}: the store is locked by another process"
    with pytest.raises(api.NativeThreadError) as caught:
        await helper(name, *positional, fake={field: "fail", "vendor_text": vendor})
    check_error(caught.value, harness=harness, operation=name, code=f"{harness}.run_failed", workspace=sandbox.workspace, vendor=vendor, exit_code=93)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["grok-read", "opencode-list", "muse-list", "muse-read"])
async def test_cancelling_a_helper_mid_child_stops_it_and_removes_its_temp_folder(api, sandbox, helper, stores, fast_stop, alive, wait_until, case) -> None:
    # AC-23 / INV-14: CancelledError propagates unchanged, after the
    # child is stopped and the temp folder removed.
    name, key, role, field = HELPERS[case]
    positional = seed(sandbox, stores, key)
    fake = {"serve_mode": "hold"} if case == "muse-read" else {field: "hold"}
    watched = "muse-serve" if case == "muse-read" else role
    task = asyncio.create_task(helper(name, *positional, fake=fake))
    assert await wait_until(lambda: bool(sandbox.starts(watched)) or task.done(), 30.0), "the stand-in never started"
    if task.done():
        await task
        pytest.fail("the call ended before its child started")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pid = sandbox.only_start(watched)["pid"]
    assert await wait_until(lambda: not alive(pid), fast_stop.kill_wait + 1.0)
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional"), [("run_grok_goal", ("Ship it",)), ("run_opencode_init", ()), ("run_muse_plan", ("Plan it",))])
async def test_cancelling_a_skill_run_mid_child_stops_it(api, sandbox, skill, fast_stop, alive, wait_until, name, positional) -> None:
    # AC-23 / INV-14: the run child, for every harness.
    role = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}[name.split("_")[1]]
    task = asyncio.create_task(skill(name, *positional, fake={"mode": "hold"}))
    assert await wait_until(lambda: bool(sandbox.starts(role)) or task.done(), 30.0), "the stand-in never started"
    if task.done():
        await task
        pytest.fail("the call ended before its child started")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pid = sandbox.only_start(role)["pid"]
    assert await wait_until(lambda: not alive(pid), fast_stop.kill_wait + 1.0)
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_cancelling_a_muse_skill_during_its_evidence_read_stops_the_serve_child(api, sandbox, skill, fast_stop, alive, wait_until) -> None:
    # AC-23: the evidence read is a child of the same call.
    task = asyncio.create_task(skill("run_muse_plan", "Plan it", fake={"serve_mode": "hold"}))
    assert await wait_until(lambda: bool(sandbox.starts("muse-serve")) or task.done(), 30.0), "the evidence read never started"
    if task.done():
        await task
        pytest.fail("the call ended before its child started")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pid = sandbox.only_start("muse-serve")["pid"]
    assert await wait_until(lambda: not alive(pid), fast_stop.kill_wait + 1.0)
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@win32_only
async def test_muse_helpers_in_wsl_mode_send_distro_paths(api, sandbox, helper, stores, pack, wsl_ready) -> None:
    # §9.2: workspaceRoot is launcher.visible_path(workspace), the /mnt
    # form; the export --out path is translated too; no key is
    # forwarded.
    stores.muse_session("muse-wsl", workspace_root=pack.wsl_form(sandbox.workspace), export=b"{\"wsl\": true}\n")
    wsl_stand_in(sandbox, pack)
    config = {"muse_command": None, "wsl_distro": pack.FAKE_DISTRO}
    listed = await helper("list_muse_threads", sandbox.workspace, config=config)
    assert [summary.thread_id for summary in listed] == ["muse-wsl"]
    frame = next(record["frame"] for record in sandbox.records("frame", "muse-serve") if record["frame"].get("method") == "session/list")
    assert frame["params"]["workspaceRoot"] == pack.wsl_form(sandbox.workspace)
    result = await helper("read_muse_thread", "muse-wsl", sandbox.workspace, config=config)
    assert result.text == "{\"wsl\": true}\n"
    export = sandbox.only_start("muse-export")
    assert export["via_wsl"] is True and export["options"]["--out"].startswith(pack.wsl_form(sandbox.tmp) + "/")
    for start in sandbox.starts("muse-serve") + [export]:
        assert start["credentials"]["META_API_KEY"] is None and "META_API_KEY/u" not in (start["raw_wslenv"] or "")
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@win32_only
async def test_cancelling_a_muse_helper_in_wsl_mode_reaps_with_its_mark(api, sandbox, helper, pack, wsl_ready, fast_stop, wait_until) -> None:
    # AC-23 / INV-14: the reap runs with the serve child's mark before
    # CancelledError reaches the caller.
    wsl_stand_in(sandbox, pack, serve_mode="hold")
    task = asyncio.create_task(helper("list_muse_threads", sandbox.workspace, config={"muse_command": None, "wsl_distro": pack.FAKE_DISTRO}))
    assert await wait_until(lambda: bool(sandbox.starts("muse-serve")) or task.done(), 30.0), "the stand-in never started"
    if task.done():
        await task
        pytest.fail("the call ended before its child started")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    mark = sandbox.only_start("muse-serve")["plain"]["VIDBYTE_PEER_MARK"]
    assert mark and [record["mark"] for record in sandbox.starts("wsl-reap")] == [mark]
    assert list(sandbox.tmp.iterdir()) == []
