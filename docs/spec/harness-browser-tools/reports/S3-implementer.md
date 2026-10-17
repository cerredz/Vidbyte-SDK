# S3 Implementer report: harness browser tools

- Stage: S3 implementer. Status: **DONE**. The implementation is complete, and lint and the package gate pass. The three blockers S3 reported at `0dfde894` were resolved by orchestrator-adjudicated, test-only repairs (see "Post-S3 test repairs"). Only the inherited failure stays red.
- Branch `feat/harness-browser-tools`. Code-complete HEAD `0dfde894`.
- S3's own commits change no test: `git diff 871ee369..0dfde894 --stat -- tests/` is empty.
- After the post-S3 repairs, the test baseline is `9e81a7d0`, and `git diff 9e81a7d0..HEAD --stat -- tests/` is EMPTY.
- Draft PR: opened after the fixture fold, when the branch was first pushed. Its URL is in the spec frontmatter `pr:`.
- All 37 rows of §12.3 are implemented in the §12.6 phase order, one commit per work item (19 commits, `2b2e350a` … `0dfde894`).

## Commits by phase

| Phase | Commit | Rows | Work item |
|---|---|---|---|
| P1 | `2b2e350a` enums, operations, failure codes | 1–4 | W-1 |
| P1 | `5877c763` constants and native thread texts | 7, 8 | W-1, W-4, W-7–W-10 |
| P1 | `f84f40a1` browser records, `NativeThreadRun` | 5, 6 | W-2, W-13 |
| P1 | `da596d28` `NativeThreadError.expected` names the result record | 9 | W-10 |
| P1 | `6850de45` `BrowserToolRegistry` | 10, 11 | W-1, W-3 |
| P1 | `affc030b` `ProcessReaper` | 13, 14 | W-9 |
| P2 | `f88dcc8e` error factory passes the result record | 18 | W-10 |
| P2 | `0a86d456` shared browser flow, preflight, cache, cleanup | 16, 17 | W-4, W-5, W-9, W-11 |
| P2 fix | `c665afdb` reaper PowerShell without `USERPROFILE`; named zero count | 13, 8 | W-9 (AC-16 on Windows; lint A007) |
| P2 fix | `c9edd485` `_install` split out of `ensure`; removal under the cleanup budget | 16, 7 | W-4, W-9 (lint S008, S064, A007) |
| P3 | `07269150` constants the mounts read | 7 | W-7, W-8 |
| P3 | `19fa8cf9` opencode mounts, wire, threads | 19, 25, 28 | W-6, W-13 |
| P3 | `3ae18948` Grok mounts, wire, threads | 20, 26, 29 | W-7, W-13 |
| P3 | `59dfc44c` Muse mounts, wire, threads | 21, 27, 30 | W-8, W-13 |
| P4 | `8903baa0` opencode browser functions | 22, 31 | W-6, W-11 |
| P4 | `4c084da6` Grok browser functions | 23, 32 | W-7, W-11 |
| P4 | `8290c813` Muse browser functions | 24, 33 | W-8, W-11 |
| P4 | `d70b8ba1` native re-exports (28 names) | 34 | W-11 |
| P5 | `0dfde894` READMEs, REPO_MAP, failure vocabulary | 12, 15, 35, 36, 37 | W-12, W-10 |

Budget (§8.4): 12 of 12 new files, 34 of 34 new classes, 0 dependencies, 0 new config keys, no schema change. Files outside §12.3: none. (`pipeline.md` differs from `871ee369` only by the orchestrator's `b8e02a7d`; S3 never staged it.)

## Gates (final lines)

**Final evidence after the post-S3 test repairs and the fixture fold.** The orchestrator decided not to re-run the full local source gate. Its reasons:
- The full source gate already ran on this exact source code (`0dfde894`). Every step passed except pytest, which had 7 failures: the 6 test defects since repaired, plus the 1 inherited failure.
- Since then, only test files under `tests/features/harness_threads` and `tests/features/codex_host`, and docs, have changed. `git diff 0dfde894..HEAD -- vidbyte/` is empty.
- The full suite runs again on GitHub CI, which the orchestrator dispatches after the push.

1. Focused re-run at `9676198f` of the two folders the repairs touched: `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads tests/features/codex_host`
   `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 811 passed, 3 skipped in 206.00s (0:03:26)`
   The one failure is the inherited `assert 167 == 120`.
2. Source gate re-run at `9676198f`: `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`. **Killed, not passed.** Claude Code stopped the run because the machine was critically low on memory. Other sessions' jobs were using that memory.
   - Before the kill, every step up to pytest passed, including lint (`SDK-LINT: PASS`).
   - Pytest had reached about 21% (into the harness_threads lifecycle tests) with no FAILED line.
   - It was not re-run, by the orchestrator's decision.
3. The full source gate at code-complete `0dfde894`, before the repairs: `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`
   - Every step before pytest passed: the tracked-bytecode check, lint (`SDK-LINT: PASS`), compileall, `check_context_write_paths.py`, `check_context_primitive_introductions.py` and `check_reasoning_trace_contracts.py`.
   - Pytest: `=========== 7 failed, 6615 passed, 17 skipped in 254.37s (0:04:14) ============` / `CI failed: Command failed with exit code 1: ...python.exe -m pytest`.
   - The 7 failures were the 3 routing tests and the 3 Codex packaging pins (both repaired since) and the 1 inherited test.
4. Lint at `0dfde894`: `PYTHONPATH=$(pwd) py -3.11 lint/run.py`
   `S009 IMPROVED 350 -> 346. Lower it with: python lint/run.py --rule S009 --update-baseline` / `SDK-LINT: PASS`
   - No rule regressed: A007 255/255, S008 19/19, S064 4/4, A006 34/34, S009 (mypy) 346 against an allowance of 350.
   - The S3 files have no mypy errors.
   - No baseline was raised and no suppression was added.
5. Package gate at `0dfde894`: `py -3.11 scripts/run_ci.py --stage package` (no PYTHONPATH)
   `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` (exit 0)
   This still holds, because no source has changed since `0dfde894`.

## Test status

After the repairs, one test is red. `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` is inherited: only its merge-base length assertion fails (`assert 167 == 120`). The same test fails identically on `origin/main` `6f5a7310`. This was proved in a detached scratch worktree, which was then removed and pruned.

At code-complete `0dfde894`, before the repairs, `tests/features/harness_threads` gave `4 failed, 608 passed, 3 skipped` (the 3 routing tests and the inherited one), and the full suite added the 3 Codex packaging pins. The MCP stdio flake did not occur in any run.

## Post-S3 test repairs

The orchestrator adjudicated all three blockers below as test defects or test drift. The test author fixed them in test-only commits, with every assertion unchanged:
- `305a9b67` routes the node-side fake fields through `sandbox.node`;
- `fd70e93d` and `9e81a7d0` refresh the Codex packaging pins and their comments;
- the key-shaped fixtures are now built at run time, folded into the S2 test commit `fb8ab004`.

Folding rewrote every commit from the S2 test commit onward, and step A remapped every SHA in this report. No file under `vidbyte/` changed. Details are in `reports/S2-test-author.md`, section "## Post-S3 repair (orchestrator-adjudicated)". The test baseline is now `9e81a7d0`.

## Blockers (reported at `0dfde894`; all three resolved, see "Post-S3 test repairs")

### Blocker 1: three S2 tests put node-side scenario fields where the node stand-in never reads them

**What is wrong.** Each failing test passes its fields through `browse(fake=...)`:
- `server_fail` (lifecycle:174);
- `artifact_burst` (lifecycle:228);
- `extra_tools` (mounts:392).

`conftest.browse` writes `fake` only into the harness stand-in's scenario (`sandbox.command(harness, **fake)`). But these fields are read only by `fake_browser.mcp_server` and `fake_browser.answer` (fake_browser.py:313, 314, 341, 348). Those functions run in the `node` stand-in, and `browser_world` creates that stand-in once with `sandbox.node()` and no fields, so the fields never reach it. The other S2 tests route node-side fields correctly, through `sandbox.node(**node_fields)` (runtime:38) or `node_command(sandbox, ..., server_fail=...)` (fakes:220).

**Proof that the implementation is right.** I made scratch copies of the three tests and never committed them (`scratchpad/routing_proof/test_routing_proof.py`). They ran with `-p tests.features.harness_threads.conftest`. In each copy, the assertions are unchanged; the only edit is that the field moves into `sandbox.node(<field>=...)` before `browse`. Result: `3 passed in 32.72s`.

**Fix (test-side, one line each).** Call `sandbox.node(server_fail=["playwright"])`, `sandbox.node(artifact_burst=OVER_CAP)` or `sandbox.node(extra_tools={"firecrawl": ["firecrawl_brand_new"]})` before the `browse` call, and drop those keys from `fake`. Or teach `conftest.browse` to re-create the node stand-in with node-side fields.

### Blocker 2: Codex fixed-byte pins contradict §12.3 rows 34–36

`tests/features/codex_host/test_codex_host_packaging.py` arrived with the main merge `871ee369` (#1055). It pins three things byte for byte. This spec must change each of them:

| Test | Pins | Spec row that must change it |
|---|---|---|
| `test_native_package_marker_has_the_fixed_bytes` | SHA-256 of `vidbyte/harnesses/native/__init__.py` (`0f77815c…`, 3855 LF bytes) | row 34: re-export the 9 functions and 2 records (28 names). S2's own AC-3 tests require this. |
| `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores` | the whole `##### vidbyte/harnesses/native/` REPO_MAP section | row 36: the native rows name the browser functions and modules |
| `test_harnesses_readme_bullet_follows_the_serialization_bullet` | the whole `native/` bullet of `vidbyte/harnesses/README.md` | row 35: the native paragraph covers the browser functions |

All 7 tests in that file pass at `871ee369` and 3 fail at `0dfde894`. No implementation can satisfy both the native-marker hash and S2's 28-name export test. The spec (§12.5, §13) assigns surface-pin updates to the test author, but it predates #1055, so it does not list these pins. Codex tests are out of scope for S3, and S3 may not edit tests.

**Fix (test-side).** In `test_codex_host_packaging.py`, update:
- `NATIVE_INIT_SHA256` to `6044725df61d3fdc4a9fd0ce5fd94bee306ea385293e3d802a1f2b7a1a4b950b`, the hash of the 5261 LF bytes at `d70b8ba1`;
- `REPO_MAP_SECTION` and `README_BULLET` to the texts at `0dfde894`.

The header of that test file already says the fixed texts change when their source changes.

**Options:**
- (A) S2 or the orchestrator updates both test sets on this branch: three one-line routing fixes and three pin refreshes. No source change is needed.
- (B) For rows 35 and 36 only, move the browser prose next to the pinned Codex texts and leave the pinned texts untouched. This needs a spec deviation, and `NATIVE_INIT_SHA256` still needs a refresh.
- (C) Accept the six as known-red. This leaves the PR red in CI and is not recommended.

**Recommendation: (A).**

### Blocker 3: GitHub push protection rejects the branch because of S2's synthetic DeepSeek key fixture

`git push -u origin feat/harness-browser-tools` was refused:

```
remote: error: GH013: Repository rule violations found for refs/heads/feat/harness-browser-tools.
remote:     - Push cannot contain secrets
remote:       —— DeepSeek API Key ——
remote:          - commit: fb8ab0042b2a5d34ea38aec1bea81731a532a648
remote:            path: tests/features/harness_threads/test_harness_threads_browser_acceptance.py:46
 ! [remote rejected]   feat/harness-browser-tools -> feat/harness-browser-tools (push declined due to repository rule violations)
```

The flagged value is S2's `DEEPSEEK_KEY` fixture: `sk-` plus 32 hex characters in a visibly hand-made pattern. The acceptance test sets it as `DEEPSEEK_API_KEY` to prove that keys never leak, so it is a synthetic test value, not a real credential. It lives in S2's commit `fb8ab004`, which is already in the branch history. S3 cannot clear it, because all three ways out are forbidden to S3:
- allowing a secret is a repository security decision;
- a rewrite of history means a rebase;
- changing the value means a test edit.

Because the branch could not be pushed, no draft PR exists, the frontmatter `pr:` stays empty, and the "record draft PR" commit was not made. The proof and report commits were made locally.

**Options:**
- (A) The repository owner opens GitHub's unblock link for this finding (the URL from the push output, `.../security/secret-scanning/unblock-secret/3Kq8zDp8lqnQM3C4XZpM0ZS0lSL`) and allows it as a test value. Then the branch can be pushed as it is.
- (B) S2 rewrites its own commit before the first push, so the fixture is a value the scanner does not match. One example is a string the test builds at run time. This needs an authorised history rewrite of an unpushed branch, never a force-push to a shared one.

**Recommendation: (A).** It changes no code or test and keeps every recorded SHA valid. Once the owner unblocks the finding, push, run the `gh pr create` command from the briefing, and record `pr:`.

## Implementation deviations

They are also recorded in the spec, under §17 "Implementation deviations (S3)".

1. `BrowserToolRequest` itself refuses a `tool_keys` name that is not a registry name, because the S2 registry tests require refusal at record level. §9.1 puts that check in `select`.
2. The Grok argv budget is an estimate made before the per-call folder exists. It counts the UTF-16 units of `list2cmdline` over three parts: `--agent=` with an estimated path (temp folder + `BROWSER_CALL_FOLDER_ESTIMATE` + file name), every rule option, and `--disable-web-search`. It does not count the 10-unit `streaming-json`/`json` difference.
3. Constants (rows 7 and 8) were committed before the records (rows 5 and 6), because the records import them.
4. Removal is tried 5 times, 0.2 s apart, because Windows releases a killed browser's lock late. The tries run under `asyncio.timeout(BROWSER_REAP_TIMEOUT_SECONDS)`, which satisfies lint S064 and FR-15's 10 s.
5. `MUSE_SETTINGS_PARTS` lives in `constants/native_threads.py`.
6. The suggestion refusals also list the mountable tools, because difflib suggests "kernel" for "skyvern".
7. The stdio entry prefix check uses two extra constants.
8. The reaper counts only the processes it actually stopped.
9. `prepare` pre-creates `artifacts/` and `profiles/<tool>/`.
10. The Grok call status comes from the last `tool_call_update` that has a string status.
11. `OpencodeMounts.check` refuses nothing, because opencode carries every selection.
12. Five new constants are not named in §9: `BROWSER_CALL_FOLDER_ESTIMATE`, `MUSE_TOOL_NAME_SEPARATOR`, `BROWSER_GROK_AGENT_FILE_DETAIL`, `NATIVE_USER_PROFILE_VARIABLE` and `NATIVE_REAP_NONE_COUNT`.
13. Three private helpers are not named in §9: `GrokMounts.agent_path`, `BrowserToolCache._install` and `NativeBrowserTools._remove_attempts`.
14. When the Grok agent file cannot be written, the call fails with `grok.launch_failed`.
15. The reaper's Windows PowerShell runs without `USERPROFILE`. A probe showed that starting PowerShell with a redirected `USERPROFILE` creates `AppData\Roaming` in that folder, which broke AC-16 (4 tests). Without the variable, Windows uses the profile of the logon token, and the CIM query still works.
16. The browser functions pass `{}` to `BrowserToolRequest` when `tool_keys` is None, which keeps mypy clean on the record field. The record still turns None into `{}`.

## Spec edits made by S3

- Frontmatter: `status: implemented`, because all 37 rows are implemented. `pr:` is recorded in its own commit once the draft PR is open.
- §6.2: every Proof cell gets its S3 commits. AC-3, AC-12, AC-20 and AC-24 also carry a note.
- §17: a row `r4 | 2026-10-17 | S3 implement | …`. **Flag:** an `r4` row from S1 already existed; the S3 row follows the brief literally, so the table now has two `r4` rows.
- §17 "Implementation deviations (S3)" list.

## Where the tricky parts are

- **Windows cleanup.** Two Windows-only problems showed up only in the lifecycle tests: PowerShell's `AppData\Roaming` side effect (fixed in `c665afdb`) and late lock release (deviation 4). A POSIX run never sees either.
- **Grok stream reading.** `GrokWire.read_stream` checks the outcome in a set order: timeout, then truncation, then an error event, then a non-zero exit, then a missing end event, then a `cancelled` stop reason, then the session id. A turn that Grok cancels after an unlisted tool call becomes `grok.run_failed`, naming the stop reason (EC-32 and EC-41). This path depends on Blocker 1 being fixed before it has a passing test.
- **Muse required-server translation.** Muse matches on `MUSE_REQUIRED_SERVER_MARKER` inside `vendor_message`. If Muse rewords that line, the failure falls back to plain `muse.run_failed`.
- **Plain paths.** The plain paths are unchanged (AC-15). The existing harness_threads tests pass, and each `execute` returns `NativeThreadRun`, whose `.result` is what `_call` returns.
