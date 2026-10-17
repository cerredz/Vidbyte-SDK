# S3 Implementer report: harness browser tools

- Stage: S3 implementer. Status: **BLOCKED**. The implementation is complete, and lint and the package gate pass. Six tests are red for test-side reasons that S3 may not fix. GitHub push protection also refuses the branch because of an S2 test fixture. See "Blockers".
- Branch `feat/harness-browser-tools`; code-complete HEAD `b5601413`; test baseline `a151e79c`; `git diff a151e79c..HEAD --stat -- tests/` is EMPTY.
- Draft PR: none. The push was refused (Blocker 3), so `gh pr create` could not run. The branch exists only locally.
- All 37 rows of §12.3 are implemented in the §12.6 phase order, one commit per work item (19 commits, `52820e7d` … `b5601413`).

## Commits by phase

| Phase | Commit | Rows | Work item |
|---|---|---|---|
| P1 | `52820e7d` enums, operations, failure codes | 1–4 | W-1 |
| P1 | `73507af4` constants and native thread texts | 7, 8 | W-1, W-4, W-7–W-10 |
| P1 | `9e1ee85f` browser records, `NativeThreadRun` | 5, 6 | W-2, W-13 |
| P1 | `85f359f5` `NativeThreadError.expected` names the result record | 9 | W-10 |
| P1 | `365eb03e` `BrowserToolRegistry` | 10, 11 | W-1, W-3 |
| P1 | `3012b2ce` `ProcessReaper` | 13, 14 | W-9 |
| P2 | `d0a90032` error factory passes the result record | 18 | W-10 |
| P2 | `869ac5a8` shared browser flow, preflight, cache, cleanup | 16, 17 | W-4, W-5, W-9, W-11 |
| P2 fix | `4e765944` reaper PowerShell without `USERPROFILE`; named zero count | 13, 8 | W-9 (AC-16 on Windows; lint A007) |
| P2 fix | `c883cf12` `_install` split out of `ensure`; removal under the cleanup budget | 16, 7 | W-4, W-9 (lint S008, S064, A007) |
| P3 | `7a0bb396` constants the mounts read | 7 | W-7, W-8 |
| P3 | `c1e91bc8` opencode mounts, wire, threads | 19, 25, 28 | W-6, W-13 |
| P3 | `9f1b5551` Grok mounts, wire, threads | 20, 26, 29 | W-7, W-13 |
| P3 | `1571cc9f` Muse mounts, wire, threads | 21, 27, 30 | W-8, W-13 |
| P4 | `e9c92adb` opencode browser functions | 22, 31 | W-6, W-11 |
| P4 | `453e25a0` Grok browser functions | 23, 32 | W-7, W-11 |
| P4 | `c06ace51` Muse browser functions | 24, 33 | W-8, W-11 |
| P4 | `719d3f11` native re-exports (28 names) | 34 | W-11 |
| P5 | `b5601413` READMEs, REPO_MAP, failure vocabulary | 12, 15, 35, 36, 37 | W-12, W-10 |

Budget (§8.4): 12 of 12 new files, 34 of 34 new classes, 0 dependencies, 0 new config keys, no schema change. Files outside §12.3: none. (`pipeline.md` differs from `a151e79c` only by the orchestrator's `7ad1d021`; S3 never staged it.)

## Gates (final lines, at HEAD `b5601413`)

Run in order by one script at HEAD `b5601413` (working tree clean apart from this untracked report).

1. `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads`
   `4 failed, 608 passed, 3 skipped in 179.33s (0:02:59)`. The four reds are listed under "Test status".
2. `PYTHONPATH=$(pwd) py -3.11 lint/run.py`
   `S009 IMPROVED 350 -> 346. Lower it with: python lint/run.py --rule S009 --update-baseline` / `SDK-LINT: PASS`
   No rule regressed: A007 255/255, S008 19/19, S064 4/4, A006 34/34, S009 (mypy) 346 against an allowance of 350.
   The S3 files have no mypy errors (`harnesses/native`, `lib/process` and the `browser_tools` modules).
   No baseline was raised and no suppression was added.
3. `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`
   - Every step before pytest passed: the tracked-bytecode check, lint (`SDK-LINT: PASS`), compileall, `check_context_write_paths.py`, `check_context_primitive_introductions.py` and `check_reasoning_trace_contracts.py`.
   - Pytest, the last step: `=========== 7 failed, 6615 passed, 17 skipped in 254.37s (0:04:14) ============` / `CI failed: Command failed with exit code 1: ...python.exe -m pytest`.
   - The seven failures: the four harness_threads reds and the three Codex packaging pins (Blocker 2).
   - An earlier full run at the same HEAD gave the same seven failures (6615 passed).
4. `py -3.11 scripts/run_ci.py --stage package` (no PYTHONPATH)
   `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` (exit 0)

## Test status

`tests/features/harness_threads`: `4 failed, 608 passed, 3 skipped`. The four reds:

1. `test_harness_threads_browser_lifecycle.py::test_muse_required_server_failure_carries_muses_reason`: S2 fixture-routing defect (Blocker 1).
2. `test_harness_threads_browser_lifecycle.py::test_tool_calls_and_artifacts_cap_at_a_thousand`: its artifact half is the same defect. The tool-call half passes.
3. `test_harness_threads_browser_mounts.py::test_grok_unlisted_server_tool_cancels_the_turn_loudly`: the same defect.
4. `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`: inherited. Only the merge-base length assertion fails (`assert 167 == 120`). The same test fails identically on `origin/main` `6f5a7310`; this was proved in a detached scratch worktree, which was then removed and pruned.

The full suite in the source gate adds three more reds, all in `tests/features/codex_host/test_codex_host_packaging.py` (Blocker 2). The MCP stdio flake did not occur.

## Blockers (decision needed)

### Blocker 1: three S2 tests put node-side scenario fields where the node stand-in never reads them

**What is wrong.** Each failing test passes its fields through `browse(fake=...)`:
- `server_fail` (lifecycle:174);
- `artifact_burst` (lifecycle:228);
- `extra_tools` (mounts:392).

`conftest.browse` writes `fake` only into the harness stand-in's scenario (`sandbox.command(harness, **fake)`). But these fields are read only by `fake_browser.mcp_server` and `fake_browser.answer` (fake_browser.py:313, 314, 341, 348). Those functions run in the `node` stand-in, and `browser_world` creates that stand-in once with `sandbox.node()` and no fields, so the fields never reach it. The other S2 tests route node-side fields correctly, through `sandbox.node(**node_fields)` (runtime:38) or `node_command(sandbox, ..., server_fail=...)` (fakes:220).

**Proof that the implementation is right.** I made scratch copies of the three tests and never committed them (`scratchpad/routing_proof/test_routing_proof.py`). They ran with `-p tests.features.harness_threads.conftest`. In each copy, the assertions are unchanged; the only edit is that the field moves into `sandbox.node(<field>=...)` before `browse`. Result: `3 passed in 32.72s`.

**Fix (test-side, one line each).** Call `sandbox.node(server_fail=["playwright"])`, `sandbox.node(artifact_burst=OVER_CAP)` or `sandbox.node(extra_tools={"firecrawl": ["firecrawl_brand_new"]})` before the `browse` call, and drop those keys from `fake`. Or teach `conftest.browse` to re-create the node stand-in with node-side fields.

### Blocker 2: Codex fixed-byte pins contradict §12.3 rows 34–36

`tests/features/codex_host/test_codex_host_packaging.py` arrived with the main merge `a151e79c` (#1055). It pins three things byte for byte. This spec must change each of them:

| Test | Pins | Spec row that must change it |
|---|---|---|
| `test_native_package_marker_has_the_fixed_bytes` | SHA-256 of `vidbyte/harnesses/native/__init__.py` (`0f77815c…`, 3855 LF bytes) | row 34: re-export the 9 functions and 2 records (28 names). S2's own AC-3 tests require this. |
| `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores` | the whole `##### vidbyte/harnesses/native/` REPO_MAP section | row 36: the native rows name the browser functions and modules |
| `test_harnesses_readme_bullet_follows_the_serialization_bullet` | the whole `native/` bullet of `vidbyte/harnesses/README.md` | row 35: the native paragraph covers the browser functions |

All 7 tests in that file pass at `a151e79c` and 3 fail at `b5601413`. No implementation can satisfy both the native-marker hash and S2's 28-name export test. The spec (§12.5, §13) assigns surface-pin updates to the test author, but it predates #1055, so it does not list these pins. Codex tests are out of scope for S3, and S3 may not edit tests.

**Fix (test-side).** In `test_codex_host_packaging.py`, update:
- `NATIVE_INIT_SHA256` to `6044725df61d3fdc4a9fd0ce5fd94bee306ea385293e3d802a1f2b7a1a4b950b`, the hash of the 5261 LF bytes at `719d3f11`;
- `REPO_MAP_SECTION` and `README_BULLET` to the texts at `b5601413`.

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
remote:          - commit: 2b6ff7f9f7d097ebdda480b874e9246210c7d41b
remote:            path: tests/features/harness_threads/test_harness_threads_browser_acceptance.py:46
 ! [remote rejected]   feat/harness-browser-tools -> feat/harness-browser-tools (push declined due to repository rule violations)
```

The flagged value is S2's `DEEPSEEK_KEY` fixture: `sk-` plus 32 hex characters in a visibly hand-made pattern. The acceptance test sets it as `DEEPSEEK_API_KEY` to prove that keys never leak, so it is a synthetic test value, not a real credential. It lives in S2's commit `2b6ff7f9`, which is already in the branch history. S3 cannot clear it, because all three ways out are forbidden to S3:
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

- Frontmatter: `status: implemented`, because all 37 rows are implemented and the six reds are test-side. `pr:` stays empty, because no PR could be opened (Blocker 3).
- §6.2: every Proof cell gets its S3 commits. AC-3, AC-12, AC-20 and AC-24 also carry a note.
- §17: a row `r4 | 2026-10-17 | S3 implement | …`. **Flag:** an `r4` row from S1 already existed; the S3 row follows the brief literally, so the table now has two `r4` rows.
- §17 "Implementation deviations (S3)" list.

## Where the tricky parts are

- **Windows cleanup.** Two Windows-only problems showed up only in the lifecycle tests: PowerShell's `AppData\Roaming` side effect (fixed in `4e765944`) and late lock release (deviation 4). A POSIX run never sees either.
- **Grok stream reading.** `GrokWire.read_stream` checks the outcome in a set order: timeout, then truncation, then an error event, then a non-zero exit, then a missing end event, then a `cancelled` stop reason, then the session id. A turn that Grok cancels after an unlisted tool call becomes `grok.run_failed`, naming the stop reason (EC-32 and EC-41). This path depends on Blocker 1 being fixed before it has a passing test.
- **Muse required-server translation.** Muse matches on `MUSE_REQUIRED_SERVER_MARKER` inside `vendor_message`. If Muse rewords that line, the failure falls back to plain `muse.run_failed`.
- **Plain paths.** The plain paths are unchanged (AC-15). The existing harness_threads tests pass, and each `execute` returns `NativeThreadRun`, whose `.result` is what `_call` returns.
