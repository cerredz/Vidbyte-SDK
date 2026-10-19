LENS: conformance (post-repair re-review, round 2)
VERDICT: SOUND — R-25 holds against its reproducers, its pins and six new regression probes. The fix adds no Blocker or Major. Two Minors remain: one header sentence, and one INV-8.8 gap that predates this PR and goes to a follow-up.

Reviewed: code at 335dd847 (HEAD e5edd455 differs only in 4 files under `docs/spec/`), repair-2 change `git diff 72d1ca7f..335dd847 -- vidbyte` (2 files), both files read whole, plus `code_search/base.py` and `lib/util/fulltext.py` for the interaction points. W = the worktree. SP2 = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-rereview-2/`. The probes are `SP2/probe_rr2.py`, `SP2/probe_nested.py` and the plugin `SP2/plug/old72_helpers.py`. `SP2/search_memory_72d1ca7f.py` is `git show 72d1ca7f:` of the tool, used for side-by-side runs. Outputs are in `SP2/out_335.txt` and `SP2/out_72d.txt`.

WHAT THE IMPLEMENTATION GETS RIGHT

- The fix is made at the right seam and is as small as it can be. `_entry_rows` (`search_memory.py:205-207`) and `_note_rows` (`:233-235`) now sniff through `path.open("rb")`. An `OSError` from the open, the sniff or the full read therefore reaches the existing `except (OSError, UnicodeError): continue` (`:127-130`). The source stays out of `kept`, `retain` drops it, and no fingerprint is stored. A read failure and a binary file are no longer the same `False`. `code_search/base.py`, grep and glob are untouched.
- The R-10 property survives. A warm search opens nothing: Q3.0 opens 42 times for 21 files cold, and Q3.1 opens 0 times warm. Q3.2: an armed fault on the unchanged `entries.jsonl` is never triggered, because nothing opens it. P4.1: a note that is unchanged and held under a real share-mode-0 lock still gives 1 of 1. NFR-8.1 holds at 1,900 notes plus 8,000 entries: 4 ms warm and 883 ms cold. Round 1 measured about 950 ms cold. The sniff reads 2 KB where `is_text_file` read the whole file (`base.py:115`).
- The binary rule matches grep's byte for byte. A NUL at offset 0 or 2,047 gives no rows, and a NUL at offset 2,048 or 4,000 is indexed. This is `parity=True` against `is_text_file` at each offset (Q1.4). A file that turns binary keeps its stamp with no rows and is not opened again (Q1.1 `fp == disk: True`, Q1.2 `workspace opens: 0`). It is read again once it turns back to text (Q1.3, 1 of 1).
- The pins can fail. With 72d1ca7f's two row helpers put back on the worktree's class (`-p old72_helpers`), both `read_fails_once` tests fail and R-10 still passes. Against the fixed code, all of them pass.

FIX CONFIRMATIONS

R-25 — HOLDS. Evidence:
- The R-25 reproducers:
  - `probe_rr1.py`: P1.2 under the lock gives `fingerprint=None rows=0`. P1.3 gives `{'hits': 1, 'total': 1} | …:28 rows=1`. P2.1, with entries locked, gives `0 of 0` for that one call. P2.2 gives `{'hits': 10, 'total': 41} | …:8747 rows=41`. P2.4 (the recall pre-search path) gives 10 of 41. P3.2 (after EMFILE) gives 1 of 1. P4.1 gives 1 of 1.
  - `probe_transient.py`: `A3 … beta -> 1 of 1`, `A4 … -> 1 of 1`, `A6 … xi -> 1 of 1`.
- The pins: `-k read_fails_once` gives `2 passed, 20 deselected`. The same pins with 72d1ca7f's helpers give `2 failed, 1 passed, 19 deselected`.
- Side by side, 335dd847 against 72d1ca7f:
  - Q5.2 (`entries.jsonl` after one EIO at open): `2 of 2` against `0 of 0`.
  - Q7.2 (a note readable again after three denied calls): `2 of 2` against `1 of 1`. At 72d1ca7f the note stays hidden.
- What the fix keeps:
  - R-2: `-k "lone_surrogate or utf8_cannot_encode"` gives `4 passed`. `source.encode` still runs before any open (`:232`).
  - R-7/R-10: `-k warm_search` gives `1 passed`.
  - Related suites: `207 passed`.
  - Lint: `SDK-LINT: PASS`.

Regression probes the procedure asked for (all at 335dd847):

| Case | Probe | Result |
|---|---|---|
| A changed file turns binary, then text again | Q1.1–Q1.4 | Its rows are dropped and its stamp is stored. The warm search opens 0 files. It is read again as text. The 2,048-byte boundary matches grep. |
| A changed file fails, then succeeds | Pins; P1–P3; A3–A6; Q2 (the second open, the full read, fails with EIO after a clean sniff) | Left out for one call with `fp: None`. Found on the next call (`1 of 1`, `fp == disk: True`). |
| An unchanged file under a lock | P4.1 (real lock); Q3.2 (armed audit hook) | 1 of 1. No open is attempted. |
| A note grows past the byte cap during the refresh | Q4 (cap 1,000; the note grows to 8,015 B between the listing and the read) | Call 1 indexes it once under its old stamp (`10 of 400`, `fp …:15`). Call 2 leaves it out (`0 of 0`, `fp: None`). At 72d1ca7f, call 1 gave `0 of 0`. This is the declared change; 84e566bb had the same window (it called `iter_files` sniff, then `_stamp`, then read with no size check). See R-RR2-1. |
| `entries.jsonl` fails with an OSError that is not about permission | Q5.1 (EIO at open); Q5.3 (EIO from the full `read_text` after a clean sniff); Q5.5 (the file is replaced by a folder after the listing); pin (EMFILE) | Each call returns SUCCESS with that file left out. The next call finds `2 of 2`, `3 of 3`, and `4 of 4` once the file is restored. |
| A file deleted between the listing and the open, or between the sniff and the read | Q6.1; Q6.4 | SUCCESS; the other note is still found (`1 of 1`) and `fp: None`. A recreated file is found again (Q6.3, `2 of 2`). |
| A changed file that stays unreadable (extra probe) | Q7.1 | Each call makes one failed open and returns the other notes. Once readable, the file is indexed (Q7.2, `2 of 2`, 2 opens). Before the fix it was stored as empty and never read again. |

FINDINGS

R-RR2-1 [Minor] [conformance/header-drift] vidbyte/tools/builtins/code_search/search_memory.py:9, :117-123 — The header does not list the one behavior change of this repair, and a new comment clause is wrong for one of its three subjects
  Evidence: the repair dropped `is_text_file`'s second size check (`base.py:113-114`), so the byte cap now comes only from `_listing`'s stat (`:182`, `:192`). Q4.1 at 335dd847 gives `grew to 8015 B during the refresh, iota -> SUCCESS 10 of 400 … fp stored: …:15`; at 72d1ca7f the same probe gives `0 of 0`. KNOWN EDGE CASES (`:9`) has no sentence for this window. Separately, the new `_lookup` clause (`:121-123`) reads: "A file that vanished since the listing, that cannot be read for a moment, or whose name UTF-8 cannot encode, is left out of this call; its new fingerprint is not stored, so the next call reads it again". A file whose name UTF-8 cannot encode is never read. Every call raises at `source.encode` (`:232`) and leaves it out again.
  Failure: a later agent finds that a file past the cap can be indexed for one call. Nothing in the header explains it, so the agent may restore `is_text_file` (which WHAT NOT TO DO 6 forbids) or add a second stat. The search results are unchanged either way.
  Smallest fix: add to KNOWN EDGE CASES: "A file that grows past the byte cap between the listing and the read is indexed once under its old fingerprint and left out from the next listing on, because the cap is checked only on the listing's stat." Change "reads it again" to "tries it again". The §17 S5 deviation that R-27 assigns to S6 should carry the same sentence.
  Spec IDs: INV-8.4, INV-8.5, R-27 (§17 S5 block, rows 16 and 20).

R-RR2-2 [Minor] [conformance/pre-existing] vidbyte/tools/builtins/code_search/search_memory.py:208-221 — A deeply nested JSON line in entries.jsonl fails every search, against INV-8.8
  Evidence: `_entry_rows` catches `(ValueError, KeyError, TypeError, ConfigurationError)` (`:220`). `json.loads` of a line nested 1,000 or more levels deep raises `RecursionError`, which is a `RuntimeError`. `python -I SP2/probe_nested.py W` gives: `depth 1000 RecursionError: maximum recursion depth exceeded while decoding a JSON array …` and `search raised RecursionError …`. A valid entry was in the same file, and that search did not return it. `vidbyte/tools/executor.py:70-76` turns the exception into `Tool execution failed: …`, so the run goes on.
  Failure: `bash` writes a 2 KB line of 1,000 nested brackets into `entries.jsonl`. Every `search_memory` call of every agent in the tree, and every recall pre-search, then returns an execution error until the line is removed. INV-8.8 says such a line "never fails a search". Why Minor and not Major:
  - No realistic model or `remember` path writes such a line.
  - grep and read_lines keep working, and removing the line restores search.
  - The gap is not new in this repair. It is the same except tuple since 84e566bb.
  - Main's own `workspace.py:268-271` has the same tuple and fails on the same line.
  Smallest fix: add `RecursionError` to the except tuple at `:220`. This is a follow-up, not a repair row. `workspace.py:271` belongs to main's code and to its own PR.
  Spec IDs: INV-8.8, EC-8.8.

Judged, no finding:
- The sniff block appears twice, in `:205-207` and `:233-235`. A shared helper would make the call chain three levels deep (AGENTS.md principle 1). Lifting the sniff into `_lookup` would add nesting under S024 (S3 deviation row 20). Repeating three lines is the cheapest shape the rules allow.
- `INFINITE_SEARCH_SNIFF_BYTES` copies `base.py:115`'s literal 2048 instead of sharing it. INV-8.5 fixes the value at 2,048, `base.py` cannot be changed (a decision already made), and Q1.4 shows the boundary matches.
- During a transient failure, the old rows of the failing file are also dropped for that one call. P2.1 shows all 40 entries giving `0 of 0` while `entries.jsonl` is locked. This matches the S3 deviation for row 20 ("skipped for that call") and the header. 84e566bb behaved the same way. The test-pin report also accepts the keep-old-rows option, but the spec does not require it.
- A file that stays unreadable now costs one failed open per call (Q7.1), where before it was stored as empty. This is the price of being able to recover, and it never affects unchanged readable files (Q3.1).

VERIFIED CLAIMS

- Repair report, "An OSError from either open, the sniff or the full read, reaches `_lookup`'s except": held (Q2.1, Q5.1, Q5.3, Q5.5, Q6.4).
- "R-10: a warm search opens no unchanged file": held (Q3.1 0 opens, Q3.2, P4.1, `-k warm_search` passed).
- "The binary rule: a NUL in the first 2,048 bytes gives no rows, the fingerprint is stored, not reopened": held (Q1.1, Q1.2, Q1.4).
- "R-2 / EC-8.8: `source.encode` still runs before the open": held (`:232` before `:233`; 4 R-2 tests pass).
- "The exception is not narrowed (EMFILE passes)": held (pin, P3.2, plus EIO in Q5.1 and Q5.3).
- "`code_search/base.py` unchanged": held (`git diff 72d1ca7f..335dd847 --name-only` lists only the constants file and `search_memory.py` under `vidbyte/`).
- "A file growing past the cap is indexed once, then dropped; 84e566bb had the same window": held (Q4.1 and Q4.2; 84e566bb `_lookup` listed through `iter_files`, then `_stamp`, then an unbounded `read_text`). The header does not record it (R-RR2-1).
- "The sniff reads 2 KB where is_text_file read the whole file": held (`base.py:115` `path.read_bytes()[:2048]` against `handle.read(INFINITE_SEARCH_SNIFF_BYTES)`). Cold build took 883 ms against round 1's about 950 ms.
- "Tests untouched since the pin; lint, CI config and Semgrep untouched": held (`git log --first-parent 1385c8e7..HEAD -- tests` prints nothing; `git diff 0002f0ca HEAD -- lint .github .semgrep | wc -l` gives 0).
- "Code at HEAD is 335dd847": held (`git diff 335dd847 HEAD --name-only` lists 4 files under `docs/spec/`).
- The constant: held. It is defined at `vidbyte/lib/constants/infinite.py:145`, its comment at `:140-142` names it, and it sits in sorted order in `__all__`. The public API contract is still `current at 5ccc4926… (645 exports)`. No new comment line in the diff is over 72 columns.
- INV-8.4, INV-8.5, INV-8.9, NFR-8.1 and the S3 row-20 deviation: held for the changed paths. INV-8.8: not held for a nesting-depth line that predates this PR (R-RR2-2).
- Weighted words "faster, more accurate, and saves on tokens": the fix restores accuracy (a changed file is searchable again after one failed read). Warm speed is unchanged (4 ms) and the cold build reads less.

COMMANDS RUN (all with `timeout`; git with `</dev/null` and `GIT_TERMINAL_PROMPT=0`)

- `git log --oneline -8; git diff --stat 72d1ca7f..335dd847` → HEAD `e5edd455`; the code is the 2 `vidbyte/` files, and the rest is tests and docs.
- `git diff 72d1ca7f..335dd847 -- vidbyte` → read in full. `cat -n search_memory.py` and `base.py` 1-135 → read whole.
- `PYTHONPATH=W python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_search.py -k read_fails_once -q -p no:cacheprovider` → `2 passed, 20 deselected in 0.74s`
- `… tests/features/infinite_memory_agent -k warm_search …` → `1 passed, 178 deselected in 0.79s`
- `… tests/features/infinite_memory_agent tests/test_fulltext_index.py tests/test_code_search_tools.py -k "lone_surrogate or utf8_cannot_encode" …` → `4 passed, 203 deselected in 0.90s`
- `… tests/features/infinite_memory_agent tests/test_fulltext_index.py tests/test_code_search_tools.py -q -p no:cacheprovider` → `207 passed in 7.85s`
- `PYTHONPATH="W;SP2/plug" python -m pytest …search.py -k "read_fails_once or warm_search" -p old72_helpers` → `FAILED …note_whose_read_fails_once…`, `FAILED …entries_file_whose_read_fails_once…`, `2 failed, 1 passed, 19 deselected in 0.27s`
- `python -I -X pycache_prefix=SP2/pyc s5-rrverify/probe_rr1.py W` → `P1.3 … {'hits': 1, 'total': 1} | fingerprint=…:28 rows=1`; `P2.2 … {'hits': 10, 'total': 41} | …:8747 rows=41`; `P2.4 … {'hits': 10, 'total': 41}`; `P3.2 … {'hits': 1, 'total': 1}`; `P4.1 steady unchanged but locked … {'hits': 1, 'total': 1}`
- `python -I … s5-rereview/probe_transient.py W` → `A3 … 1 of 1`, `A4 … 1 of 1`, `A6 … xi -> 1 of 1`, `B4 closed, rho -> 1 of 1`
- `python -I … SP2/probe_rr2.py W` → `LOADED …worktree…\search_memory.py`. Q1.2 gives `workspace opens: 0`. Q1.4 gives parity True at 0, 2047, 2048 and 4000. Q2.2 gives `1 of 1 | fp == disk: True`. Q3.1 gives `('SUCCESS 10 of 21 …', 0)`. Q4.1 gives `10 of 400 … fp stored: …:15`. Q4.2 gives `0 of 0 | fp: None`. Q5.2, Q5.4 and Q5.6 give `2 of 2`, `3 of 3` and `4 of 4`. Q6.1 gives `1 of 1 | fp: None`. Q7.1 gives one failed open per call. Q7.2 gives `2 of 2`.
- `python -I … SP2/probe_rr2.py W SP2/search_memory_72d1ca7f.py` → Q4.1 `0 of 0`, Q5.2 `0 of 0`, Q6.1 `fp: …:21`, Q7.1 opens `1, 0, 0`, Q7.2 `('SUCCESS 1 of 1 …', 0)`.
- `PYTHONPATH=W python … s4-eng/probe_scale.py 1900 8000` → `cold build 883 ms`, `warm 4 ms` ×3, `1 note chg 4 ms`, `entry append 74 ms`. A later section of the script raises on the removed `_stamp`; that is unrelated.
- `python -I … SP2/probe_nested.py W` → `3.11.0 recursionlimit 1000`; `depth 1000 RecursionError …`; `search raised RecursionError maximum recursion depth exceeded while decoding a JSON array …`
- `PYTHONIOENCODING=utf-8 python lint/run.py` → exit 0; `A007 … 255 255 RATCHETED`; `S024 … 25 25 RATCHETED`; `SDK-LINT: PASS`
- `PYTHONPATH=W python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 5ccc4926… (vidbyte-sdk 0.3.0, 645 exports).`
- `git log --first-parent --format='%h %s' 1385c8e7..HEAD -- tests` → (empty); `git diff 0002f0ca HEAD -- lint .github .semgrep | wc -l` → `0`; `git diff 335dd847 HEAD --name-only` → 4 files under `docs/spec/`; `git status --short` → only this report.
- `awk 'length>72'` over the added `#` lines of the diff → none.
