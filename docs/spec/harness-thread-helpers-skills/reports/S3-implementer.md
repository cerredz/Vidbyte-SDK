# S3 implementer: harness-thread-helpers-skills

STATUS: DONE · Spec r3 (approved → implemented) · Branch `feat/harness-thread-helpers-skills` · gates at `4206cee2` · Draft PR [#1147](https://github.com/cerredz/Vidbyte-SDK/pull/1147)

## Commits (first parent, oldest first)
Each `feat`/`fix`/`docs` commit covers one §12.3 row group and names its work item and spec IDs. `pipeline.md` was never staged.

| SHA | Message |
|---|---|
| `ad12d7d2` | feat(enums): add native thread helper and command vocabularies [W-1; FR-17, FR-18, AC-20] |
| `3e4548d5` | feat(enums): export the six new native enums [W-1; FR-18, AC-20] |
| `f1e9368e` | feat(failure): append command_not_run and store_unreadable codes [W-1; FR-17, INV-22, AC-20] |
| `6161a680` | feat(lib): add RecordFieldConverter.to_utc_datetime [W-1; FR-4, D-13] |
| `5df442cd` | feat(constants): add native thread helper and command values and texts [W-1; FR-17, D-12, AC-20] |
| `dbcd8efd` | feat(records): add helper, summary, command and Grok argument records [W-1; FR-4, D-1, D-25, D-30, D-32] |
| `da687a33` | fix(errors): make NativeThreadError.expected generic for helpers [W-1; D-20] |
| `e14eebaa` | refactor(native): widen request types to NativeHelperRequest [W-2; D-1, INV-26] |
| `00f29ef5` | refactor(grok): move the private home, fallback and environment to GrokHome [W-2; D-10, INV-26] |
| `fe00839d` | refactor(muse): move config folder, serve and reaping run to MuseChildren [W-2; D-10, INV-26] |
| `76297896` | feat(hostkit): add NativeThreadListing and NativeCommandEvidence [W-3; FR-5, FR-8, FR-9, FR-15, AC-2, AC-6, AC-7, AC-14, AC-17] |
| `c12ce245` | feat(grok): add GrokStreamWire and GrokHelperWire readers [W-4, W-7; FR-12, INV-6, INV-29, AC-14, AC-19, AC-29] |
| `b8f0610c` | feat(opencode): read helper child output and report an unknown command as command_not_run [W-5, W-8; FR-2, FR-13, D-8, D-19, D-26, AC-16, AC-19, AC-31, AC-32] |
| `2ffcac65` | feat(muse): add MuseSessionWire for session/list, session/read and evidence items [W-6, W-9; FR-3, FR-14, INV-6, D-33, AC-17, AC-19, AC-34] |
| `0b7516f3` | fix(native): keep the A007, S008, S009 and S054 lint ratchets at baseline [W-1, W-4, W-5, W-6; INV-15, NFR-6] |
| `f3429925` | feat(grok): add GrokStore for scope-wide and one-id summary.json reads [W-4; FR-1, FR-4, FR-5, FR-11, INV-4, INV-6, INV-13, D-11, D-21, D-27, D-31, AC-9, AC-19, AC-27, AC-28] |
| `509bc733` | feat(grok): add the eight keyless Grok thread helpers and their flows [W-4; FR-1, FR-5 to FR-11, INV-2, INV-3, INV-10, INV-11, INV-16, INV-18, AC-2 to AC-9, AC-25] |
| `77df8952` | feat(native): export the Grok thread helpers, NativeThreadSummary, NativeCommandOutput, GrokThreadScope and GrokCommand [W-10; FR-18, INV-1] |
| `9b197327` | feat(opencode): add the eight keyless opencode thread helpers and their flows [W-5; FR-2, FR-5 to FR-10, INV-2, INV-9, INV-16, D-19, D-22, D-26, AC-2 to AC-8, AC-31, AC-32] |
| `99bd0651` | feat(native): export the opencode thread helpers [W-10; FR-18, INV-1] |
| `c89c0373` | fix(harnesses): keep the A007 and S051 ratchets at baseline in the helper flows [W-3, W-4, W-5; INV-15, NFR-6] |
| `53a9c82a` | feat(muse): add the six keyless Muse thread helpers, init_muse_workspace and the evidence reads [W-6; FR-3, FR-4 to FR-8, FR-14, INV-2, INV-4, INV-14, INV-18, INV-23, D-17, D-33, AC-2 to AC-6, AC-10, AC-11, AC-18, AC-19, AC-23, AC-25] |
| `26d2a986` | feat(native): export the Muse thread helpers and init_muse_workspace [W-10; FR-18, INV-1] |
| `30ff853e` | feat(grok): add the fourteen Grok command functions with a minted session id and fail-closed evidence [W-7; FR-12, FR-15, FR-19, INV-8, INV-9, INV-16, INV-24, INV-29, D-25, D-28, D-29, D-30, D-32, AC-1, AC-12 to AC-15, AC-23, AC-24, AC-29, AC-30, AC-33] |
| `a5960acf` | feat(native): export the Grok command functions [W-10; FR-18, INV-1] |
| `1282b712` | feat(opencode): send --command and no stdin for an argument-less command run [W-8; FR-13, D-8, INV-26, AC-16] |
| `a7a53747` | feat(opencode): add run_opencode_command, run_opencode_review, run_opencode_init and run_opencode_plan [W-8; FR-13, FR-15, FR-19, INV-9, INV-25, D-8, D-25, AC-12, AC-16, AC-24] |
| `4bcc76d3` | feat(native): export the opencode command functions [W-10; FR-18, INV-1] |
| `a8f6c179` | feat(muse): add the six Muse skill functions with keyless, fail-closed evidence reads [W-9; FR-14, FR-15, FR-19, INV-8, INV-23, INV-24, INV-25, D-9, D-25, D-33, AC-12, AC-17, AC-23, AC-24, AC-34] |
| `8bcd9a5b` | feat(native): export the Muse skill functions; the native package now exports 68 names [W-10; FR-18, INV-1, AC-20] |
| `f3206141` | docs(native): describe the helpers, command and skill functions in the package header [W-10; FR-18, INV-1] |
| `1e2192c8` | docs(harnesses): document the thread helpers, Grok scopes, command and skill functions and their limits [W-11; FR-20, AC-26, EC-63, EC-72, EC-74, EC-76, EC-78, T-6] |
| `94870d71` | docs(repo-map): name listing, reading, lineage, search, delete and verified command runs in the native entry [W-11; FR-20, AC-26] |
| `56d14412` | fix(grok): name design_doc when run_grok_execute_plan gets no plan [W-7; INV-3, D-25] |
| `59287e00` | docs(harnesses): name the key variables helper children drop [W-11; FR-20, INV-2] |
| `4206cee2` | chore(merge): catch up with main at 239c408a |

After the gates: `cde2c1d9` `docs(spec): record harness-thread-helpers-skills S3 implementation and draft PR [W-11; AC-1 to AC-34]`, which fills the 34 §6.2 Proof cells, sets the frontmatter to `status: implemented` with the `pr:` link, and adds the r3 (S3) row to §17. A later commit adds this report.

## Produced
- **§12.3 rows 1–34, in phase order P1 → P6.** Rows 35–38 are S2's and were not touched. No file under `tests/` was changed.
- **The §8.4 budget is used exactly: 10 new source files, 2,034 lines.** The largest is 366 lines (NFR-6):

  | File | Lines | Holds |
  |---|---|---|
  | `vidbyte/harnesses/native/hostkit/listing.py` | 75 | `NativeThreadListing` (ordering, cut, since, dedupe) |
  | `vidbyte/harnesses/native/hostkit/evidence.py` | 74 | `NativeCommandEvidence` (fail-closed tool and fragment checks) |
  | `vidbyte/harnesses/native/grok/store.py` | 251 | `GrokStore` (`summary.json` reads, scope-wide and by id) |
  | `vidbyte/harnesses/native/grok/helpers.py` | 284 | `GrokThreadHelpers` (8 helpers), `GrokHelperRun` |
  | `vidbyte/harnesses/native/grok/commands.py` | 313 | `GrokCommands` (14 functions), `GrokCommandRun` |
  | `vidbyte/harnesses/native/opencode/helpers.py` | 257 | `OpencodeThreadHelpers` (8 helpers), `OpencodeHelperRun` |
  | `vidbyte/harnesses/native/opencode/commands.py` | 112 | `OpencodeCommands` (4 functions) |
  | `vidbyte/harnesses/native/muse/children.py` | 146 | `MuseChildren` (config folder, serve, reaping run) |
  | `vidbyte/harnesses/native/muse/helpers.py` | 366 | `MuseThreadHelpers` (6 helpers + `init_muse_workspace`), `MuseHelperRun` |
  | `vidbyte/harnesses/native/muse/commands.py` | 156 | `MuseCommands` (6 skill functions), `MuseCommandRun` |

- **Public surface.** There are 47 functions. `vidbyte.harnesses.native` exports 68 names, with literal, ASCII-sorted `__all__` lists (Grok 25, opencode 15, Muse 16). Root `__all__` is unchanged (INV-1).
- **Edited files (23):**
  - five `lib/` modules: the native enums, the enum exports, the failure codes, the native records and the native constants;
  - `lib/dataclasses/validation.py` (`to_utc_datetime`) and `lib/errors/base.py`;
  - 14 harness modules: the native, hostkit, Grok, opencode and Muse `__init__` files, plus the `threads`, `wire`, `launcher` and `errors` modules they touch;
  - `vidbyte/harnesses/README.md` (14.9k characters, under A009);
  - `REPO_MAP.md`.
- **#1036 behaviour is unchanged (INV-26).** The 431 unedited #1036 tests pass, with the same skips. The only change to the opencode `run` argv adds `--command` when a command is set.

## Gates (final tree `4206cee2`, after the merge with main at `239c408a`)
- **The suite.** `env -u DEEPSEEK_API_KEY $PY -m pytest tests/features/harness_threads -q -p no:cacheprovider` ended:
  ```
  998 passed, 3 skipped in 83.91s (0:01:23)
  ```
  The 3 skips are platform-only: Muse's PATH lookup outside win32 ×2 and the POSIX execute bit.
- **Lint.** `$PY lint/run.py` ended as below, and `git diff 239c408a -- lint/baseline.json` is empty. The IMPROVED rules were left alone; no baseline was lowered or raised.
  ```
  S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

  SDK-LINT: PASS
  ```
- **CI source.** `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY $PY scripts/run_ci.py --stage source` ended:
  ```
  ================ 6558 passed, 17 skipped in 132.05s (0:02:12) =================
  CI passed.
  ```
- **CI package.** `env -u DEEPSEEK_API_KEY $PY scripts/run_ci.py --stage package` ended:
  ```
  Successfully built vidbyte_sdk-0.3.0.tar.gz and vidbyte_sdk-0.3.0-py3-none-any.whl
  ...vidbyte_sdk-0.3.0-py3-none-any.whl: PASSED
  ...vidbyte_sdk-0.3.0.tar.gz: PASSED
  No broken requirements found.
  Installed vidbyte-sdk 0.3.0 passed smoke checks.
  CI passed.
  ```
- **Semgrep.** These are the two commands from `.github/workflows/static-policy.yml`. First `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`:
  ```
  1/1: ✓ All tests passed
   • Findings: 0 (0 blocking)
  Ran 1 rule on 975 files: 0 findings.
  ```
- **Mypy and the static-policy test.** The source stage includes the staged mypy contract ratchet (S009 at its 350 baseline). `test_harness_threads_static_policy.py` covers the 10 new modules and passes in the suite above.

## Deviations from the letter of §8.5, §9 and §12.3
None of these changes a public signature. The same list is the r3 (S3) row in §17.
1. `MuseSessionWire.result` takes `method` and `thread_id` keywords. The new `MuseSessionWire.exited` checks an export or init child's timeout, output cap and exit status.
2. `GrokHelperWire.document` takes `thread_id`, so code-review export errors carry the minted id.
3. `MuseChildren.serve` takes `removed`. Every helper and evidence child removes all four key variables (`NATIVE_HELPER_REMOVED_VARIABLES`), not only its own harness's.
4. `NativeThreadListing.newest` takes `limit: int | None`, so flows pass the request's checked limit without an `or 0` literal, which A007 would flag.
5. Internal helpers beyond §8.5:
   - `GrokStore.home`, which maps an unknown user home to `store_unreadable`;
   - `GrokHelperRun._found`;
   - opencode's `OpencodeHelperRun._child(..., options=)` and `_query`;
   - `GrokCommandRun.line` and `_words`;
   - the opencode wire's `_summary(parent_member=)`.
6. The generic helper `_call`s return `Any`, because INV-15 allows no module-level `TypeVar`.
7. Listing and search order:
   - `list_muse_threads` asks `session/list` for `NATIVE_LIST_MAX_LIMIT` sessions and cuts the list in the SDK, because Muse orders ties by ascending id (INV-7);
   - Grok search matches before the dedupe.
8. Constants beyond row 4:
   - `NATIVE_SINCE_MIN`, `NATIVE_TITLE_PATTERN`, `NATIVE_QUERY_PATTERN`, `GROK_MAX_EFFORTS`, `GROK_BLANK_TEXT_COMMANDS`, `GROK_REVIEW_MAX_TARGETS`, `NATIVE_COMMAND_PART_SEPARATOR`, `OPENCODE_SESSION_QUERY_MAX_ROWS`, `NATIVE_BINARY_READ_MODE` and `OPENCODE_PLAN_AGENT_RULE`.
   - `NATIVE_TEXT_ARGUMENTS` maps `run_grok_execute_plan` to `design_doc`. `/review` and `/code-review` take no text, so they fall back to `arguments`.
   - The wording of `MUSE_GOAL_PROMPT_TEMPLATE` (S2 gap 1) and the `features.video_gen` location in the `grok.command_not_run` cause (S2 gap 2) are my choices.
9. `NativeEnvironmentVariable.PWD = auto()`, because bandit S105 reads a literal `"PWD"` as a password. Grok's `end.sessionId` is compared with the minted id case-insensitively.
10. Order inside `GrokCommands._call`: it builds `GrokCommandArguments` and runs the win32 units check under the text's public name. It then builds the request with the line and fills `skill_names` with `dataclasses.replace`. The request needs the line, and the line needs the checked arguments.
11. `lint/run.py` prints `SDK-LINT: PASS` as its only verdict line (`lint/core/report.py:58`). AC-22 names `AGENT-LINT`, which the tool does not print.
12. The global semgrep is broken by mcp 2.x. The scan ran from an isolated venv with CI's `semgrep==1.170.1`.
13. This machine sets `DEEPSEEK_API_KEY`, so the tests and gates ran with it unset (see the next section).

## Environment assumptions
- **`DEEPSEEK_API_KEY`.** The test pack's `CREDENTIAL_NAMES` counts it as a caller key that no helper child may carry. INV-2 and the pinned `NativeEnvironmentVariable` require only the SDK's four key variables to be removed, and the README now says so. With the variable set, the same suite ends `16 failed, 982 passed, 3 skipped in 83.70s`. Every failure is an INV-2 or INV-23 "no key in child" assertion, in the Grok export and delete helpers, the Muse helpers and skill functions, and one opencode list test. CI runners do not set it.
- **Semgrep venv.** `.venvs/harness-thread-helpers-semgrep` was put first on `PATH` in `/c/...` form. A `C:/...` entry breaks on its colon, and the broken global `pysemgrep` then wins.
- **No real vendor CLI, key, `~/.grok` or store was used.** Every run went through the stand-ins. The research captures in scratch (`oc-export.json`, `oc-config.json`, `inspect*.json`) were not committed.

## Branch upkeep
- **Merge with main.** `4206cee2` merges `origin/main` at `239c408a`, with no rebase. Lint, CI and semgrep above ran on the merged tree.
- **`pipeline.md`.** It stays modified in the worktree and was never staged.

## Open items
- **For S4:**
  - Deviation 11: AC-22's banner text. Either the spec reads `SDK-LINT: PASS`, or the AC is treated as met.
  - Deviation 13: whether `CREDENTIAL_NAMES` should leave out non-SDK keys. That is a test change, so it is not mine to make.
- **For S5:** remote CI dispatch and the move to ready, both outside S3's remit.
- **Pre-existing:** the MCP stdio flake did not come up. `tests/test_mcp_stdio_transport.py` passed in the source stage.
