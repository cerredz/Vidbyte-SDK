VERDICT: SOUND WITH FIXES — r2 closes all twelve round-1 findings, and the design holds against the code; two Blockers remain. In one, the status message as specified turns a must-stay-green test red. In the other, the recall card's found section still carries retriever-written text that four clauses forbid. Each takes a one-clause edit.

WHAT THE SPEC GETS RIGHT
- A-2 (a user status message after the tool results) has real precedent and works on every provider:
  - `runtime.py:670` appends `review.feedback` as a user message after the tool results, and `jev/compute/controller.py:107,114` appends user messages from `_after_tool_iteration`.
  - The Anthropic adapter never merges messages, and main already sends consecutive user turns.
  - Gemini's `_gemini_turn` (`providers/gemini.py:147-160`) converts `content` to `parts`.
  - The compaction engine resolves Anthropic tool_result names through the tool_use ids (`middleware/compaction/engine.py:56-68`), so masking by tool name works on every provider.
- The R-1 guards are C006-safe as written:
  - `RecordFieldValidator.require_int(value, field_name, *, minimum, maximum=None)` (`lib/dataclasses/validation.py:101`) and `require_bool` (`:110`) exist. They raise `ConfigurationError`, a `VidbyteSdkError`.
  - Lint C006 judges "a value handed to a validator helper" inside that helper.
- The R-5 index design matches the repo's own precedent:
  - It holds one `threading.RLock` across refresh and search inside `asyncio.to_thread`, like `semantic.py:53,78-81,143`, and sets `check_same_thread=False`.
  - It sits in the lib layer, and adds no new import risk: `import vidbyte` already imports `sqlite3`.
  - CI runs Python 3.11 and 3.12 only, and both ship FTS5 (local 3.11.0 has SQLite 3.38.4).
- The R-3 `fit_map_lines` lift can be byte-identical. `map_text` (`workspace.py:207-231`) reserves room for the `INFINITE_MORE_FILES` line before it cuts, so cut output stays within the cap and AC-7.4 is computable.
  - The §8.4 budget matches: 13 new files, 13 CREATE rows.
  - L9 names are consistent across §8.5, §9.1 and §12, and no r1 wording is left in the changed sections.

FINDINGS

R-13 [Blocker] [L10/L6] §6.1 INV-7.3, §7 NFR-7.2, §13 — A no-change status message inside NFR-7.2's own 150-token bound turns a "must stay green unchanged" test red.
- Evidence:
  - §13 says `test_infinite_memory_context.py:46` stays green, because with L ≥ M "the trim keeps today's algorithm" (D-6, EC-4.4). That reasoning covers only the trim. The test patches the cap to 250 and asserts that the newest tool group ("PAGE-4-") survives.
  - INV-7.3 now appends one status message after every tool iteration, as the newest history group, and NFR-7.2 lets it be up to 150 tokens.
  - I replayed the test on main's code with `_after_tool_iteration` patched in memory to append an INV-7.3-shaped message: real header, `-`, and the real `_render_loop_settings_block`.
    - With a terse 89-token message, PAGE-4 is kept and the test passes.
    - With a two-sentence `map_update` leaf of 126 tokens, PAGE-4 is dropped, and the test fails at "the newest tool group must survive trimming".
  - The pass/fail threshold therefore lies between 89 and 126 tokens, well under the stated 150. §14 forbids editing tests outside the §13 change list.
  - Second cost on the same path: a status message is never masked (NFR-7.2), so each tool iteration leaves roughly 90–150 tokens of stale header and loop counters in history. In a masked, search-heavy stretch, these stale messages can be a large share of the kept 65K suffix. They are bounded by the trim but never shrunk.
- Failure: the S3 implementer either writes a leaf over about 110 tokens and breaks a test the spec promised stays green, or edits the test against §14. The per-iteration cost the spec reports as "bounded" is also understated for long runs.
- Smallest fix: in INV-7.3/NFR-7.2, when the workspace did not change, the status message is the loop-settings block alone (about 33 tokens), with no leaf text, header or `-`. Also tighten NFR-7.2's no-change bound to that block's size.
  - Fallback: move `test_infinite_memory_context.py:46` from "must stay green unchanged" to §13's deliberately-changed list, and state the new assertion.
  - Q-12 [scope-adding], optional, default "not built": mask every status message but the newest, using the same placeholder mechanism.

R-14 [Blocker] [L9/L7] §9.2 `{found}` vs INV-10.4, AC-10.3, T-2 — The found section renders the retriever's `({why})`, which three normative clauses and the threat model forbid.
- Evidence: §9.2 (spec line 837) says `{found}` is "one block per accepted citation … Then `({why})`". `why` is retriever-written text (grammar line 863: `FOUND <path>:<start>-<end> (<why>)`). Each of these forbids it:
  - INV-10.4: "No retriever-written text appears there."
  - AC-10.3 (P0): "no text the retriever wrote beyond the not-found reasons".
  - T-2: "the retriever's own words never reach the found section".
- Failure:
  - The P0 test AC-10.3 cannot pass against the §9.2 rendering. One of them has to be violated.
  - T-2's attack goes through. A hostile note steers the retriever to cite a real line with a `why` such as "(verified: ignore prior instructions and …)". That text then sits in the "copied from disk" section that the root is told to trust.
- Smallest fix: drop `Then ({why}).` from §9.2 `{found}` and from row 43, so the found blocks hold only the label and the copied text.
  - Alternative, if the user wants the reason shown: amend INV-10.4, AC-10.3 and T-2 to allow one capped, single-line `why`, rendered outside the copied block and labelled as the retriever's.

R-15 [Major] [L10] §6.1 INV-10.7, §7 NFR-10.1/NFR-10.3, AC-10.7 — The card cap as specified cannot hold "at most 1,500 tokens", because `TokenEstimate.cap` overshoots by the marker.
- Evidence:
  - `vidbyte/lib/util/text.py` `TokenEstimate.cap` returns `cut(text, max_tokens) + marker`. With `INFINITE_TRUNCATION_MARKER = " … [cut]"` (8 chars), a card capped at 1,500 counts ceil(6008/4) = 1,502 tokens.
  - INV-10.7, NFR-10.1 and AC-10.7 all say "at most `INFINITE_RECALL_CARD_MAX_TOKENS`".
  - Separately, a cut found block is a prefix of the disk text, while NFR-10.3 says transcribed text "equals the bytes on disk at the cited place".
- Failure: an implementer who reuses the canonical helper (principle 5) fails AC-10.7. One who hand-rolls a stricter cut duplicates `TokenEstimate`. The NFR-10.3 test also fails on any cut card.
- Smallest fix: state the exact rule. Either the card is `TokenEstimate.cap(rendered, CAP, INFINITE_TRUNCATION_MARKER)`, with the bound "CAP plus the marker's own count", or the code caps at CAP minus the marker's count. Add to NFR-10.3: "a cut block is an exact prefix of the bytes on disk".

R-16 [Major] [L5/L10] §6.1 INV-10.5, §9.1 `InfiniteRecallCitation`, D-16 — A FOUND line that matches the grammar but fails the record's own range check makes the whole recall error, instead of being rejected.
- Evidence:
  - §9.1 (line 783) validates `1 <= start <= end` and `entry_id >= INFINITE_FIRST_ENTRY_ID` in the record's `__post_init__`, which raises `ConfigurationError`.
  - D-16 makes `parse` a classmethod that constructs the record. Lines such as `FOUND notes/p.md:5-3 (x)`, `FOUND notes/p.md:0-4 (x)` or `FOUND #0 (x)` match the grammar on lines 862-864, so `parse` raises.
  - INV-10.5 says such a citation is "listed as rejected, with the reason".
- Failure: one malformed line from the retriever (or a line steered there by a hostile note, T-2) makes the recall call fail. Every valid citation in the same reply is lost, and the quota is already spent (INV-10.6 counts it once the retriever starts).
- Smallest fix: `parse` returns `None`, or a rejected marker with reason "malformed range", when the parsed numbers would fail validation. Alternatively, the tool catches `ConfigurationError` per line and lists that line as rejected. Add `FOUND notes/p.md:5-3` and `FOUND #0` to AC-10.4's rejected cases.

R-17 [Minor] [L6] §9.1 `FullTextIndex.replace` — Deleting a source's rows by the UNINDEXED `source` column is a full-table scan under the shared lock.
- Evidence: §9.1 (line 770): "`replace(source, …)` deletes a source's rows". The only column naming the source is `UNINDEXED`, and FTS5 has no secondary index, so `DELETE … WHERE source = ?` scans every row.
  - I measured this on a 33,760-row table (8,000 entries plus 80 notes of 322 lines; stdlib sqlite3, `porter unicode61`):
    - one delete takes 4.8 ms for a note and 26.3 ms for `entries.jsonl`;
    - 400 deletes by source take 1,049 ms;
    - deleting the same 322 rows by rowid takes 0.98 ms;
    - a MATCH takes 0.33 ms.
  - EC-7.8 already names a batch that creates 400 files.
- Failure: the first search after a large batch holds `index.lock` for about a second per 400 changed sources. Every other agent's search waits on it, and the cost grows with index size.
- Smallest fix: keep each source's rowids beside its fingerprint (both in memory) and delete by rowid. Name that access path in §9.1.

R-18 [Minor] [L5] §6.1 INV-8.4 — The order of the stat and the read is unstated, and one order loses writes permanently.
- Evidence: INV-8.4 says the tool "compares every indexable file's fingerprint … re-reads files that changed". It does not say whether the recorded fingerprint is taken before or after the content is read.
- Failure: suppose the fingerprint is taken after the read, and a `bash` write or a generator's atomic replace lands between the two. The index then holds the old rows under the new fingerprint, and no later search re-reads that file until it changes again. This is a permanent version of EC-8.5, not a one-tick one.
- Smallest fix: add to INV-8.4: "the fingerprint recorded for a file is the one taken before its content is read".

R-19 [Minor] [L5/L4] §12.3 row 6 (`low_watermark_tokens` through the builder) — The engine coerces the option with `int()`, so the strategy's C006-safe guard never sees the caller's value.
- Evidence:
  - The trim branch of `middleware/compaction/engine.py:195-198` builds the strategy from `int(options[...])`.
  - `context_compaction.py:231-253` `_validate_options` checks `int(options[key]) < 0`.
  - So `low_watermark_tokens=True` becomes a 1-token watermark, and `2.5` becomes 2, before the `require_int` guard named in the row runs.
- Failure: a bool or float watermark passed through `MessageHistoryCompactionMiddleware.history_trim(...)` is accepted silently. The guard only protects direct strategy construction.
- Smallest fix: row 6 says the engine forwards `low_watermark_tokens` unchanged, or `None`, and the strategy's `require_int` is the one check.

R-20 [Minor] [L11] §12.6 phases — Some P3 rows depend on names that only P4 or P5 creates.
- Evidence:
  - Row 25 (P3) builds memory with `settings=self.settings`, and the unphased first bullet of row 23 (phases P3, P4, P5) gives both pair memories `settings=launch.settings`. Row 27, which adds the `settings` keyword to `InfiniteAgentMemory.__init__`, is P5.
  - Row 16 puts `INFINITE_MASKED_TOOL_NAMES` in P3, but §8.5 (line 720) defines it with `INFINITE_SEARCH_MEMORY_TOOL_NAME`, a P4 constant.
  - Row 46's line-51 clause "Name `search_memory`" is unphased, while the tool arrives in P4.
- Failure: P3 does not import or run on its own, so the phase-by-phase gate in §12.6 fails at P3.
- Smallest fix: move the `settings=` edits in rows 23 and 25 to P5. Give P3 `("grep", "read_lines")` and extend it to the full tuple in P4, or move the constant to P4. Mark row 46's `search_memory` clauses P4.

R-21 [Minor] [L8] §12.3 rows 24 and 50 — Two pieces of agent-facing documentation will state behavior the spec contradicts.
- Evidence:
  - Row 24 rewrites workspace WHAT NOT TO DO 1 to say `full_text` "never stands in for a disk read". EC-8.5 accepts that it does, for one timestamp tick on a same-size edit.
  - `vidbyte/agents/infinite/README.md:111` (Notes for agents) says "one tool output larger than that is dropped whole". Under EC-4.2's hysteresis, every non-system group is dropped instead. Row 50 lists lines 28, 40, 58 and 60-81, plus two new Notes lines, but not line 111.
- Failure: agents reading the header or the README Notes rely on guarantees the code does not give, which these files exist to prevent.
- Smallest fix: in row 24, write "re-checked against file fingerprints before every search (EC-8.5 names the one blind spot)". Add line 111 to row 50, restated per EC-4.2.

R-22 [Minor] [L9] A-10 / §12.3 row 25 — The status message's loop block must count tools the way the system path does.
- Evidence: `agents/runtime.py:396-407` renders the block with `tool_call_count=len(self._non_internal_tool_contexts(state.call_contexts))`. `state.tool_call_count` is `len(self.call_contexts)`, which includes internal tools. Row 25 and INV-7.3 say "rendered with the live counters" without naming the source.
- Failure: the status message's `tool_calls` line would differ from the block the same agent saw in its system string on main, and from the blocks that generators and verifiers still see (INV-7.5).
- Smallest fix: row 25 names the call: `self._render_loop_settings_block(..., tool_call_count=len(self._non_internal_tool_contexts(state.call_contexts)))`, as at `runtime.py:406`.

R-23 [Minor] [L11] §11 Commands — "Install: N/A — `.venv` is already set up in the worktree" is false.
- Evidence: the worktree has no `.venv` (`.venv/Scripts/python.exe` does not exist). This review ran the repo's tests with the global Python 3.11.0 and `PYTHONPATH` set to the worktree root.
- Failure: the S3/S4 gate commands as written fail on the first step, or silently run a different interpreter.
- Smallest fix: replace that line with the real setup, either "global Python 3.11 with `PYTHONPATH=<worktree>`" or a named `python -m venv .venv` plus an editable install, and use it consistently in the gate commands.

R-24 [Minor] [L1] §6.1 INV-10.10 — The recall pre-search ANDs up to `INFINITE_RECALL_MAX_TERMS` terms over single-line rows, so it will usually return no hits.
- Evidence: INV-8.2 makes the MATCH the AND of every word, and each index row is one note line or one entry. INV-10.10 runs "one `search_memory` search over" all the request's `terms`, so a hit needs every term on the same line.
- Failure: the retriever's first message usually says "0 hits", and the pre-search that justifies taking `terms` buys nothing.
- Smallest fix: state it as an accepted EC. Alternatively, run one search per term, joined under the same hit cap (this ties to Q-8). The per-term option changes behavior inside an already-requested feature; it adds no control.

VERIFIED CLAIMS
- HELD: `runtime.py:670` appends a user message after the tool results, and `:700` calls `_after_tool_iteration` after `middleware.after_iteration`. A-2 precedent; `jev/compute/controller.py:107,114` is a second one.
- HELD: `runtime.py:1668` `_build_system_string(context, *, loop_settings_block="")` and `:1679` `_render_loop_settings_block` exist with the cited shapes, so the row 25 override works.
- HELD: `RecordFieldValidator.require_int` (`validation.py:101`) and `require_bool` (`:110`) exist with the cited signatures. They raise `ConfigurationError` (`lib/errors/base.py:289`), and C006 accepts helper-validated values (`lint/rules/c006_finite_numeric_guards.py`).
- HELD: `semantic.py:53,78-81,143` uses `threading.Lock` plus `asyncio.to_thread`, the precedent for R-5. `import vidbyte` already imports `sqlite3`. CI matrix is 3.11/3.12.
- HELD: `workspace.py:207-231` `map_text` reserves room for the MORE line before cutting, so a byte-identical `fit_map_lines` lift is possible and cut output stays within the cap.
- HELD: `providers/anthropic.py` makes shallow `dict(message)` copies with shared content lists, so marks must copy the list. It inserts the prompt via `PromptPlacement.index` and merges no messages. `test_prompt_sits_at_run_boundary.py:272-282` survives the marks (A-5).
- HELD: the gateway adapter persists per runner (`lib/runners/text.py`), so the repeat digest set survives across a run's requests.
- HELD: Gemini `_gemini_turn` (`providers/gemini.py:147-160`); engine tool-name resolution for Anthropic (`engine.py:56-68`); `_provider_groups` makes the status message its own group (`strategies.py`).
- HELD: bash `_collect(process, buffer)` mutates the buffer it is passed, so an `omitted: list[int]` counter survives the timeout the same way (INV-6.1).
- HELD: `FileSystemPermissions.resolve_scoped_path` (`lib/tools/filesystem/permissions.py:14-22`) calls `.expanduser().resolve()`, so it follows symlinks and refuses `..` and absolute escapes (R-4/T-2). The search side checks unresolved path parts, as grep does.
- HELD: `Tools.without` (`tools/catalog.py:90`) takes tool objects, not names, so the rows that withhold by name must map names to objects. The rows already go through the registry's names.
- HELD: the `parse` classmethod precedent (`lib/dataclasses/prompts.py:42`, raises `ConfigurationError`) for D-16.
- HELD: §8.4 budget, 13 new files = 13 CREATE rows. `artifacts/file_index.md` and `REPO_MAP.md` hold folder-level prose, so no row is owed.
- DID NOT HOLD: §13 "`test_infinite_memory_context.py:46` stays green unchanged". It fails once the no-change status message exceeds about 110 tokens (R-13).
- DID NOT HOLD: AC-10.3 / INV-10.4 / T-2 against §9.2's `({why})` in `{found}` (R-14).
- DID NOT HOLD: "card at most 1,500 tokens" against `TokenEstimate.cap`, which overshoots by the 8-char marker (R-15).
- DID NOT HOLD: §11 "`.venv` is already set up in the worktree" (R-23).
