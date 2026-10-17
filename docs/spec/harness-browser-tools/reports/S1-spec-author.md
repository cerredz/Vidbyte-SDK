# S1 spec author report — harness-browser-tools

- **Stage:** S1 spec author
- **Date:** 2026-10-17
- **Spec:** `docs/spec/harness-browser-tools/spec.md`, revision r1, commit `db79ae32`
- **Base:** `845a4d9b`
- **Branch:** `feat/harness-browser-tools`

## What I read

**Under docs/**, only the five allowed files:
- `request.md`, in parts: §A prompts, §C decisions, constraints, hints and open questions, §D weighted words;
- `context/code-map.md`;
- `context/vendor-facts.md` §1–§8;
- `reports/S0-scout.md`;
- `reports/S0-vendor-scout.md`.

**Rules:**
- `AGENTS.md`, all of it;
- `REPO_MAP.md:160-170`;
- `vidbyte/harnesses/README.md:176-186`;
- `vidbyte/lib/README.md` and `vidbyte/lib/registries/README.md`;
- the field-guide entries listed in spec §11;
- the lint rules S020, S054 and S055.

**#1036 code:**
- `vidbyte/harnesses/native/{grok,opencode,muse}/{__init__,threads,wire}.py`;
- `vidbyte/harnesses/native/muse/launcher.py`, including the WSL reap and peer mark;
- `vidbyte/harnesses/native/hostkit/{__init__,errors,launcher,skills}.py`;
- `vidbyte/harnesses/native/__init__.py`.

**lib:**
- enums: `native_threads`, `failure`;
- dataclasses: `native_threads`, `process`, `validation`;
- `constants/native_threads.py`;
- `errors/base.py`, for `NativeThreadError` with `expected` and `relevant_tests`;
- process: `__init__`, `runner`;
- registries: `runtimes`, `provider_keys`, `__init__`.

**Tests:**
- `tests/features/harness_threads/{conftest,fake_harness}.py`, reading the structure and the sandbox seam;
- the surface, static-policy and errors tests, for the pins the change moves;
- `pyproject.toml`.

**Vendor sources:**
- Grok user guide: `14-headless-mode.md` (flags, streaming-json event table) and `26-config-reference.md`;
- the Grok probe logs, in vendor-facts and S0 scratch;
- `@playwright/mcp` 0.0.83 capability declarations and Chrome channel lookup (`coreBundle.js`);
- chrome-devtools-mcp 1.11.0 browser options;
- env-var names in each package's source;
- the remote README/docs for Jina, Parallel and Browserbase.

I did not read the `vidbyte-sdk-browser-agent` worktree, and nothing in the spec is named `BrowserAgent`.

## Approaches weighed

### Overall shape

1. **Raw MCP configs passed through a `tools=` argument.** This was the smallest design and I rejected it (§8.3). It has no registry, pin, install, cleanup or reader, so it fails FR-5/6/9/14/15 and INV-1 ("each function has all layers").
2. **A `tools=` keyword on the nine plain functions.** Rejected. It breaks INV-14 (plain functions byte-identical) and Prompt 3's names.
3. **Separate browser run classes that copy the #1036 flow.** Rejected (D-3). It duplicates the launcher, key, timeout and reader rules.
4. **Chosen:**
   - an optional `mount` on each `<H>ThreadRun.execute`, returning `NativeThreadRun(result, outcome)`;
   - thin `<H>BrowserRun` main functions that run the twelve layers.

   The plain `_call`s take `.result`, so plain behaviour is unchanged.

### Grok channel

I weighed a `config.toml` in the private home plus a per-home lock (the request's open question) against a per-call `--agent` file.

- **Chosen: the agent file.** The private home is shared per workspace, so concurrent calls with different tool sets would collide.
- The agent-file route is verified: the sequence form, used with `-p`, adds servers beside `config.toml`'s.
- Concurrent runs sharing one `GROK_HOME` work (vendor facts §2/§7).
- Keys travel in Grok's env overlay, which servers inherit. Agent-file env does not expand `${VAR}`.

### Other decisions

- **Codes:** 12 per-harness codes versus 4 shared `browser.*` codes. **Chosen: shared (D-13).** The cause is the tool, and the existing 9-problem × 3-harness grid that the tests enumerate stays intact.
- **Cleanup:** an env-filter or tree-kill wrapper per server versus a command-line-marker reaper after the harness exits. **Chosen: the reaper (D-12).** Chrome is detached on POSIX, and `taskkill /T` misses grandchildren of an exited leader. The per-call folder is on every browser's command line. `MuseLauncher.reap` is house precedent.
- **Install:** `npx -y pkg@ver` versus the npm bundled with Node, installing into `~/.vidbyte/tools`. **Chosen: the cache (D-5).** On Windows `npx` is a batch file that `NativeLauncher` would refuse, and its first run is slow.

## Where I disagree with the request or scout (with evidence)

1. **"15-20 popular ones" mountable.**
   - The registry knows 31 names, but only 13 are mountable. The other 18 are answered by name, with a reason.
   - The evidence is in vendor facts §4/§7:
     - wdio 4.0.0 fails to start on Node 22.12;
     - the uvx servers (fetch, duckduckgo) cold-start in 2.6–2.9 s, beyond Grok's measured ~2 s grace, so they would never be usable in one-turn Grok runs;
     - browserstack needs two credentials;
     - kernel and cloudflare are OAuth-only;
     - crawl4ai needs Docker;
     - agent-browser, @playwright/cli, midscene and devbrowser are CLI+skill tools, not MCP servers.
   - Shipping them as mountable would violate the "every entry verified" rule (KD-4).
2. **"Every harness" does not mean every tool on every harness.** The mount table (spec §9.1) refuses the following with `browser.mount_unsupported`:
   - **Muse keyed tools.** Muse has no env inheritance and no `${VAR}` expansion, so a key would have to be a literal in `settings.json`, which KD-6 forbids.
   - **Muse WSL stdio tools.** WSL has no Linux Node, and Windows Node through interop fails.
   - **Grok remote tools.** There is no verified per-run remote channel.

   As a result, Muse WSL gets only jina and parallel (keyless remote), and Browserbase works only on opencode.
3. **Env-filter launcher.** The request §C.0.2 Insight recommends it. I default it to no (D-17, Q-7):
   - The probe (vendor facts §6) shows it works for server env.
   - It does not hide keys from the agent's own shell, because for Grok and opencode the keys sit in the harness env either way.
   - Killing only the wrapper orphans the real server on Windows (§6c).
4. **Required check on opencode.** opencode prints no MCP status in `run --format json`, and a failed server only logs. The only evidence is a mounted-tool call, so a browser run whose agent used no browser tool raises `browser.tools_unavailable` (EC-17). That is stricter than "the server never ran". It is flagged as Q-9 (default yes).
5. **Cache folder name.** The request terminology says `~/.vidbyte/tools/<name>@<version>`. The spec uses `<tool>-<version>`, which keeps scoped-package `@` and `/` out of path segments and matches `BrowserTool` values.
6. **Touching an existing text.** `grok.output_too_large`'s likely cause names only `GROK_CLI_MAX_OUTPUT_BYTES` and "one JSON answer". The browser path streams, and screenshots can push the stream past 4 MiB, so the browser path uses `NATIVE_PROCESS_MAX_OUTPUT_BYTES` and the text widens to name both caps (D-19). The tests compare the error to the table, not to a literal (verified in `test_harness_threads_errors.py:193-204`, `conftest.py:307-308`).
7. **Scout.** I found no factual disagreement with S0. One fact is new: `MuseExecOutput.read` already maps a failed `run.terminal` to `muse.run_failed`, with the reason as `vendor_message` (`muse/wire.py`). That is the hook the Muse required-server translation uses.

## Assumptions I am least sure of (spec §15)

- **A-1 — Muse tool-call record format.** I assumed `mcp__<srv>__<tool>` in `task.lifecycle.proposed`/`side_effect_intent` `task_kind`/`operation`. The echo provider cannot call tools, so this is unverified. If wrong, only `MuseExecOutput.tool_calls` changes.
- **A-2 — Muse `exec` allows MCP calls headless without an approve-all mode.** If wrong, the implementer must stop BLOCKED; an approve-all mode is forbidden.
- **A-5 — Grok's `--agent` body supplements the coding agent rather than replacing its prompt.** If wrong, D-7 flips to `config.toml` plus a per-home lock, which is a BLOCKED report.
- **A-4 — Grok accepts these forms:** JSON flow-style frontmatter; the joined forms `--agent=`, `--allow=` and `--deny=`; and `--agent` with `--resume` and `--fork-session`.
- **A-6 — Grok's final answer** is the last non-empty text segment between `usage` boundaries.
- **A-8 — `npm-cli.js` beside Node.** It is absent on Debian apt Node; EC-13 covers that gap with a clear code.
- **A-13 — `ps -A -ww` availability** (BusyBox lacks `-ww`).
- **A-10, A-11 and A-12 — key rules and remote tool names.** Tavily's key rule is required, exa works keyless, and the remote tool names come from docs (no probe).

## Counts

- G 5 · NG 14 · INV 18 (13 new + 5 must-not-regress) · AC 24 · EC 38 · FR 19 · NFR 9 · D 21 · T 5 · W 13 · A 16 · Q 13 (0 blocking).
- Budget: 12 new files and 30 new classes. 0 new dependencies, 0 config keys and 0 tables. 9 public functions and 2 re-exported records.
- §12.3 has 37 rows in 5 phases.

## Addendum — revision r2 (review r1 applied), 2026-10-17, commit 9921722e

Triaged all 15 findings in `reports/S1-spec-review.md`; dispositions are in spec §16. 14 accepted, R-12 accepted in part.

- **What I verified before applying:**
  - vendor facts §1: Muse `schema_version`, bad-entry silent disable, the 127.0.0.1 route "under mirrored networking", servers start in the workspace;
  - `lint/baseline.json`: S020 1, S061 6, S041/S047/S052 0, A007 255, S009 350;
  - `lint/rules/s061_bounded_safe_path.py`: the `….backend` receiver exemption, and `args[0]` is the checked argument;
  - `LocalFileSystemBackend.write_text`, and its `self.backend` precedent in `vidbyte/agents/infinite/workspace.py`;
  - `vidbyte/lib/errors/base.py`: enums are imported only under `TYPE_CHECKING`;
  - the five `_thread`-naming next-step texts in `constants/native_threads.py`;
  - the Grok guide: HTTP entries in agent `mcpServers` are documented, but their keys are not (07-mcp-servers.md:407, 16-subagents.md:220).
- **Muse on Windows, R-9 and the coordinator's steer.** I weighed the loopback bridge seriously. It is real but too large and too unverified for this PR, for four reasons:
  - 127.0.0.1 from WSL reaches Windows only under mirrored networking, and WSL defaults to NAT;
  - among the stdio tools, only Playwright has a known HTTP mode (`--port`);
  - it needs an SDK-owned server lifecycle: port choice, readiness and stop;
  - it exposes an unauthenticated local endpoint that drives a browser.

  I stated the limit plainly instead (§2, §4, EC-42, AC-19, README row): Muse on Windows mounts only jina and parallel, and every stdio tool raises `browser.mount_unsupported`. I added Q-15 with both routes, the bridge and an in-distro Node. Grok keyless remote is likewise Q-18, unprobed.
- **Where I diverged from the reviewer's suggested fix:**
  - **R-10 Muse.** I prevent the silent disable by construction (AC-26) and accept the residual in EC-39 and Q-17. The reviewer's "≥ 1 call" option would make every Muse call depend on A-1, the unverified tool-call format.
  - **R-12.** I did not move `BrowserToolCache` to `lib/process` (D-26). It has no second caller.
  - **R-13.** I widened five texts, not four. `GROK_THREAD_NOT_FOUND` also names plain functions.
- **Least sure now:** A-1, A-2, A-5, plus two new ones:
  - A-17: in opencode, a wildcard deny followed by an exact allow keeps the tool listed;
  - A-18: Grok accepts an exact `MCPTool(...)` in `--allow`.
- **Counts r2:**
  - IDs: G 5 · NG 14 · INV 18 · AC 28 · EC 43 · FR 19 · NFR 9 · D 26 · T 6 · W 13 · A 18 · Q 18 (0 blocking).
  - Budget: 12 new files and 31 classes.

## Addendum: revision r3 (final; applies review r2 and vendor facts §9)

Commit 14930722 (spec.md only). Frontmatter: `revision: 3`, `status: approved`.

**What I verified in the code before writing**
- `RecordFieldValidator.require_text` and `require_text_items` end with `got {_received(...)}`, which quotes values up to 80 characters unless the field name is credential-named. `accepts_text(value, *, max_chars, pattern=None)` at line 51 does not raise. `to_tuple` and `to_mapping` name only the type, so they never quote. This led to D-28.
- A006 builds its graph from AST imports, including imports inside functions. It skips façade `__init__` modules and `TYPE_CHECKING` blocks, and it reports every edge of a cycle.
  - Today, harness modules import hostkit only through its façade.
  - `muse/launcher.py` imports only hostkit and lib, so `browser → launcher` is safe.
  - `hostkit/browser.py` must import `hostkit.errors` from its concrete module, because the façade imports this module. This is in D-27 and row 16.
- `lint/core/report.py:58` prints `SDK-LINT: PASS`. CI runs on `ubuntu-latest`. `conftest.py:396` has `wsl_ready`, which runs on win32 only and builds a `wsl.exe` stand-in. The REPO_MAP `vidbyte/lib/process/` row lists three helpers.
- `vidbyte.lib.tools.filesystem.backends.local` imports only lib, so the writer adds no import cycle.

**R-16 (Blocker).** I applied the reviewer's smallest fix.
- `<H>Mounts` holds only compile helpers, and `mounts.py` imports only lib and hostkit.
- The seam is now `<H>BrowserHarness(config)` in `browser.py`.
- Classes go from 31 to 34. The file count stays at 12.

**Q-15 / Muse on Windows: re-weighed, kept as Q-15 (not built).** First the facts, corrected:
- MuseUbuntu1 is WSL 1, so it shares Windows' loopback.
- Muse mounted a Windows `127.0.0.1` HTTP MCP with default settings.
- A WSL 2 distro would need mirrored networking. That is untested.

I took the coordinator's steer and the user's words seriously. On this user's own machine, Muse runs only in WSL mode, so without the bridge `run_muse_with_browser` has no browser there. The bridge is the smallest route to one. I still did not build it, for three reasons:
1. Playwright 0.0.83's HTTP mode has never been probed: `--port`, binding to `127.0.0.1`, the readiness signal, and Host-header checks.
2. It needs a new SDK-owned server lifecycle. Today's helpers are one-shot.
3. Its posture is unacceptable without those probes. It would be an unauthenticated loopback endpoint whose core tools include `browser_run_code_unsafe`, `browser_evaluate` and `file://` navigation. For the whole call, any local process of any user could drive it, and so could a hostile page through DNS rebinding. That is the pattern of the MCP Inspector advisory (CVE-2025-49596).

Q-15 now lists these prerequisites and the posture, so the user can decide with the facts. §2 says exactly what Muse in WSL mode mounts: only keyless jina and parallel. The nearest thing to a browser there is Jina's remote `capture_screenshot_url`.

**Q-18: re-decided, now built.** Grok mounts the keyless remote tools, jina and parallel, as url-only agent-file entries.
- This form was verified under `-p`.
- Keyed remote tools stay refused, because Grok does not expand `${VAR}` in agent-file headers.
- The residual risk is A-19: how real servers answer Grok's `server/discover`. The required check catches it as EC-45.

**Other dispositions.** All other findings were accepted as the reviewer proposed: R-17 (D-28), R-19 (readers skip bad names), R-20 (`NATIVE_PS_PATHS`), R-21, R-22, R-23, R-24, R-25 and R-26. The round-1 partials R-2, R-7, R-9 and R-12 are closed.

**Least-sure items after r3**
- A-1 and A-2: the Muse tool-call record, and whether MCP calls are allowed headless.
- A-5: whether the Grok agent body weakens the coding prompt.
- A-19: whether real servers tolerate `server/discover`.
- The `(?i)` grammar pattern in `BROWSER_TOOL_STRING_PATTERN`: it is the first case-insensitive pattern run through `accepts_text`. An implementer may prefer to lower-case the item before checking it.

**Counts:** G 5, NG 14, INV 18, AC 33, EC 45, FR 19, NFR 9, D 28, T 6, W 13, A 19, Q 18 (none blocking; Q-18 resolved). §12.3 still has 37 rows and 12 Add rows. The only undefined ID is INV-20, an external reference to #1036.

## Addendum: revision r4 (aligned with the S2 tests; not a review round)

Commit b125e64b (spec.md only). Frontmatter: `revision: 4`; `status: approved` is unchanged. Nothing about the architecture or behaviour changed. I only wrote down choices the S2 tests made where the spec said nothing (S2 report, "Spec defects and ambiguities", items 1 to 8).

**What I read (read-only):**
- `conftest.py`: `check_browser_error` asserts `error.next_step == NATIVE_THREAD_NEXT_STEPS[code]`, and checks the message order: function, code, label, workspace, thread id, observations, vendor text, cause, next step.
- The AC-18, AC-19 and EC-12 tests: each looks for the situation detail (`narrow|fewer`, `jina`/`parallel`, the folder) anywhere in `str(error)`.
- The registry test pins Playwright's exact `core` set, the count in each group and the 41-tool union. It pins only the trailing entry parts.
- The surface test orders `BROWSER_FUNCTIONS` harness-major.
- The EC-14 and EC-22 tests patch `Path.home` and `NATIVE_PS_PATHS`.
- The Muse AC-12 test passes no thread id.
- `hostkit/errors.py`: `failure` already prints the observation, built from its detail argument, before the cause and the next step.

**Gap 2 decision (D-29):**
- Each code keeps exactly one cause text and one next-step text, as FR-16, INV-6 and the #1036 tables already said.
- The guidance for each situation (the budget, the tools that WSL mode can mount, the broken folder) goes in the observation.
- It is the only reading that satisfies all three tests: a folder path cannot sit in a fixed next-step text, and the tests require the next step to equal the table's text.

**Tests against decisions the spec made:** I found none. I checked:
- the contract test's pinned names, constants, record fields and allowed sibling imports (threads → launcher is allowed, as D-27 implies);
- the bindings in the test plan: the Grok agent body, the key routes and the children rules;
- the AC-27 and AC-18 assertions.

This was not an exhaustive audit of all 177 tests.

**Counts:**
- IDs: G 5, NG 14, INV 18, AC 33, EC 45, FR 19, NFR 9, D 29, T 6, W 13, A 19, Q 18.
- §12.3 still has 37 rows, 12 of them Add rows.
- The §8.4 budget is unchanged: 12 files and 34 classes.
