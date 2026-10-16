LENS: conformance
VERDICT: SOUND — every finding handed to S5 is fixed as spec r5 specifies (D-33, D-34, D-35, the R-23 `member` rule, the R-3 stale-copy cut), the area suite, the full suite and lint pass with an empty baseline diff, and only two clarity Minors remain, one in a module header and one in spec text.

WHAT THE IMPLEMENTATION GETS RIGHT
- D-33 r5 is one path. All 6 Muse functions reach one `NativeCommandEvidence.require(..., member=MUSE_READ_SKILL_ID_MEMBER)` (`vidbyte/harnesses/native/muse/commands.py:149`). It is fed by `MuseSessionWire.tool_calls` (`muse/wire.py:299`), which reads `history.items` for inline and `history.snapshot.state.items` for snapshot and anchoredSnapshot (`:319`). `none` is command_not_run naming `noneReason` (`:315`), and an unknown mode is protocol_mismatch naming `items`. `MuseHelperRun` has no `transcript` flow, and no export runs for evidence. A 26-case matrix over the pure readers matches every row of D-33, EC-56, EC-79, EC-83 and EC-84.
- D-34 is the narrow change it should be. `remember_thread` has exactly 2 callers: `grok/commands.py:238`, right after `GrokStreamWire.read`, and `muse/commands.py:139`, right after `MuseThreadRun.execute`. Through the repo stand-in, a later defect gives `runtime.error` with the minted `--session-id` named in the message. A missing program still gives `grok.not_installed` with `thread_id=None`. #1036's `run_grok_thread` defect path still gives `thread_id=None`, as `origin/main:hostkit/errors.py:151` does (INV-26).
- D-35 is pure and ordered: `@staticmethod child_problem` at `hostkit/errors.py:90`. It has 3 call sites with their own marker sources: `grok/wire.py:246` (stderr, stdout), `opencode/wire.py:231` (stderr) and `muse/wire.py:277` (no marker). Main's 4 reader copies are untouched. The thread_not_found and run_failed templates use neither `{seconds}` nor `{cap_bytes}`, so no message changed.
- Contract and budget are intact:
  - 68 sorted exports, split 25, 15 and 16 across the three packages; 56 coroutines.
  - 152 `FailureCode` members.
  - 10 new source files, 20 harness classes, 6 records, 6 enums, 0 dependencies and 0 config keys.
  - Every file is under 1,000 lines. The constants file is 842 lines (cap 900) and the records file 598 (cap 600).
  - No new comment line is wider than 72 columns in the 31 changed `vidbyte/*.py` files.
  - The §4 snippet in the acceptance test equals the spec code block: 1,195 characters each, compared byte for byte.

FINDINGS (ranked)
R-C1 [Minor] [comment text] vidbyte/harnesses/native/muse/commands.py:8 — WHAT NOT TO DO item 1 still names "the export", which this module no longer runs
  Evidence: `:8` reads "1. Do not give the evidence read or the export a key". Five lines up, `:5` of the same header says "no `muse export` runs for evidence (spec D-33)". `grep -n 'transcript\|export' vidbyte/harnesses/native/muse/commands.py` hits only `:5` and `:8`. §12.3 row 27 (`spec.md:1166`) asked for the header update, and ROLE IN CODEBASE and ARCHITECTURE NOTE were updated; item 1 was missed.
  Failure: the header contradicts itself. A maintainer reading item 1 infers that this module starts an export child. Behavior is not affected.
  Smallest fix: "1. Do not give the evidence read a key; only the exec child carries META_API_KEY."
  Spec IDs: D-33, §12.3 row 27, INV-23.

R-C2 [Minor] [spec text] docs/spec/harness-thread-helpers-skills/spec.md:1260 — r5 leftovers: §12.6 names the withdrawn `transcript` flow, three Proof cells still say "implementation pending (S5)", and row 27's "No `require_text` call" reads wider than meant
  Evidence:
    - `spec.md:1260` says "Muse's row 27 on row 26 (`tool_calls`, `transcript`)". But `spec.md:1165` (row 26, r5) removes that flow, and `MuseHelperRun` has no `transcript` (the verifier's `repro_muse_d33_rule.py` raises `AttributeError: ... no attribute 'transcript'`).
    - `spec.md:355` (AC-17), `:372` (AC-34) and `:373` (AC-35) still end "*implementation pending (S5)*". `reports/S5-repair-1.md:48-50` records `cdbbd72b`, `3fbe9568` and `f8c00aa7`, and the named tests pass.
    - `spec.md:1166` says "No `require_text` call … remain in this module". Yet `muse/commands.py:99` keeps `RecordFieldValidator.require_text(...)`, the D-25 argument check. §12.4 (`spec.md:1194`) scopes the rule correctly to `MuseCommandRun`, and that version holds.
  Failure: the traceability column misstates status, and the dependency note names a flow that no longer exists. Read literally, row 27 would flag a correct D-25 check.
  Smallest fix (spec text, S1 or orchestrator):
    - drop "`, `transcript`" at `:1260`;
    - replace the three pending markers with "implemented in `<sha>`";
    - in row 27, write "No `NativeCommandEvidence.require_text` call".
  Spec IDs: §12.6, §12.3 row 27, AC-17, AC-34, AC-35, D-25.

VERIFIED CLAIMS:
- R-1 fixed. Comparing comment lines over 72 columns between 578c88bb and origin/main for all 31 changed `vidbyte/*.py` files prints `files=31 new_wide_comment_lines=0`.
- R-2 fixed (D-33 r5). `d33_paths.py`, for each of inline, snapshot and anchoredSnapshot:
  - `read_skill id=plan` → EVIDENCE OK;
  - `create_goal` → OK;
  - text only (skill and goal) → `muse.command_not_run thread_id_ok=True`;
  - `bundled:plan-extra` → command_not_run;
  - args as an object → OK;
  - args not JSON → command_not_run.

  Other modes and shapes:
  - `none` → command_not_run naming `noneReason` and `historyBudget`;
  - `pagedView` → `muse.protocol_mismatch` naming `items`;
  - anchored with items only in `history.items` → command_not_run (fails closed);
  - inline with `items` null → protocol_mismatch naming `items`;
  - no history → protocol_mismatch naming `history`.

  `repro_muse_goal_anchored.py`: all 4 cases → `muse.command_not_run` with an id.
- R-2 claim check. The verifier's `repro_muse_evidence_id.py` case B RETURNS, which is correct under r5: the stand-in's anchored `state.items` keeps the call, so the patched export mkdir is never reached (checked against `fake_harness_helpers.muse_read`). Case A raises `muse.launch_failed` with `error.thread_id` set. `repro_muse_d33_rule.py` raises AttributeError `transcript`, as expected because r5 deleted the flow.
- R-3 fixed (`grok/helpers.py:155-156`). `search_dupe.py`: list → `[('T1','write the docs',...)]`; search `'LOGIN'` → `[]`.
- R-4 fixed by the granted fixture `228b2a9e` (conftest sandbox delenv). The area suite passes with `DEEPSEEK_API_KEY` set.
- R-5 fixed (D-34):
  - `s4c-inv29/repro.py`: malformed → `GROK_PROTOCOL_MISMATCH` with the minted id; wrong agent and missing → `COMMAND_NOT_RUN` with an id.
  - `repro_grok_plan_evidence_id.py`: `grok.protocol_mismatch`, and the id equals the argv `--session-id`.
  - `d34_paths.py`, my own AC-35 runtime.error probe, which has no test in the pack:
    - `[1 goal, defect in evidence] runtime.error thread_id==minted: True named_in_message: True`
    - `[2 missing program] grok.not_installed thread_id=None`
    - `[3 #1036 run, defect] runtime.error thread_id=None`
- R-6 fixed (D-35), with the call sites above. The order is timed_out, then stdout_truncated, then marker plus failed exit, then failed exit, then None, using `NATIVE_SUCCESS_EXIT_CODE` (`hostkit/errors.py:89-104`).
- R-10 fixed (`grok/commands.py:257-258`). The `else:` narrows inline, and with no command the check fails closed with `tools=()`. S009 stays at 350/350.
- R-11 fixed in docs only:
  - the enums header names `_generate_next_value_`;
  - the README hostkit sentence names "listing order and the command evidence check";
  - `muse/children.py` cites `#1036 INV-9` and `#1036 EC-34`;
  - A009 is clean.
- R-15 fixed (`lib/dataclasses/validation.py:198-199`). `OverflowError` from `astimezone(UTC)` becomes the field's `ConfigurationError`.
- R-16 fixed. The opencode next step equals the §12.4 text, and its helper_surface pin is green.
- R-17 fixed (`muse/helpers.py:347-350`). `FileNotFoundError` gives protocol_mismatch (`MUSE_EXPORT_FILE_MISSING_DETAIL`). `OSError` gives protocol_mismatch with `MUSE_EXPORT_FILE_UNREADABLE_DETAIL`, naming the path and the error type.
- R-21, trivial part, fixed. `# @intent grok-delete-is-checked-on-disk` at `grok/helpers.py:222` and `folder = found.path.parent` at `:227` now sit inside `delete` (def `:215`). The A002 count improved: 605/703.
- R-23 fixed (`hostkit/evidence.py:69-82`). With `member` set, a call counts only if `json.loads` gives a dict whose `member` value equals the fragment; a ValueError counts as no match. Grok passes no member, so its substring rule is unchanged. `repro_muse_skill_prefix.py` → `muse.command_not_run`.
- R-7 (spec text) holds. AC-22, NFR-5 and §11 say `SDK-LINT: PASS` (`spec.md:360`, `:505`, `:1023`).
- No regression in the repair delta `462e6d45..578c88bb`:
  - main's 4 reader copies are untouched (`GrokWire.read`, `MuseWire.read_answer`, `MuseExecOutput.read`, `OpencodeWire.read`);
  - `from_configuration_error` and `from_unexpected` keep main's signatures;
  - no source-fix commit touched `tests/`;
  - only S2 commits (`5180083f`, `228b2a9e`, `2d61818e`) touched `tests/features/harness_threads`, within the granted edits.
- INV-15 holds. The new member name is the constant `MUSE_READ_SKILL_ID_MEMBER = "id"` (`lib/constants/native_threads.py:406`). No literal was added to the native modules, and the static-policy test passes.
- Held, both prosecution and defense:
  - INV-1, 2, 5, 7, 8, 15, 22, 26, 29;
  - AC-1, 17, 34, 35;
  - EC-17, 56, 61, 79, 82-85;
  - NFR-5, NFR-6, NFR-9;
  - §8.4, the §12.3 file list, §12.4, and the §14 Never items (no key in any helper or evidence child, no text evidence, no export for Muse evidence, no new dependency or config key).
- Merge status. origin/main is now `f7f32b19`, one commit (#1160) past the merge base `8da41971`. It touches only `vidbyte/agents/runtime.py` and `tests/test_prompt_sits_at_run_boundary.py`, which do not overlap this branch's files, so there is no conflict and no merge is requested.

COMMANDS RUN:
- `"$PY" -m pytest -p no:cacheprovider -q tests/features/harness_threads` (DEEPSEEK set) → `1025 passed, 3 skipped in 88.53s (0:01:28)`
- `"$PY" lint/run.py` → exit 0, `SDK-LINT: PASS`. A002 605/703 IMPROVED; C002, S009, S024, S008 and A001 RATCHETED; S052 and A009 CLEAN; S064 RATCHETED at 4.
- `git diff origin/main...578c88bb -- lint/baseline.json | wc -l` → `0`
- the comment-width loop (awk `length($0) > 72 && $0 ~ /^[ \t]*#/`, head vs origin/main, `comm -23`) → `files=31 new_wide_comment_lines=0`
- `"$PY" scratchpad/s5rr/d33_paths.py` → the 26 lines summarized under R-2
- `"$PY" scratchpad/s5rr/d34_paths.py <worktree> <scratch>` (scratch HOME and USERPROFILE, repo stand-in only) → the 3 lines under R-5
- the verifier's repros under scratch HOME and USERPROFILE: `repro_muse_evidence_id.py`, `repro_muse_d33_rule.py`, `repro_muse_goal_anchored.py`, `s4c-inv29/repro.py`, `repro_grok_plan_evidence_id.py`, `search_dupe.py`, `repro_muse_skill_prefix.py` → outputs as quoted above
- `grep -rn 'remember_thread\|child_problem(' vidbyte/` → 2 and 3 call sites, as listed
- `git show origin/main:vidbyte/harnesses/native/hostkit/errors.py | grep -n -A12 'def from_unexpected'` → main uses `request.thread_id` only (`:151`)
- `git log --oneline 8da41971..origin/main` → `f7f32b19 ... (#1160)`. The files it touches do not overlap this branch's (`comm -12` is empty).
- `"$PY" -m pytest -p no:cacheprovider -q -x` (full suite at HEAD e1e10861 with scratch HOME and USERPROFILE and `PYTHONDONTWRITEBYTECODE=1`; it deselects the known Windows-flaky MCP stdio test) → `6631 passed, 17 skipped, 1 deselected in 135.73s (0:02:15)`. Afterwards `git status --short` shows only this report.
