# S2 test author: S4 additions for the InfiniteMemory agent

STATUS: DONE. Nine new tests (18 cases) were added to the pack's subject modules for the confirmed S4 findings, bound to spec r5 at HEAD `8d6c230a`:

- Four R-11 cases pass at HEAD. Each fails under its matching mutant.
- Fourteen regression cases (R-1, R-3, R-4, R-6, R-8) fail at HEAD for the reason the review gives, and pass under the review's proposed fixes.

R-5's literal join and R-18's README sentence are done. No assertion changed and no production file was touched. The tests and test-plan are commit `9af96d42`.

## Inventory

| Test (module) | Cases | Finding → spec IDs | At HEAD |
|---|---|---|---|
| `test_a_pair_whose_card_or_record_cannot_be_written_as_given_still_finishes_beside_its_sibling` (delegation) | 3: `u2028-in-a-note-path`, `u0085-in-a-note-path`, `lone-surrogate-in-the-reply` | R-1 → INV-29, INV-32 | RED |
| `test_an_unchecked_card_with_long_dropped_and_files_lists_stays_inside_the_nfr7_bound` (delegation) | 1 | R-3 → NFR-7 (r5), INV-4, EC-12 | RED |
| `test_a_finished_pair_replays_after_its_context_entry_was_superseded_and_new_pairs_still_run` (delegation) | 1 | R-4 → INV-26, INV-9 | RED |
| `test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages` (verification) | 1 | R-11 → INV-17, INV-15, INV-32 | GREEN |
| `test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key` (verification) | 1 | R-11 → INV-16 | GREEN |
| `test_edit_file_refuses_an_edit_that_would_pass_a_cap_and_changes_nothing` (workspace) | 2: `note-over-max-file-tokens`, `workspace-over-max-tokens` | R-11 → INV-19, INV-32, AC-17 | GREEN |
| `test_a_memory_write_that_fails_on_disk_is_a_refusal_and_leaves_no_temp_file` (workspace) | 6: `remember`, `write_note`, `edit_file` × `replace-fails`, `lone-surrogate` | R-8 → INV-32, INV-19, §12.4 | RED |
| `test_a_note_path_with_a_colon_is_saved_or_refused_without_leaving_stray_files` (workspace) | 1 | R-8 → INV-32, INV-19, INV-20 | RED on NTFS; green on POSIX |
| `test_remember_tells_the_model_to_keep_a_long_paste_in_a_note_or_a_pointer` (workspace) | 2: `multi-line-log`, `one-line-over-the-cap` | R-6 → EC-18, INV-17, INV-32 | RED |

Edits that are not assertions:

- **R-5.** `test_map_labels_and_usage_read_the_disk_and_never_fail_on_bad_lines` now passes one string literal where it passed three adjacent ones. An AST comparison against HEAD reports `identical value: True`, and S062 drops from 889 to 888 (`IMPROVED`). S5 can now restore `vidbyte/lib/registries/runtimes.py`.
- **R-18.** README line 7 now says what the pack covers.
- **Headers and docs.** The three module headers list the new tests and finding IDs. In `FEATURE.md`, the failure inventory gains nine lines, the historical-regressions entry covers S4, and R-2 is added under omitted strategies. The README's File Index and Logs are updated too.

No fixture, conftest, or shared helper changed.

## Red at HEAD (exact, `--tb=line`)

```
PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider  →  14 failed, 93 passed
R-1 u2028   launch_subagent failed instead of returning both cards: "[tool_error kind=execution_error]\nTool execution failed: Each item of InfiniteResultCard.files must be one line of non-blank text; got 'notes/acme\u2028prices.md'."
R-1 u0085   ... got 'notes/acme\x85prices.md'.
R-1 surr.   ... Tool execution failed: 'utf-8' codec can't encode character '\ud83d' in position 185: surrogates not allowed
R-3         the card is 3467 tokens, over the NFR-7 bound of 1642
R-4         relaunching the finished pair a was refused: [tool_error kind=execution_error] ... Memory entry #1 is not a live entry
R-8 x3 OS   <tool> let the failed write out as a raw error: "...Tool execution failed: [Errno 13] Access is denied: '...entries.jsonl' / '...notes\\prices.md'"
R-8 x3 VE   <tool> let the failed write out as a raw error: "...Tool execution failed: 'utf-8' codec can't encode character '\ud83d' ... surrogates not allowed"
R-8 colon   the failed write escaped as a raw error: "...Tool execution failed: [WinError 87] The parameter is incorrect: '...notes\\.standup 10:30.md.<x>.tmp' -> ..."
R-6 x2      the refusal does not tell the model to store a pointer or a note
```

## Mutation proof (R-11)

The four R-11 cases are selected with `-k "when_it_stages or verifiers_own_key or edit_file_refuses_an_edit"`. Each line gives the plugin, then the result:

```
HEAD (no plugin)                          4 passed
VMUT=V1  (vmut.py, check_entry no-op)     1 failed: test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages; 3 passed
VMUT=V2  (edit_file without caps)         2 failed: test_edit_file_refuses_an_edit_that_would_pass_a_cap_and_changes_nothing[note-over-max-file-tokens], [workspace-over-max-tokens]; 2 passed
VMUT=V3  (every pair entry by=/gen)       1 failed: test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key; 3 passed
VMUT=V4  (no yield; not an R-11 rule)     4 passed
MUT=M1   (mutplug.py)                     1 failed: ..._when_it_stages; 3 passed
MUT=M2                                    2 failed: both edit_file cases; 2 passed
MUT=M3                                    1 failed: ..._verifiers_own_key; 3 passed
S2MUT=E1 (s2mut.py, max_file_tokens off)  1 failed: [note-over-max-file-tokens] only; 3 passed
S2MUT=E2 (s2mut.py, _room off)            1 failed: [workspace-over-max-tokens] only; 3 passed
S2MUT=S1 (s2mut.py, staged list ignored)  1 failed: ..._when_it_stages ("Staged as s2"); 3 passed
```

Invocation: `VMUT=<m> PYTHONPATH="<worktree>;<scratchpad>/s4-verifier" python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider -p vmut -k ...`. `mutplug` runs from `s4-engineering`, and `s2mut` from `s2-additions`.

## The red tests pin behavior, not one fix

Each VFIX fix in the verifier's `vfix.py` turns only its own new tests green:

| Fix | Tests it turns green |
|---|---|
| NOTEPATH | the two R-1 path cases |
| JOURNAL | the R-1 surrogate case |
| CARDCAP | R-3 |
| REPLAY | R-4 |
| REPLACE | the six R-8 write cases |
| EC18 | R-6 multi-line |

Under any one fix, every other new red test stays red. My scratch plugin `s2fix.py` (`S2FIX=ALL`) applies all six fixes together. It also adds the two the review described but did not code: the advice on the over-cap message (R-6) and the colon refusal in `_note_path` (R-8 fix 3). With all of them in place, the whole pack gives `107 passed`.

Scratch files are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/316f126c-6db0-45d5-b506-cdb76c0921d5/scratchpad/s2-additions/`.

## Gates

- `python lint/run.py` gives `SDK-LINT: PASS`:
  - S062 `888 889 IMPROVED` (down by one);
  - S041 `0 0 CLEAN` and S047 `0 0 CLEAN`;
  - A001 `642 642 RATCHETED`.

  `--all` lists no finding in the pack for A001, A002, S001, S020, S041, S047 or S062.
- `ruff check --select F,E9,B,ASYNC,DTZ tests/features/infinite_memory_agent` reports `All checks passed!`.
- `PYTHONPATH=$(pwd) python scripts/run_ci.py` passes hygiene, lint, compileall and the write-path checks. Its pytest stage then gives `14 failed, 5266 passed, 14 skipped`. All 14 failures are the intended red tests, and none is outside the pack.

## Judgment calls

1. **R-1 does not hard-require a FAILED or UNCHECKED card for the path trigger.** The review's recommended fix (`_note_path` refuses the path) gives a normal `passed` card, so requiring UNCHECKED would reject that fix. The test instead pins INV-29's promise for any fix: every key gets `pair_finished`, both cards return, and `launch_subagent` does not error. It then accepts the two spec-conformant outcomes:
   - the path is refused at write time, with the quota line and no file left;
   - the path is accepted, and the card is `unchecked` with status `done`.
2. **R-1 uses U+2028 and U+0085, not `\n`.** Windows refuses `\n` in a file name at the OS level, so on this host a newline path never reaches the card and becomes R-8's raw OSError instead. A newline case would therefore be green here and red on POSIX.
3. **R-8 adds the colon case (trigger c).** It is backed by INV-32 ("writes nothing") and INV-19. It is red only on NTFS. On POSIX the colon is legal, and the test then requires an exact save. With `VFIX=REPLACE` alone it stays red, because unlinking the temp leaves the NTFS stream base file. That is the review's reason for fix (3).
4. **R-8's lone-surrogate cases require a refusal.** Neither silent success nor sanitizing passes. Both INV-32 and the review's REPLACE fix point to a refusal.
5. **R-8 fault injection.** `os.replace` is patched for the test's duration with a one-shot failure that fires only for the tool's target file, and the test asserts that the fault fired. An implementation whose atomic swap does not call `os.replace` would fail that precondition rather than pass silently. `Path.replace` does call it.
6. **R-3's bound.** It is the sum of the following, counted with `TokenEstimate`:
   - the literal text of the `result_card` template (via `string.Formatter().parse`);
   - the short fields: `a`, `root/a`, `done`, `unchecked`, and `-` for the empty entries field;
   - 4 × (`INFINITE_CARD_TEXT_MAX_TOKENS` + the marker's tokens).

   Because `ceil` is subadditive, a card whose four fields are each cut to the cap plus the marker always fits. The test also requires exactly four markers, and that the journal card keeps every dropped entry and path.
7. **R-6 was written,** because it is deterministic here and backed by EC-18, as the brief allows. The prescribed commit subject omits R-6, so the subject was kept verbatim and R-6 is named in the commit body.
8. **R-2 was not written.** Windows `resolve()` returns the on-disk case of every existing protected name, so the test would pass at HEAD for the wrong reason. Making it fail here needs a fake `resolve_scoped_path`, which is not a seam this pack fakes. It is listed under "Tests deliberately NOT written" in test-plan.md and in FEATURE.md.
9. **R-13's alternative was not done.** Dropping the yield and gating AC-37 with `Gate(2)` was not granted, and it would change an existing test's script.

## Notes for S5

- Every refused memory write must render `memory_rejected_prompt` and the quota line. A failed write must leave no `*.tmp` file under the workspace, and the snapshot taken before the call must equal the one after it.
- A colon note path must be refused before any temp file is created, or the stray NTFS file stays.
- The R-1 surrogate test reads the journal as strict UTF-8. Writing records with `ensure_ascii` default (VFIX=JOURNAL) satisfies it, while writing with `surrogatepass` would not.
- In the R-4 test, `a` and `b` must each start and finish exactly once. A replayed card comes back under `replayed_label`, and cards return in task order.
- EC-18's refusal needs the word "pointer" or "note" outside the rejection template and the quota line. This applies to the multi-line case and to the over-cap case alike.

## Commits

- `9af96d42` test(infinite-memory): add S4 regression and mutation-killing tests [R-1, R-3, R-4, R-5, R-8, R-11, R-18]
- (this report) docs(spec): record S2 test additions for S4 findings

## Re-review additions (R-26, R-27)

After S5 fixed R-1 to R-13, all 107 cases passed at HEAD `52eaafe8`. The S5 re-review (`reports/S5-rereview-verifier.md`) confirmed two Majors that those cases missed. Four tests were added; no existing assertion changed.

| Finding | Spec IDs | Test | At `52eaafe8` | Under `apply_fixes.py both` |
|---|---|---|---|---|
| R-26 | INV-21, §9.2, AC-30 | contract → `test_a_read_only_seed_is_copied_again_each_time_an_agent_attaches` | RED | GREEN |
| R-27 | INV-19, INV-32, INV-18 | workspace → `test_a_supersede_whose_new_text_cannot_be_written_changes_neither_entry_file` | RED | GREEN |
| R-27 | INV-20, INV-19, INV-32 | workspace → `test_a_new_note_whose_description_cannot_be_written_leaves_no_note_and_keeps_the_allowance` | RED | GREEN |
| R-27 | INV-16, INV-29, INV-17 | verification → `test_an_entry_text_that_cannot_be_written_never_costs_the_pair_its_verdict_or_other_entries` | RED | GREEN |

Red at HEAD (`--tb=line`, whole pack `4 failed, 107 passed`):

```
R-26:            shutil.py:258: PermissionError: [Errno 13] Permission denied: '...\project\memory\seed\brief.md'
R-27 supersede:  a refused supersede changed ['superseded.jsonl'] although the model was told nothing was saved
R-27 new note:   a refused new note changed ['notes/a.md'] although the model was told nothing was saved
R-27 pair:       an unwritable staged entry turned the verdict into 'unchecked':
                 "'utf-8' codec can't encode character '\\ud83d' in position 301: surrogates not allowed"
```

Green under the trial fix. `git archive HEAD` was extracted to the S2 scratch folder `s2-additions/fix-rr` (LF, as `apply_fixes.py` asserts), the four edited test modules were copied in, and `python $V/apply_fixes.py <dir> both` was run. With `PYTHONPATH=<dir>`, `-k "read_only_seed or cannot_be_written"` gives `7 passed` (the 4 new tests plus the 3 R-1 cases the filter also matches), and the whole pack gives `111 passed`.

Gates: `python lint/run.py` gives `SDK-LINT: PASS` (`S062 889 889`, `S041 0 0`, `S047 0 0`, `A001 642 642`). `ruff check --select F,E9,B,ASYNC,DTZ` on the pack is clean. The full suite gives `4 failed, 5280 passed, 14 skipped`, and the 4 failures are the new tests. `ruff format --check` reports 8 pack files, the same 8 it reports at HEAD; it is not part of the gate.

### Judgment calls

1. **R-26 uses three builds, not two.** Before the third build the source is edited and made read-only again. A fix that skipped an identical copy would pass two builds, but the third fails it, because the old read-only copy must be overwritten with new bytes. A `finally` block makes every file under `tmp_path` writable again, so cleanup works on Windows.
2. **The R-27 supersede case sends the refused call twice.** At HEAD the first refusal already changes `superseded.jsonl`, and the second would duplicate #1 there. The test compares the snapshot before the first call with the one after the second, then requires a clean supersede to move #1 exactly once.
3. **The R-27 new-note case makes only the description unwritable.** The note's own text is valid, so the failure can only come from `files.jsonl`. The test also proves the new-file allowance (1) stays unspent: the clean retry creates the note, and a second new note is then refused.
4. **The pair case accepts either fix.** A lone-surrogate entry may be refused when staged (an error with the quota line) or listed as `s2` in `dropped` at commit. Either way the verdict must stay `passed` and both valid entries must commit, matching the card's ids. The case was cheap and deterministic, so it was written rather than deferred.
5. **The lone surrogate is written as a `\ud83d` escape in the source.** No raw surrogate or line-separator character is in any edited file. A provider's escaped `"\ud83d"` decodes to this value, so the model can send it.

### Not written

- **R-29 (a Windows lock on the second file).** The re-review downgraded it to a Minor follow-up and left its fix open. Holding the lock needs a second file handle from the test, which is a filesystem fake this pack was not granted. The test would also pin one fix before either is chosen. It is listed under "Tests deliberately NOT written" in test-plan.md.
- **R-28.** It is a spec and documentation finding, with nothing to assert.

### Notes for S5

- The R-26 copy must match the source byte for byte after every attach, including after the source changes while both are read-only.
- Every R-27 refusal must render `memory_rejected_prompt` and the quota line, and leave the snapshot unchanged. Check that the text can be encoded before the first of the two writes, not between them.
- For a pair, an unwritable staged entry must not raise out of the commit. Refuse it at stage time, or drop it with a reason in `dropped`.

### Commits

- `11b19a7d` test(infinite-memory): add regression tests for re-review findings [R-26, R-27]
- (this section) docs(spec): record S2 test additions for re-review findings
