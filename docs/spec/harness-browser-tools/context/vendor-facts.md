# Vendor facts for harness browser tools (S0 vendor scout, 2026-10-16)

Every fact is tagged: `[V: probe]` = checked by a local, model-free probe; `[V: <path>:<line>]` = read in source, docs or binary strings; `[U]` = unverified.
`VP` = `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\1da32edd-ec0f-4839-ba1f-52db538ed13c\scratchpad\vendor-probe`. Probe scripts are in `VP\scripts\`. Raw outputs are in `VP\logs\`, `VP\obs\` and `VP\muse\outputs\muse_probe_root.tgz`. The scripts are listed in `reports/S0-vendor-scout.md`.
Versions: muse 1.0.1 (WSL `MuseUbuntu1`), grok 1.0.52, opencode 1.18.31, Node v22.12.0, Python 3.11, uv 0.11.7. No probe called a real model or a paid API, and no probe used a real key. The only fake credential was `probe-not-a-key`.
"Fake endpoint" means `VP\scripts\fake_llm_server.py`. It is a scripted, stdlib-only OpenAI-compatible server on 127.0.0.1 that replays fixed replies (text or tool calls). It also runs a logging proxy that refuses every request. It is not a model.

## 1. Muse

Setup: every run used `muse exec --provider echo --json`. HOME and all XDG dirs were private under `/tmp/vbprobe-*`, `MUSE_NO_AUTO_UPDATE=1`, and `META_API_KEY` was unset (`VP\scripts\muse_run.sh`).

**Echo provider**
- The echo provider is local. It replies `echo: <prompt>`, makes no Meta call and needs no key. [V: probe]
- Echo can never call a tool. Prompts naming an MCP tool, `/mcp`, and a raw tool_calls JSON were all just echoed back. Scripted providers exist only in test builds (`RecordingSessionClient: no scripted response`). [V: probe + strings]

**Settings file**
- Path: `$XDG_CONFIG_HOME/muse/settings.json`. It must contain `"schema_version": 1`. Without it the run exits 1 with: `malformed settings file at …: missing field `schema_version` at line 1 column 2`. [V: probe]

**Accepted stdio shape** [V: probe]
```json
{"schema_version":1,"mcpServers":{"<name>":{"command":"python3","args":["..."],"env":{"K":"literal"}}}}
```
- `mcpServers` is an object keyed by server name.
- `command` is a string, and `args` is a separate list.
- `"transport":"stdio"` is optional.
- Unknown keys are silently ignored: `timeout`, `required`, `optional`, `type`, `cwd`, `startup_timeout_sec`.
- `"enabled":false` removes a server.

**Accepted HTTP shapes** [V: probe against a local HTTP canary]
- Working forms:
  - `{"url":U}`
  - `{"transport":"streamable_http","url":U}` (underscore)
  - `{"type":"http","url":U}` (`type` is ignored)
  - Literal `headers` work, including `Authorization`.
- Each request carries `accept: application/json, text/event-stream` and `mcp-protocol-version: 2024-11-05`.

**A bad entry disables ALL MCP** [V: probe]
- Any of these counts as bad:
  - `command` as a list;
  - the array/`{id,…}` plugin form;
  - `transport` set to `"streamable-http"` (dash), `"http"` or `"pigeon"`;
  - `env` on an HTTP entry.
- The run still exits 0 and completes normally.
- The only trace is one status record in session.jsonl: `MCP configuration error in "<path>/settings.json"; MCP is disabled for this runtime`.
- `--json` stdout contains no MCP mention at all.

**Every configured server is required** [V: probe]
- If any server fails to start, the run fails with rc=1. The `run.terminal` record says `invalid run configuration: Required MCP server `<name>` failed during startup: <cause>`.
- Causes seen:
  - `the transport closed unexpectedly.`
  - `the configured command is unavailable.`
  - `the startup operation timed out.`
  - `the process could not be started or the server could not be reached.` (HTTP)
- `required:false` and `optional:true` change nothing.

**Startup timing**
- Observed: a server that delayed `initialize` by 5 s gave a 10.4 s run; 8 s gave 13.5 s; a server that never replied failed at 35.4 s. [V: probe]
- Inferred from those timings: a first spawn is abandoned at about 5 s, then a second spawn waits up to about 30 s. [U: the budgets are inferred]
- `startup_timeout_sec` (2 or 3) was ignored. [V: probe]
- MCP startup is a foreground task that finishes before the first model request, so Muse has no first-prompt race. [V: probe]

**Server env** [V: probe]
- A stdio server receives ONLY `HOME LANG LOGNAME PATH SHELL TERM USER` plus the entry's `env`.
- Muse's own env is not inherited. That includes vars forwarded from Windows through WSLENV: they reach muse but not its servers.
- `${VAR}`, `${HOME}` and `${USER}` are NOT expanded anywhere: not in `env` values (the literal `${PROBE_SECRET_SRC}` arrived), not in `args` (the server failed with "transport closed"), not in `headers` (the literal `Bearer ${…}` was sent).
- Consequence: secrets must be literal values in settings.json.
- Secrets did not appear in session.jsonl, stdout or stderr.
- The binary contains the string "only ${USER} and ${HOME} expand". Its scope is unknown. [V: strings; U: scope]

**Other server details** [V: probe]
- The `cwd` key is ignored: the server's cwd is the workspace.
- MCP client: clientInfo `tbh` 0.1.0, protocol `2024-11-05`, JSON-lines framing.
- Servers are killed by signal at exit; stdin is not closed first. No leftover processes were seen.

**Tool naming** [V: probe]
- Tools are named `mcp__<server>__<tool>`. The server name is normalized: `my-srv` becomes namespace `mcp__my_srv`.
- A server named `a__b` is accepted, which makes the names ambiguous.
- MCP tools are direct model tools, not meta-tools.
- Where they are visible in session.jsonl:
  - `runtime.mcp_tool_identity_catalog` (`canonical_id`, `raw_tool_name`, `server_name`, `surface.namespace`);
  - `model_request_configured.toolset.active_tools`.
- `enabled_tools` and `disabled_tools` did NOT change the catalog or the active tools. Their call-time effect is [U].

**Session log**
- Path: `${XDG_DATA_HOME:-$HOME/.local/share}/muse/sessions/YYYY/MM/DD/<id>/session.jsonl`. [V: strings line 62713 + probe]
- `--no-session-log` hides every MCP diagnostic. [V: probe]
- Muse touches `/root/.local/share/muse` on every run (dir mtime changes) even with HOME and XDG overridden. stderr shows `local session messaging unavailable: registry_io … os error 38`. Which file it touches is [U]. [V: probe]

**Windows Node through WSL interop**
- It fails for stdio MCP. node.exe starts, but `process.stdin` throws `Error: open EISDIR at new Socket (node:net:441)`, also via `cmd.exe /c`. Muse then reports "transport closed unexpectedly". [V: probe]
- A process launched through interop gets the full Windows env (about 88 vars), plus any var named in `"WSLENV"` inside the entry's `env`. Its cwd becomes `\\wsl.localhost\MuseUbuntu1\tmp\…`. [V: probe]
- Working route: a Windows-hosted HTTP MCP server on `127.0.0.1` is reachable from WSL (mirrored networking). `{"url":"http://127.0.0.1:18932/mcp"}` mounted `mcp__winhttp__canary_ping`. [V: probe]

**Approval and web tools**
- What approval mode and the approval judge do to an MCP call headless is [U]: echo cannot issue a call.
- Strings show: `--approval-mode untrusted|on-request|never`; `--disable-approval`; a judge that "only ever auto-allows already-Prompt-bound calls or falls back to the human"; allow rules only in the enterprise `execution.tool_rules.<id>`. [V: strings]
- `--approval-mode never` did not change the active tools. [V: probe]
- `--disable-web-tools` removes `web_search` from the active tools; MCP tools are unaffected. [V: probe]

## 2. Grok

Setup: a private `GROK_HOME`; `XAI_API_KEY` unset or set to `probe-not-a-key`; offline guard. The fake-endpoint runs used `VP\scripts\grok_llm_case.sh` and `VP\grokllm\home\config.toml`.

**Fully offline `grok -p`** [V: probe]
- Config used: `[endpoints] xai_api_base_url` and `cli_chat_proxy_base_url` set to the fake endpoint, plus `[model.fake] base_url=<fake> api_key="probe-not-a-key" api_backend="chat_completions"` and `[models] default="fake"`.
- Env used: `XAI_API_KEY=probe-not-a-key`, `USERPROFILE=<empty dir>`, and the proxy set to the refusing logger.
- Result: 0 proxied requests across all runs.
- Side requests still go to the xAI base URL:
  - `GET /v1/models`;
  - `GET /`;
  - `POST /v1/responses` for the session title, with `model:"grok-4.6"`.
- Each turn also makes an extra `turn-summary` chat completion with no tools, sent to the session model.
- Fakes must answer these side requests or tolerate them failing. Grok tolerated 404s.

**Request headers**
- `authorization: Bearer <key>`, `x-grok-client-mode: headless`, `x-grok-session-id`, `x-grok-conv-id`, `x-grok-model-override`, `user-agent: grok-shell/1.0.52 (windows; x86_64)`. [V: probe]

**How the model sees MCP** [V: probe, request body]
- MCP tools are NOT in `tools[]`. The model only gets the meta-tools `search_tool{query,limit}` and `use_tool{tool_name,tool_input|tool_input_file|file}`.
- The prompt gets a user-role reminder: `MCP server connected:\n- canary (3 tools)\n\nCall `search_tool` to get a tool's input schema before you call `use_tool`. …`
- `search_tool` returns `{"results":[{"server","tools":[{"tool_name":"canary__canary_ping","description","score","input_schema"}]}]}`.
- A `use_tool` call succeeds without a prior `search_tool` call.
- MCP names appear in stdout as `available_commands.tools` entries `<server>__<tool>`, but only after the servers connect.

**streaming-json events seen** [V: probe]
- `available_commands{tools,commands}` (several times)
- `tool_call{toolCallId,title:"use_tool",kind:"use_tool",status:"pending",toolName:"use_tool",rawInput:{tool_name,tool_input}}`
- `tool_call_update{status:null}`
- `tool_call_update{status:"completed",rawOutput:{"type":"MCP","tool_name":"echo_secret_ok","server_name":"canary","output":{"OkayOutput":"pong {}"}}}`
- On failure: `status:"failed"` with `content[0].content.text` = the error.
- `text{data}`, then `usage`, then `end{stopReason,sessionId,requestId,cwd,usage,num_turns,modelUsage}`.

**streaming-json examples in the docs** [V: ~/.grok/docs/user-guide/14-headless-mode.md:236-243], verbatim:
- `{"type":"tool_call","toolCallId":"call_1","title":"Read","kind":"read","status":"in_progress","toolName":"read_file","rawInput":{"path":"src/main.rs"},"content":[],"locations":[]}`
- `{"type":"tool_call_update","toolCallId":"call_1","status":"completed","content":[],"rawOutput":{"lines":42},"locations":[]}`
- `{"type":"end","stopReason":"end_turn","sessionId":"abc123","requestId":"xyz789","cwd":"/repo","usage":{...},"num_turns":7,"modelUsage":{...}}`
- The doc shows `in_progress`; the probe saw `pending`, then `null`, then the final status.

**Approval headless** [V: probe]
- With no rule, an MCP call through `use_tool` ends the whole turn. The update says `"User cancelled the execution for tool `use_tool`"`, then `end.stopReason:"cancelled"`, and the **exit code is 0**.
- These allow the call: `--allow "MCPTool(canary__*)"` and `--allow "mcp__canary"`.
- Deny wins in both tests: `--allow MCPTool(canary__*) --deny MCPTool(canary__echo_secret_ok)`, and `--always-approve --deny mcp__canary__echo_secret_ok`.
  - The tool result is `Tool `use_tool` was not executed: Denied by permission policy: deny rule on mcp matching "canary__echo_secret_ok"`, and the turn continues.
- Grammar: `MCPTool(<server>__<glob>)` matches full `server__tool` names; `mcp__srv`, `mcp__srv__tool`, `mcp__srv__*` and `mcp__*` are accepted [V: 22-permissions-and-safety.md:370-374]. Deny beats ask beats allow, regardless of source [V: 22:275, 22:383-387; 14-headless-mode.md:120].

**Tool filters** [V: probe]
- `disabled_mcp_tools = { canary = ["echo_secret_ok"] }` (top-level key) removes the tool from `available_commands` and from `search_tool`. A call to it returns `Tool not found: canary__echo_secret_ok`.
- Key definitions: [V: 26-config-reference.md:172-182].

**Startup grace and first-prompt race** [V: probe, 1 sample]
- With a server that delays `initialize` by 8 s, the first model request left 1.98 s after the server spawned.
- That request carried `MCP servers currently connecting (tools will become available shortly):\n- canary\n\nDo not attempt to use tools from these servers yet…`.
- `search_tool` returned `{"results":[],"status":"partial","note":"Some MCP servers are still connecting…"}`.
- The single-turn run ended (4.6 s) before the tools ever appeared.
- With a fast server, the first request already said "connected".
- So the "Blocking startup grace" is about 2 s. Docs: [14-headless-mode.md:304], [07-mcp-servers.md:452].

**Failed or broken servers**
- A server that cannot start is not fatal. The model is told `MCP servers that failed to connect:\n- broken (connection failed)`, and rc=0. [V: probe]
- stdout carries no MCP status event. Only `streaming-messages-json` has `mcp_servers[].status` [V: 14-headless-mode.md:304].

**Per-run channels**
- `$GROK_HOME/config.toml` `[mcp_servers.x]` works in `-p`. [V: probe]
- `--agent <file.md>` works with `-p` [V: probe]:
  - its `mcpServers` frontmatter is a **sequence**: `- name: x / command: … / args: [..] / env: [{name: K, value: V}]`;
  - the map form fails at startup (rc=1) with `failed to parse agent definition: mcpServers: invalid type: map, expected a sequence`;
  - the agent's server is added next to the config.toml servers;
  - the file body is added to Grok's system prompt;
  - `${VAR}` is NOT expanded in agent-file env (the literal arrived), unlike config.toml.
- `grok inspect` does not accept `--agent` (as a subcommand flag it errors; as a global flag it is ignored) and does not show agent servers. [V: probe]
- `--plugin-dir` exists only on `grok agent … stdio`. [V: help]
- `GROK_CONFIG` overlays cannot add MCP servers [V: 05-configuration.md:~20-30].
- `-p` and `--single` are the same flag. [V: help]

**Secrets and env** [V: probe]
- In config.toml, `${VAR}` is expanded in `env`.
- The server inherits Grok's full env: 102-105 vars, including names such as `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` and `XAI_API_KEY`.
- `grok mcp list --json` prints the expanded secret.
- `grok mcp doctor` handshake: protocol `2025-11-25`, clientInfo `grok-shell-<server>` 1.0.52.
- In `-p`, servers are killed at exit (stdin not closed).

**User-level sources leak in** [V: probe, `grok inspect --json`]
- Grok resolves `~` from **USERPROFILE**; setting HOME does nothing.
- With all `GROK_CLAUDE_*` and `GROK_CURSOR_*` compat cells set to 0, these still load:
  - 108 skills from `~/.agents/skills` (a native root);
  - 16 hooks from `C:\Users\422mi\.claude` (including a PowerShell `session_start` hook);
  - 8 permission rules from `~/.claude/settings.local.json`.
- `GROK_CLAUDE_MCPS_ENABLED=0` disables `~/.claude.json` servers in inspect.
- **But `grok mcp doctor` still spawned the user's `wmux` server from `~/.claude.json`** with MCPS=0.
- `USERPROFILE=<empty dir>` hides every user source: 0 skills, 0 hooks, no permission files, only config.toml servers.
- Compat env vars: [V: 26-config-reference.md:120-131].

**Workspace `.mcp.json`** [V: probe]
- `./.mcp.json` in an untrusted, non-git cwd is listed by `inspect` (source `mcpJson`, not disabled).
- It was NOT loaded by `-p` (MCPS=0, untrusted). Which of those two gates blocked it is [U].

**What `-p` writes into GROK_HOME** [V: probe]
- `sessions/<url-encoded cwd>/<session-id>/` containing `chat_history.jsonl`, `events.jsonl`, `updates.jsonl`, `tool_definitions.json`, `system_prompt.txt`, `summary.json`, `usage.json`, `prompt_context.json`, `rewind_points.jsonl`, `*.lock`;
- `sessions/session_search.sqlite`, `prompt_history.jsonl`, `models_cache.json`, `agent_id`;
- `docs/user-guide/*.md` (27 files), `installed-plugins/registry.lock`, `*.lock`, `logs/unified.jsonl`, `logs/mcp/<server>.stderr.log`.
- `inspect` and `mcp list` also write `docs/` and `logs/`.

**Concurrency** [V: probe]
- 3 simultaneous `-p` runs sharing one GROK_HOME and one cwd all ended `end_turn`, each with its own session id.
- Same-session concurrency is "best-effort" [V: 17-sessions.md:216].

## 3. opencode

Setup: `VP\scripts\oc_run.sh` used private `XDG_CONFIG/DATA/CACHE/STATE`, `OPENCODE_DISABLE_AUTOUPDATE=1`, `OPENCODE_DISABLE_MODELS_FETCH=1`, and a dead proxy. No `opencode run` was used. Model-path facts come from `opencode serve` plus the session API with a fake `@ai-sdk/openai-compatible` provider pointed at the fake endpoint (`VP\scripts\oc_session_probe.sh`).

**Config layers**
- Three layers load together:
  - `$XDG_CONFIG_HOME/opencode/opencode.json` (global);
  - `./opencode.json` (project);
  - `OPENCODE_CONFIG_CONTENT`.
- All three servers connected in `opencode mcp list`. [V: probe]
- `OPENCODE_DISABLE_PROJECT_CONFIG=1` hides the project file. [V: probe]
- A partial `{"mcp":{"globalcanary":{"enabled":false}}}` in CONFIG_CONTENT deep-merges onto the global entry and shows it as `○ globalcanary disabled`. [V: probe]
- A private `XDG_CONFIG_HOME` hides the user's real global config (`debug paths` shows the private dir). [V: probe]
- `debug paths` shows `home` = the real USERPROFILE, `tmp` = `%TEMP%\opencode`. [V: probe]

**External skills from the real home** [V: probe]
- Even with private XDG, the build agent allow-lists 97 `~/.claude/skills/*` dirs and 108 `~/.agents/skills/*` dirs as `external_directory`.
- `OPENCODE_DISABLE_EXTERNAL_SKILLS=1` plus `OPENCODE_DISABLE_CLAUDE_CODE=1` drops both counts to 0.
- Flag names come from binary strings, including `OPENCODE_PURE`, `OPENCODE_TEST_HOME`, `OPENCODE_AUTH_CONTENT` and `OPENCODE_DISABLE_CHANNEL_DB`. [V: strings]

**Secrets and env** [V: probe]
- `{env:PROBE_SECRET_SRC}` is expanded.
- **`opencode debug config` prints the expanded secret.**
- The server inherits opencode's full env (108-110 vars) plus `environment`.
- MCP client: protocol `2025-11-25`, clientInfo `opencode` 1.18.31, stdin closed cleanly at exit.

**Permissions**
- `debug agent build` shows the resolved ordered ruleset: built-in defaults (`*` allow, `doom_loop` ask, `external_directory`…, `read` with `*.env` ask…), then global-file rules, then CONFIG_CONTENT rules in key order. [V: probe]
- A `"<tool>":"deny"` rule (pattern `*`) **removes the tool from the model's tool list**. [V: probe, request body]
  - Request tools with bash, edit, write and webfetch denied: `glob grep question read skill task todowrite` + MCP.
  - With `canary_*: allow` then `canary_echo_secret_ok: deny`, the tool was absent. Calling it returned `Model tried to call unavailable tool 'canary_echo_secret_ok'. Available tools: …`.

**Tool naming** [V: probe]
- MCP tools are direct model tools named `<server>_<tool>`, e.g. `canary_canary_ping`, `globalcanary_env_inherit_yes`, `projcanary_canary_ping`.
- Tool results come back to the model verbatim (`pong {"a": 1}`).

**No offline MCP tool listing** [V: probe]
- `opencode debug agent <name> --tool <id>` runs only built-ins: `Tool canary_canary_ping not found for agent build`, and MCP servers are not started.
- `opencode serve` `GET /experimental/tool/ids` and `GET /experimental/tool?provider=&model=` list built-ins only.
- `GET /mcp` gives `{"<name>":{"status":"connected"}}`.
- Only a session (fake provider) shows the MCP tool names.

**Bad and failed entries** [V: probe]
- A bad shape is fatal. rc=1 with `Configuration is invalid at OPENCODE_CONFIG_CONTENT ↳ Expected array, got "python" mcp.badshape.command`.
- A server that fails to start is non-fatal: `✗ broken failed  MCP error -32000: Connection closed`.

**Network and data**
- At first session start with an empty private cache, opencode tried `CONNECT github.com:443` (blocked). The cause is [U]; a ripgrep download is suspected. [V: probe, proxy log]
- Data lives in `XDG_DATA/opencode/{opencode.db,log,repos}`, `XDG_STATE/opencode/locks` and `XDG_CACHE/opencode/bin`. [V: probe]
- Isolated runs did not touch the real `~/.local/share/opencode/opencode.db*`. [V: probe, mtime before and after]

## 4. Tool packages

Probe: `VP\scripts\q4_tools.py` and `q4_uvx.py`.
- Each package was installed with `npm install --prefix VP\tc\<name>@<ver>` and started with `node <abs bin>` on Node v22.12.0, using a minimal env (system vars only).
- Each server was first started with no key, then with `probe-not-a-key` if that failed.
- Network was observed with a `NODE_OPTIONS=--require net_observe.cjs` hook that logs every socket connect and DNS lookup.
- Cold start = spawn to `initialize` reply.
- Python servers ran through `uvx` with a private `UV_CACHE_DIR` and `UV_TOOL_DIR` under `VP\uv`.
- All values below are [V: probe].

| tool string | package@ver | bin (relative to package) | engines.node | starts on 22.12? | needs key to start? | network at start? | cold start ms | tools |
|---|---|---|---|---|---|---|---|---|
| playwright | @playwright/mcp@0.0.83 | `cli.js` | >=18 | yes | no | none | 236 | 25 (66 with caps) |
| chrome-devtools | chrome-devtools-mcp@1.11.0 | `build/src/bin/chrome-devtools-mcp.js` | ^20.19 \|\| ^22.12 \|\| >=23 | yes | no | **yes**: play.googleapis.com (usage stats), registry.npmjs.org (update check). None with `--no-usage-statistics` + `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1` | 450 (416 quiet) | 32 |
| firecrawl | firecrawl-mcp@3.30.2 | `dist/index.js` | >=22.0.0 | yes | **no** (local keyless mode) | none | 704 | 26 |
| exa | exa-mcp-server@3.4.2 | `dist/stdio.cjs` | >=20.0.0 | yes | no | none | 105 | 2 |
| tavily | tavily-mcp@0.2.22 | `build/index.js` | – | yes | no | none | 398 | 5 |
| brave | @brave/brave-search-mcp-server@2.1.4 | `dist/index.js` | – | yes | **yes** (`BRAVE_API_KEY`) | none | 296 | 8 |
| perplexity | @perplexity-ai/mcp-server@1.3.0 | `dist/index.js` | >=18 | yes | **yes** (`PERPLEXITY_API_KEY`) | none | 227 | 4 |
| brightdata | @brightdata/mcp@3.1.0 | `server.js` | – | yes | **yes** (`API_TOKEN`) | **yes**: api.brightdata.com | 925 | 32 |
| apify | @apify/actors-mcp-server@0.18.4 | `dist/stdio.js` | >=22.0.0 | yes | **yes** (`APIFY_TOKEN` or `~/.apify/auth.json`) | **yes**: api.apify.com, o272833.ingest.us.sentry.io (Sentry even without a key) | 1484 | 10 |
| browserstack | @browserstack/mcp-server@2.2.3 | `dist/index.js` | >=20.9.0 | yes | **yes** (`BROWSERSTACK_USERNAME`, `_ACCESS_KEY`) | **yes**: api.browserstack.com | 723 | 52 |
| wdio | @wdio/mcp@4.0.0 | `lib/server.js` | >=22.19.0 | **NO**: `TypeError: Cannot read properties of undefined (reading 'bind')` at `undici/lib/interceptor/decompress.js:78` (zstd) | – | – | – | – |
| searxng | mcp-searxng@2.6.0 | `dist/cli.js` | >=22 | yes | no (`SEARXNG_URL` not needed to start) | none | 609 | 4 |
| linkup | linkup-mcp-server@3.4.0 | `bin/linkup-mcp-server.js` | **>=24.0.0** | **yes** (with key) | **yes** (`LINKUP_API_KEY`) | none | 280 | 4 |
| fetch | mcp-server-fetch 2026.10.10 (`uvx --python 3.11 mcp-server-fetch`) | uvx | – | n/a (Python 3.11) | no | [U] (no Python hook) | 2903 first / 557 warm | 1 |
| duckduckgo | duckduckgo-mcp-server 0.7.0 (`uvx … duckduckgo-mcp-server`) | uvx | – | n/a | no | [U] | 2584 first / 777 warm | 3 |

Install size (`npm install`, all exit 0):

| package | size |
|---|---|
| playwright | 19 MB |
| chrome-devtools | 14 MB |
| firecrawl | 61 MB |
| exa | 40 MB |
| tavily | 28 MB |
| brave | 22 MB |
| perplexity | 25 MB |
| brightdata | 112 MB |
| apify | 142 MB |
| browserstack | 125 MB |
| wdio | 252 MB |
| searxng | 34 MB |
| linkup | 38 MB |
| uv cache for both Python servers | 114 MB |

Install logs: `VP\logs\install_summary.tsv`.

### Exact tool names [V: probe, `tools/list`]

**Playwright**
- `@playwright/mcp` with no caps (25): `browser_close browser_resize browser_console_messages browser_handle_dialog browser_emulate_media browser_evaluate browser_file_upload browser_drop browser_find browser_fill_form browser_press_key browser_type browser_navigate browser_navigate_back browser_network_requests browser_network_request browser_run_code_unsafe browser_take_screenshot browser_snapshot browser_click browser_drag browser_hover browser_select_option browser_tabs browser_wait_for`
- With `--caps=devtools,storage,network,pdf,vision` (66): the 25 above plus `browser_cookie_list browser_cookie_get browser_cookie_set browser_cookie_delete browser_cookie_clear browser_resume browser_highlight browser_hide_highlight browser_annotate browser_mouse_move_xy browser_mouse_click_xy browser_mouse_drag_xy browser_mouse_down browser_mouse_up browser_mouse_wheel browser_network_state_set browser_pdf_save browser_start_recording browser_stop_recording browser_route browser_route_list browser_unroute browser_storage_state browser_set_storage_state browser_start_tracing browser_stop_tracing browser_start_video browser_stop_video browser_video_chapter browser_video_show_actions browser_video_hide_actions browser_localstorage_list browser_localstorage_get browser_localstorage_set browser_localstorage_delete browser_localstorage_clear browser_sessionstorage_list browser_sessionstorage_get browser_sessionstorage_set browser_sessionstorage_delete browser_sessionstorage_clear`
- `--help` lists only `vision, pdf, devtools` as caps, yet `storage` and `network` are accepted and add tools.

**Other packages**
- chrome-devtools (32): `click close_page drag emulate evaluate_script fill fill_form get_console_message get_css_styles get_network_request handle_dialog hover lighthouse_audit list_console_messages list_network_requests list_pages navigate_page new_page performance_analyze_insight performance_start_trace performance_stop_trace press_key resize_page screencast_start screencast_stop select_page take_heapsnapshot take_screenshot take_snapshot type_text upload_file wait_for`
- firecrawl (26, keyless): `firecrawl_scrape firecrawl_map firecrawl_search firecrawl_find_tools firecrawl_crawl firecrawl_check_crawl_status firecrawl_agent firecrawl_agent_status firecrawl_interact firecrawl_interact_stop firecrawl_parse firecrawl_monitor_create firecrawl_monitor_list firecrawl_monitor_get firecrawl_monitor_update firecrawl_monitor_delete firecrawl_monitor_run firecrawl_monitor_checks firecrawl_monitor_check firecrawl_research_search_papers firecrawl_research_inspect_paper firecrawl_research_related_papers firecrawl_research_read_paper firecrawl_developer_search firecrawl_gov_search firecrawl_credit_usage`
  - The README says 27 in the full keyed profile.
- exa (2): `web_search_exa web_fetch_exa`
- tavily (5): `tavily_search tavily_extract tavily_crawl tavily_map tavily_research`
- brave (8): `brave_web_search brave_local_search brave_video_search brave_image_search brave_news_search brave_summarizer brave_llm_context brave_place_search`
- perplexity (4): `perplexity_ask perplexity_research perplexity_reason perplexity_search`
- brightdata (32): `search_engine scrape_as_markdown search_engine_batch scrape_batch scrape_as_html extract discover list_dataset_fields search_dataset search_scrapers get_scraper_details run_scraper get_scraper_progress get_scraper_results refresh_scrapers session_stats chatgpt_ai_insights perplexity_ai_insights scraping_browser_navigate scraping_browser_go_back scraping_browser_go_forward scraping_browser_snapshot scraping_browser_click_ref scraping_browser_type_ref scraping_browser_screenshot scraping_browser_network_requests scraping_browser_wait_for_ref scraping_browser_fill_form scraping_browser_get_text scraping_browser_get_html scraping_browser_scroll scraping_browser_scroll_to_ref`
- apify (10): `search-actors fetch-actor-details call-actor get-actor-run get-dataset-items get-key-value-store-record abort-actor-run search-apify-docs fetch-apify-docs report-problem`
- browserstack (52): the full list is in `VP\logs\q4\browserstack.json`. It includes `runBrowserLiveSession runAppLiveSession takeAppScreenshot startAccessibilityScan fetchAutomationScreenshots invokeCapability …` (camelCase).
- searxng (4): `searxng_web_search searxng_search_suggestions searxng_instance_info web_url_read`
- linkup (4): `linkup-search linkup-research linkup-get-research linkup-fetch`
- fetch (1): `fetch`
- duckduckgo (3): `search fetch_content expand_link`
- Name hygiene: names with `-` (apify, linkup) or camelCase (browserstack) pass through each harness's own sanitizer.

### Remote endpoints (docs only; READMEs saved in `…\scratchpad\readmes\` or in the installed packages)

- **Firecrawl**
  - Keyless: `https://mcp.firecrawl.dev/v2/mcp` (only scrape/search/parse).
  - With a key: the same URL plus `Authorization: Bearer <FIRECRAWL_API_KEY>`.
  - OAuth: `/v2/mcp-oauth`. Search-only: `/v2/mcp-search`.
  - [V: tc\firecrawl-mcp@3.30.2\…\README.md:40-72]
- **Exa**
  - `https://mcp.exa.ai/mcp`, anonymous and rate-limited.
  - Key as `?exaApiKey=`, `Authorization: Bearer`, or `x-api-key`.
  - Choose tools with `?tools=a,b` (this replaces the defaults).
  - [V: exa README:25-30,105-130]
- **Tavily**: `https://mcp.tavily.com/mcp/?tavilyApiKey=<key>`, or an Authorization header, or OAuth. [V: tavily README:20-30,54-62]
- **Linkup**: `https://mcp.linkup.so/mcp`, with `?apiKey=` or a bearer token. [V: linkup README:44-50,72-80]
- **Browserbase**
  - `https://mcp.browserbase.com/mcp` (SHTTP).
  - 6 tools: `start end navigate act observe extract`.
  - The stdio form needs `BROWSERBASE_API_KEY` and `GEMINI_API_KEY`.
  - [V: readmes\browserbase.README.md:15-47,66-85]
- **Jina**
  - `https://mcp.jina.ai/v1`; `Authorization: Bearer ${JINA_API_KEY}` is optional.
  - Without a key: `primer`, `guess_datetime_url` and `search_jina_blog`; `read_url` and `capture_screenshot_url` at rate limits.
  - `search_web` and other tools need a key.
  - Filter with `?include_tags=` / `?exclude_tags=`.
  - [V: readmes\jina.README.md:15-17,64-80,122-136]
- **Parallel**
  - `https://search.parallel.ai/mcp`: "free to use — no API key required"; Bearer for paid.
  - `https://search.parallel.ai/mcp-oauth`.
  - [V: readmes\parallel.docs.html (docs.parallel.ai/integrations/mcp/search-mcp)]

## 5. Browser process tree

Probe: `VP\scripts\q5_browser.py`, raw output in `VP\logs\q5_*.json`. Command: `node <abs cli.js> --headless [--isolated] --output-dir=VP\pw-art\<v> [--user-data-dir=VP\pw-prof\<v>]`.

**Flags**
- `--isolated` with `--user-data-dir` is fatal at startup: `Error: Browser userDataDir is not supported in isolated mode.` (`playwright-core/lib/coreBundle.js:74313`). [V: probe]

**Navigate and screenshot** [V: probe]
- `browser_navigate` to a local `file:///…/probe_page.html` took 335-594 ms (cold browser launch included).
- `browser_take_screenshot` returns a text block plus an inline base64 `image` part.

**Where files land** [V: probe]
- An auto-named screenshot goes to `--output-dir` as `page-<ISO-ts>.png`. The response cites it relative to the cwd (`pw-art\udd_taskkill\page-….png`).
- A screenshot with an explicit `filename` goes to the **server's cwd** (the workspace root), not to `--output-dir` (`./named_shot.png`). Help: "Files with an explicit name are resolved against the workspace root instead".

**Process tree** [V: probe, Win32_Process]
- node runs `chrome.exe`, the system Google Chrome stable at `C:\Program Files\Google\Chrome\Application\chrome.exe`. That root Chrome is a **direct child of node**, and its renderers and helpers are children of the root.
- The root uses `--headless --remote-debugging-pipe`.
- With `--user-data-dir`, the dir is on the Chrome command lines.
- With `--isolated`, the root gets `--user-data-dir=%TEMP%\playwright_chromiumdev_profile-XXXXXX`.

**Ending the server** [V: probe]
- `taskkill /T /F` on node kills node and every Chrome; 0 survivors after 3 s.
  - **But with `--isolated` the temp profile `%TEMP%\playwright_chromiumdev_profile-*` is left behind.** I deleted the one this probe leaked.
- Closing stdin: node exits with code 0 in 81-126 ms, and Playwright closes Chrome itself; 0 survivors.
  - The isolated temp profile is removed.
  - A `--user-data-dir` profile stays (that is intended).

## 6. Env-filter wrapper

Files: `VP\scripts\env_filter_wrapper.py` (stdlib), with flags `--allow NAME`, `--allow-prefix P`, `--set K=V`, `--rename DST=SRC`, `-- cmd…`. It calls `subprocess.run(cmd, env=filtered)` with stdio inherited. Test script: `VP\scripts\q6_wrapper_test.py`.

- **(a) From the stdlib client** [V: probe]
  - The handshake works: init in 67 ms, 3 tools, calls answered, exit 0 on stdin close.
  - The canary saw ONLY `PATH PROBE_LITERAL PROBE_SECRET SYSTEMROOT TEMP TMP`.
  - `PROBE_SECRET` arrived through `--rename PROBE_SECRET=VB_STAGED_SECRET`.
  - `LEAK_ME` and `PROBE_CANARY` from the outer env did not arrive.
- **(b) From `opencode mcp list`** (wrapper in `mcp.<x>.command`) [V: probe]
  - `✓ wrapped connected`.
  - The canary saw only `PATH PROBE_SECRET SYSTEMROOT`. clientInfo was opencode, and stdin was closed cleanly.
- **(c) Kill reach** [V: probe]
  - `taskkill /PID <wrapper> /T /F` kills the wrapper and the real server.
  - Killing **only** the wrapper (TerminateProcess) **orphans the real server**. It was still alive 4.5 s later, because the client still held the pipe and no EOF arrived. I killed it.
  - So on Windows a launcher must tree-kill, or close the server's stdin.
  - On Linux (Muse) the wrapper could `os.execve` instead, leaving no extra process. [U: not probed]

## 7. What changed versus request.md §C.9

- **Muse (C.9.2 §3): every [U] is now resolved.**
  - Shape: an object keyed by name, `command` string plus `args`, and required `schema_version:1`. The plugin array form is rejected.
  - Transport is `streamable_http` (underscore), not `streamable-http`.
  - Secrets: there is NO `${VAR}` expansion and NO env inheritance (not even WSLENV), so secrets must be literal in the private settings.json.
  - Every server is required, and one failure fails the run.
  - Windows `npx`/node through interop does **not** work for stdio. Use a Linux binary, or a Windows HTTP server on 127.0.0.1.
  - Naming is `mcp__<server>__<tool>`, as direct tools.
  - `enabled_tools`/`disabled_tools` do not filter the catalog.
  - Diagnostics exist only in session.jsonl.
- **Grok (C.9.2 §2)**
  - Channel (c) `--agent <file>` is now [V] and works with `-p`, but its frontmatter is a sequence with `env:[{name,value}]` and no `${VAR}` expansion.
  - Headless with no allow rule **cancels the whole turn with exit 0**; C.9 said only "headless cannot prompt".
  - Deny beats `--always-approve`.
  - The blocking grace is about 2 s [was U]. The race is real: an 8 s server never became usable in a one-turn run.
  - Concurrent runs sharing one GROK_HOME work, which reduces the EC-27 concern for distinct sessions.
  - Compat vars are NOT enough: `~/.agents/skills`, `~/.claude` hooks and `~/.claude/settings.local.json` permissions still load. Only `USERPROFILE=<private dir>` isolates. `grok mcp doctor` ignores `GROK_CLAUDE_MCPS_ENABLED=0`.
  - Even with a custom model, Grok calls the xAI base (`/v1/models`, `/`, `/v1/responses` title) unless `[endpoints]` is overridden.
  - The first-turn tool list holds `search_tool`/`use_tool` only.
- **opencode (C.9.2 §1)**
  - A permission `deny` *removes* the tool from the model's list; it is not a call-time rejection.
  - `debug config` leaks expanded secrets.
  - There is no offline MCP tool-listing command.
  - The user's `~/.claude/skills` and `~/.agents/skills` load despite private XDG; `OPENCODE_DISABLE_EXTERNAL_SKILLS=1` and `OPENCODE_DISABLE_CLAUDE_CODE=1` stop them.
  - `OPENCODE_DISABLE_PROJECT_CONFIG=1` hides `./opencode.json`.
  - A bad config shape is fatal (C.9 only covered failed servers).
- **Tools (C.9.1/C.9.3)**
  - "Node ≥ 24 packages fail on 22" is answered: Linkup does **not** fail on 22.12. But `@wdio/mcp` 4.0.0 (engines ≥ 22.19) **does** fail on 22.12.
  - Firecrawl, Exa, Tavily and SearXNG start without keys.
  - Brave, Perplexity, Bright Data, Apify, BrowserStack and Linkup exit at start without one.
  - Bright Data, Apify (plus Sentry) and BrowserStack call home at startup.
  - Chrome DevTools also needs `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1`, not only `--no-usage-statistics`.
  - Tool counts that differ from C.9: Brave 8 (C.9 listed 5), Perplexity 4 (adds `perplexity_search`), Firecrawl 26 keyless (README 27).
  - Playwright `--isolated` + `--user-data-dir` is fatal, and pass 1 listed both flags without noting this.
  - Explicitly named Playwright files land in the workspace root, not `--output-dir`.
- **C.9.2 "Hardest blocker (3)"**: the env-filter wrapper is a working, harness-neutral fix for stdio servers. It needs a tree-kill or a stdin close on Windows.

## 8. Still unverified

- Muse:
  - what approval mode or the judge does to a real MCP call (echo cannot call tools);
  - the call-time effect of `enabled_tools`/`disabled_tools`;
  - the exact startup budgets (about 5 s then about 30 s are inferred);
  - which file under `/root/.local/share/muse` is touched;
  - whether the agent-level `mcp.json`/`--agents` route exists.
- Grok:
  - whether `./.mcp.json` was blocked by folder trust or by `GROK_CLAUDE_MCPS_ENABLED=0`;
  - the grace length beyond one sample;
  - whether the grace differs with several servers;
  - `streaming-messages-json` `mcp_servers[].status` shapes;
  - `$GROK_HOME/plugins/<p>/.mcp.json` in `-p`;
  - same-session-id concurrency;
  - whether `--agent` changes the default toolset beyond the system prompt.
- opencode:
  - the cause of the `CONNECT github.com:443` at session start;
  - the `run --format json` event shapes (not run, by rule);
  - the behavior of an `ask` permission in `serve` (the session would wait for a reply);
  - MCP `timeout` semantics.
- Tools:
  - network at start for the Python servers (no hook);
  - the full keyed Firecrawl profile (27);
  - Linkup on Node 22.12 for actual calls;
  - every remote endpoint (docs only, no probe);
  - chrome-devtools real browser run and its process tree (only Playwright was run).
- Wrapper: `os.execve` on Linux/Muse.
- I saw the real `~/.local/share/opencode/opencode.db-shm` mtime change at 22:44:25 during the probe window. A before/after re-test shows the isolated runs do not touch it, so it was probably another process [U].
