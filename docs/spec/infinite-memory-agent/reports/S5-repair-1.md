# S5 repair iteration 1/8: InfiniteMemory agent

Branch `feat/infinite-memory-agent`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1084 (draft). Start 12aa9f5f, end 5ee09e99 (pushed), plus the docs commit that carries this report. `git diff 9af96d42..HEAD -- tests/` is empty: no test was changed.

## Gate matrix

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS (was 14 failed, 93 passed) | `...................................  [100%]` / `107 passed in 3.21s` |
| Lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| Import order (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (no new finding) | `Found 223 errors.` / `[*] 223 fixable with the --fix option.` (origin/main also 223) |
| Semgrep (CI only) | stub launcher, `scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` | PASS | `Ran 1 rule on 946 files: 0 findings.` / exit 0 |
| Full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `5280 passed, 14 skipped in 49.81s` / `CI passed.` / `exit=0` |
| Full local gate, package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / `exit=0` |
| Remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1084` | none (workflows disabled repo-wide) | `no checks reported on the 'feat/infinite-memory-agent' branch` |

Every lint rule count at HEAD equals the origin/main export (179d8adc, the merge base): S008 19, C012 23, S061 5, S062 889, S051 259, A001 642, A002 566, A007 255, S025 261; `diff` of the two count lists exits 0.

## Per finding

- **R-1 (Blocker), 1e0b1524.** `_note_path` refuses a path where `path.splitlines() != [path]` (U+2028, U+0085, `\n`), checked on the raw path because `files_written` records the raw path. The journal's `_append` writes ASCII JSON (`json.dumps(record)`; `ensure_ascii=False` kept in workspace.py so entries stay greppable). The card build and `pair_finished` moved into `InfinitePair._finish`, called from the try and from the except (UNCHECKED, capped error text, files kept). Evidence: `-k card_or_record_cannot_be_written` → `3 passed`. A probe showed the guard move alone does not hold the lone-surrogate case (the fallback card rewrites the same summary), so both halves are needed.
- **R-2, 1769a44f.** Protected names compare on `relative.as_posix().casefold()`. No test can show it on Windows (resolve returns disk case); the S4 probe `v6_case_fold.py` now refuses `Entries.jsonl`, `SEED/brief.md`, `.RUNS/x.jsonl`.
- **R-3, a47a7614.** `render` cuts the joined dropped and files texts to the card cap with `TokenEstimate.count/cut` and `INFINITE_TRUNCATION_MARKER`; README limits line updated. Evidence: `-k long_dropped_and_files_lists` → `1 passed` (was 3467 tokens against a 1642 bound).
- **R-4, a6b4e4c1.** `_check(cards, fresh)`: duplicate names over all cards; tools, `#N` context, and max_agents over new pairs only; no await between check and reserve. Evidence: `-k replays_after_its_context_entry_was_superseded` → `1 passed`.
- **R-5, c4822ebb.** Restored main's two f-string lines; `git diff origin/main..HEAD -- vidbyte/lib/registries/runtimes.py` now shows only the import and the registry row. S062 889 = main.
- **R-6, 3617ec69.** `remember` refuses multi-line text without echoing it and points to `write_note` plus a one-line pointer; the cap message adds the same advice. Evidence: `-k keep_a_long_paste_in_a_note` → `2 passed`.
- **R-7, 29760f65 + 5ee09e99.** The model check uses `ProviderModelRegistry.validate_provider_model_pair` (error names `model_name`); seeds copy through `LocalFileSystemBackend.copy`; `shutil` is gone from workspace.py. The try/except first raised `__post_init__` C901 to 11 (S008 REGRESSED 20 vs 19); 5ee09e99 moved it into `_validate_model` (precedent `JevRunBriefSettings._validate_model`), and S008 is back to 19.
- **R-8, f8387a78.** `_replace` deletes its temp file on any failure and re-raises; remember, write_note, and edit_file turn `ConfigurationError`, `ToolExecutionError`, `OSError`, and `ValueError` into a refusal; a colon in the resolved relative path is refused. `_commit` is untouched. Evidence: `-k memory_write_that_fails_on_disk` → `6 passed`; `-k note_path_with_a_colon` → `1 passed`.
- **R-9, 99e95803.** 22 comment lines rewrapped to 72 columns with the words unchanged; an awk scan of the new modules finds no comment line over 72.
- **R-10, fddefd51.** All 19 parameter-description leaves of `infinite_memory.json` are four general sentences with no examples; "such as s2" removed from `drop_entry_tool_description`.
- **R-11, R-18.** Fixed by the S2 additions at 9af96d42; no source change.
- **Minors (trivial):** R-12 61bdbb6b (`finished_lines` called from `run`), R-13 6b55613c (intent says fairness only; the yield stays for AC-37), R-15 649777fa (`INFINITE_MIN_CAP`), R-16 9c5b0650, R-17 c5f4859f, R-21 714c1aa0, R-23 5cdac067.

## Test changes proposed

None.

## Findings believed wrong

None.

## Open, and next hypotheses

- R-14, R-19, R-20, R-22, R-24, R-25 stay `open`: marked `follow-up` in review.md and left open by the brief.
- **For the orchestrator, not a gate failure.** R-7's backend copy inherits `shutil.copy2`'s mode bits. A read-only seed gives a read-only copy, and a second setup over the same folder raises PermissionError (probe in the session scratchpad `s5-1/ro/`). No AC covers it; it is named in workspace.py KNOWN EDGE CASES. Next step if wanted: a mode option on the lib backend's copy (outside §12.3).
- **For the orchestrator, no finding names it.** A write that touches several files can still be partial: a root `remember` with `supersedes` and a lone surrogate writes superseded.jsonl before entries.jsonl fails, and a new `write_note` whose description holds a lone surrogate writes the note before files.jsonl fails. Next step: encode-check every changed text before the write loop.
- The local semgrep 1.170.1 cannot import under mcp 2.x; it was run through a launcher that stubs only its unused `mcp` subcommand. CI runs it in its own environment.
- `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` failed once in a full run, passed 3/3 alone, and passed in the next full run. It is flaky, and this change does not touch it.
