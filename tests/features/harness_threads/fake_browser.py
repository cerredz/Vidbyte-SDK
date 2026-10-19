"""FILE: tests/features/harness_threads/fake_browser.py

PURPOSE: The browser-tool half of the stand-ins: a fake `node` that answers `--version`, plays the npm bundled beside it (`npm-cli.js install --prefix <staging> <package>@<version>`) and runs the pinned MCP servers as stdio JSON-RPC servers; the stdio MCP client the fake harnesses use to start a compiled server and call its tools; an offline stand-in for the three remote MCP endpoints; and how each vendor reads its compiled mount (opencode `mcp`/`permission`, the Grok `--agent` file with `--allow`/`--deny`, Muse `settings.json`).
ROLE IN CODEBASE: Imported by fake_harness.py, which runs as a real child process, and by two tests that read its vendor facts (test_harness_threads_browser_fakes.py checks the fakes themselves; test_harness_threads_browser_registry.py compares the registry with the tool lists served here). A `node` stand-in on the sandbox PATH runs fake_harness.py with the scenario program "node", which hands its arguments to run_node here.
ARCHITECTURE NOTE: A cached tool entry file holds one JSON object, {"fake_mcp_server": "<tool>"}, written by the test's cache helper or by the fake npm; the fake node reads it to know which server to play, and SERVERS holds what each pinned server exposes (vendor facts §4), so the tool lists the fakes serve are the vendor's, not the SDK's registry. A server started with a profile option (`--user-data-dir`, `--userDataDir`) creates the profile folder and starts a "browser": a sleeper whose command line carries the profile path and which holds a lock file inside it, like Chrome. A short-lived spawner (SPAWNER) starts it and exits, so the browser is an orphan on every platform; on POSIX it also leads its own session, as Playwright's Chrome does (EC-21). No tree stop of the harness reaches it, and only a reap by command-line marker ends it before its limit. The mount readers apply the vendor rules spec §13 lists: opencode deep-merges the content onto a scenario's global config and the last matching permission wins, with a denied tool removed from the model's list; Grok lets deny beat allow and cancels the whole turn (exit 0) on a tool with neither rule; Muse exits 1 without `"schema_version": 1`, silently disables all MCP on a bad entry, passes its servers only seven environment names, and fails the run when any server fails to start.
FUNCTION INVENTORY: run_node dispatches the fake node; node_version, npm_install and mcp_server play one role each; server_options parses a server's options; start_browser starts the sleeper; answer builds one JSON-RPC reply; screenshot writes auto-named artifacts; StdioSession is the client side of one stdio server; RemoteSession is the offline stand-in for one remote endpoint; hold and rendezvous wait on files with a bounded limit; digest, key_digests and sanitize hide credentials; deep_merge, plan, probe_of and close_all serve the mount readers; OpencodeMount, GrokMount (with rule_matches and split_frontmatter) and MuseMount read and run one vendor's mount.
COMMON MODIFICATION PATTERNS: A new pinned tool adds one SERVERS row (its tools from a `tools/list` probe, a probe tool and the key variable it needs at start); a new remote endpoint adds one REMOTES row; a new vendor rule goes into that vendor's mount class with a scenario field to switch it on.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte or anything outside the standard library. 2. Do not contact the network: remote endpoints are answered from REMOTES. 3. Do not log a credential value; log digest(value). 4. Never use shell=True.
KNOWN EDGE CASES: A Python stand-in on win32 cannot start without SYSTEMROOT, so a fake Muse passes it to its servers beside the seven names the real Muse passes (vendor facts §1). The sleeper exits by itself after BROWSER_SECONDS so a missing reap cannot leak it for long. Screenshot names carry the pid and a counter instead of a clock, so nothing depends on wall-clock time.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §9.1, §13; docs/spec/harness-browser-tools/context/vendor-facts.md §1-§5, §9
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
NODE_VERSION = "v22.12.0"
BROWSER_SECONDS = 30
HOLD_LIMIT_SECONDS = 30.0
RENDEZVOUS_SECONDS = 10.0
CLOSE_SECONDS = 10.0
POLL_SECONDS = 0.02
NPM_FLAGS = ["install", "--no-audit", "--no-fund", "--prefix"]
PROFILE_OPTIONS = ("--user-data-dir", "--userDataDir")
OUTPUT_OPTION = "--output-dir"
CAPS_OPTION = "--caps"
SCREENSHOT_TOOLS = ("browser_take_screenshot", "take_screenshot")
TOOL_KEY_NAMES = ("FIRECRAWL_API_KEY", "EXA_API_KEY", "TAVILY_API_KEY", "BRAVE_API_KEY", "PERPLEXITY_API_KEY", "API_TOKEN", "APIFY_TOKEN", "LINKUP_API_KEY")
SLEEPER = "import os, sys, time\nlock = open(os.path.join(sys.argv[2], 'fake-browser.lock'), 'w')\ntime.sleep(float(sys.argv[3]))\n"
SPAWNER = "\n".join((
    "import subprocess, sys",
    "flags = 0x00000008 | 0x00000200 if sys.platform == 'win32' else 0",
    "child = subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, start_new_session=sys.platform != 'win32')",
    "print(child.pid, flush=True)",
    "",
))
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake screenshot\n"

PLAYWRIGHT_CORE = (
    "browser_close", "browser_resize", "browser_console_messages", "browser_handle_dialog", "browser_emulate_media", "browser_evaluate",
    "browser_file_upload", "browser_drop", "browser_find", "browser_fill_form", "browser_press_key", "browser_type", "browser_navigate",
    "browser_navigate_back", "browser_network_requests", "browser_network_request", "browser_run_code_unsafe", "browser_take_screenshot",
    "browser_snapshot", "browser_click", "browser_drag", "browser_hover", "browser_select_option", "browser_tabs", "browser_wait_for",
)
PLAYWRIGHT_CAPS = {
    "devtools": (
        "browser_resume", "browser_highlight", "browser_hide_highlight", "browser_annotate", "browser_start_recording", "browser_stop_recording",
        "browser_start_tracing", "browser_stop_tracing", "browser_start_video", "browser_stop_video", "browser_video_chapter",
        "browser_video_show_actions", "browser_video_hide_actions",
    ),
    "storage": (
        "browser_cookie_list", "browser_cookie_get", "browser_cookie_set", "browser_cookie_delete", "browser_cookie_clear", "browser_storage_state",
        "browser_set_storage_state", "browser_localstorage_list", "browser_localstorage_get", "browser_localstorage_set", "browser_localstorage_delete",
        "browser_localstorage_clear", "browser_sessionstorage_list", "browser_sessionstorage_get", "browser_sessionstorage_set",
        "browser_sessionstorage_delete", "browser_sessionstorage_clear",
    ),
    "network": ("browser_network_state_set", "browser_route", "browser_route_list", "browser_unroute"),
    "pdf": ("browser_pdf_save",),
    "vision": ("browser_mouse_move_xy", "browser_mouse_click_xy", "browser_mouse_drag_xy", "browser_mouse_down", "browser_mouse_up", "browser_mouse_wheel"),
}
# What each pinned server lists with `tools/list` (vendor facts §4), the
# tool a fake agent calls by default, and the key variable without which
# the real server exits at start (vendor facts §7 "Tools").
SERVERS: dict[str, dict[str, Any]] = {
    "playwright": {"tools": PLAYWRIGHT_CORE, "caps": PLAYWRIGHT_CAPS, "probe": "browser_navigate", "start_key": None},
    "chromedevtools": {
        "tools": (
            "click", "close_page", "drag", "emulate", "evaluate_script", "fill", "fill_form", "get_console_message", "get_css_styles",
            "get_network_request", "handle_dialog", "hover", "lighthouse_audit", "list_console_messages", "list_network_requests", "list_pages",
            "navigate_page", "new_page", "performance_analyze_insight", "performance_start_trace", "performance_stop_trace", "press_key",
            "resize_page", "screencast_start", "screencast_stop", "select_page", "take_heapsnapshot", "take_screenshot", "take_snapshot",
            "type_text", "upload_file", "wait_for",
        ),
        "probe": "navigate_page",
        "start_key": None,
    },
    "firecrawl": {
        "tools": (
            "firecrawl_scrape", "firecrawl_map", "firecrawl_search", "firecrawl_find_tools", "firecrawl_crawl", "firecrawl_check_crawl_status",
            "firecrawl_agent", "firecrawl_agent_status", "firecrawl_interact", "firecrawl_interact_stop", "firecrawl_parse", "firecrawl_monitor_create",
            "firecrawl_monitor_list", "firecrawl_monitor_get", "firecrawl_monitor_update", "firecrawl_monitor_delete", "firecrawl_monitor_run",
            "firecrawl_monitor_checks", "firecrawl_monitor_check", "firecrawl_research_search_papers", "firecrawl_research_inspect_paper",
            "firecrawl_research_related_papers", "firecrawl_research_read_paper", "firecrawl_developer_search", "firecrawl_gov_search",
            "firecrawl_credit_usage",
        ),
        "probe": "firecrawl_search",
        "start_key": None,
    },
    "exa": {"tools": ("web_search_exa", "web_fetch_exa"), "probe": "web_search_exa", "start_key": None},
    "tavily": {"tools": ("tavily_search", "tavily_extract", "tavily_crawl", "tavily_map", "tavily_research"), "probe": "tavily_search", "start_key": None},
    "brave": {
        "tools": ("brave_web_search", "brave_local_search", "brave_video_search", "brave_image_search", "brave_news_search", "brave_summarizer", "brave_llm_context", "brave_place_search"),
        "probe": "brave_web_search",
        "start_key": "BRAVE_API_KEY",
    },
    "perplexity": {"tools": ("perplexity_ask", "perplexity_research", "perplexity_reason", "perplexity_search"), "probe": "perplexity_search", "start_key": "PERPLEXITY_API_KEY"},
    "brightdata": {
        "tools": (
            "search_engine", "scrape_as_markdown", "search_engine_batch", "scrape_batch", "scrape_as_html", "extract", "discover", "list_dataset_fields",
            "search_dataset", "search_scrapers", "get_scraper_details", "run_scraper", "get_scraper_progress", "get_scraper_results", "refresh_scrapers",
            "session_stats", "chatgpt_ai_insights", "perplexity_ai_insights", "scraping_browser_navigate", "scraping_browser_go_back",
            "scraping_browser_go_forward", "scraping_browser_snapshot", "scraping_browser_click_ref", "scraping_browser_type_ref",
            "scraping_browser_screenshot", "scraping_browser_network_requests", "scraping_browser_wait_for_ref", "scraping_browser_fill_form",
            "scraping_browser_get_text", "scraping_browser_get_html", "scraping_browser_scroll", "scraping_browser_scroll_to_ref",
        ),
        "probe": "search_engine",
        "start_key": "API_TOKEN",
    },
    "apify": {
        "tools": ("search-actors", "fetch-actor-details", "call-actor", "get-actor-run", "get-dataset-items", "get-key-value-store-record", "abort-actor-run", "search-apify-docs", "fetch-apify-docs", "report-problem"),
        "probe": "search-actors",
        "start_key": "APIFY_TOKEN",
    },
    "linkup": {"tools": ("linkup-search", "linkup-research", "linkup-get-research", "linkup-fetch"), "probe": "linkup-search", "start_key": "LINKUP_API_KEY"},
}
# The remote endpoints (spec §9.1, vendor facts §4 "Remote endpoints"),
# answered offline; `bearer` means a call without an Authorization
# header is refused, as Browserbase does.
REMOTES: dict[str, dict[str, Any]] = {
    "https://mcp.browserbase.com/mcp": {"server": "browserbase", "tools": ("start", "end", "navigate", "act", "observe", "extract"), "probe": "navigate", "bearer": True},
    "https://mcp.jina.ai/v1": {
        "server": "jina",
        "tools": ("primer", "guess_datetime_url", "search_web", "search_arxiv", "search_ssrn", "search_images", "search_jina_blog", "read_url", "capture_screenshot_url", "expand_query", "sort_by_relevance", "deduplicate_strings"),
        "probe": "read_url",
        "bearer": False,
    },
    "https://search.parallel.ai/mcp": {"server": "parallel", "tools": ("web_search", "web_fetch"), "probe": "web_search", "bearer": False},
}
PROBES = {**{name: row["probe"] for name, row in SERVERS.items()}, **{row["server"]: row["probe"] for row in REMOTES.values()}}


def digest(value: str) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest(), "length": len(value)}


def key_digests(env: dict[str, str]) -> dict[str, Any]:
    return {name: (digest(env[name]) if name in env else None) for name in TOOL_KEY_NAMES}


def hold(scenario: dict[str, Any]) -> str:
    release = scenario.get("release_file")
    deadline = time.monotonic() + HOLD_LIMIT_SECONDS
    while time.monotonic() < deadline:
        if release and os.path.exists(release):
            return "released"
        time.sleep(POLL_SECONDS)
    return "limit"


def rendezvous(scenario: dict[str, Any], name: str, parties: int) -> int:
    # Waits until `parties` processes have arrived at the named meeting
    # point, or the bounded limit passes; returns how many arrived.
    folder = Path(scenario["state_dir"]) / f"rendezvous-{name}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{os.getpid()}.here").write_text("here", encoding="utf-8")
    deadline = time.monotonic() + float(scenario.get("rendezvous_seconds", RENDEZVOUS_SECONDS))
    while time.monotonic() < deadline and len(list(folder.glob("*.here"))) < parties:
        time.sleep(POLL_SECONDS)
    return len(list(folder.glob("*.here")))


def write_line(text: str) -> None:
    try:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
    except (OSError, ValueError):
        os._exit(0)


def write_err(text: str) -> None:
    try:
        sys.stderr.buffer.write((text + "\n").encode("utf-8"))
        sys.stderr.buffer.flush()
    except (OSError, ValueError):
        os._exit(0)


def run_node(scenario: dict[str, Any], args: list[str], log_class: Any) -> None:
    # The fake node: `--version`, the bundled npm, or a pinned server.
    if args == ["--version"]:
        node_version(scenario, args, log_class)
    if args and args[0].replace("\\", "/").endswith("/npm/bin/npm-cli.js"):
        npm_install(scenario, args, log_class)
    if args:
        mcp_server(scenario, args, log_class)
    log = log_class(scenario["log_dir"], "node-unknown")
    log.write("start", role="node-unknown", argv=args)
    write_err("fake node: nothing to run")
    sys.exit(9)


def node_version(scenario: dict[str, Any], args: list[str], log_class: Any) -> None:
    log = log_class(scenario["log_dir"], "node-version")
    log.write("start", role="node-version", argv=args, cwd=os.getcwd(), tool_credentials=key_digests(dict(os.environ)))
    write_line(scenario.get("node_version", NODE_VERSION))
    sys.exit(0)


def npm_install(scenario: dict[str, Any], args: list[str], log_class: Any) -> None:
    # `node <npm-cli.js> install --no-audit --no-fund --prefix <staging>
    # <package>@<version>`, exactly (spec FR-9); anything else is
    # refused.
    log = log_class(scenario["log_dir"], "npm")
    env = dict(os.environ)
    log.write("start", role="npm", argv=args, cwd=os.getcwd(), npm_cli_exists=Path(args[0]).is_file(), tool_credentials=key_digests(env))
    if not Path(args[0]).is_file():
        # Real node cannot run a script that is not there (EC-13).
        write_err(f"Error: Cannot find module '{args[0]}'")
        sys.exit(1)
    if len(args) != 7 or args[1:5] != NPM_FLAGS or not Path(args[5]).is_absolute():
        write_err(f"npm error: fake npm expects install --no-audit --no-fund --prefix <absolute staging> <package>@<version>, got {args[1:]!r}")
        sys.exit(2)
    staging, requested = Path(args[5]), args[6]
    mode = scenario.get("npm_mode", "ok")
    if mode == "fail":
        write_err(f"npm error code E404\nnpm error 404 Not Found - GET https://registry.npmjs.org/{requested} - Not found")
        sys.exit(1)
    if mode == "hold":
        log.write("held", outcome=hold(scenario))
    if mode == "rendezvous":
        log.write("met", arrived=rendezvous(scenario, "npm", 2))
    package = scenario.get("packages", {}).get(requested)
    if package is None:
        write_err(f"npm error code ETARGET\nnpm error notarget No matching version found for {requested}.")
        sys.exit(1)
    folder = staging.joinpath("node_modules", *package["package"].split("/"))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(json.dumps({"name": package["package"], "version": requested.rsplit("@", 1)[1]}), encoding="utf-8")
    if mode != "no_entry":
        entry = folder.joinpath(*package["entry"])
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(json.dumps({"fake_mcp_server": package["tool"]}), encoding="utf-8")
    log.write("installed", package=requested, staging=str(staging))
    sys.exit(0)


def server_options(arguments: list[str]) -> dict[str, Any]:
    # Joined (`--flag=value`) and separate (`--flag value`) forms, as a
    # commander-style CLI accepts them; bare switches are listed.
    options: dict[str, Any] = {"switches": [], "values": {}, "stray": []}
    index = 0
    valued = (*PROFILE_OPTIONS, OUTPUT_OPTION, CAPS_OPTION)
    while index < len(arguments):
        element = arguments[index]
        if element.startswith("--") and "=" in element:
            flag, value = element.split("=", 1)
            options["values"][flag] = value
        elif element in valued and index + 1 < len(arguments):
            options["values"][element] = arguments[index + 1]
            index += 1
        elif element.startswith("--"):
            options["switches"].append(element)
        else:
            options["stray"].append(element)
        index += 1
    return options


def start_browser(profile: Path) -> int:
    # Chrome stand-in: its command line carries the profile path and it
    # holds a lock file inside the profile. A short-lived spawner starts
    # it and exits, so its parent is gone: a tree stop of the harness
    # cannot reach it on win32, and on POSIX it leads its own session
    # (EC-21). Only a reap by command-line marker ends it early.
    profile.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-c", SPAWNER, sys.executable, "-c", SLEEPER, f"--user-data-dir={profile}", str(profile), str(BROWSER_SECONDS)]
    spawned = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=CLOSE_SECONDS, check=False)
    return int(spawned.stdout.split()[0])


def screenshot(output: str | None, count: int, log: Any) -> list[str]:
    # Auto-named files land in the output directory (vendor facts §5).
    if output is None:
        return []
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for index in range(count):
        path = folder / f"page-{os.getpid()}-{index:04d}.png"
        path.write_bytes(PNG_BYTES)
        written.append(str(path))
    log.write("artifacts", count=len(written), first=written[:1])
    return written


def answer(frame: dict[str, Any], identity: str, exposed: list[str], scenario: dict[str, Any], output: str | None, log: Any) -> dict[str, Any] | None:
    method = frame.get("method")
    if "id" not in frame:
        return None
    reply: dict[str, Any] = {"jsonrpc": "2.0", "id": frame["id"]}
    if method == "initialize":
        reply["result"] = {"protocolVersion": (frame.get("params") or {}).get("protocolVersion", PROTOCOL_VERSION), "capabilities": {"tools": {}}, "serverInfo": {"name": f"fake-{identity}", "version": "0.0.0"}}
        return reply
    if method == "tools/list":
        reply["result"] = {"tools": [{"name": name, "description": f"fake {identity} {name}", "inputSchema": {"type": "object"}} for name in exposed]}
        return reply
    if method == "tools/call":
        name = (frame.get("params") or {}).get("name")
        if name not in exposed:
            reply["error"] = {"code": -32602, "message": f"Tool not found: {name}"}
            log.write("tool_call", name=name, found=False)
            return reply
        files = screenshot(output, int(scenario.get("artifact_burst", 1)), log) if name in SCREENSHOT_TOOLS else []
        failed = name in scenario.get("failing_tools", [])
        log.write("tool_call", name=name, found=True, failed=failed, artifacts=len(files))
        reply["result"] = {"content": [{"type": "text", "text": f"fake {identity} ran {name}"}], "isError": failed}
        return reply
    reply["error"] = {"code": -32601, "message": f"method {method} not found"}
    return reply


def mcp_server(scenario: dict[str, Any], args: list[str], log_class: Any) -> None:
    # `node <absolute entry> <arguments>`: which server is played comes
    # from the entry file the cache holds.
    entry = Path(args[0])
    try:
        identity = json.loads(entry.read_text(encoding="utf-8"))["fake_mcp_server"]
    except (OSError, ValueError, KeyError, TypeError):
        log = log_class(scenario["log_dir"], "node-missing-entry")
        log.write("start", role="node-missing-entry", argv=args)
        write_err(f"Error: Cannot find module '{entry}'")
        sys.exit(1)
    env = dict(os.environ)
    row = SERVERS[identity]
    options = server_options(args[1:])
    log = log_class(scenario["log_dir"], f"mcp-{identity}")
    log.write(
        "start", role=f"mcp-{identity}", argv=args, entry=str(entry), entry_absolute=entry.is_absolute(), cwd=os.getcwd(), options=options,
        tool_credentials=key_digests(env), chrome_update_checks=env.get("CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS"), env_names=sorted(env),
    )
    if identity in scenario.get("server_fail", []):
        write_err(f"fake {identity}: failed during startup")
        sys.exit(1)
    if row["start_key"] is not None and not env.get(row["start_key"]):
        write_err(f"Error: {row['start_key']} environment variable is required")
        sys.exit(1)
    caps = [cap for cap in options["values"].get(CAPS_OPTION, "").split(",") if cap]
    exposed = [*row["tools"], *(name for cap in caps for name in row.get("caps", {}).get(cap, ())), *scenario.get("extra_tools", {}).get(identity, [])]
    profile = next((options["values"][flag] for flag in PROFILE_OPTIONS if flag in options["values"]), None)
    if profile is not None:
        log.write("browser", browser_pid=start_browser(Path(profile)), profile=profile)
    output = options["values"].get(OUTPUT_OPTION)
    stream = getattr(sys.stdin, "buffer", None)
    for raw in iter(stream.readline, b"") if stream is not None else []:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        reply = answer(frame, identity, exposed, scenario, output, log) if isinstance(frame, dict) else None
        if reply is not None:
            write_line(json.dumps(reply))
    log.write("eof")
    sys.exit(0)


class StdioSession:
    """The client side of one stdio MCP server a fake harness starts."""

    def __init__(self, name: str, command: list[str], env: dict[str, str], cwd: str | None, client: str) -> None:
        self.name = name
        self.tools: list[str] = []
        self.reason: str | None = None
        self.sequence = 0
        try:
            self.process: subprocess.Popen[bytes] | None = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, cwd=cwd)
        except OSError:
            self.process, self.reason = None, "the configured command is unavailable."
            return
        if self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": client, "version": "1.0.0"}}) is None:
            self.reason = "the transport closed unexpectedly."
            return
        self.notify("notifications/initialized")
        listed = self.request("tools/list", {})
        if listed is None:
            self.reason = "the transport closed unexpectedly."
            return
        self.tools = [tool["name"] for tool in listed.get("result", {}).get("tools", []) if isinstance(tool, dict) and isinstance(tool.get("name"), str)]

    @property
    def connected(self) -> bool:
        return self.reason is None

    def notify(self, method: str) -> None:
        self.send({"jsonrpc": "2.0", "method": method})

    def send(self, frame: dict[str, Any]) -> bool:
        if self.process is None or self.process.stdin is None:
            return False
        try:
            self.process.stdin.write((json.dumps(frame) + "\n").encode("utf-8"))
            self.process.stdin.flush()
        except OSError:
            return False
        return True

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        self.sequence += 1
        if self.process is None or self.process.stdout is None or not self.send({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}):
            return None
        line = self.process.stdout.readline()
        if not line:
            return None
        try:
            reply = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            return None
        return reply if isinstance(reply, dict) else None

    def call(self, tool: str) -> str:
        # "completed" or "failed", as the harness reports the call.
        reply = self.request("tools/call", {"name": tool, "arguments": {}})
        if reply is None or "error" in reply or reply.get("result", {}).get("isError"):
            return "failed"
        return "completed"

    def close(self) -> None:
        if self.process is None:
            return
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
            self.process.wait(timeout=CLOSE_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()


class RemoteSession:
    """An offline stand-in for one remote MCP endpoint."""

    def __init__(self, name: str, url: str, headers: dict[str, str], log: Any) -> None:
        self.name = name
        row = REMOTES.get(url)
        authorization = headers.get("Authorization")
        log.write("remote", name=name, url=url, header_names=sorted(headers), authorization=None if authorization is None else digest(authorization))
        self.tools: list[str] = []
        self.reason: str | None = None
        if row is None:
            self.reason = "the process could not be started or the server could not be reached."
        elif row["bearer"] and not authorization:
            self.reason = "the server answered 401 Unauthorized."
        else:
            self.tools = list(row["tools"])
        self.log = log

    @property
    def connected(self) -> bool:
        return self.reason is None

    def call(self, tool: str) -> str:
        self.log.write("remote_call", name=self.name, tool=tool)
        return "completed" if tool in self.tools else "failed"

    def close(self) -> None:
        return None


SECRET_MEMBERS = ("apiKey", "Authorization", *TOOL_KEY_NAMES)
PROBE_NAMES = frozenset(PROBES.values())
GROK_BUILTINS = ("read_file", "run_terminal_cmd", "search_tool", "use_tool")
MUSE_SERVER_ENV = ("HOME", "LANG", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
WINDOWS_PYTHON_ENV = ("SYSTEMROOT",)


def sanitize(node: Any) -> Any:
    # A compiled config with every credential-bearing member digested:
    # apiKey, Authorization, a key variable, or a {name, value} pair
    # whose name is a key variable.
    if isinstance(node, dict):
        secret_pair = node.get("name") in TOOL_KEY_NAMES and isinstance(node.get("value"), str)
        return {key: (digest(value) if (key in SECRET_MEMBERS or (secret_pair and key == "value")) and isinstance(value, str) else sanitize(value)) for key, value in node.items()}
    if isinstance(node, list):
        return [sanitize(value) for value in node]
    return node


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    # opencode merges OPENCODE_CONFIG_CONTENT onto the global config,
    # member by member (vendor facts §3).
    merged = dict(base)
    for key, value in overlay.items():
        merged[key] = deep_merge(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) else value
    return merged


def plan(scenario: dict[str, Any], prompt: str, default: list[str]) -> list[str]:
    # The calls the fake agent makes, in the harness's own tool names:
    # the first calls_by_prompt entry whose marker is in the prompt,
    # else browser_calls, else one probe call per mounted server.
    for marker, calls in scenario.get("calls_by_prompt", {}).items():
        if marker in prompt:
            return list(calls)
    if "browser_calls" in scenario:
        return list(scenario["browser_calls"])
    return default


def probe_of(session: Any) -> str | None:
    return next((tool for tool in session.tools if tool in PROBE_NAMES), None)


def close_all(sessions: dict[str, Any]) -> None:
    for session in sessions.values():
        session.close()


class OpencodeMount:
    """How opencode reads and runs the `mcp` and `permission` members."""

    def __init__(self, scenario: dict[str, Any], log: Any, content: dict[str, Any], env: dict[str, str], cwd: str) -> None:
        self.scenario, self.log = scenario, log
        self.sessions: dict[str, Any] = {}
        self.problem: str | None = None
        self.visible: list[str] = []
        global_config = scenario.get("global_config", {})
        merged = deep_merge(global_config.get("mcp", {}), content.get("mcp", {}))
        self.rules = [*global_config.get("permission", {}).items(), *(content.get("permission") or {}).items()]
        for name, entry in merged.items():
            command = entry.get("command") if isinstance(entry, dict) else None
            if not isinstance(entry, dict) or (entry.get("type") == "local" and not (isinstance(command, list) and command and all(isinstance(part, str) for part in command))):
                self.problem = f"Configuration is invalid at OPENCODE_CONFIG_CONTENT\n  Expected array, got {json.dumps(command)} mcp.{name}.command"
                return
        for name, entry in merged.items():
            if entry.get("enabled", True) is not True:
                log.write("mcp_server", name=name, enabled=False, connected=False)
                continue
            if entry.get("type") == "local":
                session: Any = StdioSession(name, entry["command"], {**env, **(entry.get("environment") or {})}, cwd, "opencode")
            elif entry.get("type") == "remote":
                session = RemoteSession(name, str(entry.get("url")), entry.get("headers") or {}, log)
            else:
                self.problem = f"Configuration is invalid at OPENCODE_CONFIG_CONTENT\n  Invalid input mcp.{name}.type"
                return
            self.sessions[name] = session
            log.write("mcp_server", name=name, enabled=True, connected=session.connected, reason=session.reason, tools=session.tools)
        self.visible = [f"{name}_{tool}" for name, session in self.sessions.items() if session.connected for tool in session.tools if self.permission(f"{name}_{tool}") != "deny"]
        log.write("mcp_tools", visible=self.visible, webfetch=self.permission("webfetch"), websearch=self.permission("websearch"), rules=self.rules)

    @staticmethod
    def start(scenario: dict[str, Any], log: Any, env: dict[str, str], cwd: str) -> OpencodeMount | None:
        raw = env.get("OPENCODE_CONFIG_CONTENT")
        try:
            content = json.loads(raw) if raw else None
        except ValueError:
            return None
        if not isinstance(content, dict) or "mcp" not in content:
            return None
        return OpencodeMount(scenario, log, content, env, cwd)

    def permission(self, tool: str) -> str:
        # The built-in `*` allow first; the last matching rule wins.
        decision = "allow"
        for pattern, action in self.rules:
            if fnmatch.fnmatchcase(tool, pattern):
                decision = action
        return decision

    def run(self, prompt: str) -> list[tuple[str, str]]:
        # Each planned call the model can see runs on its server; a
        # denied tool is absent from the model's list, so it is never
        # called (vendor facts §3).
        default = []
        for name, session in self.sessions.items():
            probe = probe_of(session) if session.connected else None
            if probe is not None and f"{name}_{probe}" in self.visible:
                default.append(f"{name}_{probe}")
        calls: list[tuple[str, str]] = []
        for tool in plan(self.scenario, prompt, default):
            server = max((name for name in self.sessions if tool.startswith(name + "_")), key=len, default=None)
            if tool not in self.visible or server is None:
                self.log.write("unavailable", tool=tool)
                continue
            status = self.sessions[server].call(tool[len(server) + 1 :])
            calls.append((tool, "completed" if status == "completed" else "error"))
        close_all(self.sessions)
        if calls and int(self.scenario.get("repeat_calls", 0)) > 1:
            calls = [calls[0]] * int(self.scenario["repeat_calls"])
        calls += [(tool, "error") for tool in self.scenario.get("bogus_calls", [])]
        self.log.write("browser_calls", calls=calls[:50], count=len(calls))
        return calls


def rule_matches(rule: str, tool: str) -> bool:
    # MCPTool(<server>__<glob>) matches full server__tool names.
    if rule.startswith("MCPTool(") and rule.endswith(")"):
        return fnmatch.fnmatchcase(tool, rule[len("MCPTool(") : -1])
    return False


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return None, text


class GrokMount:
    """How Grok reads a `--agent` file and applies --allow/--deny."""

    def __init__(self, scenario: dict[str, Any], log: Any, path: str, rules: dict[str, list[str]], env: dict[str, str], cwd: str) -> None:
        self.scenario, self.log = scenario, log
        self.sessions: dict[str, Any] = {}
        self.problem: str | None = None
        self.allows, self.denies = rules["allow"], rules["deny"]
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            self.problem = f"failed to read agent definition at {path}"
            return
        front, body = split_frontmatter(text)
        try:
            agent = json.loads(front) if front is not None else None
        except ValueError:
            agent = None
        if not isinstance(agent, dict) or not isinstance(agent.get("name"), str) or not isinstance(agent.get("description"), str):
            self.problem = "failed to parse agent definition: expected frontmatter with a name and a description"
            return
        servers = agent.get("mcpServers", [])
        if isinstance(servers, dict):
            self.problem = "failed to parse agent definition: mcpServers: invalid type: map, expected a sequence"
            return
        if not isinstance(servers, list) or not all(isinstance(entry, dict) and isinstance(entry.get("name"), str) for entry in servers):
            self.problem = "failed to parse agent definition: mcpServers: every entry needs a name"
            return
        secrets = sorted(name for name in (*TOOL_KEY_NAMES, "XAI_API_KEY", "GROK_CODE_XAI_API_KEY") if env.get(name) and env[name] in text)
        log.write("agent", path=path, name=agent["name"], description=agent["description"], body=body, top_keys=sorted(agent), servers=sanitize(servers), keys_in_file=secrets)
        for entry in servers:
            name = entry["name"]
            if name in scenario.get("grok_unlisted", []):
                log.write("mcp_server", name=name, connected=False, reason="still connecting after the startup grace")
                continue
            if "url" in entry:
                headers = entry.get("headers") or {}
                pairs = {pair.get("name"): pair.get("value") for pair in headers if isinstance(pair, dict)} if isinstance(headers, list) else dict(headers)
                session: Any = RemoteSession(name, str(entry["url"]), pairs, log)
            else:
                pairs_env = entry.get("env", [])
                if not isinstance(entry.get("command"), str) or not isinstance(entry.get("args"), list) or not isinstance(pairs_env, list):
                    self.problem = f"failed to parse agent definition: mcpServers: invalid entry {name}"
                    return
                session = StdioSession(name, [entry["command"], *entry["args"]], {**env, **{pair["name"]: pair["value"] for pair in pairs_env}}, cwd, f"grok-shell-{name}")
            self.sessions[name] = session
            log.write("mcp_server", name=name, connected=session.connected, reason=session.reason, tools=session.tools)

    def decision(self, tool: str) -> str:
        # Deny beats allow; a tool with neither rule asks, which a
        # headless run cannot answer (vendor facts §2, §9).
        if any(rule_matches(rule, tool) for rule in self.denies):
            return "deny"
        if any(rule_matches(rule, tool) for rule in self.allows):
            return "allow"
        return "ask"

    def events(self, prompt: str) -> tuple[list[dict[str, Any]], str]:
        connected = [f"{name}__{tool}" for name, session in self.sessions.items() if session.connected for tool in session.tools]
        events: list[dict[str, Any]] = [{"type": "available_commands", "tools": [*GROK_BUILTINS, *connected], "commands": ["help", "compact"]}]
        default = []
        for name, session in self.sessions.items():
            probe = probe_of(session) if session.connected else None
            if probe is not None and self.decision(f"{name}__{probe}") == "allow":
                default.append(f"{name}__{probe}")
        stop = "end_turn"
        calls: list[tuple[str, str]] = []
        for index, tool in enumerate(plan(self.scenario, prompt, default), 1):
            call_id = f"call_{index}"
            events.append({"type": "tool_call", "toolCallId": call_id, "title": "use_tool", "kind": "use_tool", "status": "pending", "toolName": "use_tool", "rawInput": {"tool_name": tool, "tool_input": {}}})
            events.append({"type": "tool_call_update", "toolCallId": call_id, "status": None})
            server, _, name = tool.partition("__")
            session = self.sessions.get(server)
            decision = self.decision(tool)
            if decision == "deny":
                reason, status = f'Tool `use_tool` was not executed: Denied by permission policy: deny rule on mcp matching "{tool}"', "failed"
            elif session is None or not session.connected or name not in session.tools:
                reason, status = f"Tool not found: {tool}", "failed"
            elif decision == "ask":
                events.append({"type": "tool_call_update", "toolCallId": call_id, "status": "failed", "content": [{"type": "content", "content": {"type": "text", "text": "User cancelled the execution for tool `use_tool`"}}]})
                calls.append((tool, "cancelled"))
                stop = "cancelled"
                break
            else:
                status, reason = session.call(name), None
            update: dict[str, Any] = {"type": "tool_call_update", "toolCallId": call_id, "status": status}
            if reason is None:
                update["rawOutput"] = {"type": "MCP", "tool_name": name, "server_name": server, "output": {"OkayOutput": f"fake {server} ran {name}"}}
            else:
                update["content"] = [{"type": "content", "content": {"type": "text", "text": reason}}]
            events.append(update)
            calls.append((tool, status))
        for offset, tool in enumerate(self.scenario.get("bogus_calls", []) if stop != "cancelled" else [], 1):
            call_id = f"call_bogus_{offset}"
            events.append({"type": "tool_call", "toolCallId": call_id, "title": "use_tool", "kind": "use_tool", "status": "pending", "toolName": "use_tool", "rawInput": {"tool_name": tool, "tool_input": {}}})
            events.append({"type": "tool_call_update", "toolCallId": call_id, "status": "failed", "content": [{"type": "content", "content": {"type": "text", "text": f"Tool not found: {tool}"}}]})
        if stop != "cancelled":
            events.append({"type": "tool_call", "toolCallId": "call_builtin", "title": "Read", "kind": "read", "status": "pending", "toolName": "read_file", "rawInput": {"path": "README.md"}})
            events.append({"type": "tool_call_update", "toolCallId": "call_builtin", "status": "completed", "rawOutput": {"lines": 3}})
        close_all(self.sessions)
        self.log.write("browser_calls", calls=calls, stop=stop)
        return events, stop


class MuseMount:
    """How Muse reads `$XDG_CONFIG_HOME/muse/settings.json` (vendor facts §1)."""

    def __init__(self, scenario: dict[str, Any], log: Any, path: Path, env: dict[str, str], workspace: Path | None) -> None:
        self.scenario, self.log = scenario, log
        self.sessions: dict[str, Any] = {}
        self.fatal: str | None = None
        self.failed: str | None = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.fatal = f"malformed settings file at {path}: expected value at line 1 column 1"
            return
        if not isinstance(data, dict) or "schema_version" not in data:
            self.fatal = f"malformed settings file at {path}: missing field `schema_version` at line 1 column 2"
            return
        if data["schema_version"] != 1:
            self.fatal = f"malformed settings file at {path}: unsupported schema_version {data['schema_version']!r}"
            return
        servers = data.get("mcpServers", {})
        disabled = MuseMount.bad_entry(servers)
        log.write("settings", path=str(path), top_keys=sorted(data), schema_version=data["schema_version"], servers=sanitize(servers), disabled=disabled)
        if disabled is not None:
            # The real Muse traces this only in session.jsonl and still
            # exits 0 (EC-39).
            log.write("mcp_disabled", reason=disabled)
            return
        base = {name: env[name] for name in MUSE_SERVER_ENV if name in env}
        if sys.platform == "win32":
            base.update({name: os.environ[name] for name in WINDOWS_PYTHON_ENV if name in os.environ})
        for name, entry in servers.items():
            if entry.get("enabled") is False:
                continue
            if "url" in entry:
                session: Any = RemoteSession(name, str(entry["url"]), entry.get("headers") or {}, log)
            else:
                session = StdioSession(name, [entry["command"], *entry.get("args", [])], {**base, **(entry.get("env") or {})}, None if workspace is None else str(workspace), "tbh")
            log.write("mcp_server", name=name, connected=session.connected, reason=session.reason, tools=session.tools)
            self.sessions[name] = session
            if not session.connected:
                # Every configured server is required (vendor facts §1).
                self.failed = f"invalid run configuration: Required MCP server `{name}` failed during startup: {session.reason}"
                close_all(self.sessions)
                return

    @staticmethod
    def start(scenario: dict[str, Any], log: Any, xdg: Path | None, env: dict[str, str], workspace: Path | None) -> MuseMount | None:
        if xdg is None or not (xdg / "muse" / "settings.json").is_file():
            return None
        return MuseMount(scenario, log, xdg / "muse" / "settings.json", env, workspace)

    @staticmethod
    def bad_entry(servers: Any) -> str | None:
        # Any of these silently disables ALL MCP in the real Muse.
        if not isinstance(servers, dict):
            return "mcpServers is not an object keyed by server name"
        for name, entry in servers.items():
            if not isinstance(entry, dict):
                return f"{name}: the entry is not an object"
            transport = entry.get("transport")
            if "url" in entry:
                if transport not in (None, "streamable_http") or "env" in entry or not isinstance(entry["url"], str):
                    return f"{name}: an HTTP entry needs transport streamable_http and no env"
                continue
            arguments, values = entry.get("args", []), entry.get("env", {})
            if not isinstance(entry.get("command"), str) or transport not in (None, "stdio"):
                return f"{name}: command must be one string"
            if not (isinstance(arguments, list) and all(isinstance(item, str) for item in arguments)):
                return f"{name}: args must be a list of strings"
            if not (isinstance(values, dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in values.items())):
                return f"{name}: env must map names to strings"
        return None

    def records(self, prompt: str) -> list[tuple[str, dict[str, Any]]]:
        # A proposed task (odd calls) or a side-effect intent (even
        # calls) per MCP call, then its completed or failed record
        # (spec A-1).
        default = [f"mcp__{name}__{probe}" for name, session in self.sessions.items() if (probe := probe_of(session)) is not None]
        records: list[tuple[str, dict[str, Any]]] = []
        for index, tool in enumerate(plan(self.scenario, prompt, default), 1):
            task_id = f"task-{index:04d}"
            records.append(("task.lifecycle.proposed", {"task_id": task_id, "task_kind": tool}) if index % 2 else ("side_effect_intent", {"task_id": task_id, "operation": tool}))
            parts = tool.split("__", 2)
            session = self.sessions.get(parts[1]) if len(parts) == 3 else None
            status = session.call(parts[2]) if session is not None and parts[2] in session.tools else "failed"
            records.append(("task.lifecycle.completed", {"task_id": task_id}) if status == "completed" else ("task.lifecycle.failed", {"task_id": task_id, "reason": "the tool call failed"}))
        for offset, tool in enumerate(self.scenario.get("bogus_calls", []), 1):
            task_id = f"task-bogus-{offset:04d}"
            records += [("task.lifecycle.proposed", {"task_id": task_id, "task_kind": tool}), ("task.lifecycle.failed", {"task_id": task_id, "reason": f"Tool not found: {tool}"})]
        close_all(self.sessions)
        self.log.write("browser_calls", calls=[payload for _, payload in records][:50])
        return records
