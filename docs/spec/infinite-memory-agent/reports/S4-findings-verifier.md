# S4 findings verifier — infinite-memory-agent

- **Diff:** `origin/main...def85360`. HEAD `7ffe2067` differs from `def85360` only in `docs/`.
- **Inputs read:**
  - the three S4 reviews;
  - the spec, r4: Part A, all of Part B, §8.1/8.4/8.5, §9.1–9.3, §10, §12.3, §12.4, §13, §14, §16, and §17;
  - the test plan's coverage map and its "NOT written" list;
  - AGENTS.md, house-style.md, and the review.md format;
  - the field-guide entries `comment-format.md`, `model-facing-tool-contracts.md`, and `jev-capability-layout.md` (index);
  - lint/README and the S025/S061 rule sources.
- **Own scripts** are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/316f126c-6db0-45d5-b506-cdb76c0921d5/scratchpad/s4-verifier/`, abbreviated `$S`:
  - probes `v1_card_guard.py`, `v2_replace_leak.py`, `v3_colon_unc.py`, `v4_replay.py`, `v5_ec18_card.py`, `v6_case_fold.py`, and `v7_locked_file.py`;
  - the mutation plugin `vmut.py`;
  - the fix-trial plugin `vfix.py`;
  - `base/`, an export of origin/main;
  - `head/`, an export of `def85360` with the R-7 fix applied.
- **Nothing in the worktree was edited** except `review.md` and this report.

## 1. Merge map (original IDs → merged IDs)

| Original | Lens | Original severity | Merged | Final severity | Disposition |
|---|---|---|---|---|---|
| R-C1 | conformance | Blocker | R-1 | Blocker | CONFIRMED (same root cause as R-E1) |
| R-E1 | engineering | Blocker | R-1 | Blocker | CONFIRMED |
| R-C4 | conformance | Major | R-2 | Major | CONFIRMED (simulated macOS + source evidence) |
| R-C3 | conformance | Major | R-3 | Major | CONFIRMED, needs spec edit (NFR-7) |
| R-E7 | engineering | Minor | R-3 | Major | merged into R-C3; highest severity kept |
| R-E3 | engineering | Major | R-4 | Major | CONFIRMED |
| R-V2 | conventions | Major | R-5 | Major | CONFIRMED, needs test change |
| R-C6 | conformance | Minor | R-5 | Major | merged into R-V2; highest severity kept |
| R-C2 | conformance | Major | R-6 | Major | CONFIRMED |
| R-V1 | conventions | Major | R-7 | Major | CONFIRMED; fix proven in a scratch copy |
| R-E2 | engineering | Major | R-8 | Major | CONFIRMED in part; the `_commit` sub-claim is REFUTED |
| R-E9 (colon path part) | engineering | Minor | R-8 | Major | the colon trigger is the same leak; folded into R-8 |
| R-V5 | conventions | Major | R-9 | Major | CONFIRMED for 21 lines; the base.py part is REFUTED |
| R-V3 | conventions | Major | R-10 | Major | CONFIRMED (19 leaves, not 18) |
| R-E4 | engineering | Major | R-11 | Major | CONFIRMED, needs test change |
| R-V4 | conventions | Major | R-12 | Minor | DOWNGRADED |
| R-C5 | conformance | Minor | R-13 | Minor | merged |
| R-E5 | engineering | Minor | R-13 | Minor | merged |
| R-V7 | conventions | Minor | R-13 | Minor | merged |
| R-C7 | conformance | Minor | R-14 | Minor | merged |
| R-V6 | conventions | Minor | R-14 | Minor | merged |
| R-V8 | conventions | Minor | R-15 | Minor | passed through |
| R-V9 | conventions | Minor | R-16 | Minor | passed through |
| R-V10 | conventions | Minor | R-17 | Minor | passed through |
| R-V11 | conventions | Minor | R-18 | Minor | passed through, needs test change |
| R-V12 | conventions | Minor | R-19 | Minor | passed through |
| R-V13 | conventions | Minor | R-20 | Minor | passed through |
| R-V14 | conventions | Minor | R-21 | Minor | passed through |
| R-E6 (+ conformance NFR-4 note) | engineering | Minor | R-22 | Minor | passed through |
| R-E8 | engineering | Minor | R-23 | Minor | passed through |
| R-E9 (UNC part) | engineering | Minor | R-24 | Minor | passed through; pre-existing helper |
| — | verifier | — | R-25 | Minor | new [verifier] finding |

Totals: 1 Blocker and 10 Majors confirmed; 14 Minors. Two sub-claims were refuted (R-E2 `_commit`, R-V5 base.py) and one finding was downgraded (R-V4).

## 2. Verification of every Blocker and Major

### R-1 (R-C1 + R-E1): card build and `pair_finished` outside the pair guard. CONFIRMED, Blocker

- **Code.** The guard at `launch.py:220-245` ends with `except (VidbyteSdkError, OSError, ValueError)`. Three lines then run unguarded:
  - `launch.py:251` computes `files`;
  - `launch.py:252` calls `InfiniteResultCard(...)`;
  - `launch.py:253` calls `launch.journal.pair_finished(...)`.
- **How `files` fails validation.**
  - `files` uses `_text_items(self, "files")` with the default `one_line=True` (`lib/dataclasses/infinite.py:208` → `:55` `item.splitlines() != [item]`).
  - `memory.py:98` records the raw model path.
  - `_note_path` (`workspace.py:272-286`) never checks the path for line breaks.
- **How the journal write fails.** `journal.py:187` writes `json.dumps(record, ensure_ascii=False)` to a UTF-8 handle, and that write raises on a lone surrogate.
- **Own run.** From the worktree, `PYTHONPATH=$(pwd) python $S/v1_card_guard.py`:
  ```
  --- U+2028 in a note path
  launch result: "[tool_error kind=execution_error]\nTool execution failed: Each item of InfiniteResultCard.files must be one line of non-blank text; got 'notes/a\\u2028b.md'."
  b's card reached root: False
  journal: [('run_started', None), ('pair_started', 'root/a'), ('pair_started', 'root/b'), ('pair_finished', 'root/b'), ('run_finished', None)]
  --- U+0085 in a note path
  launch result: "[tool_error kind=execution_error]\nTool execution failed: Each item of InfiniteResultCard.files must be one line of non-blank text; got 'notes/a\\x85b.md'."
  b's card reached root: False
  --- lone surrogate in generator reply
  launch result: "[tool_error kind=execution_error]\nTool execution failed: 'utf-8' codec can't encode character '\\ud83d' in position 182: surrogates not allowed"
  b's card reached root: False
  ```
- **Spec.** INV-29 names "building the card" among the steps whose errors become the pair's own card, and adds "Either way `pair_finished` is written, the pair's card and every sibling's card are returned, and the `launch_subagent` call does not raise". `ConfigurationError` and `UnicodeEncodeError` (a `ValueError`) are both classes INV-29 lists. The EC-41 exception covers a journal write failing "in its own error path". The surrogate failure is on the normal path, and its cause is the encoding choice, not the disk.
- **Existing guard?** None. `InfiniteWorkspace` validates no other property of the path.
- **Calibration.** Blocker. It contradicts INV-29's "every" and the field-guide stage rule, it loses sibling cards, and the unfinished key re-runs the pair (duplicate commits).
- **Smallest fix, tried in memory.**
  - `VFIX=NOTEPATH` adds the `_note_path` splitlines refusal: `89 passed`, and the probe returns `b's card reached root: True` with `pair_finished` for both keys.
  - `VFIX=JOURNAL` drops `ensure_ascii` in the journal only: `89 passed`, and the surrogate case returns both cards.
- **Do not drop `ensure_ascii=False` in `workspace.py:170/329`.** `entries.jsonl` must stay grep-able for non-ASCII text (D-3, AC-15, AC-42); escaping would make `grep café` miss.
- **After both changes no reachable card field can fail validation:**
  - name and key come from validated slugs;
  - status and verdict are enums;
  - summary and review may be any text;
  - entries are ints ≥ 1;
  - dropped items are non-blank and may span lines;
  - files are one line once `_note_path` refuses multi-line paths.
- **Alternative.** The reviewers' structural fix (a second guard with a fallback card) is valid but larger, and it still needs the journal change.

### R-2 (R-C4): case-sensitive protected paths on macOS. CONFIRMED, Major

- **Code.** `workspace.py:284` compares `relative.parts[0]` and `relative.as_posix()` with lowercase constants. `permissions.py:16` resolves with `.resolve()`.
- **Why `resolve()` keeps the caller's case on macOS.** On POSIX, `Path.resolve` is `os.path.realpath`. `C:/Users/422mi/AppData/Local/Programs/Python/Python311/Lib/posixpath.py:448-458`:
  ```
  newpath = join(path, name)
  ...
  if not is_link:
      path = newpath
  ```
  Non-links keep the caller's spelling. APFS is case-insensitive by default, so `Entries.jsonl` opens `entries.jsonl`.
- **Own run (simulation).** `python $S/v6_case_fold.py` replaces `resolve_scoped_path` with posix-style resolution, on this case-insensitive NTFS volume:
  ```
  'Entries.jsonl' -> accepted
  'SEED/brief.md' -> accepted
  '.RUNS/x.jsonl' -> accepted
  entries.jsonl now: 'INJECTED\n'
  seed/brief.md now: 'seed text\nINJECTED\n'
  ```
  It cannot run natively here: the engineering probe showed Windows `resolve()` returns the on-disk case.
- **Spec.** It breaks INV-20 (protected paths) and INV-21 ("Tools never write under `seed/`").
- **Calibration.** Major. It is a guardrail bypass on a mainstream OS, and the only route under a policy that denies EXECUTE (T-2's named control). With the default `allow_all`, bash can already do the same (D-10), so it is not a Blocker.
- **Fix trial.** `VFIX=CASEFOLD`: all three paths are refused, and the pack gives `89 passed`.

### R-3 (R-C3 + R-E7): card bound vs NFR-7. CONFIRMED, Major, needs spec edit

- **Code.** `render` (`launch.py:362`) joins `card.dropped` and `card.files` with no cap. `dropped` items carry the full entry text (`launch.py:249`, `memory.py:115`), and `files` lists every path a child appended to or edited (`memory.py:98, 105`).
- **Own run.** `python $S/v5_ec18_card.py`: EC-12 (no VERDICT line), 5 staged entries at the 60-token cap, 30 appended notes, and summary and review at the cap:
  ```
  card tokens: 1484 | NFR-7 bound 2 x cap = 800 + template
     Summary line tokens: 405
     Review line tokens: 404
     Entries dropped line tokens: 354
     Files written line tokens: 304
  ```
- **Spec.** NFR-7 (P0, "VERY limitied") says a pair adds at most 2 × `INFINITE_CARD_TEXT_MAX_TOKENS` of card text plus the fixed template. INV-4 caps only summary and review, and D-14 makes `dropped` and `files` card fields. So the spec contradicts itself unless the list fields are capped and NFR-7's arithmetic is restated.
- **Fix trial.** `VFIX=CARDCAP` caps each list field at the card cap. The probe stays at 1,484 tokens, because each list is already under 400. Per-field capping bounds the card at a constant (≤ 4 × cap + template), but it cannot meet "2 ×" while summary and review each keep a full cap. Hence **needs: spec edit**.
- **Calibration.** I kept the conformance severity (Major) over engineering's Minor. The `files` list grows with the number of notes appended, up to `max_files` paths, which is the unbounded-growth case the weighted words target, and it happens on the ordinary EC-12 path.

### R-4 (R-E3): replay refused by the context check. CONFIRMED, Major

- **Code.** `launch.py:124` builds `pairs` from unfinished keys only. `launch.py:125` then calls `self._check(cards, len(pairs))` over all cards, and `_check` (`:180-186`) validates every card's tools and `#N` context.
- **Own run.** `python $S/v4_replay.py`:
  ```
  1st launch a: ### Pair a (root/a) | Status: done. Verdict: passed. | ...
  2nd launch a alone (should replay): [tool_error kind=execution_error] | No task was started, because the batch needs a change: Memory entry #1 is not a live entry in entries.jsonl; ...
  3rd launch a + new b: [tool_error kind=execution_error] | No task was started, ... Memory entry #1 is not a live entry ...
  b's generator called: False
  ```
- **Spec adjudication.** Row 20 orders "check the batch" (including "every `#N` context id live") before "split replays". INV-26 says a finished key returns its recorded card, starts no agent, and adds no usage. EC-7's reason for refusing a stale id ("the child works from nothing or from a stale fact") cannot apply to a replay, because no child starts. Part B governs, so the fix is production-only, and no spec edit is needed.
- **Fix trial.** `VFIX=REPLAY` keeps the duplicate check over all cards and runs the other checks over new cards only:
  ```
  2nd launch a alone (should replay): (Replayed: this pair already finished earlier in this run, so it was not run again.) | ### Pair a (root/a) ...
  b's generator called: True
  ```
  The pack gives `89 passed`.
- **Trap.** `pairs` is a dict comprehension, so two new tasks with the same name collapse into one key. The duplicate check must keep running over `cards`, or EC-5/AC-6 regress.

### R-5 (R-V2 + R-C6): S062 offset by rewriting untouched registry code. CONFIRMED, Major, needs test change

- **Own run.** I ran `python lint/run.py --rule S062 --format json` on both trees:
  - export of main: `main 889 ['vidbyte/lib/registries/runtimes.py:51']`;
  - HEAD: `889 ['tests/features/infinite_memory_agent/test_infinite_memory_workspace.py:399']`.
- **Diff.** `git diff origin/main...def85360 -- vidbyte/lib/registries/runtimes.py` joins `f"Unknown runtime type '{runtime_type.value}'. "` and `f"Supported: {cls.supported_runtimes()}"` into one f-string. That message is not part of row 25, which covers only the import and the registry row.
- **Rules.**
  - AGENTS.md: "Do not rewrite untouched code just to make it conform; that belongs in its own pull request."
  - lint/README: "Freeze existing debt while failing any count increase and preserving reductions."
  - S3 records the deviation openly in §17 as an offset.
- **Adjudication.** Conformance said Minor and conventions said Major. I kept Major. The rewrite exists only to hide a new finding from the ratchet, which is the behavior both written rules forbid, and a reviewer reading the diff would ask why an unrelated message was reflowed.
- **Fix.** No production-only fix exists. Reverting `runtimes.py` alone gives S062 890 > 889 (REGRESSED), so the test literal must be joined (**needs: test change**). If the orchestrator declines, the finding should be waived, not "fixed" another way. Raising the baseline is forbidden.

### R-6 (R-C2): EC-18 guidance missing, and the paste is repeated back. CONFIRMED, Major

- **Code.** `InfiniteRememberTool._draft` (`memory.py:165-177`) builds `InfiniteEntryDraft`. Its `_text_field` raises `… must be one line of non-blank text; got {value!r}` (`lib/dataclasses/infinite.py:41-44`), and `refusal()` wraps that message. The cap message at `workspace.py:261` says only "shorten it to one short line".
- **Own run.** `python $S/v5_ec18_card.py`:
  ```
  multi-line log: log 14289 chars; result 14741 chars, 3686 tokens; mentions pointer/note: False
     head: [tool_error kind=execution_error] | Nothing was saved, because the call needs a change: InfiniteEntryDraft.text must be one line of non-blank text; got
  over-cap line: ... result 272 chars, 68 tokens; mentions pointer/note: False
  ```
- **Spec.** EC-18's "User sees: `ToolResult.error` telling it to store a pointer or a note" is not met.
- **Calibration.** Major. It is a Part B row with a stated user-visible behavior, and the repeated paste costs about 3.7k tokens in the root's context, the one the user called "VERY limitied".
- **Fix layer.** The fix belongs in the tool layer. Principle 4 wants record errors to name the bad value, so the record's own message stays as it is.
- **Fix trial.** `VFIX=EC18` gives `89 passed`. The probe shows `result 349 chars, 88 tokens; mentions pointer/note: True`. AC-14's two-line case requires only the rejection template and the quota line, which `refusal()` still adds.

### R-7 (R-V1): new C012 and S061 findings that pass on stale headroom. CONFIRMED, Major

- **Own run.** On main, from `git archive origin/main | tar -x -C $S/base`, then `git init && git add -A` inside the scratch copy only:
  ```
  C012   provider-model-registry-validation         23     24 IMPROVED
  S061   bounded-safe-path                           5      6 IMPROVED
  ```
- **At HEAD:** C012 is `24 RATCHETED` and S061 is `6 RATCHETED`. The new locations are `vidbyte/agents/infinite/settings.py:134` (C012, "no method of InfiniteMemoryAgentSettings checks it against the ProviderModelRegistry model catalog") and `vidbyte/agents/infinite/workspace.py:79` (S061, `copyfile(...)` with a non-literal path). Both rules are `[BLOCKING]`.
- **Main's C012 list** includes `vidbyte/agents/jev/settings.py:132`. The sibling precedent carries the same debt, but it predates the gate, so it is grandfathered.
- **Rule.** lint/README: "baseline.json maps each rule ID to the number of violations that predated its gate … Freeze existing debt while failing any count increase and preserving reductions." The PR does not raise `baseline.json`; it spends a reduction someone else made. I read NFR-6 ("no lint baseline count rises") and §12.4 literally: they are met. The ratchet rule in lint/README is not.
- **Behavior check.** The fix does not make the agent stricter than `BaseAgent` in effect. `BaseAgent(provider="openai", model_name="my-finetune-xyz").run(...)` raises `AgentExecutionError` caused by `ConfigurationError No runner mapping for provider/model 'openai/my-finetune-xyz'`. Validating at construction moves the same refusal earlier, where AGENTS.md principle 4 wants it.
- **Fix proven in a scratch copy of `def85360`** (`$S/head`; the worktree is untouched). Changes: the registry call after `settings.py:165`, the import placed after `vidbyte.lib.errors`, `self.backend = LocalFileSystemBackend()` with `self.backend.copy(...)`, and `import shutil` removed. Then `git init && git add -A` in the copy:
  ```
  S051   modernized-import-and-syntax-hygiene      259    259 RATCHETED
  C012   provider-model-registry-validation         23     24 IMPROVED
  S061   bounded-safe-path                           5      6 IMPROVED
  SDK-LINT: PASS
  89 passed in 2.17s
  ```
  The first attempt put the import directly under `from __future__` and left `import shutil`. That gave `S051 260 259 REGRESSED`, so import placement matters.
- **S061's exemption.** It applies only when the receiver is `<x>.backend` (`lint/rules/s061_bounded_safe_path.py:37-40`). `LocalFileSystemBackend().copy(...)` would still be flagged.
- **Test models.** The pack uses only `openai`/`gpt-4.1`, which passes `validate_provider_model_pair`.

### R-8 (R-E2, plus the colon trigger from R-E9): `_replace` leaks its temp file, and raw errors escape the tools. CONFIRMED, Major (one sub-claim refuted)

- **Code.** `_replace` (`workspace.py:299-307`) has no `try/finally` around `fdopen().write` and `os.replace`. The tool `execute` methods catch only `(ConfigurationError, ToolExecutionError)` (`memory.py:160, 208, 241`).
- **Own run (a) and (b).** `python $S/v2_replace_leak.py`:
  ```
  (a) remember result: "[tool_error kind=execution_error]\nTool execution failed: 'utf-8' codec can't encode character '\\ud83d' in position 49: surrogates not allowed"
  (a) write_note result: '[tool_error kind=execution_error]\nNothing was saved, because the call needs a change: This write would make 5 files, over max_files (4); ...'
  (a) files on disk: ['.entries.jsonl.l473qi2j.tmp', 'entries.jsonl', 'files.jsonl', 'superseded.jsonl']
  (b) remember result: "[tool_error kind=execution_error]\nTool execution failed: [WinError 5] Access is denied: '...\\.entries.jsonl.i3oihqt8.tmp' -> '...'"
  (b) files on disk: ['.entries.jsonl.i3oihqt8.tmp', 'entries.jsonl', 'files.jsonl', 'superseded.jsonl']
  ```
- **Append vs replace on Windows** (inline script):
  ```
  plain append while another process reads: 'a\nb\n'
  os.replace: PermissionError 5
  ```
- **Own run (c), colon path.** `python $S/v3_colon_unc.py`:
  ```
  'notes/standup 10:30.md' -> OSError [WinError 87] The parameter is incorrect: '...\\memory\\notes\\.stand
     tree: ['entries.jsonl', 'files.jsonl', 'notes', 'notes/.standup 10', 'superseded.jsonl']
  ```
  Unlinking the temp does not clean this up (inline script):
  ```
  after mkstemp: ['.standup 10'] | temp path: .standup 10:30.md.po6f3bi_.tmp
  after unlink(temp): ['.standup 10']
  ```
  This is why the fix needs a `:` refusal in `_note_path` as well as the unlink.
- **Spec.**
  - INV-32: a rejected call returns `ToolResult.error`, says what to fix, gives the quota, and writes nothing.
  - §12.4: "never raises out of `execute`".
  - INV-19: caps are counted from disk, so a leaked temp file counts toward them.
  - Row 17 designed plain appends. §17 deviation 5 moved every append to `os.replace`, which creates the Windows failure in (b).
- **Refuted sub-claim.** "One failed commit drops everything staged → catch `OSError`/`ValueError` in `_commit`". INV-29 says an error after the generator returns, committing included, makes the verdict UNCHECKED and drops the uncommitted entries, and "A commit's `ToolExecutionError` is the exception". `_commit` catching only `ToolExecutionError` is therefore spec-conformant.
- **Not required.** Going back to plain appends (engineering's option 3) would avoid (b), but it reintroduces torn-line risk in `entries.jsonl`, which `_entry_lines` refuses. Both are defensible. With (1)+(2) applied, a sharing violation becomes a clean refusal the model can retry.
- **Fix trial.** `VFIX=REPLACE` (unlink in `_replace`; `OSError`/`ValueError` caught in the three write tools) gives `89 passed`. The probe shows no `.tmp` left in either case, both results carry the rejection template and the quota line, and the later `write_note` succeeds: `Saved the file notes/a.md. Quota left: 5 of 5 memory entries and 0 of 1 new files.`

### R-9 (R-V5): comment lines over 72 columns. CONFIRMED for 21 lines, Major; base.py part REFUTED

- **Source.** I found a binding source:
  - Field guide `comment-format.md`: "Wrap every comment line at 72 columns, counting the indent … Check: `awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched." Its Evidence is the owner's review rejection on PR #690.
  - Spec §12.4: "Every multi-line `#` comment is ≤ 72 columns … Source: `comment-format.md`."
- **Own run** (awk over the new modules):
  ```
  vidbyte/agents/infinite/journal.py:132 (73 cols)  ... vidbyte/agents/infinite/launch.py:213 (76 cols) ... vidbyte/lib/dataclasses/infinite.py:128 (73 cols)
  total: 21
  ```
- **Calibration.** It is a field-guide lesson whose stated Check fails. The overruns are only 1–4 columns and change no behavior, so it is Major, not Blocker.
- **base.py refuted.** `vidbyte/agents/base.py:76-77` is 99 columns on main (legacy block). The PR extended it by one clause in the same style, as row 26 instructs. Rewrapping would rewrite untouched code (AGENTS.md), and the field guide says "leave untouched files alone".

### R-10 (R-V3): parameter descriptions are labels with examples. CONFIRMED, Major

- **Source.** Field guide `model-facing-tool-contracts.md:5`: "give the tool and every parameter a consistent 4–5 sentence general description, and omit concrete examples from model-facing prose." S025 states the same contract (`lint/rules/s025_model_facing_description_depth.py:281`). Its header says text built by a method call "is exempted, not flagged". That is a limit of the static analysis, not a waiver of the contract.
- **Spec.** §12.4 and row 7 mention only tool descriptions at 4–5 sentences. Spec silence does not override the field guide (house-style: "the repository wins").
- **Grain of the repo.** I counted sentences per family:
  ```
  infinite_memory param leaves: 19 sentence counts: [1,1,1,1,1,1,1,1,1,2,2,2,2,2,2,2,2,2,2]
  jev_bulk_work param leaves: 1 sentence counts: [4]
  jev_swarm param leaves: 8 sentence counts: [4,4,4,4,4,4,4,4]
  ```
  Every sibling family follows the rule. The reviewer said 18 leaves; I count 19: 8 launch, 5 remember, 3 write_note, 2 edit_file, and 1 drop_entry.
- **Test safety.** Tests pin only leaf names (`test_infinite_memory_contract.py:64-…`) and read text through `prompt_text(leaf)`, so rewriting the text keeps them green.

### R-11 (R-E4): guardrail rules with no test. CONFIRMED, Major, needs test change

- **Own mutation run.** Plugin `$S/vmut.py`, run with `VMUT=<m> PYTHONPATH="C:/…worktree;C:/…s4-verifier" python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider -p vmut`:
  ```
  == V1   89 passed in 1.44s      (InfiniteWorkspace.check_entry is a no-op)
  == V2   89 passed in 1.43s      (edit_file without max_file_tokens and _room)
  == V3   89 passed in 1.48s      (verifier-staged entries stamped by=<pair>/gen)
  == V4   FAILED ...test_a_malformed_entries_line_drops_each_pairs_entries_but_the_run_finishes
          1 failed, 88 passed in 1.63s
  ```
  V4 failing shows the plugin is active.
- **Test plan.** Its "Tests deliberately NOT written" section (`test-plan.md:69-74`) omits only EC-15/EC-16 and the record `__post_init__` unit tests, none of these three rules.
- **Calibration.** Major. These are the user's "deterministic guardrails", and a regression in any of them ships green. Every fix lives in `tests/`, so it needs a test change.

## 3. Minors: what I checked

- **R-12** (`launch.py:290-300`): read directly. No field-guide lesson on call depth: `grep -n -i -E "one level|call chain|helper calls|third|principle 1|flat list"` over the field guide matches only an unrelated pricebook line.
- **R-13**: AC-37's test comment at `test_infinite_memory_verification.py:109` says "The first verifier to start appends line 3, after both generators staged and before either commit". With non-suspending fake runners that ordering needs the yield. No INV orders work across pairs, so the yield is a test-driven artifact. It costs nothing, though, so the fix is rewording the comment, not removing the yield.
- **R-14 to R-21**: each read at the cited line:
  - `memory.py:113` uses `or 'none'`;
  - `settings.py:82` and `:192` hold the literal minimums;
  - `launch.py:4` says "still above the depth cap";
  - `README.md:66` has the trimming sentence;
  - the tests README line 7 says the pack fails;
  - `journal.py:126`, `launch.py:188` and `runtime.py:74` are the R-19 sites;
  - `launch.py:214` has `writer =InfiniteAgentMemory(`;
  - the prompts README rows 68–70 and entries 247/259/276 split the Jev group.
- **R-23**: `agent.py:49` includes `{settings!r}`. The INV-2 test (`test_infinite_memory_contract.py:301`) accepts `"dict" in text`, so dropping the repr keeps it green.
- **R-24**: `python $S/v3_colon_unc.py` → `'//nonexistent-host-s4/share/x.md' -> FileNotFoundError [WinError 53] The network path was not found`. The lookup happens in the untouched `FileSystemPermissions.resolve_scoped_path` (`git diff --stat origin/main...def85360 -- vidbyte/lib/tools/` is empty), so this belongs in a follow-up PR.
- **R-25 [verifier]**: `python $S/v7_locked_file.py`, where a subprocess holds `notes/report.md` with share mode 0:
  ```
  holder: locked
  run raised: AgentExecutionError | cause: PermissionError [Errno 13] Permission denied: '...\\memory\\n
  journal: ['run_started']
  ```
  I kept this as a Minor follow-up rather than a Major. INV-22 promises tolerance of bad *content* only, the trigger needs an outside actor, and the error names the file. The orchestrator may promote it if "Unattended, resumable" should cover unreadable files.

## 4. Severity blind-spot check (step 6)

- **Convention fixes that could break conformance:**
  - R-7's registry validation could have refused models that `BaseAgent` accepts. Checked: `BaseAgent` refuses unknown models at run time anyway, and the pack's model passes.
  - R-10's prompt rewrite could have broken tests. Checked: tests pin only leaf names.
  - R-9 could have pushed a repair agent to rewrap base.py's legacy block, against row 26. Refuted explicitly.
- **Fix interactions:**
  - R-1, R-2, and R-8(3) all edit `InfiniteWorkspace._note_path`. Do them in one edit, and keep it a flat helper (principle 1).
  - R-4's fix must keep the duplicate check over all cards, because the `pairs` dict collapses duplicate names.
  - R-22 and R-25 touch the same `_file_tokens`.
- **New finding:** R-25 (above). I found no further Blocker-class risk in `runtime.py`, `agent.py`, `journal.py`, or the batch path. The stop reason is stored as `.value`; the class lock is held only around synchronous I/O with no `await`; `InfinitePair`'s entry-superseded-between-check-and-start case becomes a FAILED card inside the guard.

## 5. Disagreements adjudicated

| Topic | Positions | Ruling | Evidence |
|---|---|---|---|
| Card bound (R-C3 vs R-E7) | conformance Major, engineering Minor | Major, needs spec edit | 1,484-token card on EC-12; per-field caps cannot meet "2 ×" (`VFIX=CARDCAP`) |
| S062 offset (R-C6 vs R-V2) | conformance Minor, conventions Major | Major, needs test change | AGENTS.md "untouched code" rule plus lint/README; lint JSON on main vs HEAD |
| Call depth (R-V4) | conventions Major; orchestrator expected Minor | Minor (downgraded) | No field-guide lesson; clarity only; one hop to a public static formatter |
| 72-column comments (R-V5) | conventions Major | Major for 21 lines; base.py refuted | `comment-format.md` is binding and its Check fails; base.py is a legacy block |
| Parameter descriptions (R-V3) | conventions Major; S025 exempts Prompts text | Major | Field guide plus sibling families at 4 sentences; S025 exemption is an analysis limit |
| Lint headroom (R-V1) | conventions Major; S3 "no baseline raised" | Major; production-only fix proven | Main counts 23/5; scratch HEAD+fix gives 23/5 and `SDK-LINT: PASS` |
| `asyncio.sleep(0)` (R-C5/R-E5/R-V7) | all Minor; S3 says AC-5 and AC-37 need it | Minor; reword the comment; S3's AC-5 claim is false | `VMUT=V4` fails only AC-37 |
| R-E3 vs row 20 order | engineering: Part B governs | Agreed; production-only fix | INV-26 vs row 20; EC-7's harm cannot occur for a replay |
| R-E2 `_commit` catch | engineering: catch `OSError` in `_commit` | Refuted | INV-29 makes non-`ToolExecutionError` commit errors UNCHECKED |
| R-C4 macOS | conformance Major, reasoning only | Confirmed by source and simulation | `posixpath._joinrealpath` keeps case; `v6_case_fold.py` |

## 6. Commands run (final lines)

- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `89 passed in 2.04s`
- `PYTHONPATH=$(pwd) python lint/run.py` → `S061 RATCHETED: 6 known finding(s)…` / `S062 RATCHETED: 889 known finding(s)…` / `SDK-LINT: PASS`
- Main export (`$S/base`): `python lint/run.py --rule C012` → `C012 IMPROVED 24 -> 23`; `--rule S061` → `S061 IMPROVED 6 -> 5`; `--rule S062` → `S062 RATCHETED: 889`
- Scratch HEAD + R-7 fix (`$S/head`): `python lint/run.py` → `SDK-LINT: PASS`; pack → `89 passed in 2.17s`
- `VFIX=C012|REPLAY|NOTEPATH|JOURNAL|EC18|REPLACE|CARDCAP|CASEFOLD … -p vfix` → `89 passed` each
- `VMUT=V1|V2|V3 … -p vmut` → `89 passed` each; `VMUT=V4` → `1 failed, 88 passed`
- `git status --porcelain` before writing → empty. After writing, only `review.md` and this report should appear.
