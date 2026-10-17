# S5 re-review findings verifier, round 1

Stage: S5, post-repair re-review round 1. Input: `reports/S5-rereview.md` (R-RR1 Major, R-RR2 and R-RR3 Minor).
Code under review: `72d1ca7f`. HEAD at the time of this run: `c3e6f817`, which is 72d1ca7f plus docs only (`git diff --stat 72d1ca7f HEAD` touches only `pipeline.md` and `reports/S5-rereview.md`).
Scratchpad root (`SP` below): `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad`. My probes are in `SP/s5-rrverify/`. `W` is the worktree. `v84` is `SP/s5-rereview/v84`; I checked that its `search_memory.py`, `base.py`, and `fulltext.py` equal `git show 84e566bb:<path>` byte for byte, apart from CRLF.

Verdict of the appended review.md section: **MERGEABLE AFTER FIXES**, with 1 confirmed Major (R-25), 0 refuted, and 3 Minors (R-26, R-27, R-28).

## 1. Mapping from re-review IDs to review IDs

| Re-review ID | Review ID | Classification |
|---|---|---|
| R-RR1 | R-25 | CONFIRMED Major. The re-review's smallest fix is corrected: its literal `handle.read(2048)` fails lint A007. |
| R-RR2 | R-26 | Minor, pre-existing, follow-up `[scope-adding]` |
| R-RR3 | R-27 | Minor, trivial, owner S6 PR author (§17 S5 deviation block) |
| (new) | R-28 | [verifier] Minor, follow-up: on Windows the NTFS directory entry lags while a writer holds a note open |

## 2. R-RR1 verification (now R-25)

### 2.1 Mechanism, read from the code

- `search_memory.py:125` reads `rows = None if index.fingerprint(source) == stamp else read_rows(source, Path(path))`, and `:126-127` reads `except (OSError, UnicodeError): continue`. `stamp` comes from the listing (`:180`, `:190`).
- `_entry_rows` (`:200-201`) and `_note_rows` (`:225-226`) both begin with `if not self.is_text_file(path): return …`.
- `base.py:110-118` `is_text_file` wraps both `path.stat()` and `path.read_bytes()[:2048]` in `except OSError: return False`.
- So a read error becomes a binary verdict, and the helper returns `[]`. `_lookup` then calls `index.replace(source, stamp, [])`, which stores the new fingerprint with no rows (`fulltext.py:59-74`), and keeps the source. Every later call sees `fingerprint == stamp` and never reads the file again until its size or mtime changes.
- `git show 7eb2942c -- vidbyte/tools/builtins/code_search/search_memory.py` adds both gates (the `+        if not self.is_text_file(path):` hunks). At 84e566bb, `iter_files` sniffed every file through `is_text_file`, so a file that failed the sniff was never listed, `retain` dropped it, and the next call read it again.

### 2.2 Probes on both commits

The reviewer's probe, run as `python -I -X pycache_prefix=… SP/s5-rereview/probe_transient.py <side>` with `TMP` inside `s5-rrverify/tmp`:

```
=== branch 72d1ca7f (worktree) ===
A2 note changed, held exclusively, beta -> 0 of 0 matching entries and note lines shown.
A3 lock released, nothing else changed, beta -> 0 of 0 matching entries and note lines shown.
A4 again, beta -> 0 of 0 matching entries and note lines shown.
A5 entries changed, held exclusively, xi -> 0 of 0 matching entries and note lines shown.
A6 lock released, xi -> 0 of 0 matching entries and note lines shown.
=== 84e566bb (v84) ===
A2 note changed, held exclusively, beta -> 0 of 0 matching entries and note lines shown.
A3 lock released, nothing else changed, beta -> 1 of 1 matching entries and note lines shown.
A4 again, beta -> 1 of 1 matching entries and note lines shown.
A5 entries changed, held exclusively, xi -> 0 of 0 matching entries and note lines shown.
A6 lock released, xi -> 1 of 1 matching entries and note lines shown.
```

My own probe, `SP/s5-rrverify/probe_rr1.py`, works differently from the reviewer's:

- It builds a real `InfiniteWorkspace` and gets the tool from `InfiniteMemoryAgentTools.get_tools(…, workspace.full_text)`, as agents and recall do.
- It reads the index's stored fingerprint and its row count per source.
- It adds a second tool on the same index, which is the recall pre-search path.
- It adds a non-lock seam: `Path.open` raises `EMFILE` once.

```
72d1ca7f
P1.1 under lock: stat ok -> 1792228515482600100:28 | is_text_file -> False | read_bytes -> PermissionError winerror=None
P1.2 search beta under lock -> success {'hits': 0, 'total': 0} | fingerprint=1792228515482600100:28 rows=0 | disk stamp 1792228515482600100:28
P1.3 lock released, search beta -> success {'hits': 0, 'total': 0} | fingerprint=1792228515482600100:28 rows=0
P2.0 40 entries, search basic -> success {'hits': 10, 'total': 40}
P2.1 entry 41 appended, entries.jsonl locked, search basic -> success {'hits': 0, 'total': 0}
P2.2 lock released, search basic -> success {'hits': 0, 'total': 0} | fingerprint=1792228515490139500:8747 rows=0
P2.3 search vendor7 -> success {'hits': 0, 'total': 0}
P2.4 second tool on the same index (recall pre-search path), search basic -> success {'hits': 0, 'total': 0}
P2.5 entry 42 appended (file changed again), search basic -> success {'hits': 10, 'total': 42}
P3.1 memo changed, one EMFILE, search delta -> success {'hits': 0, 'total': 0} | fired 1
P3.2 next search delta -> success {'hits': 0, 'total': 0} | fingerprint=1792228515499394600:26 rows=0
84e566bb
P1.2 search beta under lock -> success {'hits': 0, 'total': 0} | fingerprint=None rows=0 | disk stamp …:28
P1.3 lock released, search beta -> success {'hits': 1, 'total': 1} | fingerprint=…:28 rows=1
P2.2 lock released, search basic -> success {'hits': 10, 'total': 41} | fingerprint=…:8747 rows=41
P2.4 second tool on the same index (recall pre-search path), search basic -> success {'hits': 10, 'total': 41}
P3.2 next search delta -> success {'hits': 1, 'total': 1} | fingerprint=…:26 rows=1
```

A contrast run (P4, a fresh note indexed cleanly, then locked while unchanged) shows the branch is better than 84e566bb for unchanged files: branch `P4.1 … {'hits': 1, 'total': 1}`, 84e566bb `P4.1 … {'hits': 0, 'total': 0}`.

### 2.3 The four questions

1. **Regression or pre-existing?** It is a regression introduced by `7eb2942c` (the R-7 fix). 84e566bb read the file again on the next call (A3, A6, P1.3, P2.2, P3.2 above).
2. **Does it break INV-8.4 as written?** Yes. INV-8.4 says the tool "re-reads files that changed … so a search always reflects the disk at call time". After the lock is released, nothing transient remains, but P1.3, P1.4, P2.2, P2.3, P2.4, and P3.2 all return a state that is not the disk's, and they keep doing so. No lock can be satisfied during the locked call itself, which is what the S3 deviation carves out. The permanence is the breach.
3. **Does it break the S3 deviation for row 20 ("a file that raises `OSError` mid-refresh is skipped for that call")?** Yes, in both halves. The `OSError` never reaches `_lookup`, because `is_text_file` catches it. And the file is not skipped: it is stored as empty under the new fingerprint, and then it is skipped on every later call, not only that call.
4. **What is the user impact?** It is silent: each search returns `success` with "0 of 0", and no notice. The index is one per `InfiniteWorkspace` (`workspace.py:75`), built once per `InfiniteMemoryAgent` (`agent.py:64`) and shared by the root, generators, verifiers, and the retriever (`recall.py:113`). So one bad moment hides the file from the whole tree, and from every recall pre-search, for the life of the agent object or until the file changes again. For `entries.jsonl`, every remembered entry disappears (P2: 41 of 41) until the next `remember`. For a note written once and never touched again, the loss lasts for the agent object's whole life. The common triggers are on Windows: a scanner, indexer, sync client, or backup agent that opens a just-written file without read sharing, which happens most often right after a write, exactly when the file's fingerprint has changed. Any `OSError` on any platform, such as `EMFILE` under load, has the same effect (P3). The workspace's own writes are not a trigger: `LocalFileSystemBackend.write_text(atomic=True)` writes a temporary file and calls `os.replace` (`vidbyte/lib/tools/filesystem/backends/local.py:41-45`), which never holds the target without sharing. Nothing on disk is lost.

Severity stays **Major**. It is not a Blocker, because the trigger is a transient external condition that must coincide with the read of a changed file, and the file heals itself on its next change. It is not a Minor, because the miss is silent and unbounded in time, and it can hide every remembered entry. That defeats the request's "faster, more accurate" lookups (G-2).

## 3. Fix proof

### 3.1 The re-review's fix works, but its literal fails lint

I exported 72d1ca7f with `git archive` to `SP/s5-rrverify/tree`. I made it a throwaway git repo there (`git init`, one commit), because `lint/run.py` enumerates files with `git ls-files`. This touched only the scratch folder, never the worktree's repository. The clean export reproduces the gate: `SDK-LINT: PASS`, A007 255/255. Four variants of `search_memory.py` (generator `make_variants.py` and `make_v4.py`):

| Variant | Shape | Full `python lint/run.py` |
|---|---|---|
| V1 (re-review's literal) | `with path.open("rb") as handle: if b"\x00" in handle.read(2048): return …` | `A007 operational-constants 257 255 REGRESSED` / `A007 REGRESSED: 257 finding(s), allowance 255.` / `SDK-LINT: FAIL` |
| V2 (base.py style) | `if b"\x00" in path.read_bytes()[:2048]: return …` | `A007 … 257 255 REGRESSED` / `SDK-LINT: FAIL` |
| V3 | V1 with a module constant `SNIFF_BYTES = 2048` in `search_memory.py` | `A007 … 255 255 RATCHETED` / `SDK-LINT: PASS` |
| V4 (recommended) | V1 with `INFINITE_SEARCH_SNIFF_BYTES = 2048` in `vidbyte/lib/constants/infinite.py` (commented, in `__all__`), imported by `search_memory.py` | `A007 … 255 255 RATCHETED` / `S024 … 25 25 RATCHETED` / `SDK-LINT: PASS` |

A007 counts every numeric literal passed to a `read`/`read_bytes` call (`lint/rules/a007_operational_constants.py`, `OPERATIONAL_CALLS`), and its count is ratcheted at 255. V4 follows the tool header's rule that bounds stay in `vidbyte/lib/constants/infinite.py` (row 16's file). The constant is not in any public-API contract (`INFINITE_SEARCH_MAX_HITS` appears in no contract file), and C016 stays clean. The V4 patch is in `SP/s5-rrverify/v4.diff`; its files are CRLF, so re-type the patch rather than `git apply` it. V3 also passes lint if the repair wants a one-file change.

Final lines of the V4 lint run (`SP/s5-rrverify/lint_v4.txt`):
```
S062 RATCHETED: 889 known finding(s). Inspect with: python lint/run.py --rule S062 --all
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all
SDK-LINT: PASS
```

### 3.2 Behaviour proof

- Plugin `SP/s5-rrverify/fix_rr1.py` copies both helpers line for line and changes only the gate. It leaves the byte cap to `_listing`, which takes it from the same stat that gives the fingerprint.
- Scratch pins `SP/s5-rrverify/test_rr1_pin.py`:
  - a changed note, `Path.open` raising `PermissionError` once;
  - `entries.jsonl`, `Path.open` raising `OSError(EMFILE)` once;
  - an audit hook that aborts any open once;
  - a real Windows share-mode-0 lock;
  - a guard: a changed binary note is kept with no rows, and a warm search opens nothing.

| Run | Result (last line) |
|---|---|
| pins on 72d1ca7f, no fix | `4 failed, 1 passed in 19.06s` (the binary guard passes) |
| pins on 72d1ca7f + `-p fix_rr1` | `5 passed in 15.02s` |
| pins on 84e566bb (`PYTHONPATH="v84;W" --import-mode=append`, cwd `s5-rereview/runner`) | `1 failed, 4 passed in 17.28s` (the warm-search guard fails there by design, because the old walk read every file) |
| `tests/features/infinite_memory_agent tests/test_fulltext_index.py tests/test_code_search_tools.py`, no fix | `205 passed in 9.30s` |
| the same + `-p fix_rr1` | `205 passed in 8.12s` |
| R-10 warm test, INV-8.5 binary test, R-2 surrogate entry and name tests, INV-8.8, edit/delete refresh, and the 5 pins, one process, `-p fix_rr1` | `11 passed in 16.21s` |
| V4 source in the scratch tree: the 3 suites + the 5 pins | `210 passed in 10.31s` |
| V4 source in the scratch tree: the full `tests` | `6582 passed, 17 skipped in 123.61s (0:02:03)` |

The full-suite total (6,599) equals the orchestrator's gate at 72d1ca7f (6580 passed, 3 failed, 16 skipped). The 3 inherited harness_threads failures pass in the clean export, so they depend on the environment, not on this change.

Both probes with the fix loaded (`SP/s5-rrverify/run_with_fix.py <W> <probe>`):
- `probe_transient.py`: `A3 … 1 of 1`, `A4 … 1 of 1`, `A6 … 1 of 1`.
- `probe_rr1.py`: `P1.3 … 1/1 rows=1`, `P2.2 … total 41 rows=41`, `P2.4 … 41`, `P3.2 … 1/1`, and `P4.1 … 1/1`, so the warm-path advantage is kept.

### 3.3 What the fix must not break (all verified green with it)

- **R-10 warm-search contract** (`test_a_warm_search_opens_no_unchanged_file_and_reads_a_changed_one_again`): the sniff stays inside the row helpers, which run only for a changed fingerprint. A changed file is opened twice (sniff, then read), the same count as today's `is_text_file` plus `read_text`. The test compares sets.
- **R-2's per-line skips and EC-8.8**: the per-line `try` in `_entry_rows` is unchanged, and `source.encode("utf-8")` stays before the open in `_note_rows`.
- **Binary handling that `_listing` relies on**: a NUL in the first 2,048 bytes still returns `[]`, so the file is stored with no rows and is not opened again until it changes (pin 5).
- **A vanished file**: `FileNotFoundError` now reaches `continue`, so the file is left out of the call, which matches the header's KNOWN EDGE CASES.
- **A side benefit**: today's `is_text_file` reads the whole file to sniff 2 KB, and the fix reads 2 KB.

### 3.4 Smaller or safer alternatives considered

- **Overriding `is_text_file` in the subclass so it raises.** This is the same size, but the helpers would then call an own method at depth 3 (AGENTS.md principle 1), and it would invert a base-class contract. Rejected.
- **Decoding one `read_bytes()` for both the sniff and the rows.** This saves an open, but `read_text_lines` reads in text mode with universal newlines, so line numbers would differ from grep and `read_lines` for files with lone `\r`. Rejected.
- **Optional, not built (no scope additions): keep the old rows on a read error** instead of dropping them for that call. A lock would then never empty the entries for that call. This goes beyond the S3 deviation's "skipped for that call" and changes the vanished-file edge case, so it is a Q for the owner, not part of the fix.

### 3.5 Regression test (required; for the test author)

- **Spec IDs:** INV-8.4, plus the S3 deviation for row 20 (and G-2 for the entries case).
- **File:** `tests/features/infinite_memory_agent/test_infinite_memory_search.py`.
- **Seam:** `Path.open` raising `PermissionError` once for one changed note's path, or a raising `sys.addaudithook` on the `"open"` event for that path, which works whatever open API the repair uses. Both are proven red on 72d1ca7f and green with the fix.
- **Asserts:** the second search returns the new line, and the same case for `entries.jsonl` finds every entry.
- **Rules:** the rewrite must change the file size (the pack's WHAT NOT TO DO 3, EC-8.5). Do not rely on timing. A Windows share-lock case may be added, but it cannot be the only pin, because Linux CI would skip it.

## 4. Minor calibration

### R-RR2 → R-26 (Minor, follow-up, `[scope-adding]`)

My own probe, `SP/s5-rrverify/probe_rr2_link.py`, creates the link `notes/runlink.md -> .runs/r1.jsonl`. It gives the same output on both sides:
`journalword -> .runs/r1.jsonl:1: {"event": "run_started", "task": "Journalword task"} | 1 of 1 matching entries and note lines shown.`

- **Pre-existing:** the output is identical on 84e566bb.
- **The same path catches other bookkeeping files:** a link to `superseded.jsonl` or `files.jsonl` takes the same route. A link to `entries.jsonl` does not: `_listing` overwrites that key with the entries reader at `:190`.
- **Low reach:** it needs the agent's own `bash` to create the link, and grep behaves the same way.
- **Why it is a follow-up:** a fix would make `search_memory`'s ignore rules depart from grep's, which is a design change.

### R-RR3 → R-27 (Minor, trivial, owner S6 PR author)

Confirmed by reading:
- `spec.md:528` and `:1024` name `iter_files`, and row 20 (`:1130`) builds on them.
- The §8.5 sketch (`:645-652`) and row 15 (`:1125`) put the conditions inside `_attach_cache_breakpoints`. The code gates in `_create_payload` (`anthropic.py:83-84`: `if not self._holds_cache_control(payload) and self._is_repeat(payload): self._attach_cache_breakpoints(payload, config)`).
- §17 has only "Implementation deviations (S3)" (`:1429`).

The established mechanism is a deviation list in §17, which S3 already used, and S6 already finalizes the frontmatter, §5, and §17. So R-27 fits S6's remit as an "Implementation deviations (S5)" block, without editing rows 15 and 20 or §8.5. The block should name:
- the `_listing` scandir walk (row 20);
- the `_create_payload` gate (row 15, §8.5);
- the R-13 literal import;
- R-19's counted attempt;
- R-25's sniff and its constant (row 16);
- R-28 as a known blind spot, unless it gets fixed.

It is not a repair row.

## 5. Blind spots next to the repaired code ([verifier])

- **No other `is_text_file` swallow on a cached path.** `grep -rn is_text_file vidbyte` finds `base.py:106` (grep and glob's per-call walk, which caches nothing) and `search_memory.py:200` and `:225` (R-25) only.
- **`retain` dropping a source after a transient error is one call only.** `SP/s5-rrverify/probe_listing_errors.py`, branch and branch+fix: `S1 notes/ unlistable once: beta 0` → `S2 next call: beta 1`; `S3 entries stat fails once: xi 0` → `S4 next call: xi 1`. `_listing`'s own swallows (`:162`, `:168`, `:187`) are correct.
- **The fingerprint is taken before the read.** `stamp` comes from the listing (`:180`, `:190`), and the read follows at `:125`. INV-8.4's order holds.
- **R-28, new and Windows-only.** `DirEntry.stat()` (`:167`) returns the NTFS directory entry, which lags while another handle holds the file open for writing.
  - `probe_dirent_lag.py`: `L1 open writer, flushed, no fsync: os.stat size=13 | scandir size=0 | same=False`.
  - `probe_dirent_lag2.py`, with no `os.stat` between steps: the branch gives `D4 third line flushed, search sigma -> {'hits': 0, 'total': 0}` and `D5 writer closed, search sigma -> {'hits': 1, …}`. 84e566bb gives `D4 … {'hits': 1, …}`. Two runs per side are identical.
  - It is a regression of R-7, because the old `_stamp` used `os.stat`. But it is bounded by the writer's handle lifetime, it heals on close, and grep still sees the text. Minor, follow-up.
  - Cost of the alternative (`bench_stat.py`): `scandir: best of 5 = 1.9 ms`, `os.stat: best of 5 = 30.6 ms` for 1,900 files. That fits NFR-8.1's 50 ms but takes most of it, so the owner decides.
- **No interaction with R-20.** The R-25 fix returns before `replace`. A failed insert inside `replace` leaves the old fingerprint (`fulltext.py:72-74` run only after the insert), so the next call reads the file again.
- **Nothing Blocker-class** sits next to R-25.

## 6. Commands run

All commands ran with a timeout and `</dev/null`, git commands with `GIT_TERMINAL_PROMPT=0`. Probe temp data went to `SP/s5-rrverify/tmp` (`TMP`/`TEMP`), and bytecode to `SP/s5-rrverify/pyc` (`-X pycache_prefix`).

- `git rev-parse HEAD` → `c3e6f817…`; `git diff --stat 72d1ca7f HEAD` → `pipeline.md`, `reports/S5-rereview.md` only.
- `git diff 84e566bb 72d1ca7f -- vidbyte/tools/builtins/code_search/search_memory.py`; `git diff 84e566bb 72d1ca7f -- vidbyte/lib/util/fulltext.py`, whose non-comment changed lines are none.
- `git show 7eb2942c -- …search_memory.py | grep is_text_file` → `+        if not self.is_text_file(path):` (two hunks); `git log 84e566bb..72d1ca7f -- …search_memory.py` → `1a6365e6`, `7eb2942c`, `0e41b3a2`.
- `python -I SP/s5-rereview/probe_transient.py W` and `… v84` (§2.2).
- `python -I SP/s5-rrverify/probe_rr1.py W` and `… v84` (§2.2, P4 rerun).
- `PYTHONPATH="W;SP/s5-rrverify" python -m pytest SP/s5-rrverify/test_rr1_pin.py -q -p no:cacheprovider [-p fix_rr1] --rootdir W` (§3.2).
- `PYTHONPATH="W;SP/s5-rrverify" python -m pytest tests/features/infinite_memory_agent tests/test_fulltext_index.py tests/test_code_search_tools.py -q -p no:cacheprovider [-p fix_rr1]`, cwd W (§3.2).
- `PYTHONPATH="v84;W" python -m pytest SP/s5-rrverify/test_rr1_pin.py -v --import-mode=append --rootdir W`, cwd `SP/s5-rereview/runner` (§3.2).
- `python -I SP/s5-rrverify/run_with_fix.py W <probe>` for `probe_transient.py`, `probe_rr1.py`, and `probe_listing_errors.py`.
- `git archive 72d1ca7f | tar -x -C SP/s5-rrverify/tree`; in the scratch tree only: `git init`, `git add -A`, `git commit`; then `python lint/run.py` for clean, V1, V2, V3, and V4 (§3.1).
- In the scratch tree with V4: `python -m pytest <3 suites> SP/s5-rrverify/test_rr1_pin.py -q` → `210 passed`; `python -m pytest tests -q --maxfail=50` → `6582 passed, 17 skipped`.
- `python -I SP/s5-rrverify/probe_rr2_link.py W` and `… v84` (§4).
- `python -I SP/s5-rrverify/probe_dirent_lag.py W` (twice); `python -I SP/s5-rrverify/probe_dirent_lag2.py W` and `… v84` (twice each); `python -I SP/s5-rrverify/bench_stat.py` (§5).
- `grep -rn is_text_file vidbyte`; reads of `anthropic.py:76-90`, `local.py:25-58`, `workspace.py`, `agent.py:55-70`, and `recall.py:113` (§2.3, §4, §5).
