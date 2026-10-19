LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every R-1..R-23 fix holds against its review.md evidence, but the R-7 seed-copy change introduced a regression that blocks a second setup over a persisting workspace when a seed is read-only, and the multi-file memory writes still break INV-19/INV-32 ("a refused write changes nothing") on paths the R-8 fix and its test never covered.

Scope: post-repair re-review of `origin/main...e2b76a60`, with full reads of every production file changed since `def85360` (launch, journal, workspace, memory, settings, agent, runtime, constants, dataclasses, registry, README, prompt JSON). `$S` below is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/316f126c-6db0-45d5-b506-cdb76c0921d5/scratchpad/s5-rereview`. Run each probe from the worktree as `PYTHONPATH=$(pwd) python $S/<script>`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- **R-1 holds on every path I could reach.** A U+2028 note path and a U+0085 note path are both refused. A lone surrogate in a generator reply, in a verifier review, or in a staged entry still returns both cards. The journal holds exactly one `pair_finished` per key (`{'root/a': 1, 'root/b': 1}`). An injected `OSError` inside `_finish`'s own journal write still returns both cards.
  - The guard is still exactly `(VidbyteSdkError, OSError, ValueError)`, so cancellation propagates. AC-23 passes.
  - Leave `InfinitePair._finish` and the ASCII journal alone.
- **R-4 batch admission is still check-then-reserve, with no `await` in between** (`launch.py:125-134`).
  - Replays skip only the tools, `#N` context, and `max_agents` checks.
  - The name check still covers the whole batch: `[a, a]` is refused.
  - The `max_parallel` check (`_cards`, line 156) still counts replays: `[a, c, d]` with `max_parallel=2` is refused.
  - A finished pair whose `#1` was later superseded replays, alone and beside a new task.
- **R-3, R-6, and R-10 conform as written.**
  - R-3: a card with 5 long dropped entries, 30 files, and 5,000-character summary and review renders at 1,597 tokens, under the r5 NFR-7 bound of 1,639. The journal card keeps all 5 dropped entries and all 30 files.
  - R-6: `remember` refuses a 300-line log in 79 tokens. The refusal carries the note-and-pointer advice and does not echo the log. A one-line entry is still accepted (AC-14).
  - R-10: all 23 description leaves are 4–5 sentences with no examples, and the family still has 40 leaves.
- **Scope and gates.**
  - The diff has 18 added and 15 modified non-test files, all of them §12.3 paths.
  - `tests/` holds only S2 additions, and `git diff 9af96d42..e2b76a60 -- tests/` is empty.
  - `lint/baseline.json` is untouched, and production code has no suppressions.
  - `python lint/run.py` ends `SDK-LINT: PASS` with C012 23, S061 5, S062 889, and S008 19.
  - The §4 snippet runs verbatim offline (AC-1).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Major] [request fidelity / INV-21] vidbyte/agents/infinite/workspace.py:79 — R-7's seed copy keeps a read-only seed's mode bits, so the second setup over the same workspace raises PermissionError, and a new agent on that `memory/` folder or a crash-resume from a new process cannot even be built (regression introduced by 29760f65)
  Evidence: `workspace.py:79` `self.backend.copy(Path(seed), self.root / INFINITE_SEED_DIRNAME / Path(seed).name)` → `vidbyte/lib/tools/filesystem/backends/local.py:73` `shutil.copy2(source, destination)`, which copies mode bits; the pre-R-7 code (`git show def85360:vidbyte/agents/infinite/workspace.py:79`) used `shutil.copyfile`, which does not. `python $S/ro_seed.py` (brief.md set read-only, §4 settings): `agent A built; run A: FINAL A` / `seed copy writable: False` / `agent B construction raised PermissionError: [Errno 13] Permission denied: '…\memory\seed\brief.md'` / `resume-process construction raised PermissionError: [Errno 13] …` / `copyfile copy writable: True`. No test builds an agent twice over one workspace with a seed (`grep -n seed_files tests/features/infinite_memory_agent/*.py`). The only record of the limitation is the KNOWN EDGE CASES line in `workspace.py:9`. The README and the spec do not mention it.
  Failure: a read-only developer seed, such as a mode 0444 file from Perforce, Nix, or Bazel, or a Windows read-only attribute, plus a persisting workspace (D-6, A-2), breaks two things.
    - A second `InfiniteMemoryAgent(settings)` raises a raw `PermissionError`. INV-21 says each seed "is copied, overwriting", and §9.2 says construction passes on only `ConfigurationError`.
    - The process that would `resume()` a crashed or killed run must build the agent first, so it fails the same way until a person runs chmod on `memory/seed/<name>`. Making the source writable does not help, because the old read-only copy blocks the overwrite.
    - This breaks the §4 promise "A second agent pointed at the same `memory/` folder sees everything the first one saved". It also breaks the weighted words "Unattended, resumable" for this class of input.
    - Rated Major, not Blocker, because:
      - it fails loudly at construction;
      - no workspace data is lost;
      - one chmod recovers it;
      - only read-only seeds trigger it.
  Smallest fix: after the copy at line 79, keep the copy writable for its owner, for example `destination.chmod(destination.stat().st_mode | stat.S_IWRITE)` with `destination` bound to the target path. Tools already never write under `seed/`, because `_note_path` enforces that, not the mode bits. S061 does not list `chmod` (`lint/rules/s061_bounded_safe_path.py:27-28`), so the ratchet is unaffected. Then drop the KNOWN EDGE CASES sentence. A regression test that builds twice over one workspace with a read-only seed needs a test change.
  Spec IDs: INV-21, D-24, D-6, A-2, §4 (last paragraph), AC-30 (with seeds), FR-4, FR-11; request.md §D "Unattended, resumable"

R-C2 [Major] [request fidelity / INV-19, INV-32] vidbyte/agents/infinite/workspace.py:146-147 and :172-173 — a refused memory write that touches two files can leave the first one written, while the model is told "Nothing was saved" (R-8 fixed the temp-file leak but not these partial writes)
  Evidence: the write loops `for relative, text in changed.items(): self._replace(relative, text)` (`commit_entry`, superseded file first) and `for name, content in changed.items(): self._replace(name, content)` (`write_note`, note first, then `files.jsonl`) encode each text only when that file is written. `python $S/partial.py` gives four results.
    - Root `remember(text="beta \ud800 replaces alpha", supersedes=1)` returns `"Nothing was saved, because the call needs a change: 'utf-8' codec can't encode character '\ud800' …"`.
    - `write_note("notes/a.md", description="first note \ud800")` returns the same "Nothing was saved …".
    - The next `write_note("notes/b.md", …)` returns `Saved the file notes/b.md … 0 of 1 new files`.
    - With `entries.jsonl` held open (Windows), the supersede returns `[WinError 5] Access is denied`.
    - The disk afterwards holds `notes/a.md: 'hello'` with no `files.jsonl` line (`files.jsonl paths: ['notes/b.md']`), and `live ids: [1] | superseded ids: [1, 1]`.
  The R-8 test (`test_a_memory_write_that_fails_on_disk_is_a_refusal_and_leaves_no_temp_file`, which asserts `states[0] == states[1]`) uses only single-file writes: a plain remember, an append, and an edit.
  `python $S/r1_guard.py` shows the same root cause at stage time. A pair agent's `remember("staged \ud800 fact")` is accepted (`Staged as s2`). Its commit then raises `ValueError`, which turns the verifier's `VERDICT: passed` into `Verdict: unchecked` and drops the valid `s3 (a third fact)`.
  Failure: the guarantee is broken in three places.
    - **Supersede plus an unencodable text, or a locked `entries.jsonl` on Windows.** The refused call still copies the old line into `superseded.jsonl`, and each retry adds another copy.
    - **New note plus an unencodable description.** The refused call still creates the note without a description, so the map shows "(no description)". The agent's new-file allowance is not spent, so one agent creates 2 new files against `INFINITE_NEW_FILES_PER_AGENT = 1`. For a pair agent the path is also missing from `files_written`, so neither its verifier nor its card lists a file that was written.
    - **Claims that are false.** Each case contradicts INV-19 "A refused write changes nothing on disk", INV-32 "The call writes nothing", the README line 70 "a refused write changes nothing", the `memory.py:5` header "so a refused call changes nothing", and the model-facing "Nothing was saved".
    - This is not a regression (S3 wrote in the same order), but no S4 finding named it.
  Smallest fix:
    - In `commit_entry` and `write_note`, encode every value of `changed` (`text.encode("utf-8")`) before the first `_replace`. A lone surrogate then raises `UnicodeEncodeError`, a `ValueError` the tools already turn into a refusal, before any byte is written.
    - Do the same for `draft.text` and `refs` in `_entry_rules`, so staging refuses what could never commit.
    - For the Windows-lock case (an `OSError` on the second `os.replace`), choose one: write the first file back from the text already read under the lock, or name it as a crash-equivalent limitation in INV-19 and the README.
    - Add the supersede and new-note cases to the R-8 test. That needs a test change.
  Spec IDs: INV-19, INV-20 (per-agent new-file cap; a description is required on create), INV-32, INV-12 (the verifier receives the paths the generator wrote), FR-5, FR-6; review.md R-8

R-C3 [Minor] [deviations] vidbyte/agents/infinite/workspace.py:280-290; vidbyte/agents/infinite/settings.py:206-213; vidbyte/lib/constants/infinite.py:28; vidbyte/agents/infinite/journal.py:190 — the repair added contract rules that spec r5 never recorded
  Evidence: `grep -n "colon\|ProviderModelRegistry\|INFINITE_MIN_CAP\|ASCII\|copy2" docs/spec/infinite-memory-agent/spec.md` finds none of them. §17 lists only S3 deviations, and r5 (8d6c230a, 08:19) predates the repair commits. The new rules are:
    - INV-20 lists the note-path rules, but `_note_path` now also refuses multi-line paths and paths containing a colon. The `note_path_description` leaf already tells the model.
    - §9.3 says `model_name` has the "same meaning as `BaseAgent`", but `_validate_model` now refuses any model `ProviderModelRegistry` does not catalog at construction. My probe: `openai/gpt-4.1-2025-04-14` and `anthropic/claude-sonnet-4-5` are refused by the settings, yet `BaseAgent(...)` constructs and `_runner_for_model()` returns a `TextModelRunner` for both. This matches the `JevAgentSettings._validate_model` precedent and the `vidbyte/config` strict policy, but neither AC-2 nor §9.3 says it.
    - `INFINITE_MIN_CAP` is not in row 3 or §17.
    - The journal is now ASCII-escaped JSON, which §9.1 and D-25 do not mention.
    - D-24's seed copy now keeps permission bits (see R-C1).
  Failure (convention): a reader of the spec or the folder README cannot learn these rules. A developer with a dated model snapshot gets a construction-time refusal that no doc mentions, and the escape hatch `ProviderModelRegistry.STRICT_MODEL_VALIDATION = False` is undocumented here. A human reviewer would write: "record what the repair changed in the contract".
  Smallest fix:
    - Add an "S5 repair deviations" list to §17 with the five items.
    - Add "one line, no colon" to INV-20.
    - Add one clause to §9.3 and to the README's limits list, naming the catalog check and the escape hatch.
    - This needs a spec edit and no code.
  Spec IDs: INV-20, §9.3, AC-2, §12.3 row 3, §17, D-24, D-25

VERIFIED CLAIMS:

1. **AC-1, §4 snippet verbatim offline:** held. Plain mode prints `FINAL: Acme is cheapest.`, `seed equal: True`, the three bookkeeping files, and events `run_started … run_finished`. Delegate mode commits `by=root/prices/gen` and `verified_by=root/prices/ver`. The `openai`/`gpt-4.1` pair passes R-7's model check.
2. **R-1 (1e0b1524), INV-29 "every":** held.
   - Note paths with U+2028 and U+0085 are refused.
   - Surrogates in a reply, a review, and a staged entry still return both cards, with `pair_finished` once per key.
   - Errors inside `_finish` (my `$S/r1_finish_fault.py` injection):
     - When the journal write fails before writing, there is one record per key, and the sibling's card is intact.
     - When it fails after the line reaches disk (an fsync-style failure), `root/a` gets 2 records (`passed`, then `unchecked`). The journal re-reads without error and keeps the last one.
     - That corner is harmless and sits next to EC-41, so it is not a finding.
3. **R-2 (1769a44f):** held in simulation. With `resolve_scoped_path` patched to keep the caller's spelling, `Entries.jsonl`, `SEED/brief.md`, and `.RUNS/x.jsonl` are refused and `notes/ok.md` is accepted.
4. **R-3 (a47a7614), r5 NFR-7:** held. The card is 1,597 tokens against a bound of 1,639. The journal keeps 5 dropped entries and 30 files. The `Files written` line ends with the marker.
5. **R-4 (a6b4e4c1):** held. Replay works alone and beside a new task. `max_parallel`, duplicate-name, and `max_agents` refusals still fire. No `await` sits between `_check` and `pair_started`.
6. **R-5 (c4822ebb):** held. `git diff origin/main...e2b76a60 -- vidbyte/lib/registries/runtimes.py` shows only the import and the registry row, and S062 is 889.
7. **R-6 (3617ec69), EC-18:** held. The refusal is not stricter than before.
   - A trailing-newline entry was already refused by `InfiniteEntryDraft`'s one-line rule at `def85360`.
   - That refusal now says "spans several lines", which is cosmetic.
   - The legitimate one-line entry is accepted for the root and for a generator.
8. **R-7 (29760f65, 5ee09e99):** the lint goal held (C012 23 and S061 5 equal main). The seed copy regressed (R-C1). The model check refuses uncatalogued snapshots that `BaseAgent` accepts (R-C3).
9. **R-8 (f8387a78):** partly held.
   - No temp file is left, and every failure is a clean refusal with the quota line (`-k memory_write_that_fails_on_disk` gives 6 passed, and `-k note_path_with_a_colon` gives 1 passed).
   - "Changes nothing" does not hold for multi-file writes (R-C2).
10. **R-9 (99e95803):** held. The awk check prints no comment line over 72 columns in any new module. The one wide line left is in base.py's legacy block, whose finding the verifier refuted.
11. **R-10 (fddefd51):** held. Every parameter leaf has 4 sentences, every tool leaf 5, none has an example, and `{max_parallel}` is kept.
12. **R-11 and R-18 (9af96d42):** held. Those tests exist and pass.
13. **Trivial Minors:** held.
    - R-12 (61bdbb6b): `finished` is computed in `run`.
    - R-13 (6b55613c): the `@intent` comment now says "fairness only".
    - R-15 (649777fa): `INFINITE_MIN_CAP` is used.
    - R-16 (9c5b0650): the header says "below".
    - R-17 (c5f4859f): the README says "oldest … first".
    - R-21 (714c1aa0): the spacing is fixed, and the Jev rows are contiguous from line 68 on.
    - R-23 (5cdac067): the error message no longer carries `{settings!r}`.
14. **Implementer claim "107 passed" and the per-finding `-k` counts (3, 1, 1, 2, 6, 1):** all held.
15. **Implementer claim "`git diff 9af96d42..HEAD -- tests/` is empty":** held.
16. **Briefing claim "every rule count equals origin/main":** held for the counts shown. The final line is `SDK-LINT: PASS`.
17. **§8.4 budget:** held.
    - 18 new files.
    - 26 classes plus `TokenEstimate`.
    - `launch.py` is 384 lines without its header, under 400.
    - No new dependency.
18. **§14 "Never":** held. There is no baseline edit and no suppression, and no test was weakened.
19. **§5 diagrams against the call path:** no divergence. `pair_finished` is now written inside `InfinitePair`'s guard, as the sequence diagram's ordering implies.

COMMANDS RUN:

- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `107 passed in 3.02s`
- `PYTHONPATH=$(pwd) python lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS`
  - C012 23/24 IMPROVED
  - S061 5/6 IMPROVED
  - S062 889 RATCHETED
  - S008 19 RATCHETED
- `pytest … -k card_or_record_cannot_be_written | long_dropped_and_files_lists | replays_after_its_context_entry_was_superseded | keep_a_long_paste_in_a_note | memory_write_that_fails_on_disk | note_path_with_a_colon` → `3 passed`, `1 passed`, `1 passed`, `2 passed`, `6 passed`, `1 passed`
- `python $S/snippet.py plain` → `FINAL: Acme is cheapest.` / `seed equal: True` / `events: ['run_started', 'run_finished']`
- `python $S/snippet.py delegate` → `events: ['run_started', 'pair_started', 'pair_finished', 'run_finished']`
- `python $S/ro_seed.py` → `seed copy writable: False` / `agent B construction raised PermissionError: [Errno 13] …` / `resume-process construction raised PermissionError …` / `copyfile copy writable: True`
- `python $S/partial.py` → `notes/a.md: 'hello'` / `files.jsonl paths: ['notes/b.md']` / `live ids: [1] | superseded ids: [1, 1]`
- `python $S/r1_guard.py` → `pair_finished per key: {'root/a': 1, 'root/b': 1}` / `notes on disk: ['notes/ok.md']`
- `python $S/r1_finish_fault.py before-write` → `{'root/a': 1, 'root/b': 1}`
- `python $S/r1_finish_fault.py after-write` → `{'root/a': 2, 'root/b': 1}` / `journal re-reads; root/a card verdict: unchecked`
- `python $S/r4_replay.py` → replayed ×3, `over max_parallel (2)`, `Two tasks are named a`, `would start 2 agents after the 6 already started`; agents called a, b, and e only
- `python $S/r3_card.py` → `rendered card tokens: 1597 | NFR-7 bound …: 1639` / `journal card: dropped 5 items, files 30 items`
- `python $S/r6_ec18.py` → multi-line: error, 79 tokens, advice True, no echo; legit one line: success (root and generator)
- An inline script that simulates `resolve_scoped_path` keeping the caller's spelling → three protected spellings refused, `notes/ok.md` accepted
- An inline script that builds settings for several models → `gpt-4.1-2025-04-14` and `anthropic/claude-sonnet-4-5` refused; `BaseAgent` constructs both, and `_runner_for_model()` returns a `TextModelRunner` for both
- `git diff origin/main...e2b76a60 -- lint/ | wc -l` → `0`
- `git diff --name-status origin/main...e2b76a60 -- tests/` → 10 files, all `A`
- `git diff --stat 9af96d42..e2b76a60 -- tests/` → empty
- awk check for comment lines over 72 columns → only `vidbyte/agents/base.py`'s legacy block
- `git status --porcelain` → empty
