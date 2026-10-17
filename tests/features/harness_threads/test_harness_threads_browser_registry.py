"""FILE: tests/features/harness_threads/test_harness_threads_browser_registry.py

PURPOSE: Tool strings to pinned selections (docs/spec/harness-browser-tools/spec.md §9.1, FR-4 to FR-7): the registry rows against vendor facts §4 (AC-23), the selection rules with additive server-flag capabilities and fail-closed narrowing (D-24, INV-11), and every refusal of `tools` and `tool_keys` naming only an index, a registry name or a position, never the caller's text (AC-4, AC-5, AC-8, AC-25, AC-29, AC-30, EC-1 to EC-7, D-28), both at the record and registry level and through the public functions before any process or file (INV-9).
ROLE IN CODEBASE: Start here when a registry row, a capability, a refusal text or the BrowserToolRequest checks change.
ARCHITECTURE NOTE: The vendor's own tool lists come from fake_browser.py (the fake servers serve exactly those names), so the registry is checked against vendor facts, not against itself. Record and registry refusals are read through the ConfigurationError they raise (`details["field"]`); the public-function refusals are read through check_browser_error, which also proves no fragment of a key-shaped value reaches any error surface.
FUNCTION INVENTORY: request and select build a request and resolve it; refused returns the ConfigurationError a request raises; assert_unquoted proves no 8-character fragment of a value is in an error; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A pin bump in spec §9.1 changes STDIO_ROWS (and BROWSER_PACKAGES in conftest.py); a new tool adds one STDIO_ROWS or REMOTE_ROWS row and its CAPABILITIES entry.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte at module level. 2. Do not use a real key; the fake keys are shaped like real ones so a leak is visible.
KNOWN EDGE CASES: The spec gives stdio entries relative to node_modules/<package>/ (§9.1 seed table) and also says "relative to the install prefix" (§9.1 record rules), so only the trailing entry parts are pinned. The Playwright split of the 41 capability tools into devtools/storage/network/pdf/vision is pinned by counts and by the union only; vendor facts §4 gives the counts, not the per-group names.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §6.2 AC-4, AC-5, AC-8, AC-23, AC-25, AC-29, AC-30, §6.3 EC-1 to EC-7, §8.1 D-24, D-28, §9.1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_browser_registry.py
"""

from __future__ import annotations

import json
import re

import fake_browser as vendor
import pytest

FIRECRAWL_KEY = "fc-" + "3f9a2b7c4d1e8f6a" + "5b0c9d2e7f1a4b8c"
BRAVE_KEY = "BSA" + "k3v9Qx7Lm2Np8Rt4" + "Wz6Yb1Cd5Fg0Hj"
TAVILY_KEY = "tvly-dev-" + "8Hq2Lm4Np6Rt8Vx0" + "Zb2Cd4Fg6Hj8Kl0"
BRIGHTDATA_KEY = "4c7e9a1b3d5f7a9c" + "1e3b5d7f9a1c3e5b" + "7d9f1a3c5e7b9d1f" + "3a5c7e9b1d3f5a7c"
MOUNTABLE = ("playwright", "chromedevtools", "firecrawl", "exa", "tavily", "brave", "perplexity", "brightdata", "apify", "linkup", "browserbase", "jina", "parallel")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Spec §9.1 seed registry, stdio rows: package, version, trailing entry
# parts, key rule, key variable, arguments, profile/output/caps options,
# needs Chrome, non-secret environment, default capabilities.
STDIO_ROWS = {
    "playwright": ("@playwright/mcp", "0.0.83", ("cli.js",), "none", None, ("--headless",), "--user-data-dir", "--output-dir", "--caps", True, {}, ("core",)),
    "chromedevtools": ("chrome-devtools-mcp", "1.11.0", ("build", "src", "bin", "chrome-devtools-mcp.js"), "none", None, ("--headless", "--no-usage-statistics"), "--userDataDir", None, None, True, {"CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS": "1"}, ("all",)),
    "firecrawl": ("firecrawl-mcp", "3.30.2", ("dist", "index.js"), "optional", "FIRECRAWL_API_KEY", (), None, None, None, False, {}, ("all",)),
    "exa": ("exa-mcp-server", "3.4.2", ("dist", "stdio.cjs"), "optional", "EXA_API_KEY", (), None, None, None, False, {}, ("all",)),
    "tavily": ("tavily-mcp", "0.2.22", ("build", "index.js"), "required", "TAVILY_API_KEY", (), None, None, None, False, {}, ("all",)),
    "brave": ("@brave/brave-search-mcp-server", "2.1.4", ("dist", "index.js"), "required", "BRAVE_API_KEY", (), None, None, None, False, {}, ("all",)),
    "perplexity": ("@perplexity-ai/mcp-server", "1.3.0", ("dist", "index.js"), "required", "PERPLEXITY_API_KEY", (), None, None, None, False, {}, ("all",)),
    "brightdata": ("@brightdata/mcp", "3.1.0", ("server.js",), "required", "API_TOKEN", (), None, None, None, False, {}, ("all",)),
    "apify": ("@apify/actors-mcp-server", "0.18.4", ("dist", "stdio.js"), "required", "APIFY_TOKEN", (), None, None, None, False, {}, ("all",)),
    "linkup": ("linkup-mcp-server", "3.4.0", ("bin", "linkup-mcp-server.js"), "required", "LINKUP_API_KEY", (), None, None, None, False, {}, ("all",)),
}
REMOTE_ROWS = {"browserbase": ("https://mcp.browserbase.com/mcp", "required"), "jina": ("https://mcp.jina.ai/v1", "optional"), "parallel": ("https://search.parallel.ai/mcp", "optional")}
REMOTE_TOOLS = {row["server"]: set(row["tools"]) for row in vendor.REMOTES.values()}
SCRAPING_BROWSER = {name for name in vendor.SERVERS["brightdata"]["tools"] if name.startswith("scraping_browser_")}
CAPABILITIES = {
    "chromedevtools": {"all": set(vendor.SERVERS["chromedevtools"]["tools"])},
    "firecrawl": {
        "all": set(vendor.SERVERS["firecrawl"]["tools"]), "search": {"firecrawl_search"}, "scrape": {"firecrawl_scrape"}, "map": {"firecrawl_map"},
        "crawl": {"firecrawl_crawl", "firecrawl_check_crawl_status"}, "interact": {"firecrawl_interact", "firecrawl_interact_stop"},
    },
    "exa": {"all": {"web_search_exa", "web_fetch_exa"}, "search": {"web_search_exa"}, "fetch": {"web_fetch_exa"}},
    "tavily": {"all": set(vendor.SERVERS["tavily"]["tools"]), "search": {"tavily_search"}, "extract": {"tavily_extract"}, "crawl": {"tavily_crawl"}, "map": {"tavily_map"}, "research": {"tavily_research"}},
    "brave": {"all": set(vendor.SERVERS["brave"]["tools"]), "search": {"brave_web_search"}},
    "perplexity": {"all": set(vendor.SERVERS["perplexity"]["tools"]), "search": {"perplexity_search"}, "research": {"perplexity_research"}},
    "brightdata": {"all": set(vendor.SERVERS["brightdata"]["tools"]), "search": {"search_engine", "search_engine_batch"}, "scrape": {"scrape_as_markdown", "scrape_as_html", "scrape_batch"}, "browser": SCRAPING_BROWSER},
    "apify": {"all": set(vendor.SERVERS["apify"]["tools"])},
    "linkup": {"all": set(vendor.SERVERS["linkup"]["tools"]), "search": {"linkup-search"}, "fetch": {"linkup-fetch"}, "research": {"linkup-research", "linkup-get-research"}},
    "browserbase": {"all": REMOTE_TOOLS["browserbase"]},
    "jina": {"all": REMOTE_TOOLS["jina"], "search": {"search_web", "search_arxiv", "search_ssrn", "search_images", "search_jina_blog"}, "fetch": {"read_url", "capture_screenshot_url"}},
    "parallel": {"all": {"web_search", "web_fetch"}, "search": {"web_search"}, "fetch": {"web_fetch"}},
}
TOOL_COUNTS = {"chromedevtools": 32, "firecrawl": 26, "tavily": 5, "brave": 8, "perplexity": 4, "brightdata": 32, "apify": 10, "linkup": 4, "jina": 12}
PLAYWRIGHT_CAP_COUNTS = {"devtools": 13, "storage": 17, "network": 4, "pdf": 1, "vision": 6}
EXCLUSION_WORDS = {"browserstack": "credential", "searxng": "instance", "wdio": "22.12", "fetch": "uvx", "duckduckgo": "uvx", "crawl4ai": "Docker", "kernel": "OAuth", "cloudflare": "OAuth", "puppeteer": "rchived", "hyperbrowser": "nmaintained"}
SHARED_REASONS = (("fetch", "duckduckgo"), ("agentbrowser", "playwrightcli", "midscene", "devbrowser"), ("kernel", "cloudflare"), ("scrapling", "steel", "browserless"))
HOSTS_TEXT = "hosts are not supported in this release"


def request(lib, tools, keys=None):
    return lib.BrowserToolRequest(tools=tools, tool_keys=keys)


def select(lib, *tools, keys=None):
    return lib.BrowserToolRegistry.select(request(lib, list(tools), keys))


def refused(lib, tools, keys=None):
    with pytest.raises(lib.ConfigurationError) as caught:
        lib.BrowserToolRegistry.select(request(lib, tools, keys))
    return caught.value


def assert_unquoted(error, value: str, pack) -> None:
    # D-28: no 8-character run of the caller's text in the message, the
    # repr or any detail.
    surfaces = {"str": str(error), "repr": repr(error), "details": json.dumps(getattr(error, "details", {}), default=str)}
    for surface, text in surfaces.items():
        leaked = [piece for piece in pack.fragments(value) if piece in text]
        assert leaked == [], f"{surface} quotes the refused value: {leaked[:3]}"


def test_stdio_rows_pin_package_version_entry_key_and_options(browser_lib) -> None:
    # AC-23 / FR-6 / §9.1: exact version, entry, key rule, arguments,
    # options and non-secret environment for every stdio row.
    lib = browser_lib
    enums = lib.browser_enums
    for tool, (package, version, entry, rule, variable, arguments, profile, output, caps, chrome, environment, defaults) in STDIO_ROWS.items():
        row = lib.BrowserToolRegistry.definition(enums.BrowserTool(tool))
        assert row.tool is enums.BrowserTool(tool) and row.transport is enums.BrowserToolTransport.STDIO, tool
        assert (row.package, row.version, row.url) == (package, version, None) and VERSION.fullmatch(row.version), tool
        assert tuple(row.entry)[-len(entry) :] == entry, f"{tool}: entry {row.entry}"
        assert row.key_rule is enums.BrowserKeyRequirement(rule) and (row.key_variable is None if variable is None else row.key_variable == enums.BrowserToolVariable(variable)), tool
        assert tuple(row.arguments) == arguments and (row.profile_option, row.output_option, row.caps_option, row.needs_chrome) == (profile, output, caps, chrome), tool
        assert dict(row.environment) == environment, tool
        assert tuple(capability.value for capability in row.default_capabilities) == defaults, tool


def test_remote_rows_pin_https_urls_and_bearer_keys(browser_lib) -> None:
    # AC-23 / §9.1: an https URL, no package, a key only as a Bearer
    # header (no key variable).
    lib = browser_lib
    enums = lib.browser_enums
    for tool, (url, rule) in REMOTE_ROWS.items():
        row = lib.BrowserToolRegistry.definition(enums.BrowserTool(tool))
        assert row.transport is enums.BrowserToolTransport.REMOTE and row.url == url and url.startswith("https://"), tool
        assert (row.package, row.version, tuple(row.entry), row.key_variable, row.needs_chrome) == (None, None, (), None, False), tool
        assert row.key_rule is enums.BrowserKeyRequirement(rule), tool
        assert tuple(capability.value for capability in row.default_capabilities) == ("all",), tool


def test_capability_tool_names_match_vendor_facts(browser_lib, pack) -> None:
    # AC-23 / vendor facts §4: each capability's exact tools, unique,
    # NATIVE_NAME_PATTERN within 64; only Playwright's groups carry a
    # server value.
    lib = browser_lib
    for tool in MOUNTABLE:
        row = lib.BrowserToolRegistry.definition(lib.BrowserTool(tool))
        groups = {capability.name.value: capability for capability in row.capabilities}
        assert len(groups) == len(row.capabilities), f"{tool}: capability names repeat"
        for capability in row.capabilities:
            assert capability.tools and len(set(capability.tools)) == len(capability.tools), f"{tool}:{capability.name}"
            assert all(NAME.fullmatch(name) and len(name) <= 64 for name in capability.tools), f"{tool}:{capability.name}"
        if tool == "playwright":
            continue
        assert {name: set(group.tools) for name, group in groups.items()} == CAPABILITIES[tool], tool
        assert all(group.server_value is None for group in groups.values()), tool
        if tool in TOOL_COUNTS:
            assert len(groups["all"].tools) == TOOL_COUNTS[tool], tool


def test_playwright_core_and_server_flag_groups_match_vendor_facts(browser_lib) -> None:
    # AC-23 / D-24: core is the 25 no-caps tools; each other group is
    # turned on by --caps=<its name> and adds its own tools.
    lib = browser_lib
    row = lib.BrowserToolRegistry.definition(lib.BrowserTool.PLAYWRIGHT)
    groups = {capability.name.value: capability for capability in row.capabilities}
    assert set(groups) == {"core", *PLAYWRIGHT_CAP_COUNTS}
    assert set(groups["core"].tools) == set(vendor.PLAYWRIGHT_CORE) and len(groups["core"].tools) == 25 and groups["core"].server_value is None
    assert {name: len(groups[name].tools) for name in PLAYWRIGHT_CAP_COUNTS} == PLAYWRIGHT_CAP_COUNTS
    assert all(groups[name].server_value == name for name in PLAYWRIGHT_CAP_COUNTS)
    added = [name for group in PLAYWRIGHT_CAP_COUNTS for name in groups[group].tools]
    assert set(added) == {name for names in vendor.PLAYWRIGHT_CAPS.values() for name in names} and len(added) == len(set(added)) == 41
    assert not set(added) & set(groups["core"].tools)


def test_every_exclusion_has_its_recorded_reason(browser_lib) -> None:
    # FR-6 / AC-23: 18 named exclusions, each with its §9.1 reason.
    reasons = browser_lib.browser_constants.BROWSER_TOOL_EXCLUSION_REASONS
    exclusion = browser_lib.browser_enums.BrowserToolExclusion
    for name, word in EXCLUSION_WORDS.items():
        assert word.lower() in reasons[exclusion(name)].lower(), name
    for group in SHARED_REASONS:
        assert len({reasons[exclusion(name)] for name in group}) == 1, f"§9.1 gives {group} one reason"


def test_selection_defaults_additive_caps_and_fail_closed_narrowing(browser_lib) -> None:
    # §9.1 / D-24 / FR-5 / FR-12: defaults apply; a server-flag group
    # adds to the defaults and denies nothing; a base group narrows and
    # denies the rest of the exposed tools in registry order.
    lib = browser_lib
    core = lib.BrowserToolRegistry.definition(lib.BrowserTool.PLAYWRIGHT)
    groups = {capability.name.value: tuple(capability.tools) for capability in core.capabilities}
    (plain,) = select(lib, "playwright")
    assert (plain.allowed, plain.denied, tuple(plain.server_capabilities)) == (groups["core"], (), ())
    (devtools,) = select(lib, "playwright:devtools")
    assert len(devtools.allowed) == 38 and set(devtools.allowed) == {*groups["core"], *groups["devtools"]} and devtools.denied == ()
    assert tuple(devtools.server_capabilities) == ("devtools",)
    for item in ("playwright:devtools,pdf", "playwright:pdf,devtools"):
        (both,) = select(lib, item)
        assert len(both.allowed) == 39 and both.denied == () and tuple(both.server_capabilities) == ("devtools", "pdf"), item
    everything = next(tuple(capability.tools) for capability in lib.BrowserToolRegistry.definition(lib.BrowserTool.FIRECRAWL).capabilities if capability.name.value == "all")
    (search,) = select(lib, "firecrawl:search")
    assert search.allowed == ("firecrawl_search",) and search.denied == tuple(name for name in everything if name != "firecrawl_search") and len(search.denied) == 25
    (two,) = select(lib, "FIRECRAWL:Search,SCRAPE")
    assert set(two.allowed) == {"firecrawl_search", "firecrawl_scrape"} and len(two.denied) == 24
    (whole,) = select(lib, "firecrawl")
    assert set(whole.allowed) == set(everything) and whole.denied == ()


def test_selection_keeps_request_order_carries_keys_hidden_and_is_deterministic(browser_lib) -> None:
    # INV-11 / D-28: the same strings give the same selections; a key
    # rides on its selection and never shows in a repr.
    lib = browser_lib
    tools = ["jina", "brightdata:browser", "playwright", "firecrawl:search"]
    keys = {"brightdata": BRIGHTDATA_KEY, "firecrawl": FIRECRAWL_KEY}
    first = lib.BrowserToolRegistry.select(request(lib, tools, keys))
    assert first == lib.BrowserToolRegistry.select(request(lib, list(tools), dict(keys)))
    assert [selection.definition.tool.value for selection in first] == ["jina", "brightdata", "playwright", "firecrawl"]
    assert [selection.key for selection in first] == [None, BRIGHTDATA_KEY, None, FIRECRAWL_KEY]
    assert len(first[1].allowed) == 14 and len(first[1].denied) == 18
    for text in (repr(first), repr(request(lib, tools, keys))):
        assert BRIGHTDATA_KEY not in text and FIRECRAWL_KEY not in text


def test_request_accepts_the_boundaries(browser_lib) -> None:
    # FR-4 / EC-2 / EC-7: 8 items, a 128-character grammar item at the
    # record, a 4,096-character key.
    lib = browser_lib
    cap = lib.browser_constants.BROWSER_TOOLS_MAX_PER_CALL
    eight = ["playwright", "chromedevtools", "firecrawl", "exa", "jina", "parallel", "tavily", "brave"]
    assert len(eight) == cap
    assert len(select(lib, *eight, keys={"tavily": TAVILY_KEY, "brave": BRAVE_KEY})) == cap
    assert request(lib, ["a" * 128]).tools == ("a" * 128,)
    (row,) = select(lib, "firecrawl", keys={"firecrawl": "k" * 4096})
    assert row.key == "k" * 4096


@pytest.mark.parametrize(("tools", "field"), [
    ("playwright", "tools"), ([], "tools"), (["jina"] * 9, "tools"), (["playwright\n"], "tools[0]"), (["p" * 129], "tools[0]"),
    (["jina", "play wright"], "tools[1]"), (["playwright:"], "tools[0]"), ([f"{FIRECRAWL_KEY}\n"], "tools[0]"),
])
def test_request_record_refuses_bad_tools_without_quoting(browser_lib, pack, tools, field) -> None:
    # EC-1 to EC-3 / AC-25 / D-28: refused when the record is built,
    # before any key is registered; never split into characters, never
    # quoted.
    with pytest.raises(browser_lib.ConfigurationError) as caught:
        request(browser_lib, tools)
    assert caught.value.details["field"] == field
    for item in ([tools] if isinstance(tools, str) else tools):
        if len(item.strip()) >= 8:
            assert_unquoted(caught.value, item.strip(), pack)


@pytest.mark.parametrize(("keys", "field", "value"), [
    ({"firecrawl": f"{FIRECRAWL_KEY}\n"}, "tool_keys[firecrawl]", FIRECRAWL_KEY), ({"firecrawl": ""}, "tool_keys[firecrawl]", None),
    ({"firecrawl": "fc-" + "3f9a2b7c 4d1e8f6a5b0c"}, "tool_keys[firecrawl]", "4d1e8f6a5b0c"), ({"firecrawl": "k" * 4097}, "tool_keys[firecrawl]", None),
    ({FIRECRAWL_KEY: "firecrawl"}, "tool_keys entry 0", FIRECRAWL_KEY), ({"firecrawl": FIRECRAWL_KEY, "puppeteer": "has space"}, "tool_keys[puppeteer]", None),
    ({"firecrawl": FIRECRAWL_KEY, f"{BRAVE_KEY} x": "value"}, "tool_keys entry 1", BRAVE_KEY),
])
def test_request_record_refuses_bad_tool_keys_without_quoting(browser_lib, pack, keys, field, value) -> None:
    # EC-7 / AC-29 / AC-30 / D-28: whitespace, empty and over-long keys
    # and non-text names are refused by the record; an entry is named by
    # its registry name, else by its position.
    with pytest.raises(browser_lib.ConfigurationError) as caught:
        request(browser_lib, ["firecrawl"], keys)
    assert caught.value.details["field"] == field
    if value is not None:
        assert_unquoted(caught.value, value, pack)


def test_registry_suggests_a_close_name_or_lists_the_mountable_tools(browser_lib, pack) -> None:
    # AC-4 / FR-5 / EC-5: did-you-mean from registry names; with no
    # close name, the 13 mountable tools (or the tool's capabilities).
    lib = browser_lib
    typo = refused(lib, ["jina", "playwrite"])
    assert typo.details["field"] == "tools[1]" and "playwright" in str(typo) and "playwrite" not in str(typo)
    unknown = refused(lib, ["skyvern"])
    assert unknown.details["field"] == "tools[0]" and all(name in str(unknown) for name in MOUNTABLE) and "skyvern" not in str(unknown)
    capability = refused(lib, ["firecrawl:serch"])
    assert capability.details["field"] == "tools[0]" and "search" in str(capability) and "serch" not in str(capability)
    nothing_close = refused(lib, ["firecrawl:zzzzzz"])
    assert all(name in str(nothing_close) for name in ("search", "scrape", "map", "crawl", "interact")) and "zzzzzz" not in str(nothing_close)
    key_shaped = refused(lib, [FIRECRAWL_KEY])
    assert key_shaped.details["field"] == "tools[0]"
    assert_unquoted(key_shaped, FIRECRAWL_KEY, pack)


def test_registry_refuses_exclusions_hosts_and_duplicates(browser_lib) -> None:
    # AC-5 / EC-4 / FR-5 / NG-6: the recorded reason; hosts reserved; a
    # repeated tool names both indexes.
    lib = browser_lib
    reasons = lib.browser_constants.BROWSER_TOOL_EXCLUSION_REASONS
    for name in ("puppeteer", "fetch"):
        error = refused(lib, [name])
        assert error.details["field"] == "tools[0]" and reasons[lib.browser_enums.BrowserToolExclusion(name)] in str(error), name
    host = refused(lib, ["playwright@browserbase"])
    assert host.details["field"] == "tools[0]" and HOSTS_TEXT in str(host).lower()
    for pair in (["playwright", "playwright:vision"], ["firecrawl:search", "FIRECRAWL"]):
        duplicate = refused(lib, pair)
        assert duplicate.details["field"] == "tools[1]" and "tools[0]" in str(duplicate), pair


@pytest.mark.parametrize(("tools", "keys", "field"), [
    (["brave"], None, "tool_keys[brave]"), (["playwright"], {"playwright": FIRECRAWL_KEY}, "tool_keys[playwright]"),
    (["playwright"], {"firecrawl": FIRECRAWL_KEY}, "tool_keys[firecrawl]"), (["playwright"], {"puppeteer": FIRECRAWL_KEY}, "tool_keys[puppeteer]"),
    (["firecrawl"], {"firecrawll": FIRECRAWL_KEY}, "tool_keys entry 0"), (["firecrawl"], {"firecrawl": FIRECRAWL_KEY, "frecrawl": BRAVE_KEY}, "tool_keys entry 1"),
])
def test_registry_refuses_keys_by_meaning_without_echoing_them(browser_lib, pack, tools, keys, field) -> None:
    # AC-8 / EC-6 / FR-7: a missing required key; a key for a none-rule
    # tool, for a tool not in tools, or under a name that is not a
    # registry name (named by position).
    error = refused(browser_lib, tools, keys)
    assert error.details["field"] == field
    for name, value in (keys or {}).items():
        assert_unquoted(error, value, pack)
        if name not in MOUNTABLE and name != "puppeteer":
            assert name not in str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "tools", "keys", "field", "shown", "hidden"), [
    ("opencode", ["playwrite"], None, "tools[0]", "playwright", "playwrite"),
    ("grok", ["skyvern"], None, "tools[0]", "chromedevtools", "skyvern"),
    ("muse", ["puppeteer"], None, "tools[0]", None, None),
    ("opencode", ["playwright@browserbase"], None, "tools[0]", None, None),
    ("grok", ["brave"], None, "tool_keys[brave]", None, None),
    ("muse", [FIRECRAWL_KEY], None, "tools[0]", None, FIRECRAWL_KEY),
    ("opencode", ["firecrawl"], {"firecrawl": f"{FIRECRAWL_KEY}\n"}, "tool_keys[firecrawl]", None, FIRECRAWL_KEY),
    ("grok", ["firecrawl"], {FIRECRAWL_KEY: "firecrawl"}, "tool_keys entry 0", None, FIRECRAWL_KEY),
    ("muse", "playwright", None, "tools", None, None),
])
async def test_public_functions_refuse_bad_tools_before_any_process_or_file(browser_api, browser_world, sandbox, browse, check_browser_error, harness, tools, keys, field, shown, hidden) -> None:
    # AC-4 / AC-5 / AC-8 / AC-17 / AC-25 / AC-29 / AC-30 / INV-9:
    # configuration.invalid_argument naming the argument, from the
    # browser function, with nothing started and nothing written.
    before = sandbox.snapshot()
    with pytest.raises(browser_api.NativeThreadError) as caught:
        await browse(harness, tools=tools, tool_keys=keys)
    observations = [("argument", (field,))] + ([("suggestion", (shown,))] if shown else [])
    check_browser_error(caught.value, harness=harness, verb="run", code="configuration.invalid_argument", workspace=sandbox.workspace, observations=observations, secrets=[hidden] if hidden and len(hidden) > 16 else [])
    if hidden:
        assert hidden not in str(caught.value)
    assert sandbox.starts() == [] and sandbox.snapshot() == before and sandbox.call_folders() == []
