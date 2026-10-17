# S5 · Test pin for R-25 — report

Status: DONE. Base HEAD `bb1f9306` (code `72d1ca7f`). Test commit `1385c8e7`. Nothing was pushed. This report is written but not committed; the orchestrator's next `docs(spec)` commit can carry it.

## What was built

The commit adds 2 tests. Both are red at HEAD for the reason R-25 names, and both are green under the verifier's proven fix. All changes are added lines (128 insertions, 0 deletions). No production file, existing line, assertion, or lint baseline was touched.

| File | Change |
|---|---|
| `tests/features/infinite_memory_agent/test_infinite_memory_search.py` | Adds `import errno`, plus a new section at the end. The section holds the fault seam (`_FAILING_OPEN`, `_FAILED_OPENS`, `_FAILING_HOOK_ADDED`, `_fail_armed_open`, `_one_open_fails`) and the two tests below. |
| `tests/features/infinite_memory_agent/FEATURE.md` | One Known Failure Modes bullet and one Historical Regressions paragraph. The file header lines stay untouched, as in the earlier S5 pack. |
| `docs/spec/infinite-memory-context-economy/test-plan.md` | A new section, "S5 re-review pin (R-25)". It holds the seam note, two coverage-map rows, the red-run table, what a repair must keep, and the tests not written. |

The tests:

1. `test_a_changed_note_whose_read_fails_once_is_found_by_the_next_search` covers INV-8.4 and the S3 deviation for row 20.
   - `notes/plans.md` is indexed, then rewritten with a new size so that only the new line holds `costs`.
   - The next search's first open of the note raises `PermissionError(EACCES)`.
   - Preconditions: exactly one open failed, and that call returned SUCCESS.
   - Then the next search and the one after must each show `notes/plans.md:1: Sigma plan now costs 129 USD`.
2. `test_a_changed_entries_file_whose_read_fails_once_has_every_entry_found_by_the_next_search` covers INV-8.4, INV-8.5, the row-20 deviation, and G-2.
   - Entry #1 is indexed, then `entries.jsonl` gains entry #2 through `write_jsonl`.
   - The next search's first open of the file raises `OSError(EMFILE)`, a plain `OSError` and not a `PermissionError`.
   - The same two preconditions apply.
   - Then the next search and the one after must each give both entries, with metadata `{"hits": 2, "total": 2}`.

Selector: `-k read_fails_once`.

## The seam, and why this one

The seam is a second `sys.addaudithook` on the `"open"` event, armed by `with _one_open_fails(target, error) as failed:`.

- While armed, the hook raises `error` from the first open whose path matches the target. It compares `normcase(abspath(...))` against the target as given and as resolved.
- It then disarms itself, so the next open of the file works.
- The context manager disarms it in `finally` and copies the failed opens into `failed`.
- A hook cannot be removed, so it is added once per process behind `_FAILING_HOOK_ADDED`, the same way the R-10 recorder is added. When unarmed it returns at once.
- It fires for `open`, `io.open`, `os.open`, and every `pathlib` read, in the worker thread that opens.

I chose it over `patch.object(Path, "open", ...)` because these tests become the contract the repair agent cannot edit, so they must not depend on how the fix opens the file.

- A `Path.open` patch sees HEAD's `read_bytes` and the proven fix's `path.open("rb")`.
- It would not see a fix that reads the whole file through builtin `open` or `os.open`. Such a fix is valid, and the patch would fail it on the precondition.
- The audit hook sees every one of those routes. The variant runs below prove it.
- Flip condition: if the repo ever bans audit hooks in tests, or an interpreter stops aborting an open when a hook raises, switch to a `Path.open` patch and accept that the fix must open the file through `pathlib`.

The seam is consistent with spec §13. The filesystem, `InfiniteWorkspace`, the toolset (`InfiniteMemoryAgentTools.get_tools`), and SQLite FTS5 stay real. The hook only injects the error the OS raises under a sharing lock or under handle exhaustion. The real share-mode-0 lock gives the same verdict (cross-check below), and it is Windows-only, so it cannot be the pin.

## Runs (final lines)

All runs used `PYTHONPATH="<worktree>[;<plugin dir>]" python -m pytest <paths> -q -p no:cacheprovider [-p <plugin>]` on Python 3.11.0 with SQLite 3.38.4. The related suites are `tests/features/infinite_memory_agent tests/test_fulltext_index.py tests/test_code_search_tools.py`.

| Run | Final line |
|---|---|
| Related suites at HEAD, before the edit | `205 passed in 8.07s` |
| Pins at HEAD (`-k read_fails_once`) | `2 failed, 20 deselected in 0.98s` |
| Related suites at HEAD with the pins (re-run at `1385c8e7`) | `2 failed, 205 passed in 8.25s` |
| Pins, `-p fix_rr1` | `2 passed, 20 deselected in 0.11s` |
| Related suites, `-p fix_rr1` (re-run at `1385c8e7`) | `207 passed in 7.26s` |
| Whole `tests/`, `-p fix_rr1` | `3 failed, 6582 passed, 16 skipped in 113.49s`. The 3 are the `harness_threads` surface tests, which fail in this environment with or without the change (verifier §3.2). 6580 + 2 = 6582 matches the orchestrator's gate. |
| Pins, `-p fixv_builtin_open` (the sniff uses builtin `open`) | `2 passed, 20 deselected in 0.11s` |
| Pins, `-p fixv_os_open` (the sniff uses `os.open` and `os.read`) | `2 passed, 20 deselected in 0.11s` |
| Pins, `-p fixv_keep_rows` (a read error keeps the old rows, the verifier's §3.4 option) | `2 passed, 20 deselected in 0.11s` |
| Pins, `-p mutv_swallow` (a wrong fix: builtin `open`, with `OSError` swallowed into no rows) | `2 failed, 20 deselected in 0.27s` |
| Pins + R-10 warm test + INV-8.5 test, pins first; then R-10 first (HEAD and `-p fix_rr1`) | HEAD: pins FAILED, the others PASSED, in both orders. Fix: `4 passed in 0.17s` and `3 passed in 0.15s`. |
| Pins + R-10 warm test on 84e566bb (`PYTHONPATH="v84;<worktree>" --import-mode=append --rootdir <worktree>`) | `1 failed, 2 passed, 19 deselected in 1.73s`. Both pins pass. R-10 fails by design ("opened 13 workspace files"), which proves the old tree was loaded. |
| Verifier's real share-lock pin (`s5-rrverify/test_rr1_pin.py -k share_mode`), HEAD / `-p fix_rr1` | `1 failed, 4 deselected in 16.34s` / `1 passed, 4 deselected in 15.00s` |
| `PYTHONIOENCODING=utf-8 python lint/run.py`, files staged | `SDK-LINT: PASS`; `git diff --cached -- lint/` is empty. |

The red reason at HEAD is the same in both tests. Both preconditions pass, so exactly one open failed and the failing call returned SUCCESS. Then the `next` search fails with `AssertionError: next search after one failed read: '0 of 0 matching entries and note lines shown.'`. In the entries test, even the untouched entry #1 is gone (`assert ([] == ['#1 fact: Al...`).

## What a repair must keep for these tests to pass

- A changed file whose open raises `OSError` during the refresh must not get its new fingerprint stored with no rows. Two outcomes pass:
  - the error reaches `_lookup`'s `except (OSError, UnicodeError): continue`, as `fix_rr1` and the review's V4 do;
  - the old rows are kept.
- The failing call itself must return SUCCESS. Its hits are not asserted.
- The pins do not care which API opens the file, or how many times. Only the first open of the target fails.
- Keep the R-10 property too: sniff only inside the row helpers. The R-10 test still counts opens on warm searches.

## Tests deliberately not written

- **A committed Windows share-mode-0 lock test.** It is not portable, and it would add ctypes literals. The verifier's scratch version was run as a cross-check instead.
- **What the failing call returns for the changed file.** Row 20 says only "skipped for that call". Keeping the old rows is the owner's open question (verifier §3.4).
- **R-26, R-27, R-28.** Out of scope by the orchestrator's ruling.

## Scratch files (never committed)

- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-pin-r25/make_variants.py` builds `fixv_os_open.py`, `fixv_keep_rows.py`, and `mutv_swallow.py` from `s5-rrverify/fix_rr1.py`, in the same folder.
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-pin-r25/fixv_builtin_open.py` is `fix_rr1.py` with `path.open("rb")` replaced by `open(path, "rb")`.
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-pin-r25/lint.txt` holds the full lint output.
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-pin-r25/eol_check.py` confirmed the three files are LF on disk and in the blobs. The `LF will be replaced by CRLF` warnings are only the `core.autocrlf=true` notice.

## Commands run

All commands ran with a timeout and `</dev/null`, and git with `GIT_TERMINAL_PROMPT=0`.

- The related suites at HEAD, then the pins and the related suites at HEAD, then the same with `-p fix_rr1`. The pin runs and the full `tests` run with `-p fix_rr1` are in the table above.
- `-p fixv_builtin_open`, `-p fixv_os_open`, `-p fixv_keep_rows`, and `-p mutv_swallow` over the pins.
- Explicit node-ID order runs: pins → R-10 → INV-8.5, and R-10 → pins, each at HEAD and with `-p fix_rr1`.
- `cmp` of `v84`'s `search_memory.py`, `base.py`, and `fulltext.py` against `git show 84e566bb:<path>`, ignoring CR: all three are the same. Then the pins on `v84` from an empty runner folder.
- The verifier's `test_rr1_pin.py -k share_mode` at HEAD and with `-p fix_rr1`.
- `git add` of the three files, then `PYTHONIOENCODING=utf-8 python lint/run.py`, then `git commit -F`.
