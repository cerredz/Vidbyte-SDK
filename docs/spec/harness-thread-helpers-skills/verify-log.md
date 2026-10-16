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
