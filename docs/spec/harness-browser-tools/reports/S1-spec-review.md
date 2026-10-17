# S1 spec review — harness-browser-tools (spec r1)

VERDICT: SOUND WITH FIXES — the `execute(mount=…)` seam, the per-call Grok agent file and the pinned registry are a sound base, but as written every real Muse browser call fails on a missing `schema_version`, the change trips four zero- or one-slack lint ratchets the spec never budgets, and the narrowing and capability rules mount the wrong tools.

## WHAT THE SPEC GETS RIGHT

- **The plain paths stay untouched.** The `mount: BrowserMount | None = None` seam on `<H>ThreadRun.execute`, with `_call` taking `.result`, keeps the nine plain functions byte-identical. I checked every surface, errors and static-policy pin that §13 lists against the tests, and the list is complete. No test references `ThreadRun`, `config_content`, `GrokWire`, `OpencodeWire` or `MuseExecOutput` internals.
- **The Grok channel avoids a race.** A per-call `--agent=<file>` (D-7) avoids a race on the shared `config.toml` inside the per-workspace private home. The sequence form, the repeatable `--allow`/`--deny` flags and concurrent runs on one `GROK_HOME` are all backed by vendor facts §2/§7 and the Grok guide (14-headless-mode.md:39-40,120).
- **The Muse refusals and the cleanup are justified.**
  - Muse keyed refusal (D-9) is forced by KD-6 together with vendor facts §1: there is no env inheritance and no `${VAR}` expansion.
  - A per-call `--user-data-dir` avoids the `--isolated` `%TEMP%` profile leak.
  - `ProcessReaper` as a lib helper has a precedent in `MuseLauncher.reap`. The precedent for its constants living in `constants/native_threads.py` is that `lib/process/runner.py` already takes its taskkill parts from there.
- **The seed registry values match the probes.** Every value matches vendor facts §4:
  - packages, exact versions and entry paths;
  - tool counts (Playwright 25 core, chrome-devtools 32, Firecrawl 26 keyless, Brave 8, Tavily 5);
  - Brightdata's 14 `scraping_browser_*` tools;
  - Playwright's `devtools 13 / storage 17 / network 4 / pdf 1 / vision 6` capability split.

## FINDINGS

**R-1 [Blocker] [L5] §9.1 Mount by harness (Muse) — the compiled `settings.json` omits the mandatory `"schema_version": 1`, so every real Muse browser call fails**
- Evidence:
  - Vendor facts §1:17 says the file "must contain `"schema_version": 1`. Without it the run exits 1 with: `malformed settings file … missing field `schema_version``".
  - §9.1 (spec:532-541) gives only the per-server entry shapes. Neither `MuseMounts.settings` (§8.5), nor row 27 of §12.3, nor any AC or EC names the field.
  - Vendor facts §1:37-45 adds that one bad entry (`env` on an HTTP entry, `command` as a list, a dashed `transport`) disables all MCP while the run still exits 0.
- Failure:
  - `run_/continue_/fork_muse_with_browser` raise `muse.run_failed` on every real Muse.
  - The fake harness never validates the file, so AC-2 passes while the feature is dead.
  - If a later edit puts `env` on a jina/parallel entry, the tools silently vanish and the result still reports success (see R-10).
- Smallest fix:
  - Put the top-level object `{"schema_version": 1, "mcpServers": {…}}` in §9.1 and keep the value in a constant.
  - Add three rules to §9.1: never emit `env` on an HTTP entry; `command` is a string; `transport` is exactly `streamable_http`.
  - Add an AC that the compiled `settings.json` carries `schema_version` 1 and those entry rules, and that the fake Muse refuses a file without them.

**R-2 [Blocker] [L8] §12.4 / §13 / §11 — the change breaks lint ratchets that have zero or one slack, and the spec never budgets them**
- Evidence (current count vs `lint/baseline.json`):
  - **S020: 1 vs 1.** `tests/features/harness_threads/README.md` has a `## File Index`, and S020 checks it against tracked files. Every new test file must be listed there, but §13 never tells the test author. FEATURE.md's suite map is the same.
  - **S061: 5 vs 6.** The rule flags `x.write_text(<non-literal>)` and bare `open(<dynamic>)`. Its check at `s061_bounded_safe_path.py:63-68` takes `args[0]`, so it flags any `write_text` whose content is a variable. `GrokMounts.write_agent` and the Muse `settings.json` write (§8.5) are two natural `write_text` calls, which makes 7 > 6.
  - **S041, S047 and S052 are all at 0.** They cover an unspecified encoding, `open` in an async function and blocking subprocess calls in async code. The coroutines `NativeBrowserTools.prepare/complete/discard` and `ProcessReaper.reap` do file and process work.
  - **A007 (operational constants): 255 vs 255.** It applies to rows 5, 6, 10 and 13 (records, registry, reaper), not only constants, but §12.4 cites it only under "Constants".
  - **S009 (staged mypy): 346 vs 350.** It runs inside `python lint/run.py`, so §11:663 "Typecheck: none" is false.
  - **Semgrep** `.semgrep/typed-mapping-boundary-policy.yml` (CI only) forbids a function that takes an `object`/`Any` parameter and returns early on `not isinstance(v, Mapping|dict)`. The wire readers in this change (streaming-json events, Muse records) are exactly where such a helper gets written. The existing readers use inline `isinstance(x, dict)` checks instead.
- Failure: AC-20 ("Lint ends with `AGENT-LINT: PASS`") fails. Under "no baseline raises", the implementer or the test author discovers it only at the gate and has to redesign the writes late.
- Smallest fix: add the following to §12.4 and §13, and correct §11:663.
  - S020: list each new test file in the README File Index and FEATURE.md.
  - S061: at most one new finding. Write both files through the reviewed `LocalFileSystemBackend.write_text` (`vidbyte/lib/tools/filesystem/backends/local.py`), held as a `backend` attribute (the receiver form S061 exempts), or through one shared contained writer.
  - S041/S047/S052: pass an explicit encoding from constants; do file I/O in coroutines through `asyncio.to_thread`, as `GrokThreadRun._prepare_home` does; start children only through `CliRunner`.
  - A007: zero new findings, so every limit, timeout and cap in lib modules comes from constants.
  - S009: mypy has 4 slack.
  - Semgrep: readers use inline `isinstance` checks, never an `object`-parameter early-return helper.

**R-3 [Blocker] [L4] §8.1 D-15 / §12.3 row 9 — `NativeThreadError(result_record: str | None)` types a closed set as a plain `str`**
- Evidence:
  - AGENTS.md §Enums: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum … not a plain `str`."
  - `NATIVE_THREAD_RESULT_RECORDS` maps the 18 operations onto exactly two names, `NativeThreadResult` and `BrowserThreadResult`.
  - `vidbyte/lib/errors/base.py:601` builds `expected` from `operation.value`, and its only `vidbyte` import is from `lib.enums`.
- Failure: the plain-`str` parameter is a direct AGENTS.md contradiction and draws a placement or convention comment in review. A typo in the table ships silently.
- Smallest fix: drop the keyword and let `NativeThreadError` derive the record from `operation`, which is already an enum, through a `NativeThreadOperation → NativeThreadResultRecord` table. Or type the keyword as a new two-member `NativeThreadResultRecord` StrEnum in `lib/enums/native_threads.py`. INV-16 still holds, because plain operations map to `NativeThreadResult`.

**R-4 [Major] [L7] §9.1 Narrow row / D-10 / AC-6 — narrowing fails open: tools missing from the registry stay allowed**
- Evidence:
  - The compiled form is a wildcard allow (`"<srv>_*":"allow"`, `--allow=MCPTool(<srv>__*)`) plus exact denies of the known others. AC-6 pins "allows `firecrawl_*` and denies the other 25".
  - Vendor facts §4 shows that the registry and the server can disagree. Firecrawl's README says 27 tools in the keyed profile, against the 26 probed keyless. A pinned version can also add a tool the registry does not list.
  - The C.0.2 compiled form the request endorsed was fail-closed: `"firecrawl_*":"deny"` followed by `"firecrawl_firecrawl_search":"allow"`. opencode's rule is that the last match wins, and a denied tool leaves the model's list.
- Failure: `firecrawl:search` with a key exposes `firecrawl_search` plus every unlisted keyed tool. That breaks FR-6/G-2 narrowing and the caller's least-privilege intent with no error.
- Smallest fix:
  - **opencode:** emit `"<srv>_*":"deny"` and then one exact allow per selected tool.
  - **Grok:** when narrowed, emit exact `--allow=MCPTool(<srv>__<tool>)` per selected tool, plus the known denies. An unlisted tool then cancels the turn: vendor facts §7 says "headless with no allow rule cancels the whole turn". The cancellation surfaces as `run_failed` instead of running silently.
  - Update AC-6 to match.

**R-5 [Major] [L1] §9.1 `BrowserToolSelection.exposed/denied` — selecting a Playwright `server_value` capability removes the core tools instead of adding to them**
- Evidence (spec:471):
  - `exposed` = the tools of every capability with no `server_value` (core, 25), plus each selected capability that has a `server_value`.
  - `allowed` = the tools of the selected capabilities.
  - `denied` = exposed − allowed.
- Failure:
  - `playwright:devtools` yields allowed = 13 devtools tools and denied = all 25 core tools, including `browser_navigate`, `browser_click` and `browser_snapshot` (vendor facts §4). The agent can start tracing but cannot open a page.
  - On Muse the same item is refused, because the deny set is non-empty.
  - This contradicts the endorsed C.0.1 meaning that `--caps=devtools` adds video and trace tools.
- Smallest fix: make server-flag capabilities additive. Selecting one adds `--caps=<value>` and allows default ∪ selected, so `denied` stays empty for `playwright:devtools` and Muse accepts it. Add an AC: `playwright:devtools,pdf` exposes 25 + 13 + 1 tools and denies none.

**R-6 [Major] [L5] §9.1 opencode channel — server ids collide with the user's own global `mcp.<name>` and inherit its members**
- Evidence:
  - Vendor facts §3:218: a partial `{"mcp":{"globalcanary":{"enabled":false}}}` in `OPENCODE_CONFIG_CONTENT` deep-merges onto the global entry.
  - The spec's server ids are the bare `BrowserTool` values (`playwright`, `firecrawl`, `exa`), which are among the most common names in a user's global opencode config.
  - Grok (private `GROK_HOME`) and Muse (fresh `XDG_CONFIG_HOME`) are not exposed to this.
- Failure: anything the user's global entry sets that the SDK's entry does not overwrite is inherited. Three cases:
  - `"enabled": false` gives a spurious `browser.tools_unavailable`.
  - A global `environment` (for example a `PLAYWRIGHT_MCP_*` isolation setting next to the SDK's `--user-data-dir`) changes or breaks the server.
  - A global `url` or `headers` on a `local` entry can make the merged config invalid.
- Smallest fix: emit `"enabled": true` and every member explicitly, or better, prefix server ids with a constant on opencode (for example `vb-playwright`; the tool names still split at the first `_`). Add an EC for a same-named global server.

**R-7 [Major] [L5] §10 T-1 / EC-3 / §9.1 Grammar — a key pasted into `tools` can be echoed in the did-you-mean refusal**
- Evidence:
  - The grammar `^[a-z0-9-]+…` is matched on the lower-cased item, and many keys pass it once lower-cased: `fc-…`, `tvly-…`, UUID-shaped tokens.
  - EC-3: a grammar refusal "quotes it only after every key is registered". A key pasted into `tools` is not in `tool_keys`, so it is never registered.
  - `HarnessRedactor._ERROR_ASSIGNMENT` (`vidbyte/harnesses/serialization.py`) redacts only `key=value` and `key: value` forms, so a bare echoed token survives.
- Failure: T-1's own threat ("pastes a tool key into `tools`") leaks the key into the error message, its `__str__` and any trace or log.
- Smallest fix: registry refusals never quote the item. They name `tools[i]` and the suggestion only. Change EC-3 and T-1 to match, and add an AC with a key-shaped item.

**R-8 [Major] [L7] §10 / D-17 / Q-7 — the cost of declining the env-filter launcher is understated**
- Evidence:
  - Grok: every stdio server and its transitive npm dependencies inherit the caller's full `os.environ` plus the overlay: `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY` and every tool key (D-7).
  - opencode: servers inherit `OPENCODE_CONFIG_CONTENT`, which holds the harness provider key and every tool key and header.
  - Muse: servers get only `HOME LANG LOGNAME PATH SHELL TERM USER` (vendor facts §1).
  - Apify calls Sentry at start (EC-34).
  - The npm install runs lifecycle scripts with the caller's environment, because the spec never passes `--ignore-scripts`.
  - D-17 argues only that the shell sees the keys anyway. Its orphan argument is weak, because stdio servers get EOF when the harness exits and the marker reaper covers the rest.
- Failure: a caller reading Q-7 ("no") cannot see that every third-party server gets every key the call holds, including the harness key. On Grok it also gets the caller's whole environment.
- Smallest fix: add a T-6 row with this per-harness exposure table, and restate Q-7 with that blast radius. Optional `[scope-adding]` Q-14: "pass `--ignore-scripts` to the pinned install?" (default: not built).

**R-9 [Major] [L1] §2 / §4 / D-9 — on Windows (Muse through WSL), `run_muse_with_browser` can mount no browser at all, and the spec never says so**
- Evidence:
  - The mount table leaves Muse WSL only keyless, unnarrowed remote tools: `jina` and `parallel`, both search or fetch services.
  - Jina's `search_web` needs a key, so keyless Jina is fetch-only.
  - AC-2 uses `["jina"]` for Muse WSL, which hides this.
  - Vendor facts §1:92 verifies that a Windows `127.0.0.1` HTTP MCP is reachable from WSL (mirrored networking), and Playwright supports `--port`. D-9 lists the loopback bridge as runner-up without analysis.
- Failure: a Windows user calling `run_muse_with_browser(tools=["playwright"])` gets `browser.mount_unsupported`, which contradicts the function's name and §4's usage example, and the README promise is unqualified.
- Smallest fix: state the limit in §2, §4 and the README, and add an AC that pins it. Add an optional `[scope-adding]` Q-15: "host keyless stdio tools on Windows loopback HTTP for Muse WSL?" (default: not built). That keeps the endorsed refusal of stdio on Muse WSL.

**R-10 [Major] [L5] §7 FR-14 / D-11 / AC-12 — the required check has holes on Muse and opencode**
- Evidence:
  - **Muse:** vendor facts §1:37-45 says a configuration error disables all MCP, exits 0, and leaves its only trace in `session.jsonl`. FR-14 relies only on the vendor's required-server failure, so a zero-tool run is reported as success.
  - **opencode:** "≥ 1 mounted-tool call" passes when one of two mounted servers never started, yet AC-12 promises the error names the server. The same rule also fails a healthy run whose agent simply did not need a tool (EC-17, Q-9).
- Failure: the FR-14/G-2 guarantee ("a mounted server never ran" raises) is false in both directions on two of the three harnesses.
- Smallest fix:
  - **opencode:** make the evidence per server (each mounted server called at least once), or rename the guarantee honestly to "no mounted tool was used" and drop "naming the server" from AC-12.
  - **Muse:** add an EC for the silent-disable path with one mitigation, either reading the per-call `session.jsonl` status record or applying opencode's ≥ 1 call rule.

**R-11 [Major] [L1] §8.1 D-21 / FR-6 / §9.1 Exclusions — the seed set is decided silently, and one exclusion reason is inaccurate**
- Evidence:
  - The request asks for "15-20 popular ones" and leaves "Seed set" as an open question. D-21 ships 13 mountable tools, only 10 of the endorsed top 20, with no Q-n.
  - The `uvx` reason says "2.6–2.9 s cold start exceeds Grok's ~2 s grace". Vendor facts §4:283-284 shows 2903/2584 ms only on the first-ever start, and 557/777 ms warm, which is under the grace.
  - `scrapling` is in that row but was never measured.
- Failure: the user's explicit target is missed without a question, and a reviewer can disprove the stated reason from the spec's own sources.
- Smallest fix: add Q-16 "Ship 13 mountable tools, below the requested 15-20?" (default: yes, 13). Reword the uvx reason as "needs a Python `uvx` runtime the SDK does not pin; the first start exceeds Grok's grace". Move scrapling to "Not verified for this release".

**R-12 [Major] [L2] §8 / §8.4 / §12.3 — the 12-layer main function is copied three times (`<H>BrowserRun`), against the endorsed "one shared main function"**
- Evidence:
  - §8:316 has each harness own "the narrated twelve-layer main function", and §8.4 counts 9 per-harness classes.
  - Request C.0.2 "Where files go" and KD-2 call for one shared flow plus a per-harness compiler and reader.
  - INV-1 ("every function runs all twelve layers in order") then depends on three copies staying in step.
  - `BrowserToolCache` and the Node floor check are reusable process and tool-runtime jobs placed in hostkit (AGENTS principle 5).
- Failure: three copies of the preflight → mount → execute → read → require → complete/discard sequence drift. A fix to cleanup ordering or to the cancellation path has to land three times, and a review comment under principle 5 is likely.
- Smallest fix:
  - Write one narrated `NativeBrowserRun.execute` in hostkit that takes a small per-harness seam: `check`, `execute(mount)`, `tool_calls`, `missing`. That drops 3 classes and still meets every FR and INV.
  - Make `BrowserToolCache` a `lib/process` helper that returns an outcome record, and let hostkit map that record to errors.

**R-13 [Minor] [L9] §6.1 INV-14 vs INV-16 / D-19; EC-31 — two text inconsistencies around reused `<harness>.*` errors**
- Evidence:
  - INV-14 says the plain functions keep the "same … errors". D-19 widens `grok.output_too_large`'s cause, which the plain Grok functions also raise. Only INV-16 states that exception.
  - Reused next-step texts name plain functions: `OPENCODE_OUTPUT_TOO_LARGE` says "split the task across several `continue_opencode_thread` calls", and `*_THREAD_NOT_FOUND` name `run_/fork_*_thread`. Following them from a browser call drops the tools (EC-31).
- Failure: an implementer reading INV-14 alone refuses D-19, and a browser caller following the advice silently loses its tools.
- Smallest fix: add "except D-19" to INV-14. Widen the four affected next-step texts to "… or the matching `_with_browser` function", or accept the gap explicitly in EC-31.

**R-14 [Minor] [L9] §6.1 INV-12 vs §6.3 EC-22 — "fresh per call" is promised but cleanup is best effort**
- Evidence: INV-12 says profiles are always removed. EC-22 says that when the reaper cannot start, "a leftover profile is ignored".
- Failure: a tester cannot write a passing test for INV-12 under EC-22. The invariant is still met in practice only because every call gets a new folder.
- Smallest fix: reword INV-12 as "each call starts from a new, empty profile; removal of the old one is best effort (EC-22)".

**R-15 [Minor] [L4] §8.5 readers / §11 — two conventions are left implicit**
- Evidence:
  - The readers return `tuple[tuple[BrowserToolCall, ...], bool]` (`(calls, truncated)`) across the wire → run → hostkit boundary, while AGENTS principle 4 prefers records between layers.
  - The field guide `blocking-lint-invariants.md` says "code that serves model-facing tools for a harness does not belong in native/". The spec never states why mounting third-party servers is not that (code-map item 18). REPO_MAP's native row ("no host objects, model-facing tools or servers here") is then edited by row 36 without that rationale.
- Failure: these draw review comments rather than causing breakage.
- Smallest fix: return a small `BrowserToolCalls(calls, truncated)` record from the readers. Add one sentence to §11: the SDK serves no tool; it only configures the vendor's MCP client to start pinned third-party servers.

## VERIFIED CLAIMS

**Held**
- **§13 pin list complete.** Checked in `test_harness_threads_surface.py`:
  - `EXPECTED_EXPORTS` has 17 names, and the subpackage `__all__` sort-equals the 3 `*_thread` names.
  - The signature test iterates only the `*_thread` FUNCTIONS, so the new functions need no signature pin.
  - `EXPECTED_ENUMS` lists for `GrokFlag`, `MuseFlag`, `NativeEnvironmentVariable` (names equal values), `OpencodeEventType`, `NativeThreadOperation` and `NativeThreadProblem`.
  - The FailureCode tail after `RULE_EVALUATION_FAILED` equals `NEW_FAILURE_CODES` (28 → 32).
  - `sorted(lib_api.process.__all__) == ["CliArgv","CliRunner","ProcessStopper"]` gains `ProcessReaper`.
- **Errors-test key set.** `test_every_code_has_its_own_likely_cause_and_next_step` keys on the 28 codes plus `CONFIGURATION_INVALID_ARGUMENT` and `RUNTIME_ERROR`, and the texts are unique per harness. +4 is correct.
- **Static policy.** `NAMED_MODULES` holds 14 modules plus an rglob of `native/`, and allows only docstrings, `__all__`, `""`, `0` and `1` as literals. There is no allow-list.
- **D-19 is safe.** No test pins the `grok.output_too_large` literal, and conftest compares against the tables.
- **A-16 holds.** Other tests touch `vidbyte.lib.enums.__all__` only through subset checks.
- **`NativeThreadError.expected`** is `f"{operation.value} returning a NativeThreadResult"` (`lib/errors/base.py:601`), with no `result_record` keyword today.
- **`import vidbyte` / root API.** The root imports explicit enum names, so root `__all__` is unaffected. Importing `vidbyte.harnesses.native` already loads `vidbyte.tools`, `vidbyte.agents` and `vidbyte.lib.registries`, so code-map item 20 is moot.
- **#1036 internals match the spec:**
  - Grok `_argv` is JOINED with `--output-format=json`, and its env overlay is `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `GROK_HOME` and `GROK_DISABLE_AUTOUPDATER`.
  - Muse `_prepare_config` uses `mkdtemp`, and its overlay holds `XDG_CONFIG_HOME`.
  - `MuseLauncher.wsl_mode` is a property.
  - `from_configuration_error` scrubs registered secrets and applies `HarnessRedactor`.
- **Validation helpers.** `to_tuple` refuses a str without quoting it, and `to_mapping` returns a `MappingProxyType`.
- **Line counts and sizes.** REPO_MAP native row is at 163-165. README sizes are within A009 (harnesses 10,972 chars; registries 7,424).
- **Machine and docs:**
  - Node v22.12.0 is installed, and `C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js` exists (A-8 on Windows).
  - Grok `--allow`/`--deny` are repeatable (14-headless-mode.md:39-40,120).
  - The opencode `CONFIG_CONTENT` deep merge is real (vendor facts §3:218).
  - The registry tool names and counts match vendor facts §4.

**Did not hold**
- **§11:663 "Typecheck: none".** S009 staged mypy runs inside `lint/run.py` (346 vs 350).
- **D-9 "Grok has no verified per-run remote channel".** It is unprobed, but the Grok guide documents HTTP entries with headers in agent `mcpServers` (07-mcp-servers.md:407, 16-subagents.md:220). Keyless jina/parallel could mount on Grok under a new A-n. The keyed remote case stays refused under KD-6, because `bearer_token_env_var` is documented only for `config.toml` (26-config-reference.md:400).
- **The uvx exclusion reason.** It holds only for the first-ever start (R-11).
- **§13 "`CONTRACT_CONSTANTS` changes".** It needs no change.
- **§12.4's lint coverage is incomplete.** S020, S061, S041/S047/S052 and the semgrep pattern are missing (R-2).
