# Verification log: Thread helpers and built-in skill functions for the Grok, opencode and Muse harnesses

Gate set (from context/code-map.md §1.2 and the S5 briefing), run from the worktree root in CI order. `PY` is the venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python`. Semgrep is the isolated venv `.venvs/harness-thread-helpers-semgrep` (semgrep 1.170.1), first on `PATH` in `/c/...` form.

| # | Gate | Command | Where |
|---|---|---|---|
| 1 | lint | `$PY lint/run.py` (must end `SDK-LINT: PASS`; `git diff 239c408a -- lint/baseline.json` empty) | local, and inside CI `source` |
| 2 | new tests (area) | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads` | local |
| 3 | full local gate | `$PY scripts/run_ci.py` (stage `all` = `source` then `package`) | local |
| 4 | semgrep fixtures | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` | local, and remote `static-policy.yml` |
| 5 | semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | local, and remote `static-policy.yml` |
| 6 | remote CI | `gh workflow run ci.yml --ref feat/harness-thread-helpers-skills` (Source 3.11, Source 3.12, Package) | remote only, dispatch-only |
| 7 | remote static policy | `gh workflow run static-policy.yml --ref feat/harness-thread-helpers-skills` | remote only, dispatch-only |

Both workflows are dispatch-only, so `gh pr checks` prints "no checks reported". Read the results with `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`.

## Iteration 1 — 2026-10-16 13:10 EDT — agent report: reports/S5-repair-1.md

**Defects in:** these came from review.md and the briefing at HEAD `999ff056`, against the test head `cd2b329b`.
- The defects: R-1 (Blocker), R-2 (Blocker) with R-23, R-6, R-5, R-3, R-4 (status only), R-16, and the trivial Minors R-10, R-11, R-15, R-17 and the trivial part of R-21.
- The failing gate was the new tests: `34 failed, 991 passed, 3 skipped in 86.89s (0:01:26)`. They were 16 in muse_commands, 8 in errors, 6 in listing_properties, 2 in grok_commands and 2 in helper_surface.
- To mark `follow-up`: R-8, R-9, R-12, R-13, R-14, R-18, R-19, R-20 and R-22. R-7 was already fixed in spec r4.

**Hypotheses and attempts (in order):**
1. **R-1.** Seven new comment lines ran past 72 columns. I rewrapped every comment block I touched.
   - Check: `scratchpad/wide.sh <rev>` runs `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'` on each changed file, compared with the base. It prints nothing against `239c408a` and nothing against `origin/main` on the final tree.
   - Every `# @intent` stays inside def+20.
2. **R-6 (landed before R-5; both edit `hostkit/errors.py`).** I added `NativeErrorFactory.child_problem` as a pure `@staticmethod`. It calls nothing else on the factory, following the `wrong_thread` precedent.
   - It replaced the hand-written mapping in `GrokHelperWire._checked` (marker in stderr or stdout), `OpencodeHelperWire._checked` (stderr only) and `MuseSessionWire.exited` (no marker).
   - Each site still raises through `errors.failure(...)` with `vendor_text`, `seconds` and `cap_bytes`.
   - Main's four older copies are untouched (AGENTS.md: do not rewrite untouched code). The `outcome.timed_out` counts per wire are grok 2, muse 3 and opencode 1: main's four plus the two D-35 keeps.
   - This worked first time.
3. **R-5.** I added `NativeErrorFactory.remember_thread`, which stores the id on the factory.
   - `failure`, `from_configuration_error`, `from_unexpected` and `from_launch_failure` take the id in this order: their explicit argument, then the remembered id, then `request.thread_id`.
   - There are exactly two call sites: right after `GrokStreamWire.read` and right after `MuseThreadRun.execute`.
   - The evidence config folder is still made with `tempfile.mkdtemp`, as the test author warned.
   - This worked first time.
4. **R-23.** `NativeCommandEvidence.require` gained `member: str | None`.
   - With `member` set, the arguments must parse as a JSON object whose `member` value equals the fragment exactly. There is no backslash folding in that mode.
   - With `member` unset, Grok's substring rule (with folding) is unchanged.
   - The constant is `MUSE_READ_SKILL_ID_MEMBER = "id"`.
5. **R-2 (spec r5 D-33).**
   - `MuseSessionWire.tool_calls` now returns `tuple[NativeToolCall, ...]` and never `None`.
   - Modes `snapshot` and `anchoredSnapshot` both read `history.snapshot.state.items`; mode `inline` reads `history.items`.
   - Mode `none` still fails closed and names `noneReason`. An unknown mode is `protocol_mismatch` naming `items`.
   - I deleted `MuseHelperRun.transcript` and the `NativeCommandEvidence.require_text` call in `muse/commands.py`. One `require(calls, tools=(tool,), fragment=…, member=MUSE_READ_SKILL_ID_MEMBER, …)` replaced them.
   - The new intent is `muse-anchored-snapshot-holds-every-item`, and the r5 `MUSE_COMMAND_NOT_RUN` likely cause is in place.
   - Reading note: the one `require_text` token left in `muse/commands.py` is `RecordFieldValidator.require_text` at :99. That is the D-25 argument-length check, not evidence. I read §12.4's "no `require_text` call" as the evidence call. A re-reviewer who greps the bare token will see it.
6. **R-3.** `GrokHelperRun.search` takes the winners of `NativeThreadListing.newest(..., cutoff=None, limit=None)` and keeps only the files whose summary won. Only then does it match.
7. **R-16.** The OPENCODE scan-cap next step is now the §12.4 text. A script copied it from spec.md, not retyped, and the test pin passes.
8. **R-10.** Three options:
   - (a) revert to `elif` and dispute the finding;
   - (b) make the agent branch the default (that only moves the `None` to `agent.value`);
   - (c) `else:` with inline narrowing.

   **First attempt failed:** a bare `else:` left `command: GrokCommand | None` at `GROK_EVIDENCE_TOOLS[command]` and `.get(command)`. That raised two mypy findings, so S009 went 350 → 352 REGRESSED.
   - It got committed because I ran `lint/run.py | tail -1`, and the exit code came from `tail`. **Lesson: never pipe a gate into `tail` for its verdict. Use `scratchpad/lintgate.sh`, which keeps lint's own exit code.**
   - I amended that unpushed commit to option (c): `tools = () if command is None else …` and `fragment = None if command is None else …`. The unreachable both-`None` case now fails closed with `command_not_run`. S009 is back to 350.
9. **R-11.** These were doc text only:
   - (a) the enums header names `_generate_next_value_`;
   - (b) the README hostkit sentence lists all five hostkit jobs;
   - (c) `muse/children.py` cites `#1036 INV-9` and `#1036 EC-34`.
10. **R-15.** `to_utc_datetime` catches `OverflowError` from `astimezone(UTC)` and raises the field's `ConfigurationError` with `details={"field": …}`.
11. **R-17.** `_export_file` gained `except OSError` after `except FileNotFoundError`. It raises `protocol_mismatch` with `MUSE_EXPORT_FILE_UNREADABLE_DETAIL` naming the path and the error type.
12. **R-21 (trivial part).** I moved `# @intent grok-delete-is-checked-on-disk` up with `folder = found.path.parent`, so it is inside `delete`'s window (def :215, intent :222). The final check keeps a one-line comment.
13. **Merge.** I ran `git merge origin/main` at `8da41971`. The briefing named `cb554ed3`, but main had moved one more commit, #1158. There were no conflicts, and the result is `6b55dde5`.
14. **Known-red tests.** Neither the harness failure-code merge-base test nor the MCP stdio flake fired in the full gate, so I needed no base-commit proof.

**Changes (one commit per defect, each lint-clean after `git add`):**

| SHA | Finding | Subject |
|---|---|---|
| `3a1dc4b1` | R-1 | `fix(harness-threads): wrap the new comment blocks at 72 columns [R-1]` |
| `53bca187` | R-6 | `fix(harness-threads): map a finished helper child in one place [R-6]` |
| `cdbbd72b` | R-5 | `fix(harness-threads): keep the paid thread's id on every later error [R-5]` |
| `3fbe9568` | R-23 | `fix(harness-threads): count a read_skill call only on its exact id [R-23]` |
| `f8c00aa7` | R-2 | `fix(harness-threads): read Muse evidence from the served items in every mode [R-2]` |
| `844583d0` | R-3 | `fix(harness-threads): dedupe Grok search before matching [R-3]` |
| `3b1ab656` | R-16 | `fix(harness-threads): give the opencode scan cap a next step that works [R-16]` |
| `b27a2ff7` | R-10 | `fix(harness-threads): end the Grok evidence dispatch in a default [R-10]` |
| `8953669d` | R-11 | `fix(harness-threads): correct three stale doc lines [R-11]` |
| `94cf9d9a` | R-15 | `fix(validation): refuse a time that overflows once moved to UTC [R-15]` |
| `27765710` | R-17 | `fix(harness-threads): map every unreadable Muse export file to protocol_mismatch [R-17]` |
| `42de68f5` | R-21 | `fix(harness-threads): move the Grok delete intent inside its window [R-21]` |
| `6b55dde5` | — | `Merge origin/main into feat/harness-thread-helpers-skills` |

**Invariants checked:**
- `git diff cd2b329b..HEAD -- tests/features/harness_threads` is empty, so there were no test edits.
- `git diff 239c408a -- lint/baseline.json` is empty.
- No new files. The 17 changed source files are all §12.3 rows.

**Gate matrix out (merged tree `6b55dde5`, `DEEPSEEK_API_KEY` set):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| lint | `$PY lint/run.py` | PASS (exit 0) | `S063 IMPROVED 4 -> 3` (already so at the base) · `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS`; S009 350/350, C002 9/9, S052 0, A002 605/703 IMPROVED |
| new tests | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads` | PASS (0 failing; was 34) | `1025 passed, 3 skipped in 87.79s (0:01:27)` |
| full local gate | `$PY scripts/run_ci.py` | PASS (exit 0) | `6632 passed, 17 skipped in 136.84s (0:02:16)` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep fixtures | `semgrep --test …` | PASS | `1/1: ✓ All tests passed` · `No tests for fixes found.` |
| semgrep scan | `semgrep scan --error …` | PASS (exit 0) | `Ran 1 rule on 975 files: 0 findings.` |
| remote checks | `gh api repos/cerredz/Vidbyte-SDK/commits/6b55dde5…/check-runs` | 4/4 green | `Package: completed success` · `Static policy: completed success` · `Source / Python 3.11: completed success` · `Source / Python 3.12: completed success` |

Remote run detail:
- CI run [38936498307](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38936498307):
  - Source 3.12: `SDK-LINT: PASS` · `6580 passed, 69 skipped, 19 warnings in 160.70s` · `CI passed.`
  - Source 3.11: `6580 passed, 69 skipped in 150.26s` · `CI passed.`
  - Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.`
- Static policy run [38936500713](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38936500713): `1/1: ✓ All tests passed` · `Ran 1 rule on 975 files: 0 findings.`
- No billing annotation appeared.

**Independent repro evidence (the S4 verifier's scripts, one line per finding):**
- R-2: `s4eng/repro_muse_goal_anchored.py`:
  - `[goal, anchoredSnapshot, exec never calls create_goal] raised muse.command_not_run`
  - `[plan, anchoredSnapshot, exec reads ANOTHER skill (bundled:import)] raised muse.command_not_run`
- R-23: `s4v-helpers/repro_muse_skill_prefix.py`: `raised muse.command_not_run`.
- R-5:
  - `s4c-inv29/repro.py`: `malformed RAISED FailureCode.GROK_PROTOCOL_MISMATCH thread_id= f27485b7-…`
  - `s4eng/repro_grok_plan_evidence_id.py`: `[plan; own summary.json has agent_name of the wrong type] raised grok.protocol_mismatch error.thread_id='59877c81-…'`
  - `s4v-helpers/repro_muse_evidence_id.py` case A: `raised muse.launch_failed error.thread_id='8b564f1b-…'`. Case B prints `RETURNED` because r5 runs no export, so the seam it patched no longer exists. It is obsolete, not red.
- R-3: `s4v-helpers/search_dupe.py`: `search 'LOGIN': []`.
- R-17: probe `scratchpad/r17_probe.py`: `win32 muse.protocol_mismatch path named: True thread_id: thread-0001`.
- R-15: both overflow inputs give `ConfigurationError` with `{'field': 'updated_at'}`.
- `s4v-helpers/repro_muse_d33_rule.py` now fails with `AttributeError: … has no attribute 'transcript'`. That is expected: the export path is deleted.

**Still open:** no confirmed finding and no gate.
- These stay `follow-up` by decision: R-8, R-9, R-12, R-13, R-14, R-18 (route S2), R-19, R-20, R-22, and R-21's 44 "external boundaries" markers.
- R-14 still reproduces as designed: `[raw code-review; …] RETURNED SUCCESS`.

## Iteration 2 — 2026-10-16 13:50 EDT — agent report: reports/S5-repair-2.md

**Defects in:** the final conformance re-review (`reports/S5-rereview.md`) returned SOUND at `578c88bb` with 0 Blocker, 0 Major and 2 Minor. Worktree HEAD was `68c2cf49`, clean.
- R-C1 is recorded as **R-24** (Minor, trivial, source). Item 1 of WHAT NOT TO DO at `vidbyte/harnesses/native/muse/commands.py:8` read "Do not give the evidence read or the export a key". Under spec r5 (D-33) this module runs no `muse export`, and `:5` of the same header says so.
- R-C2 is recorded as **R-25** (Minor, spec text). The spec author had already fixed it at `3c114e7b`.
- No gate was red. Lint, `run_ci.py`, both semgrep commands and the 4 remote checks were all green at `578c88bb`.

**Hypotheses and attempts (in order):**
1. **Reproduce R-24.** `grep -n 'transcript\|export' vidbyte/harnesses/native/muse/commands.py` hit `:4` ("re-exported"), `:5` ("no `muse export` runs for evidence") and `:8` ("or the export a key"). The contradiction is real.
2. **Options for R-24:**
   - (a) delete item 1. This loses a true warning: the evidence read must stay keyless (INV-23).
   - (b) reword item 1 to say that no export runs. This repeats the ARCHITECTURE NOTE.
   - (c) the re-review's wording: "1. Do not give the evidence read a key; only the exec child carries META_API_KEY."

   I chose (c). It is the smallest edit and keeps the INV-23 warning.
   - Before committing, I checked that (c) is true of the code. `MuseHelperRun.tool_calls` reaches `_serve`, and `muse/helpers.py:297` passes `removed=NATIVE_HELPER_REMOVED_VARIABLES`, which holds `META_API_KEY` (`lib/constants/native_threads.py:458-463`).
   - I also checked every other symbol the header names: `MuseThreadHelpers`, `init_muse_workspace`, `tool_calls`, `MUSE_READ_SKILL_ID_MEMBER`, both templates and `noneReason`. All exist.
   - It worked first time. Now `export` appears only in "re-exported" (`:4`) and "no `muse export` runs" (`:5`).
3. **Comment width.** The edited line is a module docstring line, not a `#` comment. The R-1 rule (`comment-format.md`) covers `#` comments only, and every sibling header (for example `grok/commands.py`) keeps one long line per key. So I kept the line's shape.
   - The width loop printed `files=31 new_wide_comment_lines=0`, the same as the re-review. The loop runs `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'` on each file of `git diff --name-only origin/main...HEAD -- 'vidbyte/*.py'`, then `comm -23` against the same awk over `git show origin/main:<f>`.
4. **Not touched:** `RecordFieldValidator.require_text` at `muse/commands.py:99`. That is the D-25 argument check, and the re-review's R-C2 scoping confirms it.
5. **Remote CI on a docs-only head.** The records live in committed docs, so I pushed and dispatched twice:
   - first on the code SHA `ade57291`, whose results are below;
   - then again on the docs-only records commit that carries this entry, whose results are in the S5 STATUS message.

**Changes:**

| SHA | Finding | Subject |
|---|---|---|
| `ade57291` | R-24 | `fix(harnesses): drop the stale export clause from the Muse commands header [R-24]` |
| (records commit) | — | `docs(spec): verify-log iteration 2 for harness-thread-helpers-skills` (verify-log, review statuses R-24/R-25, report) |

**Invariants checked:**
- `git diff cd2b329b..HEAD -- tests/features/harness_threads | wc -l` → `0`, so there were no test edits.
- `git diff 239c408a HEAD -- lint/baseline.json` and `git diff origin/main HEAD -- lint/baseline.json` → `0` lines each.
- `git diff --name-only 68c2cf49..ade57291` → only `vidbyte/harnesses/native/muse/commands.py`, with 1 line changed.
- `origin/main` is still `f7f32b19` (fetched 2026-10-16), and the merge base is `8da41971`. I did not merge.

**Gate matrix out (code SHA `ade57291`, `DEEPSEEK_API_KEY` set):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| lint | `$PY lint/run.py` (own exit code, after `git add`) | PASS (exit 0) | `S063 IMPROVED 4 -> 3` · `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS`; A001 642/642, A002 605/703, S009 350/350, C002 9/9, S052 0, A009 0 |
| new tests | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads` | PASS (exit 0) | `1025 passed, 3 skipped in 90.58s (0:01:30)` |
| full local gate | `$PY scripts/run_ci.py` | PASS (exit 0) | `6632 passed, 17 skipped in 138.65s (0:02:18)` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep fixtures | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` | PASS (exit 0) | `1/1: ✓ All tests passed` · `No tests for fixes found.` |
| semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS (exit 0) | `Ran 1 rule on 975 files: 0 findings.` |
| remote checks | `gh api repos/cerredz/Vidbyte-SDK/commits/ade57291…/check-runs` | 4/4 green | `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success` |

Remote run detail:
- CI run [38942154825](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38942154825):
  - Source 3.12: `SDK-LINT: PASS` · `6580 passed, 69 skipped, 19 warnings in 146.09s` · `CI passed.`
  - Source 3.11: `6580 passed, 69 skipped in 134.16s` · `CI passed.`
  - Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.`
- Static policy run [38942158122](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38942158122): `1/1: ✓ All tests passed` · `Ran 1 rule on 975 files: 0 findings.`
- The only annotation is a runner notice, not billing: "The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026."

**Still open:** no confirmed finding and no gate.
- R-24 is fixed @`ade57291`, and R-25 @`3c114e7b`.
- The follow-ups are unchanged by decision: R-8, R-9, R-12, R-13, R-14, R-18..R-20, R-22, and R-21's 44 markers.

## Iteration 3 — 2026-10-16 14:46 EDT — agent report: reports/S5-repair-3.md

**Defects in:** two trivial Minors from the S6 PR author (`reports/S6-pr-author.md`, "Things that looked wrong"), routed back to repair at HEAD `a35ccf11` (`5c93e6c9` plus one unpushed docs commit). No gate was red: all green at `71c15a2c`, and 4/4 remote at `5c93e6c9`.
- **R-26** (S6 R-open-1): `vidbyte/harnesses/README.md:179` said "22 keyless functions" but listed 23 names, because `init_muse_workspace` sat in the list.
- **R-27** (S6 R-open-2): `vidbyte/harnesses/native/grok/store.py:104-106` had three blank lines between `GrokHome` and `GrokStore`.

**Hypotheses and attempts (in order):**
1. **R-26, three options.**
   - (a) Change "22" to "23". Rejected: spec r5 (`spec.md:17`) and the PR body count 22 helpers.
   - (b) Move `init_muse_workspace` into the "Command and skill functions: 24" bullet. Rejected: that makes the bullet 25, against the PR body's 24.
   - (c) Keep "22", drop `init_muse_workspace` from the list, and give it its own sentence after the return sentence: "`init_muse_workspace` is keyless too: it runs `muse init` in the workspace, with `dry_run=True` to only show what it would create, and returns a `NativeCommandOutput`." I also dropped its clause from the return sentence, so it is described once. **Chosen.**
   - Check: a scratch script (`r26count.py`) parses the names between "keeps:" and "They take", expands `<h>`, and compares them with `vidbyte.harnesses.native.__all__`. HEAD gave 23 names; the fix gives `names listed: 22` and `listed==exports: True`. Its first version counted the bare `<h>` placeholder token as a name (25); I fixed the parser, not the README.
   - No test pins this README text (`grep` of `tests/features/harness_threads`). The README is 15,230 characters (A009 0).
2. **R-27, three options.**
   - (a) Delete one blank line. **Chosen.**
   - (b) Run a formatter on the file. Rejected: it would touch other lines.
   - (c) Dispute it. Rejected: there is no basis.
   - Reproduced first with `ruff check --no-cache --isolated --preview --select E303 vidbyte/harnesses/native/grok/store.py`: `too-many-blank-lines … (3) --> store.py:107:1`. After `sed -i '106{/^$/d}'`, the diff is `0 1` (one deletion), and E301/E302/E303/E305 over `grok/` print `All checks passed!`. The repo's lint does not select E303, so this was never a gate.
3. **The full gate, first run: FAILED, and the cause was my shell, not the branch.** I ran `export PYTHONPATH="$(pwd)"` (from code-map §1.2's worktree note), then `run_ci.py`.
   - The source stage passed: `6632 passed, 17 skipped`.
   - The package stage failed: `ModuleNotFoundError: No module named 'vidbyte'` in the smoke check. Before it, pip printed `vidbyte-sdk is already installed with the same version as the provided wheel`.
   - Root cause: `_verify_clean_install` runs `pip install` with cwd at the repo root and the inherited `PYTHONPATH`. So pip finds the git-ignored `vidbyte_sdk.egg-info` in the worktree, treats the SDK as installed, and skips the wheel. The smoke step then pops `PYTHONPATH` (`clean_python_path=True`), so nothing is importable.
   - Independent check: an empty scratch venv's `pip list` shows `vidbyte-sdk 0.3.0` with `PYTHONPATH=<worktree>`, and nothing without it.
   - `scripts/run_ci.py` is untouched by the branch. I re-ran with `PYTHONPATH` unset, as iterations 1 and 2 did, and it passed.
   - **Lesson: never export `PYTHONPATH` before `run_ci.py`.** The pip-install step inheriting it is a latent `run_ci.py` defect, outside §12.3. I did not change it.
4. **Merge state.** `origin/main` is `6983afd2` (#1160–#1164), 5 commits past the merge base `8da41971`. `comm -12` of both sides' changed files is empty. I did not merge.

**Changes:**

| SHA | Finding | Subject |
|---|---|---|
| `ccfe71ca` | R-26 | `docs(harnesses): count only the 22 helpers in the thread-helpers bullet [R-26]` |
| `25f36c6d` | R-27 | `style(harnesses): use two blank lines between GrokHome and GrokStore [R-27]` |
| (records commit) | — | `docs(spec): verify-log iteration 3 for harness-thread-helpers-skills` (verify-log, review rows R-26/R-27, report) |

**Invariants checked:**
- `git diff cd2b329b..HEAD -- tests/features/harness_threads | wc -l` → `0`, so there were no test edits.
- `git diff 239c408a HEAD -- lint/baseline.json | wc -l` → `0`.
- `git diff --name-only a35ccf11..25f36c6d` → only `vidbyte/harnesses/README.md` and `vidbyte/harnesses/native/grok/store.py`.
- Neither commit touches a `#` comment, so the R-1 width check does not apply. Each commit ran lint after `git add` and exited 0.

**Gate matrix out (code SHA `25f36c6d`, `DEEPSEEK_API_KEY` set, `PYTHONPATH` unset):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| lint | `$PY lint/run.py` (own exit code, after `git add`) | PASS (exit 0) | `S063 IMPROVED 4 -> 3` · `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS`; A009 0 CLEAN |
| new tests | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads` | PASS (exit 0) | `1025 passed, 3 skipped in 91.72s (0:01:31)` |
| full local gate | `$PY scripts/run_ci.py` | PASS (exit 0) | `6632 passed, 17 skipped in 149.54s (0:02:29)` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep fixtures | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` | PASS (exit 0) | `1/1: ✓ All tests passed` · `No tests for fixes found.` |
| semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS (exit 0) | `Ran 1 rule on 975 files: 0 findings.` |
| remote checks | `gh api repos/cerredz/Vidbyte-SDK/commits/25f36c6d…/check-runs` | 4/4 green | `Package completed success` · `Static policy completed success` · `Source / Python 3.12 completed success` · `Source / Python 3.11 completed success` |

Remote run detail:
- CI run [38951244041](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38951244041):
  - Source 3.11: `SDK-LINT: PASS` · `6580 passed, 69 skipped in 149.08s` · `CI passed.`
  - Source 3.12: `SDK-LINT: PASS` · `6580 passed, 69 skipped, 19 warnings in 154.22s` · `CI passed.`
  - Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.`
- Static policy run [38951246923](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38951246923): `1/1: ✓ All tests passed` · `Ran 1 rule on 975 files: 0 findings.`
- The only annotation is the Ubuntu 26 runner-label notice, not billing.
- The records commit that carries this entry is dispatched again. Its results are in the S5 STATUS message.

**Still open:** no confirmed finding and no gate.
- R-26 is fixed @`ccfe71ca`, and R-27 @`25f36c6d`.
- The follow-ups are unchanged by decision: R-8, R-9, R-12, R-13, R-14, R-18..R-20, R-22, and R-21's 44 markers.
- One process note for the orchestrator, not a finding: `run_ci.py`'s install step inherits `PYTHONPATH` (see attempt 3). It is a candidate field-guide lesson or a separate PR.
