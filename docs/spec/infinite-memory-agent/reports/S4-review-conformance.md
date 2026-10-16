LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the PR builds every §12.3 row inside the §8.4 budget, and the §4 snippet runs exactly as written. Four gaps need fixing first: the pair error guard stops short of building the card, which breaks INV-29's "every"; and EC-18's guidance and NFR-7's card bound are not met.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- AC-1 holds when spec §4 runs verbatim and offline. The run prints the root's answer. `memory/seed/brief.md` equals `brief.md`. The three bookkeeping files exist, and the one journal holds `run_started` → `run_finished`. With one delegated pair, the journal holds `run_started, pair_started, pair_finished, run_finished`, and the entry carries `by=root/prices/gen` and `verified_by=root/prices/ver`. Leave `agent.py`, `runtime.py`, and the journal flow alone.
- The scope matches the spec exactly:
  - 18 added and 15 modified files, the same as §12.3's 18 CREATE and 15 MODIFY rows. No file outside §12.3 is touched.
  - `tests/` and `lint/` are byte-identical to S2_HEAD `d8bcdf14`, and `lint/baseline.json` has no diff against main.
  - `base.py` changes only the frozenset member, its comment clause, and the header line.
  - There is no new dependency, error class, settings field, prompt leaf, enum member, or record field. No §3 non-goal is implemented.
- Batch and journal semantics follow INV-9/10/11/25/26 and D-22/D-25:
  - The whole batch is validated before any `pair_started` record is written.
  - A finished key replays its card with the label.
  - `agents_started` counts journal records, including those from before a resume.
  - A torn tail is skipped, then truncated before the next append. A complete tail without its newline gets its newline (probe below).
- The user-facing weighted words are honored:
  - The root prompt says "Ruthlessly delegate work to subagents".
  - Depth and parallelism default to 10.
  - The verifier runs after its generator and holds the same writing tools.
  - A pair's entries are staged and committed only after a verdict.
  - No prompt leaf carries a coding, repo, or worktree rule.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [every ID / weighted word] vidbyte/agents/infinite/launch.py:247-254 — a ConfigurationError raised while building the result card escapes the pair's guard. The launch_subagent call then fails, the sibling cards are not returned, and the key never gets pair_finished. This violates INV-29 ("a pair turns every VidbyteSdkError … into its own card", "building the card") and row 20 ("One try/except … spans its whole body"), and §17 does not report it.
  Evidence:
  - The guard ends at launch.py:244, `except (VidbyteSdkError, OSError, ValueError) as exc:`. Lines 251-253 then run outside it: `files = tuple(dict.fromkeys((*writer.files_written, *checker.files_written)))`, `self.result = InfiniteResultCard(...)`, and `launch.journal.pair_finished(self.key, self.result)`.
  - `vidbyte/lib/dataclasses/infinite.py:208` calls `_text_items(self, "files")`, which defaults to `one_line=True` and so refuses any path where `str.splitlines()` sees a break.
  - `workspace.py:281-286` (`_note_path`) accepts any path inside the root that has an allowed suffix.
  - Probe `probe_card_guard.py`: a generator calls `write_note(path="notes/a\u2028b.md", …)`. The result:

    ```
    launch result: "[tool_error kind=execution_error]\nTool execution failed: Each item of InfiniteResultCard.files must be one line of non-blank text; got 'notes/a\\u2028b.md'."
    events: [('run_started', None), ('pair_started', 'root/x'), ('pair_started', 'root/y'), ('pair_finished', 'root/y'), ('run_finished', None)]
    note exists: True
    ```
  Failure: a generator writes a note whose path holds U+2028, U+0085, or (on POSIX) "\n". The file is created, and `files_written` records the raw path. `InfiniteResultCard` then raises a ConfigurationError, which is a VidbyteSdkError, after the guard. Four things follow:
  - `ParallelPipeline`'s `gather` raises.
  - The root receives an execution error instead of two cards, so sibling `y`'s finished card never reaches it.
  - `root/x` keeps `pair_started` with no `pair_finished`, so it runs again on a relaunch.
  - A sibling still running when `gather` raises is orphaned, which is EC-41's duplicate-key hazard. The spec accepted that hazard only for exceptions outside the three guarded classes.

  This also contradicts the field guide `jev-capability-layout.md`: "Wrap the whole loop in one try/except VidbyteSdkError at the function's top level".
  Smallest fix:
  - In `InfiniteWorkspace._note_path`, refuse any path where `path.splitlines() != [path]` with a ToolExecutionError. Every other recorded text is one line, so `files_written` can then never fail the record.
  - Move the `InfiniteResultCard(...)` construction inside the guarded block, as row 20 states.
  Spec IDs: INV-29, FR-9, FR-12, §12.3 row 20, INV-20, EC-41.

R-C2 [Major] [request fidelity / EC] vidbyte/lib/dataclasses/infinite.py:41-44 (reached from vidbyte/agents/infinite/memory.py:171-177) — when `remember` refuses a pasted multi-line log, the error echoes the whole paste back into the agent's context. Neither this message nor the token-cap message (workspace.py:261) tells the model to store a pointer or a note, which EC-18 specifies.
  Evidence:
  - `raise ConfigurationError(f"{type(record).__name__}.{name} must {rule}; got {value!r}.", …)`.
  - workspace.py:261 says only "…over max_entry_tokens (60); shorten it to one short line."
  - Probe `probe_ec18.py`:

    ```
    --- multi-line log: 12507 chars; mentions pointer/note: False
    Nothing was saved, because the call needs a change: InfiniteEntryDraft.text must be one line of non-blank text; got '2026-10-15 ERROR worker 0 failed: …
    --- long line: 239 chars; mentions pointer/note: False
    ```
  Failure: an agent pastes a 200-line log into `remember` (the EC-18 trigger). The tool result repeats about 3,100 tokens of log, so the waste doubles in a context the user called "VERY limitied". The model gets no hint to write the content with `write_note` and remember a pointer, so the EC-18 row "User sees: ToolResult.error telling it to store a pointer or a note" is not met.
  Smallest fix:
  - In `InfiniteRememberTool._draft`, refuse text that is not one line with a ToolExecutionError that does not echo the text and says to save the content with `write_note` and remember a `pointer` entry.
  - Add the same advice to the token-cap message at workspace.py:261.
  Spec IDs: EC-18, INV-17, INV-32, NFR-7; request.md §D "VERY limitied".

R-C3 [Major] [weighted words / NFR] vidbyte/agents/infinite/launch.py:362 — a pair's card can add far more than NFR-7's bound of "2 × INFINITE_CARD_TEXT_MAX_TOKENS tokens of card text, plus the fixed card template", because `dropped` and `files` are rendered uncapped.
  Evidence:
  - `render` joins `"; ".join(card.dropped)` and `", ".join(card.files)` with no cap.
  - launch.py:249 and memory.py:115 copy each staged entry's full text into `dropped`.
  - memory.py:98 and :105 add every path a child appended to or edited.
  - Probe `probe_card_size.py`, with 5 staged entries, no verdict, and 40 appended notes:

    ```
    card tokens: 1603
    NFR-7 bound (2 x cap + template): 843
    files line tokens: 574
    dropped line tokens: 203
    ```
  Failure: this happens on the ordinary EC-12 path. A verifier omits its VERDICT line after the generator staged 5 entries of 60 tokens, and every entry is listed in `dropped`. That adds about 375 tokens, so the card is about 1,220 tokens against an 843 bound. A child that appends to many notes grows the card without limit, up to `max_files` paths. Every such card lands in the root's context, which the user called "VERY limitied".
  Smallest fix:
  - In `InfinitePair.render`, cut the "Entries dropped" and "Files written" values with `_capped`, using the same cap and marker.
  - Amend NFR-7 so its target names the capped fields.
  - If the spec author accepts the larger card instead, NFR-7 alone needs amending.
  Spec IDs: NFR-7, INV-4, D-14; request.md §D "VERY limitied".

R-C4 [Major] [out-of-lens] vidbyte/agents/infinite/workspace.py:281-285 — the protected-path checks compare case-sensitively. On a case-insensitive file system where `Path.resolve()` keeps the caller's case (macOS APFS, the default), `write_note`/`edit_file` on "Entries.jsonl", "SEED/brief.md", or ".RUNS/x.jsonl" pass the checks and write into a bookkeeping file, a seed, or the journal folder. This breaks INV-21's "Tools never write under seed/" and INV-20.
  Evidence:
  - `vidbyte/lib/tools/filesystem/permissions.py:16` resolves with `(root / Path(path)).expanduser().resolve()`.
  - workspace.py:281 checks `target.suffix not in INFINITE_NOTE_SUFFIXES`, which is case-sensitive.
  - workspace.py:284 checks `relative.parts[0] in (INFINITE_SEED_DIRNAME, INFINITE_RUNS_DIRNAME) or relative.as_posix() in (INFINITE_ENTRIES_FILE, …)` against lowercase constants.
  - It is not reproducible on this Windows host. `probe_paths.py` shows Windows `resolve()` returning the on-disk case, so all seven variants are refused. `posixpath.realpath` (macOS) resolves only symlinks and keeps the given case.
  Failure: prompt-injected text (T-2) leads an agent on macOS to call `write_note("Entries.jsonl", "x")`. The file exists, so the text is appended to `entries.jsonl` as a malformed line, and every later entry operation is refused until the line is repaired with bash. `"SEED/brief.md"` appends to a seed, which INV-21 says never happens.
  Smallest fix: compare case-folded values: `relative.parts[0].casefold()`, `relative.as_posix().casefold()`, and `target.suffix.casefold()`.
  Spec IDs: INV-20, INV-21, T-2.

R-C5 [Minor] [deviations] vidbyte/agents/infinite/launch.py:227-231 — the `await asyncio.sleep(INFINITE_PAIR_TURN_SECONDS)` yield is in no spec row. It exists only so that AC-37's Given is reachable with fake runners that never suspend. Its @intent comment and the §17 entry claim an ordering guarantee that does not hold, and the claim that AC-5 needs it is false.
  Evidence:
  - The comment says "@intent sibling-generators-finish-before-verifiers-judge … every generator has staged before a verdict".
  - spec.md:1229 says "so every generator in a batch stages before any verifier commits, even with runners that never suspend (AC-5, AC-37)".
  - Run with the yield swapped for a coroutine that never suspends (plugin `s4_nosleep.py`): `1 failed, 88 passed`. Only `test_a_malformed_entries_line_drops_each_pairs_entries_but_the_run_finishes` (AC-37) fails, with `AssertionError: []`. Generator b's `remember` was refused at staging because the corruption had already landed. AC-5 passes without the yield.
  Failure: with real runners, generator b may still be awaiting its model call when pair a's verifier returns and commits. A `sleep(0)` cannot hold pair a back, so "every generator has staged before a verdict" is false in production. A maintainer who trusts the @intent could build cross-sibling logic on a guarantee that does not exist.
  Smallest fix:
  - Keep the yield, but reword the comment and the §17 line to "a fairness yield between generator and verifier; no ordering guarantee".
  - Drop the AC-5 attribution.
  Spec IDs: INV-12, AC-37, AC-5, §17.

R-C6 [Minor] [boundaries] vidbyte/lib/registries/runtimes.py:53 — the PR merges the untouched "Unknown runtime type" f-strings into one, outside row 25's stated change. The merge only offsets the new S062 finding that S2's test adds, so the ratchet count hides a new violation.
  Evidence:
  - The hunk replaces the two adjacent f-strings with `f"Unknown runtime type '{runtime_type.value}'. Supported: {cls.supported_runtimes()}"`.
  - `python lint/run.py --rule S062 --all` lists `tests/features/infinite_memory_agent/test_infinite_memory_workspace.py:399 writes one string as 3 adjacent literals that Python joins implicitly.`
  - The baseline `"S062": 889` stays at 889.
  Rule: AGENTS.md, General Coding Style: "Do not rewrite untouched code just to make it conform; that belongs in its own pull request." §12.3 row 25 lists only the lazy import and the registry row. A human reviewer would write: "fix the new implicit concatenation in the test instead of rewriting an unrelated error message to keep the count flat."
  Smallest fix:
  - Restore main's two message lines in runtimes.py.
  - Join the three literals at test_infinite_memory_workspace.py:399 into one string. This changes only the test's layout, not its strength, but §14 requires asking first.
  Spec IDs: §12.3 row 25, NFR-6, §14.

R-C7 [Minor] [deviations] vidbyte/agents/infinite/launch.py:249, :297, :305; memory.py:115; workspace.py:204 — the "short fixed text in code" deviation was not needed. §9.2 says short fixed labels are `INFINITE_` constants, not inline literals, and S3 was free to add constants (it added three). These model-facing formats now sit outside both the prompt family (FR-13) and the constants module:
  - `"…: not committed, because the verdict is {v}"`
  - `"…: dropped by the verifier"`
  - the map line `"- {path} ({tokens} tokens): {label}"`
  - the pasted entry `"#{id}: {text}"`
  - the staged line `"- {key} ({kind}): {text}"`

  The INFINITE_FINISHED_PAIR_LINE label, in contrast, is a constant.
  Evidence: the five literals at the cited lines. §9.2 line 755 says "Short fixed labels are INFINITE_ constants, not prompts". §17 calls them "not prompt leaves" but does not say why they are not constants.
  Rule: §9.2 and FR-13 ("every model-facing sentence"). A reviewer would ask that these move beside INFINITE_FINISHED_PAIR_LINE.
  Smallest fix: add the five formats to `vidbyte/lib/constants/infinite.py` and `.format` them by name.
  Spec IDs: FR-13, §9.2, §17.

VERIFIED CLAIMS:
- S3: "89/89 pass" — HELD. The pack gives `89 passed in 2.06s`.
- S3: "`python lint/run.py` → SDK-LINT: PASS" — HELD, with S062 at 889/889 (but see R-C6).
- S3: "both run_ci stages pass" — the full suite was run instead, and the source result HELD: `5262 passed, 14 skipped`. One earlier `-x` run failed `tests/test_mcp_stdio_transport.py::…test_cancelled_waiter_does_not_break_transport`. On rerun it failed once and passed twice. That test is flaky, and the PR does not touch MCP.
- S3 and §17: "budget 18/18 new files; no file outside §12.3" — HELD. The name-status shows 18 A and 15 M, all §12.3 paths. The classes count 14 behavior + 1 helper + 6 records + 6 enums = 27.
- §17: "nothing under tests/ changed" — HELD. `git diff d8bcdf14 def85360 -- tests/ lint/` is empty, and `git diff origin/main...def85360 -- lint/baseline.json` is empty.
- S3: "largest module launch.py 358 lines after header (cap 400)" — HELD (370 total − 12 header). Every new `.py` file has a 12-line header.
- Row 12: "40 members; header 138 assets across 34 families" — HELD. The enum counts 40 INFINITE_MEMORY_* members, 138 members in all, and 34 families.
- AC-1 test "runs the snippet as written" — HELD. The test body pastes §4 verbatim. `snippet.py` also ran the verbatim snippet through the fake-runner seam and printed the answer with the documented workspace.
- S3 and §17: "the sleep is load-bearing for AC-5 and AC-37" — PARTLY FALSE. Only AC-37 needs it (R-C5).
- S3: "Errors are caught as VidbyteSdkError, OSError, or ValueError. The pair writes pair_finished" — DOES NOT HOLD for the card-building step (R-C1). The deviation is unreported.
- §17 deviation 6 (journal tail) — HELD. In `probe_journal.py`, both a torn tail and a newline-less complete tail end as `['run_started', 'pair_started', 'run_finished']`.
- The §17 deviations, judged one by one:
  - (1) The three constants are needed for A007. INFINITE_PAIR_TURN_SECONDS exists only for the R-C5 yield.
  - (2) `check_entry` taking staged records is needed to name "sN". It is minimal and recorded.
  - (3) Making `quota()` public, the routing methods, and `render`/`finished_lines` are minimal and recorded.
  - (4) Inline labels were not needed (R-C7).
  - (5) Whole-file temp+replace for appends is defensible: a torn append would otherwise make entries.jsonl unreadable. It is recorded. The `at` stamp `+00:00` is still ISO-8601.
  - (6) Needed, as verified above.
  - (7) Outside row 25 (R-C6).
  - (8) Benign.
  - Unreported: the card-build guard gap (R-C1) and the EC-18 message (R-C2).
- §5 diagram vs the call path:
  - It matches node by node: clash check → journal → run-bound tools → clean context → map → loop → `run_finished`, and in `launch_subagent`, validate → `pair_started` → `ParallelPipeline` → gen → ver → commit → `pair_finished` → cards.
  - Divergences: the extra `asyncio.sleep(0)` between G and V, and the card build plus `pair_finished` outside the pair's guard.
- The ID walk:
  - Every FR (1–17), INV (1–39), and AC (1–42) has matching code, and its test passes.
  - These do not hold: INV-29 and FR-12 (R-C1), EC-18 (R-C2), NFR-7 (R-C3), and INV-20/21 on case-insensitive POSIX (R-C4).
  - NFR-4 ("reads the workspace at most once") holds only loosely. `commit_entry` reads entries.jsonl and superseded.jsonl, then `_file_tokens()` reads them again, so a write can read up to about 2× the bookkeeping volume. This only affects speed and is not raised as a finding.
- request.md §A/§C fidelity:
  - Nothing the user asked for is missing apart from the declared non-goals and Q defaults.
  - There is no scope creep beyond the recorded deviations.
  - No §C decision was reversed: verifiers cannot launch, staging is kept, root writes commit at once, and both prompts are required.

COMMANDS RUN:
- `git diff --stat origin/main...def85360` → `54 files changed, 8323 insertions(+), 28 deletions(-)`
- `git diff --stat d8bcdf14 def85360 -- tests/ lint/` → (empty); `git diff origin/main...def85360 -- lint/baseline.json | wc -l` → `0`
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `89 passed in 2.06s`
- `PYTHONPATH=$(pwd) python lint/run.py` → `S062 RATCHETED: 889 known finding(s)` … `SDK-LINT: PASS`
- `PYTHONPATH=$(pwd) python lint/run.py --rule S062 --all` → `tests/features/infinite_memory_agent/test_infinite_memory_workspace.py:399 writes one string as 3 adjacent literals that Python joins implicitly.`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` → `5262 passed, 14 skipped in 46.56s` (an earlier `-x` run stopped on the flaky MCP stdio test; 2 of 3 reruns of that test pass)
- `python <scratch>/snippet.py plain` → `FINAL: Acme is cheapest.` / `seed equal: True` / `bookkeeping: ['entries.jsonl', 'files.jsonl', 'superseded.jsonl']` / `events: ['run_started', 'run_finished']`
- `python <scratch>/snippet.py delegate` → `events: ['run_started', 'pair_started', 'pair_finished', 'run_finished']`, card `Status: done. Verdict: passed.` `Entries saved: #1`
- `python <scratch>/probe_card_guard.py` → `launch result: "[tool_error kind=execution_error]\nTool execution failed: Each item of InfiniteResultCard.files must be one line…"`; `('pair_started', 'root/x')` with no `pair_finished` for it
- `python <scratch>/probe_ec18.py` → `multi-line log: 12507 chars; mentions pointer/note: False`
- `python <scratch>/probe_card_size.py` → `card tokens: 1603` / `NFR-7 bound (2 x cap + template): 843`
- `python <scratch>/probe_paths.py` → all 7 case variants refused on Windows (resolve() returns on-disk case)
- `python <scratch>/probe_journal.py` → both journals end `['run_started', 'pair_started', 'run_finished']`
- `PYTHONPATH="$(pwd);<scratch>" python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider -p s4_nosleep` → `1 failed, 88 passed` (AC-37 only)
- `<scratch>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/316f126c-6db0-45d5-b506-cdb76c0921d5/scratchpad/s4-conformance/`; every script runs with `PYTHONPATH=$(pwd)` from the worktree, with no network.
