LENS: conformance (post-repair re-review)
VERDICT: MERGEABLE AFTER FIXES — every repair holds against its evidence, but the R-7 refresh rewrite caches a transient read failure as "no rows" under the new fingerprint, so a changed note (or the whole `entries.jsonl`) stays out of search until it changes again, against INV-8.4.

Reviewed: commit 72d1ca7f (HEAD 714bd651 differs only in `pipeline.md`); fix range 84e566bb..72d1ca7f; merge 16e39b73; test pack fd6dab0b. Probe scripts are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s5-rereview/` (`SW` below; the S4 verifier and engineer probes reused here sit beside it in `s4-verify/` and `s4-eng/`). Exports: `SW/main` = origin/main 6f5a7310, `SW/v84` = 84e566bb.

WHAT THE IMPLEMENTATION GETS RIGHT

- R-3 masking is correct on every wire shape. Unread batches of 3, 4, 5 or 8 scoped outputs after the newest `assistant`/`model` turn stay whole on OpenAI (one message per result), Anthropic, Gemini (separate and single-message), and the parallel Gemini shape. After the next model turn, the outputs past `keep_recent` are masked. `bash`, `launch_subagent` and `remember` are never masked, and the input list is never mutated.
- INV-2.1 holds: the unscoped window equals main byte for byte over 9,000 random histories (3,000 × 3 modes), with digest `30fd8a41…` identical on `SW/main` and the worktree.
- The Anthropic first send is byte-equal to main even with lone surrogates in `system`, `tools` and the messages. Marks start on the repeat (3 marks). Caller-held `cache_control` gets 0 adapter marks and records 0 digests, and the caller's history is never mutated. Do not move the gate back inside `_attach_cache_breakpoints` to match the spec text; R-RR3 updates the spec instead.
- The new `_listing` walk is faster and safer than the `iter_files` walk it replaced. It indexes the same rows on an adversarial tree (hidden files, binary and oversize files, bookkeeping names, outside links, junctions), and it survives junction and symlink loops that crash the old walk with WinError 1921. Measured on 1,900 notes plus 8,000 entries: 950 ms cold, 4 ms warm, 4 ms after one changed note, 77 ms after an entry append.

FIX CONFIRMATIONS

R-1 — HOLDS — `git show 848469a2` changes the leaf to end "and any limit on the answer."; `grep -n "such as"` over the new leaves → no hits; the only digits are the existing list numbering (INV-0.3).
R-2 — HOLDS — `python -I s4-verify/run_fuzz.py W scripts/fuzz_search.py SW/fuzzroot`: every query is `success`; `'a\x00b'` → `1 of 1`, `'\ud800x'` → `0 of 0`. `python -I s4-verify/probe_poison.py W`: steps 2-10 all `success` (1 entry row kept; a surrogate-named file is left out, `kappa → 0 of 0`, while `alpha` still matches). FR-8.6: `'\x00'`, `'\ud800'`, `'\ud800\x00'` → `success 0 of 0`; `' '`, `'\t\n'`, `''`, None, 5 → `invalid_argument`. `python -I s4-verify/probe_recall_presearch.py W`: the retriever starts for both poisoned terms.
R-3 — HOLDS — `python SW/probe_mask_wires.py W`: `openai single=False batch=5: unread masked=0 | after next model turn masked=2 (expect 2) | inputs same=True | pure=True | input untouched=True` (same pattern for batch 8 → 5, Anthropic and Gemini; single-message shapes → 0); `no-model-turn …: masked=0`; `sequential mix …: masked per tool={'read_lines': 3, 'grep': 3, 'search_memory': 3}`. `python s4-verify/probe_mask_root.py W` → 3/4/5/8 unread → 0 masked on both shapes; `s4-verify/probe_mask_gemini.py W` → "5 sequential → 2", "parallel 5 → 0".
R-4 — HOLDS — `python -I SW/probe_anth.py SW/main` vs `… W`: `FIRSTBODY` lines identical (`cmp` → equal); branch `call 1: marks=0`, `call 2: marks=3`, `call 3: marks=3`; `caller history untouched after 3 calls: True`.
R-5 — HOLDS — `python -I SW/rewrap_check.py W 1a6365e6` → `files: 16 problems: 0` (code lines identical, comment word sequences identical, `@intent` lines unchanged). The awk check over the PR diff finds only 6 comment lines over 72 columns, all in `windows.py` (38, 51, 83, 128, 145, 179), each copied verbatim from main's `strategies.py`.
R-6 — HOLDS — `probe_anth.py`: `held call 1: adapter marks=0`, `held call 2: adapter marks=0`, `digests recorded while caller held marks: 0`, `plain request after held ones: marks= 0`; `python -I s4-verify/probe_anth_surrogate.py W` → calls 1 and 2 built and serialized (`surrogatepass` digest).
R-7 — HOLDS (perf) with regression R-RR1 — `PYTHONPATH=W python s4-eng/probe_scale.py 1900 8000` → cold build about 950 ms, warm 4 / 4 / 4 ms, one changed note 4 ms, entry append 77 ms (S4 measured 490 ms warm on the old walk); `walk_rows.py dump` on `SW/v84` vs `W` → identical row sets (old walk needed the loop junction removed to finish at all).
R-12 — HOLDS — `vidbyte/providers/README.md:615` reads "(see Anthropic Prompt-Cache Marks above)"; `grep -n "^#.*Prompt-Cache Marks"` → `532:## Anthropic Prompt-Cache Marks`.
R-13 — HOLDS — import probe with a cold pycache (`-X pycache_prefix=SW/pyc_cold`): `import vidbyte` succeeds, `vidbyte.lib.util.FullTextIndex.__module__` → `vidbyte.lib.util.fulltext`; `vidbyte.lib.util.Bogus` → `AttributeError`; lint C003 → `CLEAN`.
R-14 — HOLDS — `runtime.py`: `current = await asyncio.to_thread(self.workspace.map_snapshot)`; no pairs run while the root's hook runs, so moving the snapshot to a thread races with nothing.
R-15 — HOLDS — the headers of `memory.py` and `toolsets/infinite.py` now name `search_memory` and the recall modes; lint reports 0 REGRESSED.
R-16 — HOLDS — `llms.txt:519` ("`vidbyte.tools.builtins.code_search`: `GlobTool`, `GrepTool`, `SemanticSearchTool`, `InfiniteSearchMemoryTool`."), `:815` and `artifacts/file_index.md:422-424` now name `InfiniteSearchMemoryTool`; the contract check reports "current at 5ccc4926… (645 exports)".
R-19 — HOLDS — `recall.py`: the `hits` and `task` builds sit inside the `try` that catches `(VidbyteSdkError, OSError, ValueError)`. A poisoned query now returns the notice instead of raising. `memory.recalled += 1` still runs before them with no `await` between the check and the increment (EC-10.3 race closed).
R-8..R-11, R-24 (test pack fd6dab0b) — HOLDS — the selected pins on the 84e566bb source (`PYTHONPATH="SW/v84;W" --import-mode=append`, cwd `SW/runner`) → `10 failed, 1 passed, 88 deselected` (the pass is the rowid test, green by design per S5-test-pack); the same selection on the worktree → `11 passed`.
Merge 16e39b73 — HOLDS — `git diff 6f5a7310 72d1ca7f -- <files main changed>` is empty except the two intended unions: `toolsets/__init__.py` keeps both `CodexHostTools` and the `search_memory` wording, and `lib/enums/__init__.py` adds only `InfiniteRecallMode`. No branch-only file differs from a7f53b09.

FINDINGS

R-RR1 [Major] [conformance/regression] vidbyte/tools/builtins/code_search/search_memory.py:200,225 — A changed file that cannot be read for one moment is indexed as empty until it changes again
  Evidence: `search_memory.py:125-126`
    `rows = None if index.fingerprint(source) == stamp else read_rows(source, Path(path))`
    `except (OSError, UnicodeError):`
  `:200` (`_entry_rows`) and `:225` (`_note_rows`): `if not self.is_text_file(path): return []`. `base.py:113-118`: `is_text_file` wraps `path.stat()` and `path.read_bytes()` in `except OSError: return False`. So a read error never reaches `_lookup`'s `except`; `index.replace(source, stamp, [])` stores the new stamp with no rows, and every later call sees `fingerprint == stamp` and skips the file.
  `python -I SW/probe_transient.py W` (real Windows sharing violation via `CreateFileW(..., share=0)`):
    84e566bb: `A2 note changed, held exclusively, beta -> 0 of 0`; `A3 lock released … beta -> 1 of 1`; `A5 entries … xi -> 0`; `A6 lock released, xi -> 1 of 1`
    72d1ca7f: `A2 … -> 0 of 0`; `A3 lock released … -> 0 of 0`; `A4 again … -> 0 of 0`; `A5 … -> 0`; `A6 lock released, xi -> 0 of 0`
  Failure: the agent's `bash` rewrites `notes/plan.md` (or `remember` appends to `entries.jsonl`) while an antivirus scanner, indexer, backup agent or the writer itself holds the file without read sharing, which is routine on Windows. The search that runs in that moment stores the new fingerprint with zero rows. Every later `search_memory` call and every recall pre-search returns nothing from that file until it is modified again. For `entries.jsonl`, that hides every remembered entry, which breaks G-2. It also breaks INV-8.4 ("a search always reflects the disk at call time") and the S3 deviation for row 20, which promises that "a file that raises `OSError` mid-refresh is skipped for that call". At 84e566bb the file was re-read on the next call.
  Smallest fix: in `_entry_rows` and `_note_rows`, replace the `is_text_file` gate with a sniff that lets `OSError` propagate. The byte cap is already known from the listed `st_size`, and the sniff is `with path.open("rb") as handle: if b"\x00" in handle.read(2048): return []`. `_lookup` then `continue`s, the source is not added to `kept`, `retain` drops it, and the next call re-reads it. Add one test that patches `Path.open` to raise `PermissionError` once for a changed note and asserts the second search finds the new text. The test pack has none, so this is the uncovered path.
  Spec IDs: INV-8.4, G-2, FR-8.x (row 20), S3 deviation "Row 20".

R-RR2 [Minor] [conformance/pre-existing] vidbyte/tools/builtins/code_search/search_memory.py:167-180 — An in-root link to a bookkeeping file is indexed under the link's target
  Evidence: `walk_rows.py dump` on both `SW/v84` and `W` lists rows from `.runs/r1/journal.jsonl` reached through `notes/runlink.md -> .runs/r1/journal.jsonl`; `_listing` filters `child.name not in self.ignore_patterns`, checks only that the target is inside the root, and lists the file under the target's relative name.
  Failure: a `bash` call that runs `ln -s ../.runs/r1/journal.jsonl notes/j.md` puts run-journal text (the history that INV-8.5 keeps out) into search results. The old `iter_files` walk does the same, so this is not a regression of R-7.
  Smallest fix: in `_listing`, skip a linked file whose target's root-relative parts contain any name in `ignore_patterns`. [scope-adding] → follow-up.
  Spec IDs: INV-8.5.

R-RR3 [Minor] [conformance/spec-drift] docs/spec/infinite-memory-context-economy/spec.md:528,1024,1130,651-652,1125 — The spec still describes the code the repairs replaced
  Evidence: `grep -n iter_files spec.md` → `:528` "`BaseCodeSearchTool.iter_files` / `read_text_lines`", `:1024` "`…iter_files`, `read_text_lines`: file walk", row 20 (`:1130`) builds on them; `:651-652` (§8.5 sketch) and row 15 (`:1125`) put the repeat gate inside `_attach_cache_breakpoints`, while the code gates in `_create_payload` (R-4). §17 has "Implementation deviations (S3)" (`:1429`) and no S5 block.
  Failure: the next reader of row 20 or §8.5 audits code that no longer exists. A later agent could "fix" the inline `_create_payload` gate or the `_listing` walk back to the spec shape and reintroduce the junction-loop crash or the R-4 caller-held hole.
  Smallest fix: add "Implementation deviations (S5)" under §17 naming the `_listing` scandir walk (replaces `iter_files` in row 20), the `_create_payload` repeat gate (row 15, §8.5), the R-13 literal import in `lib/util.__getattr__`, and R-19 counting the attempt in the quota.
  Spec IDs: n/a (doc consistency; §17).

Deviations judged (no finding):
- R-13 literal import: `__getattr__` imports `vidbyte.lib.util.fulltext` by literal name, which satisfies C003. The `_LAZY_EXPORTS` value is read by nothing, but the comment says so and an unknown name fails loudly. Acceptable.
- R-19 quota: the attempt still counts, which matches INV-10.6 and EC-10.3. The repair report claims a refund "would put an await between check and increment"; that is wrong, because a refund in the `except` clause needs no await. No refund is required, so this is not a finding.
- `_listing`: it is a necessary deviation, since `iter_files` cannot provide stat-before-read fingerprints without a second stat and it crashes on junction loops. Its only defect is R-RR1, which sits in the row helpers, not the walk.

VERIFIED CLAIMS

- AC-1 (spec §4 snippet) — held: output matches the expected text exactly (`cmp` equal): `[lines 1-200 of 1000 shown; read on with start=201]`, `True 1000 201`, `200 True`.
- INV-2.1 — held (9,000 cases, same digest as main). INV-2.3 / AC-2.1 / AC-2.2 / AC-2.5 / EC-2.5 — held (R-3 probes above). INV-2.5 — held: no input `ContextMessage` mutated in any probe.
- FR-8.6, EC-8.8, INV-8.2 — held (R-2 probes). INV-8.5 — held for direct files; pre-existing link gap R-RR2. INV-8.8 — held: the RLock is taken across refresh and search inside `asyncio.to_thread`. NFR-8.1 — held: 4 ms warm at 1,900 notes + 8,000 entries. INV-8.4 — NOT held after a transient read error (R-RR1).
- INV-9.2, INV-9.5 — held: first body byte-equal to main; marks only on repeats; caller-held short-circuit records no digest.
- INV-10.6, EC-10.3 — held: quota checked and incremented with no await between; pre-search failures return the notice.
- INV-0.3 — held: no "such as" in new leaves; no new digits.
- §8.4 budget — held: 9 `.py` in `agents/infinite`; `strategies.py` 933, `windows.py` 197, `search_memory.py` 230, `anthropic.py` 275, `recall.py` 249 lines; 13 `BUDGET_MODULES`; budget test passes.
- §14 Never items — held: `git log --first-parent 3bda907e..72d1ca7f -- tests` lists only the merge 16e39b73 (fix commits touch no test); `git diff 84e566bb 72d1ca7f -- lint/baseline.json` is empty; no new `noqa`/`nosec`/`type: ignore` (the one "nosec" grep hit is "nanoseconds"); fix commits touch only §12.3 rows and granted doc lines.
- Call depth (AGENTS.md principle 1) — held: `depth_scan.py` on 84e566bb vs 72d1ca7f finds no new third own level; the Anthropic chains `run_text/stream_text → _create_payload → helpers` mirror main's `_attach_*`.

COMMANDS RUN (W = worktree, SW = scratch s5-rereview; all with timeout, `</dev/null`, `GIT_TERMINAL_PROMPT=0`)

- `git -C W rev-parse HEAD; git -C W diff 72d1ca7f HEAD --stat` → `714bd651…`; ` docs/spec/infinite-memory-context-economy/pipeline.md | …` (only file)
- `python SW/probe_mask_wires.py W` → 10 shape lines `unread masked=0 | after next model turn masked=<expect> | … input untouched=True`; last line `sequential mix gemini: len same=True masked per tool={'read_lines': 3, 'grep': 3, 'search_memory': 3}`
- `python -I SW/diff_window_main.py SW/main` / `… W` → `9000 30fd8a41…` (both)
- `python -I SW/probe_anth.py SW/main` / `… W` → `FIRSTBODY` equal; `call 2: marks=3`; `digests recorded while caller held marks: 0`
- `python -I SW/rewrap_check.py W 1a6365e6` → `files: 16 problems: 0`
- `python -I SW/walk_rows.py build|dump …` (v84 vs W) → identical rows; new walk adds `notes/bin.dat` as a source with no rows; loops → `success 1 of 1 ['notes/a.md']`
- `python -I SW/probe_transient.py SW/v84` → `A3 … beta -> 1 of 1`, `A6 … xi -> 1 of 1`; `… W` → `A3 … -> 0 of 0`, `A4 … -> 0 of 0`, `A6 … xi -> 0 of 0`; `B2` scandir stat = os.stat
- `PYTHONPATH=W python s4-eng/probe_scale.py 1900 8000` → cold about 950 ms, warm 4 / 4 / 4 ms, one note 4 ms, entry append 77 ms (its later breakdown section raises on the removed `_stamp` helper; irrelevant)
- `python -I s4-verify/run_fuzz.py …`, `probe_poison.py W`, `probe_recall_presearch.py W`, `probe_mask_root.py W`, `probe_mask_gemini.py W`, `probe_anth_surrogate.py W` → as quoted under FIX CONFIRMATIONS
- `python SW/ac1/snippet.py` (spec §4 snippet), output `cmp` against `SW/ac1/expected.txt` → `[lines 1-200 of 1000 shown; read on with start=201]` / `True 1000 201` / `200 True`
- `python -m pytest <related suites> -q` (cwd W) → `513 passed in 11.52s`
- `python -m pytest -k "<pack pins>" --import-mode=append --rootdir W` with `PYTHONPATH="SW/v84;W"`, cwd `SW/runner` → `10 failed, 1 passed, 88 deselected in 0.64s`; same on W → `11 passed`
- `python lint/run.py` (W) → `SDK-LINT: PASS`, `0 REGRESSED`; C003 `CLEAN`, A002 `562/703 IMPROVED`, S047 `CLEAN`, A009 `CLEAN`
- contract freshness check (W) → `current at 5ccc4926… (645 exports)`
- `python -I SW/depth_scan.py W 84e566bb 72d1ca7f` and `… W 6f5a7310 72d1ca7f` → no new depth-3 own chains
- `git -C W log --first-parent --format='%h %s' 3bda907e..72d1ca7f -- tests` → `16e39b73 Merge …` only; `git -C W diff 84e566bb 72d1ca7f -- lint/baseline.json` → (empty)
- `git -C W diff 6f5a7310 72d1ca7f -- vidbyte/toolsets/__init__.py vidbyte/lib/enums/__init__.py` → the two intended unions only
