# Verification log: InfiniteMemory agent

Gate set (from context/code-map.md §1): new-test pack `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` · lint `python lint/run.py` · import order (S051) `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` · semgrep (CI only) `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` · full local gate `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` without PYTHONPATH · remote checks `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1084`.

## Iteration 1 — 2026-10-15 09:25 — agent report: reports/S5-repair-1.md

**Defects in:** review.md R-1 (Blocker), R-2..R-11 (Major), Minors R-12..R-25. Gate state in: new-test pack `14 failed, 93 passed` (S2 additions for R-1, R-3, R-4, R-6, R-8, R-11, R-18); lint and the full local gate not yet run on 12aa9f5f this iteration.

**Hypotheses and attempts:**
- R-1: hypothesis that moving the card build and `pair_finished` inside the pair guard is enough. Probe (`PROBE=NOJOURNAL` plugin) disproved it for the lone-surrogate case: the fallback card rewrites the same summary and the journal append raises `UnicodeEncodeError` again. Fix needed both halves: the journal writes ASCII JSON (`json.dumps(record)`), and the build plus record moved into `InfinitePair._finish`, called from the try and from the except. Rejected the reviewers' alternative `files=()` in the fallback, because it would erase the files list on every error card (D-14); the new path rule (a path must be one line) makes the files valid by construction.
- R-2: protected names now compare on `relative.as_posix().casefold()`. No test can show it on Windows (resolve returns disk case); the S4 probe `v6_case_fold.py` now refuses `Entries.jsonl`, `SEED/brief.md`, `.RUNS/x.jsonl`.
- R-3: considered calling `_capped` from `render`; rejected because it makes a run → render → `_capped` two-level chain (the R-12 pattern). The dropped and files texts are cut inline with `TokenEstimate.count/cut` and `INFINITE_TRUNCATION_MARKER`.
- R-4: duplicate names are checked over all cards; tools, `#N` context, and max_agents over new pairs only. No await sits between the check and the reserve.
- R-7: the first fix put a try/except in `InfiniteMemoryAgentSettings.__post_init__`, which raised its C901 to 11, so `lint/run.py` failed (S008 REGRESSED 20 vs 19). Moved the check into `_validate_model` (precedent `JevRunBriefSettings._validate_model`); S008 back to 19. Seed copy through `LocalFileSystemBackend.copy` keeps byte equality (AC-1) but inherits `shutil.copy2`'s mode bits: a read-only seed gives a read-only copy and the next setup over the same folder raises PermissionError (verified by probe in `scratchpad/s5-1/ro/`). Named in workspace.py KNOWN EDGE CASES; not covered by any AC. Rejected read_text/write_text (breaks AC-1 for non-UTF-8 seeds) and a lib change (outside §12.3).
- R-8: `_commit` left untouched (no OSError catch there, by the brief). `_replace` removes its temporary file on any failure; remember, write_note, and edit_file turn `ConfigurationError`, `ToolExecutionError`, `OSError`, `ValueError` into a refusal; note paths with a colon are refused after resolve, so absolute paths still read "outside the workspace". Observed but not fixed (no finding names it): a multi-file write can still be partial when a later file fails to encode (root `remember` with `supersedes`, or a new `write_note` whose description holds a lone surrogate).
- Semgrep: the global semgrep 1.170.1 cannot import under mcp 2.x (`No module named 'mcp.server.fastmcp'`). Ran it through a stub launcher that replaces only the unused `mcp` subcommand; nothing installed.
- Source stage run 2 had one failure, `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`; it passed 3/3 alone and the stage passed on run 3 with no change. Known flaky test, not this change.
- R-11, R-18: closed by the S2 test additions at 9af96d42; no source change.

**Changes:**
- 1e0b1524 fix(infinite): keep a pair's card build and record inside its guard [R-1]
- 1769a44f fix(infinite): match protected note paths with case ignored [R-2]
- a47a7614 fix(infinite): cut a rendered card's dropped and files lists to the card cap [R-3]
- a6b4e4c1 fix(infinite): replay a finished pair even after its context entry was superseded [R-4]
- c4822ebb fix(registries): restore main's untouched runtime-error f-strings [R-5]
- 3617ec69 fix(infinite): tell remember to keep a long paste in a note, without echoing it [R-6]
- 29760f65 fix(infinite): validate the model and copy seeds through the backend [R-7]
- f8387a78 fix(infinite): refuse failed memory writes cleanly and leave no temp file [R-8]
- 99e95803 fix(infinite): rewrap comment lines to 72 columns [R-9]
- fddefd51 fix(prompts): give every infinite_memory parameter a four-sentence general description [R-10]
- 61bdbb6b fix(infinite): lift finished_lines into InfinitePair.run [R-12]
- 6b55613c fix(infinite): describe the pair yield as a fairness turn only [R-13]
- 649777fa fix(infinite): name the minimum cap as INFINITE_MIN_CAP [R-15]
- 9c5b0650 fix(infinite): say "below the depth cap" in the launch.py header [R-16]
- c5f4859f docs(infinite): say the history trim drops the oldest tool exchanges first [R-17]
- 714c1aa0 fix(infinite): space the writer assignment and keep the Jev prompt group whole [R-21]
- 5cdac067 fix(infinite): keep the settings value out of the agent's type refusal [R-23]
- 5ee09e99 fix(infinite): move the model check into its own settings helper [gate:lint]
- `git diff 9af96d42..HEAD -- tests/` is empty.

**Gate matrix out:**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `...................................  [100%]` / `107 passed in 3.21s` |
| Lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` (all rule counts equal origin/main: S008 19, C012 23, S051 259, S062 889) |
| Import order (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (no new finding) | `Found 223 errors.` / `[*] 223 fixable with the --fix option.` (origin/main: 223; the one in `vidbyte/lib/registries/runtimes.py:33` is main's own unsorted import block) |
| Semgrep | `python semgrep_launch.py scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` | PASS | `Ran 1 rule on 946 files: 0 findings.` / exit 0 |
| Full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `5280 passed, 14 skipped in 49.81s` / `CI passed.` / `exit=0` |
| Full local gate, package | `python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / `exit=0` |
| Remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1084` | none (workflows disabled repo-wide) | `no checks reported on the 'feat/infinite-memory-agent' branch` |

**Still open:** R-14, R-19, R-20, R-22, R-24, R-25 (Minors marked follow-up; left open by instruction). No confirmed finding open; no gate red.

## Iteration 2 — 2026-10-15 10:22 — agent report: reports/S5-repair-2.md

**Defects in:** review.md "Re-review round 1 (post-repair) — verified": R-26 (Major, a regression from R-7), R-27 (Major), R-28 (Minor, `trivial`, with a narrow spec edit granted); R-29 is `follow-up` and was left open by instruction. Gate state in at 3d7f0e57: the new-test pack had `4 failed, 107 passed`, the 4 being the S2 regression tests from 11b19a7d. Lint and both CI stages were green apart from those 4 tests.

**Hypotheses and attempts:**
- R-26: I took the verifier's proven fix, which adds the owner write bit to each seed copy after `self.backend.copy` (`copy.chmod(copy.stat().st_mode | stat.S_IWRITE)`). I did not repeat the two alternatives the verifier rejected: `shutil.copyfile` pushes S061 from 5 to 6, and skipping an identical copy fails the test, which edits the seed between builds. I also kept away from a mode option on the lib backend, which is outside §12.3. `c1_ro_seed.py` now prints `built | copy writable: True` three times. Lint is unchanged, because `chmod` is not on S061's list. The KNOWN EDGE CASES sentence about read-only copies is deleted.
- R-27: the encode checks run before any file is written, and `_commit` and the tools' catch tuples are untouched (INV-29).
  - At the top of `_entry_rules`, under its own `@intent`, the code encodes `(draft.text, *draft.refs)`.
  - In `write_note`, it encodes every value of `changed` before the write loop.
  - `commit_entry` needs no loop of its own, because it calls `_entry_rules`, and its other texts are raw lines read with `errors="replace"` or pattern-bound fields.
  - The refusal is the raw `UnicodeEncodeError` text, which the tools already catch as a `ValueError`. That text is ASCII-escaped (`'\ud83d'`), so no surrogate reaches the tool result.
  - I rejected wrapping the error in a ToolExecutionError. It adds a try/except to `_entry_rules`, which risks S008 (iteration 1's lesson), and the single-file path from R-8 already refuses the same way.
  - The verifier's comment was 73 columns, so every new comment is rewrapped to 72 columns or fewer (`awk 'length($0) > 72' … | grep '^\s*#'` prints nothing).
  - Results: the pair test takes the "refused when staged" branch. `c2_partial.py` reports `changed files: []` for steps 2–4, step 5 leaves only `notes/b.md`, and `r1_guard.py` gives both pairs `Verdict: passed` with `['a first fact', 'a third fact', 'b fact']`.
  - Step 6 of `c2_partial.py` now prints `IndexError`. That is the probe indexing an entry that was never staged, not a defect.
- R-28: the briefing grants only a §17 list plus the fix to the stale bullet, so INV-20 itself is not edited, although review.md's fix text also suggested adding "one line, no colon" to INV-20. The list names the five rules: note paths are one line with no colon (R-1, R-8); the model catalog check and `STRICT_MODEL_VALIDATION` (R-7); `INFINITE_MIN_CAP` (R-15); ASCII journal lines (R-1); and UTF-8-encodable memory text (R-27). The `runtimes.py` bullet now says the file changes only by the import and the registry row. `lint --rule S062 --all` (run with `PYTHONIOENCODING=utf-8`, because cp1252 crashes the `--all` listing through a pipe) shows main's own finding back at `runtimes.py:53` and none in the infinite tests. The README's limits list gains the `STRICT_MODEL_VALIDATION` clause.
- Full lint was run after each source fix and at the end. All 133 rule lines are byte-identical to 3d7f0e57, including C012 23, S061 5, S062 889 and S008 19.

**Changes:**
- 582b5793 fix(infinite): leave each seed copy writable so the next setup can replace it [R-26]
- c90b43be fix(infinite): refuse text UTF-8 cannot hold before any memory file is written [R-27]
- 5c5b7d33 fix(infinite): record the S5 repair rules in spec section 17 and the README [R-28]
- `git diff 11b19a7d..HEAD -- tests/` and `git diff 3d7f0e57..HEAD -- lint/` are both empty.

**Gate matrix out:**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `.......................................  [100%]` / `111 passed in 2.89s` |
| Lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` (133 rule lines identical to 3d7f0e57: C012 23, S061 5, S062 889, S008 19) |
| Import order (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (no new finding) | `Found 223 errors.` / `[*] 223 fixable with the --fix option.` (223 = origin/main; the only infinite hit is main's own block at `runtimes.py:33`) |
| Semgrep | `python scratchpad/s5-1/semgrep_launch.py scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 946 files: 0 findings.` / exit 0 |
| Full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `5284 passed, 14 skipped in 50.95s` / `CI passed.` / exit 0 (the flaky MCP stdio test did not fail this run) |
| Full local gate, package | `python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / exit 0 |
| Remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1084` | none (workflows disabled repo-wide) | `no checks reported on the 'feat/infinite-memory-agent' branch` (PR head 5c5b7d33, draft) |

**Still open:** R-29, a Windows second-process lock between the two `os.replace` calls (`follow-up`, left open by instruction). Also the follow-up Minors R-14, R-19, R-20, R-22, R-24 and R-25. No confirmed must-fix finding is open, and no gate is red.
