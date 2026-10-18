"""FILE: tests/features/harness_threads/test_harness_threads_browser_lifecycle.py

PURPOSE: What a browser call leaves behind and how it ends (docs/spec/harness-browser-tools/spec.md §5 layers 9 to 12, FR-14, FR-15, INV-4, INV-5, INV-12): the orphaned browser is reaped by its per-call folder marker however the call ends (AC-13, EC-19 to EC-22), artifacts survive only a successful return (FR-15), the required check per harness, where a failed call never counts as evidence (AC-12, EC-16 to EC-18, EC-44, EC-45), the workspace stays untouched (AC-16), concurrent calls keep their own browsers (AC-21), the 1,000 caps (EC-29), the Grok browser output cap (D-19), keys never reach error text (INV-4) and ProcessReaper itself (§8.5).
ROLE IN CODEBASE: Start here when the reaper, the discard path, the required check or the artifact collection changes.
ARCHITECTURE NOTE: A fake server started with a profile option spawns a "browser" through a short-lived spawner, so it is an orphan on every platform and leads its own session on POSIX (fake_browser.start_browser); no tree stop of the harness reaches it, and only a reap by command-line marker ends it before its 30 s limit. Each test reads the browser pids the fakes logged and checks them with the pack's process_alive. The `sweep` fixture kills any browser a failing implementation left behind.
FUNCTION INVENTORY: sweep kills leftover fake browsers after each test; gone waits until every pid is dead; changed lists the sandbox paths a call added, changed or removed; refuse runs a call that must raise; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new way for a call to end gets a test here that the browser is gone and the per-call folder handled; a new harness adds its screenshot call name to SCREENSHOT_CALLS.
WHAT NOT TO DO IN THIS FILE: 1. Do not sleep to wait for a process; poll with wait_until. 2. Do not kill a fake browser before the assertion that the SDK killed it.
KNOWN EDGE CASES: EC-22 runs only on POSIX, where the reaper's program comes from NATIVE_PS_PATHS (read through vidbyte.lib.constants.native_threads at call time); on win32 the reaper is System32 PowerShell and has no patchable path. On POSIX a killed child stays a zombie until waited; process_alive counts a zombie as gone.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §6.2 AC-12, AC-13, AC-16, AC-21, §6.3 EC-16 to EC-22, EC-29, EC-45, §7 FR-14, FR-15, NFR-4, §8.5, §9.3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_browser_lifecycle.py
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

HARNESSES = ("grok", "opencode", "muse")
BRAVE_KEY = "BSA" + "k3v9Qx7Lm2Np8Rt4" + "Wz6Yb1Cd5Fg0Hj"
SCREENSHOT_CALLS = {"opencode": "vidbyte-playwright_browser_take_screenshot", "grok": "playwright__browser_take_screenshot", "muse": "mcp__playwright__browser_take_screenshot"}
FAILURES = {
    "grok": ({"mode": "fail", "vendor_text": "the model endpoint closed the stream"}, "grok.run_failed"),
    "opencode": ({"mode": "fail", "vendor_text": "the model endpoint closed the stream"}, "opencode.run_failed"),
    "muse": ({"mode": "terminal_failed", "vendor_text": "the model endpoint closed the stream", "browser_calls": [SCREENSHOT_CALLS["muse"]]}, "muse.run_failed"),
}
ALLOWED_WRITES = ("tmp/vidbyte-browser-", "home/.vidbyte/grok-homes", "home/.vidbyte/tools")
GROK_TIMEOUT_SECONDS = 6.0
START_SECONDS = 30.0
REAP_SECONDS = 10.0
OVER_CAP = 1001
FLOOD_EXTRA_BYTES = 65536
PLAIN_CAP_EXTRA_CHARS = 1024
CAP = 1000
SLEEPER = "import sys, time\ntime.sleep(float(sys.argv[1]))\n"
SLEEPER_SECONDS = "30"
MUSE_REQUIRED_SERVER = "Required MCP server `playwright` failed during startup"
OPENCODE_NO_TOOL = "no mounted tool was used"


@pytest.fixture
def sweep(sandbox, alive):
    yield
    for pid in sandbox.browser_pids():
        if alive(pid):
            os.kill(pid, signal.SIGTERM)


async def gone(wait_until, alive, pids: list[int], seconds: float) -> bool:
    assert pids, "no fake browser was ever started, so the reap was not exercised"
    return await wait_until(lambda: not any(alive(pid) for pid in pids), seconds)


def changed(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


async def refuse(browse, lib, harness: str, **arguments: Any):
    with pytest.raises(lib.NativeThreadError) as caught:
        await browse(harness, **arguments)
    return caught.value


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_a_returned_call_reaps_its_browser_and_removes_its_folder(browser_world, browser_api, sandbox, browse, pack, alive, wait_until, sweep, harness) -> None:
    # AC-13 / FR-15 / NFR-4: the orphan browser is gone after the call;
    # no artifacts, so the whole per-call folder is removed.
    result = await browse(harness, tools=["playwright"])
    assert result.artifacts == () and result.artifacts_truncated is False
    assert await gone(wait_until, alive, sandbox.browser_pids(), pack.SLACK_SECONDS), "AC-13: the browser outlived the call"
    assert sandbox.call_folders() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_artifacts_survive_a_successful_return_and_profiles_do_not(browser_world, browser_api, sandbox, browse, pack, alive, wait_until, sweep, harness) -> None:
    # AC-13 / FR-15 / §8.5: artifacts absolute, sorted, under
    # <per-call folder>/artifacts; the profiles are removed.
    result = await browse(harness, tools=["playwright"], fake={"browser_calls": [SCREENSHOT_CALLS[harness]]})
    (folder,) = sandbox.call_folders()
    assert len(result.artifacts) == 1 and result.artifacts == tuple(sorted(result.artifacts)) and result.artifacts_truncated is False
    (artifact,) = result.artifacts
    assert isinstance(artifact, Path) and artifact.is_absolute() and artifact.is_file() and pack.same_path(artifact.parent, folder / "artifacts")
    assert not (folder / "profiles").exists()
    assert await gone(wait_until, alive, sandbox.browser_pids(), pack.SLACK_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_a_failed_run_reaps_and_discards_everything(browser_world, browser_api, sandbox, browse, check_browser_error, pack, alive, wait_until, sweep, harness) -> None:
    # AC-13 / FR-15: on a raise the browser is reaped and the whole
    # folder goes, artifacts included (Muse fails after a screenshot).
    fake, code = FAILURES[harness]
    error = await refuse(browse, browser_api, harness, tools=["playwright"], fake=fake)
    check_browser_error(error, harness=harness, verb="run", code=code, workspace=sandbox.workspace)
    assert await gone(wait_until, alive, sandbox.browser_pids(), pack.SLACK_SECONDS)
    assert sandbox.call_folders() == []
    if harness == "muse":
        assert sandbox.records("artifacts"), "the fake wrote a screenshot before failing"


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_a_cancelled_call_reaps_and_re_raises(browser_world, browser_api, sandbox, browse, pack, alive, wait_until, fast_stop, sweep, harness) -> None:
    # AC-13 / EC-20: discard runs shielded from the cancel, then
    # CancelledError propagates.
    task = asyncio.create_task(browse(harness, tools=["playwright"], fake={"mode": "hold"}))
    assert await wait_until(lambda: bool(sandbox.browser_pids()), START_SECONDS), "the fake browser never started"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await gone(wait_until, alive, sandbox.browser_pids(), REAP_SECONDS + pack.SLACK_SECONDS)
    assert sandbox.call_folders() == []


@pytest.mark.asyncio
async def test_a_timed_out_call_reaps_and_raises_the_timeout(browser_world, browser_api, sandbox, browse, check_browser_error, pack, alive, wait_until, fast_stop, sweep) -> None:
    # AC-13 / EC-19: the existing grok.timed_out; cleanup still runs
    # and artifacts are discarded.
    error = await refuse(browse, browser_api, "grok", tools=["playwright"], fake={"mode": "hold"}, config={"timeout_seconds": GROK_TIMEOUT_SECONDS})
    check_browser_error(error, harness="grok", verb="run", code="grok.timed_out", workspace=sandbox.workspace)
    assert await gone(wait_until, alive, sandbox.browser_pids(), pack.SLACK_SECONDS)
    assert sandbox.call_folders() == []


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="the POSIX reaper reads NATIVE_PS_PATHS; win32 uses System32 PowerShell")
async def test_a_missing_ps_is_not_raised(browser_world, browser_api, sandbox, browse, pack, alive, monkeypatch, sweep) -> None:
    # EC-22: no ps at any fixed path means nothing is reaped, nothing is
    # raised, and the profile removal is still attempted.
    monkeypatch.setattr(browser_api.constants, "NATIVE_PS_PATHS", (str(sandbox.root / "no-ps" / "ps"),))
    result = await browse("opencode", tools=["playwright"])
    assert isinstance(result, browser_api.BrowserThreadResult)
    pids = sandbox.browser_pids()
    assert pids and all(alive(pid) for pid in pids), "the reaper ran a ps that NATIVE_PS_PATHS did not name"
    assert not any((folder / "profiles").exists() for folder in sandbox.call_folders())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "guessed"),
    [
        pytest.param("playwright", {}, id="playwright"),
        pytest.param("jina", {}, id="jina"),
        pytest.param("playwright", {"browser_calls": ["playwright__browser_navigate"]}, id="playwright-only-call-failed"),
        pytest.param("jina", {"browser_calls": ["jina__read_url"]}, id="jina-only-call-failed"),
    ],
)
async def test_grok_names_each_server_it_never_listed(browser_world, browser_api, sandbox, browse, check_browser_error, pack, sweep, tool, guessed) -> None:
    # AC-12 / EC-16 / EC-45 / FR-14: browser.tools_unavailable with the
    # new thread id, naming the missing server. In the -only-call-failed
    # cases the model calls the dead server's tool by name anyway; Grok
    # answers "Tool not found" and exits 0. Only a listed server or a
    # completed call counts (D-11, EC-44), so it is still missing.
    error = await refuse(browse, browser_api, "grok", tools=[tool], fake={"grok_unlisted": [tool], **guessed})
    session = sandbox.answers("grok")[-1]["session"]
    check_browser_error(error, harness="grok", verb="run", code="browser.tools_unavailable", workspace=sandbox.workspace, thread_id=session, observations=[("missing server", (tool,))])
    assert sandbox.call_folders() == []
    (made,) = sandbox.records("browser_calls", "grok")
    assert made["calls"] == [[name, "failed"] for name in guessed.get("browser_calls", [])], "the fake Grok did not make exactly the guessed call, failed"


@pytest.mark.asyncio
async def test_opencode_without_a_mounted_tool_call_says_so(browser_world, browser_api, sandbox, browse, check_browser_error, pack, alive, wait_until, sweep) -> None:
    # AC-12 / EC-17 / Q-9: "no mounted tool was used", the mounted
    # servers, the thread id and the answer as vendor text.
    error = await refuse(browse, browser_api, "opencode", tools=["playwright", "firecrawl"], fake={"browser_calls": []})
    session = sandbox.answers("opencode")[-1]["session"]
    check_browser_error(error, harness="opencode", verb="run", code="browser.tools_unavailable", workspace=sandbox.workspace, thread_id=session, observations=[("no tool used", (OPENCODE_NO_TOOL,))], vendor=f"opencode answer to: {pack.PROMPT}")
    assert "playwright" in str(error) and "firecrawl" in str(error)
    assert await gone(wait_until, alive, sandbox.browser_pids(), pack.SLACK_SECONDS)
    assert sandbox.call_folders() == []


@pytest.mark.asyncio
async def test_muse_required_server_failure_carries_muses_reason(browser_world, browser_api, sandbox, browse, check_browser_error, pack, sweep) -> None:
    # AC-12 / EC-18: Muse fails the run on a required server's startup
    # failure; its reason (naming the server) is the vendor text. The
    # node stand-in plays the MCP servers, so the failure is set on it.
    sandbox.node(server_fail=["playwright"])
    error = await refuse(browse, browser_api, "muse", tools=["playwright"])
    check_browser_error(error, harness="muse", verb="run", code="browser.tools_unavailable", workspace=sandbox.workspace, vendor=MUSE_REQUIRED_SERVER)
    assert sandbox.call_folders() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_the_sdk_writes_only_in_its_four_places(browser_world, browser_api, sandbox, browse, pack, sweep, harness) -> None:
    # AC-16 / INV-5: the workspace is byte-identical; every new or
    # changed path is the kept per-call folder, the tool cache or
    # Grok's private home (Muse's per-call config folder is gone).
    before = sandbox.snapshot()
    await browse(harness, tools=["playwright"], fake={"browser_calls": [SCREENSHOT_CALLS[harness]]})
    paths = changed(before, sandbox.snapshot())
    assert [path for path in paths if path == "ws" or path.startswith("ws/")] == []
    assert [path for path in paths if not path.startswith(ALLOWED_WRITES) and path != "home/.vidbyte"] == [], paths


@pytest.mark.asyncio
async def test_a_failing_call_leaves_no_trace(browser_world, browser_api, sandbox, browse, sweep) -> None:
    # AC-16: failing calls leave the workspace and the temp folder as
    # they were.
    before = sandbox.snapshot()
    with pytest.raises(browser_api.NativeThreadError):
        await browse("opencode", tools=["playwright"], fake=FAILURES["opencode"][0])
    assert changed(before, sandbox.snapshot()) == []


@pytest.mark.asyncio
async def test_concurrent_calls_keep_their_own_folders_and_browsers(browser_world, browser_api, sandbox, browse, pack, alive, wait_until, sweep) -> None:
    # AC-21 / NFR-9 / T-4: one call's cleanup never kills the other's
    # browser; each has its own per-call folder and agent file.
    held = asyncio.create_task(browse("grok", tools=["playwright"], fake={"mode": "hold"}))
    assert await wait_until(lambda: bool(sandbox.records("browser", "mcp-playwright")), START_SECONDS), "the held call's browser never started"
    (held_browser,) = [record["browser_pid"] for record in sandbox.records("browser", "mcp-playwright")]
    quick = await browse("grok", tools=["chromedevtools"])
    assert [call.name for call in quick.tool_calls] == ["navigate_page"]
    assert alive(held_browser), "AC-21: the quick call's reap killed the held call's browser"
    sandbox.release()
    slow = await held
    assert [call.name for call in slow.tool_calls] == ["browser_navigate"] and slow.thread_id != quick.thread_id
    agents = sandbox.records("agent")
    assert len({os.path.normcase(agent["path"]) for agent in agents}) == 2
    servers = sandbox.starts("mcp-playwright") + sandbox.starts("mcp-chromedevtools")
    assert len({os.path.normcase(str(pack.call_folder(server))) for server in servers}) == 2
    assert await gone(wait_until, alive, sandbox.browser_pids(), pack.SLACK_SECONDS)


@pytest.mark.asyncio
async def test_tool_calls_and_artifacts_cap_at_a_thousand(browser_world, browser_api, sandbox, browse, sweep) -> None:
    # EC-29 / NFR-1: the first 1,000 are kept and the flags set; every
    # artifact file stays on disk. The node stand-in plays the MCP
    # servers, so the screenshot burst is set on it; only a screenshot
    # call reads it, and the first call takes none.
    sandbox.node(artifact_burst=OVER_CAP)
    calls = await browse("opencode", tools=["playwright"], fake={"repeat_calls": OVER_CAP})
    assert len(calls.tool_calls) == CAP and calls.tool_calls_truncated is True
    files = await browse("opencode", tools=["playwright"], fake={"browser_calls": [SCREENSHOT_CALLS["opencode"]]})
    assert len(files.artifacts) == CAP and files.artifacts_truncated is True
    (folder,) = sandbox.call_folders()
    assert len(list((folder / "artifacts").iterdir())) == OVER_CAP



@pytest.mark.asyncio
async def test_grok_browser_output_is_capped_at_the_process_cap(browser_world, browser_api, sandbox, browse, check_browser_error, sweep) -> None:
    # D-19 / NFR-1: streamed tool output may pass Grok's 4 MiB plain
    # cap; a browser run caps at NATIVE_PROCESS_MAX_OUTPUT_BYTES.
    constants = browser_api.constants
    long = await browse("grok", tools=["firecrawl"], fake={"mode": "long_text", "text_chars": constants.GROK_CLI_MAX_OUTPUT_BYTES + PLAIN_CAP_EXTRA_CHARS})
    assert long.text_truncated is True and len(long.text) == constants.NATIVE_RESULT_TEXT_MAX_CHARS
    cap = constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES
    error = await refuse(browse, browser_api, "grok", tools=["firecrawl"], fake={"mode": "flood", "flood_bytes": cap + FLOOD_EXTRA_BYTES})
    check_browser_error(error, harness="grok", verb="run", code="grok.output_too_large", workspace=sandbox.workspace, observations=[("byte cap", (str(cap), f"{cap:,}"))])
    assert sandbox.call_folders() == []

@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_keys_echoed_by_the_vendor_never_reach_the_error(browser_world, browser_api, sandbox, browse, check_browser_error, pack, sweep, harness) -> None:
    # INV-4 / AC-7 / KD-6: the tool key and the harness key are
    # registered as secrets before any step that can produce error text.
    fake = {"mode": "echo_secrets", "echo_names": ["BRAVE_API_KEY"]}
    error = await refuse(browse, browser_api, harness, tools=["brave"], tool_keys={"brave": BRAVE_KEY}, fake=fake)
    check_browser_error(error, harness=harness, verb="run", code=f"{harness}.run_failed", workspace=sandbox.workspace, secrets=[BRAVE_KEY, pack.API_KEY])
    assert pack.files_holding(sandbox.root, BRAVE_KEY) == []


@pytest.mark.asyncio
async def test_process_reaper_kills_by_marker_and_spares_the_rest(browser_lib, sandbox, runner_spy, alive, wait_until, pack) -> None:
    # §8.5 / FR-15 / D-12: every process whose command line carries the
    # marker is killed and counted; others survive; the marker is never
    # on the reaper's own command line; PATH holds only stand-ins.
    reaper = browser_lib.process.ProcessReaper
    marker = str(sandbox.tmp / "vidbyte-browser-reaper-probe")
    marked = [subprocess.Popen([sys.executable, "-c", SLEEPER, SLEEPER_SECONDS, marker]) for _ in range(2)]
    control = subprocess.Popen([sys.executable, "-c", SLEEPER, SLEEPER_SECONDS, str(sandbox.tmp / "vidbyte-browser-other")])
    try:
        count = await reaper.reap(marker, timeout_seconds=REAP_SECONDS)
        assert count >= len(marked)
        assert await wait_until(lambda: not any(alive(process.pid) for process in marked), pack.SLACK_SECONDS)
        assert alive(control.pid), "a process without the marker was killed"
        assert await reaper.reap(marker, timeout_seconds=REAP_SECONDS) == 0
        assert not [invocation for invocation in runner_spy if any(marker in part for part in invocation.argv)]
    finally:
        for process in (*marked, control):
            if process.poll() is None:
                process.kill()
            process.wait()


@pytest.mark.asyncio
async def test_process_reaper_never_raises_on_its_own_timeout(browser_lib, sandbox) -> None:
    # §9.1 row 13: never raises on failure or timeout; returns a count.
    count = await browser_lib.process.ProcessReaper.reap(str(sandbox.tmp / "vidbyte-browser-none"), timeout_seconds=0.001)
    assert isinstance(count, int) and count >= 0
