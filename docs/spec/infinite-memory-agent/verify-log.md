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
