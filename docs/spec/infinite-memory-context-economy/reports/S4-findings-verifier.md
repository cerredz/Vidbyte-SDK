# S4 · Findings verifier — report

Inputs: the three lens reports (`S4-review-conformance.md`, `S4-review-conventions.md`, `S4-review-engineering.md`), spec r4, test-plan, request, pipeline, code-map. Diff: `git diff 845a4d9b 84e566bb` (845a4d9b = `git merge-base origin/main 84e566bb`; origin/main has since moved to 6f5a7310, which does not affect the diff). No source edits, no commits, no stash. All probes are under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s4-verify/` (abbreviated `V/`). The reviewers' probes are in `…/scratchpad/s4-eng/` (`E/`) and `…/scratchpad/scripts/` (`C/`).

Result: 5 Blockers, 2 code Majors, 4 test-pack Majors, 13 Minors. 6 refuted or downgraded items. Verdict MERGEABLE AFTER FIXES.

## 1. Merge map (original IDs → merged IDs)

| Original | Lens | Proposed | Merged | Disposition |
|---|---|---|---|---|
| R-C1 | conformance | Major | R-2 (+ R-19) | CONFIRMED; merged with R-E2 (one root cause: text SQLite cannot bind or FTS5 cannot parse). The recall quota sub-claim is split off as Minor R-19. |
| R-E2 | engineering | Blocker | R-2 | CONFIRMED; the fix is extended to file names (verifier), and its transaction part is split off as Minor R-20. |
| R-E1 | engineering | Blocker | R-3 | CONFIRMED; the proposed fix is corrected for Gemini; needs a spec amendment. |
| R-V2 | conventions | Blocker | R-4 | CONFIRMED |
| R-V1 | conventions | Blocker | R-5 (source, 41 lines), R-23 (tests, 167 lines), 6 moved lines refuted | Split as the orchestrator ordered |
| R-V4 | conventions | Major | R-1 (example clause; upgraded to Blocker), R-22 (sections; downgraded to Minor) | Split: two different rules, two different files |
| R-E3 | engineering | Major | R-7 | CONFIRMED |
| R-V3 | conventions | Major | R-21 | DOWNGRADED (spec-prescribed) |
| R-E5 | engineering | Minor | R-8, R-9, R-10 (test-pack Majors), R-24 (test-pack Minor) | One row per gap, as ordered |
| R-E4 | engineering | Minor | R-14 | pass-through, trivial |
| R-C2 | conformance | Minor | R-18 | pass-through, follow-up (spec gap) |
| R-V5 | conventions | Minor | R-17 | pass-through, follow-up |
| R-V6 | conventions | Minor | R-16 | pass-through, trivial (file outside §12.3 → grant) |
| R-V7 | conventions | Minor | R-12 | pass-through, trivial |
| R-V8 | conventions | Minor | R-15 | pass-through, trivial |
| R-V9 | conventions | Minor | R-13 | pass-through, trivial |
| — | verifier | Major | R-6 | NEW: Anthropic digest raises on a lone surrogate (INV-9.2 regression) |
| — | verifier | Major | R-11 | NEW test-pack for R-6 |
| — | verifier | Minor | R-19, R-20 | recall pre-search placement; non-atomic `replace` |

## 2. Verifications

### R-2 (R-C1 + R-E2) — CONFIRMED, Blocker

Code facts:
- `search_memory.py:74` keeps any word with one alphanumeric character, so `a\x00b` survives.
- `fulltext.py:115` quotes it as `"a\x00b"`. FTS5's parser stops at the NUL.
- `execute` catches only `ConfigurationError` (`:82`).
- `_entry_rows` (`:137-151`) validates the shape but never checks that the text can be encoded. `executemany` (`fulltext.py:69`) raises after `_delete` (`:64` → `:136-137`) has already committed.
- `_lookup`'s `try` catches only `OSError` (`:119`).

Commands:

`python -I -X pycache_prefix=V/pyc V/run_fuzz.py <wt> C/fuzz_search.py V/fuzzroot`:
```
'a\x00b' RAISED OperationalError unterminated string
'zeta\x00' RAISED OperationalError unterminated string
'\ud800x' RAISED UnicodeEncodeError 'utf-8' codec can't encode character '\ud800' in position 1: surrogates not allowed
(all 14 other hostile queries: success)
```

`E/probe_queries.py` (through `V/run_fuzz.py`): the same NUL raises, and a lone-surrogate entry line RAISES on both the first and the second call. `workspace.entries((1,))` still reads the file.

`python -I V/probe_poison.py <wt>` (own probe):
```
1 before poison, alpha -> success: '1 of 1 matching entries and note lines shown.'
2 after poison, alpha -> RAISED UnicodeEncodeError ... position 6: surrogates not allowed
3 after poison, gamma (note only) -> RAISED UnicodeEncodeError
4 rows left for entries.jsonl: 0 | fingerprint unchanged: True
5 surrogate in kind only, alpha -> RAISED UnicodeEncodeError
6 file cleaned, alpha -> success
7 NUL in entry text, alpha -> success
8 NUL in a note past 2048 bytes, omega -> success
9 file with surrogate name created; kappa -> RAISED UnicodeEncodeError | alpha -> RAISED UnicodeEncodeError
10 name removed, alpha -> success
```

Lines 9–10 are new evidence the reviewers did not have. A file *name* that UTF-8 cannot hold also poisons every search. Engineering's fix (encode only inside `_entry_rows`) would not cover it. On Linux, the same happens for a file name with non-UTF-8 bytes: Python decodes it with surrogateescape to `\udcXX`. That is reasoned from the standard library; it was not run on Linux. Lines 7–8 show that a NUL inside indexed text is harmless; only the query side breaks on NUL.

`python -I V/probe_recall_presearch.py <wt>` (stubbed memory; the retriever is replaced by one that asserts):
```
'a\x00b' RAISED OperationalError unterminated string | recalled = 1 | retriever started: False
'\ud800x' RAISED UnicodeEncodeError ... | recalled = 1 | retriever started: False
```

Spec reading:
- INV-8.2: "No query text can raise an FTS5 syntax error". "unterminated string" is an FTS5 syntax error.
- INV-8.8: "A malformed line in entries.jsonl is left out of the index and never fails a search". The workspace itself refuses text UTF-8 cannot hold (`workspace.py:276-280`, `@intent unwritable-entries-are-refused-first`), so such a line is not an entry the workspace would write.
- T-1 (spec.md:930) names a crashed tool as the harm that quoting prevents.
- The runtime wraps the raise (`runtime.py:1482-1486` → "Tool execution failed: …"), so the run survives. But the shared index means **every** agent's `search_memory` fails until the file changes. That is a broken result, so Blocker.

Fix proven as a scratch plugin `V/fix_r1.py`:
- `execute` normalizes the query with `replace("\x00"," ").encode("utf-8","ignore").decode()`.
- `_entry_rows` encodes `kind + text` inside its `try`.
- `_note_rows` encodes `source`.
- `_lookup` catches `(OSError, UnicodeError)`.

Runs with the plugin:
- fuzz: `'a\x00b' success '1 of 1'`, `'zeta\x00' success '1 of 1'`, `'\ud800x' success '0 of 0'`.
- poison probe: lines 2–10 all `success`. Line 9: `kappa` is 0 of 0, and `alpha` is 1 of 1.
- recall probe: the retriever starts for both terms.
- `PYTHONPATH="<wt>;V" python -m pytest tests/test_fulltext_index.py tests/features/infinite_memory_agent/test_infinite_memory_search.py tests/features/infinite_memory_agent/test_infinite_memory_recall.py tests/test_code_search_tools.py -q -p no:cacheprovider -p fix_r1`:
```
...........................................................              [100%]
59 passed in 1.21s
```

Is the recall quota a separate defect? Adjudicated **no** (Minor R-19). The spent quota with no retriever is caused only by the pre-search raising, and R-2 removes every known trigger: with the plugin, the retriever starts. INV-10.6 makes free only the calls "refused for validation or quota". EC-10.3 already counts an attempt that fails after it starts. Only the placement is left: the pre-search sits outside the `try` at `recall.py:121`, so any future raise becomes the runtime's generic message instead of the recall-shaped one. Moving one line fixes it.

Advisable spec line for the orchestrator. It is not needed for the entry half, which INV-8.8 already covers. **EC-8.8** | A workspace file whose name UTF-8 cannot hold (a lone surrogate on Windows, or non-UTF-8 bytes decoded with surrogateescape on Linux), or an `entries.jsonl` line whose `kind` or `text` holds a lone surrogate. | The entry line is left out as malformed (INV-8.8). The file is left out of the index for that call, like a file that vanished. | No hits from it; every other search works. | INV-8.5, INV-8.8 |

### R-3 (R-E1) — CONFIRMED, Blocker; needs a spec amendment

Code: `windows.py:143-161` counts each scoped tool's results newest-first, by message order alone. It has no notion of which results the model has answered.

`PYTHONPATH=<wt> python E/probe_mask_batch.py`:
```
anthropic: newest turn = 5 parallel read_lines; masked before the model ever saw them: 2
anthropic: after re-issuing the same 5 in order, masked in newest batch: 2
openai: ... 2 / 2
```

Own probe through the **root agent's real middleware instance** (`build_agent(...).middleware[0]`), on the runtime's own wire shapes. `ToolsFormatter` writes one `{"role":"user","content":[tool_result]}` per Anthropic result (`vidbyte/lib/tools/formatter.py`) and one `{"role":"tool",…}` per OpenAI result. `python V/probe_mask_root.py <wt>`:
```
parallel batch of 3 unread read_lines -> masked: anthropic-shape 0, openai-shape 0
parallel batch of 4 unread read_lines -> masked: anthropic-shape 1, openai-shape 1
parallel batch of 5 unread read_lines -> masked: anthropic-shape 2, openai-shape 2
parallel batch of 8 unread read_lines -> masked: anthropic-shape 5, openai-shape 5
```

Spec and user reading:
- request.md §A Prompt 2 item 3, a §D weighted word: "remove all of the tools call inputs/outputs (escept the final ones/ones that it needs) … because the agent no longer needs this". An output the model has never read is one it needs.
- The placeholder (INV-2.6) tells the model to call again, and calling again in the same order masks the same files again. That is the re-run loop that request.md:58 and :121 reject for dedup.
- INV-2.3 is implemented to the letter, and the spec never considered parallel batches. So this is a weighted-word violation (a Blocker trigger), not an implementation slip.

**Engineering's proposed fix has a defect.** `mut_mask_batch.py` finds the last model turn with `m.role == "assistant"`. I printed the normalized `(role, kind)` the engine hands the strategy:
```
gemini [('user', 'message'), ('model', 'tool_call'), ('user', 'tool_result')]
anthropic [('user', 'message'), ('assistant', 'tool_call'), ('user', 'tool_result')]
openai [('user', 'message'), ('assistant', 'tool_call'), ('tool', 'tool_result')]
```
On Gemini, `last_assistant` is therefore −1, every result counts as unread, and masking switches off. `python V/probe_mask_gemini.py <wt>`, current code, then with engineering's plugin:
```
current:   gemini shape, 5 sequential read_lines -> masked: 2 | parallel batch of 5 unread -> masked: 2
with fix:  gemini shape, 5 sequential read_lines -> masked: 0 | parallel batch of 5 unread -> masked: 0
```
The corrected plugin `V/fix_mask_batch.py` uses `m.role in ("assistant", "model")`:
```
gemini: 5 sequential -> masked: 2 | parallel batch of 5 unread -> masked: 0
root probe: batches of 3/4/5/8 -> 0/0/0/0 on both anthropic and openai shapes
PYTHONPATH="<wt>;V" python -m pytest tests/test_compaction_windows.py tests/features/infinite_memory_agent/test_infinite_memory_economy.py tests/test_context_compaction_middleware.py tests/test_deterministic_compaction_middleware.py tests/features/infinite_memory_agent/test_infinite_memory_recall.py -q -p no:cacheprovider -p fix_mask_batch
........                                                                 [100%]
152 passed in 3.07s
```
Engineering's plugin also passes the same 152 tests (own run: `152 passed in 2.91s`). So no existing test covers Gemini masking, nor parallel-batch masking in either direction (test-pack R-9).

**Does the fix fit the current spec? No.** INV-2.3's second sentence, "In STRIP mode each older output's content becomes the placeholder", requires outputs 4 and 5 of a pending batch to be masked. INV-2.1 (unscoped equals main) and INV-2.5 (pure function) still hold under the fix. AC-2.1 and AC-2.2 stay true as tested, because their histories put one call in each turn. Amendment for the orchestrator to route:

- **INV-2.3 before:** "For each scoped tool name, the newest `keep_recent` outputs stay whole. In STRIP mode each older output's content becomes the placeholder, and its metadata gains `compaction` and `original_chars`, as on `main`."
- **INV-2.3 after:** "For each scoped tool name, the newest `keep_recent` outputs stay whole. With a non-empty `tools` scope, every scoped output after the newest model turn (a message whose normalized role is `assistant` or, on Gemini, `model`) also stays whole, because the model has not read it yet. Those outputs still count toward `keep_recent`, so once the model has answered, the outputs past the newest `keep_recent` are masked as usual. In STRIP mode the content of every other older output becomes the placeholder, and its metadata gains `compaction` and `original_chars`, as on `main`."
- **AC-2.1 Given, before:** "a root history with 5 `grep` calls and results". **After:** "a root history with 5 `grep` calls and results, one call per model turn".
- **New AC-2.5** (P0): Given a newest model turn of 5 parallel `read_lines` calls and their results, on the OpenAI, Anthropic, and Gemini wires; When the InfiniteMemory masking runs; Then all 5 outputs are whole, and after one more model turn exactly the oldest 2 of them are the `masked_output` text, while every call (input) is unchanged.
- **New EC-2.5:** | A parallel turn returns more scoped outputs of one tool than `keep_recent`. | Outputs after the newest model turn are never masked. They count toward `keep_recent`, so the view after the model's reply masks only those past the newest three. | Every output of the batch on the call that shows it. | INV-2.3 |

### R-4 (R-V2) — CONFIRMED, Blocker

`python V/depth_scan.py <wt>` is an own AST scan. It counts both calls and `self._x` references, so a method passed to `to_thread` is caught too:
```
AnthropicProvider: _create_payload -> _attach_cache_breakpoints -> _holds_cache_control
AnthropicProvider: _create_payload -> _attach_cache_breakpoints -> _is_repeat
AnthropicProvider: _create_payload -> _attach_cache_breakpoints -> _marked_message
InfiniteSearchMemoryTool: execute -> _lookup -> _entry_rows / _note_rows / _stamp
InfinitePair: run -> render -> finished_lines
InfiniteWorkspace: map_text -> map_snapshot -> _descriptions / _text
ContextCompactionEngine: compact_* -> _build_strategy -> _string_tuple / _require_summarizer
```

How each chain was judged:
- **Anthropic** (`anthropic.py:148`, `:169`). Spec row 15 (spec.md:1122) says `_attach_cache_breakpoints` "checks the conditions". It does not prescribe helpers, and checklist spec.md:1173 requires one level. In the same file, none of the six existing `_attach_*` helpers calls a method of the class (scan: no `_attach_* -> X` chain). So this is a real AGENTS.md principle-1 break in new code: Blocker under the calibration.
  - The fix must keep the short-circuit. When the caller already holds `cache_control`, `_is_repeat` must not run, or the digest is recorded and INV-9.2 changes.
- **`search_memory`** (missed by the conventions scan, because `_lookup` goes through `to_thread`). Not raised. The spec names `semantic.py:78-81` as the precedent (row 20), and it has the same shape: `execute → to_thread(_index_and_rank) → rebuild_index/_rank → _cosine`. A worker callable that holds the lock is forced by INV-8.9, and S3 disclosed it.
- **`render → finished_lines` and `map_text → map_snapshot`.** Prescribed by INV-5.1 and FR-7.2 (spec.md:236), as the reviewer said.
- **Engine.** `_build_strategy → _string_tuple` already exists on main.

### R-5 (R-V1) — CONFIRMED for source (41 lines); tests split off; 6 moved lines refuted

The rule, quoted from `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/comment-format.md`:
- Scope: "Writing or editing any `#` comment in SDK code that runs past one line".
- Do: "Wrap every comment line at 72 columns, counting the indent, and fill the lines evenly. … A single-line comment that would pass 72 columns becomes a wrapped block too."
- Check: "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched."
- Evidence: "Not a lint rule: 4,325 of 5,965 existing comment lines are wider, so leave untouched files alone."

It says 72 columns, yes. spec.md:1174 restates it in the §12.4 checklist: "Comment blocks wrap at 72 columns, and every `@intent <slug>` sits within 20 lines of its `def`."

Own count over the added lines only:
```
git diff -U0 845a4d9b 84e566bb -- '*.py' | awk '
/^\+\+\+ /{f=substr($0,7); next}
/^@@/{match($0,/\+[0-9]+/); n=substr($0,RSTART+1,RLENGTH-1)+0; next}
/^\+/{l=substr($0,2); if (l ~ /^[ \t]*#/ && length(l)>72) print f ":" n ":" length(l) ":" l; n++; next}'
```
Result: 214 total, 47 under `vidbyte/`, 167 under `tests/`, 0 elsewhere. This matches the reviewer's `wide.txt` (214). Saved as `V/wide_mine.txt`, with the source rows classified in `V/wide_src_class.txt`.

Source split (`git grep -qF <text> 845a4d9b -- vidbyte` per line):
- 6 lines are ON-MAIN, moved verbatim by D-3: `windows.py:38, :51, :83, :127, :144, :164`. Refuted. They are untouched code, which AGENTS.md says not to rewrite just to conform.
- 41 lines are NEW, in 16 files (listed in review.md R-5). Most are 73–76 columns. The worst are `context_compaction.py:165` and `:252` (135), `engine.py:197` (129), and `windows.py:123` (119).

Is main consistent with the rule? I sampled every `.py` file added on main between the rule's commit f7a02bae (2026-10-10, "fix: resolve review comments on PR #690") and 845a4d9b:
```
vidbyte: files added after the rule=109 comment lines=1895 wider-than-72=45
tests: files added after the rule=131 comment lines=1831 wider-than-72=1212
```
Since the rule landed, source follows it (2.4% over) and tests do not (66% over). Does the rule bind tests? The text says "SDK code", and practice applies it only to `vidbyte/`. So the 167 test lines form their own row, R-23 (`tests-comment-only`). My recommendation is to waive it: it would be churn in S2's tests against main's own practice.

### R-1 / R-22 (R-V4) — split

`prompt-families.md`: "Give role prompts headed sections: purpose, tools, workflow, memory, limits, and reply. … Put no numeric limits in prose".
`model-facing-tool-contracts.md`: "give the tool and every parameter a consistent 4–5 sentence general description, and omit concrete examples from model-facing prose" (Because: "examples narrow behavior").

- **R-1, the example clause.** `recall_question_description.md:1`: "Name the subject, the values you need, and any limit such as a period, a source, or a version." That is a direct break of the tool-contract rule. Spec row 37 (spec.md:1145) has "same" as its standard, which refers to row 36's governing standard (the model-facing-tool-contracts guide, "No number, no example"). `grep -noiE "such as|for example|for instance|e\.g\."` over the 10 new leaves and the changed lines finds only this clause. Upgraded Major → Blocker, because the calibration lists "contradicts a field-guide lesson" as a Blocker. The fix is one clause, and the description keeps its 4 sentences. No number is involved (INV-0.3 holds).
- **R-22, the sections.** Headings in the retriever leaf: `# Your role: retriever`, `# How to search`, `# Your final reply`. Verifier: 7 headings; generator: 7; root: 10. The content of purpose, tools, workflow, limits and reply is present (quoted in review.md), and "memory" does not apply (D-14: no memory tools). The reviewer predicted the retriever "may search again or stop early" when it meets a masked output. That is not supported:
  - the sibling trimming section (`verifier_system_prompt.md:29`) never mentions masking;
  - the placeholder states what to do (INV-2.6);
  - the retriever's loop is 8 iterations (NFR-10.2), far below a 90K-token history.

  Downgraded to Minor (follow-up). The `feat/infinite-memory-prompts` branch is rewriting this family.

### R-21 (R-V3) — DOWNGRADED to Minor

Spec lines that prescribe the per-site construction:
- spec.md:1129, row 22: the literal tuple in `agent.py`.
- spec.md:1130, row 23: "middleware `(masking, trim with low watermark, *limits)` as in row 22", with standard "NFR-0.2 (32 lines of headroom: no new helpers here)".
- spec.md:454, FR-10.5: the retriever "holds the map drawn at its start, the masking and trim middleware".
- D-14: built "like a pair's child".

At 845a4d9b the map item was already built at `runtime.py:115` and `launch.py:276`. `grep` shows the three tuples are byte-identical today, so nothing has drifted. A shape the spec prescribed is not an implementation defect.

### R-7 (R-E3) — CONFIRMED, Major

NFR-8.1 (spec.md:476): "At the default workspace caps on the dev machine, a `search_memory` call with the index already built returns in under 50 ms of tool time. The first call, which builds the index, returns in under 2 s." The default caps are `INFINITE_DEFAULT_MAX_FILES = 2_000` and `INFINITE_DEFAULT_MAX_TOKENS = 2_000_000` (constants:49-50).

`PYTHONPATH=<wt> python -X pycache_prefix=V/pyc E/probe_scale.py 1900 8000` (own run):
```
files=1900 entries=8000 bytes=8,277,629
cold build  1290 ms
warm        490 ms / 466 ms / 472 ms
1 note chg  491 ms ; entry append 551 ms
breakdown: iter_files 433 ms, stat 26 ms, retain(list) 25 ms, search 0.1 ms
20 parallel warm searches 9704 ms wall
```

Cause, confirmed in `base.py:89-121`:
- `iter_files` calls `path.resolve()` per file.
- `is_text_file` does `path.read_bytes()[:2048]`, which reads each whole file on every call.
- `relative_path` resolves again (`:62`).
- `retain(kept)` with a list makes `source not in sources` O(n²).

Grep (grep.py:93, :122) and glob share these, so the fix belongs in `_lookup`. Changing the base would change the shared walk under CodingAgent's grep and glob (INV-3.1, INV-R.1), and row 9 limits the base change to one constant.

Feasibility (own prototype `V/proto_walk.py`): an `os.scandir` walk that skips ignored names and symlinks, takes the fingerprint from `DirEntry.stat`, leaves unchanged files unsniffed, and passes `retain(set)`, under the lock:
```
scandir warm refresh+search ms: [3.1, 2.8, 2.8, 2.7, 2.8] | sources 1901 | changed 0
```
`changed 0` means its keys and fingerprints equal the live index's, so the target is reachable with a large margin.

The fix must keep:
- the in-root guard and the once-per-file guard (resolve only symlinked entries);
- INV-8.4: stat before read;
- INV-8.5: the bookkeeping names, the byte cap, and the NUL sniff, done for changed files only;
- INV-8.9: the lock;
- R-2's per-source `UnicodeError` skip;
- flat helpers.

### R-6 — NEW [verifier], CONFIRMED, Major

I found this while checking the cross-lens blind spot "lone surrogates in other new encode paths". `anthropic.py:189`:
```
encoded = json.dumps([payload.get("tools"), payload.get("system")], sort_keys=True, ensure_ascii=False).encode("utf-8")
```
The digest is computed on every request that holds no `cache_control`, the first one included. Main's transport serializes with `json.dumps(json_body).encode("utf-8")` (`vidbyte/lib/http/transport.py:87`, `:142`, `:186`, `:207`), and `ensure_ascii` defaults to True there, which escapes a lone surrogate.

`python -I V/probe_anth_surrogate.py <wt>` and `… <main-base>`. The workspace has the file `notes/caf\ud800.md`, and the system is `map_text()`, as for the root:
```
--- branch
map holds a lone surrogate: True
call 1: RAISED UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 310: surrogates not al
call 2: RAISED UnicodeEncodeError: ...
--- main 845a4d9b (scratch export)
map holds a lone surrogate: True
call 1: payload built and serialized by the transport's json.dumps
call 2: payload built and serialized by the transport's json.dumps
```

This breaks INV-9.2: a first request "carries no marks, and its body is byte-identical to `main`". Instead it raises before sending. It also breaks INV-0.2, because the adapter is shared by the whole SDK. I did not verify whether Anthropic's API accepts an escaped lone surrogate, so on main that request might still fail at the vendor. That is why this is Major, not Blocker: a rare input, but an SDK-wide regression on a path the spec pins to main.

Row 15 prescribes the `json.dumps` arguments but not the encode step, so this fix fits the spec. With `.encode("utf-8", "surrogatepass")` (plugin `V/fix_anth_digest.py`), the probe builds both calls, and:
```
PYTHONPATH="<wt>;V" python -m pytest tests/test_anthropic_cache_breakpoints.py tests/test_prompt_sits_at_run_boundary.py -q -p no:cacheprovider -p fix_anth_digest
...........................                                              [100%]
27 passed in 0.39s
```

### Test-pack gaps (R-8 … R-11, R-24)

- **`mut_delete`**, own run: `PYTHONPATH="<wt>;E" python -m pytest tests/test_fulltext_index.py tests/features/infinite_memory_agent/test_infinite_memory_search.py tests/features/infinite_memory_agent/test_infinite_memory_recall.py -q -p no:cacheprovider -p mut_delete` → `44 passed in 0.67s`. The mutation survives. Engineering cited INV-8.6 for it, but INV-8.6 is the snippet cap. The delete-by-rowid rule lives in §9.1 Refresh (spec.md:781) and row 12 (spec.md:1119). This becomes R-24, a Minor, because the property is performance-only (spec review R-17 was Minor).
- **R-2, R-3 and R-6** each ship with the related suites green. Unmodified baseline: `PYTHONPATH=<wt> python -m pytest tests/test_compaction_windows.py tests/features/infinite_memory_agent tests/test_context_compaction_middleware.py tests/test_deterministic_compaction_middleware.py tests/test_fulltext_index.py tests/test_code_search_tools.py tests/test_anthropic_cache_breakpoints.py -q -p no:cacheprovider` → `331 passed in 10.22s`.
- **NFR-8.1.** test-plan.md lists it under "Tests deliberately NOT written": "Timing on a shared CI host is noise, and the briefing forbids wall-clock tests." So R-10 asks for a deterministic stand-in (no unchanged file is re-read on a warm search), not a benchmark.

### The transaction niche fact — Minor R-20

`fulltext.py:63-64` (`_delete` with its own `with connection:` at `:136`) commits the delete, then `:68-69` inserts in a second transaction. If the insert raises, the source keeps no rows and its old fingerprint. That is real (`probe_poison` line 4: `rows left for entries.jsonl: 0 | fingerprint unchanged: True`).

It is not a separate Major:
- The next call sees the new stamp, which differs from the old fingerprint, re-reads the file, and retries. The state heals itself unless the insert fails every time, and the only such failure found is R-2's.
- After the R-2 fix the same probe shows `rows left for entries.jsonl: 1 | fingerprint unchanged: False`.

Making `_delete` and the insert one transaction needs `_delete` and `retain` to stop opening their own `with connection:`. The nested sqlite3 context manager commits at the inner exit. Follow-up.

## 3. Adjudications between reviewers

- **R-C1 (Major) vs R-E2 (Blocker) on severity.** Blocker kept. The query half alone would be Major, because the run survives one bad call. The row half fails every later search for the whole tree, and the merged finding keeps the higher severity.
- **R-E2's fix vs a fix at the index helper.** I kept the guard in `search_memory` and not in `FullTextIndex`/`FullTextRow`. If `FullTextRow` refused such text with `ConfigurationError`, `_note_rows` would raise it, and `execute` would report it as `fts5_unavailable` (`search_memory.py:82-85`), which is wrong. Per-line skipping for entries also matches INV-8.8 ("left out", only that line).
- **Conventions' "every fix is mechanical, no behavior change" vs engineering's "the core mechanisms hold".** Both are true for their lenses. Neither lens tried Gemini histories (R-3 fix) or encoding paths outside FTS (R-6). Those are the verifier additions.
- **R-V1's scope.** The reviewer counted test lines in the Blocker. The orchestrator's rule (tests are not edited without a grant) and main's practice (66% wide) separate them.

## 4. Fix order that avoids conflicts (for S5)

0. Orchestrator: route the INV-2.3 / AC-2.1 / AC-2.5 / EC-2.5 amendment (and optionally EC-8.8) before R-3 and before the test author writes R-9.
1. R-1: `recall_question_description.md`. Independent.
2. R-2: `search_memory.py` (`execute`, `_entry_rows`, `_note_rows`, `_lookup` except tuple).
3. R-7: `search_memory.py` `_lookup` walk, **after** R-2, carrying R-2's `UnicodeError` skip.
4. R-3: `windows.py` `ToolOutputSlidingWindowCompaction.compact`, after the amendment.
5. R-6: `anthropic.py:189` (one line), **then** R-4's restructure of `_create_payload` / `_attach_cache_breakpoints`.
6. Trivial Minors: R-19 (`recall.py`), R-14 (`runtime.py`, one line, keeping #1159's merge small), R-13 (`util/__init__.py`), R-12 (`providers/README.md`), R-15 (headers), R-16 only with a grant.
7. R-5 rewrap **last**, over every `vidbyte/` file the diff touches, because steps 1–6 add comments. Then run the awk check over `git diff -U0 845a4d9b HEAD -- 'vidbyte/*.py'`, then `PYTHONIOENCODING=utf-8 python lint/run.py --rule A002`, then the full lint.
8. Test author, separately: R-8, R-9 (after the amendment), R-10, R-11, R-24.

## 5. Commands run (all with a timeout and `</dev/null`)

- `git merge-base origin/main 84e566bb` → 845a4d9bd5f1…
- `git diff --stat origin/main...84e566bb -- vidbyte` → 55 files, +1742/−338
- the five probe and fix-plugin runs quoted above, plus `E/probe_mask_batch.py` with and without `mut_mask_batch`
- `python V/depth_scan.py <wt>` (AST scan, quoted above)
- the awk width count and `git grep -F` classification; main's per-area count for files added since f7a02bae (quoted above)
- `grep` over the new leaves for example markers; `sed` and `grep` on anthropic.py, windows.py, search_memory.py, fulltext.py, recall.py, base.py, runtime.py:1332-1348/:1472-1486, formatter.py, transport.py, providers/README.md:532/:610-615, util/__init__.py, registries/infinite.py, constants/infinite.py
- pytest runs: 331 passed (baseline), 152 passed (×2: engineering's and the corrected masking fix), 59 passed (`fix_r1`), 44 passed (`mut_delete` survives), 27 passed (`fix_anth_digest`)

No file other than `review.md` and this report was written in the worktree. `git status` shows only these plus the three untracked lens reports.
