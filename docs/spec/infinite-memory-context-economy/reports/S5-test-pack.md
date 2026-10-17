# S5 · Test-pack author — report

Status: DONE. Base HEAD `c3ecd466`; test commit `fd6dab0b`, followed by the `docs(spec)` commit that carries this report. Nothing was pushed.

## What was built

There are 15 new tests, 10 of them red at HEAD, each tied to a row in `review.md`. No production file, existing assertion, lint baseline, or spec section other than the AC-2.5 Proof cell was touched.

| Row (pins) | Tests | At HEAD | Proven green under | Killed by |
|---|---|---|---|---|
| R-8 (R-2) | 3 SRCH + 1 RCL | red ×4 | `fix_r2_r5` | n/a |
| R-9 (R-3) | 3 ECO AC-2.5 cases, CW scope test | red ×4 | `fix_mask_batch` | `mut_mask_batch` (AC-2.5 `[gemini]`, CW scope test) |
| R-9 guards | 3 ECO sequential cases, CW unscoped test | green ×4 | n/a | `mut_mask_batch` (sequential `[gemini]`); `mut_mask_unscoped` (CW unscoped test, plus 3 existing `DeterministicStrategyTests`) |
| R-10 (R-7) | 1 SRCH | red | `fix_r7` (still red under `fix_r2_r5` alone) | n/a |
| R-11 (R-6) | 1 ACB (2 subtests) | red | `fix_anth_digest` | n/a |
| R-24 (rowid deletes) | 1 FTI | green | n/a | `mut_delete` |

Files (all under the test tree): `tests/features/infinite_memory_agent/test_infinite_memory_search.py`, `test_infinite_memory_recall.py`, `test_infinite_memory_economy.py`, `FEATURE.md` (new Known Failure Modes bullets and a Historical Regressions paragraph, both added lines only); `tests/test_compaction_windows.py`, `tests/test_anthropic_cache_breakpoints.py`, `tests/test_fulltext_index.py`. Also `test-plan.md` (the "S5 test-pack additions" section: its coverage map, red run, and tests not written) and spec §6.2's AC-2.5 Proof cell.

## Runs

All runs use `PYTHONPATH="<wt>[;plugin dirs]" python -m pytest -p no:cacheprovider -q` over the 7 related paths listed in test-plan.md. The environment is Python 3.11.0, SQLite 3.38.4 with FTS5, and pytest 8.3.5.

| Run | Final line |
|---|---|
| HEAD before the edits | `331 passed in 9.04s` |
| HEAD with the S5 tests | `10 failed, 336 passed in 9.53s` |
| `-p fix_r7 -p fix_mask_batch -p fix_anth_digest` | `346 passed in 9.00s` |
| `-p mut_delete` | `11 failed, 335 passed` (the HEAD reds plus FTI rowid) |
| `-p mut_mask_batch` | `9 failed, 337 passed` |
| `-p mut_mask_unscoped` | `10 failed, 336 passed` |
| Whole `tests/` tree at HEAD | `13 failed, 6370 passed, 16 skipped in 112.38s`: the 10 S5 reds, plus 3 tests in `tests/features/harness_threads/test_harness_threads_surface.py` that fail when run alone too. They compare this branch's packages and failure codes with main (`assert 148 == 120`, among others) and do not involve S5. |

`PYTHONIOENCODING=utf-8 python lint/run.py` with the files staged ended `SDK-LINT: PASS`. The baseline is unchanged: S061 and S063 print "IMPROVED", but those come from earlier stages, and no baseline update was run. Every added `#` comment line is at most 72 columns.

## Red reasons at HEAD

- **The SRCH query test.** `fulltext.py:104: sqlite3.OperationalError: unterminated string`.
- **The SRCH entry-line and note-name tests.** `fulltext.py:69: UnicodeEncodeError`, on `'\ud800'` and on `'\udcff'`.
- **The RCL test.** "the pre-search raised, so the retriever never started" (`assert 0 == 1`).
- **The ECO AC-2.5 cases.** "masking hid an output the model has not read yet".
- **The CW scope test.** "an output after the newest model turn was masked".
- **The SRCH warm-search test.** "a search with nothing changed opened 13 workspace files".
- **The ACB test.** `anthropic.py:189: UnicodeEncodeError` in both subtests.

## Spec-order defect in the verifier's fix

`s4-verify/fix_r1.py` normalizes the query before the FR-8.6 blank check, so a query of `"\x00"` comes back `invalid_argument`. Spec r5 INV-8.2 reads a NUL as whitespace, and FR-8.6 tests the query as given (`"\x00".strip()` is not blank), so the right answer is SUCCESS with 0 of 0. The R-8 query test pins the spec, which makes it red under `fix_r1` and green under `fix_r2_r5`. That plugin runs the blank check on the raw query, then `query.replace("\x00", " ").encode("utf-8", "ignore").decode("utf-8")`. **The repair must follow this order: blank check, then normalize.**

## What a repair must keep (seams the tests use)

- **R-10.** Opens are counted with `sys.addaudithook` "open" events. On a warm search, no unchanged workspace file may be opened by any route: `open`, `Path.read_bytes`/`read_text`, or an `is_text_file` sniff. Stat, `resolve` and `os.scandir` are free. The cold search must still read through Python's file APIs, so its opens are seen (the positive control). A changed size must count as a change.
- **R-9.** The test takes the root's masking from `build_agent(tmp_path).middleware[0]`, so masking must stay first. The placeholder is the `masked_output` leaf. A model turn is role `assistant` or `model`. With `tools=()` the output must equal main's.
- **R-11.** The first body must equal main's body exactly, so do not escape or alter the text that is sent. Make only the digest safe (for example `surrogatepass`), and the repeat must still be marked.
- **R-24.** The helper must open its connection through `sqlite3.connect` (or a module-level `fulltext.connect`), where the trace is attached. Each DELETE must name `rowid` and never `source`.
- **R-8.** A bad entry line is skipped like a malformed one, and the other entries stay. A note whose name UTF-8 cannot encode is left out, and the other notes stay. Both must keep working on a second search and on a fresh `FullTextIndex`.

## Scratch plugins (not committed)

- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-tests/fix_r2_r5.py`
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-tests/fix_r7.py`
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-tests/mut_mask_unscoped.py`
- The probes `probe_audit.py`, `probe_name.py` and `probe_trace.py` are in the same folder.
- From earlier stages: `.../scratchpad/s4-verify/fix_r1.py`, `fix_mask_batch.py` and `fix_anth_digest.py`, and `.../scratchpad/s4-eng/mut_delete.py` and `mut_mask_batch.py`.

## Tests deliberately not written

These are listed with reasons in test-plan.md under "S5 tests deliberately NOT written":

- R-8 at helper level, because the guard lives in `search_memory`.
- Re-sniffing a skipped binary file on warm searches, on which the spec is silent.
- R-19, which has no trigger left after R-2 and no allowed fault seam.
- R-17, R-18, R-20, R-21 and R-22, by the orchestrator's ruling.
- R-3 through a full `ScriptedTree` run, which allows one call per step.
- The FR-8.6 wording.
- New header lines in the touched test files, since comment-only edits are forbidden. `FEATURE.md` carries the map instead.
