"""FILE: vidbyte/lib/constants/browser_tools.py

PURPOSE: Holds every fixed value and text of the browser tools the harness thread functions mount: the pinned registry data of each tool (package, version, entry, URL, arguments, options, environment and each capability's exact tool names), the recorded reason of each excluded name, the tool-string grammar, the bounds, the tool cache and per-call folder names, the Node floor, the npm install arguments, Chrome's searched locations, the Grok, opencode and Muse mount vocabulary, and the refusal and observation texts.
ROLE IN CODEBASE: Imported by the records in vidbyte/lib/dataclasses/browser_tools.py, the registry in vidbyte/lib/registries/browser_tools.py, hostkit/browser.py and the per-harness mounts, browser and wire modules under vidbyte/harnesses/native/.
ARCHITECTURE NOTE: The harness modules hold no literals of their own (spec INV-15), so every vendor fact of the browser feature lives here, one place per fact; the registry only arranges these values into rows. BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS, BROWSER_REAP_TIMEOUT_SECONDS and BROWSER_CHROME_PATHS are read through this module object at call time, never bound by a from-import, so one patch reaches every user. Tool tuples keep the order the pinned server lists them in (vendor facts section 4), which is the registry order a narrowed selection denies in.
FUNCTION INVENTORY: No functions. Constants grouped as bounds, grammar, the tool cache and per-call folder, Node and npm, Chrome, per-tool registry data, exclusion reasons, the Grok, opencode and Muse mount vocabulary, then the refusal and observation texts.
COMMON MODIFICATION PATTERNS: A new mountable tool adds its package, version, entry, arguments and capability tool tuples here under its own prefix, one registry row in vidbyte/lib/registries/browser_tools.py and one BrowserTool member. A pin bump changes the version and, when the server's tool list changed, the tool tuples, from a fresh `tools/list` probe.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte above vidbyte.lib.enums. 2. Do not name a constant with a password, token or secret word and give it a string (lint S054); key variable names live in BrowserToolVariable. 3. Do not put a caller's text into a refusal template; refusals name an index, a registry name or a position only (spec D-28). 4. Do not write a credential word followed by ":" or "=" in a text, because HarnessRedactor would rewrite it.
KNOWN EDGE CASES: BROWSER_CHROME_PATHS is chosen for the running platform when this module loads; Windows entries hold %VAR% references that os.path.expandvars fills in at call time, and an unset variable leaves an entry that names no file. A stdio entry tuple starts with node_modules and the package's own path parts, because it is relative to the install prefix ~/.vidbyte/tools/<tool>-<version>. The Playwright capability groups other than core are additive server flags (--caps), so each holds only the tools that flag adds.
RELATED DOCS: vidbyte/harnesses/README.md; vidbyte/lib/registries/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_contract.py, tests/features/harness_threads/test_harness_threads_browser_registry.py
"""

from __future__ import annotations

import sys
from types import MappingProxyType

from vidbyte.lib.enums.browser_tools import BrowserToolExclusion

# Contract bounds: counts, sizes, times and the suggestion threshold.
BROWSER_TOOLS_MAX_PER_CALL = 8
BROWSER_TOOL_STRING_MAX_CHARS = 128
BROWSER_TOOL_CALLS_MAX_ITEMS = 1000
BROWSER_ARTIFACTS_MAX_ITEMS = 1000
BROWSER_SUGGESTION_CUTOFF = 0.6
BROWSER_SUGGESTION_COUNT = 1
BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS = 600.0
BROWSER_REAP_TIMEOUT_SECONDS = 10.0
# The command-line units the Grok browser options may take (spec NFR-6):
# the measured 608-unit worst case of the plain options, a 30,000-unit
# prompt and this budget stay under Windows' 32,766.
GROK_BROWSER_RULES_MAX_UNITS = 1800
MUSE_SETTINGS_SCHEMA_VERSION = 1

# The tool-string grammar
# <tool>[:<capability>[,<capability>...]][@<host>], applied with
# re.fullmatch; a host is reserved for a later release.
BROWSER_TOOL_STRING_PATTERN = r"(?i)[a-z0-9-]+(:[a-z0-9-]+(,[a-z0-9-]+)*)?(@[a-z0-9-]+)?"
BROWSER_CAPABILITY_SEPARATOR = ":"
BROWSER_CAPABILITY_LIST_SEPARATOR = ","
BROWSER_HOST_SEPARATOR = "@"

# The tool cache and the per-call folder.
BROWSER_TOOL_CACHE_PARTS = (".vidbyte", "tools")
BROWSER_STAGING_FOLDER = ".staging"
BROWSER_TOOL_FOLDER_TEMPLATE = "{tool}-{version}"
BROWSER_CALL_FOLDER_PREFIX = "vidbyte-browser-"
# tempfile.mkdtemp names a folder with this many random characters
# after the prefix; the Grok budget counts the agent path with it.
BROWSER_CALL_FOLDER_RANDOM_CHARS = 8
# A per-call folder name of the real length, for the Grok budget,
# which is checked before the folder exists.
BROWSER_CALL_FOLDER_ESTIMATE = BROWSER_CALL_FOLDER_PREFIX + "x" * BROWSER_CALL_FOLDER_RANDOM_CHARS
BROWSER_ARTIFACTS_FOLDER = "artifacts"
BROWSER_PROFILES_FOLDER = "profiles"
BROWSER_FILE_ENCODING = "utf-8"
# Removing a profile right after its browser was killed can race the
# operating system releasing the browser's lock file, so the removal
# is tried a few times, a short pause apart, until one deadline set
# BROWSER_REAP_TIMEOUT_SECONDS after the reap starts, which the reap
# and every removal of the call share.
BROWSER_REMOVE_ATTEMPTS = 5
BROWSER_REMOVE_PAUSE_SECONDS = 0.2

# Node and the npm bundled with it (spec D-5, D-6).
BROWSER_NODE_PROGRAM = "node"
BROWSER_NODE_VERSION_OPTION = "--version"
BROWSER_NODE_VERSION_PATTERN = r"v(\d+)\.(\d+)\.(\d+)"
BROWSER_NODE_MIN_VERSION = (22, 12, 0)
BROWSER_VERSION_SEPARATOR = "."
# npm-cli.js sits beside node.exe on Windows and under ../lib beside
# bin/node on POSIX, as the Node installers lay it out.
BROWSER_NPM_CLI_WINDOWS_PARTS = ("node_modules", "npm", "bin", "npm-cli.js")
BROWSER_NPM_CLI_POSIX_PARTS = ("lib", "node_modules", "npm", "bin", "npm-cli.js")
BROWSER_NPM_INSTALL_ARGUMENTS = ("install", "--no-audit", "--no-fund", "--prefix")
BROWSER_PACKAGE_VERSION_TEMPLATE = "{package}@{version}"
# npm installs a package under <prefix>/node_modules/<package path
# parts>, so every stdio entry starts with these parts.
BROWSER_NODE_MODULES_FOLDER = "node_modules"
BROWSER_PACKAGE_PATH_SEPARATOR = "/"

# Chrome stable at Playwright's chrome-channel locations, per platform,
# searched in order after os.path.expandvars (spec section 9.3).
BROWSER_CHROME_WINDOWS_PATHS = (
    "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe",
    "%PROGRAMFILES%\\Google\\Chrome\\Application\\chrome.exe",
    "%PROGRAMFILES(X86)%\\Google\\Chrome\\Application\\chrome.exe",
    "%HOMEDRIVE%\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
)
BROWSER_CHROME_MACOS_PATHS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",)
BROWSER_CHROME_LINUX_PATHS = ("/opt/google/chrome/chrome",)
BROWSER_CHROME_PLATFORM_PATHS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {
        "win32": BROWSER_CHROME_WINDOWS_PATHS,
        "darwin": BROWSER_CHROME_MACOS_PATHS,
    }
)
BROWSER_CHROME_PATHS: tuple[str, ...] = BROWSER_CHROME_PLATFORM_PATHS.get(sys.platform, BROWSER_CHROME_LINUX_PATHS)

# Per-tool registry data (spec section 9.1 seed registry; vendor facts
# section 4: `npm install` on Node 22.12.0 and `tools/list` probes).
# Playwright: @playwright/mcp 0.0.83.
PLAYWRIGHT_PACKAGE = "@playwright/mcp"
PLAYWRIGHT_VERSION = "0.0.83"
PLAYWRIGHT_ENTRY = ("node_modules", "@playwright", "mcp", "cli.js")
PLAYWRIGHT_ARGUMENTS = ("--headless",)
PLAYWRIGHT_PROFILE_OPTION = "--user-data-dir"
PLAYWRIGHT_OUTPUT_OPTION = "--output-dir"
PLAYWRIGHT_CAPS_OPTION = "--caps"
PLAYWRIGHT_CORE_TOOLS = (
    "browser_close", "browser_resize", "browser_console_messages", "browser_handle_dialog", "browser_emulate_media", "browser_evaluate",
    "browser_file_upload", "browser_drop", "browser_find", "browser_fill_form", "browser_press_key", "browser_type", "browser_navigate",
    "browser_navigate_back", "browser_network_requests", "browser_network_request", "browser_run_code_unsafe", "browser_take_screenshot",
    "browser_snapshot", "browser_click", "browser_drag", "browser_hover", "browser_select_option", "browser_tabs", "browser_wait_for",
)
PLAYWRIGHT_DEVTOOLS_TOOLS = (
    "browser_resume", "browser_highlight", "browser_hide_highlight", "browser_annotate", "browser_start_recording", "browser_stop_recording",
    "browser_start_tracing", "browser_stop_tracing", "browser_start_video", "browser_stop_video", "browser_video_chapter",
    "browser_video_show_actions", "browser_video_hide_actions",
)
PLAYWRIGHT_STORAGE_TOOLS = (
    "browser_cookie_list", "browser_cookie_get", "browser_cookie_set", "browser_cookie_delete", "browser_cookie_clear", "browser_storage_state",
    "browser_set_storage_state", "browser_localstorage_list", "browser_localstorage_get", "browser_localstorage_set", "browser_localstorage_delete",
    "browser_localstorage_clear", "browser_sessionstorage_list", "browser_sessionstorage_get", "browser_sessionstorage_set",
    "browser_sessionstorage_delete", "browser_sessionstorage_clear",
)
PLAYWRIGHT_NETWORK_TOOLS = ("browser_network_state_set", "browser_route", "browser_route_list", "browser_unroute")
PLAYWRIGHT_PDF_TOOLS = ("browser_pdf_save",)
PLAYWRIGHT_VISION_TOOLS = ("browser_mouse_move_xy", "browser_mouse_click_xy", "browser_mouse_drag_xy", "browser_mouse_down", "browser_mouse_up", "browser_mouse_wheel")

# Chrome DevTools: chrome-devtools-mcp 1.11.0, started quiet
# (spec D-21).
CHROMEDEVTOOLS_PACKAGE = "chrome-devtools-mcp"
CHROMEDEVTOOLS_VERSION = "1.11.0"
CHROMEDEVTOOLS_ENTRY = ("node_modules", "chrome-devtools-mcp", "build", "src", "bin", "chrome-devtools-mcp.js")
CHROMEDEVTOOLS_ARGUMENTS = ("--headless", "--no-usage-statistics")
CHROMEDEVTOOLS_PROFILE_OPTION = "--userDataDir"
CHROMEDEVTOOLS_QUIET_SWITCH = "1"
CHROMEDEVTOOLS_ALL_TOOLS = (
    "click", "close_page", "drag", "emulate", "evaluate_script", "fill", "fill_form", "get_console_message", "get_css_styles",
    "get_network_request", "handle_dialog", "hover", "lighthouse_audit", "list_console_messages", "list_network_requests", "list_pages",
    "navigate_page", "new_page", "performance_analyze_insight", "performance_start_trace", "performance_stop_trace", "press_key",
    "resize_page", "screencast_start", "screencast_stop", "select_page", "take_heapsnapshot", "take_screenshot", "take_snapshot",
    "type_text", "upload_file", "wait_for",
)

# Firecrawl: firecrawl-mcp 3.30.2 (26 tools probed keyless).
FIRECRAWL_PACKAGE = "firecrawl-mcp"
FIRECRAWL_VERSION = "3.30.2"
FIRECRAWL_ENTRY = ("node_modules", "firecrawl-mcp", "dist", "index.js")
FIRECRAWL_ALL_TOOLS = (
    "firecrawl_scrape", "firecrawl_map", "firecrawl_search", "firecrawl_find_tools", "firecrawl_crawl", "firecrawl_check_crawl_status",
    "firecrawl_agent", "firecrawl_agent_status", "firecrawl_interact", "firecrawl_interact_stop", "firecrawl_parse", "firecrawl_monitor_create",
    "firecrawl_monitor_list", "firecrawl_monitor_get", "firecrawl_monitor_update", "firecrawl_monitor_delete", "firecrawl_monitor_run",
    "firecrawl_monitor_checks", "firecrawl_monitor_check", "firecrawl_research_search_papers", "firecrawl_research_inspect_paper",
    "firecrawl_research_related_papers", "firecrawl_research_read_paper", "firecrawl_developer_search", "firecrawl_gov_search",
    "firecrawl_credit_usage",
)
FIRECRAWL_SEARCH_TOOLS = ("firecrawl_search",)
FIRECRAWL_SCRAPE_TOOLS = ("firecrawl_scrape",)
FIRECRAWL_MAP_TOOLS = ("firecrawl_map",)
FIRECRAWL_CRAWL_TOOLS = ("firecrawl_crawl", "firecrawl_check_crawl_status")
FIRECRAWL_INTERACT_TOOLS = ("firecrawl_interact", "firecrawl_interact_stop")

# Exa: exa-mcp-server 3.4.2.
EXA_PACKAGE = "exa-mcp-server"
EXA_VERSION = "3.4.2"
EXA_ENTRY = ("node_modules", "exa-mcp-server", "dist", "stdio.cjs")
EXA_ALL_TOOLS = ("web_search_exa", "web_fetch_exa")
EXA_SEARCH_TOOLS = ("web_search_exa",)
EXA_FETCH_TOOLS = ("web_fetch_exa",)

# Tavily: tavily-mcp 0.2.22 (starts without its key but answers no
# call without one, A-10).
TAVILY_PACKAGE = "tavily-mcp"
TAVILY_VERSION = "0.2.22"
TAVILY_ENTRY = ("node_modules", "tavily-mcp", "build", "index.js")
TAVILY_ALL_TOOLS = ("tavily_search", "tavily_extract", "tavily_crawl", "tavily_map", "tavily_research")
TAVILY_SEARCH_TOOLS = ("tavily_search",)
TAVILY_EXTRACT_TOOLS = ("tavily_extract",)
TAVILY_CRAWL_TOOLS = ("tavily_crawl",)
TAVILY_MAP_TOOLS = ("tavily_map",)
TAVILY_RESEARCH_TOOLS = ("tavily_research",)

# Brave Search: @brave/brave-search-mcp-server 2.1.4.
BRAVE_PACKAGE = "@brave/brave-search-mcp-server"
BRAVE_VERSION = "2.1.4"
BRAVE_ENTRY = ("node_modules", "@brave", "brave-search-mcp-server", "dist", "index.js")
BRAVE_ALL_TOOLS = ("brave_web_search", "brave_local_search", "brave_video_search", "brave_image_search", "brave_news_search", "brave_summarizer", "brave_llm_context", "brave_place_search")
BRAVE_SEARCH_TOOLS = ("brave_web_search",)

# Perplexity: @perplexity-ai/mcp-server 1.3.0.
PERPLEXITY_PACKAGE = "@perplexity-ai/mcp-server"
PERPLEXITY_VERSION = "1.3.0"
PERPLEXITY_ENTRY = ("node_modules", "@perplexity-ai", "mcp-server", "dist", "index.js")
PERPLEXITY_ALL_TOOLS = ("perplexity_ask", "perplexity_research", "perplexity_reason", "perplexity_search")
PERPLEXITY_SEARCH_TOOLS = ("perplexity_search",)
PERPLEXITY_RESEARCH_TOOLS = ("perplexity_research",)

# Bright Data: @brightdata/mcp 3.1.0 (its key variable is the bare
# API_TOKEN).
BRIGHTDATA_PACKAGE = "@brightdata/mcp"
BRIGHTDATA_VERSION = "3.1.0"
BRIGHTDATA_ENTRY = ("node_modules", "@brightdata", "mcp", "server.js")
BRIGHTDATA_ALL_TOOLS = (
    "search_engine", "scrape_as_markdown", "search_engine_batch", "scrape_batch", "scrape_as_html", "extract", "discover", "list_dataset_fields",
    "search_dataset", "search_scrapers", "get_scraper_details", "run_scraper", "get_scraper_progress", "get_scraper_results", "refresh_scrapers",
    "session_stats", "chatgpt_ai_insights", "perplexity_ai_insights", "scraping_browser_navigate", "scraping_browser_go_back",
    "scraping_browser_go_forward", "scraping_browser_snapshot", "scraping_browser_click_ref", "scraping_browser_type_ref",
    "scraping_browser_screenshot", "scraping_browser_network_requests", "scraping_browser_wait_for_ref", "scraping_browser_fill_form",
    "scraping_browser_get_text", "scraping_browser_get_html", "scraping_browser_scroll", "scraping_browser_scroll_to_ref",
)
BRIGHTDATA_SEARCH_TOOLS = ("search_engine", "search_engine_batch")
BRIGHTDATA_SCRAPE_TOOLS = ("scrape_as_markdown", "scrape_as_html", "scrape_batch")
BRIGHTDATA_BROWSER_TOOLS = (
    "scraping_browser_navigate", "scraping_browser_go_back", "scraping_browser_go_forward", "scraping_browser_snapshot", "scraping_browser_click_ref",
    "scraping_browser_type_ref", "scraping_browser_screenshot", "scraping_browser_network_requests", "scraping_browser_wait_for_ref",
    "scraping_browser_fill_form", "scraping_browser_get_text", "scraping_browser_get_html", "scraping_browser_scroll", "scraping_browser_scroll_to_ref",
)

# Apify: @apify/actors-mcp-server 0.18.4 (calls api.apify.com and Sentry
# at start, EC-34).
APIFY_PACKAGE = "@apify/actors-mcp-server"
APIFY_VERSION = "0.18.4"
APIFY_ENTRY = ("node_modules", "@apify", "actors-mcp-server", "dist", "stdio.js")
APIFY_ALL_TOOLS = ("search-actors", "fetch-actor-details", "call-actor", "get-actor-run", "get-dataset-items", "get-key-value-store-record", "abort-actor-run", "search-apify-docs", "fetch-apify-docs", "report-problem")

# Linkup: linkup-mcp-server 3.4.0.
LINKUP_PACKAGE = "linkup-mcp-server"
LINKUP_VERSION = "3.4.0"
LINKUP_ENTRY = ("node_modules", "linkup-mcp-server", "bin", "linkup-mcp-server.js")
LINKUP_ALL_TOOLS = ("linkup-search", "linkup-research", "linkup-get-research", "linkup-fetch")
LINKUP_SEARCH_TOOLS = ("linkup-search",)
LINKUP_FETCH_TOOLS = ("linkup-fetch",)
LINKUP_RESEARCH_TOOLS = ("linkup-research", "linkup-get-research")

# Remote endpoints (vendor docs, A-12); a key travels as a Bearer
# header.
BROWSERBASE_URL = "https://mcp.browserbase.com/mcp"
BROWSERBASE_ALL_TOOLS = ("start", "end", "navigate", "act", "observe", "extract")
JINA_URL = "https://mcp.jina.ai/v1"
JINA_ALL_TOOLS = (
    "primer", "guess_datetime_url", "search_web", "search_arxiv", "search_ssrn", "search_images", "search_jina_blog", "read_url",
    "capture_screenshot_url", "expand_query", "sort_by_relevance", "deduplicate_strings",
)
JINA_SEARCH_TOOLS = ("search_web", "search_arxiv", "search_ssrn", "search_images", "search_jina_blog")
JINA_FETCH_TOOLS = ("read_url", "capture_screenshot_url")
PARALLEL_URL = "https://search.parallel.ai/mcp"
PARALLEL_ALL_TOOLS = ("web_search", "web_fetch")
PARALLEL_SEARCH_TOOLS = ("web_search",)
PARALLEL_FETCH_TOOLS = ("web_fetch",)
BROWSER_REMOTE_URL_PREFIX = "https://"
BROWSER_EXACT_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"

# One recorded reason per excluded name (spec section 9.1 exclusions;
# vendor facts section 7).
BROWSER_TWO_CREDENTIALS_REASON = "It needs two credentials, a user name and an access value, and the SDK passes one key per tool."
BROWSER_INSTANCE_REASON = "It needs the URL of a running SearXNG instance, which the SDK does not provide."
BROWSER_NODE_FAILURE_REASON = "Its server fails to start on Node 22.12, the Node release every mountable tool was verified on."
BROWSER_UVX_REASON = "It needs a Python uvx runtime that the SDK does not pin, and its first-ever start (2.6 to 2.9 seconds) exceeds Grok's start-up grace of about 2 seconds."
BROWSER_CLI_SKILL_REASON = "It is a CLI plus a skill, not an MCP server, so there is no server to mount."
BROWSER_DOCKER_REASON = "It runs only as a Docker container, which the SDK does not start."
BROWSER_OWN_LLM_REASON = "It runs its own agent with its own LLM key and needs the uv runtime, so it is a second agent rather than a tool."
BROWSER_OAUTH_REASON = "It signs in only through OAuth in a browser window, which a headless call cannot complete."
BROWSER_ARCHIVED_REASON = "Archived by its maintainers; use playwright or chromedevtools instead."
BROWSER_UNMAINTAINED_REASON = "Unmaintained since its last release; use browserbase or playwright instead."
BROWSER_UNVERIFIED_REASON = "Not verified for this release: its server was not probed on Node 22.12 with a per-call key."
BROWSER_TOOL_EXCLUSION_REASONS: MappingProxyType[BrowserToolExclusion, str] = MappingProxyType(
    {
        BrowserToolExclusion.BROWSERSTACK: BROWSER_TWO_CREDENTIALS_REASON,
        BrowserToolExclusion.SEARXNG: BROWSER_INSTANCE_REASON,
        BrowserToolExclusion.WDIO: BROWSER_NODE_FAILURE_REASON,
        BrowserToolExclusion.FETCH: BROWSER_UVX_REASON,
        BrowserToolExclusion.DUCKDUCKGO: BROWSER_UVX_REASON,
        BrowserToolExclusion.AGENTBROWSER: BROWSER_CLI_SKILL_REASON,
        BrowserToolExclusion.PLAYWRIGHTCLI: BROWSER_CLI_SKILL_REASON,
        BrowserToolExclusion.MIDSCENE: BROWSER_CLI_SKILL_REASON,
        BrowserToolExclusion.DEVBROWSER: BROWSER_CLI_SKILL_REASON,
        BrowserToolExclusion.CRAWL4AI: BROWSER_DOCKER_REASON,
        BrowserToolExclusion.BROWSERUSE: BROWSER_OWN_LLM_REASON,
        BrowserToolExclusion.SCRAPLING: BROWSER_UNVERIFIED_REASON,
        BrowserToolExclusion.KERNEL: BROWSER_OAUTH_REASON,
        BrowserToolExclusion.CLOUDFLARE: BROWSER_OAUTH_REASON,
        BrowserToolExclusion.PUPPETEER: BROWSER_ARCHIVED_REASON,
        BrowserToolExclusion.HYPERBROWSER: BROWSER_UNMAINTAINED_REASON,
        BrowserToolExclusion.STEEL: BROWSER_UNVERIFIED_REASON,
        BrowserToolExclusion.BROWSERLESS: BROWSER_UNVERIFIED_REASON,
    }
)

# The option form every compiled server argument and Grok rule uses.
BROWSER_OPTION_TEMPLATE = "{option}={value}"

# Grok: the per-call agent file (spec D-7, D-18) and the argv rules
# (D-10). JSON is valid YAML flow style, so the frontmatter is one JSON
# object between the two fences.
GROK_BROWSER_AGENT_FILE = "vidbyte-browser-agent.md"
GROK_BROWSER_AGENT_NAME = "vidbyte-browser"
GROK_BROWSER_AGENT_DESCRIPTION = "A headless coding agent run by the Vidbyte SDK for one call."
GROK_BROWSER_AGENT_BODY = "Work on the task in the user's prompt. Use the tools that are available to you when they help, and answer with the result."
GROK_BROWSER_AGENT_FENCE = "---"
GROK_AGENT_NAME_FIELD = "name"
GROK_AGENT_DESCRIPTION_FIELD = "description"
GROK_AGENT_SERVERS_FIELD = "mcpServers"
GROK_AGENT_COMMAND_FIELD = "command"
GROK_AGENT_ARGS_FIELD = "args"
GROK_AGENT_ENV_FIELD = "env"
GROK_AGENT_ENV_VALUE_FIELD = "value"
GROK_AGENT_URL_FIELD = "url"
GROK_MCP_TOOL_RULE = "MCPTool({server}__{tool})"
GROK_MCP_TOOL_WILDCARD = "*"
GROK_TOOL_NAME_SEPARATOR = "__"

# opencode: the `mcp` and `permission` members of
# OPENCODE_CONFIG_CONTENT (spec D-10, D-23).
BROWSER_OPENCODE_SERVER_PREFIX = "vidbyte-"
OPENCODE_CONFIG_MCP_FIELD = "mcp"
OPENCODE_CONFIG_PERMISSION_FIELD = "permission"
OPENCODE_MCP_TYPE_FIELD = "type"
OPENCODE_MCP_LOCAL_TYPE = "local"
OPENCODE_MCP_REMOTE_TYPE = "remote"
OPENCODE_MCP_COMMAND_FIELD = "command"
OPENCODE_MCP_ENVIRONMENT_FIELD = "environment"
OPENCODE_MCP_ENABLED_FIELD = "enabled"
OPENCODE_MCP_URL_FIELD = "url"
OPENCODE_MCP_OAUTH_FIELD = "oauth"
OPENCODE_MCP_HEADERS_FIELD = "headers"
OPENCODE_PERMISSION_ALLOW = "allow"
OPENCODE_PERMISSION_DENY = "deny"
OPENCODE_PERMISSION_RULE = "{server}_{tool}"
OPENCODE_PERMISSION_WILDCARD = "*"
OPENCODE_WEB_TOOLS = ("webfetch", "websearch")
OPENCODE_TOOL_NAME_SEPARATOR = "_"
BROWSER_AUTHORIZATION_HEADER = "Authorization"
BROWSER_BEARER_TEMPLATE = "Bearer {value}"

# Muse: $XDG_CONFIG_HOME/muse/settings.json (MUSE_SETTINGS_PARTS in
# vidbyte/lib/constants/native_threads.py), whose top level is exactly
# {"schema_version": 1, "mcpServers": {...}} (vendor facts section 1).
MUSE_SETTINGS_VERSION_FIELD = "schema_version"
MUSE_SETTINGS_SERVERS_FIELD = "mcpServers"
MUSE_SERVER_COMMAND_FIELD = "command"
MUSE_SERVER_ARGS_FIELD = "args"
MUSE_SERVER_ENV_FIELD = "env"
MUSE_SERVER_TRANSPORT_FIELD = "transport"
MUSE_SERVER_URL_FIELD = "url"
MUSE_STREAMABLE_HTTP_TRANSPORT = "streamable_http"
MUSE_MCP_TOOL_PREFIX = "mcp"
MUSE_TOOL_NAME_SEPARATOR = "__"

# Field names of the refusals; a refusal names an index, a registry name
# or a position, never the caller's text (spec D-28).
BROWSER_TOOLS_FIELD = "tools"
BROWSER_TOOL_ITEM_FIELD = "tools[{index}]"
BROWSER_TOOL_KEYS_FIELD = "tool_keys"
BROWSER_TOOL_KEY_NAME_FIELD = "tool_keys[{name}]"
BROWSER_TOOL_KEY_ENTRY_FIELD = "tool_keys entry {index}"

# Refusal texts of the request record.
BROWSER_TOOLS_COUNT_TEXT = "tools must list from 1 to {max_items} tool strings."
BROWSER_TOOL_ITEM_TEXT = "Each tools item must be one tool string of at most {max_chars} characters in the form <tool>[:<capability>[,<capability>...]], made of letters, digits and hyphens; the item is not repeated here because it may hold a key."
BROWSER_TOOL_KEY_VALUE_TEXT = "Each tool_keys value must be one key of 1 to {max_chars} printable ASCII characters with no spaces, line breaks or braces; the value is not repeated here."
BROWSER_TOOL_KEY_NAME_TEXT = "Each tool_keys name must be the lower-case name of a browser tool, such as firecrawl; this entry's name is not one, and it is not repeated here because it may be a key."

# Refusal texts of the registry.
BROWSER_HOST_TEXT = "A host after @ is reserved for a later release: hosts are not supported in this release, so pass the tool name without it."
BROWSER_EXCLUDED_TEXT = "That tool cannot be mounted. {reason}"
# A suggestion may be an excluded name (difflib finds kernel for an
# unknown name such as skyvern), so the mountable tools are listed too.
BROWSER_TOOL_SUGGESTION_TEXT = "It names no browser tool this release can mount. Did you mean {suggestion}? The mountable tools are {tools}."
BROWSER_TOOL_UNKNOWN_TEXT = "It names no browser tool this release can mount; the mountable tools are {tools}."
BROWSER_CAPABILITY_SUGGESTION_TEXT = "It names a capability that {tool} does not have. Did you mean {suggestion}? Its capabilities are {capabilities}."
BROWSER_CAPABILITY_UNKNOWN_TEXT = "It names a capability that {tool} does not have; its capabilities are {capabilities}."
BROWSER_DUPLICATE_TEXT = "It names the same tool as tools[{first}]; list each tool once, with all of its capabilities after one colon."
BROWSER_KEY_MISSING_TEXT = "{tool} cannot start without its own key, and tool_keys holds none under the name {tool}."
BROWSER_KEY_REFUSED_TEXT = "{tool} takes no key, so tool_keys must not name it."
BROWSER_KEY_UNSELECTED_TEXT = "tool_keys names a tool that tools does not select; pass a key only for a selected tool."
BROWSER_LIST_SEPARATOR = ", "

# Observation details of the browser.* failures and the per-call folder
# (spec D-29); NativeErrorFactory.failure prints them before the likely
# cause and the next step.
BROWSER_NODE_MISSING_DETAIL = "The selected tools run on Node, and the SDK searched for node on PATH and found none; install Node {minimum} or later."
BROWSER_NODE_BATCH_DETAIL = "The node found first on PATH is the Windows batch file {program}, which the SDK never runs."
BROWSER_NODE_TOO_OLD_DETAIL = "The node at {program} reports version {found}, below {minimum}, the release the pinned tools were verified on."
BROWSER_NODE_UNREADABLE_DETAIL = "The node at {program} did not report a version the SDK can read."
BROWSER_CHROME_MISSING_DETAIL = "No Chrome stable was found for a selected tool that drives Chrome; the SDK searched {locations}."
BROWSER_HOME_UNKNOWN_DETAIL = "The user home folder, which holds the tool cache, could not be determined ({error_type}); set HOME (POSIX) or USERPROFILE (Windows) for this process."
BROWSER_CACHE_FOLDER_DETAIL = "The tool cache folder {folder} could not be prepared ({error_type})."
BROWSER_FOLDER_BROKEN_DETAIL = "The published tool folder {folder} exists but has no entry file, and the SDK does not repair it; delete that folder so the next call installs the tool again."
BROWSER_NPM_MISSING_DETAIL = "The npm that ships with Node was not found at {path}, so {package} could not be installed; install Node from nodejs.org, which puts npm beside it."
BROWSER_INSTALL_FAILED_DETAIL = "npm could not install {package} into the tool cache."
BROWSER_INSTALL_LAUNCH_DETAIL = "npm could not be started to install {package} ({kind})."
BROWSER_INSTALL_TIMEOUT_DETAIL = "npm did not finish installing {package} within {seconds} seconds, so the SDK stopped it and published nothing."
BROWSER_INSTALL_NO_ENTRY_DETAIL = "npm installed {package} but its entry file is missing, so nothing was published."
BROWSER_CALL_FOLDER_DETAIL = "The per-call browser folder could not be created in the temp folder {folder} ({error_type})."
BROWSER_TOOLS_UNAVAILABLE_DETAIL = "The vendor's output shows neither a connection to nor a completed call on these mounted servers, so no mounted tool was used on them: {servers}."
BROWSER_GROK_AGENT_FILE_DETAIL = "The Grok agent file could not be written into the per-call folder {folder} ({error_type})."
BROWSER_REQUIRED_SERVER_DETAIL = "Muse Code stopped the run because a mounted server failed to start."
BROWSER_GROK_KEYED_REMOTE_DETAIL = "Grok Build would need the key of the remote tool {tool} written into its agent file, so the SDK does not mount it; Grok mounts stdio tools with or without a key and remote tools without one."
BROWSER_GROK_BUDGET_DETAIL = "The Grok allow and deny rules for these tools take {units} command-line units, more than the {limit} the SDK leaves for them; narrow the capabilities or mount fewer tools."
BROWSER_MUSE_KEYED_DETAIL = "Muse Code passes no environment to its servers, so the key for {tool} could only be written into a file, and the SDK mounts only keyless tools on Muse."
BROWSER_MUSE_NARROWED_DETAIL = "Muse Code cannot limit a server to some of its tools, so {tool} can be mounted on Muse only whole, without a narrowing capability."
BROWSER_MUSE_WSL_DETAIL = "Muse Code in WSL mode can mount only keyless remote tools ({remote}), because the distro has no Node for the stdio tool {tool}."
