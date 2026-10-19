---
slug: harness-browser-tools
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-16 21:43
flags: none
---

# Request: browser tools for every harness — `run_opencode_with_browser`, `run_grok_with_browser`, `run_muse_with_browser` (and their continue/fork siblings), driven by a pinned browser-tool registry

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening message):

````text
vidbyte-sdk/ repo request. Take a look at pr #1036, I want to create more functions for the following use case: I want to create "coding harness with browser tools" agent/functions like this. Consider searching browser tools and browser action tools (browserbase, firecrawl, playwright, and more). I basically want to create a function like "launch_opencode_with_browser-tools(tools=)" and then pass in strings to launch the tools. Essentially, I want to have functions where we can do the following:

"launch opencode with browserbase tooling", "launch opencode with firecrawl search ability and playwright browser" capabilities. Then from here we can programmatically launch "browser based" coding agent sessions where there are all types of use cases (ex: create a video verfication where you use the computer/browser like auser, use web app like user and publish bug reports, etc). Dont think about use cases now, just want you  to think through implementation of these functions. What are all browser tools that we can implement/have a registry of and how are we going to actually implement something like this for every harness
````

**Prompt 2** (after the assistant's first design answer, §C.0.1):

````text
feel like the list of browser tools can be more extensive, feel like there are 15-20 popular ones that exist and 2) explain actually how these functions run under the hood and 3) explain how we can add these functions for not only opencode, but grok build, codex, muse, claude code, etc
````

**Prompt 3** (the `/spec-pipeline` invocation; its whole argument string, after the assistant's second design answer, §C.0.2):

````text
great, you explained the entire process really well, make sure that each function has all layers to it that makes this request possible. I want to keep the same "run_opencode_with_browser()", "run_grok_with_browser()", type of function names that we have in the repo, and want you to integrate these browser tools into every harness that we have so far in the repo. (kick off and explain this entire thing with the 'spec-pipelin' to a subagent (make sure to include in-depth response you returned to me last turn, and then can you go into depth about the following:

[ ] Bet on desktop computer use as the next registry category — cua-driver (30K stars) and E2B Desktop let agents operate any app, not only web pages. Builds on: the compile-per-harness interface. First step: a one-day spike that loads cua-driver mcp into opencode. Could we create the same type of agents the same way, except instead of attaching browser tools we attach "computer use" tools. Or is there fundamentally different ways that we have to do this? (do the agents need their own computers, is it not just tools for computer,  do agents need  permissions, etc)
````

Note on Prompt 3: the part after "and then can you go into depth about the following:" (desktop computer use) is a question the user asked the assistant to answer in the conversation. It is **not** part of this pipeline's build (see §C "Rejected alternatives" and "Constraints").

## B. Handoff block and decision ledger (verbatim, if present)

None in this conversation.

## C. Structured conversation notes

### C.0 The design the user endorsed — the assistant's two answers, verbatim

Prompt 3 opens with "great, you explained the entire process really well" and asks that the in-depth previous answer be included. Both answers are reproduced below exactly as the assistant sent them, except that each answer's closing "Next steps" checklist (ten business ideas, not design) is omitted. Where §C.0.1 and §C.0.2 disagree, §C.0.2 wins; where either disagrees with Prompt 3 (function names, harness scope), Prompt 3 wins. In both answers, "Verified" facts were checked with commands in the conversation; the research reports behind them are in §C.9.

#### C.0.1 Answer to Prompt 1 (verbatim, "Next steps" omitted)

`````markdown
## Bottom line

The right shape is a **two-layer system**: a **registry** that turns strings like `"firecrawl:search"` into neutral, pinned tool specs, and a **per-harness compiler** that turns those specs into each harness's native mounting mechanism. PR #1036 already built the hard part — every harness has a private, per-call config channel — so most harnesses need one new file each. But I found the existing presets are mostly broken, so the registry needs fresh data.

Two research agents gathered the evidence (one read vendor docs, source, and npm; one probed Grok and Claude locally with a stdio MCP canary, no model calls). I independently re-checked 13 package names on npm — all matched. Two findings affect existing code:

- **Grok leaks the user's MCP servers today (verified).** Grok scans `~/.claude.json` and Cursor's `mcp.json` by default (`~/.grok/docs/user-guide/07-mcp-servers.md:292`). `GrokThreadRun._environment` sets neither `GROK_CLAUDE_MCPS_ENABLED=0` nor `GROK_CURSOR_MCPS_ENABLED=0`, so every Grok run from #1036 also loads the user's personal MCP servers. The research agent reports Claude *skills* compat is on by default too, which would undercut the PR's "skills apply to that one call" guarantee.
- **11 of 15 web presets in `vidbyte/lib/config/mcp_presets.py` are broken.** `@browserbase/mcp-server` and `@firecrawl/mcp-server` 404 on npm (real ones: `@browserbasehq/mcp`, `firecrawl-mcp`); `python -m mcp_server_playwright` doesn't exist (real: `@playwright/mcp`); Puppeteer is archived.

`★ Insight ─────────────────────────────────────`
- "Browser tools" are really three orthogonal axes: a **driver** (the tool surface the agent sees, e.g. Playwright MCP), a **host** (where Chrome runs: local, or a cloud like Browserbase/Steel), and **web data** (search/scrape APIs like Firecrawl). Most cloud browsers expose a CDP websocket, and Playwright MCP accepts `--cdp-endpoint`, so `playwright@browserbase` gives the agent *identical tool names* regardless of host — prompts and skills become portable.
- Video verification can't rely on launch flags anymore: Playwright MCP removed `--save-video`; video is now an agent-invoked tool. If the SDK owns the browser, the SDK can record independently of the agent — evidence shouldn't depend on the agent remembering to press record.
`─────────────────────────────────────────────────`

## 1. The registry: what goes in it

Pinned versions (`npm view`, 2026-10-16). Never `@latest`: Playwright MCP removed flags within 0.0.x.

**Tier 1 — the minimal set that covers every facet**

| String | Mount | Credentials | What it adds |
|---|---|---|---|
| `playwright` | stdio `@playwright/mcp@0.0.83`; always `--headless --isolated --output-dir=<artifacts>` | none | navigate, click, snapshot, screenshot, console, network, tabs, upload; `--caps=devtools` adds video + trace tools; `storage` adds cookies |
| `chromedevtools` | stdio `chrome-devtools-mcp@1.11.0`; `--headless --isolated --no-usage-statistics` | none (needs Chrome) | perf traces, Lighthouse, heap snapshots, `.mp4` screencast |
| `browserbase` | remote `https://mcp.browserbase.com/mcp`, Bearer header (stdio repo archived 2026-07) | `BROWSERBASE_API_KEY` | NL `act/observe/extract` (hosted pays the model), stealth, proxies, cloud replay + MP4 |
| `firecrawl` | stdio `firecrawl-mcp@3.30.2` or remote `https://mcp.firecrawl.dev/v2/mcp` Bearer | `FIRECRAWL_API_KEY` | search, scrape, map, crawl, extract, interact (27 tools); `firecrawl:search` → `firecrawl_search` only |

**Tier 2 — add on request:** search (`exa-mcp-server@3.4.2`, `tavily-mcp@0.2.22`, `@brave/brave-search-mcp-server@2.1.4`, Parallel remote — free without key, `@perplexity-ai/mcp-server@1.3.0`, `linkup-mcp-server@3.4.0`); scrape/extract (Jina remote, `@apify/actors-mcp-server@0.18.4` — env is `APIFY_TOKEN`, not the preset's name, `@brightdata/mcp@3.1.0` — use stdio, its remote puts the key in the URL); cloud browsers (Steel `github:steel-dev/steel-mcp-server` pinned to a tag, Browserless remote Bearer, Browser Use Cloud, Skyvern with `lean` scope header — full is 117 tools, Notte, Anchor); CLI+skill drivers (`@playwright/cli@0.1.22`, `browse@0.11.2`, `agent-browser@0.39.1`).

**Excluded with reasons recorded:** Kernel and Cloudflare (remote is OAuth-only — headless can't complete it), Hyperbrowser/BrowserMCP (stale 2025), Puppeteer (archived), dev-browser (no Windows), Lightpanda (AGPL, Linux-only), `airtop-mcp` (unknown maintainer). Node floors matter: `agent-browser`, Linkup and Browserless need Node ≥ 24; this machine runs 22.12.

**String grammar:** `<tool>[:<facet>,<facet>][@<host>]` — `"firecrawl:search"`, `"playwright"`, `"playwright@browserbase"`. A bare facet (`"search"`, `"browser"`) resolves through a default preference list. Facets map to exact MCP tool names. Parsing is deterministic (closed enums, "did you mean…" on unknowns); never use an LLM to parse at launch time.

## 2. The code shape

```python
result = await run_opencode_browser_thread(
    "Open http://localhost:3000, sign up, report any broken step.",
    api_key=deepseek_key, model="deepseek/deepseek-v4-pro", workspace=repo,
    tools=["playwright", "firecrawl:search"],
    tool_keys={"firecrawl": firecrawl_key},   # per call, never os.environ, scrubbed from errors
)
result.thread_id, result.text, result.tool_calls, result.artifacts
```

```
tools strings ─► BrowserToolRegistry.resolve ─► McpServerSpec[]  (neutral; secrets by NAME only)
             ─► <Harness>MountCompiler.compile ─► MountPlan{env_overlay, argv options, home files, allow rules}
             ─► existing <Harness>ThreadRun.execute + CliRunner (unchanged)
             ─► wire reader + tool-call reader ─► BrowserThreadResult
```

**Naming:** `tools=`/`tool_keys=` go on all nine existing functions, because a continue must re-mount tools exactly as it re-passes `skills`. The browser entry point is `run_/continue_/fork_<harness>_browser_thread`, which follows the `<verb>_<harness>_thread` rule you set in #1036 and adds browser defaults: artifacts folder, headless+isolated flags, a short "how to verify" skill, a longer timeout. Your `launch_opencode_with_browser_tools` works as a name too, but I'd keep one pattern; that's your call.

**Placement (AGENTS.md):** enums in `lib/enums/browser_tools.py`; records (`BrowserToolDefinition`, `McpServerSpec`, `MountPlan`, `BrowserArtifact`) in `lib/dataclasses/browser_tools.py`; pinned versions and URLs in `lib/constants/browser_tools.py`; the resolver in `lib/registries/browser_tools.py`; one `mounts.py` per harness under `harnesses/native/<h>/`. The neutral `McpServerSpec` fields: `id` (`^[a-z][a-z0-9]{0,30}$`: Gemini forbids `_`, Codex forbids `.`), `transport`, `command`, `cwd`, `env` (literals only), `secret_env` (names only; values travel in the child env), `url`, `headers`, `bearer_env`, `header_env`, `tools` (exact names), `startup_timeout_s`, `tool_timeout_s`, `required`.

## 3. Mounting into each harness

| Harness | Per-call channel | Secret path | Headless allow rule | Tool name the model sees |
|---|---|---|---|---|
| **opencode** | add `mcp` + `permission` to the existing `OPENCODE_CONFIG_CONTENT` | server inherits the child env | `{"pw_*":"allow", …denies after}` | `pw_browser_navigate` |
| **Claude Code** | `--mcp-config <json>` `--strict-mcp-config` | `${VAR}` in config, value in env | `--allowedTools "mcp__pw__*"` `--permission-prompts none` | `mcp__pw__…` |
| **Codex** | `-c 'mcp_servers.pw={…}'` `--ignore-user-config` | `env_vars=["K"]` (Codex scrubs env — the only per-server isolation) | `default_tools_approval_mode="approve"`, else `exec` **denies** | `mcp__pw__…` |
| **Gemini** | temp `GEMINI_CLI_SYSTEM_SETTINGS_PATH` + `--allowed-mcp-server-names` + `--skip-trust` | `"env":{"K":"$K"}` **required** (Gemini strips key-like vars) | `trust:true` per server; default is **deny** | `mcp_pw_…` |
| **Grok** | **file only**: `$GROK_HOME/config.toml` `[mcp_servers.pw]` with `${K}` refs + compat-off vars | `${K}` expanded at load | `--allow "MCPTool(pw__*)"` | via `search_tool`/`use_tool` only |
| **Muse** | `$XDG_CONFIG_HOME/muse/settings.json` `mcpServers`, shape **unverified** | `WSLENV` (unverified) | unknown; LLM approval judge | unknown |

**The hard parts, by harness:**
1. **opencode** is easiest — the code already builds the inline config. Traps: `{env:VAR}` substitution is unescaped text (a key containing `"` breaks the JSON, so inherit instead), and a failed MCP server only logs; the run continues and the SDK must check `tool_use` events.
2. **Grok** has no `-p` argv/env channel, and its private home is shared per workspace. Two concurrent calls with different tool sets would race on `config.toml` (the existing EC-27 class). Fix: hold a per-home lock for the run's duration now; move to ACP `session/new mcpServers` later. Also: switch to `--output-format=streaming-json` to see tool calls, and handle the first-prompt MCP handshake race.
3. **Muse** isn't MCP-ready: one bad entry disables all MCP, and the WSL distro has no Linux Node (remote MCP servers sidestep that). First step: `muse exec --provider echo --json` against a test `settings.json` — a free, model-free check.
4. **Secret blast radius (all harnesses except Codex/Gemini).** In Claude, Grok, and opencode every MCP server — and the agent's own shell — can read every key in the env, including the harness key (`XAI_API_KEY`). Mitigation: a tiny `lib/process` env-filter launcher used as each server's `command`.

`★ Insight ─────────────────────────────────────`
- None of the six harnesses fails the run when a required MCP server dies at startup (except Codex with `required=true`). A "browser verification" run could silently finish with no browser. The SDK must verify independently: parse each harness's tool-call events and raise a closed code like `browser.tools_unavailable` when zero browser tool calls happened against a required server.
- Launch servers from an SDK-owned tool cache, not npx: `npm install --prefix ~/.vidbyte/tools/<name>@<ver>` once, then `node <abs>/cli.js`. That pins supply chain, avoids npx's first-run download blowing the 30 s MCP startup timeout, and dodges `npx.cmd` — which #1036's launcher already refuses.
`─────────────────────────────────────────────────`

## 4. Lifecycle concerns every launch must handle

- **Workspace pollution:** Playwright writes `.playwright-mcp/` into the workspace unless `--output-dir` is set, violating #1036's "nothing written into the workspace" invariant. Route all artifacts to a per-call folder outside the workspace and list them in the result.
- **Isolation:** Playwright and Chrome DevTools MCP are headed by default and share profiles; always pass headless + isolated + a per-call user-data-dir + free ports.
- **Cloud cost:** cloud browsers bill until released; the SDK should own session teardown (and, if it creates the session, it can download the recording after).
- **Tools with their own LLM:** self-hosted Browserbase needs `GEMINI_API_KEY`; Browser Use and Stagehand need a model key. Pass the caller's or hide those tools.

**Phasing:** (0) fix the Grok leak, replace broken presets → (1) registry + opencode → (2) Claude, Codex, Gemini once their thread functions exist → (3) Grok with file + lock → (4) SDK-owned cloud sessions and recording → (5) Muse after the echo probe.

**Follow-ups:** the Grok compat fix is two env vars in `vidbyte/harnesses/native/grok/threads.py` (plus the skills equivalent) and could be its own small PR today. All research reports, including Grok's documented MCP schema and permission grammar, are saved under `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\1da32edd-ec0f-4839-ba1f-52db538ed13c\scratchpad\readmes\` and the MCP canary under `...\scratchpad\probe\`. Want this as a `/create-design` doc in `docs/pre-design/`? I can write it.
`````

#### C.0.2 Answer to Prompt 2 (verbatim, "Next steps" omitted) — the answer the user endorsed in Prompt 3

`````markdown
## 1. The registry, ranked by measured adoption

A third research pass measured 45 live tools by npm weekly downloads (week of Oct 6–12), PyPI `last_week`, and GitHub stars. I re-ran 10 of the download counts myself; all 10 matched exactly. npm and PyPI counts aren't directly comparable.

**Top 20 — seed now:**

| # | `tools=` string | What it is | Mount | Credentials | Weekly dl |
|---|---|---|---|---|---|
| 1 | `playwright` | Microsoft's local driver: snapshot, click, type, tabs, console, network; video + trace via `--caps=devtools` | stdio `@playwright/mcp@0.0.83` | – | 6.40M npm |
| 2 | `agent-browser` | Vercel's Rust driver: profiles, HAR, video, `-p` switch to Browserbase/Kernel/BrowserUse | CLI+skill or `agent-browser mcp` | – (Node ≥ 24) | 1.73M npm |
| 3 | `browseruse` | Browser Use: DOM+vision agent | stdio `uvx --from 'browser-use[cli]' browser-use --mcp`; or cloud remote | LLM key | 1.61M PyPI |
| 4 | `chromedevtools` | Google's driver: perf traces, Lighthouse, heap, `.mp4` screencast | stdio `chrome-devtools-mcp@1.11.0` | – (needs Chrome) | 1.31M npm |
| 5 | `playwrightcli` | Microsoft's token-efficient CLI for coding agents | CLI+skill `@playwright/cli@0.1.22` | – | 1.06M npm |
| 6 | `crawl4ai` | OSS local crawler: md, screenshot, PDF, JS, deep crawl | Docker server, MCP over SSE | optional LLM | 305K PyPI |
| 7 | `scrapling` | stealth local scraper with browser sessions | stdio `scrapling mcp` | – | 240K PyPI |
| 8 | `fetch` | official reference server: URL → markdown, no JS | stdio `uvx mcp-server-fetch` | – | 230K PyPI |
| 9 | `firecrawl` | search, scrape, map, crawl, extract, interact (27 tools) | stdio `firecrawl-mcp@3.30.2` / remote Bearer | `FIRECRAWL_API_KEY` | 129K npm |
| 10 | `midscene` | ByteDance vision agent + NL assertions | CLI+skill (MCP retired at 1.9.8) | `MIDSCENE_MODEL_*` | 66K npm |
| 11 | `browserbase` | cloud Chrome + NL `act/observe/extract`, stealth, MP4 replay | **remote** `https://mcp.browserbase.com/mcp` (stdio repo archived) / `browse` CLI | `BROWSERBASE_API_KEY` | browse 13.8K; Stagehand lib 1.64M |
| 12 | `duckduckgo` | keyless search | stdio `uvx duckduckgo-mcp-server` | – | 27.8K PyPI |
| 13 | `browserstack` | real devices + cross-browser grid, test authoring, a11y | stdio `@browserstack/mcp-server@2.2.3` | `BROWSERSTACK_USERNAME`/`_ACCESS_KEY` | 25.1K npm |
| 14 | `tavily` | search/extract/map/crawl | stdio `tavily-mcp@0.2.22` | `TAVILY_API_KEY` | 21.9K npm |
| 15 | `brave` | web/news/image/local search | stdio `@brave/brave-search-mcp-server@2.1.4` | `BRAVE_API_KEY` | 21.5K npm |
| 16 | `exa` | neural search + fetch | stdio `exa-mcp-server@3.4.2` / remote Bearer | `EXA_API_KEY` | 19.0K npm |
| 17 | `apify` | thousands of scrapers ("Actors") | stdio `@apify/actors-mcp-server@0.18.4` | `APIFY_TOKEN` | 17.1K npm |
| 18 | `brightdata` | search, scrape, scraping browser + proxies | stdio `@brightdata/mcp@3.1.0` (remote leaks key in URL) | `API_TOKEN` | 16.2K npm |
| 19 | `perplexity` | answer engine: ask/reason/research | stdio `@perplexity-ai/mcp-server@1.3.0` | `PERPLEXITY_API_KEY` | 16.1K npm |
| 20 | `devbrowser` | Puppeteer scripts via daemon | CLI+skill (**no Windows**) | – | 12.0K npm |

**Also in the registry (tier 2/3), by category:**
- **Testing grids:** `wdio` (`@wdio/mcp` 4.0.0 — Chrome/Firefox/Edge/Safari, Electron, iOS/Android via Appium, reaches Sauce/LambdaTest), `selenium` (`@angiejones/mcp-selenium`), `saucelabs` (remote, Basic header).
- **Cloud browsers:** `steel` (pin `github:steel-dev/steel-mcp-server#<tag>`), `browserless` (remote Bearer; SSPL), `kernel` (`@onkernel/cli`; its MCP is OAuth-only), `agentcore` (AWS Bedrock AgentCore Browser, `AGENTCORE_ENABLE_TOOLS=browser` + AWS creds), `anchor`, `notte`, `skyvern` (send scope `lean`; full is 117 tools).
- **Search:** `searxng` (self-hosted), `linkup`, `kagi`, `parallel` (remote, free without key), `jina` (remote; read without key).
- **Scrape:** `oxylabs`, `zenrows` (set `ZENROWS_AUTO_SIGNUP=false` — its stdio server auto-creates an account), `spider`, `scrapegraph`.
- **Computer use (desktop):** `cuadriver` (trycua `cua-driver mcp`, macOS/Windows/Linux desktop control), `e2bdesktop` (library; needs a wrapper).
- **Harness flags, not tools:** Claude Code `--chrome` (real Chrome via extension; claude.ai login only, no WSL).

**Excluded with recorded reasons:** deprecated/archived (Puppeteer reference — still 24K/wk, old Brave server, stdio Browserbase MCP, Midscene MCP, E2B MCP, Octomind, Cloudflare Playwright MCP); stale >12 months (Hyperbrowser MCP, BrowserMCP, Shortest, MultiOn); look-alikes (npm `browser-use` is someone else's); pivoted (Magnitude is now an inference engine).

**String grammar:** `<tool>[:<capability>,…][@<host>]`. `"firecrawl:search"` enables only `firecrawl_search`; `"playwright@browserbase"` runs Playwright's tools against a Browserbase cloud browser; a bare `"search"`/`"browser"` resolves through a default preference.

`★ Insight ─────────────────────────────────────`
- Adoption is moving from MCP servers to **CLI + skill**: Microsoft's own README recommends `playwright-cli` over its MCP for coding agents, agent-browser (1.7M/wk) is CLI-first, and Midscene dropped MCP entirely. So the registry needs **two delivery routes per tool** — MCP mount, or CLI + skill — and #1036's existing `skills=` parameter is already half of the second route.
- The tools rot fast. Four entries from my first research pass were stale on checking (Browserbase stdio archived, Hyperbrowser stale, Midscene MCP retired, Magnitude pivoted). A registry without a nightly freshness check will decay the way `mcp_presets.py` did.
`─────────────────────────────────────────────────`

## 2. What actually happens under the hood

Take `run_opencode_browser_thread("Sign up on localhost:3000 and report broken steps", tools=["playwright", "firecrawl:search"], tool_keys={"firecrawl": key}, ...)`.

**The process tree it creates:**

```
python (your asyncio code)
└─ opencode run --format=json --dir=<ws> --model=<m>     ← CliRunner child: own process group (POSIX) / taskkill tree (Windows)
   ├─ node <toolcache>/@playwright/mcp@0.0.83/cli.js --headless --isolated --user-data-dir=<call>/profile --output-dir=<call>/artifacts
   │  └─ chrome --headless …        ← started on the FIRST browser tool call; on POSIX it is DETACHED (own process group)
   └─ node <toolcache>/firecrawl-mcp@3.30.2/dist/index.js  ──HTTPS──► api.firecrawl.dev
```

Three protocols are stacked: **SDK↔harness** is one argv + env overlay in, JSON lines out (#1036's `CliRunner`, unchanged). **Harness↔tool** is MCP: the harness is an MCP *client* that starts each server as a child and speaks JSON-RPC over that child's stdin/stdout (or HTTPS for a remote server). **Tool↔browser** is the Chrome DevTools Protocol.

**Phase A — SDK preparation (Python, before any process starts)**

1. **Validate.** `NativeThreadRequest` checks prompt, key, workspace, model (as today). A new `BrowserToolRequest` checks the `tools` strings and `tool_keys`. An unknown string fails here with "unknown tool 'playwrite', did you mean 'playwright'" — before any process or file exists.
2. **Resolve.** `BrowserToolRegistry` maps `"firecrawl:search"` to a pinned definition: package `firecrawl-mcp@3.30.2`, entry point, required env `FIRECRAWL_API_KEY`, allowed tools `("firecrawl_search",)`. Output: neutral `McpServerSpec` records that name secrets by **variable name only**.
3. **Preflight.** `ToolCache.ensure` runs `npm install --prefix ~/.vidbyte/tools/firecrawl-mcp@3.30.2` once per version, checks Node ≥ 22 and that Chrome exists. Later calls start servers with `node <abs path>`: exact version, no npx download eating the harness's 30 s MCP startup timeout, no `npx.cmd` (which #1036's launcher refuses).
4. **Per-call folder outside the workspace:** `profile/` (fresh browser profile) and `artifacts/` (screenshots, video, traces).
5. **Compile.** `OpencodeMountCompiler` turns the specs into opencode's native form: an `mcp` block and a `permission` block merged into the `OPENCODE_CONFIG_CONTENT` the code already builds, plus `FIRECRAWL_API_KEY` in the child's env overlay. The value is registered with `errors.register_secret` so any error text scrubs it.

**Phase B — harness boot (inside opencode)**

6. opencode merges its config layers (inline last), starts both MCP servers, and does the MCP handshake with each:
   ```
   opencode → playwright-mcp   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{…}}
   opencode → playwright-mcp   {"id":2,"method":"tools/list"}        → ~25 tool schemas
   ```
   It registers them as `playwright_browser_navigate`, `firecrawl_firecrawl_search`, etc. The permission block denies every Firecrawl tool except search, so the model never sees the others.

**Phase C — the agent loop**

7. The model gets the prompt plus every tool schema and answers with a tool call: `playwright_browser_navigate {"url":"http://localhost:3000"}`.
8. opencode checks permission. In `opencode run`, an "ask" is auto-rejected, which is why the compiler emits explicit `allow` rules. Then it forwards the call:
   ```
   opencode → playwright-mcp   {"id":7,"method":"tools/call","params":{"name":"browser_navigate","arguments":{"url":"…"}}}
   playwright-mcp → chrome     (first call: launch Chrome) CDP Page.navigate …
   playwright-mcp → opencode   {"id":7,"result":{"content":[{"type":"text","text":"Page URL: …\n- button \"Sign up\" [ref=e12]\n- textbox \"Email\" [ref=e15] …"}]}}
   ```
   That result is an **accessibility snapshot**: the page as a text tree with stable refs. The model's next call is `browser_click {"ref":"e12"}`. This is how an agent "uses the app like a user" without vision: it reads the page structure, not pixels.
9. The loop repeats, mixing in `firecrawl_search` when it needs outside information. opencode prints one JSON line per event, including `{"type":"tool_use","part":{"tool":"playwright_browser_click","state":{…}}}`.

**Phase D — teardown and result**

10. **Normal end:** opencode goes idle and exits, closes the MCP servers' stdin, and Playwright closes Chrome. **Timeout:** #1036's `ProcessStopper` stops the tree (POSIX: SIGTERM to the group, wait, SIGKILL; Windows: `taskkill /T /F`). **Cancel:** the SDK stops the tree, then re-raises `CancelledError`.
11. **SDK read:** the existing `OpencodeWire.read` returns thread id and final text; a new `ToolCallReader` collects the `tool_use` events into `tool_calls`; the artifacts folder is listed into `artifacts`; a browser reaper kills any Chrome still using this call's `profile/` dir. It returns `BrowserThreadResult`.

**Three under-the-hood facts that shape the design:**
- **A continue gets a fresh browser.** MCP servers live only as long as the harness process. `continue_opencode_browser_thread` restores the *conversation* from opencode's database, but the browser starts over with no cookies. To keep login state across calls, persist the profile per thread (`--user-data-dir=<sdk>/profiles/<thread_id>`) or use a cloud context (Browserbase `contextId`).
- **Chrome can escape the tree kill.** I checked Playwright's source (`processLauncher.js:111`, `detached: process.platform !== "win32"`): on Linux and macOS, Chrome leads its own process group, so `ProcessStopper`'s group SIGKILL misses it. Only Playwright's SIGTERM handler closes it, and only if that finishes inside the grace period. That's why step 11 has a reaper keyed on the per-call profile dir. An SDK-owned browser (below) removes the problem entirely.
- **Missing tools don't fail the run.** opencode, Claude, Gemini, and Grok all continue if a server fails to start. The SDK must check `tool_calls` itself and raise `browser.tools_unavailable` when a required server never connected.

`★ Insight ─────────────────────────────────────`
- The secret boundary is the environment, not the file system. The design keeps keys off argv and disk, but in Claude, Grok, and opencode every MCP server inherits the harness's whole env — the Firecrawl server can read `XAI_API_KEY`, and the agent's shell can read `FIRECRAWL_API_KEY`. Only Codex (`env_vars` allowlist) and Gemini (strips key-like names) isolate. A small `lib/process` launcher used as each server's `command` (keep listed vars, then exec the real server) closes this.
- The "SDK-owned browser" pattern (`playwright@<host>`) fixes several problems at once. The SDK starts Chrome locally, or creates a Browserbase/Steel session via their API, and passes the CDP address via `--cdp-endpoint`. The SDK then owns Chrome's PID (no orphans), records the session itself (evidence independent of the agent), and always releases cloud sessions (no runaway bill).
`─────────────────────────────────────────────────`

## 3. Adding it for every harness

**The only harness-specific code is two small pieces; everything else is shared:**

```python
class MountCompiler(Protocol):                     # one per harness: harnesses/native/<h>/mounts.py
    def compile(self, servers: tuple[McpServerSpec, ...], context: MountContext) -> MountPlan: ...

class ToolCallReader(Protocol):                    # one per harness: harnesses/native/<h>/wire.py
    def read(self, outcome: CliOutcome, names: Mapping[str, ToolRef]) -> tuple[BrowserToolCall, ...]: ...

@dataclass(frozen=True, slots=True)                # lib/dataclasses/browser_tools.py
class MountPlan:
    env_overlay: Mapping[str, str]       # the ONLY place secret values live
    options: tuple[CliOption, ...]       # extra argv flags (allow rules, config flags)
    config_patch: Mapping[str, object]   # merged into an inline config the harness already builds
    files: tuple[PlannedFile, ...]       # written only into the SDK's private home/temp dir, never holding a secret
    tool_names: Mapping[str, ToolRef]    # harness-visible name → (server, tool), for reading tool calls back
```

The shared main function is the same for every harness: resolve → preflight → compile with that harness's compiler → run the **existing** `<Harness>ThreadRun.execute` with the plan → read tool calls → reap → return.

Here is the **same input** (`playwright` + `firecrawl:search`) compiled for each harness:

**opencode** (ready now; thread functions on `main`). Inline config, secret by inheritance, permission rules (last match wins):
```json
OPENCODE_CONFIG_CONTENT = {"provider": {...existing...},
  "mcp": {"playwright": {"type":"local","command":["node","<tc>/@playwright/mcp@0.0.83/cli.js","--headless","--isolated","--user-data-dir=<call>/profile","--output-dir=<call>/artifacts"],"timeout":60000},
          "firecrawl":  {"type":"local","command":["node","<tc>/firecrawl-mcp@3.30.2/dist/index.js"]}},
  "permission": {"playwright_*":"allow","firecrawl_*":"deny","firecrawl_firecrawl_search":"allow","webfetch":"deny","websearch":"deny"}}
env overlay: FIRECRAWL_API_KEY=<key>      # NOT {env:…} — opencode pastes it unescaped into the JSON
tool calls: {"type":"tool_use","part":{"tool":"playwright_browser_click",...}}
```

**Claude Code** (PR #1044 is being reshaped into `run_claude_thread`; the compiler adds flags):
```
claude -p --output-format stream-json --verbose
  --mcp-config '{"mcpServers":{"playwright":{"type":"stdio","command":"node","args":[…]},
                               "firecrawl":{"type":"stdio","command":"node","args":[…],"env":{"FIRECRAWL_API_KEY":"${FIRECRAWL_API_KEY}"}}}}'
  --strict-mcp-config                                   # ignore the user's own servers
  --allowedTools "mcp__playwright__*" "mcp__firecrawl__firecrawl_search"
  --disallowedTools WebFetch WebSearch  --permission-prompts none
env: ANTHROPIC_API_KEY, FIRECRAWL_API_KEY, CLAUDE_CONFIG_DIR=<private>
thread verbs: --resume <id>, --resume <id> --fork-session
```

**Codex** (PR #1055 is still the old host shape; first needs `run_codex_thread` on `codex exec --json`):
```
codex exec --json --ignore-user-config -C <ws>
  -c 'mcp_servers.playwright={command="node",args=[…],startup_timeout_sec=60,default_tools_approval_mode="approve",required=true}'
  -c 'mcp_servers.firecrawl={command="node",args=[…],env_vars=["FIRECRAWL_API_KEY"],enabled_tools=["firecrawl_search"],default_tools_approval_mode="approve",required=true}'
  -c 'web_search="disabled"'
```
Without `approve`, `exec` **denies** every MCP call. `required=true` is the only native "fail if the server didn't start" in any harness. Tool calls arrive as `{"type":"mcp_tool_call","server","tool","status"}`. Continue: `codex exec resume <id>`; fork: the app-server `thread/fork` that `vidbyte/agents/codex/fork.py` already uses.

**Gemini CLI** (no SDK support yet):
```
<private tmp>/settings.json  (no secret inside):
{"mcpServers":{"playwright":{"command":"node","args":[…],"trust":true},
               "firecrawl":{"command":"node","args":[…],"env":{"FIRECRAWL_API_KEY":"$FIRECRAWL_API_KEY"},"includeTools":["firecrawl_search"],"trust":true}},
 "tools":{"exclude":["google_web_search","web_fetch"]}}
gemini -p … --output-format stream-json --allowed-mcp-server-names playwright firecrawl --skip-trust
env: GEMINI_CLI_SYSTEM_SETTINGS_PATH=<that file>, GEMINI_API_KEY, FIRECRAWL_API_KEY
```
The `env` mapping is **required** (Gemini strips key-looking vars from servers), server ids can't contain `_`, and without `trust:true` headless denies the call and still exits 0.

**Grok Build** (thread functions on `main`; the hardest one):
```toml
# $GROK_HOME/config.toml  — written by the SDK into its private home; holds references, not values
[mcp_servers.playwright]
command = "node"
args = ["<tc>/@playwright/mcp@0.0.83/cli.js", "--headless", "--isolated", …]
startup_timeout_sec = 60
[mcp_servers.firecrawl]
command = "node"
args = ["<tc>/firecrawl-mcp@3.30.2/dist/index.js"]
env = { FIRECRAWL_API_KEY = "${FIRECRAWL_API_KEY}" }
```
```
grok --single=… --output-format=streaming-json --allow=MCPTool(playwright__*) --allow=MCPTool(firecrawl__firecrawl_search)
     --deny=MCPTool(firecrawl__firecrawl_scrape) … --disable-web-search
env: XAI_API_KEY, GROK_HOME, FIRECRAWL_API_KEY, GROK_CLAUDE_MCPS_ENABLED=0, GROK_CURSOR_MCPS_ENABLED=0
```
Grok-specific: there is **no per-run argv/env channel** in `-p`, so the config must be a file. The private home is shared per workspace, so the SDK must hold a per-home lock for the whole run (later: ACP `session/new mcpServers` removes that). The model reaches MCP tools only through `search_tool`/`use_tool`, so hiding tools means `--deny` rules built from the registry's full tool list. `streaming-json` is required to see which tools ran. The compat vars also fix today's leak.

**Muse Code** (thread functions on `main`; MCP unconfirmed):
The likely channel is `$XDG_CONFIG_HOME/muse/settings.json` → `mcpServers`, in the per-call temp folder #1036 already creates. The binary contains the field names (`transport`, `command`, `env`, `enabled_tools`), but the exact shape is unverified. Three blockers: one bad entry disables all MCP; the WSL distro has no Linux Node, so stdio servers can't start (but **remote** servers — Browserbase, Firecrawl, Exa, Jina — avoid it); approvals go to an LLM judge. Plan: run the free `muse exec --provider echo --json` probe (no model call) to pin the schema; until then, compile Muse to remote-MCP or CLI+skill only, and refuse stdio tools with `browser.mount_unsupported` instead of silently dropping them.

**Other CLIs, one line each:** Kilo reuses opencode's compiler with `KILO_CONFIG_CONTENT`. Amp: `--mcp-config` with `${VAR}`. Cursor CLI: only `.cursor/mcp.json` in the workspace (breaks the no-workspace-writes rule) plus `--approve-mcps --trust`. Goose: `--with-extension` puts env values on argv, so refuse secrets there.

**What a harness can't express is decided up front.** Each compiler declares a capability table (separate startup timeouts, hidden tools, `required`, remote-only). A request a harness can't express fails at validation with a closed failure code, never by silently dropping a tool.

**To add a new harness, five steps:** (1) `run_/continue_/fork_<h>_thread` in the #1036 pattern; (2) `<h>/mounts.py` compiler; (3) the tool-call reader in `<h>/wire.py`; (4) its row in the capability table; (5) tests: golden compile tests (spec → exact argv/env/files), a fake harness that **actually starts** the fake MCP server named in the compiled config and calls one tool offline, and an opt-in live smoke test.

**Where files go (AGENTS.md placement):** `lib/enums/browser_tools.py` (`BrowserTool`, `BrowserCapability`, `McpTransport`, `BrowserHost`), `lib/dataclasses/browser_tools.py` (`BrowserToolDefinition`, `McpServerSpec`, `MountPlan`, `BrowserThreadResult`), `lib/constants/browser_tools.py` (pinned versions, URLs, env names), `lib/registries/browser_tools.py` (resolver), `lib/process/` (tool cache + env-filter launcher), `harnesses/native/hostkit/browser.py` (shared main flow + reaper), `harnesses/native/<h>/mounts.py` per harness.

**Follow-ups (housekeeping):** ship the Grok compat-var fix as its own small PR; replace the 11 broken `mcp_presets.py` entries; turn the research scripts (`npmstats.mjs`, `pypistats.mjs`, `ghstats.sh` in `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\1da32edd-ec0f-4839-ba1f-52db538ed13c\scratchpad\`) into a nightly freshness gate; run the Muse echo probe. If you want this as a design doc, I can write it with `/create-design` into `docs/pre-design/browser-thread-functions.md`.
`````

### Key decisions

- **KD-1 Function names follow `<verb>_<harness>_with_browser`.** Prompt 3: "I want to keep the same "run_opencode_with_browser()", "run_grok_with_browser()", type of function names that we have in the repo". This **replaces** both earlier names: Prompt 1's `launch_opencode_with_browser-tools(tools=)` and the assistant's suggested `run_<harness>_browser_thread` (§C.0.1, §C.0.2). `run_opencode_with_browser` and `run_grok_with_browser` are literal; `run_muse_with_browser` follows the same pattern. Whether the `continue_` and `fork_` verbs exist (`continue_opencode_with_browser`, `fork_grok_with_browser`, …) is an open question below; the existing thread API on `main` has all three verbs for every harness.
- **KD-2 Every harness on `main` gets the functions.** Prompt 3: "integrate these browser tools into every harness that we have so far in the repo". The harness thread functions on `main` are under `vidbyte/harnesses/native/`: **Grok Build (`grok`), opencode (`opencode`), Muse Code (`muse`)** — nine functions `run_/continue_/fork_<harness>_thread` (PR #1036, merged 2026-10-15). Claude Code (PR #1044, open, `[WIP]`) and Codex (PR #1055, open, still the old host-class shape) are **not on `main`**; they are out of this PR, and the design must make adding them later one compiler module plus one tool-call reader each (§C.0.2 §3 shows their compiled forms). `vidbyte/agents/codex/` (CodexAgent over the Codex app-server) is on `main`; whether it counts as a harness here is an open question below.
- **KD-3 Every function has every layer the endorsed design lists.** Prompt 3: "make sure that each function has all layers to it that makes this request possible". The layers, from §C.0.2: (1) validated request records for tools and tool keys; (2) a registry that resolves `tools=` strings deterministically to pinned definitions, with capability filters (`"firecrawl:search"`); (3) per-call tool credentials passed by the caller, never read from `os.environ`, never on argv or in a file, registered as secrets for scrubbing; (4) preflight: an SDK-owned, version-pinned tool install (no `npx @latest`), runtime checks (Node version floor, browser binary); (5) a per-call folder outside the workspace for the browser profile and artifacts; (6) a per-harness mount compiler producing env overlay, argv options, config patch and private-home files; (7) headless permission (allow) rules so tool calls are not auto-rejected, and turning off the harness's own built-in web tools so the run uses the chosen tools; (8) a tool-call reader per harness that records which browser tools ran; (9) a required-tool check that fails with a closed code when a required server never ran; (10) browser cleanup so no Chrome outlives the call; (11) a result record with thread id, text, tool calls and artifacts; (12) closed failure codes with detailed messages in the #1036 `NativeErrorFactory` style.
- **KD-4 The registry is extensive, measured, and pinned.** Prompt 2: "feel like the list of browser tools can be more extensive, feel like there are 15-20 popular ones that exist". Prompt 1: "What are all browser tools that we can implement/have a registry of". The endorsed list is §C.0.2 §1 (top 20 plus tier-2/3 by category, plus the excluded list), backed by §C.9.3. Every registry entry pins an exact version; strings are parsed deterministically; unknown strings fail with a suggestion.
- **KD-5 The harness's own CLI does the agent work.** Carried from #1036 (its request KD-3): the SDK drives the vendor program and never reimplements an agent loop or an MCP client for the harness. The harness is the MCP client; the SDK only compiles configuration and reads output.
- **KD-6 #1036's invariants hold for the browser functions.** The caller's harness key and every tool key never go on the command line, into a file, into `os.environ`, or into an error message; nothing is written into the workspace; every failure raises one `NativeThreadError` with a closed `FailureCode`, likely cause and next step; no approve-everything permission mode is added (the header of `vidbyte/lib/enums/native_threads.py` forbids `bypassPermissions`, `--yolo`, `--auto`, `--always-approve` members).

### Rejected alternatives

- `launch_opencode_with_browser-tools(tools=)` (Prompt 1) and `run_<harness>_browser_thread` (assistant, §C.0.1/§C.0.2) — replaced by Prompt 3's `run_<harness>_with_browser`.
- Launching tool servers with `npx -y <pkg>@latest` — unpinned supply chain, `@playwright/mcp` removed flags inside 0.0.x, first-run download can exceed the harness's 30 s MCP startup timeout, and on Windows `npx` is `npx.cmd`, which #1036's `NativeLauncher` refuses for the harness itself (§C.0.1 Insight).
- An LLM parsing the `tools=` strings — nondeterministic and unverifiable (§C.0.1 §1).
- Secrets through opencode's `{env:VAR}` substitution — it pastes the raw value into the JSON text unescaped; a key containing `"` or `\` breaks the config (§C.9.2 opencode item 3).
- Writing tool config into the workspace (`.mcp.json`, `.grok/config.toml`, `opencode.json`, `.playwright-mcp/`) — breaks #1036's "nothing is written into the workspace" and needs folder trust in Grok (§C.9.2 Grok item 2).
- Approve-everything permission modes (`--always-approve`, `--yolo`, `--auto`, `bypassPermissions`) — forbidden by the existing enum header; per-tool allow rules are used instead.
- Building desktop computer use in this PR — Prompt 3 asks a question about it ("Could we create the same type of agents the same way…?"), answered in the conversation; it is not a build request for this pipeline.

### Constraints and assumptions

- AGENTS.md binds (read it in full): dataclasses in `vidbyte/lib/dataclasses/<domain>.py`; enums in `vidbyte/lib/enums/<domain>.py` exported from `vidbyte/lib/enums/__init__.py`; constants in `vidbyte/lib/constants/<domain>.py`; `vidbyte/lib/` never imports a higher layer; call chains one level deep; narrated main functions; validated frozen dataclasses; files well under 1,000 lines; canonical shared helpers in `vidbyte/lib/`; full local gate `python scripts/run_ci.py` before calling work complete; `docs/` is opaque except named files. There is no CLI in the SDK; never add one.
- No test, gate or agent may call a paid model, a paid API, or a real MCP server from the registry. Tests use offline stand-ins the way `tests/features/harness_threads/fake_harness.py` does (a scripted stand-in that runs as a real child process). A fake MCP server that a fake harness actually starts from the compiled config is the endorsed test shape (§C.0.2 §3 step 5).
- Machine facts (verified in the conversation): Node 22.12.0 is installed; Grok Build 1.0.52 at `C:\Users\422mi\.grok\bin\grok.exe` with its user guide at `C:\Users\422mi\.grok\docs\user-guide\*.md`; opencode 1.18.31; Muse Code 1.0.1 only inside WSL distro `MuseUbuntu1` (`/usr/local/bin/muse`, run with `MUSE_NO_AUTO_UPDATE=1`), which has python3 but no Linux Node; claude 2.1.302, codex 0.163.0, gemini 0.42.0 also installed.
- A **separate pipeline run from another session** is in progress on branch `feat/browser-agent` (worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-browser-agent`, title "BrowserAgent: JevAgent-shaped agent and runtime for long-running browser tasks"). Do not read, edit, or depend on it, and do not use the name `BrowserAgent` for anything in this PR.
- PRs #1044 (Claude) and #1055 (Codex) are open and not on `main`. Do not depend on or edit them.
- The user wants depth, not a stub: "make sure that each function has all layers to it that makes this request possible" (Prompt 3).

### Clarifications and answers

- Q (Prompt 1): "What are all browser tools that we can implement/have a registry of" — A: §C.0.1 §1, extended in §C.0.2 §1 after Prompt 2 asked for 15–20 popular ones; evidence in §C.9.1 and §C.9.3.
- Q (Prompt 1): "how are we going to actually implement something like this for every harness" — A: §C.0.1 §2–§3; Prompt 2 asked for more depth ("explain actually how these functions run under the hood", "how we can add these functions for not only opencode, but grok build, codex, muse, claude code, etc") — A: §C.0.2 §2–§3. Prompt 3 endorsed it ("great, you explained the entire process really well").
- Q (assistant, §C.0.1): use `launch_opencode_with_browser_tools` or `run_<harness>_browser_thread`? — A (Prompt 3): neither; `run_opencode_with_browser()`, `run_grok_with_browser()` "type of function names".

### Terminology

- **harness** — a vendor coding-agent CLI the SDK drives headless: Grok Build (`grok`), opencode (`opencode`), Muse Code (`muse`) on `main`.
- **thread** — one conversation with a harness (vendor term: session), which can be run, continued and forked (#1036).
- **browser tool** — a tool server or CLI that gives the agent browser, search, scrape or crawl abilities (Playwright MCP, Firecrawl, Browserbase, …); one registry entry.
- **capability** (the answers also say "facet") — a named subset of a tool's MCP tools, e.g. `firecrawl:search` → only `firecrawl_search`.
- **mount** — making a tool available inside one harness run through that harness's own config mechanism (inline config, argv flags, private-home file).
- **mount compiler** — the per-harness code that turns neutral tool specs into that harness's mount.
- **tool cache** — an SDK-owned folder of version-pinned tool installs (e.g. `~/.vidbyte/tools/<name>@<version>`), started with `node <absolute path>` rather than `npx`.
- **host** — where the browser runs (local Chrome, or a cloud browser such as Browserbase) as opposed to the **driver** (the tool surface the agent sees).
- **artifacts** — files a run produces as evidence (screenshots, video, traces) in a per-call folder outside the workspace.

### Implementation hints

- Model on PR #1036's code (on `main`): `vidbyte/harnesses/native/{grok,opencode,muse}/threads.py` and `wire.py`; `vidbyte/harnesses/native/hostkit/{errors,launcher,skills}.py`; `vidbyte/lib/process/{argv,runner}.py` (`CliArgv`, `CliRunner`, `ProcessStopper`); `vidbyte/lib/dataclasses/native_threads.py`; `vidbyte/lib/enums/native_threads.py`; `vidbyte/lib/constants/native_threads.py`; `FailureCode` in `vidbyte/lib/enums/failure.py`; `NativeThreadError` in `vidbyte/lib/errors/base.py`; tests in `tests/features/harness_threads/` with `fake_harness.py`.
- Existing per-call channels the browser functions build on: opencode's `OPENCODE_CONFIG_CONTENT` (built by `OpencodeWire.config_content`), Grok's private `GROK_HOME` under `~/.vidbyte/grok-homes/<hash of workspace>` (built by `GrokThreadRun._prepare_home`; shared by every call in one workspace), Muse's per-call `tempfile.mkdtemp()` `XDG_CONFIG_HOME` (built by `MuseThreadRun._prepare_config`, removed however the call ends).
- `CliRunner` starts the child with the caller's environment minus `env_remove`, plus `env_overlay`; POSIX children get `start_new_session=True`; `ProcessStopper.stop_tree` on POSIX sends SIGTERM to the group, waits the grace period, then SIGKILL; on Windows it runs `taskkill /T /F` from the System32 folder; "On Windows, taskkill /T cannot reach a grandchild of a leader that already exited" (`vidbyte/lib/process/runner.py` header).
- Verified in the conversation: Playwright launches browsers with `detached: process.platform !== "win32"` (`playwright-core` 1.56.1 `lib/server/utils/processLauncher.js:108-111`), so on POSIX Chrome leads its own process group and the SDK's group SIGKILL does not reach it; Playwright's own SIGINT/SIGTERM handlers call `gracefullyCloseAll`.
- Verified in the conversation: Grok scans Claude and Cursor MCP sources by default — `~/.grok/docs/user-guide/07-mcp-servers.md:292`: "The Claude and Cursor MCP sources are scanned by default. To disable scanning for a specific vendor, set `[compat.<vendor>] mcps = false` … or the corresponding environment variable (`GROK_CURSOR_MCPS_ENABLED`, `GROK_CLAUDE_MCPS_ENABLED`)"; `26-config-reference.md:122,129`. `vidbyte/harnesses/native/grok/threads.py` sets neither variable today.
- Verified in the conversation: Grok's model reaches MCP tools only through the meta-tools `search_tool` / `use_tool` with the qualified catalog key `server__tool` (`07-mcp-servers.md:205-240`).
- Verified in the conversation (`npm view`, 2026-10-16): `@browserbase/mcp-server` and `@firecrawl/mcp-server` return E404; PyPI `mcp-server-playwright` returns 404; real packages `@playwright/mcp` 0.0.83, `chrome-devtools-mcp` 1.11.0, `@browserbasehq/mcp` 3.0.0, `firecrawl-mcp` 3.30.2, `@playwright/cli` 0.1.22, `agent-browser` 0.39.1 (engines node >=24), `browse` 0.11.2, `firecrawl-cli` 1.26.7 (node >=22), `exa-mcp-server` 3.4.2, `tavily-mcp` 0.2.22, `@apify/actors-mcp-server` 0.18.4 (node >=22), `@brave/brave-search-mcp-server` 2.1.4, `@brightdata/mcp` 3.1.0. Weekly downloads re-checked: `@playwright/mcp` 6,403,349; `chrome-devtools-mcp` 1,305,336; `agent-browser` 1,726,779; `@browserstack/mcp-server` 25,130; `@wdio/mcp` 7,181; `firecrawl-mcp` 129,393; `@midscene/web` 66,120; PyPI `browser-use` 1,607,436, `crawl4ai` 304,918, `mcp-server-fetch` 229,977.
- The existing MCP preset catalog (`vidbyte/lib/config/mcp_presets.py`, registry `vidbyte/tools/mcp/presets.py` `McpPresetRegistry`) serves the SDK's own agent loop through `McpServerConfig`; 11 of its 15 web presets name packages that 404, are deprecated, or are not the vendor's (§C.9.1 §0). Its record `McpPresetDefinition` has no version pin, entry point, per-capability tool names or remote auth style.
- The SDK already has direct API clients for Browserbase search/fetch and Firecrawl scrape (`vidbyte/tools/builtins/operations/clients/{browserbase,firecrawl}.py`, on `HttpTransport`); they are SDK-agent tools, not harness mounts.
- Probe material from the conversation: a stdio MCP canary server at `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\1da32edd-ec0f-4839-ba1f-52db538ed13c\scratchpad\probe\probe_mcp.py` (reports `echo_secret_ok|missing` and `env_inherit_yes|no` through its tool names); saved vendor READMEs in `...\scratchpad\readmes\`; adoption scripts and raw outputs in `...\scratchpad\` (`npmstats.mjs`, `pypistats.mjs`, `ghstats.sh`, `partA_npm.jsonl`, `partB_npm.jsonl`, `pypi.jsonl`, `ghA.txt`, `ghB.txt`).

### Open questions

- **Verbs:** do `continue_<harness>_with_browser` and `fork_<harness>_with_browser` exist next to `run_<harness>_with_browser`? The thread API on `main` has all three verbs per harness, and a continue must re-mount tools because MCP servers live only as long as the harness process (§C.0.2 §2 "A continue gets a fresh browser").
- **CodexAgent:** does "every harness that we have so far in the repo" include `vidbyte/agents/codex/` (an SDK agent over the Codex app-server, on `main`), or only the three harness subpackages under `vidbyte/harnesses/native/`?
- **Seed set:** which registry entries ship in this PR, given that every entry must be verified (package, version, entry point, env names, per-capability tool names)? MCP-mountable tools (stdio or remote with header auth) fit the mount compilers directly; CLI+skill-only tools (`agent-browser` CLI, `@playwright/cli`, `midscene`, `devbrowser`) need a skill route; tools needing Docker (`crawl4ai`), Python `uvx` (`fetch`, `duckduckgo`, `browseruse`, `scrapling`) or OAuth need their own runtime handling.
- **Muse MCP:** what exactly does Muse 1.0.1 accept in `$XDG_CONFIG_HOME/muse/settings.json` `mcpServers`, how does a server get its env inside WSL, and what does headless approval do to an MCP call? Muse's WSL distro has no Linux Node, so stdio npm servers cannot start there; remote MCP servers can.
- **Grok concurrency:** Grok's MCP config must be a file in the private home that every call in one workspace shares; how are concurrent `run_grok_with_browser` calls with different tool sets kept from colliding (a per-home lock held for the run, or another route)?
- **Grok output:** detecting tool calls needs `--output-format=streaming-json` instead of today's `json`; how does `GrokWire.read` change, and does the plain `run_grok_thread` path stay on `json`?
- **Grok compat leak:** the browser path must set `GROK_CLAUDE_MCPS_ENABLED=0` and `GROK_CURSOR_MCPS_ENABLED=0` so only the chosen tools load; whether the plain `run_grok_thread` path also changes in this PR is not something the user asked for.
- **Existing preset catalog:** does the new registry reuse, correct, or stay separate from `McpPresetRegistry` and `mcp_presets.py`?
- **Host layer:** is `"playwright@browserbase"` (SDK-created cloud session passed to the driver as a CDP endpoint, SDK-owned recording and release) in this PR, or a later step? §C.0.1 phasing put it after the per-harness work.
- **Secret isolation:** is the env-filter launcher (each MCP server sees only its own variables) in this PR? §C.0.2 Insight recommends it; without it, every server and the agent's shell see every key in Grok, opencode and Muse runs.
- **Browser state across continue/fork:** fresh profile per call, or a persisted profile per thread?
- **Prompt/skill:** does each `<verb>_<harness>_with_browser` add a short browser skill or instruction (where artifacts go, how to reach Grok's `use_tool`), or pass the caller's prompt unchanged?

### C.9 Research evidence (reports from research subagents run during the conversation)

These are the reports the two answers rest on, reproduced from the research agents' final messages. Facts are tagged VERIFIED/UNVERIFIED (or [V]/[U]) as the agents tagged them. The 2026-10-16 runs called no model and no paid API, installed nothing globally, and changed no user config.

#### C.9.1 Browser tool landscape (research pass 1)

Package names, versions and dates are from `npm view` / PyPI JSON on 2026-10-16; tools, env vars and flags from the npm README (R), a GitHub file (GH, via `gh api`), or vendor docs (D). Everything is VERIFIED unless tagged (U).

**§0. SDK preset audit**

| Preset today | Registry result | Replace with |
|---|---|---|
| `npx -y @browserbase/mcp-server` | E404 | Remote `https://mcp.browserbase.com/mcp` (Bearer) or `npx -y @browserbasehq/mcp@3.0.0` |
| `npx -y @firecrawl/mcp-server` | E404 | `npx -y firecrawl-mcp@3.30.2` |
| `python -m mcp_server_playwright` | PyPI 404 | `npx -y @playwright/mcp@0.0.83` |
| `npx -y @modelcontextprotocol/server-puppeteer` | deprecated; repo `servers-archived` archived | drop |
| `npx -y @modelcontextprotocol/server-brave-search` | deprecated | `npx -y @brave/brave-search-mcp-server@2.1.4` |
| `npx -y @modelcontextprotocol/server-google-search` | E404 | drop |
| `npx -y @exa-labs/mcp-server` | E404 | `npx -y exa-mcp-server@3.4.2` |
| `python -m mcp_server_tavily` | PyPI 404 | `npx -y tavily-mcp@0.2.22` (PyPI `tavily-mcp` is not Tavily's) |
| `npx -y apify-mcp-server` + `APIFY_API_TOKEN` | E404 + wrong env | `npx -y @apify/actors-mcp-server@0.18.4` + `APIFY_TOKEN` |
| `python -m mcp_server_jina_reader` | PyPI 404 | remote `https://mcp.jina.ai/v1` |
| `python -m mcp_server_perplexity` | `mcp-server-perplexity` unofficial (2024-12) | `npx -y @perplexity-ai/mcp-server@1.3.0` |
| `python -m mcp_server_linkup` | PyPI 404 | `npx -y linkup-mcp-server@3.4.0` |
| `python -m mcp_server_serper` | PyPI 404 | community `serper-search-scrape-mcp-server` (stale 2025-02), else drop |
| `python -m mcp_server_duckduckgo` | PyPI 404 | `uvx duckduckgo-mcp-server` (0.7.0) |
| `python -m mcp_server_searxng` | `mcp-server-searxng` stale 2025-04 | `npx -y mcp-searxng@2.6.0` |

**Local drivers**

- **Playwright MCP** — `@playwright/mcp` 0.0.83 (2026-09-28), bin `playwright-mcp`, Apache-2.0, Node ≥ 18. `npx -y @playwright/mcp@0.0.83`; `--port N` gives HTTP at `/mcp`. Tools (R): ~25 core — `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_file_upload`, `browser_take_screenshot`, `browser_console_messages`, `browser_network_requests`, `browser_evaluate`, `browser_run_code_unsafe`, `browser_tabs`, …. `--caps` opt-ins: `network` (route/unroute/state), `storage` (17 cookie and local/session storage tools, storage-state), `devtools` (`browser_start_video`, `browser_start_tracing`, `browser_start_recording`, video chapters, highlight), `vision` (`browser_mouse_*_xy`), `pdf` (`browser_pdf_save`), `testing`, `config`. Flags (GH `program.ts`): `--headless`, `--browser`, `--isolated`, `--user-data-dir`, `--storage-state`, `--output-dir`, `--save-session`, `--viewport-size`, `--allowed-origins/--blocked-origins`, `--cdp-endpoint/--cdp-header`, `--proxy-server`, `--shared-browser-context`, `--secrets`, `--image-responses`, `--snapshot-mode`, `--idle-timeout`, `--no-sandbox`. `--save-video`/`--save-trace` no longer exist in source; video and tracing are now tools under `--caps=devtools`. Artifacts go to `.playwright-mcp/` in the workspace unless `--output-dir` is set (traces under `traces/`, videos `video-{ts}.webm`). Headed by default (headless only on Linux with no DISPLAY); default browser is the system Google Chrome (`channel: 'chrome'`).
- **Playwright CLI** — `@playwright/cli` 0.1.22, bin `playwright-cli` (the unscoped `playwright-cli` is deprecated). `npm i -g @playwright/cli@latest`; `playwright-cli install --skills`. Headless by default; named sessions `-s=` / `PLAYWRIGHT_CLI_SESSION`; `tracing-start`, `video-start x.webm --cursor`, `show` (live dashboard), cookie/storage/route commands; output to `.playwright-cli/`. Microsoft's README recommends CLI+skill over MCP for coding agents.
- **Chrome DevTools MCP** — `chrome-devtools-mcp` 1.11.0 (2026-10-15), bins `chrome-devtools-mcp` and `chrome-devtools`, Node ^20.19 / ^22.12 / ≥ 23. Tools (GH `tool-reference.md`): input (`click`, `fill`, `fill_form`, `upload_file`, `click_at`), navigation (`navigate_page`, `new_page`, `list_pages`), emulation, performance (`performance_start_trace`, `performance_analyze_insight`), network, debugging (`list_console_messages`, `evaluate_script`, `lighthouse_audit`, `screencast_start` → .mp4, `take_snapshot`), memory (heap snapshots), extensions, WebMCP, PWA. Flags: `--headless`, `--isolated`, `--user-data-dir`, `--channel`, `--browser-url/--ws-endpoint/--ws-headers`, `--slim`, `--category-*`, `--allowed-url-pattern`, `--viewport`, `--proxy-server`, `--page-id-routing`, `--no-usage-statistics`, `--no-performance-crux`. CLI `chrome-devtools <tool>` runs against a background daemon (headless+isolated by default). Ships skills in `skills/`. Requires an installed stable Chrome. Shares `~/.cache/chrome-devtools-mcp/chrome-profile` by default.
- **agent-browser (Vercel)** — `agent-browser` 0.39.1, Apache-2.0, Rust binary (Windows/macOS/Linux); npm declares Node ≥ 24. `npm i -g agent-browser && agent-browser install` (Chrome for Testing; Linux `--with-deps`). MCP `agent-browser mcp --tools core|network|state|debug|tabs|react|mobile|all`. Skill `npx skills add vercel-labs/agent-browser`. Env: `AGENT_BROWSER_SESSION`, `_PROVIDER`, `_ALLOWED_DOMAINS`, `_ENGINE` (chrome/lightpanda/obscura), `_PROFILE`, `_ENCRYPTION_KEY`; `chat` needs `AI_GATEWAY_API_KEY`. Artifacts: video (.webm/.mp4, needs ffmpeg), traces, `network har`, annotated screenshots, dashboard with live view on port 4848. `-p` selects Browserbase, Browserless, Browser Use, Kernel or AWS AgentCore.
- **dev-browser** — `dev-browser` 0.2.9, MIT, Puppeteer scripts via daemon; `dev-browser mcp` exposes `dev_browser_run`, `dev_browser_pages`, `dev_browser_browsers`, `dev_browser_stop`, `dev_browser_help`; `dev-browser install-skill --claude|--codex|--agents`. No Windows support; headed by default.
- **Browser Use (OSS)** — PyPI `browser-use` 0.13.11, MIT, Python ≥ 3.11 (npm `browser-use` is an unrelated port). Local MCP `uvx --from 'browser-use[cli]' browser-use --mcp`: `browser_navigate`, `browser_click`, `browser_type`, `browser_get_state`, `browser_scroll`, tab tools, `browser_extract_content`, `browser_get_html`, `browser_screenshot`, session tools, `retry_with_browser_use_agent`; needs `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`; `BROWSER_USE_HEADLESS`. `browser-use --cli-mcp` exposes `browser_exec`, `browser_screenshot`. CLI `uv tool install browser-use`, `browser-use skill install`; by default attaches to the user's real Chrome; `BU_CDP_URL`/`BU_CDP_WS`, cloud via `BU_NAME`.
- **Lightpanda** — GitHub 1.0.1 (2026-10-15), AGPL-3.0; npm wrapper `@lightpanda/browser` 1.6.0; PyPI `lightpanda` 1.0.1. `lightpanda mcp` (stdio) or `--port 9223` HTTP; `serve` CDP 9222; no native Windows (WSL works); telemetry on by default (`LIGHTPANDA_DISABLE_TELEMETRY=true`).
- **Extension bridges** — Playwright `--extension` (Chrome/Edge); `@browsermcp/mcp` 0.1.3 stale (no push since 2025-04).

**Cloud browsers**

- **Browserbase** — Remote MCP `https://mcp.browserbase.com/mcp` (streamable HTTP), `Authorization: Bearer $BROWSERBASE_API_KEY` (GH Stagehand README; docs also show `?browserbaseApiKey=`); the hosted server pays for its Gemini model. Stdio `@browserbasehq/mcp` 3.0.0 (2026-03-31) — repo archived 2026-07; old name deprecated; env `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID`, `GEMINI_API_KEY` (or `--modelName`/`--modelApiKey`); flags `--proxies`, `--advancedStealth`, `--keepAlive`, `--contextId`, `--persist`, `--browserWidth/Height`. Tools: `start`, `end`, `navigate`, `act`, `observe`, `extract` (act/observe/extract call an LLM). CLI `npm i -g browse` (0.11.2, bin `browse`): local or remote with key, daemon sessions `BROWSE_SESSION`, snapshot/click/fill/upload/screenshot/tabs/`network on`; cloud `browse cloud sessions debug` (live view), `downloads get`, contexts, `cloud fetch`, `cloud search`; `browse skills install` (repo `browserbase/skills`). Artifacts: HLS replay + MP4 downloads (D). Free plan 3 concurrent sessions. Library `@browserbasehq/stagehand` 4.2.1 (Node ≥ 22.18) / PyPI `stagehand` 4.2.1, needs a model key.
- **Kernel** — Remote `https://mcp.onkernel.com/mcp`, OAuth 2.1 only (README). Tools `manage_browsers`, `manage_replays` (MP4, paid), `manage_browser_files`, `computer_action`, `execute_playwright_code`, `browser_repl`, `exec_command`, `web_search`. CLI `@onkernel/cli` 0.49.0 (`kernel`) with `KERNEL_API_KEY`.
- **Steel** — MCP not on npm: `npx -y github:steel-dev/steel-mcp-server` (pin a tag; latest release v2.0.1). Env `STEEL_API_KEY`, `STEEL_LOCAL`, `STEEL_BASE_URL`, `STEEL_PROFILE=browse|scrape`, `STEEL_MAX_SESSIONS` (10), `STEEL_SESSION_TIMEOUT_MS`. 16 tools incl. `steel_scrape`, `steel_screenshot`, `steel_pdf`, `steel_session_create/_release`, `steel_navigate`, `steel_snapshot`, `steel_act`, `steel_session_replay`, `steel_session_live_view`. $0.10/browser-hour.
- **Browserless** — Remote `https://mcp.browserless.io/mcp` (Bearer preferred, or `?token=`); `@browserless.io/mcp` 1.39.0, SSPL-1.0, Node ≥ 24, `BROWSERLESS_TOKEN`; tools `browserless_smartscraper`, `_search`, `_map`, `_crawl`, `_performance` (Lighthouse), `_function`, `_export`, `_agent`, `_profiles`, `_sessions` (rrweb replay), `_logs`.
- **Anchor** — Remote `https://api.anchorbrowser.io/v1/mcp`, `/v1/mcp/browser`, `/v1/mcp/actions/{domain}`; OAuth or `anchor-api-key` header.
- **Notte** — Remote `https://api.notte.cc/mcp` Bearer `NOTTE_API_KEY`; PyPI `notte-mcp` 1.8.28 (`python -m notte_mcp.server`); SSPL-1.0.
- **Skyvern** — Remote `https://api.skyvern.com/mcp/` with `x-api-key`; 117 tools by default; scopes `operate` 30, `build` 62, `browser` 54, `lean` 33 via `/mcp/x/<scope>` or `X-Skyvern-Scope`; AGPL-3.0.
- **Browser Use Cloud** — Remote `https://api.browser-use.com/v3/mcp` Bearer; tools `run_session`, `get_session` (live URL), `send_task`, `stop_session`, `list_browser_profiles`; recording off by default (`enableRecording`).
- **Cloudflare Browser Run** — Remote `https://browser.mcp.cloudflare.com/mcp` (OAuth or account API token); `get_url_markdown`, `get_url_screenshot`, `get_url_pdf`, `get_url_json`, `start_crawl`; no click/act. `@cloudflare/playwright-mcp` archived 2026-04.
- **Bright Data** — stdio `npx -y @brightdata/mcp@3.1.0` (bin `mcp`) with `API_TOKEN`; restrict with `GROUPS`/`TOOLS` (32 tools default); remote `https://mcp.brightdata.com/mcp?token=…`; `search_engine`, `scrape_as_markdown`, `extract`, 14 `scraping_browser_*`.

**Search / scrape / crawl**

- **Firecrawl** — stdio `firecrawl-mcp` 3.30.2, Node ≥ 22, `FIRECRAWL_API_KEY` (`FIRECRAWL_API_URL` for self-hosted). Remote `https://mcp.firecrawl.dev/v2/mcp` Bearer (without a key, scrape/search/parse still work, rate-limited); `/v2/mcp-search` serves search tools only. 27 tools: `firecrawl_scrape`, `_search`, `_map`, `_crawl`, `_parse`, `_agent`, `_interact`, `_research_*`, `_monitor_*`. CLI `firecrawl-cli` 1.26.7 (bin `firecrawl`); npm `firecrawl` is the SDK (no bin).
- **Exa** — stdio `exa-mcp-server` 3.4.2, `EXA_API_KEY`; remote `https://mcp.exa.ai/mcp` (OAuth, `?exaApiKey=`, or Bearer); tools `web_search_exa`, `web_fetch_exa`, opt-in `web_search_advanced_exa`, `agent_run` via `?tools=`.
- **Tavily** — stdio `tavily-mcp` 0.2.22, `TAVILY_API_KEY`; remote `https://mcp.tavily.com/mcp/` (`?tavilyApiKey=`, Bearer, or OAuth); `tavily_search`, `_extract`, `_map`, `_crawl`, `_research`; CLI PyPI `tavily-cli` 0.1.8 (`tvly`).
- **Brave** — `@brave/brave-search-mcp-server` 2.1.4, `BRAVE_API_KEY`; `brave_web_search`, `_news_search`, `_image_search`, `_local_search`, `_llm_context`; filter with `BRAVE_MCP_ENABLED_TOOLS`.
- **Jina** — remote `https://mcp.jina.ai/v1`, optional Bearer; `read_url`, `search_web`, `capture_screenshot_url`; `include_tags=` filter.
- **Perplexity** — `@perplexity-ai/mcp-server` 1.3.0, `PERPLEXITY_API_KEY`, or remote `https://api.perplexity.ai/mcp` Bearer; `perplexity_ask`, `_reason`, `_research`.
- **Apify** — `@apify/actors-mcp-server` 0.18.4, `APIFY_TOKEN`, or remote `https://mcp.apify.com` Bearer.
- **Linkup** — `linkup-mcp-server` 3.4.0 (Node ≥ 24), `LINKUP_API_KEY`; remote `https://mcp.linkup.so/mcp` Bearer.
- **Parallel** — remote `https://search.parallel.ai/mcp`, free without key, Bearer for paid; `web_search`, `web_fetch`.
- **SearXNG** — `mcp-searxng` 2.6.0, `SEARXNG_URL`.

**Gotchas the launcher must handle**

1. Pin versions (`@playwright/mcp` removed flags within 0.0.x); refresh pins with a scheduled `npm view` job.
2. Secrets in URLs (Tavily, Exa, Linkup, Bright Data, Browserless, Browserbase document key-in-URL); use header forms; Bright Data remote documents only `?token=`, so use its stdio.
3. OAuth-only remotes (Kernel, Cloudflare) cannot complete headless; record `auth_mode` per entry.
4. Tools that need their own LLM key (self-hosted Browserbase: `GEMINI_API_KEY`; Browser Use local MCP: `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`; Stagehand, Lightpanda `agent`, agent-browser `chat`).
5. Browser downloads: Chrome for Testing 155 ≈ 199 MB linux64, 206 MB win64; headless shell ≈ 125 MB. Playwright MCP needs system Google Chrome, or `npx playwright install chrome`, or `--executable-path`.
6. Headless defaults differ (Playwright MCP, Chrome DevTools MCP, dev-browser are headed by default; Browser Use CLI attaches to the real Chrome) — always pass `--headless`.
7. Shared profiles: a persistent Playwright profile allows one browser at a time; Chrome DevTools MCP shares one profile by default — use `--isolated` or a per-session user-data-dir.
8. Ports: Playwright HTTP 8931, agent-browser dashboard 4848, Lightpanda 9222/9223, Firecrawl HTTP 3000, Brave/Browserless HTTP 8080.
9. Windows: `npx` is `npx.cmd`; dev-browser has no Windows build; Lightpanda WSL-only.
10. Node floors: agent-browser, Linkup, Browserless need ≥ 24; Firecrawl ≥ 22; this machine runs 22.12.
11. Look-alikes: npm `browser-use`, `browserless`, `firecrawl` (no bin), `tavily-cli`; PyPI `tavily-mcp`, `browser-use-mcp`, `perplexity-mcp`.
12. Telemetry on by default: Chrome DevTools MCP (`--no-usage-statistics`, `--no-performance-crux`), Lightpanda.
13. Origin filters are not a security boundary (Playwright `--allowed-origins` says so).
14. Cloud browsers bill until released — call `end`/`release`/`stop` on teardown.

Not verified by pass 1: Bright Data remote header auth; Kernel remote API-key Bearer; Cloudflare token on the browser server; whether Node ≥ 24 packages fail on Node 22; full Lightpanda and Perplexity tool lists; stdio `@browserless.io/mcp`; Steel MCP version (README 3.0.0 vs release v2.0.1); Notte local transport.

#### C.9.2 How each harness mounts tools headless (research pass 2)

Versions: claude 2.1.302, codex 0.163.0, gemini 0.42.0, opencode 1.18.31, grok 1.0.52, muse 1.0.1, kilo 7.5.6. Evidence: a stdio MCP canary (`scratchpad\probe\probe_mcp.py`, reports what the server process receives through its tool names `echo_secret_ok|missing` and `env_inherit_yes|no`) launched directly with `py` and via bare `npx`; Grok via `grok mcp doctor` / `grok inspect` with a temporary `GROK_HOME`; Claude via `claude -p --bare` with a temporary `CLAUDE_CONFIG_DIR` and `ANTHROPIC_BASE_URL=http://127.0.0.1:9` (only `system/init` is emitted, then it fails). No model turn ran. Tags: [V: source] verified in source, [V: probe] checked by a local probe, [U] unverified.

**1. opencode 1.18.31** (anomalyco/opencode@v1.18.31; O = packages/opencode/src, C = packages/core/src)
1. Schema [V: C/v1/config/mcp.ts:6-59] — local `{"type":"local","command":[argv…],"environment":{},"cwd"?,"enabled"?,"timeout"?}` (ms); remote `{"type":"remote","url","headers"?,"oauth"?:{…}|false,"enabled"?,"timeout"?}` (no transport key; tries StreamableHTTP then SSE, O/mcp/index.ts:269-283); `{"enabled":false}` alone turns off a named global server.
2. Channels — `OPENCODE_CONFIG_CONTENT` merges after global and project files; `OPENCODE_PERMISSION` merges last (O/config/config.ts:482-488, 559-561) [V]. An isolated `opencode mcp list` showed `✓ pw connected` from the env var alone [V: probe]. The user's global servers still load; hide them per name with `enabled:false`, or all with a private `XDG_CONFIG_HOME` (C/global.ts:13; auth lives in XDG_DATA); `~/.opencode/opencode.json` still loads. ACP `session/new` `mcpServers` is also wired (O/acp/service.ts:189-196).
3. Secrets — the server process gets `{...process.env, ...environment}` (O/mcp/index.ts:341-357), so it inherits everything. `{env:VAR}` is replaced as raw text before JSON parsing (O/config/variable.ts:36-38), not JSON-escaped; a missing variable silently becomes `""` [V].
4. Permission — each MCP call does `ctx.ask(...)` (O/session/tools.ts:408); the default ruleset is `"*":"allow"` (O/agent/agent.ts:120); in `run`, an `ask` auto-rejects (O/cli/cmd/run.ts:801-820) [V]. Rule: `"permission":{"playwright_*":"allow"}`; last match wins (O/permission/index.ts:210).
5. Filter — `tools:{x:false}` becomes deny rules placed before the `permission` rules, so a later `pw_*: allow` cancels them (config.ts:567-577, probe) [V]. Use `permission` only, ordered allow-all first then deny: `{"pw_*":"allow","pw_browser_install":"deny"}`.
6. Naming — `playwright_browser_navigate`; `[^A-Za-z0-9_-]` becomes `_` (O/mcp/catalog.ts:117-119) [V].
7. Startup and output — connect timeout `timeout ?? 30000` (index.ts:38); a failed server only gets a log line; the run continues and no JSON event reports it. `--format=json` emits `{"type":"tool_use","part":{"tool":"playwright_…","state":{status,input,output}}}` (run.ts:678-690) [V].
8. Windows — bare `npx` connected [V: probe].
9. Web — `webfetch` is always present; `websearch` only for opencode providers or the Exa/Parallel flags (O/tool/registry.ts:58-64); turn both off with `permission:{webfetch:"deny",websearch:"deny"}` [V].
10. Skills — the `skill` tool exists [V].

**2. Grok Build 1.0.52** (primary source `~/.grok/docs/user-guide`)
1. Schema [V: 07-mcp-servers.md; 26-config-reference.md:395-417] — `[mcp_servers.<name>]` keys `command, args, env, cwd, enabled, startup_timeout_sec (30), tool_timeout_sec, tool_timeouts, url, headers, bearer_token_env_var, bearer_token_file, oauth*`; separate keys `disabled_mcp_servers` and `disabled_mcp_tools = {server=[tools]}` (config-ref:172-182).
2. Channels — no flag; `GROK_CONFIG` "cannot spawn commands" (05-configuration.md:30). (a) `$GROK_HOME/config.toml`, needs no folder trust: doctor connected both probe servers [V: probe]. (b) `$GROK_HOME/plugins/<p>/.mcp.json` (`~/.grok/plugins` "trusted automatically", 09-plugins.md:148, 424) [U for `-p`]. (c) `--agent <file>` with `mcpServers` frontmatter (16-subagents.md:220) [U]. (d) ACP `grok agent stdio` with `session/new mcpServers` / `_meta.pluginDirs` (15-agent-mode.md:197-213), not available on `-p`. Workspace `.grok/config.toml` / `.mcp.json` need folder trust (10-hooks.md:83) and would write into the workspace. Leak in today's SDK [V: probe]: with an empty private `GROK_HOME`, `grok inspect --json` lists the server `wmux` from the user's `~/.claude.json` as enabled (compat defaults on); `GROK_CLAUDE_MCPS_ENABLED=0` turns it off; `GROK_CURSOR_MCPS_ENABLED` is the Cursor equivalent; Claude-skills compat is also on by default; `vidbyte/harnesses/native/grok/threads.py` sets neither variable.
3. Secrets — `env = { PROBE_SECRET = "${PROBE_SECRET_SRC}" }` expanded at load: the probe received the value while the file held only the reference [V: probe]; the doc lists `url, command, args, env, headers` as expanded. The server process inherits Grok's whole environment (canary present; ANTHROPIC/GEMINI keys visible) [V: probe], so `XAI_API_KEY` reaches every MCP server. Remote: `headers={Authorization="Bearer ${T}"}` or `bearer_token_env_var`. `grok mcp list --json` prints the expanded secret to stdout [V: probe].
4. Permission — MCP is not on the never-prompt list (22-permissions:140-150); headless cannot prompt. Rule `--allow "MCPTool(playwright__*)"`; `mcp__playwright__*` also accepted (22:370-374) [V]; deny always wins; `--permission-mode dontAsk` runs only pre-approved tools [V doc].
5. Filter — no per-server allowlist; `disabled_mcp_tools` lives in the config file; `--deny MCPTool(srv__tool)` works per run [V].
6. Naming — catalog key `server__tool` [V doc]; server names `[A-Za-z_][A-Za-z0-9_-]*`, must not end in `_` or contain `__`. The model calls MCP tools only through the meta-tools `search_tool`/`use_tool` [V doc].
7. Startup and output — default 30 s; `MCP_TIMEOUT` (ms) or `GROK_MCP_STARTUP_TIMEOUT_SECS`; server stderr to `$GROK_HOME/logs/mcp/<s>.stderr.log` [V]. First-prompt race: tools "missing on the first prompt because the handshake is still running" (07:452); headless has a "Blocking startup grace" of unknown length (14:304) [U]. Today's `--output-format json` contains no tool calls [V 14:140-175]; `streaming-json` has `tool_call{toolName,rawInput}`; `streaming-messages-json` init has `mcp_servers[].status`.
8. Windows — bare `npx` resolved through PATHEXT [V: probe].
9. Web — `--disable-web-search` ("Disable web search and web fetch tools") [V].
10. Skills — `$GROK_HOME/skills` (the SDK already uses it).

**3. Muse Code 1.0.1** (help output plus `strings` over `muse-bin-1.0.1-R2006.1`)
1. Schema — no `muse mcp` command [V]; the MSP schema export has no MCP fields, so `serve` has no session MCP channel [V: probe]. File `$XDG_CONFIG_HOME/muse/settings.json`, top-level key `mcpServers` [V: strings]; field names in the binary `transport (stdio|streamable-http), command, env, cwd, url, headers, framing, enabled, startup_timeout_sec, enabled_tools, disabled_tools` [V: strings]; exact entry shape [U] (Codex-like). Plugin form `{"id":"x","transport":"stdio","command":["python3","mcp/server.py"]}` [V: embedded doc].
2. Channel — the SDK's per-call private `XDG_CONFIG_HOME`; when set, `~/.config/muse` is not used [V: strings]; `--agents <JSON>` and the string "Agent `mcp.json`" hint at an agent-level route [U].
3. Secrets — the string "only ${USER} and ${HOME} expand" exists [V; which file U]; assume no `${VAR}`; rely on inheritance through `WSLENV` [U].
4. Permission — `--approval-mode untrusted|on-request|never` (default on-request), LLM `--approval-judge` (default on), `--user-input-auto-resolve` [V: help]; what happens to an MCP call headless [U]; allow rules `execution.tool_rules.<id>` exist only in the enterprise policy plane [V: strings].
5–6. Filter `enabled_tools`/`disabled_tools` [V: strings]; a `mcp__` prefix appears [U exact form].
7. Failure — "MCP configuration error in <file>; MCP is disabled for this runtime" [V: string]: one bad entry turns off all MCP.
8. WSL — Ubuntu 24.04 with python3 but no Linux node; PATH includes `/mnt/c/Program Files/nodejs/`, so `npx` would run Windows Node through interop [V: PATH; U whether it works]; secrets must travel through `WSLENV`.
9. Web — `--disable-web-tools` [V: help].
Cheap schema check not yet run: `muse exec --provider echo --json` against a test `settings.json` (the echo provider makes no Meta call).

**4. Claude Code 2.1.302** — schema `{"mcpServers":{"id":{"type":"stdio","command","args","env"}}}`, remote `{"type":"http"|"sse","url","headers","headersHelper"}`, per-server `timeout` ms [V: docs]; `--mcp-config <file|json…>` + `--strict-mcp-config` (init showed only `"source":"dynamic"` servers) [V: probe]; `${VAR}` / `${VAR:-default}` in command, args, env, url, headers [V: docs; probe got `echo_secret_ok`]; servers inherit the full env [V: probe]; `--allowedTools "mcp__playwright__*"` (globs only after a literal `mcp__<server>__`), `--permission-prompts none` denies anything that would prompt [V: help], result carries `permission_denials`; naming `mcp__<server>__<tool>` [V: probe]; a broken server shows `"status":"failed"` in init and the run continues [V: probe]; `MCP_TIMEOUT` ms; Windows bare `npx` [V: probe]; web off via `--disallowedTools WebFetch WebSearch`; skills via `--plugin-dir` "for this session only" [V: help].

**5. Codex CLI 0.163.0** (openai/codex@rust-v0.163.0) — stdio `command,args,env,env_vars,cwd`; HTTP `url,bearer_token_env_var,http_headers,env_http_headers`; shared `enabled,required,startup_timeout_sec,tool_timeout_sec,default_tools_approval_mode,enabled_tools,disabled_tools,tools.<t>.approval_mode`; no SSE [V]. `-c 'mcp_servers.pw={…}'` parsed (`codex mcp get`) [V]; user servers merge in, `exec --ignore-user-config` drops them [V]; ids must not contain `.`. Server env = default allowlist + `env_vars` names (rmcp-client/src/utils.rs:16-58) [V]; no `${VAR}` [U]. `exec` forces approval `Never`: a non-read-only MCP tool is denied ("requires approval, but approval policy is never", core/src/mcp_tool_call.rs:1602) unless `approval_mode="approve"` [V]. `enabled_tools`/`disabled_tools` exact names (codex-mcp/src/tools.rs:63-96); naming `mcp__<server>__<tool>`; defaults 30 s start, 300 s per call; `required=true` fails the run (connection_manager/required.rs:55); `--json` reports `{"type":"mcp_tool_call","server","tool","status",…}` [V]; Windows PATHEXT ok; web off `-c web_search="disabled"`; skills only in workspace or home `.agents/skills`.

**6. Gemini CLI 0.42.0** — `command,args,env,cwd,url,httpUrl,headers,type(stdio|sse|http),timeout,trust,includeTools,excludeTools`, no `enabled` [V]; `GEMINI_CLI_SYSTEM_SETTINGS_PATH=<tmp>.json` highest precedence; `--allowed-mcp-server-names a b`; `GEMINI_CLI_HOME` full isolation; headless in an untrusted folder is fatal, so `--skip-trust` [V]; `$VAR`/`${VAR}`/`${VAR:-d}` interpolation; servers get a sanitized env that drops `KEY|TOKEN|SECRET…` names, so list secrets explicitly `"env":{"K":"$K"}` [V]; non-interactive default DENY (not fatal); allow via `trust:true`, `--allowed-mcp-server-names`, or a `--policy` TOML [V]; naming `mcp_<server>_<tool>` (ids must not contain `_`); 10-minute default timeout; failed server silent, exit 0; `stream-json` reports `tool_use{tool_name}`; web off `"tools":{"exclude":["google_web_search","web_fetch"]}`.

**7. Minor CLIs** — Kilo 7.5.6 `KILO_CONFIG_CONTENT` with opencode's schema [V]; Amp `--mcp-config` with `${VAR}` [V]; Cursor CLI `.cursor/mcp.json` only, headless `--approve-mcps --trust` [V]; Goose `run --with-extension` puts env values in argv [U]; Crush config file only [U]; Cline `--config <dir>` [U].

**Synthesis (pass 2)**

| Harness | Per-run channel | Secret path | Allow rule (headless) | Tool filter | Naming | Platform |
|---|---|---|---|---|---|---|
| opencode | `OPENCODE_CONFIG_CONTENT` (+ private XDG to hide globals) | `{env:K}` or inherit | `permission{"id_t":"allow"}` (default already allow) | permission rules only | `id_tool` | npx ok |
| Grok | file `$GROK_HOME/config.toml` (+ `GROK_CLAUDE/CURSOR_MCPS_ENABLED=0`) | `${K}` (inherit-all) | `--allow MCPTool(id__t)` | `disabled_mcp_tools` / `--deny` | `id__tool` via `use_tool` | npx ok |
| Muse | file `$XDG_CONFIG_HOME/muse/settings.json` [U shape] | `WSLENV` inherit [U] | U | `enabled_tools` [U] | `mcp__…` [U] | WSL, no Linux node |
| Claude | `--mcp-config <json>` `--strict-mcp-config` | `${K}` (inherit-all) | `--allowedTools mcp__id__t` + `--permission-prompts none` | allow list | `mcp__id__tool` | npx ok |
| Codex | `-c mcp_servers.id={…}` + `--ignore-user-config` | `env_vars=["K"]`, `bearer_token_env_var` | `default_tools_approval_mode="approve"` | `enabled_tools` (exact) | `mcp__id__tool` | npx ok |
| Gemini | `GEMINI_CLI_SYSTEM_SETTINGS_PATH` + `--allowed-mcp-server-names` + `--skip-trust` | `"K":"$K"` (required) | `trust:true` / policy TOML | `includeTools` | `mcp_id_tool` | npx ok |

Proposed neutral `McpServerSpec` (every harness but Muse can express all): `id` (`^[a-z][a-z0-9]{0,30}$`), `transport` (`stdio`|`http`), `command` (argv, bare program first), `cwd`, `env` (literals, never secrets), `secret_env` (names only; same name in server), `url`, `headers` (literals), `bearer_env`, `header_env`, `tools` (exact raw names or `None`), `startup_timeout_s`, `tool_timeout_s`, `required`. Not natively expressible everywhere: `required` (Codex only; elsewhere check after the run); separate startup/tool timeouts (Gemini and opencode have one `timeout`); `tools` as a hidden allowlist (Grok still shows tools through `search_tool`; opencode filters only via permission); renaming a variable for the server (not on Codex); Muse unconfirmed.

Hardest blockers (pass 2): (1) Grok `-p` has no argv/env channel; it needs `config.toml` (safe with `${K}`), and the private `GROK_HOME` is shared per workspace by concurrent calls (EC-27 class): key the home by workspace + tool-set hash (breaks resume when tools change) or move Grok to ACP; also set compat-off vars, switch to `streaming-json`, handle the first-prompt race. (2) Muse: schema unconfirmed, one bad entry disables all MCP, no Linux node, LLM approval judge — use CLI+SKILL.md for Muse for now, or verify with the echo provider. (3) Every MCP server inherits the full harness env in Claude, Grok and opencode (harness key and every secret; the agent's shell too); only Codex and Gemini clean it. (4) Gemini and Codex deny by default; every harness but Muse can express a per-server allow without an approve-everything mode. (5) opencode `{env:}` is not escaped. Skills route: Claude per run via `--plugin-dir`; Gemini via `GEMINI_CLI_HOME`; Codex only workspace/home skill dirs; every CLI route needs shell permission (broader than an MCP allow), so MCP is the main route and skills are Muse's fallback.

#### C.9.3 Adoption ranking and additional tools (research pass 3)

Read-only commands, 2026-10-16: npm weekly downloads `curl -s https://api.npmjs.org/downloads/point/last-week/<pkg>` (week 2026-10-06..12); version/date from `https://registry.npmjs.org/<pkg>`; PyPI `last_week` from `https://pypistats.org/api/packages/<pkg>/recent`, version/date from `https://pypi.org/pypi/<pkg>/json`; stars via `gh api repos/<owner>/<repo> --jq '{stars:.stargazers_count,archived,pushed_at,license:.license.spdx_id}'`. Raw outputs in `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\1da32edd-ec0f-4839-ba1f-52db538ed13c\scratchpad\{partA_npm.jsonl,partB_npm.jsonl,discovery_npm.jsonl,pypi.jsonl,ghA.txt,ghB.txt}`. Changes found since pass 1: Browserbase's stdio repo is archived and its README points to the hosted `https://mcp.browserbase.com/mcp`; `hyperbrowser-mcp` has had no release since 2025-04-13; Midscene no longer ships MCP (CLI + skills now); Magnitude pivoted to an inference engine.

Capability codes: nav=navigate/act, snap=accessibility snapshot, shot=screenshot, vid=video, logs=console/network, srch=search, scr=scrape, crawl, ext=extract, dev=real-device/cross-browser, vis=vision acting, NL=natural-language steps.

Tier 1 (seed now):

| # | Tool → artifact | Category | Mount | Key env | Wk dl | ★ |
|---|---|---|---|---|---|---|
| 1 | playwright → `@playwright/mcp` 0.0.83 | local driver | stdio | – | 6,403,349 [N] | 38,243 |
| 2 | `agent-browser` 0.39.1 (Node ≥ 24) | local driver | CLI+SKILL | – | 1,726,779 [N] | 44,100 |
| 3 | `browser-use` (PyPI 0.13.11) | vision/DOM agent | stdio MCP/CLI | LLM key | 1,607,436 [P] | 118,200 |
| 4 | `chrome-devtools-mcp` 1.11.0 | local driver + perf | stdio | – | 1,305,336 [N] | 53,681 |
| 5 | `@playwright/cli` 0.1.22 | local driver | CLI+SKILL | – | 1,062,999 [N] | 14,261 |
| 6 | fetch → `mcp-server-fetch` 2026.10.10 (MIT) | scrape (no JS) | stdio `uvx mcp-server-fetch` | – | 229,977 [P] | 91,314 |
| 7 | duckduckgo → `duckduckgo-mcp-server` 0.7.0 | search, keyless | stdio `uvx duckduckgo-mcp-server` | – | 27,833 [P] | 1,538 |
| 8 | `@browserstack/mcp-server` 2.2.3 (AGPL-3.0-only) | testing grid; nav/dev/a11y/NL tests | stdio; remote mcp.browserstack.com (OAuth, cannot test localhost) | BROWSERSTACK_USERNAME, BROWSERSTACK_ACCESS_KEY | 25,130 [N] | 155 |
| 9 | firecrawl → `firecrawl-mcp` 3.30.2 / `firecrawl-cli` 1.26.7 | scrape-crawl + srch | stdio; remote; CLI | FIRECRAWL_API_KEY | 129,393 / 15,401 [N] | 7,615 (MCP); 192,191 firecrawl |
| 10 | `tavily-mcp` 0.2.22 | search | stdio; remote | TAVILY_API_KEY | 21,864 [N] | 2,433 |
| 11 | `@brave/brave-search-mcp-server` 2.1.4 | search | stdio | BRAVE_API_KEY | 21,507 [N] | 1,504 |
| 12 | `exa-mcp-server` 3.4.2 | search | remote (Bearer or x-api-key) or stdio | EXA_API_KEY | 19,044 [N] | 5,138 |
| 13 | `@apify/actors-mcp-server` 0.18.4 | scrape-crawl | stdio; remote | APIFY_TOKEN | 17,093 [N] | 11,578 |
| 14 | `@brightdata/mcp` 3.1.0 | scrape + srch + browser | stdio; remote | API_TOKEN | 16,203 [N] | 2,678 |
| 15 | `@perplexity-ai/mcp-server` 1.3.0 | search/answer | stdio | PERPLEXITY_API_KEY | 16,084 [N] | 2,573 |
| 16 | browserbase → remote `https://mcp.browserbase.com/mcp` + `browse` 0.11.2 CLI | cloud browser | remote / CLI+SKILL | BROWSERBASE_API_KEY | browse 13,836; stagehand lib 1,640,981 [N] | 25,705 |

Tier 2 (add on request):

| # | Tool → artifact | Category | Mount | Key env | Wk dl | ★ |
|---|---|---|---|---|---|---|
| 17 | `crawl4ai` 0.9.5 (Apache-2.0) | scrape-crawl, local | Docker server; MCP over SSE `http://localhost:11235/mcp/sse` or WebSocket, no streamable HTTP | optional LLM keys | 304,918 [P] | 85,667 |
| 18 | `scrapling` 0.4.15 (BSD-3) | stealth scrape, local | `pip install "scrapling[ai]"` then stdio `scrapling mcp` | – | 240,306 [P] | 88,105 |
| 19 | midscene → `@midscene/web` 1.16.0 (MIT) | vision agent; vis/nav/ext/assert | CLI+SKILL (`npx skills add web-infra-dev/midscene-skills`) | MIDSCENE_MODEL_API_KEY, _NAME, _BASE_URL, _FAMILY | 66,120 [N] | 15,307 |
| 20 | cua-driver (trycua) 0.36.0, MIT | computer use (desktop + browser) | stdio `cua-driver mcp` (installed by cua.ai script) | – | 671,787 [N] for `@trycua/cua-driver` (SDK, no bin; likely dependency-inflated) | 29,966 |
| 21 | `dev-browser` 0.2.9 | local driver | CLI+SKILL | – | 11,994 [N] | 6,668 |
| 22 | `mcp-searxng` 2.6.0 | search (self-hosted) | stdio | SEARXNG_URL | 10,282 [N] | 1,312 |
| 23 | kernel → `@onkernel/cli` 0.49.0 | cloud browser | CLI; remote MCP (OAuth) | KERNEL_API_KEY | 8,325 [N] | 29 / 1,102 |
| 24 | `@wdio/mcp` 4.0.0 (MIT) | testing grid; Chrome/Firefox/Edge/Safari, Electron, iOS/Android via Appium; BrowserStack/Sauce/LambdaTest/TestingBot | stdio `npx -y @wdio/mcp` (`--http` option) | provider creds, optional | 7,181 [N] | 41 |
| 25 | jina → remote `https://mcp.jina.ai/v1` | scrape + srch | remote HTTP, Bearer optional | JINA_API_KEY (for search) | n/a | 882 |

Tier 3 (niche): `@executeautomation/playwright-mcp-server` 1.0.12 (14,310/wk; overlaps official Playwright MCP); `@lightpanda/browser` 1.6.0 (no native Windows); `fetcher-mcp` 0.3.9; `oxylabs-mcp` 0.10.0 (`uvx oxylabs-mcp` or remote with headers; OXYLABS_API_TOKEN or _USERNAME/_PASSWORD); `@agentdeskai/browser-tools-mcp` 2.0.2 (needs extension in real Chrome); `@browserless.io/mcp` 1.39.0 (SSPL); `awslabs.amazon-bedrock-agentcore-mcp-server` 0.2.1 (AgentCore Browser, 25 tools, `uvx …`, `AGENTCORE_ENABLE_TOOLS=browser`, AWS creds); `skyvern` 1.0.56; `@zenrows/mcp` 2.10.2 (set `ZENROWS_AUTO_SIGNUP=false`); `kagimcp` 1.0.2 (KAGI_API_KEY, Python 3.12); `@angiejones/mcp-selenium` 0.2.3 (Chrome/Firefox/Edge/Safari via Selenium; stdio); `mcp-chrome-bridge` 1.0.31 (extension); `linkup-mcp-server` 3.4.0; `notte-mcp` 1.8.28 (SSPL); `scrapegraph-mcp` 1.0.1; `sauce-api-mcp` 1.2.2 + remote `https://mcp.saucelabs.com` (Basic header + `X-Sauce-Region`; SAUCE_USERNAME, SAUCE_ACCESS_KEY); `spider-cloud-mcp` 1.2.2 (SPIDER_API_KEY); steel (`npx -y github:steel-dev/steel-mcp-server`, STEEL_API_KEY); ScrapingBee remote (key only in the query string); Zyte remote (sign-in via client). Library-only, need a wrapper: `nova-act` 3.4.187.0 (NOVA_ACT_API_KEY or IAM); E2B Desktop (`e2b-desktop` PyPI, `@e2b/desktop` npm; E2B_API_KEY). Claude in Chrome (`claude --chrome`) is a harness flag, not a registry tool.

Avoid (pass 3): deprecated — `@modelcontextprotocol/server-puppeteer` (still 24,297/wk) and fork `@hisma/server-puppeteer`, `@modelcontextprotocol/server-brave-search` (22,947/wk), `@browserbasehq/mcp-server-browserbase` and `@browserbasehq/browse-cli` (point to `browse`), `@midscene/mcp` (ended at 1.9.8), `@e2b/mcp-server` (deprecated, archived), `@steel-dev/cli` (now a native binary); archived repos — browserbase/mcp-server-browserbase (so stdio `@browserbasehq/mcp` is unmaintained), OctoMind-dev/octomind-mcp, cloudflare/playwright-mcp; no release in > 12 months — `hyperbrowser-mcp` (2025-04-13), `@browsermcp/mcp` (2025-04-11, still 9,336/wk), `@antiwork/shortest` (2025-04-01), `puppeteer-mcp-server` (2025-03-14), `@tokenizin/mcp-npx-fetch`, `@automatalabs/mcp-server-playwright`, `nova-act-mcp`, `crawl4ai-mcp`, `browser-use-mcp-server`, `mcp-browser-use`, `multion` (2024-10-08), `scrapybara` SDK (2025-05-28); pivoted — magnitudedev/magnitude (`magnitude-mcp` 22/wk); look-alike — npm `browser-use` (webllm/browser-use, 15★); OAuth-only remotes — TestMu AI / LambdaTest `https://mcp.lambdatest.com/mcp`, Cloudflare Browser Rendering; not tools — Anthropic computer-use-demo, openai-cua-sample-app (reference apps); no Azure or Google browser MCP/CLI found.

Not verified (pass 3): Zyte auth and tools; Kernel exact remote URL; whether Scrapybara/MultiOn services still run; ScrapeGraph's hosted endpoint move; `@trycua/cua-driver` and `@antiwork/shortest` counts are probably dependency-inflated; pypistats oxylabs-mcp `last_week` 4,374 > `last_month` 4,016 (impossible, unreliable); Windows behaviour and entry-point names taken from READMEs, not run (Lightpanda's README states no Windows build).

## D. Weighted words

- "every harness" — Prompt 1: "What are all browser tools that we can implement/have a registry of and how are we going to actually implement something like this for every harness"
- "every harness … so far in the repo" — Prompt 3: "want you to integrate these browser tools into every harness that we have so far in the repo"
- "each … all layers" — Prompt 3: "make sure that each function has all layers to it that makes this request possible"
- "same" — Prompt 3: "I want to keep the same "run_opencode_with_browser()", "run_grok_with_browser()", type of function names that we have in the repo"
- "all" — Prompt 1: "What are all browser tools that we can implement/have a registry of"
- "all types" — Prompt 1: "we can programmatically launch "browser based" coding agent sessions where there are all types of use cases"
- "Dont think about use cases now" — Prompt 1: "Dont think about use cases now, just want you  to think through implementation of these functions."
- "more extensive" / "15-20 popular ones" — Prompt 2: "feel like the list of browser tools can be more extensive, feel like there are 15-20 popular ones that exist"
- "actually" — Prompt 2: "explain actually how these functions run under the hood"; Prompt 1: "how are we going to actually implement something like this"
- "not only opencode" — Prompt 2: "explain how we can add these functions for not only opencode, but grok build, codex, muse, claude code, etc"
- "entire" — Prompt 3: "you explained the entire process really well"; "kick off and explain this entire thing with the 'spec-pipelin' to a subagent"
- "programmatically" — Prompt 1: "Then from here we can programmatically launch "browser based" coding agent sessions"
- "pass in strings" — Prompt 1: "and then pass in strings to launch the tools"
