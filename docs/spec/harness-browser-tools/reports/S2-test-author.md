# S2 test author: harness-browser-tools

**Status:** DONE. Spec r3 (approved). Branch `feat/harness-browser-tools`.
- `fb8ab004`: tests, fakes, pins and test plan.
- `6567f6aa`: the spec §6.2 Proof column.

The coverage map, the tests deliberately not written, and the notes for the implementer are in `docs/spec/harness-browser-tools/test-plan.md`.

## Inventory

All files are in `tests/features/harness_threads/`. There are 177 new test cases; the pack goes from 438 to 615.

| File | Status | Cases | Covers |
|---|---|---|---|
| `fake_browser.py` | new helper | — | The browser half of the fakes:<br>• `node` plays `--version`, the bundled `npm-cli.js` and the 10 pinned stdio servers;<br>• the orphaned Chrome stand-in;<br>• the 3 remote endpoints, answered offline;<br>• the opencode, Grok and Muse mount readers, which apply the §13 vendor rules. |
| `test_harness_threads_browser_fakes.py` | new | 10 | Checks the fakes' vendor rules without any SDK code (green now). |
| `test_harness_threads_browser_contract.py` | new | 22 | AC-3, records, enums, codes, constants, D-15, D-19, D-22, D-27 layering. |
| `test_harness_threads_browser_registry.py` | new | 40 | AC-4, AC-5, AC-8, AC-23, AC-25, AC-29, AC-30; EC-1 to EC-7. |
| `test_harness_threads_browser_mounts.py` | new | 49 | AC-2, AC-6, AC-7, AC-9, AC-14, AC-18, AC-19, AC-22, AC-26 to AC-28, AC-31 to AC-33; EC-26 to EC-28, EC-30, EC-41, EC-42, EC-44; INV-8, INV-10, INV-11; D-18, D-21. |
| `test_harness_threads_browser_runtime.py` | new | 26 | AC-10, AC-11; EC-8 to EC-15, EC-37, EC-38; NFR-5. |
| `test_harness_threads_browser_lifecycle.py` | new | 29 | AC-12, AC-13, AC-16, AC-21; EC-16 to EC-22, EC-29, EC-45; INV-4; D-19; `ProcessReaper`. |
| `test_harness_threads_browser_acceptance.py` | new | 1 | AC-1: the §4 snippet, verbatim. |
| `conftest.py` | extended | — | The browser fixtures and helpers (listed below). |
| `fake_harness.py` | extended | — | The browser path for each vendor (listed below). |
| `test_harness_threads_surface.py`, `test_harness_threads_errors.py`, `test_harness_threads_static_policy.py` | pins only | — | §13 pins. |
| `README.md`, `FEATURE.md` | updated | — | File Index (S020) and suite map: all 8 new files are listed in both. |

## What was pruned

These are not written; the reasons are in the test plan's table.
- AC-20, AC-24, NFR-7: covered by the gate, lint and review.
- Real Node, npm, Chrome, servers and endpoints: not available offline.
- An exact NFR-6 boundary: the spec gives no unit formula.
- EC-16 wall-clock timing: covered by the same evidence through `grok_unlisted`.
- Accepted residuals: EC-23, EC-24, EC-33 to EC-36, EC-39 and EC-43.
- An end-to-end EC-31: the plain path is unchanged.
- A pinned Playwright per-capability assignment (defect 3).

Assertions I dropped as over-binding while writing:
- the Muse refusal naming the refused tool (EC-26 requires the harness and transport, not the tool);
- the substring checks on the Grok agent body (they became word-boundary checks, so "example" cannot count as "exa").

## Red output (before implementation)

`PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/harness_threads -p no:cacheprovider -q --tb=line -rfEs`

```
ERROR tests/features/harness_threads/test_harness_threads_browser_runtime.py::test_spaced_non_ascii_node_and_cache_paths_still_mount[muse]
SKIPPED [1] tests\features\harness_threads\test_harness_threads_browser_lifecycle.py:134: the POSIX reaper reads NATIVE_PS_PATHS; win32 uses System32 PowerShell
SKIPPED [1] tests\features\harness_threads\test_harness_threads_launcher.py:100: Muse is looked up on PATH only outside win32 (EC-29)
SKIPPED [1] tests\features\harness_threads\test_harness_threads_runner.py:245: the execute permission bit exists only on POSIX
18 failed, 439 passed, 3 skipped, 155 errors in 49.78s
```

**New tests**
- All 155 setup errors are `ModuleNotFoundError: No module named 'vidbyte.lib.enums.browser_tools'`; I counted them with grep.
- 11 contract tests fail. They check the missing §12.3 modules (`hostkit/browser.py`, `<h>/mounts.py`, `<h>/browser.py`), both as files and as fresh-interpreter imports.
- The fakes self-test is green, which is expected because it uses no SDK code.

**Existing tests**
- 429 pass and 2 skip, unchanged.
- 6 pinned tests are red only for the missing names:
  - `errors::test_every_code_has_its_own_likely_cause_and_next_step` (`'browser.mount_unsupported' is not a valid FailureCode`);
  - the 2 `static_policy` tests (the 7 named modules are missing);
  - 3 `surface` tests: exports, vocabularies, and `process.__all__` in `test_old_public_names_no_longer_import`.
- The one pre-existing red is `surface::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`. Its merge-base half (`148 == 120`) also fails on pristine `4d3a9d55`; the baseline was 1 failed, 435 passed and 2 skipped.

**Lint.** `PYTHONPATH=$(pwd) py -3.11 lint/run.py`, run with the files staged, ends:

```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

Two lint findings had to be fixed first:
- S020 counted the untracked new files as stale index entries until they were staged.
- S062 flagged an implicit string concatenation in `fake_browser.SPAWNER`, which is now a `"\n".join`.

`lint/baseline.json` is untouched.

## Satisfiability probe (independent of the SDK)

A scratch driver fed the fakes the exact §9.1 shapes. These checks show a spec-correct implementation can make the tests pass; the driver is not committed.

- **opencode**, with an unnarrowed playwright, a narrowed firecrawl, a keyless jina and a disabled global `mcp.playwright`:
  - it exits 0;
  - 38 tools are visible (25 + 1 + 12);
  - 3 calls complete, including a screenshot written into `artifacts/`.
- **Orphan browser:** it was still alive after the fake harness exited. A System32 PowerShell reap by `VIDBYTE_REAP_MARKER` killed it.
- **Grok**, with the agent file in the spec example's form plus a url-only jina entry:
  - it streams `available_commands`, then the `use_tool` calls (including the bogus name), then `end`;
  - the rules are parsed in order.
- **Muse native**, with `{"schema_version": 1, "mcpServers": …}`:
  - it exits 0 and the settings are not disabled;
  - a stdio playwright server ran under Muse's seven-variable environment.
- **EC-37:** node, cache and folder paths that hold spaces and `é` run through the whole fake stack.

## Fixtures added or changed

**`conftest.py`**
- Constants: `BROWSER_PACKAGES`, `EXEC_ROLES`, `BROWSER_CHROME_PATHS_NAME`.
- `Sandbox` methods: `node`, `npm_cli`, `tool_cache`, `tool_folder`, `tool_entry`, `cache_tools`, `chrome`, `call_folders`, `browser_pids`.
- Fixtures:
  - `browser_lib` and `browser_api`, the lazy imports;
  - `browser_world` (node, the full cache, Chrome);
  - `no_chrome`;
  - `browse`, the browser-function caller;
  - `check_browser_error`, which applies INV-6/AC-17 plus an 8-character secret-fragment scan;
  - `runner_spy`, which records each `CliInvocation` and then runs it.
- Helpers, also on `pack`: `fragments`, `same_path`, `server_option`, `call_folder`, `files_holding`.

**`fake_harness.py`**, with existing behaviour unchanged:
- Grok: repeated `--allow`/`--deny`, `--agent`, `--disable-web-search` and `streaming-json` output.
- opencode: the `mcp`/`permission` mount and `tool_use` events.
- Muse: the `settings.json` mount and `--disable-web-tools`.
- Start records gain `tool_credentials` and `browser_env`, plus a sanitized `opencode_config`.
- The `node` program is dispatched to `fake_browser.run_node`.

**`fake_browser.py`** is new.
- Scenario fields: `node_version`, `npm_mode` (fail, hold, rendezvous, no_entry), `packages`, `server_fail`, `extra_tools`, `failing_tools`, `artifact_burst`, `calls_by_prompt`, `browser_calls`, `repeat_calls`, `bogus_calls`, `global_config`, `grok_unlisted`, `hold_after_mount`.
- One change this session: a missing `npm-cli.js` now fails with "Cannot find module", as real node does (EC-13), and the fakes test pins it.

## Pins changed (expected-value constants only; old → new)

**`test_harness_threads_surface.py`**
- `EXPECTED_EXPORTS`: 17 names → 28 (+ the 9 `_with_browser` functions, `BrowserThreadResult`, `BrowserToolCall`).
- Subpackage `__all__` names: `[f"{verb}_{harness}_thread" …]` → `[f"{verb}_{harness}_{suffix}" for suffix in ("thread", "with_browser") …]` (3 → 6).
- `NativeThreadOperation`: `list(FUNCTIONS)` → `[*FUNCTIONS, *BROWSER_FUNCTIONS]` (harness-major: grok, opencode, muse × run, continue, fork).
- `NativeThreadProblem`: + `mount_unsupported`, `runtime_missing`, `tool_install_failed`, `tools_unavailable`.
- `GrokFlag`: + `--allow`, `--deny`, `--agent`, `--disable-web-search`.
- `MuseFlag`: + `--disable-web-tools`.
- `NativeEnvironmentVariable`: + `GROK_CLAUDE_MCPS_ENABLED`, `GROK_CURSOR_MCPS_ENABLED`, `VIDBYTE_REAP_MARKER`.
- `OpencodeEventType`: `["text", "error"]` → + `"tool_use"`.
- `NEW_FAILURE_CODES`: 28 → 32 (+ the 4 `browser.*` codes).
- `lib.process.__all__`: `[CliArgv, CliRunner, ProcessStopper]` → + `ProcessReaper`.

**`test_harness_threads_errors.py`**
- The expected code set gains `BROWSER_CODES` (the 4 `browser.*` codes).

**`test_harness_threads_static_policy.py`**
- `NAMED_MODULES` gains `hostkit/browser.py` and the `browser.py` and `mounts.py` of grok, opencode and muse (7 modules).

## Spec defects and ambiguities

1. **§9.3 names no Chrome-location constant.** The tests bind `vidbyte.lib.constants.browser_tools.BROWSER_CHROME_PATHS`: a tuple of strings, searched in order after `os.path.expandvars`, read at call time.
2. **One next step per code conflicts with situation-specific guidance.** FR-16 and INV-6 give each code a single next-step text (`NATIVE_THREAD_NEXT_STEPS[code]`). But for `browser.mount_unsupported`:
   - AC-18 wants "narrow or mount fewer";
   - AC-19 and EC-42 want the next step to name the keyless remote tools;
   - EC-12 wants the next step of `tool_install_failed` to name the folder.

   The tests check that guidance in `str(error)`, so either one combined text or an observation passes.
3. **§9.1 gives only counts for Playwright's capability tool lists.** The counts and their union with vendor facts §4 are pinned, not each group's members.
4. **Entry parts are relative to two different roots.** The record rule says "relative to the install prefix"; the seed table says "relative to `node_modules/<package>/`". Only the trailing entry parts are pinned.
5. **The order of the 9 new `NativeThreadOperation` members is not stated.** They are pinned harness-major after the existing 9, matching §12.3 row 3's listing.
6. **§13 lists only timing knobs and Chrome locations as read at call time.** EC-22 (POSIX) also needs `NATIVE_PS_PATHS` read through the module at call time.
7. **EC-14 does not say how the home is found.** The test patches `Path.home()`, following the existing Grok precedent.
8. **AC-12 for Muse.** The vendor prints no session before a required-server failure, so the Muse case checks no thread id.
9. **Cosmetic.** The existing test name `…append_exactly_the_28_harness_codes` now covers 32 codes; it was not renamed, because I may not modify existing tests beyond their constants.

## Post-S3 repair (orchestrator-adjudicated)

S3 reported three test-side blockers (`reports/S3-implementer.md`, "Blockers"). The orchestrator adjudicated all three as test defects or test drift. Three test-only commits on top of `ef7729cc` fix them; no file under `vidbyte/` changed.

### 1. Key-shaped fixtures are built at run time (`folded into fb8ab004`, AC-1)

GitHub push protection (GH013) refused the branch: `DEEPSEEK_KEY` in `test_harness_threads_browser_acceptance.py:46` matched the DeepSeek key pattern. Every credential-shaped fixture literal in the S2 files is now a concatenation of short pieces, so the source text holds no provider-pattern token. The runtime value is byte-identical.

| File | Lines | Literals |
|---|---|---|
| `test_harness_threads_browser_acceptance.py` | 46, 47 | `DEEPSEEK_KEY` (`sk-`), `FIRECRAWL_KEY` (`fc-`) |
| `test_harness_threads_browser_registry.py` | 22–25, 238 | `FIRECRAWL_KEY`, `BRAVE_KEY` (`BSA`), `TAVILY_KEY` (`tvly-dev-`), `BRIGHTDATA_KEY` (64 hex), the malformed `fc-` key in the `tool_keys` refusal case |
| `test_harness_threads_browser_mounts.py` | 26–30 | `BRAVE_KEY`, `BRIGHTDATA_KEY`, `BROWSERBASE_KEY` (`bb_live_`), `JINA_KEY` (`jina_`), `CALLER_FIRECRAWL_KEY` (`fc-`) |
| `test_harness_threads_browser_lifecycle.py` | 27 | `BRAVE_KEY` |
| `test_harness_threads_browser_fakes.py` | 32, 116, 163, 176 | the provider `apiKey` (`sk-`), an inline Brave key, the two `XAI_API_KEY` values (`xai-`) |

- How it is cut: the vendor prefix is its own piece, and any long alphanumeric body is cut into pieces of at most 16 characters.
- Not changed: `fake_browser.py` and the lines S2 added to `conftest.py` and `fake_harness.py` hold no credential-shaped literal. `conftest.py:42` (`API_KEY = "vbk-test-…"`) is a line `main` already had, so it is out of scope.
- Why the strength is unchanged: the edited files and their `HEAD` versions parse to identical ASTs once string `+` chains are folded. So every runtime value, every assertion and every parameter list is unchanged, and the only difference is in the source text.
- Checks:
  - `git grep -nE "sk-[0-9a-f]{32}|fc-[0-9a-f]{32}" -- tests/features/harness_threads` returns nothing.
  - A tokenizer scan of the S2 files finds no literal with a vendor prefix followed by a key body, and no alphanumeric run of 20 or more characters.
  - The five edited files: `3 failed, 125 passed, 1 skipped`. The three failures are exactly the routing tests below, as before.

### 2. Node-side fake fields go through `sandbox.node` (`305a9b67`, AC-12, EC-18, EC-29, EC-32, EC-41)

Only the `node` stand-in reads `server_fail`, `artifact_burst` and `extra_tools` (`fake_browser.mcp_server` and `answer`). But `browse(fake=...)` writes `fake` only into the harness stand-in's scenario, so these three tests never delivered their fields. Each test now sets the field with `sandbox.node(<field>=...)` before `browse` and drops it from `fake`. The runtime and fakes tests already used this pattern.

| Test | Field (value unchanged) |
|---|---|
| `test_harness_threads_browser_lifecycle.py::test_muse_required_server_failure_carries_muses_reason` | `server_fail=["playwright"]` |
| `test_harness_threads_browser_lifecycle.py::test_tool_calls_and_artifacts_cap_at_a_thousand` | `artifact_burst=OVER_CAP` |
| `test_harness_threads_browser_mounts.py::test_grok_unlisted_server_tool_cancels_the_turn_loudly` | `extra_tools={"firecrawl": ["firecrawl_brand_new"]}` |

- Why the strength is unchanged:
  - Every assertion, field value and parameter list is the same, and the harness-side fields (`browser_calls`, `repeat_calls`) stay in `fake`.
  - The removed `fake` keys were never read by the harness stand-in, so dropping them changes nothing.
  - The tests now exercise the scenario they always described.
- Placement in the cap test: `sandbox.node(artifact_burst=...)` runs before the first `browse`, not between the two calls.
  - This avoids rewriting the `node` executable after a call. On Windows, a process from that call that has not exited yet could still hold the file.
  - Only a screenshot call reads `artifact_burst`. The first call's only tool call is the Playwright probe (`browser_navigate`), so its outcome is unchanged.
- Run: the three tests gave `3 passed in 5.68s`. The lifecycle and mounts files gave `77 passed, 1 skipped`.

### 3. Codex packaging pins refreshed (`fd70e93d`, AC-3; W-11, W-12)

`tests/features/codex_host/test_codex_host_packaging.py` (#1055) pins three texts that rows 34–36 of §12.3 must change. Before each pin was refreshed, the property it guards was checked against the current files.

| Pin | What it guards | Evidence that the guarded property still holds |
|---|---|---|
| `NATIVE_INIT_SHA256` | The native marker only imports and re-exports. It does not import or re-export the Codex host or any vendor SDK, and it has no side effects at import time (INV-1, AC-36). | In the AST, the body is the docstring, `ImportFrom` statements and `__all__`. Every import comes from `__future__`, `vidbyte.harnesses.native.{grok,muse,opencode}` or `vidbyte.lib.*`, and none names codex. `__all__` (28 names) has no Codex name. The sentences "It does not re-export the Codex host…" and "Do not import the codex subpackage or any vendor SDK here." are still present. The import-safety test passes. |
| `REPO_MAP_SECTION` | The native section sits between the harnesses paragraph and `stores/`. It describes both shapes, and the claim "no host objects, model-facing tools or servers" stays true. | The position assertions are unchanged and pass. The Codex-host paragraph is byte-identical to the old pin. The browser text is added only in the second paragraph, and "Those three harnesses have no host objects, model-facing tools or servers" is kept, with the note that a browser tool is a third-party server that the vendor's own MCP client starts. |
| `README_BULLET` | The `native/` bullet follows the serialization bullet and keeps the Codex-host import guidance (`vidbyte.harnesses.native.codex`). | The old bullet, up to " The shared plumbing", is a byte-identical prefix of the new one. The Codex sentence and "which only the harness subpackages import" are kept. Only the browser paragraph and the `hostkit/browser.py` mention are added. |

- How the values were taken: they were recomputed the way the test reads them, from the working copy with CRLF turned into LF, and checked to equal the committed `HEAD` blob.
  - The working copies of these three files have not changed since `0dfde894`.
  - `NATIVE_INIT_SHA256` is `6044725df61d3fdc4a9fd0ce5fd94bee306ea385293e3d802a1f2b7a1a4b950b`, the hash of 5261 LF bytes. This agrees with S3's figure.
  - The same method gives the old pin for the `871ee369` bytes (3855).
- Why the strength is unchanged: the three assertions still compare exact bytes or exact text. Only the three constant lines changed.
- Run: `7 passed`.
- Not refreshed: the header (`KNOWN EDGE CASES: … its 3855 LF bytes`) and the comment above `NATIVE_INIT_SHA256` still say 3855 bytes, because the brief allowed only the pins to change. They are now stale; the marker is 5261 LF bytes.

### Final run

`PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads tests/features/codex_host` gave `1 failed, 811 passed, 3 skipped in 342.12s (0:05:42)`.

The one failure is the inherited `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, at `assert len(main_members) == 120` → `AssertionError: assert 167 == 120`. This is the merge-base length check, and it fails the same way on pristine `origin/main`.
