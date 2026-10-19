# S0 vendor scout report

**Status:** done. **Produced:** `docs/spec/harness-browser-tools/context/vendor-facts.md`. Every fact there carries a tag: `[V: probe]`, `[V: path:line]` or `[U]`. **Commits:** none.

## What was done

Every vendor question was answered with free, local, model-free probes:

- **Muse** (Q1): 50+ settings variants, run with the echo provider inside WSL.
- **Grok** (Q2):
  - `inspect` / `mcp list` / `mcp doctor` with a private `GROK_HOME`;
  - full `grok -p` runs against a scripted fake OpenAI-compatible endpoint on 127.0.0.1. Its `[endpoints]` and `[model.fake]` settings point every request, side requests included, at the fake. Nothing reached xAI, and the refusing proxy logged 0 outbound requests.
- **opencode** (Q3): `mcp list`, `debug config|paths|agent`, and `opencode serve` plus its session API with a fake `@ai-sdk/openai-compatible` provider.
- **Tool packages** (Q4): 13 npm packages and 2 uvx packages started on Node 22.12. A `NODE_OPTIONS` connect/DNS hook observed their network use.
- **Browser** (Q5): a real headless Chrome run with Playwright MCP, plus a Win32_Process tree check.
- **Wrapper** (Q6): an env-filter wrapper, tested from the stdlib client and from `opencode mcp list`.

**Deviation, stated plainly.** The brief said "no `opencode run`". I did not use `opencode run`. Instead I drove opencode's own server (`opencode serve`) with a scripted local fake provider. That fake is not a model and makes no network call, so it fits the brief's intent (no model calls, no paid APIs). It was the only way to observe the real MCP tool names and the permission effects on the request body. I used the same fake-endpoint method for `grok -p`, after verifying that every Grok endpoint was redirected locally.

## Findings that change the design (details and tags in vendor-facts.md)

1. **Muse**
   - Settings shape: `{"schema_version":1,"mcpServers":{"x":{"command":"…","args":[…],"env":{…}}}}`.
   - No `${VAR}` expansion and no env inheritance, so secrets must be literal values in the per-call private settings.json.
   - One bad entry silently disables all MCP, and the run still exits 0.
   - Every server is required: one startup failure fails the run.
   - Windows Node does not work through WSL interop. A Windows-hosted HTTP server on 127.0.0.1 does.
2. **Grok**
   - Headless with no allow rule cancels the whole turn, but still exits 0.
   - `--allow MCPTool(x__*)` works. Deny wins, even over `--always-approve`.
   - The model sees MCP only through `search_tool`/`use_tool`.
   - The startup grace is about 2 s, so a slow server is not usable in a one-turn run.
   - `--agent <file>` is a per-run mount route that needs no shared config write. Its `mcpServers` is a sequence, with `env:[{name,value}]` and no `${}` expansion.
   - Only `USERPROFILE=<private dir>` stops the user's skills, hooks and permission files from loading.
   - Concurrent `-p` runs sharing one GROK_HOME work.
3. **opencode**
   - Tools are `<server>_<tool>` direct tools.
   - A `deny` rule removes the tool from the model's list.
   - `debug config` prints expanded secrets.
   - External skills from the real home load unless `OPENCODE_DISABLE_EXTERNAL_SKILLS=1` and `OPENCODE_DISABLE_CLAUDE_CODE=1` are set.
   - A bad config shape is fatal.
4. **Tool packages**
   - `@wdio/mcp` 4.0.0 fails on Node 22.12. Linkup (engines ≥ 24) works.
   - Six packages exit at start without a key.
   - Bright Data, Apify (with Sentry) and BrowserStack call home at startup.
   - chrome-devtools-mcp also needs `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1`.
5. **Playwright**
   - `--isolated` together with `--user-data-dir` is fatal.
   - Explicitly named files land in the workspace root.
   - `taskkill /T /F` leaks the isolated temp profile; closing stdin cleans it up.
6. **Env-filter wrapper**
   - It works with every harness channel tested.
   - Killing only the wrapper on Windows orphans the server. Launchers must tree-kill or close stdin.

## Larger move this opens

The fake-endpoint method (`fake_llm_server.py` with `grok_llm_case.sh` and `oc_session_probe.sh`) gives S2 *recorded* request and response shapes from the real binaries. That means offline fakes can be checked against vendor behavior instead of being guessed. For Grok and opencode, S2 could run the real binaries in CI against the scripted endpoint: hermetic, no keys, and the actual mount compilers exercised end to end. Muse cannot do this, because echo cannot call tools.

## Probe scripts (all under `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\1da32edd-ec0f-4839-ba1f-52db538ed13c\scratchpad\vendor-probe\scripts\`)

**Shared**
- `...\scripts\mcp_client.py`: stdlib stdio MCP probe client.
- `...\scripts\canary_mcp.py`: stdlib stdio canary that records env names, values of `PROBE_*` vars, the handshake and calls.
- `...\scripts\canary_mcp.js`: Node canary.
- `...\scripts\canary_http_mcp.py`: streamable-HTTP canary.
- `...\scripts\bin_strings_grep.py`: binary string search.
- `...\scripts\kill_port.sh`: kills the listener on a probe port.
- `...\scripts\fake_llm_server.py`: scripted OpenAI-compatible fake plus a refusing, logging proxy.

**Muse**
- `...\scripts\muse_run.sh`, `muse_run_variant.sh`, `muse_batch.sh`: run Muse variants.
- `...\scripts\muse_make_variants.py`: writes the settings variants.
- `...\scripts\muse_http_test.sh`: HTTP variants H1-H12.
- `...\scripts\muse_report.py`, `muse_summarize.py`: summarize runs.
- `...\scripts\muse_strings_grep.sh`, `muse_approval_grep.sh`: search binary strings.
- `...\scripts\wsl_interop_test.sh`, `wsl_interop_test2.sh`: Windows Node through interop.
- `...\scripts\muse_cleanup.sh`: removes the WSL probe dirs.
- Evidence: `...\vendor-probe\muse\outputs\muse_probe_root.tgz` and `*.out`.

**Grok**
- `...\scripts\grok_run.sh`: inspect, list and doctor with a private home.
- `...\scripts\grok_inspect_summary.py`: summarizes inspect output.
- `...\scripts\grok_llm_run.sh`, `grok_llm_case.sh`, `grok_llm_summary.py`: offline `-p` runs against the fake endpoint.
- Homes: `...\vendor-probe\grokhome`, `grokllm\home*`. Logs: `...\vendor-probe\logs\grok*`, `grokllm\fake_*.jsonl`.

**opencode**
- `...\scripts\oc_run.sh`: isolated CLI runs.
- `...\scripts\oc_serve_probe.sh`: server endpoints.
- `...\scripts\oc_session_probe.sh`: a session with the fake provider.
- Config: `...\vendor-probe\oc\occ_*.json`. Logs: `...\vendor-probe\logs\oc_*`, `oc\fake_mcp1.jsonl`.

**Tool packages**
- `...\scripts\install_all.sh`: npm installs into `...\vendor-probe\tc\`.
- `...\scripts\q4_tools.py`: Node servers.
- `...\scripts\net_observe.cjs`: connect/DNS hook.
- `...\scripts\q4_uvx.py`: Python servers with a private uv cache.
- `...\scripts\q4_summary.py`: summarizes the results.
- Results: `...\vendor-probe\logs\q4\*.json`. READMEs: `...\scratchpad\readmes\`.

**Browser and wrapper**
- `...\scripts\q5_browser.py`: real browser run. Results in `...\vendor-probe\logs\q5_*.json`; screenshots in `...\vendor-probe\pw-art\`.
- `...\scripts\env_filter_wrapper.py`: the wrapper.
- `...\scripts\q6_wrapper_test.py`: wrapper test. Output in `...\vendor-probe\logs\q6_wrapper_test.out`.

## Hygiene

- No user config was changed: `~/.grok`, `~/.config/opencode`, `~/.claude*`, `~/.vidbyte` and the WSL home were all left alone. Nothing was installed globally; uvx used a private cache and tool dir.
- The real `~/.local/share/opencode/opencode.db*` was not touched by the isolated runs (re-tested before and after).
- The WSL dirs `/tmp/vbprobe-2598226333` and `/tmp/vbprobe-strings` are removed. No muse, python3 or canary processes are left in WSL.
- On Windows, no node, chrome, grok, opencode, python or uv process with probe paths in its command line remains. Probe ports 18932, 18940, 18941 and 18950 are closed.
- One `%TEMP%\playwright_chromiumdev_profile-*` dir leaked by the taskkill test; I deleted it.
- An early version of `q5_browser.py` matched its own driver shell by command-line tag and killed it. This was fixed by matching only chrome and node processes. No user process was affected.
- Nothing was written outside the scratch area, WSL `/tmp/vbprobe-*`, and these two output files.
