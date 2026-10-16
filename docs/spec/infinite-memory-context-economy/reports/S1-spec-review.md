VERDICT: SOUND WITH FIXES — The design is right and fits the repo, but two defects would fail the gate (C006 is missing from the new guards, and AC-4.1/4.2 contradict INV-4.2), and five gaps would show up in production: the uncapped status message, superseded-memory citations, a per-instance index on the event loop, masking eroding hysteresis, and a card cap that cuts the not-found list.

WHAT THE SPEC GETS RIGHT
- It found the real blocker behind items 4, 7 and 9. The root's system string carries a per-call `- max_iterations: n/500` (`vidbyte/agents/runtime.py:_render_loop_settings_block` :1679–1690, joined in `_build_system_string` :1668). The spec moves it into a plain user message that follows the existing review-feedback precedent (`runtime.py:670`, `messages.append({"role": "user", "content": review.feedback})`).
- Item 9 is shaped correctly for the gateway:
  - Marks are block-level `{"type":"ephemeral"}` with no `ttl`.
  - They go on payload copies only, gated on a repeated tools+system digest.
  - The backend's `_require_short_cache` (`backend/provider/generative_models/client.py:260–276`) admits exactly this.
  - The managed wire test (`tests/features/sdk_managed_text/test_managed_text_wire_contract.py:172–185`) stays green, because every call there uses a fresh runner and so never repeats.
- The retriever has no `InfiniteAgentRole`. This sidesteps the contract test that gives every role `remember`/`write_note` (`test_infinite_memory_contract.py:378–390`) and avoids `launch.py:268–274` routing it to verifier rules. Code, not the retriever, copies cited text from disk.
- The repo changes are precise and safe:
  - The class move to `windows.py` touches only package-internal import sites (`compaction/__init__.py`, `engine.py:30,33,198,206`, `context_compaction.py:9,253`; the test imports from the package). Neither class is in `contracts/sdk-public-api.json`.
  - The deliberately-changed test list in §13 is complete. I checked the other system/map readers: `test_infinite_memory_context.py:57`, `test_infinite_memory_acceptance.py:165–166`, `test_infinite_memory_delegation.py:416–417` and `test_infinite_memory_contract.py:239` all stay green.

FINDINGS

R-1 [Blocker] [L8] §12.3 rows 4, 10, 11, 26 — The new numeric guards will raise the C006 count, and NFR-0.3 forbids any rise
  Evidence:
  - Row 4 asks for "negative low_watermark_tokens -> ValueError" (§8 sketch, spec :566).
  - Row 10 asks for a `context_lines` range check in `GrepTool.__init__`.
  - §9.1 says `FullTextMatches.total` "is an `int` ≥ `len(hits)`" and `InfiniteRecallCitation` holds "`entry_id` (an `int` ≥ …)" or "`1 <= start <= end`".
  - None of these rows lists C006 in its lint column.
  - The sibling guard being copied is already a finding. `python lint/run.py --rule C006 --all` reports: "strategies.py:599 `TrimWithProviderBoundariesCompaction.__init__` range-checks `max_messages` … with `max_messages is not None and max_messages < 0`, but no guard on that value rejects `True`, `float('nan')` and `float('inf')`." The baseline is `"C006": 104` (`lint/baseline.json:15`).
  - C006 scans every `__init__`/`__post_init__` and every validator-named helper (`lint/rules/c006_finite_numeric_guards.py`, `_CONSTRUCTORS`, `_VALIDATOR_NAME`).
  Failure: The implementer writes `if low_watermark_tokens is not None and low_watermark_tokens < 0: raise ValueError`, mirroring :599. The same happens for `context_lines` and the record ranges. `True`, NaN and inf pass these checks, so C006 goes from 104 to 105 or more. `lint/run.py` then exits non-zero, which fails NFR-0.3 and the gate.
  Smallest fix:
  - Add C006 to the lint column of rows 4, 10, 11 and 26.
  - State the guard shape: `isinstance(x, bool) or not isinstance(x, int) or x < bound` (the repair text C006 prints), or `RecordFieldValidator.require_int` where a validator is in reach.
  - Add the §14 checklist line "No new C006 finding."

R-2 [Blocker] [L9] §7 AC-4.1, AC-4.2 vs §6 INV-4.2/INV-4.4 — The P0 trim ACs contradict the P0 invariant, so the tests cannot pass against a correct implementation
  Evidence:
  - AC-4.1: "max_tokens=90_000, low_watermark_tokens=65_000 and a non-system history of 91,000 tokens … the kept history is … at most 65,000 tokens plus less than one group".
  - INV-4.2: the trim "drops the shortest prefix of non-system groups whose cumulative tokens reach `ceil((N − B) / S) · S`".
  - AC-4.2: "5 more small groups (under 25,000 tokens in total)".
  Failure:
  - AC-4.1: with N = 91,000 and B ≤ 90,000, ceil((N−B)/S) = 1, so INV-4.2 drops about 25,000 tokens and keeps between 66,000 minus one group and 66,000. With "many small groups" (well under 1,000 tokens each), that range never overlaps "< 65,000 + one group". The S2 test is red against an INV-correct S3 implementation.
  - AC-4.2: appending between 24,000 and 25,000 tokens pushes N − B past 25,000. The ceil then becomes 2 and the cut moves, so the AC's "same first kept message" fails although the AC's precondition holds.
  Smallest fix:
  - AC-4.1 → "kept ≤ N − S (66,000) and > 66,000 minus the largest group, and ≤ B".
  - AC-4.2 → "at most 24,000 tokens in total (so ceil((N−B)/S) is unchanged)".

R-3 [Major] [L5] [L6] §6 INV-7.3, EC-7.7 — The root's status message is unbounded and escapes every cap the map had
  Evidence:
  - INV-7.3: "`{changes}` set to the current map line of every added or changed file plus `- {path}: removed` for every removed file".
  - EC-7.7: "The status diff uses the uncapped snapshot".
  - Today `map_text` caps at `INFINITE_MAP_MAX_TOKENS = 8_000` with `INFINITE_MORE_FILES` (`vidbyte/agents/infinite/workspace.py:207–231`).
  - `INFINITE_NEW_FILES_PER_AGENT = 10` and `INFINITE_DEFAULT_MAX_FILES = 2_000` (`vidbyte/lib/constants/infinite.py`).
  - The status message is a plain user message, so the tool-result cap (`INFINITE_TOOL_RESULT_MAX_CHARS`, `runtime.py:1985`) and the masking window (tool outputs only) never touch it. `_provider_groups` makes it one indivisible group.
  Failure:
  - A 20-pair batch lets 40 children create up to 400 files, plus edits. Alternatively, one root `bash` loop writes 1,500 notes.
  - The next status message is then one group of tens of thousands of tokens: about 160 tokens per line with a 150-token description, or about 15 per "(no description)" line. It is re-sent on every call until trimmed.
  - If it exceeds B, EC-4.2 applies: "every non-system group is dropped", including the newest tool results the root needs.
  - The constants header's 105,000-token budget sum no longer bounds the root's context.
  - Separately, because the root's loop block is never empty (max_iterations 500), INV-7.3 appends a header-plus-loop-block message on every iteration. That per-iteration overhead is stated nowhere.
  Smallest fix:
  - Cap `{changes}` at `INFINITE_MAP_MAX_TOKENS`, using the same TokenEstimate cut as `map_text`. End with the `INFINITE_MORE_FILES` line ("…n more changed files; use grep or search_memory").
  - Add an EC and an AC for a status message over the cap.
  - State the per-iteration token overhead in an NFR.
  - This keeps the settled "frozen map + one-line deltas" design.

R-4 [Major] [L5] [L7] §6 INV-10.5, EC-10.2 — Range citations can transcribe superseded memory and run journals as "found"
  Evidence:
  - INV-10.5 accepts a range when "its path resolves inside the workspace to an existing file; `1 <= start <= end <= total lines`; `end − start + 1 <= max_read_lines`".
  - Row 20 shows the spec knows which files are not memory: `ignore_patterns=(INFINITE_RUNS_DIRNAME, INFINITE_SUPERSEDED_FILE, INFINITE_FILES_FILE, INFINITE_ENTRIES_FILE)`.
  - Superseding an entry moves it to `superseded.jsonl` (`workspace.py`), and `InfiniteWorkspace.entries(ids)` raises for non-live ids. That is the very check the range path skips.
  - EC-10.2 reads "`.runs/…` outside the read window", which implies `.runs/…` inside the window is accepted.
  Failure: Under DELEGATED, the retriever greps an old price and replies `FOUND superseded.jsonl:3-3 (Acme price)`. Every INV-10.5 condition holds, so the code copies the superseded fact into "found" and the root acts on it. The same path transcribes other agents' `.runs/` journal lines or raw `entries.jsonl` JSON. Either way, the request's "entry live" rule (request.md:114) is bypassed through the path form.
  Smallest fix:
  - Add to INV-10.5: "and the path does not match any of `search_memory`'s ignore patterns (share one constant tuple); entries are cited only by `#id`."
  - Reword EC-10.2.
  - Add a `superseded.jsonl` range citation and a `.runs/` citation to AC-10.4.
  - This is not scope-adding: it closes a bypass of a check the request already requires.

R-5 [Major] [L1] [L6] [L5] §8 D-11, §9.1, §12.3 rows 12 and 20 — The full-text index is one per tool instance, not one per workspace, and it runs on the event loop
  Evidence:
  - The request says (request.md:112): "Index in memory per workspace, refreshed from file fingerprints".
  - The spec says (§9.1 :737): "one per `FullTextIndex` (one per `search_memory` tool instance)".
  - Row 20 says only "File reading happens in sync helpers". Nothing says `asyncio.to_thread`.
  - Row 12 nonetheless gives `FullTextIndex` "`check_same_thread=False` and a `threading.Lock`", which only matters if the index is used off the loop thread.
  - The nearest sibling is `vidbyte/tools/builtins/code_search/semantic.py:SemanticSearchTool`: an in-memory index plus a `threading.Lock` plus `await asyncio.to_thread(self._index_and_rank, …)` under `@intent semantic-search-runs-off-the-event-loop`.
  - Lint S047 (ASYNC230) and S052 do not cover `sqlite3`, so nothing catches the blocking.
  Failure:
  - A 20-pair batch has a root, 20 generators and 20 verifiers, each with its own `search_memory`. Each one's first search reads every live entry and every note line and builds a separate FTS5 table, up to 41 builds of the same workspace. A recall retriever adds one more each time.
  - Every search also stats every file (fingerprint refresh) and runs bm25 on the event loop thread, stalling all parallel pairs that share that loop.
  Smallest fix:
  - One `FullTextIndex` per workspace. `InfiniteMemoryAgent` builds it next to the workspace and passes it to `InfiniteMemoryAgentTools`/`get_tools` (agents → tools → lib, no upward import).
  - `InfiniteSearchMemoryTool.execute` awaits `asyncio.to_thread(...)` for refresh plus search, as `SemanticSearchTool` does.
  - Cite `semantic.py` as the precedent in row 20.

R-6 [Major] [L5] [L9] §10 EC-4.3, §11 NFR-4.1, §6 INV-4.4 — Masking ahead of the trim breaks INV-4.4's premise, so hysteresis oscillates, and EC-4.3 understates the cost
  Evidence:
  - INV-4.4 holds only when "the later one equals the earlier one plus appended groups".
  - D-2 places masking first, and AC-2.4 has the trim measure the masked view.
  - EC-4.3: "The cut moves back by up to S tokens, which causes one cache miss. | One extra write."
  - NFR-4.1 (P0): "the trimmed history's first message changes at most once per 25,000 tokens of growth".
  Failure:
  - A new small `read_lines` result masks the 4th-newest one, which can be a 200-line read of about 2–3K tokens. N therefore falls by about 2–3K. Whenever N sat within that amount above a multiple of S, ceil((N−B)/S) drops by one.
  - The cut jumps back by up to 25,000 tokens: old groups reappear and the history jumps from about 66K to about 90K, forcing a full-history write. A few calls later N re-crosses and the cut jumps forward again, forcing a second full write.
  - That is two extra writes per dip, not one. With hundreds of masking events per run, at roughly net-drop/S ≈ 10% chance each, NFR-4.1 does not hold for the wired root, and G-1's saving is overstated.
  Smallest fix:
  - Restate EC-4.3 as "two full-history writes per dip, probability ≈ net drop / S per masking event".
  - Scope NFR-4.1 to the bare strategy (INV-4.4).
  - Add a P1 AC that counts cut moves over a scripted masked root run.
  - Optionally make the cut monotone within a run, by keeping the last multiple in `run_state` under a private key class, which avoids D-5's `type(self)` collision. Masking stays first, as settled.

R-7 [Major] [L1] [L3] §11 NFR-10.1, §9 leaf table (`recall_card.md`), INV-10.7 — The 1,500-token card cap cuts exactly the parts the request says the card must list
  Evidence:
  - The request (request.md:114): "the card is capped (~1,500 tokens) and lists what was not found and which searches ran".
  - The leaf order is `{question}`, `{found}`, `{not_found}`, `{rejected}`, `{searches}` (spec :728).
  - INV-10.7 cuts the whole card at the end and appends `INFINITE_TRUNCATION_MARKER`.
  - INV-10.5 allows a range up to `max_read_lines` (200 lines).
  Failure: One valid 200-line citation (about 2–3K tokens) fills the card. `not_found`, `rejected` and `searches` are all cut, so the caller cannot tell a partial answer from a complete one. It then re-asks, spending its `INFINITE_RECALLS_PER_AGENT` quota on searches that already ran.
  Smallest fix: Render `not_found`, `rejected` and `searches` before `found`, or cap `{found}` at the room the other sections leave and cut only it, with the marker. Add an AC with a 200-line citation that still shows the searches line.

R-8 [Minor] [L10] §7 AC-8.1 — The only P0 entry-hit AC can never produce a hit
  Evidence: The query is `enterprise pricing zeta` against "Zeta lists Enterprise at 999 USD". With `porter unicode61` and quoted, AND-joined words (D-11), "pricing" stems to "price", which is absent. The AC's "if all three words occur" branch is dead, so only "no hit" is tested.
  Failure: Ranking, `#7 fact: …` rendering, and the shown/total line for a hit go untested at P0. AC-8.5 checks only counts and snippet length.
  Smallest fix: Query `enterprise zeta` (or `zeta enterprise lists`). Expect `#7 fact: …` as the first hit, and keep a separate negative AC.

R-9 [Minor] [L9] [L10] §6 INV-6.2, INV-6.4 — `T = min(TAIL, MAX)` makes any cap at or below 25,000 tail-only, which contradicts D-8, and the timeout marker can claim a drop that never happened
  Evidence:
  - INV-6.2: "T = `min(BASH_TAIL_OUTPUT_BYTES, BASH_MAX_OUTPUT_BYTES)` and H = `BASH_MAX_OUTPUT_BYTES − T`".
  - `tests/features/coding_agent/test_bash_tool_process_bounds.py:244` patches `BASH_MAX_OUTPUT_BYTES` to `SMALL_CAP_BYTES = 1000` (:41), and that test is on §13's deliberately-changed list.
  - INV-6.4 shows the marker "when the held bytes reach `BASH_MAX_OUTPUT_BYTES`".
  Failure: In that test H = 0, so the output has no head at all. The rewritten "…_with_the_first_bytes_…" test cannot assert a head unless `BASH_TAIL_OUTPUT_BYTES` is patched too. Separately, a command that prints exactly MAX bytes and then hangs is told "the middle of the output is not shown" although nothing was dropped.
  Smallest fix:
  - Use `T = min(TAIL, MAX // 2)`.
  - Show the timeout marker only when the bytes seen exceed H + T.
  - In §13, tell the test author to patch both constants.

R-10 [Minor] [L5] §10 EC-8.5 — The fingerprint blind spot is the filesystem timestamp tick, not "the same nanosecond"
  Evidence: EC-8.5: "A file modified within the same nanosecond with the same size … A stale row, rare."
  Failure:
  - mtime resolution is about 2 s on FAT/exFAT, 1 s on many network shares, and about 1–4 ms (kernel tick) on ext4.
  - A `bash` `sed -i` that changes "49 USD" to "59 USD" keeps the size. If it lands within one tick of the last indexed write, `search_memory` serves the old price until the next differing write.
  Smallest fix: Restate EC-8.5 as "same timestamp tick (ms to 2 s, filesystem-dependent) and the same size, as with same-length numeric edits". The decision itself (mtime_ns + size) is settled and stays.

R-11 [Minor] [L9] §10 EC-7.6, §6 INV-4.5 — The children's cost claim is inaccurate, and their context loss is unstated
  Evidence:
  - EC-7.6: "Their cost per call is unchanged from `main`".
  - INV-4.5: "Every InfiniteMemory agent trims with … `low_watermark_tokens`=65,000".
  - Children's loop sets `max_iterations=500` (`vidbyte/agents/infinite/settings.py:123–129`), so their system string changes on every call and they never get a cache read (EC-9.4).
  Failure: Once over 90K, a generator or verifier now keeps 65–90K instead of about 90K. Its per-call cost is lower than on `main`, not unchanged, and it gives up to 25K tokens of history mid-task for no cache benefit. A reader cannot see this tradeoff.
  Smallest fix: Reword EC-7.6 to state that children trade up to S tokens of history for fewer billed tokens and get no cache gain. This flags a risk only; the settled trim targets stay.

R-12 [Minor] [L4] §16 A-6, EC-9.9, §9.2 — The backend path is wrong, and forwarding is verifiable in code
  Evidence:
  - The spec cites "backend `generative_gateway/client.py:259-277`".
  - The file is `C:/Users/422mi/vidbyte-repos/vidbyte/backend/provider/generative_models/client.py`, which has `_require_short_cache` at :260–276 and Anthropic `allowed_fields` at :119.
  - A-6 says "forwarding is not verified live". In code, `plan()` builds `wire = {**body, "model": request.model}`, and `send` posts `plan.wire` unchanged.
  Failure: The next agent looks in a path that does not exist, and A-6's "If wrong" branch looks likelier than the code shows.
  Smallest fix: Correct the path. Change A-6 to "forwarding verified in `client.py` `plan()`/`send()`; not verified with a live key."

VERIFIED CLAIMS
- The per-call counter is in the system string: `runtime.py:1596` `_build_iteration_call_options` → `_render_loop_settings_block` (:1679, `- max_iterations: {n}/{max}`) → `_build_system_string` (:1668, fixed + loop block + primitives + body) → `setdefault("system", …)`. HELD.
- Status-message precedent: `runtime.py:670` appends `{"role":"user","content":review.feedback}` after tool results. HELD.
- EC-7.3: the contract-rejection and finish-review CONTINUE paths skip `_after_tool_iteration` (:925, "may append to messages"). HELD.
- The root's prompt is inserted at index 0. `_apply_before_model_call_transform` (:1085–1110) swaps only `messages` and adjusts `prompt_index`; the root's boundary is 0. HELD.
- `state.iteration_count` is incremented after the model call (:471), so the counter in the status message is the next call's value. HELD.
- The gateway admits block-level marks: `_require_short_cache` walks every node, refuses non-dict `cache_control`, and accepts a `ttl` only from `{"5m"}`. `cache_control` is not a top-level allowed field. HELD. Forwarding is unchanged in code (`plan`/`send`). HELD; A-6 understates it (R-12).
- Anthropic adapter: `_attach_instructions` sends `system` as a string, and `_attach_extra_body` runs last in `_create_payload` (`vidbyte/providers/anthropic.py:54–63`). HELD.
- "This adapter instance": `TextModelRunner.__init__` builds the provider once, and the runner is cached per BaseAgent (`base.py:1659–1674`, `_runner_cache`; also `continual_trace.py:70`, `handoff.py:74`). HELD: the digest set persists across the root's runs, and children and retrievers start cold.
- Managed wire test (`test_managed_text_wire_contract.py:172–185`, `EMITTED_KEYS` :49): a fresh runner per call means no repeat and no marks, so it stays green. HELD.
- Moved classes: import sites and public API as listed in "gets right". The `TrimWithProviderBoundariesCompaction` nested `cost` and non-contiguous keep are at `strategies.py:594–636`, `ToolOutputSlidingWindowCompaction` is at :663–711, and `__all__` is at :994. HELD.
- `_provider_groups` pairs a tool call with its consecutive tool results; any other message, including the status message, is its own group. HELD.
- C006 baseline is 104 and `strategies.py:599` is already a finding. HELD (drives R-1).
- Budgets: `workspace` 332, `memory` 251 (149 headroom, matching D-16), `launch` 368/400 (32 headroom). The package has 8/8 `.py` files. `EXPECTED_LEAVES`=40 (:49), `PRESET_TOOLS` (:118/:373), registry test :378–390. HELD.
- §13 test list: `test_infinite_memory_workspace.py:340–372` reads `map_section(call.system)`, so it changes. `test_infinite_memory_resume.py:345` derives from `INFINITE_RESERVED_TOOL_NAMES`, so it adjusts itself. The other readers stay green. HELD.
- Bash code facts (`bash.py` constants :33–36, timeout path and marker :130–138, `_collect` :176–193, `_render` :236–240) match the spec. HELD. `process_bounds.py:244` patches MAX to 1,000. NEW (R-9).
- `FileSystemPermissions.resolve_scoped_path` follows symlinks and refuses escapes. HELD (covers `../secret`, not superseded or journal files, see R-4).
- `OverwriteLineLimit` is referenced only by `vidbyte/tools/toolsets/coding.py:6,28,90` and by no test, so the rename is safe. `read_lines.py` matches §4. HELD.
- Lint scope: S047 = ASYNC230 and S052 = ASYNC100/105/110/220/221. Neither covers `sqlite3`. HELD (R-5).
- A-2 (a user message after tool results): Anthropic merges consecutive user turns, OpenAI Responses accepts it, and Gemini keeps a separate user turn after function responses. HELD as an assumption.
- The AC-1 snippet's `ToolCall(tool_name, arguments)` and `FileSystemTool(config)` signatures are valid. HELD.
- `REPO_MAP.md`, `artifacts/file_index.md` and `llms.txt` list no compaction or code_search filenames, so no map row is owed. HELD.
- "Index in memory per workspace" (request.md:112) vs "one per `search_memory` tool instance" (§9.1). DID NOT HOLD (R-5).
- AC-8.1 can produce a hit. DID NOT HOLD: porter turns "pricing" into "price", which is absent (R-8).
- AC-4.1 is consistent with INV-4.2. DID NOT HOLD (R-2).
