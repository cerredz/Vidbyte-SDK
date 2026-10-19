"""FILE: tests/features/harness_threads/test_harness_threads_browser_runtime.py

PURPOSE: What a browser call needs before the harness starts (docs/spec/harness-browser-tools/spec.md §5 layers 4 and 5, FR-8, FR-9, NFR-5): Node on PATH at or above 22.12.0 and never a batch file, Chrome only for the tools that need it (AC-10, EC-8, EC-9), one pinned install per tool published by rename into ~/.vidbyte/tools (AC-11, EC-10 to EC-14), the per-call folder (EC-15), a missing harness after a cold install (EC-38) and the warm-cache child count (NFR-5).
ROLE IN CODEBASE: Start here when the Node check, the Chrome search, the tool cache, the npm install or the per-call folder changes.
ARCHITECTURE NOTE: The fake node on the sandbox PATH answers `--version` from its scenario and plays the npm bundled beside it (fake_browser.npm_install), which accepts only the exact FR-9 argv and installs the fake server's entry file; npm_mode switches it to fail (E404), hold, rendezvous or no_entry. Timing knobs and the Chrome locations are patched through vidbyte.lib.constants.browser_tools, as spec §13 allows; nothing in the SDK is mocked, and runner_spy only records the CliInvocations before running them.
FUNCTION INVENTORY: cold_world builds node and Chrome with an empty cache; under reports whether a path lies inside a folder; staging_left lists leftover staging folders; refuse runs a call that must raise; harness_index finds the harness's own invocation in runner_spy; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new preflight rule adds a scenario field to the fake node (fake_browser.py) and a test here that the harness never starts.
WHAT NOT TO DO IN THIS FILE: 1. Do not let a test reach a real node, npm or Chrome: PATH holds only the sandbox bin folder and BROWSER_CHROME_PATHS is always patched. 2. Do not unset HOME on POSIX: expanduser would fall back to the real home and install there; EC-14 patches Path.home as test_harness_threads_launcher.py does.
KNOWN EDGE CASES: The batch-file and `.cmd` cases exist only on win32. The install race uses the fake's file rendezvous, so both installs overlap without any sleep; a design that serialises installs still passes, only slower.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §6.2 AC-10, AC-11, §6.3 EC-8 to EC-15, EC-38, §7 FR-8, FR-9, NFR-5, §9.3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_browser_runtime.py
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from pathlib import Path
from typing import Any

import pytest

HARNESSES = ("grok", "opencode", "muse")
PLAYWRIGHT_SPEC = "@playwright/mcp@0.0.83"
NPM_FLAGS = ["install", "--no-audit", "--no-fund", "--prefix"]
OLD_NODES = ("v22.11.0", "v20.18.1")
SPACED_HOME = "home dir é"
SPACED_BIN = "bin dir é"
INSTALL_TIMEOUT_SECONDS = 1.0
NPM_START_SECONDS = 30.0
win32_only = pytest.mark.skipif(sys.platform != "win32", reason="node.cmd and node.bat exist only on win32 (EC-8)")


def cold_world(sandbox, lib, monkeypatch, **node_fields: Any) -> Path:
    # Node and Chrome present, nothing in the tool cache.
    node = sandbox.node(**node_fields)
    monkeypatch.setattr(lib.browser_constants, "BROWSER_CHROME_PATHS", (str(sandbox.chrome()),))
    return node


def under(path: Path | str, folder: Path) -> bool:
    inner = os.path.normcase(os.path.abspath(str(path)))
    outer = os.path.normcase(os.path.abspath(str(folder)))
    return inner.startswith(outer + os.sep)


def staging_left(sandbox) -> list[str]:
    staging = sandbox.tool_cache / ".staging"
    return sorted(path.name for path in staging.iterdir()) if staging.is_dir() else []


async def refuse(browse, lib, harness: str, **arguments: Any):
    with pytest.raises(lib.NativeThreadError) as caught:
        await browse(harness, **arguments)
    return caught.value


def harness_index(invocations: list[Any], pack) -> int:
    found = [index for index, invocation in enumerate(invocations) if str(pack.FAKE) in [str(part) for part in invocation.argv]]
    assert len(found) == 1, [list(invocation.argv) for invocation in invocations]
    return found[0]


def mentions(message: str, path: Path | str, pack) -> bool:
    folded = message.lower() if sys.platform == "win32" else message
    return any((spelling.lower() if sys.platform == "win32" else spelling) in folded for spelling in pack.path_spellings(path))


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_no_node_on_path_is_runtime_missing(browser_api, sandbox, browse, check_browser_error, pack, monkeypatch, harness) -> None:
    # AC-10 / FR-8: a stdio tool with no node on PATH; the harness is
    # never started.
    sandbox.cache_tools()
    monkeypatch.setattr(browser_api.browser_constants, "BROWSER_CHROME_PATHS", (str(sandbox.chrome()),))
    error = await refuse(browse, browser_api, harness, tools=["firecrawl"])
    check_browser_error(error, harness=harness, verb="run", code="browser.runtime_missing", workspace=sandbox.workspace)
    assert "node" in str(error).lower()
    assert sandbox.starts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("version", OLD_NODES)
async def test_node_below_the_floor_is_runtime_missing_naming_the_version(browser_api, sandbox, browse, check_browser_error, pack, monkeypatch, version) -> None:
    # AC-10 / D-6: node --version below 22.12.0 names what was found.
    cold_world(sandbox, browser_api, monkeypatch, node_version=version)
    sandbox.cache_tools()
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"])
    check_browser_error(error, harness="opencode", verb="run", code="browser.runtime_missing", workspace=sandbox.workspace)
    assert version.lstrip("v") in str(error)
    assert len(sandbox.starts("node-version")) == 1 and sandbox.starts("opencode") == [] and sandbox.starts("npm") == []


@pytest.mark.asyncio
@win32_only
@pytest.mark.parametrize("name", ["node.cmd", "node.bat"])
async def test_a_batch_file_node_is_refused_unrun(browser_api, sandbox, browse, check_browser_error, pack, monkeypatch, name) -> None:
    # EC-8 / D-6: refused as NativeLauncher refuses harness batch files;
    # the batch file never runs.
    target, marker = sandbox.batch_file(sandbox.bin, name)
    sandbox.cache_tools()
    monkeypatch.setattr(browser_api.browser_constants, "BROWSER_CHROME_PATHS", (str(sandbox.chrome()),))
    error = await refuse(browse, browser_api, "grok", tools=["firecrawl"])
    check_browser_error(error, harness="grok", verb="run", code="browser.runtime_missing", workspace=sandbox.workspace)
    assert mentions(str(error), target, pack), str(error)
    assert not marker.exists() and sandbox.starts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["playwright", "chromedevtools"])
async def test_no_chrome_is_runtime_missing_listing_the_searched_locations(browser_api, sandbox, browse, check_browser_error, pack, no_chrome, tool) -> None:
    # AC-10 / EC-9: the error lists where Chrome was looked for; the
    # harness is never started.
    sandbox.node()
    sandbox.cache_tools()
    error = await refuse(browse, browser_api, "opencode", tools=[tool])
    check_browser_error(error, harness="opencode", verb="run", code="browser.runtime_missing", workspace=sandbox.workspace)
    assert mentions(str(error), no_chrome, pack), str(error)
    assert sandbox.starts("opencode") == []


@pytest.mark.asyncio
async def test_a_tool_that_needs_no_chrome_runs_without_it(browser_api, sandbox, browse, no_chrome) -> None:
    # INV-1 / FR-8: the Chrome check passes when no selected tool needs
    # Chrome.
    sandbox.node()
    sandbox.cache_tools()
    result = await browse("opencode", tools=["firecrawl"])
    assert [call.name for call in result.tool_calls] == ["firecrawl_search"]


@pytest.mark.asyncio
async def test_cold_cache_installs_once_with_the_pinned_argv_and_publishes(browser_api, sandbox, browse, pack, monkeypatch) -> None:
    # AC-11 / FR-9 / INV-8: <node> <bundled npm-cli.js> install
    # --no-audit --no-fund --prefix <staging> <package>@<version>, then
    # an atomic publish into ~/.vidbyte/tools/playwright-0.0.83; the
    # second call installs nothing.
    node = cold_world(sandbox, browser_api, monkeypatch)
    first = await browse("opencode", tools=["playwright"])
    (install,) = sandbox.starts("npm")
    assert pack.same_path(install["argv"][0], sandbox.npm_cli(node)) and install["npm_cli_exists"] is True
    assert install["argv"][1:5] == NPM_FLAGS and install["argv"][6] == PLAYWRIGHT_SPEC
    assert under(install["argv"][5], sandbox.tool_cache / ".staging"), install["argv"][5]
    assert sandbox.tool_entry("playwright").is_file() and staging_left(sandbox) == []
    (server,) = sandbox.starts("mcp-playwright")
    assert pack.same_path(server["entry"], sandbox.tool_entry("playwright")) and server["entry_absolute"] is True
    second = await browse("opencode", tools=["playwright"])
    assert len(sandbox.starts("npm")) == 1
    assert [call.name for call in first.tool_calls] == [call.name for call in second.tool_calls] == ["browser_navigate"]


@pytest.mark.asyncio
async def test_a_failing_install_publishes_nothing_and_attaches_npms_text(browser_api, sandbox, browse, check_browser_error, pack, monkeypatch) -> None:
    # AC-11 / EC-13: browser.tool_install_failed with npm's stderr as
    # the vendor text; no published folder, no staging left, no harness.
    cold_world(sandbox, browser_api, monkeypatch, npm_mode="fail")
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"])
    check_browser_error(error, harness="opencode", verb="run", code="browser.tool_install_failed", workspace=sandbox.workspace, vendor="E404")
    assert not sandbox.tool_folder("playwright").exists() and staging_left(sandbox) == []
    assert sandbox.starts("opencode") == []


@pytest.mark.asyncio
async def test_an_install_without_the_entry_file_is_not_published(browser_api, sandbox, browse, check_browser_error, monkeypatch) -> None:
    # FR-9 "verifies the entry": npm exits 0 but the entry is missing.
    cold_world(sandbox, browser_api, monkeypatch, npm_mode="no_entry")
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"])
    check_browser_error(error, harness="opencode", verb="run", code="browser.tool_install_failed", workspace=sandbox.workspace)
    assert not sandbox.tool_folder("playwright").exists() and staging_left(sandbox) == []
    assert sandbox.starts("opencode") == []


@pytest.mark.asyncio
async def test_two_racing_installs_converge_on_one_published_copy(browser_api, sandbox, browse, pack, monkeypatch) -> None:
    # EC-10 / D-5 / NFR-9: each install uses its own staging folder; the
    # first rename publishes and the loser removes its staging.
    cold_world(sandbox, browser_api, monkeypatch, npm_mode="rendezvous")
    first, second = await asyncio.gather(browse("opencode", tools=["playwright"]), browse("grok", tools=["playwright"]))
    assert [call.name for call in first.tool_calls] == [call.name for call in second.tool_calls] == ["browser_navigate"]
    installs = sandbox.starts("npm")
    assert 1 <= len(installs) <= 2 and len({os.path.normcase(start["argv"][5]) for start in installs}) == len(installs)
    assert sandbox.tool_entry("playwright").is_file() and staging_left(sandbox) == []
    assert sorted(path.name for path in sandbox.tool_cache.iterdir() if path.name != ".staging") == ["playwright-0.0.83"]


@pytest.mark.asyncio
async def test_an_install_past_its_bound_is_stopped_and_cleaned(browser_api, sandbox, browse, check_browser_error, pack, monkeypatch, fast_stop, wait_until) -> None:
    # EC-11: BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS (read at call time)
    # bounds npm; staging removed, npm stopped, nothing published.
    cold_world(sandbox, browser_api, monkeypatch, npm_mode="hold")
    monkeypatch.setattr(browser_api.browser_constants, "BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS", INSTALL_TIMEOUT_SECONDS)
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"])
    check_browser_error(error, harness="opencode", verb="run", code="browser.tool_install_failed", workspace=sandbox.workspace)
    (install,) = sandbox.starts("npm")
    assert await wait_until(lambda: not pack.process_alive(install["pid"]), fast_stop.kill_wait + fast_stop.slack), "npm outlived its bound"
    assert not sandbox.tool_folder("playwright").exists() and staging_left(sandbox) == [] and sandbox.starts("opencode") == []


@pytest.mark.asyncio
async def test_a_cancelled_install_is_stopped_cleaned_and_re_raised(browser_api, sandbox, browse, pack, monkeypatch, fast_stop, wait_until) -> None:
    # EC-11 / EC-20: cancel re-raises CancelledError after the staging
    # is removed.
    cold_world(sandbox, browser_api, monkeypatch, npm_mode="hold")
    task = asyncio.create_task(browse("opencode", tools=["playwright"]))
    assert await wait_until(lambda: bool(sandbox.starts("npm")), NPM_START_SECONDS), "npm never started"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (install,) = sandbox.starts("npm")
    assert await wait_until(lambda: not pack.process_alive(install["pid"]), fast_stop.kill_wait + fast_stop.slack), "npm outlived the cancel"
    assert not sandbox.tool_folder("playwright").exists() and staging_left(sandbox) == [] and sandbox.starts("opencode") == []


@pytest.mark.asyncio
async def test_a_broken_published_folder_is_named_not_repaired(browser_api, sandbox, browse, check_browser_error, pack, monkeypatch) -> None:
    # EC-12: the published folder exists without its entry file; the
    # error names the folder to delete and nothing is installed.
    cold_world(sandbox, browser_api, monkeypatch)
    package = sandbox.tool_folder("playwright") / "node_modules" / "@playwright" / "mcp"
    package.mkdir(parents=True)
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"])
    check_browser_error(error, harness="opencode", verb="run", code="browser.tool_install_failed", workspace=sandbox.workspace)
    assert mentions(str(error), sandbox.tool_folder("playwright"), pack), str(error)
    assert sandbox.starts("npm") == [] and package.is_dir() and not sandbox.tool_entry("playwright").exists()


@pytest.mark.asyncio
async def test_a_node_without_its_bundled_npm_cannot_install(browser_api, sandbox, browse, check_browser_error, monkeypatch) -> None:
    # EC-13 / A-8: a Debian-style node with no npm-cli.js beside it.
    node = cold_world(sandbox, browser_api, monkeypatch)
    sandbox.npm_cli(node).unlink()
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"])
    check_browser_error(error, harness="opencode", verb="run", code="browser.tool_install_failed", workspace=sandbox.workspace)
    assert not sandbox.tool_folder("playwright").exists() and sandbox.starts("opencode") == []


@pytest.mark.asyncio
async def test_an_unknown_home_is_tool_install_failed(browser_api, sandbox, browse, check_browser_error, monkeypatch) -> None:
    # EC-14: Path.home() raising RuntimeError (the seam the plain Grok
    # home test uses) means no cache can exist.
    cold_world(sandbox, browser_api, monkeypatch)
    command = sandbox.command("opencode")

    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(pathlib.Path, "home", classmethod(no_home))
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"], command=command)
    check_browser_error(error, harness="opencode", verb="run", code="browser.tool_install_failed", workspace=sandbox.workspace)
    assert sandbox.starts("npm") == [] and sandbox.starts("opencode") == []


@pytest.mark.asyncio
async def test_an_uncreatable_call_folder_is_launch_failed(browser_world, browser_api, sandbox, browse, check_browser_error, pack, monkeypatch) -> None:
    # EC-15 / D-3: mkdtemp fails before anything starts; the harness's
    # own launch_failed with the folder detail.
    missing = sandbox.root / "no-such-temp"
    monkeypatch.setattr("tempfile.tempdir", str(missing))
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"])
    check_browser_error(error, harness="opencode", verb="run", code="opencode.launch_failed", workspace=sandbox.workspace)
    assert mentions(str(error), missing, pack), str(error)
    assert sandbox.starts("opencode") == [] and not missing.exists()


@pytest.mark.asyncio
async def test_a_missing_harness_after_a_cold_install_keeps_the_install(browser_api, sandbox, browse, check_browser_error, monkeypatch) -> None:
    # EC-38 / D-3: the install is kept and the plain path's
    # opencode.not_installed is raised.
    cold_world(sandbox, browser_api, monkeypatch)
    error = await refuse(browse, browser_api, "opencode", tools=["playwright"], config={"opencode_command": None})
    check_browser_error(error, harness="opencode", verb="run", code="opencode.not_installed", workspace=sandbox.workspace)
    assert len(sandbox.starts("npm")) == 1 and sandbox.tool_entry("playwright").is_file()
    assert sandbox.call_folders() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("tools", "before"), [(["playwright"], 1), (["jina"], 0)])
async def test_a_warm_call_starts_at_most_one_child_before_and_one_after(browser_world, browser_api, sandbox, browse, runner_spy, pack, tools, before) -> None:
    # NFR-5 / INV-1: node --version before the harness only when a stdio
    # tool is selected; at most the reaper after it; no install.
    await browse("opencode", tools=tools)
    index = harness_index(runner_spy, pack)
    assert len(runner_spy[:index]) == before, [list(invocation.argv) for invocation in runner_spy[:index]]
    if before:
        (version,) = runner_spy[:index]
        assert pack.same_path(version.argv[0], browser_world.node) and list(version.argv[1:]) == ["--version"]
    assert len(runner_spy[index + 1 :]) <= 1 and sandbox.starts("npm") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_spaced_non_ascii_node_and_cache_paths_still_mount(browser_api, sandbox, browse, pack, monkeypatch, harness) -> None:
    # EC-37 / INV-8: argv elements are never shell-joined and every
    # config is JSON-encoded, so node, the entry and the per-call
    # folder may hold spaces and non-ASCII characters.
    sandbox.home, sandbox.bin = sandbox.root / SPACED_HOME, sandbox.root / SPACED_BIN
    sandbox.home.mkdir()
    sandbox.bin.mkdir()
    for name in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(name, str(sandbox.home))
    monkeypatch.setenv("PATH", str(sandbox.bin))
    cold_world(sandbox, browser_api, monkeypatch)
    sandbox.cache_tools("playwright")
    result = await browse(harness, tools=["playwright"])
    assert [call.name for call in result.tool_calls] == ["browser_navigate"]
    (server,) = sandbox.starts("mcp-playwright")
    assert pack.same_path(server["entry"], sandbox.tool_entry("playwright")) and sandbox.starts("npm") == []
