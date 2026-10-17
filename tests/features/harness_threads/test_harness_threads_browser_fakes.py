"""FILE: tests/features/harness_threads/test_harness_threads_browser_fakes.py

PURPOSE: Self-tests of the browser stand-ins (fake_harness.py with fake_browser.py), driven with hand-written mounts and no SDK code: the fake `node` plays `--version`, the bundled npm and the pinned MCP servers; and each fake vendor applies the vendor rules spec §13 lists, so a mount the SDK compiles wrongly fails against the fake as it would against the vendor: opencode's last matching permission wins and a denied tool leaves the model's list, Grok lets deny beat allow and cancels the turn (exit 0) on a tool with neither rule, and Muse exits 1 without `"schema_version": 1`, silently disables all MCP on a bad entry and fails the run when a server cannot start.
ROLE IN CODEBASE: Infrastructure checks for the other browser test files, which trust these rules. They import nothing from vidbyte, so they pass before the feature lands; a failure here means a fake broke, not the SDK.
ARCHITECTURE NOTE: Every program runs as a real child process (`python -u fake_harness.py <scenario> ...`), exactly as the SDK would start it. A server entry in a hand-written mount is that same command with the scenario program "node", so the fake vendor starts a real stdio MCP server.
FUNCTION INVENTORY: run_fake runs one stand-in to completion; node_command builds the fake node command for a cached entry; events parses JSON lines; opencode_content builds an OPENCODE_CONFIG_CONTENT; the test_* functions are one rule each.
COMMON MODIFICATION PATTERNS: A new vendor rule in fake_browser.py gets one test here that shows the rule biting.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte. 2. Do not reach the network or a real vendor CLI.
KNOWN EDGE CASES: The fake browser outlives its server on purpose (only a reap ends it early), so a test that starts one kills it itself.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §13; docs/spec/harness-browser-tools/context/vendor-facts.md §1-§3, §7, §9
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_browser_fakes.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import fake_browser
import pytest

FAKE = Path(__file__).resolve().parent / "fake_harness.py"
RUN_SECONDS = 120
BROWSER_START_SECONDS = 10.0
MODEL = "deepseek/deepseek-v4-pro"
OPENCODE_ARGS = ["run", "--format=json", f"--model={MODEL}"]
PROVIDER = {"deepseek": {"options": {"apiKey": "sk-" + "fake-provider-key-0001"}}}
JINA = "https://mcp.jina.ai/v1"
SEARCH = "firecrawl_search"
PACKAGES = {"@playwright/mcp@0.0.83": {"tool": "playwright", "package": "@playwright/mcp", "entry": ["cli.js"]}}


def run_fake(sandbox, program: str, args: list[str], *, env: dict[str, str] | None = None, stdin: str | None = None, **fields: Any) -> subprocess.CompletedProcess[bytes]:
    scenario = sandbox.scenario(program, **fields)
    return subprocess.run([sys.executable, "-u", str(FAKE), str(scenario), *args], input=None if stdin is None else stdin.encode("utf-8"), env={**os.environ, **(env or {})}, capture_output=True, timeout=RUN_SECONDS, check=False)


def node_command(sandbox, tool: str, *options: str, **fields: Any) -> list[str]:
    # A cached entry for `tool` and the fake node that serves it.
    entry = sandbox.root / "cache" / tool / "index.js"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(json.dumps({"fake_mcp_server": tool}), encoding="utf-8")
    return [sys.executable, "-u", str(FAKE), str(sandbox.scenario("node", **fields)), str(entry), *options]


def events(stdout: bytes) -> list[dict[str, Any]]:
    found = []
    for line in stdout.decode("utf-8").splitlines():
        if line.startswith("{"):
            found.append(json.loads(line))
    return found


def opencode_content(command: list[str], permission: dict[str, str]) -> str:
    return json.dumps({"provider": PROVIDER, "mcp": {"vidbyte-firecrawl": {"type": "local", "command": command, "environment": {}, "enabled": True}}, "permission": permission})


def test_fake_node_answers_version_and_plays_the_bundled_npm(sandbox) -> None:
    # FR-8 / FR-9: `node --version`; `node <npm-cli.js> install
    # --no-audit --no-fund --prefix <staging> <package>@<version>`
    # writes the entry the cache verifies; any other npm command fails,
    # and so does a missing npm-cli.js, as real node does (EC-13).
    version = run_fake(sandbox, "node", ["--version"], node_version="v22.11.0")
    assert version.returncode == 0 and version.stdout.decode().strip() == "v22.11.0"
    npm = str(sandbox.root / "node" / "node_modules" / "npm" / "bin" / "npm-cli.js")
    staging = sandbox.root / "staging"
    absent = run_fake(sandbox, "node", [npm, "install", "--no-audit", "--no-fund", "--prefix", str(staging), "@playwright/mcp@0.0.83"], packages=PACKAGES)
    assert absent.returncode == 1 and b"Cannot find module" in absent.stderr and not staging.exists()
    Path(npm).parent.mkdir(parents=True)
    Path(npm).write_text("// fake npm-cli.js\n", encoding="utf-8")
    installed = run_fake(sandbox, "node", [npm, "install", "--no-audit", "--no-fund", "--prefix", str(staging), "@playwright/mcp@0.0.83"], packages=PACKAGES)
    assert installed.returncode == 0, installed.stderr
    assert json.loads((staging / "node_modules" / "@playwright" / "mcp" / "cli.js").read_text(encoding="utf-8")) == {"fake_mcp_server": "playwright"}
    floating = run_fake(sandbox, "node", [npm, "install", "--prefix", str(staging), "@playwright/mcp@latest"], packages=PACKAGES)
    assert floating.returncode == 2
    failed = run_fake(sandbox, "node", [npm, "install", "--no-audit", "--no-fund", "--prefix", str(staging), "@playwright/mcp@0.0.83"], packages=PACKAGES, npm_mode="fail")
    assert failed.returncode == 1 and b"E404" in failed.stderr


@pytest.mark.asyncio
async def test_fake_server_lists_its_tools_writes_artifacts_and_leaves_a_marked_browser(sandbox, pack, wait_until) -> None:
    # Vendor facts §4/§5: the pinned server's tools plus its --caps
    # groups; auto-named screenshots in --output-dir; a browser whose
    # command line carries the profile and which outlives the server.
    profile, output = sandbox.tmp / "call" / "profiles" / "playwright", sandbox.tmp / "call" / "artifacts"
    command = node_command(sandbox, "playwright", "--headless", f"--user-data-dir={profile}", f"--output-dir={output}", "--caps=devtools,pdf")
    session = fake_browser.StdioSession("playwright", command, dict(os.environ), str(sandbox.workspace), "self-test")
    try:
        assert session.connected, session.reason
        assert len(session.tools) == 25 + 13 + 1 and "browser_pdf_save" in session.tools and "browser_mouse_click_xy" not in session.tools
        assert session.call("browser_take_screenshot") == "completed"
        assert session.call("browser_no_such_tool") == "failed"
    finally:
        session.close()
    assert [path.suffix for path in output.iterdir()] == [".png"]
    browsers = sandbox.browser_pids()
    assert len(browsers) == 1
    assert await wait_until(lambda: (profile / "fake-browser.lock").is_file(), BROWSER_START_SECONDS)
    try:
        assert pack.process_alive(browsers[0]), "the fake browser must outlive its server, as Chrome does"
    finally:
        os.kill(browsers[0], signal.SIGTERM)


def test_fake_server_without_its_start_key_fails_to_start(sandbox) -> None:
    # Vendor facts §7: brave exits at start without BRAVE_API_KEY.
    environment = {name: value for name, value in os.environ.items() if name != "BRAVE_API_KEY"}
    session = fake_browser.StdioSession("brave", node_command(sandbox, "brave"), environment, None, "self-test")
    session.close()
    assert not session.connected
    keyed = fake_browser.StdioSession("brave", node_command(sandbox, "brave"), {**environment, "BRAVE_API_KEY": "BSA" + "k3v9Qx7Lm2Np8Rt4" + "Wz6Yb1Cd5Fg0Hj"}, None, "self-test")
    keyed.close()
    assert keyed.connected and "brave_web_search" in keyed.tools


@pytest.mark.parametrize(("permission", "visible"), [
    ({"vidbyte-firecrawl_*": "deny", f"vidbyte-firecrawl_{SEARCH}": "allow"}, [f"vidbyte-firecrawl_{SEARCH}"]),
    ({f"vidbyte-firecrawl_{SEARCH}": "allow", "vidbyte-firecrawl_*": "deny"}, []),
])
def test_fake_opencode_applies_the_last_matching_permission(sandbox, permission, visible) -> None:
    # Vendor facts §3/§9 (A-17): last match wins and a denied tool
    # leaves the model's list, so allow-then-deny hides every tool.
    rules = {**permission, "webfetch": "deny", "websearch": "deny"}
    content = opencode_content(node_command(sandbox, "firecrawl"), rules)
    finished = run_fake(sandbox, "opencode", OPENCODE_ARGS, env={"OPENCODE_CONFIG_CONTENT": content}, stdin="Find the docs.")
    assert finished.returncode == 0, finished.stderr
    tools = sandbox.records("mcp_tools", "opencode")
    assert len(tools) == 1 and tools[0]["visible"] == visible
    assert (tools[0]["webfetch"], tools[0]["websearch"]) == ("deny", "deny")
    used = [event["part"]["tool"] for event in events(finished.stdout) if event.get("type") == "tool_use" and event["part"].get("tool", "").startswith("vidbyte-")]
    assert used == visible


def test_fake_opencode_merges_a_global_entry_of_the_same_id(sandbox) -> None:
    # Vendor facts §3 (D-23): a global mcp entry with the same id is
    # merged member by member, so its "enabled": false survives unless
    # the content sets "enabled" itself.
    command = node_command(sandbox, "firecrawl")
    content = json.dumps({"provider": PROVIDER, "mcp": {"vidbyte-firecrawl": {"type": "local", "command": command}}, "permission": {"vidbyte-firecrawl_*": "allow"}})
    finished = run_fake(sandbox, "opencode", OPENCODE_ARGS, env={"OPENCODE_CONFIG_CONTENT": content}, stdin="Find the docs.", global_config={"mcp": {"vidbyte-firecrawl": {"enabled": False}}})
    assert finished.returncode == 0, finished.stderr
    assert [record["enabled"] for record in sandbox.records("mcp_server", "opencode")] == [False]


def test_fake_grok_lets_deny_beat_allow_and_cancels_a_tool_with_no_rule(sandbox) -> None:
    # Vendor facts §2/§9 (A-18): an exact deny beats an allow and the
    # turn continues; a mounted tool with neither rule cancels the turn
    # (stopReason cancelled, exit 0).
    agent = sandbox.tmp / "call" / "agent.md"
    agent.parent.mkdir(parents=True)
    servers = [{"name": "firecrawl", "command": sys.executable, "args": node_command(sandbox, "firecrawl")[1:], "env": []}]
    agent.write_text("---\n" + json.dumps({"name": "self-test", "description": "Self test.", "mcpServers": servers}) + "\n---\nBe brief.\n", encoding="utf-8")
    argv = [
        "--single=Find the docs.", "--output-format=streaming-json", f"--cwd={sandbox.workspace}", f"--agent={agent}", "--disable-web-search",
        f"--allow=MCPTool(firecrawl__{SEARCH})", "--allow=MCPTool(firecrawl__firecrawl_scrape)", "--deny=MCPTool(firecrawl__firecrawl_scrape)",
    ]
    calls = [f"firecrawl__{SEARCH}", "firecrawl__firecrawl_scrape", "firecrawl__firecrawl_map"]
    finished = run_fake(sandbox, "grok", argv, env={"GROK_HOME": str(sandbox.home / "grok"), "XAI_API_KEY": "xai-" + "fake-key-0001"}, browser_calls=calls)
    assert finished.returncode == 0, finished.stderr
    stream = events(finished.stdout)
    assert stream[0]["type"] == "available_commands" and f"firecrawl__{SEARCH}" in stream[0]["tools"]
    finals = {event["toolCallId"]: event for event in stream if event["type"] == "tool_call_update" and event["status"] is not None}
    assert [finals[f"call_{index}"]["status"] for index in (1, 2, 3)] == ["completed", "failed", "failed"]
    assert "Denied by permission policy" in json.dumps(finals["call_2"]) and "cancelled" in json.dumps(finals["call_3"])
    assert stream[-1]["type"] == "end" and stream[-1]["stopReason"] == "cancelled"


def test_fake_grok_refuses_a_map_of_servers_and_mounts_a_url_only_entry(sandbox) -> None:
    # Vendor facts §9: mcpServers is a sequence; a url-only entry is a
    # keyless remote server.
    home = {"GROK_HOME": str(sandbox.home / "grok"), "XAI_API_KEY": "xai-" + "fake-key-0001"}
    agent = sandbox.tmp / "agent.md"
    agent.write_text("---\n" + json.dumps({"name": "a", "description": "b", "mcpServers": {"jina": {"url": JINA}}}) + "\n---\nBe brief.\n", encoding="utf-8")
    common = ["--single=Read it.", "--output-format=streaming-json", f"--cwd={sandbox.workspace}", f"--agent={agent}"]
    refused = run_fake(sandbox, "grok", common, env=home)
    assert refused.returncode == 1 and b"expected a sequence" in refused.stderr
    agent.write_text("---\n" + json.dumps({"name": "a", "description": "b", "mcpServers": [{"name": "jina", "url": JINA}]}) + "\n---\nBe brief.\n", encoding="utf-8")
    mounted = run_fake(sandbox, "grok", [*common, "--allow=MCPTool(jina__*)"], env=home)
    assert mounted.returncode == 0, mounted.stderr
    assert [record["tool"] for record in sandbox.records("remote_call")] == ["read_url"]


def write_settings(folder: Path, data: Any) -> None:
    (folder / "muse").mkdir(parents=True, exist_ok=True)
    (folder / "muse" / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def run_muse(sandbox, folder: Path, **fields: Any) -> subprocess.CompletedProcess[bytes]:
    argv = ["exec", "--json", "--provider", "meta", "--workspace", str(sandbox.workspace), "--user-input-auto-resolve", "--disable-web-tools", "--", "Read it."]
    return run_fake(sandbox, "muse", argv, env={"XDG_CONFIG_HOME": str(folder), "META_API_KEY": "meta-fake-key-0001"}, **fields)


def test_fake_muse_needs_schema_version_and_silently_drops_mcp_on_a_bad_entry(sandbox) -> None:
    # Vendor facts §1 (AC-26, EC-39): no schema_version exits 1; a
    # command list, another transport, or env on an HTTP entry disables
    # every server while the run still exits 0.
    folder = sandbox.tmp / "muse-config"
    write_settings(folder, {"mcpServers": {"jina": {"transport": "streamable_http", "url": JINA}}})
    assert run_muse(sandbox, folder).returncode == 1
    for bad in ({"transport": "http", "url": JINA}, {"transport": "streamable_http", "url": JINA, "env": {}}):
        write_settings(folder, {"schema_version": 1, "mcpServers": {"jina": bad}})
        finished = run_muse(sandbox, folder)
        assert finished.returncode == 0 and b"mcp__jina__" not in finished.stdout
    write_settings(folder, {"schema_version": 1, "mcpServers": {"firecrawl": {"command": node_command(sandbox, "firecrawl"), "args": []}}})
    assert run_muse(sandbox, folder).returncode == 0
    assert len(sandbox.records("mcp_disabled")) == 3
    write_settings(folder, {"schema_version": 1, "mcpServers": {"jina": {"transport": "streamable_http", "url": JINA}}})
    finished = run_muse(sandbox, folder)
    assert finished.returncode == 0 and b"mcp__jina__read_url" in finished.stdout


def test_fake_muse_fails_the_run_when_a_server_cannot_start(sandbox) -> None:
    # Vendor facts §1 (EC-18): every configured server is required.
    folder = sandbox.tmp / "muse-config"
    command = node_command(sandbox, "firecrawl", server_fail=["firecrawl"])
    write_settings(folder, {"schema_version": 1, "mcpServers": {"firecrawl": {"command": command[0], "args": command[1:]}}})
    finished = run_muse(sandbox, folder)
    assert finished.returncode == 1
    terminal = [record for record in events(finished.stdout) if record.get("payload_type") == "run.terminal.failed"]
    assert len(terminal) == 1 and "Required MCP server `firecrawl` failed during startup" in terminal[0]["payload"]["reason"]
