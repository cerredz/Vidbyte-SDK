# S5 · Repair iteration 2 — report

Status: DONE. Every gate is green apart from the 3 inherited local-only `harness_threads` surface failures, and no confirmed finding is open. Base HEAD `0002f0ca` (code `72d1ca7f` plus the R-25 test pin `1385c8e7`). Fix commit `335dd847`. Docs commit: see verify-log.md, Iteration 2.

## Defects in

- **R-25 (Major)**, the only open confirmed finding. It is a regression from iteration 1's R-7 walk (`7eb2942c`). Both row helpers in `search_memory.py` gated on `BaseCodeSearchTool.is_text_file`, which catches `OSError` and returns False. A changed file whose read failed once therefore looked binary, and `_lookup` stored its new fingerprint with no rows. The file stayed out of every search until it changed again. For `entries.jsonl` that hid every remembered entry.
- No failing gate was handed in. The pins `-k read_fails_once` were red at `0002f0ca`, and everything else was green at `72d1ca7f`.

## Root cause in one line

A read failure and a binary file took the same `False` path through `is_text_file`, so the refresh could not tell "skip this call" from "store as empty".

## The fix (`335dd847`)

| File | Change |
|---|---|
| `vidbyte/lib/constants/infinite.py` | Adds `INFINITE_SEARCH_SNIFF_BYTES = 2_048` to the existing search_memory block. The block's comment now names it ("how many leading bytes of a changed file it reads for a NUL, grep's sign of a binary file"). The constant is added to `__all__`. `2_048` follows the file's own `1_000` / `1_500` digit grouping. |
| `vidbyte/tools/builtins/code_search/search_memory.py` | Imports the constant. Both `_entry_rows` and `_note_rows` replace `if not self.is_text_file(path): return …` with `with path.open("rb") as handle:` / `if b"\x00" in handle.read(INFINITE_SEARCH_SNIFF_BYTES): return …`. The comments in `_lookup` and in both helpers now say that a file that cannot be read for a moment is left out of this call, and read again on the next. The header's KNOWN EDGE CASES gains the same sentence. WHAT NOT TO DO gains item 6: do not sniff a changed file with `is_text_file`, which reports a failed read as binary. |

What happens now:
- An `OSError` from either open, the sniff or the full read, reaches `_lookup`'s existing `except (OSError, UnicodeError): continue`.
- The source then stays out of `kept`, `retain` drops its rows, and its fingerprint is never stored.
- The next call sees a fingerprint mismatch (none stored) and reads the file again.

What the fix keeps (each was checked):
- **R-10: a warm search opens no unchanged file.** The sniff sits inside the row helpers, which `_lookup` calls only when the fingerprint changed. `test_a_warm_search_opens_no_unchanged_file_and_reads_a_changed_one_again` is green. `probe_rr1.py` P4.1, a locked but unchanged note, still gives 1/1.
- **The binary rule.** A NUL in the first 2,048 bytes still gives no rows, and that fingerprint is stored, so the file is not reopened until it changes. The committed binary-note case in `test_infinite_memory_search.py` is green. The verifier's scratch pin `test_a_changed_binary_note_is_kept_with_no_rows_and_a_warm_search_opens_nothing` passes against this tree.
- **R-2 / EC-8.8.** `source.encode("utf-8")` still runs before the open in `_note_rows`.
- **Line numbers.** They still come from `read_text_lines`.
- **The exception is not narrowed.** The entries pin raises a plain `OSError(EMFILE)`, and it passes.
- **`code_search/base.py` is unchanged**, and so are grep and glob.

One intended difference, which I checked and kept: `is_text_file` also checked the file's size again against `max_file_bytes`. The new sniff does not. `_listing` already applies the byte cap, from the same `stat` that gives the fingerprint, so the cap and the fingerprint now describe one moment.
- A file that grows past the cap between the listing and the read is indexed once under its old fingerprint.
- The next listing leaves it out, because it is over the cap, and `retain` drops it.
- The pre-R-7 code (84e566bb) had the same window between `iter_files`' sniff and the read. This is not a new failure mode.
- The sniff now reads 2 KB where `is_text_file` read the whole file and sliced it, so a changed file costs one less full read.

## Hypotheses and attempts

1. The briefing's proven fix (verifier's `fix_rr1.py` / `v4.diff`) was retyped by hand (the diff is CRLF). It held on the first attempt: pins `2 passed`, related suites `348 passed`. No other hypothesis was needed.
2. Comment wrapping: the R-5 rule is 72 columns counting the indent, greedy fill. I generated each block with `textwrap.wrap(width=72)` (scratch `s5-repair2/wrap.py`). The `_lookup` block's existing line 3 is not greedy: it stops at "A file" with room for "that". I kept lines 1–3 as they were and rewrapped only from line 4, to keep the diff to the changed sentence. Every new comment line is 72 columns or less.
3. Gate tooling slip, which was not a code problem: the pinned `s5-repair1/semgrep170/Scripts/semgrep.exe`, called by its full path, failed with `ModuleNotFoundError: No module named 'mcp.server.fastmcp' … This is mcp 2.x`. The venv holds mcp 1.23.3. The cause is that the `semgrep` launcher runs `pysemgrep` from PATH, which found the global `Python311\Scripts\pysemgrep.exe` (mcp 2.x). The fix is to put the venv's `Scripts` first on PATH (`export PATH="$(cygpath -u "$V")/Scripts:$PATH"`). After that, `semgrep --version` gives `1.170.1`.

## Independent checks (not the pins)

| Check | Result |
|---|---|
| `python -I s5-rrverify/probe_rr1.py <worktree>` (real share-mode-0 lock via `CreateFileW`, plus EMFILE) | `P1.3 lock released, search beta -> success {'hits': 1, 'total': 1} \| fingerprint=…:28 rows=1` · `P2.2 lock released, search basic -> success {'hits': 10, 'total': 41} \| fingerprint=…:8747 rows=41` · `P2.4 second tool on the same index (recall pre-search path), search basic -> success {'hits': 10, 'total': 41}` · `P3.2 next search delta -> success {'hits': 1, 'total': 1}` · `P4.1 steady unchanged but locked, search epsilon -> success {'hits': 1, 'total': 1}`. At 72d1ca7f, P1.3, P2.2, P2.4 and P3.2 were 0. |
| `python -I s5-rereview/probe_transient.py <worktree>` | `A3 lock released, nothing else changed, beta -> 1 of 1` · `A4 again, beta -> 1 of 1` · `A6 lock released, xi -> 1 of 1`. At 72d1ca7f all three were 0 of 0. |
| Verifier's 5 scratch pins `s5-rrverify/test_rr1_pin.py` (Path.open patch, audit hook, real share-mode-0 lock, binary-note keep) on this tree; `search_memory.__file__` confirmed to be the worktree's | `5 passed in 0.72s`; the share-lock case reports `PASSED`, not skipped. |

## Gate matrix

All local gates ran at `335dd847` in this worktree, in CI order.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| R-25 pins | `PYTHONPATH=<worktree> python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_search.py -k read_fails_once -q -p no:cacheprovider` | PASS (before the fix: `2 failed, 20 deselected in 0.89s`) | `2 passed, 20 deselected in 0.75s` |
| related suites | the verify-log gate-set list | PASS | `348 passed in 8.84s` |
| lint | `PYTHONIOENCODING=utf-8 python lint/run.py` (files staged) | PASS | `A007   operational-constants                     255    255 RATCHETED` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| source | `PYTHONPATH="$(cygpath -w "$(pwd)")" python scripts/run_ci.py --stage source` | lint, compileall, the context checks and the trace contracts PASS; pytest has only the 3 inherited failures | `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `…::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` · `…::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` · `=========== 3 failed, 6582 passed, 16 skipped in 112.00s (0:01:52) ============` |
| package | `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 5ccc4926362e7f46620a1e1594d28f6b2686c959 (vidbyte-sdk 0.3.0, 645 exports).` |
| Semgrep 1.170.1 | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`; `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS (exit 0, exit 0) | `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 1008 files: 0 findings.` |

The 3 source-stage failures are inherited, and they fail for the same reasons as in iteration 1: `assert 167 == 120`, `Left contains 8 more items, first extra item: 'vidbyte/tools/README.md'`, and `At index 29 diff: 'InfiniteRecallMode' != 'InfiniteWorkspaceSettings'`. They compare the checkout with `origin/main`, and they skip on CI's depth-1 checkout.

The constant did not change the contract. `vidbyte.lib.constants.infinite` is not a tracked module, so the hash and the 645 exports are the same as in iteration 1.

## Remote

I pushed `0002f0ca..335dd847` and dispatched both workflows. `gh run list` confirmed `headSha 335dd847ffc365260599903aeb387062ff675a20` for both runs.

| Run | Jobs API | Final lines |
|---|---|---|
| ci.yml 39023135090 | `Source / Python 3.11: completed/success` · `Source / Python 3.12: completed/success` · `Package: completed/success` | `6401 passed, 200 skipped in 90.83s` · `CI passed.` · `6401 passed, 200 skipped, 19 warnings in 128.71s` · `CI passed.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| static-policy.yml 39023136622 | `Static policy: completed/success` | `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 1008 files: 0 findings.` |

Remote Source rose from iteration 1's 6399 to 6401 passed, with the same 200 skipped, so both pins run on Linux too. The pins use an audit hook, not a Windows lock.

The docs commit (verify-log, review.md, this report) is pushed after these runs. It changes no code, so the runs above stand for the code at HEAD.

## Still open

- No confirmed finding is open. R-25 is `fixed @335dd847` in review.md.
- R-27 (spec drift) belongs to the S6 PR author. Its §17 "Implementation deviations (S5)" block should name R-25's own sniff and `INFINITE_SEARCH_SNIFF_BYTES` (row 16). It should also note that the byte cap now comes only from `_listing`'s stat.
- R-26 and R-28 are follow-ups. R-23 is waived. R-17, R-18, R-20, R-21 and R-22 are follow-ups.
- The 3 inherited `harness_threads` surface failures are local only. I did not edit them.
- Checks the orchestrator can run again:
  - `git log --first-parent 1385c8e7..HEAD -- tests` prints nothing.
  - `git diff 0002f0ca HEAD -- lint .github .semgrep` is empty.

## Scratch files (never committed)

- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-repair2/` holds `wrap.py`, `probe_rr1.txt`, `probe_transient.txt`, `lint1.txt`, `source.txt`, `package.txt`, `semgrep_test.txt`, `semgrep_scan.txt`, `msg-r25.txt`, and `pinrun/`.
