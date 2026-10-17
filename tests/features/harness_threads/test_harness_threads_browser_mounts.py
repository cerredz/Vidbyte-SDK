"""FILE: tests/features/harness_threads/test_harness_threads_browser_mounts.py

PURPOSE: What each harness is given and what it reports back (docs/spec/harness-browser-tools/spec.md §9.1 "Mount by harness", FR-11 to FR-13, FR-17): all nine functions mount a tool and read the vendor's own calls (AC-2), web tools off, fail-closed narrowing (AC-6), where a tool key travels (AC-7, AC-9), Grok's compat switches (AC-14), the argv budget (AC-18), Muse in WSL mode (AC-19, AC-31), remote tools (AC-22, AC-32), the Muse settings shape (AC-26), additive Playwright caps (AC-27), prefixed opencode ids (AC-28), byte-stable compiles (INV-11), the server command (INV-8, D-21) and readers that skip vendor-written names (AC-33, EC-28, EC-30, EC-41).
ROLE IN CODEBASE: Start here when a compiled mount, a permission rule, a reader or a refusal of an unsupported combination changes.
ARCHITECTURE NOTE: Every call is a real browser function against the fake vendor, which reads the compiled mount the way the vendor does and starts the fake node servers it names (fake_browser.py); assertions read what those processes logged, never the SDK's internals. Refusals are checked to start nothing (no `node --version` either) and write nothing, which proves they come before preflight (INV-9).
FUNCTION INVENTORY: expect_call builds one BrowserToolCall; exec_start reads the harness's last start record; refuse runs a call that must raise and returns the error; strip_folder replaces a per-call folder path in a compiled config; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new vendor rule goes into fake_browser.py first (with a self-test in test_harness_threads_browser_fakes.py), then gets an assertion here.
WHAT NOT TO DO IN THIS FILE: 1. Do not read a key back from a log; the fakes log digests (pack.key_digest). 2. Do not mock CliRunner; runner_spy only records and then runs.
KNOWN EDGE CASES: The fakes log records with sorted keys, so rule order is read from the opencode reader's `rules` list and the Grok start's `rules`, never from a logged mapping. The default fake agent calls one probe tool per mounted server (playwright: browser_navigate, firecrawl: firecrawl_search, jina: read_url, brave: brave_web_search, browserbase: navigate).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §6.2 AC-2, AC-6, AC-7, AC-9, AC-14, AC-18, AC-19, AC-22, AC-26 to AC-28, AC-31 to AC-33, §6.3 EC-26 to EC-30, EC-40 to EC-44, §9.1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_browser_mounts.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

HARNESSES = ("grok", "opencode", "muse")
VERBS = ("run", "continue", "fork")
BRAVE_KEY = "BSA" + "k3v9Qx7Lm2Np8Rt4" + "Wz6Yb1Cd5Fg0Hj"
BRIGHTDATA_KEY = "4c7e9a1b3d5f7a9c" + "1e3b5d7f9a1c3e5b" + "7d9f1a3c5e7b9d1f" + "3a5c7e9b1d3f5a7c"
BROWSERBASE_KEY = "bb_live_" + "Xq7Lm2Np8Rt4Wz6Y" + "b1Cd5Fg0Hj3Kv"
JINA_KEY = "jina_" + "7c1f9e2d4b6a8c0e" + "3f5a7b9d1c2e4f6a" + "8b0c3d5e7f9a1b2c"
CALLER_FIRECRAWL_KEY = "fc-" + "9e8d7c6b5a4f3e2d" + "1c0b9a8f7e6d5c4b"
JINA_URL = "https://mcp.jina.ai/v1"
BROWSERBASE_URL = "https://mcp.browserbase.com/mcp"
WEB_SWITCHES = {"grok": "--disable-web-search", "muse": "--disable-web-tools"}
COMPAT_OFF = {"GROK_CLAUDE_MCPS_ENABLED": "0", "GROK_CURSOR_MCPS_ENABLED": "0"}
WSL_ONLY_REMOTE = ("jina", "parallel")
BUDGET_HINT = re.compile(r"narrow|fewer", re.IGNORECASE)
MOUNT_WORD = re.compile(r"\bmount", re.IGNORECASE)
BOGUS_NAMES = {
    "opencode": ["vidbyte-playwright_browser navigate", "vidbyte-playwright__leading", "vidbyte-playwright_" + "x" * 65],
    "grok": ["playwright__browser navigate", "playwright__" + "x" * 65],
    "muse": ["mcp__playwright__browser navigate", "mcp__playwright__" + "x" * 65],
}


def expect_call(lib, tool: str, name: str, status: str = "completed"):
    return lib.BrowserToolCall(tool=lib.BrowserTool(tool), name=name, status=lib.BrowserToolCallStatus(status))


def exec_start(sandbox, pack, harness: str) -> dict[str, Any]:
    return sandbox.starts(pack.EXEC_ROLES[harness])[-1]


async def refuse(browse, lib, harness: str, **arguments: Any):
    with pytest.raises(lib.NativeThreadError) as caught:
        await browse(harness, **arguments)
    return caught.value


def strip_folder(node: Any, folder: Path) -> Any:
    # INV-11: the compiled mount apart from the per-call folder path,
    # in either spelling.
    if isinstance(node, dict):
        return {key: strip_folder(value, folder) for key, value in node.items()}
    if isinstance(node, list):
        return [strip_folder(value, folder) for value in node]
    if isinstance(node, str):
        return node.replace(str(folder), "<folder>").replace(folder.as_posix(), "<folder>")
    return node


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("harness", HARNESSES)
async def test_every_browser_function_mounts_a_tool_and_reads_the_vendors_calls(browser_api, browser_world, sandbox, call, browse, pack, harness, verb) -> None:
    # AC-2 / FR-1 / FR-3 / FR-10 / FR-12 / FR-13 / INV-10: a
    # BrowserThreadResult from the vendor's output; web tools off; the
    # prompt unchanged; profile and output under a per-call folder
    # outside the workspace.
    lib = browser_api
    thread_id = None if verb == "run" else (await call(harness)).thread_id
    result = await browse(harness, verb, tools=["playwright"], thread_id=thread_id)
    assert isinstance(result, lib.BrowserThreadResult) and result.harness is lib.enums.NativeHarness(harness)
    assert result.thread_id == sandbox.answers(pack.EXEC_ROLES[harness])[-1]["session"]
    if verb != "run":
        assert (result.thread_id == thread_id) is (verb == "continue")
    assert (result.text, result.text_truncated) == (f"{harness} answer to: {pack.PROMPT}", False)
    assert result.tool_calls == (expect_call(lib, "playwright", "browser_navigate"),) and result.tool_calls_truncated is False
    assert (result.artifacts, result.artifacts_truncated) == ((), False)
    start = exec_start(sandbox, pack, harness)
    if harness == "opencode":
        (tools,) = sandbox.records("mcp_tools", "opencode")
        assert (tools["webfetch"], tools["websearch"]) == ("deny", "deny") and start["stdin_text"] == pack.PROMPT
    else:
        assert WEB_SWITCHES[harness] in start["switches"]
        assert (start["options"]["--single"] if harness == "grok" else start["operands"][0]) == pack.PROMPT
    (server,) = sandbox.starts("mcp-playwright")
    folder = pack.call_folder(server)
    assert pack.same_path(folder.parent, sandbox.tmp) and folder.name.startswith("vidbyte-browser-")
    assert Path(pack.server_option(server, "--user-data-dir")).name == "playwright" and Path(pack.server_option(server, "--user-data-dir")).parent.name == "profiles"
    assert pack.same_path(pack.server_option(server, "--output-dir"), folder / "artifacts")
    assert not os.path.normcase(str(folder)).startswith(os.path.normcase(str(sandbox.workspace)))


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS)
async def test_muse_in_wsl_mode_mounts_jina_without_node_or_chrome(browser_api, sandbox, call, browse, pack, wsl_ready, no_chrome, verb) -> None:
    # AC-2 / AC-19 / AC-31 / §2: WSL mode mounts the keyless remote
    # tool as {"transport": "streamable_http", "url": ...}; no node and
    # no Chrome are looked for, nothing is installed.
    lib = browser_api
    sandbox.stand_in(sandbox.bin, "wsl", "muse", as_wsl=True, wsl={"distros": [pack.FAKE_DISTRO], "muse_path": "/usr/local/bin/muse"})
    config = {"muse_command": None, "wsl_distro": pack.FAKE_DISTRO}
    thread_id = None if verb == "run" else (await call("muse", config=config)).thread_id
    result = await browse("muse", verb, tools=["jina"], config=config, thread_id=thread_id)
    assert isinstance(result, lib.BrowserThreadResult) and result.tool_calls == (expect_call(lib, "jina", "read_url"),)
    assert result.thread_id == sandbox.answers("muse-exec")[-1]["session"]
    start = exec_start(sandbox, pack, "muse")
    assert start["via_wsl"] is True and "--disable-web-tools" in start["switches"]
    settings = sandbox.records("settings")[-1]
    assert settings["servers"] == {"jina": {"transport": "streamable_http", "url": JINA_URL}} and settings["disabled"] is None
    assert sandbox.starts("node-version") == [] and sandbox.starts("npm") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["playwright", "chromedevtools", "firecrawl", "exa"])
async def test_muse_in_wsl_mode_refuses_every_stdio_tool_before_any_io(browser_api, browser_world, sandbox, browse, check_browser_error, pack, tool) -> None:
    # AC-19 / EC-42 / INV-9: browser.mount_unsupported naming what WSL
    # mode can mount; nothing started (not even node) and nothing
    # written. WSL mode is a config, so this runs on every platform.
    before = sandbox.snapshot()
    error = await refuse(browse, browser_api, "muse", tools=[tool], config={"muse_command": None, "wsl_distro": pack.FAKE_DISTRO})
    check_browser_error(error, harness="muse", verb="run", code="browser.mount_unsupported", workspace=sandbox.workspace)
    assert all(name in str(error) for name in WSL_ONLY_REMOTE), str(error)
    assert sandbox.starts() == [] and sandbox.snapshot() == before


@pytest.mark.asyncio
async def test_opencode_mounts_jina_with_no_node_and_no_chrome(browser_api, sandbox, browse, no_chrome) -> None:
    # AC-31 / INV-1 / FR-8: a remote-only selection needs no Node and no
    # Chrome, and installs nothing.
    result = await browse("opencode", tools=["jina"])
    assert result.tool_calls == (expect_call(browser_api, "jina", "read_url"),)
    assert sandbox.starts("node-version") == [] and sandbox.starts("npm") == []


@pytest.mark.asyncio
async def test_opencode_narrowing_denies_the_server_then_allows_one_tool(browser_api, browser_world, sandbox, browse) -> None:
    # AC-6 / D-10 / FR-12: "vidbyte-firecrawl_*": "deny" first, then the
    # one exact allow; the model sees only that tool.
    result = await browse("opencode", tools=["firecrawl:search"])
    (tools,) = sandbox.records("mcp_tools", "opencode")
    rules = [tuple(rule) for rule in tools["rules"] if rule[0].startswith("vidbyte-firecrawl")]
    assert rules == [("vidbyte-firecrawl_*", "deny"), ("vidbyte-firecrawl_firecrawl_search", "allow")]
    assert tools["visible"] == ["vidbyte-firecrawl_firecrawl_search"]
    assert result.tool_calls == (expect_call(browser_api, "firecrawl", "firecrawl_search"),)


@pytest.mark.asyncio
async def test_grok_narrowing_allows_exactly_and_denies_every_other_known_tool(browser_api, browser_world, sandbox, browse) -> None:
    # AC-6 / D-10 / EC-41: one exact allow, one exact deny per other
    # known Firecrawl tool, no wildcard allow.
    lib = browser_api
    (selection,) = lib.BrowserToolRegistry.select(lib.BrowserToolRequest(tools=["firecrawl:search"], tool_keys=None))
    result = await browse("grok", tools=["firecrawl:search"])
    rules = sandbox.only_start("grok")["rules"]
    assert rules["allow"] == ["MCPTool(firecrawl__firecrawl_search)"]
    assert sorted(rules["deny"]) == sorted(f"MCPTool(firecrawl__{name})" for name in selection.denied) and len(rules["deny"]) == 25
    assert result.tool_calls == (expect_call(lib, "firecrawl", "firecrawl_search"),)


@pytest.mark.asyncio
@pytest.mark.parametrize(("tools", "keys", "secret"), [(["firecrawl:search"], None, None), (["brave"], {"brave": BRAVE_KEY}, BRAVE_KEY)])
async def test_muse_refuses_narrowing_and_keys_before_any_io(browser_api, browser_world, sandbox, browse, check_browser_error, tools, keys, secret) -> None:
    # AC-6 / AC-7 / EC-26 / EC-27 / D-9: Muse cannot filter its catalog
    # and takes a key only as a literal in a file.
    before = sandbox.snapshot()
    error = await refuse(browse, browser_api, "muse", tools=tools, tool_keys=keys)
    check_browser_error(error, harness="muse", verb="run", code="browser.mount_unsupported", workspace=sandbox.workspace, secrets=[secret] if secret else [])
    assert sandbox.starts() == [] and sandbox.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "carrier"), [("grok", "BRAVE_API_KEY"), ("opencode", "OPENCODE_CONFIG_CONTENT")])
async def test_tool_key_travels_only_in_the_child_environment(browser_api, browser_world, sandbox, browse, runner_spy, pack, harness, carrier) -> None:
    # AC-7 / INV-4 / D-7: Grok's overlay holds BRAVE_API_KEY (servers
    # inherit it); opencode carries it inside OPENCODE_CONFIG_CONTENT.
    # Never in argv, stdin, a written file or os.environ.
    result = await browse(harness, tools=["brave"], tool_keys={"brave": BRAVE_KEY})
    assert result.tool_calls == (expect_call(browser_api, "brave", "brave_web_search"),)
    holders = [name for invocation in runner_spy for name, value in invocation.env_overlay.items() if BRAVE_KEY in value]
    assert holders == [carrier]
    assert not [element for invocation in runner_spy for element in invocation.argv if BRAVE_KEY in element]
    assert not [invocation for invocation in runner_spy if BRAVE_KEY in (invocation.stdin_text or "")]
    (server,) = sandbox.starts("mcp-brave")
    assert server["tool_credentials"]["BRAVE_API_KEY"] == pack.key_digest(BRAVE_KEY)
    start = exec_start(sandbox, pack, harness)
    if harness == "grok":
        assert start["tool_credentials"]["BRAVE_API_KEY"] == pack.key_digest(BRAVE_KEY) and sandbox.records("agent")[0]["keys_in_file"] == []
    else:
        assert start["tool_credentials"]["BRAVE_API_KEY"] is None
        assert start["opencode_config"]["mcp"]["vidbyte-brave"]["environment"]["BRAVE_API_KEY"] == pack.key_digest(BRAVE_KEY)
    assert BRAVE_KEY not in os.environ.values() and pack.files_holding(sandbox.root, BRAVE_KEY) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_a_key_in_the_callers_environment_is_never_used_silently(browser_api, browser_world, sandbox, browse, monkeypatch, pack, harness) -> None:
    # AC-9 / INV-13 / D-20: FIRECRAWL_API_KEY is removed from the
    # harness child, so its servers never see it.
    monkeypatch.setenv("FIRECRAWL_API_KEY", CALLER_FIRECRAWL_KEY)
    await browse(harness, tools=["firecrawl"])
    assert exec_start(sandbox, pack, harness)["tool_credentials"]["FIRECRAWL_API_KEY"] is None
    (server,) = sandbox.starts("mcp-firecrawl")
    assert server["tool_credentials"]["FIRECRAWL_API_KEY"] is None
    assert os.environ["FIRECRAWL_API_KEY"] == CALLER_FIRECRAWL_KEY


@pytest.mark.asyncio
async def test_grok_browser_runs_switch_off_compat_scans_and_stream(browser_api, browser_world, sandbox, call, browse) -> None:
    # AC-14 / FR-17 / D-8 / INV-14: compat scans off and streaming-json
    # on the browser path only; the plain path is unchanged.
    await browse("grok", tools=["playwright"])
    await call("grok")
    browser, plain = sandbox.starts("grok")
    assert browser["browser_env"] == COMPAT_OFF and browser["options"]["--output-format"] == "streaming-json"
    assert plain["browser_env"] == {name: None for name in COMPAT_OFF} and plain["options"]["--output-format"] == "json"
    assert "--agent" not in plain["options"] and plain["rules"] == {"allow": [], "deny": []}


@pytest.mark.asyncio
async def test_grok_refuses_rules_beyond_the_argv_budget(browser_api, browser_world, sandbox, browse, check_browser_error) -> None:
    # AC-18 / EC-25 / NFR-6: two narrowed servers need more than
    # GROK_BROWSER_RULES_MAX_UNITS of deny rules.
    before = sandbox.snapshot()
    error = await refuse(browse, browser_api, "grok", tools=["firecrawl:search", "brightdata:search"], tool_keys={"brightdata": BRIGHTDATA_KEY})
    check_browser_error(error, harness="grok", verb="run", code="browser.mount_unsupported", workspace=sandbox.workspace, secrets=[BRIGHTDATA_KEY])
    assert BUDGET_HINT.search(str(error)), str(error)
    assert sandbox.starts() == [] and sandbox.snapshot() == before


@pytest.mark.asyncio
async def test_opencode_mounts_a_keyed_remote_tool_with_a_bearer_header(browser_api, browser_world, sandbox, browse, pack) -> None:
    # AC-22 / §9.1: {"type": "remote", "url", "oauth": false, "enabled":
    # true, "headers": {"Authorization": "Bearer <key>"}}.
    result = await browse("opencode", tools=["browserbase"], tool_keys={"browserbase": BROWSERBASE_KEY})
    entry = sandbox.only_start("opencode")["opencode_config"]["mcp"]["vidbyte-browserbase"]
    assert entry == {"type": "remote", "url": BROWSERBASE_URL, "oauth": False, "enabled": True, "headers": {"Authorization": pack.key_digest(f"Bearer {BROWSERBASE_KEY}")}}
    assert sandbox.records("remote")[0]["authorization"] == pack.key_digest(f"Bearer {BROWSERBASE_KEY}")
    assert result.tool_calls == (expect_call(browser_api, "browserbase", "navigate"),)


@pytest.mark.asyncio
@pytest.mark.parametrize(("tools", "keys", "secret"), [(["browserbase"], {"browserbase": BROWSERBASE_KEY}, BROWSERBASE_KEY), (["jina"], {"jina": JINA_KEY}, JINA_KEY)])
async def test_grok_refuses_a_keyed_remote_tool_before_any_io(browser_api, browser_world, sandbox, browse, check_browser_error, tools, keys, secret) -> None:
    # AC-22 / AC-32 / D-9: the key would have to be written into the
    # agent file, so the call is refused and the key appears nowhere.
    before = sandbox.snapshot()
    error = await refuse(browse, browser_api, "grok", tools=tools, tool_keys=keys)
    check_browser_error(error, harness="grok", verb="run", code="browser.mount_unsupported", workspace=sandbox.workspace, secrets=[secret])
    assert sandbox.starts() == [] and sandbox.snapshot() == before


@pytest.mark.asyncio
async def test_grok_mounts_keyless_jina_as_a_url_only_entry(browser_api, browser_world, sandbox, browse) -> None:
    # AC-32 / Q-18: {"name": "jina", "url": ...} in the agent file and a
    # wildcard allow for the unnarrowed server.
    result = await browse("grok", tools=["jina"])
    (agent,) = sandbox.records("agent")
    assert agent["servers"] == [{"name": "jina", "url": JINA_URL}]
    assert "MCPTool(jina__*)" in sandbox.only_start("grok")["rules"]["allow"]
    assert result.tool_calls == (expect_call(browser_api, "jina", "read_url"),)


@pytest.mark.asyncio
async def test_grok_agent_file_lives_in_the_call_folder_with_a_neutral_body(browser_api, browser_world, sandbox, browse, pack) -> None:
    # D-7 / D-18 / INV-5 / INV-8: --agent=<per-call folder>/<file>;
    # stdio entries are <node> with [<absolute entry>, ...]; the body
    # names no tool and never says tools are mounted.
    await browse("grok", tools=["playwright"])
    (agent,) = sandbox.records("agent")
    (server,) = sandbox.starts("mcp-playwright")
    assert pack.same_path(Path(agent["path"]).parent, pack.call_folder(server))
    (entry,) = agent["servers"]
    assert entry["name"] == "playwright" and pack.same_path(entry["command"], browser_world.node)
    assert pack.same_path(entry["args"][0], sandbox.tool_entry("playwright")) and "--headless" in entry["args"] and isinstance(entry["env"], list)
    body = agent["body"]
    named = [tool.value for tool in browser_api.BrowserTool if re.search(rf"\b{tool.value}\b", body, re.IGNORECASE)]
    assert body.strip() and not MOUNT_WORD.search(body) and named == [], body


@pytest.mark.asyncio
async def test_muse_settings_have_the_one_verified_shape(browser_api, browser_world, sandbox, browse, pack) -> None:
    # AC-26 / EC-39 / D-25: exactly {"schema_version": 1, "mcpServers"};
    # a string command with a separate args list; a remote entry with
    # streamable_http and no env; the fake (which drops all MCP on a bad
    # entry) runs both servers.
    result = await browse("muse", tools=["playwright", "jina"])
    (settings,) = sandbox.records("settings")
    assert settings["top_keys"] == ["mcpServers", "schema_version"] and settings["schema_version"] == 1 and settings["disabled"] is None
    playwright = settings["servers"]["playwright"]
    assert isinstance(playwright["command"], str) and pack.same_path(playwright["command"], browser_world.node)
    assert isinstance(playwright["args"], list) and pack.same_path(playwright["args"][0], sandbox.tool_entry("playwright"))
    assert settings["servers"]["jina"] == {"transport": "streamable_http", "url": JINA_URL}
    assert sorted(result.tool_calls, key=lambda call: call.tool.value) == [expect_call(browser_api, "jina", "read_url"), expect_call(browser_api, "playwright", "browser_navigate")]
    assert Path(settings["path"]).parts[-2:] == ("muse", "settings.json")


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_playwright_caps_add_tools_and_deny_none(browser_api, browser_world, sandbox, browse, harness) -> None:
    # AC-27 / D-24: --caps=devtools,pdf; 25 + 13 + 1 = 39 allowed and
    # nothing denied, so Muse native accepts it.
    result = await browse(harness, tools=["playwright:devtools,pdf"])
    (server,) = sandbox.starts("mcp-playwright")
    assert server["options"]["values"].get("--caps") == "devtools,pdf"
    assert result.tool_calls == (expect_call(browser_api, "playwright", "browser_navigate"),)
    if harness == "opencode":
        (tools,) = sandbox.records("mcp_tools", "opencode")
        assert len([name for name in tools["visible"] if name.startswith("vidbyte-playwright_")]) == 39
        assert [tuple(rule) for rule in tools["rules"] if rule[0].startswith("vidbyte-playwright")] == [("vidbyte-playwright_*", "allow")]
    if harness == "grok":
        assert sandbox.only_start("grok")["rules"] == {"allow": ["MCPTool(playwright__*)"], "deny": []}


@pytest.mark.asyncio
async def test_opencode_ids_are_prefixed_and_enabled_beside_a_users_own_entry(browser_api, browser_world, sandbox, browse, pack) -> None:
    # AC-28 / EC-40 / D-23: a disabled global mcp.playwright neither
    # merges into nor disables the SDK's server.
    user = {"mcp": {"playwright": {"type": "local", "command": ["user-playwright-mcp"], "enabled": False}}}
    result = await browse("opencode", tools=["playwright", "jina"], fake={"global_config": user})
    content = sandbox.only_start("opencode")["opencode_config"]["mcp"]
    assert sorted(content) == ["vidbyte-jina", "vidbyte-playwright"] and all(entry["enabled"] is True for entry in content.values())
    command = content["vidbyte-playwright"]["command"]
    assert content["vidbyte-playwright"]["type"] == "local" and pack.same_path(command[0], browser_world.node) and pack.same_path(command[1], sandbox.tool_entry("playwright"))
    assert content["vidbyte-jina"] == {"type": "remote", "url": JINA_URL, "oauth": False, "enabled": True}
    servers = {record["name"]: record for record in sandbox.records("mcp_server", "opencode")}
    assert servers["playwright"]["enabled"] is False and servers["vidbyte-playwright"]["connected"] is True
    assert expect_call(browser_api, "playwright", "browser_navigate") in result.tool_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_chrome_devtools_starts_quiet(browser_api, browser_world, sandbox, browse, harness) -> None:
    # D-21 / EC-34: --no-usage-statistics and
    # CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1 on every harness.
    result = await browse(harness, tools=["chromedevtools"])
    (server,) = sandbox.starts("mcp-chromedevtools")
    assert server["chrome_update_checks"] == "1" and "--no-usage-statistics" in server["options"]["switches"] and "--headless" in server["options"]["switches"]
    assert result.tool_calls == (expect_call(browser_api, "chromedevtools", "navigate_page"),)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["opencode", "grok"])
async def test_same_strings_compile_the_same_mount(browser_api, browser_world, sandbox, browse, pack, harness) -> None:
    # INV-11: two calls with the same tools give the same compiled
    # mount apart from the per-call folder path.
    tools = ["playwright", "firecrawl:search"]
    await browse(harness, tools=tools)
    await browse(harness, tools=tools)
    folders = [pack.call_folder(record) for record in sandbox.starts("mcp-playwright")]
    assert len(folders) == 2 and folders[0] != folders[1]
    if harness == "opencode":
        compiled = [start["opencode_config"] for start in sandbox.starts("opencode")]
    else:
        compiled = [{"servers": agent["servers"], "rules": start["rules"]} for agent, start in zip(sandbox.records("agent"), sandbox.starts("grok"))]
    assert strip_folder(compiled[0], folders[0]) == strip_folder(compiled[1], folders[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_readers_skip_vendor_names_that_fail_the_name_rule(browser_api, browser_world, sandbox, browse, harness) -> None:
    # AC-33 / EC-44 / FR-13: a call whose tool part fails
    # NATIVE_NAME_PATTERN or 64 characters is skipped; the paid run is
    # never turned into configuration.invalid_argument.
    result = await browse(harness, tools=["playwright"], fake={"bogus_calls": BOGUS_NAMES[harness]})
    assert result.tool_calls == (expect_call(browser_api, "playwright", "browser_navigate"),)


@pytest.mark.asyncio
async def test_grok_denied_call_is_a_failed_tool_call(browser_api, browser_world, sandbox, browse) -> None:
    # EC-28: Grok answers a denied tool and the turn continues.
    calls = ["firecrawl__firecrawl_search", "firecrawl__firecrawl_scrape"]
    result = await browse("grok", tools=["firecrawl:search"], fake={"browser_calls": calls})
    assert result.tool_calls == (expect_call(browser_api, "firecrawl", "firecrawl_search"), expect_call(browser_api, "firecrawl", "firecrawl_scrape", "failed"))


@pytest.mark.asyncio
async def test_grok_unlisted_server_tool_cancels_the_turn_loudly(browser_api, browser_world, sandbox, browse, check_browser_error) -> None:
    # EC-41 / EC-32 / D-8: a tool the registry does not list has neither
    # rule, so headless Grok cancels the turn: grok.run_failed naming
    # the stop reason, never a silent extra tool.
    fake = {"extra_tools": {"firecrawl": ["firecrawl_brand_new"]}, "browser_calls": ["firecrawl__firecrawl_brand_new"]}
    error = await refuse(browse, browser_api, "grok", tools=["firecrawl:search"], fake=fake)
    check_browser_error(error, harness="grok", verb="run", code="grok.run_failed", workspace=sandbox.workspace)
    assert "cancelled" in str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["opencode", "grok"])
async def test_continue_remounts_a_different_tool_set(browser_api, browser_world, sandbox, browse, pack, harness) -> None:
    # EC-30 / D-16: a continue with other tools mounts only those.
    first = await browse(harness, tools=["playwright"])
    second = await browse(harness, "continue", tools=["firecrawl"], thread_id=first.thread_id)
    assert second.thread_id == first.thread_id and second.tool_calls == (expect_call(browser_api, "firecrawl", "firecrawl_search"),)
    if harness == "opencode":
        assert sorted(sandbox.starts("opencode")[-1]["opencode_config"]["mcp"]) == ["vidbyte-firecrawl"]
    else:
        assert [entry["name"] for entry in sandbox.records("agent")[-1]["servers"]] == ["firecrawl"]
    assert json.dumps(sandbox.starts(pack.EXEC_ROLES[harness])[-1]["argv"]).count("playwright") == 0
